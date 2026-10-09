#!/usr/bin/env python3
"""T24 - close crosses above the Bollinger middle band with RSI(14) below 30 on at least one of the previous 10 bars
(short: close crosses below the middle band with RSI above 70 on at least one of the previous 10 bars).
YT2 trigger; the frame is tools/yt1/frame_t.py.

Middle band = SMA20 of the close (ind.bollinger(c, 20, 2)[0]). Cross: close[k] > mid[k] and close[k-1] <= mid[k-1].
"Previous 10 bars" = bars k-10 .. k-1; the signal bar itself is not counted.
"""
import numpy as np
import core
import ind
import frame_t

ID = "T24"
NAME = "TRADING RUSH close crosses the Bollinger middle after RSI < 30 / > 70 + EMA200"
VARIANTS = {"base": dict(tf=5), "nb1": dict(tf=3), "nb2": dict(tf=15)}

BB_LEN, BB_MULT = 20, 2.0
RSI_LEN, HI, LO = 14, 70.0, 30.0
RECENT = 10


def any_prev(cond, n):
    """True at bar k when cond was True on at least one of the bars k-n .. k-1 (bar k itself is not counted)."""
    cs = np.cumsum(np.r_[0, np.asarray(cond, bool).astype(np.int64)])       # cs[j] = number of True in cond[:j]
    k = np.arange(len(cond))
    return (cs[k] - cs[np.maximum(k - n, 0)]) > 0


def trigger(o, h, l, c, v):
    mid = ind.bollinger(c, BB_LEN, BB_MULT)[0]
    r = ind.rsi(c, RSI_LEN)
    with np.errstate(invalid="ignore"):
        was_low, was_high = any_prev(r < LO, RECENT), any_prev(r > HI, RECENT)
        long_ = ind.crossed_up(c, mid) & was_low
        short_ = ind.crossed_dn(c, mid) & was_high
    return dict(long=long_, short=short_, stop_l=None, stop_s=None)


def orders(ctx, tf=5):
    return frame_t.orders(ctx, tf, trigger)


def trades(ctx, **p):
    return core.run_orders(ctx, orders(ctx, **p), one_at_a_time=True, skip_roll=2)
