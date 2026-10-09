#!/usr/bin/env python3
"""C19e - TRADING RUSH single trigger: RSI back out of the extreme zone, with the 200 EMA.

Frame: s_C19a.frame_orders (Family C common frame, swing stop, 1.5R, EMA200 side filter).
Long:  RSI(14) crosses back above 30. Short: RSI(14) crosses back below 70.
"""
import core
import ind
import s_C19a as frame

ID = "C19e"
NAME = "TRADING RUSH RSI(14) back above 30 / below 70 + EMA200"
VARIANTS = {
    "base": dict(tf=5),
    "nb1": dict(tf=3),
    "nb2": dict(tf=15),
}


def trigger(o, h, l, c):
    r = ind.rsi(c, 14)
    return ind.crossed_up(r, 30.0), ind.crossed_dn(r, 70.0)


def orders(ctx, tf=5):
    return frame.frame_orders(ctx, tf, trigger)


def trades(ctx, **p):
    return core.run_orders(ctx, orders(ctx, **p), one_at_a_time=True, skip_roll=2)
