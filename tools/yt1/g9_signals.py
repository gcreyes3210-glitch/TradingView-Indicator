#!/usr/bin/env python3
"""G9 signals - every CISD signal of the YT6 grid (YT6_SPEC.md, Part 1) with its confluence columns, computed once.

    build(ctx, tfs=(1, 5, 15))   one row per CISD on the 1-, 5- and 15-minute clock-aligned series whose decision bar
                                 (the 1-minute bar that closes the CISD bar) is at 02:00-04:59, 08:30-10:59 or
                                 13:30-14:59 New York (the union of the five windows). Every column is known at the
                                 close of the decision bar.
    order_of(ctx, row, X, N)     the core.simulate keyword arguments of one signal's order under target rule X
                                 (2R / pdx / liq) and entry N (close / retest / pos); the ONE place where an order is
                                 built, used by outcomes() here and by s_G9.orders().
    outcomes(ctx, sig)           adds, per signal, the trade under the house fills for each of the 9 (X, N) pairs
                                 (R, pnl, filled, risk_pts) and the `tradable` flag.
    python3 tools/yt1/g9_signals.py --phase is|full     writes data/studies/yt1/<phase>/G9_signals.parquet

Columns of build() (long written, shorts mirrored; the YT5 columns are computed exactly as g8_signals does):
    tf, i, date, time, side, tod, entry_ref, prot, stop     the frame (i = index of the 1-minute decision bar)
    rt_px                                                   the opening price the CISD closed through (retest limit)
    w_ldn, w_am, w_open, w_sb, w_pm                         W: the decision bar is inside the window
    bias (0/1), kind ('cont' / 'fail' / '')                 B any / cont / fail: tt.bias agrees with the trade
    b_inv                                                   B inv: bias exists, an hour candle completed since 18:00
                                                            closed beyond EQ against it, the trade is against the bias
    e_disc, e_prem                                          E: signal close below / above EQ of cand1
    m_d18, m_mid, m_both                                    M: signal close below the 18:00 open / the 00:00 open /
                                                            the 00:00 open and the 08:30 open
    r_pd, r_sess                                            R raid: protected low below the low level, close back above
    r_pd_brk, r_sess_brk                                    R failure to manipulate: protected low above the high level
    h_h1, h_h4, s_smt                                       H, S as YT5
    x_pdx, q_pdx_075 / _100 / _150                          X pdx: cand1's high, and whether it is at least 0.75 / 1 /
                                                            1.5 R above the signal close
    x_liq_075 / _100 / _150, q_liq_*                        X liq: the nearest of {cand1's high, the session high of
                                                            the window, today's high since 18:00 through the decision
                                                            bar} at least that far above the close (NaN / False: none)
    a_*                                                     audit values behind the columns; bars up to `i` only
`sess` levels: lowest low / highest high from 18:00 through 08:29, for a London-window row from 18:00 through 01:59.
Readings (R) are listed in notes/G9.md. The building blocks come from tt.py and g8_signals.py unchanged.
"""
import argparse, pathlib, sys, time
import numpy as np
import pandas as pd
sys.path.insert(0, str(pathlib.Path(__file__).parent))
import core
import tt
import g8_signals as g8
from g8_signals import _ns, _series, _htf, _es, day_ok, target_of

TFS = (1, 5, 15)
WINDOWS = {"ldn": (120, 299), "am": (510, 659), "open": (570, 659), "sb": (600, 659), "pm": (810, 899)}
XS = ("2R", "pdx", "liq")                       # target rules
NS = ("close", "retest", "pos")                 # entry styles
MD = ((0.75, "075"), (1.0, "100"), (1.5, "150"))    # minimum target distance in R: the grid uses 1R ('100')
K_NB = (2.0, 1.5, 3.0)                          # X 2R: the rule and its two neighbours
MD_NB = ("100", "075", "150")                   # X pdx / liq: the rule and its two neighbours
REST_MIN = 30                                   # retest: the limit rests 30 minutes
T = core.TICK
MIN_NS = g8.MIN_NS
HOUR_NS = g8.HOUR_NS
REF_MIN = g8.REF_MIN


def _nsx(ctx):
    """UTC nanoseconds of every 1-minute bar (cached on the context)."""
    c = ctx.__dict__
    if "_g9_ns" not in c:
        c["_g9_ns"] = _ns(ctx.ts)
    return c["_g9_ns"]


def _run_ext(ctx):
    """(hi, lo): highest high / lowest low of the trading day (from its first bar, 18:00) through each bar."""
    c = ctx.__dict__
    if "_g9_run" not in c:
        for x in (ctx.O, ctx.H, ctx.L, ctx.C):                    # levels are bar prices: the positional limit form
            assert (x * 4 == np.round(x * 4)).all(), "prices off the 0.25 tick grid"      # relies on the tick grid
        td = ctx.tdate
        first = np.r_[0, np.flatnonzero(td[1:] != td[:-1]) + 1]
        grp = np.zeros(ctx.n, np.int64)
        grp[first] = 1
        grp = np.cumsum(grp)
        c["_g9_run"] = (pd.Series(ctx.H).groupby(grp).cummax().to_numpy(),
                        pd.Series(ctx.L).groupby(grp).cummin().to_numpy())
    return c["_g9_run"]


def _hour_close_ext(ctx):
    """Per clock-hour candle k of g8._htf(ctx, 1): (tday, cmin, cmax) = the trading date of the candle, and the lowest
    / highest CLOSE of the hour candles of that trading day (18:00 on) up to and including candle k, over candles
    holding at least half their minutes (+inf / -inf while there is none)."""
    c = ctx.__dict__
    if "_g9_hc" not in c:
        X = _htf(ctx, 1)
        tday = ctx.tdate[X["i_first"]]
        assert (tday == ctx.tdate[X["i_last"]]).all(), "an hour candle straddles 18:00"
        full = X["n"] * 2 >= 60
        grp = pd.Series(tday).ne(pd.Series(tday).shift()).cumsum().to_numpy()
        lo = pd.Series(np.where(full, X["c"], np.inf)).groupby(grp).cummin().to_numpy()
        hi = pd.Series(np.where(full, X["c"], -np.inf)).groupby(grp).cummax().to_numpy()
        c["_g9_hc"] = (tday, lo, hi)
    return c["_g9_hc"]


def _day_levels9(ctx, dates):
    """Per calendar date (unique datetime64[D]): the g8 day levels (bias, kind, cand1 high / low, 18:00 open, 18:00-
    08:29 high / low) plus the 18:00-01:59 high / low, the 00:00 open and the 08:30 open with the index of the bar
    they come from (-1: the date has no bar at or after that minute) and whether that bar is the exact minute."""
    bias, kind, h1, l1, op, sh, sl = g8._day_levels(ctx, dates)
    n = len(dates)
    lh, ll, o00, o830 = (np.full(n, np.nan) for _ in range(4))
    i00, i830 = np.full(n, -1, np.int64), np.full(n, -1, np.int64)
    x00, x830 = np.zeros(n, bool), np.zeros(n, bool)
    for q, d in enumerate(dates):
        ts_d = pd.Timestamp(d)
        i18 = int(np.searchsorted(ctx.tdate, d, "left"))         # first bar of the trading day (18:00 the evening before)
        if i18 < ctx.n and ctx.tdate[i18] == d:
            hi = ctx.span(ts_d, 120, 120)[0]                     # first bar at or after 02:00
            if hi > i18:
                lh[q], ll[q] = ctx.H[i18:hi].max(), ctx.L[i18:hi].min()
        z = ctx.span(ts_d, 0, 0)[0]                              # first bar at or after 00:00 of the cash date
        if z < ctx.n and ctx.cdate[z] == d:
            i00[q], o00[q], x00[q] = z, ctx.O[z], ctx.tod[z] == 0
        z = ctx.span(ts_d, 510, 510)[0]                          # first bar at or after 08:30 of the cash date
        if z < ctx.n and ctx.cdate[z] == d:
            i830[q], o830[q], x830[q] = z, ctx.O[z], ctx.tod[z] == 510
    return dict(bias=bias, kind=kind, h1=h1, l1=l1, op=op, sh=sh, sl=sl, lh=lh, ll=ll, o00=o00, o830=o830,
                i00=i00, i830=i830, x00=x00, x830=x830)


def _build_tf(ctx, tf):
    o, h, l, c, i_first, i_last = _series(ctx, tf)
    bull, bear, plo, phi, sb, ss = tt.cisd_ex(o, h, l, c)
    tod_last = ctx.tod[i_last]
    inwin = np.zeros(len(c), bool)
    for a, z in WINDOWS.values():
        inwin |= (tod_last >= a) & (tod_last <= z)
    kb, ks = np.flatnonzero(bull & inwin), np.flatnonzero(bear & inwin)
    k = np.r_[kb, ks]
    side = np.r_[np.ones(len(kb), np.int8), -np.ones(len(ks), np.int8)]
    prot = np.r_[plo[kb], phi[ks]]
    start = np.r_[sb[kb], ss[ks]]
    order = np.lexsort((-side, i_last[k]))                       # by decision bar; a long before a short on the same bar
    k, side, prot, start = k[order], side[order], prot[order], start[order]
    i = i_last[k].astype(np.int64)
    i0 = i_first[start].astype(np.int64)                         # first 1-minute bar of the run's first candle
    close = c[k]
    rt_px = o[start]                                             # the opening price the CISD closed through
    assert np.array_equal(close, ctx.C[i])
    long = side > 0
    assert (np.where(long, close > rt_px, close < rt_px)).all(), "a CISD that did not close through its opening price"
    tod = ctx.tod[i]
    ldn = (tod >= 120) & (tod <= 299)
    stop = prot - side * T
    risk = np.abs(close - stop)                                  # R = signal close - stop

    # ---- day levels (B, E, M, R, X)
    dates = ctx.cdate[i]
    assert (ctx.tdate[i] == dates).all(), "a decision bar outside 00:00-17:59"
    ud, inv = np.unique(dates, return_inverse=True)
    D = _day_levels9(ctx, ud)
    d_bias = D["bias"][inv]
    agree = (d_bias == side) & (d_bias != 0)
    kind = np.where(agree, D["kind"][inv], "")
    h1, l1 = D["h1"][inv], D["l1"][inv]
    eq = (h1 + l1) / 2.0
    op = D["op"][inv]
    s_hi = np.where(ldn, D["lh"][inv], D["sh"][inv])             # the finished session range of the row's window
    s_lo = np.where(ldn, D["ll"][inv], D["sl"][inv])
    pd_lvl = np.where(long, l1, h1)                              # raid levels: the LOW levels for a long
    ss_lvl = np.where(long, s_lo, s_hi)
    pdx = np.where(long, h1, l1)                                 # break / target levels: the HIGH levels for a long
    ssx = np.where(long, s_hi, s_lo)
    run_hi, run_lo = _run_ext(ctx)
    dayx = np.where(long, run_hi[i], run_lo[i])                  # today's high (low) since 18:00 through the decision bar
    o00 = np.where((D["i00"][inv] >= 0) & (D["i00"][inv] <= i), D["o00"][inv], np.nan)   # known once that bar opened
    o830 = np.where((D["i830"][inv] >= 0) & (D["i830"][inv] <= i), D["o830"][inv], np.nan)
    with np.errstate(invalid="ignore"):
        e_disc = np.where(long, close < eq, close > eq)
        e_prem = np.where(long, close > eq, close < eq)
        m_d18 = np.where(long, close < op, close > op)
        m_mid = np.where(long, close < o00, close > o00)
        m_830 = np.where(long, close < o830, close > o830)
        m_both = m_mid & m_830
        r_pd = np.where(long, (prot < pd_lvl) & (close > pd_lvl), (prot > pd_lvl) & (close < pd_lvl))
        r_sess = np.where(long, (prot < ss_lvl) & (close > ss_lvl), (prot > ss_lvl) & (close < ss_lvl))
        r_pd_brk = np.where(long, prot > pdx, prot < pdx)
        r_sess_brk = np.where(long, prot > ssx, prot < ssx)

    # ---- B inv: a completed hour candle since 18:00 closed beyond EQ against the bias; the trade is against the bias
    X1 = _htf(ctx, 1)
    h_tday, h_cmin, h_cmax = _hour_close_ext(ctx)
    kk = np.searchsorted(X1["i_last"], i, "right") - 1           # last hour candle complete at the decision bar
    okk = (kk >= 0) & (h_tday[np.maximum(kk, 0)] == dates)       # ... and it belongs to this trading day
    kk = np.maximum(kk, 0)
    inv_close = np.where(d_bias > 0, h_cmin[kk], np.where(d_bias < 0, h_cmax[kk], np.nan))
    inv_close = np.where(okk & np.isfinite(inv_close), inv_close, np.nan)
    with np.errstate(invalid="ignore"):
        beyond = np.where(d_bias > 0, inv_close < eq, inv_close > eq)
    b_inv = (d_bias != 0) & (side == -d_bias) & beyond

    # ---- X: pdx and liq levels at the three minimum distances
    xcols = {}
    cand = np.c_[pdx, ssx, dayx]                                 # in the order the spec lists them
    with np.errstate(invalid="ignore"):
        dist = (cand - close[:, None]) * side[:, None]           # distance in the trade's direction
        for mult, tag in MD:
            need = mult * risk
            xcols["q_pdx_" + tag] = dist[:, 0] >= need
            okc = dist >= need[:, None]                          # NaN (a missing level) is False
            dd = np.where(okc, dist, np.inf)
            j = dd.argmin(axis=1)                                # the nearest; ties -> the first listed
            has = okc.any(axis=1)
            xcols["x_liq_" + tag] = np.where(has, cand[np.arange(len(i)), j], np.nan)
            xcols["q_liq_" + tag] = has
            xcols["a_liq_src_" + tag] = np.where(has, j, -1).astype(np.int8)

    # ---- H: the last 1-hour / 4-hour candle whose last 1-minute bar is at or before the decision bar (as g8)
    hh = {}
    for hours in (1, 4):
        X = _htf(ctx, hours)
        q4 = np.searchsorted(X["i_last"], i, "right") - 1
        ok = q4 >= 0
        q4 = np.maximum(q4, 0)
        hh[hours] = ok & np.where(long, X["bull"][q4], X["bear"][q4])

    # ---- S: SMT with ES on the run against the 120 minutes before it (as g8)
    ns = _nsx(ctx)
    ens, EL, EH, cum = _es(ctx)
    t0, t1 = ns[i0], ns[i]
    lo = np.searchsorted(ns, t0 - REF_MIN * MIN_NS, "left")       # MNQ reference bars lo .. i0 - 1
    a0 = np.searchsorted(ens, t0 - REF_MIN * MIN_NS, "left")      # ES reference bars a0 .. a - 1
    a = np.searchsorted(ens, t0, "left")                          # ES run bars a .. b - 1 (through the decision minute)
    b = np.searchsorted(ens, t1, "right")
    m = len(i)
    nq_ref, es_run, es_ref = np.full(m, np.nan), np.full(m, np.nan), np.full(m, np.nan)
    smt = np.zeros(m, bool)
    L, H = ctx.L, ctx.H
    for q in range(m):
        if lo[q] >= i0[q] or a0[q] >= a[q] or a[q] >= b[q]:
            continue                                              # no reference bars (MNQ or ES), or no ES run bars
        if long[q]:
            nq_ref[q] = L[lo[q]:i0[q]].min()
            es_ref[q], es_run[q] = EL[a0[q]:a[q]].min(), EL[a[q]:b[q]].min()
        else:
            nq_ref[q] = H[lo[q]:i0[q]].max()
            es_ref[q], es_run[q] = EH[a0[q]:a[q]].max(), EH[a[q]:b[q]].max()
        if cum[i[q] + 1] - cum[lo[q]] != i[q] + 1 - lo[q]:
            continue                                              # an MNQ minute of either span has no ES bar
        if long[q]:
            smt[q] = (prot[q] < nq_ref[q]) != (es_run[q] < es_ref[q])
        else:
            smt[q] = (prot[q] > nq_ref[q]) != (es_run[q] > es_ref[q])

    df = pd.DataFrame({
        "tf": np.full(m, tf, np.int8), "i": i.astype(np.int32),
        "date": pd.DatetimeIndex(dates.astype("datetime64[ns]")), "time": ctx.ts[i], "side": side,
        "tod": tod.astype(np.int16), "entry_ref": close, "prot": prot, "stop": stop, "rt_px": rt_px,
        "w_ldn": ldn, "w_am": (tod >= 510) & (tod <= 659), "w_open": (tod >= 570) & (tod <= 659),
        "w_sb": (tod >= 600) & (tod <= 659), "w_pm": (tod >= 810) & (tod <= 899),
        "bias": agree.astype(np.int8), "kind": pd.Categorical(kind, categories=["", "cont", "fail"]),
        "b_inv": b_inv.astype(bool),
        "e_disc": e_disc.astype(bool), "e_prem": e_prem.astype(bool),
        "m_d18": m_d18.astype(bool), "m_mid": m_mid.astype(bool), "m_both": m_both.astype(bool),
        "r_pd": r_pd.astype(bool), "r_sess": r_sess.astype(bool),
        "r_pd_brk": r_pd_brk.astype(bool), "r_sess_brk": r_sess_brk.astype(bool),
        "h_h1": hh[1], "h_h4": hh[4], "s_smt": smt,
        "x_pdx": pdx, "q_pdx_075": xcols["q_pdx_075"], "q_pdx_100": xcols["q_pdx_100"], "q_pdx_150": xcols["q_pdx_150"],
        "x_liq_075": xcols["x_liq_075"], "x_liq_100": xcols["x_liq_100"], "x_liq_150": xcols["x_liq_150"],
        "q_liq_075": xcols["q_liq_075"], "q_liq_100": xcols["q_liq_100"], "q_liq_150": xcols["q_liq_150"],
        "a_liq_src_075": xcols["a_liq_src_075"], "a_liq_src_100": xcols["a_liq_src_100"],
        "a_liq_src_150": xcols["a_liq_src_150"],
        "a_dbias": d_bias.astype(np.int8), "a_eq": eq, "a_inv_close": inv_close,
        "a_open18": op, "a_open00": o00, "a_open830": o830,
        "a_x00": D["x00"][inv] & np.isfinite(o00), "a_x830": D["x830"][inv] & np.isfinite(o830),
        "a_pd": pd_lvl, "a_sess": ss_lvl, "a_sessx": ssx, "a_dayx": dayx, "a_run0": i0.astype(np.int32),
        "a_nq_ref": nq_ref, "a_es_run": es_run, "a_es_ref": es_ref})
    return df


def build(ctx, tfs=TFS):
    """All CISD signals of the grid with their confluence columns (see the module docstring). Nothing here reads a
    bar after the decision bar `i`. Rows are ordered by timeframe, then decision bar, then long before short."""
    cache = ctx.__dict__.setdefault("_g9_sig", {})
    parts = []
    for tf in tfs:
        if tf not in cache:
            cache[tf] = _build_tf(ctx, tf)
        parts.append(cache[tf])
    return pd.concat(parts, ignore_index=True) if len(parts) > 1 else parts[0].copy()


# ------------------------------------------------------------------ orders
def exit_of(ctx, date, ldn):
    """The flat bar of a signal: the day's flat bar (days.i_end), or for a London-window signal the last 1-minute bar
    before 08:30 of the cash date (the 08:29 bar). None when there is none (not a cash day / no such bar)."""
    cache = ctx.__dict__.setdefault("_g9_exit", {})
    key = (date, bool(ldn))
    if key not in cache:
        d = pd.Timestamp(date)
        if ldn:
            lo, hi = ctx.span(d, 0, 510)
            cache[key] = hi - 1 if hi > lo else None
        else:
            cache[key] = int(ctx.days.i_end[d]) if d in ctx.days.index else None
    return cache[key]


def pos_bar(ctx, i):
    """Index of the first 1-minute bar of the next clock hour after decision bar i (the positional entry bar), or
    None at the end of the data. Uses timestamps only."""
    ns = _nsx(ctx)
    j = int(np.searchsorted(ns, (ns[i] // HOUR_NS + 1) * HOUR_NS, "left"))
    return j if j < ctx.n else None


def order_of(ctx, r, X, N, k=2.0, md="100", exit_i=None, open_target=True):
    """The core.simulate keyword arguments of the order of signal row r (a row of build()) under target rule X and
    entry N, or None when the order is cancelled before it can be placed (positional only).

    Target: X '2R' -> k R from the entry price before slippage, on the tick grid (YT1 common rules);
            X 'pdx' / 'liq' -> the level itself (column x_pdx / x_liq_<md>); the row must qualify at distance md.
    N 'close'   market at the decision bar's close.
    N 'retest'  limit at rt_px resting on the bars within 30 minutes after the decision bar's close, cancelled if the
                stop price trades first (cancel_lo / cancel_hi = the stop). 2R is measured from the limit price.
    N 'pos'     market at the open of bar j = the first 1-minute bar of the next clock hour. The order is placed at
                the close of bar j - 1 (its `i`); none if the stop price traded on a bar after the decision bar and
                before j. 2R: etype 'open' with the target 2R from open[j] (the s_Z00 exception: an 'open' order may
                read that open to place its target; open_target=False leaves the target out, which is the form the
                mirrored-future test compares). Level target: 'cancelled if the open is at or beyond the target' is
                written without reading the open, as a limit one tick inside the target that rests on bar j only and
                is cancelled at the target: on the tick grid bar j's open is either at / beyond the target (cancelled)
                or at / inside the limit (filled at the open, as a market order would be)."""
    side, i, stop = int(r.side), int(r.i), float(r.stop)
    if X == "2R":
        level = None
    else:
        level = float(r.x_pdx) if X == "pdx" else float(getattr(r, "x_liq_" + md))
        assert bool(getattr(r, f"q_{X}_{md}")) and level == level, "the signal does not qualify for this target"
    if N == "close":
        tgt = level if level is not None else target_of(r.entry_ref, stop, side, k)
        return dict(i=i, side=side, etype="close", stop=stop, target=float(tgt), exit_i=exit_i)
    if N == "retest":
        px = float(r.rt_px)
        tgt = level if level is not None else target_of(px, stop, side, k)
        ns = _nsx(ctx)
        expire = int(np.searchsorted(ns, ns[i] + REST_MIN * MIN_NS, "right")) - 1
        o = dict(i=i, side=side, etype="limit", price=px, expire=expire, stop=stop, target=float(tgt), exit_i=exit_i)
        o["cancel_lo" if side > 0 else "cancel_hi"] = stop
        return o
    assert N == "pos"
    j = pos_bar(ctx, i)
    if j is None:
        return None
    if j - 1 > i and ((ctx.L[i + 1:j].min() <= stop) if side > 0 else (ctx.H[i + 1:j].max() >= stop)):
        return None                                           # the stop price traded before the hour opened
    if level is None:
        o = dict(i=j - 1, side=side, etype="open", stop=stop, exit_i=exit_i)
        if open_target:
            o["target"] = float(target_of(ctx.O[j], stop, side, k))
        return o
    o = dict(i=j - 1, side=side, etype="limit", price=level - side * T, expire=j, stop=stop, target=level,
             exit_i=exit_i)
    o["cancel_hi" if side > 0 else "cancel_lo"] = level
    return o


def ocol(what, X, N):
    """Name of an outcome column: what in R / pnl / f (filled) / risk."""
    return f"{what}_{X}_{N}"


def _sim_rows(ctx, rows, verify):
    """Simulate the 9 (X, N) orders of each row. Returns dict of arrays (in row order) and, with verify, the 2R
    orders of every row (tagged) for the run_orders cross-check."""
    n = len(rows)
    res = {}
    for X in XS:
        for N in NS:
            res[ocol("R", X, N)] = np.full(n, np.nan)
            res[ocol("pnl", X, N)] = np.full(n, np.nan)
            res[ocol("risk", X, N)] = np.full(n, np.nan, np.float32)
            res[ocol("f", X, N)] = np.zeros(n, bool)
    ok, trad = np.zeros(n, bool), np.zeros(n, bool)
    exi = np.full(n, -1, np.int32)
    jr, jp = np.full(n, -1, np.int32), np.full(n, -1, np.int32)
    orders2 = []
    for q, row in enumerate(rows):
        ok[q] = day_ok(ctx, row.i)
        ex = exit_of(ctx, row.date, row.w_ldn)
        exi[q] = -1 if ex is None else ex
        if verify:
            for N in NS:
                o = order_of(ctx, row, "2R", N, exit_i=int(row.i) if ex is None else ex)
                if o is not None:
                    o["tag"] = f"{row.q}|{N}"
                    orders2.append(o)
        trad[q] = ok[q] and ex is not None and row.i < ex
        if not trad[q]:
            continue
        for X in XS:
            if X != "2R" and not getattr(row, f"q_{X}_100"):
                continue
            for N in NS:
                o = order_of(ctx, row, X, N, exit_i=ex)
                t = core.simulate(ctx, **o) if o is not None else None
                if N == "close":
                    assert t is not None, "a tradable signal whose market-at-close order does not fill"
                if t is None:
                    continue
                res[ocol("R", X, N)][q], res[ocol("pnl", X, N)][q] = t["R"], t["pnl"]
                res[ocol("risk", X, N)][q], res[ocol("f", X, N)][q] = t["risk_pts"], True
                if X == "2R" and N == "retest":
                    jr[q] = t["j"]
                if X == "2R" and N == "pos":
                    jp[q] = t["j"]
                if N == "pos" and X != "2R" and q % 7 == 0:
                    # the limit form of the positional order against a plain market-at-open order with that target
                    t2 = core.simulate(ctx, i=o["i"], side=o["side"], etype="open", stop=o["stop"],
                                       target=o["target"], exit_i=ex)
                    assert t2 is not None and t2["pnl"] == t["pnl"] and t2["R"] == t["R"] and t2["j"] == t["j"]
    res.update(day_ok=ok, tradable=trad, exit_i=exi, j_retest=jr, j_pos=jp)
    return res, orders2


_FORK = {}


def _worker(span):
    ctx, rows, verify = _FORK["a"]
    return _sim_rows(ctx, rows[span[0]:span[1]], verify)


def outcomes(ctx, sig, verify=True, procs=1):
    """Adds, for each target rule X in 2R / pdx / liq (minimum distance 1R) and entry N in close / retest / pos, the
    columns R_X_N, pnl_X_N, risk_X_N and f_X_N (the order filled), plus day_ok, tradable, exit_i, j_retest, j_pos.
    tradable = the day passes the run_orders(skip_roll=2) day filter and the signal has a later flat bar (an order
    can be placed). Outcomes exist on tradable rows only, and for pdx / liq only where the signal qualifies.
    verify=True: the 2R orders of ALL signals for each of the three entries are also passed through
    core.run_orders(skip_roll=2) and the trades it returns must be exactly the filled rows, with the same pnl and R.
    procs=2 splits the rows over two worker processes (fork); the result is identical to the single-process one."""
    sig = sig.copy()
    n = len(sig)
    sig["q"] = np.arange(n)
    rows = list(sig.itertuples(index=False))
    sig = sig.drop(columns="q")
    if procs > 1 and n > 1000:
        import multiprocessing as mp
        cut = [round(n * a / procs) for a in range(procs + 1)]
        _FORK["a"] = (ctx, rows, verify)
        with mp.get_context("fork").Pool(procs) as pool:
            parts = pool.map(_worker, [(cut[a], cut[a + 1]) for a in range(procs)])
        _FORK.clear()
        res = {key: np.concatenate([p[0][key] for p in parts]) for key in parts[0][0]}
        orders2 = [o for p in parts for o in p[1]]
    else:
        res, orders2 = _sim_rows(ctx, rows, verify)
    for X in XS:
        for N in NS:
            for w in ("R", "pnl", "risk", "f"):
                sig[ocol(w, X, N)] = res[ocol(w, X, N)]
    for key in ("day_ok", "tradable", "exit_i", "j_retest", "j_pos"):
        sig[key] = res[key]
    assert (sig.f_2R_close == sig.tradable).all()
    for X in ("pdx", "liq"):
        assert (sig[ocol("f", X, "close")] == (sig.tradable & sig[f"q_{X}_100"])).all()
    if verify:
        tr = core.run_orders(ctx, orders2, one_at_a_time=False, max_per_day=None, skip_roll=2)
        msg = []
        for N in NS:
            got = np.array(sorted(int(t["tag"].split("|")[0]) for t in tr if t["tag"].endswith("|" + N)), dtype=int)
            want = np.flatnonzero(sig[ocol("f", "2R", N)].to_numpy())
            assert np.array_equal(got, want), f"run_orders trades a different set of signals ({N})"
            msg.append(f"{N} {len(got)}")
        Rc = {N: sig[ocol("R", "2R", N)].to_numpy() for N in NS}
        Pc = {N: sig[ocol("pnl", "2R", N)].to_numpy() for N in NS}
        for t in tr:
            q, N = t["tag"].split("|")
            assert t["pnl"] == Pc[N][int(q)] and t["R"] == Rc[N][int(q)]
        sig.attrs["verified"] = (f"of {n} signals core.run_orders(skip_roll=2) trades, at 2R, " + ", ".join(msg)
                                 + " = the filled rows, same pnl and R")
    return sig


def path(phase):
    return core.OUT / phase / "G9_signals.parquet"


BOOLS = ["bias", "b_inv", "e_disc", "e_prem", "m_d18", "m_mid", "m_both", "r_pd", "r_sess", "r_pd_brk", "r_sess_brk",
         "h_h1", "h_h4", "s_smt", "q_pdx_100", "q_liq_100"]


def report(sig):
    g = sig.groupby("tf")
    print(pd.DataFrame({"signals": g.size(), "long": g.side.apply(lambda s: int((s > 0).sum())),
                        "short": g.side.apply(lambda s: int((s < 0).sum())), "tradable": g.tradable.sum(),
                        "dates": g.date.nunique()}).to_string())
    w = ["w_ldn", "w_am", "w_open", "w_sb", "w_pm"]
    print("signals per timeframe and window (all / tradable):")
    print(pd.concat([sig.groupby("tf")[w].sum().add_suffix("_all"),
                     sig[sig.tradable].groupby("tf")[w].sum().add_suffix("_trad")], axis=1).to_string())
    print("share of tradable signals with each column true, by timeframe (London window / the other windows):")
    for lab, m in (("ldn", sig.w_ldn), ("other", ~sig.w_ldn)):
        s = sig[sig.tradable & m]
        print(lab)
        print((s.groupby("tf")[BOOLS].mean() * 100).round(1).to_string())
    print("share of tradable signals whose order fills, by entry (2R target), by timeframe:")
    s = sig[sig.tradable]
    print((s.groupby("tf")[[ocol("f", "2R", N) for N in NS]].mean() * 100).round(1).to_string())


def main():
    import run
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", choices=["is", "full"], required=True)
    ap.add_argument("--procs", type=int, default=1, help="worker processes for the simulations (1 or 2)")
    ap.add_argument("--time-sample", type=int, default=0,
                    help="only time the simulations on this many evenly spaced signals; writes nothing")
    a = ap.parse_args()
    assert a.procs in (1, 2)
    pd.set_option("display.width", 250)
    t0 = time.time()
    ctx = core.Ctx(run.bars(a.phase))
    sig = build(ctx)
    print(f"G9 signals   phase {a.phase}   bars {ctx.ts[0]} -> {ctx.ts[-1]}   {len(sig)} signals built in "
          f"{time.time() - t0:.0f}s", flush=True)
    if a.time_sample:
        s = sig.iloc[np.linspace(0, len(sig) - 1, a.time_sample).astype(int)]
        t1 = time.time()
        outcomes(ctx, s, verify=False)
        dt = time.time() - t1
        print(f"simulated {len(s)} signals x 9 in {dt:.1f}s -> about {dt / len(s) * len(sig) / 60:.1f} minutes for "
              f"all {len(sig)} in one process (the run_orders cross-check adds about a third)")
        return
    t1 = time.time()
    sig = outcomes(ctx, sig, procs=a.procs)
    print(f"outcomes in {time.time() - t1:.0f}s ({a.procs} process{'es' if a.procs > 1 else ''})")
    print("run_orders check:", sig.attrs.get("verified"))
    if a.phase == "is":
        assert sig.time.max() < core.IS_END
    p = path(a.phase)
    p.parent.mkdir(parents=True, exist_ok=True)
    sig.attrs = {}
    sig.to_parquet(p, index=False)
    print(f"wrote {p}   {len(sig)} rows   {p.stat().st_size / 1e6:.1f} MB   {time.time() - t0:.0f}s")
    report(sig)


if __name__ == "__main__":
    main()
