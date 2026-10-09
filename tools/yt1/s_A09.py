#!/usr/bin/env python3
"""A09 - ICT Silver Bullet, first FVG in the hour with the midnight-open side rule (YT1_SPEC.md, Family A).

Signal: 3-minute bars. The first FVG whose three bars open at or after 10:00 and whose third closes by 11:00, counted
only if bullish with its top below the midnight open (the 00:00 bar's open) or bearish with its bottom above.
Entry: limit at the near edge, resting until 10:59. Stop: 1 tick beyond candle 1's extreme. Target 2R
(neighbours 1.5R, 3R). Reported: `pm` = 14:00-15:00; `nofilter` = the first FVG of either direction.

Readings added to the spec text (fixed before any run; see notes/A09.md):
  * "counted only if": an FVG that fails the side rule is not counted and the search goes on; the signal is the first
    FVG that is counted (in `nofilter` it is simply the first FVG);
  * top of a bullish gap = low of candle 3, strictly below the midnight open; bottom of a bearish gap = high of
    candle 3, strictly above it;
  * a day with no 1-minute bar stamped 00:00 has no midnight open and is not traded (not in `nofilter`, which does
    not use it);
  * one order a day, filled or not; the target is measured from the limit price;
  * candles 1, 2, 3 are adjacent rows of the 3-minute series inside the window.
"""
import numpy as np
import pandas as pd
import core

ID = "A09"
NAME = "ICT Silver Bullet, first FVG with the midnight-open side rule"
VARIANTS = {
    "base": dict(k=2.0),
    "nb1": dict(k=1.5),
    "nb2": dict(k=3.0),
    "pm": dict(k=2.0, w0="14:00", w1="15:00"),
    "nofilter": dict(k=2.0, side_rule=False),
}
T = core.TICK


# ---- shared FVG helper (copied between s_A01 / s_A03 / s_A09 / s_A10 / s_A14)
def _rows(index, date, hm0, hm1):
    """Row positions [lo, hi) of the N-minute bars OPENING at hm0 <= time < hm1 on the (week)day `date`."""
    d = pd.Timestamp(date).tz_localize(core.TZ)
    m0 = core.hhmm(hm0) if isinstance(hm0, str) else hm0
    m1 = core.hhmm(hm1) if isinstance(hm1, str) else hm1
    return (int(index.searchsorted(d + pd.Timedelta(minutes=m0), "left")),
            int(index.searchsorted(d + pd.Timedelta(minutes=m1), "left")))


def _fvgs(H, L, lo, hi):
    """Every FVG whose three bars k-2, k-1, k are all rows in [lo, hi), in time order, as (k, side).
    Bullish (+1) at k when low[k] > high[k-2]; bearish (-1) when high[k] < low[k-2]. Prices are on the tick grid, so
    any gap is >= 1 tick. The gap is known at the close of bar k (1-minute bar i_last[k])."""
    out = []
    for k in range(lo + 2, hi):
        if L[k] > H[k - 2]:
            out.append((k, 1))
        elif H[k] < L[k - 2]:
            out.append((k, -1))
    return out
# ---- end of shared helper


def orders(ctx, k=2.0, w0="10:00", w1="11:00", side_rule=True):
    b = ctx.bars(3)
    H3, L3 = b.high.to_numpy(float), b.low.to_numpy(float)
    i_last = b.i_last.to_numpy()
    out = []
    for d, day in ctx.days.iterrows():
        mo = None
        if side_rule:
            i0 = ctx.idx(d, "00:00")
            if i0 is None:
                continue                                       # no 00:00 bar: no midnight open, no trade
            mo = ctx.O[int(i0)]
        lo, hi = _rows(b.index, d, w0, w1)                     # 3-minute bars opening inside the window
        ws, we = ctx.span(d, w0, w1)
        if we <= ws:
            continue
        expire = we - 1                                        # the window's last 1-minute bar (10:59)
        for kk, side in _fvgs(H3, L3, lo, hi):
            if side > 0:
                price, stop = L3[kk], L3[kk - 2] - T           # near edge = top of the bullish gap = low of candle 3
                if side_rule and not price < mo:
                    continue
            else:
                price, stop = H3[kk], H3[kk - 2] + T           # near edge = bottom of the bearish gap
                if side_rule and not price > mo:
                    continue
            target = core.tick_round(price + side * k * abs(price - stop))
            out.append(dict(i=int(i_last[kk]), side=side, etype="limit", price=float(price), expire=int(expire),
                            stop=float(stop), target=float(target), exit_i=int(day.i_end),
                            tag="L" if side > 0 else "S"))
            break                                              # the first counted FVG only
    return out


def trades(ctx, **p):
    return core.run_orders(ctx, orders(ctx, **p), max_per_day=1)
