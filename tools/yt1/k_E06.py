#!/usr/bin/env python3
"""K-E06 - NQ Stats AM TBR: the first touch of the 08:00 open +/- 0.25 SD and the return to the 08:00 open by 12:00.

Spec text (YT1_SPEC.md, K-E06): two readings of the SD (trading-day close-to-close % change; 08:00 -> 12:00 % change).
The reading whose in-sample touch rate of +/- 0.25 SD between 08:00 and 12:00 is nearer the published 98.9 % is the one
E06 uses. Reported: touch rate, reversion to the 08:00 open by 12:00 overall and by touch half-hour.
Claimed: 74 %; 08:xx 79 %.

Definitions used (fixed before the first run; see notes/K-E06.md):
  * session = a cash day of the day table that has an 08:00 bar; its window is the 1-minute bars 08:00 .. 11:59.
  * SD = sample standard deviation (n - 1, around the mean) of the 20 values before the session, never the session's
    own:
      'cc'  % change of the trading-day close (last bar of the 18:00 -> 17:00 trading date, the bars of the day
            table's ATR) from the previous trading-day close; the 20 trading dates before the session's date.
      'am'  close of the last bar before 12:00 / open of the 08:00 bar - 1; the 20 previous sessions.
  * levels = 08:00 open x (1 +/- 0.25 x SD), not rounded. Touch = a bar's high >= the upper level or low <= the lower
    one; the first such bar from 08:00 to 11:59 is the first touch. Inside that one bar the order of events is the
    harness path (open -> nearer extreme -> farther extreme -> close).
  * reversion = after the touch, price trades at the 08:00 open again (low <= open after an upper touch, high >= open
    after a lower touch) in the rest of the touch bar's path or in any later bar up to 11:59.
  * every such session is counted, roll days and early-close days included (the measure is intraday).
  * selection for E06: |touch rate - 0.989| on the sessions before 2023-01-01 only, whatever span is being measured;
    the smaller distance wins, a tie goes to 'cc' (the reading the spec lists first). No trade result is involved.
"""
import numpy as np
import pandas as pd
import core

NAME = "AM TBR: first touch of the 08:00 open +/- 0.25 SD (08:00-11:59) and return to the 08:00 open by 12:00"
READINGS = ("cc", "am")
LABEL = {"cc": "trading-day close-to-close % change", "am": "08:00 -> 12:00 % change"}
PUBLISHED_TOUCH = 2545 / 2572                      # 98.9 %
CLAIM = dict(reversion=1891 / 2545, up=927 / 1252, down=964 / 1293,
             by_hour={"08": 0.790, "09": 0.695, "10": 0.396, "11": 0.091},
             by_half_hour_up={"08:00": 0.828, "08:30": 0.751, "09:00": 0.701, "09:30": 0.695},
             by_half_hour_down={"08:00": 0.831, "08:30": 0.765, "09:00": 0.712, "09:30": 0.683})
N_SD = 20


def sd_table(ctx, reading):
    """Series by cash date: the SD (a fraction, e.g. 0.012) a session may use at its 08:00 open. Prior sessions only."""
    key = "_yt1E06_sd_" + reading
    s = getattr(ctx, key, None)
    if s is not None:
        return s
    D = ctx.days
    if reading == "cc":
        c = ctx.a.groupby(pd.DatetimeIndex(ctx.tdate)).close.last()        # trading-day closes
        r = c / c.shift(1) - 1
        s = r.rolling(N_SD).std(ddof=1).shift(1).reindex(D.index)          # the 20 trading dates before this one
    elif reading == "am":
        v = {}
        for d in D.index:
            i8 = ctx.idx(d, "08:00")
            lo, hi = ctx.span(d, "08:00", "12:00")
            if i8 is None or hi - 1 <= i8:
                continue
            v[d] = ctx.C[hi - 1] / ctx.O[i8] - 1
        v = pd.Series(v, dtype=float)
        s = v.rolling(N_SD).std(ddof=1).shift(1).reindex(D.index)          # the 20 sessions before this one
    else:
        raise ValueError(reading)
    setattr(ctx, key, s)
    return s


def first_touch(ctx, lo, hi, up, dn):
    """First bar in [lo, hi) with high >= up or low <= dn. Returns (k, side, both) or None; side +1 = the upper level
    first. both = the bar reached both levels (side then follows the harness path)."""
    hit = np.flatnonzero((ctx.H[lo:hi] >= up) | (ctx.L[lo:hi] <= dn))
    if not len(hit):
        return None
    k = lo + int(hit[0])
    a, b = ctx.H[k] >= up, ctx.L[k] <= dn
    if a and b:
        p = core._path(ctx.O[k], ctx.H[k], ctx.L[k], ctx.C[k])
        side = 1 if p[0] >= up else -1 if p[0] <= dn else 1 if p[1] >= up else -1
        return k, side, True
    return k, (1 if a else -1), False


def _reverted_in_touch_bar(ctx, k, side, up, dn, o8):
    """After the touch inside bar k, does the rest of the bar's path trade back to the 08:00 open?"""
    p = core._path(ctx.O[k], ctx.H[k], ctx.L[k], ctx.C[k])
    lvl = up if side > 0 else dn
    for s in range(4):
        if (p[s] >= lvl) if side > 0 else (p[s] <= lvl):
            rest = p[s + 1:]
            return bool(rest) and (min(rest) <= o8 if side > 0 else max(rest) >= o8)
    return False


def _rows(ctx, reading):
    D, sd = ctx.days, sd_table(ctx, reading)
    rows = []
    for d in D.index:
        s = sd[d]
        i8 = ctx.idx(d, "08:00")
        if i8 is None or not s == s or s <= 0:
            continue
        lo, hi = ctx.span(d, "08:00", "12:00")
        o8 = ctx.O[i8]
        up, dn = o8 * (1 + 0.25 * s), o8 * (1 - 0.25 * s)
        row = dict(date=d, sd=s, touched=False, side=0, both=False, reverted=False, tod=-1)
        ft = first_touch(ctx, lo, hi, up, dn)
        if ft is not None:
            k, side, both = ft
            rev = _reverted_in_touch_bar(ctx, k, side, up, dn, o8)
            if not rev and hi > k + 1:
                rev = bool((ctx.L[k + 1:hi] <= o8).any() if side > 0 else (ctx.H[k + 1:hi] >= o8).any())
            row.update(touched=True, side=side, both=both, reverted=rev, tod=int(ctx.tod[k]))
        rows.append(row)
    return pd.DataFrame(rows)


def _rate(m):
    return round(float(np.mean(m)), 4) if len(m) else None


def _block(x):
    t = x[x.touched]
    out = dict(sessions=int(len(x)), touched=int(len(t)), touch_rate=_rate(x.touched),
               claimed_touch_rate=round(PUBLISHED_TOUCH, 4),
               median_sd_pct=round(float(x.sd.median() * 100), 3) if len(x) else None,
               first_touch_upper=int((t.side > 0).sum()), first_touch_lower=int((t.side < 0).sum()),
               both_levels_in_the_first_touch_bar=int(t.both.sum()),
               reverted=int(t.reverted.sum()), reversion_rate=_rate(t.reverted),
               claimed_reversion_rate=round(CLAIM["reversion"], 4),
               reversion_after_upper_touch=_rate(t.reverted[t.side > 0]), claimed_after_upper=round(CLAIM["up"], 4),
               reversion_after_lower_touch=_rate(t.reverted[t.side < 0]), claimed_after_lower=round(CLAIM["down"], 4))
    bh = {}
    for h in (8, 9, 10, 11):
        g = t[t.tod // 60 == h]
        bh[f"{h:02d}"] = dict(n=int(len(g)), reversion_rate=_rate(g.reverted), claimed=CLAIM["by_hour"][f"{h:02d}"])
    out["by_touch_hour"] = bh
    hh = {}
    for m in range(480, 720, 30):
        g = t[(t.tod >= m) & (t.tod < m + 30)]
        lab = f"{m // 60:02d}:{m % 60:02d}"
        hh[lab] = dict(n=int(len(g)), reversion_rate=_rate(g.reverted),
                       n_upper=int((g.side > 0).sum()), after_upper=_rate(g.reverted[g.side > 0]),
                       claimed_after_upper=CLAIM["by_half_hour_up"].get(lab),
                       n_lower=int((g.side < 0).sum()), after_lower=_rate(g.reverted[g.side < 0]),
                       claimed_after_lower=CLAIM["by_half_hour_down"].get(lab))
    out["by_touch_half_hour"] = hh
    out["by_year"] = {int(y): dict(sessions=int(len(g)), touch_rate=_rate(g.touched),
                                   reversion_rate=_rate(g.reverted[g.touched]))
                      for y, g in x.groupby(pd.DatetimeIndex(x.date).year)}
    return out


def measure(ctx):
    is_end = core.IS_END.tz_localize(None)
    res = dict(claim="98.9 % of sessions touch the 08:00 open +/- 0.25 SD by 12:00; 74 % of those return to the 08:00 "
                     "open by 12:00 (first touch in the 08:00 hour: 79 %)",
               span=f"{ctx.days.index[0].date()} -> {ctx.days.index[-1].date()}", readings={})
    sel = {}
    for r in READINGS:
        x = _rows(ctx, r)
        res["readings"][r] = dict(sd=LABEL[r], **_block(x))
        xi = x[x.date < is_end]
        sel[r] = dict(sessions=int(len(xi)), touched=int(xi.touched.sum()), touch_rate=float(xi.touched.mean()))
        sel[r]["distance_from_published"] = abs(sel[r]["touch_rate"] - PUBLISHED_TOUCH)
    chosen = "am" if sel["am"]["distance_from_published"] < sel["cc"]["distance_from_published"] else "cc"
    res["selection"] = dict(rule="in-sample (before 2023-01-01) touch rate nearer the published 98.9 %; tie -> cc",
                            published_touch_rate=PUBLISHED_TOUCH, in_sample=sel, selected=chosen,
                            selected_label=LABEL[chosen])
    return res


def show(res):
    print(res["claim"], "  ", res["span"])
    for r in READINGS:
        b = res["readings"][r]
        print(f"SD = {b['sd']}  (median SD {b['median_sd_pct']} %)")
        print(f"   sessions {b['sessions']}  touched {b['touched']} = {b['touch_rate']:.2%}  claimed {b['claimed_touch_rate']:.2%}"
              f"   first touch upper {b['first_touch_upper']} / lower {b['first_touch_lower']}"
              f"  (both levels in the touch bar: {b['both_levels_in_the_first_touch_bar']})")
        print(f"   back to the 08:00 open by 12:00: {b['reverted']} = {b['reversion_rate']:.1%}  claimed {b['claimed_reversion_rate']:.1%}"
              f"   after upper {b['reversion_after_upper_touch']:.1%} (claimed {b['claimed_after_upper']:.1%})"
              f"  after lower {b['reversion_after_lower_touch']:.1%} (claimed {b['claimed_after_lower']:.1%})")
        print("   by touch hour: " + "  ".join(
            f"{h}:xx {v['reversion_rate']:.1%} (n {v['n']}, claimed {v['claimed']:.1%})" if v["n"] else f"{h}:xx n 0"
            for h, v in b["by_touch_hour"].items()))
        for lab, v in b["by_touch_half_hour"].items():
            if not v["n"]:
                print(f"   {lab}  n 0")
                continue
            f = lambda z: "  n/a" if z is None else f"{z:.1%}"
            print(f"   {lab}  n {v['n']:>4}  reverted {v['reversion_rate']:.1%}   upper {f(v['after_upper'])} (n {v['n_upper']},"
                  f" claimed {f(v['claimed_after_upper'])})   lower {f(v['after_lower'])} (n {v['n_lower']},"
                  f" claimed {f(v['claimed_after_lower'])})")
        print("   by year: " + "  ".join(f"{y} touch {v['touch_rate']:.1%} rev {v['reversion_rate']:.1%} (n {v['sessions']})"
                                         for y, v in b["by_year"].items()))
    s = res["selection"]
    print("selection for E06 (in-sample sessions only; published touch rate %.2f %%):" % (100 * s["published_touch_rate"]))
    for r in READINGS:
        v = s["in_sample"][r]
        print(f"   {r}: {v['touched']} of {v['sessions']} = {v['touch_rate']:.2%}, distance {v['distance_from_published']:.4f}")
    print(f"   selected: {s['selected']} ({s['selected_label']})")
