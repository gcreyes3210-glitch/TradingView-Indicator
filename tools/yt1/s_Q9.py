#!/usr/bin/env python3
"""Q9 - the rest of the day predicts the last half-hour (N02, Baltussen, Da, Lammers, Martens).  YT11_SPEC.md, Part 4.

Spec: at the close of the 15:29 bar: long if the close is above the previous regular session's close, short if
below. Exit at the flat bar (15:59). Not on early-close days. No stop: R unit = 0.1 x daily ATR. One trade a day.
Neighbours: decided at 15:00; at 15:45. Reported `big` = only when the move from the previous close is at least
0.5 x ATR.

Readings (all fixed before the first run, see notes/Q9.md):
  * previous regular session's close = the day table's `pdc` (the previous cash day's last 09:30-16:00 close).
  * "decided at 15:00" / "at 15:45" = at the close of the 14:59 / 15:44 bar, as the base's 15:30 decision is the
    close of the 15:29 bar.
  * a close equal to the previous close is no trade; a day whose decision minute has no bar is no trade.
  * ATR = the day table's `atr` (daily ATR(14) through the previous trading day).
"""
import core

ID = "Q9"
NAME = "Rest of the day (previous close -> 15:30) predicts the last half-hour (N02)"
VARIANTS = {
    "base": dict(bar="15:29"),
    "nb1": dict(bar="14:59"),
    "nb2": dict(bar="15:44"),
    "big": dict(bar="15:29", min_move_atr=0.5),
}


def orders(ctx, bar="15:29", min_move_atr=0.0):
    C = ctx.C
    out = []
    for d, day in ctx.days.iterrows():
        if day.early or not (day.pdc == day.pdc) or not (day.atr == day.atr):
            continue
        i = ctx.idx(d, bar)
        if i is None:
            continue
        move = C[i] - day.pdc
        if move == 0 or abs(move) < min_move_atr * day.atr:
            continue
        side = 1 if move > 0 else -1
        out.append(dict(i=int(i), side=side, etype="close", exit_i=int(day.i_end), r_pts=0.1 * float(day.atr),
                        tag="L" if side > 0 else "S"))
    return out


def trades(ctx, **p):
    return core.run_orders(ctx, orders(ctx, **p), one_at_a_time=True)
