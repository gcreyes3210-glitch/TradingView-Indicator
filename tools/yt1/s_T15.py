#!/usr/bin/env python3
"""T15 - TRADING RUSH single trigger: Schaff Trend Cycle (10, 23, 50) crosses above 25 (short: crosses below 75).

Trigger only; the frame (frame_t.py) does the rest.
STC, Schaff's algorithm as the standard TradingView scripts code it (length 10, fast 23, slow 50, factor 0.5):
    m   = EMA23(close) - EMA50(close)
    f1  = 100 x (m - lowest(m, 10)) / (highest(m, 10) - lowest(m, 10));  the previous f1 when that range is 0
    pf  = previous pf + 0.5 x (f1 - previous pf)                          (first pf = first f1)
    f2  = 100 x (pf - lowest(pf, 10)) / (highest(pf, 10) - lowest(pf, 10));  the previous f2 when that range is 0
    STC = previous STC + 0.5 x (f2 - previous STC)                        (first STC = first f2)
highest / lowest include the current bar. A "previous f1 / f2" that does not exist yet is 0.
"""
import numpy as np
import core
import ind
import frame_t

ID = "T15"
NAME = "TRADING RUSH Schaff Trend Cycle (10, 23, 50) crosses 25 / 75 + EMA200"
VARIANTS = {"base": dict(tf=5), "nb1": dict(tf=3), "nb2": dict(tf=15)}


def stoch_hold(x, n):
    """100 x (x - lowest) / (highest - lowest) over the last n bars; holds the previous value when the range is 0."""
    lo = ind.rolling_min(x, n)
    rng = ind.rolling_max(x, n) - lo
    valid = np.isfinite(rng)
    with np.errstate(invalid="ignore", divide="ignore"):
        good = valid & (rng > 0)
        raw = np.where(good, 100.0 * (x - lo) / rng, np.nan)
    last = np.maximum.accumulate(np.where(good, np.arange(len(x)), -1))
    held = np.where(last >= 0, raw[np.maximum(last, 0)], 0.0)
    return np.where(valid, held, np.nan)


def smooth(x, a):
    """y = previous y + a x (x - previous y), started at the first value of x that exists."""
    out = np.full(len(x), np.nan)
    ok = np.flatnonzero(np.isfinite(x))
    if len(ok):
        s = int(ok[0])
        xs = x[s:].tolist()
        y = xs[0]
        ys = [y]
        for q in xs[1:]:
            y = y + a * (q - y)
            ys.append(y)
        out[s:] = ys
    return out


def stc(c, length=10, fast=23, slow=50, factor=0.5):
    m = ind.ema(c, fast) - ind.ema(c, slow)
    pf = smooth(stoch_hold(m, length), factor)
    return smooth(stoch_hold(pf, length), factor)


def trigger(o, h, l, c, v):
    s = stc(c)
    return dict(long=ind.crossed_up(s, 25.0), short=ind.crossed_dn(s, 75.0), stop_l=None, stop_s=None)


def orders(ctx, tf=5):
    return frame_t.orders(ctx, tf, trigger)


def trades(ctx, **p):
    return core.run_orders(ctx, orders(ctx, **p), one_at_a_time=True, skip_roll=2)
