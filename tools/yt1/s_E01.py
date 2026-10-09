#!/usr/bin/env python3
"""E01 - NQ Stats Hour Stats, fade the first breach of the previous hour's high / low back to the hour's open.

Spec text (YT1_SPEC.md, E01):
  Hours 09:00 ... 15:00 that open strictly inside the previous hour's range. Sell limit 1 tick above the previous
  hour's high and buy limit 1 tick below its low, resting for the hour's first 20 minutes; the first to fill is the
  trade; the level must be >= 0.10 % of price from the hour's open. Target: the hour's open. No stop; exit at the
  close of the hour's last bar. R unit = entry to the hour's open. One per hour.
  Neighbours: 0.05 %, 0.15 %.   Reported: stop1 = a stop the same distance beyond the entry.

Readings added (fixed before the first run; see notes/E01.md):
  * hours are clock hours; the previous hour of the 09:00 hour is 08:00-08:59. The hour's open is the open of its
    first 1-minute bar.
  * timing: the hour's open is not known at the close of the previous hour's last bar, so the decision bar is the
    hour's FIRST 1-minute bar (i = the HH:00 bar): its open is the hour's open, and the two limits rest from HH:01
    through HH:19. simulate cannot place a resting order at a bar's open. If that first bar has itself already traded
    at either limit price, the hour's first breach is over before an order can rest: no trade in that hour.
  * "the first to fill is the trade; the level must be >= x % from the open": both limits always compete; the one
    that fills first is the hour's trade, and it is taken only if ITS level (the previous hour's high for the sell,
    low for the buy) is at least x % of the hour's open away from the hour's open. If the first fill is at a nearer
    level there is no trade that hour (the later breach of the other side is not the first breach). An order whose
    level is too near is returned with a tag ending in "x" so trades() can apply this.
  * R unit = |limit price - the hour's open| (the order's price, before slippage).
  * stop1: stop = limit price +/- that same distance.
  * roll days and days without a daily ATR are not traded (applied in trades(), as run_orders does).
"""
import numpy as np
import pandas as pd
import core

ID = "E01"
NAME = "NQ Stats Hour Stats: fade the first breach of the previous hour's high / low to the hour's open"
VARIANTS = {
    "base": dict(min_pct=0.10),
    "nb1": dict(min_pct=0.05),
    "nb2": dict(min_pct=0.15),
    "stop1": dict(min_pct=0.10, stop1=True),
}
HOURS = range(9, 16)                                           # hours 09:00 ... 15:00
REST_MIN = 20                                                  # the limits rest for the hour's first 20 minutes


def orders(ctx, min_pct=0.10, stop1=False):
    """Two orders (sell limit, buy limit) for every hour that opens strictly inside the previous hour's range and
    whose first bar has not already traded at either limit price. tag = 'HHS' / 'HHL', plus 'x' when that order's
    level is nearer to the hour's open than min_pct % of the open."""
    O, H, L = ctx.O, ctx.H, ctx.L
    T = core.TICK
    out = []
    for d, day in ctx.days.iterrows():
        i_end = int(day.i_end)
        for h in HOURS:
            p0, p1 = ctx.span(d, (h - 1) * 60, h * 60)          # the previous clock hour
            c0, c1 = ctx.span(d, h * 60, (h + 1) * 60)          # this clock hour
            if p1 <= p0 or c1 <= c0:
                continue
            i = c0                                              # the hour's first bar; decision at its close
            if i >= i_end:
                continue
            ph, pl = float(H[p0:p1].max()), float(L[p0:p1].min())
            o = float(O[i])                                     # the hour's open
            if not (pl < o < ph):                               # opens strictly inside the previous hour's range
                continue
            sell, buy = ph + T, pl - T
            if H[i] >= sell or L[i] <= buy:                     # the first breach came in the hour's first minute
                continue
            _, e1 = ctx.span(d, h * 60, h * 60 + REST_MIN)
            expire = e1 - 1                                     # the last bar of the hour's first 20 minutes
            if expire <= i:
                continue
            exit_i = min(c1 - 1, i_end)                         # the hour's last bar, or the flat bar if earlier
            thr = min_pct / 100.0 * o
            for side, price, level in ((-1, sell, ph), (1, buy, pl)):
                r = abs(price - o)
                od = dict(i=int(i), side=side, etype="limit", price=price, expire=int(expire), target=o,
                          exit_i=int(exit_i), r_pts=r,
                          tag=f"{h:02d}{'S' if side < 0 else 'L'}" + ("" if abs(level - o) >= thr - 1e-9 else "x"))
                if stop1:
                    od["stop"] = price - side * r
                out.append(od)
    return out


def trades(ctx, **p):
    by = {}
    for o in orders(ctx, **p):
        by.setdefault(o["i"], []).append(o)
    out = []
    for i in sorted(by):
        d = pd.Timestamp(ctx.cdate[i])
        if d in ctx.roll_dates or d in ctx.noatr_dates or ctx.dayn[i] < 0:
            continue
        fills = []
        for o in by[i]:
            t = core.simulate(ctx, **o)
            if t is not None:
                fills.append(t)
        if not fills:
            continue
        fills.sort(key=lambda t: t["j"])
        if len(fills) == 2 and fills[0]["j"] == fills[1]["j"]:   # both limits filled in the same bar: take neither
            continue
        t = fills[0]                                            # the first to fill is the hour's trade
        if t["tag"].endswith("x"):                              # ... and its level is too near the hour's open
            continue
        out.append(t)
    return out
