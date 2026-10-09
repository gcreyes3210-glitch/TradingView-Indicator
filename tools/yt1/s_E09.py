#!/usr/bin/env python3
"""E09 - noise-area intraday momentum (Zarattini, Aziz, Barbon, "Beat the Market").

Spec text (YT1_SPEC.md, E09):
  sigma(t) = 14-day average of |close(t) / 09:30 open - 1| at the same minute.
  Upper = max(09:30 open, previous close) x (1 + sigma), lower mirror.
  Decisions only at the closes ending HH:00 and HH:30, 10:00 -> 15:30: flat and above the upper -> long; long and
  below max(upper, 09:30 VWAP) -> out (and short if also below the lower). Mirror. Each position is one trade.
  Neighbours: 7, 28 days. Reported: `opp` = stop only at the opposite boundary.

Readings added (fixed before the first run; see notes/E09.md):
  * decision bars = the 1-minute bars 09:59, 10:29, ... 15:29 of a cash day, before its flat bar; a missing bar is a
    skipped decision. "Above" / "below" are strict and are tested on that bar's close.
  * sigma at a minute = the mean of |close of that minute's bar / that day's 09:30 open - 1| over the previous N cash
    days that have a bar at that minute (today not included). No sigma yet = no decision.
  * previous close = the previous cash day's last RTH close (day table pdc).
  * VWAP = ind.session_vwap (hlc3 x volume) of the 1-minute bars from 09:30, read at the decision bar.
  * the state machine acts once per decision close on the state it had before that close: a long that is closed
    is not re-opened at the same close; if the close is also below the lower boundary a short is opened at it.
    As written, opening a position needs only the close beyond the boundary (not beyond the VWAP).
  * each position is one order: market at the decision close, no price stop, exit_sig true only at decision closes
    where the exit condition holds, otherwise the flat bar. R unit = 0.1 x daily ATR(14) (common rules).
  * `opp`: a long is closed only when the close is below the lower boundary (and a short is opened there); mirror.
  * the orders are simulated one by one (a reversal's entry is on the previous trade's exit bar, which run_orders
    would skip); roll days and days without an ATR are left out in trades().
"""
import numpy as np
import pandas as pd
import core
import ind

ID = "E09"
NAME = "Noise-area intraday momentum: half-hourly closes beyond open/prior-close x (1 +/- sigma), VWAP trailing exit"
VARIANTS = {
    "base": dict(days=14),
    "nb1": dict(days=7),
    "nb2": dict(days=28),
    "opp": dict(days=14, opp=True),
}
DEC_TOD = [h * 60 + m for h in range(9, 16) for m in (29, 59)][1:-1]      # 09:59, 10:29, ... 15:29


def _vwap(ctx):
    """09:30-anchored VWAP per 1-minute bar (NaN outside 09:30-15:59)."""
    v = getattr(ctx, "_yt1E09_vwap", None)
    if v is None:
        m = np.flatnonzero((ctx.tod >= 570) & (ctx.tod < 960))
        vw, _ = ind.session_vwap(ctx.H[m], ctx.L[m], ctx.C[m], ctx.V[m], ctx.tod[m] == 570)
        v = np.full(ctx.n, np.nan)
        v[m] = vw
        ctx._yt1E09_vwap = v
    return v


def _table(ctx, days):
    """Per cash day (rows) and decision minute (columns): bar position (-1 = none), upper and lower boundary."""
    key = f"_yt1E09_tab_{days}"
    t = getattr(ctx, key, None)
    if t is not None:
        return t
    D = ctx.days
    nd, nc = len(D), len(DEC_TOD)
    o930, pdc = D.o930.to_numpy(float), D.pdc.to_numpy(float)
    pos = np.full((nd, nc), -1, dtype=np.int64)
    sig = np.full((nd, nc), np.nan)
    n0 = int(D.n.iloc[0])
    assert (D.n.to_numpy() == n0 + np.arange(nd)).all()
    for c, tod in enumerate(DEC_TOD):
        b = np.flatnonzero((ctx.tod == tod) & (ctx.dayn >= n0))           # this minute's bar on every cash day
        r = ctx.dayn[b] - n0                                              # row of the day table
        pos[r, c] = b
        move = pd.Series(np.abs(ctx.C[b] / o930[r] - 1))                  # one value per day that has the bar
        sig[r, c] = move.rolling(days).mean().shift(1).to_numpy()         # the previous `days` such days
    hi, lo = np.maximum(o930, pdc), np.minimum(o930, pdc)
    upper, lower = hi[:, None] * (1 + sig), lo[:, None] * (1 - sig)
    t = (pos, upper, lower)
    setattr(ctx, key, t)
    return t


def orders(ctx, days=14, opp=False):
    D = ctx.days
    pos, upper, lower = _table(ctx, days)
    vw, C = _vwap(ctx), ctx.C
    exit_long, exit_short = np.zeros(ctx.n, bool), np.zeros(ctx.n, bool)
    i_end, atr = D.i_end.to_numpy(), D.atr.to_numpy(float)
    out = []
    for r in range(len(D)):
        state = 0
        r_pts = 0.1 * atr[r] if atr[r] == atr[r] else None
        for c in range(len(DEC_TOD)):
            i = int(pos[r, c])
            up, lw = upper[r, c], lower[r, c]
            if i < 0 or i >= i_end[r] or not (up == up and lw == lw):
                continue
            cl = C[i]
            if opp:
                x_long, x_short = cl < lw, cl > up
            else:
                x_long, x_short = cl < max(up, vw[i]), cl > min(lw, vw[i])
            exit_long[i], exit_short[i] = x_long, x_short
            if state == 1:
                new = (-1 if cl < lw else 0) if x_long else 1
            elif state == -1:
                new = (1 if cl > up else 0) if x_short else -1
            else:
                new = 1 if cl > up else -1 if cl < lw else 0
            if new != state and new != 0:
                out.append(dict(i=i, side=new, etype="close", exit_i=int(i_end[r]),
                                exit_sig=exit_long if new > 0 else exit_short, r_pts=r_pts,
                                tag="L" if new > 0 else "S"))
            state = new
    return out


def trades(ctx, **p):
    out, busy = [], -1
    for o in sorted(orders(ctx, **p), key=lambda o: o["i"]):
        d = pd.Timestamp(ctx.cdate[o["i"]])
        if d in ctx.roll_dates or d in ctx.noatr_dates or ctx.dayn[o["i"]] < 0:
            continue
        t = core.simulate(ctx, **o)
        if t is None:
            continue
        assert t["j"] >= busy, "positions overlap"           # a reversal enters on the previous exit bar, never before
        busy = t["k"]
        out.append(t)
    return out
