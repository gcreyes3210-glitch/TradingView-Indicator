#!/usr/bin/env python3
"""G6 - TTrades scalping model (YT4_SPEC.md, Part 2).

Bias required (tt.bias). Gate: a clock-hour candle opening 08:00 ... 14:00 that is a candle 2 or candle 3 closure in
the bias direction (tt.closure2 / tt.closure3 on the hourly candles). In the next hour: one of its first two
15-minute candles (hh:00, hh:15) is a candle 2 closure in that direction; then the first 1-minute CISD in that
direction (tt.cisd on the continuous 1-minute series) on a bar after that 15-minute candle has closed, from 09:30 on.
Entry at the CISD bar's close, stop 1 tick beyond the protected low / high, target k R (2; neighbours 1.5 and 3),
exit at the hour's last bar or the flat bar, whichever comes first. One trade per hour, one position at a time.

Readings (R), all fixed before the first run - see notes/G6.md.
"""
import numpy as np
import core
import tt

ID = "G6"
NAME = "TTrades scalping model (1H closure, 15m candle 2 closure, 1m CISD in the next hour)"
VARIANTS = {
    "base": dict(k=2.0),
    "nb1": dict(k=1.5),
    "nb2": dict(k=3.0),
}
T = core.TICK


def _candle(ctx, d, m0, m1, need):
    """(open, high, low, close, hi) of the 1-minute bars m0 <= time < m1 on date d (hi = position after its last
    bar), or None when it holds fewer than `need` bars."""
    lo, hi = ctx.span(d, m0, m1)
    if hi - lo < need:
        return None
    return ctx.O[lo], ctx.H[lo:hi].max(), ctx.L[lo:hi].min(), ctx.C[hi - 1], hi


def _arr(cands, f):
    return np.array([c[f] for c in cands], float)


def _closure2(prev, cur, side):
    bull, bear = tt.closure2(_arr((prev, cur), 1), _arr((prev, cur), 2), _arr((prev, cur), 3))
    return bool(bull[1] if side > 0 else bear[1])


def _closure3(c0, c1, c2, side):
    cs = (c0, c1, c2)
    bull, bear = tt.closure3(_arr(cs, 0), _arr(cs, 1), _arr(cs, 2), _arr(cs, 3))
    return bool(bull[2] if side > 0 else bear[2])


def _cisd1(ctx):
    if getattr(ctx, "_g6_cisd", None) is None:          # the same for every variant: computed once per context
        ctx._g6_cisd = tt.cisd(ctx.O, ctx.H, ctx.L, ctx.C)
    return ctx._g6_cisd


def orders(ctx, k=2.0):
    B = tt.bias(ctx)
    bull, bear, plo, phi = _cisd1(ctx)
    C = ctx.C
    out = []
    for d, day in ctx.days.iterrows():
        side = int(B.bias[d])
        if side == 0:
            continue
        i930 = int(day.i_open)
        # hourly candles 06:00 ... 14:00; a candle needs at least half its minutes (YT4_SPEC Part 1)
        hr = {h: _candle(ctx, d, h * 60, h * 60 + 60, 30) for h in range(6, 15)}
        for h in range(8, 15):                          # gate hour opens 08:00 ... 14:00
            c0, c1, c2 = hr[h - 2], hr[h - 1], hr[h]
            if c1 is None or c2 is None:
                continue
            if not (_closure2(c1, c2, side) or (c0 is not None and _closure3(c0, c1, c2, side))):
                continue
            m = (h + 1) * 60                            # the next hour
            q = [_candle(ctx, d, m - 15, m, 1), _candle(ctx, d, m, m + 15, 1), _candle(ctx, d, m + 15, m + 30, 1)]
            start = None
            for a in (1, 2):                            # its first two 15-minute candles, in time order
                if q[a - 1] is not None and q[a] is not None and _closure2(q[a - 1], q[a], side):
                    start = q[a][4]                     # first 1-minute bar after that 15-minute candle has closed
                    break
            if start is None:
                continue
            lo, hi = ctx.span(d, m, m + 60)             # 1-minute bars of the next hour
            s = max(start, i930)                        # from 09:30 on
            if s >= hi:
                continue
            sig = (bull if side > 0 else bear)[s:hi]
            if not sig.any():
                continue
            i = s + int(sig.argmax())                   # the first 1-minute CISD in the bias direction
            entry = C[i]
            stop = plo[i] - T if side > 0 else phi[i] + T
            target = core.tick_round(entry + side * k * abs(entry - stop))
            out.append(dict(i=int(i), side=side, etype="close", stop=float(stop), target=float(target),
                            exit_i=int(min(hi - 1, day.i_end)),
                            tag=("L" if side > 0 else "S") + f"{h + 1:02d}"))
    return out


def trades(ctx, **p):
    return core.run_orders(ctx, orders(ctx, **p))       # one order per hour, one position at a time
