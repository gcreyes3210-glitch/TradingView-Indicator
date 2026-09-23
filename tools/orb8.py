#!/usr/bin/env python3
"""ORB8: ORB v1.3 plus three context filters found in the ORB context check — an in-sample demonstration, not a rule.

    python3 tools/orb_engine.py --start 2019-06-01 --out t.csv && python3 tools/orb8.py t.csv [--n 1000]

Filters (all known at 09:45): skip the day if (1) the previous cash day's range is in the top tercile of the 60 cash
days before it, (2) the overnight range is wider than the previous cash day's range, (3) |09:30 gap| < 0.5 x the
opening-range width. Because ORB takes at most one trade a day and every filter is a whole-day skip, filtering the
v1.3 trade list is exactly the filtered rule. Then 1,000 random removals of the same number of trades from v1.3 show
where the stacked filter sits against chance.
"""
import sys
import numpy as np
import pandas as pd
from orb_engine import stats

TZ = "America/New_York"
args = [a for a in sys.argv[1:] if not a.startswith("--")]
nsim = int(sys.argv[sys.argv.index("--n") + 1]) if "--n" in sys.argv else 1000
t = pd.read_csv(args[0])
t["entry_time"] = pd.to_datetime(t.entry_time, utc=True).dt.tz_convert(TZ)
t["day"] = t.entry_time.dt.date
t["year"] = t.entry_time.dt.year
t["R"] = t.pnl / (t.risk * 2.0)

b = pd.read_parquet("data/bars/MNQ_5m.parquet")
tod = b.index.hour * 60 + b.index.minute
rth = b[(tod >= 570) & (tod < 960)]
g = rth.groupby(rth.index.date)
rng = (g.high.max() - g.low.min())
prev_rng = rng.shift(1)                                         # previous cash day's range, indexed by the trade day
q = prev_rng.shift(1).rolling(60).quantile(2 / 3)              # top-tercile cut of the 60 cash days before it
t["f1"] = [bool(prev_rng.get(d, np.nan) > q.get(d, np.nan)) for d in t.day]
t["f2"] = t.on_w > t.pd_range
t["f3"] = t.gap.abs() < 0.5 * t.or_w
t["skip"] = t.f1 | t.f2 | t.f3
keep = t[~t.skip]


def metrics(x):
    s = stats(x)
    eq = x.R.cumsum()
    by = x.groupby("year").pnl.sum()
    return dict(n=len(x), net=s["net"], pf=s["pf"], win=s["win"], dd=s["dd"], R=round(x.R.mean(), 3),
                ddR=round((eq - eq.cummax()).min(), 1), pos_years=int((by > 0).sum()))


print(f"v1.3: {metrics(t)}")
print(f"skipped by filter: f1 {int(t.f1.sum())}  f2 {int(t.f2.sum())}  f3 {int(t.f3.sum())}  any {int(t.skip.sum())}; "
      f"skipped trades net {t[t.skip].pnl.sum():+,.0f}")
m8 = metrics(keep)
print(f"ORB8: {m8}")
print("ORB8 per year: " + "  ".join(f"{y} {v:+,.0f} ({int((keep.year == y).sum())})" for y, v in keep.groupby('year').pnl.sum().items()))
print("v1.3 per year: " + "  ".join(f"{y} {v:+,.0f}" for y, v in t.groupby('year').pnl.sum().items()))

rng_ = np.random.default_rng(7)
sims = []
for _ in range(nsim):
    idx = np.sort(rng_.choice(len(t), size=len(keep), replace=False))
    sims.append(metrics(t.iloc[idx]))
sims = pd.DataFrame(sims)
print(f"\n{nsim} random removals of {int(t.skip.sum())} trades (keeping {len(keep)}):")
for k in ("net", "pf", "R", "dd", "ddR", "pos_years"):
    v = m8[k]
    pct = (sims[k] < v).mean() * 100 + (sims[k] == v).mean() * 50
    print(f"  {k:<9} ORB8 {v:>8}   random p5 {sims[k].quantile(.05):>8.2f}  p50 {sims[k].median():>8.2f}  "
          f"p95 {sims[k].quantile(.95):>8.2f}   ORB8 at percentile {pct:.1f}")
