#!/usr/bin/env python3
"""Q1 - VWAP stop-and-reverse (N20, Zarattini and Aziz).

Spec text (YT11_SPEC.md, Part 4, Q1):
  At the close of the 09:30 bar: long if the close is above VWAP, short if below (equal: wait for the first close
  that differs). At every later 1-minute close on the other side of VWAP the position is closed and reversed at that
  close. Flat at the flat bar. Each leg is one trade with its own costs. No stop.
  Neighbours: decisions on 3-minute closes; on 5-minute closes.

Shared definition: VWAP = anchored at 09:30, sum(hlc3 x volume) / sum(volume) on 1-minute bars, through the bar just
closed (ind.session_vwap on the 09:30-15:59 bars, restarted at the first of them each day).

Readings fixed before the first run (see notes/Q1.md):
  * a close equal to VWAP is on neither side: it starts nothing and reverses nothing.
  * each leg is one order: market at the close of its flip bar, exit_i = the next flip bar (the close at which the
    position is reversed) or the flat bar; R unit = 0.1 x that day's daily ATR(14). A flip on the flat bar itself is
    only the exit of the leg before it.
  * neighbours: the decision bars are the 09:30 one-minute bar and then the last 1-minute bar of every 3-minute
    (5-minute) clock bar; VWAP stays the 1-minute VWAP. "Wait for the first close that differs" then means the
    first decision close that differs.
  * the legs are handed to run_orders with one_at_a_time=False: a leg's signal bar IS the previous leg's exit bar,
    which one_at_a_time=True would drop. The legs cannot overlap by construction (asserted in trades()).
"""
import numpy as np
import core
import ind

ID = "Q1"
NAME = "VWAP stop-and-reverse on 1-minute closes (N20)"
VARIANTS = {
    "base": dict(every=1),
    "nb1": dict(every=3),
    "nb2": dict(every=5),
}
OPEN, CLOSE = 9 * 60 + 30, 16 * 60


def _vwap(ctx):
    """09:30-anchored VWAP of hlc3 per 1-minute bar (NaN outside 09:30-15:59)."""
    v = getattr(ctx, "_yt11_vwap", None)
    if v is None:
        m = np.flatnonzero((ctx.tod >= OPEN) & (ctx.tod < CLOSE))
        new = np.r_[True, ctx.cdate[m][1:] != ctx.cdate[m][:-1]]          # the first session bar of each date
        vw, sd = ind.session_vwap(ctx.H[m], ctx.L[m], ctx.C[m], ctx.V[m], new)
        v = (np.full(ctx.n, np.nan), np.full(ctx.n, np.nan))
        v[0][m], v[1][m] = vw, sd
        ctx._yt11_vwap = v
    return v


def orders(ctx, every=1):
    vw, _ = _vwap(ctx)
    with np.errstate(invalid="ignore"):
        s = np.sign(ctx.C - vw)                                           # NaN where there is no VWAP
    s[np.isnan(s)] = 0.0
    dec = None
    if every > 1:
        dec = np.zeros(ctx.n, bool)
        dec[ctx.bars(every).i_last.to_numpy()] = True                     # closes of the N-minute clock bars
    D = ctx.days
    out = []
    for i_open, i_end, atr in zip(D.i_open.to_numpy(), D.i_end.to_numpy(), D.atr.to_numpy(float)):
        k = np.arange(i_open, i_end)                                      # decisions before the flat bar
        if dec is not None:
            keep = dec[k]
            keep[0] = True                                                # the 09:30 one-minute bar
            k = k[keep]
        k = k[s[k] != 0]
        if len(k) == 0:
            continue
        sk = s[k]
        flip = np.r_[True, sk[1:] != sk[:-1]]                             # the first side, then every change of side
        f, fs = k[flip], sk[flip]
        ends = np.r_[f[1:], i_end]
        r_pts = 0.1 * atr if atr == atr else None
        for i, side, x in zip(f.tolist(), fs.tolist(), ends.tolist()):
            out.append(dict(i=int(i), side=int(side), etype="close", exit_i=int(x), r_pts=r_pts,
                            tag="L" if side > 0 else "S"))
    return out


def trades(ctx, **p):
    tr = core.run_orders(ctx, orders(ctx, **p), one_at_a_time=False)
    for a, b in zip(tr[:-1], tr[1:]):
        assert b["j"] >= a["k"], "legs overlap"
    return tr
