#!/usr/bin/env python3
"""Setup charts: 1-minute bars 09:30 -> exit for randomly chosen OB1-1m, AMD1-1m and OTE1-1m trades, with the setup
geometry each engine recorded (overnight / accumulation range, fractal swing used, sweep or displacement leg, FVGs in
the leg, order block or OTE zone, entry, stop, target and exit).

    python3 tools/setup_charts.py [--n 4] [--seed 2026] [--out data/studies/setup_charts]

Trades are re-run from the engines' 1m defaults (tools/ob_engine.py, amd_engine.py, ote_engine.py) and chosen with
numpy's default_rng(seed). FVGs are recomputed from the bars inside the recorded leg: OB and OTE draw the gaps in the
trade's direction (the displacement), AMD the gaps against it (the ones the trigger inverts).
"""
import sys, pathlib
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
sys.path.insert(0, str(pathlib.Path(__file__).parent))
import ob_engine, amd_engine, ote_engine

TZ = "America/New_York"
opt = lambda k, d: type(d)(sys.argv[sys.argv.index(k) + 1]) if k in sys.argv else d
N, SEED, OUT = opt("--n", 4), opt("--seed", 2026), pathlib.Path(opt("--out", "data/studies/setup_charts"))
UP, DN = "#26a69a", "#ef5350"


def overnight(one, day):
    d = pd.Timestamp(day, tz=TZ)
    w = one[(one.index >= d - pd.Timedelta(days=4)) & (one.index < d + pd.Timedelta(hours=9, minutes=30))]
    start = w[(w.index.hour == 18) & (w.index.minute == 0)].index[-1]
    w = w[w.index >= start]
    return w.high.max(), w.low.min()


def fvgs(b, t0, t1, bullish):
    """Gaps completed on bars in [t0, t1]: (start time, end time, low edge, high edge)."""
    x = b[(b.index >= t0 - pd.Timedelta(minutes=2)) & (b.index <= t1)]
    out = []
    for i in range(2, len(x)):
        if bullish and x.high.iloc[i - 2] < x.low.iloc[i] and x.index[i] >= t0:
            out.append((x.index[i - 2], x.index[i], x.high.iloc[i - 2], x.low.iloc[i]))
        if not bullish and x.low.iloc[i - 2] > x.high.iloc[i] and x.index[i] >= t0:
            out.append((x.index[i - 2], x.index[i], x.high.iloc[i], x.low.iloc[i - 2]))
    return out


def chart(one, r, kind, path):
    d = r.entry_time.date()
    t_end = r.exit_time + pd.Timedelta(minutes=5)
    b = one[(one.index >= pd.Timestamp(f"{d} 09:30", tz=TZ)) & (one.index <= t_end)]
    xi = {t: i for i, t in enumerate(b.index)}
    X = lambda t: xi.get(t, np.searchsorted(b.index, t))
    onH, onL = overnight(one, d)
    fig, ax = plt.subplots(figsize=(16, 8))
    for i, (o, h, l, c) in enumerate(zip(b.open, b.high, b.low, b.close)):
        col = UP if c >= o else DN
        ax.plot([i, i], [l, h], color=col, lw=0.8)
        ax.add_patch(Rectangle((i - 0.35, min(o, c)), 0.7, max(abs(c - o), 0.05), color=col, lw=0))
    n = len(b)

    labels = []                                          # right-hand line labels, placed at the end without overlap

    def hline(y, label, color, ls="-", lw=1.2, x0=0):
        ax.plot([x0, n - 1], [y, y], color=color, ls=ls, lw=lw)
        labels.append((y, f" {label} {y:,.2f}", color))

    def mark(t, y, label, color, marker="o", dy=0):
        ax.plot(X(t), y, marker=marker, color=color, ms=9, mec="black", mew=0.6, zorder=5)
        ax.annotate(label, (X(t), y), xytext=(8, 10 + dy), textcoords="offset points", fontsize=8, color=color,
                    arrowprops=dict(arrowstyle="-", color=color, lw=0.6))

    def zone(t0, lo, hi, label, color, alpha=0.18):
        ax.add_patch(Rectangle((X(t0) - 0.5, lo), n - X(t0), hi - lo, color=color, alpha=alpha, lw=0))
        ax.text(X(t0), hi, f" {label}", fontsize=8, color=color, va="bottom")

    long_ = r.side == "L"
    hline(onH, "overnight high", "#7e57c2", "--"); hline(onL, "overnight low", "#7e57c2", "--")
    if kind == "OB":
        mark(r.frac_t, r.frac_px, "fractal swing broken (BOS level)", "#1565c0")
        ax.plot([X(r.frac_t), X(r.bos_t)], [r.frac_px, r.frac_px], color="#1565c0", lw=1, ls=":")
        mark(r.bos_t, b.close.iloc[X(r.bos_t)], "BOS close (displacement)", "#1565c0", "s", dy=-30)
        for g in fvgs(b, r.ob_t, r.bos_t, long_):
            ax.add_patch(Rectangle((X(g[0]) - 0.5, g[2]), n - X(g[0]), g[3] - g[2], color="#ffb300", alpha=0.35, lw=0))
            ax.text(X(g[1]), g[3], " FVG (leg)", fontsize=8, color="#ef6c00", va="bottom")
        zone(r.ob_t, r.ob_lo, r.ob_hi, "order block", "#546e7a")
        hline(r.lim, "limit (OB edge)", "#37474f", ":")
        title = f"OB1-1m · order block pullback"
    elif kind == "AMD":
        zone(pd.Timestamp(f"{d} 09:30", tz=TZ), r.acc_lo, r.acc_hi, "accumulation (overnight) range", "#7e57c2", 0.05)
        w = b[(b.index >= r.sweep_t) & (b.index <= r.trig_t)]
        mark((w.low.idxmin() if long_ else w.high.idxmax()), r.ext, "sweep extreme (manipulation)", "#c62828")
        mark(r.sweep_t, b.high.iloc[X(r.sweep_t)] if not long_ else b.low.iloc[X(r.sweep_t)], "sweep bar", "#c62828", "v" if long_ else "^", dy=-20)
        mark(r.leg_t, r.leg_px, "sweep-leg start (fractal / MSS level)", "#1565c0", dy=-30)
        ax.plot([X(r.leg_t), X(r.trig_t)], [r.leg_px, r.leg_px], color="#1565c0", lw=1, ls=":")
        mark(r.conf_t, b.close.iloc[X(r.conf_t)], "close back inside (confirmation)", "#6a1b9a", "s", dy=20)
        for g in fvgs(b, r.leg_t, r.conf_t, not long_):
            ax.add_patch(Rectangle((X(g[0]) - 0.5, g[2]), n - X(g[0]), g[3] - g[2], color="#ffb300", alpha=0.35, lw=0))
            ax.text(X(g[1]), g[3], " FVG in the sweep leg", fontsize=8, color="#ef6c00", va="bottom")
        mark(r.trig_t, b.close.iloc[X(r.trig_t)], f"trigger: {r.trigger}", "#2e7d32", "D", dy=-45)
        title = "AMD1-1m · accumulation → manipulation → distribution"
    else:
        if pd.notna(r.sweep_t):
            mark(r.sweep_t, r.base_px, "sweep of the overnight extreme", "#c62828")
        mark(r.frac_t, r.frac_px, "fractal swing broken (MSS level)", "#1565c0", dy=-30)
        ax.plot([X(r.frac_t), X(r.mss_t)], [r.frac_px, r.frac_px], color="#1565c0", lw=1, ls=":")
        mark(r.mss_t, b.close.iloc[X(r.mss_t)], "MSS close", "#1565c0", "s", dy=20)
        ax.plot([X(r.base_t), X(r.entry_time)], [r.base_px, r.ext_px], color="#6a1b9a", lw=1.5)
        ax.text(X(r.base_t), r.base_px, " leg 0 %", fontsize=8, color="#6a1b9a", va="top")
        leg = abs(r.ext_px - r.base_px)
        z1, z2 = (r.ext_px - 0.79 * leg, r.ext_px - 0.62 * leg) if long_ else (r.ext_px + 0.62 * leg, r.ext_px + 0.79 * leg)
        zone(r.mss_t, z1, z2, "OTE zone 62–79 %", "#00897b", 0.2)
        hline(r.level, f"limit {r.f:.3f}", "#004d40", ":")
        for g in fvgs(b, r.base_t, r.mss_t, long_):
            ax.add_patch(Rectangle((X(g[0]) - 0.5, g[2]), n - X(g[0]), g[3] - g[2], color="#ffb300", alpha=0.35, lw=0))
            ax.text(X(g[1]), g[3], " FVG (leg)", fontsize=8, color="#ef6c00", va="bottom")
        title = "OTE1-1m · optimal trade entry"
    hline(r.stop, "stop", DN, "-", 1.4); hline(r.tp, "target", UP, "-", 1.4)
    mark(r.entry_time, r.entry, f"entry {'long' if long_ else 'short'}", "black", "^" if long_ else "v", dy=25)
    mark(r.exit_time, r.exit, f"exit ({r.reason})", "#e65100", "X", dy=-25)
    lo, hi = ax.get_ylim()
    gap, placed = 0.028 * (hi - lo), []
    for y, text, color in sorted(labels, key=lambda z: -z[0]):
        yy = y
        while any(abs(yy - q) < gap for q in placed):
            yy -= gap
        placed.append(yy)
        ax.annotate(text, (n - 1, y), xytext=(n - 0.5, yy), fontsize=8, color=color, va="center",
                    arrowprops=dict(arrowstyle="-", color=color, lw=0.5) if yy != y else None)
    ticks = [i for i, t in enumerate(b.index) if t.minute % 15 == 0]
    ax.set_xticks(ticks, [b.index[i].strftime("%H:%M") for i in ticks], fontsize=8)
    ax.set_xlim(-1, n + max(14, n // 6))
    ax.set_title(f"{title} — {d} {'LONG' if long_ else 'SHORT'} · {r.reason} · {r.pnl:+,.1f} $ · {r.R:+.2f} R "
                 f"(risk {r.risk:.2f} pts) · MNQ 1m, New York time", fontsize=11)
    ax.grid(alpha=0.2)
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)


if __name__ == "__main__":
    one = pd.read_parquet("data/bars/MNQ_1m.parquet")
    OUT.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(SEED)
    for kind, mod in (("OB", ob_engine), ("AMD", amd_engine), ("OTE", ote_engine)):
        t = mod.run(one, tf=1)[0]
        pick = t.iloc[np.sort(rng.choice(len(t), size=N, replace=False))]
        for _, r in pick.iterrows():
            path = OUT / f"{kind}1-1m_{r.entry_time:%Y-%m-%d}_{'long' if r.side == 'L' else 'short'}.png"
            chart(one, r, kind, path)
            print(f"{path}  {r.reason} {r.pnl:+.1f} $ {r.R:+.2f} R")
