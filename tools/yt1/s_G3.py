#!/usr/bin/env python3
"""G3 - TTrades: EQ continuation day (YT4_SPEC.md, Part 2).

Rule (long; short is the mirror):
  day          tt.bias kind `cont` only (candle 1 closed above candle 2's high -> long).
  EQ           midpoint of candle 1's high and low.
  respect (R)  no clock-hour candle since 18:00 has closed below EQ.
  trigger      the first 5-minute bullish CISD of the morning (bar closing after 08:30 and by 11:00) that closes
               above EQ. Entry at that bar's close, stop 1 tick beyond the protected low, target 2R, flat bar,
               one trade a day.
  neighbours   targets 1.5R and 3R (the default).
  reported     pdh = target candle 1's high instead of 2R, no trade if it is nearer than 1R.

Readings (all fixed before the first run; listed in notes/G3.md):
  * "clock-hour candle since 18:00" = the 60-minute buckets of the trading day (18:00 the evening before onwards)
    whose hour has ended by the end of the signal bar; closed below = close < EQ (strict).
  * "closes above EQ" = close > EQ (strict). A morning CISD that closes at or below EQ is passed over; the next one
    is looked at. Respect is permanent: once an hour has closed below EQ the day is over.
  * pdh: the trigger bar is unchanged; if candle 1's high is nearer to the entry than 1R (|entry - stop|, before
    slippage) there is no trade that day (a later CISD is not taken instead).
  * the CISD is taken on the continuous 5-minute series; a bar is acted on at the close of its last 1-minute bar.
"""
import numpy as np
import pandas as pd
import core
import tt

ID = "G3"
NAME = "TTrades EQ continuation day (cont bias, hourly closes respect EQ, morning 5m CISD above EQ)"
VARIANTS = {
    "base": dict(k=2.0),
    "nb1": dict(k=1.5),
    "nb2": dict(k=3.0),
    "pdh": dict(k=2.0, pdh=True),
}
TF = 5
MORNING = ("08:30", "11:00")


def _nbars(ctx, tf):
    cache = ctx.__dict__.setdefault("_g3_bars", {})
    if tf not in cache:
        b = ctx.bars(tf)
        o, h, l, c = (b[k].to_numpy(float) for k in ("open", "high", "low", "close"))
        bull, bear, plo, phi = tt.cisd(o, h, l, c)
        cache[tf] = dict(c=c, bull=bull, bear=bear, plo=plo, phi=phi, index=b.index,
                         i_first=b.i_first.to_numpy(), i_last=b.i_last.to_numpy())
    return cache[tf]


def orders(ctx, k=2.0, pdh=False):
    X = _nbars(ctx, TF)
    c, i_first, i_last = X["c"], X["i_first"], X["i_last"]
    B = tt.bias(ctx)
    hb = ctx.bars(60)                                        # clock-hour candles
    h_close, h_first = hb.close.to_numpy(float), hb.i_first.to_numpy()
    h_end = hb.index + pd.Timedelta(minutes=60)              # the moment each hour is complete
    T = core.TICK
    out = []
    for d, day in ctx.days.iterrows():
        b = B.loc[d]
        side = int(b.bias)
        if side == 0 or b.kind != "cont":
            continue
        eq = (float(b.h1) + float(b.l1)) / 2.0
        lo, hi = ctx.span(d, *MORNING)
        if hi <= lo:
            continue
        k0 = int(np.searchsorted(i_first, lo, "left"))
        k1 = int(np.searchsorted(i_last, hi, "left"))
        i18 = int(np.searchsorted(ctx.tdate, np.datetime64(d, "D"), "left"))   # first bar of the trading day (18:00)
        g0 = int(np.searchsorted(h_first, i18, "left"))      # first hour candle of the trading day
        sig = X["bull"] if side > 0 else X["bear"]
        for kk in range(k0, k1):
            if not sig[kk]:
                continue
            i = int(i_last[kk])
            t_end = X["index"][kk] + pd.Timedelta(minutes=TF)                   # end of the signal bar
            g1 = int(h_end.searchsorted(t_end, "right"))     # hour candles that have ended by then
            hc = h_close[g0:g1]
            if (hc < eq).any() if side > 0 else (hc > eq).any():
                break                                        # an hour has closed beyond EQ: no respect, day over
            entry = c[kk]
            if side * (entry - eq) <= 0:
                continue                                     # this CISD does not close above (below) EQ
            stop = X["plo"][kk] - T if side > 0 else X["phi"][kk] + T
            risk = abs(entry - stop)
            if pdh:
                target = float(b.h1) if side > 0 else float(b.l1)
                if side * (target - entry) < risk:
                    break                                    # candle 1's high is nearer than 1R: no trade
            else:
                target = core.tick_round(entry + side * k * risk)
            out.append(dict(i=i, side=side, etype="close", stop=float(stop), target=float(target),
                            exit_i=int(day.i_end), tag=f"{'L' if side > 0 else 'S'}|eq{eq:.3f}"))
            break
    return out


def trades(ctx, **p):
    return core.run_orders(ctx, orders(ctx, **p), max_per_day=1)
