#!/usr/bin/env python3
"""B07 - DR / IDR defining range (TheMas7er): trade the confirmation.

Spec text (YT1_SPEC.md, B07):
  DR      high / low of 09:30-10:29 (neighbours: DR ending 10:14, ending 10:44).
  Signal  the first 5-minute close beyond the DR, on bars opening 10:30 or later and closing by 15:00 -> enter at
          that close.
  Stop    beyond the opposite DR extreme (1 tick).   Exit  flat bar.
  port    (reported) stop 0.5 x IDR height beyond the opposite IDR side and target 0.5 x IDR height beyond the near
          IDR side (IDR = highest / lowest 5-minute body in the window), the "DR/IDR Break .5 TP" script.

Readings added (fixed before the first run; see notes/B07.md):
  * "beyond the DR" = strictly above the DR high / below the DR low.
  * neighbours: the signal bars start when the neighbour's DR ends (bars opening 10:15 or later / 10:45 or later).
  * port: same signal and entry; the stop is exactly 0.5 x IDR height beyond the IDR side (a stated distance, so no
    extra tick), put on the tick grid away from the entry; the target is rounded to the nearest tick.
"""
import numpy as np
import pandas as pd
import core

ID = "B07"
NAME = "DR / IDR 09:30-10:29, first 5m close beyond, stop the opposite DR extreme, flat bar"
VARIANTS = {
    "base": dict(dr_end="10:29"),
    "nb1": dict(dr_end="10:14"),
    "nb2": dict(dr_end="10:44"),
    "port": dict(dr_end="10:29", port=True),
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


def orders(ctx, dr_end="10:29", port=False):
    tab = ib_table(ctx, dr_end)
    b = ctx.bars(5)
    bt = b.index
    bc = b.close.to_numpy(float)
    bil = b.i_last.to_numpy()
    T = core.TICK
    start = core.hhmm(dr_end) + 1
    out = []
    for d, day in ctx.days.iterrows():
        r = tab.get(d)
        if r is None:
            continue
        t0 = pd.Timestamp(d).tz_localize(core.TZ)
        a = int(bt.searchsorted(t0 + pd.Timedelta(minutes=start)))    # 5m bars opening at the DR's end ..
        z = int(bt.searchsorted(t0 + pd.Timedelta(minutes=900)))      # .. and closing by 15:00
        for k in range(a, z):
            c = float(bc[k])
            side = 1 if c > r["hi"] else -1 if c < r["lo"] else 0
            if not side:
                continue
            o = dict(i=int(bil[k]), side=side, etype="close", exit_i=int(day.i_end), tag="L" if side > 0 else "S")
            if not port:
                o["stop"] = r["lo"] - T if side > 0 else r["hi"] + T
            else:
                h = r["body_hi"] - r["body_lo"]
                if side > 0:
                    o["stop"] = core.tick_round(r["body_lo"] - 0.5 * h, "down")
                    o["target"] = core.tick_round(r["body_hi"] + 0.5 * h)
                else:
                    o["stop"] = core.tick_round(r["body_hi"] + 0.5 * h, "up")
                    o["target"] = core.tick_round(r["body_lo"] - 0.5 * h)
            out.append(o)
            break
    return out


def trades(ctx, **p):
    return core.run_orders(ctx, orders(ctx, **p), max_per_day=1)
