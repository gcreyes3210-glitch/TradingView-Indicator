#!/usr/bin/env python3
"""T22 - a bar that opens and closes above the SMA20 of highs, after one that did not
(short: opens and closes below the SMA20 of lows, after one that did not). YT2 trigger; the frame is frame_t.py.

SMA20 of highs at bar k = the mean of the 20 highs k-19 .. k (the bar's own high included, as TradingView plots it);
likewise the lows. "After one that did not": the previous bar did not both open and close beyond its own band value,
and the band existed on that previous bar (the same form as the pattern module's Keltner trigger).
"""
import numpy as np
import core
import ind
import frame_t

ID = "T22"
NAME = "TRADING RUSH open-and-close outside the SMA20 high / low channel + EMA200"
VARIANTS = {"base": dict(tf=5), "nb1": dict(tf=3), "nb2": dict(tf=15)}

LEN = 20


def trigger(o, h, l, c, v):
    up, lo = ind.sma(h, LEN), ind.sma(l, LEN)
    with np.errstate(invalid="ignore"):
        above, below = (o > up) & (c > up), (o < lo) & (c < lo)
    known = np.isfinite(up) & np.isfinite(lo)
    long_, short_ = np.zeros(len(c), bool), np.zeros(len(c), bool)
    long_[1:] = above[1:] & ~above[:-1] & known[:-1]
    short_[1:] = below[1:] & ~below[:-1] & known[:-1]
    return dict(long=long_, short=short_, stop_l=None, stop_s=None)


def orders(ctx, tf=5):
    return frame_t.orders(ctx, tf, trigger)


def trades(ctx, **p):
    return core.run_orders(ctx, orders(ctx, **p), one_at_a_time=True, skip_roll=2)
