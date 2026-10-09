#!/usr/bin/env python3
"""RE10a - E10a first hour continuation, second independent coding from the spec text.

Spec (YT1_SPEC.md, E10a): At the 10:29 close: long if above the 09:30 open, short if below. No stop, flat bar.
Neighbours: 09:59, 10:59.

Coded as: one market order a day at the close of the 1-minute bar stamped `hm`, long if that close > the 09:30 bar's
open, short if <, nothing if equal or if that minute has no bar. Exit at the flat bar. R unit = 0.1 x daily ATR(14).
"""
import core

ID = "RE10a"
NAME = "First hour continuation (E10a, second coder)"
VARIANTS = {
    "base": dict(hm="10:29"),
    "nb1": dict(hm="09:59"),
    "nb2": dict(hm="10:59"),
}


def orders(ctx, hm="10:29"):
    out = []
    for d, day in ctx.days.iterrows():
        if not day.atr == day.atr:
            continue                                  # no daily ATR: no R unit, and the day is not traded
        i = ctx.idx(d, hm)
        if i is None:
            continue
        i = int(i)
        c, o = ctx.C[i], float(day.o930)
        if c == o:
            continue
        side = 1 if c > o else -1
        out.append(dict(i=i, side=side, etype="close", exit_i=int(day.i_end), r_pts=0.1 * float(day.atr),
                        tag="L" if side > 0 else "S"))
    return out


def trades(ctx, **p):
    return core.run_orders(ctx, orders(ctx, **p), max_per_day=1)
