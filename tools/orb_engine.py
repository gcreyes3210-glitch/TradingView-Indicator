#!/usr/bin/env python3
"""Local bar-by-bar replica of ORB_strategy.pine (v1.3 defaults).

    python3 tools/orb_engine.py [--bars data/bars/MNQ_5m.parquet] [--start 2020-01-01] [--or 09:30-10:00]
                                [--entry-window 10:00-11:30] [--entry-mode close|stop] [--max-trades 2]
                                [--min-brk 0] [--point-value 5] [--out trades.csv]

Mirrors the Pine script's per-bar state machine on 5m bars stamped with their open time (New York):
    opening range 09:30-09:45 · entries 09:45-11:30 · trade window 09:30-16:00 · overnight 18:00-09:30
    long when close > ORH + 2 ticks + 0.15 x range, short when close < ORL - 2 ticks - 0.15 x range,
    only on days whose opening range breaks the overnight range, max 1 trade a day, stop = other side ± 2 ticks,
    no target, flat on the first bar after 16:00. Each side is taken at most once a day, so with max 2 trades
    the second trade is the other side, after the first has been stopped out.
Fill model (the calibration rules):
    entry at the signal bar's close; stop filled at the stop price when a later bar trades through it;
    nothing trades after a close entry within its own bar, so the entry bar's low/high never stops it
    (TradingView agrees: 2026-04-13, entry bar touched the stop before closing out); time exit at the close
    of the bar that opens at 16:00; stop beats the time exit on the same bar.
    Costs: 1 tick slippage against every fill + $1 commission per side, 1 contract; MNQ $2/point (MES: --point-value 5).
Stop-order entry (--entry-mode stop): while flat inside the entry window, buy stop at ORH + 2 ticks and sell stop at
    ORL - 2 ticks rest from each bar's close to the next bar. They fill at the stop price when a bar trades through it,
    or at the open when the bar opens beyond it. The first side to fill (bar path as TradingView assumes it: open ->
    nearer extreme -> other extreme -> close) wins and cancels the other; the protective stop is live for the
    rest of that bar's path.
"""
import argparse
import pandas as pd

TICK, PT_VALUE, COMM_SIDE, SLIP_TICKS = 0.25, 2.0, 1.0, 1

P = dict(
    or_sess=("09:30", "09:45"), entry_sess=("09:45", "11:30"), trade_sess=("09:30", "16:00"),
    on_sess=("18:00", "09:30"), rth_sess=("09:30", "16:00"),
    point_value=PT_VALUE, entry_mode="close", buf_ticks=2, max_trades=1, min_or_ticks=4, min_brk_or=0.15, on_filter="break",
    start=pd.Timestamp("2020-01-01", tz="America/New_York"),
)


def _mins(s):
    h, m = s.split(":"); return int(h) * 60 + int(m)


def in_sess(tod, sess):
    a, b = _mins(sess[0]), _mins(sess[1])
    return (a <= tod < b) if a < b else (tod >= a or tod < b)


def _path(o, h, l, c):
    """TradingView's intrabar assumption: open -> the extreme nearer the open -> the other extreme -> close."""
    return [o, h, l, c] if abs(h - o) < abs(o - l) else [o, l, h, c]


def _stop_entry(o, h, l, c, entL, entS):
    """First resting entry stop to fill on this bar. Returns (side, fill price, remaining path) or None."""
    pts = _path(o, h, l, c)
    if entL is not None and o >= entL:
        return "L", o, pts
    if entS is not None and o <= entS:
        return "S", o, pts
    for a, b, k in zip(pts, pts[1:], range(1, 4)):
        if entL is not None and a < entL <= b:
            return "L", entL, [entL] + pts[k:]
        if entS is not None and a > entS >= b:
            return "S", entS, [entS] + pts[k:]
    return None


def run(bars, p=P, entry_bar_stop=False, **over):
    p = {**p, **over}
    buf = p["buf_ticks"] * TICK
    slip = SLIP_TICKS * TICK
    stop_mode = p["entry_mode"] == "stop"
    ts = bars.index
    tod = (ts.hour * 60 + ts.minute).to_numpy()
    O, H, L, C = (bars[k].to_numpy() for k in ("open", "high", "low", "close"))

    trades = []
    prev = dict(inOR=False, inEntry=False, inTrade=False, inON=False, inRth=False)
    onH = onL = ONH = ONL = None
    rthH = rthL = rthC = rthO = pdH = pdL = pdC = pdO = None
    orH = orL = ORH = ORL = orW = None
    orReady, openLoc, gap, pdPct = False, "-", None, None
    tradesToday = longsToday = shortsToday = 0
    pos = None  # dict(side, entry, stop, i, tag)
    pend = None  # stop-order mode: dict(L=price|None, S=price|None) resting for this bar

    def close_pos(i, px, reason):
        nonlocal pos
        sgn = 1 if pos["side"] == "L" else -1
        fill = px - sgn * slip
        pnl = sgn * (fill - pos["entry"]) * p["point_value"] - 2 * COMM_SIDE
        trades.append(dict(side=pos["side"], entry_time=ts[pos["i"]], entry=pos["entry"], exit_time=ts[i],
                           exit=fill, reason=reason, pnl=pnl, risk=pos["risk"], n=pos["n"], gap_fill=pos["gap_fill"],
                           **pos["tag"]))
        pos = None

    def open_pos(i, side, px, stop, gap_fill=False):
        nonlocal pos
        sgn = 1 if side == "L" else -1
        pos = dict(side=side, entry=px + sgn * slip, stop=stop, i=i, risk=sgn * (px - stop), n=tradesToday,
                   gap_fill=gap_fill, tag=dict(or_w=orW, on=openLoc, pd=pdPct, gap=gap,
                   on_w=None if ONH is None else ONH - ONL, pd_range=None if pdH is None else pdH - pdL,
                   pd_dir=None if pdC is None else ("up" if pdC > pdO else "down" if pdC < pdO else "flat")))

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

        # broker emulator: resting entry stops placed at the previous bar's close
        if stop_mode and pend is not None and pos is None:
            hit = _stop_entry(O[i], H[i], L[i], C[i], pend["L"], pend["S"])
            if hit:
                side, px, rest = hit
                stop = ORL - buf if side == "L" else ORH + buf
                tradesToday += 1
                if side == "L":
                    longsToday += 1
                else:
                    shortsToday += 1
                open_pos(i, side, px, stop, gap_fill=px == O[i])
                if (side == "L" and min(rest) <= stop) or (side == "S" and max(rest) >= stop):
                    close_pos(i, stop, "SL")
        pend = None

        if inON:
            onH = max(onH, H[i]) if prev["inON"] else H[i]
            onL = min(onL, L[i]) if prev["inON"] else L[i]
        if onEnd:
            ONH, ONL = onH, onL
        if inRth:
            rthH = max(rthH, H[i]) if prev["inRth"] else H[i]
            rthL = min(rthL, L[i]) if prev["inRth"] else L[i]
            rthC = C[i]
            if not prev["inRth"]:
                rthO = O[i]
        if rthEnd:
            pdH, pdL, pdC, pdO = rthH, rthL, rthC, rthO

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
        if canTrade and stop_mode:
            if okOn and (longsToday == 0 or shortsToday == 0):
                pend = dict(L=ORH + buf if longsToday == 0 else None, S=ORL - buf if shortsToday == 0 else None)
        elif canTrade:
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
                if sgn * (C[i] - stop) > 0:
                    open_pos(i, side, C[i], stop)
                    if entry_bar_stop and ((side == "L" and L[i] <= stop) or (side == "S" and H[i] >= stop)):
                        close_pos(i, stop, "SL")

        if tradeEnd and pos is not None:
            close_pos(i, C[i], "time")

        prev = dict(inOR=inOR, inEntry=inEntry, inTrade=inTrade, inON=inON, inRth=inRth)

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
                avg_loss=round(pnl[pnl < 0].mean()) if (pnl < 0).any() else None,
                **({"R": round(df.R.mean(), 3)} if "R" in df else {}))


def report(tr, groups=("side", "reason")):
    def row(name, d):
        s = stats(d)
        print(f"  {name:<10}" + "  ".join(f"{k} {v}" for k, v in s.items()))
    row("all", tr)
    print(" per calendar year:")
    for y, d in tr.groupby(tr.entry_time.dt.year):
        row(str(y), d)
    for g in groups:
        print(f" by {g}:")
        for k, d in tr.groupby(g):
            row(str(k), d)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--bars", default="data/bars/MNQ_5m.parquet")
    ap.add_argument("--start", default="2020-01-01")
    ap.add_argument("--or", dest="or_sess", default="-".join(P["or_sess"]))
    ap.add_argument("--entry-window", default="-".join(P["entry_sess"]))
    ap.add_argument("--entry-mode", choices=["close", "stop"], default=P["entry_mode"])
    ap.add_argument("--max-trades", type=int, default=P["max_trades"])
    ap.add_argument("--min-brk", type=float, default=P["min_brk_or"])
    ap.add_argument("--point-value", type=float, default=PT_VALUE, help="$ per point: MNQ 2, MES 5")
    ap.add_argument("--out")
    a = ap.parse_args()
    bars = pd.read_parquet(a.bars)
    tr = run(bars, start=pd.Timestamp(a.start, tz="America/New_York"), or_sess=tuple(a.or_sess.split("-")),
             entry_sess=tuple(a.entry_window.split("-")), entry_mode=a.entry_mode, max_trades=a.max_trades,
             min_brk_or=a.min_brk, point_value=a.point_value)
    print(f"{tr.entry_time.iloc[0].date()} -> {bars.index[-1].date()}  or {a.or_sess}  entries {a.entry_window}  "
          f"mode {a.entry_mode}  max {a.max_trades}  min brk {a.min_brk}")
    report(tr, groups=("side", "reason", "n"))
    if a.out:
        tr.to_csv(a.out, index=False)
