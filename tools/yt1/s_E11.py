#!/usr/bin/env python3
"""E11 - Larry Williams open +/- prior range (StatOasis video; 0.25 factor and bracket from WH SelfInvest).

Spec text (YT1_SPEC.md, E11):
  W = previous RTH range. From the 09:30 bar's close: buy stop at the 09:30 open + 0.25 W, sell stop at - 0.25 W,
  resting to 15:00; the first to fill only. Stop and target 0.5 W from the entry. Neighbours: 0.20, 0.30.
  Reported: `lw1` = +/- 1.0 W, no stop, exit 15:00, no Monday longs, no Monday / Friday shorts (the video's
  crude-oil version).

Readings added (fixed before the first run; see notes/E11.md):
  * W = previous cash day's RTH high - low (days.pdh - days.pdl). Signal bar = the 09:30 bar; both orders rest from
    the 09:31 bar through the last bar before 15:00 (the 14:59 bar), never past the flat bar.
  * levels off the tick grid: an order at the exact level trades at the first tick at or beyond it, so the buy stop
    is rounded up and the sell stop down (away from the open).
  * "0.5 W from the entry" is measured from the order's price (the harness needs the bracket before the fill): the
    protective stop goes on the tick grid away from the entry (a stated distance, no extra tick), the target to the
    nearest tick. The neighbours change the 0.25 factor only; the bracket stays 0.5 W.
  * "the first to fill only": each order is simulated on its own and the one with the earlier fill bar is the day's
    trade; both filling in the same 1-minute bar = no trade (the order of the two fills is unknown).
  * `lw1`: levels +/- 1.0 W, no stop and no target, closed at the close of the last bar before 15:00; no orders at
    all on Mondays, no sell stop on Fridays (the day-of-week rule removes the order before "first to fill" is
    applied, so on a Friday the buy stop stands alone). R unit 0.1 x the day's daily ATR(14).
"""
import pandas as pd
import core

ID = "E11"
NAME = "Larry Williams open +/- 0.25 x previous RTH range, stop orders to 15:00, first to fill, bracket 0.5 W"
VARIANTS = {
    "base": dict(k=0.25),
    "nb1": dict(k=0.20),
    "nb2": dict(k=0.30),
    "lw1": dict(k=1.0, lw1=True),
}


def orders(ctx, k=0.25, lw1=False):
    """Both candidate orders of every day (same signal bar i = the 09:30 bar)."""
    out = []
    for d, day in ctx.days.iterrows():
        pdh, pdl, o, atr = float(day.pdh), float(day.pdl), float(day.o930), float(day.atr)
        if not (pdh == pdh and pdl == pdl):
            continue
        W = pdh - pdl
        if W <= 0:
            continue
        i = int(day.i_open)
        lo, hi = ctx.span(d, "09:30", "15:00")
        exp = min(hi - 1, int(day.i_end))                   # the last bar before 15:00 (and never past the flat bar)
        if exp <= i:
            continue
        buy = core.tick_round(o + k * W, "up")
        sell = core.tick_round(o - k * W, "down")
        if lw1:
            if not (atr == atr):
                continue
            common = dict(i=i, etype="stop", expire=exp, exit_i=exp, r_pts=0.1 * atr)
            if day.dow != 0:
                out.append(dict(side=1, price=buy, tag="L", **common))
            if day.dow not in (0, 4):
                out.append(dict(side=-1, price=sell, tag="S", **common))
        else:
            common = dict(i=i, etype="stop", expire=exp, exit_i=int(day.i_end))
            out.append(dict(side=1, price=buy, stop=core.tick_round(buy - 0.5 * W, "down"),
                            target=core.tick_round(buy + 0.5 * W), tag="L", **common))
            out.append(dict(side=-1, price=sell, stop=core.tick_round(sell + 0.5 * W, "up"),
                            target=core.tick_round(sell - 0.5 * W), tag="S", **common))
    return out


def first_fill(ctx, orders):
    """[(order, trade)]: per signal bar, the candidate that fills first (same fill bar: none). Roll days and days
    without a daily ATR are not traded."""
    by = {}
    for o in orders:
        by.setdefault(o["i"], []).append(o)
    out = []
    for i in sorted(by):
        d = pd.Timestamp(ctx.cdate[i])
        if d in ctx.roll_dates or d in ctx.noatr_dates or ctx.dayn[i] < 0:
            continue
        done = [(o, t) for o, t in ((o, core.simulate(ctx, **o)) for o in by[i]) if t is not None]
        if not done:
            continue
        j = min(t["j"] for _, t in done)
        first = [x for x in done if x[1]["j"] == j]
        if len(first) == 1:
            out.append(first[0])
    return out


def trades(ctx, **p):
    return [t for _, t in first_fill(ctx, orders(ctx, **p))]
