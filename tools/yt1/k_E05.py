#!/usr/bin/env python3
"""K-E05 - NQ Stats ALN sessions: how often each London-versus-Asia pattern occurs and how often the New York
session (08:00-16:00) breaks London's high / low, by pattern.
Claimed: P3 80.8 % / 65.5 %, P4 68.6 % / 75.0 %, P1 71.5 % / 70.4 % (and P2 81.1 % / 74.9 %).

Definitions (the source's, research note E entry 5; fixed before the first run, see notes/K-E05.md):
  * for cash day D: Asia = 20:00-23:59 on the calendar day before D plus 00:00-01:59 on D; London = 02:00-07:59;
    New York = 08:00-15:59 (an early-close day ends at its halt). Days on which any of the three has no bars, or on
    which the contract changes between Asia's first bar and New York's last, are left out.
  * a break is trading at least 1 tick beyond the level.
    P1 London engulfs Asia: London high above Asia high AND London low below Asia low.
    P2 Asia engulfs London: neither.     P3 partial up: the high only.     P4 partial down: the low only.
  * New York breaks London's high: some bar 08:00-15:59 with high >= London high + 0.25; low mirror. "High first":
    the bar that first broke the high is earlier than the one that first broke the low (or the low never broke);
    both first broken in the same bar is counted apart.
Every published figure is carried next to the measured one.
"""
import numpy as np
import pandas as pd
import core

NAME = "ALN sessions: London-vs-Asia pattern frequencies and New York breaks of London's high / low by pattern"
# published (nqstats.com/aln_sessions.html, 2016-2025, 2,542 sessions), by pattern
PUB = {
    "P1": dict(freq=0.220, ny_breaks_high=0.715, ny_breaks_low=0.704, both=0.425, high_first=0.507, low_first=0.487, neither=None),
    "P2": dict(freq=0.069, ny_breaks_high=0.811, ny_breaks_low=0.749, both=0.560, high_first=0.531, low_first=0.469, neither=0.0),
    "P3": dict(freq=0.410, ny_breaks_high=0.808, ny_breaks_low=0.655, both=0.476, high_first=0.620, low_first=0.368, neither=0.012),
    "P4": dict(freq=0.302, ny_breaks_high=0.686, ny_breaks_low=0.750, both=0.446, high_first=0.446, low_first=0.544, neither=0.010),
}


def _rows(ctx):
    T = core.TICK
    H, L = ctx.H, ctx.L
    rows, cnt = [], dict(days=0, missing_session=0, contract_change=0)
    for d, day in ctx.days.iterrows():
        cnt["days"] += 1
        a0, _ = ctx.span(d - pd.Timedelta(days=1), "20:00", "23:59")
        _, a1 = ctx.span(d, "00:00", "02:00")
        l0, l1 = ctx.span(d, "02:00", "08:00")
        n0, n1 = ctx.span(d, "08:00", "16:00")
        if a1 <= a0 or l1 <= l0 or n1 <= n0:
            cnt["missing_session"] += 1
            continue
        if ctx.iid[a0] != ctx.iid[n1 - 1]:
            cnt["contract_change"] += 1
            continue
        ah, al = H[a0:a1].max(), L[a0:a1].min()
        lh, ll = H[l0:l1].max(), L[l0:l1].min()
        up, dn = bool(lh >= ah + T), bool(ll <= al - T)
        pat = "P1" if up and dn else "P3" if up else "P4" if dn else "P2"
        bh, bl = H[n0:n1] >= lh + T, L[n0:n1] <= ll - T
        kh = int(bh.argmax()) if bh.any() else None
        kl = int(bl.argmax()) if bl.any() else None
        first = ("none" if kh is None and kl is None else "high" if kl is None or (kh is not None and kh < kl)
                 else "low" if kh is None or kl < kh else "same bar")
        rows.append(dict(date=d, early=bool(day.early), pat=pat, hi=kh is not None, lo=kl is not None, first=first,
                         london_outside_asia=bool(ll > ah or lh < al)))
    return pd.DataFrame(rows), cnt


def _sh(m):
    return round(float(m.mean()), 4) if len(m) else None


def _block(x):
    out = {}
    for p in ("P1", "P2", "P3", "P4"):
        g = x[x.pat == p]
        out[p] = dict(n=int(len(g)), freq=round(len(g) / len(x), 4) if len(x) else None,
                      ny_breaks_high=_sh(g.hi), ny_breaks_low=_sh(g.lo), both=_sh(g.hi & g.lo),
                      neither=_sh(~g.hi & ~g.lo), high_first=_sh(g["first"] == "high"),
                      low_first=_sh(g["first"] == "low"), same_bar=_sh(g["first"] == "same bar"), claimed=PUB[p])
    return out


def measure(ctx):
    x, cnt = _rows(ctx)
    return dict(claim="NY (08:00-16:00) breaks London's high / low: P3 80.8 % / 65.5 %, P4 68.6 % / 75.0 %, "
                      "P1 71.5 % / 70.4 %",
                span=f"{ctx.days.index[0].date()} -> {ctx.days.index[-1].date()}",
                counts=dict(cnt, sessions=int(len(x)), early_close_days=int(x.early.sum()),
                            london_entirely_outside_asia=int(x.london_outside_asia.sum())),
                all_sessions=_block(x), without_early_close_days=_block(x[~x.early]),
                by_year={int(y): {p: dict(n=int((g.pat == p).sum()), ny_breaks_high=_sh(g.hi[g.pat == p]),
                                          ny_breaks_low=_sh(g.lo[g.pat == p])) for p in ("P1", "P2", "P3", "P4")}
                         for y, g in x.groupby(pd.DatetimeIndex(x.date).year)})


def show(res):
    c = res["counts"]
    print(res["claim"], "  ", res["span"])
    print(f"cash days {c['days']}: a session without bars {c['missing_session']}, contract change "
          f"{c['contract_change']}, sessions {c['sessions']} (early-close days {c['early_close_days']}, London "
          f"entirely outside Asia {c['london_entirely_outside_asia']})")

    def pc(v):
        return "  -  " if v is None else f"{v:5.1%}"

    for blk in ("all_sessions", "without_early_close_days"):
        print(blk + ":   measured (claimed)")
        for p, r in res[blk].items():
            q = r["claimed"]
            print(f"  {p}  n {r['n']:>4}  freq {pc(r['freq'])} ({pc(q['freq'])})  NY breaks London high "
                  f"{pc(r['ny_breaks_high'])} ({pc(q['ny_breaks_high'])})  low {pc(r['ny_breaks_low'])} "
                  f"({pc(q['ny_breaks_low'])})  both {pc(r['both'])} ({pc(q['both'])})  neither {pc(r['neither'])} "
                  f"({pc(q['neither'])})  high first {pc(r['high_first'])} ({pc(q['high_first'])})  low first "
                  f"{pc(r['low_first'])} ({pc(q['low_first'])})")
    for y, r in res["by_year"].items():
        print(f"  {y}: " + "  ".join(f"{p} n {v['n']} high {pc(v['ny_breaks_high'])} low {pc(v['ny_breaks_low'])}"
                                     for p, v in r.items()))
