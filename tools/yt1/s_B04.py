#!/usr/bin/env python3
"""B04 - Jooviers Gems London box: break of the 04:00-08:59 range by a 5-minute close after the New York open.

Spec text (YT1_SPEC.md, B04):
  Box     high / low of 04:00-08:59 (neighbours: from 03:00, from 05:00); void if 09:00-09:29 trades outside it.
  Signal  the first 5-minute close outside the box from 09:30, closing by 11:00 -> enter at that close.
  Stop    beyond the breakout bar's opposite extreme (1 tick).   Target  2R (entry price +/- 2 x |entry - stop| before
          slippage, rounded to the tick).

Readings added (fixed before the first run; see notes/B04.md):
  * "trades outside" / "close outside" = strictly beyond the box edge (a touch of the edge is not outside).
  * the box is built from whatever 1-minute bars exist in the window; a day with no bar in it has no box.
"""
import numpy as np
import pandas as pd
import core

ID = "B04"
NAME = "Jooviers Gems London box (04:00-08:59), first 5m close outside from 09:30"
VARIANTS = {
    "base": dict(box_start="04:00"),
    "nb1": dict(box_start="03:00"),
    "nb2": dict(box_start="05:00"),
}


def orders(ctx, box_start="04:00"):
    b = ctx.bars(5)
    bt = b.index
    bh, bl, bc = (b[k].to_numpy(float) for k in ("high", "low", "close"))
    bil = b.i_last.to_numpy()
    T = core.TICK
    out = []
    for d, day in ctx.days.iterrows():
        lo, hi = ctx.span(d, box_start, "09:00")
        if hi <= lo:
            continue
        box_h, box_l = float(ctx.H[lo:hi].max()), float(ctx.L[lo:hi].min())
        p0, p1 = ctx.span(d, "09:00", "09:30")
        if p1 > p0 and (ctx.H[p0:p1].max() > box_h or ctx.L[p0:p1].min() < box_l):
            continue                                         # 09:00-09:29 traded outside the box: void
        t0 = pd.Timestamp(d).tz_localize(core.TZ)
        a = int(bt.searchsorted(t0 + pd.Timedelta(minutes=570)))      # 5m bars opening 09:30 ..
        z = int(bt.searchsorted(t0 + pd.Timedelta(minutes=660)))      # .. 10:55 (closing by 11:00)
        for k in range(a, z):
            c = float(bc[k])
            if c > box_h:
                stop = float(bl[k]) - T
                out.append(dict(i=int(bil[k]), side=1, etype="close", stop=stop,
                                target=core.tick_round(c + 2 * (c - stop)), exit_i=int(day.i_end), tag="L"))
                break
            if c < box_l:
                stop = float(bh[k]) + T
                out.append(dict(i=int(bil[k]), side=-1, etype="close", stop=stop,
                                target=core.tick_round(c - 2 * (stop - c)), exit_i=int(day.i_end), tag="S"))
                break
    return out


def trades(ctx, **p):
    return core.run_orders(ctx, orders(ctx, **p), max_per_day=1)
