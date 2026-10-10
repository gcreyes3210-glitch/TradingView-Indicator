#!/usr/bin/env python3
"""G12 checks (YT11_SPEC.md, Part 3, "Checks"). Reads bars; writes nothing. The last line starts with PASS or FAIL.

    python3 tools/yt1/g12_verify.py [--phase is|full] [--parts abcd]

  a  replay    every order of six `mkt` combinations (and of the frozen picks' mkt form) on a sample of cash days,
               roll days and days without an ATR included, through core.run_orders -> core.simulate: the same
               trades, bar for bar, and the same P&L to the cent (at least 2,000 trades)
  b  limits    30 `lim` orders, filled and unfilled, printed with the decision bar and the next bar so they can be
               checked by hand; each is also recomputed here from the printed bars with scalar arithmetic, and so
               are 3,000 more that are not printed
  c  future    the look-ahead test: bars truncated at random mid-session times; (1) every trade of six combinations
               (and the frozen picks) that had exited by the cut must be identical, (2) every signal value (side, z)
               of all 18 signals at every bar up to the cut must be identical. Two deliberately leaky signals
               (patched in memory) show what each half catches. Then the harness's own mirrored-future test
               (core.causal_check) on three mkt combinations.
  d  slow      whole days of nine combinations (and the frozen picks) re-derived from the spec text with plain loops
               and the harness's clock (ctx.idx): decisions, s, s_d, VWAP, sides, strengths, fills and P&L, trade for trade
  e  grid      the grid row of the picks and of 24 random combinations recomputed with pandas from the trade list;
               the picks of G12_selected.json re-derived from the frozen grid file
"""
import argparse, json, math, pathlib, sys, time
import numpy as np
import pandas as pd
sys.path.insert(0, str(pathlib.Path(__file__).parent))
import core, run
import g12_sim as gs

MKT6 = ["mom-1.z0.k1.mkt", "rev-5.z1.k5.mkt", "es-15.z0.k15.mkt", "esr-30.z2.k30.mkt", "vw.z1.k2.mkt", "vwr.z0.k10.mkt"]
LIM6 = ["mom-5.z0.k1.lim", "rev-30.z1.k3.lim", "es-1.z0.k2.lim", "esr-5.z1.k10.lim", "vw.z2.k30.lim", "vwr.z0.k5.lim"]
LOOK6 = ["mom-5.z0.k1.lim", "rev-30.z1.k3.mkt", "es-1.z0.k2.lim", "esr-5.z1.k10.mkt", "vw.z2.k30.lim", "vwr.z0.k5.mkt"]
SLOW9 = ["mom-1.z0.k1.mkt", "rev-5.z1.k5.mkt", "es-15.z0.k15.mkt", "esr-30.z2.k30.mkt", "vw.z1.k2.mkt", "vwr.z0.k10.mkt",
         "mom-30.z1.k3.lim", "es-1.z1.k1.lim", "vwr.z2.k30.lim"]
CAUSAL3 = ["mom-15.z1.k5.mkt", "es-5.z0.k10.mkt", "vw.z1.k15.mkt"]
BAD = []


def check(ok, msg):
    print(("  ok    " if ok else "  FAIL  ") + msg)
    if not ok:
        BAD.append(msg)
    return ok


def picks():
    p = core.OUT / "G12_selected.json"
    return [r["name"] for r in json.loads(p.read_text())["picks"]] if p.exists() else []


def as_mkt(nm):
    return gs.name(dict(gs.parse(nm), E="mkt"))


def uniq(xs):
    return list(dict.fromkeys(xs))


# ------------------------------------------------------------------ a: replay through the harness
def replay(ctx, P, names, n_days=100, seed=12):
    print("\n(a) replay through core.run_orders / core.simulate (one_at_a_time=False, skip_roll=True)")
    D = ctx.days
    rng = np.random.default_rng(seed)
    rows = set(rng.choice(len(D), size=min(n_days, len(D)), replace=False).tolist())
    rows |= set(np.flatnonzero(~P.traded).tolist())                      # every roll day and day without an ATR
    rows |= set(np.flatnonzero(D.early.to_numpy(bool))[:6].tolist())
    rows = np.array(sorted(rows))
    days = P.day[rows]
    print(f"  {len(rows)} cash days: {int(P.traded[rows].sum())} traded, {int((~P.traded[rows]).sum())} roll / no-ATR days,"
          f" {int(D.early.to_numpy(bool)[rows].sum())} early closes")
    total = 0
    for nm in names:
        t0 = time.time()
        dset = np.isin(ctx.cdate, days)
        o = [x for x in gs.orders(P, nm) if dset[x["i"]]]
        n_untraded = sum(1 for x in o if not P.traded[P.sess[x["i"]]])
        h = core.trades_df(core.run_orders(ctx, o, one_at_a_time=False, skip_roll=True))
        mine = gs.trades(P, nm)
        mine = mine[np.isin(mine.day.to_numpy().astype("datetime64[D]"), days)].reset_index(drop=True)
        ok = len(h) == len(mine)
        worst = float("nan")
        if ok and len(h):
            s = np.where(h.side.to_numpy() == "L", 1, -1)
            worst = float(np.abs(h.pnl.to_numpy() - mine.net.to_numpy()).max())
            ok = (np.array_equal(h.i.to_numpy(), mine.i.to_numpy()) and np.array_equal(h.k.to_numpy(), mine.x.to_numpy())
                  and np.array_equal(h.j.to_numpy(), mine.i.to_numpy()) and np.array_equal(s, mine.side.to_numpy())
                  and worst < 0.005
                  and np.array_equal(h.entry.to_numpy(), mine.ref.to_numpy() + s * core.SLIP)
                  and np.array_equal(h.exit.to_numpy(), mine.exit_px.to_numpy() - s * core.SLIP)
                  and np.allclose(h.R.to_numpy(), mine.net.to_numpy() / mine.unit.to_numpy(), rtol=1e-12, atol=0)
                  and (h.reason == "time").all())
            ok = ok and bool((mine.i.to_numpy()[1:] >= mine.x.to_numpy()[:-1]).all())     # one position at a time
        total += len(h)
        check(ok, f"{nm:<20} orders {len(o):>6} ({n_untraded} on untraded days, dropped by run_orders)  harness trades"
                  f" {len(h):>6}  vectorised {len(mine):>6}  largest P&L difference ${worst:.4f}"
                  f"  net ${mine.net.sum():+.2f} = ${h.pnl.sum():+.2f}   [{time.time() - t0:.0f}s]")
    check(total >= 2000, f"{total} mkt trades replayed (at least 2,000 required)")


# ------------------------------------------------------------------ b: limit orders by hand
def _scalar_lim(ctx, ts, side, k):
    """One lim order from the bars alone, by timestamp: (filled, gross, net, next bar or None, exit bar)."""
    a = ctx.a
    dec = a.loc[ts]
    t1, tx = ts + pd.Timedelta(minutes=1), ts + pd.Timedelta(minutes=k)
    nxt = a.loc[t1] if t1 in a.index else None
    ex = a.loc[tx]
    limit = float(dec.close)
    if nxt is None:
        filled = False
    elif side > 0:
        filled = float(nxt.low) <= limit - 0.25
    else:
        filled = float(nxt.high) >= limit + 0.25
    gross = side * (float(ex.close) - limit) * 2.0
    net = side * ((float(ex.close) - side * 0.25) - limit) * 2.0 - 1.0 - 1.0
    return filled, gross, net, nxt, ex


def limits(ctx, P, names, seed=21, more=3000):
    print("\n(b) lim orders: a limit at the decision bar's close, filled only if the next 1-minute bar trades at least one"
          " tick through it\n    (long: next low <= limit - 0.25; short: next high >= limit + 0.25), at the limit, no slippage;"
          " out at the close k minutes after the decision, 1 tick against; $1 a side")
    rng = np.random.default_rng(seed)
    n_print = n_more = 0
    ok_all = True
    for nm in names:
        c = gs.parse(nm)
        o = gs.trades(P, nm, all_orders=True)
        f, u = np.flatnonzero(o.filled.to_numpy()), np.flatnonzero(~o.filled.to_numpy())
        sel = np.r_[rng.choice(f, size=min(3, len(f)), replace=False), rng.choice(u, size=min(2, len(u)), replace=False)].astype(int)
        print(f"  {nm}: {len(o)} orders, {len(f)} filled ({len(f) / max(len(o), 1):.1%})")
        for q in sorted(sel.tolist()):
            r = o.iloc[q]
            ts = r.sig_time
            filled, gross, net, nxt, ex = _scalar_lim(ctx, ts, int(r.side), c["K"])
            dec = ctx.a.loc[ts]
            need = f"low <= {dec.close - 0.25:.2f}" if r.side > 0 else f"high >= {dec.close + 0.25:.2f}"
            same = (filled == bool(r.filled)) and abs(gross - r.gross) < 1e-9 and (not filled or abs(net - r.net) < 0.005)
            ok_all &= same
            n_print += 1
            print(f"    {ts:%Y-%m-%d %H:%M} {'LONG ' if r.side > 0 else 'SHORT'} z {r.z:5.2f}  decision bar O {dec.open:.2f} H {dec.high:.2f}"
                  f" L {dec.low:.2f} C {dec.close:.2f} -> limit {dec.close:.2f}; next bar "
                  + (f"{nxt.name:%H:%M} O {nxt.open:.2f} H {nxt.high:.2f} L {nxt.low:.2f} C {nxt.close:.2f}" if nxt is not None else "MISSING")
                  + f"; needs {need}: {'FILLED' if r.filled else 'not filled'}"
                  + (f"; out {ex.name:%H:%M} close {ex.close:.2f}: gross ${r.gross:+.2f} net ${r.net:+.2f}" if r.filled else "")
                  + ("" if same else "   <-- DISAGREES with the scalar recomputation"))
        for q in rng.choice(len(o), size=min(more // len(names), len(o)), replace=False).tolist():
            r = o.iloc[q]
            filled, gross, net, _, _ = _scalar_lim(ctx, r.sig_time, int(r.side), c["K"])
            ok_all &= (filled == bool(r.filled)) and abs(gross - r.gross) < 1e-9 and (not filled or abs(net - r.net) < 0.005)
            n_more += 1
    check(ok_all, f"{n_print} printed lim orders and {n_more} more agree with the scalar recomputation from the bars")


# ------------------------------------------------------------------ c: the look-ahead test
COLS = ["day", "i", "x", "side", "z", "ref", "exit_px", "gross", "net", "unit"]


def _cut_ctx(A, T, d):
    """A context on the bars up to T. The harness reads a session cut short as an early close and would put its flat
    bar 10 minutes before the last bar; the cut day's flat bar is set to the last bar present, so that every decision
    whose exit is at or before the cut exists in the truncated run."""
    a = A[A.index <= T]
    c = core.Ctx(a)
    assert d in c.days.index, "the cut day has too few bars to be a session of the truncated day table"
    c.days.at[d, "i_last"] = len(a) - 1
    c.days.at[d, "i_end"] = len(a) - 1
    return c


def _trades_equal(P, Pc, nm, iT):
    f = gs.trades(P, nm)
    f = f[f.x <= iT][COLS].reset_index(drop=True)
    t = gs.trades(Pc, nm)[COLS].reset_index(drop=True)
    return len(f) == len(t) and f.equals(t), len(f)


def _signals_equal(P, Pc, iT):
    bad = []
    for g in gs.GS:
        s0, z0 = P.signal(g)
        s1, z1 = Pc.signal(g)
        if not (np.array_equal(s0[:iT + 1], s1[:iT + 1]) and np.array_equal(z0[:iT + 1], z1[:iT + 1], equal_nan=True)):
            bad.append(g)
    return bad


def lookahead(A, ctx, P, names, n_cuts=6, seed=7):
    print("\n(c) look-ahead: bars truncated at random mid-session times")
    D = ctx.days
    rng = np.random.default_rng(seed)
    full = np.flatnonzero(P.traded & (D.n_bars.to_numpy() == 390) & (np.arange(len(D)) > 40))
    cuts = []
    for q in sorted(rng.choice(full, size=min(n_cuts, len(full)), replace=False).tolist()):
        d = D.index[q]
        cuts.append((d, (d + pd.Timedelta(minutes=int(rng.integers(735, 931)))).tz_localize(core.TZ)))   # 12:15 .. 15:30
    orig = gs.Prep.signal

    def leak(shift):
        def f(self, G):
            s, z = orig(self, G)
            return np.roll(s, -shift), np.roll(z, -shift)
        return f

    for d, T in cuts:
        t0 = time.time()
        c = _cut_ctx(A, T, d)
        Pc = gs.Prep(c)
        iT = c.n - 1
        assert ctx.ts[iT] == T == c.ts[-1]
        n_tr, bad_tr = 0, []
        for nm in names:
            same, n = _trades_equal(P, Pc, nm, iT)
            n_tr += n
            if not same:
                bad_tr.append(nm)
        bad_sig = _signals_equal(P, Pc, iT)
        check(not bad_tr and not bad_sig,
              f"cut {T:%Y-%m-%d %H:%M}: {len(names)} combinations, {n_tr} trades exited by the cut identical"
              f"{'' if not bad_tr else ' EXCEPT ' + ', '.join(bad_tr)}; side and z of all 18 signals identical at every bar"
              f" up to the cut{'' if not bad_sig else ' EXCEPT ' + ', '.join(bad_sig)}   [{time.time() - t0:.0f}s]")
    # negative controls on the last cut: a signal that reads 1 bar ahead, and one that reads 31 bars ahead
    for shift in (1, 31):
        gs.Prep.signal = leak(shift)
        try:
            Pl, Plc = gs.Prep(ctx), gs.Prep(c)
            caught_tr = [nm for nm in names if not _trades_equal(Pl, Plc, nm, iT)[0]]
            caught_sig = _signals_equal(Pl, Plc, iT)
        finally:
            gs.Prep.signal = orig
        check(len(caught_sig) >= 12 and (shift == 1 or len(caught_tr) >= 1),
              f"negative control, every signal reading {shift} bar{'s' if shift > 1 else ''} ahead: the signal test fails"
              f" {len(caught_sig)} of {len(gs.GS)} signals; the exited-trades test alone fails {len(caught_tr)} of"
              f" {len(names)} combinations" + (" (a peek shorter than the holding time is inside every exited trade:"
                                               " that is why the signal test is run as well)" if shift == 1 else ""))


def mirrored(A, names, cuts=5):
    print("\n(c) the harness's mirrored-future test (core.causal_check) on the mkt orders")
    for nm in names:
        t0 = time.time()
        ok = core.causal_check(lambda cx: gs.orders(gs.Prep(cx), nm), A, n_samples=cuts, verbose=False)
        check(ok, f"{nm}: orders up to {cuts} sampled signal bars unchanged under a mirrored future   [{time.time() - t0:.0f}s]")


# ------------------------------------------------------------------ d: the slow reference
class Slow:
    """The spec text with plain loops. Sessions by the day table's dates and flat-bar minute, bars found by the
    harness's wall clock (ctx.idx), ES by a timestamp dictionary; no array of g12_sim is read."""

    def __init__(self, ctx):
        self.c = ctx
        D = ctx.days
        self.end = {np.datetime64(d, "D"): int(ctx.tod[int(e)]) for d, e in zip(D.index, D.i_end)}
        es = ctx.extra("ES")
        k = es.index.asi8.tolist()
        self.esc, self.esi = dict(zip(k, es.close.to_numpy(float).tolist())), dict(zip(k, es.instrument_id.to_numpy().tolist()))
        self.ns = ctx.ts.asi8

    def insess(self, b):
        e = self.end.get(self.c.cdate[b])
        return e is not None and 570 <= self.c.tod[b] <= e

    def window(self, i_last, n=gs.WIN + 420):
        """Bars with an in-session 1-minute return, latest first, from i_last back."""
        c, out, b = self.c, [], i_last
        while b >= 1 and len(out) < n:
            if (self.insess(b) and self.insess(b - 1) and c.cdate[b] == c.cdate[b - 1] and c.tod[b] - c.tod[b - 1] == 1
                    and c.iid[b] == c.iid[b - 1]):
                out.append(b)
            b -= 1
        return out

    def s_at(self, lst, i, es):
        w = [b for b in lst if b <= i][:gs.WIN]
        if len(w) < gs.WIN:
            return None
        C, ns = self.c.C, self.ns
        r = [math.log(C[b] / C[b - 1]) for b in w]
        if not es:
            return float(np.std(r))
        dd = []
        for b, rb in zip(w, r):
            e1, e0 = self.esc.get(ns[b]), self.esc.get(ns[b - 1])
            if e1 is None or e0 is None or self.esi[ns[b]] != self.esi[ns[b - 1]]:
                continue
            dd.append(math.log(e1 / e0) - rb)
        return float(np.std(dd)) if len(dd) >= 2 else None

    def sig(self, G, d, minute, i, lst):
        """(side, z) at the close of bar i (stamped `minute` on day d); z None when it cannot be computed."""
        ctx = self.c
        C = ctx.C
        f, L = gs.split(G)
        flip = -1 if f in ("rev", "esr", "vwr") else 1
        if L is None:
            a = ctx.idx(d, 570)
            sv = spv = sp2 = 0.0
            for b in range(a, i + 1):
                tp = (ctx.H[b] + ctx.L[b] + C[b]) / 3
                sv += ctx.V[b]; spv += tp * ctx.V[b]; sp2 += tp * tp * ctx.V[b]
            vw = spv / sv
            sd = math.sqrt(max(sp2 / sv - vw * vw, 0.0))
            x = C[i] - vw
            z = abs(x) / sd if sd > 0 else (math.inf if x != 0 else None)
        else:
            j = ctx.idx(d, minute - L)
            if j is None or ctx.iid[j] != ctx.iid[i]:
                return 0, None
            if f in ("mom", "rev"):
                x = C[i] - C[j]
                s = self.s_at(lst, i, False)
                z = None if s is None else abs(math.log(C[i] / C[j])) / (s * math.sqrt(L))
            else:
                ei, ej = self.esc.get(self.ns[i]), self.esc.get(self.ns[j])
                if ei is None or ej is None or self.esi[self.ns[i]] != self.esi[self.ns[j]]:
                    return 0, None
                x = math.log(ei / ej) - math.log(C[i] / C[j])
                s = self.s_at(lst, i, True)
                z = None if s is None else (abs(x) / (s * math.sqrt(L)) if s > 0 else (math.inf if x != 0 else None))
        side = int(x > 0) - int(x < 0)
        return flip * side, (z if side else None)

    def day_trades(self, nm, d):
        """[(i, x, side, z, gross, net)] of combination nm on cash day d."""
        ctx = self.c
        c = gs.parse(nm)
        row = ctx.days.loc[d]
        if bool(row.roll) or not (row.atr == row.atr):
            return []
        k, Z = c["K"], c["Z"]
        flat = int(ctx.tod[int(row.i_end)])
        lst = self.window(int(row.i_end))
        out, minute = [], 599
        while minute + k <= flat:
            m, minute = minute, minute + k
            i, x = ctx.idx(d, m), ctx.idx(d, m + k)
            if i is None or x is None:
                continue
            side, z = self.sig(c["G"], d, m, i, lst)
            if side == 0 or z is None or not (z >= Z):
                continue
            gross = side * (ctx.C[x] - ctx.C[i]) * 2.0
            if c["E"] == "mkt":
                net = side * ((ctx.C[x] - side * 0.25) - (ctx.C[i] + side * 0.25)) * 2.0 - 2.0
            else:
                n1 = ctx.idx(d, m + 1)
                if n1 is None or not (ctx.L[n1] <= ctx.C[i] - 0.25 if side > 0 else ctx.H[n1] >= ctx.C[i] + 0.25):
                    continue
                net = side * ((ctx.C[x] - side * 0.25) - ctx.C[i]) * 2.0 - 2.0
            out.append((int(i), int(x), int(side), float(z), float(gross), float(net)))
        return out


def slow(ctx, P, names, n_days=12, seed=31):
    print("\n(d) whole days re-derived with plain loops from the spec text")
    D = ctx.days
    S = Slow(ctx)
    rng = np.random.default_rng(seed)
    tr = np.flatnonzero(P.traded)
    special = []
    for m, lab in ((P.traded & D.early.to_numpy(bool), "early close"),
                   (P.traded & ~D.early.to_numpy(bool) & (D.n_bars.to_numpy() < 390), "missing minutes"),
                   (D.roll.to_numpy(bool), "roll day"), (np.isnan(P.atr), "no ATR")):
        q = np.flatnonzero(m)
        if len(q):
            special.append((int(q[len(q) // 2]), lab))
    # the session after an ES minute is missing inside a session (s_d leaves that minute out)
    es_t = set(ctx.extra("ES").index.asi8.tolist())
    miss = [b for b, t in zip(np.flatnonzero(P.sess >= 0).tolist(), ctx.ts.asi8[P.sess >= 0].tolist()) if t not in es_t][:1]
    for b in miss:
        q = int(P.sess[b])
        special += [(q, "an ES minute missing")] + ([(q + 1, "the session after an ES minute is missing")] if q + 1 < len(D) else [])
    for nm in names:
        t0 = time.time()
        rows = [(int(q), "") for q in sorted(rng.choice(tr, size=min(n_days, len(tr)), replace=False).tolist())] + special
        fast = gs.trades(P, nm)
        fday = fast.day.to_numpy().astype("datetime64[D]")
        n, zmax, bad = 0, 0.0, []
        for q, lab in rows:
            d = D.index[q]
            ref = S.day_trades(nm, d)
            f = fast[fday == P.day[q]]
            same = len(ref) == len(f)
            if same and len(ref):
                r = np.array(ref)
                same = (np.array_equal(r[:, 0].astype(int), f.i.to_numpy()) and np.array_equal(r[:, 1].astype(int), f.x.to_numpy())
                        and np.array_equal(r[:, 2].astype(int), f.side.to_numpy()) and np.allclose(r[:, 4], f.gross.to_numpy(), atol=1e-9)
                        and np.allclose(r[:, 5], f.net.to_numpy(), atol=1e-9))
                fin = np.isfinite(r[:, 3]) & np.isfinite(f.z.to_numpy()) if same else None
                if same:
                    same = np.array_equal(np.isfinite(r[:, 3]), np.isfinite(f.z.to_numpy())) and \
                        np.allclose(r[fin, 3], f.z.to_numpy()[fin], rtol=1e-7, atol=1e-10)
                    zmax = max(zmax, float(np.abs(r[fin, 3] - f.z.to_numpy()[fin]).max()) if fin.any() else 0.0)
            n += len(ref)
            if not same:
                bad.append(f"{d.date()}{' (' + lab + ')' if lab else ''}: slow {len(ref)} fast {len(f)}")
        check(not bad, f"{nm:<20} {len(rows)} days ({', '.join(dict.fromkeys(l for _, l in rows if l)) or 'random'}"
                       f"{' + ' + str(n_days) + ' random' if special else ''}): {n} trades identical, largest z difference"
                       f" {zmax:.1e}{'' if not bad else '  MISMATCH ' + '; '.join(bad)}   [{time.time() - t0:.0f}s]")


# ------------------------------------------------------------------ e: the grid row from the trade list
def grid_rows(ctx, P, pk, n_rand=24, seed=41):
    print("\n(e) grid rows recomputed with pandas from the trade lists; the selection recomputed from the grid file")
    import g12_grid as gg
    table, _ = gg.evaluate(P)
    rng = np.random.default_rng(seed)
    all_ = [gs.name(c) for c in gs.combos()]
    names = uniq(pk + [all_[q] for q in sorted(rng.choice(len(all_), size=n_rand, replace=False).tolist())])
    D = ctx.days
    bad, worst = [], 0.0
    for nm in names:
        c = gs.parse(nm)
        df = gs.trades(P, nm)
        sess = pd.DatetimeIndex(D.index[gs.sessions(P, c["K"])])
        S = len(sess)
        dn = df.groupby("day").net.sum().reindex(sess, fill_value=0.0)
        du = (df.gross / df.unit).groupby(df.day).sum().reindex(sess, fill_value=0.0)
        mine = {"n": len(df), "sessions": S, "tpd": len(df) / S, "gross_pt": df.gross.mean(), "gross_pts": df.gross.mean() / 2,
                "net_pt": df.net.mean(), "net_day": df.net.sum() / S, "net": df.net.sum(), "gross": df.gross.sum(),
                "t": du.mean() / (du.std(ddof=1) / math.sqrt(S)) if du.std(ddof=1) > 0 else float("nan"),
                "win": (df.net > 0).mean() * 100, "dd": float((dn.cumsum() - dn.cumsum().cummax().clip(lower=0)).min()),
                "days": df.day.nunique()}
        for y, v in df.groupby(df.day.dt.year).net.sum().items():
            mine[f"y{y}"] = v
        row = table.loc[nm]
        for k, v in mine.items():
            a, b = float(row[k]), float(v)
            if a != a and b != b:
                continue
            err = abs(a - b) / max(1.0, abs(b))
            worst = max(worst, err)
            if not err < 1e-9:
                bad.append(f"{nm}.{k}: grid {a} trades {b}")
    check(not bad, f"{len(names)} combinations ({len(pk)} picks + {n_rand} random): every column of the grid row equals the"
                   f" pandas recomputation (largest relative difference {worst:.1e})" + ("" if not bad else "  " + "; ".join(bad[:5])))
    p, g = core.OUT / "G12_selected.json", core.OUT / "is" / "G12_grid.csv"
    if p.exists() and g.exists():
        sel = json.loads(p.read_text())
        f = pd.read_csv(g, index_col="name")
        same = bool((f.n.to_numpy() == table.n.to_numpy()).all() and np.allclose(f.net.to_numpy(), table.net.to_numpy(), atol=0.005)) \
            if ctx.ts[-1] < core.IS_END else None
        want = []
        for tier, lo, hi in (("A", 100, np.inf), ("B", 30, 100), ("C", 10, 30)):
            sub = f[(f.tpd >= lo) & (f.tpd < hi)]
            if not len(sub) or sub.t.notna().sum() == 0:
                continue
            p1 = sub.t.idxmax()
            want.append((f"{tier}1", p1))
            p2 = sub.net_day.idxmax()
            if p2 not in (p1, gs.mirror(p1)):
                want.append((f"{tier}2", p2))
        got = [(r["id"], r["name"]) for r in sel["picks"]]
        check(want == got and same is not False,
              f"the picks of G12_selected.json are the ones the frozen grid file gives: {', '.join(f'{a} {b}' for a, b in got)}"
              + ("" if same is None else f"; the frozen grid file equals a fresh evaluation: {same}"))
    else:
        print("  (no selection file yet: the selection is not rechecked)")


# ------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", choices=["is", "full"], default="is")
    ap.add_argument("--parts", default="abcde")
    a = ap.parse_args()
    pd.set_option("display.width", 250)
    t0 = time.time()
    A = run.bars(a.phase)
    ctx = core.Ctx(A)
    P = gs.prep(ctx)
    pk = picks()
    print(f"G12 verify   phase {a.phase}   bars {ctx.ts[0]} -> {ctx.ts[-1]}   traded days {int(P.traded.sum())}"
          f"   frozen picks: {', '.join(pk) if pk else 'none yet'}")
    all_ = gs.combos()
    check(len(all_) == gs.N_GRID and len({gs.name(c) for c in all_}) == gs.N_GRID
          and all(gs.parse(gs.name(c)) == c for c in all_) and all(gs.mirror(gs.mirror(gs.name(c))) == gs.name(c) for c in all_),
          f"{len(all_)} combinations, names unique and parse back, mirror of mirror is itself")
    check([int(np.bincount(P.decisions(k).d).max()) for k in gs.KS] == [360, 180, 120, 72, 36, 24, 12],
          "decisions on a full session: " + ", ".join(f"k{k} {int(np.bincount(P.decisions(k).d).max())}" for k in gs.KS)
          + " (the spec: 360, 180, 120, 72, 36, 24, 12)")
    if "a" in a.parts:
        replay(ctx, P, uniq(MKT6 + [as_mkt(x) for x in pk]))
    if "b" in a.parts:
        limits(ctx, P, LIM6)
    if "c" in a.parts:
        lookahead(A, ctx, P, uniq(LOOK6 + pk))
        mirrored(A, CAUSAL3)
    if "d" in a.parts:
        slow(ctx, P, uniq(SLOW9 + pk))
    if "e" in a.parts:
        grid_rows(ctx, P, pk)
    print(f"\ntotal {time.time() - t0:.0f}s")
    if BAD:
        print(f"FAIL  {len(BAD)} check(s) failed: " + " | ".join(BAD)[:600])
        sys.exit(1)
    print(f"PASS  G12 verification, parts {a.parts}: every check agreed")


if __name__ == "__main__":
    main()
