#!/usr/bin/env python3
"""Extend data/bars/<SYM>_1m.parquet (and rebuild <SYM>_5m) with Databento GLBX.MDP3 ohlcv-1m, continuous front by volume.

    DATABENTO_API_KEY=... python3 tools/extend_bars.py --end 2026-10-09 [--max-cost 10] [--symbols MNQ ES] [--quote]

Starts one minute after the last bar on disk. Quotes every symbol with the cost endpoint first and downloads nothing if
the total is at or above --max-cost (USD). --quote prints the quote and stops. 5m bars are rebuilt from the whole 1m
file exactly as tools/build_bars.py does (stamped with their open time).
"""
import os, sys, pathlib
import databento as db, pandas as pd

ROOT = pathlib.Path(__file__).resolve().parent.parent
BARS, RAW = ROOT / "data" / "bars", ROOT / "data" / "raw"


def opt(k, d):
    return sys.argv[sys.argv.index(k) + 1] if k in sys.argv else d


def symbols():
    if "--symbols" not in sys.argv:
        return ["MNQ", "ES"]
    i, out = sys.argv.index("--symbols") + 1, []
    while i < len(sys.argv) and not sys.argv[i].startswith("--"):
        out.append(sys.argv[i]); i += 1
    return out


c = db.Historical(os.environ["DATABENTO_API_KEY"])
end = pd.Timestamp(opt("--end", pd.Timestamp.now("UTC").strftime("%Y-%m-%d")), tz="UTC")
jobs = []
for sym in symbols():
    last = pd.read_parquet(BARS / f"{sym}_1m.parquet", columns=["close"]).index[-1]
    start = (last + pd.Timedelta(minutes=1)).tz_convert("UTC")
    kw = dict(dataset="GLBX.MDP3", symbols=[f"{sym}.v.0"], stype_in="continuous", schema="ohlcv-1m",
              start=start.isoformat(), end=end.isoformat())
    cost = c.metadata.get_cost(**kw)
    print(f"{sym}: {start} -> {end}  ${cost:.2f}")
    jobs.append((sym, kw, cost))
total = sum(j[2] for j in jobs)
print(f"total ${total:.2f} (cap ${float(opt('--max-cost', 10)):.2f})")
if "--quote" in sys.argv or total >= float(opt("--max-cost", 10)):
    sys.exit(0 if "--quote" in sys.argv else 1)

for sym, kw, _ in jobs:
    path = RAW / f"{sym}_ohlcv1m_ext_{kw['start'][:10]}.dbn.zst"
    path.parent.mkdir(parents=True, exist_ok=True)
    c.timeseries.get_range(**kw, path=str(path))
    new = db.DBNStore.from_file(str(path)).to_df(price_type="float", pretty_ts=True, map_symbols=False)
    new = new[["instrument_id", "open", "high", "low", "close", "volume"]]
    new.index = new.index.tz_convert("America/New_York"); new.index.name = "ts"
    old = pd.read_parquet(BARS / f"{sym}_1m.parquet")
    df = pd.concat([old, new[new.index > old.index[-1]]])
    df.to_parquet(BARS / f"{sym}_1m.parquet")
    b5 = df.resample("5min", label="left", closed="left").agg(
        {"instrument_id": "last", "open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
    ).dropna(subset=["open"])
    b5["instrument_id"] = b5["instrument_id"].astype("uint32")
    b5.to_parquet(BARS / f"{sym}_5m.parquet")
    print(f"{sym}: +{len(df) - len(old):,} 1m bars, now {df.index[0]} -> {df.index[-1]}; 5m {len(b5):,}")
