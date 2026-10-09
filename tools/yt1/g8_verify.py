#!/usr/bin/env python3
"""G8 checks (the ones quoted in notes/G8.md). Reads the signal file; changes nothing.

    python3 tools/yt1/g8_verify.py --phase is --recon       grid row vs standard harness: every s_G8 variant and 60
                                                            random combinations at 2R / 1.5R / 3R, trade by trade
    python3 tools/yt1/g8_verify.py --phase is --rc          the reality check recomputed the slow way (resampling the
                                                            day rows, numpy mean / std) against g8_grid.reality_check
    python3 tools/yt1/g8_verify.py --phase is --ref 600     every signal column recomputed by a separately written
                                                            slow reference (pandas time slices on the 1-minute bars)
                                                            on 600 random signals plus up to 60 per timeframe with each
                                                            of r_pd, r_sess, s_smt, h_h4, h_h1 true (about 3 minutes)
"""
import argparse, pathlib, sys
import numpy as np
import pandas as pd
sys.path.insert(0, str(pathlib.Path(__file__).parent))
import core, run, tt
import g8_grid, g8_signals, s_G8

TZ = core.TZ
COL = {2.0: ("net", "mR", "R20"), 1.5: ("net15", "mR15", "R15"), 3.0: ("net30", "mR30", "R30")}


def recon(ctx, sig):
    grid = g8_grid.evaluate(sig)

    def one(label, c, k):
        df = core.trades_df(s_G8.trades(ctx, c=c, k=k))
        g = grid.loc[c]
        rows = g8_grid.pick(sig, g8_grid.parse(c))
        same = np.array_equal(df.i.to_numpy(), rows.i.to_numpy()) and np.allclose(
            df.R.to_numpy(), rows[COL[k][2]].to_numpy(), atol=1e-12)
        ok = bool(len(df) == g.n and abs(df.pnl.sum() - g[COL[k][0]]) < 0.005
                  and (len(df) == 0 or abs(df.R.mean() - g[COL[k][1]]) < 1e-9) and same)
        return ok, (f"{label:<8} {c:<46} {k:>3}R  harness n {len(df):>4} net {df.pnl.sum():>+10.2f} R {df.R.mean():+.6f}"
                    f" | grid n {int(g.n):>4} net {g[COL[k][0]]:>+10.2f} R {g[COL[k][1]]:+.6f} | {'MATCH' if ok else 'DIFF'}")
    bad = 0
    for v, p in s_G8.VARIANTS.items():
        ok, line = one(v, p["c"], p["k"])
        bad += not ok
        print(line)
    rng = np.random.default_rng(7)
    samp = rng.choice(list(grid.index[grid.n > 0]), 60, replace=False)
    m = 0
    for c in samp:
        for k in (2.0, 1.5, 3.0):
            ok, line = one("rand", c, k)
            m += ok
            if not ok:
                print(line)
                bad += 1
    print(f"random combinations with trades: {m} of {len(samp) * 3} (60 combinations x 3 targets) match")
    print("total mismatches:", bad)
    return bad


def slow_rc(sig, n_boot=2000, seed=1):
    table = g8_grid.evaluate(sig)
    names = list(g8_grid.eligible(table).index)
    days, X = g8_grid._daily(sig, names)
    D = len(days)
    t_obs = np.sqrt(D) * X.mean(0) / X.std(0, ddof=1)
    Xc = X - X.mean(0)
    rng = np.random.default_rng(seed)
    mx = np.empty(n_boot)
    for b in range(n_boot):
        Y = Xc[rng.integers(0, D, size=D)]
        mx[b] = np.nanmax(np.sqrt(D) * Y.mean(0) / Y.std(0, ddof=1))
    rc = g8_grid.reality_check(sig, table, n_boot=n_boot, seed=seed)
    b = rc["boot_max_t"]
    print(f"slow : observed max t {t_obs.max():.6f}  resampled mean {mx.mean():.6f} min {mx.min():.6f} max {mx.max():.6f}"
          f" median {np.quantile(mx, .5):.6f} 95% {np.quantile(mx, .95):.6f}  p {(mx >= t_obs.max()).mean():.4f}")
    print(f"fast : observed max t {rc['t_obs_max']:.6f}  resampled mean {b['mean']:.6f} min {b['min']:.6f} max {b['max']:.6f}"
          f" median {b['q50']:.6f} 95% {b['q95']:.6f}  p {rc['p']:.4f}")
    return int(not (abs(mx.mean() - b["mean"]) < 1e-9 and abs(t_obs.max() - rc["t_obs_max"]) < 1e-9))


# ------------------------------------------------------------------ slow reference of every signal column
def _wall(d, off):
    return (pd.Timestamp(d) + pd.Timedelta(off)).tz_localize(TZ)


def _ref_htf(a, t_dec, hours, side):
    mins = hours * 60
    naive = t_dec.tz_localize(None)
    blk = naive.floor("h") if hours == 1 else (naive - pd.Timedelta(hours=2)).floor("4h") + pd.Timedelta(hours=2)
    got, tries = [], 0
    while len(got) < 3 and tries < 400:                       # walk back over clock blocks
        t0 = blk.tz_localize(TZ, nonexistent="shift_forward", ambiguous=True)
        x = a[(a.index >= t0) & (a.index < t0 + pd.Timedelta(minutes=mins))]
        if len(x) and x.index[-1] <= t_dec:                   # complete: its last bar is at or before the decision
            got.append(dict(o=x.open.iloc[0], h=x.high.max(), l=x.low.min(), c=x.close.iloc[-1], n=len(x)))
        blk -= pd.Timedelta(minutes=mins)
        tries += 1
    if len(got) < 2:
        return False
    k, p = got[0], got[1]
    half = mins / 2
    c2 = c3 = False
    if k["n"] >= half and p["n"] >= half:
        c2 = (k["l"] < p["l"] and k["c"] > p["l"]) if side > 0 else (k["h"] > p["h"] and k["c"] < p["h"])
        if len(got) == 3 and got[2]["n"] >= half:
            q = got[2]
            if side > 0:
                c3 = p["l"] < q["l"] and k["l"] >= p["l"] and k["c"] > max(p["o"], p["c"])
            else:
                c3 = p["h"] > q["h"] and k["h"] <= p["h"] and k["c"] < min(p["o"], p["c"])
    return bool(c2 or c3)


def _ref(ctx, es, B, DAILY, row):
    a = ctx.a
    tf, i, side = int(row.tf), int(row.i), int(row.side)
    t_dec = ctx.ts[i]
    d = t_dec.tz_localize(None).normalize()
    out = {}
    if tf == 1:
        o, h, l, c = ctx.O, ctx.H, ctx.L, ctx.C
        k, ifirst = i, np.arange(ctx.n)
    else:
        b = ctx.bars(tf)
        o, h, l, c = (b[x].to_numpy(float) for x in ("open", "high", "low", "close"))
        ifirst = b.i_first.to_numpy()
        k = int(np.searchsorted(b.i_last.to_numpy(), i))
        assert b.i_last.iloc[k] == i
    if side > 0:                                              # the CISD from its definition, walking back
        assert not (c[k] < o[k])
        j = k - 1
        while not (c[j] < o[j]):
            j -= 1
        e = j
        while c[j - 1] < o[j - 1]:
            j -= 1
        assert c[k] > o[j] and not (c[e + 1:k] > o[j]).any()
        prot = l[j:k + 1].min()
    else:
        assert not (c[k] > o[k])
        j = k - 1
        while not (c[j] > o[j]):
            j -= 1
        e = j
        while c[j - 1] > o[j - 1]:
            j -= 1
        assert c[k] < o[j] and not (c[e + 1:k] < o[j]).any()
        prot = h[j:k + 1].max()
    close = c[k]
    tod = t_dec.hour * 60 + t_dec.minute
    out.update(prot=prot, stop=prot - side * 0.25, entry_ref=close, a_run0=int(ifirst[j]), tod=tod,
               w_am=510 <= tod <= 659, w_open=570 <= tod <= 659, w_sb=600 <= tod <= 659, w_pm=810 <= tod <= 899)
    bb = B.loc[d] if d in B.index else None
    agree = bb is not None and int(bb.bias) == side
    out["bias"], out["kind"] = int(agree), (bb.kind if agree else "")
    e_disc = e_prem = r_pd = False
    if bb is not None and bb.kind != "roll" and bb.h1 == bb.h1:
        prev = DAILY.index[DAILY.index < d][-1]               # candle 1 from the raw bars: 18:00 -> 17:00
        x = a[(a.index >= _wall(prev, "-6h")) & (a.index < _wall(prev, "17h"))]
        h1, l1 = x.high.max(), x.low.min()
        assert h1 == bb.h1 and l1 == bb.l1
        eq = (h1 + l1) / 2
        if side > 0:
            e_disc, e_prem, r_pd = close < eq, close > eq, (prot < l1 and close > l1)
        else:
            e_disc, e_prem, r_pd = close > eq, close < eq, (prot > h1 and close < h1)
    out["e_disc"], out["e_prem"], out["r_pd"] = bool(e_disc), bool(e_prem), bool(r_pd)
    op = a[(a.index >= _wall(d, "-6h")) & (a.index <= t_dec)].open.iloc[0]
    out["o_below"] = bool(close < op) if side > 0 else bool(close > op)
    ss = a[(a.index >= _wall(d, "-6h")) & (a.index < _wall(d, "8h30min"))]
    out["r_sess"] = bool(len(ss) and ((prot < ss.low.min() and close > ss.low.min()) if side > 0 else
                                      (prot > ss.high.max() and close < ss.high.max())))
    out["h_h1"], out["h_h4"] = _ref_htf(a, t_dec, 1, side), _ref_htf(a, t_dec, 4, side)
    t0 = ctx.ts[out["a_run0"]]
    nq_run = a[(a.index >= t0) & (a.index <= t_dec)]
    nq_ref = a[(a.index >= t0 - pd.Timedelta(minutes=120)) & (a.index < t0)]
    es_run = es[(es.index >= t0) & (es.index <= t_dec)]
    es_ref = es[(es.index >= t0 - pd.Timedelta(minutes=120)) & (es.index < t0)]
    smt = False
    if len(nq_ref) and nq_run.index.isin(es.index).all() and nq_ref.index.isin(es.index).all():
        if side > 0:
            assert nq_run.low.min() == prot
            smt = (nq_run.low.min() < nq_ref.low.min()) != (es_run.low.min() < es_ref.low.min())
        else:
            assert nq_run.high.max() == prot
            smt = (nq_run.high.max() > nq_ref.high.max()) != (es_run.high.max() > es_ref.high.max())
    out["s_smt"] = bool(smt)
    return out


def reference(ctx, sig, n=600, seed=11):
    es, B, DAILY = ctx.extra("ES"), tt.bias(ctx), tt.daily(ctx)
    rng = np.random.default_rng(seed)
    idx = set(rng.choice(len(sig), min(n, len(sig)), replace=False).tolist())
    for col in ("r_pd", "r_sess", "s_smt", "h_h4", "h_h1"):
        for tf in (1, 5, 15):
            m = np.flatnonzero((sig[col] & (sig.tf == tf)).to_numpy())
            idx |= set(rng.choice(m, min(60, len(m)), replace=False).tolist())
    cols = ["tod", "entry_ref", "prot", "stop", "a_run0", "w_am", "w_open", "w_sb", "w_pm", "bias", "kind", "e_disc",
            "e_prem", "o_below", "r_pd", "r_sess", "h_h1", "h_h4", "s_smt"]
    bad = {c: 0 for c in cols}
    for q in sorted(idx):
        row = sig.iloc[q]
        r = _ref(ctx, es, B, DAILY, row)
        for c in cols:
            if r[c] != row[c]:
                bad[c] += 1
                if bad[c] <= 3:
                    print("DIFF", c, "tf", row.tf, row.time, "side", row.side, "stored", row[c], "reference", r[c])
    s = sig.iloc[sorted(idx)]
    print(f"{len(idx)} signals compared ({s.groupby('tf').size().to_dict()}); differences per column: {bad}")
    print("true counts in the sample:", {c: int(s[c].sum()) for c in cols if sig[c].dtype == bool})
    return sum(bad.values())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", choices=["is", "full"], default="is")
    ap.add_argument("--recon", action="store_true")
    ap.add_argument("--rc", action="store_true")
    ap.add_argument("--ref", type=int, default=0)
    a = ap.parse_args()
    sig = pd.read_parquet(g8_signals.path(a.phase))
    bad = 0
    if a.recon or a.ref:
        ctx = core.Ctx(run.bars(a.phase))
    if a.recon:
        bad += recon(ctx, sig)
    if a.rc:
        bad += slow_rc(sig)
    if a.ref:
        bad += reference(ctx, sig, a.ref)
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
