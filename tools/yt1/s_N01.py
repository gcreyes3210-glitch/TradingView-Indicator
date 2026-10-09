#!/usr/bin/env python3
"""N01 - NQSimon: Asia-range deviations, New York morning reversal (YT3_SPEC.md).

Leg = the Asia range, 20:00-23:59 of the calendar evening before the cash day (wick high H, wick low L, W = H - L,
no trade if W < 10 points). Manipulation side = the first side of that range traded >= 1 tick beyond from 00:00, read
from the 1-minute bars 00:00 -> 09:29 (low first -> longs only, high first -> shorts only, neither -> no trade).
Long day: buy limits at Z2 = L - 2 W and Z4 = L - 4 W, each only if its level has not traded 00:00 -> 09:29, resting
09:30 -> 11:29, cancelled at Void = L - 4.5 W; stop a fixed distance below the ORDER price, target H, else the flat
bar. Shorts mirror above H with target L.

Everything in an order is known at the close of its signal bar (the 09:29 bar, or the last bar before 09:30):
the Asia range ended at 23:59 the evening before, the side and the "level has not traded" tests use bars before 09:30,
and the `bias` variant uses the previous cash session's close (pdc) and the high / low of the session before it.

Readings added (see notes/N01.md): the same 1-minute bar beyond both sides of the range = no trade; Void (a multiple
of half a tick) is rounded away from the range; one position at a time is enforced in trades() (see there).
"""
import numpy as np
import pandas as pd
import core

ID = "N01"
NAME = "NQSimon Asia-range deviations, NY morning reversal"
VARIANTS = {
    "base": dict(stop_pts=10.0),
    "nb1": dict(stop_pts=7.5),
    "nb2": dict(stop_pts=15.0),
    "scaled": dict(stop_pct=0.0004),        # stop 0.04 % of the order price (10 points at 25,000)
    "bias": dict(bias=True),                # longs only after a close above the prior session's high; shorts mirror
}
MIN_W = 10.0
EPS = 1e-9


def setups(ctx):
    """One dict per cash day that has an Asia range: the facts known at the close of the last bar before 09:30."""
    T = core.TICK
    D = ctx.days
    pph, ppl = D.rth_h.shift(2), D.rth_l.shift(2)          # the session before the previous one (complete long ago)
    out = []
    for d, day in D.iterrows():
        a0, a1 = ctx.span(d - pd.Timedelta(days=1), "20:00", 1440)   # previous calendar evening 20:00 -> 23:59
        if a1 <= a0:
            continue
        hr, lr = float(ctx.H[a0:a1].max()), float(ctx.L[a0:a1].min())
        w = hr - lr
        m0, m1 = ctx.span(d, "00:00", "09:30")                       # the cash day's own date, 00:00 -> 09:29
        s = dict(date=d, H=hr, L=lr, W=w, side=0, i=None, both=False)
        out.append(s)
        if m1 <= m0:
            continue
        lo, hi = ctx.L[m0:m1], ctx.H[m0:m1]
        kl = np.flatnonzero(lo <= lr - T + EPS)
        kh = np.flatnonzero(hi >= hr + T - EPS)
        kl = int(kl[0]) if len(kl) else None
        kh = int(kh[0]) if len(kh) else None
        if kl is None and kh is None:
            continue
        if kl is not None and kh is not None and kl == kh:           # one bar beyond both sides: order unknown
            s["both"] = True
            continue
        side = 1 if (kh is None or (kl is not None and kl < kh)) else -1
        s["side"] = side
        s["i"] = m1 - 1                                               # the 09:29 bar, or the last bar before 09:30
        e0, e1 = ctx.span(d, "09:30", "11:30")
        s["expire"] = e1 - 1                                          # the 11:29 bar, or the last bar before 11:30
        s["exit_i"] = int(day.i_end)
        if side > 0:
            s["z2"] = core.tick_round(lr - 2 * w)
            s["z4"] = core.tick_round(lr - 4 * w)
            s["void"] = core.tick_round(lr - 4.5 * w, "down")
            ext = float(lo.min())
            s["z2_free"], s["z4_free"] = ext > s["z2"] + EPS, ext > s["z4"] + EPS
            s["target"] = hr
        else:
            s["z2"] = core.tick_round(hr + 2 * w)
            s["z4"] = core.tick_round(hr + 4 * w)
            s["void"] = core.tick_round(hr + 4.5 * w, "up")
            ext = float(hi.max())
            s["z2_free"], s["z4_free"] = ext < s["z2"] - EPS, ext < s["z4"] - EPS
            s["target"] = lr
        s["bias_ok"] = bool(day.pdc > pph[d]) if side > 0 else bool(day.pdc < ppl[d])   # NaN compares False
    return out


def orders(ctx, stop_pts=10.0, stop_pct=None, bias=False):
    out = []
    for s in setups(ctx):
        if s["side"] == 0 or s["W"] < MIN_W - EPS:
            continue
        if bias and not s["bias_ok"]:
            continue
        side = s["side"]
        for lvl in ("z2", "z4"):                                      # Z2 first: it is the nearer level
            if not s[lvl + "_free"]:
                continue
            price = s[lvl]
            dist = stop_pts if stop_pct is None else stop_pct * price
            o = dict(i=int(s["i"]), side=side, etype="limit", price=price, expire=int(s["expire"]),
                     stop=core.tick_round(price - side * dist), target=s["target"], exit_i=s["exit_i"],
                     tag=("L" if side > 0 else "S") + lvl[1])
            o["cancel_lo" if side > 0 else "cancel_hi"] = s["void"]
            out.append(o)
    return out


def _one_position(tr):
    """Drop a trade filled while the day's earlier trade was still open. The stop of the Z2 order lies between Z2 and
    Z4, so the Z2 trade is always out before Z4 can fill; a Z4 fill on the bar the Z2 trade was stopped is after that
    stop on the bar's path and is kept. This check is the rule's "one position at a time" made explicit."""
    out = []
    for t in tr:
        p = out[-1] if out else None
        if p is not None and (t["j"] < p["k"] or (t["j"] == p["k"] and p["reason"] != "SL")):
            continue
        out.append(t)
    return out


def trades(ctx, **p):
    # Both of a day's orders share one signal bar, so run_orders(one_at_a_time=True) would drop the Z4 order whenever
    # the Z2 order filled (its test is "signal bar <= previous exit bar"), i.e. one trade a day, not the spec's two.
    # The two orders are therefore simulated independently by the harness and the one-position rule is applied to
    # the resulting fill / exit bars. Roll and no-ATR days are dropped by run_orders.
    return _one_position(core.run_orders(ctx, orders(ctx, **p), one_at_a_time=False, max_per_day=2))


def diag(ctx, **p):
    """Counts for the notes (not used by any order)."""
    S = setups(ctx)
    skip = ctx.roll_dates | ctx.noatr_dates
    df = pd.DataFrame([dict(date=s["date"], W=s["W"], side=s["side"], both=s["both"]) for s in S])
    df["year"] = pd.DatetimeIndex(df.date).year
    res = dict(cash_days=int(len(ctx.days)), days_with_asia=int(len(df)), w_lt_10=int((df.W < MIN_W - EPS).sum()),
               side_days_all=int((df.side != 0).sum()), both_sides_one_bar=int(df.both.sum()))
    ok = df[(df.W >= MIN_W - EPS)]
    res["side_days_w_ok"] = int((ok.side != 0).sum())
    res["long_days"], res["short_days"] = int((ok.side > 0).sum()), int((ok.side < 0).sum())
    res["W_by_year"] = {int(y): dict(n=int(len(g)), mean=round(float(g.W.mean()), 2), median=float(g.W.median()))
                        for y, g in df.groupby("year")}
    o = orders(ctx, **p)
    live = [x for x in o if pd.Timestamp(ctx.cdate[x["i"]]) not in skip]
    res["orders"] = {k: sum(1 for x in o if x["tag"][1] == k) for k in "24"}
    res["orders_tradable_days"] = {k: sum(1 for x in live if x["tag"][1] == k) for k in "24"}
    res["order_days_tradable"] = len({x["i"] for x in live})
    raw = core.run_orders(ctx, o, one_at_a_time=False, max_per_day=2)
    t = pd.DataFrame(trades(ctx, **p))
    res["dropped_by_one_position"] = len(raw) - len(t)
    res["filled"] = {k: int((t.tag.str[1] == k).sum()) for k in "24"}
    res["days_both_filled"] = int((t.groupby("i").size() == 2).sum())
    res["trades"] = int(len(t))
    res["stopped_on_fill_bar"] = int(((t.reason == "SL") & (t.k == t.j)).sum())
    res["stopped_on_fill_bar_share"] = round(float(((t.reason == "SL") & (t.k == t.j)).mean()), 4)
    res["reasons"] = t.reason.value_counts().to_dict()
    res["n_if_run_orders_one_at_a_time_True"] = len(core.run_orders(ctx, o, one_at_a_time=True, max_per_day=2))
    return res
