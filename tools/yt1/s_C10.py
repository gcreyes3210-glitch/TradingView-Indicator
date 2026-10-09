#!/usr/bin/env python3
"""C10 - 9 / 20 EMA "Bone Zone" first pullback (5-minute only; stated for stocks). YT1_SPEC.md, family C.

Spec: Trend up (R) = EMA9 > EMA20 after at least 3 consecutive bars with low > EMA9. First pullback = the first later
bar with low <= EMA9. Enter at the close of the first up bar, from that bar on, that closes at or above EMA20,
provided no bar since the touch closed below EMA20 (that ends the set-up for the day). Signal bars closing
09:45 -> 11:00. Stop: beyond the pullback's low. Target 3R. One per direction per day. Neighbours: 2R, 4R.
Short mirrored (highs below EMA9, touch = high >= EMA9, first down bar closing at or below EMA20, a close above
EMA20 ends it, stop beyond the pullback's high).

Frame: 5-minute bars (the bar size is the parameter `bar`), EMA9 / EMA20 on the continuous 24-hour series, entry at
the signal bar's close, one position at a time, skip_roll=2.

The sequence, once per cash day and per direction, on that day's bars opening at or after 09:30 (see notes/C10.md
for the readings):
  1. trend established at the first bar t where the current run of consecutive bars with low > EMA9 (each bar
     against its own EMA9, counted from the 09:30 bar) is at least 3 long and EMA9[t] > EMA20[t];
  2. the pullback = the first bar after t with low <= EMA9;
  3. from the pullback bar on, bar by bar: a close below EMA20 ends the set-up for the day; otherwise the first bar
     with close > open and close >= EMA20 is the signal bar. It is taken only if it closes 09:45 .. 11:00;
  4. stop = 1 tick below the pullback bar's low; target = close + k x (close - stop), rounded to the tick.
"""
import numpy as np
import core
import ind

ID = "C10"
NAME = '9 / 20 EMA "Bone Zone" first pullback'
VARIANTS = {
    "base": dict(k=3.0),
    "nb1": dict(k=2.0),
    "nb2": dict(k=4.0),
}

RUN = 3                                          # consecutive bars clear of EMA9 that establish the trend
T_OPEN = 9 * 60 + 30                             # the day's sequence starts with the 09:30 bar
T_FIRST, T_LAST = 9 * 60 + 45, 11 * 60           # signal bars close 09:45 .. 11:00


def sequence(side, O, H, L, C, e9, e20, m):
    """Walk one cash day's bars m (positions in the N-minute series, in time order) for one direction.
    Returns (trend bar, pullback bar, signal bar); an element is None when that step was not reached. Each step
    reads the bar it is on and earlier bars only."""
    run, t, p = 0, None, None
    for k in m:
        if t is None:                            # 1. waiting for the trend
            clear = L[k] > e9[k] if side > 0 else H[k] < e9[k]
            run = run + 1 if clear else 0
            if run >= RUN and (e9[k] > e20[k] if side > 0 else e9[k] < e20[k]):
                t = k
            continue                             # the pullback is a LATER bar
        if p is None:                            # 2. waiting for the first pullback
            if not (L[k] <= e9[k] if side > 0 else H[k] >= e9[k]):
                continue
            p = k
        # 3. from the pullback bar on
        if (C[k] < e20[k]) if side > 0 else (C[k] > e20[k]):
            return t, p, None                    # the set-up is over for the day
        if side > 0 and C[k] > O[k] and C[k] >= e20[k]:
            return t, p, k
        if side < 0 and C[k] < O[k] and C[k] <= e20[k]:
            return t, p, k
    return t, p, None


def orders(ctx, k=3.0, bar=5):
    b = ctx.bars(bar)
    O, H, L, C = b.open.to_numpy(), b.high.to_numpy(), b.low.to_numpy(), b.close.to_numpy()
    tod = (b.index.hour * 60 + b.index.minute).to_numpy()
    i_last = b.i_last.to_numpy()
    dn = ctx.dayn[i_last]
    e9, e20 = ind.ema(C, 9), ind.ema(C, 20)

    # bars of each cash day that can take part: opening at or after 09:30, closing by 11:00
    use = np.flatnonzero((dn >= 0) & (tod >= T_OPEN) & (tod + bar <= T_LAST))
    cut = np.flatnonzero(np.diff(dn[use])) + 1
    i_end = ctx.days.i_end.to_numpy()
    out = []
    for m in np.split(use, cut):
        if len(m) == 0:
            continue
        e = int(i_end[dn[m[0]]])
        for side in (1, -1):
            t, p, s = sequence(side, O, H, L, C, e9, e20, m)
            if s is None or tod[s] + bar < T_FIRST or int(i_last[s]) >= e:
                continue
            stop = (L[p] - core.TICK) if side > 0 else (H[p] + core.TICK)
            target = core.tick_round(C[s] + side * k * abs(C[s] - stop))
            out.append(dict(i=int(i_last[s]), side=side, etype="close", stop=float(stop), target=target, exit_i=e,
                            tag="L" if side > 0 else "S"))
    return out


def trades(ctx, **p):
    return core.run_orders(ctx, orders(ctx, **p), skip_roll=2)
