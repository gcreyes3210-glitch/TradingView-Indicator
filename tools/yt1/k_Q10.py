#!/usr/bin/env python3
"""K-Q10 - the mean MNQ return of each of the 24 clock hours, New York time (YT11_SPEC.md, Q10, "Reported").

Published, on ES (N06, Boyarchenko, Larsen and Whelan, 1998-2020, Table I, basis points per day before costs):
00:00-01:00 +0.46 (t 2.8), 01:00-02:00 +0.43 (t 2.8), 02:00-03:00 +1.5 (t 7.1; 1.48 in the introduction),
17:00-18:00 -0.43 (t -3.6); "the other hours are flat". MNQ does not trade 17:00-18:00.

Definitions (fixed before the first run, see notes/K-Q10.md):
  * hour H (0 .. 23) = from the close of the bar stamped (H-1):59 to the close of the bar stamped H:59, by the wall
    clock (hour 0 starts at the 23:59 bar of the previous calendar date). Both bars must exist; a day on which
    either minute has no bar is not counted for that hour.
  * an hour belongs to the trading day of its H:59 bar (18:00 and later belong to the next day). Only trading days
    that are cash days of the day table are counted, and roll days are excluded (the contract changes at 19:00 or
    20:00 on the evening before a roll day, inside that trading day). The two bars must be the same contract.
  * return in basis points = (close / close - 1) x 10,000; in points = the difference of the two closes.
    t = mean / (standard deviation / sqrt(n)), n = the number of days counted.
  * MNQ is shut 17:00-18:00, so hours 17 and 18 have no (H-1):59 / H:59 pair on a normal day (a stray 17:59 bar
    gives them a handful of days at most). Two rows outside the 24 stand in for them: `17_halt` = the close of the
    16:59 bar to the open of the 18:00 bar of the same calendar date (the daily halt, Monday to Thursday evenings;
    the weekend gap is not in it), and `18_from_open` = the open of the 18:00 bar to the close of the 18:59 bar.
"""
import numpy as np
import pandas as pd
import core

NAME = "Mean MNQ return of each of the 24 clock hours (New York), roll days excluded"
CLAIMED_ES_BP = {0: 0.46, 1: 0.43, 2: 1.5, 17: -0.43}       # N06 Table I, ES 1998-2020; the others "flat"
CLAIMED_ES_T = {0: 2.8, 1: 2.8, 2: 7.1, 17: -3.6}


def _stat(p0, p1):
    p0, p1 = np.asarray(p0, float), np.asarray(p1, float)
    n = int(len(p0))
    if n == 0:
        return dict(n=0, mean_bp=None, t_bp=None, mean_pts=None, t_pts=None)
    bp, pts = (p1 / p0 - 1) * 1e4, p1 - p0

    def t(x):
        s = x.std(ddof=1) if n > 1 else 0.0
        return round(float(x.mean() / (s / np.sqrt(n))), 2) if s > 0 else None

    return dict(n=n, mean_bp=round(float(bp.mean()), 3), t_bp=t(bp), mean_pts=round(float(pts.mean()), 3),
                t_pts=t(pts), sd_bp=round(float(bp.std(ddof=1)), 2) if n > 1 else None,
                share_up=round(float((pts > 0).mean()), 4))


def measure(ctx):
    O, C, tod, iid = ctx.O, ctx.C, ctx.tod, ctx.iid
    naive = ctx.ts.tz_localize(None)                         # New York wall clock
    assert naive.is_unique, "a wall-clock minute appears twice"
    pos = pd.Series(np.arange(ctx.n), index=naive)
    tday = pd.DatetimeIndex(ctx.tdate)
    ok_day = pd.Series(True, index=ctx.days.index)
    ok_day[list(ctx.roll_dates)] = False

    def find(end, back_min):
        """For the bars `end`: the bar stamped back_min minutes earlier on the wall clock (-1 if none)."""
        p = pos.reindex(naive[end] - pd.Timedelta(minutes=back_min)).to_numpy()
        return np.where(np.isnan(p), -1, p).astype(int)

    def keep(end, start, cnt):
        """The pairs to count, and what was left out."""
        cash = tday[end].isin(ctx.days.index)
        roll = cash & tday[end].isin(list(ctx.roll_dates))
        has = start >= 0
        same = has & (iid[np.maximum(start, 0)] == iid[end])
        cnt["not_a_cash_trading_day"] += int((~cash).sum())
        cnt["roll_day"] += int(roll.sum())
        cnt["start_bar_missing"] += int((cash & ~roll & ~has).sum())
        cnt["contract_change"] += int((cash & ~roll & has & ~same).sum())
        return cash & ~roll & has & same

    cnt = dict(not_a_cash_trading_day=0, roll_day=0, start_bar_missing=0, contract_change=0)
    days_ok = int(ok_day.sum())
    hours = {}
    for h in range(24):
        end = np.flatnonzero(tod == h * 60 + 59)             # bars stamped H:59
        start = find(end, 60)                                # bars stamped (H-1):59
        m = keep(end, start, cnt)
        r = _stat(C[start[m]], C[end[m]])
        r["hour"] = f"{h:02d}:00-{(h + 1) % 24:02d}:00"
        r["days_without_the_pair"] = days_ok - r["n"]
        if h in CLAIMED_ES_BP:
            r["claimed_es_bp"], r["claimed_es_t"] = CLAIMED_ES_BP[h], CLAIMED_ES_T[h]
        hours[f"{h:02d}"] = r
    # the two hours around the daily halt, which the definition cannot measure (outside the 24 rows)
    c2 = dict(cnt)                                           # their left-out pairs are not added to the counts
    b1800 = np.flatnonzero(tod == 18 * 60)                   # bars stamped 18:00
    s1659 = find(b1800, 61)                                  # the 16:59 bar of the same calendar date
    m1 = keep(b1800, s1659, c2)
    end = np.flatnonzero(tod == 18 * 60 + 59)
    s1800 = find(end, 59)                                    # the 18:00 bar
    m2 = keep(end, s1800, c2)
    extra = {"17_halt": dict(_stat(C[s1659[m1]], O[b1800[m1]]), hour="16:59 close -> 18:00 open"),
             "18_from_open": dict(_stat(O[s1800[m2]], C[end[m2]]), hour="18:00 open -> 18:59 close")}
    q10 = hours["02"]
    return dict(definition="hour H = close of the (H-1):59 bar -> close of the H:59 bar, New York wall clock; trading "
                           "days that are cash days of the day table; roll days excluded",
                span=f"{ctx.days.index[0].date()} -> {ctx.days.index[-1].date()}",
                cash_days=int(len(ctx.days)), roll_days=int(len(ctx.roll_dates)), days_counted_at_most=days_ok,
                left_out_hour_pairs=cnt,
                q10_hour=dict(hour=q10["hour"], n=q10["n"], mean_bp=q10["mean_bp"], t_bp=q10["t_bp"],
                              mean_pts=q10["mean_pts"], claimed_es_bp=1.48, cost_round_trip_pts=1.5),
                hours=hours, outside_the_24=extra)


def show(res):
    print(res["definition"])
    print(f"span {res['span']}   cash days {res['cash_days']}, roll days {res['roll_days']}, "
          f"days counted at most {res['days_counted_at_most']}   left out: {res['left_out_hour_pairs']}")

    def line(k, r):
        if not r["n"]:
            return f"  {k:<13} {r['hour']:<26} n     0"
        t_bp = f"{r['t_bp']:+6.2f}" if r["t_bp"] is not None else "     -"
        t_pt = f"{r['t_pts']:+6.2f}" if r["t_pts"] is not None else "     -"
        cl = f"   ES published {r['claimed_es_bp']:+.2f} bp (t {r['claimed_es_t']:+.1f})" if "claimed_es_bp" in r else ""
        return (f"  {k:<13} {r['hour']:<26} n {r['n']:>5}  mean {r['mean_bp']:>+7.3f} bp  t {t_bp}"
                f"   {r['mean_pts']:>+7.3f} pts  t {t_pt}   up {r['share_up']:.1%}{cl}")

    for k, r in res["hours"].items():
        print(line(k, r))
    print("outside the 24 rows (MNQ is shut 17:00-18:00, so there is no 17:59 bar to end hour 17 or start hour 18):")
    for k, r in res["outside_the_24"].items():
        print(line(k, r))
    q = res["q10_hour"]
    print(f"Q10's hour {q['hour']}: {q['mean_bp']:+.3f} bp = {q['mean_pts']:+.3f} points a day before costs "
          f"(n {q['n']}, t {q['t_bp']}); published on ES {q['claimed_es_bp']} bp; a round trip costs "
          f"{q['cost_round_trip_pts']} points")
