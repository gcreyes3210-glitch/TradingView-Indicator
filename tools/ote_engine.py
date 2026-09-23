#!/usr/bin/env python3
"""ICT optimal trade entry (OTE), spec in BACKTEST_LOG.md. Same fill model and costs as orb_engine.py; bars resampled
from the 1-minute Parquet to --tf 1/2/3/5 minutes, stamped by open time; fractal / FVG helpers from ob_engine.py.

    python3 tools/ote_engine.py --tf 1 [--f 0.62] [--target leg|opposite|none|2r] [--liq overnight|prevday]
                                [--continuation] [--orb-trades t.csv] [--out trades.csv]

Rule (bullish; bearish mirror), New York time, on the TF bars:
    liquidity = overnight (18:00-09:30) low (--liq prevday: previous cash session's low).
    sweep = the first bar from 09:30 and before 11:00 whose low < liquidity (a bar through both sides: day skipped);
      the first sweep of the day decides the setup.
    MSS = the first close after the sweep bar above the most recent 3-bar fractal high confirmed since 09:30 before the
      sweep bar (none -> no setup), by 11:15; sweep low = lowest low from the sweep bar to the MSS bar; the leg (sweep
      low bar .. MSS bar) must hold a bullish FVG; leg = running high - sweep low, >= 8 ticks at the MSS.
    entry: limit at level = running high - f x leg (f = 0.705), where the running high is taken through the previous
      bar (the resting order), working from the bar after the MSS for 30 bars and before 11:30; filled at the level
      when a bar's low <= level; if that bar's low also <= stop, stopped on that bar.
    stop = sweep low - 2 ticks; target = the running high at the fill (--target opposite: overnight high, skip if
      reward:risk < 1.5 at the fill; none: hold to 12:00; 2r). Stop beats target; flat at the close of the first bar
      at/after 12:00. One trade a day.
    --continuation (f): no sweep; bias from the 09:30-09:45 range vs the overnight range (high broken -> bullish, low ->
      bearish, both -> either, inside -> none); setup = the first close from 09:45 to 11:00 above the latest confirmed
      fractal high since 09:30 (first close above it) in an allowed direction, leg low = lowest low from the fractal bar
      to the MSS bar, same FVG, leg, entry, stop (leg low - 2 ticks) and target.
Costs: 1 tick slippage on every fill, $1 commission per side, $2/point, 1 contract.
"""
import argparse
import numpy as np
import pandas as pd
from orb_engine import TICK, PT_VALUE, COMM_SIDE, SLIP_TICKS, report
from amd_engine import resample, in_win, _m
from ob_engine import _tick, fractal_high, fractal_low, bull_fvg, bear_fvg

TZ = "America/New_York"
P = dict(tf=1, f=0.705, target="leg", liq="overnight", continuation=False, sweep_end="11:00", mss_end="11:15",
         entry_end="11:30", flat="12:00", valid_bars=30, buf_ticks=2, min_leg_ticks=8, rr_opp=1.5,
         start=pd.Timestamp("2019-06-01", tz=TZ))


def run(one, orb=None, **over):
    p = {**P, **over}
    buf, slip = p["buf_ticks"] * TICK, SLIP_TICKS * TICK
    bars = resample(one, p["tf"])
    ts = bars.index
    tod = np.asarray(ts.hour * 60 + ts.minute)
    O, H, L, C = (bars[k].to_numpy() for k in ("open", "high", "low", "close"))
    dates = np.array(ts.date)
    rthm = (tod >= 570) & (tod < 960)
    rth = np.flatnonzero(rthm)
    opens = pd.Series(rth, index=dates[rth]).groupby(level=0).min()
    onmask = in_win(tod, "18:00", "09:30")
    sweep_end, mss_end, entry_end, flat = (_m(p[k]) for k in ("sweep_end", "mss_end", "entry_end", "flat"))
    orb = orb or {}

    trades = []
    cnt = dict(days=0, sweeps=0, ambiguous=0, no_fractal=0, mss=0, no_fvg=0, small=0, filled=0, expired=0, rr=0)
    prev_open = None
    for d, i0 in opens.items():
        span0, prev_open = (prev_open + 1 if prev_open is not None else 0), i0
        if ts[i0] < p["start"] or span0 == 0:
            continue
        on_idx = np.arange(span0, i0)[onmask[span0:i0]]
        pd_idx = np.arange(span0, i0)[rthm[span0:i0]]
        if len(on_idx) == 0 or len(pd_idx) == 0:
            continue
        onH, onL = H[on_idx].max(), L[on_idx].min()
        liqH, liqL = (onH, onL) if p["liq"] == "overnight" else (H[pd_idx].max(), L[pd_idx].min())
        orb_i = np.arange(i0, min(i0 + 16, len(ts)))
        orb_i = orb_i[(tod[orb_i] < 585) & (dates[orb_i] == d)]
        orH, orL = H[orb_i].max(), L[orb_i].min()
        daytype = "both" if orH > onH and orL < onL else "high" if orH > onH else "low" if orL < onL else "inside"
        iend = i0
        while iend + 1 < len(ts) and dates[iend + 1] == d and tod[iend + 1] < flat:
            iend += 1
        iend = min(iend + 1, len(ts) - 1)
        day = [i for i in range(i0, iend) if dates[i] == d]
        cnt["days"] += 1

        def last_fractal(side, before):
            """(price, centre) of the latest fractal high (L side) / low (S side) confirmed before bar `before`."""
            for m in range(before - 2, i0, -1):
                if (fractal_high(H, m) if side == "L" else fractal_low(L, m)):
                    return (H[m] if side == "L" else L[m]), m
            return None

        setup = None
        if not p["continuation"]:
            s = side = None
            for k in day:
                if tod[k] >= sweep_end:
                    break
                up, dn = H[k] > liqH, L[k] < liqL
                if up and dn:
                    cnt["ambiguous"] += 1
                    break
                if up or dn:
                    s, side = k, ("S" if up else "L")
                    break
            if s is None:
                continue
            cnt["sweeps"] += 1
            fr = last_fractal(side, s)
            if fr is None:
                cnt["no_fractal"] += 1
                continue
            sgn = 1 if side == "L" else -1
            mss = next((k for k in day if k > s and tod[k] < mss_end and sgn * (C[k] - fr[0]) > 0), None)
            if mss is None:
                continue
            seg = np.arange(s, mss + 1)
            lo_i = seg[np.argmin(L[seg])] if side == "L" else seg[np.argmax(H[seg])]
            setup = (side, lo_i, mss)
        else:
            allowed = {"high": "L", "low": "S", "both": "LS", "inside": ""}[daytype]
            if not allowed:
                continue
            fh = fl = None
            for k in day:
                m = k - 1
                if m - 1 >= i0:
                    if fractal_high(H, m):
                        fh = (H[m], m, False)
                    if fractal_low(L, m):
                        fl = (L[m], m, False)
                if tod[k] >= sweep_end:
                    break
                for side in ("L", "S"):
                    f = fh if side == "L" else fl
                    if f is None or f[2] or f[1] + 1 >= k:
                        continue
                    if not ((C[k] > f[0]) if side == "L" else (C[k] < f[0])):
                        continue
                    if side == "L":
                        fh = (f[0], f[1], True)
                    else:
                        fl = (f[0], f[1], True)
                    if side in allowed and tod[k] >= 585 and setup is None:
                        seg = np.arange(f[1], k + 1)
                        lo_i = seg[np.argmin(L[seg])] if side == "L" else seg[np.argmax(H[seg])]
                        setup = (side, lo_i, k)
                if setup is not None:
                    break
            if setup is None:
                continue
            cnt["sweeps"] += 1
        side, lo_i, mss = setup
        sgn = 1 if side == "L" else -1
        cnt["mss"] += 1
        if not any((bull_fvg(H, L, i) if side == "L" else bear_fvg(H, L, i)) for i in range(lo_i + 2, mss + 1)):
            cnt["no_fvg"] += 1
            continue
        base = L[lo_i] if side == "L" else H[lo_i]                       # 0 % of the leg
        run_ext = H[lo_i:mss + 1].max() if side == "L" else L[lo_i:mss + 1].min()
        if sgn * (run_ext - base) < p["min_leg_ticks"] * TICK:
            cnt["small"] += 1
            continue
        stop = base - buf if side == "L" else base + buf
        fill = None
        deepest = 0.0
        for i in range(mss + 1, min(mss + 1 + p["valid_bars"], iend)):
            if dates[i] != d or tod[i] >= entry_end:
                break
            leg = sgn * (run_ext - base)
            level = _tick(run_ext - sgn * p["f"] * leg)
            if (L[i] <= level) if side == "L" else (H[i] >= level):
                fill = (i, level, run_ext, leg)
                break
            run_ext = max(run_ext, H[i]) if side == "L" else min(run_ext, L[i])
        if fill is None:
            cnt["expired"] += 1
            continue
        i, level, ext, leg = fill
        risk = sgn * (level - stop)
        if p["target"] == "leg":
            tp = ext
        elif p["target"] == "opposite":
            tp = onH if side == "L" else onL
            if sgn * (tp - level) / risk < p["rr_opp"]:
                cnt["rr"] += 1
                continue
        elif p["target"] == "2r":
            tp = _tick(level + sgn * 2 * risk)
        else:
            tp = None
        rr = None if tp is None else sgn * (tp - level) / risk
        cnt["filled"] += 1
        entry = level + sgn * slip
        if (L[i] <= stop) if side == "L" else (H[i] >= stop):
            out = (i, stop, "SL")
        else:
            out, x = None, i + 1
            while out is None:
                if (L[x] <= stop) if side == "L" else (H[x] >= stop):
                    out = (x, stop, "SL")
                elif tp is not None and ((H[x] >= tp) if side == "L" else (L[x] <= tp)):
                    out = (x, tp, "TP")
                elif x >= iend:
                    out = (x, C[x], "time")
                x += 1
        xi, xpx, reason = out
        worst = L[i:xi + 1].min() if side == "L" else H[i:xi + 1].max()
        deepest = sgn * (ext - worst) / leg
        px = xpx - sgn * slip
        pnl = sgn * (px - entry) * PT_VALUE - 2 * COMM_SIDE
        trades.append(dict(side=side, entry_time=ts[i], entry=entry, exit_time=ts[xi], exit=px, reason=reason, pnl=pnl,
                           risk=risk, R=pnl / (risk * PT_VALUE), rr=rr, tf=p["tf"], leg=leg, deepest=deepest,
                           bars=i - mss, day=daytype, orb=orb.get(d, "-")))
    return pd.DataFrame(trades), cnt


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--bars1m", default="data/bars/MNQ_1m.parquet")
    ap.add_argument("--tf", type=int, choices=[1, 2, 3, 5], default=1)
    ap.add_argument("--start", default="2019-06-01")
    ap.add_argument("--f", type=float, default=P["f"])
    ap.add_argument("--target", choices=["leg", "opposite", "none", "2r"], default=P["target"])
    ap.add_argument("--liq", choices=["overnight", "prevday"], default=P["liq"])
    ap.add_argument("--continuation", action="store_true")
    ap.add_argument("--orb-trades")
    ap.add_argument("--out")
    a = ap.parse_args()
    orb = {}
    if a.orb_trades:
        o = pd.read_csv(a.orb_trades)
        orb = dict(zip(pd.to_datetime(o.entry_time, utc=True).dt.tz_convert(TZ).dt.date, o.side))
    tr, cnt = run(pd.read_parquet(a.bars1m), orb, tf=a.tf, start=pd.Timestamp(a.start, tz=TZ), f=a.f,
                  target=a.target, liq=a.liq, continuation=a.continuation)
    print(f"tf {a.tf}m f {a.f} target {a.target} liq {a.liq} continuation {a.continuation}: {len(tr)} trades  "
          f"funnel {cnt}")
    if len(tr):
        tr["orb_day"] = tr.orb != "-"
        report(tr, groups=("side", "reason", "orb_day"))
    if a.out:
        tr.to_csv(a.out, index=False)
