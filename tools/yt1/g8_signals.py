#!/usr/bin/env python3
"""G8 signals - every CISD signal of the YT5 grid with its confluence columns (YT5_SPEC.md), computed once.

    build(ctx, tfs=(1, 5, 15))   one row per CISD on the 1-, 5- and 15-minute clock-aligned series whose decision bar
                                 (the 1-minute bar that closes the CISD bar) is at 08:30-10:59 or 13:30-14:59 New York.
                                 Every column is known at the close of the decision bar.
    outcomes(ctx, sig)           adds the trade of each signal under the house fills (core.simulate) for targets 1.5R,
                                 2R and 3R, and the `tradable` flag.
    python3 tools/yt1/g8_signals.py --phase is|full     writes data/studies/yt1/<phase>/G8_signals.parquet

Columns of build():
    tf, i, date, time, side, tod, entry_ref, prot, stop      the frame (i = index of the 1-minute decision bar)
    w_am, w_open, w_sb, w_pm                                  W: the decision bar is inside the window
    bias (0/1), kind ('cont' / 'fail' / '')                   B: tt.bias agrees with the trade, and the kind behind it
    e_disc, e_prem                                            E: signal close below / above EQ (mirrored for shorts)
    o_below                                                   O: signal close below the 18:00 open (mirrored)
    r_pd, r_sess                                              R: raid of candle 1's low / of the 18:00-08:29 low
    h_h1, h_h4                                                H: last completed 1-hour / 4-hour candle is a closure
    s_smt                                                     S: SMT divergence with ES on the run
    a_*                                                       audit values behind the columns (levels, run start);
                                                              they use bars up to the decision bar only
Readings (R) are listed in notes/G8.md. The building blocks come from tt.py unchanged.
"""
import argparse, pathlib, sys, time
import numpy as np
import pandas as pd
sys.path.insert(0, str(pathlib.Path(__file__).parent))
import core
import tt

TFS = (1, 5, 15)
WINDOWS = {"am": (510, 659), "open": (570, 659), "sb": (600, 659), "pm": (810, 899)}   # tod of the decision bar
TARGETS = ((1.5, "15"), (2.0, "20"), (3.0, "30"))
T = core.TICK
MIN_NS = 60 * 10 ** 9
HOUR_NS = 60 * MIN_NS
REF_MIN = 120                       # SMT reference: the 120 minutes before the run begins


def _ns(index):
    return index.as_unit("ns").asi8


def _series(ctx, tf):
    """(open, high, low, close, i_first, i_last) of the clock-aligned tf-minute series (tf = 1: the bars themselves)."""
    if tf == 1:
        ar = np.arange(ctx.n)
        return ctx.O, ctx.H, ctx.L, ctx.C, ar, ar
    b = ctx.bars(tf)
    o, h, l, c = (b[x].to_numpy(float) for x in ("open", "high", "low", "close"))
    return o, h, l, c, b.i_first.to_numpy(), b.i_last.to_numpy()


def _htf(ctx, hours):
    """Clock-hour (hours = 1) or 4-hour (18:00, 22:00, 02:00, 06:00, 10:00, 14:00 New York) candles of the continuous
    series, one per clock block that holds at least one 1-minute bar, with tt.closure2 / tt.closure3 on them.
    bull[k] / bear[k] = candle k is a candle 2 or candle 3 closure, where every candle the pattern reads holds at
    least half its minutes (otherwise False). i_last[k] = the 1-minute bar that closes candle k."""
    cache = ctx.__dict__.setdefault("_g8_htf", {})
    if hours in cache:
        return cache[hours]
    wall = _ns(ctx.ts.tz_localize(None))                          # New York wall clock
    key = (wall - (2 * HOUR_NS if hours == 4 else 0)) // (hours * HOUR_NS)
    assert (np.diff(key) >= 0).all(), "wall-clock blocks out of order"
    first = np.r_[0, np.flatnonzero(key[1:] != key[:-1]) + 1]
    last = np.r_[first[1:] - 1, ctx.n - 1]
    o, c = ctx.O[first], ctx.C[last]
    h, l = np.maximum.reduceat(ctx.H, first), np.minimum.reduceat(ctx.L, first)
    n = last - first + 1
    full = n * 2 >= hours * 60                                    # at least half its minutes
    ok2 = full & np.r_[False, full[:-1]]
    ok3 = ok2 & np.r_[False, False, full[:-2]]
    c2b, c2s = tt.closure2(h, l, c)
    c3b, c3s = tt.closure3(o, h, l, c)
    out = dict(i_first=first, i_last=last, n=n, o=o, h=h, l=l, c=c,
               bull=(c2b & ok2) | (c3b & ok3), bear=(c2s & ok2) | (c3s & ok3))
    cache[hours] = out
    return out


def _es(ctx):
    """ES 1-minute bars matched to MNQ by timestamp: (ns, low, high, cum) where cum[j] = number of MNQ bars before
    position j that have an ES bar with the same timestamp."""
    if getattr(ctx, "_g8_es", None) is None:
        es = ctx.extra("ES")
        assert es.index.is_monotonic_increasing and es.index.is_unique
        ens = _ns(es.index)
        has = np.isin(_ns(ctx.ts), ens)
        ctx._g8_es = (ens, es.low.to_numpy(float), es.high.to_numpy(float), np.r_[0, np.cumsum(has)])
    return ctx._g8_es


def _day_levels(ctx, dates):
    """Per calendar date (datetime64[D] array, unique): bias, kind, candle-1 high / low (NaN where tt.bias has none or
    says 'roll'), the 18:00 open of the trading day, and the high / low from 18:00 through 08:29."""
    B = tt.bias(ctx)
    n = len(dates)
    bias, kind = np.zeros(n, np.int8), np.full(n, "", object)
    h1, l1, op, sh, sl = (np.full(n, np.nan) for _ in range(5))
    for q, d in enumerate(dates):
        ts_d = pd.Timestamp(d)
        if ts_d in B.index:
            row = B.loc[ts_d]
            bias[q], kind[q] = int(row.bias), row.kind
            if row.kind != "roll":                               # (R) candle 1 not usable across a roll
                h1[q], l1[q] = row.h1, row.l1
        i18 = int(np.searchsorted(ctx.tdate, d, "left"))         # first bar of the trading day (18:00 the evening before)
        if i18 < ctx.n and ctx.tdate[i18] == d:
            op[q] = ctx.O[i18]
            hi = ctx.span(ts_d, 510, 510)[0]                     # first bar at or after 08:30
            if hi > i18:
                sh[q], sl[q] = ctx.H[i18:hi].max(), ctx.L[i18:hi].min()
    return bias, kind, h1, l1, op, sh, sl


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
    assert np.array_equal(close, ctx.C[i])
    long = side > 0
    tod = ctx.tod[i]

    # ---- day levels (B, E, O, R)
    dates = ctx.cdate[i]
    ud, inv = np.unique(dates, return_inverse=True)
    d_bias, d_kind, d_h1, d_l1, d_op, d_sh, d_sl = _day_levels(ctx, ud)
    agree = (d_bias[inv] == side) & (d_bias[inv] != 0)
    kind = np.where(agree, d_kind[inv], "")
    eq = (d_h1[inv] + d_l1[inv]) / 2.0
    op = d_op[inv]
    pd_lvl = np.where(long, d_l1[inv], d_h1[inv])
    ss_lvl = np.where(long, d_sl[inv], d_sh[inv])
    with np.errstate(invalid="ignore"):
        e_disc = np.where(long, close < eq, close > eq)
        e_prem = np.where(long, close > eq, close < eq)
        o_below = np.where(long, close < op, close > op)
        r_pd = np.where(long, (prot < pd_lvl) & (close > pd_lvl), (prot > pd_lvl) & (close < pd_lvl))
        r_sess = np.where(long, (prot < ss_lvl) & (close > ss_lvl), (prot > ss_lvl) & (close < ss_lvl))

    # ---- H: the last 1-hour / 4-hour candle whose last 1-minute bar is at or before the decision bar
    hh = {}
    for hours in (1, 4):
        X = _htf(ctx, hours)
        kk = np.searchsorted(X["i_last"], i, "right") - 1
        ok = kk >= 0
        kk = np.maximum(kk, 0)
        hh[hours] = ok & np.where(long, X["bull"][kk], X["bear"][kk])

    # ---- S: SMT with ES on the run against the 120 minutes before it
    ns = _ns(ctx.ts)
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
        "tod": tod.astype(np.int16), "entry_ref": close, "prot": prot, "stop": prot - side * T,
        "w_am": (tod >= 510) & (tod <= 659), "w_open": (tod >= 570) & (tod <= 659),
        "w_sb": (tod >= 600) & (tod <= 659), "w_pm": (tod >= 810) & (tod <= 899),
        "bias": agree.astype(np.int8), "kind": pd.Categorical(kind, categories=["", "cont", "fail"]),
        "e_disc": e_disc.astype(bool), "e_prem": e_prem.astype(bool), "o_below": o_below.astype(bool),
        "r_pd": r_pd.astype(bool), "r_sess": r_sess.astype(bool), "h_h1": hh[1], "h_h4": hh[4], "s_smt": smt,
        "a_eq": eq, "a_open": op, "a_pd": pd_lvl, "a_sess": ss_lvl, "a_run0": i0.astype(np.int32),
        "a_nq_ref": nq_ref, "a_es_run": es_run, "a_es_ref": es_ref})
    return df


def build(ctx, tfs=TFS):
    """All CISD signals of the grid with their confluence columns (see the module docstring). Nothing here reads a
    bar after the decision bar `i`. Rows are ordered by timeframe, then decision bar, then long before short."""
    cache = ctx.__dict__.setdefault("_g8_sig", {})
    parts = []
    for tf in tfs:
        if tf not in cache:
            cache[tf] = _build_tf(ctx, tf)
        parts.append(cache[tf])
    return pd.concat(parts, ignore_index=True) if len(parts) > 1 else parts[0].copy()


def target_of(entry_ref, stop, side, k):
    """R target as the YT1 common rules: entry +/- k x |entry - stop| before slippage, on the tick grid."""
    return core.tick_round(entry_ref + side * k * abs(entry_ref - stop))


def order_of(ctx, row, k, exit_i):
    return dict(i=int(row.i), side=int(row.side), etype="close", stop=float(row.stop),
                target=float(target_of(row.entry_ref, row.stop, row.side, k)), exit_i=int(exit_i))


def day_ok(ctx, i):
    """The day filter of core.run_orders(..., skip_roll=2) for a signal bar i: False on a roll day and the cash day
    after it, on a day without a daily ATR, and on a calendar date that is not a cash day."""
    d = pd.Timestamp(ctx.cdate[i])
    return not (d in ctx.roll2_dates or d in ctx.noatr_dates or ctx.dayn[i] < 0)


def outcomes(ctx, sig, verify=True):
    """Adds R15 pnl15 R20 pnl20 R30 pnl30 risk_pts reason (2R exit) day_ok tradable. Entry at the decision bar's
    close, the registered stop, target k R, flat at the day's flat bar; fills by core.simulate.
    tradable = the day passes the run_orders day filter and simulate returns a trade (it returns none for a signal at
    or after the flat bar or at the end of the data).
    verify=True: the 2R orders of ALL signals are also passed through core.run_orders(skip_roll=2) and the trades it
    returns must be exactly the tradable rows, with the same pnl and R."""
    sig = sig.copy()
    n = len(sig)
    i_end = ctx.days.i_end
    ok = np.zeros(n, bool)
    res = {f"{c}{s}": np.full(n, np.nan) for _, s in TARGETS for c in ("R", "pnl")}
    risk = np.full(n, np.nan)
    reason = np.full(n, "", object)
    trad = np.zeros(n, bool)
    orders2 = []
    for q, row in enumerate(sig.itertuples(index=False)):
        ok[q] = day_ok(ctx, row.i)
        d = pd.Timestamp(row.date)
        ex = int(i_end[d]) if d in i_end.index else int(row.i)
        if verify:
            o = order_of(ctx, row, 2.0, ex)
            o["tag"] = str(q)
            orders2.append(o)
        if not ok[q]:
            continue
        got = 0
        for k, s in TARGETS:
            t = core.simulate(ctx, **order_of(ctx, row, k, ex))
            if t is None:
                continue
            got += 1
            res["R" + s][q], res["pnl" + s][q] = t["R"], t["pnl"]
            if s == "20":
                risk[q], reason[q] = t["risk_pts"], t["reason"]
        assert got in (0, len(TARGETS)), "a signal fills for one target and not for another"
        trad[q] = got > 0
    for s in ("15", "20", "30"):
        sig["R" + s], sig["pnl" + s] = res["R" + s], res["pnl" + s]
    sig["risk_pts"] = risk
    sig["reason"] = pd.Categorical(reason, categories=["", "SL", "TP", "time"])
    sig["day_ok"] = ok
    sig["tradable"] = trad
    if verify:
        tr = core.run_orders(ctx, orders2, one_at_a_time=False, max_per_day=None, skip_roll=2)
        got = np.array(sorted(int(t["tag"]) for t in tr), dtype=int)
        assert np.array_equal(got, np.flatnonzero(trad)), "run_orders trades a different set of signals"
        for t in tr:
            q = int(t["tag"])
            assert t["pnl"] == res["pnl20"][q] and t["R"] == res["R20"][q]
        sig.attrs["verified"] = f"{len(tr)} of {n} signals traded by core.run_orders(skip_roll=2) = the tradable rows"
    return sig


def path(phase):
    return core.OUT / phase / "G8_signals.parquet"


def main():
    import run
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", choices=["is", "full"], required=True)
    a = ap.parse_args()
    t0 = time.time()
    ctx = core.Ctx(run.bars(a.phase))
    sig = build(ctx)
    print(f"G8 signals   phase {a.phase}   bars {ctx.ts[0]} -> {ctx.ts[-1]}   built in {time.time() - t0:.0f}s")
    sig = outcomes(ctx, sig)
    print("run_orders check:", sig.attrs.get("verified"))
    if a.phase == "is":
        assert sig.time.max() < core.IS_END
    p = path(a.phase)
    p.parent.mkdir(parents=True, exist_ok=True)
    sig.attrs = {}
    sig.to_parquet(p, index=False)
    print(f"wrote {p}   {len(sig)} rows   {time.time() - t0:.0f}s")
    g = sig.groupby("tf")
    print(pd.DataFrame({"signals": g.size(), "long": g.side.apply(lambda s: int((s > 0).sum())),
                        "short": g.side.apply(lambda s: int((s < 0).sum())), "tradable": g.tradable.sum(),
                        "days": g.date.nunique()}).to_string())
    cols = ["w_am", "w_open", "w_sb", "w_pm", "bias", "e_disc", "e_prem", "o_below", "r_pd", "r_sess", "h_h1", "h_h4",
            "s_smt"]
    print("share of tradable signals with each column true, by timeframe:")
    print((sig[sig.tradable].groupby("tf")[cols].mean() * 100).round(1).to_string())


if __name__ == "__main__":
    main()
