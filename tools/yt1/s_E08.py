#!/usr/bin/env python3
"""E08 - outside-open reversal (edgeful; stated on RTY).

Spec text (YT1_SPEC.md, E08):
  The 09:30 open is above the previous RTH high by >= 0.05 x daily ATR -> short at the 09:30 open; target that high;
  stop half the target distance above the entry. Mirror below the previous low.
  Neighbours: stop one third of, equal to, the target distance.

Readings added (fixed before the first run; see notes/E08.md):
  * signal bar = the last 1-minute bar before 09:30 on the same calendar day (the 09:29 bar; on five in-sample days
    of March 2020 an earlier bar, the market being halted); etype 'open' fills at the 09:30 bar's open.
    The 09:30 open itself is read to decide the trade and to place its stop and target: this is the exception written
    in s_Z00.py (an order at the open may read that open). Nothing else of the 09:30 bar is read.
  * previous RTH high / low = day table pdh / pdl; daily ATR = day table atr (through the previous trading day).
  * target distance = |09:30 open - previous high / low| before slippage; the stop is that distance x the fraction
    from the open, rounded to the tick away from the entry (never tighter than the text). The target is the level.
  * exit otherwise at the flat bar.
"""
import numpy as np
import core

ID = "E08"
NAME = "Outside-open reversal: 09:30 open beyond the previous RTH range by >= 0.05 ATR, fade to that level"
VARIANTS = {
    "base": dict(frac=1 / 2),
    "nb1": dict(frac=1 / 3),
    "nb2": dict(frac=1.0),
}


def orders(ctx, frac=1 / 2, gap=0.05):
    out = []
    for d, day in ctx.days.iterrows():
        i = int(day.i_open) - 1                              # the bar before 09:30
        if i < 0 or ctx.dayn[i] != day.n:
            continue
        if not (day.atr == day.atr and day.pdh == day.pdh and day.pdl == day.pdl):
            continue
        o = ctx.O[i + 1]                                     # the 09:30 open: the fill price of this 'open' order
        thr = gap * day.atr
        if o - day.pdh >= thr:
            dist = o - day.pdh
            out.append(dict(i=i, side=-1, etype="open", stop=core.tick_round(o + frac * dist, "up"),
                            target=float(day.pdh), exit_i=int(day.i_end), tag="S"))
        elif day.pdl - o >= thr:
            dist = day.pdl - o
            out.append(dict(i=i, side=1, etype="open", stop=core.tick_round(o - frac * dist, "down"),
                            target=float(day.pdl), exit_i=int(day.i_end), tag="L"))
    return out


def trades(ctx, **p):
    return core.run_orders(ctx, orders(ctx, **p), max_per_day=1)


def check_with_true_open(a, n_samples=16, seed=5, back_days=150, fwd_days=7):
    """`run.py E08 --check` fails by construction: it mirrors every price after the signal bar, the 09:30 open
    included, and this order's stop is placed from that open (the s_Z00 exception). This is core.causal_check with
    one difference: in the mirrored future the OPEN of the first bar after the signal bar keeps its true value.
    Everything else after the signal bar (that bar's high, low and close, and every later bar) is mirrored.
    Run:  python3 tools/yt1/s_E08.py"""
    import pandas as pd
    full = core.Ctx(a)
    od = orders(full)
    rng = np.random.default_rng(seed)
    t0 = a.index[0] + pd.Timedelta(days=back_days)
    cand = [o for o in od if t0 < full.ts[o["i"]] < a.index[-1] - pd.Timedelta(days=fwd_days + 1)]
    picks = [cand[k] for k in sorted(rng.choice(len(cand), size=min(n_samples, len(cand)), replace=False))]
    bad = 0
    for o in picks:
        T = full.ts[o["i"]]
        w = a[(a.index >= T - pd.Timedelta(days=back_days)) & (a.index < T + pd.Timedelta(days=fwd_days))]
        m = core._reflect(w, T)
        nxt = w.index[w.index > T][0]
        m.loc[nxt, "open"] = w.loc[nxt, "open"]
        c0, c1 = core.Ctx(w), core.Ctx(m)
        k0 = sorted(str(core._okey(c0, x)) for x in orders(c0) if c0.ts[x["i"]] <= T)
        k1 = sorted(str(core._okey(c1, x)) for x in orders(c1) if c1.ts[x["i"]] <= T)
        same = k0 == k1
        bad += not same
        print(f"  {'ok ' if same else 'DIFFERENT'}  {T}  {len(k0)} orders, next bar {nxt.strftime('%H:%M')} open kept, "
              f"the rest of the future mirrored")
    return bad == 0


if __name__ == "__main__":
    import sys, pathlib
    sys.path.insert(0, str(pathlib.Path(__file__).parent))
    a = core.load_bars("MNQ", cut=core.IS_END)
    assert a.index.max() < core.IS_END
    print("E08 look-ahead test with the 09:30 open kept:", "PASS" if check_with_true_open(a) else "FAIL")
