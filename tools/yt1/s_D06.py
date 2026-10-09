#!/usr/bin/env python3
"""D06 - Trapped traders (Trader Dale), YT1_SPEC.md Family D.

Bar N has a buy imbalance in its top 3 price rows; bar N+1 closes below the lowest such imbalance price -> short at
that close. Stop: beyond the higher of the two bars' highs. Target 2R. Mirror. Neighbours: top 2, top 4 rows.
NQ 5-minute footprint bars opening 09:30 .. 11:25; one position at a time; filled on MNQ 1-minute bars.

Family D common: buy imbalance at price p = buy[p] >= 3 x sell[p - 1 tick] and buy[p] >= 10 contracts; sell
imbalance at p = sell[p] >= 3 x buy[p + 1 tick] and sell[p] >= 10.

Readings added to the spec text (all fixed before the first run; see notes/D06.md):
  * "top 3 price rows" = the three highest rows of bar N's footprint table (one row per price traded), mirror the
    three lowest; a price with no row traded nothing, so its volume in the diagonal comparison is 0;
  * bars N and N+1 are footprint bars five minutes apart, both opening 09:30 .. 11:25; bar N+1's close and the two
    bars' highs / lows are those of the MNQ 1-minute bars of their five minutes; the footprint's imbalance price is
    compared with the MNQ close unchanged; the signal is taken at the close of the MNQ 1-minute bar T+4 of bar N+1;
  * "closes below" is strict; the mirror = bar N has a sell imbalance in its bottom 3 rows and bar N+1 closes above
    the highest such price -> long, stop beyond the lower of the two lows;
  * a bar N+1 that gives a short and a long at the same close gives no trade;
  * stop = 1 tick beyond; target = close -/+ 2 x |close - stop|, on the tick grid;
  * trade count as D03: any number a day, one position at a time (base); `day1...` = one trade per day.
"""
import numpy as np
import pandas as pd
import core

ID = "D06"
NAME = "Trapped traders (Trader Dale)"
VARIANTS = {
    "base": dict(rows=3),
    "nb1": dict(rows=2),
    "nb2": dict(rows=4),
    # not in the spec's list: the other reading of the trade count (one trade per day), same three row counts
    "day1": dict(rows=3, per_day=1),
    "day1_nb1": dict(rows=2, per_day=1),
    "day1_nb2": dict(rows=4, per_day=1),
}
T = core.TICK
FLOOR = 10.0                                              # contracts (the spec's floor for an imbalance)
RATIO = 3.0


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


def orders(ctx, rows=3, per_day=None):
    out = []
    for d, bars in fp_table(ctx).items():
        day = ctx.days.loc[d]
        by_tod = {b["tod"]: b for b in bars}
        for bar in bars:                                  # bar N
            nxt = by_tod.get(bar["tod"] + 5)              # bar N+1
            if nxt is None or nxt["tod"] > 685 or nxt["i_last"] is None or "o" not in bar:
                continue
            bi, si = imbalances(bar, RATIO)
            pt, c = bar["pt"], nxt["c"]
            top, bot = bi[-rows:], si[:rows]
            short = bool(top.any()) and c < pt[-rows:][top].min() * T
            long_ = bool(bot.any()) and c > pt[:rows][bot].max() * T
            if short == long_:
                continue                                  # no signal, or both sides at the same close
            if short:
                side, stop = -1, max(bar["h"], nxt["h"]) + T
            else:
                side, stop = 1, min(bar["l"], nxt["l"]) - T
            target = core.tick_round(c + side * 2.0 * abs(c - stop))
            out.append(dict(i=nxt["i_last"], side=side, etype="close", stop=float(stop), target=float(target),
                            exit_i=int(day.i_end), tag="L" if side > 0 else "S"))
    return out


def trades(ctx, rows=3, per_day=None):
    return core.run_orders(ctx, orders(ctx, rows=rows), max_per_day=per_day)
