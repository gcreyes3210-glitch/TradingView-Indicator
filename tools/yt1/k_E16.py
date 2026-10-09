#!/usr/bin/env python3
"""K-E16 - news-candle "data high / data low" (EzTrades): on days with an 08:30 release, after one side of the 08:30
5-minute bar is traded through, the share of days on which the other side is traded through by 16:00.
Claimed: "around 85% of the time, the untapped side gets taken out the same day".

Definitions used (fixed before the first run; see notes/K-E16.md):
  * event day: a cash day of the day table whose event set (`ctx.days.ev`) holds CPI, NFP, PPI, retail_sales,
    GDP_advance or PCE, and for which data/events.csv gives the release time 08:30 (the harness calendar has the
    advance GDP estimate only; a release listed at another time is not an 08:30 release).
  * news candle: the 5-minute bar 08:30-08:34, built from its 1-minute bars; data high / data low = its high / low.
  * traded through: a 1-minute bar from 08:35 on with high > data high (low < data low), at least one tick beyond.
    The first such bar on either side is the sweep. "The other side by 16:00": a bar after the sweep bar, up to the
    last bar before 16:00 (the halt on a short day), trades through the opposite level. A single 1-minute bar that
    trades through both levels counts as swept and completed (its order inside the minute is unknown; counted and
    shown separately).
  * headline = days on which the other side was traded through / days on which one side was traded through.
  * every event day of the day table is counted, roll days and short days included (the levels are intraday); the
    figure without short days is given beside it. Control: the same measure on the cash days without any of these
    releases (the 08:30 bar is then an ordinary bar).
"""
import numpy as np
import pandas as pd
import core

NAME = "News candle: after one side of the 08:30 5m bar is traded through, the other side is traded through by 16:00"
CLAIMED = 0.85
TYPES = ("CPI", "NFP", "PPI", "retail_sales", "GDP_advance", "PCE")


def _times():
    """{(date string, type): release time} from the event calendar."""
    ev = pd.read_csv(core.ROOT / "data" / "events.csv", dtype=str)
    ev = ev[ev.type.isin(TYPES)]
    return {(r.date, r.type): r.time_ny for r in ev.itertuples()}


def _rows(ctx):
    times = _times()
    H, L, tod = ctx.H, ctx.L, ctx.tod
    rows = []
    for d, day in ctx.days.iterrows():
        ds = d.strftime("%Y-%m-%d")
        named = sorted(t for t in day.ev if t in TYPES)
        at830 = [t for t in named if times.get((ds, t)) == "08:30"]
        s0, s1 = ctx.span(d, "08:30", "08:35")
        e0, e1 = ctx.span(d, "08:35", "16:00")
        row = dict(date=d, event=bool(at830), types="+".join(at830), other_time="+".join(t for t in named if t not in at830),
                   early=bool(day.early), ok=bool(s1 > s0 and e1 > e0), first="", done=False, same_minute=False,
                   t_sweep=-1, t_done=-1, width=np.nan)
        if row["ok"]:
            dh, dl = float(H[s0:s1].max()), float(L[s0:s1].min())
            row["width"] = dh - dl
            up = np.flatnonzero(H[e0:e1] > dh)
            dn = np.flatnonzero(L[e0:e1] < dl)
            iu = int(up[0]) if len(up) else None
            idn = int(dn[0]) if len(dn) else None
            if iu is not None or idn is not None:
                if iu is not None and idn is not None and iu == idn:
                    row.update(first="both", done=True, same_minute=True, t_sweep=int(tod[e0 + iu]), t_done=int(tod[e0 + iu]))
                elif idn is None or (iu is not None and iu < idn):
                    row.update(first="high", t_sweep=int(tod[e0 + iu]))
                    if idn is not None:
                        row.update(done=True, t_done=int(tod[e0 + idn]))
                else:
                    row.update(first="low", t_sweep=int(tod[e0 + idn]))
                    if iu is not None:
                        row.update(done=True, t_done=int(tod[e0 + iu]))
        rows.append(row)
    return pd.DataFrame(rows)


def _rate(m):
    return round(float(np.mean(m)), 4) if len(m) else None


def _block(x):
    """x = rows of usable days. Counts and rates among the days on which one side was traded through."""
    s = x[x["first"] != ""]
    out = dict(
        days=int(len(x)), days_one_side_traded_through=int(len(s)), days_neither_side=int(len(x) - len(s)),
        other_side_traded_through_by_1600=int(s.done.sum()),
        share_other_side_traded_through_by_1600=_rate(s.done), claimed=CLAIMED,
        first_sweep_was_the_high=dict(n=int((s["first"] == "high").sum()), share_low_then_taken=_rate(s.done[s["first"] == "high"])),
        first_sweep_was_the_low=dict(n=int((s["first"] == "low").sum()), share_high_then_taken=_rate(s.done[s["first"] == "low"])),
        both_in_the_same_minute=int(s.same_minute.sum()),
        share_of_all_days_with_both_sides_traded_through=_rate(x.done) if len(x) else None,
        other_side_taken_by=dict(
            by_0930=_rate(s.done & (s.t_done < 570)), by_1200=_rate(s.done & (s.t_done < 720)),
            by_1600=_rate(s.done)),
        first_sweep_before_0930=dict(n=int((s.t_sweep < 570).sum()), share_other_side_taken=_rate(s.done[s.t_sweep < 570])),
        first_sweep_at_or_after_0930=dict(n=int((s.t_sweep >= 570).sum()), share_other_side_taken=_rate(s.done[s.t_sweep >= 570])),
        median_news_candle_range_pts=round(float(x.width.median()), 2) if len(x) else None)
    return out


def measure(ctx):
    r = _rows(ctx)
    ev, non = r[r.event], r[~r.event & (r.other_time == "")]
    evu, nonu = ev[ev.ok], non[non.ok]
    cal = pd.read_csv(core.ROOT / "data" / "events.csv", dtype=str)
    cal = cal[cal.type.isin(TYPES) & (cal.time_ny == "08:30")]
    d0, d1 = ctx.days.index[0].strftime("%Y-%m-%d"), ctx.days.index[-1].strftime("%Y-%m-%d")
    in_span = sorted(set(cal.date[(cal.date >= d0) & (cal.date <= d1)]))
    have = set(ev.date.dt.strftime("%Y-%m-%d"))
    res = dict(
        claim="after one side of the 08:30 news candle is traded through, the other side is taken the same day: about 85 %",
        span=f"{d0} -> {d1}",
        release_days_in_calendar=len(in_span), release_days_with_a_cash_session=int(len(ev)),
        release_days_without_a_cash_session=[x for x in in_span if x not in have],
        release_days_without_0830_bars=[str(x.date()) for x in ev.date[~ev.ok]],
        releases_listed_at_another_time=[f"{x.date.date()} {x.other_time}" for x in r[r.other_time != ""].itertuples()],
        event_days=_block(evu))
    res["event_days"]["without_short_days"] = _block(evu[~evu.early])
    res["event_days"]["by_type"] = {t: (lambda b: dict(days=b["days"], one_side=b["days_one_side_traded_through"],
                                                        share=b["share_other_side_traded_through_by_1600"]))(
        _block(evu[evu.types.str.split("+").apply(lambda v: t in v)])) for t in TYPES}
    res["event_days"]["by_year"] = {int(y): (lambda b: dict(days=b["days"], one_side=b["days_one_side_traded_through"],
                                                            share=b["share_other_side_traded_through_by_1600"]))(_block(g))
                                    for y, g in evu.groupby(evu.date.dt.year)}
    res["control_days_without_a_release"] = _block(nonu)
    return res


def show(res):
    print(res["claim"], "  ", res["span"])
    print(f"08:30 release days in the calendar {res['release_days_in_calendar']}, with a cash session "
          f"{res['release_days_with_a_cash_session']}; without: {res['release_days_without_a_cash_session']}; "
          f"without 08:30 bars: {res['release_days_without_0830_bars']}; listed at another time: "
          f"{res['releases_listed_at_another_time']}")
    for name in ("event_days", "control_days_without_a_release"):
        b = res[name]
        print(f"{name:<32} days {b['days']}  one side traded through {b['days_one_side_traded_through']}  "
              f"(neither {b['days_neither_side']})  other side by 16:00: {b['other_side_traded_through_by_1600']} = "
              f"{b['share_other_side_traded_through_by_1600']:.1%}   claimed {b['claimed']:.0%}")
        fh, fl, t = b["first_sweep_was_the_high"], b["first_sweep_was_the_low"], b["other_side_taken_by"]
        print(f"{'':<32} high first {fh['n']} -> low taken {fh['share_low_then_taken']:.1%};  low first {fl['n']} -> high "
              f"taken {fl['share_high_then_taken']:.1%};  both in one minute {b['both_in_the_same_minute']}")
        a, c = b["first_sweep_before_0930"], b["first_sweep_at_or_after_0930"]
        print(f"{'':<32} other side taken by 09:30 {t['by_0930']:.1%}, by 12:00 {t['by_1200']:.1%}, by 16:00 {t['by_1600']:.1%};  "
              f"first sweep before 09:30: n {a['n']} -> {a['share_other_side_taken']:.1%};  at or after 09:30: n {c['n']} -> "
              + (f"{c['share_other_side_taken']:.1%}" if c['share_other_side_taken'] is not None else "n/a")
              + f";  median candle range {b['median_news_candle_range_pts']} pts")
    b = res["event_days"]
    w = b["without_short_days"]
    print(f"event days without short days: {w['other_side_traded_through_by_1600']} of {w['days_one_side_traded_through']} = "
          f"{w['share_other_side_traded_through_by_1600']:.1%}")
    print("by type: " + "  ".join(f"{k} {v['share']:.1%} (n {v['one_side']})" for k, v in b["by_type"].items() if v["one_side"]))
    print("by year: " + "  ".join(f"{k} {v['share']:.1%} (n {v['one_side']})" for k, v in b["by_year"].items() if v["one_side"]))
