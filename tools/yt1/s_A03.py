#!/usr/bin/env python3
"""A03 - Casper 30-minute range, sweep and FVG back inside (YT1_SPEC.md, Family A).

Range: high / low of 09:30-09:59 (1-minute bars). 5-minute bars from 10:00, signal bars closing by 11:00.
Short: after a 5-minute bar has traded above the range high, the first bearish FVG whose third bar closes below the
range high and at least one of whose three bars traded above it; enter at the close of candle 3. Long mirror at the
range low. First signal of the day. Stop: 1 tick beyond the highest candle body (max of open, close) from the first
sweep bar through candle 3 (lowest body for longs). Target 2R (neighbours 1.5R, 3R).

Readings added to the spec text (fixed before any run; see notes/A03.md):
  * "5-minute bars from 10:00" applies to every bar the rule uses: the first sweep bar and all three FVG candles open
    at or after 10:00 (so candle 3 opens 10:10 ... 10:55);
  * "traded above" = high > range high (on the tick grid the same as 1 tick beyond); "closes below" = close < it;
  * the first sweep bar is the first 5-minute bar from 10:00 with high > range high (low < range low for longs); the
    sweep bar may be one of the three FVG candles;
  * candles 1, 2, 3 are adjacent rows of the 5-minute series inside the window.
"""
import numpy as np
import pandas as pd
import core

ID = "A03"
NAME = "Casper 30-minute range, sweep and FVG back inside"
VARIANTS = {
    "base": dict(k=2.0),
    "nb1": dict(k=1.5),
    "nb2": dict(k=3.0),
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
# ---- end of shared helper (the FVG test is written inline below because the rule adds conditions bar by bar)


def orders(ctx, k=2.0):
    b = ctx.bars(5)
    O5, H5, L5, C5 = (b[c].to_numpy(float) for c in ("open", "high", "low", "close"))
    i_last = b.i_last.to_numpy()
    out = []
    for d, day in ctx.days.iterrows():
        r0, r1 = ctx.span(d, "09:30", "10:00")
        if r1 <= r0:
            continue
        rh, rl = ctx.H[r0:r1].max(), ctx.L[r0:r1].min()
        lo, hi = _rows(b.index, d, "10:00", "11:00")           # 5-minute bars opening 10:00 ... 10:55
        su = sd = None                                         # first bar that traded above the high / below the low
        for kk in range(lo, hi):
            if su is None and H5[kk] > rh:
                su = kk
            if sd is None and L5[kk] < rl:
                sd = kk
            if kk < lo + 2:
                continue                                       # all three candles open at or after 10:00
            o = None
            if H5[kk] < L5[kk - 2]:                            # bearish FVG completed at kk
                if su is not None and C5[kk] < rh and H5[kk - 2:kk + 1].max() > rh:
                    body = max(O5[su:kk + 1].max(), C5[su:kk + 1].max())
                    stop = body + T
                    entry = C5[kk]
                    o = dict(side=-1, stop=float(stop), target=float(core.tick_round(entry - k * (stop - entry))), tag="S")
            elif L5[kk] > H5[kk - 2]:                          # bullish FVG completed at kk
                if sd is not None and C5[kk] > rl and L5[kk - 2:kk + 1].min() < rl:
                    body = min(O5[sd:kk + 1].min(), C5[sd:kk + 1].min())
                    stop = body - T
                    entry = C5[kk]
                    o = dict(side=1, stop=float(stop), target=float(core.tick_round(entry + k * (entry - stop))), tag="L")
            if o is not None:
                o.update(i=int(i_last[kk]), etype="close", exit_i=int(day.i_end))
                out.append(o)
                break                                          # first signal of the day
    return out


def trades(ctx, **p):
    return core.run_orders(ctx, orders(ctx, **p), max_per_day=1)
