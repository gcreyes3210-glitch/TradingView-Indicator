#!/usr/bin/env python3
"""Literature: IM1 (intraday momentum), ORB9 (5-minute ORB), NR7 / ID filters on ORB v1.4 — pre-registered in
BACKTEST_LOG.md, "Literature".

    python3 tools/lit1.py is        walk-forward step 1: filter runs (and their bases) on bars cut at 2022-12-31 23:59
    python3 tools/lit1.py full      every run on 2019-06-01 -> end of bars; checks the in-sample part equals step 1
    python3 tools/lit1.py charts    10 random IM1-a and 10 random ORB9-a trades, cut at entry

MNQ 1m bars (Databento, New York time). House fills: 1 tick per fill, $1 per side, $2 / point, stop first, a bar
opening beyond a stop / target fills at its open. Output in data/studies/lit1/.
"""
import sys, math, pathlib, json
import numpy as np
import pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from ifvg_engine import rma_atr, trading_date
import orb_engine

TZ = "America/New_York"
TICK, PV, COMM = 0.25, 2.0, 1.0
START = pd.Timestamp("2019-06-01", tz=TZ)
IS_END = pd.Timestamp("2023-01-01", tz=TZ)
OUT = pathlib.Path("data/studies/lit1")
BONF = 0.05 / 8


# ---------------------------------------------------------------- data
def load(cut=None):
    a = pd.read_parquet("data/bars/MNQ_1m.parquet")
    b5 = pd.read_parquet("data/bars/MNQ_5m.parquet")
    if cut is not None:
        a, b5 = a[a.index < cut], b5[b5.index < cut]
        assert a.index.max() < cut and b5.index.max() < cut, "in-sample bars reach into the out-of-sample window"
    return a, b5


def days_table(a):
    """One row per cash date: the closes / opens the rules read, prior close, daily ATR, early-close end time."""
    ts = a.index
    tod = ts.hour * 60 + ts.minute
    td = trading_date(ts)
    # daily ATR(14) on trading-day bars, the last completed day before each trading day
    g = a.groupby(td)
    D = pd.DataFrame({"h": g.high.max(), "l": g.low.min(), "c": g.close.last()})
    D["atr"] = rma_atr(D.h.to_numpy(), D.l.to_numpy(), D.c.to_numpy())
    D["atr_prev"] = D.atr.shift(1)
    cash = a[(tod >= 570) & (tod < 960)]
    ct = cash.index.hour * 60 + cash.index.minute
    cd = cash.index.normalize().tz_localize(None)
    rows = pd.DataFrame(index=sorted(set(cd)))

    def at(m, col):
        x = cash[ct == m]
        return pd.Series(x[col].to_numpy(), index=x.index.normalize().tz_localize(None))
    for name, m, col in (("o930", 570, "open"), ("c944", 584, "close"), ("c959", 599, "close"), ("c1014", 614, "close"),
                         ("c1529", 929, "close"), ("c1559", 959, "close")):
        rows[name] = at(m, col)
    cg = cash.groupby(cd)
    rows["rth_h"], rows["rth_l"], rows["last_c"] = cg.high.max(), cg.low.min(), cg.close.last()
    rows["prev_close"] = rows.last_c.shift(1)
    rows["atr"] = D.atr_prev.reindex(rows.index)
    ev = pd.read_csv("data/events.csv")
    early = ev[ev.type == "early_close"].set_index("date").time_ny
    rows["early_end"] = [early.get(d.strftime("%Y-%m-%d")) for d in rows.index]
    # overnight 18:00 -> 09:29 of the trading day
    on = a[(tod >= 1080) | (tod < 570)]
    og = on.groupby(trading_date(on.index))
    rows["on_h"], rows["on_l"] = og.high.max().reindex(rows.index), og.low.min().reindex(rows.index)
    rows = rows[rows.index >= START.tz_localize(None).normalize()]
    return rows


# ---------------------------------------------------------------- IM1
def im1(T, variant="a", sig_col="c959"):
    d = T[T.early_end.isna()].dropna(subset=[sig_col, "c1529", "c1559", "prev_close", "atr"]).copy()
    base = d.o930 if variant == "b" else d.prev_close
    d["sig"] = d[sig_col] - base
    d["sig_ret"] = (d[sig_col] - d.prev_close).abs() / d.prev_close
    # IM1-c: above the median of the previous 20 sessions' |signal return| (all sessions with a value, today excluded)
    allret = ((T[sig_col] - T.prev_close).abs() / T.prev_close)
    med = allret.shift(1).rolling(20).median()
    d["med20"] = med.reindex(d.index)
    if variant == "c":
        d = d[d.sig_ret > d.med20]
    d = d[d.sig != 0]
    sgn = np.sign(d.sig)
    entry, exit_ = d.c1529 + sgn * TICK, d.c1559 - sgn * TICK
    d["side"] = np.where(sgn > 0, "L", "S")
    d["pnl"] = sgn * (exit_ - entry) * PV - 2 * COMM
    d["risk"] = 0.1 * d.atr
    d["R"] = d.pnl / (d.risk * PV)
    last = np.sign(d.c1559 - d.c1529)
    d["hit"] = last == sgn
    d["last_up"] = last > 0
    d["entry_time"] = [pd.Timestamp(x).tz_localize(TZ) + pd.Timedelta(hours=15, minutes=29) for x in d.index]
    return d


# ---------------------------------------------------------------- ORB9
def orb9(a, T, floor=0.1, target=None, on_filter=False):
    ts = a.index
    O, H, L, C = (a[k].to_numpy() for k in ("open", "high", "low", "close"))
    pos = pd.Series(np.arange(len(ts)), index=ts)
    out = []
    for d, r in T.iterrows():
        if pd.isna(r.atr):
            continue
        t0 = pd.Timestamp(d).tz_localize(TZ) + pd.Timedelta(hours=9, minutes=30)
        try:
            i0 = pos[t0]; i5 = pos[t0 + pd.Timedelta(minutes=5)]
        except KeyError:
            continue
        if i5 - i0 != 5 or ts[i0 + 4] != t0 + pd.Timedelta(minutes=4):
            continue
        fo, fc, fh, fl = O[i0], C[i0 + 4], H[i0:i0 + 5].max(), L[i0:i0 + 5].min()
        if fc == fo:
            continue
        if on_filter and not (fh > r.on_h or fl < r.on_l):
            continue
        sgn = 1 if fc > fo else -1
        fill = O[i5] + sgn * TICK
        stop = fl if sgn > 0 else fh
        if sgn * (fill - stop) < floor * r.atr:              # minimum risk, rounded to the tick away from the fill
            raw = fill - sgn * floor * r.atr
            stop = (math.floor if sgn > 0 else math.ceil)(raw / TICK) * TICK
        risk = sgn * (fill - stop)
        tgt = round((fill + sgn * target * risk) / TICK) * TICK if target else None
        end = 959 if pd.isna(r.early_end) else int(r.early_end[:2]) * 60 + int(r.early_end[3:]) - 11
        te = pd.Timestamp(d).tz_localize(TZ) + pd.Timedelta(minutes=end)
        ie = pos.get(te)
        if ie is None:
            continue
        res = None
        for i in range(i5, ie + 1):
            if (O[i] <= stop if sgn > 0 else O[i] >= stop) and i > i5:
                res = (i, O[i], "SL"); break
            if (L[i] <= stop) if sgn > 0 else (H[i] >= stop):
                res = (i, stop, "SL"); break
            if tgt is not None:
                if i > i5 and (O[i] >= tgt if sgn > 0 else O[i] <= tgt):
                    res = (i, O[i], "TP"); break
                if (H[i] >= tgt) if sgn > 0 else (L[i] <= tgt):
                    res = (i, tgt, "TP"); break
        if res is None:
            res = (ie, C[ie], "time" if pd.isna(r.early_end) else "early")
        px = res[1] - sgn * TICK
        pnl = sgn * (px - fill) * PV - 2 * COMM
        out.append(dict(day=d, entry_time=ts[i5], side="L" if sgn > 0 else "S", entry=fill, stop=stop, risk=risk,
                        target=tgt, exit_time=ts[res[0]], exit=px, reason=res[2], pnl=pnl, R=pnl / (risk * PV),
                        fh=fh, fl=fl, on_h=r.on_h, on_l=r.on_l, atr=r.atr))
    return pd.DataFrame(out)


# ---------------------------------------------------------------- ORB v1.4 and NR7 / ID
def v14(b5):
    t = orb_engine.run(b5, start=START)
    t["entry_time"] = pd.to_datetime(t.entry_time)
    t["day"] = t.entry_time.dt.tz_localize(None).dt.normalize()
    t["R"] = t.pnl / (t.risk * PV)
    return t


def nr_id(T):
    rng = T.rth_h - T.rth_l
    prev = rng.shift(1)
    nr7_prev = pd.Series([prev.iloc[i] < prev.iloc[i - 6:i].min() if i >= 7 else np.nan
                          for i in range(len(prev))], index=T.index)
    id_prev = (T.rth_h.shift(1) < T.rth_h.shift(2)) & (T.rth_l.shift(1) > T.rth_l.shift(2))
    return nr7_prev, id_prev


# ---------------------------------------------------------------- reporting
def summ(t):
    if t is None or len(t) == 0:
        return dict(n=0)
    y = pd.to_datetime(t.entry_time).dt.year
    by = t.groupby(y).pnl.sum()
    h1, h2 = t[y <= 2022], t[y >= 2023]
    eq = t.pnl.cumsum()
    gw, gl = t.pnl[t.pnl > 0].sum(), -t.pnl[t.pnl < 0].sum()
    return dict(n=len(t), net=round(t.pnl.sum()), R=round(t.R.mean(), 3), win=round(100 * (t.pnl > 0).mean(), 1),
                pf=round(gw / gl, 2) if gl else None, dd=round((eq - eq.cummax()).min()),
                pos_years=int((by > 0).sum()), years=int(y.nunique()),
                R_h1=round(h1.R.mean(), 3) if len(h1) else None, R_h2=round(h2.R.mean(), 3) if len(h2) else None)


def by(t, label):
    y = pd.to_datetime(t.entry_time).dt.year
    print(f"  {label} R by year: " + " ".join(f"{k} {g.R.mean():+.3f} ({len(g)}, {g.pnl.sum():+,.0f})" for k, g in t.groupby(y)))
    print(f"  {label} side: " + " | ".join(f"{k}: n {len(g)} net {g.pnl.sum():+,.0f} R {g.R.mean():+.3f}" for k, g in t.groupby("side")))


def binom_p(k, n, p0=0.5):
    lp = lambda i: math.lgamma(n + 1) - math.lgamma(i + 1) - math.lgamma(n - i + 1) + i * math.log(p0) + (n - i) * math.log(1 - p0)
    return float(sum(math.exp(lp(i)) for i in range(k, n + 1)))


def boot_p(R, n=10000, seed=1):
    rng = np.random.default_rng(seed)
    R = np.asarray(R)
    m = R[rng.integers(0, len(R), size=(n, len(R)))].mean(axis=1)
    return float((m <= 0).mean())


def criterion(s, nb, p):
    parts = dict(years=s["pos_years"] >= 6, R=s["R"] >= 0.05, halves=(s["R_h1"] or -1) >= 0 and (s["R_h2"] or -1) >= 0,
                 neighbours=all(np.sign(x["R"]) == np.sign(s["R"]) and x["R"] != 0 for x in nb), p=p < BONF)
    return all(parts.values()), parts


def orb8_test(t, keep_mask, nsim=1000, seed=7):
    keep, skip = t[keep_mask], t[~keep_mask]
    rng = np.random.default_rng(seed)
    sims = np.array([t.R.to_numpy()[rng.choice(len(t), size=len(keep), replace=False)].mean() for _ in range(nsim)])
    return dict(n_all=len(t), n_keep=len(keep), n_skip=len(skip), R_all=round(t.R.mean(), 3), R_keep=round(keep.R.mean(), 3),
                net_keep=round(keep.pnl.sum()), net_skip=round(skip.pnl.sum()), p_random=float((sims >= keep.R.mean()).mean()))


# ---------------------------------------------------------------- phases
def run_is():
    OUT.mkdir(parents=True, exist_ok=True)
    a, b5 = load(cut=IS_END)
    T = days_table(a)
    print(f"IN-SAMPLE ONLY: bars {a.index[0]} -> {a.index[-1]}  ({len(T)} cash days)")
    res = {}
    for name, t in (("IM1-a", im1(T, "a")), ("IM1-c", im1(T, "c")),
                    ("ORB9-a", orb9(a, T)), ("ORB9-c", orb9(a, T, on_filter=True))):
        t.to_csv(OUT / f"is_{name}.csv")
        s = summ(t); res[name] = s
        print(f"\n== {name} IS: " + "  ".join(f"{k} {v}" for k, v in s.items()))
        by(t, name)
    v = v14(b5)
    v.to_csv(OUT / "is_v14.csv", index=False)
    nr7, idp = nr_id(T)
    print(f"\n== ORB v1.4 IS: " + "  ".join(f"{k} {v_}" for k, v_ in summ(v).items()))
    for name, flag in (("NR7", nr7), ("ID", idp)):
        km = v.day.map(flag).fillna(False).astype(bool).to_numpy()
        o = orb8_test(v, km)
        res[name] = o
        print(f"== {name} IS (v1.4 kept only after an {name} day): {o}")
        by(v[km], name + " kept")
    json.dump(res, open(OUT / "is_results.json", "w"), indent=1, default=str)


def run_full():
    a, b5 = load()
    T = days_table(a)
    print(f"FULL: bars {a.index[0]} -> {a.index[-1]}  ({len(T)} cash days)")
    rows = []
    # walk-forward check: the in-sample part of each filter run equals the in-sample-only run
    for name, t in (("IM1-c", im1(T, "c")), ("ORB9-c", orb9(a, T, on_filter=True))):
        ref = pd.read_csv(OUT / f"is_{name}.csv")
        x = t[pd.to_datetime(t.entry_time).dt.tz_convert(TZ) < IS_END] if "entry_time" in t else t
        assert np.allclose(x.pnl.to_numpy(), ref.pnl.to_numpy()), f"{name}: in-sample part differs from the IS-only run"
    print("walk-forward check: IM1-c and ORB9-c in-sample trades equal the IS-only runs")

    # IM1
    for v in ("a", "b", "c"):
        name = f"IM1-{v}"
        t = im1(T, v)
        t.to_csv(OUT / f"{name}.csv")
        s = summ(t)
        k, n = int(t.hit.sum()), len(t)
        p = binom_p(k, n)
        nb = [summ(im1(T, v, c)) for c in ("c944", "c1014")]
        ok, parts = criterion(s, nb, p)
        print(f"\n== {name}: " + "  ".join(f"{kk} {vv}" for kk, vv in s.items()))
        by(t, name)
        print(f"  signal hit rate vs the last half hour: {k}/{n} = {k / n:.1%}, one-sided binomial p {p:.4f}; "
              f"up last-half-hours {t.last_up.mean():.1%}")
        print(f"  neighbours (signal at 09:45 / 10:15): R {nb[0]['R']} / {nb[1]['R']}  (n {nb[0]['n']} / {nb[1]['n']})")
        print(f"  criterion: {'PASS' if ok else 'fail'} {parts}")
        rows.append(dict(run=name, **s, p=round(p, 5), hit=round(k / n, 4), nb1_R=nb[0]["R"], nb2_R=nb[1]["R"], passes=ok))
    # ORB9
    base = {}
    for v, kw in (("a", {}), ("b", dict(target=10)), ("c", dict(on_filter=True))):
        name = f"ORB9-{v}"
        t = orb9(a, T, **kw)
        t.to_csv(OUT / f"{name}.csv", index=False)
        base[v] = t
        s = summ(t)
        p = boot_p(t.R)
        nb = [summ(orb9(a, T, floor=f, **kw)) for f in (0.05, 0.2)]
        ok, parts = criterion(s, nb, p)
        print(f"\n== {name}: " + "  ".join(f"{kk} {vv}" for kk, vv in s.items()))
        by(t, name)
        print(f"  exits: {t.reason.value_counts().to_dict()}  floor applied on {int((t.risk < 0.1 * t.atr + TICK).sum())} trades")
        print(f"  bootstrap p (mean R > 0): {p:.4f}; neighbours (floor 0.05 / 0.2 ATR): R {nb[0]['R']} / {nb[1]['R']}")
        print(f"  criterion: {'PASS' if ok else 'fail'} {parts}")
        rows.append(dict(run=name, **s, p=round(p, 5), nb1_R=nb[0]["R"], nb2_R=nb[1]["R"], passes=ok))
    # filters vs base, IS / OOS
    for name, t, b in (("IM1-c", pd.read_csv(OUT / "IM1-c.csv", parse_dates=["entry_time"]), pd.read_csv(OUT / "IM1-a.csv", parse_dates=["entry_time"])),
                       ("ORB9-c", base["c"], base["a"])):
        f = lambda x, lo, hi: x[(pd.to_datetime(x.entry_time, utc=True) >= lo) & (pd.to_datetime(x.entry_time, utc=True) < hi)].R.mean()
        lo, mid, hi = pd.Timestamp("2000-01-01", tz="UTC"), IS_END.tz_convert("UTC"), pd.Timestamp("2100-01-01", tz="UTC")
        print(f"  walk-forward {name} vs base, R/trade: IS {f(t, lo, mid):+.3f} vs {f(b, lo, mid):+.3f}; "
              f"OOS {f(t, mid, hi):+.3f} vs {f(b, mid, hi):+.3f}")
    # ORB9-a vs v1.4
    v = v14(b5)
    v.to_csv(OUT / "v14.csv", index=False)
    print(f"\n== ORB v1.4 (same span): " + "  ".join(f"{k} {x}" for k, x in summ(v).items()))
    by(v, "v1.4")
    o9 = base["a"]
    d9 = o9.groupby(pd.to_datetime(o9.day)).pnl.sum()
    dv = v.groupby("day").pnl.sum()
    alld = pd.DatetimeIndex(T.index)
    both = d9.index.intersection(dv.index)
    x9, xv = d9.reindex(alld, fill_value=0), dv.reindex(alld, fill_value=0)
    print(f"  trading days: ORB9-a {len(d9)}, v1.4 {len(dv)}, both {len(both)}, either {len(d9.index.union(dv.index))}; "
          f"share of v1.4 days ORB9-a also trades {len(both) / len(dv):.1%}")
    print(f"  daily P&L correlation: all {len(alld)} cash days (0 = no trade) {np.corrcoef(x9, xv)[0, 1]:+.3f}; "
          f"days both traded {np.corrcoef(d9[both], dv[both])[0, 1]:+.3f}; same direction on both-days "
          f"{(np.sign(o9.set_index(pd.to_datetime(o9.day)).side.map({'L': 1, 'S': -1})[both]) == np.sign(v.groupby('day').side.first().map({'L': 1, 'S': -1})[both])).mean():.1%}")
    # NR7 / ID
    nr7, idp = nr_id(T)
    for name, flag in (("NR7", nr7), ("ID", idp)):
        km = v.day.map(flag).fillna(False).astype(bool).to_numpy()
        o = orb8_test(v, km)
        isd = v.entry_time.dt.tz_convert(TZ) < IS_END
        skip_is, skip_oos = v[~km & isd].pnl.sum(), v[~km & ~isd].pnl.sum()
        ok = skip_is < 0 and skip_oos < 0 and o["R_keep"] > o["R_all"] and o["p_random"] < 0.05
        print(f"\n== {name}: {o}; skipped net IS {skip_is:+,.0f} / OOS {skip_oos:+,.0f}; kept R IS "
              f"{v[km & isd].R.mean():+.3f} / OOS {v[km & ~isd].R.mean():+.3f}")
        by(v[km], name + " kept")
        print(f"  ORB8 test: {'PASS' if ok else 'fail'}; Bonferroni (p_random < {BONF:.5f}): {o['p_random'] < BONF}")
        rows.append(dict(run=name, **summ(v[km]), p=o["p_random"], net_skip_is=round(skip_is), net_skip_oos=round(skip_oos),
                         R_all=o["R_all"], passes=ok and o["p_random"] < BONF))
    d = pd.DataFrame(rows)
    d.to_csv(OUT / "summary.csv", index=False)
    print("\n" + d.to_string(index=False))


def charts(n=10, seed=11):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle
    a, _ = load()
    out = pathlib.Path("data/studies/lit1_charts"); out.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(seed)
    key = []

    def candles(ax, x):
        for k, (o, h, l, c) in enumerate(zip(x.open, x.high, x.low, x.close)):
            col = "#26a69a" if c >= o else "#ef5350"
            ax.plot([k, k], [l, h], color=col, lw=0.8)
            ax.add_patch(Rectangle((k - 0.35, min(o, c)), 0.7, max(abs(c - o), 0.05), color=col, lw=0))

    t = pd.read_csv(OUT / "IM1-a.csv", parse_dates=["entry_time"])
    for c, r in enumerate(t.iloc[np.sort(rng.choice(len(t), n, replace=False))].itertuples(), 1):
        e = pd.Timestamp(r.entry_time).tz_convert(TZ)
        x = a.loc[e.normalize() + pd.Timedelta(hours=9, minutes=30): e].resample("5min", label="left", closed="left").agg(
            {"open": "first", "high": "max", "low": "min", "close": "last"}).dropna()
        fig, ax = plt.subplots(figsize=(15, 7))
        candles(ax, x)
        ax.axhline(r.prev_close, color="#1565c0", ls="-.", lw=1); ax.text(0, r.prev_close, f" prior 16:00 close {r.prev_close:,.2f}", color="#1565c0", fontsize=8, va="bottom")
        k10 = list(x.index).index(e.normalize() + pd.Timedelta(hours=9, minutes=55))
        ax.plot(k10, r.c959, "o", color="#6a1b9a"); ax.text(k10, r.c959, f"  10:00 close {r.c959:,.2f}", color="#6a1b9a", fontsize=8)
        ax.plot(len(x) - 1, r.c1529, ">" if r.side == "L" else "<", color="black", ms=11)
        ax.text(len(x) + 0.5, r.c1529, f" entry {'LONG' if r.side == 'L' else 'SHORT'} at the 15:30 close {r.c1529:,.2f}", fontsize=8, va="center")
        ax.set_xticks(range(0, len(x), 6), [ts.strftime("%H:%M") for ts in x.index[::6]], fontsize=7)
        ax.set_xlim(-1, len(x) + 14)
        ax.set_title(f"im1_{c:02d} · {e:%Y-%m-%d %a} · IM1-a {'LONG' if r.side == 'L' else 'SHORT'} · MNQ 5m, cut at entry · outcome hidden", fontsize=10)
        ax.grid(alpha=0.2); fig.tight_layout(); fig.savefig(out / f"im1_{c:02d}.png", dpi=90); plt.close(fig)
        key.append(dict(id=f"im1_{c:02d}", entry_time=e, side=r.side))
    t = pd.read_csv(OUT / "ORB9-a.csv", parse_dates=["entry_time"])
    for c, r in enumerate(t.iloc[np.sort(rng.choice(len(t), n, replace=False))].itertuples(), 1):
        e = pd.Timestamp(r.entry_time).tz_convert(TZ)
        x = a.loc[e.normalize() + pd.Timedelta(hours=8, minutes=30): e - pd.Timedelta(minutes=1)]
        fig, ax = plt.subplots(figsize=(15, 7))
        candles(ax, x)
        k0 = len(x) - 5
        ax.add_patch(Rectangle((k0 - 0.5, r.fl), 5, r.fh - r.fl, color="#ffb300", alpha=0.25))
        ax.text(k0 - 6, r.fl, "first 5m bar 09:30-09:35 ", fontsize=8, color="#e65100", va="top", ha="right")
        lo, hi = min(x.low.min(), r.stop), max(x.high.max(), r.stop)
        lo, hi = lo - 0.08 * (hi - lo), hi + 0.08 * (hi - lo)
        ax.set_ylim(lo, hi)
        off = []
        for lv, lab in ((r.on_h, "overnight high"), (r.on_l, "overnight low")):
            if lo <= lv <= hi:
                ax.axhline(lv, color="#546e7a", ls="--", lw=0.8); ax.text(0, lv, f" {lab} {lv:,.2f}", fontsize=8, color="#546e7a", va="bottom")
            else:
                off.append(f"{lab} {lv:,.2f} (off chart)")
        if off:
            ax.text(0.01, 0.02, " · ".join(off), transform=ax.transAxes, fontsize=8, color="#546e7a")
        ax.axhline(r.stop, color="#c62828", lw=1.2)
        ax.text(len(x) + 0.5, r.stop, f" stop {r.stop:,.2f}", color="#c62828", fontsize=8, va="top" if r.side == "S" else "bottom")
        ax.plot(len(x), r.entry, ">" if r.side == "L" else "<", color="black", ms=11)
        ax.text(len(x) + 0.5, r.entry, f" entry {'LONG' if r.side == 'L' else 'SHORT'} at the 09:35 open {r.entry:,.2f}", fontsize=8, va="center")
        ax.set_xticks(range(0, len(x), 5), [ts.strftime("%H:%M") for ts in x.index[::5]], fontsize=7)
        ax.set_xlim(-1, len(x) + 16)
        ax.set_title(f"orb9_{c:02d} · {e:%Y-%m-%d %a} · ORB9-a {'LONG' if r.side == 'L' else 'SHORT'} · MNQ 1m, cut at entry · outcome hidden", fontsize=10)
        ax.grid(alpha=0.2); fig.tight_layout(); fig.savefig(out / f"orb9_{c:02d}.png", dpi=90); plt.close(fig)
        key.append(dict(id=f"orb9_{c:02d}", entry_time=e, side=r.side))
    pd.DataFrame(key).to_csv(out / "charts_key.csv", index=False)
    pd.DataFrame(dict(id=[k["id"] for k in key], setup_is_right="", note="")).to_csv(out / "answers.csv", index=False)
    print(f"{len(key)} charts in {out}")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "full"
    {"is": run_is, "full": run_full, "charts": charts}[cmd]()
