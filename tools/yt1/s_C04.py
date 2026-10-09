#!/usr/bin/env python3
"""C04 - Donchian(20) + 200 EMA (TRADING RUSH), family C common frame.

Spec: Long: the upper band rises on this bar, the latest band move before it was the lower band falling,
close > EMA200. Stop: beyond the lower band. 1.5R. Short mirrored: the lower band falls on this bar, the latest band
move before it was the upper band rising, close < EMA200, stop beyond the upper band.

Common frame (YT1_SPEC.md, family C): `bar`-minute MNQ bars, indicators on the continuous 24-hour series, signals on
bars closing 09:35 -> 15:00, entry at the signal bar's close, one position at a time, any number a day, the cash day
of a roll and the day after it skipped (run_orders skip_roll=2). Neighbours: 3-minute and 15-minute bars.

Readings added to the spec text (fixed before any run):
  * Bands = ind.donchian(high, low, 20): highest high / lowest low of the last 20 bars including the current one.
    "The upper band rises on this bar" = upper[k] > upper[k-1]; "the lower band falls" = lower[k] < lower[k-1].
  * "Band move" = one of the two moves the rule names, the upper band rising or the lower band falling (the source:
    "the upper band makes a new higher high, after lower band had made a lower low"). The passive moves - the upper
    band stepping down or the lower band stepping up when an old extreme leaves the 20-bar window - are not events.
    This is a reading: the words "the latest band move" could also be taken to include them.
  * "Before it" = on an earlier bar (k' < k), anywhere on the continuous series (it may be overnight), whatever the
    close was doing against EMA200 at the time. So a long needs the most recent bar before k on which either event
    happened to be a bar on which the lower band fell.
  * Event order when both bands move outward on the same bar (an outside bar through both 20-bar extremes; the order
    inside the bar is not known from the bar): for the signal on that bar only the events of earlier bars count, so
    it can be a long or a short signal according to the earlier state; for later bars that bar counts as the latest
    move of BOTH kinds (it qualifies the next upper-band rise as a long and the next lower-band fall as a short).
  * Stop = lower[k] - 1 tick (upper[k] + 1 tick), the band value on the signal bar. Target = close +/- 1.5 x
    |close - stop|, rounded to the nearest tick.
  * "bars closing 09:35 -> 15:00": the bar's clock close (open + bar minutes) lies in [09:35, 15:00].
"""
import numpy as np
import core
import ind

ID = "C04"
NAME = "Donchian(20) + 200 EMA"
VARIANTS = {
    "base": dict(bar=5),
    "nb1": dict(bar=3),
    "nb2": dict(bar=15),
}
K_R = 1.5
T = core.TICK


def _frame(ctx, bar):
    """Family C frame. Returns (bars, i_last, i_end, ok): ok[k] = bar k may carry a signal (it closes 09:35 -> 15:00
    on a cash day and before that day's flat bar); the decision is made at the close of 1-minute bar i_last[k]."""
    b = ctx.bars(bar)
    tod = (b.index.hour * 60 + b.index.minute).to_numpy()
    bday = b.index.tz_localize(None).normalize()
    i_end = ctx.days.i_end.reindex(bday).to_numpy(float)          # NaN: the date has no cash session
    i_last = b.i_last.to_numpy()
    ok = (tod + bar >= 575) & (tod + bar <= 900) & ~np.isnan(i_end)
    ok[ok] = i_last[ok] < i_end[ok]
    return b, i_last, i_end, ok


def _last_before(ev):
    """out[k] = index of the latest bar j < k with ev[j], or -1."""
    n = len(ev)
    at = np.maximum.accumulate(np.where(ev, np.arange(n), -1))    # latest j <= k
    return np.r_[-1, at[:-1]]


def signals(ctx, bar=5):
    b, i_last, i_end, ok = _frame(ctx, bar)
    h, l, c = b.high.to_numpy(float), b.low.to_numpy(float), b.close.to_numpy(float)
    e200 = ind.ema(c, 200)
    up, lo = ind.donchian(h, l, 20)
    rise = np.zeros(len(c), bool)
    fall = np.zeros(len(c), bool)
    rise[1:] = up[1:] > up[:-1]                                    # NaN during warm-up compares False
    fall[1:] = lo[1:] < lo[:-1]
    last_rise, last_fall = _last_before(rise), _last_before(fall)
    long_ = ok & rise & (last_fall >= 0) & (last_fall >= last_rise) & (c > e200)
    short_ = ok & fall & (last_rise >= 0) & (last_rise >= last_fall) & (c < e200)
    return dict(b=b, c=c, i_last=i_last, i_end=i_end, long=long_, short=short_, stop_l=lo - T, stop_s=up + T,
                up=up, lo=lo, rise=rise, fall=fall, last_rise=last_rise, last_fall=last_fall, e200=e200)


def orders(ctx, bar=5):
    g = signals(ctx, bar)
    c, i_last, i_end = g["c"], g["i_last"], g["i_end"]
    out = []
    for side, flag, stops in ((1, g["long"], g["stop_l"]), (-1, g["short"], g["stop_s"])):
        for k in np.flatnonzero(flag):
            entry, stop = float(c[k]), float(stops[k])
            target = core.tick_round(entry + side * K_R * abs(entry - stop))
            out.append(dict(i=int(i_last[k]), side=side, etype="close", stop=stop, target=target,
                            exit_i=int(i_end[k]), tag="L" if side > 0 else "S"))
    return out


def diag(ctx, bar=5):
    """Signal counts, stops not on the losing side of the entry (the harness drops those), and how often both bands
    moved outward on one bar (the tie case of the event ordering)."""
    g = signals(ctx, bar)
    c = g["c"]
    kl, ks = np.flatnonzero(g["long"]), np.flatnonzero(g["short"])
    both = g["rise"] & g["fall"]
    tie = (g["last_rise"] == g["last_fall"]) & (g["last_rise"] >= 0)
    return dict(long=len(kl), short=len(ks),
                bad_stop=int((~(g["stop_l"][kl] < c[kl])).sum() + (~(g["stop_s"][ks] > c[ks])).sum()),
                bars_both_bands_move=int(both.sum()), signals_on_such_a_bar=int((both & (g["long"] | g["short"])).sum()),
                signals_whose_latest_move_was_such_a_bar=int((tie & (g["long"] | g["short"])).sum()))


def trades(ctx, **p):
    return core.run_orders(ctx, orders(ctx, **p), skip_roll=2)
