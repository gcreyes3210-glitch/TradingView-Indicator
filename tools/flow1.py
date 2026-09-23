#!/usr/bin/env python3
"""FLOW1: order-flow context of the ORB v1.4 trades (pre-registered, no rule change).

    python3 tools/build_flow.py build && python3 tools/flow1.py

Trades: ORB v1.4 defaults from tools/orb_engine.py, MNQ 5m, 2019-06 -> 2026-09-21. Flow: data/flow/<NQ|ES>_flow_1m.parquet
(CME aggressor flag; unclassified volume excluded from delta). Seven measures, each signed in the trade's direction
(positive = flow agrees with the trade):
    NQ_sig / ES_sig   delta during the signal bar (the 5m bar whose close is the entry)
    NQ_cum / ES_cum   cumulative delta from 09:30 through the end of the signal bar
    NQ_or  / ES_or    delta during the opening range 09:30-09:45
    div               NQ minus ES cumulative delta through the signal bar, each divided by that symbol's volume since
                      09:30 (raw contract counts would be dominated by ES's larger volume)
Terciles within each calendar year (volumes grew several-fold over 2019-2026, as ranges and gaps did in the context
check). For each measure: net and R per trade by tercile, per calendar year, and top minus bottom tercile in each half
with a shuffle p (tercile labels permuted within each year, 20,000 shuffles, one-sided: top better than bottom).
Criterion (pre-registered): top beats bottom by >= 0.1 R per trade with p < 0.0015 (0.01 / 7) in BOTH 2019-2022 and
2023-2026.
"""
import sys
import numpy as np
import pandas as pd
sys.path.insert(0, __import__("os").path.dirname(__file__))
from orb_engine import run

TZ = "America/New_York"
MEASURES = ["NQ_sig", "NQ_cum", "NQ_or", "ES_sig", "ES_cum", "ES_or", "div"]
HALVES = (("2019-2022", 2019, 2022), ("2023-2026", 2023, 2026))
NSH, P_MAX, MIN_DIFF = 20000, 0.01 / 7, 0.1

t = run(pd.read_parquet("data/bars/MNQ_5m.parquet"), start=pd.Timestamp("2019-06-01", tz=TZ))
t["R"] = t.pnl / (t.risk * 2.0)
t["year"] = t.entry_time.dt.year
t["sgn"] = np.where(t.side == "L", 1, -1)

flow = {s: pd.read_parquet(f"data/flow/{s}_flow_1m.parquet") for s in ("NQ", "ES")}
for s, f in flow.items():
    f["day"] = f.index.date
vals = {m: [] for m in MEASURES}
for _, r in t.iterrows():
    d, t0 = r.entry_time.date(), r.entry_time
    t1 = t0 + pd.Timedelta(minutes=5)
    got = {}
    for s, f in flow.items():
        day = f[f.day == d]
        if day.empty:
            got[s] = None
            continue
        sig = day[(day.index >= t0) & (day.index < t1)].delta.sum()
        upto = day[day.index < t1]
        cum = upto.cum_delta.iloc[-1] if len(upto) else np.nan
        cvol = upto.cum_volume.iloc[-1] if len(upto) else np.nan
        orr = day[day.index < pd.Timestamp(f"{d} 09:45", tz=TZ)].delta.sum()
        got[s] = (sig, cum, orr, cum / cvol if cvol else np.nan)
    for s in ("NQ", "ES"):
        g = got[s]
        for k, m in enumerate(("sig", "cum", "or")):
            vals[f"{s}_{m}"].append(r.sgn * g[k] if g else np.nan)
    vals["div"].append(r.sgn * (got["NQ"][3] - got["ES"][3]) if got["NQ"] and got["ES"] else np.nan)
for m in MEASURES:
    t[m] = vals[m]
have = t[MEASURES].notna().all(axis=1)
print(f"{len(t)} ORB v1.4 trades, net {t.pnl.sum():+,.0f}, {t.R.mean():+.3f} R; with flow for all measures: "
      f"{int(have.sum())} (missing {int((~have).sum())})")
t = t[have].copy()
rng = np.random.default_rng(11)


def shuffle_p(x, lab, obs):
    """x: R, lab: tercile 0/1/2, years: within-year permutation; p = share with top - bottom >= obs."""
    hits = 0
    Rv = x.R.to_numpy()
    groups = [np.flatnonzero((x.year == y).to_numpy()) for y in sorted(x.year.unique())]
    lab = lab.copy()
    for _ in range(NSH // 1000):
        L = np.tile(lab, (1000, 1))
        for gi in groups:
            L[:, gi] = np.take_along_axis(L[:, gi], rng.random((1000, len(gi))).argsort(axis=1), axis=1)
        top = np.where(L == 2, Rv, 0).sum(1) / (L == 2).sum(1)
        bot = np.where(L == 0, Rv, 0).sum(1) / (L == 0).sum(1)
        hits += int(((top - bot) >= obs).sum())
    return hits / NSH


out = []
for m in MEASURES:
    t[f"{m}_t"] = t.groupby("year")[m].transform(lambda s: pd.qcut(s.rank(method="first"), 3, labels=False)).astype(int)
    tab = t.groupby(f"{m}_t").agg(n=("R", "size"), net=("pnl", "sum"), R=("R", "mean"))
    yr = t.pivot_table(index=f"{m}_t", columns="year", values="R", aggfunc="mean")
    print(f"\n== {m}: tercile (0 = flow most against the trade, 2 = most with it)")
    for k, r in tab.iterrows():
        print(f"  T{k + 1} n {int(r.n):>3} net {r.net:>+8,.0f} R/trade {r.R:+.3f}  R by year " +
              " ".join(f"{v:+.2f}" for v in yr.loc[k]))
    row = dict(measure=m)
    for hn, lo, hi in HALVES:
        x = t[(t.year >= lo) & (t.year <= hi)]
        lab = x[f"{m}_t"].to_numpy()
        diff = x.R[lab == 2].mean() - x.R[lab == 0].mean()
        p = shuffle_p(x, lab, diff)
        row[f"diff_{hn}"], row[f"p_{hn}"] = diff, p
        print(f"  {hn}: top - bottom {diff:+.3f} R per trade, shuffle p {p:.4f}")
    row["counts"] = all(row[f"diff_{h}"] >= MIN_DIFF and row[f"p_{h}"] < P_MAX for h, _, _ in HALVES)
    for k in range(3):
        row[f"T{k + 1}_n"], row[f"T{k + 1}_net"], row[f"T{k + 1}_R"] = int(tab.n[k]), round(tab.net[k]), round(tab.R[k], 3)
    out.append(row)
res = pd.DataFrame(out)
pd.set_option("display.width", 250)
print("\n", res.round(4).to_string(index=False))
