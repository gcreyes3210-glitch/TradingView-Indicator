#!/usr/bin/env python3
"""E12 - Larry Williams Oops (long only, end-of-day exit, as tested in the StatOasis video).

Spec text (YT1_SPEC.md, E12):
  The 09:30 open is below the previous RTH low -> buy stop at that low from the 09:30 bar's close to 15:00.
  No stop. Neighbours: gap >= 0.05, >= 0.10 x daily ATR. Reported: `both` with the short mirror.

Readings added (fixed before the first run; see notes/E12.md):
  * signal bar = the 09:30 bar (the open is its open); the buy stop rests from the 09:31 bar through the last bar
    before 15:00 (the 14:59 bar). If the market is already at or above the low when the order starts to rest, the
    harness fills it at that bar's open (a stop order placed through the market).
  * base: any open strictly below the previous RTH low. Neighbours: previous RTH low - 09:30 open >= 0.05 / 0.10 x
    the day's daily ATR(14).
  * "end-of-day exit" = the flat bar. No stop, so the R unit is 0.1 x the day's daily ATR(14).
  * `both`: adds the mirror (09:30 open strictly above the previous RTH high -> sell stop at that high). The two
    set-ups cannot occur on the same day.
"""
import core

ID = "E12"
NAME = "Larry Williams Oops: open below the previous RTH low, buy stop at that low to 15:00, no stop, flat bar"
VARIANTS = {
    "base": dict(gap=0.0),
    "nb1": dict(gap=0.05),
    "nb2": dict(gap=0.10),
    "both": dict(gap=0.0, both=True),
}


def orders(ctx, gap=0.0, both=False):
    out = []
    for d, day in ctx.days.iterrows():
        atr, pdh, pdl, o = float(day.atr), float(day.pdh), float(day.pdl), float(day.o930)
        if not (atr == atr and pdh == pdh and pdl == pdl):
            continue
        i = int(day.i_open)
        lo, hi = ctx.span(d, "09:30", "15:00")
        exp = min(hi - 1, int(day.i_end))                   # the last bar before 15:00 (and never past the flat bar)
        if exp <= i:
            continue
        common = dict(i=i, etype="stop", expire=exp, exit_i=int(day.i_end), r_pts=0.1 * atr)
        if o < pdl and (pdl - o) >= gap * atr:
            out.append(dict(side=1, price=pdl, tag="L", **common))
        elif both and o > pdh and (o - pdh) >= gap * atr:
            out.append(dict(side=-1, price=pdh, tag="S", **common))
    return out


def trades(ctx, **p):
    return core.run_orders(ctx, orders(ctx, **p), max_per_day=1)
