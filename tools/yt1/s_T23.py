#!/usr/bin/env python3
"""T23 - RSI(14) crosses above 70 with ADX(14, 14) >= 25 (short: RSI crosses below 30 with ADX >= 25).
Own stop: EMA21 of the close. YT2 trigger; the frame is tools/yt1/frame_t.py.

RSI = ind.rsi (Wilder averages of the up and down closes, alpha 1/14). ADX = ind.dmi(h, l, c, 14, 14)[2]: the Wilder
average (14) of DX = 100 x |+DI - -DI| / (+DI + -DI), with +DI / -DI = 100 x Wilder(+DM / -DM, 14) / Wilder(TR, 14).
ADX is read on the signal bar. The stop level handed to the frame is EMA21 (ind.ema) at every bar; the frame reads it
on the signal bar.
"""
import numpy as np
import core
import ind
import frame_t

ID = "T23"
NAME = "TRADING RUSH RSI crosses 70 / 30 with ADX >= 25, stop at EMA21 + EMA200"
VARIANTS = {"base": dict(tf=5), "nb1": dict(tf=3), "nb2": dict(tf=15)}

RSI_LEN, HI, LO = 14, 70.0, 30.0
DI_LEN, ADX_LEN, ADX_MIN = 14, 14, 25.0
STOP_EMA = 21


def trigger(o, h, l, c, v):
    r = ind.rsi(c, RSI_LEN)
    adx = ind.dmi(h, l, c, DI_LEN, ADX_LEN)[2]
    e21 = ind.ema(c, STOP_EMA)
    with np.errstate(invalid="ignore"):
        strong = adx >= ADX_MIN
        long_ = ind.crossed_up(r, HI) & strong
        short_ = ind.crossed_dn(r, LO) & strong
    return dict(long=long_, short=short_, stop_l=e21, stop_s=e21)


def orders(ctx, tf=5):
    return frame_t.orders(ctx, tf, trigger)


def trades(ctx, **p):
    return core.run_orders(ctx, orders(ctx, **p), one_at_a_time=True, skip_roll=2)
