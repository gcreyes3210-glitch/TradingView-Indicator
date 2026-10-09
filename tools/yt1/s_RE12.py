#!/usr/bin/env python3
"""RE12 - E12 Larry Williams Oops, second independent coding from the spec text.

Spec (YT1_SPEC.md, E12): long only, end-of-day exit. The 09:30 open is below the previous RTH low -> buy stop at that
low from the 09:30 bar's close to 15:00. No stop. Neighbours: gap >= 0.05, >= 0.10 x daily ATR. Reported: `both` with
the short mirror.

Coded as: signal bar = the 09:30 bar (the condition needs only its open and the previous cash day's RTH low, both
known at its close). One buy stop at the previous RTH low resting on the bars 09:31 .. 14:59; exit at the flat bar.
gap = previous RTH low - 09:30 open; base needs gap > 0, the neighbours gap >= min_gap x daily ATR(14).
R unit = 0.1 x daily ATR(14). `both` adds the mirror: 09:30 open above the previous RTH high -> sell stop at that high.
"""
import core

ID = "RE12"
NAME = "Larry Williams Oops (E12, second coder)"
VARIANTS = {
    "base": dict(min_gap=0.0),
    "nb1": dict(min_gap=0.05),
    "nb2": dict(min_gap=0.10),
    "both": dict(min_gap=0.0, both=True),
}


def orders(ctx, min_gap=0.0, both=False):
    out = []
    for d, day in ctx.days.iterrows():
        atr = float(day.atr)
        if not atr == atr:
            continue                                  # no daily ATR: no R unit, and the day is not traded
        o = float(day.o930)
        side = level = None
        if day.pdl == day.pdl and o < day.pdl and (day.pdl - o) >= min_gap * atr:
            side, level = 1, float(day.pdl)
        elif both and day.pdh == day.pdh and o > day.pdh and (o - day.pdh) >= min_gap * atr:
            side, level = -1, float(day.pdh)
        if side is None:
            continue
        lo, hi = ctx.span(d, "09:31", "15:00")        # the order rests on bars after the 09:30 bar and before 15:00
        if hi <= lo:
            continue
        out.append(dict(i=int(day.i_open), side=side, etype="stop", price=level, expire=hi - 1,
                        exit_i=int(day.i_end), r_pts=0.1 * atr, tag="L" if side > 0 else "S"))
    return out


def trades(ctx, **p):
    return core.run_orders(ctx, orders(ctx, **p), max_per_day=1)
