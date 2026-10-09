#!/usr/bin/env python3
"""T01 - TRADING RUSH single trigger: RSI(14) crosses above 50 (short: crosses below 50).

Trigger only; the frame (frame_t.py) adds the window, the EMA200 side filter, the swing stop, the 1.5R target, the fills.
RSI = ind.rsi (TradingView ta.rsi: Wilder averages of the up and down closes-to-close changes, seeded with their SMA).
"Crosses above 50" = RSI > 50 on this bar and <= 50 on the previous bar (ind.crossed_up).
"""
import numpy as np
import core
import ind
import frame_t

ID = "T01"
NAME = "TRADING RUSH RSI(14) crosses 50 + EMA200"
VARIANTS = {"base": dict(tf=5), "nb1": dict(tf=3), "nb2": dict(tf=15)}


def trigger(o, h, l, c, v):
    r = ind.rsi(c, 14)
    return dict(long=ind.crossed_up(r, 50.0), short=ind.crossed_dn(r, 50.0), stop_l=None, stop_s=None)


def orders(ctx, tf=5):
    return frame_t.orders(ctx, tf, trigger)


def trades(ctx, **p):
    return core.run_orders(ctx, orders(ctx, **p), one_at_a_time=True, skip_roll=2)
