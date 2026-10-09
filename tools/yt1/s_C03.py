#!/usr/bin/env python3
"""C03 - Triple Supertrend + Stochastic RSI + 200 EMA (TradeSmart re-test), family C common frame.

Spec: Supertrend (12, 3), (11, 2), (10, 1); Stochastic RSI (3, 3, 14, 14). Long: close > EMA200, %K crosses above %D
with the previous %K below 20, at least two Supertrends up. Stop: the second Supertrend line below the close,
counting from the close. 1.5R. Short mirrored (previous %K above 80, at least two Supertrends down, the second
Supertrend line above the close).

Common frame (YT1_SPEC.md, family C): `bar`-minute MNQ bars, indicators on the continuous 24-hour series, signals on
bars closing 09:35 -> 15:00, entry at the signal bar's close, one position at a time, any number a day, the cash day
of a roll and the day after it skipped (run_orders skip_roll=2). Neighbours: 3-minute and 15-minute bars.

Readings added to the spec text (fixed before any run):
  * "%K crosses above %D" is ind.crossed_up on completed bars (K[k] > D[k], K[k-1] <= D[k-1]); "the previous %K"
    is K[k-1]. Everything else (EMA200, Supertrend directions and lines) is read on the signal bar k.
  * The stop: the three Supertrend lines of bar k that are strictly below close[k] are ordered from the close
    downwards and the second is taken (so with three lines below it is the middle one, with two the lower one). The
    direction flag is not used for the stop. Fewer than two lines below the close = no stop exists = no order
    (counted by diag(); TradingView's Supertrend, which ind.supertrend reproduces exactly, can on a very large bar
    report "up" with its line above the close when the factor is 1).
  * A line value is not on the tick grid: the stop is the first tick at or beyond the line (rounded down for a long,
    up for a short), which is touched by exactly the same bars as the line itself.
  * Target = close +/- 1.5 x |close - stop|, rounded to the nearest tick.
  * "bars closing 09:35 -> 15:00": the bar's clock close (open + bar minutes) lies in [09:35, 15:00].
"""
import numpy as np
import core
import ind

ID = "C03"
NAME = "Triple Supertrend + Stochastic RSI + 200 EMA"
VARIANTS = {
    "base": dict(bar=5),
    "nb1": dict(bar=3),
    "nb2": dict(bar=15),
}
K_R = 1.5
ST = ((12, 3.0), (11, 2.0), (10, 1.0))


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


def _second_line(lines_k, close_k, side):
    """The second Supertrend line beyond the close on the stop side, counting from the close; None if there is none."""
    if side > 0:
        x = sorted((v for v in lines_k if v < close_k), reverse=True)
    else:
        x = sorted(v for v in lines_k if v > close_k)
    if len(x) < 2:
        return None
    return core.tick_round(float(x[1]), "down" if side > 0 else "up")


def signals(ctx, bar=5):
    b, i_last, i_end, ok = _frame(ctx, bar)
    h, l, c = b.high.to_numpy(float), b.low.to_numpy(float), b.close.to_numpy(float)
    e200 = ind.ema(c, 200)
    st = [ind.supertrend(h, l, c, a, f) for a, f in ST]
    lines = np.column_stack([x[0] for x in st])                    # (n, 3)
    dirs = np.column_stack([x[1] for x in st])
    n_up, n_dn = (dirs == 1).sum(axis=1), (dirs == -1).sum(axis=1)
    K, D = ind.stoch_rsi(c, 3, 3, 14, 14)
    Kp = np.r_[np.nan, K[:-1]]
    long_ = ok & ind.crossed_up(K, D) & (Kp < 20) & (n_up >= 2) & (c > e200)
    short_ = ok & ind.crossed_dn(K, D) & (Kp > 80) & (n_dn >= 2) & (c < e200)
    return dict(b=b, c=c, i_last=i_last, i_end=i_end, long=long_, short=short_, lines=lines, dirs=dirs, K=K, D=D,
                e200=e200)


def orders(ctx, bar=5):
    g = signals(ctx, bar)
    c, i_last, i_end, lines = g["c"], g["i_last"], g["i_end"], g["lines"]
    out = []
    for side, flag in ((1, g["long"]), (-1, g["short"])):
        for k in np.flatnonzero(flag):
            entry = float(c[k])
            stop = _second_line(lines[k], entry, side)
            if stop is None:
                continue
            target = core.tick_round(entry + side * K_R * abs(entry - stop))
            out.append(dict(i=int(i_last[k]), side=side, etype="close", stop=stop, target=target,
                            exit_i=int(i_end[k]), tag="L" if side > 0 else "S"))
    return out


def diag(ctx, bar=5):
    """Signal counts; signals with no second line on the stop side (no order); orders whose stop is not on the losing
    side of the entry (the harness drops those; impossible here by construction, counted anyway)."""
    g = signals(ctx, bar)
    c, lines = g["c"], g["lines"]
    no_stop = bad = 0
    for side, flag in ((1, g["long"]), (-1, g["short"])):
        for k in np.flatnonzero(flag):
            s = _second_line(lines[k], float(c[k]), side)
            if s is None:
                no_stop += 1
            elif not ((s < c[k]) if side > 0 else (s > c[k])):
                bad += 1
    return dict(long=int(g["long"].sum()), short=int(g["short"].sum()), no_stop=no_stop, bad_stop=bad)


def trades(ctx, **p):
    return core.run_orders(ctx, orders(ctx, **p), skip_roll=2)
