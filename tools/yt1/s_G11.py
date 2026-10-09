#!/usr/bin/env python3
"""G11 - the break-and-retest grid as a standard harness module (YT8_SPEC.md, Part 1).

A variant is one combination of the grid (its name, see g11_grid.name) and a neighbour number. This module trades
ONE combination directly: for each cash day it builds the level, the break, the displacement test, the side filter,
the entry, the stop and the target with the set-up functions of g11_sim.py and its own cut-off (the 11:00 cut-off
is simulated here, not derived), and hands the orders to core.run_orders(skip_roll=2). It never reads the grid's
trade file, so `run.py G11` reproducing a grid row is a check of both.

    E one   orders() = the day's first order.
    E re    orders() = the day's first order and, where core.simulate says that order's trade was stopped on a bar
            closing by the cut-off, the re-entry order (a market order at the close of the re-entry candle with the
            first trade's stop and target prices). The re-entry order's bar is after the first trade's exit bar, so
            it is a function of bars up to its own bar only; core.run_orders (one position at a time, at most two
            trades a day) then trades the two in sequence.

    nb 0 the combination; nb 1 the other cut-off; nb 2 the adjacent target (1.5R -> 2R, 2R -> 3R, 3R -> 2R,
    hold -> 3R)  (the order YT8_SPEC lists the neighbours in)

VARIANTS  base / nb1 / nb2            pick 1 of data/studies/yt1/G11_selected.json and its two registered neighbours
          p2, p2_nb1, p2_nb2 ...      the other frozen picks
          chk1 ... chk14              look-ahead / reconciliation combinations, fixed before any result was seen:
                                      together they switch on every level of every one of the nine choices

    python3 tools/yt1/s_G11.py --check base,p2,chk1     mirrored-future test on the named variants ("all" = every one)
"""
import argparse, json, pathlib, sys
import numpy as np
import pandas as pd
sys.path.insert(0, str(pathlib.Path(__file__).parent))
import core
import g11_grid
import g11_sim as gs
from g11_grid import name, parse, neighbour

ID = "G11"
NAME = "Break-and-retest grid: the frozen picks (YT8)"
SEL_PATH = g11_grid.SEL_PATH
PLACEHOLDER = "Lor15.Kc5.Dnone.Nedge.Snear.X2R.W11.Eone.Fnone"          # only until G11_selected.json exists
CHECKS = (                                                    # fixed up front (before the grid was evaluated)
    "Lor5.Kc1.Dnone.Nedge.Snear.X1.5R.W11.Eone.Fnone",       # or5, c1, edge x near (0.25 W), 1.5R
    "Lor15.Kc5.Dfvg.Nconf.Snear.X2R.W12.Ere.Fema200",        # fvg, conf x near, re-entry, ema200
    "Lor30.Kc15.Dext.Nzone.Snear.X3R.W11.Ere.Fvwap",         # or30, c15, ext, zone (5-minute candles), 3R, vwap
    "Lpd.Kc5.Dnone.Nconf.Snear.Xhold.W12.Eone.Fema921",      # pd, hold, ema921
    "Lor15.Kc1.Dext.Nmid.Snear.X2R.W12.Ere.Fnone",           # mid entry x near (midline - 0.25 W), ext on 1 minute
    "Lor5.Kc5.Dnone.Npoc.Snear.X3R.W11.Eone.Fvwap",          # poc x near (value-area low)
    "Lor30.Kc5.Dfvg.Nedge.Smid.Xhold.W12.Ere.Fnone",         # edge x mid stop, hold with re-entry
    "Lor15.Kc15.Dnone.Npoc.Sfar.X1.5R.W12.Eone.Fema200",     # poc x far stop
    "Lpd.Kc1.Dext.Nedge.Snear.X2R.W12.Ere.Fnone",            # pd edge (waits for W), ext with the 09:30-09:44 width
    "Lpd.Kc15.Dfvg.Nzone.Snear.X1.5R.W11.Eone.Fnone",        # pd zone
    "Lor5.Kc15.Dext.Nconf.Sfar.X2R.W11.Ere.Fema921",         # conf x far stop
    "Lor30.Kc1.Dnone.Nzone.Smid.X3R.W12.Ere.Fnone",          # zone (1-minute candles) x mid stop
    "Lor5.Kc1.Dext.Nconf.Smid.Xhold.W11.Eone.Fnone",         # conf x mid stop
    "Lor15.Kc5.Dnone.Nmid.Sfar.X2R.W11.Ere.Fnone",           # mid entry x far stop
)
FLAG = {"ema200": 0, "vwap": 1, "ema921": 2}


def nb_label(c, nb):
    return name(neighbour(parse(c) if isinstance(c, str) else c, nb))


def _picks():
    if SEL_PATH.exists():
        got = [(int(r["pick"]), r["name"]) for r in json.loads(SEL_PATH.read_text())["picks"]]
        if got:
            return got
    return [(1, PLACEHOLDER)]


def _variants():
    v = {}
    for n, c in _picks():
        pre = "" if n == 1 else f"p{n}_"
        v["base" if n == 1 else f"p{n}"] = dict(c=c, nb=0)
        v[pre + "nb1"] = dict(c=c, nb=1)
        v[pre + "nb2"] = dict(c=c, nb=2)
    for n, c in enumerate(CHECKS, 1):
        v[f"chk{n}"] = dict(c=c, nb=0)
    return v


VARIANTS = _variants()


def day_orders(P, d, day, c):
    """(first order, re-entry order) of combination c (a dict) on cash day d; either may be None. Each order is
    built from bars up to its own bar `i` only: the re-entry from the first trade's stop-out, which is before it."""
    cut, i_end = gs.day_frame(P, d, day, gs.CUT[c["W"]])
    lv = gs.level(P, d, day, c["L"])
    if lv is None:
        return None, None
    br = gs.find_break(P, lv, c["K"], cut)
    if br is None:
        return None, None
    if c["F"] != "none" and not gs.filter_flags(P, br)[FLAG[c["F"]]]:
        return None, None                                     # the filter rejects the break: no trade that day
    if c["D"] == "fvg" and not gs.fvg_flag(P, br):
        return None, None
    a = gs.arm_bar(P, lv, br, c["D"], cut)
    if a is None:
        return None, None
    plan = gs.entry_plan(P, lv, br, c["N"], a, cut)
    if plan is None:
        return None, None
    o = gs.first_order(br.side, plan, gs.stop_ticks(lv, br.side, c["N"], c["S"], plan), c["X"], cut, i_end)
    if o is None:
        return None, None
    o2 = None
    if c["E"] == "re":
        o2 = gs.reentry_order(P, lv, c["K"], br.side, core.simulate(P.ctx, **o), o, cut)
    tag = f"{'L' if br.side > 0 else 'S'}|{name(c)}|b{br.b}"
    o["tag"] = tag + "|1"
    if o2 is not None:
        o2["tag"] = tag + "|2"
    return o, o2


def orders(ctx, c=PLACEHOLDER, nb=0, which=None):
    """Every candidate order of combination c (neighbour nb). which = 1 / 2 keeps only the first orders / only the
    re-entry orders (used by the look-ahead test to sample re-entry bars)."""
    combo = neighbour(parse(c), nb)
    P = gs.prep(ctx)
    out = []
    for d, day in ctx.days.iterrows():
        o1, o2 = day_orders(P, d, day, combo)
        if o1 is not None and which in (None, 1):
            out.append(o1)
        if o2 is not None and which in (None, 2):
            out.append(o2)
    return out


def trades(ctx, **p):
    combo = neighbour(parse(p.get("c", PLACEHOLDER)), p.get("nb", 0))
    return core.run_orders(ctx, orders(ctx, **p), max_per_day=2 if combo["E"] == "re" else 1, skip_roll=2)


def main():
    import run
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", required=True, help="variant names, comma separated, or 'all'")
    ap.add_argument("--cuts", type=int, default=16)
    a = ap.parse_args()
    names = list(VARIANTS) if a.check == "all" else a.check.split(",")
    A = run.bars("is")
    bad = 0
    for v in names:
        p = VARIANTS[v]
        combo = neighbour(parse(p["c"]), p["nb"])
        seen = []

        def make(cx, p=p, seen=seen, which=None):
            o = orders(cx, which=which, **p)
            seen.append(len(o))
            return o
        ok = core.causal_check(make, A, n_samples=a.cuts, verbose=False)
        line = f"G11 {v:<8} {name(combo):<50} orders {seen[0]:>4}  look-ahead test: {'PASS' if ok else 'FAIL'}"
        bad += not ok
        if combo["E"] == "re":
            # the same test with the sample drawn from the re-entry orders only: every sampled bar is a re-entry
            # candle's close, and every re-entry order up to it must be identical under a mirrored future
            seen2 = []
            n2 = len(orders(core.Ctx(A), which=2, **p))
            if n2:
                ok2 = core.causal_check(lambda cx, p=p: make(cx, p, seen2, 2), A, n_samples=a.cuts, verbose=False)
                line += f"   | re-entry orders alone ({n2}): {'PASS' if ok2 else 'FAIL'}"
                bad += not ok2
            else:
                line += "   | no re-entry orders"
        print(line, flush=True)
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
