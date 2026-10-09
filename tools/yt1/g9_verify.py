#!/usr/bin/env python3
"""G9 checks (the ones quoted in notes/G9.md). Reads the signal file; changes nothing.

    python3 tools/yt1/g9_verify.py --cols         the columns shared with g8_signals equal G8's for every signal of
                                                  the am / open / sb / pm windows (against is/G8_signals.parquet)
    python3 tools/yt1/g9_verify.py --yt5          the 5,184 YT5 combinations (is/G8_grid.csv) against the matching
                                                  YT6 combinations (M from O, X 2R, N close)
    python3 tools/yt1/g9_verify.py --ref 600      every NEW column recomputed by a separately written slow reference
                                                  (pandas time slices on the 1-minute bars) on 600 random signals
                                                  plus up to 40 per timeframe with each new column true; the YT5
                                                  columns of the same signals against g8_verify's slow reference
    python3 tools/yt1/g9_verify.py --recon        grid row vs standard harness: every s_G9 variant, and 63 random
                                                  combinations (7 per target x entry pair) trade by trade
    python3 tools/yt1/g9_verify.py --rc           the reality check: float64 against float32 chunks on a subset, the
                                                  slow resampling of day rows, and G8's numbers on the YT5 subset
    python3 tools/yt1/g9_verify.py --hand         the bars behind the hand checks of notes/G9.md
"""
import argparse, pathlib, sys, time
import numpy as np
import pandas as pd
sys.path.insert(0, str(pathlib.Path(__file__).parent))
import core, run, tt
import g8_grid, g8_signals, g8_verify
import g9_grid, g9_signals, s_G9

TZ = core.TZ
ocol = g9_signals.ocol


# ------------------------------------------------------------------ YT5 reproduction
def cols_vs_g8(sig):
    g8 = pd.read_parquet(g8_signals.path("is"))
    s = sig[~sig.w_ldn]
    key = ["tf", "i", "side"]
    assert not s.duplicated(key).any() and not g8.duplicated(key).any()
    m = g8.merge(s, on=key, how="outer", suffixes=("_8", "_9"), indicator=True)
    print(f"G8 signals {len(g8)}   G9 signals outside the London window {len(s)}   matched on (tf, i, side) "
          f"{int((m._merge == 'both').sum())}   only G8 {int((m._merge == 'left_only').sum())}   only G9 "
          f"{int((m._merge == 'right_only').sum())}")
    bad = int((m._merge != "both").sum())
    pairs = [(c, c) for c in ("date", "time", "tod", "entry_ref", "prot", "stop", "w_am", "w_open", "w_sb", "w_pm",
                              "bias", "kind", "e_disc", "e_prem", "r_pd", "r_sess", "h_h1", "h_h4", "s_smt",
                              "a_eq", "a_pd", "a_sess", "a_run0", "a_nq_ref", "a_es_run", "a_es_ref", "tradable",
                              "day_ok")]
    out = {}
    for c8, c9 in pairs:
        a, b = m[c8 + "_8"], m[c9 + "_9"]
        if a.dtype.kind == "f":
            d = int((~((a == b) | (a.isna() & b.isna()))).sum())
        else:
            d = int((a.astype(str) != b.astype(str)).sum())
        out[c8] = d
    for c8, c9 in (("o_below", "m_d18"), ("a_open", "a_open18"), ("R20", ocol("R", "2R", "close")),
                   ("pnl20", ocol("pnl", "2R", "close"))):
        a, b = m[c8], m[c9]
        out[f"{c8}={c9}"] = int((~((a == b) | (a.isna() & b.isna()))).sum())
    print("differences per column:", out)
    bad += sum(out.values())
    print("YT5 columns:", "IDENTICAL for every signal" if bad == 0 else f"{bad} DIFFERENCES")
    return bad


def yt5_vs_grid(sig):
    old = g8_grid.read_grid(core.OUT / "is" / "G8_grid.csv")
    new = g9_grid.evaluate(sig)
    assert len(old) == 5184
    mmap = {"none": "none", "below": "d18"}
    n_ok, bad = 0, []
    for nm, r in old.iterrows():
        c = dict(T=int(r["T"]), W=r["W"], B=r["B"], E=r["E"], M=mmap[r["O"]], R=r["R"], H=r["H"], S=r["S"], X="2R",
                 N="close")
        g = new.loc[g9_grid.name(c)]
        same = int(g.n) == int(r.n) and int(g.orders) == int(r.n) and abs(g.net - r.net) < 0.005
        for a, b in ((g.mR, r.mR), (g.sd, r.sd), (g.t, r.t), (g.win, r.win)):
            same &= (a != a and b != b) or abs(a - b) < 1e-12
        for y in (2019, 2020, 2021, 2022):
            same &= abs(g[f"y{y}"] - r[f"y{y}"]) < 0.005
        if same:
            n_ok += 1
        else:
            bad.append(nm)
    print(f"YT5 combinations reproduced by the matching YT6 combination (n, orders, net $, mean R, sd, t, win %, net by "
          f"year): {n_ok} of {len(old)}")
    for nm in bad[:10]:
        print("  DIFF", nm)
    return len(bad)


# ------------------------------------------------------------------ slow reference of the new columns
def _wall(d, off):
    return (pd.Timestamp(d) + pd.Timedelta(off)).tz_localize(TZ)


def _ref9(ctx, B, DAILY, row):
    a = ctx.a
    tf, i, side = int(row.tf), int(row.i), int(row.side)
    t_dec = ctx.ts[i]
    d = t_dec.tz_localize(None).normalize()
    tod = t_dec.hour * 60 + t_dec.minute
    ldn = 120 <= tod <= 299
    out = {"w_ldn": ldn}
    # the opening price the CISD closed through: walk back from the signal bar
    if tf == 1:
        o, c, k = ctx.O, ctx.C, i
    else:
        b = ctx.bars(tf)
        o, c = b.open.to_numpy(float), b.close.to_numpy(float)
        k = int(np.searchsorted(b.i_last.to_numpy(), i))
    j = k - 1
    if side > 0:
        while not (c[j] < o[j]):
            j -= 1
        while c[j - 1] < o[j - 1]:
            j -= 1
    else:
        while not (c[j] > o[j]):
            j -= 1
        while c[j - 1] > o[j - 1]:
            j -= 1
    out["rt_px"] = o[j]
    close, prot, stop = float(row.entry_ref), float(row.prot), float(row.stop)
    R = abs(close - stop)
    today = a[(a.index >= _wall(d, "-6h")) & (a.index <= t_dec)]
    o18 = today.open.iloc[0]
    x = a[(a.index >= _wall(d, "0h")) & (a.index <= t_dec)]
    o00 = x.open.iloc[0] if len(x) else np.nan
    x = a[(a.index >= _wall(d, "8h30min")) & (a.index <= t_dec)]
    o830 = x.open.iloc[0] if len(x) else np.nan
    below = (lambda lv: bool(close < lv)) if side > 0 else (lambda lv: bool(close > lv))
    out["m_d18"], out["m_mid"] = below(o18), below(o00)
    out["m_both"] = below(o00) and below(o830)
    ss = a[(a.index >= _wall(d, "-6h")) & (a.index < _wall(d, "2h" if ldn else "8h30min"))]
    s_hi, s_lo = (ss.high.max(), ss.low.min()) if len(ss) else (np.nan, np.nan)
    bb = B.loc[d] if d in B.index else None
    h1 = l1 = np.nan
    if bb is not None and bb.kind != "roll" and bb.h1 == bb.h1:
        prev = DAILY.index[DAILY.index < d][-1]               # cand1 from the raw bars: 18:00 -> 17:00
        x = a[(a.index >= _wall(prev, "-6h")) & (a.index < _wall(prev, "17h"))]
        h1, l1 = x.high.max(), x.low.min()
    eq = (h1 + l1) / 2
    if side > 0:
        out["r_sess"] = bool(prot < s_lo and close > s_lo)
        out["r_pd_brk"], out["r_sess_brk"] = bool(prot > h1), bool(prot > s_hi)
        cand = [h1, s_hi, today.high.max()]
    else:
        out["r_sess"] = bool(prot > s_hi and close < s_hi)
        out["r_pd_brk"], out["r_sess_brk"] = bool(prot < l1), bool(prot < s_lo)
        cand = [l1, s_lo, today.low.min()]
    out["x_pdx"] = cand[0]
    for mult, tag in g9_signals.MD:
        far = [(lv - close) * side for lv in cand]
        out["q_pdx_" + tag] = bool(far[0] >= mult * R)
        okc = [(f, n) for n, f in enumerate(far) if f >= mult * R]
        out["q_liq_" + tag] = bool(okc)
        out["x_liq_" + tag] = cand[min(okc)[1]] if okc else np.nan
    # B inv: an hour candle completed since 18:00 closed beyond EQ against the bias; the trade is against the bias
    inv = False
    bias = int(bb.bias) if bb is not None else 0
    if bias != 0 and side == -bias:
        h = _wall(d, "-6h")
        while h <= t_dec:
            x = a[(a.index >= h) & (a.index < h + pd.Timedelta(hours=1))]
            if len(x) >= 30 and x.index[-1] <= t_dec:
                cl = x.close.iloc[-1]
                inv |= bool(cl < eq) if bias > 0 else bool(cl > eq)
            h += pd.Timedelta(hours=1)
    out["b_inv"] = inv
    return out


def reference(ctx, sig, n=600, seed=11):
    es, B, DAILY = ctx.extra("ES"), tt.bias(ctx), tt.daily(ctx)
    rng = np.random.default_rng(seed)
    idx = set(rng.choice(len(sig), min(n, len(sig)), replace=False).tolist())
    new = ["b_inv", "m_mid", "m_both", "r_sess", "r_pd_brk", "r_sess_brk"]
    for col in new + ["w_ldn"]:
        for tf in (1, 5, 15):
            m = np.flatnonzero((sig[col] & (sig.tf == tf)).to_numpy())
            idx |= set(rng.choice(m, min(40, len(m)), replace=False).tolist())
    for col in ("q_pdx_100", "q_liq_100", "q_liq_150"):                 # ... and false
        for tf in (1, 5, 15):
            m = np.flatnonzero((~sig[col] & (sig.tf == tf)).to_numpy())
            idx |= set(rng.choice(m, min(40, len(m)), replace=False).tolist())
    cols9 = ["w_ldn", "rt_px", "m_d18", "m_mid", "m_both", "r_sess", "r_pd_brk", "r_sess_brk", "b_inv", "x_pdx",
             "q_pdx_075", "q_pdx_100", "q_pdx_150", "x_liq_075", "x_liq_100", "x_liq_150", "q_liq_075", "q_liq_100",
             "q_liq_150"]
    cols8 = ["tod", "entry_ref", "prot", "stop", "a_run0", "bias", "kind", "e_disc", "e_prem", "r_pd", "h_h1", "h_h4",
             "s_smt"]
    bad = {c: 0 for c in cols9 + cols8}
    for q in sorted(idx):
        row = sig.iloc[q]
        r = _ref9(ctx, B, DAILY, row)
        for c in cols9:
            a, b = r[c], row[c]
            if not (a == b or (a != a and b != b)):
                bad[c] += 1
                if bad[c] <= 3:
                    print("DIFF", c, "tf", row.tf, row.time, "side", row.side, "stored", b, "reference", a)
        r8 = g8_verify._ref(ctx, es, B, DAILY, row)
        for c in cols8:
            if r8[c] != row[c]:
                bad[c] += 1
                if bad[c] <= 3:
                    print("DIFF", c, "tf", row.tf, row.time, "side", row.side, "stored", row[c], "reference", r8[c])
    s = sig.iloc[sorted(idx)]
    print(f"{len(idx)} signals compared ({s.groupby('tf').size().to_dict()}; {int(s.w_ldn.sum())} in the London window); "
          f"differences per column: {bad}")
    print("true counts in the sample:", {c: int(s[c].sum()) for c in cols9 + cols8 if sig[c].dtype == bool})
    return sum(bad.values())


# ------------------------------------------------------------------ grid row against the standard harness
def _one(ctx, sig, grid, label, c, nb=0):
    """Harness trades of (c, nb) against the grid side. nb = 0: the grid row and the outcome columns, trade by trade.
    nb > 0 (not a grid row): the orders of g9_grid.pick at the neighbour's distance / multiple simulated one by one
    with core.simulate (no run_orders)."""
    df = core.trades_df(s_G9.trades(ctx, c=c, nb=nb))
    dec = np.array([int(t.rsplit("|", 1)[1]) for t in df.tag], dtype=np.int64)
    combo, k, md = s_G9.params(c, nb)
    if nb == 0:
        g = grid.loc[c]
        tr = g9_grid.trades_of(sig, combo)
        gi, gR, gn, gnet, gmR = tr.i.to_numpy(), tr.R.to_numpy(), int(g.n), float(g.net), float(g.mR)
    else:
        rows = g9_grid.pick(sig, combo, md=md)
        gi, gR, pn = [], [], []
        for r in rows.itertuples(index=False):
            o = g9_signals.order_of(ctx, r, combo["X"], combo["N"], k=k, md=md, exit_i=int(r.exit_i))
            t = core.simulate(ctx, **o) if o is not None else None
            if t is not None:
                gi.append(r.i), gR.append(t["R"]), pn.append(t["pnl"])
        gi, gR = np.array(gi, dtype=np.int64), np.array(gR)
        gn, gnet, gmR = len(gi), float(np.sum(pn)), float(np.mean(gR)) if len(gi) else float("nan")
    same = np.array_equal(dec, gi) and np.allclose(df.R.to_numpy(), gR, atol=1e-12, rtol=0)
    ok = bool(len(df) == gn and abs(df.pnl.sum() - gnet) < 0.005 and (len(df) == 0 or abs(df.R.mean() - gmR) < 1e-9) and same)
    hm = df.R.mean() if len(df) else float("nan")
    return ok, (f"{label:<7} {c:<56} {s_G9.nb_label(c, nb):<13} harness n {len(df):>4} net {df.pnl.sum():>+10.2f} R {hm:+.6f}"
                f" | grid n {gn:>4} net {gnet:>+10.2f} R {gmR:+.6f} | {'MATCH' if ok else 'DIFF'}")


def recon(ctx, sig):
    grid = g9_grid.evaluate(sig)
    bad = 0
    for v, p in s_G9.VARIANTS.items():
        ok, line = _one(ctx, sig, grid, v, p["c"], p["nb"])
        bad += not ok
        print(line, flush=True)
        f = core.OUT / "is" / f"G9_{v}.csv"                    # what the standard runner wrote, if it has been run
        if f.exists() and p["nb"] == 0:
            d = pd.read_csv(f)
            g = grid.loc[p["c"]]
            if not (len(d) == g.n and abs(d.pnl.sum() - g.net) < 0.005):
                bad += 1
                print(f"   run.py file {f.name}: n {len(d)} net {d.pnl.sum():+.2f}  DIFFERS from the grid row")
    rng = np.random.default_rng(7)
    m = tot = 0
    for X in g9_grid.LEVELS["X"]:
        for N in g9_grid.LEVELS["N"]:
            pool = list(grid.index[(grid.n > 0) & (grid.X == X) & (grid.N == N)])
            for c in rng.choice(pool, 7, replace=False):
                ok, line = _one(ctx, sig, grid, "rand", c)
                tot += 1
                m += ok
                if not ok:
                    print(line)
                    bad += 1
    print(f"random combinations with trades, 7 per target x entry pair, trade by trade: {m} of {tot} match")
    print("total mismatches:", bad)
    return bad


# ------------------------------------------------------------------ reality check
def rc_checks(sig):
    table = g9_grid.evaluate(sig)
    sc = g9_grid.Scan(sig)
    e = g9_grid.eligible(table)
    bad = 0
    # 1. the YT5 subset in float64 against the numbers G8 stored (same statistic, same days, same draws)
    old = g8_grid.read_grid(core.OUT / "is" / "G8_grid.csv")
    eo = g8_grid.eligible(old)
    mmap = {"none": "none", "below": "d18"}
    names = [g9_grid.name(dict(T=int(r["T"]), W=r["W"], B=r["B"], E=r["E"], M=mmap[r["O"]], R=r["R"], H=r["H"], S=r["S"],
                               X="2R", N="close")) for _, r in eo.iterrows()]
    rc = g9_grid.reality_check(sig, table, scan=sc, names=names, dtype=np.float64)
    import json
    g8rc = json.loads((core.OUT / "is" / "G8_reality.json").read_text())
    b, b8 = rc["boot_max_t"], g8rc["boot_max_t"]
    same = (rc["n_days"] == g8rc["n_days"] and abs(rc["t_obs_max"] - g8rc["t_obs_max"]) < 1e-9
            and all(abs(b[k] - b8[k]) < 1e-9 for k in b8) and rc["p"] == g8rc["p"])
    print(f"YT5 subset ({len(names)} combinations, float64): days {rc['n_days']}  observed {rc['t_obs_max']:.6f}  resampled "
          f"mean {b['mean']:.6f} median {b['q50']:.6f} 95% {b['q95']:.6f}  p {rc['p']:.4f}   G8 stored: observed "
          f"{g8rc['t_obs_max']:.6f} mean {b8['mean']:.6f} median {b8['q50']:.6f} 95% {b8['q95']:.6f} p {g8rc['p']:.4f}"
          f"   -> {'IDENTICAL' if same else 'DIFFERENT'}")
    bad += not same
    # 1b. the whole eligible set in float64 against the stored float32 result
    import json as _json
    st = _json.loads((core.OUT / "is" / "G9_reality.json").read_text())
    f64 = g9_grid.reality_check(sig, table, scan=sc, dtype=np.float64)
    b, bs = f64["boot_max_t"], st["boot_max_t"]
    print(f"all {f64['n_eligible']} eligible in float64 ({f64['matrix_MB']} MB, {f64['seconds']}s): observed {f64['t_obs_max']:.6f} "
          f"median {b['q50']:.6f} 95% {b['q95']:.6f} p {f64['p']:.4f}   stored (float32): observed {st['t_obs_max']:.6f} median "
          f"{bs['q50']:.6f} 95% {bs['q95']:.6f} p {st['p']:.4f}")
    bad += not (abs(f64["t_obs_max"] - st["t_obs_max"]) < 1e-5 and abs(b["q50"] - bs["q50"]) < 1e-3 and f64["p"] == st["p"])
    # 2. float32 chunks against float64 and against the slow resampling of day rows, on a random subset of eligible
    rng = np.random.default_rng(3)
    sub = list(rng.choice(e.index, min(3000, len(e)), replace=False))
    r32 = g9_grid.reality_check(sig, table, scan=sc, names=sub, dtype=np.float32, chunk=1024, return_max=True)
    r64 = g9_grid.reality_check(sig, table, scan=sc, names=sub, dtype=np.float64, chunk=1024, return_max=True)
    days, X = g9_grid._daily(sc, table, sub, np.float64)
    D = len(days)
    t_obs = np.sqrt(D) * X.mean(0) / X.std(0, ddof=1)
    Xc = X - X.mean(0)
    rs = np.random.default_rng(1)
    nslow = 300
    mx = np.empty(nslow)
    for q in range(nslow):
        Y = Xc[rs.integers(0, D, size=D)]
        mx[q] = np.nanmax(np.sqrt(D) * Y.mean(0) / Y.std(0, ddof=1))
    d1 = float(np.abs(r64["_mx"][:nslow] - mx).max())
    d2 = float(np.abs(r32["_mx"] - r64["_mx"]).max())
    d3 = float(np.abs(r64["_t_obs"] - t_obs).max())
    print(f"subset of {len(sub)} eligible combinations: slow resampling of day rows (first {nslow} resamples) vs float64 "
          f"chunks: largest difference in the resample's max t {d1:.2e}; observed t {d3:.2e}; float32 vs float64 over "
          f"2000 resamples: {d2:.2e}; p float32 {r32['p']:.4f} float64 {r64['p']:.4f}")
    bad += not (d1 < 1e-9 and d3 < 1e-6 and d2 < 1e-3 and r32["p"] == r64["p"])
    return int(bad)


# ------------------------------------------------------------------ hand checks: the bars behind a signal
def _bars(ctx, lo, hi, tf=1):
    """1-minute bars lo..hi (indices, inclusive) as text; tf > 1: the tf-minute bars whose last minute is in there."""
    if tf == 1:
        x = ctx.a.iloc[lo:hi + 1][["open", "high", "low", "close"]]
    else:
        b = ctx.bars(tf)
        x = b[(b.i_last >= lo) & (b.i_last <= hi)][["open", "high", "low", "close"]]
    return "\n".join(f"      {t.strftime('%m-%d %H:%M')}  o {r.open:.2f}  h {r.high:.2f}  l {r.low:.2f}  c {r.close:.2f}"
                     for t, r in x.iterrows())


def _ext(ctx, lo, hi):
    """(high, its time, low, its time) of 1-minute bars lo..hi-1."""
    h, l = ctx.H[lo:hi], ctx.L[lo:hi]
    return (h.max(), ctx.ts[lo + int(h.argmax())].strftime("%m-%d %H:%M"), l.min(),
            ctx.ts[lo + int(l.argmin())].strftime("%m-%d %H:%M"))


def explain(ctx, sig, row, pairs=(), title=""):
    """Prints the raw bars and levels behind one signal row, and the simulated trade of each (X, N) in `pairs`."""
    B = tt.bias(ctx)
    i, side, tf = int(row.i), int(row.side), int(row.tf)
    d = pd.Timestamp(row.date)
    L = side > 0
    print(f"\n=== {title}\n    {tf}m {'long' if L else 'short'}  decision bar {ctx.ts[i]}  close {row.entry_ref:.2f}  protected "
          f"{'low' if L else 'high'} {row.prot:.2f}  stop {row.stop:.2f}  R {abs(row.entry_ref - row.stop):.2f}  rt_px {row.rt_px:.2f}"
          f"  windows: {[w for w in ('ldn', 'am', 'open', 'sb', 'pm') if row['w_' + w]]}")
    print(f"    the run ({tf}m bars from the run's first candle to the CISD bar):")
    print(_bars(ctx, int(row.a_run0), i, tf))
    bb = B.loc[d] if d in B.index else None
    if bb is not None:
        print(f"    tt.bias {d.date()}: bias {int(bb.bias)} kind '{bb.kind}'  cand1 high {bb.h1:.2f} low {bb.l1:.2f}  EQ "
              f"{(bb.h1 + bb.l1) / 2:.3f}   cand2 high {bb.h2:.2f} low {bb.l2:.2f}  cand1 close {bb.c1:.2f}")
    i18 = int(np.searchsorted(ctx.tdate, np.datetime64(d, "D"), "left"))
    cut = ctx.span(d, 120, 120)[0] if row.w_ldn else ctx.span(d, 510, 510)[0]
    sh, sht, sl, slt = _ext(ctx, i18, cut)
    dh, dht, dl, dlt = _ext(ctx, i18, i + 1)
    print(f"    trading day opens {ctx.ts[i18].strftime('%m-%d %H:%M')} at {ctx.O[i18]:.2f}   session range to "
          f"{'01:59' if row.w_ldn else '08:29'}: high {sh:.2f} ({sht}) low {sl:.2f} ({slt})   today's range through the decision "
          f"bar: high {dh:.2f} ({dht}) low {dl:.2f} ({dlt})")
    for hm, lab in ((0, "00:00"), (510, "08:30")):
        z = ctx.span(d, hm, hm)[0]
        if z < ctx.n and ctx.cdate[z] == np.datetime64(d, "D"):
            print(f"    first bar at or after {lab}: {ctx.ts[z].strftime('%H:%M')} open {ctx.O[z]:.2f}"
                  + ("" if z <= i else "   (after the decision bar: not known)"))
    if bb is not None and int(bb.bias) != 0:
        X1 = g8_signals._htf(ctx, 1)
        ks = np.flatnonzero((X1["i_first"] >= i18) & (X1["i_last"] <= i))
        print("    completed hour candles since 18:00 (close, minutes): "
              + "  ".join(f"{ctx.ts[X1['i_first'][k]].strftime('%H')}h {X1['c'][k]:.2f}({X1['n'][k]})" for k in ks))
    cols = ["bias", "kind", "b_inv", "e_disc", "e_prem", "m_d18", "m_mid", "m_both", "r_pd", "r_sess", "r_pd_brk",
            "r_sess_brk", "h_h1", "h_h4", "s_smt", "x_pdx", "q_pdx_075", "q_pdx_100", "q_pdx_150", "x_liq_075",
            "x_liq_100", "x_liq_150", "a_liq_src_100"]
    print("    stored: " + "  ".join(f"{c} {row[c]}" for c in cols))
    ex = g9_signals.exit_of(ctx, row.date, row.w_ldn)
    for X, N in pairs:
        if X != "2R" and not row[f"q_{X}_100"]:
            print(f"    {X} x {N}: the signal does not qualify for {X}")
            continue
        o = g9_signals.order_of(ctx, row, X, N, exit_i=ex)
        if o is None:
            j = g9_signals.pos_bar(ctx, i)
            print(f"    {X} x {N}: no order - the stop price traded before the hour opened; bars after the decision bar to "
                  f"the bar before {ctx.ts[j].strftime('%H:%M')}:")
            hit = i + 1 + int(np.argmax((ctx.L[i + 1:j] <= row.stop) if L else (ctx.H[i + 1:j] >= row.stop)))
            print(_bars(ctx, i + 1, min(hit, i + 6)) + ("\n      ..." if hit > i + 6 else ""))
            if hit > i + 6:
                print(_bars(ctx, hit, hit))
            continue
        t = core.simulate(ctx, **o)
        od = {k: (ctx.ts[v].strftime("%H:%M") if k in ("i", "expire", "exit_i") else v) for k, v in o.items()}
        print(f"    {X} x {N}: order {od}")
        if t is None:
            last = min(o.get("expire", o["i"] + 1), o["i"] + 31)
            print(f"      -> no fill.  bars {ctx.ts[o['i'] + 1].strftime('%H:%M')}-{ctx.ts[last].strftime('%H:%M')}: lowest low "
                  f"{ctx.L[o['i'] + 1:last + 1].min():.2f}  highest high {ctx.H[o['i'] + 1:last + 1].max():.2f}; first bar:")
            print(_bars(ctx, o["i"] + 1, o["i"] + 1))
        else:
            print(f"      -> fill {t['entry_time'].strftime('%H:%M')} at {t['entry']:.2f}, exit {t['exit_time'].strftime('%H:%M')} at "
                  f"{t['exit']:.2f} ({t['reason']}), pnl {t['pnl']:+.2f}, R {t['R']:+.4f}   stored R {row[ocol('R', X, N)]:+.4f}"
                  f" pnl {row[ocol('pnl', X, N)]:+.2f}; fill bar and exit bar:")
            print(_bars(ctx, t["j"], t["j"]))
            print(_bars(ctx, t["k"], t["k"]))


def hand(ctx, sig):
    """The signals of the hand checks in notes/G9.md: one draw (numpy default_rng(2026)) per description below, among
    the tradable signals."""
    rng = np.random.default_rng(2026)
    s = sig[sig.tradable]
    f = lambda X, N: s[ocol("f", X, N)]
    R = (s.entry_ref - s.stop).abs()
    stop_gap = pd.Series(False, index=s.index)                      # a bar opens at / through the stop while the limit rests
    ns = g9_signals._nsx(ctx)
    for q, r in s[~f("2R", "retest")].iterrows():
        e = int(np.searchsorted(ns, ns[r.i] + 30 * g9_signals.MIN_NS, "right")) - 1
        e = min(e, int(r.exit_i))
        if e > r.i:
            stop_gap[q] = bool(((ctx.O[r.i + 1:e + 1] <= r.stop) if r.side > 0 else (ctx.O[r.i + 1:e + 1] >= r.stop)).any())
    print(f"retest orders (2R) not filled: {int((~f('2R', 'retest')).sum())} of {len(s)}; of these, cancelled because a bar "
          f"opened at or through the stop price before the limit filled: {int(stop_gap.sum())}")
    jpos = np.array([g9_signals.pos_bar(ctx, int(i)) or -1 for i in s.i])
    beyond = pd.Series(False, index=s.index)                        # pos x level target: the hour opens at / beyond the target
    m = (s.q_liq_100 & ~f("liq", "pos") & f("2R", "pos")).to_numpy()
    beyond[s.index[m]] = True
    print(f"positional orders: not placed or not filled at 2R {int((~f('2R', 'pos')).sum())} of {len(s)}; with a liq target, "
          f"cancelled because the hour opened at or beyond the target: {int(beyond.sum())}; with a pdx target: "
          f"{int((s.q_pdx_100 & ~f('pdx', 'pos') & f('2R', 'pos')).sum())}")
    against = (s.a_dbias != 0) & (s.side == -s.a_dbias)
    cases = [
        ("1  b_inv TRUE (5m, sb window)", s.b_inv & (s.tf == 5) & s.w_sb, (("2R", "close"),)),
        ("2  b_inv FALSE although the trade is against a daily bias (5m, sb window)", ~s.b_inv & against & (s.tf == 5) & s.w_sb, ()),
        ("3  m_mid TRUE, m_both FALSE (am window)", s.m_mid & ~s.m_both & s.w_am & (s.tf == 5), ()),
        ("4  m_both TRUE; pdx does not qualify (pm window)", s.m_both & s.w_pm & ~s.q_pdx_100 & (s.tf == 15), (("pdx", "close"),)),
        ("5  m_mid FALSE; r_pd_brk TRUE (5m, open window, h_h1)", ~s.m_mid & s.r_pd_brk & s.h_h1 & s.w_open & (s.tf == 5), (("2R", "close"),)),
        ("6  r_sess_brk TRUE (1m, open window); positional entry at 2R", s.r_sess_brk & s.w_open & (s.tf == 1) & f("2R", "pos"), (("2R", "pos"),)),
        ("7  r_sess_brk FALSE and r_pd_brk FALSE; positional order cancelled by the stop (1m, open)", ~s.r_sess_brk & ~s.r_pd_brk & s.w_open & (s.tf == 1) & ~f("2R", "pos"), (("2R", "pos"),)),
        ("8  London window: r_sess TRUE on the 18:00-01:59 range; liq target, retest fill", s.w_ldn & s.r_sess & s.q_liq_100 & f("liq", "retest") & (s.tf == 1), (("liq", "retest"),)),
        ("9  London window: r_sess_brk TRUE on the 18:00-01:59 range (15m); the 08:29 exit", s.w_ldn & s.r_sess_brk & (s.tf == 15), (("2R", "close"),)),
        ("10 liq target = the session high / low, not cand1's (am window); retest not filled in 30 minutes", s.q_liq_100 & (s.a_liq_src_100 == 1) & s.w_am & ~f("liq", "retest") & ~stop_gap & (s.tf == 5), (("liq", "retest"), ("liq", "close"))),
        ("11 liq target = today's high / low (the nearest of three that qualify)", s.q_liq_100 & (s.a_liq_src_100 == 2) & s.q_pdx_100 & s.w_am & (s.tf == 15), (("liq", "close"),)),
        ("12 retest cancelled: a bar opens at or through the stop before the limit fills", stop_gap, (("2R", "retest"),)),
        ("13 positional with a level target: the hour opens at or beyond the target", beyond & (s.tf == 5), (("liq", "pos"), ("2R", "pos"))),
        ("14 pdx x retest fill (15m, am, s_smt)", s.s_smt & s.w_am & (s.tf == 15) & s.q_pdx_100 & f("pdx", "retest"), (("pdx", "retest"),)),
    ]
    for title, m, pairs in cases:
        pool = s[m.to_numpy()]
        if not len(pool):
            print(f"\n=== {title}: no such signal")
            continue
        row = pool.iloc[int(rng.integers(0, len(pool)))]
        explain(ctx, sig, row, pairs, f"{title}   [{len(pool)} such signals]")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", choices=["is", "full"], default="is")
    ap.add_argument("--cols", action="store_true")
    ap.add_argument("--yt5", action="store_true")
    ap.add_argument("--recon", action="store_true")
    ap.add_argument("--rc", action="store_true")
    ap.add_argument("--ref", type=int, default=0)
    ap.add_argument("--hand", action="store_true")
    a = ap.parse_args()
    pd.set_option("display.width", 250)
    sig = pd.read_parquet(g9_signals.path(a.phase))
    bad = 0
    t0 = time.time()
    if a.recon or a.ref or a.hand:
        ctx = core.Ctx(run.bars(a.phase))
    if a.cols:
        bad += cols_vs_g8(sig)
    if a.yt5:
        bad += yt5_vs_grid(sig)
    if a.ref:
        bad += reference(ctx, sig, a.ref)
    if a.recon:
        bad += recon(ctx, sig)
    if a.rc:
        bad += rc_checks(sig)
    if a.hand:
        hand(ctx, sig)
    print(f"[{time.time() - t0:.0f}s]")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
