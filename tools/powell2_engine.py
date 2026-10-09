#!/usr/bin/env python3
"""POWELL P2 (the author's guide), as pre-registered in BACKTEST_LOG.md (2026-09-25). MNQ 1m (+ ES 1m), house fills.

    python3 tools/powell2_engine.py all [--outdir data/studies/powell2]
    python3 tools/powell2_engine.py charts [--n 10] [--seed 31] [--out data/studies/powell2_charts]

O = open of the 10:00 1m bar; A = RMA(14) 5m ATR of the bar closed at 10:00, fixed for the day.
Manipulation: one side of O reaches k x A (k = 0.5; neighbours 0.35, 0.75) while the other side is not exceeded by
more than 0.1 x A on any bar before the signal's first close (void otherwise). Bias = against the manipulation.
Signal: two consecutive 1m closes through O on the bias side, the second by the bar opening 11:29 (S5: plus a 5m
candle opening at 10:05 or later closing through O; the signal is the later of the two).
Target: nearest unswept bias-side liquidity >= 1.0 x A beyond O: 5m 3-bar fractals and equal highs / lows (two
fractals within 0.1 x A, level = the farther one), formed since 18:00 the prior evening, confirmed by the signal.
Stop: target distance / 5 (R3: / 3) from the entry; skipped if below 0.4 x A.
Entry: base = limit at O from the bar after the signal to the bar opening 11:29 (fill at O, or the open if the bar
opens beyond; only the stop is checked on the fill bar); ET = close of the first bar after the signal that trades
to O and closes back on the bias side. Break-even: the stop moves to the entry price from the bar after price first
reaches the nearest bias-side fractal between the entry and the target. Flat at the close of the last bar before
16:00 (early-close rule). One trade a day. 1 tick slippage on every fill, stop first, $1 / side, $2 / point.
Filter F: skip days whose overnight range (18:00-09:30) > 1.5 x the median of the previous 20 days', CPI / PPI / NFP
and FOMC days (data/events.csv), and days where MNQ's and ES's 09:30-10:00 moves differ in sign.
"""
import sys, math, pathlib, collections
import numpy as np
import pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from powell_engine import rma_atr, flat_index, atr_at, summary
from ifvg_engine import trading_date

TZ = "America/New_York"
TICK, PV, COMM = 0.25, 2.0, 1.0
opt = lambda k, d: type(d)(sys.argv[sys.argv.index(k) + 1]) if k in sys.argv else d
END = 11 * 60 + 29
RUNS = {"base": dict(), "S5": dict(s5=True), "ET": dict(et=True), "R3": dict(div=3),
        "F": dict(filt=True), "F+ET": dict(filt=True, et=True)}


def prepare():
    one = pd.read_parquet("data/bars/MNQ_1m.parquet")
    es = pd.read_parquet("data/bars/ES_1m.parquet")
    b5 = pd.read_parquet("data/bars/MNQ_5m.parquet")
    atr5 = pd.Series(rma_atr(b5.high.to_numpy(), b5.low.to_numpy(), b5.close.to_numpy()), index=b5.index)
    one["td"] = trading_date(one.index)
    tod = one.index.hour * 60 + one.index.minute
    on = one[(tod >= 18 * 60) | (tod < 9 * 60 + 30)]
    g = on.groupby("td")
    onr = (g.high.max() - g.low.min())
    ratio = onr / onr.rolling(20).median().shift(1)
    ev = pd.read_csv("data/events.csv")
    news = set(pd.to_datetime(ev[ev.type.isin(["CPI", "PPI", "NFP", "FOMC"])].date))
    b5["td"] = trading_date(b5.index)
    days = []
    for d, x in one.groupby(one.index.date):
        m = x.index.hour * 60 + x.index.minute
        x = x[(m >= 570) & (m < 960)]
        if x.empty or not ((x.index.hour == 10) & (x.index.minute == 0)).any():
            continue
        td = pd.Timestamp(d)
        pre = x[x.index.hour * 60 + x.index.minute < 600]
        e = es[(es.index >= pd.Timestamp(f"{d} 09:30", tz=TZ)) & (es.index < pd.Timestamp(f"{d} 10:00", tz=TZ))]
        mq = pre.close.iloc[-1] - pre.open.iloc[0] if len(pre) else 0
        me = e.close.iloc[-1] - e.open.iloc[0] if len(e) else 0
        days.append(dict(date=d, x=x.drop(columns=["td"]), b5=b5[b5.td == td], on_ratio=ratio.get(td, np.nan),
                         news=td in news, dir930="up" if mq > 0 else "down", div930=np.sign(mq) != np.sign(me)))
    return days, atr5


def liquidity(b5, x, t_sig, O, side, A):
    """(target, break-even level) for a bias side ('S' = below O, 'L' = above O) as known at the close of t_sig."""
    end = t_sig + pd.Timedelta(minutes=1)
    w = b5[b5.index + pd.Timedelta(minutes=5) <= end]
    H, L, T = w.high.to_numpy(), w.low.to_numpy(), w.index
    xs = x[x.index <= t_sig]
    pts = []
    for p in range(1, len(w) - 1):
        after = T[p + 1]
        if side == "S" and L[p] < L[p - 1] and L[p] <= L[p + 1]:
            later = min(L[p + 1:].min(), xs[xs.index >= after + pd.Timedelta(minutes=5)].low.min() if len(xs) else np.inf)
            if later >= L[p]:
                pts.append(L[p])
        if side == "L" and H[p] > H[p - 1] and H[p] >= H[p + 1]:
            later = max(H[p + 1:].max(), xs[xs.index >= after + pd.Timedelta(minutes=5)].high.max() if len(xs) else -np.inf)
            if later <= H[p]:
                pts.append(H[p])
    sg = -1 if side == "S" else 1
    eq = [(min(a, b) if side == "S" else max(a, b)) for i, a in enumerate(pts) for b in pts[i + 1:] if abs(a - b) <= 0.1 * A]
    cand = [v for v in pts + eq if sg * (v - O) >= A]
    tgt = (max(cand) if side == "S" else min(cand)) if cand else None
    return tgt, pts


def run(days, atr5, k=0.5, s5=False, et=False, div=5, filt=False):
    out, fun = [], collections.Counter()
    for dd in days:
        if filt and (dd["on_ratio"] > 1.5 or dd["news"] or dd["div930"]):
            continue
        x = dd["x"]
        t = x.index
        tod = t.hour * 60 + t.minute
        O_, H, L, C = (x[c].to_numpy() for c in ("open", "high", "low", "close"))
        i0 = int(np.flatnonzero(tod == 600)[0])
        fl = flat_index(x)
        O = O_[i0]
        A = atr_at(atr5, t[i0] - pd.Timedelta(minutes=1))
        if not A > 0:
            continue
        fun["1 days"] += 1
        tol, m = 0.1 * A, k * A
        armed, hi, lo, pend, sig_j, s5_j = None, -np.inf, np.inf, None, None, None
        for j in range(i0, min(fl, len(x))):
            if tod[j] > END:
                break
            hi, lo = max(hi, H[j]), min(lo, L[j])
            if armed is None:
                if hi - O >= m and O - lo <= tol:
                    armed = "up"
                elif O - lo >= m and hi - O <= tol:
                    armed = "down"
                elif hi - O > tol and O - lo > tol:
                    break
                if armed:
                    fun["2 manipulation"] += 1
                    ext = None
            if armed is None:
                continue
            through = C[j] < O if armed == "up" else C[j] > O
            beyond = (O - L[j] > tol) if armed == "up" else (H[j] - O > tol)
            if sig_j is None:
                if through:
                    if pend is None:
                        pend = j
                    else:
                        sig_j = j
                else:
                    if pend is not None and ((O - L[pend] > tol) if armed == "up" else (H[pend] - O > tol)):
                        break
                    pend = None
                    if beyond:
                        break
            if sig_j is not None and s5:
                # a 5m candle opening >= 10:05 whose close (at the end of 1m bar j) is through O
                if s5_j is None and tod[j] >= 609 and (tod[j] + 1) % 5 == 0:
                    c5 = C[j]
                    if (c5 < O) if armed == "up" else (c5 > O):
                        s5_j = j
                if s5_j is None:
                    continue
            if sig_j is not None:
                break
        if sig_j is None or (s5 and s5_j is None):
            continue
        sj = max(sig_j, s5_j) if s5 else sig_j
        fun["3 signal"] += 1
        side = "S" if armed == "up" else "L"
        sg = -1 if side == "S" else 1
        ext = max(H[i0:sj + 1]) if armed == "up" else min(L[i0:sj + 1])
        tgt, pts = liquidity(dd["b5"], x, t[sj], O, side, A)
        if tgt is None:
            continue
        fun["4 target found"] += 1
        # entry
        fill, fj = None, None
        for q in range(sj + 1, fl + 1):
            if tod[q] > END:
                break
            if et:
                touch = (H[q] >= O) if side == "S" else (L[q] <= O)
                if touch and ((C[q] < O) if side == "S" else (C[q] > O)):
                    fill, fj = C[q], q
                    break
            else:
                if (H[q] >= O) if side == "S" else (L[q] <= O):
                    fill, fj = (max(O, O_[q]) if side == "S" else min(O, O_[q])), q
                    break
        ref = O if not et else fill
        if fill is None:
            dist = sg * (tgt - O)
            fun["5 1:%d affordable" % div] += int(dist / div >= 0.4 * A)
            continue
        dist = sg * (tgt - ref)
        if dist <= 0 or dist / div < 0.4 * A:
            continue
        fun["5 1:%d affordable" % div] += 1
        fun["6 filled"] += 1
        risk = dist / div
        stop = ref - sg * risk
        entry = fill + sg * TICK
        be_c = [v for v in pts if sg * (v - ref) > 0 and sg * (tgt - v) > 0]
        be_lvl = (max(be_c) if side == "S" else min(be_c)) if be_c else None
        cur, be_on, res = stop, False, None
        for q in range(fj, fl + 1):
            o = O_[q]
            if q > fj and sg * (o - cur) <= 0:
                res = (q, o - sg * TICK, "BE" if be_on else "SL"); break
            if (L[q] <= cur) if sg > 0 else (H[q] >= cur):
                if q > fj or not et:
                    res = (q, cur - sg * TICK, "BE" if be_on else "SL"); break
            if q > fj:
                if sg * (o - tgt) >= 0:
                    res = (q, o - sg * TICK, "TP"); break
                if (H[q] >= tgt) if sg > 0 else (L[q] <= tgt):
                    res = (q, tgt - sg * TICK, "TP"); break
            if be_lvl is not None and not be_on and ((H[q] >= be_lvl) if sg > 0 else (L[q] <= be_lvl)) and q > fj:
                be_on, cur = True, fill
        if res is None:
            res = (fl, C[fl] - sg * TICK, "time")
        pnl = sg * (res[1] - entry) * PV - 2 * COMM
        out.append(dict(date=dd["date"], entry_time=t[fj], side=side, O=O, A=A, manip=armed, ext=ext, signal_t=t[sj],
                        target=tgt, be_level=be_lvl, stop=stop, fill=fill, entry=entry, risk=risk,
                        exit_time=t[res[0]], exit=res[1], reason=res[2], pnl=pnl, R=pnl / (risk * PV),
                        match=armed == dd["dir930"], on_ratio=dd["on_ratio"]))
    return pd.DataFrame(out), fun


def run_all(outdir):
    outdir = pathlib.Path(outdir); outdir.mkdir(parents=True, exist_ok=True)
    days, atr5 = prepare()
    rows = []
    for name, kw in RUNS.items():
        t, fun = run(days, atr5, **kw)
        t.to_csv(outdir / f"P2_{name}.csv", index=False)
        s = summary(t)
        print(f"\n==== {name}: " + "  ".join(f"{a} {b}" for a, b in s.items()))
        if not t.empty:
            y = t.entry_time.dt.year
            t["on_ter"] = pd.qcut(t.on_ratio.rank(method="first"), 3, labels=["low", "mid", "high"])
            for lab, col in (("year", y), ("side", t.side), ("exit", t.reason), ("manip matches 09:30-10:00", t.match),
                             ("overnight expansion tercile", t.on_ter)):
                print(f"  by {lab}: " + " | ".join(f"{a}: n {len(g)} net {g.pnl.sum():+,.0f} R {g.R.mean():+.3f}"
                                                   for a, g in t.groupby(col, observed=True)))
        print("  funnel: " + " -> ".join(f"{a[2:]} {b}" for a, b in sorted(fun.items())))
        ns = {}
        for kk in (0.35, 0.75):
            tn, _ = run(days, atr5, k=kk, **kw)
            ns[kk] = summary(tn)
            print(f"    neighbour {kk} A: " + "  ".join(f"{a} {b}" for a, b in ns[kk].items()))
        crit = dict(years=s.get("pos_years", 0) >= 6, R=s.get("R", -1) >= 0.05,
                    halves=(s.get("R_h1") if s.get("R_h1") is not None else -1) >= 0 and (s.get("R_h2") if s.get("R_h2") is not None else -1) >= 0,
                    neighbours=all(v.get("n", 0) > 0 and np.sign(v.get("R", 0)) == np.sign(s.get("R", 0)) for v in ns.values()),
                    bonferroni=s.get("p", 1) < 0.05 / 6)
        print(f"  criterion: {crit} -> {'PASS' if all(crit.values()) else 'fail'}")
        rows.append(dict(run=name, **s, **{f"c_{a}": b for a, b in crit.items()}, passes=all(crit.values())))
    r = pd.DataFrame(rows)
    print(r.to_string(index=False))
    r.to_csv(outdir / "P2_summary.csv", index=False)


def charts(n=10, seed=31, out="data/studies/powell2_charts"):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle
    days, atr5 = prepare()
    t, _ = run(days, atr5)
    dx = {d["date"]: d["x"] for d in days}
    rng = np.random.default_rng(seed)
    pick = t.iloc[np.sort(rng.choice(len(t), size=min(n, len(t)), replace=False))]
    out = pathlib.Path(out); out.mkdir(parents=True, exist_ok=True)
    key = []
    for c, r in enumerate(pick.itertuples(), 1):
        x = dx[r.date]
        x = x[x.index <= r.entry_time]
        fig, ax = plt.subplots(figsize=(15, 8))
        for i, (o, h, l, cl) in enumerate(zip(x.open, x.high, x.low, x.close)):
            col = "#26a69a" if cl >= o else "#ef5350"
            ax.plot([i, i], [l, h], color=col, lw=0.8)
            ax.add_patch(Rectangle((i - 0.35, min(o, cl)), 0.7, max(abs(cl - o), 0.05), color=col, lw=0))
        n_ = len(x)
        ix = lambda ts: int(np.searchsorted(x.index, ts))
        ax.axvline(ix(pd.Timestamp(f"{r.date} 10:00", tz=TZ)), color="#1565c0", lw=0.6, ls=":")
        ax.axvline(ix(r.signal_t), color="#6a1b9a", lw=0.6, ls=":")
        ax.text(ix(r.signal_t), x.high.max(), " signal (2nd close through O)", fontsize=8, color="#6a1b9a", va="top")
        lines = [(r.O, "O = 10:00 open", "#1565c0", "-"), (r.target, "target (liquidity)", "#2e7d32", "--"),
                 (r.stop, "stop (target / 5)", "#c62828", "-"), (r.ext, "manipulation extreme", "#7e57c2", "-.")]
        if pd.notna(r.be_level):
            lines.append((r.be_level, "break-even trigger", "#ef6c00", ":"))
        for y, lab, col, ls in lines:
            ax.axhline(y, color=col, ls=ls, lw=1)
            ax.text(n_ + 0.5, y, f" {lab} {y:,.2f}", fontsize=8, color=col, va="center")
        ax.plot(n_ - 1, r.fill, ">" if r.side == "L" else "<", color="black", ms=11)
        ticks = [i for i in range(n_) if x.index[i].minute % 5 == 0]
        ax.set_xticks(ticks, [x.index[i].strftime("%H:%M") for i in ticks], fontsize=7, rotation=90)
        ax.set_xlim(-1, n_ + 20)
        lo_, hi_ = min(x.low.min(), r.target, r.stop), max(x.high.max(), r.target, r.stop)
        ax.set_ylim(lo_ - 0.03 * (hi_ - lo_), hi_ + 0.03 * (hi_ - lo_))
        ax.set_title(f"powell2_{c:02d} · {r.date} · P2 base · {r.manip}side manipulation -> {'LONG' if r.side == 'L' else 'SHORT'} · "
                     f"limit at O filled {r.entry_time:%H:%M} · MNQ 1m cut at the fill · outcome hidden", fontsize=10)
        ax.grid(alpha=0.2)
        fig.tight_layout()
        fig.savefig(out / f"powell2_{c:02d}.png", dpi=95)
        plt.close(fig)
        key.append(dict(id=f"powell2_{c:02d}", date=r.date, entry_time=r.entry_time, side=r.side))
    pd.DataFrame(key).to_csv(out / "charts_key.csv", index=False)
    pd.DataFrame(dict(id=[k["id"] for k in key], setup_is_right="", target_is_right="", note="")).to_csv(out / "answers.csv", index=False)
    print(f"{len(key)} charts in {out}")


if __name__ == "__main__":
    if sys.argv[1] == "all":
        run_all(opt("--outdir", "data/studies/powell2"))
    else:
        charts(opt("--n", 10), opt("--seed", 31))
