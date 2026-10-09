#!/usr/bin/env python3
"""G1 - TTrades: the daily bias on its own (YT4_SPEC.md, Part 2).

Rule: bias bullish -> long at the 09:30 open, bearish -> short; no stop; flat at the flat bar. R unit 0.1 x daily ATR.
Neighbours: `cont` days only; `fail` days only.

How it is coded:
  * the bias is tt.bias(ctx) as it stands (candle 1 = the 18:00 -> 17:00 trading day that closed the evening before,
    candle 2 = the one before it; no bias across a contract roll). It is complete at 17:00 the evening before.
  * "at the 09:30 open": etype 'open' with i = the last 1-minute bar before the 09:30 bar, so the fill is the open of
    the 09:30 bar (plus the house tick of slippage). Nothing of the 09:30 bar is read.
  * no stop, no target; exit at the close of the flat bar (day.i_end); r_pts = 0.1 x day.atr (the daily ATR(14)
    through the previous trading day).
  * one order a day; roll days and days without an ATR are dropped by core.run_orders.
"""
import numpy as np
import core
import tt

ID = "G1"
NAME = "TTrades daily bias on its own (09:30 open to the flat bar)"
VARIANTS = {
    "base": dict(kind=None),          # every day with a bias
    "nb1": dict(kind="cont"),         # the bias comes from a continuation close
    "nb2": dict(kind="fail"),         # the bias comes from a failed run
}


def orders(ctx, kind=None):
    B = tt.bias(ctx)
    out = []
    for d, day in ctx.days.iterrows():
        b = B.loc[d]
        side = int(b.bias)
        if side == 0 or (kind is not None and b.kind != kind):
            continue
        if not np.isfinite(day.atr):
            continue                                   # no R unit (the harness drops these days as well)
        i = int(day.i_open) - 1                        # the last 1-minute bar before 09:30
        if i < 0:
            continue
        out.append(dict(i=i, side=side, etype="open", exit_i=int(day.i_end), r_pts=0.1 * float(day.atr),
                        tag=("L|" if side > 0 else "S|") + str(b.kind)))
    return out


def trades(ctx, **p):
    return core.run_orders(ctx, orders(ctx, **p), max_per_day=1)
