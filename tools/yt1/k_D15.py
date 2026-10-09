#!/usr/bin/env python3
"""K-D15 - Exhaustion prints (Orderflows), claim check. YT1_SPEC.md:
"New-session-high bars whose total volume at the high price is <= 9 contracts against the rest: share whose high
holds for the next six bars."

Definitions used (fixed before the first run; see notes/K-D15.md):
  * every price here is the footprint's own (NQ): a bar's high = its highest footprint price, the session high = the
    highest high of the day's earlier footprint bars from the 09:30 bar; event bars open 09:35 .. 11:25;
  * exhaustion print = buy + sell at the high price <= 9 contracts (the video's "value of nine"); the rest = > 9;
  * "holds for the next six bars" = none of the next six footprint bars trades above the high (equal is a hold).
    The window ends at the day's last footprint bar (the 11:30 bar), so bars opening after 11:00 have fewer than six
    bars to survive: the headline counts every event with its window cut there, and `full_window_only` gives the
    same for the events that have all six bars (opening by 11:00);
  * low mirror: new-session-low bars, total volume at the low price <= 9, the low holds;
  * every day present in the footprint is counted; pooled = high events and low events together.
The video publishes no figure; the direction claimed is that an exhaustion print marks the end of the move, so its
extreme should hold more often than the rest.
"""
import numpy as np
import pandas as pd
import core

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


# ---- shared event table for the three order-flow claim checks (copied between k_D07 / k_D15 / k_D08)
def extreme_events(ctx):
    """One row per footprint bar that sets a new session high and / or a new session low.
    Session = the day's footprint bars from the 09:30 bar. A bar's high / low here = its highest / lowest footprint
    price (NQ), so the event, the volume at the extreme price and "traded through" are all read on one instrument.
    New session high = the bar's high is above the highest high of ALL the session's earlier bars (so never the
    09:30 bar). Event bars open 09:35 .. 11:25 (family D's sample); outcome windows run to the day's last footprint
    bar (the 11:30 bar, i.e. to 11:35). Columns per event:
      side            +1 a new high, -1 a new low (a bar that is both gives two rows)
      buy_x, sell_x   buy / sell volume at the extreme price
      n_later         footprint bars after it that day;  n_next = min(6, n_later)
      through_end     a later bar that day traded beyond the extreme (>= 1 tick)
      through_6       one of the next six bars did (window cut at the day's last bar)
      up, down        MNQ 5-minute close > open / close < open;   delta   sum(buy) - sum(sell)
      move_6          (MNQ close of the bar six bars later, or of the day's last footprint bar if fewer remain,
                      minus this bar's MNQ close) / the mean MNQ high - low range of the day's 5-minute bars from
                      09:30 up to and including this bar."""
    rows = []
    for d, bars in fp_table(ctx).items():
        if not bars or bars[0]["tod"] != 570:
            continue                                      # no 09:30 bar: the session's start is unknown
        hi = np.array([b["pt"][-1] for b in bars])
        lo = np.array([b["pt"][0] for b in bars])
        rng = np.array([b["h"] - b["l"] if "o" in b else np.nan for b in bars])
        for k in range(1, len(bars)):
            b = bars[k]
            if b["tod"] > 685 or k + 1 >= len(bars):
                continue                                  # outside the sample, or no later bar to look at
            n_later = len(bars) - 1 - k
            n_next = min(6, n_later)
            e = bars[k + n_next]
            ar = np.nanmean(rng[:k + 1]) if np.isfinite(rng[:k + 1]).any() else np.nan
            ok = "o" in b and "o" in e and ar == ar and ar > 0
            base = dict(date=d, tod=b["tod"], n_later=n_later, n_next=n_next, delta=b["delta"],
                        up=bool(b["c"] > b["o"]) if "o" in b else None,
                        down=bool(b["c"] < b["o"]) if "o" in b else None,
                        move_6=(e["c"] - b["c"]) / ar if ok else np.nan)
            if hi[k] > hi[:k].max():
                rows.append(dict(base, side=1, buy_x=float(b["buy"][-1]), sell_x=float(b["sell"][-1]),
                                 through_end=bool((hi[k + 1:] > hi[k]).any()),
                                 through_6=bool((hi[k + 1:k + 7] > hi[k]).any())))
            if lo[k] < lo[:k].min():
                rows.append(dict(base, side=-1, buy_x=float(b["buy"][0]), sell_x=float(b["sell"][0]),
                                 through_end=bool((lo[k + 1:] < lo[k]).any()),
                                 through_6=bool((lo[k + 1:k + 7] < lo[k]).any())))
    cols = ["date", "tod", "side", "buy_x", "sell_x", "n_later", "n_next", "through_end", "through_6", "up", "down",
            "delta", "move_6"]
    return pd.DataFrame(rows, columns=cols)


def _rate(x):
    """count, hits and share of a bool series (share None when empty)."""
    n = int(len(x))
    return dict(n=n, hits=int(x.sum()) if n else 0, rate=round(float(x.mean()), 4) if n else None)


def _diff(a, b):
    return None if a is None or b is None else round(a - b, 4)
# ---- end of shared event table


NAME = "Exhaustion prints: new session high / low with <= 9 contracts at the extreme, holds for six bars"
CLAIMED = "no figure published; direction claimed: an extreme with <= 9 contracts holds more often than the rest"
THIN = 9.0


def _block(x):
    thin = ((x.buy_x + x.sell_x) <= THIN).to_numpy()
    hold = ~x.through_6
    a, b = _rate(hold[thin]), _rate(hold[~thin])
    return dict(events=int(len(x)), exhaustion=a, rest=b, all=_rate(hold),
                difference_exhaustion_minus_rest=_diff(a["rate"], b["rate"]), claimed=CLAIMED)


def measure(ctx):
    x = extreme_events(ctx)
    days = fp_table(ctx)
    full = x[x.n_later >= 6]
    res = dict(claim="a new session high (low) with <= 9 contracts traded at the extreme price holds for the next "
                     "six 5-minute bars more often than one with more",
               claimed=CLAIMED, span=f"{min(days).date()} -> {max(days).date()}", footprint_days=len(days),
               rate_is="share of events whose extreme is not traded through in the next six footprint bars "
                       "(window cut at the day's last footprint bar)",
               highs=_block(x[x.side > 0]), lows=_block(x[x.side < 0]), pooled=_block(x),
               full_window_only=dict(note="events with all six later bars (opening by 11:00)",
                                     highs=_block(full[full.side > 0]), lows=_block(full[full.side < 0]),
                                     pooled=_block(full)))
    res["by_year_pooled"] = {int(y): _block(g) for y, g in x.groupby(pd.DatetimeIndex(x.date).year)}
    return res


def _line(nm, r):
    a, b = r["exhaustion"], r["rest"]
    fa = f"{a['rate']:.1%}" if a["n"] else "-"
    d = r["difference_exhaustion_minus_rest"]
    return (f"{nm:<7} events {r['events']:>5}  <= 9 contracts: holds {a['hits']}/{a['n']} = {fa}   rest: holds "
            f"{b['hits']}/{b['n']} = " + (f"{b['rate']:.1%}" if b["n"] else "-") + "   difference " + (f"{d:+.1%}" if d is not None else "-"))


def show(res):
    print(res["claim"], "  ", res["span"], f"  ({res['footprint_days']} footprint days)")
    print("claimed:", res["claimed"])
    for nm in ("highs", "lows", "pooled"):
        print(_line(nm, res[nm]))
    print("full six-bar window only (events opening by 11:00):")
    for nm in ("highs", "lows", "pooled"):
        print(_line(nm, res["full_window_only"][nm]))
    print("pooled by year: " + "  ".join(
        f"{y} <=9 " + (f"{v['exhaustion']['rate']:.1%}" if v['exhaustion']['n'] else "-")
        + f" (n {v['exhaustion']['n']}) rest " + (f"{v['rest']['rate']:.1%}" if v['rest']['n'] else "-") + f" (n {v['rest']['n']})"
        for y, v in res["by_year_pooled"].items()))
