#!/usr/bin/env python3
"""ES filters on ORB v1.4 (pre-registered in BACKTEST_LOG.md, "ES filters on ORB v1.4").

    python3 tools/es_filters.py                      the ES filter study (buckets and the ORB8 test)
    python3 tools/es_filters.py baseline             ES-diverge / ES-confirm by year: share, hit rate, R (forward-test baseline)
    python3 tools/es_filters.py tier --phase is|full the tiered-sizing walk-forward (2 contracts on ES-diverge, else 1)

For each v1.4 trade (data/studies/lit1/v14.csv): ES-confirm / ES-diverge (ES's 09:30-09:44 range broken by a 1m close
on the trade's side by NQ's entry close) and the 09:30-09:44 NQ/ES 1m return correlation (within-year terciles).
Buckets by half, then the ORB8 adoption test for: keep ES-confirm, keep ES-diverge, keep the top correlation tercile.
Output data/studies/es_filters/.
"""
import sys, pathlib
import numpy as np
import pandas as pd

TZ = "America/New_York"
OUT = pathlib.Path("data/studies/es_filters")
BONF = 0.05 / 3


def load_es(cut=None):
    """MNQ 1m index and ES 1m bars on it (a missing ES minute repeats the last), optionally cut before `cut`."""
    a = pd.read_parquet("data/bars/MNQ_1m.parquet", columns=["close"])
    e = pd.read_parquet("data/bars/ES_1m.parquet")
    if cut is not None:
        a, e = a[a.index < cut], e[e.index < cut]
        assert a.index.max() < cut and e.index.max() < cut, "bars reach past the cut"
    return a, e.reindex(a.index).ffill()


def es_confirm(e, et, side):
    """True if ES closed beyond its 09:30-09:44 range on `side` by a 1m close from 09:45 through the last minute of the
    5m entry bar opening at `et` (NY time); False if not (ES-diverge); NaN if the ES bars do not reach that minute."""
    d0 = et.normalize()
    end = et + pd.Timedelta(minutes=4)
    if e.index[-1] < end:
        return np.nan
    er = e.loc[d0 + pd.Timedelta(hours=9, minutes=30): d0 + pd.Timedelta(hours=9, minutes=44)]
    after = e.loc[d0 + pd.Timedelta(hours=9, minutes=45): end]
    return bool((after.close > er.high.max()).any()) if side == "L" else bool((after.close < er.low.min()).any())


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    v = pd.read_csv("data/studies/lit1/v14.csv")
    v["et"] = pd.to_datetime(v.entry_time, utc=True).dt.tz_convert(TZ)
    v["R"] = v.pnl / (v.risk * 2.0)
    a = pd.read_parquet("data/bars/MNQ_1m.parquet")
    e = pd.read_parquet("data/bars/ES_1m.parquet").reindex(a.index).ffill()
    conf, corr = [], []
    for r in v.itertuples():
        d0 = r.et.normalize()
        o0, o1 = d0 + pd.Timedelta(hours=9, minutes=30), d0 + pd.Timedelta(hours=9, minutes=44)
        conf.append(es_confirm(e, r.et, r.side))
        cn = a.close.loc[o0 - pd.Timedelta(minutes=1): o1]
        ce = e.close.loc[o0 - pd.Timedelta(minutes=1): o1]
        rn, re_ = cn.pct_change().iloc[1:], ce.pct_change().iloc[1:]
        corr.append(np.corrcoef(rn, re_)[0, 1] if len(rn) == 15 and rn.std() > 0 and re_.std() > 0 else np.nan)
    v["es_confirm"], v["corr"] = conf, corr
    v["year"], v["half"] = v.et.dt.year, np.where(v.et.dt.year <= 2022, "2019-22", "2023-26")
    v["corr_t"] = v.groupby("year")["corr"].transform(lambda s: pd.qcut(s, 3, labels=["low", "mid", "high"]))
    v.to_csv(OUT / "v14_es.csv", index=False)
    print(f"v1.4: {len(v)} trades, net {v.pnl.sum():+,.0f}, R/trade {v.R.mean():+.3f}; correlation missing on "
          f"{int(v['corr'].isna().sum())}; median correlation {v['corr'].median():.3f}")

    def line(g):
        return f"n {len(g):>4}  net {g.pnl.sum():>+8,.0f}  R/trade {g.R.mean():+.3f}" if len(g) else "n    0"
    for name, col, vals in (("ES-confirm / ES-diverge", "es_confirm", [True, False]), ("correlation tercile", "corr_t", ["low", "mid", "high"])):
        print(f"\n== {name}")
        for k in vals:
            g = v[v[col] == k]
            lab = {True: "ES-confirm", False: "ES-diverge"}.get(k, k)
            print(f"  {str(lab):<11} all {line(g)} | 2019-22 {line(g[g.half == '2019-22'])} | 2023-26 {line(g[g.half == '2023-26'])}")
            print(f"  {'':<11} R by year: " + " ".join(f"{y} {x.R.mean():+.2f} ({len(x)})" for y, x in g.groupby("year")))

    rows = []
    rng = np.random.default_rng(7)
    for name, keep in (("keep ES-confirm", v.es_confirm), ("keep ES-diverge", ~v.es_confirm), ("keep top correlation tercile", v.corr_t == "high")):
        keep = keep.to_numpy(dtype=bool)
        k, s = v[keep], v[~keep]
        sims = np.array([v.R.to_numpy()[rng.choice(len(v), size=len(k), replace=False)].mean() for _ in range(1000)])
        p = float((sims >= k.R.mean()).mean())
        si, so = s[s.half == "2019-22"].pnl.sum(), s[s.half == "2023-26"].pnl.sum()
        parts = dict(skip_is_neg=si < 0, skip_oos_neg=so < 0, kept_R_higher=k.R.mean() > v.R.mean(), p_bonf=p < BONF)
        ok = all(parts.values())
        print(f"\n== {name}: kept {len(k)} R {k.R.mean():+.3f} net {k.pnl.sum():+,.0f} (all {v.R.mean():+.3f}); skipped {len(s)} "
              f"net IS {si:+,.0f} / OOS {so:+,.0f}; random share >= kept R {p:.3f} (5 %: {p < 0.05}, {BONF:.4f}: {p < BONF})")
        print(f"   test: {'PASS' if ok else 'fail'} {parts}")
        rows.append(dict(filter=name, n_keep=len(k), R_keep=round(k.R.mean(), 3), net_keep=round(k.pnl.sum()), n_skip=len(s),
                         net_skip_is=round(si), net_skip_oos=round(so), p_random=p, **parts, passes=ok))
    pd.DataFrame(rows).to_csv(OUT / "summary.csv", index=False)


def baseline():
    v = pd.read_csv(OUT / "v14_es.csv")
    v["et"] = pd.to_datetime(v.entry_time, utc=True).dt.tz_convert(TZ)
    print("Forward-test baseline, v1.4 backtest 2019-06-01 -> 2026-10-06 (879 trades)")
    rows = []
    for y, g in list(v.groupby(v.et.dt.year)) + [("all", v)]:
        dv, cf = g[~g.es_confirm], g[g.es_confirm]
        rows.append(dict(year=y, trades=len(g), diverge=len(dv), share=round(len(dv) / len(g), 3),
                         div_hit=round((dv.pnl > 0).mean(), 3), div_R=round(dv.R.mean(), 3), div_net=round(dv.pnl.sum()),
                         conf_hit=round((cf.pnl > 0).mean(), 3), conf_R=round(cf.R.mean(), 3), conf_net=round(cf.pnl.sum())))
    d = pd.DataFrame(rows)
    d.to_csv(OUT / "baseline.csv", index=False)
    print(d.to_string(index=False))


def rod(x):
    eq = np.cumsum(x)
    dd = -(eq - np.maximum.accumulate(eq)).min()
    return x.sum() / dd if dd > 0 else np.inf


def tier(phase):
    sys.path.insert(0, str(pathlib.Path(__file__).parent))
    import orb_engine
    IS_END = pd.Timestamp("2023-01-01", tz=TZ)
    cut = IS_END if phase == "is" else None
    b5 = pd.read_parquet("data/bars/MNQ_5m.parquet")
    if cut is not None:
        b5 = b5[b5.index < cut]
        assert b5.index.max() < cut
    a, e = load_es(cut)
    v = orb_engine.run(b5, start=pd.Timestamp("2019-06-01", tz=TZ))
    v["et"] = pd.to_datetime(v.entry_time).dt.tz_convert(TZ)
    v["R"] = v.pnl / (v.risk * 2.0)
    v["diverge"] = [not es_confirm(e, t, sd) for t, sd in zip(v.et, v.side)]
    v["n_tier"] = np.where(v.diverge, 2, 1)
    v["half"] = np.where(v.et.dt.year <= 2022, "2019-22", "2023-26")
    if phase == "is":
        v.to_csv(OUT / "tier_is.csv", index=False)
    else:
        ref = pd.read_csv(OUT / "tier_is.csv")
        x = v[v.half == "2019-22"]
        assert len(x) == len(ref) and np.allclose(x.pnl.to_numpy(), ref.pnl.to_numpy()) and \
            (x.diverge.to_numpy() == ref.diverge.to_numpy()).all(), "2019-2022 trades or flags differ from step 1"
        print("walk-forward check: 2019-2022 trades and flags equal step 1")
        v.to_csv(OUT / "tier_full.csv", index=False)
    rows = []
    for h in (["2019-22"] if phase == "is" else ["2019-22", "2023-26"]):
        g = v[v.half == h]
        res = {}
        for name, n in (("tiered", g.n_tier.to_numpy()), ("(a) 1 contract", np.ones(len(g))), ("(b) 2 contracts", 2 * np.ones(len(g)))):
            r, d = n * g.R.to_numpy(), n * g.pnl.to_numpy()
            eqd = np.cumsum(d); eqr = np.cumsum(r)
            res[name] = (rod(r), rod(d))
            rows.append(dict(half=h, book=name, trades=len(g), contracts=int(n.sum()), net=round(d.sum()), R=round(r.sum(), 1),
                             dd=round((eqd - np.maximum.accumulate(eqd)).min()), ddR=round((eqr - np.maximum.accumulate(eqr)).min(), 1),
                             rod_R=round(rod(r), 2), rod_usd=round(rod(d), 2)))
        beat = all(res["tiered"][k] > res[c][k] for c in ("(a) 1 contract", "(b) 2 contracts") for k in (0, 1))
        print(f"\n{h}: {len(g)} trades, {int(g.diverge.sum())} ES-diverge; tiered beats (a) and (b) in R and $: {beat}")
        rows[-1]["tier_beats_both"] = rows[-2]["tier_beats_both"] = rows[-3]["tier_beats_both"] = beat
    d = pd.DataFrame(rows)
    d.to_csv(OUT / f"tier_{phase}_summary.csv", index=False)
    print(d.to_string(index=False))
    if phase == "full":
        ok = d.groupby("half").tier_beats_both.first().all()
        print(f"\nadoption rule (tiered beats both comparisons in R and $, both halves): {'ADOPT' if ok else 'not adopted'}")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "study"
    if cmd == "baseline":
        baseline()
    elif cmd == "tier":
        tier(sys.argv[sys.argv.index("--phase") + 1])
    else:
        main()
