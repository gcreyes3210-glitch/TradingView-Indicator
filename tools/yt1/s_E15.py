#!/usr/bin/env python3
"""E15 - Camarilla pivots (Xtrades; stated on QQQ). YT1_SPEC.md, Family E.

Spec text:
  From the previous RTH high H, low L, close C, W = H - L:
      R3 / S3 = C +- 1.1 W / 4,   R4 / S4 = C +- 1.1 W / 2,   R5 = (H / L) x C,   S5 = C - (R5 - C).
  5-minute bars, signals closing by 15:00, each set-up once a day, one position at a time:
      (1) a bar with low <= S3 closing above S3   -> long,  stop S4, target R3
      (2) first close above R4                    -> long,  stop R3, target R5
      (3) first close below S4                    -> short, stop S3, target S5
      (4) a bar with high >= R3 closing below R3  -> short, stop R4, target S3
  One test, the four pooled. Neighbours: 3-minute, 15-minute bars.

Readings added to the spec text (all fixed before the first run; see notes/E15.md):
  * H, L, C are `pdh`, `pdl`, `pdc` of the day table: the previous cash day's 09:30-16:00 high, low and last close.
  * signal bars are the N-minute bars opening at 09:30 or later whose last minute is 14:59 or earlier.
  * "each set-up once a day": a set-up's one order of the day is its FIRST qualifying bar. Under "one position at a
    time" (run_orders: an order signalled at or before the open trade's exit bar is skipped) a skipped order is not
    replaced by a later bar of the same set-up.
  * the conditions are tested on the exact (unrounded) levels; "above" / "below" are strict.
  * "stop S4", "target R3": the stop and the target sit AT the level (the entry says "stop S4", not "beyond S4").
    A level between two ticks becomes the first tradable price at or through it in the direction price has to travel
    (long: stop rounded down, target rounded up; short: the mirror), so the order triggers exactly when the level
    trades.
  * when one bar qualifies for more than one set-up, the orders are issued in the spec's order (1), (2), (3), (4);
    the first one is the trade and the others are skipped by the one-position rule (they still count as that
    set-up's signal of the day).
  * nothing is added for a close that is already at or beyond the set-up's target: the order goes to the harness as
    written (the target then fills at the next bar's open). `diag()` counts those and the orders whose stop is not
    on the losing side of the signal close (which the harness rejects).
Each order's tag is its set-up number: "s1", "s2", "s3", "s4".
"""
import numpy as np
import pandas as pd
import core

ID = "E15"
NAME = "Camarilla pivots: S3 / R3 rejection and R4 / S4 breakout, four set-ups pooled"
VARIANTS = {
    "base": dict(tf=5),
    "nb1": dict(tf=3),
    "nb2": dict(tf=15),
}


def levels(H, L, C):
    """Camarilla levels from the previous RTH high, low and close (exact, not rounded)."""
    W = H - L
    r5 = (H / L) * C
    return dict(R3=C + 1.1 * W / 4, S3=C - 1.1 * W / 4, R4=C + 1.1 * W / 2, S4=C - 1.1 * W / 2, R5=r5, S5=C - (r5 - C))


def _rows(index, date, m0, m1):
    """Row positions [lo, hi) of the N-minute bars OPENING at m0 <= minute-of-day < m1 on calendar `date`."""
    d = pd.Timestamp(date).tz_localize(core.TZ)
    return (int(index.searchsorted(d + pd.Timedelta(minutes=m0), "left")),
            int(index.searchsorted(d + pd.Timedelta(minutes=m1), "left")))


def orders(ctx, tf=5):
    b = ctx.bars(tf)
    Hn, Ln, Cn = b.high.to_numpy(float), b.low.to_numpy(float), b.close.to_numpy(float)
    i_last = b.i_last.to_numpy()
    dn, up = "down", "up"
    out = []
    for d, day in ctx.days.iterrows():
        H, L, C = day.pdh, day.pdl, day.pdc
        if not (H == H and L == L and C == C) or H <= L or L <= 0:
            continue
        lv = levels(float(H), float(L), float(C))
        R3, S3, R4, S4, R5, S5 = (lv[k] for k in ("R3", "S3", "R4", "S4", "R5", "S5"))
        # bars opening 09:30 .. and closing by 15:00 (last minute 14:59 or earlier)
        lo, hi = _rows(b.index, d, 570, 900 - tf + 1)
        ex = int(day.i_end)
        done = [False, False, False, False]
        for k in range(lo, hi):
            i = int(i_last[k])
            h, l, c = Hn[k], Ln[k], Cn[k]
            if not done[0] and l <= S3 and c > S3:
                done[0] = True
                out.append(dict(i=i, side=1, etype="close", stop=core.tick_round(S4, dn),
                                target=core.tick_round(R3, up), exit_i=ex, tag="s1"))
            if not done[1] and c > R4:
                done[1] = True
                out.append(dict(i=i, side=1, etype="close", stop=core.tick_round(R3, dn),
                                target=core.tick_round(R5, up), exit_i=ex, tag="s2"))
            if not done[2] and c < S4:
                done[2] = True
                out.append(dict(i=i, side=-1, etype="close", stop=core.tick_round(S3, up),
                                target=core.tick_round(S5, dn), exit_i=ex, tag="s3"))
            if not done[3] and h >= R3 and c < R3:
                done[3] = True
                out.append(dict(i=i, side=-1, etype="close", stop=core.tick_round(R4, up),
                                target=core.tick_round(S3, dn), exit_i=ex, tag="s4"))
            if all(done):
                break
    return out


def trades(ctx, **p):
    return core.run_orders(ctx, orders(ctx, **p), one_at_a_time=True)


def diag(ctx, tf=5):
    """Counts for the notes: orders per set-up, orders the harness rejects because the stop is not on the losing side
    of the entry, orders whose target is not on the winning side of the entry, bars with more than one set-up, and
    what became of every order (traded / skipped and why)."""
    od = sorted(orders(ctx, tf=tf), key=lambda o: o["i"])
    tr = trades(ctx, tf=tf)
    taken = {(t["i"], t["tag"]) for t in tr}
    res = dict(tf=tf, orders=len(od), trades=len(tr))
    per = {}
    for s in ("s1", "s2", "s3", "s4"):
        per[s] = dict(orders=sum(o["tag"] == s for o in od), trades=sum(t["tag"] == s for t in tr))
    res["per_setup"] = per
    bad_stop = [o for o in od if not ((o["stop"] < ctx.C[o["i"]]) if o["side"] > 0 else (o["stop"] > ctx.C[o["i"]]))]
    bad_tgt = [o for o in od if not ((o["target"] > ctx.C[o["i"]]) if o["side"] > 0 else (o["target"] < ctx.C[o["i"]]))]
    res["stop_not_on_losing_side"] = {s: sum(o["tag"] == s for o in bad_stop) for s in per}
    res["target_not_on_winning_side"] = {s: sum(o["tag"] == s for o in bad_tgt) for s in per}
    res["target_not_on_winning_side_traded"] = sum((o["i"], o["tag"]) in taken for o in bad_tgt)
    by_bar = {}
    for o in od:
        by_bar.setdefault(o["i"], []).append(o["tag"])
    multi = {i: t for i, t in by_bar.items() if len(t) > 1}
    res["bars_with_two_setups"] = {"+".join(t): sum(1 for x in multi.values() if x == t) for t in map(list, {tuple(v) for v in multi.values()})}
    why = dict(roll_day=0, no_atr=0, at_or_after_flat_bar=0, position_open_or_same_bar=0, traded=0, other=0)
    for o in od:
        dts = pd.Timestamp(ctx.cdate[o["i"]])
        if (o["i"], o["tag"]) in taken:
            why["traded"] += 1
        elif dts in ctx.roll_dates:
            why["roll_day"] += 1
        elif dts in ctx.noatr_dates:
            why["no_atr"] += 1
        elif o["i"] >= o["exit_i"]:
            why["at_or_after_flat_bar"] += 1
        elif o in bad_stop:
            why["other"] += 1
        else:
            why["position_open_or_same_bar"] += 1
    res["fate_of_orders"] = why
    return res
