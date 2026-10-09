#!/usr/bin/env python3
"""T04 - TRADING RUSH single trigger: Chande Momentum Oscillator(9) crosses above -50 (short: crosses below +50).

Trigger only; the frame (frame_t.py) does the rest.
CMO (TradingView built-in, length 9, source close): d = close - previous close; su = sum over the last 9 bars of the
changes that are >= 0, sd = sum of the sizes of the changes that are < 0; CMO = 100 x (su - sd) / (su + sd).
Nine unchanged closes in a row give 0 / 0 = no value (as on TradingView), and no cross can use that bar.
"""
import numpy as np
import core
import ind
import frame_t

ID = "T04"
NAME = "TRADING RUSH CMO(9) crosses -50 / +50 + EMA200"
VARIANTS = {"base": dict(tf=5), "nb1": dict(tf=3), "nb2": dict(tf=15)}


def rsum(x, n):
    """Sum of the last n values including the current one; x may start with NaNs."""
    x = np.asarray(x, float)
    out = np.full(len(x), np.nan)
    ok = np.flatnonzero(np.isfinite(x))
    if len(ok) and len(x) - ok[0] >= n:
        s = ok[0]
        cs = np.cumsum(np.insert(x[s:], 0, 0.0))
        out[s + n - 1:] = cs[n:] - cs[:-n]
    return out


def cmo(c, n=9):
    d = np.diff(np.asarray(c, float), prepend=np.nan)
    up, dn = np.where(d >= 0, d, 0.0), np.where(d < 0, -d, 0.0)
    up[0] = dn[0] = np.nan                          # the first bar has no change
    su, sd = rsum(up, n), rsum(dn, n)
    with np.errstate(divide="ignore", invalid="ignore"):
        out = 100.0 * (su - sd) / (su + sd)
    out[(su + sd) == 0] = np.nan
    return out


def trigger(o, h, l, c, v):
    x = cmo(c, 9)
    return dict(long=ind.crossed_up(x, -50.0), short=ind.crossed_dn(x, 50.0), stop_l=None, stop_s=None)


def orders(ctx, tf=5):
    return frame_t.orders(ctx, tf, trigger)


def trades(ctx, **p):
    return core.run_orders(ctx, orders(ctx, **p), one_at_a_time=True, skip_roll=2)
