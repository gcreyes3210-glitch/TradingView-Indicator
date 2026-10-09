#!/usr/bin/env python3
"""C19b - TRADING RUSH single trigger: a bar that opens and closes outside the Keltner channel, with the 200 EMA.

Frame: s_C19a.frame_orders (Family C common frame, swing stop, 1.5R, EMA200 side filter).
Keltner as the spec states it: EMA20 basis, 2 x ATR(10) (Wilder).
Long:  a bar that opens and closes above the upper Keltner after one that did not. Short: mirror at the lower line.
"""
import numpy as np
import core
import ind
import s_C19a as frame

ID = "C19b"
NAME = "TRADING RUSH Keltner (20, 2 x ATR10) open-and-close outside + EMA200"
VARIANTS = {
    "base": dict(tf=5),
    "nb1": dict(tf=3),
    "nb2": dict(tf=15),
}


def trigger(o, h, l, c):
    _, up, lo = ind.keltner(h, l, c, n=20, mult=2.0, atr_len=10)
    with np.errstate(invalid="ignore"):
        above = (o > up) & (c > up)                 # False while the channel is warming up
        below = (o < lo) & (c < lo)
    known = np.isfinite(up) & np.isfinite(lo)
    ls, ss = np.zeros(len(c), bool), np.zeros(len(c), bool)
    ls[1:] = above[1:] & ~above[:-1] & known[:-1]   # the previous bar had a channel and did not do it
    ss[1:] = below[1:] & ~below[:-1] & known[:-1]
    return ls, ss


def orders(ctx, tf=5):
    return frame.frame_orders(ctx, tf, trigger)


def trades(ctx, **p):
    return core.run_orders(ctx, orders(ctx, **p), one_at_a_time=True, skip_roll=2)
