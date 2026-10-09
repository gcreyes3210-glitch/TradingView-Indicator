#!/usr/bin/env python3
"""B01 - Quick Flip Scalper (ProRealAlgos): fade an oversized 15-minute opening candle with a reversal candle that
prints outside its box.

Spec text (YT1_SPEC.md, B01):
  Box     high / low of 09:30-09:44. Traded only if box height >= thr x daily ATR(14) (thr 0.25; neighbours 0.20, 0.30).
          Red opening candle (09:44 close < 09:30 open) -> longs below the box only; green -> shorts above only;
          equal -> none.
  Signal  5-minute bars opening 09:45 .. 10:55 whose body lies entirely outside the box on the trade side and which are
          a hammer (lower wick >= 2 x body, upper wick <= body, range >= 4 ticks) or a bullish engulfing (up bar after a
          down bar, close >= previous open, open <= previous close); mirror for shorts. First signal only.
  Entry   the next 5-minute bar's open.   Stop  beyond the signal bar's extreme (1 tick).   Target  the far side of
          the box.

Readings added (fixed before the first run; see notes/B01.md):
  * "body entirely outside the box": strictly beyond the edge (long: max(open, close) < box low).
  * "previous" bar of an engulfing = the 5-minute bar stamped exactly 5 minutes earlier (it may be the 09:40 bar);
    if that bucket has no bar the engulfing test is false.
  * a doji (body 0) passes the hammer test when it has no upper wick and a range of >= 4 ticks, as the sizes are written.
  * the stop and the target do not depend on the fill, so the next bar's open is never read here; the harness drops
    the order if that open is at or through the stop.
"""
import numpy as np
import pandas as pd
import core

ID = "B01"
NAME = "Quick Flip Scalper (15m box >= x ATR, reversal candle outside the box)"
VARIANTS = {
    "base": dict(thr=0.25),
    "nb1": dict(thr=0.20),
    "nb2": dict(thr=0.30),
}


def orders(ctx, thr=0.25):
    b = ctx.bars(5)
    bt = b.index
    bo, bh, bl, bc = (b[k].to_numpy(float) for k in ("open", "high", "low", "close"))
    bil = b.i_last.to_numpy()
    T = core.TICK
    five = pd.Timedelta(minutes=5)
    out = []
    for d, day in ctx.days.iterrows():
        atr = day.atr
        if not atr == atr:                                   # no daily ATR: not traded
            continue
        lo, hi = ctx.span(d, "09:30", "09:45")               # the 15-minute opening candle, 1-minute bars
        if hi <= lo:
            continue
        box_h, box_l = float(ctx.H[lo:hi].max()), float(ctx.L[lo:hi].min())
        if box_h - box_l < thr * atr:
            continue
        o, c = ctx.O[lo], ctx.C[hi - 1]                      # 09:30 open, 09:44 close
        if c < o:
            side = 1                                         # red opening candle: longs below the box
        elif c > o:
            side = -1                                        # green: shorts above the box
        else:
            continue
        t0 = pd.Timestamp(d).tz_localize(core.TZ)
        a = int(bt.searchsorted(t0 + pd.Timedelta(minutes=585)))      # 5m bars opening 09:45 ..
        z = int(bt.searchsorted(t0 + pd.Timedelta(minutes=660)))      # .. 10:55
        for k in range(a, z):
            top, bot = max(bo[k], bc[k]), min(bo[k], bc[k])
            body, rng = top - bot, bh[k] - bl[k]
            up_w, lo_w = bh[k] - top, bot - bl[k]
            prev = k >= 1 and bt[k] - bt[k - 1] == five
            if side > 0:
                if not top < box_l:
                    continue
                hammer = lo_w >= 2 * body and up_w <= body and rng >= 4 * T
                engulf = bool(prev and bc[k] > bo[k] and bc[k - 1] < bo[k - 1]
                              and bc[k] >= bo[k - 1] and bo[k] <= bc[k - 1])
                if hammer or engulf:
                    out.append(dict(i=int(bil[k]), side=1, etype="open", stop=float(bl[k]) - T, target=box_h,
                                    exit_i=int(day.i_end), tag="hammer" if hammer else "engulf"))
                    break
            else:
                if not bot > box_h:
                    continue
                hammer = up_w >= 2 * body and lo_w <= body and rng >= 4 * T
                engulf = bool(prev and bc[k] < bo[k] and bc[k - 1] > bo[k - 1]
                              and bc[k] <= bo[k - 1] and bo[k] >= bc[k - 1])
                if hammer or engulf:
                    out.append(dict(i=int(bil[k]), side=-1, etype="open", stop=float(bh[k]) + T, target=box_l,
                                    exit_i=int(day.i_end), tag="inv_hammer" if hammer else "engulf"))
                    break
    return out


def trades(ctx, **p):
    return core.run_orders(ctx, orders(ctx, **p), max_per_day=1)
