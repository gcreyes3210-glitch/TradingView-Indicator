#!/usr/bin/env python3
"""G8 - the YT5 confluence grid as a standard harness module (YT5_SPEC.md).

A variant is one combination of the grid (its name, see g8_grid.name) and a target multiple. The signals and their
confluence columns come from g8_signals.build, the rows a combination trades from g8_grid.pick; the harness then does
the day filter (roll day and the day after, no-ATR days, non-cash days) and the fills, so the standard runner trades
exactly the rows the grid counts.

Frame: CISD on the clock-aligned bars of the trigger timeframe, entry at the close of the 1-minute bar that closes the
CISD bar, stop 1 tick beyond the protected low / high, target k R, flat at the flat bar, one trade a day (the first
signal of the day inside the window that meets every confluence).

VARIANTS  base / nb1 / nb2          pick 1 of data/studies/yt1/G8_selected.json at 2R / 1.5R / 3R
          p2, p2_nb1, p2_nb2 ...    the other frozen picks, same three targets
          chk1 ... chk8             look-ahead check combinations, fixed before any result was seen: together they
                                    switch on every level of every confluence at least once

    python3 tools/yt1/s_G8.py --check base,p2,chk1     mirrored-future test on the named variants ("all" = every one)
"""
import argparse, json, pathlib, sys
import numpy as np
import pandas as pd
sys.path.insert(0, str(pathlib.Path(__file__).parent))
import core
import g8_grid
import g8_signals

ID = "G8"
NAME = "TTrades confluence grid: the frozen picks (YT5)"
PLACEHOLDER = "T5.Wam.Bany.Enone.Onone.Rnone.Hnone.Snone"     # only until G8_selected.json exists
CHECKS = (                                                    # fixed up front (before the grid was evaluated)
    "T1.Wam.Bany.Enone.Onone.Rnone.Hnone.Ssmt",               # B any, S smt
    "T5.Wopen.Bcont.Enone.Obelow.Rnone.Hnone.Snone",          # T 5, W open, B cont, O below
    "T1.Wsb.Bfail.Enone.Onone.Rnone.Hnone.Snone",             # W sb, B fail
    "T15.Wpm.Bnone.Edisc.Onone.Rnone.Hh1.Snone",              # T 15, W pm, E disc, H h1
    "T5.Wam.Bnone.Eprem.Onone.Rsess.Hnone.Snone",             # E prem, R sess
    "T1.Wam.Bnone.Enone.Onone.Rpd.Hnone.Snone",               # R pd
    "T5.Wam.Bnone.Enone.Onone.Rnone.Hh4.Snone",               # H h4
    "T1.Wam.Bnone.Enone.Onone.Rnone.Hnone.Snone",             # every confluence at none: the bare 1-minute CISD
)


def _picks():
    p = g8_grid.SEL_PATH
    if p.exists():
        names = [r["name"] for r in json.loads(p.read_text())["picks"]]
        if names:
            return names
    return [PLACEHOLDER]


def _variants():
    v = {}
    for n, c in enumerate(_picks(), 1):
        pre = "" if n == 1 else f"p{n}_"
        v["base" if n == 1 else f"p{n}"] = dict(c=c, k=2.0)
        v[pre + "nb1"] = dict(c=c, k=1.5)
        v[pre + "nb2"] = dict(c=c, k=3.0)
    for n, c in enumerate(CHECKS, 1):
        v[f"chk{n}"] = dict(c=c, k=2.0)
    return v


VARIANTS = _variants()


def orders(ctx, c=PLACEHOLDER, k=2.0):
    combo = g8_grid.parse(c)
    sig = g8_signals.build(ctx, tfs=(combo["T"],))            # no outcome columns: nothing after the decision bar
    rows = g8_grid.pick(sig, combo)                           # first signal of each day that meets every confluence
    i_end = ctx.days.i_end
    out = []
    for r in rows.itertuples(index=False):
        d = pd.Timestamp(r.date)
        if d not in i_end.index:
            continue                                          # not a cash day: no flat bar (the harness drops it too)
        out.append(dict(i=int(r.i), side=int(r.side), etype="close", stop=float(r.stop),
                        target=float(g8_signals.target_of(r.entry_ref, r.stop, r.side, k)), exit_i=int(i_end[d]),
                        tag=f"{'L' if r.side > 0 else 'S'}|{c}"))
    return out


def trades(ctx, **p):
    return core.run_orders(ctx, orders(ctx, **p), max_per_day=1, skip_roll=2)


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
        seen = []                                             # orders per call: the first call is the whole span

        def make(cx, p=p, seen=seen):
            o = orders(cx, **p)
            seen.append(len(o))
            return o
        ok = core.causal_check(make, A, n_samples=a.cuts, verbose=False)
        print(f"G8 {v:<8} {p['c']:<46} k {p['k']}  orders {seen[0]:>4}  sampled signal bars {(len(seen) - 1) // 2:>2}"
              f"  look-ahead test: {'PASS' if ok else 'FAIL'}", flush=True)
        bad += not ok
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
