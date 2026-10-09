#!/usr/bin/env python3
"""C08 - Bollinger upper-band breakout + 200 MA (long only, as tested). YT1_SPEC.md, family C.

Spec: long when close > SMA200, the close crosses above the upper Bollinger band (20, 2), and the previous trading day
closed above its 9-day EMA. Swing stop, 1.5R. Neighbours: the same rule on 3-minute and 15-minute bars.

Family C frame: N-minute bars (N = `bar`, 5 in the base), indicators on the continuous 24-hour series, signal bars
closing 09:35 -> 15:00, entry at the signal bar's close, one position at a time, any number a day, skip_roll=2.
Swing stop = 1 tick beyond the lowest low of the last 10 bars including the signal bar.
Target = entry close + 1.5 x (entry close - stop), rounded to the tick.

Daily filter: trading days run 18:00 -> 17:00 (ctx.tdate, the same days core uses for the daily ATR). For a signal
bar on trading day D only the PREVIOUS completed trading day is read: its last close against the 9-day EMA of the
daily closes up to and including that day. Nothing of day D itself enters the filter.
"""
import numpy as np
import core
import ind

ID = "C08"
NAME = "Bollinger upper-band breakout + 200 SMA + daily 9 EMA (long only)"
VARIANTS = {
    "base": dict(bar=5),
    "nb1": dict(bar=3),
    "nb2": dict(bar=15),
}

SWING = 10          # bars in the swing stop, signal bar included
K_R = 1.5           # target in R
T_FIRST, T_LAST = 9 * 60 + 35, 15 * 60          # signal bars close 09:35 .. 15:00


def _prev_day_ok(ctx):
    """For every 1-minute bar: True when the trading day BEFORE the bar's own trading day closed above its 9-day EMA
    (EMA of the daily closes through that previous day). Trading day = 18:00 -> 17:00."""
    td = ctx.tdate
    days, first = np.unique(td, return_index=True)            # trading days in order, first bar of each
    last = np.r_[first[1:] - 1, ctx.n - 1]                    # last bar of each trading day
    dclose = ctx.C[last]
    e9 = ind.ema(dclose, 9)
    above = dclose > e9                                       # NaN while warming up -> False
    prev = np.r_[False, above[:-1]]                           # day j reads day j-1 only
    return prev[np.searchsorted(days, td)]


def orders(ctx, bar=5):
    b = ctx.bars(bar)
    H, L, C = b.high.to_numpy(), b.low.to_numpy(), b.close.to_numpy()
    tod = (b.index.hour * 60 + b.index.minute).to_numpy()
    i_last = b.i_last.to_numpy()
    dn = ctx.dayn[i_last]                                     # running number of the cash day (-1 = none)
    i_end = ctx.days.i_end.to_numpy()

    sma200 = ind.sma(C, 200)
    _, upper, _, _ = ind.bollinger(C, 20, 2.0)
    cross = ind.crossed_up(C, upper)                          # close[k] > upper[k] and close[k-1] <= upper[k-1]
    day_ok = _prev_day_ok(ctx)[i_last]
    swing_lo = ind.rolling_min(L, SWING)

    in_win = (dn >= 0) & (tod + bar >= T_FIRST) & (tod + bar <= T_LAST)
    sig = in_win & cross & (C > sma200) & day_ok
    out = []
    for k in np.flatnonzero(sig):
        i, e = int(i_last[k]), int(i_end[dn[k]])
        if i >= e or np.isnan(swing_lo[k]):
            continue
        stop = swing_lo[k] - core.TICK
        target = core.tick_round(C[k] + K_R * (C[k] - stop))
        out.append(dict(i=i, side=1, etype="close", stop=float(stop), target=target, exit_i=e, tag="L"))
    return out


def trades(ctx, **p):
    return core.run_orders(ctx, orders(ctx, **p), skip_roll=2)
