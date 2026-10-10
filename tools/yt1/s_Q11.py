#!/usr/bin/env python3
"""Q11 - the lunch pattern (N11, Quantpedia, on SPY).  YT11_SPEC.md, Part 4.

Spec: short at the close of the 10:59 bar, out at the close of the 11:59 bar; long there, out at the close of the
13:59 bar. Two trades a day, scored together. No stop: R unit = 0.1 x daily ATR. Neighbours: the long leg ending
12:59; the short leg starting 11:30. Reported: each leg alone (`short`, `long`).

Readings (all fixed before the first run, see notes/Q11.md):
  * "the long leg ending 12:59" = out at the close of the 12:59 bar; "the short leg starting 11:30" = short at the
    close of the 11:29 bar (the clock time 11:30, as the base's 11:00 start is the close of the 10:59 bar).
  * early-close days are traded (the entry does not exclude them); an exit time after the day's flat bar becomes the
    flat bar (common rule "Flat").
  * a leg whose entry minute or exit minute has no bar is no trade; the other leg is still taken.
  * the two legs are back to back (the short leg's exit bar is the long leg's signal bar), so the legs are run with
    run_orders(one_at_a_time=False): with True the harness drops an order signalled on the previous trade's exit
    bar. The positions never overlap: the short is closed at the same close the long is opened at.
"""
import core

ID = "Q11"
NAME = "Lunch pattern: short 11:00 -> 12:00, long 12:00 -> 14:00 (N11)"
VARIANTS = {
    "base": dict(short_in="10:59", short_out="11:59", long_in="11:59", long_out="13:59"),
    "nb1": dict(short_in="10:59", short_out="11:59", long_in="11:59", long_out="12:59"),
    "nb2": dict(short_in="11:29", short_out="11:59", long_in="11:59", long_out="13:59"),
    "short": dict(short_in="10:59", short_out="11:59", long_in="11:59", long_out="13:59", legs="short"),
    "long": dict(short_in="10:59", short_out="11:59", long_in="11:59", long_out="13:59", legs="long"),
}


def _leg(ctx, d, day, side, t_in, t_out):
    i = ctx.idx(d, t_in)
    # an exit time past the flat bar (early-close days) is the flat bar
    x = int(day.i_end) if core.hhmm(t_out) > int(day.end_tod) else ctx.idx(d, t_out)
    if i is None or x is None or i >= x:
        return None
    return dict(i=int(i), side=side, etype="close", exit_i=int(x), r_pts=0.1 * float(day.atr),
                tag="short leg" if side < 0 else "long leg")


def orders(ctx, short_in="10:59", short_out="11:59", long_in="11:59", long_out="13:59", legs="both"):
    out = []
    for d, day in ctx.days.iterrows():
        if not (day.atr == day.atr):
            continue
        if legs in ("both", "short"):
            o = _leg(ctx, d, day, -1, short_in, short_out)
            if o:
                out.append(o)
        if legs in ("both", "long"):
            o = _leg(ctx, d, day, 1, long_in, long_out)
            if o:
                out.append(o)
    return out


def trades(ctx, **p):
    return core.run_orders(ctx, orders(ctx, **p), one_at_a_time=False)
