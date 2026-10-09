#!/usr/bin/env python3
"""Acceptance and split checks for any engine trade list with an R column.

    python3 tools/split_check.py trades.csv [--splits trigger,side,orb_day]

Prints positive calendar years and R per trade (the acceptance inputs), then for each split: n, net and R per trade
per bucket, R per trade by year, and the orb_context.py test: best / worst bucket by full-sample R per trade, the
number of years the best beats the worst (6 of 8 needed), and 2,000 within-year label shuffles (share that reach
6 years, share that do at least as well as observed). Buckets with fewer than 20 trades are left out.
"""
import sys
import numpy as np
import pandas as pd

args = [a for a in sys.argv[1:] if not a.startswith("--")]
splits = sys.argv[sys.argv.index("--splits") + 1].split(",") if "--splits" in sys.argv else []
t = pd.read_csv(args[0])
t["year"] = pd.to_datetime(t.entry_time, utc=True).dt.tz_convert("America/New_York").dt.year
years = sorted(t.year.unique())
by = t.groupby("year").pnl.sum()
print(f"{len(t)} trades, net {t.pnl.sum():+,.0f}, {t.R.mean():+.3f} R/trade, positive years {int((by > 0).sum())} of {len(years)}")


def verdict(d, col):
    full = d.groupby(col).R.mean()
    yr = d.pivot_table(index=col, columns="year", values="R", aggfunc="mean")
    best, worst = full.idxmax(), full.idxmin()
    beats = sum(1 for y in years if y in yr and pd.notna(yr.loc[best, y]) and pd.notna(yr.loc[worst, y])
                and yr.loc[best, y] > yr.loc[worst, y])
    return best, worst, beats


for col in splits:
    d = t[t.groupby(col)[col].transform("size") >= 20].copy()
    d[col] = d[col].astype(str)
    best, worst, beats = verdict(d, col)
    rng = np.random.default_rng(1)
    six = atleast = 0
    for _ in range(2000):
        s = d[[col, "year", "R"]].copy()
        s[col] = s.groupby("year")[col].transform(lambda x: rng.permutation(x.to_numpy()))
        k = verdict(s, col)[2]
        six += k >= 6; atleast += k >= beats
    print(f"== {col}: best {best} vs worst {worst}: best beats worst in {beats} of {len(years)} years -> "
          f"{'COUNTS' if beats >= 6 else 'does not count'}   [shuffles: {six / 20:.0f}% count, {atleast / 20:.0f}% reach {beats}+]")
    yr = d.pivot_table(index=col, columns="year", values="R", aggfunc="mean")
    for b, g in d.groupby(col):
        print(f"  {b:<6} n {len(g):>4}  net {g.pnl.sum():>+8,.0f}  R/trade {g.R.mean():+.3f}   R by year "
              + " ".join(f"{yr.loc[b, y]:+.2f}" if pd.notna(yr.loc[b, y]) else "  -  " for y in years))
