#!/usr/bin/env python3
"""LEV2 events (YT10_SPEC.md): the first tap of every MID1 / VPN1 level after the open, each level scored on its own
through core.simulate, plus the aligned-value day types with the VA-trend trade and ORB v1.4 by day.

    events(ctx, study, at_open=True, score=True, procs=1, profs=None, codes=None)
        study 'mid' (lev2_levels.mid_levels) or 'vp' (lev2_levels.vp_levels). One row per level-day of a study day
        (dropped placebos left out). No clusters, no "fresh" requirement: every row that is not skipped is an event.
        p0        the 09:30 open (at_open=False: the last close before it, the form the look-ahead test compares)
        side      'S' support (level below p0) / 'R' resistance (above); skipped = within 0.04 x ATR of p0
        px        the order price: the level on the tick grid, R up / S down (lev1_events.px_grid)
        tapped, tap, tap_time, bucket     first 1-minute bar of 09:30 .. 15:00 with high >= px (R) / low <= px (S)
        dist_open |level - p0| / ATR; dbucket = its registered distance bucket (measured before the skip rule)
        crossed   price traded through the level between its set time and 09:29 (lev2_levels; a split, not a filter)
        stack     VPN1 real profile levels: the number of OTHER profiles (of the 13) with any of their three levels
                  within 0.03 x ATR of this level; sbucket '0' / '1' / '2' / '3+'   (-1 / '' elsewhere)
        bias, bias_rel   tt.bias of the day; 'with' = the fade is in the bias direction (support on a bullish day,
                  resistance on a bearish day), 'against', 'none' (no bias)
        away30, thru30   as lev1_events
        for each variant v of VARIANTS (lev1's 9 fades '<stop>x<k>' and 3 breaks 'brk_<stop>', and 'brk_a04x2' = the
                  break with a 2R target, the a04 x 2R neighbour of a break pick): f_v, R_v, pnl_v, win_v, why_v
        nofill, jbad, ghost   as lev1_events (unfilled variants of a tapped event; fills on another bar than the tap;
                  an untapped event whose resting headline order filled)
    orders_of(r, variant)     the core.simulate keyword arguments of an event row's order (s_L2 uses the same)
    va_orders(ctx, which)     the VA-trend orders: which = 'rth' (the rule), 'eth', 'rth3' (its two neighbours)
    daytypes(ctx)             lev2_levels.day_types + the 09:30 -> flat-bar move, the three VA-trend trades and the
                              day's ORB v1.4 trade (cal_orb inside the harness)

Orders, as lev1_events: one resting order per event from the bar before 09:30 (i = w0 - 1) to the 15:00 bar. Fade =
limit against the tap, stop d beyond the level, target k x d. Break = stop order with the move, stop d on the other
side, target 3 x d (2 x d for brk_a04x2). d: p20 = 20 points, a04 / a08 = 0.04 / 0.08 x ATR on the tick grid, at
least 2 ticks. Flat at the day's flat bar.

    python3 tools/yt1/lev2_events.py --phase is [--study mid|vp|all] [--procs 2]
        writes data/studies/yt1/is/MID1_events.parquet, VPN1_events.parquet, VPN1_daytypes.csv
    python3 tools/yt1/lev2_events.py --phase full       the same on every bar (refuses if there are no later bars)
    python3 tools/yt1/lev2_events.py --same             one process against two: the frames must be identical
"""
import argparse, pathlib, sys, time
import numpy as np
import pandas as pd
sys.path.insert(0, str(pathlib.Path(__file__).parent))
import core
import tt
import lev1_levels as LL
import lev1_events as LE
import lev2_levels as LV

TICK = core.TICK
SKIP = LE.SKIP                                         # 0.04 x ATR
BRK2 = "brk_a04x2"
VARIANTS = LE.FADES + LE.BREAKS + [BRK2]
HEAD, ASKED, NB1, NB2 = "a04x3", "p20x3", "a08x3", "a04x2"
BHEAD, BNB1, BNB2 = "brk_a04", "brk_a08", BRK2
BUCKETS = LE.BUCKETS
DIST_BINS = ((0.0, 0.10, "<0.10"), (0.10, 0.25, "0.10-0.25"), (0.25, 0.50, "0.25-0.50"), (0.50, np.inf, ">=0.50"))
SBUCKETS = ("0", "1", "2", "3+")
VA = ("rth", "eth", "rth3")                            # VA-trend: the rule and its two neighbours
VA_R = 0.1                                             # R unit of a trade without a stop, x ATR


def stop_of(variant):
    return "a04" if variant == BRK2 else LE.stop_of(variant)


def order_of(i, side, px, d, variant, expire, exit_i):
    """lev1_events.order_of, plus the 2R break."""
    if variant == BRK2:
        return dict(i=int(i), side=side, etype="stop", price=float(px), expire=int(expire), stop=float(px - side * d),
                    target=float(px + side * 2 * d), exit_i=int(exit_i))
    return LE.order_of(i, side, px, d, variant, expire, exit_i)


def orders_of(r, variant):
    side = 1 if r.side == "R" else -1
    d = LE.stop_pts(r.atr)[stop_of(variant)]
    return [order_of(int(r.w0) - 1, side, r.px, d, variant, int(r.w1), int(r.exit_i))]


COLS = ["date", "study", "code", "inst", "lid", "group", "prof", "N", "stype", "level", "hour", "is_placebo", "parent",
        "value", "px", "atr", "t_set", "t_end", "w0", "w1", "exit_i", "p0", "side", "skipped", "crossed", "is_event",
        "tapped", "tap", "tap_time", "bucket", "dist_open", "dbucket", "away30", "thru30", "stack", "sbucket", "bias",
        "bias_rel", "sessions", "n_sess", "nbars", "vol", "late_min", "d_p20", "d_a04", "d_a08", "nofill", "jbad", "ghost"]
VCOLS = [f"{w}_{v}" for v in VARIANTS for w in ("f", "R", "pnl", "win", "why")]


def _score(ctx, side, w0, w1, px, tap, dist, exit_i):
    """The 13 variants of one event through core.simulate. Returns (values in VCOLS order, nofill, jbad, ghost)."""
    sim = core.simulate
    if tap < 0:                                           # never tapped: the resting headline order must not fill
        return None, 0, 0, sim(ctx, **order_of(w0 - 1, side, px, dist["a04"], HEAD, w1, exit_i)) is not None
    vals, nofill, jbad = [], 0, 0
    for v in VARIANTS:
        t = sim(ctx, **order_of(w0 - 1, side, px, dist[stop_of(v)], v, w1, exit_i))
        if t is None:
            nofill += 1
            vals += [False, np.nan, np.nan, False, ""]
        else:
            jbad += int(t["j"] != tap)
            vals += [True, t["R"], t["pnl"], t["reason"] == "TP", t["reason"]]
    return vals, nofill, jbad, False


def _dbucket(x):
    for lo, hi, name in DIST_BINS:
        if lo <= x < hi:
            return name
    return ""


def _days(ctx, PS, lvd, days, score, study, keep, stack_ok):
    """Event rows of the given study days. lvd: {date: frame of that day's level rows}; keep: None or a set of codes
    (the other rows only count towards `stack`)."""
    O, H, L, C = ctx.O, ctx.H, ctx.L, ctx.C
    ts, tod = ctx.ts, ctx.tod
    tns = ts.asi8
    m30 = pd.Timedelta(minutes=30).as_unit(ts.unit).value
    D = ctx.days
    d_atr, d_open, d_end = (dict(zip(D.index, D[k].to_numpy())) for k in ("atr", "i_open", "i_end"))
    bias = tt.bias(ctx).bias.to_dict()
    vp = study == "vp"
    real_profs = set(LV.PROFS)
    out = []
    for d in days:
        x = lvd.get(d)
        if x is None:
            continue
        atr, i_open, exit_i = float(d_atr[d]), int(d_open[d]), int(d_end[d])
        p0 = float(PS[i_open])
        dist = LE.stop_pts(atr)
        n = len(x)
        code, inst, lid, grp_ = x.code.to_numpy(), x.inst.to_numpy(), x.lid.to_numpy(), x.group.to_numpy()
        par_, tset_, tend_ = x.parent.to_numpy(), x.t_set.to_numpy(), x.t_end.to_numpy()
        crs_, plc = x.crossed.to_numpy(), x.is_placebo.to_numpy()
        val, w0, w1 = x.value.to_numpy(float), x.w0.to_numpy(), x.w1.to_numpy()
        if vp:
            prof, N_, sty, lvl = x.prof.to_numpy(), x.N.to_numpy(), x.stype.to_numpy(), x.level.to_numpy()
            ses, nses, nb_, vol_ = x.sessions.to_numpy(), x.n_sess.to_numpy(), x.nbars.to_numpy(), x.vol.to_numpy()
            hour, late = np.full(n, -1), np.zeros(n, int)
        else:
            prof = sty = lvl = ses = np.array([""] * n, dtype=object)
            N_ = nses = nb_ = np.zeros(n, int)
            vol_ = np.full(n, np.nan)
            hour, late = x.hour.to_numpy(), x.late_min.to_numpy()
        side = np.where(val > p0, 1, np.where(val < p0, -1, 0))
        skipped = ~(np.abs(val - p0) > SKIP * atr)             # within 0.04 x ATR of the 09:30 open (or no p0)
        px = LE.px_grid(val, side)
        b = int(bias.get(d, 0))
        # ---- stacked levels: other profiles with any level within 0.03 x ATR
        stack = np.full(n, -1)
        if vp and stack_ok:
            rs = np.flatnonzero(~plc & np.isin(prof, list(real_profs)))
            near = LL.NEAR * atr
            for k in rs:
                m = (np.abs(val[rs] - val[k]) <= near) & (prof[rs] != prof[k])
                stack[k] = len(set(prof[rs][m]))
        memo = {}
        for k in range(n):
            if keep is not None and code[k] not in keep:
                continue
            s = int(side[k])
            a, e_ = int(w0[k]), int(w1[k])
            tap, pxk = -1, float(px[k])
            if not skipped[k]:
                hit = (H[a:e_ + 1] >= pxk) if s > 0 else (L[a:e_ + 1] <= pxk)
                if hit.any():
                    tap = a + int(np.argmax(hit))
            tapped = tap >= 0
            away = thru = np.nan
            bucket, tap_time = "", pd.NaT
            lvlv = float(val[k])
            dopen = abs(lvlv - p0) / atr
            if tapped:
                e = min(int(np.searchsorted(tns, tns[tap] + m30, "right")) - 1, exit_i)
                if s > 0:
                    thru = max(H[tap:e + 1].max() - lvlv, 0.0) / atr
                    away = max(lvlv - min(C[tap], L[tap + 1:e + 1].min() if e > tap else C[tap]), 0.0) / atr
                else:
                    thru = max(lvlv - L[tap:e + 1].min(), 0.0) / atr
                    away = max(max(C[tap], H[tap + 1:e + 1].max() if e > tap else C[tap]) - lvlv, 0.0) / atr
                t_ = int(tod[tap])
                bucket = BUCKETS[0] if t_ < 600 else BUCKETS[1] if t_ < 690 else BUCKETS[2]
                tap_time = ts[tap]
            vals, nofill, jbad, ghost = None, 0, 0, False
            if score and not skipped[k]:
                mk = (s, a, e_, pxk)
                if mk not in memo:
                    memo[mk] = _score(ctx, s, a, e_, pxk, tap, dist, exit_i)
                vals, nofill, jbad, ghost = memo[mk]
            if vals is None:
                vals = [False, np.nan, np.nan, False, ""] * len(VARIANTS)
            rel = "none" if b == 0 or s == 0 else ("with" if (s < 0) == (b > 0) else "against")
            sk = int(stack[k])
            out.append([d, study, code[k], inst[k], lid[k], grp_[k], prof[k], int(N_[k]), sty[k], lvl[k], int(hour[k]),
                        bool(plc[k]), par_[k], lvlv, pxk, atr, int(tset_[k]), int(tend_[k]), a, e_, exit_i, p0,
                        "R" if s > 0 else "S" if s < 0 else "", bool(skipped[k]), bool(crs_[k]), bool(not skipped[k]),
                        tapped, tap, tap_time, bucket, dopen, _dbucket(dopen), away, thru, sk,
                        "" if sk < 0 else SBUCKETS[min(sk, 3)], b, rel, ses[k], int(nses[k]), int(nb_[k]),
                        float(vol_[k]), int(late[k]), dist["p20"], dist["a04"], dist["a08"], nofill, jbad, bool(ghost)]
                       + list(vals))
    return out


_FORK = {}


def _worker(span):
    ctx, PS, lvd, days, score, study, keep, stack_ok = _FORK["a"]
    return _days(ctx, PS, lvd, days[span[0]:span[1]], score, study, keep, stack_ok)


def events(ctx, study, at_open=True, score=True, procs=1, profs=None, codes=None):
    """profs (VPN1 only): build only these profiles (no placebos, no stack count). codes: emit only these codes."""
    assert study in ("mid", "vp")
    c = LV._cache(ctx)
    key = ("events", study, bool(at_open), bool(score), None if profs is None else tuple(profs),
           None if codes is None else tuple(sorted(codes)))
    if key in c:
        return c[key]
    lv = LV.mid_levels(ctx) if study == "mid" else LV.vp_levels(ctx, profs)
    PS = LL.pstart(ctx, at_open)
    days = LV.ok_days(ctx)
    x = lv[~lv.dropped & (lv.w0 <= lv.w1) & lv.date.isin(set(days))]
    lvd = {d: g for d, g in x.groupby("date", sort=False)}
    keep = None if codes is None else set(codes)
    stack_ok = study == "vp" and profs is None
    if procs > 1 and len(days) > 40:
        import multiprocessing as mp
        w = np.cumsum([len(lvd[d]) if d in lvd else 0 for d in days])
        cuts = [0] + [int(np.searchsorted(w, w[-1] * a / procs)) for a in range(1, procs)] + [len(days)]
        _FORK["a"] = (ctx, PS, lvd, days, score, study, keep, stack_ok)
        with mp.get_context("fork").Pool(procs) as pool:
            parts = pool.map(_worker, [(cuts[a], cuts[a + 1]) for a in range(procs)])
        _FORK.clear()
        rows = [r for p in parts for r in p]
    else:
        rows = _days(ctx, PS, lvd, days, score, study, keep, stack_ok)
    ev = pd.DataFrame(rows, columns=COLS + VCOLS)
    for v in VARIANTS:
        ev[f"f_{v}"] = ev[f"f_{v}"].astype(bool)
        ev[f"win_{v}"] = ev[f"win_{v}"].astype(bool)
    c[key] = ev
    return ev


# ------------------------------------------------------------------ aligned value: day types, VA-trend, ORB by day
def va_orders(ctx, which="rth", at_open=True):
    """VA-trend: on a study day whose 09:30 open is above all five VAHs (below all five VALs) of rth1..5, a market
    order decided on the last bar before 09:30 and filled at the 09:30 open, long (short), no stop, flat at the flat
    bar, R unit 0.1 x ATR. which 'eth': eth1..5; 'rth3': rth1..3. at_open=False compares the last close before 09:30
    with the value areas instead of the 09:30 open (the look-ahead test's form)."""
    assert which in VA
    dt = LV.day_types(ctx, at_open)
    D = ctx.days
    typ = dt[f"type_{which}"].to_dict()
    out = []
    for d in LV.ok_days(ctx):
        t = typ[d]
        if t not in ("above", "below"):
            continue
        out.append(dict(i=int(D.i_open[d]) - 1, side=1 if t == "above" else -1, etype="open", exit_i=int(D.i_end[d]),
                        r_pts=VA_R * float(D.atr[d]), tag=f"va_{which}|{t}|{d:%Y-%m-%d}"))
    return out


def daytypes(ctx):
    """One row per cash day: lev2_levels.day_types (09:30 open, ATR, the VAH / POC / VAL of rth1..5 and eth1..5, the
    three day types), study (a study day), move_up = (close of the flat bar - 09:30 open) / ATR, va_<which>_side / _R /
    _pnl (the VA-trend trades through core.simulate) and orb_side / orb_R / orb_pnl (ORB v1.4: cal_orb.orders through
    core.run_orders(skip_roll=False), its trade of that cash day if any)."""
    import cal_orb
    D = ctx.days
    dt = LV.day_types(ctx, True).copy()
    ok = set(LV.ok_days(ctx))
    dt.insert(0, "study", [d in ok for d in dt.index])
    dt["move_up"] = (ctx.C[D.i_end.to_numpy()] - ctx.O[D.i_open.to_numpy()]) / D.atr.to_numpy()
    for which in VA:
        side, R, pnl = {}, {}, {}
        for o in va_orders(ctx, which):
            t = core.simulate(ctx, **o)
            d = pd.Timestamp(o["tag"].split("|")[2])
            if t is not None:
                assert t["j"] == int(D.i_open[d])
                side[d], R[d], pnl[d] = ("L" if o["side"] > 0 else "S"), t["R"], t["pnl"]
        dt[f"va_{which}_side"] = [side.get(d, "") for d in dt.index]
        dt[f"va_{which}_R"] = [R.get(d, np.nan) for d in dt.index]
        dt[f"va_{which}_pnl"] = [pnl.get(d, np.nan) for d in dt.index]
    orb = core.trades_df(core.run_orders(ctx, cal_orb.orders(ctx), skip_roll=False))
    od = pd.DatetimeIndex(orb.entry_time).tz_localize(None).normalize()
    assert not od.duplicated().any()
    o = orb.set_index(od)
    dt["orb_side"] = [o.side.get(d, "") for d in dt.index]
    dt["orb_R"] = o.R.reindex(dt.index).to_numpy()
    dt["orb_pnl"] = o.pnl.reindex(dt.index).to_numpy()
    dt.index.name = "date"
    return dt.reset_index()


# ------------------------------------------------------------------ counts and the fill-bar check
def report(ev, label):
    out = []
    nd = ev.date.nunique()
    e = ev[ev.is_event]
    t = e[e.tapped]
    out.append(f"{label}: study days {nd}; level-days {len(ev)}; skipped (within 0.04 x ATR of the 09:30 open) "
               f"{int(ev.skipped.sum())}; events (watched) {len(e)}; tapped {len(t)} ({len(t) / max(len(e), 1):.1%}); "
               f"crossed before 09:30 among tapped {int(t.crossed.sum())} ({t.crossed.mean():.1%})")
    groups = [("real", ~e.is_placebo & (e.group != "aligned POC")), ("placebo", e.is_placebo)]
    if (e.group == "aligned POC").any():
        groups.append(("aligned POC", e.group == "aligned POC"))
    for nm, m in groups:
        q = e[m]
        qt = q[q.tapped]
        out.append(f"  {nm:<12} level-days {int((ev.is_placebo if nm == 'placebo' else (ev.group == 'aligned POC') if nm == 'aligned POC' else (~ev.is_placebo & (ev.group != 'aligned POC'))).sum()):>6}"
                   f"  events {len(q):>6}  tapped {len(qt):>6} ({len(qt) / max(len(q), 1):.1%})  S {int((qt.side == 'S').sum())} / R "
                   f"{int((qt.side == 'R').sum())}  by time {', '.join(f'{b} {int((qt.bucket == b).sum())}' for b in BUCKETS)}")
    nv = len(VARIANTS)
    uq = t.drop_duplicates(["date", "side", "px"])
    out.append(f"  fill bar = tap bar: {len(t)} tapped events x {nv} variants = {len(t) * nv} orders; filled on the tap bar "
               f"{int(sum(t[f'f_{v}'].sum() for v in VARIANTS) - t.jbad.sum())}; filled on another bar {int(t.jbad.sum())}; "
               f"not filled {int(t.nofill.sum())} (events with at least one unfilled variant: {int((t.nofill > 0).sum())}); "
               f"untapped events whose resting headline order filled: {int(e.ghost.sum())} of {int((~e.tapped).sum())}; "
               f"distinct orders (date x side x price) among the tapped events: {len(uq)}")
    nf = t[t.nofill > 0]
    if len(nf):
        out.append(f"  not filled by variant: { {v: int((~nf[f'f_{v}']).sum()) for v in VARIANTS} }")
        for r in nf.itertuples():
            out.append(f"    {r.date.date()} {r.lid} {r.side} px {r.px:.2f} tap {r.tap_time}")
    return out


def report_days(dt):
    s = dt[dt.study]
    out = [f"day types on the {len(s)} study days: " + "; ".join(
        f"{c[5:]}: " + ", ".join(f"{k or 'not built'} {v}" for k, v in s[c].value_counts().reindex(["above", "below", "inside", "mixed", ""]).fillna(0).astype(int).items())
        for c in ("type_rth", "type_eth", "type_rth3"))]
    out.append("VA-trend trades: " + ", ".join(f"{w} {int((s[f'va_{w}_side'] != '').sum())}" for w in VA)
               + f"; ORB v1.4 trades on study days {int((s.orb_side != '').sum())} (on all cash days {int((dt.orb_side != '').sum())})")
    return out


def build(ctx, study, procs=2):
    """(events frame, seconds)"""
    t0 = time.time()
    ev = events(ctx, study, procs=procs)
    return ev, time.time() - t0


def main():
    import run
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", choices=["is", "full"], default="is")
    ap.add_argument("--study", choices=["mid", "vp", "all"], default="all")
    ap.add_argument("--procs", type=int, default=2)
    ap.add_argument("--same", action="store_true", help="build with 1 and with 2 processes and compare the frames")
    a = ap.parse_args()
    assert 1 <= a.procs <= 2, "at most 2 worker processes"
    t00 = time.time()
    A = run.bars(a.phase)
    if a.phase == "full" and A.index.max() < core.IS_END:
        raise SystemExit("no bars after 2022-12-31 in this data directory: the full phase cannot run here")
    ctx = core.Ctx(A)
    d = core.OUT / a.phase
    d.mkdir(parents=True, exist_ok=True)
    print(f"LEV2 events   phase {a.phase}   bars {A.index[0]} -> {A.index[-1]}")
    if a.same:
        for study in ("mid", "vp"):
            t0 = time.time()
            e1 = events(ctx, study, procs=1)
            t1 = time.time()
            LV._cache(ctx).pop(("events", study, True, True, None, None))
            e2 = events(ctx, study, procs=2)
            print(f"{study}: 1 process {t1 - t0:.0f}s, 2 processes {time.time() - t1:.0f}s, {len(e1)} rows, identical frames: "
                  f"{bool(e1.equals(e2))}")
        return
    for line in LV.counts(ctx):
        print(line)
    if a.study in ("mid", "all"):
        ev, sec = build(ctx, "mid", a.procs)
        ev.to_parquet(d / "MID1_events.parquet", index=False)
        for line in report(ev, "MID1"):
            print(line)
        print(f"wrote {d / 'MID1_events.parquet'} ({len(ev)} rows) [{sec:.0f}s]")
    if a.study in ("vp", "all"):
        ev, sec = build(ctx, "vp", a.procs)
        ev.to_parquet(d / "VPN1_events.parquet", index=False)
        for line in report(ev, "VPN1"):
            print(line)
        print(f"wrote {d / 'VPN1_events.parquet'} ({len(ev)} rows) [{sec:.0f}s, {a.procs} process(es)]")
        t0 = time.time()
        dt = daytypes(ctx)
        dt.to_csv(d / "VPN1_daytypes.csv", index=False)
        for line in report_days(dt):
            print(line)
        print(f"wrote {d / 'VPN1_daytypes.csv'} ({len(dt)} rows) [{time.time() - t0:.0f}s]")
    print(f"total {time.time() - t00:.0f}s")


if __name__ == "__main__":
    main()
