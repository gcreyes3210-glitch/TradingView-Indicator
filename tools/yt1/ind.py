#!/usr/bin/env python3
"""Indicators for YT1, written to TradingView's definitions. All are causal: the value at bar k uses bars <= k only.
Inputs are numpy arrays of one bar series (any timeframe); outputs are arrays of the same length (NaN while warming up).
"""
import numpy as np


def sma(x, n):
    x = np.asarray(x, float)
    out = np.full(len(x), np.nan)
    if len(x) >= n:
        c = np.cumsum(np.insert(x, 0, 0.0))
        out[n - 1:] = (c[n:] - c[:-n]) / n
    return out


def ema(x, n):
    """ta.ema: alpha = 2 / (n + 1), seeded with the SMA of the first n values."""
    x = np.asarray(x, float)
    out = np.full(len(x), np.nan)
    if len(x) < n:
        return out
    a = 2.0 / (n + 1)
    out[n - 1] = x[:n].mean()
    for i in range(n, len(x)):
        out[i] = a * x[i] + (1 - a) * out[i - 1]
    return out


def ema_nan(x, n):
    """EMA of a series that starts with NaNs (e.g. an EMA of an indicator)."""
    x = np.asarray(x, float)
    out = np.full(len(x), np.nan)
    ok = np.flatnonzero(~np.isnan(x))
    if len(ok) >= n:
        s = ok[0]
        out[s:] = ema(x[s:], n)
    return out


def rma(x, n):
    """Wilder's moving average (ta.rma): alpha = 1 / n, seeded with the SMA of the first n values."""
    x = np.asarray(x, float)
    out = np.full(len(x), np.nan)
    ok = np.flatnonzero(~np.isnan(x))
    if len(ok) < n:
        return out
    s = ok[0]
    out[s + n - 1] = x[s:s + n].mean()
    for i in range(s + n, len(x)):
        out[i] = (out[i - 1] * (n - 1) + x[i]) / n
    return out


def wma(x, n):
    x = np.asarray(x, float)
    out = np.full(len(x), np.nan)
    w = np.arange(1, n + 1, dtype=float)
    if len(x) >= n:
        out[n - 1:] = np.convolve(x, w[::-1], mode="valid") / w.sum()
    return out


def hma(x, n):
    return wma_nan(2 * wma(x, n // 2) - wma(x, n), int(round(np.sqrt(n))))


def wma_nan(x, n):
    x = np.asarray(x, float)
    out = np.full(len(x), np.nan)
    ok = np.flatnonzero(~np.isnan(x))
    if len(ok) >= n:
        s = ok[0]
        out[s:] = wma(x[s:], n)
    return out


def true_range(h, l, c):
    pc = np.r_[np.nan, c[:-1]]
    tr = np.nanmax(np.c_[h - l, np.abs(h - pc), np.abs(l - pc)], axis=1)
    tr[0] = h[0] - l[0]
    return tr


def atr(h, l, c, n=14):
    """ta.atr: Wilder average of the true range."""
    return rma(true_range(h, l, c), n)


def rolling_max(x, n):
    """Highest value of the last n bars including the current one."""
    import pandas as pd
    return pd.Series(x).rolling(n).max().to_numpy()


def rolling_min(x, n):
    import pandas as pd
    return pd.Series(x).rolling(n).min().to_numpy()


def stdev(x, n):
    """ta.stdev (population standard deviation over n bars)."""
    import pandas as pd
    return pd.Series(x).rolling(n).std(ddof=0).to_numpy()


def rsi(c, n=14):
    c = np.asarray(c, float)
    d = np.diff(c, prepend=np.nan)
    up, dn = np.where(d > 0, d, 0.0), np.where(d < 0, -d, 0.0)
    up[0] = dn[0] = np.nan
    au, ad = rma(up, n), rma(dn, n)
    with np.errstate(divide="ignore", invalid="ignore"):
        rs = au / ad
        out = 100 - 100 / (1 + rs)
    out[ad == 0] = 100.0
    out[np.isnan(au)] = np.nan
    return out


def macd(c, fast=12, slow=26, sig=9):
    """Returns (macd line, signal line, histogram)."""
    m = ema(c, fast) - ema(c, slow)
    s = ema_nan(m, sig)
    return m, s, m - s


def stoch(h, l, c, k=14, smooth_k=3, d=3):
    """Returns (%K smoothed, %D). TradingView's Stochastic(14, 3, 3)."""
    hh, ll = rolling_max(h, k), rolling_min(l, k)
    with np.errstate(divide="ignore", invalid="ignore"):
        raw = 100 * (c - ll) / (hh - ll)
    raw[(hh - ll) == 0] = 50.0
    kk = _sma_nan(raw, smooth_k)
    return kk, _sma_nan(kk, d)


def _sma_nan(x, n):
    x = np.asarray(x, float)
    out = np.full(len(x), np.nan)
    ok = np.flatnonzero(~np.isnan(x))
    if len(ok) >= n:
        s = ok[0]
        out[s:] = sma(x[s:], n)
    return out


def stoch_rsi(c, smooth_k=3, smooth_d=3, rsi_len=14, stoch_len=14):
    """TradingView's Stochastic RSI (3, 3, 14, 14). Returns (K, D)."""
    r = rsi(c, rsi_len)
    hh, ll = rolling_max(r, stoch_len), rolling_min(r, stoch_len)
    with np.errstate(divide="ignore", invalid="ignore"):
        raw = 100 * (r - ll) / (hh - ll)
    raw[(hh - ll) == 0] = 50.0
    k = _sma_nan(raw, smooth_k)
    return k, _sma_nan(k, smooth_d)


def bollinger(c, n=20, mult=2.0):
    """Returns (basis, upper, lower, %B)."""
    b, sd = sma(c, n), stdev(c, n)
    up, lo = b + mult * sd, b - mult * sd
    with np.errstate(divide="ignore", invalid="ignore"):
        pb = (c - lo) / (up - lo)
    return b, up, lo, pb


def keltner(h, l, c, n=20, mult=1.5, atr_len=None):
    """EMA(n) basis +/- mult x ATR(atr_len or n). Returns (basis, upper, lower)."""
    b = ema(c, n)
    r = atr(h, l, c, atr_len or n)
    return b, b + mult * r, b - mult * r


def donchian(h, l, n=20):
    """Returns (upper, lower) = highest high / lowest low of the last n bars including the current one."""
    return rolling_max(h, n), rolling_min(l, n)


def supertrend(h, l, c, atr_len=10, factor=3.0):
    """ta.supertrend. Returns (line, direction) with direction +1 = uptrend (line below price), -1 = downtrend."""
    n = len(c)
    a = atr(h, l, c, atr_len)
    hl2 = (h + l) / 2
    ub, lb = hl2 + factor * a, hl2 - factor * a
    line, dr = np.full(n, np.nan), np.zeros(n, int)
    fub, flb = np.full(n, np.nan), np.full(n, np.nan)
    for i in range(n):
        if np.isnan(a[i]):
            continue
        if np.isnan(fub[i - 1]) if i else True:
            fub[i], flb[i], dr[i] = ub[i], lb[i], -1
        else:
            flb[i] = lb[i] if (lb[i] > flb[i - 1] or c[i - 1] < flb[i - 1]) else flb[i - 1]
            fub[i] = ub[i] if (ub[i] < fub[i - 1] or c[i - 1] > fub[i - 1]) else fub[i - 1]
            if dr[i - 1] == -1:
                dr[i] = 1 if c[i] > fub[i] else -1
            else:
                dr[i] = -1 if c[i] < flb[i] else 1
        line[i] = flb[i] if dr[i] == 1 else fub[i]
    return line, dr


def psar(h, l, start=0.02, inc=0.02, mx=0.2, c=None):
    """ta.sar, transcribed from TradingView's reference implementation (pine_sar). Returns (sar, direction) with
    direction +1 = dots below price. Pass the closes as c for TradingView's first-bar rule (close > previous close
    starts below); without them the first direction is taken from the highs.
    (Corrected 2026-10-09 after coder C07 showed the first version put the dot inside the bar on turn bars: it
    reversed to the old extreme point instead of max(high, extreme) / min(low, extreme) and clamped before testing
    for the reversal.)"""
    n = len(h)
    sar, dr = np.full(n, np.nan), np.zeros(n, int)
    if n < 2:
        return sar, dr
    below = (c[1] > c[0]) if c is not None else (h[1] >= h[0])
    if below:
        mm, res = h[1], l[0]
    else:
        mm, res = l[1], h[0]
    acc = start
    for i in range(1, n):
        first = i == 1
        res = res + acc * (mm - res)
        if below:
            if res > l[i]:
                first, below = True, False
                res = max(h[i], mm)
                mm, acc = l[i], start
        else:
            if res < h[i]:
                first, below = True, True
                res = min(l[i], mm)
                mm, acc = h[i], start
        if not first:
            if below:
                if h[i] > mm:
                    mm, acc = h[i], min(acc + inc, mx)
            else:
                if l[i] < mm:
                    mm, acc = l[i], min(acc + inc, mx)
        if below:
            res = min(res, l[i - 1])
            if i > 1:
                res = min(res, l[i - 2])
        else:
            res = max(res, h[i - 1])
            if i > 1:
                res = max(res, h[i - 2])
        sar[i], dr[i] = res, 1 if below else -1
    return sar, dr


def dmi(h, l, c, n=14, adx_len=14):
    """Returns (+DI, -DI, ADX)."""
    up, dn = np.diff(h, prepend=np.nan), -np.diff(l, prepend=np.nan)
    pdm = np.where((up > dn) & (up > 0), up, 0.0)
    mdm = np.where((dn > up) & (dn > 0), dn, 0.0)
    pdm[0] = mdm[0] = np.nan
    tr = rma(true_range(h, l, c), n)
    with np.errstate(divide="ignore", invalid="ignore"):
        pdi, mdi = 100 * rma(pdm, n) / tr, 100 * rma(mdm, n) / tr
        dx = 100 * np.abs(pdi - mdi) / (pdi + mdi)
    dx[(pdi + mdi) == 0] = 0.0
    return pdi, mdi, rma(dx, adx_len)


def linreg(x, n):
    """ta.linreg(x, n, 0): the end value of the least-squares line over the last n bars."""
    import pandas as pd
    x = np.asarray(x, float)
    t = np.arange(n, dtype=float)
    tm, tv = t.mean(), ((t - t.mean()) ** 2).sum()
    s = pd.Series(x)
    m = s.rolling(n).mean().to_numpy()
    cov = s.rolling(n).apply(lambda w: ((t - tm) * (w - w.mean())).sum(), raw=True).to_numpy()
    slope = cov / tv
    return m + slope * (n - 1 - tm)


def session_vwap(h, l, c, v, new_session):
    """VWAP of hlc3 that restarts where new_session[k] is True. Returns (vwap, sd) with sd the volume-weighted
    standard deviation of hlc3 around the VWAP (TradingView's VWAP bands)."""
    tp = (h + l + c) / 3
    n = len(c)
    vw, sd = np.full(n, np.nan), np.full(n, np.nan)
    sv = spv = sp2 = 0.0
    started = False
    for i in range(n):
        if new_session[i]:
            sv = spv = sp2 = 0.0
            started = True
        if not started:
            continue
        sv += v[i]; spv += tp[i] * v[i]; sp2 += tp[i] * tp[i] * v[i]
        if sv > 0:
            m = spv / sv
            vw[i] = m
            sd[i] = np.sqrt(max(sp2 / sv - m * m, 0.0))
    return vw, sd


def crossed_up(x, y):
    """x crossed above y on this bar (x[k] > y[k] and x[k-1] <= y[k-1]). y may be a number."""
    x = np.asarray(x, float)
    y = np.full(len(x), float(y)) if np.isscalar(y) else np.asarray(y, float)
    out = np.zeros(len(x), bool)
    out[1:] = (x[1:] > y[1:]) & (x[:-1] <= y[:-1])
    return out


def crossed_dn(x, y):
    x = np.asarray(x, float)
    y = np.full(len(x), float(y)) if np.isscalar(y) else np.asarray(y, float)
    out = np.zeros(len(x), bool)
    out[1:] = (x[1:] < y[1:]) & (x[:-1] >= y[:-1])
    return out


def fvg_bull(h, l):
    """Bullish fair value gap completed at bar k: low[k] > high[k-2]. Returns bool array; the gap is
    (high[k-2], low[k]) and its three candles are k-2, k-1, k."""
    out = np.zeros(len(h), bool)
    out[2:] = l[2:] > h[:-2]
    return out


def fvg_bear(h, l):
    """Bearish fair value gap completed at bar k: high[k] < low[k-2]. The gap is (high[k], low[k-2])."""
    out = np.zeros(len(h), bool)
    out[2:] = h[2:] < l[:-2]
    return out


def fractal_high(h, left=1, right=1):
    """Swing high confirmed at bar k for the pivot at k - right: returns an array with the pivot's high at the bar
    where it becomes known (NaN elsewhere). Strictly higher than `left` bars before and `right` bars after."""
    n = len(h)
    out = np.full(n, np.nan)
    for k in range(left + right, n):
        p = k - right
        if h[p] > h[p - left:p].max() and h[p] > h[p + 1:k + 1].max():
            out[k] = h[p]
    return out


def fractal_low(l, left=1, right=1):
    n = len(l)
    out = np.full(n, np.nan)
    for k in range(left + right, n):
        p = k - right
        if l[p] < l[p - left:p].min() and l[p] < l[p + 1:k + 1].min():
            out[k] = l[p]
    return out
