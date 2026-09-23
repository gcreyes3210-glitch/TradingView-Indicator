#!/usr/bin/env python3
"""IVC: initiative continuation from prior value (spec in BACKTEST_LOG.md). Local engine, same bars, fill model and
costs as orb_engine.py.

    python3 tools/ivc_engine.py [--start 2019-06-01] [--accept va|poc|off] [--ref va|pd|on] [--ib 09:30-10:00]
                                [--entry-window 10:00-12:00] [--entry close|retest] [--orb-trades t.csv] [--out trades.csv]

Rule (v1, New York time):
    reference = previous cash session (09:30-16:00) volume profile from the 1-minute bars: 1-point rows, each 1m bar's
      volume spread evenly over the rows its range touched, POC = row with the most volume (lowest on ties), value
      area = 70 % of the volume, grown from the POC two rows at a time on the heavier side (VP_80Rule_strategy.pine);
      VAH = top of the highest VA row, VAL = bottom of the lowest, POC = middle of its row.
    open location at 09:30: above (open > VAH) / below (open < VAL) / inside (no trade)
    initial balance (IB) = 09:30-10:30; acceptance: above-VA day needs IB low > VAH, below-VA day IB high < VAL
    10:30-12:00: above-VA day -> long on the first 5m close > IB high + 2 ticks + 0.15 x IB width (short mirror);
      direction away from value only, one trade a day, skip if IB width < 4 ticks
    stop = other side of the IB -/+ 2 ticks, no target, flat at the close of the 16:00 bar
Variants: --accept poc (IB low > POC / IB high < POC) · --ref pd (open and IB beyond PDH / PDL) · --ib 09:30-10:00
    --entry-window 10:00-12:00 · --accept off (open outside value is enough) · --entry retest (after the qualifying close,
    a limit at the IB high / low filled on one of the next 6 bars, else no trade) · --ref on (overnight 18:00-09:30
    profile instead of the previous cash session).
Fills: entry at the signal close (retest: at the limit, or at the bar's open if it opens through it); stop filled at
the stop price when a later bar trades through it (retest: also later in the fill bar, TradingView's bar path);
time exit at the close of the first bar at or after 16:00. Costs: 1 tick slippage on every fill, $1 commission per
side, $2/point, 1 contract.
"""
import argparse
import numpy as np
import pandas as pd
from orb_engine import TICK, PT_VALUE, COMM_SIDE, SLIP_TICKS, report, _path

ROW, VA_PCT = 1.0, 0.70
TZ = "America/New_York"
P = dict(accept="va", ref="va", ib=("09:30", "10:30"), entry_sess=("10:30", "12:00"), entry="close",
         buf_ticks=2, min_brk=0.15, min_ib_ticks=4, retest_bars=6, start=pd.Timestamp("2019-06-01", tz=TZ))


def profile(h, l, v):
    """POC, VAH, VAL of 1m bars (arrays) on 1-point rows, as VP_80Rule_strategy.pine builds them."""
    lo0 = np.floor(l.min() / ROW) * ROW
    iLo = np.floor((l - lo0) / ROW + 1e-9).astype(int)
    iHi = np.floor((h - lo0) / ROW + 1e-9).astype(int)
    n = iHi.max() + 1
    share = v / (iHi - iLo + 1)
    d = np.zeros(n + 1)
    np.add.at(d, iLo, share)
    np.add.at(d, iHi + 1, -share)
    rows = np.cumsum(d)[:n]
    ip = int(np.argmax(rows))                       # first max = lowest row on ties
    target, acc, up, dn = rows.sum() * VA_PCT, rows[ip], ip, ip
    while acc < target and (up < n - 1 or dn > 0):
        aUp = rows[up + 1] + (rows[up + 2] if up + 2 <= n - 1 else 0.0) if up + 1 <= n - 1 else -1.0
        aDn = rows[dn - 1] + (rows[dn - 2] if dn - 2 >= 0 else 0.0) if dn - 1 >= 0 else -1.0
        if aUp >= aDn and up < n - 1:
            k = min(2, n - 1 - up); acc += rows[up + 1:up + 1 + k].sum(); up += k
        elif dn > 0:
            k = min(2, dn); acc += rows[dn - k:dn].sum(); dn -= k
        else:
            break
    return lo0 + (ip + 0.5) * ROW, lo0 + (up + 1) * ROW, lo0 + dn * ROW


def day_context(one):
    """Per RTH date: previous cash session profile + H/L/C, overnight (18:00-09:30) profile and range."""
    tod = one.index.hour * 60 + one.index.minute
    rth = one[(tod >= 570) & (tod < 960)]
    dates = np.array(sorted(set(rth.index.date)))
    ctx = {}
    for d, g in rth.groupby(rth.index.date):
        poc, vah, val = profile(g.high.to_numpy(), g.low.to_numpy(), g.volume.to_numpy().astype(float))
        ctx[d] = dict(poc=poc, vah=vah, val=val, H=g.high.max(), L=g.low.min(), C=g.close.iloc[-1])
    # overnight bars belong to the next RTH date (>= 18:00: strictly after their calendar date; < 09:30: same or after)
    on = one[(tod >= 1080) | (tod < 570)]
    cal = np.array(on.index.date)
    after = (on.index.hour * 60 + on.index.minute >= 1080)
    idx = np.where(after, np.searchsorted(dates, cal, side="right"), np.searchsorted(dates, cal, side="left"))
    ok = idx < len(dates)
    on = on[ok]; idx = idx[ok]
    onctx = {}
    for k, g in on.groupby(idx):
        poc, vah, val = profile(g.high.to_numpy(), g.low.to_numpy(), g.volume.to_numpy().astype(float))
        onctx[dates[k]] = dict(poc=poc, vah=vah, val=val, H=g.high.max(), L=g.low.min())
    prev = {dates[k]: ctx[dates[k - 1]] for k in range(1, len(dates))}
    return dates, prev, onctx


def _mins(s):
    h, m = s.split(":"); return int(h) * 60 + int(m)


def run(b5, one, orb_days=frozenset(), **over):
    p = {**P, **over}
    buf, slip = p["buf_ticks"] * TICK, SLIP_TICKS * TICK
    dates, prev, onctx = day_context(one)
    ts = b5.index
    tod = ts.hour * 60 + ts.minute
    O, H, L, C = (b5[k].to_numpy() for k in ("open", "high", "low", "close"))
    day_of = np.array(ts.date)
    ib0, ib1 = _mins(p["ib"][0]), _mins(p["ib"][1])
    e0, e1 = _mins(p["entry_sess"][0]), _mins(p["entry_sess"][1])
    first = pd.Series(np.arange(len(ts)), index=ts)[(tod >= 570) & (tod < 960)]
    starts = first.groupby(first.index.date).min()

    trades = []
    for d, i0 in starts.items():
        if ts[i0] < p["start"] or d not in prev or d not in onctx:
            continue
        pd_ = prev[d]
        ref = onctx[d] if p["ref"] == "on" else pd_
        hi_ref, lo_ref = (pd_["H"], pd_["L"]) if p["ref"] == "pd" else (ref["vah"], ref["val"])
        op = O[i0]
        loc = "above" if op > hi_ref else "below" if op < lo_ref else "inside"
        # day's bars through the first bar at/after 16:00
        j = i0
        while j + 1 < len(ts) and (day_of[j + 1] == d and tod[j + 1] < 960):
            j += 1
        iend = j + 1 if j + 1 < len(ts) else j
        ib = [i for i in range(i0, iend) if ib0 <= tod[i] < ib1]
        if not ib:
            continue
        ibH, ibL = H[ib].max(), L[ib].min()
        ibW = ibH - ibL
        on = onctx[d]
        orb = [i for i in range(i0, iend) if 570 <= tod[i] < 585]
        orH, orL = H[orb].max(), L[orb].min()
        daytype = "balance" if orH <= on["H"] and orL >= on["L"] else "break"
        tag = dict(open_loc=loc, ib_w=ibW, ib_pd=100 * ibW / (pd_["H"] - pd_["L"]), gap=op - pd_["C"], day=daytype,
                   orb_day=d in orb_days, ib_vs_ref=("IBL>VAH" if ibL > ref["vah"] else "IBL>POC" if ibL > ref["poc"]
                                                   else "IBH<VAL" if ibH < ref["val"] else "IBH<POC" if ibH < ref["poc"]
                                                   else "overlaps POC"))
        if loc == "inside" or ibW < p["min_ib_ticks"] * TICK:
            continue
        if p["accept"] == "va":
            acc = ibL > hi_ref if loc == "above" else ibH < lo_ref
        elif p["accept"] == "poc":
            acc = ibL > ref["poc"] if loc == "above" else ibH < ref["poc"]
        else:
            acc = True
        if not acc:
            continue
        side, sgn = ("L", 1) if loc == "above" else ("S", -1)
        trig = ibH + buf + p["min_brk"] * ibW if side == "L" else ibL - buf - p["min_brk"] * ibW
        stop = ibL - buf if side == "L" else ibH + buf
        sig = next((i for i in range(i0, iend) if e0 <= tod[i] < e1 and sgn * (C[i] - trig) > 0), None)
        if sig is None:
            continue
        pos = None
        if p["entry"] == "close":
            pos = dict(i=sig, px=C[sig])
        else:
            lim = ibH if side == "L" else ibL
            for i in range(sig + 1, min(sig + 1 + p["retest_bars"], iend)):
                if sgn * (O[i] - lim) <= 0:
                    pos = dict(i=i, px=O[i], rest=_path(O[i], H[i], L[i], C[i]))
                elif (L[i] <= lim) if side == "L" else (H[i] >= lim):
                    pts = _path(O[i], H[i], L[i], C[i])
                    k = next(k for k in range(1, 4) if sgn * (pts[k] - lim) <= 0)
                    pos = dict(i=i, px=lim, rest=[lim] + pts[k:])
                if pos:
                    break
        if pos is None:
            continue
        entry, ie = pos["px"] + sgn * slip, pos["i"]
        exit_px, exit_i, reason = None, None, None
        if "rest" in pos and ((min(pos["rest"]) <= stop) if side == "L" else (max(pos["rest"]) >= stop)):
            exit_px, exit_i, reason = stop, ie, "SL"
        for i in range(ie + 1, iend + 1):
            if exit_px is not None:
                break
            if (L[i] <= stop) if side == "L" else (H[i] >= stop):
                exit_px, exit_i, reason = stop, i, "SL"
            elif i == iend:
                exit_px, exit_i, reason = C[i], i, "time"
        fill = exit_px - sgn * slip
        pnl = sgn * (fill - entry) * PT_VALUE - 2 * COMM_SIDE
        risk = sgn * (pos["px"] - stop)
        trades.append(dict(side=side, entry_time=ts[ie], entry=entry, exit_time=ts[exit_i], exit=fill, reason=reason,
                           pnl=pnl, risk=risk, R=pnl / (risk * PT_VALUE), **tag))
    return pd.DataFrame(trades)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--bars", default="data/bars/MNQ_5m.parquet")
    ap.add_argument("--bars1m", default="data/bars/MNQ_1m.parquet")
    ap.add_argument("--start", default="2019-06-01")
    ap.add_argument("--accept", choices=["va", "poc", "off"], default=P["accept"])
    ap.add_argument("--ref", choices=["va", "pd", "on"], default=P["ref"])
    ap.add_argument("--ib", default="-".join(P["ib"]))
    ap.add_argument("--entry-window", default="-".join(P["entry_sess"]))
    ap.add_argument("--entry", choices=["close", "retest"], default=P["entry"])
    ap.add_argument("--orb-trades", help="ORB trade list (orb_engine.py --out) to tag the days ORB traded")
    ap.add_argument("--out")
    a = ap.parse_args()
    orb_days = frozenset()
    if a.orb_trades:
        orb_days = frozenset(pd.to_datetime(pd.read_csv(a.orb_trades).entry_time, utc=True).dt.tz_convert(TZ).dt.date)
    tr = run(pd.read_parquet(a.bars), pd.read_parquet(a.bars1m), orb_days, start=pd.Timestamp(a.start, tz=TZ),
             accept=a.accept, ref=a.ref, ib=tuple(a.ib.split("-")), entry_sess=tuple(a.entry_window.split("-")),
             entry=a.entry)
    print(f"accept {a.accept}  ref {a.ref}  ib {a.ib}  entries {a.entry_window}  entry {a.entry}  -> {len(tr)} trades")
    if len(tr):
        report(tr, groups=("side", "reason", "open_loc", "orb_day"))
    if a.out:
        tr.to_csv(a.out, index=False)
