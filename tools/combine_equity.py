#!/usr/bin/env python3
"""Additivity check: a second rule's trades against a base rule's, one contract each.

    python3 tools/combine_equity.py base.csv other.csv [--names ORB,IVC1]

Reports the other rule on the days the base rule did not trade, the overlap, the daily-PnL correlation on shared
days, and the combined equity curve (trades ordered by exit time) against the base alone.
"""
import sys
import pandas as pd
from orb_engine import stats

args = [a for a in sys.argv[1:] if not a.startswith("--")]
names = sys.argv[sys.argv.index("--names") + 1].split(",") if "--names" in sys.argv else ["base", "other"]
tz = "America/New_York"
a, b = (pd.read_csv(f).drop(columns=["R"], errors="ignore") for f in args[:2])  # R is not comparable across rules
for t in (a, b):
    for c in ("entry_time", "exit_time"):
        t[c] = pd.to_datetime(t[c], utc=True).dt.tz_convert(tz)
    t["day"] = t.entry_time.dt.date

shared = set(a.day) & set(b.day)
only = b[~b.day.isin(set(a.day))]
print(f"{names[0]} {len(a)} trades from {a.entry_time.min().date()}, {names[1]} {len(b)} trades from {b.entry_time.min().date()}")
print(f"{names[1]} on days {names[0]} did not trade: " + "  ".join(f"{k} {v}" for k, v in stats(only).items()))
print(f"{names[1]} on shared days:              " + "  ".join(f"{k} {v}" for k, v in stats(b[b.day.isin(shared)]).items()))
print(f"overlap: {len(shared)} days on which both traded ({100 * len(shared) / len(b):.0f} % of {names[1]} trades), "
      f"same side on {sum(1 for d in shared if a[a.day == d].side.iloc[0] == b[b.day == d].side.iloc[0])}")
da, db = a.groupby("day").pnl.sum(), b.groupby("day").pnl.sum()
print(f"daily PnL correlation on shared days: {da[list(shared)].corr(db[list(shared)]):+.2f}")

comb = pd.concat([a.assign(rule=names[0]), b.assign(rule=names[1])]).sort_values("exit_time")
print(f"\n{'':<10}" + "  ".join(f"{k:>8}" for k in stats(a)))
for n, t in ((names[0], a), (names[1], b), ("combined", comb)):
    print(f"{n:<10}" + "  ".join(f"{str(v):>8}" for v in stats(t).values()))
print("\nper calendar year (net):   " + names[0] + " / " + names[1] + " / combined")
for y in sorted(comb.exit_time.dt.year.unique()):
    f = lambda t: t[t.exit_time.dt.year == y].pnl.sum()
    print(f"  {y}  {f(a):+9,.0f}  {f(b):+9,.0f}  {f(comb):+9,.0f}")
