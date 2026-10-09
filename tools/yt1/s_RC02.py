#!/usr/bin/env python3
"""RC02 - 8-55 EMA pullback on NQ, long only (TradersPost). Second, independent coding of C02 from YT1_SPEC.md.

Spec text (Family C): N-minute MNQ bars, indicators on the continuous 24-hour series, entry at the signal bar's close,
one position at a time, any number a day. Bullish = EMA55 >= EMA165 and EMA8 > EMA55. Long when bullish, a low was
below EMA55 within the last 6 bars and the close is above EMA8; signal bars opening 10:00 ... 15:50. Exit: trailing
stop at the highest (bar high x 0.9925) since entry, or a bar that turns bearish (EMA55 <= EMA165 and EMA8 < EMA55),
or the flat bar. No initial stop (R unit = 0.1 x daily ATR). Neighbours: 3-minute and 15-minute bars.

Readings made here are listed in notes/RC02.md.
"""
import numpy as np
import pandas as pd
import core
import ind

ID = "RC02"
NAME = "8-55 EMA pullback, long only (second coder)"
VARIANTS = {
    "base": dict(tf=5),
    "nb1": dict(tf=3),
    "nb2": dict(tf=15),
}

TRAIL = 0.9925          # stop = bar high x 0.9925
LOOKBACK = 6            # "within the last 6 bars", the signal bar included
T_FIRST, T_LAST = core.hhmm("10:00"), core.hhmm("15:50")     # signal bars OPENING in this window, both ends included


class _DayTrail:
    """A float array of length n that is NaN everywhere except on [start, start + len(seg)), held compactly.
    simulate() only reads trail[k]; the look-ahead test reads np.asarray(trail). One full-length array per candidate
    order would not fit in memory, and each order needs its own (the running maximum starts at its own entry)."""

    def __init__(self, n, start, seg):
        self.n, self.start, self.seg = int(n), int(start), seg

    def __len__(self):
        return self.n

    def __getitem__(self, k):
        if isinstance(k, (int, np.integer)):
            j = int(k) - self.start
            return float(self.seg[j]) if 0 <= j < len(self.seg) else float("nan")
        return self.__array__()[k]

    def __array__(self, dtype=None, copy=None):
        out = np.full(self.n, np.nan)
        out[self.start:self.start + len(self.seg)] = self.seg
        return out if dtype is None else out.astype(dtype)


def orders(ctx, tf=5):
    b = ctx.bars(tf)
    H, L, C = b.high.to_numpy(float), b.low.to_numpy(float), b.close.to_numpy(float)
    i_last = b.i_last.to_numpy()
    tod = (b.index.hour * 60 + b.index.minute).to_numpy()            # the bar's open time
    bday = b.index.tz_localize(None).normalize()

    e8, e55, e165 = ind.ema(C, 8), ind.ema(C, 55), ind.ema(C, 165)   # on every bar of the 24-hour series
    bull = (e55 >= e165) & (e8 > e55)                                # NaN (warm-up) compares False
    bear = (e55 <= e165) & (e8 < e55)
    low_below = (L < e55).astype(float)                              # each bar's low against its own EMA55
    recent = pd.Series(low_below).rolling(LOOKBACK, min_periods=1).max().to_numpy() > 0      # bars k-5 .. k
    sig = bull & recent & (C > e8) & (tod >= T_FIRST) & (tod <= T_LAST)

    # the bar that is bearish: the trade is closed at that bar's close (its last 1-minute bar)
    exit_sig = np.zeros(ctx.n, bool)
    exit_sig[i_last[bear]] = True

    # stop level contributed by each completed N-minute bar, on the tick grid (rounded down: same trigger bars)
    lvl = np.floor(H * TRAIL / core.TICK + 1e-9) * core.TICK

    days = ctx.days
    day_of = {d: (int(r.i_end), float(r.atr)) for d, r in zip(days.index, days.itertuples())}
    out = []
    for k in np.flatnonzero(sig):
        info = day_of.get(bday[k])
        if info is None:
            continue                                                 # not a cash day
        i_end, atr = info
        i = int(i_last[k])
        if i >= i_end or not atr == atr:
            continue                                                 # at / after the flat bar, or no daily ATR
        # trailing stop: highest (bar high x 0.9925) over the N-minute bars completed AFTER the entry, up to the flat
        # bar. trail[t] is the level known at the close of 1-minute bar t (it applies from bar t + 1).
        q_end = int(np.searchsorted(i_last, i_end, "right"))         # bars k+1 .. q_end-1 close by the flat bar
        seg = np.full(i_end - i + 1, np.nan)
        if q_end > k + 1:
            run = np.maximum.accumulate(lvl[k + 1:q_end])
            pos = i_last[k + 1:q_end] - i                            # offset (>= 1) at which each level becomes known
            j = np.searchsorted(pos, np.arange(len(seg)), "right") - 1
            ok = j >= 0
            seg[ok] = run[j[ok]]
        out.append(dict(i=i, side=1, etype="close", stop=None, r_pts=0.1 * atr, exit_i=i_end,
                        trail=_DayTrail(ctx.n, i, seg), exit_sig=exit_sig, tag=f"L{tf}"))
    return out


def trades(ctx, **p):
    return core.run_orders(ctx, orders(ctx, **p), one_at_a_time=True, max_per_day=None, skip_roll=2)
