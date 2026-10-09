#!/usr/bin/env python3
"""FLOW2: order flow around IFVG-1m and AMD1-1m trades on the order-flow days (observation only, no rule change).

    python3 tools/flow2.py [--ifvg data/studies/ifvg1m/IFVG1m_T3_Z-all.csv]

Trades: the IFVG-1m primary run (T3, Z-all) and the AMD1-1m defaults (tools/amd_engine.py run(tf=1)), kept when the
entry date is one of the 876 order-flow days (data/flow, NQ and ES trades 09:30-11:35 New York, CME aggressor flag).
Six measures, deltas signed in the trade's direction (positive = aggressive flow in the trade's direction):
    sweep_delta   NQ delta on the sweep bar (1m)
    sweep_cum     NQ cumulative delta from 09:30 through the sweep bar
    sweep_div     NQ minus ES cumulative delta through the sweep bar, each divided by its volume since 09:30
    stack         largest stacked imbalance on the inversion candle, in the trade's direction: a buy imbalance at
                  price p = NQ buy-aggressor volume at p >= 3 x the sell-aggressor volume at p - 1 tick (floor 1
                  contract); a sell imbalance at p = sell volume at p >= 3 x buy volume at p + 1 tick; the count is
                  the longest run of consecutive ticks with an imbalance on the trade's side (1m footprint built
                  from data/raw/NQ trades for that minute)
    absorption    NQ volume on the inversion candle / (its range in ticks + 1), unsigned
    entry_delta   NQ delta on the entry bar
Inversion candle: IFVG-1m = the entry bar (the inversion close is the entry); AMD1-1m = the trigger bar (trig_t;
for MSS triggers the break candle). Sweep bar: IFVG-1m = the first 1m bar beyond the level; AMD1-1m = sweep_t.
A measure is missing when its minute is outside 09:30-11:34 (e.g. a sweep before 09:30).
Per family and measure: terciles within each calendar year, n / net / R per trade by tercile, top minus bottom
R per trade, and a two-sided shuffle p (tercile labels permuted within year, 20,000 times; the sign of each effect
was not pre-registered). Bonferroni across the six measures: p < 0.05 / 6 = 0.0083 per family.
"""
import sys, pathlib, collections
import numpy as np
import pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).parent))
TZ = "America/New_York"
TICK = 0.25
MEASURES = ["sweep_delta", "sweep_cum", "sweep_div", "stack", "absorption", "entry_delta"]
NSH = 20000
rng = np.random.default_rng(12)


def load_trades():
    import amd_engine
    one = pd.read_parquet("data/bars/MNQ_1m.parquet")
    ts = one.index
    i = pd.read_csv(sys.argv[sys.argv.index("--ifvg") + 1] if "--ifvg" in sys.argv else "data/studies/ifvg1m/IFVG1m_T3_Z-all.csv")
    i["entry_time"] = pd.to_datetime(i.entry_time, utc=True).dt.tz_convert(TZ)
    i = i.assign(family="IFVG-1m", sweep_t=ts[i.sweep_j.astype(int)], inv_t=i.entry_time)
    a = amd_engine.run(one, tf=1)[0]
    a = a.assign(family="AMD1-1m", inv_t=a.trig_t)
    cols = ["family", "side", "entry_time", "sweep_t", "inv_t", "pnl", "R"]
    return pd.concat([i[cols], a[cols]], ignore_index=True)


def footprint(day, minutes):
    import databento as db
    f = pathlib.Path(f"data/raw/NQ/{day}.dbn.zst")
    if not f.exists():
        return {}
    df = db.DBNStore.from_file(str(f)).to_df(price_type="float", pretty_ts=True, map_symbols=False)
    df.index = pd.DatetimeIndex(df.ts_event).tz_convert(TZ)
    out = {}
    for m in minutes:
        x = df[(df.index >= m) & (df.index < m + pd.Timedelta(minutes=1))]
        if x.empty:
            continue
        side = x.side.astype(str)
        buy = x["size"].where(side == "B", 0).groupby(x.price).sum()
        sell = x["size"].where(side == "A", 0).groupby(x.price).sum()
        out[m] = (buy, sell, x.price.max(), x.price.min(), x["size"].sum())
    return out


def stack(buy, sell, sgn):
    px = np.round(np.arange(min(buy.index.min(), sell.index.min()), max(buy.index.max(), sell.index.max()) + TICK / 2, TICK), 2)
    b = buy.reindex(px, fill_value=0).to_numpy(); s = sell.reindex(px, fill_value=0).to_numpy()
    if sgn > 0:      # buy imbalance at p vs sell at p - 1 tick
        imb = np.r_[False, b[1:] >= 3 * np.maximum(s[:-1], 1)]
    else:            # sell imbalance at p vs buy at p + 1 tick
        imb = np.r_[s[:-1] >= 3 * np.maximum(b[1:], 1), False]
    best = run = 0
    for v in imb:
        run = run + 1 if v else 0
        best = max(best, run)
    return best


def shuffle_p(R, lab, years):
    groups = [np.flatnonzero(years == y) for y in np.unique(years)]
    obs = R[lab == 2].mean() - R[lab == 0].mean()
    hits = 0
    for _ in range(NSH // 1000):
        L = np.tile(lab, (1000, 1))
        for gi in groups:
            L[:, gi] = np.take_along_axis(L[:, gi], rng.random((1000, len(gi))).argsort(axis=1), axis=1)
        top = np.where(L == 2, R, 0).sum(1) / (L == 2).sum(1)
        bot = np.where(L == 0, R, 0).sum(1) / (L == 0).sum(1)
        hits += int((np.abs(top - bot) >= abs(obs)).sum())
    return obs, hits / NSH


def main():
    flow = {s: pd.read_parquet(f"data/flow/{s}_flow_1m.parquet") for s in ("NQ", "ES")}
    days = sorted(set(flow["NQ"].index.date))
    t = load_trades()
    t = t[t.entry_time.dt.date.isin(set(days))].reset_index(drop=True)
    t["sgn"] = np.where(t.side == "L", 1, -1)
    nq, es = flow["NQ"], flow["ES"]
    get = lambda f, m, c: f[c].get(m, np.nan)
    t["sweep_delta"] = [s * get(nq, m, "delta") for s, m in zip(t.sgn, t.sweep_t)]
    t["sweep_cum"] = [s * get(nq, m, "cum_delta") for s, m in zip(t.sgn, t.sweep_t)]
    t["sweep_div"] = [s * (get(nq, m, "cum_delta") / get(nq, m, "cum_volume") - get(es, m, "cum_delta") / get(es, m, "cum_volume"))
                      for s, m in zip(t.sgn, t.sweep_t)]
    t["entry_delta"] = [s * get(nq, m, "delta") for s, m in zip(t.sgn, t.entry_time)]
    t["stack"], t["absorption"] = np.nan, np.nan
    need = collections.defaultdict(set)
    for m in t.inv_t:
        if m in nq.index:
            need[m.date()].add(m)
    fp = {}
    for d, ms in sorted(need.items()):
        fp.update(footprint(d, sorted(ms)))
    for k, r in t.iterrows():
        if r.inv_t in fp:
            buy, sell, hi, lo, vol = fp[r.inv_t]
            t.at[k, "stack"] = stack(buy, sell, r.sgn)
            t.at[k, "absorption"] = vol / ((hi - lo) / TICK + 1)
    t["year"] = t.entry_time.dt.year
    t.to_csv("data/studies/flow2_trades.csv", index=False)
    for fam, g in t.groupby("family"):
        print(f"\n######## {fam}: {len(g)} trades on order-flow days, net {g.pnl.sum():+,.0f}, {g.R.mean():+.3f} R/trade")
        for m in MEASURES:
            x = g[g[m].notna()].copy()
            if len(x) < 30:
                print(f"== {m}: {len(x)} trades with the measure, too few"); continue
            x["ter"] = x.groupby("year")[m].transform(lambda s: pd.qcut(s.rank(method="first"), 3, labels=False)).astype(int)
            obs, p = shuffle_p(x.R.to_numpy(), x.ter.to_numpy(), x.year.to_numpy())
            tab = x.groupby("ter").agg(n=("R", "size"), net=("pnl", "sum"), R=("R", "mean"), lo=(m, "min"), hi=(m, "max"))
            flag = "below the Bonferroni bar" if p < 0.05 / 6 else "not significant"
            print(f"== {m}: {len(x)} of {len(g)} trades have it; top - bottom {obs:+.3f} R, two-sided p {p:.4f} ({flag})")
            for ter, r in tab.iterrows():
                print(f"   {['bottom', 'middle', 'top'][ter]:<6} n {int(r.n):>3}  range {r.lo:+,.2f} .. {r.hi:+,.2f}  net {r.net:+8,.0f}  R/trade {r.R:+.3f}")


if __name__ == "__main__":
    main()
