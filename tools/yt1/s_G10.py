#!/usr/bin/env python3
"""G10 - the hourly add to an open ORB v1.4 trade (YT7_SPEC.md, Part 1). Second coder: written from the spec text,
tt.py, core.py and cal_orb.py only.

The signal (long written, short mirrors):
  overnight high = highest high of the 1-minute bars 18:00 .. 08:29 of the current trading day;
  a bullish CISD (tt.cisd on the whole 1-minute series) on a bar 09:30 .. 10:59 whose protected low is above the
  overnight high; the first such signal of the day, long or short, is the day's signal;
  buy at the open of the first 1-minute bar of the next clock hour (10:00 / 11:00); cancelled if price trades at or
  below the stop between the signal bar's close and that open; stop 1 tick below the protected low; target k R from
  the fill; flat at the flat bar.
G10 base: the day's signal is taken only if, at that hour's open, an ORB v1.4 trade entered earlier that day is still
open and on the same side. One add a day; the add has its own stop and target.

Variants: base 2R, nb1 1.5R, nb2 3R, retry, alone, naive (no signal: second contract on the hour while ORB is in),
signal (the day's signal with no ORB condition).

How the fill-dependent target is handled (see notes/G10.md):
  orders(ctx, **p)       every order built from bars up to the close of its bar i ONLY: side, stop, flat bar. It
                         carries NO target, because the target is k R from the order's own fill = open[i + 1].
  full_orders(ctx, **p)  the same orders with target = tick_round(open[i+1] + side * k * |open[i+1] - stop|): the one
                         exception s_Z00.py allows (an 'open' order may read ctx.O[i + 1] to place its own target).
  trades(ctx, **p)       core.run_orders(ctx, full_orders(...), max_per_day=1, skip_roll=2).
  `run.py G10 --check` / core.causal_check run on orders(); check_true_open() (E08's form of the test: the future is
  mirrored except the open of the first bar after the signal bar) runs on full_orders(), targets included.

Readings (R), all fixed before the first run - see notes/G10.md.
"""
import numpy as np
import pandas as pd
import core
import tt
import cal_orb

ID = "G10"
NAME = "Hourly add to an open ORB v1.4 trade (1m CISD beyond the overnight extreme, entry at the next hour's open)"
VARIANTS = {
    "base": dict(k=2.0, mode="base"),
    "nb1": dict(k=1.5, mode="base"),
    "nb2": dict(k=3.0, mode="base"),
    "retry": dict(k=2.0, mode="retry"),
    "alone": dict(k=2.0, mode="alone"),
    "naive": dict(k=None, mode="naive"),
    "signal": dict(k=2.0, mode="signal"),
}
T = core.TICK


def _hm(t):
    return f"{int(t) // 60:02d}{int(t) % 60:02d}"


def prep(ctx):
    """Per-context tables, built once: the day's qualifying signals and ORB v1.4's trade of each day.
    sig[d]  = list of (k, side, stop, level) in time order: k = the CISD bar (09:30 .. 10:59), stop = 1 tick beyond the
              protected low / high, level = the overnight high / low it is beyond.
    orb[d]  = dict(j entry bar, k exit bar, side, stop, flat = ORB's own flat bar). Callers use k ONLY through the
              test `k <= i` (had ORB already exited by the close of bar i).
    on[d]   = (overnight high, its bar, overnight low, its bar)."""
    if getattr(ctx, "_g10", None) is not None:
        return ctx._g10
    H, L = ctx.H, ctx.L
    # CISD on the continuous 1-minute series (lists: the same floats as the arrays, a faster loop inside tt.cisd)
    bull, bear, plo, phi = tt.cisd(ctx.O.tolist(), H.tolist(), L.tolist(), ctx.C.tolist())
    # ORB v1.4 exactly as cal_orb's main takes it: it trades on roll days too
    oo = cal_orb.orders(ctx)
    flat = {int(o["i"]): int(o["exit_i"]) for o in oo}
    tr = core.trades_df(core.run_orders(ctx, oo, skip_roll=False))
    orb = {}
    for r in tr.itertuples():
        d = pd.Timestamp(ctx.cdate[r.j])
        assert d not in orb, "ORB v1.4 is one trade a day"
        orb[d] = dict(j=int(r.j), k=int(r.k), side=1 if r.side == "L" else -1, stop=float(r.stop), flat=flat[int(r.i)])
    sig, on = {}, {}
    tdate = ctx.tdate
    for d in ctx.days.index:
        i0 = int(np.searchsorted(tdate, np.datetime64(d, "D"), "left"))      # first bar of trading day d (18:00)
        i1 = ctx.span(d, "08:30", "08:31")[0]                                # first bar at or after 08:30 on d
        if i1 <= i0:
            continue
        a_h, a_l = i0 + int(H[i0:i1].argmax()), i0 + int(L[i0:i1].argmin())
        onh, onl = H[a_h], L[a_l]
        on[d] = (float(onh), a_h, float(onl), a_l)
        lo, hi = ctx.span(d, "09:30", "11:00")                               # CISD bars 09:30 .. 10:59
        s = []
        for k in range(lo, hi):
            if bull[k] and plo[k] > onh:
                s.append((k, 1, float(plo[k] - T), float(onh)))
            elif bear[k] and phi[k] < onl:
                s.append((k, -1, float(phi[k] + T), float(onl)))
        if s:
            sig[d] = s
    ctx._g10 = dict(sig=sig, orb=orb, on=on)
    return ctx._g10


def hour_bar(ctx, d, k):
    """The first 1-minute bar of the clock hour after bar k's (10:00 or 11:00), or None if that hour has no bar."""
    hr = int(ctx.tod[k]) // 60 + 1
    lo, hi = ctx.span(d, hr * 60, hr * 60 + 60)
    return (lo if hi > lo else None), hr


def orb_state(o, i):
    """What is known of the day's ORB trade at the close of bar i (= just before the open of bar i + 1):
    'N' it had not entered, 'X' it had entered and already exited, 'L' / 'S' it is open on that side.
    Uses the entry bar, the side, and only WHETHER the exit bar is at or before i."""
    if o is None or o["j"] > i:
        return "N"
    if o["k"] <= i:
        return "X"
    return "L" if o["side"] > 0 else "S"


def look(ctx, P, d, s):
    """One signal -> (order or None, why). why: 'ok', 'nobar', 'cancel', then the ORB state letter is in the tag."""
    k, side, stop, _ = s
    h, hr = hour_bar(ctx, d, k)
    if h is None:
        return None, "nobar", "N"
    i = h - 1                                            # the last bar before the hour's open: the decision bar
    st = orb_state(P["orb"].get(d), i)
    if i > k:                                            # bars after the signal bar, up to the last one before the open
        if (side > 0 and ctx.L[k + 1:i + 1].min() <= stop) or (side < 0 and ctx.H[k + 1:i + 1].max() >= stop):
            return None, "cancel", st
    day = ctx.days.loc[d]
    o = dict(i=int(i), side=side, etype="open", stop=float(stop), exit_i=int(day.i_end),
             tag=("L" if side > 0 else "S") + f"{hr}|sig{_hm(ctx.tod[k])}|orb{st}")
    return o, "ok", st


def orders(ctx, k=2.0, mode="base"):
    """Every order, built from bars up to the close of its bar i only. No target here (see the module docstring)."""
    P = prep(ctx)
    out = []
    if mode == "naive":
        for d, o in P["orb"].items():
            if d not in ctx.days.index:
                continue
            t = int(ctx.tod[o["j"]])                     # the 1-minute bar at whose close ORB entered
            hr = 10 if t < 600 else 11 if t < 660 else None
            if hr is None:
                continue
            lo, hi = ctx.span(d, hr * 60, hr * 60 + 60)
            if hi <= lo:
                continue
            i = lo - 1
            st = orb_state(o, i)
            if st not in ("L", "S"):
                continue
            out.append(dict(i=int(i), side=o["side"], etype="open", stop=o["stop"], exit_i=o["flat"],
                            tag=st + f"{hr}|orb{_hm(t)}"))
        return sorted(out, key=lambda x: x["i"])
    for d, sigs in P["sig"].items():
        use = sigs[:2] if mode == "retry" else sigs[:1]   # the day's signal; retry: also the next one
        for n, s in enumerate(use):
            o, why, st = look(ctx, P, d, s)
            aligned = st == ("L" if s[1] > 0 else "S")
            if mode == "signal":
                ok = o is not None
            elif mode == "alone":
                ok = o is not None and not aligned
            else:                                        # base, retry
                ok = o is not None and aligned
            if ok:
                o["tag"] += f"|n{n + 1}"
                out.append(o)
                break
    return out


def full_orders(ctx, k=2.0, mode="base"):
    """orders() plus the target: k R from the order's own fill price (the open of bar i + 1, before slippage), rounded
    to the tick. This is the only place a bar after i is read, and only its open (the s_Z00 exception)."""
    out = []
    for o in orders(ctx, k=k, mode=mode):
        o = dict(o)
        if k is not None and o["i"] + 1 < ctx.n:
            e = ctx.O[o["i"] + 1]
            o["target"] = float(core.tick_round(e + o["side"] * k * abs(e - o["stop"])))
        out.append(o)
    return out


def trades(ctx, **p):
    return core.run_orders(ctx, full_orders(ctx, **p), max_per_day=1, skip_roll=2)


def check_true_open(a, n_samples=16, seed=5, back_days=150, fwd_days=7, **p):
    """core.causal_check on full_orders() (targets included) with one difference, as s_E08.check_with_true_open: in the
    mirrored future the OPEN of the first bar after the signal bar keeps its true value (it is the order's own fill
    price); that bar's high, low and close and every later bar are mirrored."""
    full = core.Ctx(a)
    od = full_orders(full, **p)
    rng = np.random.default_rng(seed)
    t0 = a.index[0] + pd.Timedelta(days=back_days)
    cand = [o for o in od if t0 < full.ts[o["i"]] < a.index[-1] - pd.Timedelta(days=fwd_days + 1)]
    picks = [cand[j] for j in sorted(rng.choice(len(cand), size=min(n_samples, len(cand)), replace=False))]
    bad = 0
    for o in picks:
        Tm = full.ts[o["i"]]
        w = a[(a.index >= Tm - pd.Timedelta(days=back_days)) & (a.index < Tm + pd.Timedelta(days=fwd_days))]
        m = core._reflect(w, Tm)
        nxt = w.index[w.index > Tm][0]
        m.loc[nxt, "open"] = w.loc[nxt, "open"]
        c0, c1 = core.Ctx(w), core.Ctx(m)
        k0 = sorted(str(core._okey(c0, x)) for x in full_orders(c0, **p) if c0.ts[x["i"]] <= Tm)
        k1 = sorted(str(core._okey(c1, x)) for x in full_orders(c1, **p) if c1.ts[x["i"]] <= Tm)
        same = k0 == k1
        here = str(core._okey(full, o)) in k0
        bad += not same
        print(f"  {'ok ' if same else 'DIFFERENT'}  {Tm}  {len(k0)} orders, {nxt.strftime('%H:%M')} open kept, the rest "
              f"of the future mirrored" + ("" if here else "   (sampled order not reproduced on the window)"))
        if not same:
            for x in sorted(set(k0) ^ set(k1))[:4]:
                print("     ", x)
    return bad == 0


if __name__ == "__main__":
    import sys
    a = core.load_bars("MNQ", cut=core.IS_END)
    assert a.index.max() < core.IS_END
    names = sys.argv[1:] or list(VARIANTS)
    res = {}
    for v in names:
        p = VARIANTS[v]
        print(f"--- {v}: core.causal_check on orders() (no target in the order)")
        r1 = core.causal_check(lambda c: orders(c, **p), a)
        print(f"--- {v}: mirrored future with the fill bar's open kept, on full_orders() (target included)")
        r2 = check_true_open(a, **p)
        res[v] = (r1, r2)
    for v, (r1, r2) in res.items():
        print(f"G10 {v:<7} look-ahead: orders() {'PASS' if r1 else 'FAIL'}   full_orders() with true open "
              f"{'PASS' if r2 else 'FAIL'}")
