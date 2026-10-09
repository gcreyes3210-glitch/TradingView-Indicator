#!/usr/bin/env python3
"""K-E07 - NQ Stats RTH Breaks: where the 09:30 open sits against the previous day's RTH range, and what follows.

Spec text (YT1_SPEC.md, K-E07): open above the previous RTH high: closes above it (claimed 69.9 %), does not trade
the previous RTH low (88.1 %). Open below: 59.5 %, 90.4 %. Open inside: neither side 17.7 %, one 74.0 %, both 8.3 %.

Definitions used (fixed before the first run; see notes/K-E07.md):
  * previous RTH high / low = the previous cash day's 09:30-16:00 high / low (day table pdh / pdl).
  * open above = the 09:30 bar's open > that high; below = open < that low; inside = anything else (equal = inside).
  * breach (the study's own definition, the headline): a bar of today's cash session extends MORE than 1 tick beyond
    the level, i.e. session high >= level + 2 ticks, or session low <= level - 2 ticks.
    Two other definitions are reported beside it: 'through' (>= 1 tick beyond) and 'touch' (trades at the level).
  * closes above / below = the last close of the cash session (the 16:00 close; the halt on an early-close day)
    strictly above the previous high / below the previous low.
  * days: every cash day with a previous cash day, EXCEPT contract-roll days (the previous day's levels belong to the
    other contract). The same figures with the roll days left in, and without early-close days, are given beside.
    (Added after the first run, the headline untouched: the figures without early-close days AND the day after one.
    The day table counts holiday half-sessions as cash days, so on the day after one the "previous RTH range" is a
    09:30-13:00 holiday range.)
"""
import numpy as np
import pandas as pd
import core

NAME = "RTH breaks: the 09:30 open against the previous RTH range (close beyond it, the far side, inside-open days)"
CLAIM = dict(share_above=654 / 2488, share_below=363 / 2488, share_inside=1471 / 2488,
             above_closes_above=0.699, above_low_not_breached=0.881,
             below_closes_below=0.595, below_high_not_breached=0.904,
             inside_neither=0.177, inside_one=0.740, inside_both=0.083)
SPOKEN = dict(inside_neither=0.14, inside_one=0.73, inside_both=0.13, above_low_not_breached=0.84)   # archived video


def _table(ctx):
    D = ctx.days
    x = D[D.pdh.notna()][["o930", "rth_h", "rth_l", "rth_c", "pdh", "pdl", "roll", "early"]].copy()
    x["prev_early"] = D.early.shift(1).reindex(x.index).astype(bool)
    x["cls"] = np.where(x.o930 > x.pdh, "above", np.where(x.o930 < x.pdl, "below", "inside"))
    return x


def _rate(m):
    return round(float(np.mean(m)), 4) if len(m) else None


def _block(x, beyond):
    """beyond = points past the level that count as a breach of it (0 = a touch counts)."""
    hi_b = (x.rth_h >= x.pdh + beyond).to_numpy()
    lo_b = (x.rth_l <= x.pdl - beyond).to_numpy()
    ab, be, ins = (x.cls == "above").to_numpy(), (x.cls == "below").to_numpy(), (x.cls == "inside").to_numpy()
    n = len(x)
    out = dict(days=int(n))
    out["open_above"] = dict(
        n=int(ab.sum()), share_of_days=_rate(ab), claimed_share=round(CLAIM["share_above"], 4),
        closes_above_prev_high=_rate((x.rth_c > x.pdh).to_numpy()[ab]), claimed_closes_above=CLAIM["above_closes_above"],
        prev_low_not_breached=_rate(~lo_b[ab]), claimed_low_not_breached=CLAIM["above_low_not_breached"])
    out["open_below"] = dict(
        n=int(be.sum()), share_of_days=_rate(be), claimed_share=round(CLAIM["share_below"], 4),
        closes_below_prev_low=_rate((x.rth_c < x.pdl).to_numpy()[be]), claimed_closes_below=CLAIM["below_closes_below"],
        prev_high_not_breached=_rate(~hi_b[be]), claimed_high_not_breached=CLAIM["below_high_not_breached"])
    k = hi_b[ins].astype(int) + lo_b[ins].astype(int)
    out["open_inside"] = dict(
        n=int(ins.sum()), share_of_days=_rate(ins), claimed_share=round(CLAIM["share_inside"], 4),
        neither_side=_rate(k == 0), claimed_neither=CLAIM["inside_neither"],
        one_side=_rate(k == 1), claimed_one=CLAIM["inside_one"],
        both_sides=_rate(k == 2), claimed_both=CLAIM["inside_both"],
        one_side_high_only=_rate((k == 1) & hi_b[ins]), one_side_low_only=_rate((k == 1) & lo_b[ins]))
    return out


def measure(ctx):
    T = core.TICK
    x = _table(ctx)
    h = x[~x.roll]
    res = dict(claim="open above the previous RTH high: closes above it 69.9 %, previous low not breached 88.1 %; open "
                     "below: 59.5 %, 90.4 %; open inside: neither side 17.7 %, one 74.0 %, both 8.3 %",
               span=f"{x.index[0].date()} -> {x.index[-1].date()}",
               headline=_block(h, 2 * T),
               spoken_in_the_archived_video=SPOKEN,
               other_breach_definitions=dict(through_by_1_tick=_block(h, T), touch=_block(h, 0.0)),
               with_roll_days=_block(x, 2 * T),
               without_early_close_days=_block(h[~h.early], 2 * T),
               without_early_close_days_and_the_day_after_one=_block(h[~h.early & ~h.prev_early], 2 * T),
               by_year={})
    for y, g in h.groupby(h.index.year):
        b = _block(g, 2 * T)
        res["by_year"][int(y)] = dict(
            days=b["days"], n_above=b["open_above"]["n"], above_closes_above=b["open_above"]["closes_above_prev_high"],
            above_low_not_breached=b["open_above"]["prev_low_not_breached"], n_below=b["open_below"]["n"],
            below_closes_below=b["open_below"]["closes_below_prev_low"],
            below_high_not_breached=b["open_below"]["prev_high_not_breached"], n_inside=b["open_inside"]["n"],
            inside_neither=b["open_inside"]["neither_side"], inside_one=b["open_inside"]["one_side"],
            inside_both=b["open_inside"]["both_sides"])
    return res


def _p(v):
    return " n/a " if v is None else f"{v:.1%}"


def _line(tag, b):
    a, w, i = b["open_above"], b["open_below"], b["open_inside"]
    print(f"{tag}  days {b['days']}")
    print(f"   open above  n {a['n']:>4} ({_p(a['share_of_days'])} of days, claimed {_p(a['claimed_share'])})"
          f"   closes above the previous high {_p(a['closes_above_prev_high'])} (claimed {_p(a['claimed_closes_above'])})"
          f"   previous low not breached {_p(a['prev_low_not_breached'])} (claimed {_p(a['claimed_low_not_breached'])})")
    print(f"   open below  n {w['n']:>4} ({_p(w['share_of_days'])} of days, claimed {_p(w['claimed_share'])})"
          f"   closes below the previous low  {_p(w['closes_below_prev_low'])} (claimed {_p(w['claimed_closes_below'])})"
          f"   previous high not breached {_p(w['prev_high_not_breached'])} (claimed {_p(w['claimed_high_not_breached'])})")
    print(f"   open inside n {i['n']:>4} ({_p(i['share_of_days'])} of days, claimed {_p(i['claimed_share'])})"
          f"   neither side {_p(i['neither_side'])} (claimed {_p(i['claimed_neither'])})"
          f"   one side {_p(i['one_side'])} (claimed {_p(i['claimed_one'])}; high only {_p(i['one_side_high_only'])},"
          f" low only {_p(i['one_side_low_only'])})   both {_p(i['both_sides'])} (claimed {_p(i['claimed_both'])})")


def show(res):
    print(res["claim"], "  ", res["span"])
    _line("headline (breach = more than 1 tick beyond; roll days left out)", res["headline"])
    for tag, b in (("breach = 1 tick beyond", res["other_breach_definitions"]["through_by_1_tick"]),
                   ("breach = a touch of the level", res["other_breach_definitions"]["touch"]),
                   ("headline definition with the roll days left in", res["with_roll_days"]),
                   ("headline definition without early-close days", res["without_early_close_days"]),
                   ("headline definition without early-close days and the day after one",
                    res["without_early_close_days_and_the_day_after_one"])):
        if b == res["headline"]:
            print(f"{tag}: every figure identical to the headline")
        else:
            _line(tag, b)
    for y, v in res["by_year"].items():
        print(f"   {y}: above n {v['n_above']} close {_p(v['above_closes_above'])} low held {_p(v['above_low_not_breached'])}"
              f" | below n {v['n_below']} close {_p(v['below_closes_below'])} high held {_p(v['below_high_not_breached'])}"
              f" | inside n {v['n_inside']} neither {_p(v['inside_neither'])} one {_p(v['inside_one'])} both {_p(v['inside_both'])}")
