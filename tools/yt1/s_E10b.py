#!/usr/bin/env python3
"""E10b - 15:00 continuation (edgeful power-hour report).

Spec text (YT1_SPEC.md, E10b):
  At the 14:59 close: long if above the 09:30 open and above the middle of the day's range so far; short mirror.
  Stop: beyond the 09:30 open. Neighbours: 14:29, 15:29.

Readings added (fixed before the first run; see notes/E10b.md):
  * the decision bar is the 1-minute bar stamped 14:59 (14:29 / 15:29); a day on which that minute has no bar, or
    on which it is at or after the flat bar (early closes), is not traded.
  * "the day's range so far" = highest high / lowest low of the 1-minute bars from 09:30 through the decision bar;
    its middle is their average, not rounded. "Above" / "below" are strict.
  * stop = 1 tick beyond the 09:30 open (the common buffer rule). No target: the trade runs to the flat bar.
"""
import core

ID = "E10b"
NAME = "15:00 continuation: at the 14:59 close, with the side of the 09:30 open and of the range middle, stop beyond the open"
VARIANTS = {
    "base": dict(at="14:59"),
    "nb1": dict(at="14:29"),
    "nb2": dict(at="15:29"),
}


def orders(ctx, at="14:59"):
    H, L, C = ctx.H, ctx.L, ctx.C
    T = core.TICK
    out = []
    for d, day in ctx.days.iterrows():
        i = ctx.idx(d, at)
        if i is None:
            continue
        i, i0 = int(i), int(day.i_open)
        if i <= i0 or i >= int(day.i_end):
            continue
        hi, lo = float(H[i0:i + 1].max()), float(L[i0:i + 1].min())      # 09:30 .. the decision bar, inclusive
        mid = (hi + lo) / 2.0
        c, o = float(C[i]), float(day.o930)
        if c > o and c > mid:
            out.append(dict(i=i, side=1, etype="close", stop=o - T, exit_i=int(day.i_end), tag="L"))
        elif c < o and c < mid:
            out.append(dict(i=i, side=-1, etype="close", stop=o + T, exit_i=int(day.i_end), tag="S"))
    return out


def trades(ctx, **p):
    return core.run_orders(ctx, orders(ctx, **p), max_per_day=1)
