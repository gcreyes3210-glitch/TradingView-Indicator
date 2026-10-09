#!/usr/bin/env python3
"""T26 - Know Sure Thing crosses above its signal with both below zero (short: crosses below with both above zero).
YT2 trigger; the frame is tools/yt1/frame_t.py.

ROC(n)[k] = 100 x (close[k] - close[k-n]) / close[k-n].
KST = 1 x SMA10(ROC10) + 2 x SMA10(ROC15) + 3 x SMA10(ROC20) + 4 x SMA15(ROC30);  signal = SMA9(KST).
"Both below zero" is read on the cross bar: KST < 0 and signal < 0 there. First KST value at bar 44, signal at bar 52.
"""
import numpy as np
import core
import ind
import frame_t

ID = "T26"
NAME = "TRADING RUSH Know Sure Thing crosses its signal on the far side of zero + EMA200"
VARIANTS = {"base": dict(tf=5), "nb1": dict(tf=3), "nb2": dict(tf=15)}

ROCS, SMAS, WEIGHTS, SIG = (10, 15, 20, 30), (10, 10, 10, 15), (1, 2, 3, 4), 9


def roc(c, n):
    out = np.full(len(c), np.nan)
    out[n:] = 100.0 * (c[n:] - c[:-n]) / c[:-n]
    return out


def sma_nan(x, n):
    """SMA of a series that starts with NaNs: the first value is n bars after the series starts."""
    out = np.full(len(x), np.nan)
    ok = np.flatnonzero(~np.isnan(x))
    if len(ok) >= n:
        out[ok[0]:] = ind.sma(x[ok[0]:], n)
    return out


def kst(c):
    c = np.asarray(c, float)
    k = np.zeros(len(c))
    for r, s, w in zip(ROCS, SMAS, WEIGHTS):
        k = k + w * sma_nan(roc(c, r), s)
    return k, sma_nan(k, SIG)


def trigger(o, h, l, c, v):
    k, s = kst(c)
    with np.errstate(invalid="ignore"):
        long_ = ind.crossed_up(k, s) & (k < 0) & (s < 0)
        short_ = ind.crossed_dn(k, s) & (k > 0) & (s > 0)
    return dict(long=long_, short=short_, stop_l=None, stop_s=None)


def orders(ctx, tf=5):
    return frame_t.orders(ctx, tf, trigger)


def trades(ctx, **p):
    return core.run_orders(ctx, orders(ctx, **p), one_at_a_time=True, skip_roll=2)
