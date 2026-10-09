#!/usr/bin/env python3
"""H1 - Pat's manipulation-candle fade (YT8_SPEC.md, Part 2).

Spec text:
  The 09:30-09:44 candle counts if its high - low is larger than the average true range of the previous 96
  fifteen-minute bars (R: simple average, the candle itself excluded). After a down-close candle: buy limit at its
  low; after an up-close candle: sell limit at its high. The limit rests 09:45-11:59 (R). Target = 38.2 % of the
  candle's range back from the entry edge. Stop = the target distance / 1.5 beyond the entry (R). One trade a day.
  Neighbours: stop = target distance / 1.0 and / 2.0.

Readings added (fixed before the first run; see notes/H1.md):
  * the 96 bars are the 96 clock-aligned 15-minute bars of the continuous series that come immediately before the
    09:30 bar (ctx.bars(15), whatever buckets exist: the 17:00-17:59 break has none, so 96 bars reach back a little
    more than one day); the true range of the first of them uses the close of the bar before it.
  * "larger than" is strict. Down-close = 09:44 close < 09:30 open, up-close = close > open, equal = no trade.
  * target distance = 0.382 x (high - low), exact; target price = entry edge +/- that distance, stop price = entry edge
    -/+ that distance / div; each put on the tick grid with core.tick_round (nearest). Both are prices fixed from the
    limit price when the order is placed (a better fill at a gap open does not move them).
  * "rests 09:45-11:59" = the order is live in the 1-minute bars stamped 09:45 ... 11:59, the 11:59 bar included.
  * no other cancel: the limit stays even if price trades through the target first (the spec has no such rule).
"""
import numpy as np
import core

ID = "H1"
NAME = "Pat's manipulation-candle fade (09:30 15m candle > ATR96, limit at its extreme, 38.2 % target)"
VARIANTS = {
    "base": dict(div=1.5),
    "nb1": dict(div=1.0),
    "nb2": dict(div=2.0),
}

N_ATR = 96
FIB = 0.382


def orders(ctx, div=1.5):
    b = ctx.bars(15)                                    # clock-aligned 15-minute bars of the continuous series
    bh, bl, bc = b.high.to_numpy(float), b.low.to_numpy(float), b.close.to_numpy(float)
    bi_first, bi_last = b.i_first.to_numpy(), b.i_last.to_numpy()
    pc = np.r_[np.nan, bc[:-1]]                         # previous 15-minute close
    tr = np.maximum(bh - bl, np.maximum(np.abs(bh - pc), np.abs(bl - pc)))      # tr[0] is NaN (no bar before it)
    out = []
    for d, day in ctx.days.iterrows():
        lo, hi = ctx.span(d, "09:30", "09:45")          # the candle's 1-minute bars
        if hi <= lo or lo != int(day.i_open):
            continue
        k = int(np.searchsorted(bi_first, lo, "left"))  # the 15-minute bar that starts with the 09:30 bar
        if k >= len(b) or bi_first[k] != lo or bi_last[k] != hi - 1 or k < N_ATR + 1:
            continue
        atr = tr[k - N_ATR:k].mean()                    # the 96 bars before the candle, the candle excluded
        if not atr == atr:
            continue
        c_h, c_l = float(ctx.H[lo:hi].max()), float(ctx.L[lo:hi].min())
        rng = c_h - c_l
        if not rng > atr:
            continue
        o, c = ctx.O[lo], ctx.C[hi - 1]                 # 09:30 open, 09:44 close
        if c < o:
            side, edge = 1, c_l                         # down-close candle: buy limit at its low
        elif c > o:
            side, edge = -1, c_h                        # up-close candle: sell limit at its high
        else:
            continue
        e0, e1 = ctx.span(d, "09:45", "12:00")          # the order is live in the bars 09:45 .. 11:59
        if e1 <= e0:
            continue
        tdist = FIB * rng
        target = core.tick_round(edge + side * tdist)
        stop = core.tick_round(edge - side * tdist / div)
        out.append(dict(i=hi - 1, side=side, etype="limit", price=float(edge), expire=e1 - 1, stop=float(stop),
                        target=float(target), exit_i=int(day.i_end), tag="L" if side > 0 else "S"))
    return out


def trades(ctx, **p):
    return core.run_orders(ctx, orders(ctx, **p), max_per_day=1, skip_roll=2)
