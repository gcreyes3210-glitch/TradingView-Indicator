#!/usr/bin/env python3
"""Q6 - MNQ 5 / 30 / 200 EMA (M17, a TradingView script).

Spec text (YT11_SPEC.md, Part 4, Q6):
  Set-up bar closing 09:30 to 15:44: close above EMA(5), EMA(30) and EMA(200). Buy stop 1 tick above its high, live
  for the next bar only. Stop 1 tick below the set-up bar's low. Target 3R. Short: close below all three; sell stop
  1 tick below its low; stop 1 tick above its high. After any exit the next set-up bar is at least 5 bars later.
  Neighbours 2R and 4R. Reported: `fresh` = only a set-up bar whose previous bar did not qualify on that side.
  1-minute bars; one position at a time.

EMAs from ind.py on the continuous 24-hour 1-minute series.

Readings fixed before the first run (see notes/Q6.md):
  * "set-up bar closing 09:30 to 15:44" = 1-minute bars stamped 09:30 ... 15:44 (the same convention as the other
    Part 4 entries, which name a close by its bar), on a traded day before its flat bar. The order is live in the
    next bar of the series only (etype "stop", expire = i + 1).
  * target = order price + 3 x |order price - stop| (the common rule: entry price before slippage), on the tick
    grid by construction for 2R / 3R / 4R. It is fixed when the order is placed; if the next bar opens beyond the
    order price the harness fills at that open and R is measured from the real fill.
  * "after any exit the next set-up bar is at least 5 bars later": with an exit on bar k, the first bar that may be
    a set-up bar again is k + 5 (bars of the series). Unfilled orders block nothing.
  * `fresh`: the bar before the set-up bar in the series (whatever its time) did not close on that side of all
    three EMAs.
  * run_orders cannot express the five-bar gap, so trades() walks the orders in time order itself and calls
    core.simulate for each one that is allowed; roll days and days without a daily ATR are left out there, as
    run_orders does. Every fill, exit and P&L is the harness's.
"""
import numpy as np
import core
import ind

ID = "Q6"
NAME = "MNQ 5/30/200 EMA: stop-entry 1 tick beyond the set-up bar, stop beyond its other end, 3R (M17)"
VARIANTS = {
    "base": dict(k_r=3.0),
    "nb1": dict(k_r=2.0),
    "nb2": dict(k_r=4.0),
    "fresh": dict(k_r=3.0, fresh=True),
}
WIN = (9 * 60 + 30, 15 * 60 + 44)                    # stamps of the set-up bars, both included
GAP = 5                                              # bars from an exit to the next set-up bar


def _daymap(ctx):
    """Per 1-minute bar: inside a cash session before its flat bar; that day's flat bar; a traded day (no roll,
    daily ATR present)."""
    m = getattr(ctx, "_yt11_q6_daymap", None)
    if m is None:
        live = np.zeros(ctx.n, bool)
        traded = np.zeros(ctx.n, bool)
        i_end = np.full(ctx.n, -1, dtype=np.int64)
        D = ctx.days
        for d, a, z in zip(D.index, D.i_open.to_numpy(), D.i_end.to_numpy()):
            live[a:z] = True
            i_end[a:z + 1] = z
            traded[a:z + 1] = d not in ctx.roll_dates and d not in ctx.noatr_dates
        m = (live, i_end, traded)
        ctx._yt11_q6_daymap = m
    return m


def _sides(ctx):
    """Bars closing above all three EMAs / below all three."""
    s = getattr(ctx, "_yt11_q6_sides", None)
    if s is None:
        C = ctx.C
        e5, e30, e200 = ind.ema(C, 5), ind.ema(C, 30), ind.ema(C, 200)
        with np.errstate(invalid="ignore"):
            s = ((C > e5) & (C > e30) & (C > e200), (C < e5) & (C < e30) & (C < e200))
        ctx._yt11_q6_sides = s
    return s


def orders(ctx, k_r=3.0, fresh=False):
    H, L = ctx.H, ctx.L
    above, below = _sides(ctx)
    live, i_end, _ = _daymap(ctx)
    win = live & (ctx.tod >= WIN[0]) & (ctx.tod <= WIN[1])
    T = core.TICK
    out = []
    for side, q in ((1, above), (-1, below)):
        sig = q & win
        if fresh:
            sig &= ~np.r_[False, q[:-1]]
        for i in np.flatnonzero(sig).tolist():
            if side > 0:
                price, stop = H[i] + T, L[i] - T
            else:
                price, stop = L[i] - T, H[i] + T
            target = core.tick_round(price + side * k_r * abs(price - stop))
            out.append(dict(i=i, side=side, etype="stop", price=float(price), expire=i + 1, stop=float(stop),
                            target=float(target), exit_i=int(i_end[i]), tag="L" if side > 0 else "S"))
    out.sort(key=lambda o: o["i"])
    return out


def trades(ctx, **p):
    _, _, traded = _daymap(ctx)
    out, free_from = [], -1
    for o in orders(ctx, **p):
        i = o["i"]
        if i < free_from or not traded[i]:
            continue
        t = core.simulate(ctx, **o)
        if t is None:
            continue
        out.append(t)
        free_from = t["k"] + GAP                      # the next set-up bar is at least 5 bars after the exit bar
    return out
