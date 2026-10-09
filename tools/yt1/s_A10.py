#!/usr/bin/env python3
"""A10 - First presented FVG after 09:30 (YT1_SPEC.md, Family A).

Signal: 1-minute bars. The first FVG, either direction, whose three bars are 09:30 or later and whose third bar is
09:59 or earlier. Enter with the gap at the close of candle 3. Stop: 1 tick beyond candle 1's extreme. No target; flat
bar. Neighbours: the same on 2-minute and 3-minute bars.
Reported: `ce` = limit at the gap's midpoint resting to 10:59, same stop, 2R; `2R` = immediate entry, 2R target.

Readings added to the spec text (fixed before any run; see notes/A10.md):
  * on N-minute bars the three bars open at 09:30 or later and the third bar's last minute is 09:59 or earlier
    (it opens by 09:58 on 2-minute bars, 09:57 on 3-minute bars);
  * `ce`: a midpoint that falls between two ticks is moved to the first tradable price at or through it (down for a
    buy limit, up for a sell limit); the signal is still the day's first FVG, whether or not its limit fills; the 2R
    target is measured from the limit price;
  * candles 1, 2, 3 are adjacent rows of the bar series inside 09:30-09:59 (a minute without a trade has no bar).
"""
import numpy as np
import pandas as pd
import core

ID = "A10"
NAME = "First presented FVG after 09:30"
VARIANTS = {
    "base": dict(tf=1),
    "nb1": dict(tf=2),
    "nb2": dict(tf=3),
    "ce": dict(tf=1, mode="ce"),
    "2R": dict(tf=1, mode="2R"),
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


def orders(ctx, tf=1, mode="hold"):
    b = ctx.bars(tf)
    Hn, Ln, Cn = b.high.to_numpy(float), b.low.to_numpy(float), b.close.to_numpy(float)
    i_last = b.i_last.to_numpy()
    out = []
    for d, day in ctx.days.iterrows():
        lo, hi = _rows(b.index, d, "09:30", "10:00")           # bars opening 09:30 ... and ending by 09:59
        gaps = _fvgs(Hn, Ln, lo, hi)
        if not gaps:
            continue
        kk, side = gaps[0]                                     # the first presented FVG, either direction
        i = int(i_last[kk])
        stop = (Ln[kk - 2] - T) if side > 0 else (Hn[kk - 2] + T)          # beyond candle 1's extreme
        o = dict(i=i, side=side, stop=float(stop), exit_i=int(day.i_end), tag="L" if side > 0 else "S")
        if mode == "ce":
            mid = (Hn[kk - 2] + Ln[kk]) / 2 if side > 0 else (Ln[kk - 2] + Hn[kk]) / 2
            price = core.tick_round(mid, "down" if side > 0 else "up")
            ws, we = ctx.span(d, "10:00", "11:00")
            if we <= ws:
                continue
            o.update(etype="limit", price=float(price), expire=int(we - 1),
                     target=float(core.tick_round(price + side * 2.0 * abs(price - stop))))
        else:
            entry = Cn[kk]
            o.update(etype="close")
            if mode == "2R":
                o.update(target=float(core.tick_round(entry + side * 2.0 * abs(entry - stop))))
        out.append(o)
    return out


def trades(ctx, **p):
    return core.run_orders(ctx, orders(ctx, **p), max_per_day=1)
