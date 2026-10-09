#!/usr/bin/env python3
"""T08 - TRADING RUSH single trigger: PPO crosses above zero (short: crosses below zero).

Trigger only; the frame (frame_t.py) does the rest.
PPO (TradingView "Price Oscillator" built-in, 12 / 26, exponential, source close) = 100 x (EMA12 - EMA26) / EMA26.
"""
import numpy as np
import core
import ind
import frame_t

ID = "T08"
NAME = "TRADING RUSH PPO(12, 26) zero cross + EMA200"
VARIANTS = {"base": dict(tf=5), "nb1": dict(tf=3), "nb2": dict(tf=15)}


def ppo(c, fast=12, slow=26):
    es = ind.ema(c, slow)
    return 100.0 * (ind.ema(c, fast) - es) / es


def trigger(o, h, l, c, v):
    p = ppo(c)
    return dict(long=ind.crossed_up(p, 0.0), short=ind.crossed_dn(p, 0.0), stop_l=None, stop_s=None)


def orders(ctx, tf=5):
    return frame_t.orders(ctx, tf, trigger)


def trades(ctx, **p):
    return core.run_orders(ctx, orders(ctx, **p), one_at_a_time=True, skip_roll=2)
