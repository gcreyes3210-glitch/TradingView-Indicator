#!/usr/bin/env python3
"""B08 - edgeful initial-balance retracement entry.

Spec text (YT1_SPEC.md, B08):
  IB      09:30-10:29, height W. Long set-up: the IB low was set before the IB high, the 10:29 close is in the top
          quarter of the IB, and it is above the 09:30 open. Short mirror. Same-minute extremes = no trade.
  Entry   limit one quarter of W back from the IB high, resting 10:30 -> 14:59, cancelled if the target trades first.
  Stop    beyond the IB midpoint (1 tick).   Target  IB high + 0.2 W (neighbours: the IB high; IB high + 0.5 W).
  opt2    (reported) limit at the midpoint, stop beyond the IB low, same target.

Readings added (fixed before the first run; see notes/B08.md):
  * "in the top quarter" includes the quarter line itself (close >= IB high - W / 4, tested on the unrounded line).
  * computed prices go on the tick grid: entries and targets to the nearest tick; a stop is 1 tick beyond its level
    and, when that is off the grid, the next tick away from the entry.
  * "the target trades" = a bar reaches the target price (high >= target for a long), via simulate's cancel_hi / lo.
"""
import numpy as np
import pandas as pd
import core

ID = "B08"
NAME = "edgeful IB retracement: limit 1/4 W back from the IB extreme, stop beyond the midpoint"
VARIANTS = {
    "base": dict(ext=0.2),
    "nb1": dict(ext=0.0),
    "nb2": dict(ext=0.5),
    "opt2": dict(ext=0.2, opt2=True),
}


def ib_table(ctx, end="10:29"):
    """Initial balance / defining range per cash day, from the 1-minute bars 09:30 .. `end` inclusive (shared helper,
    copied between s_B07 / s_B08 / s_B09 / s_B14 / k_B07). {cash date: dict} with
        hi, lo        highest high / lowest low of the window
        i_hi, i_lo    position of the 1-minute bar that FIRST set each extreme
        o930          open of the 09:30 bar            c_end   close of the window's last bar (the `end` close)
        i_dec         position of the window's last 1-minute bar: everything here is known at its close
        body_hi, body_lo   highest / lowest 5-minute body (max / min of open, close) of the 5m bars in the window
    """
    key = "_yt1B_ib_" + end
    tab = getattr(ctx, key, None)
    if tab is not None:
        return tab
    e = core.hhmm(end) + 1
    assert e % 5 == 0, "the window must end on a 5-minute boundary"
    b = ctx.bars(5)
    bt = b.index
    bo, bc = b.open.to_numpy(float), b.close.to_numpy(float)
    b_hi, b_lo = np.maximum(bo, bc), np.minimum(bo, bc)
    tab = {}
    for d in ctx.days.index:
        lo, hi = ctx.span(d, 570, e)
        if hi <= lo:
            continue
        H, L = ctx.H[lo:hi], ctx.L[lo:hi]
        t0 = pd.Timestamp(d).tz_localize(core.TZ)
        a = int(bt.searchsorted(t0 + pd.Timedelta(minutes=570)))
        z = int(bt.searchsorted(t0 + pd.Timedelta(minutes=e)))
        if z <= a:
            continue
        tab[d] = dict(hi=float(H.max()), lo=float(L.min()), i_hi=lo + int(H.argmax()), i_lo=lo + int(L.argmin()),
                      o930=float(ctx.O[lo]), c_end=float(ctx.C[hi - 1]), i_dec=hi - 1,
                      body_hi=float(b_hi[a:z].max()), body_lo=float(b_lo[a:z].min()))
    setattr(ctx, key, tab)
    return tab


def orders(ctx, ext=0.2, opt2=False):
    tab = ib_table(ctx, "10:29")
    T = core.TICK
    out = []
    for d, day in ctx.days.iterrows():
        r = tab.get(d)
        if r is None:
            continue
        hi, lo = r["hi"], r["lo"]
        W = hi - lo
        if W <= 0 or r["i_hi"] == r["i_lo"]:                 # same-minute extremes: no trade
            continue
        e0, e1 = ctx.span(d, "10:30", "15:00")               # the limit rests 10:30 -> 14:59
        if e1 <= e0:
            continue
        c, mid = r["c_end"], (hi + lo) / 2
        if r["i_lo"] < r["i_hi"] and c >= hi - W / 4 and c > r["o930"]:
            target = core.tick_round(hi + ext * W)
            o = dict(side=1, target=target, cancel_hi=target, tag="L")
            if opt2:
                o.update(price=core.tick_round(mid), stop=lo - T)
            else:
                o.update(price=core.tick_round(hi - W / 4), stop=core.tick_round(mid - T, "down"))
        elif r["i_hi"] < r["i_lo"] and c <= lo + W / 4 and c < r["o930"]:
            target = core.tick_round(lo - ext * W)
            o = dict(side=-1, target=target, cancel_lo=target, tag="S")
            if opt2:
                o.update(price=core.tick_round(mid), stop=hi + T)
            else:
                o.update(price=core.tick_round(lo + W / 4), stop=core.tick_round(mid + T, "up"))
        else:
            continue
        o.update(i=int(r["i_dec"]), etype="limit", expire=int(e1 - 1), exit_i=int(day.i_end))
        out.append(o)
    return out


def trades(ctx, **p):
    return core.run_orders(ctx, orders(ctx, **p), max_per_day=1)
