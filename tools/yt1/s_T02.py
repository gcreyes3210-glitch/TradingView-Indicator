#!/usr/bin/env python3
"""T02 - TRADING RUSH single trigger: Awesome Oscillator crosses above zero (short: crosses below zero).

Trigger only; the frame (frame_t.py) does the rest.
AO (TradingView built-in) = SMA(hl2, 5) - SMA(hl2, 34), hl2 = (high + low) / 2.
Coded as (34 x S5 - 5 x S34) / 170 with S5 / S34 the sums of the last 5 / 34 hl2: prices sit on the 0.25 grid, so the
sums and the numerator are exact in floating point and AO's sign, and the order of two AO values, carry no rounding
noise (ind.sma(m, 5) - ind.sma(m, 34) is the same number to about 1e-12, which is enough to flip an exact tie).
"""
import numpy as np
import core
import ind
import frame_t
from s_T04 import rsum

ID = "T02"
NAME = "TRADING RUSH Awesome Oscillator (5, 34) zero cross + EMA200"
VARIANTS = {"base": dict(tf=5), "nb1": dict(tf=3), "nb2": dict(tf=15)}


def ao(h, l):
    m = (h + l) / 2                                # multiples of 0.125: exact
    return (34 * rsum(m, 5) - 5 * rsum(m, 34)) / 170


def trigger(o, h, l, c, v):
    a = ao(h, l)
    return dict(long=ind.crossed_up(a, 0.0), short=ind.crossed_dn(a, 0.0), stop_l=None, stop_s=None)


def orders(ctx, tf=5):
    return frame_t.orders(ctx, tf, trigger)


def trades(ctx, **p):
    return core.run_orders(ctx, orders(ctx, **p), one_at_a_time=True, skip_roll=2)
