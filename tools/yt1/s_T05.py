#!/usr/bin/env python3
"""T05 - TRADING RUSH single trigger: Chande Momentum Oscillator(9) crosses above 0 (short: crosses below 0).

Trigger only; the frame (frame_t.py) does the rest. CMO as T04 (s_T04.cmo).
"""
import numpy as np
import core
import ind
import frame_t
from s_T04 import cmo

ID = "T05"
NAME = "TRADING RUSH CMO(9) zero cross + EMA200"
VARIANTS = {"base": dict(tf=5), "nb1": dict(tf=3), "nb2": dict(tf=15)}


def trigger(o, h, l, c, v):
    x = cmo(c, 9)
    return dict(long=ind.crossed_up(x, 0.0), short=ind.crossed_dn(x, 0.0), stop_l=None, stop_s=None)


def orders(ctx, tf=5):
    return frame_t.orders(ctx, tf, trigger)


def trades(ctx, **p):
    return core.run_orders(ctx, orders(ctx, **p), one_at_a_time=True, skip_roll=2)
