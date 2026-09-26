#!/usr/bin/env python3
"""ONR: overnight-extreme rejection on balance days. Local engine, same bars, fill model and costs as orb_engine.py.

    python3 tools/onr_engine.py [--bars data/bars/MNQ_5m.parquet] [--start 2019-06-01] [--tp mid|opposite|none]
                                [--stop-mode width|ticks] [--entry-window 09:45-12:00] [--min-poke 0.1] [--out trades.csv]

Rule (New York time, 5m bars stamped with their open time):
    overnight range = high/low of 18:00-09:30, opening range = 09:30-09:45; trade only when the opening range is
    entirely inside the overnight range (balance day).
    09:45-12:00: the first bar that trades above the overnight high and closes back below it is a short at its close
    (mirror at the overnight low). One trade per side per day; that first qualifying bar uses the side up even when
    it is skipped (reward:risk < 1.0, or a trade already open).
    stop = highest high since price first went above the overnight high + 0.15 x overnight width
           (--stop-mode ticks: + 2 ticks); target = overnight midpoint (--tp opposite: the other overnight extreme,
           --tp none: hold to the close). Optional --min-poke k: the excursion must reach k x overnight width beyond
           the extreme for the bar to qualify.
Fills: entry at the signal close; stop / target on the tick, filled at their price when a later bar trades through
(stop wins a bar that touches both); time exit at the close of the 16:00 bar. Costs: 1 tick slippage on every fill,
$1 commission per side, $2/point, 1 contract.
"""
import argparse
import pandas as pd
from orb_engine import TICK, PT_VALUE, COMM_SIDE, SLIP_TICKS, in_sess, report, halted_after

P = dict(
    on_sess=("18:00", "09:30"), or_sess=("09:30", "09:45"), entry_sess=("09:45", "12:00"), trade_sess=("09:30", "16:00"),
    tp="mid", stop_mode="width", stop_w=0.15, stop_ticks=2, min_rr=1.0, min_poke=0.0,
    start=pd.Timestamp("2019-06-01", tz="America/New_York"),
)


def _tick(x):
    return round(x / TICK) * TICK


def run(bars, **over):
    p = {**P, **over}
    slip = SLIP_TICKS * TICK
    ts = bars.index
    tod = (ts.hour * 60 + ts.minute).to_numpy()
    H, L, C = (bars[k].to_numpy() for k in ("high", "low", "close"))

    trades = []
    prev = dict(inON=False, inOR=False, inTrade=False)
    onH = onL = ONH = ONL = orH = orL = None
    balance = False
    excHi = excLo = None       # extreme since price first went beyond the overnight high / low today
    doneS = doneL = False      # side used up today
    pos = None

    def close_pos(i, px, reason):
        nonlocal pos
        sgn = 1 if pos["side"] == "L" else -1
        fill = px - sgn * slip
        pnl = sgn * (fill - pos["entry"]) * PT_VALUE - 2 * COMM_SIDE
        trades.append(dict(side=pos["side"], entry_time=ts[pos["i"]], entry=pos["entry"], exit_time=ts[i], exit=fill,
                           reason=reason, pnl=pnl, risk=pos["risk"], R=pnl / (pos["risk"] * PT_VALUE),
                           rr=pos["rr"], on_w=pos["on_w"], poke=pos["poke"]))
        pos = None

    for i in range(len(ts)):
        t = tod[i]
        inON, inOR = in_sess(t, p["on_sess"]), in_sess(t, p["or_sess"])
        inEntry, inTrade = in_sess(t, p["entry_sess"]), in_sess(t, p["trade_sess"])
        onEnd = not inON and prev["inON"]
        orEnd = not inOR and prev["inOR"]
        tradeStart = inTrade and not prev["inTrade"]
        tradeEnd = not inTrade and prev["inTrade"]

        # resting exits on bars after the entry bar: stop first, then target
        if pos is not None and i > pos["i"]:
            if pos["side"] == "L":
                if L[i] <= pos["stop"]:
                    close_pos(i, pos["stop"], "SL")
                elif pos["tp"] is not None and H[i] >= pos["tp"]:
                    close_pos(i, pos["tp"], "TP")
            else:
                if H[i] >= pos["stop"]:
                    close_pos(i, pos["stop"], "SL")
                elif pos["tp"] is not None and L[i] <= pos["tp"]:
                    close_pos(i, pos["tp"], "TP")

        if inON:
            onH = max(onH, H[i]) if prev["inON"] else H[i]
            onL = min(onL, L[i]) if prev["inON"] else L[i]
        if onEnd:
            ONH, ONL = onH, onL
        if tradeStart:
            balance, excHi, excLo, doneS, doneL = False, None, None, False, False
        if inOR:
            orH = max(orH, H[i]) if prev["inOR"] else H[i]
            orL = min(orL, L[i]) if prev["inOR"] else L[i]
        if orEnd:
            balance = ONH is not None and orH <= ONH and orL >= ONL

        if balance and inTrade:
            if H[i] > ONH:
                excHi = H[i] if excHi is None else max(excHi, H[i])
            if L[i] < ONL:
                excLo = L[i] if excLo is None else min(excLo, L[i])

        if balance and inEntry and ts[i] >= p["start"]:
            W = ONH - ONL
            mid = (ONH + ONL) / 2
            for side in ("S", "L"):
                if side == "S":
                    fire = not doneS and H[i] > ONH and C[i] < ONH and excHi - ONH >= p["min_poke"] * W
                else:
                    fire = not doneL and L[i] < ONL and C[i] > ONL and ONL - excLo >= p["min_poke"] * W
                if not fire:
                    continue
                if side == "S":
                    doneS = True
                else:
                    doneL = True
                if pos is not None:
                    continue
                sgn = 1 if side == "L" else -1
                ext = excHi if side == "S" else excLo
                stop = ext - sgn * (p["stop_w"] * W if p["stop_mode"] == "width" else p["stop_ticks"] * TICK)
                tp = None if p["tp"] == "none" else mid if p["tp"] == "mid" else (ONL if side == "S" else ONH)
                risk = sgn * (C[i] - stop)
                rr = None if tp is None else sgn * (tp - C[i]) / risk
                if risk <= 0 or (tp is not None and rr < p["min_rr"]):
                    continue
                pos = dict(side=side, entry=C[i] + sgn * slip, stop=_tick(stop), tp=None if tp is None else _tick(tp),
                           i=i, risk=risk, rr=rr, on_w=W, poke=ext - ONH if side == "S" else ONL - ext)

        if pos is not None and inTrade and halted_after(ts, i):   # early close: flatten on the session's last bar
            close_pos(i, C[i], "time")
        if tradeEnd and pos is not None:
            close_pos(i, C[i], "time")

        prev = dict(inON=inON, inOR=inOR, inTrade=inTrade)

    return pd.DataFrame(trades)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--bars", default="data/bars/MNQ_5m.parquet")
    ap.add_argument("--start", default="2019-06-01")
    ap.add_argument("--tp", choices=["mid", "opposite", "none"], default=P["tp"])
    ap.add_argument("--stop-mode", choices=["width", "ticks"], default=P["stop_mode"])
    ap.add_argument("--entry-window", default="-".join(P["entry_sess"]))
    ap.add_argument("--min-poke", type=float, default=P["min_poke"])
    ap.add_argument("--out")
    a = ap.parse_args()
    bars = pd.read_parquet(a.bars)
    tr = run(bars, start=pd.Timestamp(a.start, tz="America/New_York"), tp=a.tp, stop_mode=a.stop_mode,
             entry_sess=tuple(a.entry_window.split("-")), min_poke=a.min_poke)
    print(f"{tr.entry_time.iloc[0].date()} -> {bars.index[-1].date()}  tp {a.tp}  stop {a.stop_mode}  "
          f"entries {a.entry_window}  min poke {a.min_poke}")
    report(tr)
    if a.out:
        tr.to_csv(a.out, index=False)
