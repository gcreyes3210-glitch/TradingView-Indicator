#!/usr/bin/env python3
"""Q8 - VWAP 2-sd reversion scalp with a tick bracket (M12b, El Trader Financiado).  YT11_SPEC.md, Part 4.

Spec: 1-minute MNQ bars, signal bars stamped 11:00 .. 13:59. A bar closes at or below VWAP - 2 x VWAP sd and above
its open: buy at the close. Stop 8 ticks below the bar's low. Target 20 ticks above the entry price, or VWAP at the
signal if nearer. Short mirrored: a close at or above VWAP + 2 x VWAP sd and below its open; stop 8 ticks above the
bar's high; target 20 ticks below the entry price, or VWAP if nearer. One position at a time; every signal that
comes while flat is taken. Neighbours: 6-tick stop with a 10-tick target; 2.5 sd. Reported x4 = stop 32 ticks beyond
the bar's extreme, target 80 ticks.

VWAP / VWAP sd: the spec's shared definitions (anchored at 09:30, sum(hlc3 x volume) / sum(volume) on 1-minute bars
through the bar just closed; sd = sqrt(sum(volume x hlc3^2) / sum(volume) - VWAP^2)) = ind.session_vwap restarted at
each day's 09:30 bar.

Readings (all fixed before the first run, see notes/Q8.md):
  * entry price = the entry reference price = the signal bar's close; the target is a fixed price set at entry.
  * "VWAP at the signal if nearer": when the VWAP of the signal bar is nearer to the close than the tick target, the
    target is that VWAP put on the tick grid (nearest tick). This holds in every variant, x4 included.
  * an order whose target, after rounding, is not beyond the signal close is not a bracket and is not sent.
"""
import numpy as np
import core
import ind

ID = "Q8"
NAME = "VWAP 2-sd reversion scalp, tick bracket, 11:00-13:59 (M12b)"
VARIANTS = {
    "base": dict(sd_k=2.0, stop_ticks=8, target_ticks=20),
    "nb1": dict(sd_k=2.0, stop_ticks=6, target_ticks=10),
    "nb2": dict(sd_k=2.5, stop_ticks=8, target_ticks=20),
    "x4": dict(sd_k=2.0, stop_ticks=32, target_ticks=80),
}

ANCHOR, WIN_LO, WIN_HI = "09:30", "11:00", "14:00"      # signal bars 11:00 .. 13:59


def session_vwap(ctx, d, day):
    """(lo, hi, vwap, sd) for the bars 09:30 .. 13:59 of cash day d; vwap[m] / sd[m] are the values through bar
    lo + m. None when the slice does not start at the day's 09:30 bar."""
    lo, hi = ctx.span(d, ANCHOR, WIN_HI)
    if hi <= lo or lo != int(day.i_open):
        return None
    new = np.zeros(hi - lo, bool)
    new[0] = True
    vw, sd = ind.session_vwap(ctx.H[lo:hi], ctx.L[lo:hi], ctx.C[lo:hi], ctx.V[lo:hi], new)
    return lo, hi, vw, sd


def orders(ctx, sd_k=2.0, stop_ticks=8, target_ticks=20):
    O, H, L, C, tod = ctx.O, ctx.H, ctx.L, ctx.C, ctx.tod
    T = core.TICK
    w0, w1 = core.hhmm(WIN_LO), core.hhmm(WIN_HI)
    out = []
    for d, day in ctx.days.iterrows():
        s = session_vwap(ctx, d, day)
        if s is None:
            continue
        lo, hi, vw, sd = s
        for k in range(lo, hi):
            if not (w0 <= tod[k] < w1):
                continue
            v, e = vw[k - lo], sd[k - lo]
            if not (v == v and e == e):
                continue
            c = C[k]
            if c <= v - sd_k * e and c > O[k]:
                side, stop, cap = 1, L[k] - stop_ticks * T, c + target_ticks * T
                target = core.tick_round(v, "nearest") if v < cap else cap
            elif c >= v + sd_k * e and c < O[k]:
                side, stop, cap = -1, H[k] + stop_ticks * T, c - target_ticks * T
                target = core.tick_round(v, "nearest") if v > cap else cap
            else:
                continue
            if not side * (target - c) > 0:
                continue
            out.append(dict(i=int(k), side=side, etype="close", stop=float(stop), target=float(target),
                            exit_i=int(day.i_end), tag="L" if side > 0 else "S"))
    return out


def trades(ctx, **p):
    return core.run_orders(ctx, orders(ctx, **p), one_at_a_time=True)
