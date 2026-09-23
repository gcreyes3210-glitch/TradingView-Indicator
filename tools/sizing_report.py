#!/usr/bin/env python3
"""Position-sizing report for an engine trade list (one contract per trade).

    python3 tools/orb_engine.py --start 2019-06-01 --out trades.csv
    python3 tools/sizing_report.py trades.csv [--point-value 2] [--recent-years 2]

R = net PnL / (risk in points at entry x point value), risk = entry signal price to stop, before costs.
Contracts per account = floor(account x risk% / (median risk points of the last N years x point value)).
"""
import sys, math
import pandas as pd

args = [a for a in sys.argv[1:] if not a.startswith("--")]
opt = lambda k, d: type(d)(sys.argv[sys.argv.index(k) + 1]) if k in sys.argv else d
pv, recent = opt("--point-value", 2.0), opt("--recent-years", 2)

tr = pd.read_csv(args[0])
tr["entry_time"] = pd.to_datetime(tr.entry_time, utc=True).dt.tz_convert("America/New_York")
tr["R"] = tr.pnl / (tr.risk * pv)

def dd(x):
    c = x.cumsum(); return (c - c.cummax()).min()

streak = run = 0
for p in tr.pnl:
    run = run + 1 if p < 0 else 0; streak = max(streak, run)
m = tr.groupby(tr.entry_time.dt.tz_localize(None).dt.to_period("M")).agg(pnl=("pnl", "sum"), R=("R", "sum"))
roll = tr[["pnl", "R"]].rolling(20).sum()
w = roll.pnl.idxmin(); wr = roll.R.idxmin()

print(f"{len(tr)} trades {tr.entry_time.iloc[0].date()} -> {tr.entry_time.iloc[-1].date()}")
q = tr.R.quantile([.05, .1, .25, .5, .75, .9, .95])
print("R: mean %+.3f  median %+.2f  min %+.2f  max %+.2f  total %+.1f" % (tr.R.mean(), tr.R.median(), tr.R.min(), tr.R.max(), tr.R.sum()))
print("   percentiles " + "  ".join(f"p{int(k*100)} {v:+.2f}" for k, v in q.items()))
print("   stops avg %+.2f R (n %d)  time exits avg %+.2f R (n %d)  share >= +2R %.1f%%  share <= -1R %.1f%%" % (
    tr[tr.reason == "SL"].R.mean(), (tr.reason == "SL").sum(), tr[tr.reason == "time"].R.mean(), (tr.reason == "time").sum(),
    100 * (tr.R >= 2).mean(), 100 * (tr.R <= -1).mean()))
print("   by bucket: " + "  ".join(f"{k} {v}" for k, v in pd.cut(tr.R, [-99, -1.5, -1, -0.5, 0, 0.5, 1, 2, 3, 5, 99]).value_counts(sort=False).items()))
print(f"longest losing streak {streak}")
print(f"worst drawdown {dd(tr.pnl):,.0f} $  /  {dd(tr.R):.1f} R")
print(f"worst month $ {m.pnl.idxmin()} {m.pnl.min():,.0f} $  ({m.loc[m.pnl.idxmin(), 'R']:+.1f} R);  worst month R {m.R.idxmin()} {m.R.min():+.1f} R")
print(f"worst 20 trades $ ending {tr.entry_time[w].date()} {roll.pnl[w]:,.0f} $;  in R ending {tr.entry_time[wr].date()} {roll.R[wr]:+.1f} R")

cut = tr.entry_time.iloc[-1] - pd.DateOffset(years=recent)
rec = tr[tr.entry_time > cut]
med = rec.risk.median()
print(f"\nmedian risk last {recent} years ({len(rec)} trades since {cut.date()}): {med:.2f} pts = ${med * pv:,.0f} per contract "
      f"(p75 {rec.risk.quantile(.75):.1f} pts, p90 {rec.risk.quantile(.9):.1f} pts)")
ddR, mR, wR = dd(tr.R), m.R.min(), roll.R.min()
print("account   risk  contracts  $ at risk  actual %   worst DD %   worst month %   worst 20 trades %   losing streak %")
for acct in (10_000, 25_000, 50_000, 100_000, 250_000):
    for pct in (0.01, 0.02):
        n = math.floor(acct * pct / (med * pv))
        a = n * med * pv / acct
        print(f"{acct:>8,}  {pct:.0%}  {n:>9}  {n * med * pv:>9,.0f}  {100 * a:>7.2f}   {100 * a * ddR:>9.1f}   {100 * a * mR:>12.1f}   "
              f"{100 * a * wR:>16.1f}   {100 * a * -streak:>14.1f}")
