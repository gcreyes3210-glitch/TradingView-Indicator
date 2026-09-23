#!/usr/bin/env python3
"""VP 80 % rule, overnight value area (VP2y settings of VP_80Rule_strategy.pine). Local engine on the 5m bars with the
overnight profile built from the 1m bars (ivc_engine.profile: 1-point rows, 70 % value area grown two rows at a time,
exactly as the Pine script builds it from 1-minute intrabars).

    python3 tools/vp80_engine.py [--start 2019-06-01] [--end 2026-09-22] [--tv-fills] [--out trades.csv]

Rule (New York time):
    value area = overnight 18:00-09:30 profile, active from the 09:30 bar. The 09:30 open must be above VAH (short
    setup) or below VAL (long setup). From the 09:30 bar on, count consecutive 5m closes inside value (VAL <= close <=
    VAH), reset by a close outside; on the bar that makes the count 6, inside 09:30-12:00, enter toward the far edge at
    that close. Stop = the edge price came in through +/- 0.25 x VA width; target = the opposite edge. Skip if reward:
    risk < 0.8 or risk > 1 x VA width (the day is used up either way). One trade a day, flat at the close of the 16:00
    bar.
Fills: entry at the signal close; stop / target resting from the next bar, on the tick. Default (the project model):
    stop beats target on a bar that touches both, 1 tick slippage on every fill including the target.
    --tv-fills (TradingView's broker emulator, for calibration): a bar that touches both is resolved by TradingView's
    bar path (open -> nearer extreme -> other extreme -> close), and the target limit fills without slippage.
Costs: $1 commission per side, $2/point, 1 contract. --slip 0 reproduces VP_80Rule_strategy.pine, which runs with
slippage = 0 (the TradingView VP records carry no slippage).
"""
import argparse
import numpy as np
import pandas as pd
from orb_engine import TICK, PT_VALUE, COMM_SIDE, SLIP_TICKS, report, _path, exit_bar
from ivc_engine import profile

TZ = "America/New_York"
P = dict(slip_ticks=SLIP_TICKS, accept=6, stop_va=0.25, min_rr=0.8, max_risk_va=1.0, entry_end=12 * 60, tv_fills=False,
         start=pd.Timestamp("2019-06-01", tz=TZ), end=pd.Timestamp("2030-01-01", tz=TZ))


def overnight_profiles(one):
    """{RTH date: (poc, vah, val)} from the 1m bars of the preceding 18:00-09:30 session."""
    tod = one.index.hour * 60 + one.index.minute
    rth_dates = np.array(sorted(set(one.index[(tod >= 570) & (tod < 960)].date)))
    on = one[(tod >= 1080) | (tod < 570)]
    cal = np.array(on.index.date)
    after = (on.index.hour * 60 + on.index.minute) >= 1080
    idx = np.where(after, np.searchsorted(rth_dates, cal, side="right"), np.searchsorted(rth_dates, cal, side="left"))
    keep = idx < len(rth_dates)
    on, idx = on[keep], idx[keep]
    return {rth_dates[k]: profile(g.high.to_numpy(), g.low.to_numpy(), g.volume.to_numpy().astype(float))
            for k, g in on.groupby(idx)}


def run(b5, one, **over):
    p = {**P, **over}
    slip = p["slip_ticks"] * TICK
    prof = overnight_profiles(one)
    ts = b5.index
    tod = np.asarray(ts.hour * 60 + ts.minute)
    O, H, L, C = (b5[k].to_numpy() for k in ("open", "high", "low", "close"))
    dates = np.array(ts.date)
    rth = np.flatnonzero((tod >= 570) & (tod < 960))
    opens = pd.Series(rth, index=dates[rth]).groupby(level=0).min()
    trades, cnt = [], dict(days=0, outside=0, accepted=0, skipped=0)
    for d, i0 in opens.items():
        if ts[i0] < p["start"] or ts[i0] > p["end"] or d not in prof:
            continue
        cnt["days"] += 1
        poc, vah, val = prof[d]
        w = vah - val
        side = "S" if O[i0] > vah else "L" if O[i0] < val else None
        if side is None:
            continue
        cnt["outside"] += 1
        iend = i0
        while iend + 1 < len(ts) and dates[iend + 1] == d and tod[iend + 1] < 960:
            iend += 1
        iend = exit_bar(ts, iend)                       # the 16:00 bar, or the last bar of an early-close session
        acc, sig = 0, None
        for i in range(i0, iend):
            acc = acc + 1 if val <= C[i] <= vah else 0
            if acc == p["accept"]:
                if tod[i] < p["entry_end"]:
                    sig = i
                break
        if sig is None:
            continue
        cnt["accepted"] += 1
        sgn = 1 if side == "L" else -1
        stop = round((val - p["stop_va"] * w if side == "L" else vah + p["stop_va"] * w) / TICK) * TICK
        tp = vah if side == "L" else val
        risk = sgn * (C[sig] - stop)
        rr = sgn * (tp - C[sig]) / risk if risk > 0 else 0
        if risk <= 0 or risk > p["max_risk_va"] * w or rr < p["min_rr"] or sgn * (tp - C[sig]) <= 0:
            cnt["skipped"] += 1
            continue
        entry = C[sig] + sgn * slip
        out = None
        for i in range(sig + 1, iend + 1):
            hit_s = (L[i] <= stop) if side == "L" else (H[i] >= stop)
            hit_t = (H[i] >= tp) if side == "L" else (L[i] <= tp)
            if hit_s and hit_t and p["tv_fills"]:
                pts = _path(O[i], H[i], L[i], C[i])
                first_t = next(k for k in range(4) if (pts[k] >= tp if side == "L" else pts[k] <= tp) or
                               (pts[k] <= stop if side == "L" else pts[k] >= stop))
                hit_s = (pts[first_t] <= stop) if side == "L" else (pts[first_t] >= stop)
                hit_t = not hit_s
            if hit_s:
                out = (i, stop - sgn * slip, "SL")
            elif hit_t:
                out = (i, tp - (0 if p["tv_fills"] else sgn * slip), "TP")
            elif i == iend:
                out = (i, C[i] - sgn * slip, "time")
            if out:
                break
        xi, px, reason = out
        pnl = sgn * (px - entry) * PT_VALUE - 2 * COMM_SIDE
        trades.append(dict(side=side, entry_time=ts[sig], entry=entry, exit_time=ts[xi], exit=px, reason=reason,
                           pnl=pnl, risk=risk, R=pnl / (risk * PT_VALUE), rr=rr, va_w=w, vah=vah, val=val, poc=poc,
                           open_loc="above" if side == "S" else "below"))
    return pd.DataFrame(trades), cnt


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--bars", default="data/bars/MNQ_5m.parquet")
    ap.add_argument("--bars1m", default="data/bars/MNQ_1m.parquet")
    ap.add_argument("--start", default="2019-06-01")
    ap.add_argument("--end", default="2030-01-01")
    ap.add_argument("--tv-fills", action="store_true")
    ap.add_argument("--slip", type=int, default=SLIP_TICKS, help="slippage ticks per fill (Pine script: 0)")
    ap.add_argument("--out")
    a = ap.parse_args()
    tr, cnt = run(pd.read_parquet(a.bars), pd.read_parquet(a.bars1m), start=pd.Timestamp(a.start, tz=TZ),
                  end=pd.Timestamp(a.end, tz=TZ), tv_fills=a.tv_fills, slip_ticks=a.slip)
    print(f"{a.start} -> {a.end}  tv fills {a.tv_fills} slip {a.slip}: {len(tr)} trades  {cnt}")
    if len(tr):
        report(tr, groups=("side", "reason"))
    if a.out:
        tr.to_csv(a.out, index=False)
