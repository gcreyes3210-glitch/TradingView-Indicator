#!/usr/bin/env python3
"""T11 - TRADING RUSH single trigger: Relative Vigor Index(10) crosses above its signal with both above zero.

Trigger only; the frame (frame_t.py) does the rest. RVI and its signal as T10 (s_T10.rvi).
Long:  RVI crosses above the signal, with RVI > 0 and signal > 0 on the cross bar.
Short: RVI crosses below the signal, with RVI < 0 and signal < 0 on the cross bar.
"""
import numpy as np
import core
import ind
import frame_t
from s_T10 import rvi

ID = "T11"
NAME = "TRADING RUSH RVI(10) crosses its signal above zero + EMA200"
VARIANTS = {"base": dict(tf=5), "nb1": dict(tf=3), "nb2": dict(tf=15)}


def trigger(o, h, l, c, v):
    r, s = rvi(o, h, l, c, 10)
    with np.errstate(invalid="ignore"):
        long_ = ind.crossed_up(r, s) & (r > 0) & (s > 0)
        short_ = ind.crossed_dn(r, s) & (r < 0) & (s < 0)
    return dict(long=long_, short=short_, stop_l=None, stop_s=None)


def orders(ctx, tf=5):
    return frame_t.orders(ctx, tf, trigger)


def trades(ctx, **p):
    return core.run_orders(ctx, orders(ctx, **p), one_at_a_time=True, skip_roll=2)
