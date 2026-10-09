#!/usr/bin/env python3
"""E05 - NQ Stats ALN sessions (Asia / London pattern, trade toward the London extreme it points to).

Spec text (YT1_SPEC.md, E05):
  Asia 20:00-01:59, London 02:00-07:59. At the 07:59 close: if London's high is above Asia's and London's low is
  inside Asia's range -> long, target 1 tick beyond London's high, stop beyond London's low; the mirror pattern ->
  short. Neighbours: entry at the 08:29 close, at the 09:29 close (no trade if target or stop traded first).

Readings added (fixed before the first run; see notes/E05.md):
  * for cash day D, Asia = 20:00-23:59 on the calendar day before D (Sunday for a Monday) plus 00:00-01:59 on D;
    London = 02:00-07:59 on D. A day on which either session has no bars is skipped.
  * "above" is strict; "inside Asia's range" includes its edges: Asia low <= London low <= Asia high.
    Mirror: London's low below Asia's low and Asia low <= London high <= Asia high -> short, target 1 tick beyond
    London's low, stop 1 tick beyond London's high.
  * the entry is a market order at the close of the bar stamped at the entry minute (no such bar = no trade).
  * neighbours: the pattern is still fixed by London 02:00-07:59; "traded first" = any bar from 08:00 through the
    entry bar itself reached the target price (London high + 1 tick for a long) or the stop price.
"""
import numpy as np
import pandas as pd
import core

ID = "E05"
NAME = "NQ Stats ALN sessions: partial engulf of Asia by London, trade to the London extreme it points to"
VARIANTS = {
    "base": dict(at="07:59"),
    "nb1": dict(at="08:29"),
    "nb2": dict(at="09:29"),
}


def sessions(ctx, d):
    """(asia_lo, asia_hi, london_lo, london_hi) bar positions [lo, hi) for cash day d, or None if either is empty."""
    a0, _ = ctx.span(d - pd.Timedelta(days=1), "20:00", "23:59")   # Asia starts the previous evening
    _, a1 = ctx.span(d, "00:00", "02:00")                          # ... and ends at 01:59
    l0, l1 = ctx.span(d, "02:00", "08:00")
    if a1 <= a0 or l1 <= l0:
        return None
    return a0, a1, l0, l1


def orders(ctx, at="07:59"):
    T = core.TICK
    H, L = ctx.H, ctx.L
    out = []
    for d, day in ctx.days.iterrows():
        i = ctx.idx(d, at)                                      # the entry bar
        if i is None:
            continue
        i = int(i)
        s = sessions(ctx, d)
        if s is None:
            continue
        a0, a1, l0, l1 = s
        assert l1 <= i + 1
        ah, al = float(H[a0:a1].max()), float(L[a0:a1].min())
        lh, ll = float(H[l0:l1].max()), float(L[l0:l1].min())
        if lh > ah and al <= ll <= ah:
            o = dict(side=1, target=lh + T, stop=ll - T, tag="L")
        elif ll < al and al <= lh <= ah:
            o = dict(side=-1, target=ll - T, stop=lh + T, tag="S")
        else:
            continue
        if i >= l1:                                             # a later entry: nothing may have traded first
            hi_, lo_ = float(H[l1:i + 1].max()), float(L[l1:i + 1].min())
            if hi_ >= max(o["target"], o["stop"]) or lo_ <= min(o["target"], o["stop"]):
                continue
        o.update(i=i, etype="close", exit_i=int(day.i_end))
        out.append(o)
    return out


def trades(ctx, **p):
    return core.run_orders(ctx, orders(ctx, **p), max_per_day=1)
