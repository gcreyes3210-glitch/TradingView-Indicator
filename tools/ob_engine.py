#!/usr/bin/env python3
"""ICT order block (OB) pullback entry, spec in BACKTEST_LOG.md. Same fill model and costs as orb_engine.py; bars
resampled from the 1-minute Parquet to --tf 1/2/3/5 minutes, stamped by open time.

    python3 tools/ob_engine.py --tf 1 [--limit top|mid] [--stop ob|leg] [--target 2r|extreme|none] [--flat 16:00]
                               [--bias orb|15m|none] [--form-end 12:00 --entry-end 13:00] [--no-fvg]
                               [--orb-trades t.csv] [--out trades.csv]

Rule (New York time, on the TF bars):
    bias (default 'orb', known at 09:45): the 09:30-09:45 range broke the overnight (18:00-09:30) high -> bullish, the
      low -> bearish, both -> either, inside -> no trade. '15m': direction of the last 15-minute 3-bar fractal break
      (first 15m close beyond the latest confirmed 15m fractal) on 15m bars closed by 09:45. 'none': either side.
    BOS (bullish): the first close above the latest 3-bar fractal high whose three bars are at/after 09:30 and which is
      confirmed before the BOS bar. Order block: the latest down-close bar (close < open) among the 3 bars before the
      BOS such that the leg (OB bar .. BOS bar) holds a bullish FVG (bar[i-2].high < bar[i].low); OB bar between
      09:30 and 11:00 (--form-end). Bearish mirror. --ob2: the block is instead the opposite-close candle holding the
      displacement leg's extreme (bullish: the lowest low between the broken fractal and the BOS bar); the leg must travel
      >= 2 x ATR(20) at the BOS and the 30 bars before the block must span >= 2 x ATR(20) at the block (else chop, void). Candidates are taken in BOS order; the first one in an allowed
      direction is the day's candidate (one per day). OB height < 4 ticks -> skipped, day used up.
    entry: limit at the OB high (--limit mid: the OB midpoint, on the tick) for the 30 bars after the BOS, working from
      09:45 when the bias needs the opening range; filled at the limit when a bar's low <= limit (bearish mirror),
      entries until 11:30 (--entry-end). A touch of the limit or the stop before the order is working uses the block
      up (it is no longer fresh). If the fill bar also reaches the stop, the trade is stopped on that bar.
    stop = OB low - 2 ticks (--stop leg: OB low - 0.1 x leg, leg = leg extreme - OB low; mirror)
    target = 2R (--target extreme: the highest high since 18:00 through the fill bar, skip if reward:risk < 1.5;
      --target none: hold to the flat time). Flat at the close of the first bar at/after 12:00 (--flat).
    Stop beats target on the same bar. Costs: 1 tick slippage on every fill, $1 commission per side, $2/point.
"""
import argparse
import numpy as np
import pandas as pd
from orb_engine import TICK, PT_VALUE, COMM_SIDE, SLIP_TICKS, report, exit_bar
from amd_engine import resample, in_win, _m

TZ = "America/New_York"
P = dict(tf=1, limit="top", stop="ob", target="2r", flat="12:00", bias="orb", form_end="11:00", entry_end="11:30",
         fvg=True, chop20=None, block="ob1", min_leg_atr=2.0, chop_bars=30, chop_atr=2.0, valid_bars=30, buf_ticks=2, min_ticks=4, stop_leg=0.1, rr_extreme=1.5,
         start=pd.Timestamp("2019-06-01", tz=TZ))


def _tick(x):
    return round(x / TICK) * TICK


# shared ICT helpers (3-bar fractals centred at m, FVGs completed at bar i)
def fractal_high(H, m):
    return H[m] > H[m - 1] and H[m] > H[m + 1]


def fractal_low(L, m):
    return L[m] < L[m - 1] and L[m] < L[m + 1]


def bull_fvg(H, L, i):
    return H[i - 2] < L[i]


def bear_fvg(H, L, i):
    return L[i - 2] > H[i]


def bias_15m(one):
    """Per date: direction of the last 15m fractal break on 15m bars that closed by 09:45 ('L' / 'S')."""
    b = resample(one, 15)
    H, L, C = b.high.to_numpy(), b.low.to_numpy(), b.close.to_numpy()
    ts = b.index
    last, fh, fl, fh_used, fl_used = None, None, None, True, True
    out, state = {}, []
    for i in range(len(b)):
        if i >= 2 and H[i - 1] > H[i - 2] and H[i - 1] > H[i]:
            fh, fh_used = H[i - 1], False
        if i >= 2 and L[i - 1] < L[i - 2] and L[i - 1] < L[i]:
            fl, fl_used = L[i - 1], False
        if fh is not None and not fh_used and C[i] > fh:
            last, fh_used = "L", True
        if fl is not None and not fl_used and C[i] < fl:
            last, fl_used = "S", True
        state.append(last)
    s = pd.Series(state, index=ts)
    at = s[(ts.hour == 9) & (ts.minute == 30)]          # the 09:30 15m bar closes at 09:45
    return {t.date(): v for t, v in at.items()}


def blocks(one, p):
    """Yield (A, day) for every day with a tradable bias: A holds the TF bar arrays (the same object every time),
    day the session indices and the day's candidate block cand = (side, OB bar j, BOS bar k) or None."""
    from types import SimpleNamespace
    bars = resample(one, p["tf"])
    ts = bars.index
    tod = np.asarray(ts.hour * 60 + ts.minute)
    O, H, L, C = (bars[k].to_numpy() for k in ("open", "high", "low", "close"))
    dates = np.array(ts.date)
    rth = np.flatnonzero((tod >= 570) & (tod < 960))
    opens = pd.Series(rth, index=dates[rth]).groupby(level=0).min()
    onmask = in_win(tod, "18:00", "09:30")
    form_end, flat = _m(p["form_end"]), _m(p["flat"])
    b15 = bias_15m(one) if p["bias"] == "15m" else {}
    pc = np.r_[np.nan, C[:-1]]
    atr = pd.Series(np.nanmax(np.c_[H - L, np.abs(H - pc), np.abs(L - pc)], axis=1)).rolling(20).mean().to_numpy()
    A = SimpleNamespace(ts=ts, tod=tod, O=O, H=H, L=L, C=C, dates=dates, onmask=onmask, atr=atr)

    prev_open = None
    for d, i0 in opens.items():
        span0, prev_open = (prev_open + 1 if prev_open is not None else 0), i0
        if ts[i0] < p["start"] or span0 == 0:
            continue
        on_idx = np.arange(span0, i0)[onmask[span0:i0]]
        if len(on_idx) == 0:
            continue
        onH, onL = H[on_idx].max(), L[on_idx].min()
        orb_i = np.arange(i0, min(i0 + 16, len(ts)))
        orb_i = orb_i[(tod[orb_i] < 585) & (dates[orb_i] == d)]
        orH, orL = H[orb_i].max(), L[orb_i].min()
        daytype = "both" if orH > onH and orL < onL else "high" if orH > onH else "low" if orL < onL else "inside"
        if p["bias"] == "orb":
            allowed = {"high": "L", "low": "S", "both": "LS", "inside": ""}[daytype]
            work_from = 585
        elif p["bias"] == "15m":
            allowed = b15.get(d) or ""
            work_from = 585
        else:
            allowed, work_from = "LS", 570
        if not allowed:
            continue
        iend = i0
        while iend + 1 < len(ts) and dates[iend + 1] == d and tod[iend + 1] < flat:
            iend += 1
        iend = exit_bar(ts, iend)                       # early close: the session's last bar

        # scan for the day's candidate, in BOS order
        cand = frac = None
        fh = fl = None            # (price, center index) of the latest confirmed fractal high / low
        fh_brk = fl_brk = True
        k = i0
        while k < iend and dates[k] == d:
            m = k - 1                                  # a fractal centred at m is confirmed by bar k (= m + 1)
            if m - 1 >= i0:
                if H[m] > H[m - 1] and H[m] > H[m + 1]:
                    fh, fh_brk = (H[m], m), False
                if L[m] < L[m - 1] and L[m] < L[m + 1]:
                    fl, fl_brk = (L[m], m), False
            for side in ("L", "S"):
                f, brk = (fh, fh_brk) if side == "L" else (fl, fl_brk)
                if f is None or brk or f[1] + 1 >= k:  # must be confirmed before the BOS bar
                    continue
                if not ((C[k] > f[0]) if side == "L" else (C[k] < f[0])):
                    continue
                if side == "L":
                    fh_brk = True
                else:
                    fl_brk = True
                if side not in allowed or cand is not None:
                    continue
                if p["block"] == "extreme":
                    # OB2: the block is the opposite-close candle holding the displacement leg's extreme (bullish: the
                    # lowest low between the broken fractal and the BOS), the leg travels >= min_leg_atr x ATR(20), and
                    # the chop_bars bars before the block span >= chop_atr x ATR(20); otherwise not a candidate
                    seg = np.arange(f[1], k + 1)
                    j = seg[np.argmin(L[seg])] if side == "L" else seg[np.argmax(H[seg])]
                    down = (C[j] < O[j]) if side == "L" else (C[j] > O[j])
                    travel = (H[j:k + 1].max() - L[j]) if side == "L" else (H[j] - L[j:k + 1].min())
                    pre = np.arange(max(j - p["chop_bars"], 0), j)
                    span = H[pre].max() - L[pre].min() if len(pre) == p["chop_bars"] else 0.0
                    fvg = any((H[i - 2] < L[i]) if side == "L" else (L[i - 2] > H[i]) for i in range(j + 2, k + 1))
                    if (j >= i0 and tod[j] < form_end and down and travel >= p["min_leg_atr"] * atr[k]
                            and span >= p["chop_atr"] * atr[j] and (fvg or not p["fvg"])):
                        cand = (side, j, k)
                        frac = f
                    continue
                for j in range(k - 1, max(k - 4, i0 - 1), -1):
                    if tod[j] >= form_end or not ((C[j] < O[j]) if side == "L" else (C[j] > O[j])):
                        continue
                    fvg = any((H[i - 2] < L[i]) if side == "L" else (L[i - 2] > H[i]) for i in range(j + 2, k + 1))
                    if fvg or not p["fvg"]:
                        cand = (side, j, k)
                        frac = f
                        break
            if cand is not None:
                break
            k += 1
        yield A, SimpleNamespace(d=d, i0=i0, iend=iend, span0=span0, daytype=daytype, work_from=work_from, cand=cand, frac=frac)


def run(one, orb=None, **over):
    p = {**P, **over}
    buf, slip = p["buf_ticks"] * TICK, SLIP_TICKS * TICK
    entry_end = _m(p["entry_end"])
    orb = orb or {}

    trades = []
    cnt = dict(days=0, candidates=0, filled=0, expired=0, small=0, used_early=0, rr=0)
    for A, day in blocks(one, p):
        ts, tod, O, H, L, C, dates, onmask = A.ts, A.tod, A.O, A.H, A.L, A.C, A.dates, A.onmask
        d, i0, iend, span0, daytype, work_from = day.d, day.i0, day.iend, day.span0, day.daytype, day.work_from
        cnt["days"] += 1
        cand = day.cand
        if cand is None:
            continue
        cnt["candidates"] += 1
        side, j, k = cand
        if p["chop20"]:
            # chop rule: no entry if the 20 bars before the setup (BOS) bar span < chop20 x ATR(20) of those bars
            pre = np.arange(max(k - 20, 0), k)
            if H[pre].max() - L[pre].min() < p["chop20"] * A.atr[k - 1]:
                cnt["chop20"] = cnt.get("chop20", 0) + 1
                continue
        sgn = 1 if side == "L" else -1
        obH, obL = H[j], L[j]
        if obH - obL < p["min_ticks"] * TICK:
            cnt["small"] += 1
            continue
        leg = (H[j:k + 1].max() - obL) if side == "L" else (obH - L[j:k + 1].min())
        lim = (obH if side == "L" else obL) if p["limit"] == "top" else _tick((obH + obL) / 2)
        if p["stop"] == "ob":
            stop = obL - buf if side == "L" else obH + buf
        else:
            stop = _tick(obL - p["stop_leg"] * leg) if side == "L" else _tick(obH + p["stop_leg"] * leg)
        # resting limit for the next valid_bars bars
        fill = None
        for i in range(k + 1, min(k + 1 + p["valid_bars"], iend)):
            if dates[i] != d or tod[i] >= entry_end:
                break
            touched = (L[i] <= lim) if side == "L" else (H[i] >= lim)
            if tod[i] < work_from:
                if touched or ((L[i] <= stop) if side == "L" else (H[i] >= stop)):
                    cnt["used_early"] += 1
                    fill = "dead"
                    break
                continue
            if touched:
                fill = i
                break
        if fill is None:
            cnt["expired"] += 1
            continue
        if fill == "dead":
            continue
        risk = sgn * (lim - stop)
        if p["target"] == "2r":
            tp = _tick(lim + sgn * 2 * risk)
        elif p["target"] == "extreme":
            seg = np.arange(span0, fill + 1)
            seg = seg[onmask[seg] | (dates[seg] == d)]
            tp = H[seg].max() if side == "L" else L[seg].min()
            if sgn * (tp - lim) / risk < p["rr_extreme"]:
                cnt["rr"] += 1
                continue
        else:
            tp = None
        cnt["filled"] += 1
        entry = lim + sgn * slip
        if (L[fill] <= stop) if side == "L" else (H[fill] >= stop):
            out = (fill, stop, "SL")
        else:
            out, i = None, fill + 1
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
        trades.append(dict(side=side, entry_time=ts[fill], entry=entry, exit_time=ts[xi], exit=px, reason=reason,
                           pnl=pnl, risk=risk, R=pnl / (risk * PT_VALUE), tf=p["tf"], bias=p["bias"], ob_h=obH - obL,
                           leg_x=leg / (obH - obL), bars=fill - k, limit=p["limit"], day=daytype,
                           orb=orb.get(d, "-"),
                           # geometry (for charts): order-block bar, BOS bar, the fractal it broke, the orders
                           ob_t=ts[j], ob_hi=obH, ob_lo=obL, bos_t=ts[k], frac_t=ts[day.frac[1]], frac_px=day.frac[0],
                           lim=lim, stop=stop, tp=tp))
    return pd.DataFrame(trades), cnt


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--bars1m", default="data/bars/MNQ_1m.parquet")
    ap.add_argument("--tf", type=int, choices=[1, 2, 3, 5], default=P["tf"])
    ap.add_argument("--start", default="2019-06-01")
    ap.add_argument("--limit", choices=["top", "mid"], default=P["limit"])
    ap.add_argument("--stop", choices=["ob", "leg"], default=P["stop"])
    ap.add_argument("--target", choices=["2r", "extreme", "none"], default=P["target"])
    ap.add_argument("--flat", default=P["flat"])
    ap.add_argument("--bias", choices=["orb", "15m", "none"], default=P["bias"])
    ap.add_argument("--form-end", default=P["form_end"])
    ap.add_argument("--entry-end", default=P["entry_end"])
    ap.add_argument("--no-fvg", action="store_true")
    ap.add_argument("--chop20", type=float, help="chop rule: skip if the 20 bars before the BOS span < x ATR(20)")
    ap.add_argument("--ob2", action="store_true", help="OB2: block = opposite-close candle at the leg extreme, leg >= 2 ATR,"
                                                      " void if the 30 bars before it span < 2 ATR")
    ap.add_argument("--orb-trades")
    ap.add_argument("--out")
    a = ap.parse_args()
    orb = {}
    if a.orb_trades:
        o = pd.read_csv(a.orb_trades)
        orb = dict(zip(pd.to_datetime(o.entry_time, utc=True).dt.tz_convert(TZ).dt.date, o.side))
    tr, cnt = run(pd.read_parquet(a.bars1m), orb, tf=a.tf, start=pd.Timestamp(a.start, tz=TZ), limit=a.limit,
                  stop=a.stop, target=a.target, flat=a.flat, bias=a.bias, form_end=a.form_end, entry_end=a.entry_end,
                  fvg=not a.no_fvg, chop20=a.chop20, **(dict(block="extreme") if a.ob2 else {}))
    print(f"tf {a.tf}m limit {a.limit} stop {a.stop} target {a.target} flat {a.flat} bias {a.bias} form<{a.form_end} "
          f"entry<{a.entry_end} fvg {not a.no_fvg}: {len(tr)} trades  blocks {cnt}")
    if len(tr):
        tr["orb_day"] = tr.orb != "-"
        report(tr, groups=("side", "reason", "orb_day"))
    if a.out:
        tr.to_csv(a.out, index=False)
