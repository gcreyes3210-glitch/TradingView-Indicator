#!/usr/bin/env python3
"""G2 - TTrades: candle 4 continuation (YT4_SPEC.md, Part 2).

Rule (long; short is the mirror):
  daily gate   candle 2 is a swing low (lower low than the candle before it, not undercut by candle 1) and candle 1
               closed above candle 2's body  = tt.closure3 on the tt.daily candles, read at candle 1.
  EQ           midpoint of candle 1's high and low.
  void         once price trades below EQ after 18:00 (any 1-minute low < EQ from the first bar of the trading day
               through the decision bar).
  trigger      the first 3-minute bullish CISD of the morning (bar closing after 08:30 and by 11:00) whose protected
               low is at or above EQ. Entry at that bar's close, stop 1 tick beyond the protected low, target 2R,
               flat bar, one trade a day.
  neighbours   5-minute and 1-minute trigger bars.

Readings (all fixed before the first run; listed in notes/G2.md):
  * the direction comes from the daily gate alone; the spec does not say "bias required" for G2, so tt.bias is not
    consulted.
  * no gate across a contract roll: a day is skipped when any of the three daily candles the gate reads, or the
    trading day's own candle, is flagged `roll` in tt.daily (what tt.bias does for its two candles).
  * the CISD is taken on the continuous N-minute series (tt.cisd over all bars), so the run of down-close candles it
    closes through may have started before 08:30; only the CISD bar itself has to close in the morning.
  * an N-minute bar is acted on at the close of its last 1-minute bar (i_last).
"""
import numpy as np
import core
import tt

ID = "G2"
NAME = "TTrades candle 4 continuation (daily candle 3 closure, EQ held, morning CISD)"
VARIANTS = {
    "base": dict(tf=3),
    "nb1": dict(tf=5),
    "nb2": dict(tf=1),
}
K_R = 2.0
MORNING = ("08:30", "11:00")          # signal bars closing after 08:30 and by 11:00


def _nbars(ctx, tf):
    """tf-minute bars of the continuous series with tt.cisd on them (cached on the context)."""
    cache = ctx.__dict__.setdefault("_g2_bars", {})
    if tf not in cache:
        b = ctx.bars(tf)
        o, h, l, c = (b[k].to_numpy(float) for k in ("open", "high", "low", "close"))
        bull, bear, plo, phi = tt.cisd(o, h, l, c)
        cache[tf] = dict(c=c, bull=bull, bear=bear, plo=plo, phi=phi,
                         i_first=b.i_first.to_numpy(), i_last=b.i_last.to_numpy())
    return cache[tf]


def gate(ctx):
    """Per cash day: (side, EQ, candle-1 high, candle-1 low) of the daily gate, side 0 = no gate."""
    D = tt.daily(ctx)
    idx = D.index
    o, h, l, c = (D[k].to_numpy(float) for k in ("open", "high", "low", "close"))
    roll = D.roll.to_numpy(bool)
    c3_bull, c3_bear = tt.closure3(o, h, l, c)
    out = {}
    for d in ctx.days.index:
        p = idx.searchsorted(d, "left")              # candles strictly before trading date d (as tt.bias)
        if p < 3:
            continue
        if roll[p - 1] or roll[p - 2] or roll[p - 3] or (p < len(idx) and idx[p] == d and roll[p]):
            continue
        side = 1 if c3_bull[p - 1] else -1 if c3_bear[p - 1] else 0
        if side:
            out[d] = (side, (h[p - 1] + l[p - 1]) / 2.0, h[p - 1], l[p - 1])
    return out


def orders(ctx, tf=3):
    X = _nbars(ctx, tf)
    c, i_first, i_last = X["c"], X["i_first"], X["i_last"]
    G = gate(ctx)
    T = core.TICK
    out = []
    for d, day in ctx.days.iterrows():
        if d not in G:
            continue
        side, eq, _, _ = G[d]
        lo, hi = ctx.span(d, *MORNING)
        if hi <= lo:
            continue
        k0 = int(np.searchsorted(i_first, lo, "left"))      # bars opening at or after 08:30 ...
        k1 = int(np.searchsorted(i_last, hi, "left"))       # ... whose last minute is 10:59 or earlier
        i18 = int(np.searchsorted(ctx.tdate, np.datetime64(d, "D"), "left"))   # first bar of the trading day (18:00)
        sig = X["bull"] if side > 0 else X["bear"]
        for k in range(k0, k1):
            if not sig[k]:
                continue
            i = int(i_last[k])
            if side > 0:
                if ctx.L[i18:i + 1].min() < eq:
                    break                                    # void: price has traded below EQ since 18:00
                if X["plo"][k] < eq:
                    continue
                stop = X["plo"][k] - T
            else:
                if ctx.H[i18:i + 1].max() > eq:
                    break
                if X["phi"][k] > eq:
                    continue
                stop = X["phi"][k] + T
            entry = c[k]
            target = core.tick_round(entry + side * K_R * abs(entry - stop))
            out.append(dict(i=i, side=side, etype="close", stop=float(stop), target=float(target),
                            exit_i=int(day.i_end), tag=f"{'L' if side > 0 else 'S'}|{tf}m|eq{eq:.3f}"))
            break
    return out


def trades(ctx, **p):
    return core.run_orders(ctx, orders(ctx, **p), max_per_day=1)
