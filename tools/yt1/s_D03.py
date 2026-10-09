#!/usr/bin/env python3
"""D03 - Stacked-imbalance pullback (ATAS), YT1_SPEC.md Family D.

Signal bar (NQ 5-minute footprint bars opening 09:30 .. 11:25): an up bar with three or more buy imbalances on
consecutive prices, upper wick <= 25 % of its range, positive delta. Entry: buy limit 1 tick above the top of the
highest such stack, resting to 11:59. Stop: 2 ticks below that stack's bottom. Target 2R. Mirror for shorts.
Neighbours: imbalance ratio 2.5 and 4. One position at a time.

Family D common: buy imbalance at price p = buy[p] >= ratio x sell[p - 1 tick] and buy[p] >= 10 contracts; sell
imbalance at p = sell[p] >= ratio x buy[p + 1 tick] and sell[p] >= 10. Trades are filled on MNQ 1-minute bars at the
footprint's prices (the footprint's NQ prices are used as MNQ prices unchanged).

Readings added to the spec text (all fixed before the first run; see notes/D03.md):
  * a price with no footprint row traded nothing, so its volume in the diagonal comparison is 0 (the lowest row of a
    bar is a buy imbalance when its buy volume is >= 10, and likewise a price just above an untraded price);
  * the bar's open / high / low / close (up bar, wick, range) are those of the MNQ 1-minute bars of its five minutes;
    delta = sum(buy) - sum(sell) of the footprint rows; a footprint bar opening at T is used at the close of the MNQ
    1-minute bar T+4, and not at all when that minute has no MNQ bar;
  * a stack = a maximal run of >= 3 adjacent ticks that are all buy imbalances; "the highest" = the one with the
    highest top; the mirror uses the lowest stack of sell imbalances (limit 1 tick below its bottom, stop 2 ticks
    above its top) on a down bar with lower wick <= 25 % of the range and negative delta;
  * "One position at a time" (family D) is read as family C's frame: any number of trades a day, one position at a
    time. The other reading (the common rule's one trade per day) is kept as `day1`, `day1_nb1`, `day1_nb2`;
  * every signal bar places its own limit; they all rest to the 11:59 bar. One position at a time is decided in the
    order things happen (see one_at_a_time): an order signalled while a position is open is not placed, and an order
    that would fill while a position is open is lost;
  * target = limit price +/- 2 x |limit price - stop| (a limit filled at a better open keeps it).
"""
import numpy as np
import pandas as pd
import core

ID = "D03"
NAME = "Stacked-imbalance pullback (ATAS)"
VARIANTS = {
    "base": dict(ratio=3.0),
    "nb1": dict(ratio=2.5),
    "nb2": dict(ratio=4.0),
    # not in the spec's list: the other reading of the trade count (one trade per day), same three ratios
    "day1": dict(ratio=3.0, per_day=1),
    "day1_nb1": dict(ratio=2.5, per_day=1),
    "day1_nb2": dict(ratio=4.0, per_day=1),
}
T = core.TICK
FLOOR = 10.0                                              # contracts (the spec's floor for an imbalance)


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


def imbalances(bar, ratio):
    """(buy_imb, sell_imb): bool per footprint row. Buy imbalance at p: buy[p] >= ratio x sell[p - 1 tick] and
    buy[p] >= 10; sell imbalance at p: sell[p] >= ratio x buy[p + 1 tick] and sell[p] >= 10. A price with no row
    has volume 0."""
    pt, b, s = bar["pt"], bar["buy"], bar["sell"]
    adj = np.diff(pt) == 1                               # row k+1 is exactly one tick above row k
    s_below, b_above = np.zeros(len(pt)), np.zeros(len(pt))
    s_below[1:][adj] = s[:-1][adj]
    b_above[:-1][adj] = b[1:][adj]
    return (b >= ratio * s_below) & (b >= FLOOR), (s >= ratio * b_above) & (s >= FLOOR)
# ---- end of shared helper


def stacks(pt, flag, n=3):
    """Maximal runs of >= n adjacent ticks that are all flagged, as (bottom tick, top tick), lowest first."""
    out, k, m = [], 0, len(pt)
    while k < m:
        if not flag[k]:
            k += 1
            continue
        e = k
        while e + 1 < m and flag[e + 1] and pt[e + 1] - pt[e] == 1:
            e += 1
        if e - k + 1 >= n:
            out.append((int(pt[k]), int(pt[e])))
        k = e + 1
    return out


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


def orders(ctx, ratio=3.0, per_day=None):
    out = []
    for d, bars in fp_table(ctx).items():
        day = ctx.days.loc[d]
        e0, e1 = ctx.span(d, "09:30", "12:00")
        if e1 <= e0:
            continue
        expire = e1 - 1                                   # the 11:59 bar (or the last bar before noon)
        for bar in bars:
            if bar["tod"] > 685 or bar["i_last"] is None:
                continue
            i, o, h, l, c = bar["i_last"], bar["o"], bar["h"], bar["l"], bar["c"]
            if i >= expire:
                continue
            rng = h - l
            if c > o and bar["delta"] > 0 and (h - c) <= 0.25 * rng:
                st = stacks(bar["pt"], imbalances(bar, ratio)[0])
                if not st:
                    continue
                bot, top = max(st, key=lambda x: x[1])   # the highest stack
                price, stop = (top + 1) * T, (bot - 2) * T
                side = 1
            elif c < o and bar["delta"] < 0 and (c - l) <= 0.25 * rng:
                st = stacks(bar["pt"], imbalances(bar, ratio)[1])
                if not st:
                    continue
                bot, top = min(st, key=lambda x: x[0])   # the lowest stack
                price, stop = (bot - 1) * T, (top + 2) * T
                side = -1
            else:
                continue
            target = core.tick_round(price + side * 2.0 * abs(price - stop))
            out.append(dict(i=i, side=side, etype="limit", price=float(price), expire=int(expire), stop=float(stop),
                            target=float(target), exit_i=int(day.i_end), tag="L" if side > 0 else "S"))
    return out


def trades(ctx, ratio=3.0, per_day=None):
    return one_at_a_time(ctx, orders(ctx, ratio=ratio), max_per_day=per_day)
