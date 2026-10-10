#!/usr/bin/env python3
"""Q2 - 1-minute VWAP with EMA 9 / 21, cross version (M14, AlgoTest).

Spec text (YT11_SPEC.md, Part 4, Q2):
  At a close from 09:35 to 15:44: EMA(9) crosses above EMA(21) on that bar, the close is above VWAP and above both
  EMAs: buy at the close. Exit at the first close where EMA(9) crosses below EMA(21) or the close is below VWAP, or
  the flat bar. No stop. Short mirrors. One position at a time.
  Neighbours: exit on the EMA cross only; exit on the VWAP close only.

Shared definitions: VWAP anchored at 09:30 (hlc3 x volume, 1-minute bars, through the bar just closed); EMAs from
ind.py on the continuous 24-hour 1-minute series.

Readings fixed before the first run (see notes/Q2.md):
  * "a close from 09:35 to 15:44" = the close of a 1-minute bar stamped 09:35 ... 15:44 (the spec names a close by
    its bar: "the close of the 09:30 bar"), on a traded cash day and before the flat bar.
  * "crosses above on that bar" = ind.crossed_up: EMA9 > EMA21 at this bar and EMA9 <= EMA21 at the bar before
    (the bar before in the 24-hour series).
  * all comparisons are strict (above / below); a close equal to VWAP is not an exit.
  * the exit is the harness's exit_sig: a bool array true at every bar whose own close meets the exit condition
    (nothing later than that bar), read by simulate only on bars after the entry bar. Short exits mirror: EMA9
    crosses above EMA21, or the close is above VWAP.
  * R unit = 0.1 x that day's daily ATR(14).
  * one position at a time is run_orders' rule: a signal on a bar at or before the previous trade's exit bar is not
    taken (so a signal that appears on the very bar that closes the previous trade is skipped).
"""
import numpy as np
import core
import ind

ID = "Q2"
NAME = "1-minute VWAP + EMA 9/21 cross, exit on the cross back or a close across VWAP (M14)"
VARIANTS = {
    "base": dict(exit="both"),
    "nb1": dict(exit="ema"),
    "nb2": dict(exit="vwap"),
}
OPEN, CLOSE = 9 * 60 + 30, 16 * 60
WIN = (9 * 60 + 35, 15 * 60 + 44)                    # stamps of the entry bars, both included


def _vwap(ctx):
    """09:30-anchored VWAP of hlc3 per 1-minute bar and its volume-weighted sd (NaN outside 09:30-15:59)."""
    v = getattr(ctx, "_yt11_vwap", None)
    if v is None:
        m = np.flatnonzero((ctx.tod >= OPEN) & (ctx.tod < CLOSE))
        new = np.r_[True, ctx.cdate[m][1:] != ctx.cdate[m][:-1]]          # the first session bar of each date
        vw, sd = ind.session_vwap(ctx.H[m], ctx.L[m], ctx.C[m], ctx.V[m], new)
        v = (np.full(ctx.n, np.nan), np.full(ctx.n, np.nan))
        v[0][m], v[1][m] = vw, sd
        ctx._yt11_vwap = v
    return v


def _ema(ctx, n):
    key = f"_yt11_ema{n}"
    e = getattr(ctx, key, None)
    if e is None:
        e = ind.ema(ctx.C, n)
        setattr(ctx, key, e)
    return e


def _daymap(ctx):
    """Per 1-minute bar: inside a cash session before its flat bar; that day's flat bar; 0.1 x that day's ATR."""
    m = getattr(ctx, "_yt11_daymap", None)
    if m is None:
        live = np.zeros(ctx.n, bool)
        i_end = np.full(ctx.n, -1, dtype=np.int64)
        r_pts = np.full(ctx.n, np.nan)
        D = ctx.days
        for a, z, atr in zip(D.i_open.to_numpy(), D.i_end.to_numpy(), D.atr.to_numpy(float)):
            live[a:z] = True
            i_end[a:z + 1] = z
            r_pts[a:z + 1] = 0.1 * atr
        m = (live, i_end, r_pts)
        ctx._yt11_daymap = m
    return m


def orders(ctx, exit="both"):
    C = ctx.C
    vw, _ = _vwap(ctx)
    e9, e21 = _ema(ctx, 9), _ema(ctx, 21)
    live, i_end, r_pts = _daymap(ctx)
    up, dn = ind.crossed_up(e9, e21), ind.crossed_dn(e9, e21)
    with np.errstate(invalid="ignore"):
        above, below = C > vw, C < vw                                      # False where there is no VWAP
        sig_l = up & above & (C > e9) & (C > e21)
        sig_s = dn & below & (C < e9) & (C < e21)
    win = live & (ctx.tod >= WIN[0]) & (ctx.tod <= WIN[1])
    if exit == "both":
        x_l, x_s = dn | below, up | above
    elif exit == "ema":
        x_l, x_s = dn, up
    elif exit == "vwap":
        x_l, x_s = below, above
    else:
        raise ValueError(exit)
    out = []
    for side, sig, xs in ((1, sig_l, x_l), (-1, sig_s, x_s)):
        for i in np.flatnonzero(sig & win).tolist():
            r = r_pts[i]
            out.append(dict(i=i, side=side, etype="close", exit_i=int(i_end[i]), exit_sig=xs,
                            r_pts=float(r) if r == r else None, tag="L" if side > 0 else "S"))
    return out


def trades(ctx, **p):
    return core.run_orders(ctx, orders(ctx, **p), one_at_a_time=True)
