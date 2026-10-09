#!/usr/bin/env python3
"""C01 - MACD + 200 EMA (TRADING RUSH), family C common frame.

Spec: Long: close > EMA200 and MACD(12, 26, 9) crosses above its signal with both lines below zero. Swing stop, 1.5R.
Short mirrored: close < EMA200 and MACD crosses below its signal with both lines above zero.

Common frame (YT1_SPEC.md, family C): `bar`-minute MNQ bars, indicators on the continuous 24-hour series, signals on
bars closing 09:35 -> 15:00, entry at the signal bar's close, one position at a time, any number a day, the cash day
of a roll and the day after it skipped (run_orders skip_roll=2). Neighbours: 3-minute and 15-minute bars.

Readings added to the spec text (fixed before any run):
  * "crosses above" is ind.crossed_up on completed bars: macd[k] > signal[k] and macd[k-1] <= signal[k-1].
  * "with both lines below zero" is read on the cross bar itself: macd[k] < 0 and signal[k] < 0.
  * "bars closing 09:35 -> 15:00": the bar's clock close (open + bar minutes) lies in [09:35, 15:00]; on 3-minute
    bars the first signal bar is therefore the one opening 09:33, on 15-minute bars the one opening 09:30.
  * Swing stop = lowest low of the 10 bars k-9..k of the same (continuous) bar series, minus 1 tick (mirror: highest
    high plus 1 tick). Target = close +/- 1.5 x |close - stop|, rounded to the nearest tick.
"""
import numpy as np
import core
import ind

ID = "C01"
NAME = "MACD + 200 EMA"
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


def signals(ctx, bar=5):
    """Per bar of the `bar`-minute series: long / short signal flags and the stop each side would use."""
    b, i_last, i_end, ok = _frame(ctx, bar)
    h, l, c = b.high.to_numpy(float), b.low.to_numpy(float), b.close.to_numpy(float)
    e200 = ind.ema(c, 200)
    m, s, _ = ind.macd(c, 12, 26, 9)
    long_ = ok & ind.crossed_up(m, s) & (m < 0) & (s < 0) & (c > e200)
    short_ = ok & ind.crossed_dn(m, s) & (m > 0) & (s > 0) & (c < e200)
    stop_l = ind.rolling_min(l, 10) - T                            # beyond the lowest low of the last 10 bars
    stop_s = ind.rolling_max(h, 10) + T
    return dict(b=b, c=c, i_last=i_last, i_end=i_end, long=long_, short=short_, stop_l=stop_l, stop_s=stop_s,
                e200=e200, macd=m, sig=s)


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
    """Signal counts, and how many carry a stop that is not on the losing side of the entry (the harness drops those)."""
    g = signals(ctx, bar)
    c = g["c"]
    kl, ks = np.flatnonzero(g["long"]), np.flatnonzero(g["short"])
    return dict(long=len(kl), short=len(ks),
                bad_stop=int((~(g["stop_l"][kl] < c[kl])).sum() + (~(g["stop_s"][ks] > c[ks])).sum()))


def trades(ctx, **p):
    return core.run_orders(ctx, orders(ctx, **p), skip_roll=2)
