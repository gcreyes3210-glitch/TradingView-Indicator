#!/usr/bin/env python3
"""T10 - TRADING RUSH single trigger: Relative Vigor Index(10) crosses above its signal with both below zero.

Trigger only; the frame (frame_t.py) does the rest.
RVI (TradingView built-in, length 10): swma(x) = (x[k-3] + 2 x[k-2] + 2 x[k-1] + x[k]) / 6;
    RVI = sum over the last 10 bars of swma(close - open)  /  sum over the last 10 bars of swma(high - low);
    signal = swma(RVI).   A zero denominator gives no value (as on TradingView).
Arithmetic: the two sums are taken before the division by 6 (which cancels), so they are exact sums of tick-grid
numbers and an RVI of exactly zero comes out as 0.0, not as +/- 1e-14; the signal is coded as
RVI[k] + ((RVI[k-3] - RVI[k]) + 2 (RVI[k-2] - RVI[k]) + 2 (RVI[k-1] - RVI[k])) / 6, the same weighted average, which
returns RVI[k] itself when the four values are equal (a flat RVI is then "at", not above or below, its signal).
Long:  RVI crosses above the signal, with RVI < 0 and signal < 0 on the cross bar.
Short: RVI crosses below the signal, with RVI > 0 and signal > 0 on the cross bar.
"""
import numpy as np
import core
import ind
import frame_t
from s_T04 import rsum

ID = "T10"
NAME = "TRADING RUSH RVI(10) crosses its signal below zero + EMA200"
VARIANTS = {"base": dict(tf=5), "nb1": dict(tf=3), "nb2": dict(tf=15)}


def swsum(x):
    """6 x swma(x) = x[k-3] + 2 x[k-2] + 2 x[k-1] + x[k] (exact for tick-grid x)."""
    x = np.asarray(x, float)
    out = np.full(len(x), np.nan)
    out[3:] = x[:-3] + 2 * x[1:-2] + 2 * x[2:-1] + x[3:]
    return out


def swma(x):
    """(x[k-3] + 2 x[k-2] + 2 x[k-1] + x[k]) / 6, written around x[k]."""
    x = np.asarray(x, float)
    out = np.full(len(x), np.nan)
    out[3:] = x[3:] + ((x[:-3] - x[3:]) + 2 * (x[1:-2] - x[3:]) + 2 * (x[2:-1] - x[3:])) / 6
    return out


def rvi(o, h, l, c, n=10):
    """Returns (RVI, signal)."""
    num, den = rsum(swsum(c - o), n), rsum(swsum(h - l), n)      # 6 x the two sums; the 6 cancels
    with np.errstate(divide="ignore", invalid="ignore"):
        r = num / den
    r[den == 0] = np.nan
    return r, swma(r)


def trigger(o, h, l, c, v):
    r, s = rvi(o, h, l, c, 10)
    with np.errstate(invalid="ignore"):
        long_ = ind.crossed_up(r, s) & (r < 0) & (s < 0)
        short_ = ind.crossed_dn(r, s) & (r > 0) & (s > 0)
    return dict(long=long_, short=short_, stop_l=None, stop_s=None)


def orders(ctx, tf=5):
    return frame_t.orders(ctx, tf, trigger)


def trades(ctx, **p):
    return core.run_orders(ctx, orders(ctx, **p), one_at_a_time=True, skip_roll=2)
