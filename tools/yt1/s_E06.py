#!/usr/bin/env python3
"""E06 - NQ Stats AM TBR, fade toward the 08:00 open.

Spec text (YT1_SPEC.md, E06):
  SD      20-day sample standard deviation of prior sessions' % change, reading fixed by K-E06.
  Signal  the first touch of the 08:00 open +/- 0.25 SD between 08:00 and 09:59.
  Entry   limit at +/- 0.44 SD on that side, resting to 09:59 (neighbours 0.35, 0.55 SD; `atlevel` 0.25 SD).
  Target  the 08:00 open.   Stop  beyond +/- 1.0 SD (1 tick).   Exit  at the 11:59 close.

Readings added (fixed before the first run; see notes/E06.md):
  * the SD reading is SD_READING below, the one K-E06's rule selected from the in-sample TOUCH rate (never a trade
    result); the SD of a session uses the 20 values before it only (k_E06.sd_table).
  * touch = a 1-minute bar's high >= open x (1 + 0.25 SD) or low <= open x (1 - 0.25 SD), levels not rounded; the
    first such bar from 08:00 on must lie in 08:00-09:59. A first-touch bar that reaches both levels gives no trade.
  * the order is placed at the close of the touch bar (the signal bar) and rests from the next bar through 09:59:
    an upper touch -> sell limit at open x (1 + k SD), a lower touch -> buy limit at open x (1 - k SD), to the
    nearest tick. A touch on the window's last bar leaves nothing to rest. If the market is already beyond the limit
    price at the next bar's open, the harness fills at that open.
  * stop = 1 tick beyond open x (1 +/- 1.0 SD); the level is off the grid, so the next tick away from the entry.
  * the order is not cancelled if price returns to the 08:00 open before it fills (the entry does not say so).
  * exit bar = the last 1-minute bar before 12:00 (the 11:59 bar).
"""
import numpy as np
import pandas as pd
import core
import k_E06

ID = "E06"
NAME = "AM TBR: after the first touch of the 08:00 open +/- 0.25 SD, limit at k SD, target the 08:00 open"
SD_READING = "am"          # 08:00 -> 12:00 % change. Written once, from K-E06's in-sample touch-rate rule:
                           # touch rate 98.78 % (am) against 95.67 % (cc); published 98.95 %. Not a trade result.
VARIANTS = {
    "base": dict(entry=0.44),
    "nb1": dict(entry=0.35),
    "nb2": dict(entry=0.55),
    "atlevel": dict(entry=0.25),
}


def orders(ctx, entry=0.44):
    assert SD_READING in k_E06.READINGS, "SD_READING is set from K-E06 before E06 is run"
    sd = k_E06.sd_table(ctx, SD_READING)
    T = core.TICK
    out = []
    for d, day in ctx.days.iterrows():
        s = sd[d]
        i8 = ctx.idx(d, "08:00")
        if i8 is None or not s == s or s <= 0:
            continue
        lo, hi = ctx.span(d, "08:00", "10:00")               # the touch window and the limit's life: 08:00 .. 09:59
        x0, x1 = ctx.span(d, "08:00", "12:00")
        last, i_exit = hi - 1, min(x1 - 1, int(day.i_end))    # the 09:59 bar; the 11:59 bar
        if i_exit <= last:
            continue
        o8 = ctx.O[i8]
        ft = k_E06.first_touch(ctx, lo, hi, o8 * (1 + 0.25 * s), o8 * (1 - 0.25 * s))
        if ft is None:
            continue
        k, tside, both = ft
        if both or k >= last:
            continue
        if tside > 0:                                        # upper level touched first: fade it, short
            o = dict(side=-1, price=core.tick_round(o8 * (1 + entry * s)),
                     stop=core.tick_round(o8 * (1 + s) + T, "up"), tag="S")
        else:
            o = dict(side=1, price=core.tick_round(o8 * (1 - entry * s)),
                     stop=core.tick_round(o8 * (1 - s) - T, "down"), tag="L")
        o.update(i=int(k), etype="limit", expire=int(last), target=float(o8), exit_i=int(i_exit))
        out.append(o)
    return out


def trades(ctx, **p):
    return core.run_orders(ctx, orders(ctx, **p), max_per_day=1)
