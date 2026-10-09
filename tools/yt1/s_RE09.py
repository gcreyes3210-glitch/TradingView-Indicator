#!/usr/bin/env python3
"""RE09 - E09 noise-area intraday momentum, second independent coding from the spec text.

Spec (YT1_SPEC.md, E09): sigma(t) = 14-day average of |close(t) / 09:30 open - 1| at the same minute.
Upper = max(09:30 open, previous close) x (1 + sigma), lower mirror. Decisions only at the closes ending HH:00 and
HH:30, 10:00 -> 15:30: flat and above the upper -> long; long and below max(upper, 09:30 VWAP) -> out (and short if
also below the lower). Mirror. Each position is one trade. Neighbours: 7, 28 days. Reported: opp = stop only at the
opposite boundary.

How it is coded
  * decision bars = the 1-minute bars stamped 09:59, 10:29, ... 15:29 (12 a day), only those before the flat bar.
  * sigma for decision minute m on day d = mean of |C(m) / o930 - 1| over the previous n_days cash days (rows of
    ctx.days, today not included); a previous day with no bar at that minute is left out of the mean.
  * one evaluation per decision close. A position is one order entered at that close (etype 'close') and closed by
    an exit_sig array that is True only at decision closes where the exit condition of that side holds; otherwise
    the flat bar closes it. A reversal is the exit plus a new order on the same bar, so trades() simulates the orders
    one by one (core.run_orders would skip an order signalled on the previous trade's exit bar).
  * no price stop: r_pts = 0.1 x the day's daily ATR(14).
"""
import numpy as np
import pandas as pd
import core, ind

ID = "RE09"
NAME = "Noise-area intraday momentum (E09, second coder)"
VARIANTS = {
    "base": dict(n_days=14),
    "nb1": dict(n_days=7),
    "nb2": dict(n_days=28),
    "opp": dict(n_days=14, opp=True),
}

# closes ending 10:00, 10:30, ... 15:30 = the 1-minute bars stamped 09:59, 10:29, ... 15:29
DEC = [h * 60 + m - 1 for h in range(10, 16) for m in (0, 30)]


def _prep(ctx):
    """Per context, independent of the parameters: positions of the decision bars (days x 12, -1 = no such bar),
    each day's |close / 09:30 open - 1| at those bars (NaN where missing) and the 09:30-anchored VWAP."""
    c = getattr(ctx, "_re09_prep", None)
    if c is not None:
        return c
    D = ctx.days
    di = np.full((len(D), len(DEC)), -1, dtype=int)
    for r, d in enumerate(D.index):
        for q, m in enumerate(DEC):
            i = ctx.idx(d, m)
            if i is not None:
                di[r, q] = int(i)
    o930 = D.o930.to_numpy(float)
    move = np.full(di.shape, np.nan)
    ok = di >= 0
    rr = np.nonzero(ok)[0]
    move[ok] = np.abs(ctx.C[di[ok]] / o930[rr] - 1.0)
    new_session = np.zeros(ctx.n, dtype=bool)
    new_session[D.i_open.to_numpy()] = True
    vwap, _ = ind.session_vwap(ctx.H, ctx.L, ctx.C, ctx.V, new_session)
    ctx._re09_prep = (di, move, vwap)
    return ctx._re09_prep


def _plan(ctx, n_days=14, opp=False):
    """Runs the state machine day by day. Returns (orders, planned exit bars): the planned exit bar of each order is
    the decision bar at which the machine closed it, or the flat bar. trades() checks simulate against it."""
    di, move, vwap = _prep(ctx)
    D = ctx.days
    C = ctx.C
    # mean over the previous n_days cash days (missing minutes left out); needs n_days previous cash days to exist
    sig = pd.DataFrame(move).rolling(n_days, min_periods=1).mean().shift(1).to_numpy().copy()
    sig[:n_days] = np.nan
    exit_long = np.zeros(ctx.n, dtype=bool)        # shared by every long order
    exit_short = np.zeros(ctx.n, dtype=bool)       # shared by every short order
    o930, pdc, atr, i_end = (D[k].to_numpy(float) for k in ("o930", "pdc", "atr", "i_end"))
    orders, plan = [], []
    for r in range(n_days, len(D)):
        if not (atr[r] == atr[r] and pdc[r] == pdc[r]):
            continue                                # no R unit (no daily ATR) or no previous close
        ie = int(i_end[r])
        ref_hi, ref_lo = max(o930[r], pdc[r]), min(o930[r], pdc[r])
        r_pts = 0.1 * atr[r]
        pos = 0                                     # +1 long, -1 short, 0 flat
        for q in range(len(DEC)):
            i, s = int(di[r, q]), sig[r, q]
            if i < 0 or i >= ie or not s == s:
                continue                            # no bar, at / after the flat bar, or no sigma: no decision
            c = C[i]
            upper, lower, v = ref_hi * (1.0 + s), ref_lo * (1.0 - s), vwap[i]
            if opp:
                x_long, x_short = c < lower, c > upper
            else:                                   # c < max(upper, vwap)  <=>  c < upper or c < vwap
                x_long, x_short = (c < upper) or (c < v), (c > lower) or (c > v)
            exit_long[i], exit_short[i] = x_long, x_short
            enter = 0
            if pos == 1:
                if x_long:
                    plan[-1] = i
                    pos = 0
                    if c < lower:
                        enter = -1
            elif pos == -1:
                if x_short:
                    plan[-1] = i
                    pos = 0
                    if c > upper:
                        enter = 1
            else:
                if c > upper:
                    enter = 1
                elif c < lower:
                    enter = -1
            if enter:
                orders.append(dict(i=i, side=enter, etype="close", exit_i=ie, r_pts=r_pts,
                                   exit_sig=exit_long if enter > 0 else exit_short, tag="L" if enter > 0 else "S"))
                plan.append(ie)
                pos = enter
    return orders, plan


def orders(ctx, **p):
    return _plan(ctx, **p)[0]


def trades(ctx, **p):
    ords, plan = _plan(ctx, **p)
    out = []
    for o, k_plan in zip(ords, plan):
        d = pd.Timestamp(ctx.cdate[o["i"]])
        if d in ctx.roll_dates or d in ctx.noatr_dates:
            continue
        t = core.simulate(ctx, **o)
        if t is None:
            continue
        assert t["k"] == k_plan, f"simulate exit {ctx.ts[t['k']]} != state machine exit {ctx.ts[k_plan]}"
        out.append(t)
    return out
