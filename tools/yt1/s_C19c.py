#!/usr/bin/env python3
"""C19c - TRADING RUSH single trigger: DMI cross, with the 200 EMA.

Frame: s_C19a.frame_orders (Family C common frame, swing stop, 1.5R, EMA200 side filter).
Long:  +DI(14) crosses above -DI(14). Short: -DI(14) crosses above +DI(14).
"""
import core
import ind
import s_C19a as frame

ID = "C19c"
NAME = "TRADING RUSH DMI(14) +DI / -DI cross + EMA200"
VARIANTS = {
    "base": dict(tf=5),
    "nb1": dict(tf=3),
    "nb2": dict(tf=15),
}


def trigger(o, h, l, c):
    pdi, mdi, _ = ind.dmi(h, l, c, 14, 14)
    return ind.crossed_up(pdi, mdi), ind.crossed_up(mdi, pdi)


def orders(ctx, tf=5):
    return frame.frame_orders(ctx, tf, trigger)


def trades(ctx, **p):
    return core.run_orders(ctx, orders(ctx, **p), one_at_a_time=True, skip_roll=2)
