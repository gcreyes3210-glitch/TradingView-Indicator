#!/usr/bin/env python3
"""B09 - IB75 (Dan Cooke): pullback toward the IB extreme that was set first.

Spec text (YT1_SPEC.md, B09):
  Set-up  the 10:29 close lies in the quarter of the IB (09:30-10:29, height W) next to the extreme that was set first.
  Entry   limit one quarter of W from that extreme, resting 10:30 -> 14:59.   Target  that extreme.
  Stop    beyond the IB midpoint (neighbours: stop at 0.40 W, 0.60 W from that extreme).
  Filter  no trade if the 18:00-anchored VWAP at 10:29 lies between entry and target (reported: novwap).

Readings added (fixed before the first run; see notes/B09.md):
  * high set first and close in the top quarter -> buy limit at IB high - W / 4, target the IB high; low set first
    and close in the bottom quarter -> sell limit at IB low + W / 4, target the IB low. Same-minute extremes: there
    is no "first", so no trade. The quarter includes its line (tested on the unrounded line).
  * the stop is 1 tick beyond the level stop_frac x W from that extreme (0.50 = the midpoint; the neighbours use the
    same 1-tick buffer); when off the grid, the next tick away from the entry. The entry goes to the nearest tick.
  * VWAP: hlc3 x volume of the 1-minute bars from the first bar of the trading day (18:00 the previous evening),
    read at the close of the IB's last bar; "between" is strict (entry < VWAP < target for a long).
  * the spec has no cancel-if-target-first for this rule, so the limit rests even after the extreme has traded again.
"""
import numpy as np
import pandas as pd
import core
import ind

ID = "B09"
NAME = "IB75 (Dan Cooke): limit 1/4 W from the first-set IB extreme, target that extreme, VWAP filter"
VARIANTS = {
    "base": dict(stop_frac=0.50),
    "nb1": dict(stop_frac=0.40),
    "nb2": dict(stop_frac=0.60),
    "novwap": dict(stop_frac=0.50, vwap=False),
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


def vwap18(ctx):
    """VWAP (hlc3, 1-minute bars) restarting at the first bar of each trading day, i.e. 18:00 the previous evening.
    Value at bar k uses bars up to k only."""
    v = getattr(ctx, "_yt1B_vwap18", None)
    if v is None:
        new = np.r_[True, ctx.tdate[1:] != ctx.tdate[:-1]]
        v, _ = ind.session_vwap(ctx.H, ctx.L, ctx.C, ctx.V, new)
        setattr(ctx, "_yt1B_vwap18", v)
    return v


def orders(ctx, stop_frac=0.50, vwap=True):
    tab = ib_table(ctx, "10:29")
    vw = vwap18(ctx) if vwap else None
    T = core.TICK
    out = []
    for d, day in ctx.days.iterrows():
        r = tab.get(d)
        if r is None:
            continue
        hi, lo = r["hi"], r["lo"]
        W = hi - lo
        if W <= 0 or r["i_hi"] == r["i_lo"]:
            continue
        e0, e1 = ctx.span(d, "10:30", "15:00")               # the limit rests 10:30 -> 14:59
        if e1 <= e0:
            continue
        c, i = r["c_end"], int(r["i_dec"])
        if r["i_hi"] < r["i_lo"] and c >= hi - W / 4:        # high set first, close in the top quarter
            side, price, target = 1, core.tick_round(hi - W / 4), hi
            stop = core.tick_round(hi - stop_frac * W - T, "down")
        elif r["i_lo"] < r["i_hi"] and c <= lo + W / 4:      # low set first, close in the bottom quarter
            side, price, target = -1, core.tick_round(lo + W / 4), lo
            stop = core.tick_round(lo + stop_frac * W + T, "up")
        else:
            continue
        if vwap:
            v = vw[i]
            if v == v and min(price, target) < v < max(price, target):
                continue                                     # VWAP in the path between entry and target
        out.append(dict(i=i, side=side, etype="limit", price=price, expire=int(e1 - 1), stop=stop, target=target,
                        exit_i=int(day.i_end), tag="L" if side > 0 else "S"))
    return out


def trades(ctx, **p):
    return core.run_orders(ctx, orders(ctx, **p), max_per_day=1)
