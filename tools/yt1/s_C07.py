#!/usr/bin/env python3
"""C07 - MACD + Parabolic SAR + 200 EMA (TradeSmart re-test), family C common frame.

Spec: Long: MACD histogram crosses above zero, close > EMA200, SAR (0.02, 0.02, 0.2) below the bar. Stop: the SAR
value. Target 1.5R; also exits at the close of a bar giving the opposite signal. Neighbours: 1R and 2R.
Short mirrored: histogram crosses below zero, close < EMA200, SAR above the bar, stop the SAR value.

Common frame (YT1_SPEC.md, family C): `bar`-minute MNQ bars (5 in all three variants), indicators on the continuous
24-hour series, signals on bars closing 09:35 -> 15:00, entry at the signal bar's close, one position at a time, any
number a day, the cash day of a roll and the day after it skipped (run_orders skip_roll=2).

Readings added to the spec text (fixed before any run):
  * MACD (12, 26, 9), the default the sourcing note gives; "histogram crosses above zero" is ind.crossed_up on
    completed bars: hist[k] > 0 and hist[k-1] <= 0.
  * "SAR below the bar" = the SAR value of bar k is below the bar's low (sar[k] < low[k]); "above the bar" =
    sar[k] > high[k]. ind.psar's direction flag is not used: on a bar where it turns, ind.psar leaves the dot at the
    old extreme, which can lie inside the bar (see notes/C07.md), and such a dot is not "below the bar".
  * "The SAR value" = sar[k] of the signal bar, fixed for the life of the trade, put on the first tick at or beyond
    it (down for a long, up for a short: touched by exactly the same bars as the unrounded value).
  * Target = close +/- k_r x |close - stop|, rounded to the nearest tick.
  * "A bar giving the opposite signal" = a bar on which the mirrored entry signal, exactly as defined above
    (window 09:35 -> 15:00 included), fires. The trade is closed at that bar's close (simulate's exit_sig). The
    opposite signal that closes a trade is not itself taken: run_orders skips an order signalled at or before the
    previous trade's exit bar, so there is no stop-and-reverse.
  * "bars closing 09:35 -> 15:00": the bar's clock close (open + bar minutes) lies in [09:35, 15:00].
"""
import numpy as np
import core
import ind

ID = "C07"
NAME = "MACD + Parabolic SAR + 200 EMA"
VARIANTS = {
    "base": dict(bar=5, k_r=1.5),
    "nb1": dict(bar=5, k_r=1.0),
    "nb2": dict(bar=5, k_r=2.0),
}


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
    b, i_last, i_end, ok = _frame(ctx, bar)
    h, l, c = b.high.to_numpy(float), b.low.to_numpy(float), b.close.to_numpy(float)
    e200 = ind.ema(c, 200)
    _, _, hist = ind.macd(c, 12, 26, 9)
    sar, sdir = ind.psar(h, l, 0.02, 0.02, 0.2)
    x_up, x_dn = ind.crossed_up(hist, 0.0), ind.crossed_dn(hist, 0.0)
    long_ = ok & x_up & (c > e200) & (sar < l)
    short_ = ok & x_dn & (c < e200) & (sar > h)
    return dict(b=b, h=h, l=l, c=c, i_last=i_last, i_end=i_end, long=long_, short=short_, sar=sar, sdir=sdir,
                hist=hist, e200=e200, ok=ok, x_up=x_up, x_dn=x_dn)


def _stop(sar_k, side):
    return core.tick_round(float(sar_k), "down" if side > 0 else "up")


def orders(ctx, bar=5, k_r=1.5):
    g = signals(ctx, bar)
    c, i_last, i_end, sar = g["c"], g["i_last"], g["i_end"], g["sar"]
    # the opposite signal, on the 1-minute clock: True at the 1-minute bar that closes a signal bar of that side
    sig_long_1m = np.zeros(ctx.n, bool)
    sig_short_1m = np.zeros(ctx.n, bool)
    sig_long_1m[i_last[g["long"]]] = True
    sig_short_1m[i_last[g["short"]]] = True
    out = []
    for side, flag, opposite in ((1, g["long"], sig_short_1m), (-1, g["short"], sig_long_1m)):
        for k in np.flatnonzero(flag):
            entry, stop = float(c[k]), _stop(sar[k], side)
            target = core.tick_round(entry + side * k_r * abs(entry - stop))
            out.append(dict(i=int(i_last[k]), side=side, etype="close", stop=stop, target=target,
                            exit_i=int(i_end[k]), exit_sig=opposite, tag="L" if side > 0 else "S"))
    return out


def diag(ctx, bar=5, k_r=1.5):
    """Signal counts; stops not on the losing side of the entry (the harness drops those; impossible here because the
    SAR must be outside the bar); and what the 'SAR below the bar' reading removes relative to ind.psar's direction
    flag (signals with the flag on the trade's side but the dot not beyond the bar, and how many of those dots are
    on the wrong side of the close, i.e. would have been dropped by the harness anyway)."""
    g = signals(ctx, bar)
    c, h, l, sar, sdir = g["c"], g["h"], g["l"], g["sar"], g["sdir"]
    bad = 0
    for side, flag in ((1, g["long"]), (-1, g["short"])):
        for k in np.flatnonzero(flag):
            s = _stop(sar[k], side)
            bad += not ((s < c[k]) if side > 0 else (s > c[k]))
    e200 = g["e200"]
    fl = g["ok"] & g["x_up"] & (c > e200) & (sdir == 1) & ~(sar < l)
    fs = g["ok"] & g["x_dn"] & (c < e200) & (sdir == -1) & ~(sar > h)
    return dict(long=int(g["long"].sum()), short=int(g["short"].sum()), bad_stop=int(bad),
                flag_ok_but_dot_not_beyond_bar=int(fl.sum() + fs.sum()),
                of_which_dot_wrong_side_of_close=int((fl & (sar >= c)).sum() + (fs & (sar <= c)).sum()))


def trades(ctx, **p):
    return core.run_orders(ctx, orders(ctx, **p), skip_roll=2)
