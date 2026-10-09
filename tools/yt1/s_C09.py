#!/usr/bin/env python3
"""C09 - Stochastic + RSI + MACD. YT1_SPEC.md, family C.

Spec: Stochastic (14, 3, 3) with both lines under 20 arms a long; either line over 80 disarms it. While armed: enter
at the first bar with RSI(14) > 50 and MACD > signal where one of those two became true on that bar. Swing stop, 1.5R.
Short mirrored: both lines over 80 arm a short, either line under 20 disarms it; while armed, the first bar with
RSI < 50 and MACD < signal where one of those two became true on that bar.
Neighbours: the same rule on 3-minute and 15-minute bars.

Family C frame: N-minute bars (N = `bar`, 5 in the base), indicators on the continuous 24-hour series, signal bars
closing 09:35 -> 15:00, entry at the signal bar's close, one position at a time, any number a day, skip_roll=2.
Swing stop = 1 tick beyond the lowest low (highest high) of the last 10 bars including the signal bar.
Target = entry close +/- 1.5 x |entry close - stop|, rounded to the tick.

The arm / disarm state machine (state() below) runs bar by bar on the continuous series, each bar in this order:
  1. the bar's own Stochastic values arm or disarm (so a bar can arm and trigger at its own close; a bar that
     disarms cannot trigger);
  2. if armed and the bar is a trigger bar, it is THE signal of that arming and the arming is used up, wherever the
     bar falls (inside the signal window or not, in a position or not). A later trigger needs a new arming.
"""
import numpy as np
import core
import ind

ID = "C09"
NAME = "Stochastic (14,3,3) arm + RSI(14) > 50 + MACD > signal"
VARIANTS = {
    "base": dict(bar=5),
    "nb1": dict(bar=3),
    "nb2": dict(bar=15),
}

SWING = 10
K_R = 1.5
T_FIRST, T_LAST = 9 * 60 + 35, 15 * 60          # signal bars close 09:35 .. 15:00
OS, OB = 20.0, 80.0


def state(K, D, trig_long, trig_short):
    """Returns (long signal, short signal, armed-long after the bar, armed-short after the bar) as arrays.
    Value at bar k uses bars <= k only."""
    n = len(K)
    sig_l, sig_s = np.zeros(n, bool), np.zeros(n, bool)
    arm_l, arm_s = np.zeros(n, bool), np.zeros(n, bool)
    al = as_ = False
    for k in range(n):
        kk, dd = K[k], D[k]                      # NaN while warming up: every comparison below is False
        if kk > OB or dd > OB:
            al = False                           # either line over 80 disarms a long
        if kk < OS and dd < OS:
            al = True                            # both lines under 20 arm a long
        if kk < OS or dd < OS:
            as_ = False                          # mirror
        if kk > OB and dd > OB:
            as_ = True
        if al and trig_long[k]:
            sig_l[k] = True
            al = False                           # the first trigger bar uses the arming up
        if as_ and trig_short[k]:
            sig_s[k] = True
            as_ = False
        arm_l[k], arm_s[k] = al, as_
    return sig_l, sig_s, arm_l, arm_s


def indicators(H, L, C):
    K, D = ind.stoch(H, L, C, 14, 3, 3)
    rsi = ind.rsi(C, 14)
    macd, sigl, _ = ind.macd(C, 12, 26, 9)
    up = (rsi > 50) & (macd > sigl)              # both long conditions true
    dn = (rsi < 50) & (macd < sigl)
    trig_long, trig_short = np.zeros(len(C), bool), np.zeros(len(C), bool)
    trig_long[1:] = up[1:] & ~up[:-1]            # both true now, at least one of the two was not true one bar ago
    trig_short[1:] = dn[1:] & ~dn[:-1]
    return K, D, rsi, macd, sigl, trig_long, trig_short


def orders(ctx, bar=5):
    b = ctx.bars(bar)
    H, L, C = b.high.to_numpy(), b.low.to_numpy(), b.close.to_numpy()
    tod = (b.index.hour * 60 + b.index.minute).to_numpy()
    i_last = b.i_last.to_numpy()
    dn = ctx.dayn[i_last]
    i_end = ctx.days.i_end.to_numpy()

    K, D, _, _, _, trig_long, trig_short = indicators(H, L, C)
    sig_l, sig_s, _, _ = state(K, D, trig_long, trig_short)
    swing_lo, swing_hi = ind.rolling_min(L, SWING), ind.rolling_max(H, SWING)

    in_win = (dn >= 0) & (tod + bar >= T_FIRST) & (tod + bar <= T_LAST)
    out = []
    for k in np.flatnonzero(in_win & (sig_l | sig_s)):
        i, e = int(i_last[k]), int(i_end[dn[k]])
        if i >= e or np.isnan(swing_lo[k]):
            continue
        if sig_l[k]:
            stop = swing_lo[k] - core.TICK
            out.append(dict(i=i, side=1, etype="close", stop=float(stop),
                            target=core.tick_round(C[k] + K_R * (C[k] - stop)), exit_i=e, tag="L"))
        if sig_s[k]:
            stop = swing_hi[k] + core.TICK
            out.append(dict(i=i, side=-1, etype="close", stop=float(stop),
                            target=core.tick_round(C[k] - K_R * (stop - C[k])), exit_i=e, tag="S"))
    return out


def trades(ctx, **p):
    return core.run_orders(ctx, orders(ctx, **p), skip_roll=2)
