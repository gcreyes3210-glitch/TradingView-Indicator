#!/usr/bin/env python3
"""G5 - TTrades 4-hour power of three (YT4_SPEC.md, Part 2).

Bias required (tt.bias). Gate: the 4-hour candle that has just closed (06:00-09:59 or 10:00-13:59 New York) is a
candle 2 closure in the bias direction (tt.closure2 against the 4-hour candle before it). Trade the next 4-hour candle
(10:00 or 14:00): the first 15-minute CISD in the bias direction (tt.cisd on the clock-aligned 15-minute series) on a
bar that opens inside it. Entry at that bar's close (the 1-minute bar that closes it), stop 1 tick beyond the
protected low / high, target k R (2; neighbours 1.5 and 3), exit at the traded 4-hour candle's last bar or the flat
bar, whichever comes first. One trade per 4-hour candle.

Readings (R), all fixed before the first run - see notes/G5.md.
"""
import numpy as np
import core
import tt

ID = "G5"
NAME = "TTrades 4-hour power of three (4H candle 2 closure, 15m CISD in the next 4H candle)"
VARIANTS = {
    "base": dict(k=2.0),
    "nb1": dict(k=1.5),
    "nb2": dict(k=3.0),
}
T = core.TICK
# (candle before the gate, gate candle, traded candle): New York clock blocks, minutes after midnight
BLOCKS = (((120, 360), (360, 600), (600, 840)),       # 02:00 | 06:00 gate | trade 10:00-13:59
          ((360, 600), (600, 840), (840, 1080)))      # 06:00 | 10:00 gate | trade 14:00-17:59 (flat bar comes first)


def _candle(ctx, d, m0, m1):
    """(high, low, close) of the 1-minute bars m0 <= time < m1 on date d, or None when the candle holds fewer than
    half its minutes (YT4_SPEC Part 1: "a candle needs at least half its minutes to count")."""
    lo, hi = ctx.span(d, m0, m1)
    if (hi - lo) * 2 < (m1 - m0):
        return None
    return ctx.H[lo:hi].max(), ctx.L[lo:hi].min(), ctx.C[hi - 1]


def orders(ctx, k=2.0):
    B = tt.bias(ctx)
    b = ctx.bars(15)                                    # clock-aligned 15-minute bars, stamped at their open
    o15, h15, l15, c15 = (b[x].to_numpy(float) for x in ("open", "high", "low", "close"))
    bull, bear, plo, phi = tt.cisd(o15, h15, l15, c15)  # on the continuous 15-minute series
    i_first, i_last = b.i_first.to_numpy(), b.i_last.to_numpy()
    out = []
    for d, day in ctx.days.iterrows():
        side = int(B.bias[d])
        if side == 0:
            continue
        for pb, gb, tb in BLOCKS:
            prev, gate = _candle(ctx, d, *pb), _candle(ctx, d, *gb)
            if prev is None or gate is None:
                continue
            c2b, c2s = tt.closure2(np.array([prev[0], gate[0]]), np.array([prev[1], gate[1]]),
                                   np.array([prev[2], gate[2]]))
            if not (c2b[1] if side > 0 else c2s[1]):
                continue
            lo, hi = ctx.span(d, *tb)                   # 1-minute bars of the traded 4-hour candle
            if hi <= lo:
                continue
            a, z = np.searchsorted(i_first, lo), np.searchsorted(i_first, hi)   # 15m bars that open inside it
            sig = (bull if side > 0 else bear)[a:z]
            if not sig.any():
                continue
            j = a + int(sig.argmax())                   # the first CISD in the bias direction
            entry = c15[j]
            stop = plo[j] - T if side > 0 else phi[j] + T
            target = core.tick_round(entry + side * k * abs(entry - stop))
            out.append(dict(i=int(i_last[j]), side=side, etype="close", stop=float(stop), target=float(target),
                            exit_i=int(min(hi - 1, day.i_end)),
                            tag=("L" if side > 0 else "S") + f"{tb[0] // 60:02d}"))
    return out


def trades(ctx, **p):
    return core.run_orders(ctx, orders(ctx, **p))       # one order per 4-hour candle, one position at a time
