#!/usr/bin/env python3
"""YT2 frame (the family C / C19 frame of YT1, with volume and an optional custom stop).

    orders(ctx, tf, trigger, k_r=1.5, ema_filter=True)
    trigger(o, h, l, c, v) -> dict(long=bool array, short=bool array, stop_l=array or None, stop_s=array or None)

Each array has one value per tf-minute bar of the continuous 24-hour series and may use bars up to and including that
bar only. The frame adds: signal bars closing 09:35 -> 15:00; close > EMA200 for longs / < EMA200 for shorts (unless
ema_filter=False); entry at the signal bar's close; the stop = the trigger's own level, 1 tick beyond it, when it is on
the losing side of the entry, otherwise the swing stop (1 tick beyond the lowest low / highest high of the last 10
bars including the signal bar); target k_r x the risk, rounded to the tick; exit at the flat bar.
trades() = one position at a time, any number a day, roll days and the day after skipped.
"""
import numpy as np
import core
import ind

WIN_LO, WIN_HI = 9 * 60 + 35, 15 * 60
SWING, EMA_LEN = 10, 200


def bars(ctx, tf):
    b = ctx.bars(tf)
    return tuple(b[k].to_numpy(float) for k in ("open", "high", "low", "close", "volume"))


def orders(ctx, tf, trigger, k_r=1.5, ema_filter=True, tag=""):
    b = ctx.bars(tf)
    o, h, l, c, v = bars(ctx, tf)
    i_last = b.i_last.to_numpy()
    close_t = (b.index.hour * 60 + b.index.minute).to_numpy() + tf
    in_win = (close_t >= WIN_LO) & (close_t <= WIN_HI)
    e200 = ind.ema(c, EMA_LEN)
    lo10, hi10 = ind.rolling_min(l, SWING), ind.rolling_max(h, SWING)
    g = trigger(o, h, l, c, v)
    ls, ss = np.asarray(g["long"], bool), np.asarray(g["short"], bool)
    sl, sh = g.get("stop_l"), g.get("stop_s")
    with np.errstate(invalid="ignore"):
        long_ok = ls & in_win & np.isfinite(lo10) & np.isfinite(e200) & ((c > e200) if ema_filter else True)
        short_ok = ss & in_win & np.isfinite(hi10) & np.isfinite(e200) & ((c < e200) if ema_filter else True)
    i_end = ctx.days.i_end.to_numpy()
    T = core.TICK
    out = []
    for k in np.flatnonzero(long_ok | short_ok):
        if long_ok[k] and short_ok[k]:
            continue                                   # both sides on one bar: no trade
        i = int(i_last[k])
        dn = ctx.dayn[i]
        if dn < 0:
            continue
        side = 1 if long_ok[k] else -1
        entry = c[k]
        stop, kind = (lo10[k] - T if side > 0 else hi10[k] + T), "swing"
        own = sl if side > 0 else sh
        if own is not None and np.isfinite(own[k]):
            lvl = core.tick_round(own[k], "down" if side > 0 else "up") - side * T
            if side * (entry - lvl) >= T:
                stop, kind = lvl, "own"
        target = core.tick_round(entry + side * k_r * abs(entry - stop))
        out.append(dict(i=i, side=side, etype="close", stop=float(stop), target=float(target),
                        exit_i=int(i_end[dn]), tag=f"{tag}{'L' if side > 0 else 'S'}|{kind}"))
    return out


def trades(ctx, tf, trigger, **kw):
    return core.run_orders(ctx, orders(ctx, tf, trigger, **kw), one_at_a_time=True, skip_roll=2)
