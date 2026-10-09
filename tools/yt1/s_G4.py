#!/usr/bin/env python3
"""G4 - TTrades: Fractal Model day trade (YT4_SPEC.md, Part 2).

Rule (long; short is the mirror):
  day          tt.bias required (bullish -> long).
  hourly gate  the first clock-hour candle opening 06:00 ... 09:00 that is a bullish candle 2 or candle 3 closure
               (tt.closure2 / tt.closure3 on the continuous 60-minute series) with its low inside candle 1's range,
               and on `cont` days at or above EQ (midpoint of candle 1's high and low).
  entry        after that hour closes: the first 5-minute bullish CISD confirms; entry at the close of the second;
               bars closing by 11:30. Stop 1 tick beyond the protected low of the bar entered on, target 2R,
               flat bar, one trade a day.
  neighbours   targets 1.5R and 3R (the default).
  reported     first  = entry at the close of the first CISD
               retest = limit at the opening price the second CISD closed through, resting 30 minutes.

Readings (all fixed before the first run; listed in notes/G4.md):
  * "the first candle that is ..." = the first of the four candles that meets every condition (closure, low inside
    candle 1's range, EQ on cont days); a closure that fails the location test is passed over.
  * "inside candle 1's range" includes the edges (l1 <= low <= h1).
  * window: 5-minute bars that open at or after the gate hour's end and close by 11:30. The 08:30 start of "the
    morning" is not applied: the rule names its own window and does not use the word.
  * nothing cancels the sequence between the first and the second CISD.
  * retest: the limit price is the opening price of the first candle of the run of down-close candles the second
    CISD closed through. tt.cisd does not return that price, so _ref_open() below walks back to the start of that run
    (and asserts that the low from there to the CISD bar equals tt.cisd's protected low). The order rests on the 30
    one-minute bars after the CISD bar; the 2R target is measured from the limit price; no fill = no trade.
"""
import numpy as np
import pandas as pd
import core
import tt

ID = "G4"
NAME = "TTrades Fractal Model day trade (bias, hourly closure in candle 1's range, second 5m CISD)"
VARIANTS = {
    "base": dict(k=2.0, entry="second"),
    "nb1": dict(k=1.5, entry="second"),
    "nb2": dict(k=3.0, entry="second"),
    "first": dict(k=2.0, entry="first"),
    "retest": dict(k=2.0, entry="retest"),
}
TF = 5
GATE_HOURS = (360, 420, 480, 540)      # clock-hour candles opening 06:00, 07:00, 08:00, 09:00
LAST_CLOSE = "11:30"
REST_MIN = 30


def _nbars(ctx, tf):
    cache = ctx.__dict__.setdefault("_g4_bars", {})
    if tf not in cache:
        b = ctx.bars(tf)
        o, h, l, c = (b[k].to_numpy(float) for k in ("open", "high", "low", "close"))
        bull, bear, plo, phi = tt.cisd(o, h, l, c)
        cache[tf] = dict(o=o, h=h, l=l, c=c, bull=bull, bear=bear, plo=plo, phi=phi, index=b.index,
                         i_first=b.i_first.to_numpy(), i_last=b.i_last.to_numpy())
    return cache[tf]


def _hours(ctx):
    if getattr(ctx, "_g4_hours", None) is None:
        hb = ctx.bars(60)
        o, h, l, c = (hb[k].to_numpy(float) for k in ("open", "high", "low", "close"))
        c2b, c2s = tt.closure2(h, l, c)
        c3b, c3s = tt.closure3(o, h, l, c)
        ctx._g4_hours = dict(h=h, l=l, c2b=c2b, c2s=c2s, c3b=c3b, c3s=c3s,
                             day=hb.index.tz_localize(None).normalize(),
                             tod=(hb.index.hour * 60 + hb.index.minute).to_numpy())
    return ctx._g4_hours


def _ref_open(X, k, side):
    """Opening price of the first candle of the latest run of down-close (long) / up-close (short) candles before the
    CISD bar k: the price that CISD closed through."""
    o, c = X["o"], X["c"]
    j = k - 1
    while j >= 0 and not side * (c[j] - o[j]) < 0:           # back to the latest opposing-close candle
        j -= 1
    assert j >= 0
    while j > 0 and side * (c[j - 1] - o[j - 1]) < 0:        # back to the first candle of that run
        j -= 1
    if side > 0:
        assert c[k] > o[j] and X["l"][j:k + 1].min() == X["plo"][k], "reference run does not match tt.cisd"
    else:
        assert c[k] < o[j] and X["h"][j:k + 1].max() == X["phi"][k], "reference run does not match tt.cisd"
    return float(o[j])


def gate_hour(ctx, d, b):
    """Index (in ctx.bars(60)) of the day's gate candle and the kind of closure, or (None, '')."""
    Hh = _hours(ctx)
    side = int(b.bias)
    eq = (float(b.h1) + float(b.l1)) / 2.0
    a0, a1 = int(Hh["day"].searchsorted(d, "left")), int(Hh["day"].searchsorted(d, "right"))
    for g in range(a0, a1):
        if Hh["tod"][g] not in GATE_HOURS:
            continue
        if side > 0:
            clos, px = (Hh["c2b"][g], Hh["c3b"][g]), Hh["l"][g]
        else:
            clos, px = (Hh["c2s"][g], Hh["c3s"][g]), Hh["h"][g]
        if not (clos[0] or clos[1]):
            continue
        if not (float(b.l1) <= px <= float(b.h1)):
            continue                                         # the candle's low (high) is outside candle 1's range
        if b.kind == "cont" and side * (px - eq) < 0:
            continue                                         # cont day: not in the defended half
        return g, "c2" if clos[0] else "c3"
    return None, ""


def orders(ctx, k=2.0, entry="second"):
    assert entry in ("second", "first", "retest")
    X = _nbars(ctx, TF)
    c, i_first, i_last = X["c"], X["i_first"], X["i_last"]
    B = tt.bias(ctx)
    Hh = _hours(ctx)
    T = core.TICK
    need = 1 if entry == "first" else 2
    out = []
    for d, day in ctx.days.iterrows():
        b = B.loc[d]
        side = int(b.bias)
        if side == 0:
            continue
        g, why = gate_hour(ctx, d, b)
        if g is None:
            continue
        t_gate = int(Hh["tod"][g]) + 60                      # the gate hour's end
        lo, hi = ctx.span(d, t_gate, LAST_CLOSE)
        if hi <= lo:
            continue
        k0 = int(np.searchsorted(i_first, lo, "left"))       # 5-minute bars opening at or after the hour's end ...
        k1 = int(np.searchsorted(i_last, hi, "left"))        # ... whose last minute is 11:29 or earlier
        sig = X["bull"] if side > 0 else X["bear"]
        hits = [kk for kk in range(k0, k1) if sig[kk]][:need]
        if len(hits) < need:
            continue
        kk = hits[-1]
        i = int(i_last[kk])
        stop = X["plo"][kk] - T if side > 0 else X["phi"][kk] + T
        tag = f"{'L' if side > 0 else 'S'}|{b.kind}|{why}@{int(Hh['tod'][g]) // 60:02d}:00"
        if entry == "retest":
            price = _ref_open(X, kk, side)
            t_end = X["index"][kk] + pd.Timedelta(minutes=TF)                    # end of the CISD bar
            expire = int(ctx.ts.searchsorted(t_end + pd.Timedelta(minutes=REST_MIN), "left")) - 1
            target = core.tick_round(price + side * k * abs(price - stop))
            out.append(dict(i=i, side=side, etype="limit", price=price, expire=expire, stop=float(stop),
                            target=float(target), exit_i=int(day.i_end), tag=tag))
        else:
            px = c[kk]
            target = core.tick_round(px + side * k * abs(px - stop))
            out.append(dict(i=i, side=side, etype="close", stop=float(stop), target=float(target),
                            exit_i=int(day.i_end), tag=tag))
    return out


def trades(ctx, **p):
    return core.run_orders(ctx, orders(ctx, **p), max_per_day=1)
