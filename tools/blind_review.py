#!/usr/bin/env python3
"""Blind setup review: charts that end at the decision bar, a private key, and scoring of a yes / no list.

    python3 tools/blind_review.py make  [--seed 7] [--out data/studies/blind]
    python3 tools/blind_review.py score <answers.csv>        (columns: id, answer = yes / no)

make: 30 setups, 10 per family (AMD1-1m, OB1-1m, OTE1-1m defaults), 5 the engine took and 5 that formed but were not
    traded, each group spread over different years where possible (numpy default_rng(seed)). Not traded = AMD setups
    skipped for reward:risk < 1.0 (outcome simulated with the normal exits) and OB / OTE limits that expired unfilled
    (outcome 0: no trade). Each chart runs from 09:30 to the decision bar — AMD: the trigger bar (entry at its close);
    OB: the BOS bar (the limit is placed from here); OTE: the MSS bar (limit at 70.5 % of the leg as of that close; it
    then trails the leg's extreme until filled) — so fills cannot give the outcome away. Shown: overnight range,
    fractal / leg / FVGs / zone, the proposed entry and stop. Not shown: date, target, anything after the decision
    bar. Files are named by a random 6-digit number; the number -> outcome key goes to <out>/key.csv, which this
    tool never prints.
score: net and R per setup (unfilled = 0) for the setups answered yes versus no, and a shuffle p for the difference
    in R per setup (answers permuted 20,000 times, one-sided: yes better than no). Prints aggregates only.
"""
import sys, pathlib
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
sys.path.insert(0, str(pathlib.Path(__file__).parent))

TZ = "America/New_York"
opt = lambda k, d: type(d)(sys.argv[sys.argv.index(k) + 1]) if k in sys.argv else d
OUT = pathlib.Path(opt("--out", "data/studies/blind"))
UP, DN = "#26a69a", "#ef5350"


def pools():
    import ob_engine, amd_engine, ote_engine
    one = pd.read_parquet("data/bars/MNQ_1m.parquet")
    out = {}
    for fam, mod in (("AMD", amd_engine), ("OB", ob_engine), ("OTE", ote_engine)):
        t = mod.run(one, tf=1, shadow=True)[0]
        dec = {"AMD": "trig_t", "OB": "bos_t", "OTE": "mss_t"}[fam]
        t["decision_t"] = pd.to_datetime(t[dec])
        t["year"] = t.decision_t.dt.year
        t["taken"] = t.status == "taken"
        out[fam] = t
    return one, out


def pick(df, n, rng):
    """n rows from df, one per year where possible (years in random order, one random row per year)."""
    years = rng.permutation(sorted(df.year.unique()))
    rows = []
    while len(rows) < n:
        for y in years:
            cand = df[(df.year == y) & ~df.index.isin(rows)]
            if len(cand) and len(rows) < n:
                rows.append(cand.index[rng.integers(len(cand))])
        if all(len(df[(df.year == y) & ~df.index.isin(rows)]) == 0 for y in years):
            break
    return df.loc[rows]


def fvgs(b, t0, t1, bullish):
    x = b[(b.index >= t0 - pd.Timedelta(minutes=2)) & (b.index <= t1)]
    out = []
    for i in range(2, len(x)):
        if bullish and x.high.iloc[i - 2] < x.low.iloc[i] and x.index[i] >= t0:
            out.append((x.index[i - 2], x.high.iloc[i - 2], x.low.iloc[i]))
        if not bullish and x.low.iloc[i - 2] > x.high.iloc[i] and x.index[i] >= t0:
            out.append((x.index[i - 2], x.high.iloc[i], x.low.iloc[i - 2]))
    return out


def chart(one, r, fam, sid, path):
    d = r.decision_t.date()
    b = one[(one.index >= pd.Timestamp(f"{d} 09:30", tz=TZ)) & (one.index <= r.decision_t)]
    X = lambda t: int(np.searchsorted(b.index, t))
    on = one[(one.index >= pd.Timestamp(d, tz=TZ) - pd.Timedelta(days=4)) & (one.index < pd.Timestamp(f"{d} 09:30", tz=TZ))]
    on = on[on.index >= on[(on.index.hour == 18) & (on.index.minute == 0)].index[-1]]
    onH, onL = on.high.max(), on.low.min()
    fig, ax = plt.subplots(figsize=(14, 7.5))
    for i, (o, h, l, c) in enumerate(zip(b.open, b.high, b.low, b.close)):
        col = UP if c >= o else DN
        ax.plot([i, i], [l, h], color=col, lw=0.8)
        ax.add_patch(Rectangle((i - 0.35, min(o, c)), 0.7, max(abs(c - o), 0.05), color=col, lw=0))
    n = len(b)
    labels = []
    hl = lambda y, lab, col, ls="-": (ax.plot([0, n + 3], [y, y], color=col, ls=ls, lw=1.2), labels.append((y, lab, col)))

    def mark(t, y, lab, col, m="o", dy=0):
        ax.plot(X(t), y, marker=m, color=col, ms=9, mec="black", mew=0.6, zorder=5)
        ax.annotate(lab, (X(t), y), xytext=(8, 10 + dy), textcoords="offset points", fontsize=8, color=col,
                    arrowprops=dict(arrowstyle="-", color=col, lw=0.6))

    def band(t0, lo, hi, lab, col, a=0.2):
        ax.add_patch(Rectangle((X(t0) - 0.5, lo), n + 3 - X(t0), hi - lo, color=col, alpha=a, lw=0))
        ax.text(X(t0), hi, f" {lab}", fontsize=8, color=col, va="bottom")

    long_ = r.side == "L"
    hl(onH, "overnight high", "#7e57c2", "--"); hl(onL, "overnight low", "#7e57c2", "--")
    if fam == "AMD":
        w = b[b.index >= pd.Timestamp(r.sweep_t)]
        mark((w.low.idxmin() if long_ else w.high.idxmax()), r.ext, "sweep extreme", "#c62828")
        mark(pd.Timestamp(r.leg_t), r.leg_px, "sweep-leg start (MSS level)", "#1565c0", dy=-30)
        mark(pd.Timestamp(r.conf_t), b.close.iloc[X(pd.Timestamp(r.conf_t))], "close back inside", "#6a1b9a", "s", dy=20)
        for g in fvgs(b, pd.Timestamp(r.leg_t), pd.Timestamp(r.conf_t), not long_):
            band(g[0], g[1], g[2], "FVG in the sweep leg", "#ffb300", 0.35)
        entry = b.close.iloc[-1]
        prop = f"proposed entry: {'buy' if long_ else 'sell'} at this bar's close"
    elif fam == "OB":
        mark(pd.Timestamp(r.frac_t), r.frac_px, "fractal swing broken", "#1565c0")
        mark(pd.Timestamp(r.bos_t), b.close.iloc[-1], "BOS close", "#1565c0", "s", dy=-30)
        for g in fvgs(b, pd.Timestamp(r.ob_t), pd.Timestamp(r.bos_t), long_):
            band(g[0], g[1], g[2], "FVG (leg)", "#ffb300", 0.35)
        band(pd.Timestamp(r.ob_t), r.ob_lo, r.ob_hi, "order block", "#546e7a")
        entry = r.lim
        prop = f"proposed entry: {'buy' if long_ else 'sell'} limit at the block edge (valid 30 bars)"
    else:
        if pd.notna(r.sweep_t):
            mark(pd.Timestamp(r.sweep_t), r.base_px, "sweep of the overnight extreme", "#c62828")
        mark(pd.Timestamp(r.frac_t), r.frac_px, "fractal swing broken (MSS level)", "#1565c0", dy=-30)
        mark(pd.Timestamp(r.mss_t), b.close.iloc[-1], "MSS close", "#1565c0", "s", dy=20)
        ax.plot([X(pd.Timestamp(r.base_t)), n - 1], [r.base_px, r.ext_mss], color="#6a1b9a", lw=1.5)
        leg = abs(r.ext_mss - r.base_px)
        z = (r.ext_mss - 0.79 * leg, r.ext_mss - 0.62 * leg) if long_ else (r.ext_mss + 0.62 * leg, r.ext_mss + 0.79 * leg)
        band(pd.Timestamp(r.mss_t), z[0], z[1], "OTE zone 62-79 %", "#00897b")
        for g in fvgs(b, pd.Timestamp(r.base_t), pd.Timestamp(r.mss_t), long_):
            band(g[0], g[1], g[2], "FVG (leg)", "#ffb300", 0.35)
        entry = r.level_mss
        prop = f"proposed entry: {'buy' if long_ else 'sell'} limit at 70.5 % of the leg (trails the leg until filled)"
    hl(entry, "proposed entry", "black", ":"); hl(r.stop, "stop", DN)
    lo, hi = ax.get_ylim()
    gap, placed = 0.03 * (hi - lo), []
    for y, lab, col in sorted(labels, key=lambda z: -z[0]):
        yy = y
        while any(abs(yy - q) < gap for q in placed):
            yy -= gap
        placed.append(yy)
        ax.annotate(f" {lab} {y:,.2f}", (n + 3, y), xytext=(n + 3.5, yy), fontsize=8, color=col, va="center",
                    arrowprops=dict(arrowstyle="-", color=col, lw=0.5) if yy != y else None)
    ticks = [i for i, t in enumerate(b.index) if t.minute % 15 == 0]
    ax.set_xticks(ticks, [b.index[i].strftime("%H:%M") for i in ticks], fontsize=8)
    ax.set_xlim(-1, n + max(16, n // 4))
    ax.set_title(f"Setup {sid} · {fam} · proposed {'LONG' if long_ else 'SHORT'} · MNQ 1m, New York time · the chart ends "
                 f"at the decision bar\n{prop}", fontsize=10)
    ax.grid(alpha=0.2)
    fig.tight_layout()
    fig.savefig(path, dpi=100)
    plt.close(fig)


def make():
    rng = np.random.default_rng(opt("--seed", 7))
    one, P = pools()
    OUT.mkdir(parents=True, exist_ok=True)
    ids = rng.choice(np.arange(100000, 1000000), size=30, replace=False)
    key, k = [], 0
    for fam in ("AMD", "OB", "OTE"):
        t = P[fam]
        for taken in (True, False):
            for _, r in pick(t[t.taken == taken], 5, rng).iterrows():
                sid = int(ids[k]); k += 1
                chart(one, r, fam, sid, OUT / f"{sid}.png")
                key.append(dict(id=sid, family=fam, taken=taken, status=r.status, date=r.decision_t.date(),
                                side=r.side, pnl=round(float(r.pnl), 2), R=round(float(r.R), 4)))
    key = pd.DataFrame(key).sample(frac=1, random_state=int(rng.integers(1 << 31))).reset_index(drop=True)
    key.to_csv(OUT / "key.csv", index=False)
    print(f"{len(key)} charts written to {OUT}/ (ids only); key saved to {OUT}/key.csv (not printed). "
          f"Mix: {key.groupby(['family', 'taken']).size().to_dict()}; years {sorted({d.year for d in key.date})}")


def score():
    ans = pd.read_csv(sys.argv[2])
    key = pd.read_csv(OUT / "key.csv")
    x = key.merge(ans.assign(id=ans.id.astype(int)), on="id", how="inner")
    x["yes"] = x.answer.str.strip().str.lower().isin(("yes", "y", "1", "true"))
    print(f"answers matched: {len(x)} of {len(key)} setups")
    for lab, g in (("yes", x[x.yes]), ("no", x[~x.yes])):
        print(f"  {lab:<3}: {len(g):>2} setups, net {g.pnl.sum():+,.1f} $, R per setup {g.R.mean() if len(g) else float('nan'):+.3f}"
              f" (taken by the engine: {int(g.taken.sum())})")
    y = x.yes.to_numpy(); R = x.R.to_numpy()
    obs = R[y].mean() - R[~y].mean()
    rng = np.random.default_rng(1)
    sims = np.array([(lambda p: R[p].mean() - R[~p].mean())(rng.permutation(y)) for _ in range(20000)])
    print(f"  yes - no: {obs:+.3f} R per setup, shuffle p {(sims >= obs).mean():.4f} (one-sided, 20,000 permutations)")


if __name__ == "__main__":
    {"make": make, "score": score}[sys.argv[1]]()
