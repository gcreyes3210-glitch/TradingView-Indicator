#!/usr/bin/env python3
"""C17 - NQ 1-minute 9 / 20 / 50 EMA pullback.

Spec: 1-minute MNQ bars, EMAs on the continuous 24-hour series; signal bars closing 09:45-11:30 and 13:30-15:30.
Trend up : EMA9 > EMA20 > EMA50 and close > EMA50.
Touch    : a bar with low <= EMA20.
Entry    : the close of the first up bar (close > open) closing above EMA9 within 5 bars of the touch (the touch bar
           itself or one of the next five), with the trend intact on every bar from the touch to the entry.
Stop     : the nearer to the entry of (1 tick beyond the lowest low since the touch) and (1 tick beyond EMA50, EMA50
           first put on the tick grid away from the trade).
Target   : 2R (neighbours 1.5R, 3R) from the signal close, rounded to the tick.
Short mirrored. One position at a time, any number a day; roll days and the day after are skipped.

Every bar that touches is a touch. When more than one touch leads to the same entry bar, the earliest of them is
"the touch" (the low since the touch then covers the whole pullback inside the 5-bar reach).
"""
import numpy as np
import core
import ind

ID = "C17"
NAME = "NQ 1-minute 9/20/50 EMA pullback"
VARIANTS = {
    "base": dict(k_r=2.0),
    "nb1": dict(k_r=1.5),
    "nb2": dict(k_r=3.0),
}

WINDOWS = ((9 * 60 + 45, 11 * 60 + 30), (13 * 60 + 30, 15 * 60 + 30))     # the bar's CLOSE time lies in one of these
REACH = 5


def _runlen(x):
    """Number of consecutive True values ending at each position (0 where x is False)."""
    x = np.asarray(x, bool)
    idx = np.arange(len(x))
    last_false = np.maximum.accumulate(np.where(~x, idx, -1))
    return idx - last_false


def _side(side, o, h, l, c, e9, e20, e50, in_win):
    """Signal bars for one direction: returns (bars, extreme since the touch). side = +1 long, -1 short."""
    n = len(c)
    with np.errstate(invalid="ignore"):
        if side > 0:
            trend = (e9 > e20) & (e20 > e50) & (c > e50)
            touch = trend & (l <= e20)
            q = (c > o) & (c > e9)                      # an up bar closing above EMA9
        else:
            trend = (e9 < e20) & (e20 < e50) & (c < e50)
            touch = trend & (h >= e20)
            q = (c < o) & (c < e9)
    tr_run = _runlen(trend)                             # trend intact on the last tr_run bars
    nq_run = _runlen(~q)                                # no entry-type bar on the last nq_run bars
    nq_prev = np.r_[0, nq_run[:-1]]                     # ... on the bars before this one
    px = l if side > 0 else h
    cand = q & trend & in_win
    best = np.full(n, -1)                               # the largest d with a valid touch at bar e - d
    ext = np.full(n, np.nan)
    run_ext = px.copy()                                 # extreme of bars e - d .. e
    for d in range(REACH + 1):
        if d:
            sh = np.r_[np.full(d, np.nan), px[:-d]]
            run_ext = np.fmin(run_ext, sh) if side > 0 else np.fmax(run_ext, sh)
        t_ok = np.r_[np.zeros(d, bool), touch[:n - d]] if d else touch
        ok = cand & t_ok & (tr_run >= d + 1) & ((nq_prev >= d) if d else True)
        best[ok] = d
        ext[ok] = run_ext[ok]
    e = np.flatnonzero(best >= 0)
    return e, ext[e]


def orders(ctx, k_r=2.0):
    o, h, l, c = ctx.O, ctx.H, ctx.L, ctx.C
    e9, e20, e50 = ind.ema(c, 9), ind.ema(c, 20), ind.ema(c, 50)
    close_t = ctx.tod + 1
    in_win = np.zeros(ctx.n, bool)
    for a, z in WINDOWS:
        in_win |= (close_t >= a) & (close_t <= z)
    in_win &= ctx.dayn >= 0
    i_end = ctx.days.i_end.to_numpy()
    T = core.TICK
    out = []
    for side in (1, -1):
        bars, ext = _side(side, o, h, l, c, e9, e20, e50, in_win)
        for i, x in zip(bars.tolist(), ext.tolist()):
            entry = c[i]
            if side > 0:
                s_swing = x - T
                s_ema = core.tick_round(e50[i], "down") - T
                stop = max(s_swing, s_ema)              # the nearer of the two to the entry
            else:
                s_swing = x + T
                s_ema = core.tick_round(e50[i], "up") + T
                stop = min(s_swing, s_ema)
            target = core.tick_round(entry + side * k_r * abs(entry - stop))
            out.append(dict(i=int(i), side=side, etype="close", stop=float(stop), target=float(target),
                            exit_i=int(i_end[ctx.dayn[i]]),
                            tag=("L" if side > 0 else "S") + (" ema" if stop == s_ema and stop != s_swing else " swing")))
    return out


def trades(ctx, **p):
    return core.run_orders(ctx, orders(ctx, **p), one_at_a_time=True, skip_roll=2)
