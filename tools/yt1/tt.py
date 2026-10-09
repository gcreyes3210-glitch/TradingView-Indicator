#!/usr/bin/env python3
"""TTrades building blocks for YT4 (definitions fixed in YT4_SPEC.md, Part 2). All causal.

    daily(ctx)          trading-day candles (18:00 -> 17:00 New York), one row per trading date
    bias(ctx)           Series indexed by cash date: +1 bullish, -1 bearish, 0 none, with the kind of close behind it
    cisd(o, h, l, c)    change in the state of delivery on any bar series
    closure2 / closure3 his candle 2 (reversal) and candle 3 closures on any bar series
"""
import numpy as np
import pandas as pd


def daily(ctx):
    """Trading-day candles: open / high / low / close, n minutes, and roll = the contract differs from the previous
    candle's. A candle with fewer than 690 one-minute bars (half of 23 hours) is dropped."""
    if getattr(ctx, "_tt_daily", None) is not None:
        return ctx._tt_daily
    td = pd.DatetimeIndex(ctx.tdate)
    g = ctx.a.groupby(td)
    D = pd.DataFrame({"open": g.open.first(), "high": g.high.max(), "low": g.low.min(), "close": g.close.last(),
                      "n": g.size(), "iid": g.instrument_id.last(), "iid0": g.instrument_id.first()})
    D = D[D.n >= 690]
    D["roll"] = (D.iid0 != D.iid) | (D.iid0 != D.iid.shift(1))
    ctx._tt_daily = D
    return D


def bias(ctx):
    """Daily bias for each cash day D, from the last two completed trading-day candles before it (1 = the one that
    closed at 17:00 the evening before, 2 = the one before that):
        bullish (+1): close1 > high2 ('cont'), or low1 < low2 and close1 > low2 and high1 <= high2 ('fail')
        bearish (-1): close1 < low2 ('cont'), or high1 > high2 and close1 < high2 and low1 >= low2 ('fail')
        otherwise 0. No bias if either candle is missing or a contract roll lies in or between them.
    Returns a DataFrame indexed by cash date: bias, kind, h1, l1, c1, o1, h2, l2 (candle 1 / 2 levels)."""
    if getattr(ctx, "_tt_bias", None) is not None:
        return ctx._tt_bias
    D = daily(ctx)
    idx = D.index
    rows = []
    for d in ctx.days.index:
        p = idx.searchsorted(d, "left")          # candles strictly before trading date d
        if p < 2:
            rows.append((0, "", *[np.nan] * 6)); continue
        c1, c2 = D.iloc[p - 1], D.iloc[p - 2]
        if c1.roll or c2.roll or (p < len(idx) and idx[p] == d and D.iloc[p].roll):
            rows.append((0, "roll", c1.high, c1.low, c1.close, c1.open, c2.high, c2.low)); continue
        b, kind = 0, ""
        if c1.close > c2.high:
            b, kind = 1, "cont"
        elif c1.close < c2.low:
            b, kind = -1, "cont"
        elif c1.low < c2.low and c1.close > c2.low and c1.high <= c2.high:
            b, kind = 1, "fail"
        elif c1.high > c2.high and c1.close < c2.high and c1.low >= c2.low:
            b, kind = -1, "fail"
        rows.append((b, kind, c1.high, c1.low, c1.close, c1.open, c2.high, c2.low))
    out = pd.DataFrame(rows, index=ctx.days.index, columns=["bias", "kind", "h1", "l1", "c1", "o1", "h2", "l2"])
    ctx._tt_bias = out
    return out


def cisd(o, h, l, c):
    """Change in the state of delivery. Bullish at bar k: the close of bar k is above the opening price of the first
    candle of the latest run of consecutive down-close candles (close < open), and it is the first close to do so
    since that run. A candle that does not close down ends a run; a later down-close candle starts a new run, which
    replaces the old reference. Bearish is the mirror on up-close candles.
    Returns (bull, bear, prot_low, prot_high): prot_low[k] = the lowest low from the first candle of that run through
    bar k (the protected low); prot_high mirrors. NaN where there is no signal."""
    n = len(o)
    bull, bear = np.zeros(n, bool), np.zeros(n, bool)
    plo, phi = np.full(n, np.nan), np.full(n, np.nan)
    d_open = d_low = u_open = u_high = np.nan
    in_d = in_u = d_pend = u_pend = False
    for k in range(n):
        down, up = c[k] < o[k], c[k] > o[k]
        if down:
            if not in_d:
                d_open, d_low, in_d, d_pend = o[k], l[k], True, True
            else:
                d_low = min(d_low, l[k])
        else:
            in_d = False
            if d_pend:
                d_low = min(d_low, l[k])
                if c[k] > d_open:
                    bull[k], plo[k], d_pend = True, d_low, False
        if up:
            if not in_u:
                u_open, u_high, in_u, u_pend = o[k], h[k], True, True
            else:
                u_high = max(u_high, h[k])
        else:
            in_u = False
            if u_pend:
                u_high = max(u_high, h[k])
                if c[k] < u_open:
                    bear[k], phi[k], u_pend = True, u_high, False
    return bull, bear, plo, phi


def closure2(h, l, c):
    """Candle 2 (reversal) closure. Bullish at bar k: low[k] < low[k-1] and close[k] > low[k-1]; bearish mirror."""
    n = len(c)
    bull, bear = np.zeros(n, bool), np.zeros(n, bool)
    bull[1:] = (l[1:] < l[:-1]) & (c[1:] > l[:-1])
    bear[1:] = (h[1:] > h[:-1]) & (c[1:] < h[:-1])
    return bull, bear


def closure3(o, h, l, c):
    """Candle 3 closure. Bullish at bar k: bar k-1 is a swing low so far (low[k-1] < low[k-2] and low[k] >= low[k-1])
    and close[k] > max(open, close) of bar k-1; bearish mirror."""
    n = len(c)
    bull, bear = np.zeros(n, bool), np.zeros(n, bool)
    top, bot = np.maximum(o, c), np.minimum(o, c)
    bull[2:] = (l[1:-1] < l[:-2]) & (l[2:] >= l[1:-1]) & (c[2:] > top[1:-1])
    bear[2:] = (h[1:-1] > h[:-2]) & (h[2:] <= h[1:-1]) & (c[2:] < bot[1:-1])
    return bull, bear
