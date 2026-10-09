#!/usr/bin/env python3
"""K-E01 - NQ Stats Hour Stats: after the first breach of the previous hour's high / low, how often the hour's open
trades before the hour ends. Claimed: 61.5 % overall (17,701 breaches, 2016-2025), 13:00 hour first 20-minute
segment 71 %, 09:00 hour first segment 87.4 %.

Definitions (the source's, research note E entry 1; fixed before the first run, see notes/K-E01.md):
  * hours: the clock hours 08:00 ... 15:00 of every cash day in the day table; the previous hour is the clock hour
    before (07:00-07:59 for the 08:00 hour). Both hours must have bars and be the same contract.
  * the hour must open strictly inside the previous hour's range (previous low < open of the hour's first bar <
    previous high).
  * breach: the first 1-minute bar of the hour that trades at least 1 tick beyond the previous hour's high or low
    (high >= previous high + 0.25, or low <= previous low - 0.25). Only that first breach counts; an hour whose first
    breaching bar is beyond both levels is counted apart (the order within the minute is unknown).
  * segment: the 20-minute third of the hour the breaching bar is in (1 = :00-:19, 2 = :20-:39, 3 = :40-:59).
  * reversion: the hour's open is touched or crossed after the breach and before the hour ends (the source: "a
    wick touching or crossing counts"). On the bars AFTER the breaching bar this is exact. On the breaching bar
    itself the order is not in 1-minute data, so three figures are given:
        rate        headline: the breaching bar is read with the house intrabar path (open -> nearer extreme ->
                    farther extreme -> close): it counts if the path reaches the hour's open after the level
        rate_later  lower bound: only bars after the breaching bar count
        rate_any    upper bound: any touch of the hour's open on the breaching bar counts too (on the hour's first
                    bar, whose open IS the hour's open, the path reading is used instead)
"""
import numpy as np
import pandas as pd
import core

NAME = "Hour Stats: first breach of the previous hour's high / low, the hour's open trades before the hour ends"
CLAIMED = dict(overall=0.615, h13_seg1=0.71, h09_seg1=0.874)
HOURS = range(8, 16)


def _rows(ctx):
    O, H, L, C, tod, iid = ctx.O, ctx.H, ctx.L, ctx.C, ctx.tod, ctx.iid
    T = core.TICK
    rows, cnt = [], dict(hours=0, contract_change=0, not_inside=0, no_breach=0, both_in_one_bar=0)
    for d, day in ctx.days.iterrows():
        for h in HOURS:
            p0, p1 = ctx.span(d, (h - 1) * 60, h * 60)
            c0, c1 = ctx.span(d, h * 60, (h + 1) * 60)
            if p1 <= p0 or c1 <= c0:
                continue
            cnt["hours"] += 1
            if iid[p0] != iid[c1 - 1]:
                cnt["contract_change"] += 1
                continue
            ph, pl = H[p0:p1].max(), L[p0:p1].min()
            o = O[c0]
            if not (pl < o < ph):
                cnt["not_inside"] += 1
                continue
            up, dn = H[c0:c1] >= ph + T, L[c0:c1] <= pl - T
            brk = up | dn
            if not brk.any():
                cnt["no_breach"] += 1
                continue
            k = int(brk.argmax())
            b = c0 + k
            if up[k] and dn[k]:
                cnt["both_in_one_bar"] += 1
                continue
            hi_side = bool(up[k])                               # True: the previous high was breached (fade = short)
            level = ph + T if hi_side else pl - T
            # after the breaching bar: exact
            later = bool((L[b + 1:c1] <= o).any()) if hi_side else bool((H[b + 1:c1] >= o).any())
            # on the breaching bar: what the house path reaches after the level
            if (O[b] >= level) if hi_side else (O[b] <= level):
                rest = [H[b], L[b], C[b]]                       # the bar opens beyond the level: all of it is after
            else:
                p = core._path(O[b], H[b], L[b], C[b])
                rest = list(p[(p.index(H[b]) if hi_side else p.index(L[b])) + 1:])
            path = bool(rest) and (min(rest) <= o if hi_side else max(rest) >= o)
            anyt = (L[b] <= o) if hi_side else (H[b] >= o)
            if k == 0:
                anyt = path                                     # the hour's first bar opens at the hour's open
            rows.append(dict(date=d, hour=h, seg=int((tod[b] - h * 60) // 20) + 1, side="high" if hi_side else "low",
                             early=bool(day.early), rev=bool(later or path), rev_later=later,
                             rev_any=bool(later or anyt), first_bar=bool(k == 0)))
    return pd.DataFrame(rows), cnt


def _r(x, claimed=None):
    out = dict(n=int(len(x)), reverted=int(x.rev.sum()) if len(x) else 0,
               rate=round(float(x.rev.mean()), 4) if len(x) else None,
               rate_later=round(float(x.rev_later.mean()), 4) if len(x) else None,
               rate_any=round(float(x.rev_any.mean()), 4) if len(x) else None)
    if claimed is not None:
        out["claimed"] = claimed
    return out


def measure(ctx):
    x, cnt = _rows(ctx)
    res = dict(claim="first breach of the previous hour's high / low -> the hour's open trades before the hour ends",
               span=f"{ctx.days.index[0].date()} -> {ctx.days.index[-1].date()}", days=int(len(ctx.days)),
               counts=dict(cnt, breaches=int(len(x)), breaches_in_the_hours_first_bar=int(x.first_bar.sum())),
               overall=_r(x, CLAIMED["overall"]),
               h13_seg1=_r(x[(x.hour == 13) & (x.seg == 1)], CLAIMED["h13_seg1"]),
               h09_seg1=_r(x[(x.hour == 9) & (x.seg == 1)], CLAIMED["h09_seg1"]),
               by_hour={f"{h:02d}:00": _r(x[x.hour == h]) for h in HOURS},
               by_segment={f"seg{s}": _r(x[x.seg == s]) for s in (1, 2, 3)},
               by_hour_and_segment={f"{h:02d}:00 seg{s}": _r(x[(x.hour == h) & (x.seg == s)])
                                    for h in HOURS for s in (1, 2, 3)},
               by_side={s: _r(x[x.side == s]) for s in ("high", "low")},
               by_year={int(y): _r(g) for y, g in x.groupby(pd.DatetimeIndex(x.date).year)},
               without_early_close_days=_r(x[~x.early], CLAIMED["overall"]))
    return res


def show(res):
    c = res["counts"]
    print(res["claim"], "  ", res["span"], f"  {res['days']} cash days")
    print(f"hours with bars {c['hours']}: contract change {c['contract_change']}, open not strictly inside "
          f"{c['not_inside']}, no breach {c['no_breach']}, both levels in the first breaching bar "
          f"{c['both_in_one_bar']}, first breaches {c['breaches']} (in the hour's first bar "
          f"{c['breaches_in_the_hours_first_bar']})")

    def line(name, r):
        if not r["n"]:
            return f"{name:<22} n     0"
        cl = f"   claimed {r['claimed']:.1%}" if "claimed" in r else ""
        return (f"{name:<22} n {r['n']:>5}  open traded {r['reverted']:>5} = {r['rate']:.1%}{cl}"
                f"   (later bars only {r['rate_later']:.1%}, any touch on the breach bar {r['rate_any']:.1%})")

    print(line("overall", res["overall"]))
    print(line("13:00 first segment", res["h13_seg1"]))
    print(line("09:00 first segment", res["h09_seg1"]))
    print(line("no early-close days", res["without_early_close_days"]))
    for k, r in res["by_segment"].items():
        print(line(k, r))
    for k, r in res["by_side"].items():
        print(line("breach of the " + k, r))
    print("by hour and segment (rate, n):")
    for h in HOURS:
        hh = f"{h:02d}:00"
        r = res["by_hour"][hh]
        cells = []
        for s in (1, 2, 3):
            q = res["by_hour_and_segment"][f"{hh} seg{s}"]
            cells.append(f"seg{s} {q['rate']:.1%} ({q['n']})" if q["n"] else f"seg{s} - (0)")
        print(f"  {hh}  all {r['rate']:.1%} ({r['n']})   " + "   ".join(cells))
    print("by year: " + "  ".join(f"{y} {r['rate']:.1%} (n {r['n']})" for y, r in res["by_year"].items()))
