#!/usr/bin/env python3
"""T06 - TRADING RUSH single trigger: Williams %R(14) crosses above -80 (short: crosses below -20).

Trigger only; the frame (frame_t.py) does the rest.
%R (TradingView built-in, length 14, source close) = 100 x (close - HH) / (HH - LL), HH / LL = the highest high /
lowest low of the last 14 bars including this one; range -100 .. 0. HH = LL gives no value (as on TradingView).
"""
import numpy as np
import core
import ind
import frame_t

ID = "T06"
NAME = "TRADING RUSH Williams %R(14) crosses -80 / -20 + EMA200"
VARIANTS = {"base": dict(tf=5), "nb1": dict(tf=3), "nb2": dict(tf=15)}


def willr(h, l, c, n=14):
    hh, ll = ind.rolling_max(h, n), ind.rolling_min(l, n)
    with np.errstate(divide="ignore", invalid="ignore"):
        out = 100.0 * (c - hh) / (hh - ll)
    out[(hh - ll) == 0] = np.nan
    return out


def trigger(o, h, l, c, v):
    r = willr(h, l, c, 14)
    return dict(long=ind.crossed_up(r, -80.0), short=ind.crossed_dn(r, -20.0), stop_l=None, stop_s=None)


def orders(ctx, tf=5):
    return frame_t.orders(ctx, tf, trigger)


def trades(ctx, **p):
    return core.run_orders(ctx, orders(ctx, **p), one_at_a_time=True, skip_roll=2)
