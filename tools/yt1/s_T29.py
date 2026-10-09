#!/usr/bin/env python3
"""T29 - MACD(12, 26, 9) crosses above its signal with Stochastic %K below 20 on at least one of the previous 10 bars
and the bar's low above EMA200 (short: MACD crosses below its signal with %K above 80 on at least one of the previous
10 bars and the bar's high below EMA200). YT2 trigger; the frame is tools/yt1/frame_t.py.

MACD = ind.macd. %K = TradingView's Stochastic(14, 3, 3) %K line = SMA3 of the raw 14-bar stochastic (ind.stoch()[0]).
"Previous 10 bars" = bars k-10 .. k-1; the signal bar itself is not counted. EMA200 = ind.ema(close, 200), the same
series the frame uses for its side filter; the low / high test is on the signal bar.
"""
import numpy as np
import core
import ind
import frame_t

ID = "T29"
NAME = "TRADING RUSH MACD crosses its signal after Stochastic < 20 / > 80, bar clear of EMA200"
VARIANTS = {"base": dict(tf=5), "nb1": dict(tf=3), "nb2": dict(tf=15)}

FAST, SLOW, SIG = 12, 26, 9
K_LEN, K_SMOOTH, D_LEN, K_LO, K_HI = 14, 3, 3, 20.0, 80.0
RECENT, EMA_LEN = 10, 200


def any_prev(cond, n):
    """True at bar k when cond was True on at least one of the bars k-n .. k-1 (bar k itself is not counted)."""
    cs = np.cumsum(np.r_[0, np.asarray(cond, bool).astype(np.int64)])       # cs[j] = number of True in cond[:j]
    k = np.arange(len(cond))
    return (cs[k] - cs[np.maximum(k - n, 0)]) > 0


def trigger(o, h, l, c, v):
    m, s, _ = ind.macd(c, FAST, SLOW, SIG)
    pk = ind.stoch(h, l, c, K_LEN, K_SMOOTH, D_LEN)[0]
    e200 = ind.ema(c, EMA_LEN)
    with np.errstate(invalid="ignore"):
        long_ = ind.crossed_up(m, s) & any_prev(pk < K_LO, RECENT) & (l > e200)
        short_ = ind.crossed_dn(m, s) & any_prev(pk > K_HI, RECENT) & (h < e200)
    return dict(long=long_, short=short_, stop_l=None, stop_s=None)


def orders(ctx, tf=5):
    return frame_t.orders(ctx, tf, trigger)


def trades(ctx, **p):
    return core.run_orders(ctx, orders(ctx, **p), one_at_a_time=True, skip_roll=2)
