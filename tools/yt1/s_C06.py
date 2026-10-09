#!/usr/bin/env python3
"""C06 - EMA 8 / 14 / 50 + Stochastic RSI + ATR bracket (Trade Pro), family C common frame.

Spec: Long: EMA8 > EMA14 > EMA50 and %K crosses above %D. Stop 3 x ATR(14), target 2 x ATR(14) from entry.
Short mirrored: EMA8 < EMA14 < EMA50 and %K crosses below %D.

Common frame (YT1_SPEC.md, family C): `bar`-minute MNQ bars, indicators on the continuous 24-hour series, signals on
bars closing 09:35 -> 15:00, entry at the signal bar's close, one position at a time, any number a day, the cash day
of a roll and the day after it skipped (run_orders skip_roll=2). Neighbours: 3-minute and 15-minute bars.

Readings added to the spec text (fixed before any run):
  * Stochastic RSI (3, 3, 14, 14), the settings the spec gives for C03 and the sourcing note gives for this video.
    No zone condition on the cross (the spec has none).
  * "%K crosses above %D" is ind.crossed_up on completed bars (K[k] > D[k], K[k-1] <= D[k-1]); the EMA stack and
    ATR(14) are read on the signal bar k.
  * "From entry" = from the signal bar's close (the entry price before slippage, as in the R-target rule).
    Stop = close -/+ 3 x ATR(14)[k] put on the first tick at or beyond that level (down for a long, up for a short:
    touched by exactly the same bars as the unrounded level); target = close +/- 2 x ATR(14)[k] rounded to the
    nearest tick.
  * "bars closing 09:35 -> 15:00": the bar's clock close (open + bar minutes) lies in [09:35, 15:00].
"""
import numpy as np
import core
import ind

ID = "C06"
NAME = "EMA 8 / 14 / 50 + Stochastic RSI + ATR bracket"
VARIANTS = {
    "base": dict(bar=5),
    "nb1": dict(bar=3),
    "nb2": dict(bar=15),
}
STOP_ATR, TARGET_ATR = 3.0, 2.0


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
    e8, e14, e50 = ind.ema(c, 8), ind.ema(c, 14), ind.ema(c, 50)
    K, D = ind.stoch_rsi(c, 3, 3, 14, 14)
    a14 = ind.atr(h, l, c, 14)
    have = ~np.isnan(a14)
    long_ = ok & have & (e8 > e14) & (e14 > e50) & ind.crossed_up(K, D)
    short_ = ok & have & (e8 < e14) & (e14 < e50) & ind.crossed_dn(K, D)
    return dict(b=b, c=c, i_last=i_last, i_end=i_end, long=long_, short=short_, atr=a14, K=K, D=D, e8=e8, e14=e14,
                e50=e50)


def _bracket(close_k, atr_k, side):
    stop = core.tick_round(close_k - side * STOP_ATR * atr_k, "down" if side > 0 else "up")
    target = core.tick_round(close_k + side * TARGET_ATR * atr_k)
    return stop, target


def orders(ctx, bar=5):
    g = signals(ctx, bar)
    c, i_last, i_end, a14 = g["c"], g["i_last"], g["i_end"], g["atr"]
    out = []
    for side, flag in ((1, g["long"]), (-1, g["short"])):
        for k in np.flatnonzero(flag):
            stop, target = _bracket(float(c[k]), float(a14[k]), side)
            out.append(dict(i=int(i_last[k]), side=side, etype="close", stop=stop, target=target,
                            exit_i=int(i_end[k]), tag="L" if side > 0 else "S"))
    return out


def diag(ctx, bar=5):
    """Signal counts and how many carry a stop that is not on the losing side of the entry (the harness drops those)."""
    g = signals(ctx, bar)
    c, a14 = g["c"], g["atr"]
    bad = 0
    for side, flag in ((1, g["long"]), (-1, g["short"])):
        for k in np.flatnonzero(flag):
            s, _ = _bracket(float(c[k]), float(a14[k]), side)
            bad += not ((s < c[k]) if side > 0 else (s > c[k]))
    return dict(long=int(g["long"].sum()), short=int(g["short"].sum()), bad_stop=int(bad))


def trades(ctx, **p):
    return core.run_orders(ctx, orders(ctx, **p), skip_roll=2)
