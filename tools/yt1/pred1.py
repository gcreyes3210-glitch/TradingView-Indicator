#!/usr/bin/env python3
"""PRED1 - can the next few minutes be predicted from the bars? (YT11_SPEC.md, Part 2)

    python3 tools/yt1/pred1.py --phase is      bars to 2022-12-31 only (asserted): fits the two models per horizon on
                                               every kept decision, saves them (PRED1_models.joblib; PRED1_ols.json =
                                               the OLS coefficients in readable form and the stamp: sha256 of the
                                               models file, time) and writes the IN-SAMPLE report is/PRED1_report.csv
                                               (+ is/PRED1_dropped.csv, what was dropped and why)
    python3 tools/yt1/pred1.py --phase full    every bar; NEVER fits: loads the saved models (exits if they are missing
                                               or are not the stamped file) -> full/PRED1_report_oos.csv (decisions
                                               from 2023-01-01), full/PRED1_report_full.csv (every decision),
                                               full/PRED1_verdict.csv / .json (the registered verdict per model x h),
                                               full/PRED1_dropped.csv; also rebuilds the in-sample report from these
                                               bars and says whether it equals the frozen one
    python3 tools/yt1/pred1.py --verify        on the in-sample bars (add --phase full for every bar), saved models:
                                               1. 2,400 trades (600 a horizon) replayed through core.run_orders ->
                                                  core.simulate(etype="close", exit_i=...), to the cent
                                               2. the inputs, s and target of about 350 decisions recomputed one at
                                                  a time in plain code from the bar table
                                               3. look-ahead: the inputs recomputed on bars truncated at six random
                                                  mid-session times must equal the full run's rows at or before the
                                                  cut (and once more with a mirrored future, the harness's test)
                                               last line starts with PASS or FAIL
    --dry-split DATE --dry-out DIR             code test only: both phases on a made-up split inside the data that is
                                               here, written to DIR (never to data/studies/yt1)

Decision (reading 1 of notes/PRED1.md): the close of a 1-minute bar whose close time is on the h-minute clock, from the
close at 10:30:00 (the bar stamped 10:29) to the bar stamped h minutes before the flat bar; h = 1, 5, 15, 30. Bars are
stamped with their open time, New York. Roll days and days without a daily ATR are not used (as core.run_orders).

    s        sd (mean removed, divisor 390) of the 390 most recent 1-minute close-to-close log returns of session bars
             (09:30 -> flat bar) at or before the decision; a return is between two bars of the same session stamped
             one minute apart, so the 09:30 bar has none; the window runs back into earlier sessions
    target   ln(close h minutes later / close) / (s x sqrt(h))

Inputs (the columns of FEATS), all from bars that have closed at the decision:
    r1 r2 r5 r15 r30 r60   ln(close / close w minutes earlier) / (s x sqrt(w))
    vwap_d  hi_d  lo_d     (close - X) / (close x s x sqrt(minutes since 09:30)), X = the session VWAP anchored at
                           09:30 (sum hlc3 x volume / sum volume through the bar just closed), the session high so far,
                           the session low so far
    vol5                   ln(volume of the last 5 minutes / (volume of the 60 minutes before them / 12))
    es1 es5                (ES log return - MNQ log return over the last 1 / 5 minutes) / s
    tod tod2               minutes since 09:30 / 390, and its square
    gap                    (09:30 open - previous session's close) / (close x s x sqrt(390))
A price "w minutes earlier" / "h minutes later" is the close of the bar stamped exactly that many minutes away (found by
its timestamp); when that minute has no bar the value is missing. A decision with any missing input (or no bar h
minutes later) is dropped and counted.

Models, fitted once in --phase is on the kept decisions:  ols = least squares with an intercept;
gbr = HistGradientBoostingRegressor(max_iter=200, learning_rate=0.05, max_depth=3, min_samples_leaf=200, random_state=1).

Trades (house fills: 1 tick against each fill, $1 a side, $2 a point = gross - $3.00), side = the sign of the forecast,
in at the decision close, out at the close h minutes later:  all = every decision;  sel = only when
|forecast| x s x sqrt(h) x close >= 1.5 points. P&L is computed here in arrays; --verify replays a sample in the harness.
"""
import os
os.environ.setdefault("OMP_NUM_THREADS", "1")           # 2 shared cores; also makes the fit independent of the machine
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
import argparse, hashlib, io, json, math, pathlib, sys, time
import numpy as np
import pandas as pd
sys.path.insert(0, str(pathlib.Path(__file__).parent))
import core
import run

HS = (1, 5, 15, 30)
RET_W = (1, 2, 5, 15, 30, 60)
ES_W = (1, 5)
FEATS = [f"r{w}" for w in RET_W] + ["vwap_d", "hi_d", "lo_d", "vol5"] + [f"es{w}" for w in ES_W] + ["tod", "tod2", "gap"]
MODELS = ("ols", "gbr")
VERSIONS = ("all", "sel")
GBR_ARGS = dict(max_iter=200, learning_rate=0.05, max_depth=3, min_samples_leaf=200, random_state=1)
N_S = 390                                # returns in s
OPEN_TOD = 570                           # 09:30
FIRST_CLOSE = 630                        # the first decision is the close at 10:30:00 (the bar stamped 10:29)
SESSION_MIN = 390
SEL_PTS = 1.5                            # the cost of a round trip in points
COST = 2 * core.SLIP * core.PV + 2 * core.COMM          # $3.00
OOS_START = pd.Timestamp("2023-01-01")
OOS_YEARS = (2023, 2024, 2025, 2026)
BASE_YEARS = tuple(range(2019, 2027))
P_MAX = 0.05 / 8
MIN_SEL = 100
YEARS_NEEDED = 3
N_BOOT, SEED = 10000, 1
MIN_NS = 60 * 10 ** 9
MODELS_NAME, OLS_NAME = "PRED1_models.joblib", "PRED1_ols.json"
LABEL = {"is": "IN-SAMPLE (the models were fitted on these same decisions)",
         "oos": "out of sample (decisions from the out-of-sample start; models frozen)",
         "full": "full span = the in-sample fit period + out of sample"}


def _ns(x):
    return pd.DatetimeIndex(x).as_unit("ns").asi8


# ------------------------------------------------------------------ inputs
def sessions_of(ctx):
    """The sessions the inputs are built on: one row per cash day of ctx.days (09:30 bar -> flat bar).
    Returns (i_open, i_end, prev_close, date, dpos): prev_close = the close of the previous session's flat bar,
    dpos = the row's position in ctx.days (-1: not a row of it).
    The last calendar date of the data is treated as still running: its session reaches the last 09:30-15:59 bar
    present, and it is a session as soon as it has a 09:30 bar. On complete data this changes nothing a decision can
    read (a decision is at or before the flat bar and reads nothing after itself); on bars that stop mid-session the
    day table does not yet know the day (it needs 150 bars) or places its flat bar 10 minutes before the last bar."""
    D = ctx.days
    io, ie = D.i_open.to_numpy(np.int64).copy(), D.i_end.to_numpy(np.int64).copy()
    date = D.index.to_numpy().astype("datetime64[D]")
    dpos = np.arange(len(D), dtype=np.int64)
    pc = np.r_[np.nan, ctx.C[ie[:-1]]] if len(D) else np.zeros(0)
    last = pd.Timestamp(ctx.cdate[-1])
    i0 = ctx.idx(last, OPEN_TOD)
    if i0 is not None:
        lo, hi = ctx.span(last, OPEN_TOD, 960)
        if len(D) and D.index[-1] == last:
            ie[-1] = max(ie[-1], hi - 1)
        else:
            assert not len(D) or D.index[-1] < last
            pc = np.r_[pc, ctx.C[ie[-1]] if len(D) else np.nan]
            io, ie = np.r_[io, int(i0)], np.r_[ie, hi - 1]
            date, dpos = np.r_[date, np.datetime64(last, "D")], np.r_[dpos, -1]
    return io, ie, pc, date, dpos


def bar_features(ctx):
    """The inputs at every session bar that closes at or after 10:30:00 (the 1-minute grid; the other horizons use a
    subset of these bars). Each row is built from bars at or before its own bar only.
    Returns a dict: ci (bar positions), ns (their stamps, UTC ns), X (len x len(FEATS)), s, date (cash date),
    dpos (row of ctx.days, -1 if the date is not one)."""
    n, C, H, L, V, tod = ctx.n, ctx.C, ctx.H, ctx.L, ctx.V, ctx.tod
    ns = _ns(ctx.ts)
    assert (np.diff(ns) > 0).all(), "bars are not in time order"
    io, ie, pc, date, dpos = sessions_of(ctx)
    assert (ie >= io).all() and (io[1:] > ie[:-1]).all(), "sessions overlap"
    mark = np.zeros(n + 1, np.int64)
    mark[io] += 1
    mark[ie + 1] -= 1
    in_ses = np.cumsum(mark[:n]) > 0
    is_open = np.zeros(n, bool)
    is_open[io] = True
    snum = np.cumsum(is_open) - 1                      # session number of a bar that is in a session

    # ---- s: the 390 most recent one-minute returns inside sessions
    one_min = np.r_[False, np.diff(ns) == MIN_NS]
    has_ret = in_ses & ~is_open & one_min              # not the session's first bar => the previous bar is in it too
    r = np.zeros(n)
    with np.errstate(divide="ignore", invalid="ignore"):     # (a mirrored future in --verify can hold prices <= 0)
        r[1:] = np.log(C[1:] / C[:-1])
    rc, cnt = r[has_ret], np.cumsum(has_ret)

    # ---- session VWAP, high and low through each bar
    vwap, shi, slo = np.full(n, np.nan), np.full(n, np.nan), np.full(n, np.nan)
    hlc3 = (H + L + C) / 3.0
    for a, b in zip(io, ie):
        sl = slice(int(a), int(b) + 1)
        cv, cpv = np.cumsum(V[sl]), np.cumsum(hlc3[sl] * V[sl])
        with np.errstate(divide="ignore", invalid="ignore"):
            vwap[sl] = np.where(cv > 0, cpv / cv, np.nan)
        shi[sl], slo[sl] = np.maximum.accumulate(H[sl]), np.minimum.accumulate(L[sl])

    ci = np.flatnonzero(in_ses & (tod + 1 >= FIRST_CLOSE))
    e = cnt[ci]
    s = np.full(len(ci), np.nan)
    ok = e >= N_S
    if ok.any():
        win = np.lib.stride_tricks.sliding_window_view(rc, N_S)
        rows, out = e[ok] - N_S, np.empty(int(ok.sum()))
        for a in range(0, len(rows), 20000):
            out[a:a + 20000] = win[rows[a:a + 20000]].std(axis=1)
        s[ok] = out
    s[~(s > 0)] = np.nan

    t = ns[ci]
    c = C[ci]
    sn = snum[ci]
    mins = (tod[ci] + 1 - OPEN_TOD).astype(float)      # minutes since 09:30 at the bar's close

    def back(w):
        """Position of the bar stamped w minutes before each row's bar, and whether that bar exists."""
        j = np.searchsorted(ns, t - w * MIN_NS)
        return j, ns[j] == t - w * MIN_NS

    es = ctx.extra("ES")
    assert es.index.is_unique
    esc = es.close.reindex(ctx.ts).to_numpy(float)     # the ES close of the same minute (NaN: ES has no bar there)
    col = {}
    with np.errstate(divide="ignore", invalid="ignore"):
        for w in sorted(set(RET_W) | set(ES_W)):
            j, okj = back(w)
            lr = np.where(okj, np.log(c / C[j]), np.nan)
            if w in RET_W:
                col[f"r{w}"] = lr / (s * math.sqrt(w))
            if w in ES_W:
                col[f"es{w}"] = (np.where(okj, np.log(esc[ci] / esc[j]), np.nan) - lr) / s
        den = c * s * np.sqrt(mins)
        col["vwap_d"], col["hi_d"], col["lo_d"] = (c - vwap[ci]) / den, (c - shi[ci]) / den, (c - slo[ci]) / den
        cum = np.r_[0.0, np.cumsum(V)]                 # whole numbers: exact
        a5, a65 = np.searchsorted(ns, t - 4 * MIN_NS), np.searchsorted(ns, t - 64 * MIN_NS)
        v5, v60 = cum[ci + 1] - cum[a5], cum[a5] - cum[a65]
        col["vol5"] = np.where((v5 > 0) & (v60 > 0), np.log(v5 / (v60 / 12.0)), np.nan)
        col["tod"] = mins / SESSION_MIN
        col["tod2"] = col["tod"] ** 2
        col["gap"] = (ctx.O[io[sn]] - pc[sn]) / (c * s * math.sqrt(SESSION_MIN))
    X = np.column_stack([col[k] for k in FEATS])
    X[~np.isfinite(X)] = np.nan
    return dict(ci=ci, ns=t, X=X, s=s, date=date[sn], dpos=dpos[sn])


def decisions(ctx, F, h):
    """The decisions of horizon h on ctx's bars: one row per decision bar that exists on a used day, kept or dropped.
    Columns: i (decision bar), k (the bar h minutes later, -1 if that minute has no bar), ns, day, year, close, s,
    the inputs, y (the target), close_k, ok (every input and the target present), why (the first thing missing).
    Second value: counts (grid points expected on used days, of which without a bar)."""
    D = ctx.days
    n, tod, C = ctx.n, ctx.tod, ctx.C
    ns_all = _ns(ctx.ts)
    i_end = D.i_end.to_numpy(np.int64)
    flat_tod = tod[i_end]
    unused = (D.roll | D.atr.isna()).to_numpy()
    assert set(D.index[unused]) == (ctx.roll_dates | ctx.noatr_dates)
    ci, dp = F["ci"], F["dpos"]
    dpc = np.where(dp >= 0, dp, 0)
    tc = tod[ci]
    m = (dp >= 0) & ~unused[dpc] & (ci <= i_end[dpc]) & ((tc + 1 - FIRST_CLOSE) % h == 0) & (tc <= flat_tod[dpc] - h)
    rows = np.flatnonzero(m)
    i = ci[rows]
    t = F["ns"][rows] + h * MIN_NS
    k = np.searchsorted(ns_all, t)
    kc = np.minimum(k, n - 1)
    has_k = (k < n) & (ns_all[kc] == t)
    assert (kc[has_k] <= i_end[dpc[rows]][has_k]).all(), "an exit after the flat bar"
    s, X = F["s"][rows], F["X"][rows]
    with np.errstate(divide="ignore", invalid="ignore"):
        y = np.where(has_k, np.log(C[kc] / C[i]) / (s * math.sqrt(h)), np.nan)
    df = pd.DataFrame(X, columns=FEATS)
    df.insert(0, "s", s)
    df.insert(0, "close", C[i])
    df.insert(0, "year", F["date"][rows].astype("datetime64[Y]").astype(int) + 1970)
    df.insert(0, "day", F["date"][rows])
    df.insert(0, "ns", F["ns"][rows])
    df.insert(0, "k", np.where(has_k, kc, -1))
    df.insert(0, "i", i)
    df["close_k"] = np.where(has_k, C[kc], np.nan)
    df["y"] = y
    why = np.full(len(df), "", dtype=object)
    for name, bad in [("no bar h minutes later", ~has_k)] + [(f, np.isnan(X[:, q])) for q, f in reversed(list(enumerate(FEATS)))] \
            + [("s", np.isnan(s))]:
        why[bad] = name                                # the last written wins: s, then the inputs in order
    why[(why == "") & ~np.isfinite(y)] = "target"           # cannot happen on real prices (all positive)
    df["why"] = why
    df["ok"] = why == ""
    # grid points a used day should have, whether or not the minute has a bar
    last = flat_tod[~unused] - h
    expected = int(np.where(last >= FIRST_CLOSE - 1, (last - (FIRST_CLOSE - 1)) // h + 1, 0).sum())
    return df, dict(expected=expected, no_bar=expected - len(df))


def build(ctx, hs=HS):
    """{h: decisions frame}, {h: counts} for the context's bars."""
    F = bar_features(ctx)
    out, cnt = {}, {}
    for h in hs:
        out[h], cnt[h] = decisions(ctx, F, h)
    return out, cnt


def dropped_table(decs, cnts, lo=None, hi=None, label=""):
    """Rows (sample, h, reason, n): what was dropped among the decisions with lo <= day < hi."""
    rows = []
    for h, d in decs.items():
        d = _period(d, lo, hi)
        rows.append(dict(sample=label, h=h, reason="decision bars on used days", n=int(len(d))))
        rows.append(dict(sample=label, h=h, reason="kept", n=int(d.ok.sum())))
        rows.append(dict(sample=label, h=h, reason="dropped", n=int((~d.ok).sum())))
        for w, c in d.why[~d.ok].value_counts().items():
            rows.append(dict(sample=label, h=h, reason=f"dropped, first missing: {w}", n=int(c)))
        if lo is None and hi is None:
            rows.append(dict(sample=label, h=h, reason="grid minutes without a bar (no decision)", n=cnts[h]["no_bar"]))
    return pd.DataFrame(rows)


def _period(d, lo=None, hi=None):
    m = np.ones(len(d), bool)
    if lo is not None:
        m &= (d.day >= np.datetime64(pd.Timestamp(lo), "D")).to_numpy()
    if hi is not None:
        m &= (d.day < np.datetime64(pd.Timestamp(hi), "D")).to_numpy()
    return d[m]


# ------------------------------------------------------------------ models
def fit_ols(X, y):
    """Least squares with an intercept. Returns the coefficients with classical and heteroskedasticity-robust (HC1)
    standard errors; all of it describes the fit sample."""
    n, p = len(y), X.shape[1] + 1
    A = np.column_stack([np.ones(n), X])
    beta, *_ = np.linalg.lstsq(A, y, rcond=None)
    res = y - A @ beta
    xtxi = np.linalg.inv(A.T @ A)
    se = np.sqrt(np.diag(xtxi) * (res @ res) / (n - p))
    hc = xtxi @ ((A * (res ** 2)[:, None]).T @ A) @ xtxi * n / (n - p)
    se_hc = np.sqrt(np.diag(hc))
    return dict(beta=beta, se=se, t=beta / se, se_hc1=se_hc, t_hc1=beta / se_hc, n=n,
                r2_zero=float(1 - (res @ res) / (y @ y)), r2_centred=float(1 - (res @ res) / ((y - y.mean()) @ (y - y.mean()))),
                sigma=float(math.sqrt((res @ res) / (n - p))))


def fit_models(decs):
    """Fits ols and gbr per horizon on the kept decisions of decs. Returns the bundle that is saved and a readable
    description of the fits."""
    import sklearn
    from sklearn.ensemble import HistGradientBoostingRegressor
    bundle = dict(study="PRED1 (YT11_SPEC.md, Part 2)", features=list(FEATS), horizons=list(HS), ols={}, gbr={},
                  gbr_args=dict(GBR_ARGS), sklearn=sklearn.__version__, numpy=np.__version__)
    info = {}
    for h in HS:
        d = decs[h][decs[h].ok]
        X, y = d[FEATS].to_numpy(float), d.y.to_numpy(float)
        assert np.isfinite(X).all() and np.isfinite(y).all() and len(y) > len(FEATS) + 1
        o = fit_ols(X, y)
        bundle["ols"][h] = dict(intercept=float(o["beta"][0]), coef=o["beta"][1:].astype(float))
        t0 = time.time()
        g = HistGradientBoostingRegressor(**GBR_ARGS).fit(X, y)
        bundle["gbr"][h] = g
        names = ["intercept"] + FEATS
        info[str(h)] = dict(
            n=int(len(y)), days=int(d.day.nunique()), first_decision=str(pd.Timestamp(d.day.min()).date()),
            last_decision=str(pd.Timestamp(d.day.max()).date()), target_mean=float(y.mean()), target_sd=float(y.std()),
            ols=dict(r2_zero_in_sample=o["r2_zero"], r2_centred_in_sample=o["r2_centred"], residual_sd=o["sigma"],
                     coef={nm: dict(b=float(o["beta"][q]), se=float(o["se"][q]), t=float(o["t"][q]),
                                    se_hc1=float(o["se_hc1"][q]), t_hc1=float(o["t_hc1"][q])) for q, nm in enumerate(names)}),
            gbr=dict(n_iter=int(g.n_iter_), early_stopping=bool(g.do_early_stopping_), fit_seconds=round(time.time() - t0, 1)))
    return bundle, info


def forecast(bundle, model, h, X):
    X = np.asarray(X, float)
    if len(X) == 0:
        return np.zeros(0)
    if model == "ols":
        o = bundle["ols"][h]
        return o["intercept"] + X @ o["coef"]
    return np.asarray(bundle["gbr"][h].predict(X), float)


def _sha(p):
    return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()


def load_models(out):
    """The frozen models. Fails if they are missing, are not the stamped file, or do not match the readable copy."""
    import joblib
    out = pathlib.Path(out)
    mp, jp = out / MODELS_NAME, out / OLS_NAME
    if not mp.exists() or not jp.exists():
        raise SystemExit(f"PRED1: {mp} / {jp.name} missing: the models are fitted and frozen by  --phase is  first; "
                         f"this phase never fits")
    js = json.loads(jp.read_text())
    if _sha(mp) != js["sha256_models"]:
        raise SystemExit(f"PRED1: {mp.name} is not the file stamped in {jp.name} (sha256 differs)")
    bundle = joblib.load(mp)
    assert bundle["features"] == FEATS and tuple(bundle["horizons"]) == HS, "the saved models are for other inputs"
    for h in HS:
        o, c = bundle["ols"][h], js["horizons"][str(h)]["ols"]["coef"]
        assert o["intercept"] == c["intercept"]["b"] and all(float(o["coef"][q]) == c[f]["b"] for q, f in enumerate(FEATS)), \
            "the saved OLS coefficients differ from the readable copy"
    return bundle, js


# ------------------------------------------------------------------ scoring
def trade_arrays(d, fc, h):
    """side, forecast move in points, gross $ and net $ of the trade each kept decision would be (side 0: none)."""
    side = np.sign(fc)
    pts = np.abs(fc) * d.s.to_numpy() * math.sqrt(h) * d.close.to_numpy()
    gross = side * (d.close_k.to_numpy() - d.close.to_numpy()) * core.PV
    return side, pts, gross, gross - COST


def score(d, fc, h, model, sample, n_bars, years):
    """The two report rows (all, sel) of one model x horizon on the kept decisions d with forecasts fc."""
    n = len(d)
    y = d.y.to_numpy(float)
    base = dict(sample=LABEL[sample], model=model, h=h)
    stats = dict(n_decision_bars=int(n_bars), n_dropped=int(n_bars - n), n_decisions=int(n), days=0, r2_zero=np.nan,
                 corr=np.nan, sign_right=np.nan, sign_right_nonzero=np.nan)
    side, pts, gross, net = trade_arrays(d, fc, h)
    dayc, inv = np.unique(d.day.to_numpy(), return_inverse=True)
    yr = d.year.to_numpy()
    if n:
        ss = float(y @ y)
        right = side * np.sign(y) > 0
        nz = y != 0
        stats.update(days=int(len(dayc)), r2_zero=1 - float((y - fc) @ (y - fc)) / ss if ss > 0 else np.nan,
                     corr=float(np.corrcoef(fc, y)[0, 1]) if n > 2 and fc.std() > 0 and y.std() > 0 else np.nan,
                     sign_right=float(right.mean()), sign_right_nonzero=float(right[nz].mean()) if nz.any() else np.nan)
    rows = []
    for v in VERSIONS:
        m = (side != 0) if v == "all" else (side != 0) & (pts >= SEL_PTS)
        nt = int(m.sum())
        r = dict(base, version=v, **stats, trades=nt, trades_per_day=np.nan, win=np.nan, gross_per_trade=np.nan,
                 net_per_trade=np.nan, net_per_day=np.nan, gross_total=0.0, net_total=0.0, p_boot_day=np.nan, years_pos=0)
        daily = np.bincount(inv[m], weights=net[m], minlength=len(dayc)) if n else np.zeros(0)
        if n:
            r.update(trades_per_day=nt / len(dayc), net_per_day=float(daily.mean()),
                     gross_total=round(float(gross[m].sum()), 2), net_total=round(float(net[m].sum()), 2),
                     p_boot_day=core.boot_p(daily, n=N_BOOT, seed=SEED))
        if nt:
            r.update(win=float((net[m] > 0).mean()), gross_per_trade=float(gross[m].mean()), net_per_trade=float(net[m].mean()))
        for yy in years:
            in_y = yr == yy
            r[f"net_{yy}"] = round(float(net[m & in_y].sum()), 2) if in_y.any() else np.nan
        r["years_pos"] = int(sum(1 for yy in years if r[f"net_{yy}"] == r[f"net_{yy}"] and r[f"net_{yy}"] > 0))
        rows.append(r)
    return rows


def report(decs, bundle, sample, lo=None, hi=None, years=BASE_YEARS):
    """One row per model x h x version over the decisions with lo <= day < hi."""
    rows = []
    for model in MODELS:
        for h in HS:
            dp = _period(decs[h], lo, hi)
            d = dp[dp.ok]
            rows += score(d, forecast(bundle, model, h, d[FEATS].to_numpy(float)), h, model, sample, len(dp), years)
    return pd.DataFrame(rows)


def verdicts(rep, years=OOS_YEARS):
    """The registered verdict per model x h from the out-of-sample report's `sel` rows."""
    out = []
    for r in rep[rep.version == "sel"].itertuples(index=False):
        ny = {int(y): getattr(r, f"net_{y}") for y in years}
        pos = int(sum(1 for v in ny.values() if v == v and v > 0))
        ch = dict(trades=bool(r.trades >= MIN_SEL), net_per_day=bool(r.net_per_day > 0), p=bool(r.p_boot_day < P_MAX),
                  years=bool(pos >= YEARS_NEEDED))
        if r.n_decisions == 0:
            v = "no out-of-sample decisions in this data: no verdict"
        elif r.trades < MIN_SEL:
            v = "predicts nothing worth a trade"
        else:
            v = "counts" if all(ch.values()) else "does not count"
        out.append(dict(model=r.model, h=r.h, oos_decisions=r.n_decisions, oos_days=r.days, sel_trades=r.trades,
                        sel_trades_per_day=r.trades_per_day, sel_net_per_trade=r.net_per_trade, sel_net_per_day=r.net_per_day,
                        p_boot_day=r.p_boot_day, p_needed=P_MAX, **{f"net_{y}": ny[y] for y in ny}, years_pos=pos,
                        years_needed=YEARS_NEEDED, min_trades=MIN_SEL, ok_trades=ch["trades"], ok_net=ch["net_per_day"],
                        ok_p=ch["p"], ok_years=ch["years"], verdict=v))
    return pd.DataFrame(out)


def _years(decs):
    ys = set(BASE_YEARS)
    for d in decs.values():
        ys |= set(int(v) for v in np.unique(d.year.to_numpy()))
    return tuple(sorted(ys))


FMT = {"r2_zero": "{:+.5f}".format, "corr": "{:+.4f}".format, "sign_right": "{:.4f}".format, "trades_per_day": "{:.2f}".format,
       "gross_per_trade": "{:+.3f}".format, "net_per_trade": "{:+.3f}".format, "net_per_day": "{:+.2f}".format,
       "net_total": "{:+.0f}".format, "p_boot_day": "{:.4f}".format, "win": "{:.3f}".format}


def show(rep, years=None):
    cols = ["model", "h", "version", "n_decisions", "days", "r2_zero", "corr", "sign_right", "trades", "trades_per_day",
            "win", "gross_per_trade", "net_per_trade", "net_per_day", "net_total", "p_boot_day"]
    cols += [f"net_{y}" for y in (years or [])]
    fm = dict(FMT, **{f"net_{y}": "{:+.0f}".format for y in (years or [])})
    return rep[cols].to_string(index=False, formatters=fm, na_rep="-")


# ------------------------------------------------------------------ phases
def phase_is(out=core.OUT, split_at=None):
    """Fit on every kept decision of the in-sample bars, freeze, and report in sample. split_at (dry run only) = a
    made-up end of the in-sample period: the bars are cut there."""
    import joblib
    t00 = time.time()
    dry = split_at is not None
    out = pathlib.Path(out)
    if dry:
        end = pd.Timestamp(split_at)
        a = core.load_bars("MNQ", cut=end.tz_localize(core.TZ))
    else:
        end = OOS_START
        a = run.bars("is")
        assert a.index.max() < core.IS_END, "in-sample bars reach into the out-of-sample window"
    ctx = core.Ctx(a)
    assert ctx.extra("ES").index.max() < end.tz_localize(core.TZ), "ES bars reach past the end of the in-sample period"
    decs, cnts = build(ctx)
    for h in HS:
        assert len(decs[h]) and pd.Timestamp(decs[h].day.max()) < end and ctx.ts[int(decs[h].k.max())] < end.tz_localize(core.TZ)
    print(f"PRED1   phase is{'  (DRY RUN on a made-up split: numbers mean nothing)' if dry else ''}   bars {ctx.ts[0]} -> "
          f"{ctx.ts[-1]}   fit sample = decisions before {end.date()}   [{time.time() - t00:.0f}s]")
    drops = dropped_table(decs, cnts, label=LABEL["is"])
    print("decisions per horizon (decision bars on used days / kept / dropped; first missing thing of the dropped):")
    for h in HS:
        d = drops[drops.h == h]
        print(f"  h {h:>2}: " + "  |  ".join(f"{r.reason} {r.n}" for r in d.itertuples(index=False)))
    bundle, info = fit_models(decs)
    out.mkdir(parents=True, exist_ok=True)
    (out / "is").mkdir(parents=True, exist_ok=True)
    mp, jp = out / MODELS_NAME, out / OLS_NAME
    old = _coefs(json.loads(jp.read_text())) if jp.exists() else None
    joblib.dump(bundle, mp)
    js = dict(study="PRED1 (YT11_SPEC.md, Part 2)", frozen=True, dry_run=dry,
              note="fitted once on the in-sample decisions; every figure in this file describes the fit sample (in-sample)",
              is_end=str((end - pd.Timedelta(days=1)).date()), oos_start=str(end.date()), bars=[str(ctx.ts[0]), str(ctx.ts[-1])],
              features=FEATS, target="ln(close h minutes later / close) / (s x sqrt(h))", gbr_args=GBR_ARGS,
              t_statistics="t = classical (equal-variance) OLS t; t_hc1 = heteroskedasticity-robust (HC1); both in-sample",
              horizons=info, versions=dict(sklearn=bundle["sklearn"], numpy=bundle["numpy"], pandas=pd.__version__,
                                           joblib=joblib.__version__, python=sys.version.split()[0]),
              models_file=MODELS_NAME, sha256_models=_sha(mp), stamped_utc=pd.Timestamp.now("UTC").strftime("%Y-%m-%d %H:%M:%S"))
    if old is not None and old != _coefs(js):
        print(f"NOTE: {jp.name} existed with different coefficients and is rewritten")
    jp.write_text(json.dumps(js, indent=1))
    load_models(out)                                          # the saved files read back and agree
    years = _years(decs)
    rep = report(decs, bundle, "is", years=years)
    rep.to_csv(out / "is" / "PRED1_report.csv", index=False, lineterminator="\n")
    drops.to_csv(out / "is" / "PRED1_dropped.csv", index=False, lineterminator="\n")
    print("\nOLS coefficients (in-sample; t = classical, t_hc1 = heteroskedasticity-robust):")
    print(coef_table(info))
    print("\ngbr: " + "   ".join(f"h {h}: {info[str(h)]['gbr']['n_iter']} iterations"
                                 f"{' (early stopping on: sklearn default for n > 10,000)' if info[str(h)]['gbr']['early_stopping'] else ''}"
                                 for h in HS))
    print(f"\n{LABEL['is']} - fit statistics and trades; trades a day and net per day are per day with a decision; "
          f"p = one-sided bootstrap of the daily net")
    print(show(rep, [y for y in years if rep[f'net_{y}'].notna().any()]))
    print(f"\nwrote {mp}, {jp}, {out / 'is' / 'PRED1_report.csv'}, {out / 'is' / 'PRED1_dropped.csv'}"
          f"   sha256 of the models file {js['sha256_models'][:16]}...   [{time.time() - t00:.0f}s]")
    return rep, js


def _coefs(js):
    try:
        return {h: {k: v["b"] for k, v in x["ols"]["coef"].items()} for h, x in js["horizons"].items()}
    except (KeyError, TypeError):
        return None


def coef_table(info):
    rows = []
    for nm in ["intercept"] + FEATS:
        r = {"input": nm}
        for h in HS:
            c = info[str(h)]["ols"]["coef"][nm]
            r[f"b_h{h}"], r[f"t_h{h}"], r[f"thc_h{h}"] = c["b"], c["t"], c["t_hc1"]
        rows.append(r)
    fm = {}
    for h in HS:
        fm.update({f"b_h{h}": "{:+.5f}".format, f"t_h{h}": "{:+.2f}".format, f"thc_h{h}": "{:+.2f}".format})
    foot = "n " + "  ".join(f"h{h}: {info[str(h)]['n']}" for h in HS) + "   in-sample R2 against zero " + \
        "  ".join(f"h{h}: {info[str(h)]['ols']['r2_zero_in_sample']:+.5f}" for h in HS)
    return pd.DataFrame(rows).to_string(index=False, formatters=fm) + "\n" + foot


def _same_report(a, b):
    """The rebuilt report a equals the frozen report b on every column of b, up to float printing (NaN = NaN)."""
    if not set(b.columns) <= set(a.columns) or len(a) != len(b):
        return False
    for c in b.columns:
        x, y = a[c].to_numpy(), b[c].to_numpy()
        if a[c].dtype.kind in "fiu" and b[c].dtype.kind in "fiu":
            if not np.allclose(x.astype(float), y.astype(float), rtol=1e-9, atol=1e-9, equal_nan=True):
                return False
        elif not (a[c].astype(str) == b[c].astype(str)).all():
            return False
    return True


def phase_full(out=core.OUT, dry=False):
    """The frozen models on every bar. Fits nothing."""
    t00 = time.time()
    out = pathlib.Path(out)
    bundle, js = load_models(out)                              # before any bar is read; exits if they are missing
    assert bool(js.get("dry_run")) == dry, "a dry-run model file can only be used by a dry run (and vice versa)"
    oos_start = pd.Timestamp(js["oos_start"])
    assert dry or oos_start == OOS_START
    ctx = core.Ctx(run.bars("is" if dry else "full"))
    decs, cnts = build(ctx)
    years = _years(decs)
    oos_years = OOS_YEARS if not dry else tuple(y for y in years if y >= oos_start.year and any((d.year == y).any() for d in decs.values()))
    n_oos = {h: int((_period(decs[h], lo=oos_start).ok).sum()) for h in HS}
    print(f"PRED1   phase full{'  (DRY RUN on a made-up split: numbers mean nothing)' if dry else ''}   bars {ctx.ts[0]} -> "
          f"{ctx.ts[-1]}   models frozen {js['stamped_utc']} UTC on decisions to {js['is_end']}   out of sample from "
          f"{oos_start.date()}   [{time.time() - t00:.0f}s]")
    import sklearn
    if sklearn.__version__ != js["versions"]["sklearn"]:
        print(f"WARNING: scikit-learn here is {sklearn.__version__}, the models were saved with {js['versions']['sklearn']}")
    if not any(n_oos.values()):
        print("NO OUT-OF-SAMPLE DECISIONS IN THIS DATA: the out-of-sample report is empty and there is no verdict")
    rep_is = report(decs, bundle, "is", hi=oos_start, years=years)
    rep_oos = report(decs, bundle, "oos", lo=oos_start, years=years)
    rep_full = report(decs, bundle, "full", years=years)
    fp = out / "is" / "PRED1_report.csv"
    if fp.exists():
        frozen = pd.read_csv(fp)
        same = _same_report(pd.read_csv(io.StringIO(rep_is.to_csv(index=False))), frozen)
        print(f"in-sample report rebuilt from these bars with the frozen models equals the frozen is/PRED1_report.csv: "
              f"{same}" + ("" if same else "   <-- NOT REPRODUCED"))
    else:
        same = None
        print("is/PRED1_report.csv is not here: the in-sample report cannot be compared")
    ver = verdicts(rep_oos, oos_years)
    d = out / "full"
    d.mkdir(parents=True, exist_ok=True)
    rep_oos.to_csv(d / "PRED1_report_oos.csv", index=False, lineterminator="\n")
    rep_full.to_csv(d / "PRED1_report_full.csv", index=False, lineterminator="\n")
    ver.to_csv(d / "PRED1_verdict.csv", index=False, lineterminator="\n")
    pd.concat([dropped_table(decs, cnts, hi=oos_start, label=LABEL["is"]), dropped_table(decs, cnts, lo=oos_start, label=LABEL["oos"]),
               dropped_table(decs, cnts, label=LABEL["full"])], ignore_index=True).to_csv(d / "PRED1_dropped.csv", index=False,
                                                                                           lineterminator="\n")
    (d / "PRED1_verdict.json").write_text(json.dumps(dict(
        study="PRED1 (YT11_SPEC.md, Part 2)", dry_run=dry, bars=[str(ctx.ts[0]), str(ctx.ts[-1])], oos_start=str(oos_start.date()),
        oos_years=list(oos_years), models_stamped_utc=js["stamped_utc"], sha256_models=js["sha256_models"],
        in_sample_report_reproduced=same, oos_decisions={str(h): n_oos[h] for h in HS},
        rule=f"counts = sel out of sample: at least {MIN_SEL} trades, mean net per day > 0 with p < {P_MAX} (one-sided "
             f"bootstrap of the daily net over days with a decision, {N_BOOT} resamples, seed {SEED}) and {YEARS_NEEDED} "
             f"of {len(oos_years)} calendar years net positive; under {MIN_SEL} sel trades = predicts nothing worth a trade",
        verdicts=json.loads(ver.to_json(orient="records"))), indent=1))
    yo = [y for y in years if rep_oos[f"net_{y}"].notna().any()]
    print(f"\n{LABEL['oos']}")
    print(show(rep_oos, yo))
    print(f"\n{LABEL['full']}")
    print(show(rep_full, [y for y in years if rep_full[f'net_{y}'].notna().any()]))
    print(f"\nregistered verdict (sel, out of sample: >= {MIN_SEL} trades, net per day > 0 with p < {P_MAX:.5f}, "
          f">= {YEARS_NEEDED} of {len(oos_years)} years net positive)")
    print(ver[["model", "h", "oos_decisions", "sel_trades", "sel_trades_per_day", "sel_net_per_trade", "sel_net_per_day",
               "p_boot_day", "years_pos", "verdict"]].to_string(index=False, na_rep="-", formatters={
                   "sel_trades_per_day": "{:.2f}".format, "sel_net_per_trade": "{:+.3f}".format,
                   "sel_net_per_day": "{:+.2f}".format, "p_boot_day": "{:.4f}".format}))
    print(f"\nwrote {d / 'PRED1_report_oos.csv'}, {d / 'PRED1_report_full.csv'}, {d / 'PRED1_verdict.csv'}, "
          f"{d / 'PRED1_verdict.json'}, {d / 'PRED1_dropped.csv'}   [{time.time() - t00:.0f}s]")
    return rep_oos, rep_full, ver


# ------------------------------------------------------------------ verification
def slow_row(ctx, i, h):
    """The inputs, s and the target of the decision at bar i, written out plainly from the bar table (timestamps and
    labels, one decision at a time): an independent second computation for --verify."""
    a, ts, D = ctx.a, ctx.ts, ctx.days
    t = ts[i]
    day = pd.Timestamp(ctx.cdate[i])
    one = pd.Timedelta(minutes=1)
    dp = D.index.get_loc(day)
    i_open = int(D.i_open.iloc[dp])
    rets, k, lo = [], i, i_open
    while len(rets) < N_S:                                     # walk back through session bars
        if k > lo:
            if ts[k] - ts[k - 1] == one:
                rets.append(math.log(ctx.C[k] / ctx.C[k - 1]))
            k -= 1
        else:
            dp -= 1
            if dp < 0:
                break
            lo, k = int(D.i_open.iloc[dp]), int(D.i_end.iloc[dp])
    s = float(np.std(np.array(rets[::-1]))) if len(rets) == N_S else np.nan
    if not s > 0:
        s = np.nan
    close = float(a.close.iloc[i])
    es = ctx.extra("ES").close

    def px(series, minutes):
        v = series.get(t - minutes * one)
        return float(v) if v is not None else np.nan

    out = {}
    for w in RET_W:
        out[f"r{w}"] = math.log(close / px(a.close, w)) / (s * math.sqrt(w)) if px(a.close, w) == px(a.close, w) else np.nan
    mins = (t - ctx._wall(day, OPEN_TOD)) / one + 1
    ses = a.iloc[i_open:i + 1]
    vwap = float((((ses.high + ses.low + ses.close) / 3) * ses.volume).sum() / ses.volume.sum())
    den = close * s * math.sqrt(mins)
    out["vwap_d"], out["hi_d"], out["lo_d"] = (close - vwap) / den, (close - float(ses.high.max())) / den, (close - float(ses.low.min())) / den
    v5 = float(a.volume.loc[t - 4 * one:t].sum())                       # label slices include both ends
    v60 = float(a.volume.loc[t - 64 * one:t - 5 * one].sum())
    out["vol5"] = math.log(v5 / (v60 / 12)) if v5 > 0 and v60 > 0 else np.nan
    for w in ES_W:
        e0, e1, m1 = px(es, 0), px(es, w), px(a.close, w)
        out[f"es{w}"] = (math.log(e0 / e1) - math.log(close / m1)) / s if e0 == e0 and e1 == e1 and m1 == m1 else np.nan
    out["tod"] = mins / 390
    out["tod2"] = (mins / 390) ** 2
    dq = D.index.get_loc(day)
    prev_close = float(a.close.iloc[int(D.i_end.iloc[dq - 1])]) if dq > 0 else np.nan
    out["gap"] = (float(a.open.iloc[i_open]) - prev_close) / (close * s * math.sqrt(390))
    nxt = px(a.close, -h)
    out["s"] = s
    out["y"] = math.log(nxt / close) / (s * math.sqrt(h)) if nxt == nxt else np.nan
    return out


def _eq(a, b):
    return np.array_equal(np.asarray(a), np.asarray(b), equal_nan=True)


def verify(phase="is", out=core.OUT, n_replay=2400, n_slow=300, n_cuts=6, seed=7):
    t00 = time.time()
    a = run.bars(phase)
    ctx = core.Ctx(a)
    F = bar_features(ctx)
    decs, cnts = {}, {}
    for h in HS:
        decs[h], cnts[h] = decisions(ctx, F, h)
    rng = np.random.default_rng(seed)
    print(f"PRED1 --verify   bars {ctx.ts[0]} -> {ctx.ts[-1]}")
    fails = []

    # ---- 1. trades replayed in the harness
    try:
        bundle, js = load_models(out)
    except SystemExit as e:
        bundle = None
        fails.append("no saved models: the trade replay did not run")
        print(f"1. trade replay NOT RUN: {e}")
    if bundle is not None:
        atr = ctx.days.atr
        per = n_replay // (len(HS) * len(MODELS) * 2)
        n_done = n_bad = n_sel = 0
        by_h = {}
        for h in HS:
            d = decs[h][decs[h].ok].reset_index(drop=True)
            for model in MODELS:
                fc = forecast(bundle, model, h, d[FEATS].to_numpy(float))
                side, pts, gross, net = trade_arrays(d, fc, h)
                sel = np.flatnonzero((side != 0) & (pts >= SEL_PTS))
                al = np.flatnonzero(side != 0)
                p_sel = rng.choice(sel, size=min(per, len(sel)), replace=False) if len(sel) else np.zeros(0, int)
                rest = np.setdiff1d(al, p_sel)
                p_all = rng.choice(rest, size=min(2 * per - len(p_sel), len(rest)), replace=False)
                pick = np.r_[p_sel, p_all].astype(int)
                orders = [dict(i=int(d.i[q]), side=int(side[q]), etype="close", exit_i=int(d.k[q]),
                               r_pts=0.1 * float(atr[pd.Timestamp(d.day[q])]), tag=str(q)) for q in pick]
                got = {int(t["tag"]): t for t in core.run_orders(ctx, orders, one_at_a_time=False)}
                for q in pick:
                    t = got.get(int(q))
                    good = (t is not None and abs(t["pnl"] - net[q]) < 0.005 and t["i"] == d.i[q] and t["j"] == d.i[q]
                            and t["k"] == d.k[q] and t["reason"] == "time"
                            and t["entry"] == d.close[q] + side[q] * core.SLIP and t["exit"] == d.close_k[q] - side[q] * core.SLIP)
                    n_bad += not good
                    if not good and n_bad <= 5:
                        print(f"   MISMATCH {model} h{h} bar {ctx.ts[int(d.i[q])]} side {side[q]:+.0f}: here {net[q]:.2f}, harness "
                              f"{None if t is None else t['pnl']}")
                n_done += len(pick)
                n_sel += len(p_sel)
                by_h[h] = by_h.get(h, 0) + len(pick)
        print(f"1. {n_done} trades ({n_sel} of them sel trades; by horizon {by_h}) replayed through core.run_orders -> "
              f"core.simulate(etype='close', exit_i=the bar h minutes later): {n_done - n_bad} agree to the cent on entry, "
              f"exit, bars and net P&L, {n_bad} differ")
        if n_bad or n_done < 2000:
            fails.append(f"trade replay: {n_bad} of {n_done} differ" if n_bad else f"only {n_done} trades replayed")
        # days the harness does not trade: no decision here, and run_orders drops an order there
        D = ctx.days
        bad_days = D.index[(D.roll | D.atr.isna()).to_numpy()]
        mine = sum(int(np.isin(decs[h].day.to_numpy().astype("datetime64[D]"), bad_days.to_numpy().astype("datetime64[D]")).sum()) for h in HS)
        probe = [dict(i=int(ctx.idx(dd, "11:59")), side=1, etype="close", exit_i=int(ctx.idx(dd, "12:04")), r_pts=1.0)
                 for dd in bad_days if ctx.idx(dd, "11:59") is not None and ctx.idx(dd, "12:04") is not None]
        kept = len(core.run_orders(ctx, probe, one_at_a_time=False))
        print(f"   roll / no-ATR days: {len(bad_days)}; decisions here on those days {mine}; of {len(probe)} probe orders "
              f"on them run_orders kept {kept}")
        if mine or kept:
            fails.append("a decision on a roll / no-ATR day")

    # ---- 2. the inputs recomputed one decision at a time in plain code
    n_bad = n_rows = n_drop = 0
    worst = 0.0
    for h in HS:
        d = decs[h]
        take = np.sort(rng.choice(len(d), size=min(n_slow // len(HS), len(d)), replace=False))
        dropped = np.flatnonzero(~d.ok.to_numpy())
        take = np.unique(np.r_[take, dropped[:: max(1, len(dropped) // 15)][:15]]).astype(int)
        for q in take:
            r = d.iloc[int(q)]
            sl = slow_row(ctx, int(r.i), h)
            for kname in FEATS + ["s", "y"]:
                x, y = float(r[kname]), float(sl[kname])
                if not np.isfinite(y):
                    y = np.nan
                same = (x != x and y != y) or (x == x and y == y and abs(x - y) <= 1e-9 + 1e-7 * abs(y))
                if x == x and y == y:
                    worst = max(worst, abs(x - y))
                if not same:
                    n_bad += 1
                    if n_bad <= 8:
                        print(f"   DIFFERENT h{h} {ctx.ts[int(r.i)]} {kname}: arrays {x!r}, plain {y!r}")
            n_rows += 1
            n_drop += not r.ok
    print(f"2. {n_rows} decisions ({n_drop} of them dropped ones), {len(FEATS)} inputs + s + target each, recomputed one at a "
          f"time from the bar table: {n_bad} values differ (largest absolute difference {worst:.2e})")
    if n_bad:
        fails.append(f"plain recomputation: {n_bad} values differ")

    # ---- 3. look-ahead: bars truncated at random mid-session times, and a mirrored future
    D = ctx.days
    used = D[~(D.roll | D.atr.isna())]
    used = used[(used.index > D.index[min(40, len(D) - 1)])]
    ns_c = F["ns"]
    leak0 = np.log(ctx.C[np.minimum(F["ci"] + 5, ctx.n - 1)] / ctx.C[F["ci"]])   # a column that reads 5 bars ahead
    n_flag = n_bad_cut = 0
    cuts = []
    for q in np.sort(rng.choice(len(used), size=min(n_cuts, len(used)), replace=False)):
        day = used.index[int(q)]
        flat = int(ctx.tod[int(used.i_end.iloc[int(q)])])
        cuts.append(ctx._wall(day, int(rng.integers(FIRST_CLOSE + 5, flat))))
    for T in cuts:
        cut_ns = _ns([T])[0]
        m0 = ns_c <= cut_ns
        day_ns = _ns([T.normalize()])[0]
        on_day = int((m0 & (ns_c >= day_ns)).sum())
        # (a) truncation: nothing after T exists
        c1 = core.Ctx(a[a.index <= T])
        assert c1.ts[-1] <= T and c1.extra("ES").index.max() <= T
        F1 = bar_features(c1)
        same = _eq(F1["ns"], ns_c[m0]) and _eq(F1["X"], F["X"][m0]) and _eq(F1["s"], F["s"][m0])
        leak1 = np.log(c1.C[np.minimum(F1["ci"] + 5, c1.n - 1)] / c1.C[F1["ci"]])
        flagged = not (len(leak1) == int(m0.sum()) and _eq(leak1, leak0[m0]))
        # (b) the same timestamps with a mirrored future (prices reflected, volume halved, ES too)
        c2 = core.Ctx(a, scramble_after=T)
        F2 = bar_features(c2)
        same2 = _eq(F2["ns"], ns_c) and _eq(F2["X"][m0], F["X"][m0]) and _eq(F2["s"][m0], F["s"][m0])
        moved, n_dec, same_y = 0, 0, True
        for h in HS:
            d0 = decs[h]
            d2, _ = decisions(c2, F2, h)
            b0 = (d0.ns <= cut_ns).to_numpy()
            b2 = (d2.ns <= cut_ns).to_numpy()
            n_dec += int(b0.sum())
            cols = ["i", "k", "ns", "close", "s"] + FEATS + ["why"]
            same2 &= len(d0) == len(d2) and int(b0.sum()) == int(b2.sum()) and all(
                _eq(d0[c_][b0].to_numpy(float), d2[c_][b2].to_numpy(float)) if c_ != "why" else
                (d0[c_][b0].to_numpy() == d2[c_][b2].to_numpy()).all() for c_ in cols)
            done = b0 & ((d0.ns + h * MIN_NS) <= cut_ns).to_numpy()            # the exit bar is at or before the cut
            same_y &= _eq(d0.y[done].to_numpy(), d2.y[done].to_numpy())
            if len(d0) == len(d2):
                moved += int((~b0 & ~(np.isclose(d0[FEATS].to_numpy(), d2[FEATS].to_numpy(), equal_nan=True).all(axis=1))).sum())
        okc = same and same2 and same_y
        n_bad_cut += not okc
        n_flag += flagged
        print(f"3. cut {T.strftime('%Y-%m-%d %H:%M')}: truncated bars -> {int(m0.sum())} input rows at or before the cut "
              f"({on_day} on the cut day) {'IDENTICAL' if same else 'DIFFERENT'}; mirrored future -> {n_dec} decision rows "
              f"at or before the cut {'IDENTICAL' if same2 and same_y else 'DIFFERENT'} ({moved} later rows changed); "
              f"control column reading 5 bars ahead {'caught' if flagged else 'NOT caught'}")
    if n_bad_cut:
        fails.append(f"look-ahead: {n_bad_cut} of {len(cuts)} cuts differ")
    if n_flag < (len(cuts) + 1) // 2:
        fails.append("look-ahead test has no teeth: the control column was not caught")
    print(f"[{time.time() - t00:.0f}s]")
    if fails:
        print("FAIL  PRED1 --verify: " + "; ".join(fails))
    else:
        print(f"PASS  PRED1 --verify: trade replay to the cent, plain recomputation of the inputs, and the look-ahead test "
              f"on {len(cuts)} truncated / mirrored cuts all agree")
    return not fails


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", choices=["is", "full"])
    ap.add_argument("--verify", action="store_true")
    ap.add_argument("--dry-split", help="code test only: a made-up split date inside the data that is here")
    ap.add_argument("--dry-out", help="code test only: directory for the dry run's files")
    a = ap.parse_args()
    pd.set_option("display.width", 300)
    if a.verify:
        assert not (a.dry_split or a.dry_out)
        sys.exit(0 if verify(a.phase or "is") else 1)
    assert a.phase, "--phase is|full or --verify"
    if a.dry_split or a.dry_out:
        assert a.dry_out and (a.dry_split or a.phase == "full"), "--dry-out DIR, with --dry-split DATE for --phase is"
        o = pathlib.Path(a.dry_out).resolve()
        assert core.OUT.resolve() != o and core.OUT.resolve() not in o.parents and core.ROOT.resolve() not in o.parents, \
            "a dry run never writes inside the lab"
        if a.phase == "is":
            phase_is(out=o, split_at=a.dry_split)
        else:
            phase_full(out=o, dry=True)
        return
    if a.phase == "is":
        phase_is()
    else:
        phase_full()


if __name__ == "__main__":
    main()
