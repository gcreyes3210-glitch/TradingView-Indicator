#!/usr/bin/env python3
"""Local bar-by-bar replica of VWAP_Reversion_strategy.pine (v1 defaults).

    python3 tools/vwr_engine.py [--bars data/bars/MNQ_5m.parquet] [--band 1.5] [--tp vwap|inner] [--regime balance|off]
                                [--entry inside|beyond] [--out trades.csv]

Mirrors the Pine script on 5m bars stamped with their open time (New York):
    balance day = opening range 09:30-09:45 inside the 18:00-09:30 overnight range (openLoc == 'inside')
    VWAP anchored at 09:30 from hlc3 x volume, sigma = volume-weighted std of hlc3 around VWAP since 09:30
    a close beyond VWAP +/- band x sigma arms that side (every bar, also before 10:00 and while in a trade);
    entry at the first close back inside (or at the first close beyond, --entry beyond), 10:00-15:00 only
    stop = excursion extreme +/- 0.5 sigma, target = VWAP at entry (or VWAP +/- 1 sigma), fixed after entry
    skip if reward:risk < 1.0 or sigma < 8 ticks; one trade per side per day (a skipped signal uses the side up)
Fill model and costs as tools/orb_engine.py: entry at the signal bar's close; stop / target (rounded to the tick) filled at their price
when a later bar trades through it (stop wins when both are touched on one bar); time exit at the close of the
16:00 bar; 1 tick slippage against every fill (target fills included, stricter than TradingView, which does not
slip limit orders) + $1 commission per side, MNQ $2/point, 1 contract.
"""
import argparse, math
import pandas as pd
from orb_engine import TICK, PT_VALUE, COMM_SIDE, SLIP_TICKS, in_sess

P = dict(
    on_sess=("18:00", "09:30"), or_sess=("09:30", "09:45"), entry_sess=("10:00", "15:00"), trade_sess=("09:30", "16:00"),
    regime="balance", band=2.0, entry="inside", min_sig_ticks=8, stop_sig=0.5, tp="vwap", min_rr=1.0, max_per_side=1,
    start=pd.Timestamp("2020-01-07", tz="America/New_York"),
)


def run(bars, **over):
    p = {**P, **over}
    slip = SLIP_TICKS * TICK
    immediate = p["entry"] == "beyond"
    ts = bars.index
    tod = (ts.hour * 60 + ts.minute).to_numpy()
    H, L, C, V = (bars[k].to_numpy() for k in ("high", "low", "close", "volume"))
    V = V.astype(float)

    trades = []
    prev = dict(inON=False, inOR=False, inTrade=False)
    onH = onL = ONH = ONL = orH = orL = None
    openLoc = "-"
    sPV = sV = sPPV = 0.0
    armUp = armDn = 0
    extHi = extLo = None
    longs = shorts = 0
    pos = None

    def close_pos(i, px, reason):
        nonlocal pos
        sgn = 1 if pos["side"] == "L" else -1
        fill = px - sgn * slip
        pnl = sgn * (fill - pos["entry"]) * PT_VALUE - 2 * COMM_SIDE
        trades.append(dict(side=pos["side"], entry_time=ts[pos["i"]], entry=pos["entry"], exit_time=ts[i], exit=fill,
                           reason=reason, pnl=pnl, risk=pos["risk"], rr=pos["rr"], sig=pos["sig"], ext=pos["ext"]))
        pos = None

    for i in range(len(ts)):
        t = tod[i]
        inON, inOR = in_sess(t, p["on_sess"]), in_sess(t, p["or_sess"])
        inEntry, inTrade = in_sess(t, p["entry_sess"]), in_sess(t, p["trade_sess"])
        onEnd = not inON and prev["inON"]
        orEnd = not inOR and prev["inOR"]
        tradeStart = inTrade and not prev["inTrade"]
        tradeEnd = not inTrade and prev["inTrade"]

        # broker emulator on bars after the entry bar: stop first (wins a shared bar), then the target limit
        if pos is not None and i > pos["i"]:
            if pos["side"] == "L":
                if L[i] <= pos["stop"]:
                    close_pos(i, pos["stop"], "SL")
                elif H[i] >= pos["tp"]:
                    close_pos(i, pos["tp"], "TP")
            else:
                if H[i] >= pos["stop"]:
                    close_pos(i, pos["stop"], "SL")
                elif L[i] <= pos["tp"]:
                    close_pos(i, pos["tp"], "TP")

        # regime
        if inON:
            onH = max(onH, H[i]) if prev["inON"] else H[i]
            onL = min(onL, L[i]) if prev["inON"] else L[i]
        if onEnd:
            ONH, ONL = onH, onL
        if inOR:
            orH = max(orH, H[i]) if prev["inOR"] else H[i]
            orL = min(orL, L[i]) if prev["inOR"] else L[i]
        if orEnd:
            openLoc = ("-" if ONH is None else "above" if orL > ONH else "below" if orH < ONL else
                       "topBreak" if orH > ONH else "botBreak" if orL < ONL else "inside")
        balance = openLoc == "inside"
        dayOk = openLoc != "-" if p["regime"] == "off" else balance

        # VWAP + sigma (anchored at the 09:30 bar)
        if tradeStart:
            sPV = sV = sPPV = 0.0
        hlc3 = (H[i] + L[i] + C[i]) / 3.0
        sPV += hlc3 * V[i]; sV += V[i]; sPPV += hlc3 * hlc3 * V[i]
        vwap = sPV / sV if sV > 0 else None
        sig = math.sqrt(max(sPPV / sV - vwap * vwap, 0.0)) if sV > 0 else None
        up = vwap + p["band"] * sig if sV > 0 else None
        dn = vwap - p["band"] * sig if sV > 0 else None
        sigOk = sig is not None and sig >= p["min_sig_ticks"] * TICK

        if tradeStart:
            armUp = armDn = 0
            extHi = extLo = None
            longs = shorts = 0

        canTrade = dayOk and inEntry and inTrade and ts[i] >= p["start"] and pos is None and sigOk

        # arm / track the excursions
        sigS = sigL = False
        if up is not None and C[i] > up:
            extHi = max(extHi, H[i]) if armUp == 1 else H[i]
            if armUp == 0:
                armUp = 1
                sigS = immediate
        elif armUp == 1:
            sigS = not immediate
            armUp = 0
        if dn is not None and C[i] < dn:
            extLo = min(extLo, L[i]) if armDn == 1 else L[i]
            if armDn == 0:
                armDn = 1
                sigL = immediate
        elif armDn == 1:
            sigL = not immediate
            armDn = 0

        # entries (short first, as in the script)
        for side, fire in (("S", sigS), ("L", sigL)):
            if not (fire and canTrade and pos is None):
                continue
            if side == "S" and shorts >= p["max_per_side"] or side == "L" and longs >= p["max_per_side"]:
                continue
            sgn = 1 if side == "L" else -1
            if side == "S":
                ext, stop = (extHi - up) / sig, extHi + p["stop_sig"] * sig
                shorts += 1
            else:
                ext, stop = (dn - extLo) / sig, extLo - p["stop_sig"] * sig
                longs += 1
            tp = vwap if p["tp"] == "vwap" else vwap - sgn * sig
            risk = sgn * (C[i] - stop)
            rr = sgn * (tp - C[i]) / risk if risk > 0 else 0.0
            if risk > 0 and sgn * (tp - C[i]) > 0 and rr >= p["min_rr"]:
                # the filters use the raw levels (as the script does); the orders rest on the nearest tick
                pos = dict(side=side, entry=C[i] + sgn * slip, stop=round(stop / TICK) * TICK, tp=round(tp / TICK) * TICK, i=i, risk=risk, rr=rr, sig=sig, ext=ext)

        if tradeEnd and pos is not None:
            close_pos(i, C[i], "time")

        prev = dict(inON=inON, inOR=inOR, inTrade=inTrade)

    return pd.DataFrame(trades)


def stats(df):
    pnl = df.pnl
    if len(df) == 0:
        return dict(n=0, net=0, win=0, pf=None, dd=0, avg_win=None, avg_loss=None)
    eq = pnl.cumsum()
    gw, gl = pnl[pnl > 0].sum(), -pnl[pnl < 0].sum()
    return dict(n=len(df), net=round(pnl.sum()), win=round(100 * (pnl > 0).mean(), 1),
                pf=round(gw / gl, 2) if gl else None, dd=round(min((eq - eq.cummax()).min(), 0)),
                avg_win=round(pnl[pnl > 0].mean()) if (pnl > 0).any() else None,
                avg_loss=round(pnl[pnl < 0].mean()) if (pnl < 0).any() else None)


def report(tr):
    def row(name, d):
        s = stats(d)
        print(f"  {name:<10}" + "  ".join(f"{k} {v}" for k, v in s.items()))
    row("all", tr)
    print(" per calendar year:")
    for y, d in tr.groupby(tr.entry_time.dt.year):
        row(str(y), d)
    print(" by side:")
    for k, d in tr.groupby("side"):
        row(k, d)
    print(" by exit:")
    for k, d in tr.groupby("reason"):
        row(k, d)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--bars", default="data/bars/MNQ_5m.parquet")
    ap.add_argument("--band", type=float, default=P["band"])
    ap.add_argument("--tp", choices=["vwap", "inner"], default=P["tp"])
    ap.add_argument("--regime", choices=["balance", "off"], default=P["regime"])
    ap.add_argument("--entry", choices=["inside", "beyond"], default=P["entry"])
    ap.add_argument("--out")
    a = ap.parse_args()
    bars = pd.read_parquet(a.bars)
    tr = run(bars, band=a.band, tp=a.tp, regime=a.regime, entry=a.entry)
    print(f"{bars.index[0].date()} -> {bars.index[-1].date()}  band {a.band}  tp {a.tp}  regime {a.regime}  entry {a.entry}")
    report(tr)
    if a.out:
        tr.to_csv(a.out, index=False)
