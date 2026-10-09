#!/usr/bin/env python3
"""T16 - SMA50 crosses above SMA200 (short: crosses below). YT2 trigger; the frame is tools/yt1/frame_t.py.

SMA(n) at bar k = the mean of the n closes k-n+1 .. k (ind.sma). Cross = ind.crossed_up / crossed_dn:
above on this bar and at or below on the previous bar.
"""
import numpy as np
import core
import ind
import frame_t

ID = "T16"
NAME = "TRADING RUSH SMA50 crosses SMA200 + EMA200"
VARIANTS = {"base": dict(tf=5), "nb1": dict(tf=3), "nb2": dict(tf=15)}

FAST, SLOW = 50, 200


def trigger(o, h, l, c, v):
    f, s = ind.sma(c, FAST), ind.sma(c, SLOW)
    with np.errstate(invalid="ignore"):
        long_, short_ = ind.crossed_up(f, s), ind.crossed_dn(f, s)
    return dict(long=long_, short=short_, stop_l=None, stop_s=None)


def orders(ctx, tf=5):
    return frame_t.orders(ctx, tf, trigger)


def trades(ctx, **p):
    return core.run_orders(ctx, orders(ctx, **p), one_at_a_time=True, skip_roll=2)
