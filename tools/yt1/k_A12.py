#!/usr/bin/env python3
"""K-A12 - ICT opening-range gap: the share of days on which the midpoint of the gap between the previous day's
16:14 close and the 09:30 open trades between 09:30 and 10:00, and by 16:00, by gap size. Claimed: about 70 %.

Definitions used (fixed before the first run; see notes/K-A12.md):
  * settlement proxy = the close of the 1-minute bar stamped 16:14 on the previous cash day (the row before in the
    day table). A previous cash day without a 16:14 bar (a short session) has no proxy: the day is left out and
    counted. A day whose 09:30 bar is another contract than that 16:14 bar (a roll in between) is left out and
    counted: the two prices are not one market.
  * gap = 09:30 bar's open - settlement proxy (positive = premium gap, negative = discount gap); midpoint = their
    average, not rounded. The midpoint "trades" in a window when a 1-minute bar of the window reaches it: low <=
    midpoint for a premium gap, high >= midpoint for a discount gap (a zero gap trades at the open).
  * windows: 09:30-10:00 = the bars 09:30 .. 09:59; "by 16:00" = 09:30 .. 15:59 (to the halt on a short day).
  * size buckets in points, as he speaks them: 20 to 75 (20 <= |gap| < 75), 75 to 120 (75 <= |gap| <= 120), higher
    than 120; gaps under 20, which he does not address, are shown as well. The same three thresholds as a percentage
    of price at 2025 levels: 20, 75 and 120 points on 21,000 = 0.0952 %, 0.3571 %, 0.5714 % of the settlement proxy.
"""
import numpy as np
import pandas as pd
import core

NAME = "ICT opening-range gap (16:14 close -> 09:30 open): the gap's midpoint trades 09:30-10:00 / by 16:00"
CLAIMED = 0.70
REF_2025 = 21000.0
EDGES_PTS = (20.0, 75.0, 120.0)
EDGES_PCT = tuple(x / REF_2025 * 100.0 for x in EDGES_PTS)
BUCKETS = ("under 20", "20 to 75", "75 to 120", "over 120")                  # points
BUCKETS_PCT = tuple(f"{b} pts at 21,000 = {r}" for b, r in zip(BUCKETS, (
    f"under {EDGES_PCT[0]:.4f} %", f"{EDGES_PCT[0]:.4f} to {EDGES_PCT[1]:.4f} %",
    f"{EDGES_PCT[1]:.4f} to {EDGES_PCT[2]:.4f} %", f"over {EDGES_PCT[2]:.4f} %")))
ALL_UP, ALL = "all from the lowest threshold up", "all gaps"


def _bucket(size, e, names):
    return names[0] if size < e[0] else names[1] if size < e[1] else names[2] if size <= e[2] else names[3]


def _rows(ctx):
    D = ctx.days
    idx = D.index
    H, L, O, C = ctx.H, ctx.L, ctx.O, ctx.C
    rows, skipped = [], dict(no_1614_bar_on_previous_cash_day=0, contract_changed_between=0)
    for n in range(1, len(D)):
        d, p = idx[n], idx[n - 1]
        j = ctx.idx(p, "16:14")
        if j is None:
            skipped["no_1614_bar_on_previous_cash_day"] += 1
            continue
        i0 = int(D.i_open.iloc[n])
        if ctx.iid[int(j)] != ctx.iid[i0]:
            skipped["contract_changed_between"] += 1
            continue
        settle, opn = float(C[int(j)]), float(O[i0])
        gap = opn - settle
        mid = (opn + settle) / 2.0
        a0, a1 = ctx.span(d, "09:30", "10:00")
        b0, b1 = ctx.span(d, "09:30", "16:00")
        if gap > 0:
            w30, wday = bool(L[a0:a1].min() <= mid), bool(L[b0:b1].min() <= mid)
        elif gap < 0:
            w30, wday = bool(H[a0:a1].max() >= mid), bool(H[b0:b1].max() >= mid)
        else:
            w30 = wday = True
        size = abs(gap)
        pct = size / settle * 100.0
        rows.append(dict(date=d, gap=gap, size=size, pct=pct, premium=gap > 0, early=bool(D.early.iloc[n]),
                         in_0930_1000=w30, by_1600=wday, b_pts=_bucket(size, EDGES_PTS, BUCKETS),
                         b_pct=_bucket(pct, EDGES_PCT, BUCKETS_PCT)))
    return pd.DataFrame(rows), skipped


def _cell(x):
    if not len(x):
        return dict(n=0, share_0930_1000=None, share_by_1600=None, claimed=CLAIMED)
    return dict(n=int(len(x)), share_0930_1000=round(float(x.in_0930_1000.mean()), 4),
                share_by_1600=round(float(x.by_1600.mean()), 4), claimed=CLAIMED)


def _table(x, col, names):
    out = {}
    for b in names:
        g = x[x[col] == b]
        c = _cell(g)
        c["premium"], c["discount"] = _cell(g[g.premium]), _cell(g[~g.premium & (g.gap != 0)])
        c["median_gap_pts"] = round(float(g["size"].median()), 2) if len(g) else None
        out[b] = c
    out[ALL_UP] = _cell(x[x[col] != names[0]])
    out[ALL] = _cell(x)
    return out


def measure(ctx):
    x, skipped = _rows(ctx)
    e = tuple(round(v, 4) for v in EDGES_PCT)
    res = dict(
        claim="the opening-range gap's midpoint trades: about 70 % (window not stated; both are measured)",
        span=f"{ctx.days.index[0].date()} -> {ctx.days.index[-1].date()}",
        cash_days=int(len(ctx.days)), days_measured=int(len(x)), days_left_out=skipped,
        short_days_measured=int(x.early.sum()),
        median_abs_gap_pts=round(float(x["size"].median()), 2), median_abs_gap_pct=round(float(x.pct.median()), 4),
        buckets_in_points=_table(x, "b_pts", BUCKETS),
        buckets_as_pct_of_price=dict(thresholds_pct=e, reference_level=REF_2025, **_table(x, "b_pct", BUCKETS_PCT)),
        by_year_20_to_75_points={int(y): _cell(g) for y, g in x[x.b_pts == BUCKETS[1]].groupby(x.date.dt.year)},
        by_year_20_to_75_as_pct={int(y): _cell(g) for y, g in x[x.b_pct == BUCKETS_PCT[1]].groupby(x.date.dt.year)})
    return res


def show(res):
    print(res["claim"], "  ", res["span"])
    print(f"cash days {res['cash_days']}, measured {res['days_measured']} (short days among them "
          f"{res['short_days_measured']}), left out {res['days_left_out']}; median |gap| {res['median_abs_gap_pts']} pts"
          f" = {res['median_abs_gap_pct']} % of price")

    def f(v):
        return "   n/a" if v is None else f"{v:6.1%}"

    for name, lab, names in (("buckets_in_points", "size in points", BUCKETS),
                             ("buckets_as_pct_of_price", "size as % of the previous 16:14 close", BUCKETS_PCT)):
        t = res[name]
        extra = f"  (thresholds {t['thresholds_pct']} % = 20 / 75 / 120 points at {t['reference_level']:.0f})" if "thresholds_pct" in t else ""
        print(f"-- {lab}{extra}")
        print(f"   {'bucket':<52} {'n':>5}  09:30-10:00  by 16:00  claimed | premium n  0930-1000  by 16:00 | discount n  0930-1000  by 16:00")
        for b in list(names) + [ALL_UP, ALL]:
            c = t[b]
            line = f"   {b:<52} {c['n']:>5}  {f(c['share_0930_1000']):>11}  {f(c['share_by_1600']):>8}  {c['claimed']:>6.0%}"
            if "premium" in c:
                p, q = c["premium"], c["discount"]
                line += (f"  | {p['n']:>9}  {f(p['share_0930_1000']):>9}  {f(p['share_by_1600']):>8} | {q['n']:>10}  "
                         f"{f(q['share_0930_1000']):>9}  {f(q['share_by_1600']):>8}")
            print(line)
    for name in ("by_year_20_to_75_points", "by_year_20_to_75_as_pct"):
        print(f"{name}: " + "  ".join(f"{y} {f(v['share_0930_1000']).strip()} / {f(v['share_by_1600']).strip()} (n {v['n']})"
                                      for y, v in res[name].items()))
