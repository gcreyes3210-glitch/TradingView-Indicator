#!/usr/bin/env python3
"""C12 - TTM Squeeze fire.

Spec: 15-minute MNQ bars (neighbours 10 and 30), indicators on the continuous 24-hour series.
Squeeze on = Bollinger (20, 2) inside Keltner (EMA20 +/- 1.5 x ATR20): upper BB < upper KC and lower BB > lower KC.
Fire      = the first squeeze-off bar after a run of >= 6 consecutive squeeze-on bars.
Momentum  = 20-bar linear regression (end value) of close - average(midpoint of the 20-bar high / low, SMA20).
Long:  at the fire bar momentum > 0 and rising (above the previous bar's), close > SMA20.
Short: momentum < 0 and falling, close < SMA20.
Entry at the fire bar's close; signal bars closing 09:45 -> 15:00.
Stop: 1 tick beyond the lowest low (highest high) of the run of squeeze-on bars that just ended.
Exit: the close of the first later bar whose momentum falls (rises for a short), or the flat bar. No target.
One position at a time, any number a day; roll days and the day after are skipped.
"""
import numpy as np
import core
import ind

ID = "C12"
NAME = "TTM Squeeze fire (BB 20/2 inside KC 20/1.5xATR20, >= 6 on bars)"
VARIANTS = {
    "base": dict(tf=15),
    "nb1": dict(tf=10),
    "nb2": dict(tf=30),
}

WIN_LO, WIN_HI = 9 * 60 + 45, 15 * 60          # signal bars CLOSE in [09:45, 15:00]
LEN, MIN_ON = 20, 6


def squeeze(h, l, c):
    """Returns (on, known, momentum, sma20) on one bar series; every value uses bars up to its own only."""
    basis, bb_up, bb_lo, _ = ind.bollinger(c, LEN, 2.0)
    _, kc_up, kc_lo = ind.keltner(h, l, c, n=LEN, mult=1.5, atr_len=LEN)
    known = np.isfinite(bb_up) & np.isfinite(bb_lo) & np.isfinite(kc_up) & np.isfinite(kc_lo)
    with np.errstate(invalid="ignore"):
        on = known & (bb_up < kc_up) & (bb_lo > kc_lo)
    mid = (ind.rolling_max(h, LEN) + ind.rolling_min(l, LEN)) / 2
    mom = ind.linreg(c - (mid + basis) / 2, LEN)
    return on, known, mom, basis


def orders(ctx, tf=15):
    b = ctx.bars(tf)
    h, l, c = (b[k].to_numpy(float) for k in ("high", "low", "close"))
    i_last = b.i_last.to_numpy()
    tod = (b.index.hour * 60 + b.index.minute).to_numpy()
    close_t = tod + tf
    in_win = (close_t >= WIN_LO) & (close_t <= WIN_HI)
    on, known, mom, sma20 = squeeze(h, l, c)
    nb = len(c)

    # run[k] = number of consecutive squeeze-on bars ending at bar k (0 when bar k is off)
    run = np.zeros(nb, int)
    for k in range(nb):
        if on[k]:
            run[k] = (run[k - 1] if k else 0) + 1
    prev_run = np.r_[0, run[:-1]]
    fire = known & ~on & (prev_run >= MIN_ON)

    dmom = np.r_[np.nan, np.diff(mom)]              # momentum minus the previous bar's
    with np.errstate(invalid="ignore"):
        rising, falling = dmom > 0, dmom < 0
        long_ok = fire & in_win & (mom > 0) & rising & (c > sma20)
        short_ok = fire & in_win & (mom < 0) & falling & (c < sma20)

    # exit arrays on the 1-minute index: a completed bar's momentum turn is known at the close of its last minute
    exit_long, exit_short = np.zeros(ctx.n, bool), np.zeros(ctx.n, bool)
    exit_long[i_last[falling]] = True
    exit_short[i_last[rising]] = True

    i_end = ctx.days.i_end.to_numpy()
    T = core.TICK
    out = []
    for k in np.flatnonzero(long_ok | short_ok):
        i = int(i_last[k])
        dn = ctx.dayn[i]
        if dn < 0:
            continue
        n_on = int(prev_run[k])                     # the run that just ended: bars k - n_on .. k - 1
        if long_ok[k]:
            stop = l[k - n_on:k].min() - T
            out.append(dict(i=i, side=1, etype="close", stop=float(stop), exit_sig=exit_long,
                            exit_i=int(i_end[dn]), tag=f"L run{n_on}"))
        else:
            stop = h[k - n_on:k].max() + T
            out.append(dict(i=i, side=-1, etype="close", stop=float(stop), exit_sig=exit_short,
                            exit_i=int(i_end[dn]), tag=f"S run{n_on}"))
    return out


def trades(ctx, **p):
    return core.run_orders(ctx, orders(ctx, **p), one_at_a_time=True, skip_roll=2)
