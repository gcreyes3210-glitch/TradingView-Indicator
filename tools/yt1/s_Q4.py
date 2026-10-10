#!/usr/bin/env python3
"""Q4 - EMA 9 / 21 cross with RSI and a volume surge, held three bars (M13, MetroTrade).

Spec text (YT11_SPEC.md, Part 4, Q4):
  At a close in 09:30-11:29 or 14:30-15:54 (the source's hours): EMA(9) crosses above EMA(21), RSI(14) above 50 and
  above its value one bar earlier, volume above 1.5 x the mean of the previous 20 bars: buy at the close, exit at
  the close three bars later. No stop. Short mirrors. One position at a time.
  Neighbours: one bar; five bars.

EMA and RSI from ind.py on the continuous 24-hour 1-minute series.

Readings fixed before the first run (see notes/Q4.md):
  * "a close in 09:30-11:29 or 14:30-15:54" = the close of a 1-minute bar stamped in one of those two ranges (the
    bars inside the source's 9:30-11:30 and 14:30-16:00; 15:54 + five bars = the flat bar), on a traded day, before
    the flat bar.
  * "crosses above" = ind.crossed_up (EMA9 > EMA21 at this bar, EMA9 <= EMA21 at the bar before).
  * "the previous 20 bars" = the 20 bars before the signal bar in the 24-hour series, the signal bar not included.
  * short mirror: EMA(9) crosses below EMA(21), RSI below 50 and below its value one bar earlier, the same volume test.
  * "three bars later" = the third bar after the signal bar in the series (exit_i = i + 3), or the flat bar if that
    comes first. R unit = 0.1 x that day's daily ATR(14).
  * one position at a time is run_orders' rule (a signal on a bar at or before the previous exit bar is skipped).
"""
import numpy as np
import core
import ind

ID = "Q4"
NAME = "EMA 9/21 cross + RSI(14) side of 50 and rising + volume surge, held N bars (M13)"
VARIANTS = {
    "base": dict(hold=3),
    "nb1": dict(hold=1),
    "nb2": dict(hold=5),
}
WINDOWS = ((9 * 60 + 30, 11 * 60 + 29), (14 * 60 + 30, 15 * 60 + 54))     # stamps of the signal bars, both included
VOL_N, VOL_K, RSI_N = 20, 1.5, 14


def _daymap(ctx):
    """Per 1-minute bar: inside a cash session before its flat bar; that day's flat bar; 0.1 x that day's ATR."""
    m = getattr(ctx, "_yt11_daymap", None)
    if m is None:
        live = np.zeros(ctx.n, bool)
        i_end = np.full(ctx.n, -1, dtype=np.int64)
        r_pts = np.full(ctx.n, np.nan)
        D = ctx.days
        for a, z, atr in zip(D.i_open.to_numpy(), D.i_end.to_numpy(), D.atr.to_numpy(float)):
            live[a:z] = True
            i_end[a:z + 1] = z
            r_pts[a:z + 1] = 0.1 * atr
        m = (live, i_end, r_pts)
        ctx._yt11_daymap = m
    return m


def _signals(ctx):
    s = getattr(ctx, "_yt11_q4", None)
    if s is None:
        C, V = ctx.C, ctx.V
        e9, e21 = ind.ema(C, 9), ind.ema(C, 21)
        rsi = ind.rsi(C, RSI_N)
        rsi_prev = np.r_[np.nan, rsi[:-1]]
        vmean = np.r_[np.nan, ind.sma(V, VOL_N)[:-1]]                     # mean of the 20 bars before this one
        live, _, _ = _daymap(ctx)
        win = np.zeros(ctx.n, bool)
        for a, z in WINDOWS:
            win |= (ctx.tod >= a) & (ctx.tod <= z)
        win &= live
        with np.errstate(invalid="ignore"):
            surge = V > VOL_K * vmean
            long_ = ind.crossed_up(e9, e21) & (rsi > 50) & (rsi > rsi_prev) & surge & win
            short = ind.crossed_dn(e9, e21) & (rsi < 50) & (rsi < rsi_prev) & surge & win
        s = (np.flatnonzero(long_), np.flatnonzero(short))
        ctx._yt11_q4 = s
    return s


def orders(ctx, hold=3):
    sig_l, sig_s = _signals(ctx)
    _, i_end, r_pts = _daymap(ctx)
    out = []
    for side, sig in ((1, sig_l), (-1, sig_s)):
        for i in sig.tolist():
            r = r_pts[i]
            out.append(dict(i=i, side=side, etype="close", exit_i=int(min(i + hold, i_end[i])),
                            r_pts=float(r) if r == r else None, tag="L" if side > 0 else "S"))
    return out


def trades(ctx, **p):
    return core.run_orders(ctx, orders(ctx, **p), one_at_a_time=True)
