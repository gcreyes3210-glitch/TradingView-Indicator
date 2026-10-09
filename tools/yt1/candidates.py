#!/usr/bin/env python3
"""YT1 candidates: second-coder comparison, out-of-sample half, drift benchmark and the ORB v1.4 comparison.
    python3 tools/yt1/candidates.py        -> data/studies/yt1/candidates.json and a printed report
"""
import sys, json, pathlib
import numpy as np, pandas as pd
sys.path.insert(0, str(pathlib.Path(__file__).parent)); sys.path.insert(0, str(pathlib.Path(__file__).parents[1]))
import core, orb_engine

CAND = ["C02", "C19b", "E09", "E10a", "E12"]
FULL = core.OUT / "full"


def load(ident):
    d = pd.read_csv(FULL / f"{ident}_base.csv")
    for c in ("sig_time", "entry_time", "exit_time"):
        d[c] = pd.to_datetime(d[c], utc=True).dt.tz_convert(core.TZ)
    d["day"] = d.entry_time.dt.tz_localize(None).dt.normalize()
    return d


def dd(x):
    c = np.cumsum(x)
    return float((c - np.maximum.accumulate(np.r_[0, c])[1:]).min()) if len(c) else 0.0


def main():
    ctx = core.Ctx(core.load_bars("MNQ"))
    days = ctx.days.index
    orb = orb_engine.run(pd.read_parquet(core.BARS / "MNQ_5m.parquet"), start=pd.Timestamp("2019-06-01", tz=core.TZ))
    orb["entry_time"] = pd.to_datetime(orb.entry_time)
    orb["day"] = orb.entry_time.dt.tz_localize(None).dt.normalize()
    orb["R"] = orb.pnl / (orb.risk * core.PV)
    orb_day = orb.groupby("day").pnl.sum().reindex(days, fill_value=0.0)
    orb_side = orb.set_index("day").side
    out = {"orb": dict(n=int(len(orb)), net=float(orb.pnl.sum()), dd=dd(orb.pnl.to_numpy()), R=float(orb.R.mean()),
                       ret_dd=float(orb.pnl.sum() / -dd(orb.pnl.to_numpy())))}
    daily = {"ORB": orb_day}
    # minute-of-day close table for the drift benchmark
    tod, C, dn = ctx.tod, ctx.C, ctx.dayn
    yr_of_day = pd.Series(days.year, index=np.arange(len(days)))
    rth = (tod >= 570) & (tod < 960) & (dn >= 0)
    close_tab = pd.DataFrame({"d": dn[rth], "t": tod[rth], "c": C[rth]}).pivot(index="d", columns="t", values="c")
    for ident in CAND:
        a, b = load(ident), load("R" + ident)
        k = ["entry_time", "side"]
        m = a.merge(b, on=k, how="outer", suffixes=("_a", "_b"), indicator=True)
        both = m[m._merge == "both"]
        r = dict(n=int(len(a)), net=float(a.pnl.sum()), R=float(a.R.mean()), p=core.boot_p(a.R.to_numpy()),
                 dd=dd(a.pnl.to_numpy()), dd_R=dd(a.R.to_numpy()), avg_trade=float(a.pnl.mean()),
                 trades_per_year=float(len(a) / 7.35), avg_risk_pts=float(a.risk_pts.mean()),
                 recode=dict(n_first=int(len(a)), n_second=int(len(b)), same_entry_and_side=int(len(both)),
                             same_pnl=int((np.abs(both.pnl_a - both.pnl_b) < 0.01).sum()),
                             only_first=int((m._merge == "left_only").sum()), only_second=int((m._merge == "right_only").sum()),
                             net_second=float(b.pnl.sum()), R_second=float(b.R.mean()), p_second=core.boot_p(b.R.to_numpy())))
        y = a.entry_time.dt.year
        oos = a[y >= 2023]
        r["oos"] = dict(n=int(len(oos)), net=float(oos.pnl.sum()), R=float(oos.R.mean()), p=core.boot_p(oos.R.to_numpy()),
                        years_pos=int(sum(oos[oos.entry_time.dt.year == yy].pnl.sum() > 0 for yy in (2023, 2024, 2025, 2026))),
                        by_year={int(yy): float(oos[oos.entry_time.dt.year == yy].pnl.sum()) for yy in (2023, 2024, 2025, 2026)})
        ins = a[y <= 2022]
        r["is"] = dict(n=int(len(ins)), net=float(ins.pnl.sum()), R=float(ins.R.mean()), p=core.boot_p(ins.R.to_numpy()))
        r["long"] = dict(n=int((a.side == "L").sum()), net=float(a.pnl[a.side == "L"].sum()), R=float(a.R[a.side == "L"].mean()) if (a.side == "L").any() else None)
        r["short"] = dict(n=int((a.side == "S").sum()), net=float(a.pnl[a.side == "S"].sum()), R=float(a.R[a.side == "S"].mean()) if (a.side == "S").any() else None)
        # drift benchmark: the same clock window, same side, on every cash day of the same calendar year
        sgn = np.where(a.side == "L", 1.0, -1.0)
        te = (a.entry_time.dt.hour * 60 + a.entry_time.dt.minute).to_numpy()
        tx = (a.exit_time.dt.hour * 60 + a.exit_time.dt.minute).to_numpy()
        gross = sgn * (a.exit.to_numpy() - a.entry.to_numpy())          # points, after slippage
        bench = np.full(len(a), np.nan)
        yrs = a.entry_time.dt.year.to_numpy()
        for i in range(len(a)):
            if te[i] in close_tab.columns and tx[i] in close_tab.columns and tx[i] > te[i]:
                rows = yr_of_day.index[yr_of_day == yrs[i]]
                rows = [x for x in rows if x in close_tab.index]
                mv = (close_tab.loc[rows, tx[i]] - close_tab.loc[rows, te[i]]).dropna()
                bench[i] = sgn[i] * mv.mean()
        ok = ~np.isnan(bench)
        ex = gross[ok] - bench[ok]
        rng = np.random.default_rng(1)
        bs = rng.choice(ex, size=(10000, len(ex)), replace=True).mean(axis=1)
        r["drift"] = dict(n=int(ok.sum()), gross_pts_per_trade=float(gross[ok].mean()), drift_pts_per_trade=float(bench[ok].mean()),
                          excess_pts_per_trade=float(ex.mean()), p_excess=float((bs <= 0).mean()))
        # against ORB v1.4
        cd = a.groupby("day").pnl.sum().reindex(days, fill_value=0.0)
        daily[ident] = cd
        on_orb = a[a.day.isin(orb.day)]
        off_orb = a[~a.day.isin(orb.day)]
        first = a.groupby("day").side.first()
        common = first.index.intersection(orb_side.index)
        comb = (cd + orb_day)
        r["vs_orb"] = dict(days_traded=int(a.day.nunique()), days_both=int(len(common)),
                           same_side_share=float((first[common] == orb_side[common]).mean()) if len(common) else None,
                           corr_daily=float(np.corrcoef(cd, orb_day)[0, 1]),
                           on_orb_days=dict(n=int(len(on_orb)), net=float(on_orb.pnl.sum()), R=float(on_orb.R.mean()) if len(on_orb) else None),
                           off_orb_days=dict(n=int(len(off_orb)), net=float(off_orb.pnl.sum()), R=float(off_orb.R.mean()) if len(off_orb) else None,
                                             p=core.boot_p(off_orb.R.to_numpy()) if len(off_orb) > 1 else None),
                           alone_ret_dd=float(cd.sum() / -dd(cd.to_numpy())),
                           orb_ret_dd=float(orb_day.sum() / -dd(orb_day.to_numpy())),
                           combined_net=float(comb.sum()), combined_dd=dd(comb.to_numpy()),
                           combined_ret_dd=float(comb.sum() / -dd(comb.to_numpy())))
        out[ident] = r
    Dm = pd.DataFrame(daily)
    out["corr"] = Dm.corr().round(3).to_dict()
    allc = Dm[CAND].sum(axis=1)
    out["all_candidates_plus_orb"] = dict(net=float((allc + Dm.ORB).sum()), dd=dd((allc + Dm.ORB).to_numpy()),
                                          ret_dd=float((allc + Dm.ORB).sum() / -dd((allc + Dm.ORB).to_numpy())))
    Dm.to_csv(core.OUT / "candidates_daily_pnl.csv")
    (core.OUT / "candidates.json").write_text(json.dumps(out, indent=1))
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
