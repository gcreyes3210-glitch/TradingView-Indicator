#!/usr/bin/env python3
"""R4 seven-year test, exactly as pre-registered in BACKTEST_LOG.md ("R4 seven-year test", 2026-09-24).

    python3 tools/r4_test.py check          R4 here vs R4 in bias_study.features on the 40 study days (must agree)
    python3 tools/r4_test.py direction      test 1: R4's direction hit rate by year vs the base rate
    python3 tools/r4_test.py filter --stage 1|2      test 2: ORB v1.4 side filter, 2019-2022 or 2023-2026

R4 at 09:30 New York: MNQ daily bars (18:00-17:00 trading days), the last `lookback` completed days plus today's bar to
09:29; an FVG = 3-bar gap on those bars not traded through at its far edge by any later bar (today's partial bar
included); short if any such FVG has its bottom above the 09:29 close, else long. Lookback 60 (primary), 40 and 80
(neighbours). Days: bias_study.eligible() (09:30 bar, >= 60 earlier trading days, same contract at the previous cash
close, 09:29 and the cash close) minus the 40 BIAS-study days.
"""
import sys, pathlib
import numpy as np
import pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import bias_study as B

TZ = "America/New_York"
opt = lambda k, d: type(d)(sys.argv[sys.argv.index(k) + 1]) if k in sys.argv else d
NSH = 20000
rng = np.random.default_rng(4)


def daily_parts(one):
    """Completed daily bars per trading day, and today's partial bar to 09:29, for every trading date."""
    g = one.groupby("td")
    full = pd.DataFrame({"high": g.high.max(), "low": g.low.min()})
    pre = one[(one.tod < 570) | (one.tod >= 18 * 60)]                # 18:00 -> 09:29 of the trading day
    gp = pre.groupby("td")
    part = pd.DataFrame({"high": gp.high.max(), "low": gp.low.min(), "last": gp.close.last()})
    return full, part


def r4_calls(one, days, lookback):
    full, part = daily_parts(one)
    tds = list(full.index)
    pos = {d: k for k, d in enumerate(tds)}
    out = {}
    for d in days:
        k = pos.get(pd.Timestamp(d))
        if k is None or k < lookback or pd.Timestamp(d) not in part.index:
            continue
        w = full.iloc[k - lookback:k]
        H = np.r_[w.high.to_numpy(), part.loc[pd.Timestamp(d), "high"]]
        L = np.r_[w.low.to_numpy(), part.loc[pd.Timestamp(d), "low"]]
        px = part.loc[pd.Timestamp(d), "last"]
        short = False
        for i in range(2, len(H)):
            if L[i] > H[i - 2] and not (L[i + 1:] <= H[i - 2]).any() and H[i - 2] > px:
                short = True; break
            if H[i] < L[i - 2] and not (H[i + 1:] >= L[i - 2]).any() and H[i] > px:
                short = True; break
        out[pd.Timestamp(d)] = "short" if short else "long"
    return out


def setup():
    one = B.one_min()
    key = pd.read_csv("data/studies/bias/key.csv")
    study = set(pd.to_datetime(key.date))
    el = [d for d in B.eligible(one) if d not in study]
    return one, el, study


def check():
    one = B.one_min()
    f = pd.concat([pd.read_csv(f"data/studies/bias/features_block{b}.csv", dtype={"id": str}) for b in (1, 2)])
    key = pd.read_csv("data/studies/bias/key.csv", dtype={"id": str})
    f = f.merge(key, on="id")
    c = r4_calls(one, pd.to_datetime(f.date), 60)
    same = sum(c[pd.Timestamp(d)] == r for d, r in zip(f.date, f.R4))
    print(f"R4 here vs bias_study features on the study days: {same} of {len(f)} agree")


def direction():
    one, el, _ = setup()
    cc = B.cash_close(one)
    for lb in (60, 40, 80):
        calls = r4_calls(one, el, lb)
        rows = []
        for d, c in calls.items():
            k = cc.index.get_loc(d)
            mv = cc.close.iloc[k] - cc.close.iloc[k - 1]
            if mv != 0:
                rows.append(dict(date=d, year=d.year, call=c, up=mv > 0, hit=(mv > 0) == (c == "long")))
        t = pd.DataFrame(rows)
        print(f"\n== lookback {lb}: {len(t)} days")
        for y, g in list(t.groupby("year")) + [("all", t)]:
            if y == "all":
                up_by = t.groupby("year").up.transform("mean")
                pr = np.where(t.call == "long", up_by, 1 - up_by)
            else:
                pr = np.where(g.call == "long", g.up.mean(), 1 - g.up.mean())
            k = int(g.hit.sum())
            print(f"  {y}: n {len(g):>3}  short calls {100 * (g.call == 'short').mean():3.0f} %  up days {100 * g.up.mean():3.0f} %  "
                  f"R4 right {k} ({100 * k / len(g):.1f} %)  expected {pr.sum():.1f}  one-sided p {B.pbinom_ge(pr, k):.3f}")
        for c, g in t.groupby("call"):
            print(f"  {c} calls: {int(g.hit.sum())} of {len(g)} right ({100 * g.hit.mean():.1f} %)")
        if lb == 60:
            t.to_csv("data/studies/bias/r4_direction.csv", index=False)


def filt(stage):
    from orb_engine import run
    one, el, _ = setup()
    t = run(pd.read_parquet("data/bars/MNQ_5m.parquet"), start=pd.Timestamp("2019-06-01", tz=TZ))
    t["R"] = t.pnl / (t.risk * 2.0)
    t["year"] = t.entry_time.dt.year
    t["d"] = pd.to_datetime(t.entry_time.dt.date)
    y0, y1 = (2019, 2022) if stage == 1 else (2023, 2026)
    res = {}
    for lb in (60, 40, 80):
        calls = r4_calls(one, el, lb)
        t[f"r4_{lb}"] = t.d.map(calls)
        against = ((t.side == "L") & (t[f"r4_{lb}"] == "short")) | ((t.side == "S") & (t[f"r4_{lb}"] == "long"))
        t[f"skip_{lb}"] = against
        w = t[(t.year >= y0) & (t.year <= y1)]
        sk, kp = w[w[f"skip_{lb}"]], w[~w[f"skip_{lb}"]]
        by = sk.groupby("year").pnl.sum()
        res[lb] = dict(n=len(w), skipped=len(sk), skipped_net=sk.pnl.sum(), skipped_R=sk.R.mean(),
                       skipped_neg_years=int((by < 0).sum()), years=int(w.year.nunique()), kept_R=kp.R.mean(), all_R=w.R.mean(),
                       kept_net=kp.pnl.sum(), all_net=w.pnl.sum(), by_year=by.round(0).to_dict(), no_call=int(w[f"r4_{lb}"].isna().sum()))
        if lb == 60:
            # shuffle: skip the same number of trades at random within each year
            Rv = w.R.to_numpy(); yrs = w.year.to_numpy(); nsk = w.groupby("year")["skip_60"].sum()
            obs = kp.R.mean()
            hits = 0
            for _ in range(NSH // 1000):
                mask = np.zeros((1000, len(w)), bool)
                for y in np.unique(yrs):
                    idx = np.flatnonzero(yrs == y)
                    r = rng.random((1000, len(idx))).argsort(axis=1)[:, :int(nsk.get(y, 0))]
                    mask[np.arange(1000)[:, None], idx[r]] = True
                kept = np.where(~mask, Rv, 0).sum(1) / (~mask).sum(1)
                hits += int((kept >= obs).sum())
            res[lb]["shuffle_p"] = hits / NSH
    print(f"==== stage {stage}: {y0}-{y1}")
    for lb, r in res.items():
        print(f"  lookback {lb}: " + "  ".join(f"{k} {round(v, 3) if isinstance(v, float) else v}" for k, v in r.items()))
    r = res[60]
    if stage == 1:
        ok = dict(skipped_net_negative=r["skipped_net"] < 0, neg_years_3_of_4=r["skipped_neg_years"] >= 3,
                  kept_R_above_all=r["kept_R"] > r["all_R"], shuffle_p_below_005=r["shuffle_p"] < 0.05,
                  neighbours_skipped_negative=all(res[lb]["skipped_net"] < 0 for lb in (40, 80)))
    else:
        full = t[~t.skip_60]
        fy = full.groupby("year").pnl.sum()
        print(f"  full span filtered ORB: n {len(full)} net {full.pnl.sum():+,.0f} R {full.R.mean():+.3f} "
              f"positive years {int((fy > 0).sum())} of {len(fy)}  by year {fy.round(0).to_dict()}")
        ok = dict(skipped_net_negative=r["skipped_net"] < 0, neg_years_3_of_4=r["skipped_neg_years"] >= 3,
                  kept_R_above_all=r["kept_R"] > r["all_R"], full_6_of_8=int((fy > 0).sum()) >= 6,
                  full_R_005=full.R.mean() >= 0.05,
                  neighbours_skipped_negative=all(res[lb]["skipped_net"] < 0 for lb in (40, 80)))
    print(f"  criteria: {ok}  -> {'PASS' if all(ok.values()) else 'FAIL'}")


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "check":
        check()
    elif cmd == "direction":
        direction()
    else:
        filt(opt("--stage", 1))
