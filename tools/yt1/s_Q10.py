#!/usr/bin/env python3
"""Q10 - the overnight drift hour (N06, Boyarchenko, Larsen, Whelan; `eu` = N07).  YT11_SPEC.md, Part 4.

Spec: buy at the close of the 01:59 bar, sell at the close of the 02:59 bar, every trading day. No stop: R unit =
0.1 x daily ATR. Neighbours: 01:30-03:30; 02:00-03:30. Reported `eu` = 23:30-03:30.

Readings (all fixed before the first run, see notes/Q10.md):
  * a window written as clock times a-b is held from the close of the bar ending at a to the close of the bar ending
    at b, as the base's own wording does for 02:00-03:00 (the 01:59 bar -> the 02:59 bar). So 01:30-03:30 = the
    01:29 bar -> the 03:29 bar; 02:00-03:30 = 01:59 -> 03:29; 23:30-03:30 = 23:29 -> 03:29.
  * trading day = a cash day of the day table (a day with a regular session); its overnight bars are the ones from
    18:00 the evening before. The 01:xx / 02:xx / 03:xx bars carry the cash day's own calendar date; the 23:29 bar
    of `eu` is on the previous calendar date (a Sunday for a Monday) and belongs to the same trading day.
  * a day on which the entry minute or the exit minute has no bar is no trade.
  * roll days and days without a daily ATR are dropped by TRADING day (see trades()): the roll flag and the ATR of
    the cash day the night leads into. ATR = that cash day's `atr`, known at 18:00 the evening before.
"""
import pandas as pd
import core

ID = "Q10"
NAME = "Overnight drift hour: long 02:00 -> 03:00 New York (N06)"
VARIANTS = {
    "base": dict(buy="01:59", sell="02:59"),
    "nb1": dict(buy="01:29", sell="03:29"),
    "nb2": dict(buy="01:59", sell="03:29"),
    "eu": dict(buy="23:29", sell="03:29"),
}

DAY_START = 18 * 60                     # 18:00 and later belongs to the next trading day


def orders(ctx, buy="01:59", sell="02:59"):
    out = []
    one_day = pd.Timedelta(days=1)
    for d, day in ctx.days.iterrows():
        if not (day.atr == day.atr):
            continue
        i = ctx.idx(d - one_day if core.hhmm(buy) >= DAY_START else d, buy)
        x = ctx.idx(d - one_day if core.hhmm(sell) >= DAY_START else d, sell)
        if i is None or x is None or x <= i:
            continue
        if pd.Timestamp(ctx.tdate[i]) != d or pd.Timestamp(ctx.tdate[x]) != d:
            continue
        out.append(dict(i=int(i), side=1, etype="close", exit_i=int(x), r_pts=0.1 * float(day.atr), tag="L"))
    return out


def trades(ctx, **p):
    """core.run_orders looks up roll / ATR / cash-day status by the CALENDAR date of the signal bar. That is the
    trading day for the 01:29 / 01:59 entries, but not for the 23:29 entry of `eu` (previous calendar date; every
    Sunday-evening entry would be dropped as "not a cash day", and the roll flag would be read one day off). So the
    same filters are applied here by trading day (ctx.tdate of the signal bar) and each order goes to core.simulate.
    For base, nb1 and nb2 this gives the same trades as core.run_orders (checked, notes/Q10.md)."""
    out, busy_until = [], -1
    for o in sorted(orders(ctx, **p), key=lambda o: o["i"]):
        d = pd.Timestamp(ctx.tdate[o["i"]])
        if d not in ctx.days.index or d in ctx.roll_dates or d in ctx.noatr_dates:
            continue
        if o["i"] <= busy_until:
            continue
        t = core.simulate(ctx, **o)
        if t is None:
            continue
        out.append(t)
        busy_until = t["k"]
    return out
