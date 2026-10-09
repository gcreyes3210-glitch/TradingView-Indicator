#!/usr/bin/env python3
"""T14 - TRADING RUSH single trigger: close above the high of the latest confirmed up fractal, first bar to do so.

Trigger only; the frame (frame_t.py) does the rest.
Up fractal at bar f (the spec's words): high[f] > high[f-1], high[f-2], high[f+1] and high[f+2], all strictly.
It is confirmed, and first usable, at bar f+2. Down fractal: the mirror on the lows.
At bar k the level is the high of the most recent up fractal confirmed at or before k (f + 2 <= k). Long on the first
bar, from the confirmation bar on, whose close is above that level: one signal per fractal at most, and a newer
confirmed fractal replaces the level (with its own first close above it). Short: the mirror with down fractals.
"""
import numpy as np
import core
import ind
import frame_t

ID = "T14"
NAME = "TRADING RUSH Williams fractal breakout (close beyond the latest confirmed fractal) + EMA200"
VARIANTS = {"base": dict(tf=5), "nb1": dict(tf=3), "nb2": dict(tf=15)}


def confirmed_fractal(x):
    """conf[k] = True when bar k-2 is an up fractal of x (x[k-2] strictly above x[k-4], x[k-3], x[k-1], x[k]).
    Uses bars up to k only. For down fractals pass -low."""
    x = np.asarray(x, float)
    conf = np.zeros(len(x), bool)
    if len(x) >= 5:
        p = x[2:-2]
        conf[4:] = (p > x[:-4]) & (p > x[1:-3]) & (p > x[3:-1]) & (p > x[4:])
    return conf


def first_break(x, c):
    """(signal, level): level[k] = x at the latest fractal confirmed at or before k (NaN before the first);
    signal[k] = c[k] > level[k] for the first time since that fractal was confirmed. Pass (-low, -close) for shorts."""
    n = len(x)
    conf = confirmed_fractal(x)
    at = np.maximum.accumulate(np.where(conf, np.arange(n), -1))     # confirmation bar of the latest fractal
    have = at >= 0
    level = np.where(have, x[np.maximum(at - 2, 0)], np.nan)
    with np.errstate(invalid="ignore"):
        above = have & (c > level)
    cs = np.cumsum(above)
    start = np.maximum(at, 0)
    before = cs[start] - above[start]                                 # closes above counted before this fractal
    return above & (cs - before == 1), level


def trigger(o, h, l, c, v):
    long_, _ = first_break(h, c)
    short_, _ = first_break(-l, -c)
    return dict(long=long_, short=short_, stop_l=None, stop_s=None)


def orders(ctx, tf=5):
    return frame_t.orders(ctx, tf, trigger)


def trades(ctx, **p):
    return core.run_orders(ctx, orders(ctx, **p), one_at_a_time=True, skip_roll=2)
