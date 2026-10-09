#!/usr/bin/env python3
"""E04 - NQ Stats Noon Curve.

Spec text (YT1_SPEC.md, E04):
  Q1 = 08:00-09:59, Q2 = 10:00-11:59. At the 11:59 close: long if Q2 traded above Q1's high and not below Q1's low;
  short mirror. Stop: beyond Q2's low. No target. Neighbours: decision at 11:29, at 12:29.

Readings added (fixed before the first run; see notes/E04.md):
  * "traded above Q1's high" = Q2's high is at least 1 tick above Q1's high; "not below Q1's low" = Q2's low is at
    or above Q1's low. Short mirror: Q2 traded below Q1's low and not above Q1's high; stop 1 tick beyond Q2's high.
  * the entry is a market order at the close of the bar stamped at the decision minute (no such bar = no trade).
  * neighbours move the decision only; Q2 stays the clock window 10:00-11:59, as much of it as has traded by the
    decision: 10:00-11:29 for the 11:29 decision, the whole 10:00-11:59 for the 12:29 decision (bars 12:00-12:29 are
    not part of Q2). At 12:29 an order whose stop is already at or beyond the entry price is not a valid order and
    the harness drops it.
  * a day with no bars in Q1 or in Q2 is skipped. Exit: the stop or the flat bar.
"""
import numpy as np
import core

ID = "E04"
NAME = "NQ Stats Noon Curve: at the noon close, with Q2's one-sided break of Q1, stop beyond Q2's other extreme"
VARIANTS = {
    "base": dict(at="11:59"),
    "nb1": dict(at="11:29"),
    "nb2": dict(at="12:29"),
}
Q1 = ("08:00", "10:00")
Q2 = (600, 720)                                                 # 10:00 .. 11:59, in minutes after midnight


def orders(ctx, at="11:59"):
    T = core.TICK
    out = []
    for d, day in ctx.days.iterrows():
        i = ctx.idx(d, at)                                      # the decision bar
        if i is None:
            continue
        i = int(i)
        a0, a1 = ctx.span(d, *Q1)
        b0, b1 = ctx.span(d, Q2[0], min(Q2[1], core.hhmm(at) + 1))   # Q2 as far as it has traded by the decision
        if a1 <= a0 or b1 <= b0:
            continue
        assert b1 <= i + 1
        q1h, q1l = float(ctx.H[a0:a1].max()), float(ctx.L[a0:a1].min())
        q2h, q2l = float(ctx.H[b0:b1].max()), float(ctx.L[b0:b1].min())
        up, dn = q2h >= q1h + T, q2l <= q1l - T
        if up and not dn:
            o = dict(side=1, stop=q2l - T, tag="L")
        elif dn and not up:
            o = dict(side=-1, stop=q2h + T, tag="S")
        else:
            continue
        o.update(i=i, etype="close", exit_i=int(day.i_end))
        out.append(o)
    return out


def trades(ctx, **p):
    return core.run_orders(ctx, orders(ctx, **p), max_per_day=1)
