#!/usr/bin/env python3
"""RC19b - TRADING RUSH single trigger: Keltner channel. Second, independent coding of C19b from YT1_SPEC.md.

Spec text (Family C): N-minute MNQ bars, indicators on the continuous 24-hour series; signals on bars closing
09:35 -> 15:00; entry at the signal bar's close; one position at a time, any number a day; long and short mirrored.
Long: close > EMA200 and a bar that opens and closes above the upper Keltner (20, 2 x ATR10) after one that did not.
Swing stop = beyond (1 tick) the lowest low of the last 10 bars including the signal bar. Target 1.5R from the entry
price before slippage, rounded to the tick. Neighbours: 3-minute and 15-minute bars.

Readings made here are listed in notes/RC19b.md.
"""
import numpy as np
import core
import ind

ID = "RC19b"
NAME = "Keltner (20, 2 x ATR10) open-and-close outside + EMA200 (second coder)"
VARIANTS = {
    "base": dict(tf=5),
    "nb1": dict(tf=3),
    "nb2": dict(tf=15),
}

C_FIRST, C_LAST = core.hhmm("09:35"), core.hhmm("15:00")     # the bar's CLOSING time (open + N minutes), both ends included
SWING, RR = 10, 1.5


def orders(ctx, tf=5):
    b = ctx.bars(tf)
    O, H, L, C = (b[c].to_numpy(float) for c in ("open", "high", "low", "close"))
    i_last = b.i_last.to_numpy()
    t_close = (b.index.hour * 60 + b.index.minute).to_numpy() + tf
    bday = b.index.tz_localize(None).normalize()
    T = core.TICK

    _, up, lo = ind.keltner(H, L, C, n=20, mult=2.0, atr_len=10)     # EMA20 of the close +/- 2 x ATR(10)
    e200 = ind.ema(C, 200)
    above = (O > up) & (C > up)                                       # opens and closes above its own bar's band
    below = (O < lo) & (C < lo)
    prev_ok = np.r_[False, ~np.isnan(up[:-1])]                        # the bar before has a band value
    prev_above, prev_below = np.r_[False, above[:-1]], np.r_[False, below[:-1]]
    win = (t_close >= C_FIRST) & (t_close <= C_LAST)
    long_sig = above & ~prev_above & prev_ok & (C > e200) & win
    short_sig = below & ~prev_below & prev_ok & (C < e200) & win
    swing_lo = ind.rolling_min(L, SWING) - T                          # bars k-9 .. k, one tick beyond
    swing_hi = ind.rolling_max(H, SWING) + T

    days = ctx.days
    end_of = {d: int(e) for d, e in zip(days.index, days.i_end)}
    out = []
    for k in np.flatnonzero(long_sig | short_sig):
        i_end = end_of.get(bday[k])
        if i_end is None:
            continue                                                  # not a cash day
        i = int(i_last[k])
        if i >= i_end:
            continue                                                  # at / after the flat bar (early closes)
        side = 1 if long_sig[k] else -1
        stop = swing_lo[k] if side > 0 else swing_hi[k]
        if not stop == stop:
            continue
        entry = C[k]
        target = core.tick_round(entry + side * RR * abs(entry - stop), "nearest")
        out.append(dict(i=i, side=side, etype="close", stop=float(stop), target=target, exit_i=i_end,
                        tag=("L" if side > 0 else "S") + str(tf)))
    return out


def trades(ctx, **p):
    return core.run_orders(ctx, orders(ctx, **p), one_at_a_time=True, max_per_day=None, skip_roll=2)
