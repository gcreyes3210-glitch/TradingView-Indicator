#!/usr/bin/env python3
"""T09 - TRADING RUSH single trigger: Fisher Transform(9) crosses above its trigger with both below zero.

Trigger only; the frame (frame_t.py) does the rest.
Fisher (TradingView built-in, length 9), m = (high + low) / 2, HH / LL = highest / lowest m of the last 9 bars:
    value  = 0.66 x ((m - LL) / (HH - LL) - 0.5) + 0.67 x previous value      (previous value 0 when there is none)
    value  = 0.999 if value > 0.99, -0.999 if value < -0.99                   (the clamped value is what is carried)
    fisher = 0.5 x ln((1 + value) / (1 - value)) + 0.5 x previous fisher      (previous fisher 0 when there is none)
    trigger line = the previous bar's fisher.
HH = LL gives no value on that bar and both recursions restart from 0 on the next (what Pine's na / nz() do).
Long:  fisher[k] > fisher[k-1] and fisher[k-1] <= fisher[k-2] (the cross), with fisher[k] < 0 and fisher[k-1] < 0
       (both lines below zero on the cross bar). Short: the mirror, both above zero.
"""
import math
import numpy as np
import core
import ind
import frame_t

ID = "T09"
NAME = "TRADING RUSH Fisher Transform(9) crosses its trigger below zero + EMA200"
VARIANTS = {"base": dict(tf=5), "nb1": dict(tf=3), "nb2": dict(tf=15)}


def fisher(h, l, n=9):
    m = (np.asarray(h, float) + np.asarray(l, float)) / 2
    hh, ll = ind.rolling_max(m, n), ind.rolling_min(m, n)
    rng = (hh - ll).tolist()
    pos = (m - ll).tolist()
    out = [math.nan] * len(m)
    val = fis = 0.0
    for i in range(len(m)):
        r = rng[i]
        if not r > 0:                              # warming up (NaN) or a flat 9-bar window: no value, restart
            val = fis = 0.0
            continue
        val = 0.66 * (pos[i] / r - 0.5) + 0.67 * val
        val = 0.999 if val > 0.99 else -0.999 if val < -0.99 else val
        fis = 0.5 * math.log((1 + val) / (1 - val)) + 0.5 * fis
        out[i] = fis
    return np.array(out)


def trigger(o, h, l, c, v):
    f = fisher(h, l, 9)
    t = np.r_[np.nan, f[:-1]]                      # the trigger line: the previous bar's fisher
    with np.errstate(invalid="ignore"):
        long_ = ind.crossed_up(f, t) & (f < 0) & (t < 0)
        short_ = ind.crossed_dn(f, t) & (f > 0) & (t > 0)
    return dict(long=long_, short=short_, stop_l=None, stop_s=None)


def orders(ctx, tf=5):
    return frame_t.orders(ctx, tf, trigger)


def trades(ctx, **p):
    return core.run_orders(ctx, orders(ctx, **p), one_at_a_time=True, skip_roll=2)
