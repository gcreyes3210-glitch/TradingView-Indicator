#!/usr/bin/env python3
"""D05 - Absorption candle, POC in the wick, delta flip, at a level (Thraxx), YT1_SPEC.md Family D.

Long (NQ 5-minute footprint bars opening 09:30 .. 11:25): the bar's low is within 0.05 x daily ATR of (or through)
the previous day's RTH low or the overnight low; the bar's highest-volume price is below its body; its delta is
positive and the previous bar's negative. Entry: buy limit 1 point above that price, resting 15 minutes. Stop: beyond
the bar's low. Target 2R. Mirror at the highs. Neighbours: 0.025, 0.10 x ATR. Reported: `nolevel`.
One position at a time. Trades are filled on MNQ 1-minute bars at the footprint's prices.

Readings added to the spec text (all fixed before the first run; see notes/D05.md):
  * the bar's open / high / low / close are those of the MNQ 1-minute bars of its five minutes; the levels are the
    day table's pdl / onl (pdh / onh), all MNQ prices; the footprint's highest-volume price is used as an MNQ price
    unchanged; a footprint bar opening at T is used at the close of the MNQ 1-minute bar T+4;
  * "within 0.05 x ATR of (or through)" a low level L: bar low <= L + 0.05 x ATR, with no limit on how far below
    (mirror: bar high >= H - 0.05 x ATR); either of the two levels is enough;
  * highest-volume price = the price with the largest buy + sell; two or more prices tied for it = no signal;
    "below its body" = strictly below min(open, close) (mirror: strictly above max(open, close));
  * the previous bar = the footprint bar that opened five minutes earlier, 09:30 or later (so the 09:30 bar is never
    a signal); delta = sum(buy) - sum(sell); positive / negative are strict;
  * "resting 15 minutes" = the 15 one-minute bars T+5 .. T+19 after the signal bar's close;
  * stop = 1 tick beyond the MNQ bar's low (high); an order whose limit is not on the right side of its stop is not
    placed; target = limit price +/- 2 x |limit price - stop|;
  * trade count as D03: any number a day, one position at a time (base); `day1...` = one trade per day.
"""
import numpy as np
import pandas as pd
import core

ID = "D05"
NAME = "Absorption candle, POC in the wick, delta flip, at a level (Thraxx)"
VARIANTS = {
    "base": dict(tol=0.05),
    "nb1": dict(tol=0.025),
    "nb2": dict(tol=0.10),
    "nolevel": dict(level=False),
    # not in the spec's list: the other reading of the trade count (one trade per day)
    "day1": dict(tol=0.05, per_day=1),
    "day1_nb1": dict(tol=0.025, per_day=1),
    "day1_nb2": dict(tol=0.10, per_day=1),
    "day1_nolevel": dict(level=False, per_day=1),
}
T = core.TICK


# ---- shared footprint helper (copied between s_D03 / s_D05 / s_D06 / k_D07 / k_D15 / k_D08)
def fp_table(ctx):
    """NQ 5-minute footprint bars by cash day: {date: [bar, ...]} in time order, bars opening 09:30 .. 11:30.
    bar: tod (minutes after midnight of the bar's open), pt (prices in ticks, ascending), buy, sell (volume per
    price), delta = sum(buy) - sum(sell), i_last = position of the MNQ 1-minute bar T+4 (None if that minute has no
    bar; the bar is known at its close), and, when the five minutes have at least one MNQ bar, o / h / l / c = the
    MNQ 5-minute bar built from those 1-minute bars. Trade rules use bars opening <= 11:25 (the family's sample)."""
    tab = getattr(ctx, "_yt1D_fp", None)
    if tab is not None:
        return tab
    f = ctx.flow("NQ_footprint_5m").sort_values(["ts", "price"], kind="stable")
    loc = f.ts.dt.tz_localize(None)                      # New York wall-clock time of each bar's open
    day = loc.dt.normalize().to_numpy()
    tod = (loc.dt.hour * 60 + loc.dt.minute).to_numpy()
    tsv = loc.to_numpy()
    pt = np.rint(f.price.to_numpy(float) / T).astype(np.int64)
    buy, sell = f.buy.to_numpy(float), f.sell.to_numpy(float)
    edge = np.flatnonzero(np.r_[True, tsv[1:] != tsv[:-1], True]) if len(f) else np.array([0])
    known = set(ctx.days.index)
    tab = {}
    for a, z in zip(edge[:-1], edge[1:]):
        m = int(tod[a])
        d = pd.Timestamp(day[a])
        if m < 570 or m > 690 or m % 5 or d not in known:
            continue
        lo, hi = ctx.span(d, m, m + 5)
        il = ctx.idx(d, m + 4)
        bar = dict(tod=m, pt=pt[a:z], buy=buy[a:z], sell=sell[a:z],
                   delta=float(buy[a:z].sum() - sell[a:z].sum()), i_last=None if il is None else int(il))
        if hi > lo:
            bar.update(o=float(ctx.O[lo]), h=float(ctx.H[lo:hi].max()), l=float(ctx.L[lo:hi].min()),
                       c=float(ctx.C[hi - 1]))
        tab.setdefault(d, []).append(bar)
    setattr(ctx, "_yt1D_fp", tab)
    return tab
# ---- end of shared helper


# ---- resting orders, one position at a time (copied between s_D03 / s_D05)
def one_at_a_time(ctx, orders, max_per_day=None):
    """Each order is simulated on its own by core.simulate (the harness does every fill); the trades are then taken
    in the order their fills happen:
      * roll days and days without a daily ATR are dropped, as core.run_orders does;
      * an order whose signal bar lies inside an open position (fill bar <= signal bar <= exit bar) was never placed
        (the harness's rule for one position at a time);
      * an order that fills while a position is open, or in the bar that position exits, is lost;
      * two or more orders filling in the same 1-minute bar: same side -> the one nearer the market fills first
        (higher buy limit, lower sell limit; equal prices -> the earlier signal); both sides -> neither is taken
        (which filled first cannot be known), the day counts one trade and stays busy until both would have exited;
      * max_per_day: at most this many trades per cash day.
    Nothing later than a fill bar decides whether that fill is taken."""
    cand = []
    for o in sorted(orders, key=lambda o: o["i"]):
        d = pd.Timestamp(ctx.cdate[o["i"]])
        if d in ctx.roll_dates or d in ctx.noatr_dates or ctx.dayn[o["i"]] < 0:
            continue
        t = core.simulate(ctx, **o)
        if t is not None:
            cand.append((t, o))
    cand.sort(key=lambda x: (x[0]["j"], x[0]["i"]))
    out, held, busy_until, per_day, cur, n = [], [], -1, {}, None, 0
    while n < len(cand):
        j = cand[n][0]["j"]
        grp = []
        while n < len(cand) and cand[n][0]["j"] == j:
            grp.append(cand[n])
            n += 1
        d = ctx.cdate[j]
        if d != cur:
            cur, held = d, []
        grp = [(t, o) for t, o in grp if not any(a <= t["i"] <= b for a, b in held)]
        if not grp or j <= busy_until:
            continue
        if max_per_day is not None and per_day.get(d, 0) >= max_per_day:
            continue
        sides = {o["side"] for _, o in grp}
        if len(sides) > 1:
            k = max(t["k"] for t, _ in grp)
            held.append((j, k))
            busy_until = max(busy_until, k)
            per_day[d] = per_day.get(d, 0) + 1
            continue
        s = sides.pop()
        t, o = min(grp, key=lambda x: (-s * x[1]["price"], x[0]["i"]))
        out.append(t)
        held.append((t["j"], t["k"]))
        busy_until = t["k"]
        per_day[d] = per_day.get(d, 0) + 1
    return out
# ---- end of copied block


def orders(ctx, tol=0.05, level=True, per_day=None):
    out = []
    for d, bars in fp_table(ctx).items():
        day = ctx.days.loc[d]
        atr = float(day.atr)
        by_tod = {b["tod"]: b for b in bars}
        for bar in bars:
            m = bar["tod"]
            prev = by_tod.get(m - 5)                      # the bar that opened five minutes earlier (>= 09:30)
            if m > 685 or bar["i_last"] is None or prev is None:
                continue
            i, o, h, l, c = bar["i_last"], bar["o"], bar["h"], bar["l"], bar["c"]
            x0, x1 = ctx.span(d, m + 5, m + 20)           # the 15 one-minute bars after the signal bar's close
            expire = x1 - 1
            if expire <= i:
                continue
            vol = bar["buy"] + bar["sell"]
            top = vol.max()
            if int((vol == top).sum()) != 1:
                continue                                  # no single highest-volume price
            poc = float(bar["pt"][int(vol.argmax())] * T)
            if bar["delta"] > 0 and prev["delta"] < 0 and poc < min(o, c):
                if level and not (l <= day.pdl + tol * atr or l <= day.onl + tol * atr):
                    continue
                side, price, stop = 1, poc + 1.0, l - T
            elif bar["delta"] < 0 and prev["delta"] > 0 and poc > max(o, c):
                if level and not (h >= day.pdh - tol * atr or h >= day.onh - tol * atr):
                    continue
                side, price, stop = -1, poc - 1.0, h + T
            else:
                continue
            if side * (price - stop) <= 0:
                continue                                  # the limit is not on the trade's side of its stop
            target = core.tick_round(price + side * 2.0 * abs(price - stop))
            out.append(dict(i=i, side=side, etype="limit", price=float(price), expire=int(expire), stop=float(stop),
                            target=float(target), exit_i=int(day.i_end), tag="L" if side > 0 else "S"))
    return out


def trades(ctx, tol=0.05, level=True, per_day=None):
    return one_at_a_time(ctx, orders(ctx, tol=tol, level=level), max_per_day=per_day)
