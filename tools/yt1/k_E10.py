#!/usr/bin/env python3
"""K-E10 - first hour and 15:00 continuation into the close (edgeful), claim check.

Claims (edgeful videos, six-month samples; research note E, entry 10):
  green first hour (09:30-10:30) -> the day closes above its open: 76-79 % on NQ; red -> closes below: 72-72.5 %
  (82 % in a three-month sample); price above the day's open at 15:00 -> the day closes above its open: about 90 %
  on YM; above the open and above the middle of the day's range at 15:00 -> 91 % on ES.

Definitions used (fixed before the first run; see notes/K-E10.md):
  * day's open = the 09:30 bar's open; "10:30 price" = the close of the bar stamped 10:29; "15:00 price" = the
    close of the bar stamped 14:59; "16:00 close" = the close of the day's last 1-minute bar before 16:00 (on an
    early-close day, its last bar before the halt).
  * green = that price strictly above the day's open, red = strictly below, equal = flat (counted, in no group).
  * what the videos claim: green -> 16:00 close > day's open (red: <).
    what a trade could capture: green -> 16:00 close > the 10:30 (15:00) price (red: <). Equal closes are not hits;
    their number is given.
  * 15:00 with the range filter (the E10b condition): also above (below) the middle of the 09:30-14:59 range.
  * every cash day of the day table is counted (roll days included); the first-hour figures are also given without
    early-close days; the 15:00 figures need a 14:59 bar inside the session, so early-close days drop out.
"""
import pandas as pd
import core

NAME = "First hour / 15:00 continuation: day closes with the sign of its first hour (of its 15:00 position)"
CLAIMS = {
    "first_hour": {"green": "76-79 %", "red": "72-72.5 % (82 % in a 3-month sample)"},
    "at_1500": {"green": "about 90 % (YM)", "red": None},
    "at_1500_and_range_middle": {"green": "91 % (ES)", "red": None},
}


def _rows(ctx):
    rows = []
    for d, day in ctx.days.iterrows():
        i0 = int(day.i_open)
        lo, hi = ctx.span(d, "09:30", "16:00")
        if hi - 1 <= i0:
            continue
        o, c16 = float(ctx.O[i0]), float(ctx.C[hi - 1])
        r = dict(date=d, early=bool(day.early), o=o, c16=c16, p1030=None, p1500=None, mid1500=None)
        i = ctx.idx(d, "10:29")
        if i is not None and i0 < int(i) < hi - 1:
            r["p1030"] = float(ctx.C[int(i)])
        i = ctx.idx(d, "14:59")
        if i is not None and i0 < int(i) < hi - 1 and not day.early:
            i = int(i)
            r["p1500"] = float(ctx.C[i])
            r["mid1500"] = (float(ctx.H[i0:i + 1].max()) + float(ctx.L[i0:i + 1].min())) / 2.0
        rows.append(r)
    return pd.DataFrame(rows)


def _group(x, col, sign, claimed):
    """x: the days of one group (all green or all red by `col`). sign +1 green / -1 red."""
    n = int(len(x))

    def cnt(m):
        return int(m.sum())

    def rate(k):
        return round(k / n, 4) if n else None

    if sign > 0:
        a, b = x.c16 > x.o, x.c16 > x[col]
    else:
        a, b = x.c16 < x.o, x.c16 < x[col]
    ka, kb = cnt(a), cnt(b)
    return dict(n=n,
                closes_same_side_of_open=ka, rate_closes_same_side_of_open=rate(ka), claimed=claimed,
                closes_beyond_signal_price=kb, rate_closes_beyond_signal_price=rate(kb),
                closes_equal_to_signal_price=cnt(x.c16 == x[col]))


def _block(x, col, claims, mid=False):
    x = x[x[col].notna()]
    g, r = x[col] > x.o, x[col] < x.o
    if mid:
        g, r = g & (x[col] > x.mid1500), r & (x[col] < x.mid1500)
    out = dict(days=int(len(x)), green=_group(x[g], col, 1, claims["green"]), red=_group(x[r], col, -1, claims["red"]))
    if mid:
        out["neither"] = int((~g & ~r).sum())
    else:
        out["flat"] = int((x[col] == x.o).sum())
    # reference: what any day does, with no signal
    n = len(x)
    out["all_days"] = dict(n=int(n),
                           rate_close_above_open=round(float((x.c16 > x.o).mean()), 4) if n else None,
                           rate_close_above_signal_price=round(float((x.c16 > x[col]).mean()), 4) if n else None)
    return out


def measure(ctx):
    x = _rows(ctx)
    res = dict(claim="green first hour -> day closes above its open 76-79 %; red -> below 72-72.5 %; "
                     "above the open at 15:00 -> closes above the open about 90 % (YM), 91 % with the range middle (ES)",
               span=f"{ctx.days.index[0].date()} -> {ctx.days.index[-1].date()}", days=int(len(x)),
               early_close_days=int(x.early.sum()))
    res["first_hour"] = _block(x, "p1030", CLAIMS["first_hour"])
    res["first_hour"]["without_early_close_days"] = _block(x[~x.early], "p1030", CLAIMS["first_hour"])
    res["at_1500"] = _block(x, "p1500", CLAIMS["at_1500"])
    res["at_1500_and_range_middle"] = _block(x, "p1500", CLAIMS["at_1500_and_range_middle"], mid=True)
    yr = pd.DatetimeIndex(x.date).year
    for name, col, mid in (("first_hour", "p1030", False), ("at_1500", "p1500", False),
                           ("at_1500_and_range_middle", "p1500", True)):
        by = {}
        for y in sorted(set(yr)):
            b = _block(x[yr == y], col, CLAIMS[name], mid)
            by[int(y)] = {s: dict(n=b[s]["n"], rate_closes_same_side_of_open=b[s]["rate_closes_same_side_of_open"],
                                  rate_closes_beyond_signal_price=b[s]["rate_closes_beyond_signal_price"])
                          for s in ("green", "red")}
        res[name]["by_year"] = by
    return res


def show(res):
    print(res["claim"])
    print(f"span {res['span']}   cash days {res['days']} (early-close {res['early_close_days']})")
    names = (("first_hour", "first hour (10:30 price vs the 09:30 open)", "10:30"),
             ("at_1500", "15:00 price vs the 09:30 open", "15:00"),
             ("at_1500_and_range_middle", "15:00 price vs the open AND the middle of the range so far", "15:00"))

    def line(lbl, g, t):
        if not g["n"]:
            return f"  {lbl:<6} n 0"
        side = "above" if lbl == "green" else "below"
        return (f"  {lbl:<6} n {g['n']:>4}   closes {side} the open: {g['closes_same_side_of_open']} = "
                f"{g['rate_closes_same_side_of_open']:.1%}  (claimed {g['claimed'] or 'not stated'})   "
                f"closes {side} the {t} price: {g['closes_beyond_signal_price']} = "
                f"{g['rate_closes_beyond_signal_price']:.1%}  (equal {g['closes_equal_to_signal_price']})")

    for key, title, t in names:
        b = res[key]
        rest = f"flat {b['flat']}" if "flat" in b else f"neither {b['neither']}"
        print(f"{title}: days {b['days']}, {rest}")
        for s in ("green", "red"):
            print(line(s, b[s], t))
        a = b["all_days"]
        print(f"  any day: closes above the open {a['rate_close_above_open']:.1%}, above the {t} price "
              f"{a['rate_close_above_signal_price']:.1%}")
        if "without_early_close_days" in b:
            w = b["without_early_close_days"]
            print("  without early-close days: " + "; ".join(
                f"{s} n {w[s]['n']} {w[s]['rate_closes_same_side_of_open']:.1%} / {w[s]['rate_closes_beyond_signal_price']:.1%}"
                for s in ("green", "red")))
        print("  by year (n, same side of the open / beyond the signal price): " + "  ".join(
            f"{y} G {v['green']['n']} {v['green']['rate_closes_same_side_of_open'] or 0:.0%}/{v['green']['rate_closes_beyond_signal_price'] or 0:.0%}"
            f" R {v['red']['n']} {v['red']['rate_closes_same_side_of_open'] or 0:.0%}/{v['red']['rate_closes_beyond_signal_price'] or 0:.0%}"
            for y, v in b["by_year"].items()))
