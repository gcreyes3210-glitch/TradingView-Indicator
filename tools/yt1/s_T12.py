#!/usr/bin/env python3
"""T12 - TRADING RUSH single trigger: Chaikin Money Flow(20) crosses above zero (short: crosses below zero).

Trigger only; the frame (frame_t.py) does the rest.
CMF (TradingView built-in, length 20): money-flow volume of a bar = ((2 x close - low - high) / (high - low)) x volume,
0 when high = low;  CMF = sum of the last 20 bars' money-flow volume / sum of the last 20 bars' volume.
Volume = the bar's summed 1-minute MNQ volume (the frame's v).
Arithmetic: the 20-bar sum of money-flow volume is taken over its own window (not as a difference of running totals,
whose rounding error of about 1e-8 would depend on all earlier bars), and where it comes out within 1e-9 of zero
relative to the sizes summed it is recomputed in exact fractions, so that a sum of exactly zero is 0.0.
"""
from fractions import Fraction
import numpy as np
from numpy.lib.stride_tricks import sliding_window_view
import core
import ind
import frame_t
from s_T04 import rsum

ID = "T12"
NAME = "TRADING RUSH Chaikin Money Flow(20) zero cross + EMA200"
VARIANTS = {"base": dict(tf=5), "nb1": dict(tf=3), "nb2": dict(tf=15)}


def mfv(h, l, c, v):
    """Money-flow volume per bar (the accumulation / distribution increment)."""
    rng = h - l
    with np.errstate(divide="ignore", invalid="ignore"):
        m = np.where(rng > 0, (2 * c - l - h) / rng, 0.0)
    return m * v


def mfv_sum(h, l, c, v, n):
    """Sum of the last n bars' money-flow volume."""
    m = mfv(h, l, c, v)
    out = np.full(len(m), np.nan)
    if len(m) < n:
        return out
    out[n - 1:] = sliding_window_view(m, n).sum(axis=1)
    size = sliding_window_view(np.abs(m), n).sum(axis=1)
    for k in np.flatnonzero(np.abs(out[n - 1:]) <= 1e-9 * size) + n - 1:      # (near) zero: redo in exact fractions
        tot = Fraction(0)
        for j in range(k - n + 1, k + 1):
            if h[j] > l[j]:
                tot += Fraction(float(2 * c[j] - l[j] - h[j])) / Fraction(float(h[j] - l[j])) * Fraction(float(v[j]))
        out[k] = float(tot)
    return out


def cmf(h, l, c, v, n=20):
    sv = rsum(v, n)
    with np.errstate(divide="ignore", invalid="ignore"):
        out = mfv_sum(h, l, c, v, n) / sv
    out[sv == 0] = np.nan
    return out


def trigger(o, h, l, c, v):
    x = cmf(h, l, c, v, 20)
    return dict(long=ind.crossed_up(x, 0.0), short=ind.crossed_dn(x, 0.0), stop_l=None, stop_s=None)


def orders(ctx, tf=5):
    return frame_t.orders(ctx, tf, trigger)


def trades(ctx, **p):
    return core.run_orders(ctx, orders(ctx, **p), one_at_a_time=True, skip_roll=2)
