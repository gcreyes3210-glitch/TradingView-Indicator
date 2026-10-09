#!/usr/bin/env python3
"""POWELL 10:00 model, as pre-registered in BACKTEST_LOG.md (2026-09-25). MNQ 1m, house fills.

    python3 tools/powell_engine.py all [--outdir DIR]        the six runs, neighbours, funnel, match-with-09:30 split
    python3 tools/powell_engine.py charts [--n 10] [--seed 21] [--out data/studies/powell_charts]

Reference = open of the 10:00 1m bar. ATR = RMA(14) of 5m bars (manipulation size: the 5m bar that closed at 10:00;
stop cap: the last 5m bar closed at the signal). Manipulation: one side of the reference reaches k x ATR (k = 0.5;
neighbours 0.35 / 0.75) while the other side has not been exceeded by more than 2 ticks by any bar before the
signal bar (both sides beyond 2 ticks before arming, or the other side broken after arming = void day).
Signal: the first 1m close back through the reference on the opposite side (may be the arming bar); entry at it.
Stop: the extreme from 10:00 through the signal bar + 2 ticks; skip if the distance > 1.5 x ATR. Windows: P1 signal
bar opens by 10:29, P4 by 13:59. Targets: 3 R, 5 R, IL = nearest confirmed 5m 3-bar fractal beyond the entry on the
profit side formed since 09:30 (skip if none or < 2 R). One trade a day; flat at the close of the last bar before
16:00, or on an early-close day at the close of the bar opening 10 minutes before the halt (halt read from the bars).
Fills: entry close + 1 tick; stop / target at the level (or the open if the bar opens beyond) - 1 tick; stop first
on a bar touching both; flatten at the close - 1 tick; $1 / side; MNQ $2 / point.
"""
import sys, math, pathlib, collections
import numpy as np
import pandas as pd

TZ = "America/New_York"
TICK, PV, COMM, TOL = 0.25, 2.0, 1.0, 0.5
opt = lambda k, d: type(d)(sys.argv[sys.argv.index(k) + 1]) if k in sys.argv else d
WIN = {"P1": 10 * 60 + 29, "P4": 13 * 60 + 59}


def rma_atr(h, l, c, n=14):
    pc = np.r_[np.nan, c[:-1]]
    tr = np.nanmax(np.c_[h - l, np.abs(h - pc), np.abs(l - pc)], axis=1)
    tr[0] = h[0] - l[0]
    return pd.Series(tr).ewm(alpha=1 / n, adjust=False).mean().to_numpy()


def load():
    one = pd.read_parquet("data/bars/MNQ_1m.parquet")
    b5 = pd.read_parquet("data/bars/MNQ_5m.parquet")
    atr5 = pd.Series(rma_atr(b5.high.to_numpy(), b5.low.to_numpy(), b5.close.to_numpy()), index=b5.index)
    days = []
    for d, x in one.groupby(one.index.date):
        m = x.index.hour * 60 + x.index.minute
        x = x[(m >= 9 * 60 + 30) & (m < 16 * 60)]
        if x.empty or not ((x.index.hour == 10) & (x.index.minute == 0)).any():
            continue
        days.append((d, x))
    return one, b5, atr5, days


def flat_index(x):
    """Index (in x) of the flatten bar: the last bar before 16:00, or the bar opening 10 min before an early halt."""
    t = x.index
    gaps = np.flatnonzero(np.diff(t.asi8) > 30 * 60 * 10 ** 9)
    last = gaps[0] if len(gaps) else len(t) - 1
    halt = t[last] + pd.Timedelta(minutes=1)
    if halt.hour * 60 + halt.minute < 16 * 60:
        cut = halt - pd.Timedelta(minutes=10)
        k = np.flatnonzero(t <= cut)
        return int(k[-1]) if len(k) else last
    return len(t) - 1


def atr_at(atr5, ts):
    """ATR of the last 5m bar closed by the end of the 1m bar opening at ts."""
    end = ts + pd.Timedelta(minutes=1)
    k = atr5.index.searchsorted(end - pd.Timedelta(minutes=5), side="right") - 1
    return atr5.iloc[k]


def fractals(b5, t0, t1, high):
    """5m fractal prices formed in [t0, ...) and confirmed (the bar after closed) by t1 (exclusive end time)."""
    x = b5[(b5.index >= t0 - pd.Timedelta(minutes=5)) & (b5.index < t1)]
    H, L, T = x.high.to_numpy(), x.low.to_numpy(), x.index
    out = []
    for p in range(1, len(x) - 1):
        if T[p] < t0 or T[p + 1] + pd.Timedelta(minutes=5) > t1:
            continue
        if high and H[p] > H[p - 1] and H[p] >= H[p + 1]:
            out.append(H[p])
        if not high and L[p] < L[p - 1] and L[p] <= L[p + 1]:
            out.append(L[p])
    return out


def signals(days, atr5, k=0.5, var="P1"):
    sig, fun = [], collections.Counter()
    for d, x in days:
        t = x.index
        tod = t.hour * 60 + t.minute
        O, H, L, C = (x[c].to_numpy() for c in ("open", "high", "low", "close"))
        i0 = int(np.flatnonzero((tod == 600))[0])
        fl = flat_index(x)
        ref = O[i0]
        a10 = atr_at(atr5, t[i0] - pd.Timedelta(minutes=1))
        if not a10 > 0:
            continue
        fun["1 days"] += 1
        m = k * a10
        pre = x[(tod >= 570) & (tod < 600)]
        dir930 = "up" if len(pre) and pre.close.iloc[-1] > pre.open.iloc[0] else "down"
        armed, hi, lo = None, -np.inf, np.inf
        for j in range(i0, len(x)):
            if tod[j] > WIN[var] or j >= fl:
                break
            hi, lo = max(hi, H[j]), min(lo, L[j])
            if armed is None:
                up, dn = hi - ref >= m and ref - lo <= TOL, ref - lo >= m and hi - ref <= TOL
                if up or dn:
                    armed = "up" if up else "down"
                    fun["2 manipulation"] += 1
                elif hi - ref > TOL and ref - lo > TOL:
                    break
            if armed is not None:
                if (armed == "up" and C[j] < ref) or (armed == "down" and C[j] > ref):
                    fun["3 signal in window"] += 1
                    side = "S" if armed == "up" else "L"
                    sg = -1 if side == "S" else 1
                    ext = hi if side == "S" else lo
                    stop = ext - sg * 2 * TICK
                    risk = sg * (C[j] - stop)
                    if risk > 1.5 * atr_at(atr5, t[j]):
                        break
                    fun["4 stop cap"] += 1
                    sig.append(dict(date=d, j=j, fl=fl, entry_time=t[j], side=side, close=C[j], stop=stop, risk=risk,
                                    ref=ref, ext=ext, atr10=a10, manip=armed, dir930=dir930, match=armed == dir930))
                    break
                if (armed == "up" and L[j] < ref - TOL) or (armed == "down" and H[j] > ref + TOL):
                    break
    return sig, fun


def trades(sig, days, b5, target):
    dx = dict(days)
    out, fun = [], collections.Counter()
    for s in sig:
        x = dx[s["date"]]
        O, H, L, C = (x[c].to_numpy() for c in ("open", "high", "low", "close"))
        sg = 1 if s["side"] == "L" else -1
        if target == "IL":
            day0 = pd.Timestamp(f"{s['date']} 09:30", tz=TZ)
            fr = fractals(b5, day0, s["entry_time"] + pd.Timedelta(minutes=1), s["side"] == "L")
            fr = [f for f in fr if sg * (f - s["close"]) > 0]
            if not fr or sg * ((min(fr) if sg > 0 else max(fr)) - s["close"]) < 2 * s["risk"]:
                fun["IL skip"] += 1
                continue
            tp = min(fr) if sg > 0 else max(fr)
        else:
            tp = s["close"] + sg * int(target[:-1]) * s["risk"]
        entry = s["close"] + sg * TICK
        res = None
        for q in range(s["j"] + 1, s["fl"] + 1):
            o = O[q]
            if sg * (o - s["stop"]) <= 0:
                res = (q, o - sg * TICK, "SL"); break
            if sg * (o - tp) >= 0:
                res = (q, o - sg * TICK, "TP"); break
            if (L[q] <= s["stop"]) if sg > 0 else (H[q] >= s["stop"]):
                res = (q, s["stop"] - sg * TICK, "SL"); break
            if (H[q] >= tp) if sg > 0 else (L[q] <= tp):
                res = (q, tp - sg * TICK, "TP"); break
        if res is None:
            res = (s["fl"], C[s["fl"]] - sg * TICK, "time")
        pnl = sg * (res[1] - entry) * PV - 2 * COMM
        out.append({**s, "tp": tp, "entry": entry, "exit_time": x.index[res[0]], "exit": res[1], "reason": res[2],
                    "pnl": pnl, "R": pnl / (s["risk"] * PV)})
    return pd.DataFrame(out), fun


def summary(t):
    if t.empty:
        return dict(n=0)
    y = t.entry_time.dt.year
    eq = t.pnl.cumsum()
    gw, gl = t.pnl[t.pnl > 0].sum(), -t.pnl[t.pnl < 0].sum()
    h1, h2 = t[y <= 2022], t[y >= 2023]
    se = t.R.std(ddof=1) / math.sqrt(len(t))
    p = 0.5 * math.erfc((t.R.mean() / se) / math.sqrt(2)) if se > 0 else float("nan")
    return dict(n=len(t), net=round(t.pnl.sum()), R=round(t.R.mean(), 3), win=round(100 * (t.pnl > 0).mean(), 1),
                pf=round(gw / gl, 2) if gl else None, dd=round((eq - eq.cummax()).min()),
                pos_years=int((t.groupby(y).pnl.sum() > 0).sum()), years=int(y.nunique()),
                R_h1=round(h1.R.mean(), 3) if len(h1) else None, R_h2=round(h2.R.mean(), 3) if len(h2) else None,
                p=round(p, 4))


def run_all(outdir):
    outdir = pathlib.Path(outdir); outdir.mkdir(parents=True, exist_ok=True)
    one, b5, atr5, days = load()
    rows = []
    for var in ("P1", "P4"):
        base, fun = signals(days, atr5, 0.5, var)
        nb = {k: signals(days, atr5, k, var)[0] for k in (0.35, 0.75)}
        for tgt in ("3R", "5R", "IL"):
            t, f2 = trades(base, days, b5, tgt)
            t.to_csv(outdir / f"POWELL_{var}_{tgt}.csv", index=False)
            s = summary(t)
            print(f"\n==== {var} {tgt}: " + "  ".join(f"{k} {v}" for k, v in s.items()))
            y = t.entry_time.dt.year
            for name, col in (("year", y), ("side", t.side), ("exit", t.reason), ("manip matches 09:30-10:00", t.match)):
                print(f"  by {name}: " + " | ".join(f"{k}: n {len(g)} net {g.pnl.sum():+,.0f} R {g.R.mean():+.3f}" for k, g in t.groupby(col)))
            print("  funnel: " + " -> ".join(f"{k[2:]} {v}" for k, v in sorted(fun.items())) +
                  (f" -> IL skipped {f2['IL skip']}" if tgt == "IL" else "") + f" -> trades {len(t)}")
            ns = {}
            for k, sg in nb.items():
                tn, _ = trades(sg, days, b5, tgt)
                ns[k] = summary(tn)
                print(f"    neighbour {k} ATR: " + "  ".join(f"{a} {b}" for a, b in ns[k].items()))
            crit = dict(years=s.get("pos_years", 0) >= 6, R=s.get("R", -1) >= 0.05,
                        halves=(s.get("R_h1") or -1) >= 0 and (s.get("R_h2") or -1) >= 0,
                        neighbours=all(np.sign(v.get("R", 0)) == np.sign(s.get("R", 0)) and v.get("n", 0) > 0 for v in ns.values()),
                        bonferroni=s.get("p", 1) < 0.05 / 6)
            print(f"  criterion: {crit} -> {'PASS' if all(crit.values()) else 'fail'}")
            rows.append(dict(run=f"{var} {tgt}", **s, **{f"c_{a}": b for a, b in crit.items()}, passes=all(crit.values())))
    print(pd.DataFrame(rows).to_string(index=False))
    pd.DataFrame(rows).to_csv(outdir / "POWELL_summary.csv", index=False)


def charts(n=10, seed=21, out="data/studies/powell_charts"):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle
    one, b5, atr5, days = load()
    sig, _ = signals(days, atr5, 0.5, "P1")
    t, _ = trades(sig, days, b5, "3R")
    rng = np.random.default_rng(seed)
    pick = t.iloc[np.sort(rng.choice(len(t), size=n, replace=False))]
    out = pathlib.Path(out); out.mkdir(parents=True, exist_ok=True)
    dx = dict(days)
    key = []
    for c, r in enumerate(pick.itertuples(), 1):
        x = dx[r.date].iloc[:r.j + 1]
        fig, ax = plt.subplots(figsize=(15, 8))
        for i, (o, h, l, cl) in enumerate(zip(x.open, x.high, x.low, x.close)):
            col = "#26a69a" if cl >= o else "#ef5350"
            ax.plot([i, i], [l, h], color=col, lw=0.8)
            ax.add_patch(Rectangle((i - 0.35, min(o, cl)), 0.7, max(abs(cl - o), 0.05), color=col, lw=0))
        n_ = len(x)
        i0 = int(np.flatnonzero((x.index.hour == 10) & (x.index.minute == 0))[0])
        ax.axvline(i0, color="#1565c0", lw=0.6, ls=":")
        ax.axhline(r.ref, color="#1565c0", lw=1.2)
        ax.text(0, r.ref, f" 10:00 open {r.ref:,.2f}", fontsize=8, color="#1565c0", va="bottom")
        m = 0.5 * r.atr10
        lvl = r.ref + m if r.manip == "up" else r.ref - m
        ax.axhline(lvl, color="#7e57c2", lw=0.8, ls="--")
        ax.text(0, lvl, f" manipulation threshold 0.5 x 5m ATR ({m:.2f} pts)", fontsize=8, color="#5e35b1", va="bottom")
        ax.axhline(r.stop, color="#c62828", lw=1.1)
        ax.text(n_ + 0.5, r.stop, f" stop {r.stop:,.2f} (extreme {r.ext:,.2f} + 2 ticks)", fontsize=8, color="#c62828", va="center")
        ax.plot(n_ - 1, r.close, ">" if r.side == "L" else "<", color="black", ms=11)
        ax.text(n_ + 0.5, r.close, f" entry {'LONG' if r.side == 'L' else 'SHORT'} {r.close:,.2f} (close back through, {r.entry_time:%H:%M})", fontsize=8, va="center")
        ticks = [i for i in range(n_) if x.index[i].minute % 5 == 0]
        ax.set_xticks(ticks, [x.index[i].strftime("%H:%M") for i in ticks], fontsize=7, rotation=90)
        ax.set_xlim(-1, n_ + 14)
        ax.set_title(f"powell_{c:02d} · {r.date} · P1 · {r.manip}side manipulation from the 10:00 open -> "
                     f"{'LONG' if r.side == 'L' else 'SHORT'} · MNQ 1m cut at entry · outcome hidden", fontsize=10)
        ax.grid(alpha=0.2)
        fig.tight_layout()
        fig.savefig(out / f"powell_{c:02d}.png", dpi=95)
        plt.close(fig)
        key.append(dict(id=f"powell_{c:02d}", date=r.date, entry_time=r.entry_time, side=r.side))
    pd.DataFrame(key).to_csv(out / "charts_key.csv", index=False)
    pd.DataFrame(dict(id=[k["id"] for k in key], manipulation_is_right="", entry_is_right="", note="")).to_csv(out / "answers.csv", index=False)
    print(f"{len(key)} charts in {out}")


if __name__ == "__main__":
    if sys.argv[1] == "all":
        run_all(opt("--outdir", "data/studies/powell"))
    else:
        charts(opt("--n", 10), opt("--seed", 21))
