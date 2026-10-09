#!/usr/bin/env python3
"""T18 - DEMA50 crosses above DEMA200 (short: crosses below). YT2 trigger; the frame is tools/yt1/frame_t.py.

DEMA(n) = 2 x EMA(close, n) - EMA(EMA(close, n), n). EMA = TradingView's ta.ema: alpha = 2 / (n + 1), seeded with the
SMA of the first n values of its input (ind.ema; the second EMA starts on the first bar where the first one exists,
ind.ema_nan). DEMA(n) therefore has its first value at bar 2n - 2.
"""
import numpy as np
import core
import ind
import frame_t

ID = "T18"
NAME = "TRADING RUSH DEMA50 crosses DEMA200 + EMA200"
VARIANTS = {"base": dict(tf=5), "nb1": dict(tf=3), "nb2": dict(tf=15)}

FAST, SLOW = 50, 200


def dema(x, n):
    e1 = ind.ema(x, n)
    e2 = ind.ema_nan(e1, n)
    return 2 * e1 - e2


def trigger(o, h, l, c, v):
    f, s = dema(c, FAST), dema(c, SLOW)
    with np.errstate(invalid="ignore"):
        long_, short_ = ind.crossed_up(f, s), ind.crossed_dn(f, s)
    return dict(long=long_, short=short_, stop_l=None, stop_s=None)


def orders(ctx, tf=5):
    return frame_t.orders(ctx, tf, trigger)


def trades(ctx, **p):
    return core.run_orders(ctx, orders(ctx, **p), one_at_a_time=True, skip_roll=2)
