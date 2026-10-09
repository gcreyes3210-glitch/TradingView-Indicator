#!/usr/bin/env python3
"""A02 - Casper 5-minute candle + 1-minute FVG break.

Spec (YT1_SPEC.md):
  Range   high / low of 09:30-09:34.
  Signal  1-minute bars 09:35 -> 10:59. A bullish FVG (low[k] > high[k-2]) whose three bars are all 09:35 or later and
          at least one of which closes above the range high -> long at the close of candle 3. Bearish mirror.
          First signal of the day.
  Stop    beyond (1 tick) the low (high) of the first of those three bars that closed outside the range. Target 2R.
  Neighbours 1.5R, 3R.  Reported: c1030 = entries to 10:29; bar2 = stop beyond candle 2's extreme.

Readings added (fixed before the first run, see notes/A02.md):
  * "closed outside the range" for the stop anchor = closed beyond the edge on the trade side (above the range high
    for a long), the same condition that makes the signal.
  * the three candles are three consecutive 1-minute bars of the series inside 09:35-10:59 (a minute without a bar is
    not a candle, as on a chart).
  * only the first signal of the day is offered; if its stop is not on the losing side of the entry price the harness
    rejects the order and the day has no trade (no second signal is looked for).
"""
import core

ID = "A02"
NAME = "Casper 5-minute candle + 1-minute FVG break"
VARIANTS = {
    "base": dict(k=2.0),
    "nb1": dict(k=1.5),
    "nb2": dict(k=3.0),
    "c1030": dict(k=2.0, last="10:29"),
    "bar2": dict(k=2.0, stop_bar="bar2"),
}


def orders(ctx, k=2.0, last="10:59", stop_bar="first_out"):
    H, L, C = ctx.H, ctx.L, ctx.C
    T = core.TICK
    end = core.hhmm(last) + 1                              # exclusive end of the signal window, minutes after midnight
    out = []
    for d, day in ctx.days.iterrows():
        r0, r1 = ctx.span(d, "09:30", "09:35")
        if r1 <= r0:
            continue
        rh, rl = H[r0:r1].max(), L[r0:r1].min()
        lo, hi = ctx.span(d, "09:35", end)                 # 1-minute bars 09:35 .. last
        for c3 in range(lo + 2, hi):                       # candle 3; candles 1 and 2 are c3 - 2, c3 - 1 (all >= 09:35)
            three = (c3 - 2, c3 - 1, c3)
            side = 0
            if L[c3] > H[c3 - 2] and any(C[x] > rh for x in three):
                side = 1
            elif H[c3] < L[c3 - 2] and any(C[x] < rl for x in three):
                side = -1
            if not side:
                continue
            if stop_bar == "bar2":
                a = c3 - 1
            else:                                          # the first of the three that closed outside, trade side
                a = next(x for x in three if (C[x] > rh if side > 0 else C[x] < rl))
            stop = L[a] - T if side > 0 else H[a] + T
            entry = C[c3]
            target = core.tick_round(entry + side * k * abs(entry - stop))
            out.append(dict(i=int(c3), side=side, etype="close", stop=float(stop), target=float(target),
                            exit_i=int(day.i_end), tag=f"{'L' if side > 0 else 'S'} c{a - c3 + 3}"))
            break                                          # first signal of the day
    return out


def trades(ctx, **p):
    return core.run_orders(ctx, orders(ctx, **p), max_per_day=1)
