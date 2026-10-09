#!/usr/bin/env python3
"""C15 - VWAP trend-day first pullback.

Spec: 5-minute MNQ bars. VWAP anchored at 09:30 each cash day, with its volume-weighted standard deviation
(ind.session_vwap on the 5-minute bars, TradingView's definition: hlc3 weighted by volume).
Run            = `run` (10; neighbours 8, 12) consecutive 5-minute closes above VWAP, counted from the 09:30 bar.
First pullback = the first later bar with low <= VWAP + 4 ticks.
Entry          = the close of the first bar, among the pullback bar and the next three, that closes above VWAP and
                 above its open; a close below VWAP first ends the set-up. Signal bars close by 15:00.
Stop           = the pullback bar's low - 0.5 x ATR(14) (5-minute, Wilder, value at the signal bar), on the tick grid.
Exit           = half at the farther of VWAP + 1 sd and 1R, half at the farther of VWAP + 2 sd and 2R (VWAP, sd and R
                 as they stand at the signal bar's close; R = signal close - stop), else the stop or the flat bar.
Short mirrored. One per direction per day; one position at a time; roll days and the day after are skipped.

Reading of what comes after a set-up that ends without an entry: a new run needs the count of consecutive closes to
start again from a close that is not above VWAP (so the same unbroken run never gives a second "first pullback").
"""
import numpy as np
import core
import ind

ID = "C15"
NAME = "VWAP (09:30 anchor) trend-day first pullback"
VARIANTS = {
    "base": dict(run=10),
    "nb1": dict(run=8),
    "nb2": dict(run=12),
}

OPEN, WIN_HI = 9 * 60 + 30, 15 * 60            # signal bars close by 15:00
TOUCH_TICKS, TRIES, ATR_LEN, ATR_K = 4, 4, 14, 0.5


def _first_signal(side, ks, o, h, l, c, vw, run):
    """The day's first entry bar for one direction. ks = the day's 5-minute bars from 09:30 in order.
    Returns (signal bar, pullback bar) or None. Prices are looked at in the trade's own direction (side = +1 / -1),
    so the long rule is written once and the short is its mirror."""
    T = core.TICK
    state, streak, p, tries = "count", 0, None, 0
    for k in ks:
        beyond = side * (c[k] - vw[k]) > 0              # the close is on the run's side of VWAP
        if state == "wait":                             # an expired set-up: the run must break before a new count
            if beyond:
                continue
            state, streak = "count", 0
            continue
        if state == "count":
            streak = streak + 1 if beyond else 0
            if streak >= run:
                state = "armed"                         # the pullback is looked for on LATER bars
            continue
        if state == "armed":
            touched = (l[k] <= vw[k] + TOUCH_TICKS * T) if side > 0 else (h[k] >= vw[k] - TOUCH_TICKS * T)
            if not touched:
                continue
            state, p, tries = "pull", k, 0              # and this same bar is the first of the four entry bars
        # state == "pull"
        if side * (c[k] - vw[k]) < 0:                   # a close through VWAP ends the set-up (and the run)
            state, streak = "count", 0
            continue
        if beyond and side * (c[k] - o[k]) > 0:
            return k, p
        tries += 1
        if tries >= TRIES:
            state = "wait"
    return None


def orders(ctx, run=10):
    b = ctx.bars(5)
    o, h, l, c, v = (b[k].to_numpy(float) for k in ("open", "high", "low", "close", "volume"))
    i_last = b.i_last.to_numpy()
    tod = (b.index.hour * 60 + b.index.minute).to_numpy()
    bday = b.index.tz_localize(None).normalize().to_numpy()
    vw, sd = ind.session_vwap(h, l, c, v, tod == OPEN)
    atr = ind.atr(h, l, c, ATR_LEN)
    sess = (tod >= OPEN) & (tod + 5 <= WIN_HI)          # bars 09:30 .. 14:55
    out = []
    for d, day in ctx.days.iterrows():
        lo, hi = np.searchsorted(bday, np.datetime64(d), "left"), np.searchsorted(bday, np.datetime64(d), "right")
        ks = lo + np.flatnonzero(sess[lo:hi])
        if len(ks) == 0 or tod[ks[0]] != OPEN:
            continue
        for side in (1, -1):
            hit = _first_signal(side, ks, o, h, l, c, vw, run)
            if hit is None:
                continue
            k, p = hit
            if not (np.isfinite(atr[k]) and np.isfinite(sd[k])):
                continue
            entry = c[k]
            ext = l[p] if side > 0 else h[p]
            stop = core.tick_round(ext - side * ATR_K * atr[k])
            r = abs(entry - stop)
            t1 = entry + side * max(side * (vw[k] + side * sd[k] - entry), r)
            t2 = entry + side * max(side * (vw[k] + side * 2 * sd[k] - entry), 2 * r)
            parts = [(float(core.tick_round(t1)), 0.5), (float(core.tick_round(t2)), 0.5)]
            out.append(dict(i=int(i_last[k]), side=side, etype="close", stop=float(stop), parts=parts,
                            exit_i=int(day.i_end), tag=("L" if side > 0 else "S") + f" pb{k - p}"))
    return out


def trades(ctx, **p):
    return core.run_orders(ctx, orders(ctx, **p), one_at_a_time=True, skip_roll=2)
