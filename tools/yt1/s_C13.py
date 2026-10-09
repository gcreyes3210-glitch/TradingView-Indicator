#!/usr/bin/env python3
"""C13 - Connors RSI + 200 MA. YT1_SPEC.md, family C.

Spec: CRSI (3, 2, 100). Long: close > SMA200 and CRSI crosses back above 10; short: close < SMA200 and CRSI crosses
below 90. Swing stop, 1.5R. Neighbours: the same rule on 3-minute and 15-minute bars.

Family C frame: N-minute bars (N = `bar`, 5 in the base), indicators on the continuous 24-hour series, signal bars
closing 09:35 -> 15:00, entry at the signal bar's close, one position at a time, any number a day, skip_roll=2.
Swing stop = 1 tick beyond the lowest low (highest high) of the last 10 bars including the signal bar.
Target = entry close +/- 1.5 x |entry close - stop|, rounded to the tick.

Connors RSI is not in ind.py; connors_rsi() below follows TradingView's built-in:
    crsi = avg( ta.rsi(close, 3), ta.rsi(updown(close), 2), ta.percentrank(ta.roc(close, 1), 100) )
    updown: the length of the current run of higher closes (+1, +2, ...) or lower closes (-1, -2, ...), 0 on an
            unchanged close;
    ta.percentrank(x, 100): the percentage of the PREVIOUS 100 values of x that are <= the current one.
"""
import numpy as np
import core
import ind

ID = "C13"
NAME = "Connors RSI (3, 2, 100) out of the extreme + 200 SMA"
VARIANTS = {
    "base": dict(bar=5),
    "nb1": dict(bar=3),
    "nb2": dict(bar=15),
}

SWING = 10
K_R = 1.5
T_FIRST, T_LAST = 9 * 60 + 35, 15 * 60          # signal bars close 09:35 .. 15:00
LO, HI = 10.0, 90.0


def streak(c):
    """TradingView's updown(): +n after n consecutive higher closes, -n after n lower closes, 0 on an equal close."""
    c = np.asarray(c, float)
    s = np.zeros(len(c))
    for k in range(1, len(c)):
        if c[k] > c[k - 1]:
            s[k] = s[k - 1] + 1 if s[k - 1] > 0 else 1.0
        elif c[k] < c[k - 1]:
            s[k] = s[k - 1] - 1 if s[k - 1] < 0 else -1.0
    return s


def percent_rank(x, n):
    """ta.percentrank(x, n): share (in %) of the previous n values that are <= the current value. NaN until n
    previous values exist."""
    x = np.asarray(x, float)
    out = np.full(len(x), np.nan)
    if len(x) <= n:
        return out
    w = np.lib.stride_tricks.sliding_window_view(x, n + 1)    # row r = x[r .. r+n], the current value is the last
    cnt = np.zeros(len(w))
    step = 50000
    for s in range(0, len(w), step):                          # in blocks, to keep memory small
        blk = w[s:s + step]
        cnt[s:s + step] = (blk[:, :n] <= blk[:, n:]).sum(axis=1)
    val = 100.0 * cnt / n
    val[np.isnan(w).any(axis=1)] = np.nan
    out[n:] = val
    return out


def connors_rsi(c, n_rsi=3, n_streak=2, n_rank=100):
    """Returns (crsi, rsi of close, rsi of streak, percent rank of the 1-bar rate of change)."""
    c = np.asarray(c, float)
    r1 = ind.rsi(c, n_rsi)
    r2 = ind.rsi(streak(c), n_streak)
    roc = np.full(len(c), np.nan)
    roc[1:] = 100.0 * (c[1:] - c[:-1]) / c[:-1]
    r3 = percent_rank(roc, n_rank)
    return (r1 + r2 + r3) / 3.0, r1, r2, r3


def orders(ctx, bar=5):
    b = ctx.bars(bar)
    H, L, C = b.high.to_numpy(), b.low.to_numpy(), b.close.to_numpy()
    tod = (b.index.hour * 60 + b.index.minute).to_numpy()
    i_last = b.i_last.to_numpy()
    dn = ctx.dayn[i_last]
    i_end = ctx.days.i_end.to_numpy()

    sma200 = ind.sma(C, 200)
    crsi = connors_rsi(C)[0]
    long_sig = ind.crossed_up(crsi, LO) & (C > sma200)        # crsi[k] > 10 and crsi[k-1] <= 10
    short_sig = ind.crossed_dn(crsi, HI) & (C < sma200)       # crsi[k] < 90 and crsi[k-1] >= 90
    swing_lo, swing_hi = ind.rolling_min(L, SWING), ind.rolling_max(H, SWING)

    in_win = (dn >= 0) & (tod + bar >= T_FIRST) & (tod + bar <= T_LAST)
    out = []
    for k in np.flatnonzero(in_win & (long_sig | short_sig)):
        i, e = int(i_last[k]), int(i_end[dn[k]])
        if i >= e or np.isnan(swing_lo[k]):
            continue
        if long_sig[k]:
            stop = swing_lo[k] - core.TICK
            out.append(dict(i=i, side=1, etype="close", stop=float(stop),
                            target=core.tick_round(C[k] + K_R * (C[k] - stop)), exit_i=e, tag="L"))
        else:
            stop = swing_hi[k] + core.TICK
            out.append(dict(i=i, side=-1, etype="close", stop=float(stop),
                            target=core.tick_round(C[k] - K_R * (stop - C[k])), exit_i=e, tag="S"))
    return out


def trades(ctx, **p):
    return core.run_orders(ctx, orders(ctx, **p), skip_roll=2)
