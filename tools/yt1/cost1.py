#!/usr/bin/env python3
"""COST1 - YT11_SPEC.md, Part 1: what a round trip costs next to the moves (description, no verdict).

    python3 tools/yt1/cost1.py --phase is      bars to 2022-12-31 only (asserted)  -> data/studies/yt1/is/COST1.csv
    python3 tools/yt1/cost1.py --phase full    every bar                           -> data/studies/yt1/full/COST1.csv

One row per market (MNQ, MES) and calendar year, and one row 'all' per market over every session of the bars read.
Regular session = the 09:30 bar .. the flat bar of every cash day of the harness's day table (ctx.days, built from
the MNQ bars; roll days and days without an ATR included: nothing is traded here). MES bars come from
ctx.extra("MES") and are placed in those same sessions by their timestamps.

    sessions       sessions of the year in which the market has a regular-session bar
    bars           regular-session 1-minute bars
    median_hl      median of high - low of those bars, points
    abs_h<h>       mean of |close(t + h) - close(t)|, points, over every regular-session bar t for which the bar
                   stamped h minutes later exists and is in the same session (h = 1, 2, 3, 5, 10, 15, 30)
    x_cost_h<h>    abs_h / the cost in points
    hit_h<h>       0.5 + cost in points / (2 x abs_h): the hit rate a bet that wins or loses abs_h needs to break even
    usd_year_<n>   n round trips a day x the cost x the sessions of that year ('all': x 252 sessions)
Cost of a round trip = 2 ticks + $2: MNQ 2 x $0.50 + $2 = $3.00 = 1.5 points; MES 2 x $1.25 + $2 = $4.50 = 0.9 points.
"""
import argparse, pathlib, sys
import numpy as np
import pandas as pd
sys.path.insert(0, str(pathlib.Path(__file__).parent))
import core

HS = (1, 2, 3, 5, 10, 15, 30)
TRIPS = (10, 50, 100, 200)
MARKETS = {"MNQ": {"tick_usd": 0.50, "pv": 2.0}, "MES": {"tick_usd": 1.25, "pv": 5.0}}
YEAR_SESSIONS = 252                       # the 'all' row's year


def _minutes(index):
    return index.tz_convert("UTC").tz_localize(None).to_numpy().astype("datetime64[m]").astype(np.int64)


def cost(sym):
    m = MARKETS[sym]
    usd = 2 * m["tick_usd"] + 2 * core.COMM
    return usd, usd / m["pv"]


def market_bars(ctx, sym):
    """The 1-minute bars of a market as a frame (MNQ: the context's own; anything else: ctx.extra)."""
    return ctx.a if sym == "MNQ" else ctx.extra(sym)


def measure(ctx, sym):
    D = ctx.days
    t_all = _minutes(ctx.ts)
    o_min, e_min = t_all[D.i_open.to_numpy()], t_all[D.i_end.to_numpy()]
    x = market_bars(ctx, sym)
    assert x.index.is_monotonic_increasing and x.index.is_unique
    t = _minutes(x.index)
    n = len(t)
    H, L, C = (x[k].to_numpy(float) for k in ("high", "low", "close"))
    iid = x["instrument_id"].to_numpy()
    q = np.searchsorted(o_min, t, "right") - 1                       # the session a bar would belong to
    qq = np.clip(q, 0, max(len(D) - 1, 0))
    ins = (q >= 0) & (t <= e_min[qq]) if len(D) else np.zeros(n, bool)
    year = D.index.year.to_numpy()[qq]
    usd, pts = cost(sym)
    move = {}
    for h in HS:
        p = np.minimum(np.searchsorted(t, t + h), max(n - 1, 0))
        ok = ins & (t[p] == t + h) & ins[p] & (qq[p] == qq) & (iid[p] == iid)
        move[h] = (ok, np.abs(C[p] - C))
    rows = []
    for label in sorted(set(year[ins].tolist())) + ["all"]:
        m = ins if label == "all" else ins & (year == label)
        ns = len(np.unique(qq[m]))
        r = {"market": sym, "year": label, "sessions": ns, "bars": int(m.sum()), "cost_usd": usd, "cost_pts": pts,
             "median_hl": float(np.median((H - L)[m])) if m.any() else np.nan}
        for h in HS:
            ok, a = move[h]
            k = ok & m
            r[f"abs_h{h}"] = float(a[k].mean()) if k.any() else np.nan
        for h in HS:
            r[f"x_cost_h{h}"] = r[f"abs_h{h}"] / pts
        for h in HS:
            r[f"hit_h{h}"] = 0.5 + pts / (2 * r[f"abs_h{h}"]) if r[f"abs_h{h}"] > 0 else np.nan
        for n_ in TRIPS:
            r[f"usd_year_{n_}"] = n_ * usd * (YEAR_SESSIONS if label == "all" else ns)
        rows.append(r)
    return pd.DataFrame(rows)


def show(tb):
    for sym, t in tb.groupby("market", sort=False):
        usd, pts = cost(sym)
        t = t.set_index("year")
        print(f"\n{sym}: a round trip costs ${usd:.2f} = {pts} points")
        a = t[["sessions", "median_hl"] + [f"abs_h{h}" for h in HS]]
        a.columns = ["sessions", "median H-L"] + [f"|move| {h}m" for h in HS]
        print(a.to_string(float_format=lambda v: f"{v:.2f}"))
        b = t[[f"x_cost_h{h}" for h in HS]]
        b.columns = [f"{h}m" for h in HS]
        print(f"  mean |move| / the cost ({pts} points)")
        print(b.to_string(float_format=lambda v: f"{v:.2f}"))
        c = t[[f"hit_h{h}" for h in HS]]
        c.columns = [f"{h}m" for h in HS]
        print("  hit rate a coin-flip-sized bet needs to break even")
        print(c.to_string(float_format=lambda v: f"{v:.3f}"))
        e = t[[f"usd_year_{n}" for n in TRIPS]]
        e.columns = [f"{n} a day" for n in TRIPS]
        print(f"  dollars a year of round trips (sessions of that year x ${usd:.2f}; 'all' = {YEAR_SESSIONS} sessions)")
        print(e.to_string(float_format=lambda v: f"{v:,.0f}"))


def main():
    import run
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", choices=["is", "full"], required=True)
    ap.add_argument("--out", help="code test only: write under this directory instead of data/studies/yt1")
    a = ap.parse_args()
    pd.set_option("display.width", 250)
    ctx = core.Ctx(run.bars(a.phase))
    if a.phase == "is":
        assert ctx.ts[-1] < core.IS_END, "in-sample bars reach into the out-of-sample window"
    print(f"COST1   phase {a.phase}   bars {ctx.ts[0]} -> {ctx.ts[-1]}   sessions {len(ctx.days)}")
    parts, missing = [], []
    for sym in MARKETS:
        try:
            market_bars(ctx, sym)
        except FileNotFoundError:
            missing.append(sym)
            continue
        if a.phase == "is":
            assert market_bars(ctx, sym).index.max() < core.IS_END
        parts.append(measure(ctx, sym))
    tb = pd.concat(parts, ignore_index=True)
    d = (pathlib.Path(a.out) if a.out else core.OUT) / a.phase
    d.mkdir(parents=True, exist_ok=True)
    tb.to_csv(d / "COST1.csv", index=False)
    show(tb)
    for sym in missing:
        print(f"\n{sym}: no bars through ctx.extra: not measured")
    print(f"\nwrote {d / 'COST1.csv'}")


if __name__ == "__main__":
    main()
