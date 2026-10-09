#!/usr/bin/env python3
"""H3 - the previous-day box, edges only (Pat's Model D, Jdub's rejection play) (YT8_SPEC.md, Part 2).

Spec text:
  Only on days whose 09:30 open is inside the previous regular session's range. From 09:30 to 11:00: after a
  1-minute bar touches the previous session's low, the first 1-minute bar (that one or later) that closes above the
  previous bar's high and above that low is entered long at its close; mirror at the high. First such trade of the
  day only. Stop 1 tick beyond the lowest low from the touch through the entry bar. Target 2R. Neighbours 1.5R and 3R.

Readings added (fixed before the first run; see notes/H3.md):
  * previous regular session's high / low = days.pdh / days.pdl (the previous cash day's 09:30-15:59 bars).
  * "inside" includes the edges: pdl <= 09:30 open <= pdh.
  * "from 09:30 to 11:00" = the 1-minute bars stamped 09:30 ... 10:59; the touch and the entry bar are both among them.
  * "touches the low" = a bar's low at or below it (the grid's definition of a touch); the first such bar at or after
    09:30 is "the touch", and it stays the touch for the rest of the window. Mirror: high at or above the high.
  * "the previous bar" = the 1-minute bar just before in the series (for the 09:30 bar, the last pre-open bar).
  * "above" / "below" are strict.
  * 2R: target = close +/- k x |close - stop|, on the close before slippage (the house rule for R targets), put on the
    tick grid with core.tick_round (nearest).
  * the first bar that qualifies on either edge is the day's trade (one bar cannot qualify on both).
"""
import numpy as np
import core

ID = "H3"
NAME = "Previous-day box, edges only: touch of yesterday's high / low, confirmation close, kR target"
VARIANTS = {
    "base": dict(rr=2.0),
    "nb1": dict(rr=1.5),
    "nb2": dict(rr=3.0),
}


def orders(ctx, rr=2.0):
    H, L, C = ctx.H, ctx.L, ctx.C
    T = core.TICK
    out = []
    for d, day in ctx.days.iterrows():
        pdh, pdl = day.pdh, day.pdl
        if not (pdh == pdh and pdl == pdl):
            continue
        s0, s1 = ctx.span(d, "09:30", "11:00")          # 1-minute bars 09:30 .. 10:59
        if s1 <= s0 or s0 != int(day.i_open) or s0 < 1:
            continue
        o = ctx.O[s0]                                   # the 09:30 bar's open
        if not (pdl <= o <= pdh):
            continue
        lo_touch = hi_touch = None
        for k in range(s0, s1):
            if lo_touch is None and L[k] <= pdl:
                lo_touch = k
            if hi_touch is None and H[k] >= pdh:
                hi_touch = k
            c = C[k]
            if lo_touch is not None and c > H[k - 1] and c > pdl:
                stop = float(L[lo_touch:k + 1].min()) - T
                out.append(dict(i=k, side=1, etype="close", stop=stop,
                                target=float(core.tick_round(c + rr * (c - stop))), exit_i=int(day.i_end), tag="L"))
                break
            if hi_touch is not None and c < L[k - 1] and c < pdh:
                stop = float(H[hi_touch:k + 1].max()) + T
                out.append(dict(i=k, side=-1, etype="close", stop=stop,
                                target=float(core.tick_round(c - rr * (stop - c))), exit_i=int(day.i_end), tag="S"))
                break
    return out


def trades(ctx, **p):
    return core.run_orders(ctx, orders(ctx, **p), max_per_day=1, skip_roll=2)
