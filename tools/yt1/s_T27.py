#!/usr/bin/env python3
"""T27 - RSI(14) crosses above 70 while Supertrend(10, 3) is up (short: RSI crosses below 30 while it is down).
NO EMA200 filter. Own stop: the Supertrend line. YT2 trigger; the frame is tools/yt1/frame_t.py.

Supertrend = ind.supertrend(h, l, c, 10, 3.0) (TradingView's ta.supertrend): bands = (high + low) / 2 -/+ 3 x ATR(10)
(Wilder), ratcheted; direction +1 = up (the line is the lower band, under price), -1 = down (the line is the upper
band). The direction and the line are read on the signal bar. The stop level handed to the frame is the line at every
bar; the frame reads it on the signal bar.
"""
import numpy as np
import core
import ind
import frame_t

ID = "T27"
NAME = "TRADING RUSH RSI crosses 70 / 30 with Supertrend, stop at the Supertrend line (no EMA200)"
VARIANTS = {"base": dict(tf=5), "nb1": dict(tf=3), "nb2": dict(tf=15)}

RSI_LEN, HI, LO = 14, 70.0, 30.0
ST_LEN, ST_FACTOR = 10, 3.0


def trigger(o, h, l, c, v):
    r = ind.rsi(c, RSI_LEN)
    line, dr = ind.supertrend(h, l, c, ST_LEN, ST_FACTOR)
    with np.errstate(invalid="ignore"):
        long_ = ind.crossed_up(r, HI) & (dr == 1)
        short_ = ind.crossed_dn(r, LO) & (dr == -1)
    return dict(long=long_, short=short_, stop_l=line, stop_s=line)


def orders(ctx, tf=5):
    return frame_t.orders(ctx, tf, trigger, ema_filter=False)


def trades(ctx, **p):
    return core.run_orders(ctx, orders(ctx, **p), one_at_a_time=True, skip_roll=2)
