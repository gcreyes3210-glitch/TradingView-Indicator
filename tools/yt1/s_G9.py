#!/usr/bin/env python3
"""G9 - the YT6 confluence grid as a standard harness module (YT6_SPEC.md, Part 1).

A variant is one combination of the grid (its name, see g9_grid.name) and a neighbour number. The signals and their
confluence columns come from g9_signals.build, the day's one order of a combination from g9_grid.pick, the order
itself from g9_signals.order_of; the harness then does the day filter (roll day and the day after, no-ATR days,
non-cash days) and the fills, so the standard runner trades exactly the orders the grid counts.

Frame: CISD on the clock-aligned bars of the trigger timeframe, decision at the close of the 1-minute bar that closes
the CISD bar, stop 1 tick beyond the protected low / high, one ORDER a day (the first signal of the day inside the
window that meets every confluence and the target's qualification; if it does not fill there is no trade that day),
flat at the flat bar, London-window trades flat at 08:29.
    N close    market at the decision bar's close
    N retest   limit at the opening price the CISD closed through, resting 30 minutes, cancelled if the stop trades
    N pos      market at the open of the first 1-minute bar of the next clock hour; no order if the stop price traded
               before then; cancelled if that open is at or beyond a level target. The order's `i` is the bar before
               the hour opens. With X 2R the target is 2R from that open, the fill price: the s_Z00 exception (an
               'open' order may read open[i + 1] to place its target). core.causal_check mirrors that open, so
               orders() returns these orders WITHOUT the target (everything decided from bars is in the order and
               is what the mirrored-future test compares) and trades() adds it (open_target=True: arithmetic on
               the fill price and the stop, nothing else). `s_G9.py --check` also runs the test on the full order
               with the one open kept (as s_E08 does); `--plain` shows the unmodified test failing on the full
               order, as it must. Only the N pos x X 2R combinations are affected.
    X 2R       target k R from the entry price (nb 0 / 1 / 2: k = 2 / 1.5 / 3)
    X pdx/liq  target = the level; the signal must have it at least m R away (nb 0 / 1 / 2: m = 1 / 0.75 / 1.5)

VARIANTS  base / nb1 / nb2          pick 1 of data/studies/yt1/G9_selected.json and its two registered neighbours
          p2, p2_nb1, p2_nb2 ...    the other frozen picks (p6 = the consensus combination)
          chk1 ... chk13            look-ahead / reconciliation combinations, fixed before any result was seen:
                                    together they switch on every level of every confluence, every window, and all
                                    nine pairs of target and entry

    python3 tools/yt1/s_G9.py --check base,p2,chk1     mirrored-future test on the named variants ("all" = every one);
                                                       a positional variant is tested three ways (see main)
"""
import argparse, json, pathlib, sys
import numpy as np
import pandas as pd
sys.path.insert(0, str(pathlib.Path(__file__).parent))
import core
import g9_grid
import g9_signals

ID = "G9"
NAME = "TTrades confluence grid 2: the frozen picks (YT6)"
PLACEHOLDER = "T5.Wam.Bany.Enone.Mnone.Rnone.Hnone.Snone.X2R.Nclose"     # only until G9_selected.json exists
CHECKS = (                                                    # fixed up front (before the grid was evaluated)
    "T1.Wldn.Bnone.Enone.Mmid.Rsess.Hnone.Snone.Xliq.Nretest",       # W ldn, M mid, R sess (18:00-01:59), liq x retest
    "T5.Wldn.Binv.Enone.Mnone.Rnone.Hnone.Snone.X2R.Npos",           # B inv in London, 2R x pos, the 08:29 exit
    "T1.Wam.Bany.Enone.Mboth.Rnone.Hnone.Ssmt.X2R.Nclose",           # B any, M both, S smt
    "T5.Wopen.Bcont.Enone.Md18.Rnone.Hnone.Snone.Xpdx.Nclose",       # W open, B cont, M d18, pdx x close
    "T1.Wsb.Bfail.Enone.Mnone.Rnone.Hnone.Snone.Xliq.Npos",          # W sb, B fail, liq x pos
    "T15.Wpm.Bnone.Edisc.Mnone.Rnone.Hh1.Snone.Xpdx.Nretest",        # T 15, W pm, E disc, H h1, pdx x retest
    "T5.Wam.Bnone.Eprem.Mnone.Rsess.Hnone.Snone.X2R.Nretest",        # E prem, R sess (18:00-08:29), 2R x retest
    "T1.Wam.Bnone.Enone.Mnone.Rpd.Hnone.Snone.Xpdx.Npos",            # R pd, pdx x pos
    "T1.Wam.Bnone.Enone.Mnone.Rpd_brk.Hnone.Snone.X2R.Nclose",       # R pd_brk
    "T5.Wam.Bnone.Enone.Mnone.Rsess_brk.Hh4.Snone.Xliq.Nclose",      # R sess_brk, H h4, liq x close
    "T15.Wldn.Bnone.Enone.Mnone.Rsess_brk.Hnone.Snone.X2R.Nclose",   # R sess_brk on the London session range
    "T1.Wam.Bnone.Enone.Mnone.Rnone.Hnone.Snone.X2R.Nclose",         # every confluence off: the bare 1-minute CISD
    "T1.Wam.Binv.Enone.Mnone.Rnone.Hnone.Snone.X2R.Npos",            # B inv in New York, 2R x pos on 1 minute
)


def _picks():
    p = g9_grid.SEL_PATH
    if p.exists():
        got = [(int(r["pick"]), r["name"]) for r in json.loads(p.read_text())["picks"]]
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


def params(c, nb):
    """(combo, target multiple k, minimum-distance tag md) of a combination name and a neighbour number."""
    combo = g9_grid.parse(c)
    if combo["X"] == "2R":
        return combo, g9_signals.K_NB[nb], "100"
    return combo, 2.0, g9_signals.MD_NB[nb]


def nb_label(c, nb):
    combo, k, md = params(c, nb)
    return f"{k:g}R" if combo["X"] == "2R" else f"{combo['X']} min {int(md) / 100:g}R"


def orders(ctx, c=PLACEHOLDER, nb=0, open_target=False):
    """The day's one order of combination c (neighbour nb), each built from bars up to its own bar `i` only.
    open_target=False (what the look-ahead test calls): a positional 2R order carries no target yet; trades() sets
    open_target=True, which adds target = 2R from open[i + 1], that order's fill price. Every other order is
    complete either way."""
    combo, k, md = params(c, nb)
    sig = g9_signals.build(ctx, tfs=(combo["T"],))            # no outcome columns: nothing after the decision bar
    rows = g9_grid.pick(sig, combo, md=md)                    # the day's one order: first qualifying signal of the day
    out = []
    for r in rows.itertuples(index=False):
        ex = g9_signals.exit_of(ctx, r.date, r.w_ldn)
        if ex is None:
            continue                                          # no flat bar (not a cash day): the harness drops it too
        o = g9_signals.order_of(ctx, r, combo["X"], combo["N"], k=k, md=md, exit_i=ex, open_target=open_target)
        if o is None:
            continue                                          # positional: cancelled before the hour opened
        o["tag"] = f"{'L' if r.side > 0 else 'S'}|{c}|{int(r.i)}"     # the last field is the decision bar
        out.append(o)
    return out


def trades(ctx, **p):
    return core.run_orders(ctx, orders(ctx, open_target=True, **p), max_per_day=1, skip_roll=2)


def open_exception(c):
    """True for the combinations whose order reads open[i + 1] to place its target (N pos with X 2R)."""
    combo = g9_grid.parse(c)
    return combo["N"] == "pos" and combo["X"] == "2R"


def check_true_open(make, a, n_samples=16, seed=5, back_days=150, fwd_days=7):
    """core.causal_check (same sampling, same comparison) with one difference: in the mirrored future the OPEN of the
    first bar after the sampled order's bar keeps its true value; that bar's high, low and close and every later bar
    are mirrored. For orders that use the s_Z00 exception (as s_E08.check_with_true_open)."""
    full = core.Ctx(a)
    od = make(full)
    rng = np.random.default_rng(seed)
    t0 = a.index[0] + pd.Timedelta(days=back_days)
    cand = [o for o in od if t0 < full.ts[o["i"]] < a.index[-1] - pd.Timedelta(days=fwd_days + 1)] or od
    if not cand:
        return False
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
    return bad == 0


def main():
    import run
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", required=True, help="variant names, comma separated, or 'all'")
    ap.add_argument("--cuts", type=int, default=16)
    ap.add_argument("--plain", action="store_true",
                    help="also run core.causal_check on the full order of the 2R x pos variants (fails by construction)")
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
        line = (f"G9 {v:<8} {p['c']:<56} {nb_label(p['c'], p['nb']):<14} orders {seen[0]:>4}  sampled order bars "
                f"{(len(seen) - 1) // 2:>2}  look-ahead test: {'PASS' if ok else 'FAIL'}")
        bad += not ok
        if p["c"].endswith(".Npos"):
            # a positional order's bar is the last bar before the hour opens, so the test above cuts the future there;
            # the same combination entered at the close has the same signals with the order ON the decision bar:
            # this run cuts the future right after the decision bars
            twin = p["c"][:-len("pos")] + "close"
            ok1 = core.causal_check(lambda cx, p=p: orders(cx, c=twin, nb=p["nb"]), A, n_samples=a.cuts, verbose=False)
            line += f"   | same signals cut at the decision bar (N close): {'PASS' if ok1 else 'FAIL'}"
            bad += not ok1
        if open_exception(p["c"]):
            ok2 = check_true_open(lambda cx, p=p: orders(cx, open_target=True, **p), A, n_samples=a.cuts)
            line += f"   | full order, entry open kept: {'PASS' if ok2 else 'FAIL'}"
            bad += not ok2
            if a.plain:
                ok3 = core.causal_check(lambda cx, p=p: orders(cx, open_target=True, **p), A, n_samples=a.cuts,
                                        verbose=False)
                line += f"   | full order, plain test: {'PASS' if ok3 else 'FAIL (by construction)'}"
        print(line, flush=True)
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
