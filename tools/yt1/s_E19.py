#!/usr/bin/env python3
"""E19 - Turnaround Tuesday, the cash session only (Quantified Strategies). YT1_SPEC.md, Family E.

Spec text:
  Monday's RTH close below Friday's -> long Tuesday's 09:30 open to the flat bar. No stop.
  Neighbours: Monday's close below Friday's low; any down day -> next day.

Readings added to the spec text (all fixed before the first run; see notes/E19.md):
  * days are the rows of the harness day table (`ctx.days`: every date with a cash session starting at 09:30).
    "Tuesday" = a row dated on a Tuesday; "Monday" = the row before it, which must be the Monday of the day before
    (no Monday session -> no trade); "Friday" = the row before that Monday: the Friday, or, when that Friday had no
    cash session, the last cash day before it (the daily-bar test in the video compares Monday's close with the
    previous close).
  * RTH close / low of a day = `rth_c` / `rth_l` of its row (09:30-16:00, or to the halt on a short day); "below" is
    strict. Both are complete before the trade day's 09:30.
  * nb2, "any down day -> next day": every cash day whose previous cash day closed below the cash day before it.
  * entry at the 09:30 bar's open: the order is signalled at the close of the last 1-minute bar before 09:30
    (etype 'open'). No stop, no target, exit at the flat bar. R unit = 0.1 x the day's daily ATR(14) (common rule).
  * the common rule drops contract-roll days only. A trade day that FOLLOWS a roll day compares two closes of
    different contracts; it is kept as the text has it and its tag carries "|xroll" so it can be split off.
Tags: the trade day's weekday, then "|xroll" (see above), "|pdEarly" (the down day was a short session) and
"|noFri" (base / nb1: the day before Monday was not a Friday) where they apply.
"""
import numpy as np
import pandas as pd
import core

ID = "E19"
NAME = "Turnaround Tuesday, cash session: down Monday -> long Tuesday 09:30 open to the flat bar"
VARIANTS = {
    "base": dict(mode="mon"),
    "nb1": dict(mode="mon_low"),
    "nb2": dict(mode="any"),
}
_WD = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


def orders(ctx, mode="mon"):
    assert mode in ("mon", "mon_low", "any")
    D = ctx.days
    idx = D.index
    c, l = D.rth_c.to_numpy(float), D.rth_l.to_numpy(float)
    dow, roll, early = D.dow.to_numpy(), D.roll.to_numpy(bool), D.early.to_numpy(bool)
    i_open, i_end, atr = D.i_open.to_numpy(), D.i_end.to_numpy(), D.atr.to_numpy(float)
    out = []
    for n in range(2, len(D)):
        p1, p2 = n - 1, n - 2                 # the down-day candidate and the day it is compared with: both complete
        if mode in ("mon", "mon_low"):
            if dow[n] != 1 or dow[p1] != 0 or (idx[n] - idx[p1]).days != 1:
                continue
        ref = l[p2] if mode == "mon_low" else c[p2]
        if not (c[p1] < ref):
            continue
        if not atr[n] == atr[n]:
            continue                          # no daily ATR: not traded (run_orders drops these days as well)
        i = int(i_open[n]) - 1                # the last 1-minute bar before 09:30
        if i < 0 or ctx.cdate[i] != np.datetime64(idx[n], "D") or ctx.tod[i] >= 570:
            continue                          # no bar earlier on the trade date to signal from
        tag = _WD[dow[n]]
        if roll[p1]:
            tag += "|xroll"
        if early[p1]:
            tag += "|pdEarly"
        if mode != "any" and dow[p2] != 4:
            tag += "|noFri"
        out.append(dict(i=i, side=1, etype="open", exit_i=int(i_end[n]), r_pts=0.1 * float(atr[n]), tag=tag))
    return out


def trades(ctx, **p):
    return core.run_orders(ctx, orders(ctx, **p), max_per_day=1)
