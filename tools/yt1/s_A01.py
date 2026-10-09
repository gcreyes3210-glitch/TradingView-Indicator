#!/usr/bin/env python3
"""A01 - JadeCap Silver Bullet (YT1_SPEC.md, Family A).

Ranges (1-minute bars): Asia 20:00-23:59 of the previous calendar evening, London 02:00-04:59, the 09:00-09:59 hour.
A level (a range's high or low) is swept at the FIRST 1-minute bar that trades >= 1 tick beyond it, counted from 00:00
(Asia), 05:00 (London), 10:00 (the 09:00 hour). Direction at a moment = against the most recently swept level.
Signal: 5-minute bars; the first FVG in the trade direction whose three bars all open at or after 10:00 and whose
third bar closes by 11:00 (an FVG pointing the other way is passed over). Entry: limit at the gap's near edge, resting
until the 10:59 bar. Stop: 1 tick beyond candle 1's extreme. Target 2R (neighbours 1.5R, 3R). `pm` = 14:00-15:00.

Readings added to the spec text (fixed before any run; see notes/A01.md):
  * the direction is read at the close of each FVG's third bar, from the sweeps that have happened up to that bar;
  * an FVG that completes while no level has been swept yet is passed over like one pointing the other way;
  * if the most recent sweep bar swept a high and a low in the same 1-minute bar there is no direction at that moment;
  * the resting limit is not cancelled by a later sweep; one order a day (the first qualifying FVG), filled or not;
  * candles 1, 2, 3 are adjacent rows of the 5-minute series inside the window;
  * the target is measured from the limit price (the harness takes a fixed target; a limit filled at a better open
    keeps that target).
"""
import numpy as np
import pandas as pd
import core

ID = "A01"
NAME = "JadeCap Silver Bullet"
VARIANTS = {
    "base": dict(k=2.0),
    "nb1": dict(k=1.5),
    "nb2": dict(k=3.0),
    "pm": dict(k=2.0, w0="14:00", w1="15:00"),
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


def _wall_span(ctx, date, m0, m1):
    """[lo, hi) of 1-minute bars with wall-clock minute m0 <= t < m1 of calendar `date` (m1 may be 1440). Built from
    the wall clock so that a Sunday evening on a daylight-saving change day is still 20:00-23:59 New York."""
    d = pd.Timestamp(date)
    t0 = (d + pd.Timedelta(minutes=m0)).tz_localize(core.TZ)
    t1 = (d + pd.Timedelta(minutes=m1)).tz_localize(core.TZ)
    return int(ctx.ts.searchsorted(t0, "left")), int(ctx.ts.searchsorted(t1, "left"))


def _first_beyond(ctx, lo, hi, level, is_high):
    """First position in [lo, hi) that trades >= 1 tick beyond `level` (above a high / below a low), else None."""
    if hi <= lo:
        return None
    m = (ctx.H[lo:hi] >= level + T) if is_high else (ctx.L[lo:hi] <= level - T)
    j = int(np.argmax(m))
    return lo + j if m[j] else None


def orders(ctx, k=2.0, w0="10:00", w1="11:00"):
    b = ctx.bars(5)
    H5, L5 = b.high.to_numpy(float), b.low.to_numpy(float)
    i_last = b.i_last.to_numpy()
    out = []
    for d, day in ctx.days.iterrows():
        lo, hi = _rows(b.index, d, w0, w1)                     # 5-minute bars opening inside the window
        gaps = _fvgs(H5, L5, lo, hi)
        if not gaps:
            continue
        ws, we = ctx.span(d, w0, w1)                           # 1-minute bars of the window; we - 1 = its last bar
        if we <= ws:
            continue
        expire = we - 1
        # the three ranges and the bar from which each one's sweep is counted
        a0, a1 = _wall_span(ctx, d - pd.Timedelta(days=1), 1200, 1440)      # previous evening 20:00-23:59
        l0, l1 = ctx.span(d, "02:00", "05:00")
        h0, h1 = ctx.span(d, "09:00", "10:00")
        s_asia = ctx.span(d, "00:00", "00:01")[0]
        s_lon = ctx.span(d, "05:00", "05:01")[0]
        s_h9 = ctx.span(d, "10:00", "10:01")[0]
        sweeps = []                                            # (1-minute bar of the sweep, +1 a high / -1 a low)
        for (r0, r1, s0) in ((a0, a1, s_asia), (l0, l1, s_lon), (h0, h1, s_h9)):
            if r1 <= r0:
                continue                                       # the range has no bars: no levels from it
            hi_lvl, lo_lvl = ctx.H[r0:r1].max(), ctx.L[r0:r1].min()
            p = _first_beyond(ctx, s0, we, hi_lvl, True)
            if p is not None:
                sweeps.append((p, 1))
            p = _first_beyond(ctx, s0, we, lo_lvl, False)
            if p is not None:
                sweeps.append((p, -1))
        if not sweeps:
            continue
        for kk, side in gaps:
            i = int(i_last[kk])
            done = [(p, t) for p, t in sweeps if p <= i]       # only sweeps that have happened by this close
            if not done:
                continue                                       # no level swept yet: no direction, FVG passed over
            pmax = max(p for p, _ in done)
            kinds = {t for p, t in done if p == pmax}
            if len(kinds) != 1:
                continue                                       # a high and a low swept in the same minute
            direction = -kinds.pop()                           # a high -> short, a low -> long
            if side != direction:
                continue                                       # an FVG pointing the other way is passed over
            if side > 0:
                price, stop = L5[kk], L5[kk - 2] - T           # near edge = low of candle 3; beyond candle 1's low
            else:
                price, stop = H5[kk], H5[kk - 2] + T
            target = core.tick_round(price + side * k * abs(price - stop))
            out.append(dict(i=i, side=side, etype="limit", price=float(price), expire=int(expire), stop=float(stop),
                            target=float(target), exit_i=int(day.i_end), tag="L" if side > 0 else "S"))
            break                                              # the first FVG in the trade direction only
    return out


def trades(ctx, **p):
    return core.run_orders(ctx, orders(ctx, **p), max_per_day=1)
