#!/usr/bin/env python3
"""ICT AMD (accumulation -> manipulation -> distribution), spec in BACKTEST_LOG.md. Same fill model and costs as
orb_engine.py; bars resampled from the 1-minute Parquet to --tf 1/2/3/5 minutes, stamped by open time.

    python3 tools/amd_engine.py --tf 5 [--acc overnight|asia|london|premarket] [--target range|2r] [--flat 16:00]
                                [--trigger any|mss|ifvg-retest] [--man-end 11:00 --entry-end 11:30]
                                [--orb-trades t.csv] [--out trades.csv]

Rule (New York time, on the TF bars):
    A = high/low of the accumulation window (default overnight 18:00-09:30; asia 20:00-00:00, london 02:00-05:00,
        premarket 08:00-09:30), the most recent one before the 09:30 open.
    M = the first bar from 09:30 (inclusive) and before 10:30 whose high > A high (bearish setup -> short) or low < A low
        (bullish -> long); a bar that takes both sides is ambiguous and the day is skipped. Sweep-leg start = the last
        3-bar fractal low (bearish; high for bullish) whose three bars are all at/after 09:30 and which is confirmed
        before the sweep bar; if none, the session low (high) from 09:30 through the sweep bar. Confirmation = the first
        close back inside (close < A high; > A low) from the sweep bar on, before 10:30; otherwise no trade.
    D, from the confirmation bar on and before 11:00, whichever comes first (tag 'both' when on the same bar):
        MSS  = close below the leg-start low (above the leg-start high)
        IFVG = close below the low of a bullish FVG (above the high of a bearish FVG) formed inside the sweep leg
               (3-bar gap bar[i-2].high < bar[i].low with leg start <= i-2 and i <= confirmation bar, formed before
               the entry bar)
        entry at that close. --trigger mss: MSS only. --trigger ifvg-retest: IFVG only, then a limit at the edge of the
        inverted FVG nearest to price (FVG low for a short, high for a long) filled on one of the next 6 bars (at the
        open if the bar opens through it), else no trade.
    stop = sweep extreme (highest high / lowest low from the sweep bar through the entry bar) +/- 2 ticks
    target = the other side of A (--target 2r: entry -/+ 2 x risk); skip if reward:risk < 1.0 at entry
    --amd2: trigger = the LAST FVG completed in the sweep leg at or before the sweep extreme (highest high / lowest low
    from the sweep bar to the confirmation bar), entered at the first close through it from the confirmation bar on,
    within 10 bars of the confirmation close (else no trade); skip if |entry - stop| > 1.5 x the 20-bar ATR at entry.
    --dir-filter (the run logged as AMD2-1m, direction from the opening range): opening range 09:30-09:45 broke the overnight high -> bullish setups only, the low -> bearish
    only, both -> either, inside -> no trade; the day's setup is taken only if its side is allowed and its entry is at
    or after 09:45 (when the filter is known).
    one trade a day, first setup only (a skipped setup uses the day up); flat at the close of the first bar at or after
    12:00 (--flat 16:00). Stop beats target on the same bar; nothing trades after a close entry inside its own bar.
Costs: 1 tick slippage on every fill (target fills included), $1 commission per side, $2/point, 1 contract.
"""
import argparse
import numpy as np
import pandas as pd
from orb_engine import TICK, PT_VALUE, COMM_SIDE, SLIP_TICKS, report, _path, exit_bar

TZ = "America/New_York"
ACC = dict(overnight=("18:00", "09:30"), asia=("20:00", "00:00"), london=("02:00", "05:00"), premarket=("08:00", "09:30"))
P = dict(tf=5, acc="overnight", man_end="10:30", entry_end="11:00", flat="12:00", target="range", trigger="any",
         dir_filter=False, fresh_bars=10, max_stop_atr=None, shadow=False,
         buf_ticks=2, min_rr=1.0, retest_bars=6, start=pd.Timestamp("2019-06-01", tz=TZ))


def _m(s):
    h, m = s.split(":"); return int(h) * 60 + int(m)


def resample(one, tf):
    if tf == 1:
        return one[["open", "high", "low", "close", "volume"]]
    return one.resample(f"{tf}min", label="left", closed="left").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}).dropna(subset=["open"])


def in_win(tod, a, b):
    a, b = _m(a), _m(b) if b != "00:00" else 1440
    return (tod >= a) & (tod < b) if a < b else (tod >= a) | (tod < b)


def run(one, orb=None, **over):
    p = {**P, **over}
    buf, slip = p["buf_ticks"] * TICK, SLIP_TICKS * TICK
    bars = resample(one, p["tf"])
    ts = bars.index
    tod = np.asarray(ts.hour * 60 + ts.minute)
    O, H, L, C = (bars[k].to_numpy() for k in ("open", "high", "low", "close"))
    dates = np.array(ts.date)
    pc = np.r_[np.nan, C[:-1]]
    atr = pd.Series(np.nanmax(np.c_[H - L, np.abs(H - pc), np.abs(L - pc)], axis=1)).rolling(20).mean().to_numpy()
    rth = np.flatnonzero((tod >= 570) & (tod < 960))
    opens = pd.Series(rth, index=dates[rth]).groupby(level=0).min()
    accmask = in_win(tod, *ACC[p["acc"]])
    man_end, entry_end, flat = _m(p["man_end"]), _m(p["entry_end"]), _m(p["flat"])
    orb = orb or {}

    trades, skipped = [], dict(ambiguous=0, rr=0, no_retest=0)
    prev_open = None
    for d, i0 in opens.items():
        span0, prev_open = (prev_open + 1 if prev_open is not None else 0), i0
        if ts[i0] < p["start"] or span0 == 0:
            continue
        acc_idx = np.arange(span0, i0)[accmask[span0:i0]]
        if len(acc_idx) == 0:
            continue
        AH, AL = H[acc_idx].max(), L[acc_idx].min()
        # last index of the day for the flat exit: first bar at/after `flat` (or the next bar after the session)
        iend = i0
        while iend + 1 < len(ts) and dates[iend + 1] == d and tod[iend + 1] < flat:
            iend += 1
        iend = exit_bar(ts, iend)                       # early close: the session's last bar

        # manipulation: first sweep bar
        s = side = None
        k = i0
        while k < iend and dates[k] == d and tod[k] < man_end:
            up, dn = H[k] > AH, L[k] < AL
            if up and dn:
                skipped["ambiguous"] += 1
                break
            if up or dn:
                s, side = k, ("S" if up else "L")
                break
            k += 1
        if s is None:
            continue
        sgn = 1 if side == "L" else -1
        # sweep-leg start
        leg = None
        for j in range(s - 2, i0, -1):              # fractal at j needs j-1 >= i0 and j+1 <= s-1
            if side == "S" and L[j] < L[j - 1] and L[j] < L[j + 1]:
                leg = j; break
            if side == "L" and H[j] > H[j - 1] and H[j] > H[j + 1]:
                leg = j; break
        if leg is None:
            seg = np.arange(i0, s + 1)
            leg = seg[np.argmin(L[seg])] if side == "S" else seg[np.argmax(H[seg])]
        legPx = L[leg] if side == "S" else H[leg]
        # confirmation: first close back inside
        c = next((k for k in range(s, iend) if tod[k] < man_end and dates[k] == d and
                  (C[k] < AH if side == "S" else C[k] > AL)), None)
        if c is None or tod[c] >= man_end:
            continue
        # FVGs inside the leg that point the setup's way (bullish FVG for a short setup)
        fvgs = []
        for i in range(leg + 2, c + 1):
            if side == "S" and H[i - 2] < L[i]:
                fvgs.append((i, H[i - 2]))           # (formed at, edge to close through = FVG low)
            if side == "L" and L[i - 2] > H[i]:
                fvgs.append((i, L[i - 2]))           # FVG high
        # distribution trigger
        trig = None
        if p["trigger"] == "last-fvg":
            # AMD2: the last FVG completed in the leg at or before the sweep extreme, inverted by the first close through
            # it from the confirmation bar on, within fresh_bars of the confirmation close
            seg = np.arange(s, c + 1)
            xb = seg[np.argmax(H[seg])] if side == "S" else seg[np.argmin(L[seg])]
            last = [(i, e) for i, e in fvgs if i <= xb]
            if last:
                i_f, edge = last[-1]
                for k in range(max(c, i_f + 1), min(c + p["fresh_bars"] + 1, iend)):
                    if tod[k] >= entry_end or dates[k] != d:
                        break
                    if sgn * (C[k] - edge) > 0:
                        trig = (k, "IFVG-last", [edge])
                        break
            if trig is None:
                skipped["no_fresh_ifvg"] = skipped.get("no_fresh_ifvg", 0) + 1
                continue
        for k in range(c, iend) if trig is None else ():
            if tod[k] >= entry_end or dates[k] != d:
                break
            mss = sgn * (C[k] - legPx) > 0
            inv = [e for i, e in fvgs if i < k and sgn * (C[k] - e) > 0]
            if p["trigger"] == "mss":
                inv = []
            if p["trigger"] == "ifvg-retest":
                mss = False
            if mss or inv:
                trig = (k, "both" if mss and inv else "MSS" if mss else "IFVG", inv)
                break
        if trig is None:
            continue
        k, kind, inv = trig
        ext = H[s:k + 1].max() if side == "S" else L[s:k + 1].min()
        stop = ext + buf if side == "S" else ext - buf
        fill_i, fill_px, rest = k, C[k], None
        if p["trigger"] == "ifvg-retest":
            edge = min(inv) if side == "S" else max(inv)   # nearest inverted FVG edge
            fill_i = None
            for i in range(k + 1, min(k + 1 + p["retest_bars"], iend)):
                if -sgn * (O[i] - edge) >= 0:           # opens at/through the sell (buy) limit
                    fill_i, fill_px, rest = i, O[i], _path(O[i], H[i], L[i], C[i]); break
                if (H[i] >= edge) if side == "S" else (L[i] <= edge):
                    pts = _path(O[i], H[i], L[i], C[i])
                    q = next(q for q in range(1, 4) if -sgn * (pts[q] - edge) >= 0)
                    fill_i, fill_px, rest = i, edge, [edge] + pts[q:]; break
            if fill_i is None:
                skipped["no_retest"] += 1
                continue
        orb_i = np.arange(i0, i0 + 16)[tod[i0:i0 + 16] < 585]
        orH, orL = H[orb_i].max(), L[orb_i].min()
        on_idx = np.arange(span0, i0)[in_win(tod[span0:i0], "18:00", "09:30")]
        onH, onL = H[on_idx].max(), L[on_idx].min()
        if p["dir_filter"]:
            # AMD2: known at 09:45 - opening range broke the overnight high -> bullish setups only, low -> bearish only,
            # both -> either, inside -> none; the entry must come at/after 09:45 (the filter is not known before)
            allowed = {(True, False): "L", (False, True): "S", (True, True): "LS", (False, False): ""}[(orH > onH, orL < onL)]
            if side not in allowed or tod[fill_i] < 585:
                skipped["dir_filter"] = skipped.get("dir_filter", 0) + 1
                continue
        if p["max_stop_atr"] is not None and abs(fill_px - stop) > p["max_stop_atr"] * atr[fill_i]:
            skipped["stop_atr"] = skipped.get("stop_atr", 0) + 1         # AMD2: stop too far for the day's volatility
            continue
        risk = sgn * (fill_px - stop)
        tp = fill_px + sgn * 2 * risk if p["target"] == "2r" else (AL if side == "S" else AH)
        rr = sgn * (tp - fill_px) / risk if risk > 0 else 0
        status = "taken"
        if risk <= 0 or rr < p["min_rr"]:
            skipped["rr"] += 1
            if not (p["shadow"] and risk > 0):
                continue
            status = "skipped_rr"      # shadow: keep the skipped setup and simulate what it would have done
        tp = round(tp / TICK) * TICK
        entry = fill_px + sgn * slip
        out = None
        if rest is not None:                      # retest fill: rest of the fill bar
            if (max(rest) >= stop) if side == "S" else (min(rest) <= stop):
                out = (fill_i, stop, "SL")
            elif (min(rest) <= tp) if side == "S" else (max(rest) >= tp):
                out = (fill_i, tp, "TP")
        i = fill_i + 1
        while out is None:
            if (H[i] >= stop) if side == "S" else (L[i] <= stop):
                out = (i, stop, "SL")
            elif (L[i] <= tp) if side == "S" else (H[i] >= tp):
                out = (i, tp, "TP")
            elif i >= iend:
                out = (i, C[i], "time")
            i += 1
        xi, xpx, reason = out
        fill = xpx - sgn * slip
        pnl = sgn * (fill - entry) * PT_VALUE - 2 * COMM_SIDE
        trades.append(dict(side=side, entry_time=ts[fill_i], entry=entry, exit_time=ts[xi], exit=fill, reason=reason,
                           pnl=pnl, risk=risk, R=pnl / (risk * PT_VALUE), rr=rr, trigger=kind, tf=p["tf"],
                           acc_w=AH - AL, depth=(ext - AH if side == "S" else AL - ext) / (AH - AL),
                           bars=fill_i - s, day="balance" if orH <= onH and orL >= onL else "break",
                           acc_hi=AH, acc_lo=AL, sweep_t=ts[s], leg_t=ts[leg], leg_px=legPx, conf_t=ts[c], trig_t=ts[k],
                           ext=ext, stop=stop, tp=tp, status=status,        # geometry (for charts)
                           orb=orb.get(d, "-"), or_break=("both" if orH > onH and orL < onL else "high" if orH > onH
                                                          else "low" if orL < onL else "inside")))
    return pd.DataFrame(trades), skipped


def amd2(one, orb=None, bars30=None, target="internal", chop=2.5, max_stop_atr=1.5, fresh=5, start=None, days=None):
    """AMD2 (amended, the trader's definitions), 1m, optionally with the gap detection on 30-second bars.

    Sweep of the overnight extreme, sweep-leg start and close back inside exactly as AMD1 (1m). The trigger gap is the
    last FVG formed in the leg into the liquidity at or before the sweep extreme (bearish setup: a bullish gap); it is
    tracked bar by bar while the extreme extends. The first close through the trigger gap is the only chance: it is the
    entry if it comes within `fresh` bars of the bar that completed the gap and the close back inside has happened; if
    it comes later or before the close back inside, or the trigger gap goes `fresh` bars without being inverted, the day
    has no trade. Stop = sweep extreme + 2 ticks. Target (internal): the most recent 3-bar fractal high (bearish setup;
    fractal low for bullish) formed since 09:30 and confirmed before the sweep bar; 'overnight' (AMD2b): the far side
    of the overnight range. Skip if reward:risk < 1.0, if |entry - stop| > max_stop_atr x ATR(20), or (chop) if the
    20 1m bars before the sweep bar span < chop x ATR(20) of those bars (ATRs use completed 1m bars only). Flat at the close of the first bar at/after 12:00.
    bars30: 30-second bars (NQ, from the trades) for the gap tracking, the extreme, the inversion and the exits up to
    their last bar (11:35); the rest stays on the MNQ 1m bars. `days` limits the run to those dates.
    """
    buf, slip = 2 * TICK, SLIP_TICKS * TICK
    ts = one.index
    tod = np.asarray(ts.hour * 60 + ts.minute)
    O, H, L, C = (one[k].to_numpy() for k in ("open", "high", "low", "close"))
    dates = np.array(ts.date)
    pc = np.r_[np.nan, C[:-1]]
    atr = pd.Series(np.nanmax(np.c_[H - L, np.abs(H - pc), np.abs(L - pc)], axis=1)).rolling(20).mean().to_numpy()
    rth = np.flatnonzero((tod >= 570) & (tod < 960))
    opens = pd.Series(rth, index=dates[rth]).groupby(level=0).min()
    onmask = in_win(tod, "18:00", "09:30")
    if bars30 is not None:
        t30 = bars30.index
        O3, H3, L3, C3 = (bars30[k].to_numpy() for k in ("open", "high", "low", "close"))
        d30 = np.array(t30.date)
    orb = orb or {}
    cnt = dict(days=0, sweeps=0, confirmed=0, no_gap=0, stale=0, early_inversion=0, no_target=0, rr=0, stop_atr=0,
               chop=0, traded=0)
    trades = []
    prev_open = None
    for d, i0 in opens.items():
        span0, prev_open = (prev_open + 1 if prev_open is not None else 0), i0
        if span0 == 0 or (start is not None and ts[i0] < start) or (days is not None and d not in days):
            continue
        acc_idx = np.arange(span0, i0)[onmask[span0:i0]]
        if len(acc_idx) == 0:
            continue
        cnt["days"] += 1
        AH, AL = H[acc_idx].max(), L[acc_idx].min()
        iend = i0
        while iend + 1 < len(ts) and dates[iend + 1] == d and tod[iend + 1] < 720:
            iend += 1
        iend = exit_bar(ts, iend)
        # ---- sweep, leg start, close back inside: as AMD1
        s = side = None
        k = i0
        while k < iend and dates[k] == d and tod[k] < 630:
            up, dn = H[k] > AH, L[k] < AL
            if up and dn:
                break
            if up or dn:
                s, side = k, ("S" if up else "L")
                break
            k += 1
        if s is None:
            continue
        cnt["sweeps"] += 1
        sgn = 1 if side == "L" else -1
        leg = None
        for j in range(s - 2, i0, -1):
            if side == "S" and L[j] < L[j - 1] and L[j] < L[j + 1]:
                leg = j; break
            if side == "L" and H[j] > H[j - 1] and H[j] > H[j + 1]:
                leg = j; break
        if leg is None:
            seg = np.arange(i0, s + 1)
            leg = seg[np.argmin(L[seg])] if side == "S" else seg[np.argmax(H[seg])]
        c = next((k for k in range(s, iend) if tod[k] < 630 and dates[k] == d and
                  (C[k] < AH if side == "S" else C[k] > AL)), None)
        if c is None or tod[c] >= 630:
            continue
        cnt["confirmed"] += 1
        conf_close = ts[c] + pd.Timedelta(minutes=1)
        # ---- trigger: on the gap-detection bars (1m, or 30s)
        if bars30 is None:
            G = dict(t=ts, H=H, L=L, C=C, O=O, lo=leg, hi=iend, step=pd.Timedelta(minutes=1))
        else:
            m30 = np.flatnonzero((d30 == d) & (t30 >= ts[leg]) & (t30 < ts[iend]))
            if len(m30) == 0:
                continue
            G = dict(t=t30, H=H3, L=L3, C=C3, O=O3, lo=m30[0], hi=m30[-1] + 1, step=pd.Timedelta(seconds=30))
        gt, gH, gL, gC = G["t"], G["H"], G["L"], G["C"]
        g_s = next(q for q in range(G["lo"], G["hi"]) if gt[q] >= ts[s])        # first gap-bar of the sweep minute
        gaps, trig, ext_i, fate = [], None, None, "no_gap"
        for q in range(G["lo"], G["hi"]):
            tq = gt[q]
            if tq.hour * 60 + tq.minute >= 660:                                # entries before 11:00
                break
            if q >= g_s:
                if ext_i is None or (gH[q] > gH[ext_i] if side == "S" else gL[q] < gL[ext_i]):
                    ext_i = q
            if q - 2 >= G["lo"] and ((gH[q - 2] < gL[q]) if side == "S" else (gL[q - 2] > gH[q])):
                gaps.append((q, gH[q - 2] if side == "S" else gL[q - 2]))    # (completed at, edge to close through)
            if ext_i is None:
                continue
            cand = [g for g in gaps if g[0] <= ext_i]
            if not cand:
                continue
            gi, edge = cand[-1]
            fate = "stale"
            if sgn * (gC[q] - edge) > 0:                                        # first close through the trigger gap
                if q - gi <= fresh and tq + G["step"] >= conf_close:
                    trig = (q, gi, edge)
                else:
                    fate = "stale" if q - gi > fresh else "early_inversion"
                break
            if q - gi > fresh:
                break
        if trig is None:
            cnt[fate] += 1
            continue
        q, gi, edge = trig
        ext = gH[g_s:q + 1].max() if side == "S" else gL[g_s:q + 1].min()
        stop = ext + buf if side == "S" else ext - buf
        fill_px = gC[q]
        entry_t = gt[q]
        m_entry = np.searchsorted(ts, entry_t, side="right") - 1                 # the 1m bar containing the entry
        # target
        if target == "internal":
            tp = None
            for m in range(s - 2, i0, -1):                                      # fractal confirmed before the sweep bar
                if side == "S" and H[m] > H[m - 1] and H[m] > H[m + 1]:
                    tp = H[m]; break
                if side == "L" and L[m] < L[m - 1] and L[m] < L[m + 1]:
                    tp = L[m]; break
            if tp is None:
                cnt["no_target"] += 1
                continue
        else:
            tp = AL if side == "S" else AH
        risk = sgn * (fill_px - stop)
        rr = sgn * (tp - fill_px) / risk if risk > 0 else 0
        if risk <= 0 or rr < 1.0:
            cnt["rr"] += 1
            continue
        a_i = m_entry if entry_t + G["step"] >= ts[m_entry] + pd.Timedelta(minutes=1) else m_entry - 1   # completed bars only
        if abs(fill_px - stop) > max_stop_atr * atr[a_i]:
            cnt["stop_atr"] += 1
            continue
        pre = np.arange(max(s - 20, 0), s)
        if chop and (H[pre].max() - L[pre].min()) < chop * atr[s - 1]:       # ATR of those same 20 bars
            cnt["chop"] += 1
            continue
        cnt["traded"] += 1
        tp = round(tp / TICK) * TICK
        entry = fill_px + sgn * slip
        out = None
        # exits: on the gap-detection bars after the entry bar, then on 1m bars from where they end
        qq = q + 1
        while out is None and qq < G["hi"] and gt[qq] < ts[iend]:
            if (gH[qq] >= stop) if side == "S" else (gL[qq] <= stop):
                out = (gt[qq], stop, "SL")
            elif (gL[qq] <= tp) if side == "S" else (gH[qq] >= tp):
                out = (gt[qq], tp, "TP")
            qq += 1
        i = np.searchsorted(ts, (gt[qq - 1] + G["step"]) if qq > q + 1 else (entry_t + G["step"]))
        i = max(i, m_entry + 1)
        while out is None:
            if (H[i] >= stop) if side == "S" else (L[i] <= stop):
                out = (ts[i], stop, "SL")
            elif (L[i] <= tp) if side == "S" else (H[i] >= tp):
                out = (ts[i], tp, "TP")
            elif i >= iend:
                out = (ts[i], C[i], "time")
            i += 1
        xt, xpx, reason = out
        fill = xpx - sgn * slip
        pnl = sgn * (fill - entry) * PT_VALUE - 2 * COMM_SIDE
        trades.append(dict(side=side, entry_time=entry_t, entry=entry, exit_time=xt, exit=fill, reason=reason, pnl=pnl,
                           risk=risk, R=pnl / (risk * PT_VALUE), rr=rr, gap_t=gt[gi], gap_edge=edge, gap_age=q - gi,
                           acc_hi=AH, acc_lo=AL, sweep_t=ts[s], leg_t=ts[leg], leg_px=L[leg] if side == "S" else H[leg],
                           conf_t=ts[c], ext=ext, stop=stop, tp=tp, orb=orb.get(d, "-")))
    return pd.DataFrame(trades), cnt


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--bars1m", default="data/bars/MNQ_1m.parquet")
    ap.add_argument("--tf", type=int, choices=[1, 2, 3, 5], default=P["tf"])
    ap.add_argument("--start", default="2019-06-01")
    ap.add_argument("--acc", choices=list(ACC), default=P["acc"])
    ap.add_argument("--target", choices=["range", "2r"], default=P["target"])
    ap.add_argument("--flat", default=P["flat"])
    ap.add_argument("--trigger", choices=["any", "mss", "ifvg-retest"], default=P["trigger"])
    ap.add_argument("--man-end", default=P["man_end"])
    ap.add_argument("--entry-end", default=P["entry_end"])
    ap.add_argument("--dir-filter", action="store_true", help="direction from the opening range vs overnight range")
    ap.add_argument("--amd2", action="store_true", help="AMD2: last FVG before the sweep extreme, inverted within 10 bars "
                                                       "of the confirmation close; skip if the stop > 1.5 x ATR(20)")
    ap.add_argument("--orb-trades")
    ap.add_argument("--out")
    a = ap.parse_args()
    orb = {}
    if a.orb_trades:
        o = pd.read_csv(a.orb_trades)
        orb = dict(zip(pd.to_datetime(o.entry_time, utc=True).dt.tz_convert(TZ).dt.date, o.side))
    kw = dict(tf=a.tf, start=pd.Timestamp(a.start, tz=TZ), acc=a.acc, target=a.target, flat=a.flat, trigger=a.trigger,
              man_end=a.man_end, entry_end=a.entry_end, dir_filter=a.dir_filter)
    if a.amd2:
        kw.update(trigger="last-fvg", max_stop_atr=1.5)
    tr, sk = run(pd.read_parquet(a.bars1m), orb, **kw)
    print(f"tf {a.tf}m acc {a.acc} target {a.target} flat {a.flat} trigger {kw['trigger']} man<{a.man_end} "
          f"entry<{a.entry_end}: {len(tr)} trades, skipped {sk}")
    if len(tr):
        tr["orb_day"] = tr.orb != "-"
        report(tr, groups=("trigger", "side", "reason", "orb_day"))
    if a.out:
        tr.to_csv(a.out, index=False)
