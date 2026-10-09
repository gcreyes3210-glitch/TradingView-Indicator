#!/usr/bin/env python3
"""T28 - MACD(12, 26, 9) crosses above its signal while Supertrend(10, 3) is up
(short: crosses below its signal while Supertrend is down). YT2 trigger; the frame is tools/yt1/frame_t.py.

MACD line = EMA12 - EMA26 of the close, signal = EMA9 of the MACD line (ind.macd). Supertrend = ind.supertrend
(direction +1 = up, -1 = down), read on the signal bar.
"""
import numpy as np
import core
import ind
import frame_t

ID = "T28"
NAME = "TRADING RUSH MACD crosses its signal with Supertrend + EMA200"
VARIANTS = {"base": dict(tf=5), "nb1": dict(tf=3), "nb2": dict(tf=15)}

FAST, SLOW, SIG = 12, 26, 9
ST_LEN, ST_FACTOR = 10, 3.0


def trigger(o, h, l, c, v):
    m, s, _ = ind.macd(c, FAST, SLOW, SIG)
    _, dr = ind.supertrend(h, l, c, ST_LEN, ST_FACTOR)
    with np.errstate(invalid="ignore"):
        long_ = ind.crossed_up(m, s) & (dr == 1)
        short_ = ind.crossed_dn(m, s) & (dr == -1)
    return dict(long=long_, short=short_, stop_l=None, stop_s=None)


def orders(ctx, tf=5):
    return frame_t.orders(ctx, tf, trigger)


def trades(ctx, **p):
    return core.run_orders(ctx, orders(ctx, **p), one_at_a_time=True, skip_roll=2)
