#!/usr/bin/env python3
"""T17 - WMA50 crosses above WMA200 (short: crosses below). Own stop: the WMA200 value on the cross bar.
YT2 trigger; the frame is tools/yt1/frame_t.py.

WMA(n) at bar k = sum(w_j * close[k-n+j], j = 1..n) / (n (n + 1) / 2) with w_j = j, so the newest close has weight n
(ind.wma). The stop level handed to the frame is WMA200 at every bar; the frame reads it on the signal (cross) bar,
puts the stop 1 tick beyond it when it is on the losing side of the entry and uses the swing stop when it is not.
"""
import numpy as np
import core
import ind
import frame_t

ID = "T17"
NAME = "TRADING RUSH WMA50 crosses WMA200, stop at WMA200 + EMA200"
VARIANTS = {"base": dict(tf=5), "nb1": dict(tf=3), "nb2": dict(tf=15)}

FAST, SLOW = 50, 200


def trigger(o, h, l, c, v):
    f, s = ind.wma(c, FAST), ind.wma(c, SLOW)
    with np.errstate(invalid="ignore"):
        long_, short_ = ind.crossed_up(f, s), ind.crossed_dn(f, s)
    return dict(long=long_, short=short_, stop_l=s, stop_s=s)


def orders(ctx, tf=5):
    return frame_t.orders(ctx, tf, trigger)


def trades(ctx, **p):
    return core.run_orders(ctx, orders(ctx, **p), one_at_a_time=True, skip_roll=2)
