#!/usr/bin/env python3
"""T21 - McGinley Dynamic(9) crosses above McGinley Dynamic(21) (short: crosses below).
YT2 trigger; the frame is tools/yt1/frame_t.py.

MD[0] = close[0];  MD[k] = MD[k-1] + (close[k] - MD[k-1]) / (n x (close[k] / MD[k-1]) ** 4)   (the spec's formula,
seeded with the first close of the series). Recursive, so it is a plain loop; each value uses closes up to k only.
"""
import numpy as np
import core
import ind
import frame_t

ID = "T21"
NAME = "TRADING RUSH McGinley Dynamic(9) crosses McGinley Dynamic(21) + EMA200"
VARIANTS = {"base": dict(tf=5), "nb1": dict(tf=3), "nb2": dict(tf=15)}

FAST, SLOW = 9, 21


def mcginley(c, n):
    x = np.asarray(c, float).tolist()
    out = [0.0] * len(x)
    if not x:
        return np.asarray(out)
    md = x[0]
    out[0] = md
    for i in range(1, len(x)):
        md = md + (x[i] - md) / (n * (x[i] / md) ** 4)
        out[i] = md
    return np.asarray(out)


def trigger(o, h, l, c, v):
    f, s = mcginley(c, FAST), mcginley(c, SLOW)
    long_, short_ = ind.crossed_up(f, s), ind.crossed_dn(f, s)
    return dict(long=long_, short=short_, stop_l=None, stop_s=None)


def orders(ctx, tf=5):
    return frame_t.orders(ctx, tf, trigger)


def trades(ctx, **p):
    return core.run_orders(ctx, orders(ctx, **p), one_at_a_time=True, skip_roll=2)
