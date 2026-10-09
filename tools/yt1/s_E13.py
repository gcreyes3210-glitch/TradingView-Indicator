#!/usr/bin/env python3
"""E13 - Crabel stretch after a 2-day narrow range (Jack Corsellis' summary of Crabel).

Spec text (YT1_SPEC.md, E13):
  RTH days. Set-up: the last two days' combined range is the narrowest two-day range of the last 20 days.
  Stretch = 10-day average of min(open - low, high - open). From the 09:30 bar's close: buy stop at the open +
  stretch, sell stop at - stretch, to 15:00; the first to fill is the trade and the other level is its stop.
  60 minutes after the fill the stop moves to the entry price (R).
  Neighbours: 0.75, 1.25 x stretch. Reported: `nr3` (three-day range, 20 days).

Readings added (fixed before the first run; see notes/E13.md):
  * days = the rows of the day table (cash sessions, short days included); everything uses COMPLETED previous days
    only: on day t the daily highs, lows and opens of t-1, t-2, ... (today's own high / low are never read).
  * N-day range ending on day s = max(high s-N+1..s) - min(low s-N+1..s). Set-up on day t: the range ending on t-1
    is <= every N-day range that lies wholly inside the last 20 completed days t-20..t-1 (19 two-day windows, 18
    three-day windows). An equal range elsewhere does not cancel the set-up. Needs 20 completed days.
  * stretch on day t = mean over t-10..t-1 of min(09:30 open - RTH low, RTH high - 09:30 open).
  * levels off the tick grid: an order at the exact level trades at the first tick at or beyond it, so the buy stop
    is rounded up and the sell stop down (away from the open). The protective stop is the other order's price
    exactly (no extra tick). No target; flat bar.
  * orders rest from the 09:31 bar through the last bar before 15:00. Each is simulated on its own and the one with
    the earlier fill bar is the trade; both filling in the same 1-minute bar = no trade.
  * break-even: with the fill in the bar stamped t, the stop is at the entry price (the fill before slippage, the
    harness's own break-even convention) for every bar after the first bar stamped t + 60 minutes or later, i.e.
    trail[k] = entry from that bar on (known at its close, applied from the next bar). The trail is built from the
    fill time alone.
"""
import numpy as np
import pandas as pd
import core

ID = "E13"
NAME = "Crabel stretch after a 2-day narrow range: stop orders at the open +/- stretch, other level is the stop, BE after 60 min"
VARIANTS = {
    "base": dict(mult=1.0),
    "nb1": dict(mult=0.75),
    "nb2": dict(mult=1.25),
    "nr3": dict(mult=1.0, nd=3),
}
LOOK, SDAYS, BE_MIN = 20, 10, 60


def day_setup(ctx, nd=2):
    """Per day-table row: (set-up True / False, stretch), both from completed previous days only."""
    D = ctx.days
    h, l, o = D.rth_h.to_numpy(float), D.rth_l.to_numpy(float), D.o930.to_numpy(float)
    n = len(D)
    rng = np.full(n, np.nan)                                # N-day range ending on row s
    for s in range(nd - 1, n):
        rng[s] = h[s - nd + 1:s + 1].max() - l[s - nd + 1:s + 1].min()
    dist = np.minimum(o - l, h - o)
    setup, stretch = np.zeros(n, bool), np.full(n, np.nan)
    for t in range(n):
        if t >= SDAYS:
            stretch[t] = dist[t - SDAYS:t].mean()           # rows t-10 .. t-1
        if t >= LOOK:
            w = rng[t - LOOK + nd - 1:t]                    # windows ending t-20+nd-1 .. t-1: inside rows t-20 .. t-1
            setup[t] = bool(rng[t - 1] <= w.min())
    return setup, stretch


def orders(ctx, mult=1.0, nd=2):
    """Both candidate orders of every set-up day (same signal bar i = the 09:30 bar), without the break-even trail
    (it depends on which one fills, and when: trades() adds it)."""
    setup, stretch = day_setup(ctx, nd)
    out = []
    for t, (d, day) in enumerate(ctx.days.iterrows()):
        if not setup[t] or not (stretch[t] == stretch[t]):
            continue
        o = float(day.o930)
        i = int(day.i_open)
        lo, hi = ctx.span(d, "09:30", "15:00")
        exp = min(hi - 1, int(day.i_end))                   # the last bar before 15:00 (and never past the flat bar)
        if exp <= i:
            continue
        buy = core.tick_round(o + mult * stretch[t], "up")
        sell = core.tick_round(o - mult * stretch[t], "down")
        if not buy > sell:
            continue
        common = dict(i=i, etype="stop", expire=exp, exit_i=int(day.i_end))
        out.append(dict(side=1, price=buy, stop=sell, tag="L", **common))
        out.append(dict(side=-1, price=sell, stop=buy, tag="S", **common))
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
    out = []
    trail = np.full(ctx.n, np.nan)
    for o, t in first_fill(ctx, orders(ctx, **p)):
        j, side = t["j"], (1 if t["side"] == "L" else -1)
        entry = t["entry"] - core.SLIP * side               # the fill before slippage
        k0 = int(ctx.ts.searchsorted(ctx.ts[j] + pd.Timedelta(minutes=BE_MIN), "left"))
        k1 = o["exit_i"] + 1
        trail[k0:k1] = entry                                # from the fill time only: NaN before, the entry after
        t2 = core.simulate(ctx, trail=trail, **o)
        trail[k0:k1] = np.nan
        if t2 is not None:
            out.append(t2)
    return out
