#!/usr/bin/env python3
"""T00 - the pattern every YT2 module follows (shown on C19b's Keltner trigger; not a YT2 test).

A YT2 module is only a trigger: bool arrays over the tf-minute bar series, each value built from bars up to and
including that bar. The frame (tools/yt1/frame_t.py) adds the window, the EMA200 side filter, the stop, the 1.5R
target and the fills. Do not re-implement any of that.
"""
import numpy as np
import core
import ind
import frame_t

ID = "T00"
NAME = "Keltner (20, 2 x ATR10) open-and-close outside (pattern module)"
VARIANTS = {"base": dict(tf=5), "nb1": dict(tf=3), "nb2": dict(tf=15)}


def trigger(o, h, l, c, v):
    _, up, lo = ind.keltner(h, l, c, n=20, mult=2.0, atr_len=10)
    with np.errstate(invalid="ignore"):
        above, below = (o > up) & (c > up), (o < lo) & (c < lo)
    known = np.isfinite(up)
    long_, short_ = np.zeros(len(c), bool), np.zeros(len(c), bool)
    long_[1:] = above[1:] & ~above[:-1] & known[:-1]
    short_[1:] = below[1:] & ~below[:-1] & known[:-1]
    return dict(long=long_, short=short_, stop_l=None, stop_s=None)     # stop_l / stop_s: an own stop level per bar, or None


def orders(ctx, tf=5):
    return frame_t.orders(ctx, tf, trigger)                              # T27 only: frame_t.orders(ctx, tf, trigger, ema_filter=False)


def trades(ctx, **p):
    return core.run_orders(ctx, orders(ctx, **p), one_at_a_time=True, skip_roll=2)
