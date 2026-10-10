#!/usr/bin/env python3
"""LEV1 events (YT9_SPEC.md): the first tap of every level after the open, scored through core.simulate.

    events(ctx, lv=None, at_open=True, score=True, procs=1)
        one row per level-day of a study day (dropped placebos and never-watched levels left out):
        p0        price at the start of the watch = the open of the first watched bar w0 (at_open=False: the last close
                  before it, see lev1_levels.pstart)
        side      'R' resistance (level above p0) / 'S' support (below); fixed here and never changed
        skipped   within 0.04 x ATR of p0: not watched that day (no tap, no cluster, no event)
        px        the order price: the level on the tick grid, rounded towards the side price comes from
                  (R up, S down), i.e. the first tick at which "high >= level" / "low <= level" is true
        cluster   real static levels with the same watch start, same side, chained while neighbours are within
                  0.03 x ATR: cid, cl_codes (sorted codes joined by '+'), cl_n. lead = nearest to p0 (every level
                  tied at that price is a lead); first_lead = the lead that comes first in lev1_levels.ORDER (one row
                  per cluster). Placebos, expected-move bands and VWAP bands are always alone.
        is_event  the row is a first-tap event: a lead of a real static cluster, or a placebo / block / moving level
        tapped, tap, tap_time, bucket   first 1-minute bar of w0..w1 whose high >= px (R) / low <= px (S); for a
                  moving level px is the value in force during that bar (lev1_levels.moving_values)
        dist_open |level - 09:30 open| / ATR          away30, thru30   largest move away from / through the level
                  from the tap to 30 minutes after it, in ATR (away: tap bar's close and later bars' extremes;
                  through: every bar from the tap bar on)
        for each variant v in VARIANTS (9 fades '<stop>x<k>', 3 breaks 'brk_<stop>'):
                  f_v (filled), R_v, pnl_v, win_v (target reached), why_v (exit reason)
        nofill    variants of a tapped event that core.simulate did not fill; jbad = filled on another bar than `tap`
        ghost     an untapped event whose resting headline order filled (must be 0)
    order_of / orders_of     the core.simulate keyword arguments of an event's order(s); s_L1 uses the same functions

Orders. Static and block levels: one resting order from the bar before w0 (i = w0 - 1, so it rests during w0) to w1.
Moving levels: at the close of every bar k - 1 (k = w0 .. w1, until the first fill) a one-bar order (expire = k) at
the value in force during bar k. Fade = limit against the move, stop d beyond the level, target k x d the other way.
Break = stop order with the move at the same price, stop d on the other side, target 3 x d. d: p20 = 20 points,
a04 / a08 = 0.04 / 0.08 x ATR rounded to the tick, at least 2 ticks. Flat at the day's flat bar.

    python3 tools/yt1/lev1_events.py --sample 40          time the simulate calls on 40 days
    python3 tools/yt1/lev1_events.py --phase is           writes data/studies/yt1/is/LEV1_levels.parquet, LEV1_events.parquet
    python3 tools/yt1/lev1_events.py --phase full         the same on every bar (refuses if there are no later bars)
"""
import argparse, pathlib, sys, time
import numpy as np
import pandas as pd
sys.path.insert(0, str(pathlib.Path(__file__).parent))
import core
import lev1_levels as LL

TICK = core.TICK
SKIP = 0.04                                   # a level within this x ATR of p0 is not watched
STOPS = ("p20", "a04", "a08")
KS = (1, 2, 3)
FADES = [f"{s}x{k}" for s in STOPS for k in KS]
BREAKS = [f"brk_{s}" for s in STOPS]
VARIANTS = FADES + BREAKS
HEAD = "a04x3"
BUCKETS = ("0930", "1000", "1130")            # 09:30-09:59, 10:00-11:29, 11:30-15:00


def stop_pts(atr):
    return {"p20": 20.0, "a04": max(core.tick_round(0.04 * atr), 2 * TICK), "a08": max(core.tick_round(0.08 * atr), 2 * TICK)}


def stop_of(variant):
    return variant[4:] if variant.startswith("brk_") else variant.split("x")[0]


def order_of(i, side, px, d, variant, expire, exit_i):
    """side: +1 the level is resistance, -1 support. Fade: short at resistance / long at support (limit).
    Break: long through resistance / short through support (stop order)."""
    if variant.startswith("brk_"):
        s = side
        return dict(i=int(i), side=s, etype="stop", price=float(px), expire=int(expire), stop=float(px - s * d),
                    target=float(px + s * 3 * d), exit_i=int(exit_i))
    s, k = -side, int(variant.split("x")[1])
    return dict(i=int(i), side=s, etype="limit", price=float(px), expire=int(expire), stop=float(px - s * d),
                target=float(px + s * k * d), exit_i=int(exit_i))


def px_grid(value, side):
    """The level on the tick grid: up for resistance, down for support (arrays or scalars)."""
    q = np.asarray(value, float) / TICK
    return np.where(np.asarray(side) > 0, np.ceil(q - 1e-9), np.floor(q + 1e-9)) * TICK


def moving_px(ctx, code, side):
    """Order price of a moving level for every 1-minute bar (the value in force during the bar, on the tick grid)."""
    c = ctx.__dict__.setdefault("_lev1", {})
    k = ("mpx", code, side)
    if k not in c:
        c[k] = px_grid(LL.moving_values(ctx)[code], side)
    return c[k]


def orders_of(ctx, r, variant, d=None):
    """Every order of event row r (a row of events()) under `variant`: one resting order for a static / block
    level; for a moving level the one-bar orders placed until the first tap (all of them when it is never tapped).
    Each order is built from bars up to its own `i` (plus, for the first bar of a watch, what p0 read)."""
    side = 1 if r.side == "R" else -1
    d = stop_pts(r.atr)[stop_of(variant)] if d is None else d
    if r.kind != "moving":
        return [order_of(int(r.w0) - 1, side, r.px, d, variant, int(r.w1), int(r.exit_i))]
    pxa = moving_px(ctx, r.code, side)
    last = int(r.tap) if r.tapped else int(r.w1)
    return [order_of(k - 1, side, pxa[k], d, variant, k, int(r.exit_i)) for k in range(int(r.w0), last + 1)]


COLS = ["date", "code", "inst", "lid", "group", "kind", "is_placebo", "parent", "value", "px", "atr", "t_set", "w0",
        "w1", "exit_i", "p0", "side", "skipped", "used", "fresh", "near_later", "cid", "cl_codes", "cl_n", "lead",
        "first_lead", "is_event", "tapped", "tap", "tap_time", "bucket", "dist_open", "away30", "thru30",
        "d_p20", "d_a04", "d_a08", "nofill", "jbad", "ghost"]
VCOLS = [f"{w}_{v}" for v in VARIANTS for w in ("f", "R", "pnl", "win", "why")]


def _score(ctx, kind, side, w0, w1, px, tap, dist, exit_i, pxa):
    """12 variants of one event through core.simulate. Returns (values in VCOLS order, nofill, jbad, ghost)."""
    sim = core.simulate
    if tap < 0:                                           # never tapped: the headline order must not fill
        if kind == "moving":
            ghost = any(sim(ctx, **order_of(k - 1, side, pxa[k], dist["a04"], HEAD, k, exit_i)) is not None
                        for k in range(w0, w1 + 1))
        else:
            ghost = sim(ctx, **order_of(w0 - 1, side, px, dist["a04"], HEAD, w1, exit_i)) is not None
        return None, 0, 0, bool(ghost)
    ghost = False
    if kind == "moving":
        i, expire, p = tap - 1, tap, pxa[tap]
        ghost = any(sim(ctx, **order_of(k - 1, side, pxa[k], dist["a04"], HEAD, k, exit_i)) is not None
                    for k in range(w0, tap))             # the earlier one-bar orders must not fill
    else:
        i, expire, p = w0 - 1, w1, px
    vals, nofill, jbad = [], 0, 0
    for v in VARIANTS:
        t = sim(ctx, **order_of(i, side, p, dist[stop_of(v)], v, expire, exit_i))
        if t is None:
            nofill += 1
            vals += [False, np.nan, np.nan, False, ""]
        else:
            jbad += int(t["j"] != tap)
            vals += [True, t["R"], t["pnl"], t["reason"] == "TP", t["reason"]]
    return vals, nofill, jbad, bool(ghost)


def _days(ctx, PS, lvd, days, score):
    """Event rows of the given study days. lvd: {date: frame of that day's level rows}."""
    O, H, L, C = ctx.O, ctx.H, ctx.L, ctx.C
    ts, tod = ctx.ts, ctx.tod
    tns = ts.asi8
    m30 = pd.Timedelta(minutes=30).as_unit(ts.unit).value
    D = ctx.days
    d_atr, d_open, d_end = (dict(zip(D.index, D[k].to_numpy())) for k in ("atr", "i_open", "i_end"))
    mv = LL.moving_values(ctx)
    out = []
    for d in days:
        x = lvd.get(d)
        if x is None:
            continue
        atr, i_open, exit_i = float(d_atr[d]), int(d_open[d]), int(d_end[d])
        o930 = O[i_open]
        dist = stop_pts(atr)
        n = len(x)
        code, kind, inst, lid = x.code.to_numpy(), x.kind.to_numpy(), x.inst.to_numpy(), x.lid.to_numpy()
        grp_, par_, tset_ = x.group.to_numpy(), x.parent.to_numpy(), x.t_set.to_numpy()
        used_, later_ = x.used.to_numpy(), x.near_later.to_numpy()
        val, w0, w1 = x.value.to_numpy(float), x.w0.to_numpy(), x.w1.to_numpy()
        plc = x.is_placebo.to_numpy()
        p0 = PS[w0]
        side = np.where(val > p0, 1, np.where(val < p0, -1, 0))
        skipped = ~(np.abs(val - p0) > SKIP * atr)             # within 0.04 x ATR (or no p0)
        px = px_grid(val, side)
        # ---- clusters among watched real static levels with the same watch start and side
        cid = np.array([""] * n, dtype=object)
        cl_codes = code.astype(object).copy()
        cl_n = np.ones(n, int)
        lead = np.ones(n, bool)
        first_lead = np.ones(n, bool)
        rs = np.flatnonzero((kind == "static") & ~plc & ~skipped)
        near = LL.NEAR * atr
        for key in sorted({(int(w0[k]), int(side[k])) for k in rs}):
            m = rs[(w0[rs] == key[0]) & (side[rs] == key[1])]
            m = m[np.argsort(val[m], kind="mergesort")]
            cut = np.flatnonzero(np.diff(val[m]) > near) + 1
            for q, grp in enumerate(np.split(m, cut)):
                c_id = f"{d.strftime('%Y%m%d')}.{'R' if key[1] > 0 else 'S'}.{key[0] - i_open}.{q}"
                gap = np.abs(val[grp] - p0[grp])
                is_lead = gap == gap.min()
                first = min(grp[is_lead], key=lambda k: (LL.RANK[code[k]], inst[k]))
                names = "+".join(sorted(code[grp]))
                for k, ld in zip(grp, is_lead):
                    cid[k], cl_codes[k], cl_n[k], lead[k], first_lead[k] = c_id, names, len(grp), ld, k == first
        # ---- taps and scores
        memo = {}
        for k in range(n):
            s = int(side[k])
            moving = kind[k] == "moving"
            is_static_real = kind[k] == "static" and not plc[k]
            a, b = int(w0[k]), int(w1[k])
            tap, pxk, pxa = -1, float(px[k]), None
            if not skipped[k]:
                if moving:
                    pxa = moving_px(ctx, code[k], s)
                    hit = (H[a:b + 1] >= pxa[a:b + 1]) if s > 0 else (L[a:b + 1] <= pxa[a:b + 1])
                else:
                    hit = (H[a:b + 1] >= pxk) if s > 0 else (L[a:b + 1] <= pxk)
                if hit.any():
                    tap = a + int(np.argmax(hit))
                    if moving:
                        pxk = float(pxa[tap])
            is_event = bool(not skipped[k] and (lead[k] if is_static_real else True))
            tapped = tap >= 0
            away = thru = np.nan
            bucket, tap_time = "", pd.NaT
            lvl = float(val[k]) if not moving else (float(mv[code[k]][tap]) if tapped else float(val[k]))
            dopen = abs(lvl - o930) / atr
            if tapped:
                e = min(int(np.searchsorted(tns, tns[tap] + m30, "right")) - 1, exit_i)
                if s > 0:
                    thru = max(H[tap:e + 1].max() - lvl, 0.0) / atr
                    away = max(lvl - min(C[tap], L[tap + 1:e + 1].min() if e > tap else C[tap]), 0.0) / atr
                else:
                    thru = max(lvl - L[tap:e + 1].min(), 0.0) / atr
                    away = max(max(C[tap], H[tap + 1:e + 1].max() if e > tap else C[tap]) - lvl, 0.0) / atr
                t_ = int(tod[tap])
                bucket = BUCKETS[0] if t_ < 600 else BUCKETS[1] if t_ < 690 else BUCKETS[2]
                tap_time = ts[tap]
            vals, nofill, jbad, ghost = None, 0, 0, False
            if score and is_event:
                mk = (code[k] if moving else "", s, a, b, None if moving else pxk)
                if mk not in memo:
                    memo[mk] = _score(ctx, kind[k], s, a, b, pxk, tap, dist, exit_i, pxa)
                vals, nofill, jbad, ghost = memo[mk]
            if vals is None:
                vals = [False, np.nan, np.nan, False, ""] * len(VARIANTS)
            out.append([d, code[k], inst[k], lid[k], grp_[k], kind[k], bool(plc[k]), par_[k], float(val[k]), pxk, atr,
                        int(tset_[k]), a, b, exit_i, float(p0[k]), "R" if s > 0 else "S" if s < 0 else "",
                        bool(skipped[k]), bool(used_[k]), bool(not used_[k]), bool(later_[k]), cid[k], cl_codes[k],
                        int(cl_n[k]), bool(lead[k]), bool(first_lead[k]), is_event, tapped, tap, tap_time, bucket,
                        dopen, away, thru, dist["p20"], dist["a04"], dist["a08"], nofill, jbad, ghost] + list(vals))
    return out


_FORK = {}


def _worker(span):
    ctx, PS, lvd, days, score = _FORK["a"]
    return _days(ctx, PS, lvd, days[span[0]:span[1]], score)


def need(sel):
    """Which level rows an event selection needs: a real static code or a pair needs every real static level (the
    clusters); a placebo, expected-move or VWAP code only its own rows."""
    if "+" in sel:
        return "static"
    code = sel.split(":")[0]
    return "static" if code in LL.STATIC else code


def events(ctx, lv=None, at_open=True, score=True, procs=1, only=None):
    """only: None = every level; 'static' = the real static levels; a code = that code's rows (see need())."""
    c = ctx.__dict__.setdefault("_lev1", {})
    key = ("events", bool(at_open), bool(score), only)
    if lv is None and key in c:
        return c[key]
    cache = lv is None
    if lv is None:
        lv = LL.levels(ctx, at_open)
    PS = LL.pstart(ctx, at_open)
    days = LL.ok_days(ctx)
    x = lv[~lv.dropped & (lv.w0 <= lv.w1) & lv.date.isin(set(days))]
    if only == "static":
        x = x[(x.kind == "static") & ~x.is_placebo]
    elif only is not None:
        x = x[x.code == only]
    lvd = {d: g for d, g in x.groupby("date", sort=False)}
    if procs > 1 and len(days) > 40:
        import multiprocessing as mp
        w = np.cumsum([len(lvd[d]) if d in lvd else 0 for d in days])
        cuts = [0] + [int(np.searchsorted(w, w[-1] * a / procs)) for a in range(1, procs)] + [len(days)]
        _FORK["a"] = (ctx, PS, lvd, days, score)
        with mp.get_context("fork").Pool(procs) as pool:
            parts = pool.map(_worker, [(cuts[a], cuts[a + 1]) for a in range(procs)])
        _FORK.clear()
        rows = [r for p in parts for r in p]
    else:
        rows = _days(ctx, PS, lvd, days, score)
    ev = pd.DataFrame(rows, columns=COLS + VCOLS)
    for v in VARIANTS:
        ev[f"f_{v}"] = ev[f"f_{v}"].astype(bool)
        ev[f"win_{v}"] = ev[f"win_{v}"].astype(bool)
    if cache:
        c[key] = ev
    return ev


def report(ev):
    """Counts and the fill-bar-equals-tap-bar check."""
    out = []
    nd = ev.date.nunique()
    w = ev[~ev.skipped]
    e = ev[ev.is_event]
    t = e[e.tapped]
    out.append(f"study days {nd}; level-days {len(ev)}; skipped near the start price {int(ev.skipped.sum())}; watched "
               f"{len(w)}; events (cluster leads, placebos, block and moving levels) {len(e)}; tapped {len(t)} "
               f"({len(t) / max(len(e), 1):.1%}); fresh among tapped {int(t.fresh.sum())} ({t.fresh.mean():.1%})")
    for nm, m in (("real static", (e.kind == "static") & ~e.is_placebo), ("placebo", e.is_placebo),
                  ("expected move", e.kind == "block"), ("VWAP bands", e.kind == "moving")):
        q = e[m]
        qt = q[q.tapped]
        out.append(f"  {nm:<14} events {len(q):>6}  tapped {len(qt):>6} ({len(qt) / max(len(q), 1):.1%})  fresh events "
                   f"{int(q.fresh.sum()):>6}  fresh tapped {int(qt.fresh.sum()):>6}")
    rs = w[(w.kind == "static") & ~w.is_placebo]
    one = rs[rs.first_lead]
    out.append(f"real static: watched level-days {len(rs)}, clusters {len(one)} (1 level {int((one.cl_n == 1).sum())}, "
               f"2 levels {int((one.cl_n == 2).sum())}, 3 or more {int((one.cl_n >= 3).sum())}); lead rows {int(rs.lead.sum())} "
               f"(of which tied leads beyond the first {int((rs.lead & ~rs.first_lead).sum())}); member rows that are not "
               f"leads {int((~rs.lead).sum())}")
    nv = len(VARIANTS)
    out.append(f"fill bar = tap bar: {len(t)} tapped events x {nv} variants = {len(t) * nv} orders; filled on the tap bar "
               f"{int(sum(t[f'f_{v}'].sum() for v in VARIANTS) - t.jbad.sum())}; filled on another bar {int(t.jbad.sum())}; "
               f"not filled {int(t.nofill.sum())} (events with at least one unfilled variant: {int((t.nofill > 0).sum())}); "
               f"untapped events whose resting headline order filled: {int(e.ghost.sum())} of {int((~e.tapped).sum())}")
    nf = t[t.nofill > 0]
    if len(nf):
        by = {v: int((~nf[f"f_{v}"]).sum()) for v in VARIANTS}
        out.append(f"  not filled by variant: {by}")
    return out


def main():
    import run
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", choices=["is", "full"], default="is")
    ap.add_argument("--procs", type=int, default=2)
    ap.add_argument("--sample", type=int, default=0, help="time the simulate calls on this many days and stop")
    a = ap.parse_args()
    assert 1 <= a.procs <= 2, "at most 2 worker processes"
    t00 = time.time()
    A = run.bars(a.phase)
    if a.phase == "full" and A.index.max() < core.IS_END:
        raise SystemExit("no bars after 2022-12-31 in this data directory: the full phase cannot run here")
    ctx = core.Ctx(A)
    lv = LL.levels(ctx)
    t_lv = time.time() - t00
    if a.sample:
        days = LL.ok_days(ctx)
        pick = sorted(np.random.default_rng(1).choice(len(days), a.sample, replace=False))
        sub = lv[lv.date.isin({days[k] for k in pick})]
        t0 = time.time()
        ev = events(ctx, sub, score=False)
        t1 = time.time()
        ev2 = events(ctx, sub, score=True)
        t2 = time.time()
        e = ev2[ev2.is_event]
        print(f"sample of {a.sample} days: {len(ev)} level-days, {len(e)} events, {int(e.tapped.sum())} tapped; "
              f"without scores {t1 - t0:.1f}s, with scores {t2 - t1:.1f}s -> about "
              f"{(t2 - t1) / a.sample * len(days):.0f}s for {len(days)} days in one process")
        return
    t0 = time.time()
    ev = events(ctx, lv, procs=a.procs)
    t_ev = time.time() - t0
    d = core.OUT / a.phase
    d.mkdir(parents=True, exist_ok=True)
    lvo = lv.copy()
    lvo["study_day"] = lvo.date.isin(set(LL.ok_days(ctx)))
    lvo.to_parquet(d / "LEV1_levels.parquet", index=False)
    ev.to_parquet(d / "LEV1_events.parquet", index=False)
    print(f"LEV1 events   phase {a.phase}   bars {A.index[0]} -> {A.index[-1]}   levels {len(lv)} rows [{t_lv:.0f}s]   "
          f"events {len(ev)} rows [{t_ev:.0f}s, {a.procs} process(es)]")
    for line in LL.counts(ctx):
        print(line)
    for line in report(ev):
        print(line)
    print(f"wrote {d / 'LEV1_levels.parquet'} and {d / 'LEV1_events.parquet'}   total {time.time() - t00:.0f}s")


if __name__ == "__main__":
    main()
