#!/usr/bin/env python3
"""Order-flow data: download Databento trades per day, then build 1-minute flow and 5-minute footprint Parquet.

    python3 tools/build_flow.py download --days days.csv [--symbols NQ.v.0 ES.v.0] [--start 09:30 --end 11:35]
    python3 tools/build_flow.py build [--symbols NQ.v.0 ES.v.0]

download: GLBX.MDP3 schema 'trades', continuous front contract by volume, one request per New York day (days.csv has a
    'day' column), window --start..--end New York time. Files go to data/raw/<SYM>/<YYYY-MM-DD>.dbn.zst (git-ignored);
    a day whose file exists is skipped, so a re-run is never billed twice. Quote first with the metadata cost endpoint
    (the 876 ORB v1.4 trade days, 09:30-11:35: NQ $146.94, ES $160.88).
build: from the raw files, per symbol, into data/flow/ (git-ignored):
    <SYM>_flow_1m.parquet      New York minute (bar open time): buy, sell and unclassified volume, delta = buy - sell,
                               trade count, cum_delta = cumulative delta since 09:30 that day, volume, cum_volume
    <SYM>_footprint_5m.parquet 5-minute bar (open time) x price: buy and sell volume
    Aggressor side is CME's flag as carried by Databento: side 'B' = buy aggressor, 'A' = sell aggressor, 'N' = none
    (unclassified: counted in volume and in unclassified, not in delta).
"""
import os, sys, time, pathlib
import pandas as pd

TZ = "America/New_York"
ROOT = pathlib.Path(__file__).resolve().parent.parent
RAW, FLOW = ROOT / "data" / "raw", ROOT / "data" / "flow"


def opt(k, d):
    return sys.argv[sys.argv.index(k) + 1] if k in sys.argv else d


def symbols():
    if "--symbols" in sys.argv:
        i = sys.argv.index("--symbols") + 1
        out = []
        while i < len(sys.argv) and not sys.argv[i].startswith("--"):
            out.append(sys.argv[i]); i += 1
        return out
    return ["NQ.v.0", "ES.v.0"]


def download():
    import socket
    import databento as db
    from concurrent.futures import ThreadPoolExecutor
    socket.setdefaulttimeout(180)          # a stalled connection would otherwise hang a worker forever
    c = db.Historical(os.environ["DATABENTO_API_KEY"])
    days = pd.read_csv(opt("--days", "days.csv")).day.astype(str).tolist()
    t0, t1 = opt("--start", "09:30"), opt("--end", "11:35")

    stop = []                              # set on 402: the account has no budget left, every later request would fail

    def one(job):
        sym, d = job
        path = RAW / sym.split(".")[0] / f"{d}.dbn.zst"
        if path.exists():
            return "skip"
        if stop:
            return "not attempted (no budget)"
        path.parent.mkdir(parents=True, exist_ok=True)
        s = pd.Timestamp(f"{d} {t0}", tz=TZ).tz_convert("UTC").isoformat()
        e = pd.Timestamp(f"{d} {t1}", tz=TZ).tz_convert("UTC").isoformat()
        tmp = path.with_suffix(".part")
        for k in range(5):
            try:
                c.timeseries.get_range(dataset="GLBX.MDP3", symbols=[sym], stype_in="continuous", schema="trades",
                                       start=s, end=e, path=str(tmp))
                tmp.rename(path)
                return "ok"
            except Exception as ex:
                err = ex
                print(f"retry {sym} {d}: {str(ex)[:120]}", flush=True)
                if "402" in str(ex):
                    stop.append(d)
                    return f"FAIL {sym} {d}: no budget (402), stopping"
                time.sleep(3 + 5 * k)
        return f"FAIL {sym} {d}: {err}"

    jobs = [(s, d) for s in symbols() for d in days]
    with ThreadPoolExecutor(int(opt("--threads", "3"))) as ex:
        res = list(ex.map(one, jobs))
    print(pd.Series([r if not r.startswith("FAIL") else "fail" for r in res]).value_counts().to_dict(), flush=True)
    for r in res:
        if r.startswith("FAIL"):
            print(r)


def build():
    import databento as db
    FLOW.mkdir(parents=True, exist_ok=True)
    for sym in symbols():
        root = sym.split(".")[0]
        files = sorted((RAW / root).glob("*.dbn.zst"))
        one_m, fp = [], []
        tot = dict(B=0, A=0, N=0)
        for f in files:
            df = db.DBNStore.from_file(str(f)).to_df(price_type="float", pretty_ts=True, map_symbols=False)
            if df.empty:
                continue
            df.index = pd.DatetimeIndex(df.ts_event).tz_convert(TZ)     # exchange event time, not receive time
            side, size = df.side.astype(str), df["size"].astype(float)
            for k in tot:
                tot[k] += size[side == k].sum()
            x = pd.DataFrame({"buy": size.where(side == "B", 0.0), "sell": size.where(side == "A", 0.0),
                              "unclassified": size.where(side == "N", 0.0), "volume": size, "trades": 1.0},
                             index=df.index)
            m = x.resample("1min", label="left", closed="left").sum()
            m = m[m.volume > 0]
            m["delta"] = m.buy - m.sell
            m["cum_delta"] = m.delta.cumsum()                    # one file = one New York day from 09:30
            m["cum_volume"] = m.volume.cumsum()
            one_m.append(m)
            b5 = df.index.floor("5min")
            f5 = pd.DataFrame({"ts": b5, "price": df.price.to_numpy(), "buy": x.buy.to_numpy(), "sell": x.sell.to_numpy()})
            fp.append(f5.groupby(["ts", "price"], as_index=False)[["buy", "sell"]].sum())
        m = pd.concat(one_m).astype({"trades": "int64"})
        m.index.name = "ts"
        m.to_parquet(FLOW / f"{root}_flow_1m.parquet")
        pd.concat(fp, ignore_index=True).to_parquet(FLOW / f"{root}_footprint_5m.parquet", index=False)
        v = sum(tot.values())
        print(f"{root}: {len(files)} days, {len(m):,} minute rows, volume {v:,.0f}; buy {tot['B'] / v:.2%}, "
              f"sell {tot['A'] / v:.2%}, unclassified {tot['N'] / v:.3%}")


if __name__ == "__main__":
    {"download": download, "build": build}[sys.argv[1]]()
