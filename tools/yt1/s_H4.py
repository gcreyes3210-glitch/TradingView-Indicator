#!/usr/bin/env python3
"""H4 - Fabio's opening-range break with a volume condition, bars only (YT8_SPEC.md, Part 2).

Spec text:
  Range 09:30-09:59. The first 5-minute candle from 10:00 to 11:25 whose open and close are both beyond the range
  (R: "the body of the candle closing above the range") and whose volume is larger than the previous 5-minute
  candle's is entered at its close. Stop 1 tick beyond that candle's low. Target 1R (his plain test). One trade a
  day. Neighbours: target 2R; and stop 2 ticks beyond the far side of the range with a 1R target.

Readings added (fixed before the first run; see notes/H4.md):
  * range = high / low of the 1-minute bars stamped 09:30 ... 09:59.
  * candles "from 10:00 to 11:25" = the clock-aligned 5-minute bars that open 10:00 ... 11:25 (the 11:25 one included).
  * "beyond" is strict: long = open > range high and close > range high; short = open < range low and close < range
    low. The candle's colour is not tested (the spec asks only where its open and close are).
  * "the previous 5-minute candle" = the bar stamped exactly 5 minutes earlier (for the 10:00 candle, the 09:55 one);
    if that bucket has no bar the candle does not qualify. "Larger" is strict.
  * the first candle that meets the body and the volume condition, on either side, is the day's only signal. If its
    stop is less than 2 ticks from its close there is no trade that day (a later candle is not looked for).
  * short: stop 1 tick above the candle's high; nb2: 2 ticks above the range high (long: 2 ticks below the range low).
  * kR: target = close +/- k x |close - stop|, on the close before slippage (the house rule for R targets); always on
    the tick grid here.
"""
import numpy as np
import pandas as pd
import core

ID = "H4"
NAME = "Fabio's 30-minute opening-range break: 5m body beyond the range with rising volume, stop under the candle"
VARIANTS = {
    "base": dict(stop_at="candle", rr=1.0),
    "nb1": dict(stop_at="candle", rr=2.0),
    "nb2": dict(stop_at="range", rr=1.0),
}


def orders(ctx, stop_at="candle", rr=1.0):
    b = ctx.bars(5)
    bt = b.index
    bo, bh, bl, bc, bv = (b[k].to_numpy(float) for k in ("open", "high", "low", "close", "volume"))
    bi_first, bi_last = b.i_first.to_numpy(), b.i_last.to_numpy()
    T = core.TICK
    five = pd.Timedelta(minutes=5)
    out = []
    for d, day in ctx.days.iterrows():
        r0, r1 = ctx.span(d, "09:30", "10:00")          # the range's 1-minute bars
        if r1 <= r0 or r0 != int(day.i_open):
            continue
        rh, rl = float(ctx.H[r0:r1].max()), float(ctx.L[r0:r1].min())
        s0, s1 = ctx.span(d, "10:00", "11:30")
        if s1 <= s0:
            continue
        m0 = int(np.searchsorted(bi_first, s0, "left")) # 5-minute bars opening 10:00 ..
        m1 = int(np.searchsorted(bi_first, s1, "left")) # .. 11:25
        for m in range(m0, m1):
            if bo[m] > rh and bc[m] > rh:
                side = 1
            elif bo[m] < rl and bc[m] < rl:
                side = -1
            else:
                continue
            if m < 1 or bt[m] - bt[m - 1] != five or not bv[m] > bv[m - 1]:
                continue
            c = bc[m]
            if stop_at == "candle":
                stop = bl[m] - T if side > 0 else bh[m] + T
            else:
                stop = rl - 2 * T if side > 0 else rh + 2 * T
            if abs(c - stop) >= 2 * T - 1e-9:
                out.append(dict(i=int(bi_last[m]), side=side, etype="close", stop=float(stop),
                                target=float(core.tick_round(c + side * rr * abs(c - stop))),
                                exit_i=int(day.i_end), tag="L" if side > 0 else "S"))
            break                                       # the first qualifying candle is the day's only signal
    return out


def trades(ctx, **p):
    return core.run_orders(ctx, orders(ctx, **p), max_per_day=1, skip_roll=2)
