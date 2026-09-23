#!/usr/bin/env python3
"""GAP: opening-gap fill. Local engine, same bars, fill model and costs as orb_engine.py.

    python3 tools/gap_engine.py [--bars data/bars/MNQ_5m.parquet] [--start 2019-06-01] [--min-gap 1.0] [--out trades.csv]

Rule (New York time, 5m bars stamped with their open time):
    gap = 09:30 open - previous cash session's 16:00 close (close of its last bar before 16:00).
    If |gap| >= min_gap x the previous cash session's high-low range (default 0.5): enter at the 09:30 bar's close
    toward the previous close (short an up gap, long a down gap). Skip if that close is already at or beyond the
    previous close (the gap filled inside the first bar, the target is behind the entry).
    stop = the 09:30 bar's high (short) / low (long) + / - 0.25 x |gap|; target = previous close.
    Flat at 12:00: close of the bar that opens at 12:00 (the ORB convention for 'flat at 16:00'). One trade a day.
Fills: stop / target on the tick, filled at their price when a later bar trades through (stop wins a bar that touches
both); 1 tick slippage on every fill, $1 commission per side, $2/point, 1 contract.
"""
import argparse
import pandas as pd
from orb_engine import TICK, PT_VALUE, COMM_SIDE, SLIP_TICKS, in_sess, report

P = dict(rth_sess=("09:30", "16:00"), trade_sess=("09:30", "12:00"), min_gap=0.5, stop_gap=0.25,
         start=pd.Timestamp("2019-06-01", tz="America/New_York"))


def _tick(x):
    return round(x / TICK) * TICK


def run(bars, **over):
    p = {**P, **over}
    slip = SLIP_TICKS * TICK
    ts = bars.index
    tod = (ts.hour * 60 + ts.minute).to_numpy()
    O, H, L, C = (bars[k].to_numpy() for k in ("open", "high", "low", "close"))

    trades = []
    prev = dict(inRth=False, inTrade=False)
    rthH = rthL = rthC = pdH = pdL = pdC = None
    pos = None

    def close_pos(i, px, reason):
        nonlocal pos
        sgn = 1 if pos["side"] == "L" else -1
        fill = px - sgn * slip
        pnl = sgn * (fill - pos["entry"]) * PT_VALUE - 2 * COMM_SIDE
        trades.append(dict(side=pos["side"], entry_time=ts[pos["i"]], entry=pos["entry"], exit_time=ts[i], exit=fill,
                           reason=reason, pnl=pnl, risk=pos["risk"], R=pnl / (pos["risk"] * PT_VALUE),
                           gap=pos["gap"], gap_x=pos["gap_x"]))
        pos = None

    for i in range(len(ts)):
        t = tod[i]
        inRth, inTrade = in_sess(t, p["rth_sess"]), in_sess(t, p["trade_sess"])
        rthStart, rthEnd = inRth and not prev["inRth"], not inRth and prev["inRth"]
        tradeEnd = not inTrade and prev["inTrade"]

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

        # entry on the first cash bar, judged against the previous finished cash session
        if rthStart and pdC is not None and pdH - pdL > 0 and ts[i] >= p["start"] and pos is None:
            gap = O[i] - pdC
            if abs(gap) >= p["min_gap"] * (pdH - pdL):
                side, sgn = ("S", -1) if gap > 0 else ("L", 1)
                stop = H[i] + p["stop_gap"] * abs(gap) if side == "S" else L[i] - p["stop_gap"] * abs(gap)
                if sgn * (pdC - C[i]) > 0:
                    pos = dict(side=side, entry=C[i] + sgn * slip, stop=_tick(stop), tp=pdC, i=i,
                               risk=sgn * (C[i] - stop), gap=gap, gap_x=abs(gap) / (pdH - pdL))

        if inRth:
            rthH = max(rthH, H[i]) if prev["inRth"] else H[i]
            rthL = min(rthL, L[i]) if prev["inRth"] else L[i]
            rthC = C[i]
        if rthEnd:
            pdH, pdL, pdC = rthH, rthL, rthC

        if tradeEnd and pos is not None:
            close_pos(i, C[i], "time")

        prev = dict(inRth=inRth, inTrade=inTrade)

    return pd.DataFrame(trades)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--bars", default="data/bars/MNQ_5m.parquet")
    ap.add_argument("--start", default="2019-06-01")
    ap.add_argument("--min-gap", type=float, default=P["min_gap"])
    ap.add_argument("--out")
    a = ap.parse_args()
    bars = pd.read_parquet(a.bars)
    tr = run(bars, start=pd.Timestamp(a.start, tz="America/New_York"), min_gap=a.min_gap)
    print(f"{tr.entry_time.iloc[0].date()} -> {bars.index[-1].date()}  min gap {a.min_gap} x previous range")
    report(tr)
    if a.out:
        tr.to_csv(a.out, index=False)
