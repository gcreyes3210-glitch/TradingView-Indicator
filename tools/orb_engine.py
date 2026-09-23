#!/usr/bin/env python3
"""Local bar-by-bar replica of ORB_strategy.pine (v1.3 defaults), close-beyond entry mode.

    python3 tools/orb_engine.py [--bars data/bars/MNQ_5m.parquet] [--out trades.csv]

Mirrors the Pine script's per-bar state machine on 5m bars stamped with their open time (New York):
    opening range 09:30-09:45 · entries 09:45-11:30 · trade window 09:30-16:00 · overnight 18:00-09:30
    long when close > ORH + 2 ticks + 0.15 x range, short when close < ORL - 2 ticks - 0.15 x range,
    only on days whose opening range breaks the overnight range, max 1 trade a day, stop = other side ± 2 ticks,
    no target, flat on the first bar after 16:00.
Fill model (the calibration rules):
    entry at the signal bar's close; stop filled at the stop price when a later bar trades through it;
    nothing trades after a close entry within its own bar, so the entry bar's low/high never stops it
    (TradingView agrees: 2026-04-13, entry bar touched the stop before closing out); time exit at the close
    of the bar that opens at 16:00; stop beats the time exit on the same bar.
    Costs: 1 tick slippage against every fill + $1 commission per side, MNQ $2/point, 1 contract.
"""
import argparse, datetime as dt
import pandas as pd

TICK, PT_VALUE, COMM_SIDE, SLIP_TICKS = 0.25, 2.0, 1.0, 1

P = dict(
    or_sess=("09:30", "09:45"), entry_sess=("09:45", "11:30"), trade_sess=("09:30", "16:00"),
    on_sess=("18:00", "09:30"), rth_sess=("09:30", "16:00"),
    buf_ticks=2, max_trades=1, min_or_ticks=4, min_brk_or=0.15, on_filter="break",
    start=pd.Timestamp("2020-01-01", tz="America/New_York"),
)


def _mins(s):
    h, m = s.split(":"); return int(h) * 60 + int(m)


def in_sess(tod, sess):
    a, b = _mins(sess[0]), _mins(sess[1])
    return (a <= tod < b) if a < b else (tod >= a or tod < b)


def run(bars, p=P, entry_bar_stop=False):
    buf = p["buf_ticks"] * TICK
    slip = SLIP_TICKS * TICK
    ts = bars.index
    tod = (ts.hour * 60 + ts.minute).to_numpy()
    O, H, L, C = (bars[k].to_numpy() for k in ("open", "high", "low", "close"))

    trades = []
    prev = dict(inOR=False, inEntry=False, inTrade=False, inON=False, inRth=False)
    onH = onL = ONH = ONL = None
    rthH = rthL = rthC = pdH = pdL = pdC = None
    orH = orL = ORH = ORL = orW = None
    orReady, openLoc, gap, pdPct = False, "-", None, None
    tradesToday = longsToday = shortsToday = 0
    pos = None  # dict(side, entry, stop, i, tag)

    def close_pos(i, px, reason):
        nonlocal pos
        sgn = 1 if pos["side"] == "L" else -1
        fill = px - sgn * slip
        pnl = sgn * (fill - pos["entry"]) * PT_VALUE - 2 * COMM_SIDE
        trades.append(dict(side=pos["side"], entry_time=ts[pos["i"]], entry=pos["entry"], exit_time=ts[i],
                           exit=fill, reason=reason, pnl=pnl, risk=pos["risk"], **pos["tag"]))
        pos = None

    for i in range(len(ts)):
        t = tod[i]
        inOR, inEntry, inTrade = in_sess(t, p["or_sess"]), in_sess(t, p["entry_sess"]), in_sess(t, p["trade_sess"])
        inON, inRth = in_sess(t, p["on_sess"]), in_sess(t, p["rth_sess"])
        orEnd = not inOR and prev["inOR"]
        tradeStart = inTrade and not prev["inTrade"]
        tradeEnd = not inTrade and prev["inTrade"]
        onEnd = not inON and prev["inON"]
        rthEnd = not inRth and prev["inRth"]

        # broker emulator: resting stop on bars after the entry bar (runs before the script, stop beats time exit)
        if pos is not None and i > pos["i"]:
            if pos["side"] == "L" and L[i] <= pos["stop"]:
                close_pos(i, pos["stop"], "SL")
            elif pos["side"] == "S" and H[i] >= pos["stop"]:
                close_pos(i, pos["stop"], "SL")

        if inON:
            onH = max(onH, H[i]) if prev["inON"] else H[i]
            onL = min(onL, L[i]) if prev["inON"] else L[i]
        if onEnd:
            ONH, ONL = onH, onL
        if inRth:
            rthH = max(rthH, H[i]) if prev["inRth"] else H[i]
            rthL = min(rthL, L[i]) if prev["inRth"] else L[i]
            rthC = C[i]
        if rthEnd:
            pdH, pdL, pdC = rthH, rthL, rthC

        if tradeStart:
            orReady, ORH, ORL, orW, openLoc = False, None, None, None, "-"
            gap = None if pdC is None else O[i] - pdC
            tradesToday = longsToday = shortsToday = 0

        if inOR:
            orH = max(orH, H[i]) if prev["inOR"] else H[i]
            orL = min(orL, L[i]) if prev["inOR"] else L[i]
        if orEnd:
            ORH, ORL = orH, orL
            orW = ORH - ORL
            if ONH is None:
                openLoc = "-"
            else:
                openLoc = ("above" if ORL > ONH else "below" if ORH < ONL else
                           "topBreak" if ORH > ONH else "botBreak" if ORL < ONL else "inside")
            pdPct = None if pdH is None or pdH - pdL <= 0 else 100.0 * orW / (pdH - pdL)
            orReady = orW >= p["min_or_ticks"] * TICK

        okOn = p["on_filter"] == "off" or openLoc in ("topBreak", "above", "botBreak", "below")
        canTrade = (orReady and inEntry and inTrade and ts[i] >= p["start"] and pos is None
                    and tradesToday < p["max_trades"])
        if canTrade:
            brkUp = C[i] > ORH + buf + p["min_brk_or"] * orW
            brkDn = C[i] < ORL - buf - p["min_brk_or"] * orW
            side = None
            if brkUp and okOn and longsToday == 0:
                side, stop = "L", ORL - buf
                longsToday += 1
            elif brkDn and okOn and shortsToday == 0:
                side, stop = "S", ORH + buf
                shortsToday += 1
            if side:
                tradesToday += 1
                sgn = 1 if side == "L" else -1
                risk = sgn * (C[i] - stop)
                if risk > 0:
                    tag = dict(or_w=orW, on=openLoc, pd=pdPct, gap=gap)
                    pos = dict(side=side, entry=C[i] + sgn * slip, stop=stop, i=i, risk=risk, tag=tag)
                    if entry_bar_stop and ((side == "L" and L[i] <= stop) or (side == "S" and H[i] >= stop)):
                        close_pos(i, stop, "SL")

        if tradeEnd and pos is not None:
            close_pos(i, C[i], "time")

        prev = dict(inOR=inOR, inEntry=inEntry, inTrade=inTrade, inON=inON, inRth=inRth)

    return pd.DataFrame(trades)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--bars", default="data/bars/MNQ_5m.parquet")
    ap.add_argument("--out")
    a = ap.parse_args()
    tr = run(pd.read_parquet(a.bars))
    print(f"{len(tr)} trades  net {tr.pnl.sum():+,.0f}")
    if a.out:
        tr.to_csv(a.out, index=False)
