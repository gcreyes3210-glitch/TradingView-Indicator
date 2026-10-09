#!/usr/bin/env python3
"""E02 - NQ Stats IB breaks, trade the bias.

Spec text (YT1_SPEC.md, E02):
  At the 10:29 close: long if the close is above the IB midpoint and the IB low was set before the high; short
  mirror. Target: 1 tick beyond the IB high. Stop: beyond the IB low. Neighbours: IB ending 10:14, 10:44.

Readings added (fixed before the first run; see notes/E02.md):
  * IB = the 1-minute bars 09:30 .. `end` inclusive; the entry is a market order at the close of the bar stamped
    `end` (no bar at that minute = no trade that day).
  * "set before": the 1-minute bar that FIRST set the IB low is earlier than the one that first set the IB high.
    Both set in the same bar = no trade. "Above the midpoint" is strict (close == midpoint = no trade).
  * short mirror: close below the midpoint and the high set before the low; target 1 tick beyond the IB low, stop
    1 tick beyond the IB high.
  * a neighbour moves the IB's end and the entry with it.
"""
import numpy as np
import core

ID = "E02"
NAME = "NQ Stats IB breaks: at the IB close, with the midpoint / first-extreme bias, target the IB extreme"
VARIANTS = {
    "base": dict(end="10:29"),
    "nb1": dict(end="10:14"),
    "nb2": dict(end="10:44"),
}


def orders(ctx, end="10:29"):
    T = core.TICK
    out = []
    for d, day in ctx.days.iterrows():
        i = ctx.idx(d, end)                                     # the decision bar: the IB's last minute
        if i is None:
            continue
        i = int(i)
        lo0, _ = ctx.span(d, "09:30", end)
        if lo0 >= i:
            continue
        H, L = ctx.H[lo0:i + 1], ctx.L[lo0:i + 1]
        hi, lo = float(H.max()), float(L.min())
        i_hi, i_lo = int(H.argmax()), int(L.argmin())           # the bar that first set each extreme
        mid = (hi + lo) / 2.0
        c = float(ctx.C[i])
        if c > mid and i_lo < i_hi:
            o = dict(side=1, target=hi + T, stop=lo - T, tag="L")
        elif c < mid and i_hi < i_lo:
            o = dict(side=-1, target=lo - T, stop=hi + T, tag="S")
        else:
            continue
        o.update(i=i, etype="close", exit_i=int(day.i_end))
        out.append(o)
    return out


def trades(ctx, **p):
    return core.run_orders(ctx, orders(ctx, **p), max_per_day=1)
