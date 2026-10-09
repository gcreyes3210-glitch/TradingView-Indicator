#!/usr/bin/env python3
"""A14 - Candle Range Theory, hourly (YT1_SPEC.md, Family A).

Range candle: each clock hour 08:00 ... 13:00. Sweep candle: the next hour, when it trades beyond exactly one extreme
of the range candle and closes back inside its range. Signal: in the 60 minutes after the sweep candle closes, the
first 5-minute FVG against the sweep whose three bars open after that close. Entry: limit at the near edge, resting to
the end of those 60 minutes. Stop: 1 tick beyond the sweep candle's extreme. Exit: half at 1R, half at the range
candle's opposite extreme; no trade if that extreme is nearer than 1R. At most 2 trades a day, one at a time.
Neighbours: all at 1R; all at the opposite extreme. Reported: `mkt` = market at the sweep candle's close, same stop,
target the opposite extreme.

Readings added to the spec text (fixed before any run; see notes/A14.md):
  * hourly candles are built from the 1-minute bars of the clock hour; "trades beyond" = high > range high or
    low < range low; "exactly one" = one and not the other;
  * "closes back inside" = the sweep candle's close is strictly back past the swept extreme (close < range high after
    a sweep of the high; close > range low after a sweep of the low), the wording the spec uses in A05;
  * a sweep of the high is traded short (bearish FVG), a sweep of the low long (bullish FVG);
  * the FVG's three 5-minute bars open in the hour after the sweep candle, so candle 3 closes inside the 60 minutes;
  * 1R = |limit price - stop|; "nearer than 1R" = distance from the limit price to the opposite extreme < 1R (equal
    is traded); the condition is kept in both neighbours and in `mkt` (there measured from the sweep candle's close);
  * only the first FVG against the sweep is the signal: if its stop is not beyond its entry, or the opposite extreme
    is nearer than 1R, the set-up gives no trade (the search does not move to a later FVG);
  * candles 1, 2, 3 are adjacent rows of the 5-minute series inside the hour.
"""
import numpy as np
import pandas as pd
import core

ID = "A14"
NAME = "Candle Range Theory, hourly"
VARIANTS = {
    "base": dict(exit="split"),
    "nb1": dict(exit="1R"),
    "nb2": dict(exit="opp"),
    "mkt": dict(exit="opp", entry="mkt"),
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


def orders(ctx, exit="split", entry="limit"):
    b = ctx.bars(5)
    H5, L5 = b.high.to_numpy(float), b.low.to_numpy(float)
    i_last = b.i_last.to_numpy()
    out = []
    for d, day in ctx.days.iterrows():
        for h in range(8, 14):                                 # range candle h:00, sweep candle (h+1):00
            a0, a1 = ctx.span(d, h * 60, (h + 1) * 60)
            s0, s1 = ctx.span(d, (h + 1) * 60, (h + 2) * 60)
            if a1 <= a0 or s1 <= s0:
                continue
            rh, rl = ctx.H[a0:a1].max(), ctx.L[a0:a1].min()
            sh, sl, sc = ctx.H[s0:s1].max(), ctx.L[s0:s1].min(), ctx.C[s1 - 1]
            up, dn = sh > rh, sl < rl
            if up == dn:
                continue                                       # neither extreme, or both
            if up:
                if not sc < rh:
                    continue                                   # did not close back inside
                side, stop, opp = -1, sh + T, rl               # short; stop beyond the sweep candle's high
            else:
                if not sc > rl:
                    continue
                side, stop, opp = 1, sl - T, rh
            tag = f"{'L' if side > 0 else 'S'} range {h:02d}:00"
            if entry == "mkt":
                price = sc
                risk = side * (price - stop)
                if risk <= 0 or side * (opp - price) < risk:
                    continue                                   # opposite extreme nearer than 1R
                out.append(dict(i=int(s1 - 1), side=side, etype="close", stop=float(stop), target=float(opp),
                                exit_i=int(day.i_end), tag=tag))
                continue
            lo, hi = _rows(b.index, d, (h + 2) * 60, (h + 3) * 60)          # 5-minute bars of the next 60 minutes
            ws, we = ctx.span(d, (h + 2) * 60, (h + 3) * 60)
            if we <= ws:
                continue
            for kk, fs in _fvgs(H5, L5, lo, hi):
                if fs != side:
                    continue
                price = L5[kk] if side > 0 else H5[kk]         # near edge
                risk = side * (price - stop)
                if risk > 0 and side * (opp - price) >= risk:
                    o = dict(i=int(i_last[kk]), side=side, etype="limit", price=float(price), expire=int(we - 1),
                             stop=float(stop), exit_i=int(day.i_end), tag=tag)
                    t1 = price + side * risk
                    if exit == "split":
                        o["parts"] = [(float(t1), 0.5), (float(opp), 0.5)]
                    elif exit == "1R":
                        o["target"] = float(t1)
                    else:
                        o["target"] = float(opp)
                    out.append(o)
                break                                          # the first FVG against the sweep, traded or not
    return out


def trades(ctx, **p):
    return core.run_orders(ctx, orders(ctx, **p), max_per_day=2)
