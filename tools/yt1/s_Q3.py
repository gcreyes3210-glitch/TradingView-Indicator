#!/usr/bin/env python3
"""Q3 - 1-minute VWAP with EMA 9, pullback version (M14, Modern Scalping).

Spec text (YT11_SPEC.md, Part 4, Q3):
  Up state at a close: close above VWAP and EMA(9) above EMA(21).
  Touch bar: its low is at or below EMA(9) and above EMA(21), with the up state at the previous close.
  Entry: the first bar from the touch bar to four bars after it that closes above its open and above EMA(9) with
  the up state, no low at or below EMA(21) since the touch; buy at its close, 09:35 to 15:29.
  Stop 1 tick below the lowest low from the touch bar through the entry bar. Target 2R. Shorts mirrored.
  Neighbours 1.5R and 3R. Reported: `long` only. One position at a time.

Shared definitions: VWAP anchored at 09:30 (hlc3 x volume, 1-minute bars, through the bar just closed); EMAs from
ind.py on the continuous 24-hour 1-minute series.

Readings fixed before the first run (see notes/Q3.md):
  * every bar that meets the touch definition is a touch bar, with its own search for an entry on itself and the
    next four bars. When several touch bars lead to the same entry bar, the earliest of them is "the touch" (so the
    lowest low covers the whole pullback inside the four-bar reach).
  * "the first bar ... that closes above its open and above EMA(9) with the up state" is found without regard to
    the clock; the trade is taken only if that bar is stamped 09:35 ... 15:29, on a traded day before its flat bar.
  * a bar's low is compared with the EMA values of that same bar; "previous close" = the bar before in the series
    (it must have a VWAP, so a touch bar is 09:31 or later).
  * target = signal close + k x (signal close - stop), core.tick_round (nearest tick).
  * short mirror: down state = close below VWAP and EMA(9) below EMA(21); touch = high at or above EMA(9) and
    below EMA(21) with the down state at the previous close; entry = first bar closing below its open and below
    EMA(9) with the down state, no high at or above EMA(21) since the touch; stop 1 tick above the highest high.
  * one position at a time is run_orders' rule (a signal on a bar at or before the previous exit bar is skipped).
"""
import numpy as np
import core
import ind

ID = "Q3"
NAME = "1-minute VWAP + EMA 9 pullback, stop under the pullback low, 2R (M14)"
VARIANTS = {
    "base": dict(k_r=2.0),
    "nb1": dict(k_r=1.5),
    "nb2": dict(k_r=3.0),
    "long": dict(k_r=2.0, sides=(1,)),
}
OPEN, CLOSE = 9 * 60 + 30, 16 * 60
WIN = (9 * 60 + 35, 15 * 60 + 29)                    # stamps of the entry bars, both included
REACH = 4                                            # the touch bar and the four bars after it


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


def _runlen(x):
    """Number of consecutive True values ending at each position (0 where x is False)."""
    x = np.asarray(x, bool)
    idx = np.arange(len(x))
    last_false = np.maximum.accumulate(np.where(~x, idx, -1))
    return idx - last_false


def _side(side, o, h, l, c, vw, e9, e21):
    """Entry bars of one direction (before the clock window): returns (bars, bars back to the touch, extreme)."""
    n = len(c)
    with np.errstate(invalid="ignore"):
        if side > 0:
            state = (c > vw) & (e9 > e21)
            touch = (l <= e9) & (l > e21)
            qual = (c > o) & (c > e9) & state           # the bar an entry is made on
            viol = l <= e21                             # a low at or below EMA(21)
            px = l
        else:
            state = (c < vw) & (e9 < e21)
            touch = (h >= e9) & (h < e21)
            qual = (c < o) & (c < e9) & state
            viol = h >= e21
            px = h
    touch = touch & np.r_[False, state[:-1]]            # the state at the previous close
    nq_prev = np.r_[0, _runlen(~qual)[:-1]]             # bars without an entry-type bar, ending at the bar before
    nv = _runlen(~viol)                                 # bars without a violation, ending at this bar
    best = np.full(n, -1)
    ext = np.full(n, np.nan)
    run_ext = px.copy()                                 # extreme of bars e - d .. e
    for d in range(REACH + 1):
        if d:
            sh = np.r_[np.full(d, np.nan), px[:-d]]
            run_ext = np.fmin(run_ext, sh) if side > 0 else np.fmax(run_ext, sh)
            t_ok = np.r_[np.zeros(d, bool), touch[:n - d]]
        else:
            t_ok = touch
        ok = qual & t_ok & (nq_prev >= d) & (nv >= d + 1)
        best[ok] = d                                    # a larger d overwrites: the earliest touch
        ext[ok] = run_ext[ok]
    e = np.flatnonzero(best >= 0)
    return e, best[e], ext[e]


def orders(ctx, k_r=2.0, sides=(1, -1)):
    o, h, l, c = ctx.O, ctx.H, ctx.L, ctx.C
    vw, _ = _vwap(ctx)
    e9, e21 = _ema(ctx, 9), _ema(ctx, 21)
    live, i_end, _ = _daymap(ctx)
    win = live & (ctx.tod >= WIN[0]) & (ctx.tod <= WIN[1])
    T = core.TICK
    out = []
    for side in sides:
        bars, back, ext = _side(side, o, h, l, c, vw, e9, e21)
        for i, d, x in zip(bars.tolist(), back.tolist(), ext.tolist()):
            if not win[i]:
                continue
            stop = x - side * T
            target = core.tick_round(c[i] + side * k_r * abs(c[i] - stop))
            out.append(dict(i=i, side=side, etype="close", stop=float(stop), target=float(target),
                            exit_i=int(i_end[i]), tag=("L" if side > 0 else "S") + f" t-{d}"))
    return out


def trades(ctx, **p):
    return core.run_orders(ctx, orders(ctx, **p), one_at_a_time=True)
