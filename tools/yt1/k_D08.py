#!/usr/bin/env python3
"""K-D08 - Delta divergence (Trader Dale), claim check. YT1_SPEC.md:
"New-session-high up bars with negative delta against the rest: mean move over the next six bars in units of the
bar-range average."

Definitions used (fixed before the first run; see notes/K-D08.md):
  * new session high: on the footprint's own prices (a bar's high = its highest footprint price, above the highest
    high of the day's earlier footprint bars from the 09:30 bar); event bars open 09:35 .. 11:25;
  * up bar = the MNQ 5-minute bar of those five minutes closes above its open; delta = sum(buy) - sum(sell) of the
    footprint bar; divergence = an up bar with delta < 0;
  * "the rest" (headline) = the other new-session-high UP bars (delta >= 0), so the two groups differ only in the
    sign of delta; `rest_all_new_highs` gives the wider reading (every other new-session-high bar, up or not);
  * move = MNQ close of the bar six bars later minus the event bar's MNQ close; when fewer than six footprint bars
    remain, the day's last footprint bar (11:30, closing 11:35) is used; `full_window_only` keeps the events with
    all six bars (opening by 11:00);
  * bar-range average = the mean high - low range of that day's MNQ 5-minute bars from 09:30 up to and including the
    event bar; the move is divided by it;
  * low mirror: new-session-low down bars with positive delta against the other new-session-low down bars;
  * pooled: highs and lows together with the move signed toward the reversal (- move after a high, + move after a
    low), so a positive pooled mean = price went back; every day present in the footprint is counted.
The video publishes no figure; the direction claimed is that an up bar at a high with negative delta warns of a
reversal, so its mean move should be lower than the rest's.
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


NAME = "Delta divergence: new-session-high up bars with negative delta, mean move over the next six bars"
CLAIMED = "no figure published; direction claimed: lower after a high (higher after a low) than the rest"


def _mean(v):
    v = np.asarray(v, float)
    v = v[np.isfinite(v)]
    n = int(len(v))
    return dict(n=n, mean=round(float(v.mean()), 4) if n else None,
                sd=round(float(v.std(ddof=1)), 4) if n > 1 else None,
                share_down=round(float((v < 0).mean()), 4) if n else None)


def _block(x, signed):
    """x: events of one side or both. signed=False: raw move (up = +). signed=True: move toward the reversal."""
    mv = (-x.side * x.move_6) if signed else x.move_6
    with_bar = ((x.side > 0) & (x.up == True)) | ((x.side < 0) & (x.down == True))      # bar closes with the move
    div = with_bar & (x.side * x.delta < 0)                                             # delta against the bar
    rest = with_bar & ~div
    a, b, c = _mean(mv[div]), _mean(mv[rest]), _mean(mv[~div])
    return dict(events=int(len(x)), divergence=a, rest=b, difference_divergence_minus_rest=_diff(a["mean"], b["mean"]),
                rest_all_new_extremes=c, difference_vs_all_new_extremes=_diff(a["mean"], c["mean"]), claimed=CLAIMED)


def _three(x):
    return dict(highs=_block(x[x.side > 0], False), lows=_block(x[x.side < 0], False), pooled=_block(x, True))


def measure(ctx):
    x = extreme_events(ctx)
    days = fp_table(ctx)
    res = dict(claim="a new-session-high up bar with negative delta is followed by a weaker move over the next six "
                     "5-minute bars than a new-session-high up bar with positive delta (low mirror)",
               claimed=CLAIMED, span=f"{min(days).date()} -> {max(days).date()}", footprint_days=len(days),
               move_is="(MNQ close six bars later, or of the day's last footprint bar, minus the event bar's close) "
                       "/ mean high - low of the day's 5-minute bars up to the event bar; highs and lows: raw sign; "
                       "pooled: signed toward the reversal (positive = price went back)",
               share_down_is="share of events with a negative value of that same number")
    res.update(_three(x))
    res["full_window_only"] = dict(note="events with all six later bars (opening by 11:00)", **_three(x[x.n_later >= 6]))
    return res


def _line(nm, r):
    a, b, c = r["divergence"], r["rest"], r["rest_all_new_extremes"]

    def f(v):
        return f"{v['mean']:+.3f} (n {v['n']})" if v["n"] else "- (n 0)"

    d = r["difference_divergence_minus_rest"]
    return (f"{nm:<7} events {r['events']:>5}  divergence {f(a)}   rest {f(b)}   difference "
            + (f"{d:+.3f}" if d is not None else "-") + f"   | against every other new extreme {f(c)}")


def show(res):
    print(res["claim"], "  ", res["span"], f"  ({res['footprint_days']} footprint days)")
    print("claimed:", res["claimed"])
    print("mean move over the next six bars, in bar-range averages (pooled = signed toward the reversal):")
    for nm in ("highs", "lows", "pooled"):
        print(_line(nm, res[nm]))
    print("full six-bar window only (events opening by 11:00):")
    for nm in ("highs", "lows", "pooled"):
        print(_line(nm, res["full_window_only"][nm]))
