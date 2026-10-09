#!/usr/bin/env python3
"""A05 - Candle Range Theory on the 05:00-09:00 candle.

Spec (YT1_SPEC.md):
  Range   high / low of 05:00-08:59; Mid = their average.
  Signal  5-minute bars from 09:30 closing by 12:00. Short at the close of the first bar with high > range high and
          close < range high; long mirror. First signal of the day; skipped if the close is already past Mid.
  Stop    beyond (1 tick) the extreme since 09:30.  Exit: half at Mid, half at the opposite boundary.
  Neighbours: all at Mid; all at the opposite boundary.
  Reported: pdc = shorts only below the previous cash close, longs only above.

Readings added (fixed before the first run, see notes/A05.md):
  * "skipped" = the day has no trade (the first signal is the only one; a later one is not looked for).
  * "past Mid" is strict and uses the exact average; the Mid ORDER price is that average put on the tick grid
    (core.tick_round nearest), because a range of an odd number of ticks has its average between two ticks.
  * a bar that gives both signals at once (a range narrower than the bar) is the first signal on both sides: no trade.
  * pdc filters the base trade (it does not go on to a later signal); the price compared with the previous cash close
    is the signal bar's close, i.e. the entry price.
"""
import numpy as np
import pandas as pd
import core

ID = "A05"
NAME = "Candle Range Theory on the 05:00-09:00 candle"
VARIANTS = {
    "base": dict(exit="half"),
    "nb1": dict(exit="mid"),
    "nb2": dict(exit="far"),
    "pdc": dict(exit="half", pdc=True),
}


def orders(ctx, exit="half", pdc=False):
    b = ctx.bars(5)
    bH, bL, bC = b.high.to_numpy(), b.low.to_numpy(), b.close.to_numpy()
    bi_last = b.i_last.to_numpy()
    T = core.TICK
    out = []
    for d, day in ctx.days.iterrows():
        r0, r1 = ctx.span(d, "05:00", "09:00")
        if r1 <= r0:
            continue
        rh, rl = ctx.H[r0:r1].max(), ctx.L[r0:r1].min()
        mid = (rh + rl) / 2.0
        mid_px = core.tick_round(mid)
        day0 = pd.Timestamp(d).tz_localize(core.TZ)
        m0 = int(b.index.searchsorted(day0 + pd.Timedelta(minutes=570), "left"))     # bars opening 09:30 ..
        m1 = int(b.index.searchsorted(day0 + pd.Timedelta(minutes=720), "left"))     # .. 11:55 (closing by 12:00)
        for m in range(m0, m1):
            short = bH[m] > rh and bC[m] < rh
            long_ = bL[m] < rl and bC[m] > rl
            if not (short or long_):
                continue
            if short and long_:
                break                                      # both sides on one bar: no first signal, no trade
            side = -1 if short else 1
            c = bC[m]
            if (c < mid) if side < 0 else (c > mid):
                break                                      # the close is already past Mid: skipped
            if pdc and not ((c < day.pdc) if side < 0 else (c > day.pdc)):
                break
            stop = bH[m0:m + 1].max() + T if side < 0 else bL[m0:m + 1].min() - T    # extreme since 09:30
            far = rl if side < 0 else rh
            o = dict(i=int(bi_last[m]), side=side, etype="close", stop=float(stop), exit_i=int(day.i_end),
                     tag="S" if side < 0 else "L")
            if exit == "half":
                o["parts"] = [(float(mid_px), 0.5), (float(far), 0.5)]
            elif exit == "mid":
                o["target"] = float(mid_px)
            else:
                o["target"] = float(far)
            out.append(o)
            break                                          # first signal of the day
    return out


def trades(ctx, **p):
    return core.run_orders(ctx, orders(ctx, **p), max_per_day=1)
