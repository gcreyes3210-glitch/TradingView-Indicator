#!/usr/bin/env python3
"""T20 - Hull MA(100) crosses above SMA200 (short: crosses below). YT2 trigger; the frame is tools/yt1/frame_t.py.

HMA(100) = WMA(2 x WMA(close, 50) - WMA(close, 100), 10)  (10 = round(sqrt(100)); ind.hma, TradingView's ta.hma).
SMA200 = the mean of the last 200 closes (ind.sma).
"""
import numpy as np
import core
import ind
import frame_t

ID = "T20"
NAME = "TRADING RUSH Hull MA(100) crosses SMA200 + EMA200"
VARIANTS = {"base": dict(tf=5), "nb1": dict(tf=3), "nb2": dict(tf=15)}

HULL, SLOW = 100, 200


def trigger(o, h, l, c, v):
    f, s = ind.hma(c, HULL), ind.sma(c, SLOW)
    with np.errstate(invalid="ignore"):
        long_, short_ = ind.crossed_up(f, s), ind.crossed_dn(f, s)
    return dict(long=long_, short=short_, stop_l=None, stop_s=None)


def orders(ctx, tf=5):
    return frame_t.orders(ctx, tf, trigger)


def trades(ctx, **p):
    return core.run_orders(ctx, orders(ctx, **p), one_at_a_time=True, skip_roll=2)
