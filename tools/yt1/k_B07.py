#!/usr/bin/env python3
"""K-B07 - the DR rule (TheMas7er): after the first 5-minute close beyond the 09:30-10:29 range, the share of days on
which the opposite extreme is not traded through by 16:00. Claimed: 80 %. Also for the body (IDR) version.

Definitions used (fixed before the first run; see notes/K-B07.md):
  * range, wick version (DR): highest high / lowest low of the 1-minute bars 09:30-10:29;
    body version (IDR): highest / lowest 5-minute body (max / min of open, close) of the twelve 5m bars 09:30-10:25.
  * confirmation: the first 5-minute bar opening 10:30 or later and closing by 16:00 whose close is strictly beyond
    the range (above its high = up, below its low = down). One confirmation a day, the first on either side.
  * held (the headline): from the first 1-minute bar after the confirming bar's close to the last bar before 16:00,
    no bar trades strictly beyond the opposite extreme of the SAME range (low < range low after an up confirmation).
  * every cash day of the day table is counted (roll days and early-close days included; an early-close day ends at
    its halt). The same figure without early-close days is given beside it.
Secondary figures, each labelled: the opposite extreme was not even touched; it was not traded through at any time
from 10:30 on (so it stayed the day's post-range extreme, the "low of day" wording); body version only: the opposite
body extreme was not CLOSED through by a later 5-minute bar, and the opposite DR (wick) extreme was not traded through
(LuxAlgo's "early indication" wording).
"""
import numpy as np
import pandas as pd
import core

NAME = "DR rule: first 5m close beyond the 09:30-10:29 range, opposite extreme not traded through by 16:00"
CLAIMED = 0.80


def ib_table(ctx, end="10:29"):
    """Initial balance / defining range per cash day, from the 1-minute bars 09:30 .. `end` inclusive (shared helper,
    copied between s_B07 / s_B08 / s_B09 / s_B14 / k_B07). {cash date: dict} with
        hi, lo        highest high / lowest low of the window
        i_hi, i_lo    position of the 1-minute bar that FIRST set each extreme
        o930          open of the 09:30 bar            c_end   close of the window's last bar (the `end` close)
        i_dec         position of the window's last 1-minute bar: everything here is known at its close
        body_hi, body_lo   highest / lowest 5-minute body (max / min of open, close) of the 5m bars in the window
    """
    key = "_yt1B_ib_" + end
    tab = getattr(ctx, key, None)
    if tab is not None:
        return tab
    e = core.hhmm(end) + 1
    assert e % 5 == 0, "the window must end on a 5-minute boundary"
    b = ctx.bars(5)
    bt = b.index
    bo, bc = b.open.to_numpy(float), b.close.to_numpy(float)
    b_hi, b_lo = np.maximum(bo, bc), np.minimum(bo, bc)
    tab = {}
    for d in ctx.days.index:
        lo, hi = ctx.span(d, 570, e)
        if hi <= lo:
            continue
        H, L = ctx.H[lo:hi], ctx.L[lo:hi]
        t0 = pd.Timestamp(d).tz_localize(core.TZ)
        a = int(bt.searchsorted(t0 + pd.Timedelta(minutes=570)))
        z = int(bt.searchsorted(t0 + pd.Timedelta(minutes=e)))
        if z <= a:
            continue
        tab[d] = dict(hi=float(H.max()), lo=float(L.min()), i_hi=lo + int(H.argmax()), i_lo=lo + int(L.argmin()),
                      o930=float(ctx.O[lo]), c_end=float(ctx.C[hi - 1]), i_dec=hi - 1,
                      body_hi=float(b_hi[a:z].max()), body_lo=float(b_lo[a:z].min()))
    setattr(ctx, key, tab)
    return tab


def _rows(ctx):
    """One row per cash day and range version with a confirmation."""
    tab = ib_table(ctx, "10:29")
    b = ctx.bars(5)
    bt = b.index
    bc = b.close.to_numpy(float)
    bil = b.i_last.to_numpy()
    H, L = ctx.H, ctx.L
    rows = []
    for d, day in ctx.days.iterrows():
        r = tab.get(d)
        if r is None:
            continue
        t0 = pd.Timestamp(d).tz_localize(core.TZ)
        a = int(bt.searchsorted(t0 + pd.Timedelta(minutes=630)))      # 5m bars opening 10:30 ..
        z = int(bt.searchsorted(t0 + pd.Timedelta(minutes=960)))      # .. and closing by 16:00
        e0, e1 = ctx.span(d, "10:30", "16:00")
        for kind, hi, lo in (("wick", r["hi"], r["lo"]), ("body", r["body_hi"], r["body_lo"])):
            row = dict(date=d, kind=kind, early=bool(day.early), conf=0, held=False, untouched=False,
                       held_from_1030=False, not_closed_through=False, dr_held=False, conf_time="")
            for k in range(a, z):
                c = bc[k]
                side = 1 if c > hi else -1 if c < lo else 0
                if not side:
                    continue
                i = int(bil[k])
                aft_l = L[i + 1:e1].min() if e1 > i + 1 else np.inf
                aft_h = H[i + 1:e1].max() if e1 > i + 1 else -np.inf
                all_l, all_h = L[e0:e1].min(), H[e0:e1].max()
                later = bc[k + 1:z]
                if side > 0:
                    row.update(conf=1, held=bool(aft_l >= lo), untouched=bool(aft_l > lo), held_from_1030=bool(all_l >= lo),
                               not_closed_through=bool(not (later < lo).any()), dr_held=bool(aft_l >= r["lo"]))
                else:
                    row.update(conf=-1, held=bool(aft_h <= hi), untouched=bool(aft_h < hi), held_from_1030=bool(all_h <= hi),
                               not_closed_through=bool(not (later > hi).any()), dr_held=bool(aft_h <= r["hi"]))
                row["conf_time"] = str(bt[k].time())[:5]
                break
            rows.append(row)
    return pd.DataFrame(rows)


def _block(x, body):
    c = x[x.conf != 0]

    def rate(m):
        return round(float(m.mean()), 4) if len(m) else None

    out = dict(
        days=int(len(x)), days_with_confirmation=int(len(c)), up=int((c.conf > 0).sum()), down=int((c.conf < 0).sum()),
        held=int(c.held.sum()) if len(c) else 0,
        share_opposite_extreme_not_traded_through=rate(c.held), claimed=CLAIMED,
        share_after_up_confirmation=rate(c.held[c.conf > 0]), share_after_down_confirmation=rate(c.held[c.conf < 0]),
        secondary=dict(
            share_not_even_touched=rate(c.untouched),
            share_not_traded_through_at_any_time_from_1030=rate(c.held_from_1030)))
    if body:
        out["secondary"]["share_opposite_body_extreme_not_closed_through_on_5m"] = rate(c.not_closed_through)
        out["secondary"]["share_opposite_DR_wick_extreme_not_traded_through"] = rate(c.dr_held)
    return out


def measure(ctx):
    x = _rows(ctx)
    res = dict(claim="after the first 5-minute close beyond the range, the opposite extreme holds: 80 %",
               span=f"{ctx.days.index[0].date()} -> {ctx.days.index[-1].date()}")
    for kind, name in (("wick", "wick_range_DR"), ("body", "body_range_IDR")):
        k = x[x.kind == kind]
        res[name] = _block(k, kind == "body")
        res[name]["without_early_close_days"] = _block(k[~k.early], kind == "body")
        c = k[k.conf != 0]
        res[name]["by_year"] = {int(y): dict(n=int(len(g)), share=round(float(g.held.mean()), 4))
                                for y, g in c.groupby(pd.DatetimeIndex(c.date).year)}
    return res


def show(res):
    print(res["claim"], "  ", res["span"])
    for name in ("wick_range_DR", "body_range_IDR"):
        r = res[name]
        print(f"{name:<16} days {r['days']}  with a confirmation {r['days_with_confirmation']} "
              f"(up {r['up']}, down {r['down']})  opposite extreme not traded through by 16:00: {r['held']} = "
              f"{r['share_opposite_extreme_not_traded_through']:.1%}   claimed {r['claimed']:.0%}")
        print(f"{'':<16} after up {r['share_after_up_confirmation']:.1%}  after down {r['share_after_down_confirmation']:.1%}"
              f"  without early-close days {r['without_early_close_days']['share_opposite_extreme_not_traded_through']:.1%}"
              f" (n {r['without_early_close_days']['days_with_confirmation']})")
        print(f"{'':<16} secondary: " + "  ".join(f"{k} {v:.1%}" for k, v in r["secondary"].items()))
        print(f"{'':<16} by year: " + "  ".join(f"{y} {v['share']:.1%} (n {v['n']})" for y, v in r["by_year"].items()))
