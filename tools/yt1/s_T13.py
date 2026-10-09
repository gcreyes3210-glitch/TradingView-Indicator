#!/usr/bin/env python3
"""T13 - TRADING RUSH single trigger: Chaikin Oscillator crosses above zero (short: crosses below zero).

Trigger only; the frame (frame_t.py) does the rest.
Chaikin Oscillator (TradingView built-in, 3 / 10) = EMA3(ADL) - EMA10(ADL), where ADL (ta.accdist) is the running
sum from the first bar of ((2 x close - low - high) / (high - low)) x volume, 0 when high = low. EMAs are ta.ema.
(The oscillator does not depend on where the running sum starts: a constant added to ADL cancels in the difference.)
"""
import numpy as np
import core
import ind
import frame_t
from s_T12 import mfv

ID = "T13"
NAME = "TRADING RUSH Chaikin Oscillator (3, 10) zero cross + EMA200"
VARIANTS = {"base": dict(tf=5), "nb1": dict(tf=3), "nb2": dict(tf=15)}


def chaikin_osc(h, l, c, v, fast=3, slow=10):
    adl = np.cumsum(mfv(h, l, c, v))
    return ind.ema(adl, fast) - ind.ema(adl, slow)


def trigger(o, h, l, c, v):
    x = chaikin_osc(h, l, c, v)
    return dict(long=ind.crossed_up(x, 0.0), short=ind.crossed_dn(x, 0.0), stop_l=None, stop_s=None)


def orders(ctx, tf=5):
    return frame_t.orders(ctx, tf, trigger)


def trades(ctx, **p):
    return core.run_orders(ctx, orders(ctx, **p), one_at_a_time=True, skip_roll=2)
