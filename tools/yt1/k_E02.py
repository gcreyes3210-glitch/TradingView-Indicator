#!/usr/bin/env python3
"""K-E02 - NQ Stats Initial Balance breaks: how often the IB high / low is broken by 12:00 and by 16:00, unfiltered
and by the two conditions (where the IB closed against its midpoint; which extreme was set first).

Definitions (the source's, research note E entry 2; fixed before the first run, see notes/K-E02.md):
  * IB = the 1-minute bars 09:30-10:29: high, low, midpoint = their average, close = the 10:29 bar's close.
  * qualifying session: a cash day of the day table whose first bar after the IB (10:30) opens inside the IB range
    (IB low <= open <= IB high). Other days are counted and left out.
  * break: any bar after the IB trading at least 1 tick beyond the level (high >= IB high + 0.25; low <= IB low -
    0.25), by noon = on bars 10:30-11:59, by close = on bars 10:30-15:59 (an early-close day ends at its halt).
  * close above / below the midpoint: strict. Low set first: the bar that FIRST set the IB low is earlier than the
    bar that first set the IB high (same bar = neither).
Every published figure is carried next to the measured one.
"""
import numpy as np
import pandas as pd
import core

NAME = "IB breaks: IB high / low broken by 12:00 and by 16:00, unfiltered and by midpoint close / first extreme"
# published (nqstats.com/ib_breaks.html, 2016-2026, 2,571 qualifying sessions): (n, by noon, by close)
PUB = {
    "unfiltered: high": (2571, 0.470, 0.629),
    "unfiltered: low": (2571, 0.398, 0.549),
    "unfiltered: either side": (2571, 0.825, 0.961),
    "close above midpoint: high": (1405, 0.701, 0.823),
    "close below midpoint: low": (1156, 0.658, 0.765),
    "low set first: high": (1298, 0.682, 0.809),
    "high set first: low": (1269, 0.578, 0.712),
    "both bullish: high": (1114, 0.740, 0.840),
    "both bearish: low": (974, 0.679, 0.780),
}


def _rows(ctx):
    T = core.TICK
    H, L = ctx.H, ctx.L
    rows, cnt = [], dict(days=0, no_ib_bar=0, opens_outside_ib=0)
    for d, day in ctx.days.iterrows():
        cnt["days"] += 1
        i = ctx.idx(d, "10:29")
        a0, a1 = ctx.span(d, "09:30", "10:30")
        n0, n1 = ctx.span(d, "10:30", "12:00")
        _, e1 = ctx.span(d, "10:30", "16:00")
        if i is None or a1 <= a0 or n1 <= n0:
            cnt["no_ib_bar"] += 1
            continue
        hi, lo = float(H[a0:a1].max()), float(L[a0:a1].min())
        if not (lo <= ctx.O[n0] <= hi):
            cnt["opens_outside_ib"] += 1
            continue
        i_hi, i_lo = int(H[a0:a1].argmax()), int(L[a0:a1].argmin())
        mid, c = (hi + lo) / 2.0, float(ctx.C[i])
        rows.append(dict(
            date=d, early=bool(day.early), above=c > mid, below=c < mid, low_first=i_lo < i_hi, high_first=i_hi < i_lo,
            hi_noon=bool(H[n0:n1].max() >= hi + T), hi_close=bool(H[n0:e1].max() >= hi + T),
            lo_noon=bool(L[n0:n1].min() <= lo - T), lo_close=bool(L[n0:e1].min() <= lo - T)))
    return pd.DataFrame(rows), cnt


def _table(x):
    sel = {
        "unfiltered: high": (x, "hi"), "unfiltered: low": (x, "lo"), "unfiltered: either side": (x, "either"),
        "close above midpoint: high": (x[x.above], "hi"), "close below midpoint: low": (x[x.below], "lo"),
        "low set first: high": (x[x.low_first], "hi"), "high set first: low": (x[x.high_first], "lo"),
        "both bullish: high": (x[x.above & x.low_first], "hi"), "both bearish: low": (x[x.below & x.high_first], "lo"),
    }
    out = {}
    for name, (g, what) in sel.items():
        if what == "either":
            noon, close = g.hi_noon | g.lo_noon, g.hi_close | g.lo_close
        else:
            noon, close = g[what + "_noon"], g[what + "_close"]
        pn, p_noon, p_close = PUB[name]
        out[name] = dict(n=int(len(g)), by_noon=round(float(noon.mean()), 4) if len(g) else None,
                         by_close=round(float(close.mean()), 4) if len(g) else None,
                         claimed_n=pn, claimed_by_noon=p_noon, claimed_by_close=p_close)
    return out


def measure(ctx):
    x, cnt = _rows(ctx)
    return dict(claim="IB high / low broken by 12:00 and by 16:00, unfiltered and by the two conditions",
                span=f"{ctx.days.index[0].date()} -> {ctx.days.index[-1].date()}",
                counts=dict(cnt, qualifying=int(len(x)), close_at_midpoint=int((~x.above & ~x.below).sum()),
                            extremes_in_same_bar=int((~x.low_first & ~x.high_first).sum()),
                            early_close_days=int(x.early.sum())),
                all_qualifying_sessions=_table(x), without_early_close_days=_table(x[~x.early]))


def show(res):
    c = res["counts"]
    print(res["claim"], "  ", res["span"])
    print(f"cash days {c['days']}: no 10:29 / 10:30 bar {c['no_ib_bar']}, 10:30 opens outside the IB "
          f"{c['opens_outside_ib']}, qualifying {c['qualifying']} (close at the midpoint {c['close_at_midpoint']}, "
          f"extremes in the same bar {c['extremes_in_same_bar']}, early-close days {c['early_close_days']})")
    for blk in ("all_qualifying_sessions", "without_early_close_days"):
        print(blk + ":   measured (claimed)")
        for name, r in res[blk].items():
            print(f"  {name:<28} n {r['n']:>4} ({r['claimed_n']:>4})   by noon {r['by_noon']:.1%} "
                  f"({r['claimed_by_noon']:.1%})   by close {r['by_close']:.1%} ({r['claimed_by_close']:.1%})")
