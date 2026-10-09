#!/usr/bin/env python3
"""E10a - First hour continuation (edgeful opening-candle report).

Spec text (YT1_SPEC.md, E10a):
  At the 10:29 close: long if above the 09:30 open, short if below. No stop, flat bar.
  Neighbours: 09:59, 10:59.

Readings added (fixed before the first run; see notes/E10a.md):
  * the decision bar is the 1-minute bar stamped 10:29 (09:59 / 10:59); a day on which that minute has no bar is
    not traded.
  * "above" / "below" are strict; a close equal to the 09:30 open is no trade.
  * no stop, so the R unit is 0.1 x the day's daily ATR(14) (the common rule).
"""
import core

ID = "E10a"
NAME = "First hour continuation: at the 10:29 close, with the side of the 09:30 open, no stop, flat bar"
VARIANTS = {
    "base": dict(at="10:29"),
    "nb1": dict(at="09:59"),
    "nb2": dict(at="10:59"),
}


def orders(ctx, at="10:29"):
    C = ctx.C
    out = []
    for d, day in ctx.days.iterrows():
        if not (day.atr == day.atr):                        # no daily ATR: no R unit (and the day is not traded)
            continue
        i = ctx.idx(d, at)
        if i is None:
            continue
        i = int(i)
        if i <= int(day.i_open) or i >= int(day.i_end):
            continue
        c, o = float(C[i]), float(day.o930)
        side = 1 if c > o else -1 if c < o else 0
        if not side:
            continue
        out.append(dict(i=i, side=side, etype="close", exit_i=int(day.i_end), r_pts=0.1 * float(day.atr),
                        tag="L" if side > 0 else "S"))
    return out


def trades(ctx, **p):
    return core.run_orders(ctx, orders(ctx, **p), max_per_day=1)
