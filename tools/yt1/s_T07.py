#!/usr/bin/env python3
"""T07 - TRADING RUSH single trigger: TRIX(18) crosses above zero (short: crosses below zero).

Trigger only; the frame (frame_t.py) does the rest.
TRIX (TradingView built-in, length 18) = 10000 x (E3 - previous E3), E3 = EMA18(EMA18(EMA18(ln close))); each EMA is
ta.ema (alpha 2 / 19, seeded with the SMA of its first 18 values). The 1-bar change of a log series is the % change
the spec names, to first order, and has the same sign.
"""
import numpy as np
import core
import ind
import frame_t

ID = "T07"
NAME = "TRADING RUSH TRIX(18) zero cross + EMA200"
VARIANTS = {"base": dict(tf=5), "nb1": dict(tf=3), "nb2": dict(tf=15)}


def trix(c, n=18):
    e3 = ind.ema_nan(ind.ema_nan(ind.ema(np.log(np.asarray(c, float)), n), n), n)
    return 10000.0 * np.diff(e3, prepend=np.nan)


def trigger(o, h, l, c, v):
    t = trix(c, 18)
    return dict(long=ind.crossed_up(t, 0.0), short=ind.crossed_dn(t, 0.0), stop_l=None, stop_s=None)


def orders(ctx, tf=5):
    return frame_t.orders(ctx, tf, trigger)


def trades(ctx, **p):
    return core.run_orders(ctx, orders(ctx, **p), one_at_a_time=True, skip_roll=2)
