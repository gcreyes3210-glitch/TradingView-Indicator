#!/usr/bin/env python3
"""Z00 - the pattern every YT1 module follows, shown on ORB v1.4 (the calibration rule; not a YT1 test).

Read this before writing a module:
  * orders(ctx, **params) builds the list of ORDER dicts (keyword arguments of core.simulate);
    trades(ctx, **params) returns core.run_orders(ctx, orders(ctx, **params), ...). The look-ahead test calls orders().
  * an order's `i` is the 1-minute bar at whose close the decision is made; nothing later may be read to build it.
    The only exception: for etype 'open' you may read ctx.O[i + 1] to place the stop / target of that same order.
  * levels that come from a whole day (days.rth_h / rth_l / rth_c) are NOT known during that day; use pdh / pdl / pdc,
    onh / onl, o930, atr, or compute from bars up to i.
  * loop over ctx.days and slice bars by time; never assume a bar exists (use ctx.idx / ctx.span, check for None).
"""
import numpy as np
import core

ID = "Z00"
NAME = "ORB v1.4 (calibration)"
VARIANTS = {
    "base": dict(min_brk=0.15),
    "nb1": dict(min_brk=0.10),
    "nb2": dict(min_brk=0.20),
}


def orders(ctx, min_brk=0.15):
    b = ctx.bars(5)                                     # 5-minute bars: open/high/low/close/volume, i_first, i_last
    H, L, C = b.high.to_numpy(), b.low.to_numpy(), b.close.to_numpy()
    tod = (b.index.hour * 60 + b.index.minute).to_numpy()
    bday = b.index.tz_localize(None).normalize()
    i_last = b.i_last.to_numpy()                        # the 1-minute bar that closes each 5-minute bar
    T = core.TICK
    orders = []
    for d, day in ctx.days.iterrows():
        m = np.flatnonzero((bday == d) & (tod >= 570) & (tod < 690))     # this day's 5m bars opening 09:30 .. 11:25
        if len(m) < 4:
            continue
        rng_bars = m[tod[m] < 585]
        if len(rng_bars) != 3:
            continue
        orh, orl = H[rng_bars].max(), L[rng_bars].min()
        w = orh - orl
        if w < 4 * T or not (orh > day.onh or orl < day.onl):            # onh / onl are known at 09:30
            continue
        for k in m[tod[m] >= 585]:
            if C[k] > orh + 2 * T + min_brk * w:
                orders.append(dict(i=int(i_last[k]), side=1, etype="close", stop=orl - 2 * T, exit_i=int(day.i_end), tag="L"))
                break
            if C[k] < orl - 2 * T - min_brk * w:
                orders.append(dict(i=int(i_last[k]), side=-1, etype="close", stop=orh + 2 * T, exit_i=int(day.i_end), tag="S"))
                break
    return orders


def trades(ctx, **p):
    return core.run_orders(ctx, orders(ctx, **p), max_per_day=1)
