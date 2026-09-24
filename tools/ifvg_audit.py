#!/usr/bin/env python3
"""IFVG agreement audit on the Run I trade list (ICT_SMT_IFVG_strategy.pine, MNQ 5m, 2025-09 -> 2026-09).

    python3 tools/ifvg_audit.py make  [--n 20] [--seed 5] [--out data/studies/audit]
    python3 tools/ifvg_audit.py score [--out data/studies/audit]        (reads <out>/answers.csv)

make: 20 random Run I trades (data/tradingview/RunI_MNQ_2025-2026.csv). Each chart: the 30 MNQ 5m bars before the entry
    bar and the entry bar, nothing after; date in the title, outcome hidden. Drawn:
      * the indicator's IFVG — reconstructed from the entry: the 5m FVG against the trade (bullish gap for a short) that
        passes the Loose filter (gap >= 0.15 ATR(14), gap candle body >= 40 % of its range, range >= 0.40 ATR), formed
        <= 30 bars before its first close through the far edge, that close on the entry bar (Run I enters at the
        inversion close) or up to 10 bars earlier when the entry waited for the SMT confirmation; latest inversion
        wins, then the newest gap, and the chart says when there were several
      * every other Loose FVG in view (thin dashed, labelled with the time of its middle candle) so another gap can be
        named by its time
      * the eligible HTF zone — reconstructed from the tag's primary zone (15m / 1H / 4H / 1D FVG or NDOG): the most
        recent zone of that kind formed <= 7 days before, not closed through, overlapping the IFVG
      * the SMT reference — reconstructed from the tag (PDH / PDL: previous 18:00-17:00 session high / low; Swing: the
        latest 5m 5/5 pivot swept within the 40 bars before entry; Pivot: the chart market's last two 5m pivots)
      * entry (the inversion close) and the stop: exact from the export for SL / TP exits (SL fill -/+ 1 tick slippage;
        TP2 = entry close +/- 3 x risk), reconstructed (sweep extreme + 2 ticks) for time exits
    Files audit_01.png .. audit_20.png, key <out>/audit_key.csv (trade number, times; no outcomes shown in the charts),
    answer template <out>/answers.csv (id, same_gap yes/no, my_gap_time HH:MM of the gap's middle candle).
score: agreement rate; for each 'no', the named gap (same direction, in view) is traded with the same stop and Run I's
    rules: entry at its first close through the far edge within 30 bars of forming (not before the chart's first
    bar), target 3 R from that entry, 200-bar time stop, stop first on a shared bar, 1 tick slippage and $1 / side;
    compared with the indicator's trade from the export.
"""
import sys, pathlib, collections
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

TZ = "America/New_York"
TICK, PV = 0.25, 2.0
opt = lambda k, d: type(d)(sys.argv[sys.argv.index(k) + 1]) if k in sys.argv else d
OUT = pathlib.Path(opt("--out", "data/studies/audit"))
UP, DN = "#26a69a", "#ef5350"


def load_trades():
    r = pd.read_csv("data/tradingview/RunI_MNQ_2025-2026.csv", encoding="utf-8-sig")
    tr = collections.defaultdict(dict)
    for _, x in r.iterrows():
        t = pd.Timestamp(x["Date and time"]).tz_localize("America/Los_Angeles").tz_convert(TZ)
        d = tr[int(x["Trade number"])]
        if x["Type"].startswith("Entry"):
            parts = x["Signal"].split("|")
            tag = dict(p.split(":", 1) for p in parts if ":" in p)
            d.update(side=parts[0], entry_time=t, entry=float(x["Price USD"]), pnl=float(x["Net PnL USD"]),
                     zone=tag.get("P", "-"), smt=tag.get("smt", "-"), tag=x["Signal"])
        else:
            d.update(exit_time=t, exit=float(x["Price USD"]), reason=x["Signal"])
    return pd.DataFrame.from_dict(tr, orient="index").sort_index()


def atr_rma(b, n=14):
    pc = b.close.shift(1)
    tr = pd.concat([b.high - b.low, (b.high - pc).abs(), (b.low - pc).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False).mean()


def fvgs(b, atr, lo_i, hi_i):
    """Loose-filter FVGs completed at bars lo_i..hi_i: dicts(i, bull, bottom, top, mid_t)."""
    H, L, O, C = b.high.to_numpy(), b.low.to_numpy(), b.open.to_numpy(), b.close.to_numpy()
    out = []
    for i in range(max(lo_i, 2), hi_i + 1):
        for bull in (True, False):
            bot, top = (H[i - 2], L[i]) if bull else (H[i], L[i - 2])
            if top <= bot:
                continue
            m = i - 1
            rng = H[m] - L[m]
            a = atr.iloc[i]
            if rng <= 0 or (top - bot) < 0.15 * a or abs(C[m] - O[m]) < 0.40 * rng or rng < 0.40 * a:
                continue
            out.append(dict(i=i, bull=bull, bottom=bot, top=top, mid_t=b.index[m]))
    return out


def chosen_ifvg(b, atr, e, side):
    """Gaps against the trade, Loose, formed <= 30 bars before their inversion, first closed through on bar e or up to
    10 bars before it (the entry waits for the SMT confirmation); latest inversion first, then the newest gap."""
    C = b.close.to_numpy()
    cands = []
    for g in fvgs(b, atr, e - 40, e - 1):
        if g["bull"] != (side == "S"):
            continue
        edge = g["bottom"] if g["bull"] else g["top"]
        through = lambda k: (C[k] < edge) if g["bull"] else (C[k] > edge)
        k = next((k for k in range(g["i"] + 1, e + 1) if through(k)), None)
        if k is not None and k >= e - 10 and k - g["i"] <= 30:
            cands.append({**g, "inv": k})
    return sorted(cands, key=lambda g: (g["inv"], g["i"]))


def htf_bars(one, rule, upto):
    """HTF bars from 1m bars; 4H and daily buckets start at 18:00 New York wall time (bucketed on naive local time so
    daylight saving does not shift them)."""
    x = one[(one.index <= upto) & (one.index >= upto - pd.Timedelta(days=12))]
    kw = dict(label="left", closed="left")
    if rule in ("4h", "1D"):
        x = x.tz_localize(None) if x.index.tz is None else x.set_axis(x.index.tz_localize(None))
        kw["origin"] = pd.Timestamp("2019-01-01 18:00")
        rule = "24h" if rule == "1D" else rule
    b = x.resample(rule, **kw).agg({"open": "first", "high": "max", "low": "min", "close": "last"}).dropna()
    if b.index.tz is None:
        b.index = b.index.tz_localize(TZ, ambiguous="NaT", nonexistent="shift_forward")
    return b


def htf_zone(one, kind, ifvg, entry_t):
    lo, hi = ifvg["bottom"], ifvg["top"]
    start = entry_t - pd.Timedelta(days=7)
    if kind == "NDOG":
        x = one[(one.index >= start) & (one.index <= entry_t)]
        best = None
        for d in sorted(set(x.index.date)):
            o18 = x[(x.index.date == d) & (x.index.hour == 18) & (x.index.minute == 0)]
            prev = x[x.index < pd.Timestamp(f"{d} 17:00", tz=TZ)]
            if len(o18) and len(prev):
                a, c = o18.open.iloc[0], prev.close.iloc[-1]
                zb, zt = min(a, c), max(a, c)
                if zt > zb and zb <= hi and zt >= lo:
                    best = dict(bottom=zb, top=zt, t=o18.index[0], name="NDOG")
        return best
    rule = {"15m": "15min", "1H": "1h", "4H": "4h", "1D": "1D"}.get(kind)
    if rule is None:
        return None
    b = htf_bars(one, rule, entry_t)
    b = b[b.index >= start]
    H, L, C = b.high.to_numpy(), b.low.to_numpy(), b.close.to_numpy()
    best = None
    for i in range(2, len(b) - 1):                       # the last (forming) HTF bar cannot complete a gap
        for bull in (True, False):
            zb, zt = (H[i - 2], L[i]) if bull else (H[i], L[i - 2])
            if zt <= zb or zb > hi or zt < lo:
                continue
            after = C[i + 1:]
            if (after < zb).any() if bull else (after > zt).any():      # closed through the far edge
                continue
            best = dict(bottom=zb, top=zt, t=b.index[i - 2], name=f"{kind} FVG")
    return best


def pivots(b, left=5, right=5):
    H, L = b.high.to_numpy(), b.low.to_numpy()
    ph, pl = [], []
    for k in range(left, len(b) - right):
        if H[k] == H[k - left:k + right + 1].max() and (H[k] > H[k - left:k]).all():
            ph.append(k)
        if L[k] == L[k - left:k + right + 1].min() and (L[k] < L[k - left:k]).all():
            pl.append(k)
    return ph, pl


def smt_ref(one, b5, e, side, smt):
    """(level, sweep bar index or None, label) reconstructed from the tag."""
    H, L = b5.high.to_numpy(), b5.low.to_numpy()
    et = b5.index[e]
    if smt.startswith("PD"):
        d = et.date() if et.hour < 18 else (et + pd.Timedelta(days=1)).date()
        s_open = pd.Timestamp(f"{d} 18:00", tz=TZ) - pd.Timedelta(days=1)
        prev = one[(one.index < s_open) & (one.index >= s_open - pd.Timedelta(days=4))]
        prev = prev[prev.index >= prev[(prev.index.hour == 18) & (prev.index.minute == 0)].index[-1]]
        lvl = prev.high.max() if smt.startswith("PDH") else prev.low.min()
        k = next((k for k in range(max(e - 60, 0), e + 1) if b5.index[k] >= s_open and
                  ((H[k] > lvl) if smt.startswith("PDH") else (L[k] < lvl))), None)
        return lvl, k, smt.rstrip("+~")
    ph, pl = pivots(b5.iloc[:e + 1])
    if smt.startswith("Swing"):
        pool = ph if side == "S" else pl
        for k in range(e, max(e - 40, 0), -1):          # latest sweep of a confirmed, still-unswept pivot
            for p in reversed([p for p in pool if p + 5 < k]):
                lvl = H[p] if side == "S" else L[p]
                prior = range(p + 1, k)
                crossed = (H[k] > lvl) if side == "S" else (L[k] < lvl)
                if crossed and not any(((H[q] > lvl) if side == "S" else (L[q] < lvl)) for q in prior):
                    return lvl, k, "Swing (5m pivot)"
        return None, None, "Swing"
    pool = [p for p in (ph if side == "S" else pl) if p <= e]
    if len(pool) >= 2:
        p = pool[-1]
        return (H[p] if side == "S" else L[p]), p, smt.rstrip("+~") + " (last 5m pivot)"
    return None, None, smt


def stop_of(tr, b5, e, sweep_k):
    entry_close = tr.entry + (TICK if tr.side == "S" else -TICK)         # the fill carries 1 tick of slippage
    if tr.reason == "SL":
        return tr.exit - (TICK if tr.side == "S" else -TICK), "exact (SL fill - slippage)", entry_close
    if tr.reason == "TP":
        risk = abs(tr.exit - entry_close) / 3
        return (entry_close + risk if tr.side == "S" else entry_close - risk), "exact (from TP2 = 3 R)", entry_close
    k0 = sweep_k if sweep_k is not None else e - 10
    seg = b5.iloc[k0:e + 1]
    ext = seg.high.max() if tr.side == "S" else seg.low.min()
    return (ext + 2 * TICK if tr.side == "S" else ext - 2 * TICK), "reconstructed (sweep extreme + 2 ticks)", entry_close


def make():
    rng = np.random.default_rng(opt("--seed", 5))
    trades = load_trades()
    b5 = pd.read_parquet("data/bars/MNQ_5m.parquet")
    one = pd.read_parquet("data/bars/MNQ_1m.parquet")
    atr = atr_rma(b5)
    OUT.mkdir(parents=True, exist_ok=True)
    pick = trades.loc[np.sort(rng.choice(trades.index, size=opt("--n", 20), replace=False))]
    pick = pick.sort_values("entry_time")
    key = []
    for n, (tno, tr) in enumerate(pick.iterrows(), 1):
        e = int(b5.index.get_indexer([tr.entry_time])[0])
        if e < 0:
            print(f"trade {tno}: entry bar not in the data, skipped"); continue
        cands = chosen_ifvg(b5, atr, e, tr.side)
        g = cands[-1] if cands else None
        lvl, sk, sname = smt_ref(one, b5, e, tr.side, tr.smt)
        stop, stop_src, entry_close = stop_of(tr, b5, e, sk)
        zone = htf_zone(one, tr.zone, g, tr.entry_time) if g else None
        s0 = max(e - 30, 0)
        v = b5.iloc[s0:e + 1]
        fig, ax = plt.subplots(figsize=(15, 8))
        for i, (o, h, l, c) in enumerate(zip(v.open, v.high, v.low, v.close)):
            col = UP if c >= o else DN
            ax.plot([i, i], [l, h], color=col, lw=0.9)
            ax.add_patch(Rectangle((i - 0.35, min(o, c)), 0.7, max(abs(c - o), 0.05), color=col, lw=0))
        nv = len(v)
        X = lambda k: k - s0
        for f in fvgs(b5, atr, s0 + 2, e):
            if g is not None and f["i"] == g["i"] and f["bull"] == g["bull"]:
                continue
            ax.add_patch(Rectangle((X(f["i"] - 2) - 0.5, f["bottom"]), nv - X(f["i"] - 2) + 1, f["top"] - f["bottom"],
                                   fill=False, ec="#9e9e9e", ls="--", lw=0.8))
            ax.text(X(f["i"] - 1), f["top"] if f["bull"] else f["bottom"], f" {f['mid_t']:%H:%M} {'bull' if f['bull'] else 'bear'} gap",
                    fontsize=7, color="#616161", va="bottom" if f["bull"] else "top")
        if g is not None:
            ax.add_patch(Rectangle((X(g["i"] - 2) - 0.5, g["bottom"]), nv - X(g["i"] - 2) + 1, g["top"] - g["bottom"],
                                   color="#ffb300", alpha=0.45, lw=1.5, ec="#e65100"))
            ax.text(X(g["i"] - 2), g["top"], f" indicator's IFVG: {g['mid_t']:%H:%M} {'bull' if g['bull'] else 'bear'} gap"
                    + (f", inverted {b5.index[g['inv']]:%H:%M}" if g["inv"] != e else "")
                    + (f" (newest of {len(cands)} candidates)" if len(cands) > 1 else ""),
                    fontsize=8, color="#e65100", va="bottom", weight="bold")
        if zone:
            x0 = max(X(int(np.searchsorted(b5.index, zone["t"]))), -1)
            ax.add_patch(Rectangle((x0 - 0.5, zone["bottom"]), nv - x0 + 1, zone["top"] - zone["bottom"],
                                   color="#7e57c2", alpha=0.12, lw=0))
            ax.text(max(x0, 0), max(zone["bottom"], min(v.low.min(), stop, entry_close)), f" eligible HTF zone (reconstructed): {zone['name']} from {zone['t']:%m-%d %H:%M}",
                    fontsize=8, color="#5e35b1", va="top")
        if lvl is not None:
            ax.axhline(lvl, color="#1565c0", ls="-.", lw=1)
            ax.text(0, lvl, f" SMT reference (reconstructed, tag {tr.smt}): {sname} {lvl:,.2f}", fontsize=8, color="#1565c0", va="bottom")
            if sk is not None and sk >= s0:
                ax.plot(X(sk), b5.high.iloc[sk] if tr.side == "S" else b5.low.iloc[sk], "*", color="#1565c0", ms=12)
        ax.axhline(stop, color=DN, lw=1.3)
        ax.text(nv + 0.5, stop, f" stop {stop:,.2f} ({stop_src})", fontsize=8, color=DN, va="center")
        ax.plot(X(e), entry_close, ">" if tr.side == "L" else "<", color="black", ms=11, zorder=6)
        ax.text(nv + 0.5, entry_close, f" entry {'LONG' if tr.side == 'L' else 'SHORT'} at the inversion close {entry_close:,.2f}",
                fontsize=8, va="center")
        ys = [v.low.min(), v.high.max(), stop, entry_close] + ([g["bottom"], g["top"]] if g else []) + \
             ([lvl] if lvl is not None else [])
        pad = 0.06 * (max(ys) - min(ys))
        ax.set_ylim(min(ys) - pad, max(ys) + pad)
        if zone:
            ax.text(nv + 0.5, min(max(zone["top"], min(ys)), max(ys)), f" HTF zone {zone['bottom']:,.2f} – {zone['top']:,.2f}",
                    fontsize=8, color="#5e35b1", va="top")
        ticks = list(range(0, nv, 3))
        ax.set_xticks(ticks, [v.index[i].strftime("%H:%M") for i in ticks], fontsize=8)
        ax.set_xlim(-1, nv + 14)
        ax.grid(alpha=0.2)
        ax.set_title(f"audit_{n:02d} · {tr.entry_time:%Y-%m-%d %a} · Run I {'LONG' if tr.side == 'L' else 'SHORT'} · entry bar "
                     f"{tr.entry_time:%H:%M} · 30 bars of context, nothing after entry · outcome hidden\n"
                     f"tag {tr.tag}", fontsize=10)
        fig.tight_layout()
        fig.savefig(OUT / f"audit_{n:02d}.png", dpi=100)
        plt.close(fig)
        key.append(dict(id=f"audit_{n:02d}", trade=tno, entry_time=tr.entry_time, side=tr.side, tag=tr.tag,
                        ifvg_mid_t=g["mid_t"] if g else None, ifvg_inverted=b5.index[g["inv"]] if g else None, ifvg_candidates=len(cands), stop=stop, stop_source=stop_src,
                        entry_close=entry_close, zone=zone["name"] if zone else None, smt_ref=lvl))
    k = pd.DataFrame(key)
    k.to_csv(OUT / "audit_key.csv", index=False)
    if not (OUT / "answers.csv").exists():
        pd.DataFrame(dict(id=k.id, same_gap="", my_gap_time="")).to_csv(OUT / "answers.csv", index=False)
    print(f"{len(k)} charts in {OUT}/; IFVG found for {int(k.ifvg_mid_t.notna().sum())}, "
          f"more than one candidate on {int((k.ifvg_candidates > 1).sum())}; stops exact {int(k.stop_source.str.startswith('exact').sum())}; "
          f"HTF zone found {int(k.zone.notna().sum())}; SMT reference found {int(k.smt_ref.notna().sum())}")


def score():
    trades = load_trades()
    b5 = pd.read_parquet("data/bars/MNQ_5m.parquet")
    atr = atr_rma(b5)
    key = pd.read_csv(OUT / "audit_key.csv")
    ans = pd.read_csv(OUT / "answers.csv", dtype=str).fillna("")
    x = key.merge(ans, on="id")
    x["agree"] = x.same_gap.str.strip().str.lower().isin(("yes", "y"))
    print(f"answered {int((x.same_gap.str.strip() != '').sum())} of {len(x)}; same gap as the indicator: "
          f"{int(x.agree.sum())} ({100 * x.agree.mean():.0f} %)")
    H, L, C = b5.high.to_numpy(), b5.low.to_numpy(), b5.close.to_numpy()
    rows = []
    for _, r in x[~x.agree & (x.my_gap_time.str.strip() != "")].iterrows():
        tr = trades.loc[int(r.trade)]
        e = int(b5.index.get_indexer([tr.entry_time])[0])
        s0 = max(e - 30, 0)
        hh, mm = map(int, r.my_gap_time.strip().split(":"))
        g = [f for f in fvgs(b5, atr, s0 + 2, e) if f["mid_t"].hour == hh and f["mid_t"].minute == mm
             and f["bull"] == (tr.side == "S")]
        res = dict(id=r.id, trade=int(r.trade), indicator_pnl=tr.pnl, my_gap=r.my_gap_time)
        if not g:
            rows.append({**res, "my_pnl": np.nan, "note": "no gap of the trade's direction at that time in view"}); continue
        g = g[0]
        edge = g["bottom"] if g["bull"] else g["top"]
        sgn = 1 if tr.side == "L" else -1
        k = next((k for k in range(g["i"] + 1, min(g["i"] + 31, len(C))) if sgn * (C[k] - edge) > 0), None)
        if k is None:
            rows.append({**res, "my_pnl": 0.0, "note": "gap never inverted within 30 bars: no trade"}); continue
        entry = C[k] + sgn * TICK
        risk = sgn * (C[k] - r.stop)
        if risk <= 0:
            rows.append({**res, "my_pnl": 0.0, "note": "stop on the wrong side of this entry: no trade"}); continue
        tp = C[k] + sgn * 3 * risk
        out = None
        for q in range(k + 1, min(k + 201, len(C))):
            if (L[q] <= r.stop) if sgn > 0 else (H[q] >= r.stop):
                out = (r.stop - sgn * TICK, "SL"); break
            if (H[q] >= tp) if sgn > 0 else (L[q] <= tp):
                out = (tp, "TP"); break
        if out is None:
            out = (C[min(k + 200, len(C) - 1)] - sgn * TICK, "time")
        pnl = sgn * (out[0] - entry) * PV - 2
        rows.append({**res, "my_pnl": round(pnl, 2), "note": f"entry {b5.index[k]:%H:%M}, {out[1]}"})
    d = pd.DataFrame(rows)
    if len(d):
        print(d.to_string(index=False))
        print(f"disagreements simulated: {len(d)}; indicator net {d.indicator_pnl.sum():+,.1f} vs your gap {d.my_pnl.sum():+,.1f}")


if __name__ == "__main__":
    {"make": make, "score": score}[sys.argv[1]]()
