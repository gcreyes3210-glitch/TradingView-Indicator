#!/usr/bin/env python3
"""ES filters on ORB v1.4 (pre-registered in BACKTEST_LOG.md, "ES filters on ORB v1.4").

    python3 tools/es_filters.py

For each v1.4 trade (data/studies/lit1/v14.csv): ES-confirm / ES-diverge (ES's 09:30-09:44 range broken by a 1m close
on the trade's side by NQ's entry close) and the 09:30-09:44 NQ/ES 1m return correlation (within-year terciles).
Buckets by half, then the ORB8 adoption test for: keep ES-confirm, keep ES-diverge, keep the top correlation tercile.
Output data/studies/es_filters/.
"""
import pathlib
import numpy as np
import pandas as pd

TZ = "America/New_York"
OUT = pathlib.Path("data/studies/es_filters")
BONF = 0.05 / 3


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
        er = e.loc[o0:o1]
        hi, lo = er.high.max(), er.low.min()
        after = e.loc[d0 + pd.Timedelta(hours=9, minutes=45): r.et + pd.Timedelta(minutes=4)]   # to NQ's entry close
        conf.append(bool((after.close > hi).any()) if r.side == "L" else bool((after.close < lo).any()))
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


if __name__ == "__main__":
    main()
