#!/usr/bin/env python3
"""K-D07 - Unfinished auctions (Trader Dale), claim check. YT1_SPEC.md:
"5-minute footprint bars that set a new session high: share whose high is traded through by 11:35, split by
unfinished (both buy and sell volume at the high price) and finished (no sell volume there). Low mirror."

Definitions used (fixed before the first run; see notes/K-D07.md):
  * every price here is the footprint's own (NQ): a bar's high = its highest footprint price, the session high = the
    highest high of the day's earlier footprint bars from the 09:30 bar, "traded through" = a later footprint bar
    of the day (through the 11:30 bar, i.e. by 11:35) trades at least one tick beyond it;
  * event bars open 09:35 .. 11:25 (family D's sample; the 09:30 bar has no earlier bar, the 11:30 bar no later one);
  * unfinished high = buy > 0 and sell > 0 at the high price; finished high = sell = 0 there. A high with sell
    volume only (buy = 0) is neither and is counted apart. Low mirror: unfinished = both sides traded at the low
    price; finished = no buy volume there; buy volume only = counted apart;
  * every day present in the footprint is counted (roll days too: nothing here compares two contracts);
  * pooled = the high events and the low events together (an outside bar can give one of each).
The claim has no published figure: Dale says the market "likes to test" a failed (unfinished) auction, so the
direction claimed is unfinished > finished.
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


NAME = "Unfinished auctions: new session high / low traded through by 11:35, unfinished vs finished"
CLAIMED = "no figure published; direction claimed: unfinished extremes are traded through more often than finished"


def _block(x):
    both = ((x.buy_x > 0) & (x.sell_x > 0)).to_numpy()
    fin = np.where(x.side > 0, x.sell_x == 0, x.buy_x == 0)          # nothing traded against the move at the extreme
    oth = ~both & ~fin
    u, f, o = _rate(x.through_end[both]), _rate(x.through_end[fin]), _rate(x.through_end[oth])
    return dict(events=int(len(x)), unfinished=u, finished=f, other_one_sided=o, all=_rate(x.through_end),
                difference_unfinished_minus_finished=_diff(u["rate"], f["rate"]), claimed=CLAIMED)


def measure(ctx):
    x = extreme_events(ctx)
    days = fp_table(ctx)
    res = dict(claim="a new session high (low) with both buy and sell volume at the extreme price is traded "
                     "through by 11:35 more often than one with volume on one side only",
               claimed=CLAIMED, span=f"{min(days).date()} -> {max(days).date()}", footprint_days=len(days),
               rate_is="share of events whose extreme a later footprint bar of the day trades through (>= 1 tick)",
               highs=_block(x[x.side > 0]), lows=_block(x[x.side < 0]), pooled=_block(x))
    res["by_year_pooled"] = {int(y): _block(g) for y, g in x.groupby(pd.DatetimeIndex(x.date).year)}
    return res


def _p(v):
    return f"{v:.1%}" if v is not None else "-"


def show(res):
    print(res["claim"], "  ", res["span"], f"  ({res['footprint_days']} footprint days)")
    print("claimed:", res["claimed"])
    for nm in ("highs", "lows", "pooled"):
        r = res[nm]
        u, f, o = r["unfinished"], r["finished"], r["other_one_sided"]
        d = r["difference_unfinished_minus_finished"]
        print(f"{nm:<7} events {r['events']:>5}  unfinished {u['hits']}/{u['n']} = {_p(u['rate'])}   finished "
              f"{f['hits']}/{f['n']} = {_p(f['rate'])}   difference " + (f"{d:+.1%}" if d is not None else "-")
              + f"   (other one-sided {o['hits']}/{o['n']} = {_p(o['rate'])}; all {_p(r['all']['rate'])})")
    print("pooled by year: " + "  ".join(
        f"{y} unf {_p(v['unfinished']['rate'])} (n {v['unfinished']['n']}) fin {_p(v['finished']['rate'])}"
        f" (n {v['finished']['n']})" for y, v in res["by_year_pooled"].items()))
