#!/usr/bin/env python3
"""Pre-registered context check on the ORB v1.3 trade list (no rule changes).

    python3 tools/orb_engine.py --start 2019-06-01 --out t.csv && python3 tools/orb_context.py t.csv

Splits (fixed before looking at the results):
    pd_dir   previous cash session's 16:00 close vs its own 09:30 open: up / down (a day that closes exactly at its
             open is neither and is left out of this split)
    pd_range previous cash session's high-low range, terciles within each calendar year (T1 = narrowest)
    gap      |09:30 open - previous 16:00 close| in points, terciles within each calendar year (T1 = smallest)
    month    calendar month of the entry
    on_vs_pd overnight (18:00-09:30) range wider or narrower than the previous cash session's range
Terciles are taken within each year because ranges and gaps roughly quadrupled from 2019 to 2026; full-sample
terciles would put whole years into one bucket.
Verdict rule: best and worst bucket = highest / lowest R per trade over the full sample. The split COUNTS only if
the best bucket's R per trade beats the worst bucket's in at least 6 of the 8 calendar years (2019 Jun-Dec ...
2026 Jan-Sep); a year in which either bucket has no trades counts as not beaten.
Shuffles (added after the pre-registration, information only): over 2,000 shuffles of the bucket labels within each
year, the share for which the same rule would say COUNTS, and the share reaching at least the observed number of years. Best and worst are picked from the same years they are
then tested on, so a split with many buckets passes by chance more often.
"""
import sys
import numpy as np
import pandas as pd

PV = 2.0
t = pd.read_csv(sys.argv[1])
t["entry_time"] = pd.to_datetime(t.entry_time, utc=True).dt.tz_convert("America/New_York")
t["year"] = t.entry_time.dt.year
t["R"] = t.pnl / (t.risk * PV)
t = t.dropna(subset=["pd_range", "gap", "on_w", "pd_dir"]).copy()


def tercile(col):
    return t.groupby("year")[col].transform(lambda x: pd.qcut(x.rank(method="first"), 3, labels=["T1", "T2", "T3"])).astype(str)


t["pd_range_b"] = tercile("pd_range")
t["absgap"] = t.gap.abs()
t["gap_b"] = tercile("absgap")
t["month_b"] = t.entry_time.dt.month.map(lambda m: f"{m:02d}")
t["on_vs_pd"] = (t.on_w > t.pd_range).map({True: "wider", False: "narrower"})
years = sorted(t.year.unique())
print(f"{len(t)} trades with full context, {years[0]}-{years[-1]}, total {t.pnl.sum():+,.0f} $, {t.R.mean():+.3f} R/trade\n")

def verdict(d, col, years):
    full = d.groupby(col).R.mean()
    yr = d.pivot_table(index=col, columns="year", values="R", aggfunc="mean")
    best, worst = full.idxmax(), full.idxmin()
    beats = sum(1 for y in years if y in yr and pd.notna(yr.loc[best, y]) and pd.notna(yr.loc[worst, y])
                and yr.loc[best, y] > yr.loc[worst, y])
    return best, worst, beats


def null_rates(d, col, years, observed, n=2000, seed=1):
    """Share of within-year label shuffles that COUNT (>= 6 years), and that do at least as well as observed."""
    rng = np.random.default_rng(seed)
    six = atleast = 0
    for _ in range(n):
        s = d[[col, "year", "R"]].copy()
        s[col] = s.groupby("year")[col].transform(lambda x: rng.permutation(x.to_numpy()))
        k = verdict(s, col, years)[2]
        six += k >= 6
        atleast += k >= observed
    return six / n, atleast / n


for name, col in (("previous day direction", "pd_dir"), ("previous day range tercile", "pd_range_b"),
                  ("gap size tercile", "gap_b"), ("month of year", "month_b"), ("overnight vs previous day range", "on_vs_pd")):
    d = t[t.pd_dir != "flat"] if col == "pd_dir" else t
    full = d.groupby(col).agg(n=("R", "size"), net=("pnl", "sum"), R=("R", "mean"))
    yr = d.pivot_table(index=col, columns="year", values="R", aggfunc="mean")
    yn = d.pivot_table(index=col, columns="year", values="pnl", aggfunc="sum")
    best, worst, beats = verdict(d, col, years)
    print(f"== {name}: best {best} ({full.loc[best, 'R']:+.3f} R) vs worst {worst} ({full.loc[worst, 'R']:+.3f} R): "
          f"best beats worst in {beats} of {len(years)} years -> {'COUNTS' if beats >= 6 else 'does not count'}"
          "   [shuffles: %.0f%% count, %.0f%% reach %d+ years]" % (*(100 * x for x in null_rates(d, col, years, beats)), beats))
    for b, r in full.iterrows():
        print(f"  {b:<9} n {int(r.n):>3}  net {r.net:>+8,.0f}  R/trade {r.R:+.3f}   R by year " +
              " ".join(f"{yr.loc[b, y]:+.2f}" if pd.notna(yr.loc[b, y]) else "  -  " for y in years) +
              "   net by year " + " ".join(f"{yn.loc[b, y]:+,.0f}" if pd.notna(yn.loc[b, y]) else "-" for y in years))
    print()
