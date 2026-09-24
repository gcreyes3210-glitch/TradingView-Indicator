#!/usr/bin/env python3
"""BLIND2: 100-setup blind review with four context panels per setup, and its pre-registered scoring.

    python3 tools/blind2.py make  [--seed 23] [--out data/studies/blind2]
    python3 tools/blind2.py score <answers.csv> [--reveal]      (columns: id, answer yes/no, confidence 1-3)

make: 100 setups from the AMD1-1m, OB1-1m and OTE1-1m setup lists with shadow setups included (taken, AMD reward:risk
    skips with a simulated result, OB / OTE limits that expired unfilled = 0), 34 / 33 / 33 by family (which family
    gets 34 is random), drawn round-robin across the years 2019-2026, uniformly within family (numpy default_rng(seed)).
    One PNG per setup, every panel cut at the decision bar (AMD trigger bar, OB BOS bar, OTE MSS bar) and rebuilt from
    1m bars up to it, so nothing after the decision is visible:
      1  MNQ 1m from 09:30: overnight range, the setup markings, proposed entry and stop (as blind_review.py)
      2  MNQ 5m over the prior cash session and the overnight session (to the decision bar): prior-day high, low and
         settlement (drawn as the last 1m close before 16:00; CME's settlement is a VWAP of the final 30 s)
      3  MNQ 1h over the prior 10 cash sessions: 1h and 4h FVGs (4h bars from 18:00) not fully traded through by the
         decision bar as shaded boxes; the swing range = the window's high and low, the leg running from the older
         extreme to the more recent one, with its 0.618-0.79 retracement (OTE) zone shaded
      4  ES (MES 1m bars: same index and price scale, full sessions; the ES trades slice covers only the ORB days) on
         panel 1's time axis: overnight high / low and the morning 3-bar swing highs / lows, for SMT comparison
    No date, target or outcome is shown (prices still hint at the era). Files <out>/<random 6-digit id>.png; the key
    (id -> family, date, side, status, filled, pnl, R) goes to <out>/key.csv and is never printed by make.
score (pre-registered 2026-09-23, before any answer):
    1. yes vs no: R per setup (unfilled = 0) and a 20,000-permutation shuffle p, one-sided (yes better than no).
    2. confidence-3 picks = setups answered yes with confidence 3, against all other setups: R per setup, net, filled
       trades (taken, or a simulated AMD fill; unfilled limits are not filled), shuffle p (the pick label permuted over
       the 100 setups, 20,000 times, one-sided). Evidence of discretionary edge ONLY IF >= 25 filled trades AND net > 0
       AND p < 0.05.
"""
import sys, pathlib
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from blind_review import pools, fvgs

TZ = "America/New_York"
opt = lambda k, d: type(d)(sys.argv[sys.argv.index(k) + 1]) if k in sys.argv else d
OUT = pathlib.Path(opt("--out", "data/studies/blind2"))
UP, DN = "#26a69a", "#ef5350"


def candles(ax, b):
    for i, (o, h, l, c) in enumerate(zip(b.open, b.high, b.low, b.close)):
        col = UP if c >= o else DN
        ax.plot([i, i], [l, h], color=col, lw=0.7)
        ax.add_patch(Rectangle((i - 0.35, min(o, c)), 0.7, max(abs(c - o), 0.05), color=col, lw=0))


def ohlc(x, rule, origin="start_day"):
    return x.resample(rule, label="left", closed="left", origin=origin).agg(
        {"open": "first", "high": "max", "low": "min", "close": "last"}).dropna()


def labelled_lines(ax, n, lines):
    lo, hi = ax.get_ylim()
    gap, placed = 0.035 * (hi - lo), []
    for y, lab, col, ls in lines:
        ax.plot([0, n + 2], [y, y], color=col, ls=ls, lw=1.1)
    for y, lab, col, ls in sorted(lines, key=lambda z: -z[0]):
        yy = y
        while any(abs(yy - q) < gap for q in placed):
            yy -= gap
        placed.append(yy)
        ax.annotate(f" {lab} {y:,.2f}", (n + 2, y), xytext=(n + 2.5, yy), fontsize=7, color=col, va="center",
                    arrowprops=dict(arrowstyle="-", color=col, lw=0.5) if yy != y else None)
    ax.set_xlim(-1, n + max(14, n // 4))


def sessions(one):
    tod = one.index.hour * 60 + one.index.minute
    return np.array(sorted(set(one.index[tod == 570].date)))


def overnight(x, d):
    w = x[(x.index >= pd.Timestamp(d, tz=TZ) - pd.Timedelta(days=4)) & (x.index < pd.Timestamp(f"{d} 09:30", tz=TZ))]
    w = w[w.index >= w[(w.index.hour == 18) & (w.index.minute == 0)].index[-1]]
    return w.high.max(), w.low.min()


def panel1(ax, one, r, fam):
    d, dec = r.decision_t.date(), r.decision_t
    b = one[(one.index >= pd.Timestamp(f"{d} 09:30", tz=TZ)) & (one.index <= dec)]
    X = lambda t: int(np.searchsorted(b.index, pd.Timestamp(t)))
    candles(ax, b)
    n, long_ = len(b), r.side == "L"
    onH, onL = overnight(one, d)
    lines = [(onH, "overnight high", "#7e57c2", "--"), (onL, "overnight low", "#7e57c2", "--")]

    def mark(t, y, lab, col, m="o", dy=0):
        ax.plot(X(t), y, marker=m, color=col, ms=8, mec="black", mew=0.5, zorder=5)
        ax.annotate(lab, (X(t), y), xytext=(6, 9 + dy), textcoords="offset points", fontsize=7, color=col,
                    arrowprops=dict(arrowstyle="-", color=col, lw=0.5))

    def band(t0, lo, hi, lab, col, a=0.2):
        ax.add_patch(Rectangle((X(t0) - 0.5, lo), n + 2 - X(t0), hi - lo, color=col, alpha=a, lw=0))
        ax.text(X(t0), hi, f" {lab}", fontsize=7, color=col, va="bottom")

    if fam == "AMD":
        w = b[b.index >= pd.Timestamp(r.sweep_t)]
        mark(w.low.idxmin() if long_ else w.high.idxmax(), r.ext, "sweep extreme", "#c62828")
        mark(r.leg_t, r.leg_px, "sweep-leg start (MSS level)", "#1565c0", dy=-26)
        mark(r.conf_t, b.close.iloc[X(r.conf_t)], "close back inside", "#6a1b9a", "s", dy=18)
        for g in fvgs(b, pd.Timestamp(r.leg_t), pd.Timestamp(r.conf_t), not long_):
            band(g[0], g[1], g[2], "FVG in the sweep leg", "#ffb300", 0.35)
        entry, prop = b.close.iloc[-1], "entry at this bar's close"
    elif fam == "OB":
        mark(r.frac_t, r.frac_px, "fractal swing broken", "#1565c0")
        mark(r.bos_t, b.close.iloc[-1], "BOS close", "#1565c0", "s", dy=-26)
        for g in fvgs(b, pd.Timestamp(r.ob_t), pd.Timestamp(r.bos_t), long_):
            band(g[0], g[1], g[2], "FVG (leg)", "#ffb300", 0.35)
        band(r.ob_t, r.ob_lo, r.ob_hi, "order block", "#546e7a")
        entry, prop = r.lim, "limit at the block edge (30 bars)"
    else:
        if pd.notna(r.sweep_t):
            mark(r.base_t, r.base_px, "sweep extreme (leg 0 %)", "#c62828")
        mark(r.frac_t, r.frac_px, "fractal broken (MSS level)", "#1565c0", dy=-26)
        mark(r.mss_t, b.close.iloc[-1], "MSS close", "#1565c0", "s", dy=18)
        ax.plot([X(r.base_t), n - 1], [r.base_px, r.ext_mss], color="#6a1b9a", lw=1.4)
        leg = abs(r.ext_mss - r.base_px)
        z = (r.ext_mss - 0.79 * leg, r.ext_mss - 0.62 * leg) if long_ else (r.ext_mss + 0.62 * leg, r.ext_mss + 0.79 * leg)
        band(r.mss_t, z[0], z[1], "OTE zone 62-79 %", "#00897b")
        for g in fvgs(b, pd.Timestamp(r.base_t), pd.Timestamp(r.mss_t), long_):
            band(g[0], g[1], g[2], "FVG (leg)", "#ffb300", 0.35)
        entry, prop = r.level_mss, "limit at 70.5 % of the leg (trails until filled)"
    lines += [(entry, "proposed entry", "black", ":"), (r.stop, "stop", DN, "-")]
    labelled_lines(ax, n, lines)
    ticks = [i for i, t in enumerate(b.index) if t.minute % 15 == 0]
    ax.set_xticks(ticks, [b.index[i].strftime("%H:%M") for i in ticks], fontsize=7)
    ax.set_title(f"1  MNQ 1m from 09:30 — proposed {'LONG' if long_ else 'SHORT'}: {prop}", fontsize=9, loc="left")
    return b.index


def panel2(ax, one, r, sess):
    d, dec = r.decision_t.date(), r.decision_t
    k = np.searchsorted(sess, d)
    pdd = sess[k - 1]
    x = one[(one.index >= pd.Timestamp(f"{pdd} 09:30", tz=TZ)) & (one.index <= dec)]
    b = ohlc(x, "5min")
    candles(ax, b)
    rthp = x[(x.index.date == pdd) & (x.index.hour * 60 + x.index.minute < 960)]
    rthp = rthp[rthp.index.hour * 60 + rthp.index.minute >= 570]
    lines = [(rthp.high.max(), "prior-day high", "#1565c0", "-"), (rthp.low.min(), "prior-day low", "#1565c0", "-"),
             (rthp.close.iloc[-1], "settlement (last 1m close before 16:00)", "#ef6c00", "--")]
    onH, onL = overnight(one, d)
    lines += [(onH, "overnight high", "#7e57c2", "--"), (onL, "overnight low", "#7e57c2", "--")]
    labelled_lines(ax, len(b), lines)
    marks = {}
    for i, t in enumerate(b.index):
        tag = "prior RTH 09:30" if (t.date() == pdd and t.hour == 9 and t.minute == 30) else \
              "overnight 18:00" if (t.hour == 18 and t.minute == 0) else \
              "today 09:30" if (t.date() == d and t.hour == 9 and t.minute == 30) else None
        if tag:
            marks[i] = tag
            ax.axvline(i, color="grey", lw=0.6, ls=":")
    ax.set_xticks(list(marks), list(marks.values()), fontsize=7)
    ax.set_title("2  MNQ 5m: prior cash session and overnight, to the decision bar", fontsize=9, loc="left")


def panel3(ax, one, r, sess):
    d, dec = r.decision_t.date(), r.decision_t
    k = np.searchsorted(sess, d)
    start = pd.Timestamp(f"{sess[max(k - 10, 0)]} 09:30", tz=TZ)
    x = one[(one.index >= start) & (one.index <= dec)]
    h1 = ohlc(x, "1h")
    h4 = ohlc(x, "4h", origin=pd.Timestamp("2019-01-01 18:00", tz=TZ))
    candles(ax, h1)
    n = len(h1)
    X = lambda t: int(np.searchsorted(h1.index, t))
    xt = x.index
    sufmin = np.minimum.accumulate(x.low.to_numpy()[::-1])[::-1]      # lowest low from each 1m bar to the cut
    sufmax = np.maximum.accumulate(x.high.to_numpy()[::-1])[::-1]
    for bars, col, lab, step in ((h1, "#ffb300", "1h FVG", pd.Timedelta(hours=1)), (h4, "#8d6e63", "4h FVG", pd.Timedelta(hours=4))):
        H, L = bars.high.to_numpy(), bars.low.to_numpy()
        for i in range(2, len(bars)):
            j = np.searchsorted(xt, bars.index[i] + step)               # first 1m bar after the gap's third bar
            for bull in (True, False):
                lo, hi = (H[i - 2], L[i]) if bull else (H[i], L[i - 2])
                if hi <= lo:
                    continue
                filled = j < len(xt) and ((sufmin[j] <= lo) if bull else (sufmax[j] >= hi))
                if not filled:
                    t0 = X(bars.index[i - 2])
                    ax.add_patch(Rectangle((t0 - 0.5, lo), n + 1 - t0, hi - lo, color=col, alpha=0.3, lw=0))
                    ax.text(t0, hi, f" {lab}", fontsize=6, color=col, va="bottom")
    hi_t, lo_t = x.high.idxmax(), x.low.idxmin()
    H, Lo = x.high.max(), x.low.min()
    up = hi_t > lo_t                                   # leg from the older extreme to the more recent one
    rng_ = H - Lo
    z = (H - 0.79 * rng_, H - 0.618 * rng_) if up else (Lo + 0.618 * rng_, Lo + 0.79 * rng_)
    ax.add_patch(Rectangle((-0.5, z[0]), n + 1, z[1] - z[0], color="#00897b", alpha=0.15, lw=0))
    ax.text(0, z[1], f" OTE 0.618-0.79 of the {'up' if up else 'down'} leg", fontsize=7, color="#00897b", va="bottom")
    labelled_lines(ax, n, [(H, "10-session swing high", "#37474f", "-"), (Lo, "10-session swing low", "#37474f", "-")])
    lab = {}
    for i, t in enumerate(h1.index):
        if t.hour == 9 and t.date() in set(sess):
            dd = t.date()
            lab[i] = "today" if dd == d else f"session -{k - int(np.searchsorted(sess, dd))}"
    ax.set_xticks(list(lab), list(lab.values()), fontsize=7)
    ax.set_title("3  MNQ 1h, prior 10 sessions: unfilled 1h / 4h FVGs, swing range and its OTE zone", fontsize=9, loc="left")


def panel4(ax, es, r, t_axis):
    d, dec = r.decision_t.date(), r.decision_t
    b = es[(es.index >= pd.Timestamp(f"{d} 09:30", tz=TZ)) & (es.index <= dec)].reindex(t_axis)
    candles(ax, b.ffill())
    n = len(b)
    onH, onL = overnight(es, d)
    H, L = b.high.to_numpy(), b.low.to_numpy()
    for i in range(1, n - 1):                         # 3-bar swings confirmed by the next bar (all before the cut)
        if H[i] > H[i - 1] and H[i] > H[i + 1]:
            ax.plot(i, H[i], "v", color="#c62828", ms=5)
        if L[i] < L[i - 1] and L[i] < L[i + 1]:
            ax.plot(i, L[i], "^", color="#2e7d32", ms=5)
    labelled_lines(ax, n, [(onH, "ES overnight high", "#7e57c2", "--"), (onL, "ES overnight low", "#7e57c2", "--")])
    ticks = [i for i, t in enumerate(b.index) if t.minute % 15 == 0]
    ax.set_xticks(ticks, [b.index[i].strftime("%H:%M") for i in ticks], fontsize=7)
    ax.set_title("4  ES (MES) 1m, same time axis as 1: overnight range, morning swing highs ▼ / lows ▲ (SMT)",
                 fontsize=9, loc="left")


def make():
    rng = np.random.default_rng(opt("--seed", 23))
    one, P = pools()
    es = pd.read_parquet("data/bars/MES_1m.parquet")
    sess = sessions(one)
    OUT.mkdir(parents=True, exist_ok=True)
    fams = ["AMD", "OB", "OTE"]
    sizes = dict(zip(fams, [33, 33, 33]))
    sizes[fams[rng.integers(3)]] += 1
    ids = rng.choice(np.arange(100000, 1000000), size=100, replace=False)
    key, k = [], 0
    for fam in fams:
        t = P[fam]
        years = list(rng.permutation(sorted(t.year.unique())))
        chosen = []
        while len(chosen) < sizes[fam]:
            for y in years:
                c = t[(t.year == y) & ~t.index.isin(chosen)]
                if len(c) and len(chosen) < sizes[fam]:
                    chosen.append(c.index[rng.integers(len(c))])
        for _, r in t.loc[chosen].iterrows():
            sid = int(ids[k]); k += 1
            fig, axs = plt.subplots(2, 2, figsize=(22, 12))
            t_axis = panel1(axs[0, 0], one, r, fam)
            panel2(axs[0, 1], one, r, sess)
            panel3(axs[1, 0], one, r, sess)
            panel4(axs[1, 1], es, r, t_axis)
            for a in axs.flat:
                a.grid(alpha=0.2); a.tick_params(axis="y", labelsize=7)
            fig.suptitle(f"Setup {sid} · {fam} · proposed {'LONG' if r.side == 'L' else 'SHORT'} · every panel ends at the "
                         f"decision bar", fontsize=12)
            fig.tight_layout()
            fig.savefig(OUT / f"{sid}.png", dpi=72)
            plt.close(fig)
            key.append(dict(id=sid, family=fam, date=r.decision_t.date(), side=r.side, status=r.status,
                            taken=bool(r.taken), filled=r.status in ("taken", "skipped_rr"),
                            pnl=round(float(r.pnl), 2), R=round(float(r.R), 4)))
    key = pd.DataFrame(key).sample(frac=1, random_state=int(rng.integers(1 << 31))).reset_index(drop=True)
    key.to_csv(OUT / "key.csv", index=False)
    print(f"{len(key)} charts in {OUT}/, key saved (not printed). Families {key.family.value_counts().to_dict()}; "
          f"years {key.date.map(lambda z: z.year).value_counts().sort_index().to_dict()}")


def perm_p(R, lab, rng, n=20000):
    obs = R[lab].mean() - R[~lab].mean()
    sims = np.array([(lambda q: R[q].mean() - R[~q].mean())(rng.permutation(lab)) for _ in range(n)])
    return obs, (sims >= obs).mean()


def score():
    ans = pd.read_csv(sys.argv[2])
    key = pd.read_csv(OUT / "key.csv")
    x = key.merge(ans.assign(id=ans.id.astype(int)), on="id", how="inner")
    x["yes"] = x.answer.str.strip().str.lower().isin(("yes", "y", "1", "true"))
    x["c3"] = x.yes & (x.confidence.astype(int) == 3)
    rng = np.random.default_rng(1)
    R = x.R.to_numpy()
    print(f"answers matched: {len(x)} of {len(key)} (win = net > 0; unfilled limits are 0 R, not filled, not a win)")
    for lab, g in (("yes", x[x.yes]), ("no", x[~x.yes])):
        print(f"  {lab:<3} {len(g):>3} setups · net {g.pnl.sum():>+9,.1f} · R per setup {g.R.mean():>+.3f} · win "
              f"{100 * (g.pnl > 0).mean():>5.1f} % · filled {int(g.filled.sum())} · engine-taken {int(g.taken.sum())}")
    obs, p = perm_p(R, x.yes.to_numpy(), rng)
    print(f"  1. yes - no: {obs:+.3f} R per setup, shuffle p {p:.4f}")
    c = x[x.c3]
    obs3, p3 = perm_p(R, x.c3.to_numpy(), rng) if 0 < len(c) < len(x) else (float("nan"), float("nan"))
    ok = int(c.filled.sum()) >= 25 and c.pnl.sum() > 0 and p3 < 0.05
    print(f"  2. confidence-3 picks: {len(c)} setups, filled {int(c.filled.sum())}, net {c.pnl.sum():+,.1f}, R per setup "
          f"{c.R.mean() if len(c) else float('nan'):+.3f} vs the rest {x[~x.c3].R.mean():+.3f} ({obs3:+.3f}), shuffle p {p3:.4f}"
          f"\n     -> {'EVIDENCE of discretionary edge' if ok else 'not evidence'} (needs >= 25 filled, net > 0, p < 0.05)")
    for fam in ("AMD", "OB", "OTE"):
        g = x[x.family == fam]
        print(f"  {fam}: yes {int(g.yes.sum())} ({g[g.yes].R.mean():+.3f} R) · no {int((~g.yes).sum())} "
              f"({g[~g.yes].R.mean():+.3f} R) · confidence-3 picks {int(g.c3.sum())}")
    if "--reveal" in sys.argv:
        print(x.sort_values(["family", "date"])[["id", "family", "date", "side", "status", "pnl", "R", "answer",
                                                  "confidence"]].to_string(index=False))


if __name__ == "__main__":
    {"make": make, "score": score}[sys.argv[1]]()
