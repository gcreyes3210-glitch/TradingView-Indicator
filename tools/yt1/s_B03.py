#!/usr/bin/env python3
"""B03 - Casper 5-minute range, break and wick retest, midpoint stop.

Spec (YT1_SPEC.md):
  Range   the 09:30 5-minute bar.  Break: the first later 5-minute close outside it sets the side for the day.
  Signal  a later 5-minute bar that trades back to the broken edge (low <= range high for longs) and closes outside
          it -> enter at its close. A close back inside the range before that cancels the day.
          Signal bars close by 11:00.
  Stop    beyond the range midpoint.  Target 2R.  Neighbours 1.5R, 3R.  Reported: c1300 = signals to 13:00.

Readings added (fixed before the first run, see notes/B03.md):
  * "closes outside it" for the signal = closes beyond the broken edge (close > range high for a long).
  * "a close back inside the range" = range low <= close <= range high (a close on an edge is not outside). A close
    beyond the OPPOSITE edge is not inside the range, so by the text it neither cancels nor signals; the side stays.
  * the signal bar is later than the breakout bar (the breakout bar cannot be its own retest).
  * stop = the first tick price at least 1 tick beyond the midpoint (the midpoint of an odd-tick range is off the grid).
"""
import pandas as pd
import core

ID = "B03"
NAME = "Casper 5-minute range, break and wick retest, midpoint stop"
VARIANTS = {
    "base": dict(k=2.0),
    "nb1": dict(k=1.5),
    "nb2": dict(k=3.0),
    "c1300": dict(k=2.0, last="13:00"),
}


def orders(ctx, k=2.0, last="11:00"):
    b = ctx.bars(5)
    bH, bL, bC = b.high.to_numpy(), b.low.to_numpy(), b.close.to_numpy()
    bi_last = b.i_last.to_numpy()
    T = core.TICK
    out = []
    for d, day in ctx.days.iterrows():
        day0 = pd.Timestamp(d).tz_localize(core.TZ)
        t0 = day0 + pd.Timedelta(minutes=570)
        m0 = int(b.index.searchsorted(t0, "left"))
        if m0 >= len(b) or b.index[m0] != t0:
            continue                                       # no 09:30 5-minute bar
        m1 = int(b.index.searchsorted(day0 + pd.Timedelta(minutes=core.hhmm(last)), "left"))  # bars closing by `last`
        rh, rl = bH[m0], bL[m0]
        mid = (rh + rl) / 2.0
        side = 0
        for m in range(m0 + 1, m1):
            c = bC[m]
            if side == 0:
                if c > rh:
                    side = 1                               # the break: sets the side for the day
                elif c < rl:
                    side = -1
                continue
            if rl <= c <= rh:
                break                                      # closed back inside the range: the day is cancelled
            if side > 0 and c > rh and bL[m] <= rh:
                stop = core.tick_round(mid - T, "down")
            elif side < 0 and c < rl and bH[m] >= rl:
                stop = core.tick_round(mid + T, "up")
            else:
                continue                                   # still outside without a retest (or beyond the far edge)
            target = core.tick_round(c + side * k * abs(c - stop))
            out.append(dict(i=int(bi_last[m]), side=side, etype="close", stop=float(stop), target=float(target),
                            exit_i=int(day.i_end), tag="L" if side > 0 else "S"))
            break
    return out


def trades(ctx, **p):
    return core.run_orders(ctx, orders(ctx, **p), max_per_day=1)
