#!/usr/bin/env python3
"""LRB: lunch-range breakout. Local engine, same bars, fill model and costs as orb_engine.py.

    python3 tools/lrb_engine.py [--bars data/bars/MNQ_5m.parquet] [--start 2019-06-01] [--lunch 12:00-14:00]
                                [--entry-window 14:00-15:00] [--days all|break|balance] [--min-brk 0]
                                [--with-morning] [--out trades.csv]

Rule (New York time, 5m bars stamped with their open time):
    lunch range = high/low of the 12:00-13:30 bars; skip the day if it is narrower than 4 ticks.
    13:30-15:00: the first close more than 2 ticks + 0.15 x lunch width beyond the range is the entry at that close
    (above = long, below = short); one trade a day. Stop = other side of the lunch range -/+ 2 ticks, no target,
    flat at the 16:00 close. All days by default.
    --days break|balance: only days whose opening range (09:30-09:45) breaks / stays inside the overnight
    range (18:00-09:30). --with-morning: longs only if the 13:30 price (close of the last bar before 13:30) is above
    the 09:30 open, shorts only if below (a breakout the other way is ignored, not a used-up day).
Tags on every trade: day = break | balance (opening range vs overnight range, '-' without an overnight range);
    lunch = where the lunch range sits against the opening range: above | below | inside (entirely within it) |
    overlap (straddles an edge of it).
Fills: entry at the signal close; stop filled at the stop price when a later bar trades through it; time exit at the
close of the 16:00 bar. Costs: 1 tick slippage on every fill, $1 commission per side, $2/point, 1 contract.
"""
import argparse
import pandas as pd
from orb_engine import TICK, PT_VALUE, COMM_SIDE, SLIP_TICKS, in_sess, report

P = dict(
    on_sess=("18:00", "09:30"), or_sess=("09:30", "09:45"), lunch_sess=("12:00", "13:30"), entry_sess=("13:30", "15:00"),
    trade_sess=("09:30", "16:00"), days="all", buf_ticks=2, min_brk=0.15, min_ticks=4, with_morning=False,
    start=pd.Timestamp("2019-06-01", tz="America/New_York"),
)


def run(bars, **over):
    p = {**P, **over}
    buf, slip = p["buf_ticks"] * TICK, SLIP_TICKS * TICK
    ts = bars.index
    tod = (ts.hour * 60 + ts.minute).to_numpy()
    O, H, L, C = (bars[k].to_numpy() for k in ("open", "high", "low", "close"))
    t1330 = 13 * 60 + 30

    trades = []
    prev = dict(inON=False, inOR=False, inLunch=False, inTrade=False)
    onH = onL = ONH = ONL = orH = orL = luH = luL = None
    dayType, lunchLoc, lunchReady = "-", "-", False
    open930 = px1330 = None
    done = False
    pos = None

    def close_pos(i, px, reason):
        nonlocal pos
        sgn = 1 if pos["side"] == "L" else -1
        fill = px - sgn * slip
        pnl = sgn * (fill - pos["entry"]) * PT_VALUE - 2 * COMM_SIDE
        trades.append(dict(side=pos["side"], entry_time=ts[pos["i"]], entry=pos["entry"], exit_time=ts[i], exit=fill,
                           reason=reason, pnl=pnl, risk=pos["risk"], R=pnl / (pos["risk"] * PT_VALUE),
                           lunch_w=pos["w"], day=pos["day"], lunch=pos["lunch"]))
        pos = None

    for i in range(len(ts)):
        t = tod[i]
        inON, inOR, inLunch = in_sess(t, p["on_sess"]), in_sess(t, p["or_sess"]), in_sess(t, p["lunch_sess"])
        inEntry, inTrade = in_sess(t, p["entry_sess"]), in_sess(t, p["trade_sess"])
        onEnd, orEnd, lunchEnd = not inON and prev["inON"], not inOR and prev["inOR"], not inLunch and prev["inLunch"]
        tradeStart, tradeEnd = inTrade and not prev["inTrade"], not inTrade and prev["inTrade"]

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
        if tradeStart:
            dayType, lunchLoc, lunchReady, done = "-", "-", False, False
            orH = orL = None
            open930, px1330 = O[i], None
        if inOR:
            orH = max(orH, H[i]) if prev["inOR"] else H[i]
            orL = min(orL, L[i]) if prev["inOR"] else L[i]
        if orEnd and ONH is not None:
            dayType = "balance" if orH <= ONH and orL >= ONL else "break"
        if inLunch:
            luH = max(luH, H[i]) if prev["inLunch"] else H[i]
            luL = min(luL, L[i]) if prev["inLunch"] else L[i]
        if t < t1330 and inTrade:
            px1330 = C[i]                      # last close before 13:30 = the 13:30 price
        if lunchEnd:
            lunchReady = luH - luL >= p["min_ticks"] * TICK
            if orH is not None:
                lunchLoc = ("above" if luL > orH else "below" if luH < orL else
                            "inside" if luH <= orH and luL >= orL else "overlap")

        dayOk = p["days"] == "all" or dayType == p["days"]
        if lunchReady and dayOk and inEntry and inTrade and not done and pos is None and ts[i] >= p["start"]:
            w = luH - luL
            # --with-morning filters a side out (as a direction filter in ORB), it does not use the day up
            okL = not p["with_morning"] or px1330 > open930
            okS = not p["with_morning"] or px1330 < open930
            side = ("L" if okL and C[i] > luH + buf + p["min_brk"] * w else
                    "S" if okS and C[i] < luL - buf - p["min_brk"] * w else None)
            if side:
                done = True                    # one trade a day: the first qualifying breakout decides it
                sgn = 1 if side == "L" else -1
                stop = luL - buf if side == "L" else luH + buf
                if sgn * (C[i] - stop) > 0:
                    pos = dict(side=side, entry=C[i] + sgn * slip, stop=stop, i=i, risk=sgn * (C[i] - stop),
                               w=w, day=dayType, lunch=lunchLoc)

        if tradeEnd and pos is not None:
            close_pos(i, C[i], "time")

        prev = dict(inON=inON, inOR=inOR, inLunch=inLunch, inTrade=inTrade)

    return pd.DataFrame(trades)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--bars", default="data/bars/MNQ_5m.parquet")
    ap.add_argument("--start", default="2019-06-01")
    ap.add_argument("--lunch", default="-".join(P["lunch_sess"]))
    ap.add_argument("--entry-window", default="-".join(P["entry_sess"]))
    ap.add_argument("--days", choices=["all", "break", "balance"], default=P["days"])
    ap.add_argument("--min-brk", type=float, default=P["min_brk"])
    ap.add_argument("--with-morning", action="store_true")
    ap.add_argument("--out")
    a = ap.parse_args()
    bars = pd.read_parquet(a.bars)
    tr = run(bars, start=pd.Timestamp(a.start, tz="America/New_York"), lunch_sess=tuple(a.lunch.split("-")),
             entry_sess=tuple(a.entry_window.split("-")), days=a.days, min_brk=a.min_brk, with_morning=a.with_morning)
    print(f"{tr.entry_time.iloc[0].date()} -> {bars.index[-1].date()}  lunch {a.lunch}  entries {a.entry_window}  "
          f"days {a.days}  min brk {a.min_brk}  with morning {a.with_morning}")
    report(tr, groups=("side", "reason", "day", "lunch"))
    if a.out:
        tr.to_csv(a.out, index=False)
