#!/usr/bin/env python3
"""T19 - TEMA50 crosses above TEMA200 (short: crosses below). YT2 trigger; the frame is tools/yt1/frame_t.py.

TEMA(n) = 3 x e1 - 3 x e2 + e3 with e1 = EMA(close, n), e2 = EMA(e1, n), e3 = EMA(e2, n). EMA = TradingView's ta.ema:
alpha = 2 / (n + 1), seeded with the SMA of the first n values of its input (ind.ema; each later EMA starts on the
first bar where its input exists, ind.ema_nan). TEMA(n) therefore has its first value at bar 3n - 3.
"""
import numpy as np
import core
import ind
import frame_t

ID = "T19"
NAME = "TRADING RUSH TEMA50 crosses TEMA200 + EMA200"
VARIANTS = {"base": dict(tf=5), "nb1": dict(tf=3), "nb2": dict(tf=15)}

FAST, SLOW = 50, 200


def tema(x, n):
    e1 = ind.ema(x, n)
    e2 = ind.ema_nan(e1, n)
    e3 = ind.ema_nan(e2, n)
    return 3 * e1 - 3 * e2 + e3


def trigger(o, h, l, c, v):
    f, s = tema(c, FAST), tema(c, SLOW)
    with np.errstate(invalid="ignore"):
        long_, short_ = ind.crossed_up(f, s), ind.crossed_dn(f, s)
    return dict(long=long_, short=short_, stop_l=None, stop_s=None)


def orders(ctx, tf=5):
    return frame_t.orders(ctx, tf, trigger)


def trades(ctx, **p):
    return core.run_orders(ctx, orders(ctx, **p), one_at_a_time=True, skip_roll=2)
