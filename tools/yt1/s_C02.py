#!/usr/bin/env python3
"""C02 - 8-55 EMA pullback on NQ (long only, as the script ships). YT1_SPEC.md, family C.

Spec: Bullish = EMA55 >= EMA165 and EMA8 > EMA55. Long when bullish, a low was below EMA55 within the last 6 bars and
the close is above EMA8; signal bars opening 10:00 ... 15:50. Exit: trailing stop at the highest (bar high x 0.9925)
since entry, or a bar that turns bearish (EMA55 <= EMA165 and EMA8 < EMA55), or the flat bar. No initial stop.
Neighbours: the same rule on 3-minute and 15-minute bars.

Family C frame: N-minute bars (N = `bar`, 5 in the base), EMAs on the continuous 24-hour series, entry at the signal
bar's close, one position at a time, any number a day, skip_roll=2.

No stop, so the R unit is r_pts = 0.1 x the day's daily ATR(14) (days.atr: through the previous trading day).

What the harness is given for the exits:
  exit_sig  one bool array on the 1-minute index, True at the 1-minute bar that closes an N-minute bar which is
            bearish (EMA55 <= EMA165 and EMA8 < EMA55, values of that N-minute bar). The same array for every order.
  trail     one array PER ORDER, built from that order's own entry onward. The order is entered at the close of
            1-minute bar i (the last minute of signal bar k). For every later N-minute bar m of the same day, at the
            1-minute bar that closes it, the level is 0.9925 x the highest high of N-minute bars k+1 .. m, rounded to
            the tick; it is carried forward minute by minute until the next N-minute bar closes. simulate applies
            trail[j] from 1-minute bar j+1. The signal bar's own high is not in it (it traded before the entry).
            A full-length array per order would need tens of gigabytes, so the array is held as _Trail: the day's
            slice plus its offset, NaN everywhere else. It reads like an array (trail[j], np.asarray(trail)).
"""
import numpy as np
import core
import ind

ID = "C02"
NAME = "8-55 EMA pullback, long only, 0.75 % trailing stop"
VARIANTS = {
    "base": dict(bar=5),
    "nb1": dict(bar=3),
    "nb2": dict(bar=15),
}

T_OPEN_FIRST, T_OPEN_LAST = 10 * 60, 15 * 60 + 50     # signal bars OPEN 10:00 .. 15:50
TOUCH = 6                                             # a low below EMA55 within the last 6 bars (signal bar included)
TRAIL = 0.9925                                        # bar high x (1 - 0.75 %)
R_ATR = 0.1                                           # R unit = 0.1 x daily ATR(14)


class _Trail:
    """A length-n float array that is NaN except on [start, start + len(vals)); stored as that slice only."""
    dtype = np.dtype(float)

    def __init__(self, n, start, vals):
        self.n, self.start, self.vals = int(n), int(start), np.asarray(vals, float)
        self.shape = (self.n,)

    def __len__(self):
        return self.n

    def __getitem__(self, j):
        if isinstance(j, slice):
            return np.asarray(self)[j]
        j = int(j)
        if j < 0:
            j += self.n
        r = j - self.start
        return float(self.vals[r]) if 0 <= r < len(self.vals) else float("nan")

    def __array__(self, dtype=None, copy=None):
        full = np.full(self.n, np.nan)
        full[self.start:self.start + len(self.vals)] = self.vals
        return full if dtype is None else full.astype(dtype)


def _trail(ctx, HN, i_last, k, i, e):
    """Trail for the order signalled on N-minute bar k (entered at the close of 1-minute bar i), flat bar e.
    Covers 1-minute bars i+1 .. e; the value at 1-minute bar j uses N-minute bars k+1 .. (last one closed by j)."""
    m1 = int(np.searchsorted(i_last, e, "right"))             # N-minute bars k+1 .. m1-1 close at or before e
    vals = np.full(e - i, np.nan)
    if m1 > k + 1:
        lv = np.maximum.accumulate(HN[k + 1:m1]) * TRAIL
        lv = np.array([core.tick_round(x) for x in lv])
        at = i_last[k + 1:m1] - (i + 1)                       # offset of each closing minute inside the slice
        for a, b, v in zip(at, np.r_[at[1:], len(vals)], lv):
            vals[a:b] = v                                     # carried forward until the next N-minute bar closes
    return _Trail(ctx.n, i + 1, vals)


def orders(ctx, bar=5):
    b = ctx.bars(bar)
    H, L, C = b.high.to_numpy(), b.low.to_numpy(), b.close.to_numpy()
    tod = (b.index.hour * 60 + b.index.minute).to_numpy()
    i_last = b.i_last.to_numpy()
    dn = ctx.dayn[i_last]
    i_end = ctx.days.i_end.to_numpy()
    atr = ctx.days.atr.to_numpy()

    e8, e55, e165 = ind.ema(C, 8), ind.ema(C, 55), ind.ema(C, 165)
    bullish = (e55 >= e165) & (e8 > e55)
    bearish = (e55 <= e165) & (e8 < e55)
    below = (L < e55).astype(float)                           # NaN EMA -> False
    touched = ind.rolling_max(below, TOUCH) > 0               # some bar among k-5 .. k had its low below its EMA55
    sig = bullish & touched & (C > e8)

    exit_sig = np.zeros(ctx.n, bool)
    exit_sig[i_last[bearish]] = True                          # known at the close of that N-minute bar

    in_win = (dn >= 0) & (tod >= T_OPEN_FIRST) & (tod <= T_OPEN_LAST)
    out = []
    for k in np.flatnonzero(in_win & sig):
        d = dn[k]
        i, e = int(i_last[k]), int(i_end[d])
        if i >= e or not atr[d] > 0:                          # at / after the flat bar, or no daily ATR
            continue
        out.append(dict(i=i, side=1, etype="close", exit_i=e, r_pts=float(R_ATR * atr[d]),
                        trail=_trail(ctx, H, i_last, k, i, e), exit_sig=exit_sig, tag="L"))
    return out


def trades(ctx, **p):
    return core.run_orders(ctx, orders(ctx, **p), skip_roll=2)
