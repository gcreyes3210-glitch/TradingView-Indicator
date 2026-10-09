#!/usr/bin/env python3
"""K-E04 - NQ Stats Noon Curve: the 08:00-16:00 high and low form on opposite sides of noon (claimed 72.81 %); and
what a trader can know at noon: P(the afternoon makes the session high | Q2 broke Q1's high only) and the low mirror,
WITHOUT the source's conditioning on the session ending as an opposite-side session (claimed, with that
conditioning: 82.12 % and 72.42 %).

Definitions (the source's, research note E entry 4; fixed before the first run, see notes/K-E04.md):
  * session 08:00-15:59; AM = 08:00-11:59, PM = 12:00-15:59; Q1 = 08:00-09:59, Q2 = 10:00-11:59.
  * the PM makes the session high when it trades at least 1 tick above the AM high (an equal high was set first by
    the AM); the PM makes the low when it trades at least 1 tick below the AM low.
    opposite sides = exactly one of the two; both in the AM = neither; both in the PM = both.
  * Q2 broke Q1's high = Q2 traded at least 1 tick above Q1's high; "high only" = and not 1 tick below Q1's low.
  * sessions: cash days of the day table with bars in Q1, Q2 and the PM, one contract throughout. The headline uses
    full sessions (no early-close days: their afternoon is cut short); all days are given beside it.
"""
import numpy as np
import pandas as pd
import core

NAME = "Noon Curve: session high and low on opposite sides of noon; the afternoon extreme given Q2's break of Q1"
# published (nqstats.com/noon_curve.html, 2016-2026, n = 2,479)
PUB_SPLIT = dict(opposite_sides=0.7281, both_in_am=0.2182, both_in_pm=0.0537)
# among the 1,805 opposite-side sessions: (n, PM sets the high, PM sets the low)
PUB_COND = {"high only": (794, 0.8212, None), "low only": (631, None, 0.7242),
            "both": (253, 0.5415, 0.4585), "neither": (127, 0.4803, 0.5197)}


def _rows(ctx):
    T = core.TICK
    H, L = ctx.H, ctx.L
    rows, cnt = [], dict(days=0, missing_bars=0, contract_change=0)
    for d, day in ctx.days.iterrows():
        cnt["days"] += 1
        a0, a1 = ctx.span(d, "08:00", "10:00")
        b0, b1 = ctx.span(d, "10:00", "12:00")
        p0, p1 = ctx.span(d, "12:00", "16:00")
        if a1 <= a0 or b1 <= b0 or p1 <= p0:
            cnt["missing_bars"] += 1
            continue
        if ctx.iid[a0] != ctx.iid[p1 - 1]:
            cnt["contract_change"] += 1
            continue
        q1h, q1l = H[a0:a1].max(), L[a0:a1].min()
        q2h, q2l = H[b0:b1].max(), L[b0:b1].min()
        amh, aml = max(q1h, q2h), min(q1l, q2l)
        pm_high, pm_low = bool(H[p0:p1].max() >= amh + T), bool(L[p0:p1].min() <= aml - T)
        up, dn = bool(q2h >= q1h + T), bool(q2l <= q1l - T)
        q2 = "both" if up and dn else "high only" if up else "low only" if dn else "neither"
        rows.append(dict(date=d, early=bool(day.early), pm_high=pm_high, pm_low=pm_low, q2=q2,
                         opposite=pm_high != pm_low))
    return pd.DataFrame(rows), cnt


def _sh(m):
    return round(float(m.mean()), 4) if len(m) else None


def _block(x):
    out = dict(sessions=int(len(x)),
               split=dict(opposite_sides=_sh(x.opposite), both_in_am=_sh(~x.pm_high & ~x.pm_low),
                          both_in_pm=_sh(x.pm_high & x.pm_low), claimed=PUB_SPLIT),
               n_opposite=int(x.opposite.sum()))
    un, co = {}, {}
    for k, (pn, ph, pl) in PUB_COND.items():
        g = x[x.q2 == k]
        go = g[g.opposite]
        un[k] = dict(n=int(len(g)), pm_makes_high=_sh(g.pm_high), pm_makes_low=_sh(g.pm_low),
                     pm_makes_high_only=_sh(g.pm_high & ~g.pm_low), pm_makes_low_only=_sh(g.pm_low & ~g.pm_high),
                     claimed_conditional_pm_high=ph, claimed_conditional_pm_low=pl)
        co[k] = dict(n=int(len(go)), pm_sets_high=_sh(go.pm_high), pm_sets_low=_sh(go.pm_low), claimed_n=pn,
                     claimed_pm_sets_high=ph, claimed_pm_sets_low=pl)
    out["at_noon_unconditional"] = un                      # what the spec asks for: no conditioning on the outcome
    out["among_opposite_side_sessions"] = co               # the source's own (outcome-conditioned) table
    return out


def measure(ctx):
    x, cnt = _rows(ctx)
    full = x[~x.early]
    res = dict(claim="08:00-16:00 high and low on opposite sides of noon 72.81 %; PM makes the high after Q2 broke "
                     "Q1's high only 82.12 %, the low mirror 72.42 % (both published conditional on the outcome)",
               span=f"{ctx.days.index[0].date()} -> {ctx.days.index[-1].date()}",
               counts=dict(cnt, sessions=int(len(x)), early_close_days=int(x.early.sum())),
               full_sessions=_block(full), all_days=_block(x))
    res["full_sessions"]["by_year_opposite_sides"] = {
        int(y): dict(n=int(len(g)), share=_sh(g.opposite)) for y, g in full.groupby(pd.DatetimeIndex(full.date).year)}
    return res


def show(res):
    c = res["counts"]
    print(res["claim"])
    print(res["span"], f"  cash days {c['days']}: missing bars {c['missing_bars']}, contract change "
          f"{c['contract_change']}, sessions {c['sessions']} (early-close days {c['early_close_days']})")

    def pc(v):
        return "   -  " if v is None else f"{v:6.1%}"

    for blk in ("full_sessions", "all_days"):
        r = res[blk]
        s, cl = r["split"], r["split"]["claimed"]
        print(f"{blk}: n {r['sessions']}   opposite sides {pc(s['opposite_sides'])} (claimed {cl['opposite_sides']:.2%})"
              f"   both in AM {pc(s['both_in_am'])} ({cl['both_in_am']:.2%})   both in PM {pc(s['both_in_pm'])} "
              f"({cl['both_in_pm']:.2%})")
        print("  known at noon, no conditioning on the outcome:")
        for k, q in r["at_noon_unconditional"].items():
            print(f"    Q2 broke {k:<9} n {q['n']:>4}   PM makes the high {pc(q['pm_makes_high'])} (claimed, conditional"
                  f" {pc(q['claimed_conditional_pm_high'])})   PM makes the low {pc(q['pm_makes_low'])} (claimed, "
                  f"conditional {pc(q['claimed_conditional_pm_low'])})   high only {pc(q['pm_makes_high_only'])}  "
                  f"low only {pc(q['pm_makes_low_only'])}")
        print(f"  the source's table, among the {r['n_opposite']} opposite-side sessions:")
        for k, q in r["among_opposite_side_sessions"].items():
            print(f"    Q2 broke {k:<9} n {q['n']:>4} ({q['claimed_n']:>3})   PM sets the high {pc(q['pm_sets_high'])} "
                  f"(claimed {pc(q['claimed_pm_sets_high'])})   PM sets the low {pc(q['pm_sets_low'])} "
                  f"(claimed {pc(q['claimed_pm_sets_low'])})")
    print("  full sessions, opposite sides by year: " + "  ".join(
        f"{y} {v['share']:.1%} (n {v['n']})" for y, v in res["full_sessions"]["by_year_opposite_sides"].items()))
