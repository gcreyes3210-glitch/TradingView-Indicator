#!/usr/bin/env python3
"""C19d - TRADING RUSH single trigger: Stochastic cross in the extreme zone, with the 200 EMA.

Frame: s_C19a.frame_orders (Family C common frame, swing stop, 1.5R, EMA200 side filter).
Stochastic (14, 3, 3). Long: %K crosses above %D with both under 20 (on the cross bar).
Short: %K crosses below %D with both over 80.
"""
import numpy as np
import core
import ind
import s_C19a as frame

ID = "C19d"
NAME = "TRADING RUSH Stochastic(14,3,3) cross under 20 / over 80 + EMA200"
VARIANTS = {
    "base": dict(tf=5),
    "nb1": dict(tf=3),
    "nb2": dict(tf=15),
}


def trigger(o, h, l, c):
    k, d = ind.stoch(h, l, c, 14, 3, 3)
    with np.errstate(invalid="ignore"):
        ls = ind.crossed_up(k, d) & (k < 20) & (d < 20)
        ss = ind.crossed_dn(k, d) & (k > 80) & (d > 80)
    return ls, ss


def orders(ctx, tf=5):
    return frame.frame_orders(ctx, tf, trigger)


def trades(ctx, **p):
    return core.run_orders(ctx, orders(ctx, **p), one_at_a_time=True, skip_roll=2)
