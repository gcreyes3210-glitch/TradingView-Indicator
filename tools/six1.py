#!/usr/bin/env python3
"""SIX: six pre-registered tests on MNQ 2019-06 -> 2026-10 (BACKTEST_LOG.md, "SIX") and the overnight-hold observation.

    python3 tools/six1.py rev | add | lrb | rv | vol | ml | overnight | all

House fills: 1 tick per fill, $1 per side per contract, MNQ $2 / pt, MES $5 / pt; stop first; a bar opening beyond a
level fills at its open. Output data/studies/six/.
"""
import sys, math, pathlib, subprocess, json
import numpy as np
import pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import orb_engine
from ifvg_engine import trading_date

TZ = "America/New_York"
TICK, MNQ_PV, MES_PV, COMM = 0.25, 2.0, 5.0, 1.0
START = pd.Timestamp("2019-06-01", tz=TZ)
OUT = pathlib.Path("data/studies/six")
BONF = 0.05 / 6
D = {}


def bars():
    if not D:
        D["a"] = pd.read_parquet("data/bars/MNQ_1m.parquet")
        D["b5"] = pd.read_parquet("data/bars/MNQ_5m.parquet")
        D["e"] = pd.read_parquet("data/bars/ES_1m.parquet").reindex(D["a"].index).ffill()
        v = orb_engine.run(D["b5"], start=START)
        v["et"] = pd.to_datetime(v.entry_time).dt.tz_convert(TZ)
        v["xt"] = pd.to_datetime(v.exit_time).dt.tz_convert(TZ)
        v["R"] = v.pnl / (v.risk * MNQ_PV)
        v["sg"] = np.where(v.side == "L", 1, -1)
        v["px"] = v.entry - v.sg * TICK                     # the close the risk is measured from
        v["stop"] = v.px - v.sg * v.risk
        D["v"] = v
    return D


# ---------------------------------------------------------------- common reporting
def summ(t, R="R", pnl="pnl", when="et"):
    if len(t) == 0:
        return dict(n=0)
    y = t[when].dt.year
    by = t.groupby(y)[pnl].sum()
    eq = t[pnl].cumsum()
    gw, gl = t[pnl][t[pnl] > 0].sum(), -t[pnl][t[pnl] < 0].sum()
    return dict(n=len(t), net=round(t[pnl].sum()), R=round(t[R].mean(), 3), win=round(100 * (t[pnl] > 0).mean(), 1),
                pf=round(gw / gl, 2) if gl else None, dd=round((eq - eq.cummax()).min()), pos_years=int((by > 0).sum()),
                years=int(y.nunique()), R_h1=round(t[y <= 2022][R].mean(), 3), R_h2=round(t[y >= 2023][R].mean(), 3))


def byyear(t, R="R", pnl="pnl", when="et"):
    y = t[when].dt.year
    return " ".join(f"{k} {g[R].mean():+.2f} ({len(g)}, {g[pnl].sum():+,.0f})" for k, g in t.groupby(y))


def boot_p(R, n=10000, seed=1):
    R = np.asarray(R, dtype=float)
    rng = np.random.default_rng(seed)
    return float((R[rng.integers(0, len(R), size=(n, len(R)))].mean(axis=1) <= 0).mean())


def criterion(s, nb, p):
    parts = dict(years=s["pos_years"] >= 6, R=s["R"] >= 0.05, halves=s["R_h1"] >= 0 and s["R_h2"] >= 0,
                 neighbours=all(x.get("R", 0) != 0 and np.sign(x["R"]) == np.sign(s["R"]) for x in nb), p=p < BONF)
    return all(parts.values()), parts


def show(name, t, nb, p, extra=""):
    s = summ(t)
    ok, parts = criterion(s, nb, p)
    print(f"\n== {name}: " + "  ".join(f"{k} {v}" for k, v in s.items()))
    print(f"   R by year: {byyear(t)}")
    print(f"   side: " + " | ".join(f"{k}: n {len(g)} net {g.pnl.sum():+,.0f} R {g.R.mean():+.3f}" for k, g in t.groupby("side")))
    print(f"   neighbours R: " + " / ".join(str(x.get("R")) for x in nb) + f"   p {p:.4f}{extra}")
    print(f"   criterion: {'PASS' if ok else 'fail'} {parts}")
    return dict(test=name, **s, p=round(p, 5), nb=[x.get("R") for x in nb], passes=ok)


def flat_1m(a, day, early_cut_minutes=11):
    """1m flatten bar index of a cash day: the 15:59 bar, or the bar opening `early_cut_minutes` before an early halt."""
    x = a.loc[day + pd.Timedelta(hours=9, minutes=30): day + pd.Timedelta(hours=16, minutes=59)]
    last = x.index[-1]
    if last.hour * 60 + last.minute >= 15 * 60 + 59:
        k = x.index.get_indexer([day + pd.Timedelta(hours=15, minutes=59)])[0]
        return x.index[k]
    halt = last + pd.Timedelta(minutes=1)
    return x.index[x.index <= halt - pd.Timedelta(minutes=early_cut_minutes)][-1]


# ---------------------------------------------------------------- (1) ORB-rev
def rev_trades(buf_ticks=2):
    d = bars(); a, v = d["a"], d["v"]
    O, H, L, C = (a[k].to_numpy() for k in ("open", "high", "low", "close"))
    pos = pd.Series(np.arange(len(a)), index=a.index)
    out = []
    for r in v[v.reason == "SL"].itertuples():
        w = a.loc[r.xt: r.xt + pd.Timedelta(minutes=4)]
        hit = (w.low <= r.stop) if r.sg > 0 else (w.high >= r.stop)
        if not hit.any():
            continue
        j = pos[hit.idxmax()]
        day = r.et.normalize()
        i0 = pos[day + pd.Timedelta(hours=9, minutes=30)]
        sg = -r.sg                                        # the reversal
        entry = r.exit                                    # v1.4's stop fill
        stop = (H[i0:j + 1].max() + buf_ticks * TICK) if sg < 0 else (L[i0:j + 1].min() - buf_ticks * TICK)
        risk = sg * (entry - stop)
        if risk <= 0:
            continue
        f = pos[flat_1m(a, day)]
        res = None
        for q in range(j + 1, f + 1):
            if sg * (O[q] - stop) <= 0:
                res = (q, O[q], "SL"); break
            if (L[q] <= stop) if sg > 0 else (H[q] >= stop):
                res = (q, stop, "SL"); break
        if res is None:
            res = (f, C[f], "time")
        px = res[1] - sg * TICK
        pnl = sg * (px - entry) * MNQ_PV - 2 * COMM
        out.append(dict(et=a.index[j], side="L" if sg > 0 else "S", entry=entry, stop=stop, risk=risk,
                        xt=a.index[res[0]], exit=px, reason=res[2], pnl=pnl, R=pnl / (risk * MNQ_PV)))
    return pd.DataFrame(out)


def test_rev():
    t = rev_trades(2)
    t.to_csv(OUT / "rev.csv", index=False)
    nb = [summ(rev_trades(b)) for b in (0, 4)]
    return show("ORB-rev", t, nb, boot_p(t.R), f"; exits {t.reason.value_counts().to_dict()}; median risk {t.risk.median():.1f} pts")


# ---------------------------------------------------------------- (2) ORB-add
def add_trades(th=1.0):
    d = bars(); b, v = d["b5"], d["v"]
    O, H, L, C = (b[k].to_numpy() for k in ("open", "high", "low", "close"))
    pos = pd.Series(np.arange(len(b)), index=b.index)
    out = []
    for r in v.itertuples():
        day = r.et.normalize()
        t1155 = day + pd.Timedelta(hours=11, minutes=55)
        if not (r.et < t1155 and r.xt > t1155):           # still open at 12:00
            continue
        i_e, i_x, k = pos[r.et], pos[r.xt], pos.get(t1155)
        if k is None or r.sg * (C[k] - r.px) < th * r.risk:
            continue
        best = (H[i_e + 1:k + 1].max() if r.sg > 0 else L[i_e + 1:k + 1].min()) if k > i_e else r.px
        pulled, fill_i = False, None
        for q in range(k + 1, i_x):
            best = max(best, H[q]) if r.sg > 0 else min(best, L[q])
            if not pulled:
                if (L[q] <= best - 0.5 * r.risk) if r.sg > 0 else (H[q] >= best + 0.5 * r.risk):
                    pulled = True
                continue
            if (C[q] > O[q]) if r.sg > 0 else (C[q] < O[q]):
                fill_i = q; break
        if fill_i is None:
            continue
        px = C[fill_i]
        risk = r.sg * (px - r.stop)
        if risk <= 0:
            continue
        entry = px + r.sg * TICK
        pnl = r.sg * (r.exit - entry) * MNQ_PV - 2 * COMM            # exits with v1.4, at v1.4's fill
        out.append(dict(et=b.index[fill_i], day=day, side=r.side, entry=entry, stop=r.stop, risk=risk, exit=r.exit,
                        reason=r.reason, pnl=pnl, R=pnl / (risk * MNQ_PV), v_risk=r.risk))
    return pd.DataFrame(out)


def test_add():
    d = bars(); v = d["v"]
    t = add_trades(1.0)
    t.to_csv(OUT / "add.csv", index=False)
    nb = [summ(add_trades(x)) for x in (0.75, 1.25)]
    row = show("ORB-add (the second contract)", t, nb, boot_p(t.R))
    # per contract and combined, drawdown in v1.4 R units
    v = v.copy()
    v["day"] = v.et.dt.normalize()
    add_by_day = t.set_index("day").pnl
    v["add_pnl"] = v.day.map(add_by_day).fillna(0.0)
    v["comb"] = v.pnl + v.add_pnl
    for lab, col in (("v1.4 (1 contract)", "pnl"), ("combined (v1.4 + add)", "comb")):
        rr = v[col] / (v.risk * MNQ_PV)
        eq = rr.cumsum()
        y = v.et.dt.year
        print(f"   {lab:<22} net {v[col].sum():+,.0f}  R total {rr.sum():+.1f}  DD {(eq - eq.cummax()).min():+.1f} R  "
              f"R/day 2019-22 {rr[y <= 2022].mean():+.3f} / 2023-26 {rr[y >= 2023].mean():+.3f}  "
              f"return/DD {rr.sum() / -(eq - eq.cummax()).min():.2f}")
    return row


# ---------------------------------------------------------------- (3) LRB
def lrb(args, tag):
    f = OUT / f"lrb_{tag}.csv"
    subprocess.run([sys.executable, "tools/lrb_engine.py", "--min-brk", "0", "--out", str(f), *args], check=True,
                   capture_output=True, text=True)
    t = pd.read_csv(f)
    t["et"] = pd.to_datetime(t.entry_time, utc=True).dt.tz_convert(TZ)
    t["R"] = t.pnl / (t.risk * MNQ_PV)
    return t


def test_lrb():
    t = lrb([], "primary")
    nb = [summ(lrb(["--lunch", "12:00-13:00", "--entry-window", "13:00-15:00"], "nb1300")),
          summ(lrb(["--lunch", "12:00-14:00", "--entry-window", "14:00-15:00"], "nb1400"))]
    row = show("LRB (LRB1d re-run)", t, nb, boot_p(t.R))
    vb = lrb(["--days", "break"], "break")
    s = summ(vb)
    print(f"   variant, v1.4 overnight-range filter (break days): " + "  ".join(f"{k} {x}" for k, x in s.items()))
    print(f"   variant R by year: {byyear(vb)}")
    return row


# ---------------------------------------------------------------- (4) RV
def rv_trades(th=2.0):
    d = bars(); a, e = d["a"], d["e"]
    if "rv" not in D:
        lr = np.log(a.close.to_numpy()) - np.log(e.close.to_numpy())
        td = trading_date(a.index)
        g = pd.DataFrame({"s": lr, "q": lr * lr, "n": 1.0}).groupby(td).sum()
        w = g.rolling(5).sum().shift(1)
        mean = w.s / w.n
        sd = np.sqrt(np.maximum(w.q / w.n - mean ** 2, 0))
        ia = pd.Series(a.instrument_id.to_numpy(), index=a.index).groupby(td).agg(["first", "last"])
        ib = pd.Series(pd.read_parquet("data/bars/ES_1m.parquet").reindex(a.index).instrument_id.ffill().to_numpy(),
                       index=a.index).groupby(td).agg(["first", "last"])
        roll = (ia["first"] != ia["last"].shift(1)) | (ia["first"] != ia["last"]) | \
               (ib["first"] != ib["last"].shift(1)) | (ib["first"] != ib["last"])
        bad = roll.astype(int).rolling(6).max().fillna(1).astype(bool)        # the day or any of the 5 before it
        D["rv"] = (lr, td, mean, sd, bad)
    lr, td, mean, sd, bad = D["rv"]
    tod = (a.index.hour * 60 + a.index.minute).to_numpy()
    CA, CE = a.close.to_numpy(), e.close.to_numpy()
    out = []
    cash = np.flatnonzero((tod >= 570) & (tod < 960))
    day_of = td[cash]
    for dd in pd.unique(day_of):
        if dd < START.tz_localize(None) or bad.get(dd, True) or not np.isfinite(sd.get(dd, np.nan)) or sd[dd] <= 0:
            continue
        idx = cash[day_of == dd]
        mu, s = mean[dd], sd[dd]
        z = (lr[idx] - mu) / s
        k, n = 0, len(idx)
        while k < n:
            i = idx[k]
            if tod[i] <= 14 * 60 + 59 and abs(z[k]) >= th:
                sgn = -1 if z[k] > 0 else 1                       # MNQ leg; ES leg is -sgn
                ea, ee = CA[i] + sgn * TICK, CE[i] - sgn * TICK
                m = k + 1
                while m < n and not ((z[m] <= 0) if sgn < 0 else (z[m] >= 0)):
                    m += 1
                m = min(m, n - 1)
                j = idx[m]
                xa, xe = CA[j] - sgn * TICK, CE[j] + sgn * TICK
                pnl = sgn * (xa - ea) * MNQ_PV - sgn * (xe - ee) * MES_PV - 4 * COMM
                unit = s * CA[i] * MNQ_PV
                out.append(dict(et=a.index[i], xt=a.index[j], side="L" if sgn > 0 else "S", z=z[k], pnl=pnl,
                                R=pnl / unit, reason="z0" if m < n - 1 or (z[m] <= 0 if sgn < 0 else z[m] >= 0) else "time"))
                k = m + 1
            else:
                k += 1
    t = pd.DataFrame(out)
    t["et"] = pd.to_datetime(t.et).dt.tz_convert(TZ)
    return t


def test_rv():
    t = rv_trades(2.0)
    t.to_csv(OUT / "rv.csv", index=False)
    nb = [summ(rv_trades(x)) for x in (1.5, 2.5)]
    _, _, _, _, bad = D["rv"]
    return show("RV (NQ/ES ratio)", t, nb, boot_p(t.R),
                f"; exits {t.reason.value_counts().to_dict()}; days skipped for rolls {int(bad.sum())}")


# ---------------------------------------------------------------- (5) ORB-vol
def rod(p):
    eq = p.cumsum()
    dd = -(eq - eq.cummax()).min()
    return p.sum() / dd if dd > 0 else np.inf


def vol_book(cap=10):
    v = bars()["v"].copy()
    v["n"] = np.minimum(np.round(250.0 / (v.risk * MNQ_PV)), cap)
    v = v[v.n >= 1].copy()
    v["pv"] = v.n * v.pnl
    v["pc"] = v.n.mean() * v.pnl
    return v


def test_vol():
    v = vol_book(10)
    v.to_csv(OUT / "vol.csv", index=False)
    y = v.et.dt.year
    halves = {}
    for h, m in (("2019-22", y <= 2022), ("2023-26", y >= 2023), ("all", y > 0)):
        halves[h] = (rod(v.pv[m]), rod(v.pc[m]))
        print(f"   {h}: risk-sized net {v.pv[m].sum():+,.0f} return/DD {halves[h][0]:.2f} | constant {v.n.mean():.2f} contracts "
              f"net {v.pc[m].sum():+,.0f} return/DD {halves[h][1]:.2f}")
    pos_years = int((v.groupby(y).pv.sum() > 0).sum())
    rng = np.random.default_rng(1)
    pv, pc = v.pv.to_numpy(), v.pc.to_numpy()
    worse = 0
    for _ in range(10000):
        ix = np.sort(rng.integers(0, len(v), size=len(v)))
        worse += rod(pd.Series(pv[ix])) <= rod(pd.Series(pc[ix]))
    p = worse / 10000
    nbs = []
    for cap in (5, 20):
        w = vol_book(cap)
        nbs.append(rod(w.pv) - rod(w.pc))
        print(f"   neighbour cap {cap}: {len(w)} trades, return/DD risk-sized {rod(w.pv):.2f} vs constant {rod(w.pc):.2f}")
    diff = halves["all"][0] - halves["all"][1]
    parts = dict(both_halves=halves["2019-22"][0] > halves["2019-22"][1] and halves["2023-26"][0] > halves["2023-26"][1],
                 years=pos_years >= 6, neighbours=all(np.sign(x) == np.sign(diff) for x in nbs), p=p < BONF)
    ok = all(parts.values())
    print(f"\n== ORB-vol: {len(v)} trades (of {len(bars()['v'])}; {len(bars()['v']) - len(v)} round to 0 contracts), "
          f"mean {v.n.mean():.2f} contracts, capped at 10 on {int((v.n == 10).sum())}; positive years {pos_years}; p {p:.4f}")
    print(f"   size distribution: {v.n.value_counts().sort_index().to_dict()}")
    print(f"   criterion: {'PASS' if ok else 'fail'} {parts}")
    return dict(test="ORB-vol", n=len(v), rod_h1=round(halves['2019-22'][0], 2), rod_h1_const=round(halves['2019-22'][1], 2),
                rod_h2=round(halves['2023-26'][0], 2), rod_h2_const=round(halves['2023-26'][1], 2), p=p, passes=ok)


# ---------------------------------------------------------------- (6) ML1
def ml_table():
    from lit1 import days_table
    a = bars()["a"]
    T = days_table(a)
    tod = a.index.hour * 60 + a.index.minute
    orb = a[(tod >= 570) & (tod < 585)]
    og = orb.groupby(orb.index.normalize().tz_localize(None))
    T["or_h"], T["or_l"] = og.high.max(), og.low.min()
    td = trading_date(a.index)
    gtd = a.groupby(td)
    T["open18"] = gtd.open.first().reindex(T.index)
    c929 = a[tod == 569]
    T["c929"] = pd.Series(c929.close.to_numpy(), index=c929.index.normalize().tz_localize(None))
    lr = np.log(T.last_c).diff()
    T["_rv20"] = lr.shift(1).rolling(20).std()
    T["_prev_rng"] = (T.rth_h - T.rth_l).shift(1)
    p = T.c944
    X = pd.DataFrame({"or_w": (T.or_h - T.or_l) / p, "or_hi_vs_on": (T.or_h - T.on_h) / p, "or_lo_vs_on": (T.or_l - T.on_l) / p,
                      "gap": (T.o930 - T.prev_close) / p, "prev_rng": T._prev_rng / p, "on_ret": (T.c929 - T.open18) / T.open18,
                      "dow": [d.dayofweek for d in T.index], "rv20": T._rv20})
    T = T.join(X)
    T = T[T.early_end.isna()].dropna(subset=list(X.columns) + ["c944", "c1559"])
    T["y"] = (T.c1559 > T.c944).astype(int)
    return T, list(X.columns)


def test_ml():
    from sklearn.ensemble import GradientBoostingClassifier
    from sklearn.model_selection import GridSearchCV, KFold
    T, F = ml_table()
    is_ = T.index < pd.Timestamp("2023-01-01")
    Xi, yi, Xo, yo = T.loc[is_, F], T.loc[is_, "y"], T.loc[~is_, F], T.loc[~is_, "y"]
    grid = GridSearchCV(GradientBoostingClassifier(subsample=0.8, random_state=1),
                        dict(n_estimators=[50, 100, 200], max_depth=[1, 2, 3], learning_rate=[0.01, 0.05, 0.1]),
                        cv=KFold(5, shuffle=False), scoring="accuracy")
    grid.fit(Xi, yi)
    m = grid.best_estimator_                       # refit on all of 2019-2022 by GridSearchCV
    T["pred"] = m.predict(T[F])                    # the one evaluation on 2023-2026 is the ~is_ part of this
    sg = np.where(T.pred == 1, 1, -1)
    T["side"] = np.where(sg > 0, "L", "S")
    T["pnl"] = sg * ((T.c1559 - sg * TICK) - (T.c944 + sg * TICK)) * MNQ_PV - 2 * COMM
    T["R"] = T.pnl / ((T.or_h - T.or_l) * MNQ_PV)
    T["et"] = [pd.Timestamp(d).tz_localize(TZ) + pd.Timedelta(hours=9, minutes=45) for d in T.index]
    T["hit"] = T.pred == T.y
    T.to_csv(OUT / "ml1.csv")
    print(f"\n== ML1: best params {grid.best_params_}, CV accuracy (2019-22) {grid.best_score_:.3f}")
    print(f"   feature importances: " + ", ".join(f"{f} {w:.2f}" for f, w in sorted(zip(F, m.feature_importances_), key=lambda x: -x[1])))
    res = {}
    for lab, mk in (("in-sample 2019-22 (training)", is_), ("out-of-sample 2023-26", ~is_)):
        x = T[mk]
        acc, up = x.hit.mean(), x.y.mean()
        k, n = int(x.hit.sum()), len(x)
        lp = lambda i: math.lgamma(n + 1) - math.lgamma(i + 1) - math.lgamma(n - i + 1) + i * math.log(up) + (n - i) * math.log(1 - up)
        p = float(sum(math.exp(lp(i)) for i in range(k, n + 1)))
        s = summ(x)
        res[lab] = (s, acc, up, p)
        print(f"   {lab}: n {n}, accuracy {acc:.3f} (always-long {up:.3f}, binomial p {p:.4f}), long share {(x.pred == 1).mean():.2f}; "
              + "  ".join(f"{kk} {vv}" for kk, vv in s.items()))
        print(f"      R by year: {byyear(x)}")
        print(f"      side: " + " | ".join(f"{kk}: n {len(g)} net {g.pnl.sum():+,.0f} R {g.R.mean():+.3f}" for kk, g in x.groupby("side")))
    s, acc, up, p = res["out-of-sample 2023-26"]
    oos = T[~is_]
    pos = int((oos.groupby(oos.et.dt.year).pnl.sum() > 0).sum())
    parts = dict(R=s["R"] >= 0.05, years=pos >= 3, accuracy=acc > up and p < BONF)
    ok = all(parts.values())
    print(f"   criterion (out of sample): {'PASS' if ok else 'fail'} {parts}; positive OOS years {pos} of 4")
    return dict(test="ML1", n_oos=len(oos), R_oos=s["R"], acc_oos=round(acc, 3), always_long=round(up, 3), p=p, passes=ok,
                params=grid.best_params_, cv=round(grid.best_score_, 3))


# ---------------------------------------------------------------- observation: overnight hold
def overnight():
    from lit1 import days_table
    T = days_table(bars()["a"])
    T = T.dropna(subset=["o930"])
    nxt = T.o930.shift(-1)
    x = T[T.early_end.isna() & T.c1559.notna() & nxt.notna()].copy()
    x["entry"], x["exit"] = x.c1559 + TICK, nxt[x.index] - TICK
    x["pnl"] = (x.exit - x.entry) * MNQ_PV - 2 * COMM
    x["pts"] = nxt[x.index] - x.c1559
    y = x.index.year
    print("\n== Overnight hold (observation): buy the 15:59 close, sell the next 09:30 open")
    print(f"   all: n {len(x)}  net {x.pnl.sum():+,.0f}  per trade {x.pnl.mean():+.1f}  win {100 * (x.pnl > 0).mean():.1f}%  "
          f"points {x.pts.sum():+,.0f} (before costs)")
    for k, g in x.groupby(y):
        print(f"   {k}: n {len(g):>3}  net {g.pnl.sum():>+7,.0f}  per trade {g.pnl.mean():+6.1f}  win {100 * (g.pnl > 0).mean():.1f}%  points {g.pts.sum():+,.0f}")
    x.to_csv(OUT / "overnight.csv")


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    cmd = sys.argv[1] if len(sys.argv) > 1 else "all"
    fn = dict(rev=test_rev, add=test_add, lrb=test_lrb, rv=test_rv, vol=test_vol, ml=test_ml, overnight=overnight)
    rows = []
    for k in (fn if cmd == "all" else [cmd]):
        r = fn[k]()
        if r is not None:
            rows.append(r)
    if cmd == "all":
        pd.DataFrame(rows).to_json(OUT / "summary.json", orient="records", indent=1, default_handler=str)
