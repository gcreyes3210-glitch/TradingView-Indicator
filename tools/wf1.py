#!/usr/bin/env python3
"""WF1: walk-forward parameter search on the ORB engine (pre-registered in BACKTEST_LOG.md, "Walk-forward").

    python3 tools/wf1.py [--out wf1_grid.csv]

In-sample 2019-06-01 .. 2022-12-31: the search sees only a copy of the bars cut at 2022-12-31 23:59 (asserted).
Out-of-sample 2023-01-01 .. 2026-09-21: read only after the top five are fixed, once for each of them and for v1.4.
Grid (4 x 4 x 4 x 3 x 2 x 2 x 2 = 1,536): opening range 10 / 15 / 20 / 30 min (entries start when it ends); entry
window end 10:30 / 11:00 / 11:30 / 12:00; min close beyond the edge 0 / 0.10 / 0.15 / 0.25 x range; overnight filter
off / break / break-direction; ORB8 filters F1 / F2 / F3 each on or off. Everything else = v1.4.
The ORB8 filters skip whole days and ORB takes at most one trade a day, so each engine run (192) is filtered exactly
for the 8 filter settings. F3 uses the setting's own opening-range width.
Rank: worst calendar year's total R, then the median year's total R (in-sample years 2019 (Jun-Dec), 2020, 2021, 2022;
a year without trades counts as 0 R). R = net PnL / (risk points x $2).
"""
import sys, itertools, time
import numpy as np
import pandas as pd
sys.path.insert(0, __import__("os").path.dirname(__file__))
from orb_engine import run, stats
from calibrate_orb import shadow_flags

TZ = "America/New_York"
IS0, IS1 = pd.Timestamp("2019-06-01", tz=TZ), pd.Timestamp("2023-01-01", tz=TZ)
OOS0, OOS1 = pd.Timestamp("2023-01-01", tz=TZ), pd.Timestamp("2026-09-22", tz=TZ)
ORS = (10, 15, 20, 30)
ENDS = ("10:30", "11:00", "11:30", "12:00")
BRKS = (0.0, 0.10, 0.15, 0.25)
ONF = ("off", "break", "direction")
FILT = list(itertools.product((False, True), repeat=3))
V14 = (15, "11:30", 0.15, "break", (False, False, False))


def hhmm(m):
    return f"{m // 60:02d}:{m % 60:02d}"


def engine(bars, orm, end, brk, onf, start):
    t = run(bars, start=start, or_sess=("09:30", hhmm(570 + orm)), entry_sess=(hhmm(570 + orm), end),
            min_brk_or=brk, on_filter=onf)
    if len(t):
        t["day"] = t.entry_time.dt.date
        t["year"] = t.entry_time.dt.year
        t["R"] = t.pnl / (t.risk * 2.0)
    return t


def apply_filters(t, flags, fl):
    if not len(t) or not any(fl):
        return t
    skip = np.zeros(len(t), bool)
    if fl[0]:
        skip |= np.array([flags.F1.get(d) is True for d in t.day])
    if fl[1]:
        skip |= (t.on_w > t.pd_range).to_numpy()
    if fl[2]:
        skip |= (t.gap.abs() < 0.5 * t.or_w).to_numpy()
    return t[~skip]


def year_R(t, years):
    by = t.groupby("year").R.sum() if len(t) else pd.Series(dtype=float)
    return [float(by.get(y, 0.0)) for y in years]


bars = pd.read_parquet("data/bars/MNQ_5m.parquet")
is_bars = bars[bars.index < IS1].copy()
assert is_bars.index.max() < IS1, "in-sample bars reach into the out-of-sample window"
is_flags = shadow_flags(is_bars, events=None)
is_years = [2019, 2020, 2021, 2022]

t0 = time.time()
rows = []
for orm, end, brk, onf in itertools.product(ORS, ENDS, BRKS, ONF):
    t = engine(is_bars, orm, end, brk, onf, IS0)
    for fl in FILT:
        x = apply_filters(t, is_flags, fl)
        yr = year_R(x, is_years)
        rows.append(dict(or_min=orm, entry_end=end, min_brk=brk, on_filter=onf, F1=fl[0], F2=fl[1], F3=fl[2],
                         n=len(x), net=round(x.pnl.sum()) if len(x) else 0, R_trade=round(x.R.mean(), 3) if len(x) else 0,
                         worst_year_R=round(min(yr), 2), median_year_R=round(float(np.median(yr)), 2),
                         years_R=" / ".join(f"{v:+.1f}" for v in yr)))
grid = pd.DataFrame(rows).sort_values(["worst_year_R", "median_year_R"], ascending=False).reset_index(drop=True)
grid.index += 1
n_comb = len(grid)
print(f"in-sample search: {n_comb:,} combinations ({len(ORS) * len(ENDS) * len(BRKS) * len(ONF)} engine runs x "
      f"{len(FILT)} filter settings) in {time.time() - t0:.0f} s")
if "--out" in sys.argv:
    grid.to_csv(sys.argv[sys.argv.index("--out") + 1])
key = lambda r: (r.or_min, r.entry_end, r.min_brk, r.on_filter, (r.F1, r.F2, r.F3))
v14_rank = int(grid[[key(r) == V14 for r in grid.itertuples()]].index[0])
print(f"\ntop 5 in sample (v1.4 ranks {v14_rank} of {n_comb:,}):")
cols = ["or_min", "entry_end", "min_brk", "on_filter", "F1", "F2", "F3", "n", "net", "R_trade", "worst_year_R",
        "median_year_R", "years_R"]
print(grid.head(5)[cols].to_string())
print(grid.loc[[v14_rank], cols].to_string(header=False))

# ---- out of sample: read now, once per setting
oos_flags = shadow_flags(bars, events=None)
oos_years = [2023, 2024, 2025, 2026]
sets = [("v1.4", V14)] + [(f"IS#{i}", key(r)) for i, r in zip(range(1, 6), grid.head(5).itertuples())]
print(f"\nout of sample 2023-01-01 .. 2026-09-21 ({n_comb:,} combinations searched in sample; top 5 and v1.4 run once):")
res = []
for name, (orm, end, brk, onf, fl) in sets:
    t = engine(bars, orm, end, brk, onf, OOS0)
    t = t[t.entry_time < OOS1]
    x = apply_filters(t, oos_flags, fl)
    s = stats(x)
    by = x.groupby("year").pnl.sum()
    eq = x.R.cumsum()
    res.append(dict(set=name, setting=f"OR{orm} to {end} brk{brk} {onf} F{''.join('1' if f else '0' for f in fl)}",
                    n=s["n"], net=s["net"], pf=s["pf"], win=s["win"], dd=s["dd"], ddR=round((eq - eq.cummax()).min(), 1),
                    R_trade=round(x.R.mean(), 3), pos_years=int((by > 0).sum()),
                    years=" / ".join(f"{by.get(y, 0):+,.0f}" for y in oos_years)))
r = pd.DataFrame(res)
print(r.to_string(index=False))
base = r.iloc[0]
win = r[(r.index > 0) & (r.net > base.net) & (r.R_trade > base.R_trade) & (r.pos_years >= 3)]
print(f"\npre-registered rule: adopt only a setting that beats v1.4 out of sample in net AND R per trade with >= 3 of 4 "
      f"positive years -> {'candidates: ' + ', '.join(win.set) if len(win) else 'none qualifies'}")
