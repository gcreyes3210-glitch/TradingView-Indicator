#!/usr/bin/env python3
"""L1 - the LEV1 fade at one level code x side, or at one pair of level codes, as a standard harness module
(YT9_SPEC.md). Built on lev1_levels.levels / lev1_events.events / lev1_events.orders_of, so it trades exactly the
events the tables count: the first tap of the level by 15:00 on study days, for the fresh events in which the level
is a lead of its cluster (a pair: the clusters holding both codes, each once).

A variant: sel   'code:R' / 'code:S' (a placebo is 'code~:R'), or 'a+b' for a pair (both sides)
           stop  p20 (20 points) / a04 / a08 (0.04 / 0.08 x ATR, on the tick grid, at least 2 ticks)
           k     target in multiples of the stop distance (fade)       trade  'fade' (limit) or 'break' (stop order, 3R)
           fresh 'fresh' (the tables' ranking set) / 'any' (used levels allowed)

Orders. A static or expected-move level: ONE resting order per event, i = the bar before the first watched bar, so
it rests during the first watched bar (09:30 for most levels, 09:45 for the opening range, the block's first bar
for an expected-move block that starts at 10:00 / 12:00 / 14:00) and expires on the last watched bar (15:00, the
end of the block, or the flat bar on a short day). A VWAP level: a one-bar order at the close of every bar until the
first fill, at the band value of the last completed 5-minute bar.

The one number read after the order's bar i: the open of bar i + 1, the first watched bar ("the price at the start
of the watch", which sets the side, the near-skip and the cluster; it also DEFINES r100 and the centre of an
expected-move block that starts at 10:00 or later). orders(ctx, ..., at_open=False), the default and what
`run.py L1 --check` and core.causal_check call, replaces that open by the last close before it, so that everything
the test compares is built from bars up to i; trades() uses at_open=True. `s_L1.py --check` runs, per variant:
    A  core.causal_check on the at_open=False orders        (levels, ATR, freshness, clusters, placebos, VWAP values)
    B  the same test on the real (at_open=True) orders with that one open kept true and everything else after bar i
       mirrored (as s_G9.check_true_open)
    --plain: also core.causal_check on the real orders, which mirrors that open too (it can only fail through it)

VARIANTS  base / nb1 / nb2      pick 1 of data/studies/yt1/LEV1_selected.json: a04 x 3R, a08 x 3R, a04 x 2R
          p2, p2_nb1, p2_nb2 ... the other frozen picks (p6-p8 are the pairs)
          chk1 ... chk19         fixed before any result was seen: every level group, a placebo, a used-allowed
                                 variant, the break trade, the 20-point stop, a pair

    python3 tools/yt1/s_L1.py --check all [--plain]      the look-ahead tests
    python3 tools/yt1/s_L1.py --recon                    run.py's saved trades against the tables, variant by variant
"""
import argparse, json, pathlib, sys
import numpy as np
import pandas as pd
sys.path.insert(0, str(pathlib.Path(__file__).parent))
import core
import lev1_levels as LL
import lev1_events as LE

ID = "L1"
NAME = "LEV1 first tap after the open: the fade at one level (YT9)"
PLACEHOLDER = "pdh:R"                                   # only until LEV1_selected.json exists
SEL_PATH = core.OUT / "LEV1_selected.json"
CHECKS = (                                              # fixed up front (before any table was built)
    dict(sel="pdh:R"),                                  # 1  previous day
    dict(sel="pwl:S"),                                  # 2  previous week
    dict(sel="onh:R"),                                  # 3  overnight
    dict(sel="asl:S"),                                  # 4  Asia
    dict(sel="ldh:R"),                                  # 5  London
    dict(sel="prl:S"),                                  # 6  pre-market
    dict(sel="o0830:R"),                                # 7  opens
    dict(sel="poc:S"),                                  # 8  profile
    dict(sel="r100:R"),                                 # 9  round numbers (defined by the 09:30 open)
    dict(sel="orl:S"),                                  # 10 opening range (watched from 09:45)
    dict(sel="em1u:R"),                                 # 11 expected move (four blocks a day)
    dict(sel="vw1d:S"),                                 # 12 VWAP band (moving, bar-by-bar orders)
    dict(sel="pdh~:R"),                                 # 13 a placebo
    dict(sel="ash:R", fresh="any"),                     # 14 used levels allowed
    dict(sel="onl:S", trade="break"),                   # 15 the break trade (a04, 3R)
    dict(sel="ash+onh"),                                # 16 a pair
    dict(sel="pdl:S", stop="p20"),                      # 17 the 20-point stop, 3R, as asked
    dict(sel="vw:R", stop="p20", k=1),                  # 18 the VWAP itself, 1R
    dict(sel="em2d:S", stop="a08"),                     # 19 the 2-sigma band, wide stop
)


def _picks():
    if SEL_PATH.exists():
        got = [(int(r["pick"]), r["sel"]) for r in json.loads(SEL_PATH.read_text())["picks"]]
        if got:
            return got
    return [(1, PLACEHOLDER)]


def _full(p):
    return dict(dict(stop="a04", k=3, trade="fade", fresh="fresh"), **p)


def _variants():
    v = {}
    for q, (n, sel) in enumerate(_picks()):
        pre = "" if q == 0 else f"p{n}_"
        v["base" if q == 0 else f"p{n}"] = _full(dict(sel=sel))
        v[pre + "nb1"] = _full(dict(sel=sel, stop="a08"))
        v[pre + "nb2"] = _full(dict(sel=sel, k=2))
    for n, p in enumerate(CHECKS, 1):
        v[f"chk{n}"] = _full(p)
    return v


VARIANTS = _variants()


def variant_name(stop="a04", k=3, trade="fade", **_):
    return f"brk_{stop}" if trade == "break" else f"{stop}x{int(k)}"


def rows_of(ev, sel, fresh="fresh"):
    """The event rows of a selection (tapped or not): what the tables call the cell's / the pair's events."""
    e = ev[ev.is_event & (ev.fresh if fresh == "fresh" else True)]
    if "+" in sel:
        a, b = sel.split("+")
        c = e[(e.kind == "static") & ~e.is_placebo & e.first_lead & (e.cl_n >= 2)]
        return c[[a in s and b in s for s in (x.split("+") for x in c.cl_codes)]]
    code, side = sel.split(":")
    return e[(e.code == code) & (e.side == side)]


def orders(ctx, sel=PLACEHOLDER, stop="a04", k=3, trade="fade", fresh="fresh", at_open=False):
    """Every order of the selection, each built from bars up to its own bar `i`; at_open=True (trades) reads in
    addition the open of the first watched bar, see the module docstring."""
    assert trade in ("fade", "break") and fresh in ("fresh", "any") and stop in LE.STOPS
    assert trade == "fade" or int(k) == 3, "the break trade has a 3R target"
    v = variant_name(stop, k, trade)
    ev = LE.events(ctx, at_open=at_open, score=False, only=LE.need(sel))
    out = []
    for r in rows_of(ev, sel, fresh).itertuples(index=False):
        for o in LE.orders_of(ctx, r, v):
            o["tag"] = f"{r.lid}|{r.side}|{r.date:%Y-%m-%d}|{r.cl_codes}"
            out.append(o)
    return out


def trades(ctx, **p):
    return core.run_orders(ctx, orders(ctx, at_open=True, **p), one_at_a_time=False, skip_roll=2)


# ------------------------------------------------------------------ look-ahead tests
def check_true_open(make, a, n_samples=16, seed=5, back_days=150, fwd_days=7):
    """core.causal_check (same sampling, same comparison of the order keys) with one difference: in the mirrored
    future the OPEN of the first bar after the sampled order's bar keeps its true value; that bar's high, low and
    close and every later bar are mirrored (as s_G9.check_true_open). Returns (ok, orders, samples)."""
    full = core.Ctx(a)
    od = make(full)
    rng = np.random.default_rng(seed)
    t0 = a.index[0] + pd.Timedelta(days=back_days)
    cand = [o for o in od if t0 < full.ts[o["i"]] < a.index[-1] - pd.Timedelta(days=fwd_days + 1)] or od
    if not cand:
        return False, 0, 0
    picks = [cand[k] for k in sorted(rng.choice(len(cand), size=min(n_samples, len(cand)), replace=False))]
    bad = 0
    for o in picks:
        T = full.ts[o["i"]]
        w = a[(a.index >= T - pd.Timedelta(days=back_days)) & (a.index < T + pd.Timedelta(days=fwd_days))]
        m = core._reflect(w, T)
        nxt = w.index[w.index > T][0]
        m.loc[nxt, "open"] = w.loc[nxt, "open"]
        c0, c1 = core.Ctx(w), core.Ctx(m)
        k0 = sorted(str(core._okey(c0, x)) for x in make(c0) if c0.ts[x["i"]] <= T)
        k1 = sorted(str(core._okey(c1, x)) for x in make(c1) if c1.ts[x["i"]] <= T)
        bad += k0 != k1
    return bad == 0, len(od), len(picks)


def _label(p):
    return f"{p['sel']:<10} {variant_name(**p):<8} {p['fresh']:<5}"


def run_checks(names, cuts=16, plain=False):
    import run
    A = run.bars("is")
    full = core.Ctx(A)
    bad = 0
    for v in names:
        p = VARIANTS[v]
        o0, o1 = orders(full, **p), orders(full, at_open=True, **p)
        k0 = {str(core._okey(full, x)) for x in o0}
        k1 = {str(core._okey(full, x)) for x in o1}
        day = [full.tod[x["i"] + 1] for x in o1]
        first = sorted({f"{t // 60:02d}:{t % 60:02d}" for t in day})
        okA = core.causal_check(lambda cx, p=p: orders(cx, **p), A, n_samples=cuts, verbose=False)
        okB, n_od, n_s = check_true_open(lambda cx, p=p: orders(cx, at_open=True, **p), A, n_samples=cuts)
        line = (f"L1 {v:<8} {_label(p)} orders {len(o1):>6} (first bars at {first[0]}..{first[-1]})  differ from the "
                f"at_open=False orders: {len(k1 - k0):>4}  | A mirrored future, open replaced by the last close: "
                f"{'PASS' if okA else 'FAIL'} | B real orders, that open kept: {'PASS' if okB else 'FAIL'} ({n_s} bars)")
        bad += (not okA) + (not okB)
        if plain:
            okC = core.causal_check(lambda cx, p=p: orders(cx, at_open=True, **p), A, n_samples=cuts, verbose=False)
            line += f" | C real orders, plain test: {'PASS' if okC else 'FAIL (through the open of bar i + 1)'}"
        print(line, flush=True)
    return bad


# ------------------------------------------------------------------ reconciliation with the tables
def recon(phase="is"):
    """Each variant's trades as saved by `run.py L1 --phase <phase>` against the events file and the table row."""
    d = core.OUT / phase
    sfx = "" if phase == "is" else "_full"                   # the full phase writes LEV1_<table>_full.csv
    ev = pd.read_parquet(d / "LEV1_events.parquet")
    rt = pd.read_csv(d / f"LEV1_reaction{sfx}.csv")
    ut = pd.read_csv(d / f"LEV1_used{sfx}.csv", low_memory=False)
    pt = pd.read_csv(d / f"LEV1_pairs{sfx}.csv")
    bad = 0
    for v, p in VARIANTS.items():
        f = d / f"L1_{v}.csv"
        if not f.exists():
            print(f"L1 {v}: no saved run ({f.name})")
            bad += 1
            continue
        tr = pd.read_csv(f)
        vn = variant_name(**p)
        rows = rows_of(ev, p["sel"], p["fresh"])
        t = rows[rows.tapped & rows[f"f_{vn}"]]
        n_e, net_e, R_e = len(t), float(t[f"pnl_{vn}"].sum()), float(t[f"R_{vn}"].mean()) if len(t) else float("nan")
        n_r, net_r, R_r = len(tr), float(tr.pnl.sum()), float(tr.R.mean()) if len(tr) else float("nan")
        # the table row
        if "+" in p["sel"]:
            row = pt[pt.pair == p["sel"]]
            where = "pairs"
        elif p["sel"].split(":")[0].endswith("~"):
            row, where = None, "placebo columns"
        elif p["fresh"] == "any":
            code, side = p["sel"].split(":")
            row = ut[(ut.table == "reaction") & (ut.set == "any") & (ut.code == code) & (ut.side == side)]
            where = "used (set any)"
        else:
            code, side = p["sel"].split(":")
            row = rt[(rt.code == code) & (rt.side == side)]
            where = "reaction"
        if row is None:
            code, side = p["sel"].split(":")
            row = rt[(rt.code == code[:-1]) & (rt.side == side)]
            n_t = int(row[f"pl_n_{vn}"].iloc[0]) if len(row) and f"pl_n_{vn}" in row else None
            R_t = float(row[f"pl_R_{vn}"].iloc[0]) if len(row) and f"pl_R_{vn}" in row else None
            net_t = float(row[f"pl_net_{vn}"].iloc[0]) if len(row) and f"pl_net_{vn}" in row else None
        elif len(row) == 1 and f"n_{vn}" in row:
            n_t, R_t, net_t = int(row[f"n_{vn}"].iloc[0]), float(row[f"R_{vn}"].iloc[0]), float(row[f"net_{vn}"].iloc[0])
        else:
            n_t = R_t = net_t = None
        same_trades = n_e == n_r and abs(net_e - net_r) < 0.005 and (n_e == 0 or abs(R_e - R_r) < 1e-9)
        if same_trades and n_e:
            a = t.sort_values("tap")[[f"pnl_{vn}", f"R_{vn}"]].to_numpy()
            b = tr.assign(_j=pd.to_datetime(tr.entry_time, utc=True)).sort_values("_j", kind="mergesort")[["pnl", "R"]].to_numpy()
            same_trades = bool(np.allclose(np.sort(a[:, 0]), np.sort(b[:, 0]), atol=0.005) and
                               np.allclose(np.sort(a[:, 1]), np.sort(b[:, 1]), atol=1e-9))
        same_table = n_t is not None and n_t == n_r and (net_t is None or abs(net_t - net_r) < 0.01) and \
            (R_t is None or n_r == 0 or abs(R_t - R_r) < 1e-5)
        bad += not (same_trades and same_table)
        print(f"L1 {v:<8} {_label(p)} run.py: n {n_r:>4} net {net_r:>+10.2f} R {R_r:>+8.4f} | events file: n {n_e:>4} net "
              f"{net_e:>+10.2f} R {R_e:>+8.4f} -> {'same' if same_trades else 'DIFFERENT'} | table ({where}): n "
              f"{n_t} net {'-' if net_t is None else f'{net_t:+.2f}'} R {'-' if R_t is None else f'{R_t:+.4f}'} -> "
              f"{'same' if same_table else 'DIFFERENT'}")
    print(f"reconciliation: {len(VARIANTS)} variants, {bad} differ -> {'OK' if bad == 0 else 'NOT OK'}")
    return bad


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", help="variant names, comma separated, or 'all'")
    ap.add_argument("--cuts", type=int, default=16)
    ap.add_argument("--plain", action="store_true", help="also core.causal_check on the real (at_open=True) orders")
    ap.add_argument("--recon", action="store_true")
    ap.add_argument("--phase", choices=["is", "full"], default="is")
    a = ap.parse_args()
    bad = 0
    if a.check:
        names = list(VARIANTS) if a.check == "all" else a.check.split(",")
        bad += run_checks(names, a.cuts, a.plain)
    if a.recon:
        bad += recon(a.phase)
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
