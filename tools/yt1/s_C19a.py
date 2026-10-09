#!/usr/bin/env python3
"""C19a - TRADING RUSH single trigger: Ichimoku conversion / base cross above the cloud, with the 200 EMA.

Spec (Family C common frame + C19): N-minute MNQ bars (5; neighbours 3 and 15), indicators on the continuous 24-hour
series; signal bars closing 09:35 -> 15:00; entry at the signal bar's close; one position at a time, any number a day;
long and short mirrored; swing stop = 1 tick beyond the lowest low (highest high) of the last 10 bars including the
signal bar; target 1.5R from the signal close, rounded to the tick; skip roll days and the day after (skip_roll=2).
Long:  close > EMA200, conversion (9) crosses above base (26), close above the cloud.
Short: close < EMA200, conversion crosses below base, close below the cloud.
Cloud at bar k = span A and span B computed at bar k - 26 (span A = (conversion + base) / 2, span B = midpoint of the
52-bar high / low).

This module also holds the frame shared by C19b .. C19e: frame_orders(ctx, tf, trigger, k_r).
"""
import numpy as np
import core
import ind

ID = "C19a"
NAME = "TRADING RUSH Ichimoku cross above the cloud + EMA200"
VARIANTS = {
    "base": dict(tf=5),
    "nb1": dict(tf=3),
    "nb2": dict(tf=15),
}

WIN_LO, WIN_HI = 9 * 60 + 35, 15 * 60          # signal bars CLOSE in [09:35, 15:00]
SWING, EMA_LEN = 10, 200


def frame_orders(ctx, tf, trigger, k_r=1.5, tag=""):
    """The C19 frame. trigger(o, h, l, c) -> (long_sig, short_sig): bool arrays over the tf-minute bar series, each
    value built from bars up to and including that bar. Adds the EMA200 side filter, the signal window, the swing
    stop and the k_r target, and returns the order dicts."""
    b = ctx.bars(tf)
    o, h, l, c = (b[k].to_numpy(float) for k in ("open", "high", "low", "close"))
    i_last = b.i_last.to_numpy()
    tod = (b.index.hour * 60 + b.index.minute).to_numpy()
    close_t = tod + tf                              # the clock time at which the bar closes
    in_win = (close_t >= WIN_LO) & (close_t <= WIN_HI)
    e200 = ind.ema(c, EMA_LEN)
    lo10, hi10 = ind.rolling_min(l, SWING), ind.rolling_max(h, SWING)
    ls, ss = trigger(o, h, l, c)
    with np.errstate(invalid="ignore"):
        long_ok = ls & in_win & (c > e200) & np.isfinite(lo10)
        short_ok = ss & in_win & (c < e200) & np.isfinite(hi10)
    i_end = ctx.days.i_end.to_numpy()
    T = core.TICK
    out = []
    for k in np.flatnonzero(long_ok | short_ok):
        i = int(i_last[k])
        dn = ctx.dayn[i]
        if dn < 0:
            continue                                # not a cash day
        side = 1 if long_ok[k] else -1
        entry = c[k]
        stop = lo10[k] - T if side > 0 else hi10[k] + T
        target = core.tick_round(entry + side * k_r * abs(entry - stop))
        out.append(dict(i=i, side=side, etype="close", stop=float(stop), target=float(target),
                        exit_i=int(i_end[dn]), tag=(tag + ("L" if side > 0 else "S"))))
    return out


def ichimoku(h, l, conv_len=9, base_len=26, span_b_len=52, disp=26):
    """Returns (conversion, base, cloud_a, cloud_b); cloud_x[k] = the span computed at bar k - disp."""
    conv = (ind.rolling_max(h, conv_len) + ind.rolling_min(l, conv_len)) / 2
    base = (ind.rolling_max(h, base_len) + ind.rolling_min(l, base_len)) / 2
    span_a = (conv + base) / 2
    span_b = (ind.rolling_max(h, span_b_len) + ind.rolling_min(l, span_b_len)) / 2
    pad = np.full(disp, np.nan)
    return conv, base, np.r_[pad, span_a[:-disp]], np.r_[pad, span_b[:-disp]]


def trigger(o, h, l, c):
    conv, base, ca, cb = ichimoku(h, l)
    top, bot = np.maximum(ca, cb), np.minimum(ca, cb)      # NaN while either span is warming up
    with np.errstate(invalid="ignore"):
        ls = ind.crossed_up(conv, base) & (c > top)
        ss = ind.crossed_dn(conv, base) & (c < bot)
    return ls, ss


def orders(ctx, tf=5):
    return frame_orders(ctx, tf, trigger)


def trades(ctx, **p):
    return core.run_orders(ctx, orders(ctx, **p), one_at_a_time=True, skip_roll=2)
