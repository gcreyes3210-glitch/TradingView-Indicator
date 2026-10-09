#!/usr/bin/env python3
"""T25 - RSI(14) crosses above 70 with a green cloud (short: RSI crosses below 30 with a red cloud).
YT2 trigger; the frame is tools/yt1/frame_t.py.

Ichimoku (9, 26, 52, 26), the cloud as in C19a: conversion = midpoint of the 9-bar high / low, base = midpoint of the
26-bar high / low, span A = (conversion + base) / 2, span B = midpoint of the 52-bar high / low, and the cloud at bar
k is the pair of spans computed at bar k - 26. Green = cloud A above cloud B at the signal bar; red = cloud A below
cloud B. Every window ends at the bar it is computed on, so the cloud at bar k uses bars up to k - 26 only.
"""
import numpy as np
import core
import ind
import frame_t

ID = "T25"
NAME = "TRADING RUSH RSI crosses 70 / 30 with a green / red Ichimoku cloud + EMA200"
VARIANTS = {"base": dict(tf=5), "nb1": dict(tf=3), "nb2": dict(tf=15)}

RSI_LEN, HI, LO = 14, 70.0, 30.0
CONV, BASE, SPAN_B, DISP = 9, 26, 52, 26


def cloud(h, l):
    """(cloud A, cloud B) at each bar = span A and span B computed DISP bars earlier (NaN while warming up)."""
    conv = (ind.rolling_max(h, CONV) + ind.rolling_min(l, CONV)) / 2
    base = (ind.rolling_max(h, BASE) + ind.rolling_min(l, BASE)) / 2
    span_a = (conv + base) / 2
    span_b = (ind.rolling_max(h, SPAN_B) + ind.rolling_min(l, SPAN_B)) / 2
    ca, cb = np.full(len(h), np.nan), np.full(len(h), np.nan)
    ca[DISP:], cb[DISP:] = span_a[:-DISP], span_b[:-DISP]
    return ca, cb


def trigger(o, h, l, c, v):
    r = ind.rsi(c, RSI_LEN)
    ca, cb = cloud(h, l)
    with np.errstate(invalid="ignore"):
        long_ = ind.crossed_up(r, HI) & (ca > cb)
        short_ = ind.crossed_dn(r, LO) & (ca < cb)
    return dict(long=long_, short=short_, stop_l=None, stop_s=None)


def orders(ctx, tf=5):
    return frame_t.orders(ctx, tf, trigger)


def trades(ctx, **p):
    return core.run_orders(ctx, orders(ctx, **p), one_at_a_time=True, skip_roll=2)
