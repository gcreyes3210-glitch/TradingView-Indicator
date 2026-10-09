#!/usr/bin/env python3
"""ICT order block + IFVG confirmation (OBI), spec in BACKTEST_LOG.md. Block detection is ob_engine.blocks() (same
bias, BOS, order block and FVG rules as OB1); only the entry differs. Same fill model and costs as orb_engine.py.

    python3 tools/obi_engine.py --tf 1 [--bias none] [--target 2r|extreme|none] [--flat 16:00] [--stop ob|pullback]
                                [--orb-trades t.csv] [--out trades.csv]

Entry (bullish; bearish mirror):
    tap = the first bar after the BOS whose low <= OB high, within 30 bars of the BOS, else the block expires.
    pullback gaps = bearish FVGs (bar[i-2].low > bar[i].high) whose first bar is at or after the BOS bar.
    confirmation = from the tap bar on, the first close above the top (bar[i-2].low) of a pullback gap formed before
      that bar; entry at that close. It must come within 20 bars of the tap and before 11:30, else the block expires.
      A close below the OB low after the BOS and before confirmation invalidates the block. With the opening-range
      bias (known at 09:45), a confirmation before 09:45 cannot be taken: no trade that day.
    stop = OB low - 2 ticks (--stop pullback: lowest low from the BOS to the confirmation bar - 2 ticks)
    target = 2R (--target extreme: the highest high since 18:00 through the entry bar, skip if reward:risk < 1.5;
      --target none: hold to the flat time); skip if the OB height < 4 ticks; flat at the close of the first bar
      at/after 12:00 (--flat). Stop beats target on the same bar; nothing trades after a close entry inside its bar.
Costs: 1 tick slippage on every fill, $1 commission per side, $2/point, 1 contract.
"""
import argparse
import numpy as np
import pandas as pd
from orb_engine import TICK, PT_VALUE, COMM_SIDE, SLIP_TICKS, report
from ob_engine import blocks, P as OB_P, _tick
from amd_engine import _m

TZ = "America/New_York"
P = {**OB_P, "stop": "ob", "tap_bars": 30, "confirm_bars": 20}


def run(one, orb=None, **over):
    p = {**P, **over}
    buf, slip = p["buf_ticks"] * TICK, SLIP_TICKS * TICK
    entry_end = _m(p["entry_end"])
    orb = orb or {}
    trades = []
    cnt = dict(days=0, formed=0, small=0, tapped=0, no_tap=0, invalidated=0, confirmed=0, no_confirm=0,
               early=0, rr=0)
    for A, day in blocks(one, p):
        ts, tod, O, H, L, C, dates, onmask = A.ts, A.tod, A.O, A.H, A.L, A.C, A.dates, A.onmask
        d, iend = day.d, day.iend
        cnt["days"] += 1
        if day.cand is None:
            continue
        cnt["formed"] += 1
        side, j, k = day.cand
        sgn = 1 if side == "L" else -1
        obH, obL = H[j], L[j]
        if obH - obL < p["min_ticks"] * TICK:
            cnt["small"] += 1
            continue
        edge, far = (obH, obL) if side == "L" else (obL, obH)
        # tap (a close through the far side of the block before it also counts as invalidation)
        tap, dead = None, False
        for i in range(k + 1, min(k + 1 + p["tap_bars"], iend)):
            if dates[i] != d:
                break
            if sgn * (C[i] - far) < 0:
                dead = True
                break
            if (L[i] <= edge) if side == "L" else (H[i] >= edge):
                tap = i
                break
        if dead:
            cnt["invalidated"] += 1
            continue
        if tap is None:
            cnt["no_tap"] += 1
            continue
        cnt["tapped"] += 1
        # confirmation: close through the top of a pullback gap (bearish FVG for a long) formed before that bar
        conf = None
        for c in range(tap, min(tap + 1 + p["confirm_bars"], iend)):
            if dates[c] != d or tod[c] >= entry_end:
                break
            if sgn * (C[c] - far) < 0:
                dead = True
                break
            tops = [(L[i - 2] if side == "L" else H[i - 2]) for i in range(k + 2, c)
                    if ((L[i - 2] > H[i]) if side == "L" else (H[i - 2] < L[i]))]
            if any(sgn * (C[c] - t) > 0 for t in tops):
                conf = c
                break
        if dead:
            cnt["invalidated"] += 1
            continue
        if conf is None:
            cnt["no_confirm"] += 1
            continue
        if tod[conf] < day.work_from:
            cnt["early"] += 1
            continue
        cnt["confirmed"] += 1
        if p["stop"] == "ob":
            stop = obL - buf if side == "L" else obH + buf
        else:
            stop = (L[k:conf + 1].min() - buf) if side == "L" else (H[k:conf + 1].max() + buf)
        risk = sgn * (C[conf] - stop)
        if risk <= 0:
            cnt["rr"] += 1
            continue
        if p["target"] == "2r":
            tp = _tick(C[conf] + sgn * 2 * risk)
        elif p["target"] == "extreme":
            seg = np.arange(day.span0, conf + 1)
            seg = seg[onmask[seg] | (dates[seg] == d)]
            tp = H[seg].max() if side == "L" else L[seg].min()
            if sgn * (tp - C[conf]) / risk < p["rr_extreme"]:
                cnt["rr"] += 1
                continue
        else:
            tp = None
        entry = C[conf] + sgn * slip
        out, i = None, conf + 1
        while out is None:
            if (L[i] <= stop) if side == "L" else (H[i] >= stop):
                out = (i, stop, "SL")
            elif tp is not None and ((H[i] >= tp) if side == "L" else (L[i] <= tp)):
                out = (i, tp, "TP")
            elif i >= iend:
                out = (i, C[i], "time")
            i += 1
        xi, xpx, reason = out
        px = xpx - sgn * slip
        pnl = sgn * (px - entry) * PT_VALUE - 2 * COMM_SIDE
        trades.append(dict(side=side, entry_time=ts[conf], entry=entry, exit_time=ts[xi], exit=px, reason=reason,
                           pnl=pnl, risk=risk, R=pnl / (risk * PT_VALUE), tf=p["tf"], ob_h=obH - obL,
                           bos_tap=tap - k, tap_conf=conf - tap, given_up=sgn * (C[conf] - edge) / (obH - obL),
                           day=day.daytype, orb=orb.get(d, "-")))
    return pd.DataFrame(trades), cnt


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--bars1m", default="data/bars/MNQ_1m.parquet")
    ap.add_argument("--tf", type=int, choices=[1, 2, 3, 5], default=1)
    ap.add_argument("--start", default="2019-06-01")
    ap.add_argument("--bias", choices=["orb", "none"], default="orb")
    ap.add_argument("--target", choices=["2r", "extreme", "none"], default="2r")
    ap.add_argument("--flat", default="12:00")
    ap.add_argument("--stop", choices=["ob", "pullback"], default="ob")
    ap.add_argument("--orb-trades")
    ap.add_argument("--out")
    a = ap.parse_args()
    orb = {}
    if a.orb_trades:
        o = pd.read_csv(a.orb_trades)
        orb = dict(zip(pd.to_datetime(o.entry_time, utc=True).dt.tz_convert(TZ).dt.date, o.side))
    tr, cnt = run(pd.read_parquet(a.bars1m), orb, tf=a.tf, start=pd.Timestamp(a.start, tz=TZ), bias=a.bias,
                  target=a.target, flat=a.flat, stop=a.stop)
    print(f"tf {a.tf}m bias {a.bias} target {a.target} flat {a.flat} stop {a.stop}: {len(tr)} trades  funnel {cnt}")
    if len(tr):
        tr["orb_day"] = tr.orb != "-"
        report(tr, groups=("side", "reason", "orb_day"))
    if a.out:
        tr.to_csv(a.out, index=False)
