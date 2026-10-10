#!/usr/bin/env python3
"""Q5 - Bollinger fade with an ADX filter, 5-minute bars (M15, CrossTrade).

Spec text (YT11_SPEC.md, Part 4, Q5):
  Signal bar closing 09:50 to 15:25: ADX(14) at most 25; low at or below the lower band of Bollinger(20, 2); lower
  wick (min(open, close) - low) more than 1.5 x the body and the close above the low. Buy at the next bar's open.
  Stop 1 x ATR(14) of 5-minute bars below the signal bar's low. Target the middle band's value at the signal bar's
  close (fixed); no trade if that is not above the signal close. Exit at the close of the 15th bar after the entry
  bar if neither is hit. Short mirrors. One position at a time.
  Neighbours: band 2.5; ADX at most 20. Reported: `m1` the same rule on 1-minute bars; `noadx`.

ADX, ATR, Bollinger from ind.py on the continuous 24-hour series of the timeframe (ctx.bars(5); a 5-minute bar is
known at the close of its last 1-minute bar, i_last).

Readings fixed before the first run (see notes/Q5.md):
  * "signal bar closing 09:50 to 15:25" = bars stamped 09:50 ... 15:25 (the same convention as the other Part 4
    entries, which name a close by its bar), on a traded day, the bar's last minute before the flat bar.
  * body = |close - open|. ADX "at most" = <=; "at or below the band" = <=; the wick test is strict.
  * stop = signal low - ATR(14) at the signal bar, core.tick_round (nearest tick); target = the middle band (SMA 20)
    at the signal bar, core.tick_round (nearest tick); "no trade if that is not above the signal close" is applied
    to the target as placed (the rounded value must be above the signal close).
  * entry: etype "open", i = the signal bar's last 1-minute bar, so the fill is the open of the next 1-minute bar =
    the next 5-minute bar's open. Stop and target are not moved for the open (the harness refuses an order whose
    stop is already on the wrong side of the fill).
  * time exit: the entry bar is the bar after the signal bar; the exit is the close (i_last) of the 15th bar after
    it, i.e. signal bar + 16 in the series, or the flat bar if that comes first.
  * short mirror: high at or above the upper band; upper wick (high - max(open, close)) more than 1.5 x the body
    and the close below the high; stop 1 x ATR above the high; target the middle band, which must be below the close.
  * `m1`: every bar is a 1-minute bar (stamps 09:50 ... 15:25, indicators on 1-minute bars, 15 one-minute bars).
  * one position at a time is run_orders' rule (a signal on a bar at or before the previous exit bar is skipped).
"""
import numpy as np
import core
import ind

ID = "Q5"
NAME = "Bollinger(20,2) wick fade to the middle band with ADX(14) <= 25, 5-minute bars (M15)"
VARIANTS = {
    "base": dict(mult=2.0, adx_max=25.0),
    "nb1": dict(mult=2.5, adx_max=25.0),
    "nb2": dict(mult=2.0, adx_max=20.0),
    "m1": dict(mult=2.0, adx_max=25.0, minutes=1),
    "noadx": dict(mult=2.0, adx_max=None),
}
WIN = (9 * 60 + 50, 15 * 60 + 25)                    # stamps of the signal bars, both included
BB_N, ADX_N, ATR_N, WICK_K, HOLD = 20, 14, 14, 1.5, 15


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


def _frame(ctx, minutes):
    """Bars of the timeframe as arrays, with ADX and ATR: (o, h, l, c, stamp minute, i_last, adx, atr)."""
    key = f"_yt11_q5_{minutes}"
    f = getattr(ctx, key, None)
    if f is None:
        if minutes == 1:
            o, h, l, c = ctx.O, ctx.H, ctx.L, ctx.C
            tod, i_last = ctx.tod, np.arange(ctx.n)
        else:
            b = ctx.bars(minutes)
            o, h, l, c = (b[k].to_numpy(float) for k in ("open", "high", "low", "close"))
            tod = (b.index.hour * 60 + b.index.minute).to_numpy()
            i_last = b.i_last.to_numpy()
        adx = ind.dmi(h, l, c, ADX_N, ADX_N)[2]
        atr = ind.atr(h, l, c, ATR_N)
        f = (o, h, l, c, tod, i_last, adx, atr)
        setattr(ctx, key, f)
    return f


def orders(ctx, mult=2.0, adx_max=25.0, minutes=5):
    o, h, l, c, tod, i_last, adx, atr = _frame(ctx, minutes)
    basis, upper, lower, _ = ind.bollinger(c, BB_N, mult)
    live, i_end, _ = _daymap(ctx)
    nb = len(c)
    body = np.abs(c - o)
    with np.errstate(invalid="ignore"):
        ok = live[i_last] & (tod >= WIN[0]) & (tod <= WIN[1]) & np.isfinite(atr) & np.isfinite(basis)
        if adx_max is not None:
            ok &= adx <= adx_max
        sig_l = ok & (l <= lower) & ((np.minimum(o, c) - l) > WICK_K * body) & (c > l)
        sig_s = ok & (h >= upper) & ((h - np.maximum(o, c)) > WICK_K * body) & (c < h)
    out = []
    for side, sig in ((1, sig_l), (-1, sig_s)):
        for k in np.flatnonzero(sig).tolist():
            target = core.tick_round(basis[k])
            if not (side * (target - c[k]) > 0):
                continue                                                  # the middle band is not beyond the close
            ext = l[k] if side > 0 else h[k]
            stop = core.tick_round(ext - side * atr[k])
            i = int(i_last[k])
            kx = k + 1 + HOLD                                             # the 15th bar after the entry bar
            x = int(i_end[i]) if kx >= nb else int(min(i_last[kx], i_end[i]))
            out.append(dict(i=i, side=side, etype="open", stop=float(stop), target=float(target), exit_i=x,
                            tag="L" if side > 0 else "S"))
    return out


def trades(ctx, **p):
    return core.run_orders(ctx, orders(ctx, **p), one_at_a_time=True)
