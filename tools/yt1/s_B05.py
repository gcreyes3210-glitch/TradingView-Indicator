#!/usr/bin/env python3
"""B05 - Scarface first-candle break and retest.

Spec (YT1_SPEC.md):
  Range   09:30-09:34. 1-minute bars. The first close outside the range (09:35 or later) sets the side.
  Zone    the last opposite-colour 1-minute bar (09:30 or later) before that breakout bar.
  Entry   limit at the broken range edge, resting from the bar after the breakout to 10:59.
  Stop    beyond (1 tick) the zone bar's extreme; if that is not beyond the entry, the breakout bar's; else no trade.
  Target  2R.  Neighbours 1.5R, 3R.

Readings added (fixed before the first run, see notes/B05.md):
  * opposite colour = close < open before a long breakout, close > open before a short one (a doji has no colour).
  * "beyond the entry" tests the bar's extreme itself against the limit price, strictly (zone low < edge for a long).
  * a day with no opposite-colour bar between 09:30 and the breakout is treated like a zone bar whose extreme is not
    beyond the entry: the breakout bar's extreme is used, else no trade.
  * the entry price for the R target is the limit price (the order is fixed at the breakout bar's close).
"""
import core

ID = "B05"
NAME = "Scarface first-candle break and retest"
VARIANTS = {
    "base": dict(k=2.0),
    "nb1": dict(k=1.5),
    "nb2": dict(k=3.0),
}


def _retest_order(ctx, day, s0, b0, b1, hi_lvl, lo_lvl, k):
    """The day's order, or None. s0 = first bar a zone bar may be (09:30); b0 .. b1 - 1 = bars on which the breakout
    close is looked for; the limit rests to bar b1 - 1 (the last bar at or before 10:59)."""
    O, H, L, C = ctx.O, ctx.H, ctx.L, ctx.C
    T = core.TICK
    for i in range(b0, b1 - 1):                            # a breakout on the last bar leaves no bar to rest on
        side = 1 if C[i] > hi_lvl else -1 if C[i] < lo_lvl else 0
        if not side:
            continue
        entry = hi_lvl if side > 0 else lo_lvl             # the broken edge
        zone = None
        for z in range(i - 1, s0 - 1, -1):                 # last opposite-colour bar before the breakout bar
            if (C[z] < O[z]) if side > 0 else (C[z] > O[z]):
                zone = z
                break
        ext, tag = None, None
        if zone is not None:
            e = L[zone] if side > 0 else H[zone]
            if (e < entry) if side > 0 else (e > entry):
                ext, tag = e, "zone"
        if ext is None:
            e = L[i] if side > 0 else H[i]
            if (e < entry) if side > 0 else (e > entry):
                ext, tag = e, "brk-nozone" if zone is None else "brk-zone-not-beyond"
        if ext is None:
            return None                                    # neither extreme is beyond the entry: no trade
        stop = ext - side * T
        target = core.tick_round(entry + side * k * abs(entry - stop))
        return dict(i=int(i), side=side, etype="limit", price=float(entry), expire=int(b1 - 1), stop=float(stop),
                    target=float(target), exit_i=int(day.i_end), tag=("L " if side > 0 else "S ") + tag)
    return None


def orders(ctx, k=2.0):
    out = []
    for d, day in ctx.days.iterrows():
        r0, r1 = ctx.span(d, "09:30", "09:35")
        if r1 <= r0:
            continue
        rh, rl = ctx.H[r0:r1].max(), ctx.L[r0:r1].min()
        b0, b1 = ctx.span(d, "09:35", "11:00")             # 1-minute bars 09:35 .. 10:59
        o = _retest_order(ctx, day, r0, b0, b1, rh, rl, k)
        if o is not None:
            out.append(o)
    return out


def trades(ctx, **p):
    return core.run_orders(ctx, orders(ctx, **p), max_per_day=1)
