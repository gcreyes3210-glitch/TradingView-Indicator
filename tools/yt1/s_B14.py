#!/usr/bin/env python3
"""B14 - IB breakout with VWAP side and a k x IB target (TradingView script by samjNQ).

Spec text (YT1_SPEC.md, B14):
  Signal  5-minute bars opening 10:30 .. 14:25. Long at the first close above the IB high (09:30-10:29) that is also
          above the 09:30-anchored VWAP; short mirror. One trade per direction per day, one at a time.
  Stop    beyond the opposite IB level (1 tick).   Target  1.5 W beyond the broken level (neighbours 1.0 W, 2.0 W).

Readings added (fixed before the first run; see notes/B14.md):
  * the long signal of a day is the first 5-minute bar whose close is above the IB high AND above the VWAP at that
    close (strict); likewise the short. Each day gives at most one long and one short order; run_orders' one-at-a-time
    rule drops one whose signal bar is at or before the other's exit bar, and it is not replaced by a later close.
  * VWAP: hlc3 x volume of the 1-minute bars from the 09:30 bar, read at the 5-minute bar's last 1-minute bar.
  * the target is rounded to the nearest tick.
"""
import numpy as np
import pandas as pd
import core
import ind

ID = "B14"
NAME = "IB breakout (samjNQ): 5m close beyond the IB on the VWAP side, stop the other IB level, target k x W"
VARIANTS = {
    "base": dict(k=1.5),
    "nb1": dict(k=1.0),
    "nb2": dict(k=2.0),
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


def orders(ctx, k=1.5):
    tab = ib_table(ctx, "10:29")
    b = ctx.bars(5)
    bt = b.index
    bc = b.close.to_numpy(float)
    bil = b.i_last.to_numpy()
    T = core.TICK
    out = []
    for d, day in ctx.days.iterrows():
        r = tab.get(d)
        if r is None:
            continue
        hi, lo = r["hi"], r["lo"]
        W = hi - lo
        if W <= 0:
            continue
        t0 = pd.Timestamp(d).tz_localize(core.TZ)
        a = int(bt.searchsorted(t0 + pd.Timedelta(minutes=630)))      # 5m bars opening 10:30 ..
        z = int(bt.searchsorted(t0 + pd.Timedelta(minutes=870)))      # .. 14:25
        if z <= a:
            continue
        s0, s1 = ctx.span(d, "09:30", "14:30")                        # 1-minute bars for the 09:30-anchored VWAP
        new = np.zeros(s1 - s0, bool)
        new[0] = True
        vw, _ = ind.session_vwap(ctx.H[s0:s1], ctx.L[s0:s1], ctx.C[s0:s1], ctx.V[s0:s1], new)
        got_l = got_s = False
        for kk in range(a, z):
            i = int(bil[kk])
            c, v = float(bc[kk]), vw[i - s0]
            if not got_l and c > hi and c > v:
                got_l = True
                out.append(dict(i=i, side=1, etype="close", stop=lo - T, target=core.tick_round(hi + k * W),
                                exit_i=int(day.i_end), tag="L"))
            if not got_s and c < lo and c < v:
                got_s = True
                out.append(dict(i=i, side=-1, etype="close", stop=hi + T, target=core.tick_round(lo - k * W),
                                exit_i=int(day.i_end), tag="S"))
            if got_l and got_s:
                break
    return out


def trades(ctx, **p):
    return core.run_orders(ctx, orders(ctx, **p), one_at_a_time=True)
