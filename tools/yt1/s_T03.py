#!/usr/bin/env python3
"""T03 - TRADING RUSH single trigger: AO below zero and this is its third consecutive rising bar.

Trigger only; the frame (frame_t.py) does the rest.
AO as T02. A bar is "rising" when AO > the previous bar's AO (TradingView's green bar), "falling" when AO < it.
Long:  AO[k] < 0, bars k, k-1, k-2 rising and bar k-3 not rising (AO[k-3] <= AO[k-4], both known).
Short: AO[k] > 0, bars k, k-1, k-2 falling and bar k-3 not falling (AO[k-3] >= AO[k-4]).
"""
import numpy as np
import core
import ind
import frame_t
from s_T02 import ao

ID = "T03"
NAME = "TRADING RUSH Awesome Oscillator third rising bar below zero + EMA200"
VARIANTS = {"base": dict(tf=5), "nb1": dict(tf=3), "nb2": dict(tf=15)}


def trigger(o, h, l, c, v):
    a = ao(h, l)
    d = np.diff(a, prepend=np.nan)                 # d[k] = AO[k] - AO[k-1]
    known = np.isfinite(d)
    rise, fall = d > 0, d < 0                      # False where unknown
    long_, short_ = np.zeros(len(c), bool), np.zeros(len(c), bool)
    long_[3:] = (a[3:] < 0) & rise[3:] & rise[2:-1] & rise[1:-2] & known[:-3] & ~rise[:-3]
    short_[3:] = (a[3:] > 0) & fall[3:] & fall[2:-1] & fall[1:-2] & known[:-3] & ~fall[:-3]
    return dict(long=long_, short=short_, stop_l=None, stop_s=None)


def orders(ctx, tf=5):
    return frame_t.orders(ctx, tf, trigger)


def trades(ctx, **p):
    return core.run_orders(ctx, orders(ctx, **p), one_at_a_time=True, skip_roll=2)
