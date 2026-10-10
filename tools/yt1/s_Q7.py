#!/usr/bin/env python3
"""Q7 - momentum scalp with a tick bracket (M12a, El Trader Financiado).  YT11_SPEC.md, Part 4.

Spec: 1-minute MNQ bars, signal bars stamped 09:30 .. 10:29. A bar closes above the session high so far (the highs
of the earlier bars from 09:30) with volume above 1.5 x the mean of the previous 20 bars: buy at the close. Stop
6 ticks below the entry price, target 16 ticks above. Short mirrored: a close below the session low so far (lows of
the earlier bars from 09:30), same volume test, stop 6 ticks above, target 16 ticks below. "Strong delta" left out.
One position at a time; every signal that comes while flat is taken. Neighbours 4 / 8 and 6 / 12 ticks; reported
x4 = 24 / 64 ticks.

Readings (all fixed before the first run, see notes/Q7.md):
  * entry price = the entry reference price = the signal bar's close; stop and target are fixed prices that many
    ticks from it (the house fill is 1 tick worse than the reference on every fill).
  * "the previous 20 bars" = the 20 one-minute bars before the signal bar on the continuous 24-hour series (for the
    first signals of the day these are pre-market bars), as a chart's 20-bar volume average shifted by one bar.
  * the 09:30 bar has no earlier bar from 09:30, so the first possible signal bar is 09:31.
  * the session high / low so far keeps running through the day whatever the trades do.
"""
import numpy as np
import core
import ind

ID = "Q7"
NAME = "Momentum scalp, tick bracket: close beyond the session extreme on 1.5x volume, 09:30-10:29 (M12a)"
VARIANTS = {
    "base": dict(stop_ticks=6, target_ticks=16),
    "nb1": dict(stop_ticks=4, target_ticks=8),
    "nb2": dict(stop_ticks=6, target_ticks=12),
    "x4": dict(stop_ticks=24, target_ticks=64),
}

WIN_LO, WIN_HI = "09:30", "10:30"          # signal bars 09:30 .. 10:29
VOL_N, VOL_K = 20, 1.5


def orders(ctx, stop_ticks=6, target_ticks=16):
    H, L, C, V = ctx.H, ctx.L, ctx.C, ctx.V
    T = core.TICK
    vm = ind.sma(V, VOL_N)                              # vm[k] = mean volume of bars k-19 .. k
    out = []
    for d, day in ctx.days.iterrows():
        lo, hi = ctx.span(d, WIN_LO, WIN_HI)
        if hi - lo < 2 or lo < VOL_N:
            continue
        # session extremes of the EARLIER bars from 09:30: for bar lo + m it is the max / min over lo .. lo + m - 1
        hh = np.maximum.accumulate(H[lo:hi])
        ll = np.minimum.accumulate(L[lo:hi])
        for k in range(lo + 1, hi):
            prev_mean = vm[k - 1]                       # mean of the 20 bars before bar k
            if not (V[k] > VOL_K * prev_mean):
                continue
            c = C[k]
            if c > hh[k - 1 - lo]:
                out.append(dict(i=int(k), side=1, etype="close", stop=c - stop_ticks * T,
                                target=c + target_ticks * T, exit_i=int(day.i_end), tag="L"))
            elif c < ll[k - 1 - lo]:
                out.append(dict(i=int(k), side=-1, etype="close", stop=c + stop_ticks * T,
                                target=c - target_ticks * T, exit_i=int(day.i_end), tag="S"))
    return out


def trades(ctx, **p):
    return core.run_orders(ctx, orders(ctx, **p), one_at_a_time=True)
