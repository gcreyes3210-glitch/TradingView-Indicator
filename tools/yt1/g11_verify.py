#!/usr/bin/env python3
"""G11 checks (the ones quoted in notes/G11.md). Reads the trade file; changes nothing.

    python3 tools/yt1/g11_verify.py --eq11        the 11:00 cut-off: every cell of every day simulated directly with
                                                  an 11:00 cut-off against the rows derived from the 12:00 run
                                                  (--eq11-days N: N random days only)
    python3 tools/yt1/g11_verify.py --recon       grid row vs standard harness: every s_G11 variant (and the files
                                                  run.py wrote), and 96 random combinations trade by trade
    python3 tools/yt1/g11_verify.py --neg         negative controls of the look-ahead test: deliberately leaky
                                                  variants (patched in memory) must FAIL
    python3 tools/yt1/g11_verify.py --slow 40     the set-up of 40 random days recomputed by a separately written
                                                  slow reference (pandas time slices on the 1-minute bars)
    python3 tools/yt1/g11_verify.py --rc          the reality check in float64 and by slow resampling of day rows
    python3 tools/yt1/g11_verify.py --counts      the counts quoted in the notes
    python3 tools/yt1/g11_verify.py --hand        the bars behind the hand checks of notes/G11.md
"""
import argparse, json, pathlib, sys, time
import numpy as np
import pandas as pd
sys.path.insert(0, str(pathlib.Path(__file__).parent))
import core, run, ind
import g11_grid as gg
import g11_sim as gs
import s_G11

TZ = core.TZ
T = core.TICK
CMP = ["day", "side", "L", "K", "D", "N", "S", "X", "which", "i", "j", "k", "b", "entry_px", "entry", "stop",
       "target", "exit", "reason", "pnl", "R", "risk_pts", "f_ema200", "f_vwap", "f_ema921"]


# ------------------------------------------------------------------ the 11:00 cut-off
def eq11(ctx, trades, n_days=0, seed=11):
    days = gs.traded_days(ctx)
    if n_days:
        rng = np.random.default_rng(seed)
        days = [days[q] for q in sorted(rng.choice(len(days), n_days, replace=False))]
    t0 = time.time()
    direct, _ = gs.run(ctx, procs=2 if len(days) > 100 else 1, cut_tod=gs.CUT["11"], days=days)
    der = trades[trades.in11 & trades.day.isin(days)]
    key = ["L", "K", "D", "N", "S", "X", "day", "which"]
    a = direct[CMP].sort_values(key, kind="mergesort").reset_index(drop=True)
    b = der[CMP].sort_values(key, kind="mergesort").reset_index(drop=True)
    for k in ("L", "K", "D", "N", "S", "X", "reason"):
        a[k], b[k] = a[k].astype(str), b[k].astype(str)
    same = len(a) == len(b) and a.equals(b)
    pairs = len(gs.cells()) * len(days)
    all12 = trades[trades.day.isin(days)]
    g12 = all12[all12.which == 1].groupby(key[:-1], observed=True).ngroups
    g11 = der[der.which == 1].groupby(key[:-1], observed=True).ngroups
    print(f"11:00 cut-off: {len(days)} days x {len(gs.cells())} cells = {pairs} (combination, day) pairs simulated directly"
          f" with an 11:00 cut-off ({time.time() - t0:.0f}s)")
    print(f"  pairs with a first trade under 12:00: {g12}; with an entry by 11:00: {g11}; first trades entered after 11:00"
          f" (absent under 11:00): {g12 - g11}")
    print(f"  re-entries under 12:00: {(all12.which == 2).sum()}; of them entered by 11:00 (the stop-out and the re-entry "
          f"candle's close both by 11:00): {(der.which == 2).sum()}")
    print(f"  direct 11:00 trades {len(a)}   derived (12:00 rows with the entry bar closing by 11:00) {len(b)}   "
          f"every column of every trade identical: {same}")
    if not same:
        m = a.merge(b, on=key, how="outer", indicator=True, suffixes=("_d", "_x"))
        print(m[m._merge != "both"].head(10).to_string())
        if len(a) == len(b):
            for c in CMP:
                if not a[c].equals(b[c]):
                    print("  differs:", c, int((a[c] != b[c]).sum()))
    return 0 if same else 1


# ------------------------------------------------------------------ grid against the harness
def _one(ctx, trades, grid, label, cname, nb=0):
    c = gg.neighbour(gg.parse(cname), nb)
    nm = gg.name(c)
    g = gg.pick(trades, c)
    h = core.trades_df(s_G11.trades(ctx, c=cname, nb=nb))
    row = grid.loc[nm]
    ok = len(h) == len(g) == int(row.n)
    if ok and len(h):
        ok &= np.array_equal(h.i.to_numpy(), g.i.to_numpy()) and np.array_equal(h.j.to_numpy(), g.j.to_numpy()) \
            and np.array_equal(h.k.to_numpy(), g.k.to_numpy())
        for col in ("entry", "exit", "stop", "pnl", "R", "risk_pts"):
            ok &= np.array_equal(h[col].to_numpy(), g[col].to_numpy())
        ok &= np.array_equal(h.reason.to_numpy(), g.reason.astype(str).to_numpy())
        ok &= np.array_equal((h.side == "L").to_numpy(), (g.side > 0).to_numpy())
        ok &= abs(h.pnl.sum() - row.net) < 0.005 and abs(h.R.mean() - row.mR) < 1e-12
    line = (f"  {label:<8} {nm:<50} grid n {int(row.n):>4} net {row.net:>+10.2f} R {row.mR:+.6f} | harness n {len(h):>4} "
            f"net {h.pnl.sum():>+10.2f} R {(h.R.mean() if len(h) else float('nan')):+.6f}  {'OK' if ok else 'MISMATCH'}")
    return bool(ok), line


def recon(ctx, trades, n_rand=96):
    grid = gg.evaluate(trades)
    bad = 0
    print("every variant of s_G11 through the harness against the grid row (trade by trade: bars, prices, pnl, R):")
    for v, p in s_G11.VARIANTS.items():
        ok, line = _one(ctx, trades, grid, v, p["c"], p["nb"])
        bad += not ok
        nm = gg.name(gg.neighbour(gg.parse(p["c"]), p["nb"]))
        f = core.OUT / "is" / f"G11_{v}.csv"                   # what the standard runner wrote, if it has been run
        if f.exists():
            d = pd.read_csv(f)
            g = grid.loc[nm]
            same = len(d) == g.n and abs(d.pnl.sum() - g.net) < 0.005 and (len(d) == 0 or abs(d.R.mean() - g.mR) < 1e-9)
            line += f"   run.py file: n {len(d)} net {d.pnl.sum():+.2f} R {(d.R.mean() if len(d) else float('nan')):+.6f} {'OK' if same else 'DIFFERS'}"
            bad += not same
        else:
            line += "   (no run.py file)"
        print(line, flush=True)
    rng = np.random.default_rng(7)
    all_ = gg.combos()
    # a stratified draw: for every (N, S) pair that exists, every X and both E appear; L, K, D, W, F at random
    pairs = sorted({(c["N"], c["S"]) for c in all_}, key=lambda x: (gs.NS.index(x[0]), gs.SS.index(x[1])))
    chosen = []
    q = 0
    while len(chosen) < n_rand:
        N, S = pairs[q % len(pairs)]
        X = gs.XS[(q // len(pairs) + q) % 4]
        E = ("one", "re")[(q // len(pairs) + q // 2) % 2]
        pool = [c for c in all_ if c["N"] == N and c["S"] == S and c["X"] == X and c["E"] == E]
        chosen.append(pool[int(rng.integers(len(pool)))])
        q += 1
    m = tot = with_tr = 0
    cov = {k: set() for k in gg.ORDER}
    for c in chosen:
        ok, line = _one(ctx, trades, grid, "rand", gg.name(c))
        tot += 1
        m += ok
        with_tr += int(grid.loc[gg.name(c)].n > 0)
        for k in gg.ORDER:
            cov[k].add(c[k])
        if not ok:
            print(line)
            bad += 1
    print(f"random combinations trade by trade: {m} of {tot} match ({with_tr} of them have trades; levels covered: "
          + ", ".join(f"{k} {len(cov[k])}/{len(gg.LEVELS[k])}" for k in gg.ORDER) + ")")
    print("total mismatches:", bad)
    return bad


# ------------------------------------------------------------------ negative controls
def _leaks():
    """name -> (variant to run, patcher returning an undo function). Each patch makes one set-up function read
    bars after the order's own bar; it lives in memory only."""
    def p_ext():                                   # the excursion is looked for over the whole morning, in hindsight
        old = gs.arm_bar
        def arm(P, lv, br, D, cut):
            if D != "ext":
                return br.b
            thr_hit = (P.Ht[lv.watch0:cut + 1] * gs.EXT_DEN >= gs.EXT_DEN * lv.hi + gs.EXT_NUM * lv.W).any() if br.side > 0 \
                else (P.Lt[lv.watch0:cut + 1] * gs.EXT_DEN <= gs.EXT_DEN * lv.lo - gs.EXT_NUM * lv.W).any()
            return br.b if thr_hit else None
        gs.arm_bar = arm
        return lambda: setattr(gs, "arm_bar", old)

    def p_conf_stop():                             # the pullback low is read through 5 bars after the confirmation
        old = gs.entry_plan
        def plan(P, lv, br, N, a, cut):
            pl = old(P, lv, br, N, a, cut)
            if pl is not None and pl["kind"] == "close":
                c = pl["i"]
                pl["pull"] = int(P.Lt[pl["touch"]:c + 6].min()) if br.side > 0 else int(P.Ht[pl["touch"]:c + 6].max())
            return pl
        gs.entry_plan = plan
        return lambda: setattr(gs, "entry_plan", old)

    def p_break():                                 # the break candle is only accepted if the next 1-minute bar agrees
        old = gs.find_break
        def fb(P, lv, K, cut):
            br = old(P, lv, K, cut)
            if br is not None and br.b + 1 < len(P.Ct) and br.side * (P.Ct[br.b + 1] - P.Ct[br.b]) < 0:
                return None
            return br
        gs.find_break = fb
        return lambda: setattr(gs, "find_break", old)

    def p_reentry():                               # the re-entry candle is only taken if the next 1-minute bar closes higher
        old = gs.reentry_bar
        def rb(P, lv, K, side, k1, cut):
            i2 = old(P, lv, K, side, k1, cut)
            if i2 is not None and i2 + 1 < len(P.Ct) and side * (P.Ct[i2 + 1] - P.Ct[i2]) <= 0:
                return None
            return i2
        gs.reentry_bar = rb
        return lambda: setattr(gs, "reentry_bar", old)

    def p_flags():                                 # the EMA / VWAP side filter is read 3 five-minute bars / 15 minutes ahead
        old = gs.filter_flags
        def ff(P, br):
            j5 = int(np.searchsorted(P.tab[5]["i_last"], br.b, "right")) - 1 + 3
            j5 = min(j5, len(P.ema200) - 1)
            b2 = min(br.b + 15, len(P.Ct) - 1)
            c, s = P.ctx.C[b2], br.side
            return (bool(s * (c - P.ema200[j5]) > 0), bool(s * (c - P.vwap[b2]) > 0), bool(s * (P.ema9[j5] - P.ema21[j5]) > 0))
        gs.filter_flags = ff
        return lambda: setattr(gs, "filter_flags", old)

    def p_poc():                                   # the profile is built on the range plus the next 30 minutes
        old = gs.profile
        def pr(P, s_lo, s_hi):
            return old(P, s_lo, min(s_hi + 30, len(P.Ct)))
        gs.profile = pr
        return lambda: setattr(gs, "profile", old)

    def p_zone():                                  # the demand candle is searched up to 3 candles AFTER the break
        old = gs.zone_candle
        def zc(P, br):
            if br.K == "c1":
                o, h, l, c, q, m = P.Ot, P.Ht, P.Lt, P.Ct, br.b + 3, 1
            else:
                tb = P.tab[5]
                o, h, l, c, m = tb["o"], tb["h"], tb["l"], tb["c"], 5
                q = int(np.searchsorted(tb["i_last"], br.b, "left")) + 3
            q = min(q, len(c) - 1)
            for r in range(q, max(q - gs.ZONE_LOOKBACK, -1), -1):
                if (c[r] < o[r]) if br.side > 0 else (c[r] > o[r]):
                    return int(h[r]), int(l[r]), r, m
            return None
        gs.zone_candle = zc
        return lambda: setattr(gs, "zone_candle", old)

    def p_level():                                 # the opening range is read 5 minutes too long
        old = gs.level
        def lvf(P, d, day, L):
            lv = old(P, d, day, L)
            if lv is not None and L != "pd":
                hi = min(lv.s_hi + 5, len(P.Ct))
                lv.hi, lv.lo = int(P.Ht[lv.s_lo:hi].max()), int(P.Lt[lv.s_lo:hi].min())
                lv.W, lv.mid2 = lv.hi - lv.lo, lv.hi + lv.lo
            return lv
        gs.level = lvf
        return lambda: setattr(gs, "level", old)

    return {
        "ext: excursion looked for over the whole morning": ("chk5", p_ext, None),
        "conf: pullback low read 5 bars past the confirmation": ("chk2", p_conf_stop, None),
        "break: accepted only if the next 1-minute bar agrees": ("chk1", p_break, None),
        "re-entry: taken only if the next 1-minute bar closes higher": ("chk2", p_reentry, 2),
        "re-entry: the same, full order list": ("chk7", p_reentry, None),
        "filter: EMA / VWAP read 15 minutes ahead": ("chk4", p_flags, None),
        "filter: the same on vwap": ("chk6", p_flags, None),
        "poc: profile built on the range plus 30 minutes": ("chk6", p_poc, None),
        "zone: demand candle searched after the break": ("chk12", p_zone, None),
        "level: opening range read 5 minutes too long": ("chk1", p_level, None),
    }


def negative(A, cuts=16):
    bad = 0
    for label, (v, patch, which) in _leaks().items():
        p = s_G11.VARIANTS[v]
        make = lambda cx, p=p, which=which: s_G11.orders(cx, which=which, **p)
        clean = core.causal_check(make, A, n_samples=cuts, verbose=False)
        undo = patch()
        try:
            leaky = core.causal_check(make, A, n_samples=cuts, verbose=False)
        finally:
            undo()
        ok = clean and not leaky
        bad += not ok
        print(f"  {label:<62} {v:<6} unpatched {'PASS' if clean else 'FAIL'}   leaky {'PASS' if leaky else 'FAIL'}"
              f"   -> {'as it must be' if ok else 'THE TEST DOES NOT SEE THIS LEAK'}", flush=True)
    return bad


# ------------------------------------------------------------------ slow reference of the set-up
def _slow_day(ctx, d, day, e5):
    """The set-up rows of one day recomputed from pandas time slices of the 1-minute bars (written separately from
    g11_sim: no shared code, float prices, no tick integers). Returns {(L, K): dict}."""
    a = ctx.a
    t = lambda hm: (pd.Timestamp(d) + pd.Timedelta(hm + ":00")).tz_localize(TZ)
    m = a[(a.index >= t("09:30")) & (a.index < t("12:00"))]
    out = {}
    for L, mins in (("or5", 5), ("or15", 15), ("or30", 30), ("pd", 0)):
        if L == "pd":
            hi, lo, start = day.pdh, day.pdl, t("09:30")
            r15 = m[m.index < t("09:45")]
            W = r15.high.max() - r15.low.min()
            watch, known = t("09:30"), r15.index[-1]
        else:
            rng = m[m.index < t("09:30") + pd.Timedelta(minutes=mins)]
            hi, lo = rng.high.max(), rng.low.min()
            W, start = hi - lo, t("09:30") + pd.Timedelta(minutes=mins)
            watch, known = start, rng.index[-1]
        for K, km in (("c1", 1), ("c5", 5), ("c15", 15)):
            after = m[m.index >= start]
            if not len(after):
                out[(L, K)] = dict(side=0)
                continue
            g = after.groupby(after.index.floor(f"{km}min"))
            cand = pd.DataFrame({"close": g.close.last(), "last": g.apply(lambda x: x.index[-1])})
            cand = cand[(cand.index >= start)]
            hit = cand[(cand.close > hi) | (cand.close < lo)]
            if not len(hit):
                out[(L, K)] = dict(side=0)
                continue
            r = hit.iloc[0]
            side = 1 if r.close > hi else -1
            b_ts = r["last"]
            # fvg: 1-minute bars of the breaking candle and of the two K candles before it
            allb = a[a.index <= b_ts].iloc[-3 * km * 4:]
            gk = allb.groupby(allb.index.floor(f"{km}min"))
            firsts = gk.apply(lambda x: x.index[0])
            s0 = firsts.iloc[-3]
            w = a[(a.index >= s0) & (a.index <= b_ts)]
            hh, ll = w.high.to_numpy(), w.low.to_numpy()
            fv = any((ll[k] > hh[k - 2]) if side > 0 else (hh[k] < ll[k - 2]) for k in range(2, len(w)))
            # ext
            wb = m[m.index >= watch]
            thr = hi + 0.7 * W if side > 0 else lo - 0.7 * W
            reach = wb[(wb.high >= thr - 1e-9)] if side > 0 else wb[(wb.low <= thr + 1e-9)]
            e_ts = None
            if len(reach):
                e_ts = max(reach.index[0], known)
            # flags
            c = a.close[b_ts]
            done = e5[e5["end"] <= b_ts].iloc[-1]
            day_bars = a[(a.index >= t("09:30")) & (a.index <= b_ts)]
            tp = (day_bars.high + day_bars.low + day_bars.close) / 3
            vw = (tp * day_bars.volume).sum() / day_bars.volume.sum()
            out[(L, K)] = dict(side=side, b=b_ts, close=float(r.close), hi=float(hi), lo=float(lo), W=float(W), fvg=bool(fv),
                               ext=e_ts, f_ema200=bool(side * (c - done.e200) > 0), f_vwap=bool(side * (c - vw) > 0),
                               f_ema921=bool(side * (done.e9 - done.e21) > 0),
                               prof=_slow_profile(rng) if L != "pd" else (np.nan, np.nan, np.nan))
    return out


def _slow_profile(rng):
    """(poc, val, vah) of a set of 1-minute bars with float arithmetic: volume / number of ticks added to every tick
    of each bar; ties within 1e-7 of a contract count as equal."""
    lo, hi = rng.low.min(), rng.high.max()
    px = np.round(np.arange(lo, hi + T / 2, T) / T) * T
    vol = np.zeros(len(px))
    for r in rng.itertuples():
        m = (px >= r.low - 1e-9) & (px <= r.high + 1e-9)
        vol[m] += r.volume / m.sum()
    eps = 1e-7
    q = int(np.flatnonzero(vol >= vol.max() - eps)[0])
    a = z = q
    acc, total = vol[q], vol.sum()
    while acc < 0.7 * total - eps:
        down = vol[a - 1] if a > 0 else None
        up = vol[z + 1] if z < len(px) - 1 else None
        if down is not None and (up is None or down >= up - eps):
            a -= 1
            acc += vol[a]
        else:
            z += 1
            acc += vol[z]
    return float(px[q]), float(px[a]), float(px[z])


def _slow_orders(ctx, d, x, L, K, D):
    """{(N, S): (decision time, entry price, stop price)} of the day's first order for every entry style and stop
    rule that exists, from pandas slices of the 1-minute bars (floats; separately written from g11_sim)."""
    import math
    a = ctx.a
    t = lambda hm: (pd.Timestamp(d) + pd.Timedelta(hm + ":00")).tz_localize(TZ)
    side, hi, lo, W, b = x["side"], x["hi"], x["lo"], x["W"], x["b"]
    if D == "ext":
        if x["ext"] is None:
            return {}
        arm = max(b, x["ext"])
    else:
        arm = b
    level = hi if side > 0 else lo
    mid = (hi + lo) / 2
    away = (lambda v: math.floor(v / T + 1e-9) * T) if side > 0 else (lambda v: math.ceil(v / T - 1e-9) * T)
    last_ok = a[(a.index >= t("09:30")) & (a.index < t("12:00"))].index[-1]
    entries = {}
    # conf
    after = a[(a.index > arm) & (a.index <= last_ok)]
    touch = after[after.low <= level] if side > 0 else after[after.high >= level]
    if len(touch):
        t0 = touch.index[0]
        prev = a.shift(1)
        seq = a[(a.index >= t0) & (a.index <= last_ok)]
        for ts_, row in seq.iterrows():
            if (row.close > prev.high[ts_]) if side > 0 else (row.close < prev.low[ts_]):
                w = a[(a.index >= t0) & (a.index <= ts_)]
                pull = w.low.min() if side > 0 else w.high.max()
                entries["conf"] = (ts_, float(row.close), pull - side * T)
                break
    # limits
    lim = {"edge": (level, away(level - side * 0.25 * W))}
    if L != "pd":
        poc, val, vah = x["prof"]
        lim["mid"] = (away(mid), away(mid - side * 0.25 * W))
        lim["poc"] = (poc, (val - T) if side > 0 else (vah + T))
    if K == "c1":
        cand = a[a.index < b].iloc[-12:]
        cand = pd.DataFrame({"o": cand.open, "h": cand.high, "l": cand.low, "c": cand.close})
    else:
        b5 = ctx.bars(5)
        ends = ctx.ts[b5.i_last.to_numpy()]
        cand = b5[ends < b].iloc[-12:]
        cand = pd.DataFrame({"o": cand.open, "h": cand.high, "l": cand.low, "c": cand.close})
    z = cand[cand.c < cand.o] if side > 0 else cand[cand.c > cand.o]
    if len(z):
        zc = z.iloc[-1]
        lim["zone"] = ((zc.h, zc.l - T) if side > 0 else (zc.l, zc.h + T))
    for N, (px, near) in lim.items():
        if not ((px < x["close"]) if side > 0 else (px > x["close"])):
            continue
        at = arm
        if N == "edge" and L == "pd":
            at = max(arm, a[(a.index >= t("09:30")) & (a.index < t("09:45"))].index[-1])
        entries[N] = (at, float(px), float(near))
    out = {}
    for N, (ts_, px, near) in entries.items():
        stops = {"near": near}
        if L != "pd":
            stops["mid"] = away(mid) - side * T
            stops["far"] = (lo - 2 * T) if side > 0 else (hi + 2 * T)
        for S, st in stops.items():
            if gs.exists(L, N, S) and side * (px - st) >= 2 * T - 1e-9:
                out[(N, S)] = (ts_, px, float(st))
    return out


def slow(ctx, setups, trades, n_days=40, seed=4):
    b5 = ctx.bars(5)
    c5 = b5.close.to_numpy(float)
    e5 = pd.DataFrame({"end": ctx.ts[b5.i_last.to_numpy()], "e200": ind.ema(c5, 200), "e9": ind.ema(c5, 9),
                       "e21": ind.ema(c5, 21)})      # ind.ema is the house definition (TradingView seeding)
    days = gs.traded_days(ctx)
    rng = np.random.default_rng(seed)
    pickd = [days[q] for q in sorted(rng.choice(len(days), n_days, replace=False))]
    bad = n = n_tr = n_ord = 0
    for d in pickd:
        ref = _slow_day(ctx, d, ctx.days.loc[d], e5)
        rows = setups[setups.day == d]
        for r in rows.itertuples(index=False):
            x = ref[(r.L, r.K)]
            n += 1
            if x["side"] != r.side:
                bad += 1
                print("  DIFF side", d.date(), r.L, r.K, x["side"], r.side)
                continue
            if r.side == 0:
                continue
            e_ref = -1 if x["ext"] is None else int(ctx.pos[x["ext"]])
            got = (ctx.ts[r.b], r.close, r.level_hi, r.level_lo, r.W, bool(r.d_fvg), int(r.ext_i), bool(r.f_ema200),
                   bool(r.f_vwap), bool(r.f_ema921))
            want = (x["b"], x["close"], x["hi"], x["lo"], x["W"], x["fvg"], e_ref, x["f_ema200"], x["f_vwap"], x["f_ema921"])
            if got != want:
                bad += 1
                print("  DIFF", d.date(), r.L, r.K, "\n     got ", got, "\n     want", want)
            if r.L != "pd" and (r.poc, r.val, r.vah) != x["prof"]:
                bad += 1
                print("  DIFF profile", d.date(), r.L, r.K, (r.poc, r.val, r.vah), x["prof"])
            # every first trade of the file must be the slow reference's order: decision bar, entry price, stop, target
            tr = trades[(trades.day == d) & (trades.L == r.L) & (trades.K == r.K) & (trades.which == 1)]
            for D in ("none", "ext"):
                ref_o = _slow_orders(ctx, d, x, r.L, r.K, D)
                for u in tr[tr.D == D].itertuples(index=False):
                    n_tr += 1
                    w = ref_o.get((u.N, u.S))
                    k = gs.XK[u.X]
                    tg = np.nan if k is None else core.tick_round(u.entry_px + u.side * k * abs(u.entry_px - u.stop))
                    if w is None or (u.sig_time, u.entry_px, u.stop) != w or not (tg == u.target or (tg != tg and u.target != u.target)):
                        bad += 1
                        if bad < 15:
                            print("  DIFF order", d.date(), r.L, r.K, D, u.N, u.S, u.X, (u.sig_time, u.entry_px, u.stop, u.target), w, tg)
                # a trade in the file for every (N, S) only where the slow reference has an order
                n_ord += len(ref_o)
            fv = tr[tr.D == "fvg"]
            if len(fv) and not x["fvg"]:
                bad += 1
                print("  DIFF: fvg trades on a day whose slow fvg flag is false", d.date(), r.L, r.K)
    print(f"slow reference of the set-up (level, W, break bar, side, fvg flag, excursion bar, three filter flags, point of "
          f"control and value area): {n_days} random days, {n} day x L x K rows; of the orders (decision bar, entry price, "
          f"stop, target; D none and ext): {n_tr} first trades of the file checked against {n_ord} slow orders x 4 targets;"
          f" {bad} differences")
    return bad


# ------------------------------------------------------------------ reality check
def rc_checks(trades, setups):
    table = gg.evaluate(trades)
    cl = gg.Cells(trades)
    days = gg.period_days(setups)
    e = gg.eligible(table)
    bad = 0
    st = json.loads((core.OUT / "is" / "G11_reality.json").read_text())
    f64 = gg.reality_check(trades, table, days, cells=cl, dtype=np.float64)
    b, bs = f64["boot_max_t"], st["boot_max_t"]
    print(f"all {f64['n_eligible']} eligible in float64 ({f64['matrix_MB']} MB, {f64['seconds']}s): observed {f64['t_obs_max']:.6f} "
          f"median {b['q50']:.6f} 95% {b['q95']:.6f} p {f64['p']:.4f}   stored (float32): observed {st['t_obs_max']:.6f} median "
          f"{bs['q50']:.6f} 95% {bs['q95']:.6f} p {st['p']:.4f}")
    bad += not (abs(f64["t_obs_max"] - st["t_obs_max"]) < 1e-5 and abs(b["q50"] - bs["q50"]) < 1e-3 and f64["p"] == st["p"])
    rng = np.random.default_rng(3)
    sub = list(rng.choice(e.index, min(2000, len(e)), replace=False))
    r64 = gg.reality_check(trades, table, days, cells=cl, names=sub, dtype=np.float64, chunk=1024, return_max=True)
    X = gg._daily(cl, sub, days, np.float64)
    D = len(days)
    t_obs = np.sqrt(D) * X.mean(0) / X.std(0, ddof=1)
    Xc = X - X.mean(0)
    rs = np.random.default_rng(1)
    nslow = 300
    mx = np.empty(nslow)
    for q in range(nslow):
        idx = rs.integers(0, D, size=D)
        Y = Xc[idx]
        with np.errstate(invalid="ignore", divide="ignore"):
            tt = np.sqrt(D) * Y.mean(0) / Y.std(0, ddof=1)
        mx[q] = np.nanmax(tt)
    d1 = float(np.abs(mx - r64["_mx"][:nslow]).max())
    d2 = float(np.nanmax(np.abs(t_obs - r64["_t_obs"])))
    print(f"{len(sub)} random eligible combinations, {nslow} resamples drawn the slow way (numpy mean / std of the "
          f"resampled day rows): largest difference in a resample's largest t {d1:.2e}, in an observed t {d2:.2e}")
    bad += not (d1 < 1e-9 and d2 < 1e-9)
    # the day-level series of the best combination, rebuilt from pick()
    nm = st["t_obs_max_name"]
    tr = gg.pick(trades, gg.parse(nm))
    x = np.zeros(D)
    dd = tr.day.to_numpy().astype("datetime64[D]").astype(np.int64)
    np.add.at(x, np.searchsorted(days, dd), tr.R.to_numpy())
    t1 = np.sqrt(D) * x.mean() / x.std(ddof=1)
    print(f"observed day-level t of {nm} rebuilt from pick(): {t1:.6f} (stored {st['t_obs_max']:.6f})")
    bad += not abs(t1 - st["t_obs_max"]) < 1e-9
    return bad


# ------------------------------------------------------------------ counts
def counts(ctx, trades, setups):
    pd.set_option("display.width", 250)
    gs.report(trades, setups)
    P = gs.prep(ctx)
    # the fvg flag under the other parse of the sentence (information only; not used anywhere)
    alt = {}
    for r in setups[setups.side != 0].itertuples(index=False):
        if r.K == "c1":
            s0 = r.b - 2
        else:
            tb = P.tab[gs.K_MIN[r.K]]
            s0 = int(tb["i_first"][int(np.searchsorted(tb["i_last"], r.b, "left"))]) - 2
        f = P.fvg_up if r.side > 0 else P.fvg_dn
        alt.setdefault(r.K, []).append(bool(f[s0 + 2:r.b + 1].any()))
    print("D fvg, share of breaks with the flag true:")
    for K in gs.KS:
        s = setups[(setups.side != 0) & (setups.K == K)]
        print(f"  {K}: as coded (bars of the breaking candle and of the two K candles before it) {s.d_fvg.mean() * 100:.1f} %"
              f"   [other parse, not used: bars of the breaking candle and the two 1-minute bars before it "
              f"{np.mean(alt[K]) * 100:.1f} %]")
    s = setups[setups.side != 0]
    il5 = P.tab[5]["i_last"]
    odd = {K: int((ctx.tod[s[s.K == K].b.to_numpy()] % gs.K_MIN[K] != gs.K_MIN[K] - 1).sum()) for K in ("c5", "c15")}
    print("break candles whose last 1-minute bar is not the bucket's last clock minute:", odd)
    pdx = s[(s.L == "pd")]
    w_i = np.array([P.ix(d)[gs.OPEN + 15] - 1 for d in pdx.day])
    print("pd breaks decided before the 09:30-09:44 width is known (edge x near and ext wait for it):",
          {K: int(((pdx.K == K).to_numpy() & (pdx.b.to_numpy() < w_i)).sum()) for K in gs.KS})
    first = trades[trades.which == 1]
    re_ = trades[trades.which == 2]
    print(f"first trades {len(first)}: reasons {first.reason.value_counts().to_dict()}")
    print(f"re-entries {len(re_)}: reasons {re_.reason.value_counts().to_dict()}")
    print("risk in points, first trades: " + first.risk_pts.describe(percentiles=[.01, .1, .5, .9, .99]).round(2).to_dict().__str__())
    print("risk in points, re-entries:   " + re_.risk_pts.describe(percentiles=[.01, .1, .5, .9, .99]).round(2).to_dict().__str__())
    print("R of re-entries:              " + re_.R.describe(percentiles=[.01, .1, .5, .9, .99]).round(3).to_dict().__str__())
    print("R of first trades:            " + first.R.describe(percentiles=[.01, .1, .5, .9, .99]).round(3).to_dict().__str__())
    lim = first[first.N != "conf"]
    print(f"limit fills at a better open than the limit price: {int((np.abs(lim.entry - lim.side * T - lim.entry_px) > 1e-9).sum())}"
          f" of {len(lim)} limit fills")
    half = setups[(setups.L != "pd")].drop_duplicates(["day", "L"])
    print(f"opening ranges with a half-tick midline: {int((((half.level_hi + half.level_lo) / T) % 2 == 1).sum())} of {len(half)}")
    n = trades.groupby(["L", "K", "D", "N", "S", "X"], observed=True).size()
    print("trades per cell (first trades + re-entries): " + n.describe().round(0).to_dict().__str__())


# ------------------------------------------------------------------ hand checks
def explain(ctx, d, c):
    """Walks one combination through one day with the set-up functions and says where it stops. Returns a dict
    (status, the objects along the way, the orders and the core.simulate results). Diagnostic only."""
    P = gs.prep(ctx)
    d = pd.Timestamp(d)
    day = ctx.days.loc[d]
    cut, i_end = gs.day_frame(P, d, day, gs.CUT[c["W"]])
    out = dict(cut=cut, i_end=i_end, status=None)
    lv = gs.level(P, d, day, c["L"])
    out["lv"] = lv
    if lv is None:
        return dict(out, status="no level")
    br = gs.find_break(P, lv, c["K"], cut)
    out["br"] = br
    if br is None:
        return dict(out, status="no break by the cut-off")
    out["flags"] = gs.filter_flags(P, br)
    out["fvg"] = gs.fvg_flag(P, br)
    out["ext"] = gs.ext_bar(P, lv, br.side, cut)
    if c["F"] != "none" and not out["flags"][s_G11.FLAG[c["F"]]]:
        return dict(out, status=f"rejected by the filter {c['F']}")
    if c["D"] == "fvg" and not out["fvg"]:
        return dict(out, status="rejected by fvg: no 1-minute gap in the break's direction")
    a = gs.arm_bar(P, lv, br, c["D"], cut)
    out["arm"] = a
    if a is None:
        return dict(out, status="ext: price never traded 0.7 W beyond the level by the cut-off")
    plan = gs.entry_plan(P, lv, br, c["N"], a, cut)
    out["plan"] = plan
    if plan is None:
        why = "no entry"
        if c["N"] == "zone":
            z = gs.zone_candle(P, br)
            out["zone"] = z
            why = "no demand candle within 12 candles" if z is None else (
                "the zone is not beyond the breaking candle's close: no order"
                if br.side * (br.close - (z[0] if br.side > 0 else z[1])) <= 0 else "the order could only be placed at the cut-off")
        elif c["N"] == "conf":
            lvl = lv.hi if br.side > 0 else lv.lo
            t = np.flatnonzero(P.Lt[a + 1:cut + 1] <= lvl) if br.side > 0 else np.flatnonzero(P.Ht[a + 1:cut + 1] >= lvl)
            why = "no touch of the level by the cut-off" if not len(t) else "a touch, but no confirmation candle by the cut-off"
            if len(t):
                out["touch"] = a + 1 + int(t[0])
        else:
            why = "the limit is not beyond the breaking candle's close, or could only be placed at the cut-off"
        return dict(out, status=why)
    st = gs.stop_ticks(lv, br.side, c["N"], c["S"], plan)
    out["stop_t"] = st
    o = gs.first_order(br.side, plan, st, c["X"], cut, i_end)
    out["o1"] = o
    if o is None:
        return dict(out, status=f"not placed: the stop {st * T} is less than 2 ticks beyond the entry price {plan['px'] * T}")
    t1 = core.simulate(ctx, **o)
    out["t1"] = t1
    if t1 is None:
        why = "the limit did not fill by the cut-off"
        if o["etype"] == "limit":
            s, px = br.side, o["price"]
            for k in range(o["i"] + 1, cut + 1):
                opened_through_stop = s * (ctx.O[k] - o["stop"]) <= 0
                reached = (ctx.L[k] <= px) if s > 0 else (ctx.H[k] >= px)
                if opened_through_stop:
                    why = f"the limit was cancelled: bar {ctx.ts[k].strftime('%H:%M')} opened at {ctx.O[k]}, at / through the stop"
                    out["cancel_bar"] = k
                    break
                if reached:
                    why = "?"
                    break
        return dict(out, status=why)
    out["status"] = "first trade"
    if c["E"] == "re":
        o2 = gs.reentry_order(P, lv, c["K"], br.side, t1, o, cut)
        out["o2"] = o2
        if o2 is not None:
            out["t2"] = core.simulate(ctx, **o2)
            out["status"] = "first trade and re-entry"
        elif t1["reason"] == "SL" and t1["k"] <= cut:
            i2 = gs.reentry_bar(P, lv, c["K"], br.side, int(t1["k"]), cut)
            out["re_bar"] = i2
            out["status"] = "first trade; " + ("no candle closed back beyond the level by the cut-off" if i2 is None
                                               else f"re-entry candle {ctx.ts[i2].strftime('%H:%M')} close {ctx.C[i2]} skipped (within 2 ticks of the stop, or at / beyond the target)")
    return out


def _bars(ctx, lo, hi, mark=None):
    mark = mark or {}
    for k in range(lo, hi + 1):
        print(f"      {ctx.ts[k].strftime('%H:%M')}  O {ctx.O[k]:>9.2f}  H {ctx.H[k]:>9.2f}  L {ctx.L[k]:>9.2f}  C {ctx.C[k]:>9.2f}"
              f"  V {int(ctx.V[k]):>5}" + (f"   <- {mark[k]}" if k in mark else ""))


def show(ctx, d, cname, title="", bars=True, profile=False, extra_bars=3):
    c = gg.parse(cname)
    P = gs.prep(ctx)
    d = pd.Timestamp(d)
    x = explain(ctx, d, c)
    hm = lambda k: ctx.ts[k].strftime("%H:%M")
    print(f"\n=== {title}\n    {d.date()}  {cname}")
    lv, br = x.get("lv"), x.get("br")
    if lv is None:
        print("    ", x["status"]); return x
    ix = P.ix(d)
    print(f"    level {c['L']}: high {lv.hi * T} low {lv.lo * T}  W {lv.W * T}  midline {lv.mid2 * T / 2}"
          + (f"  (range bars {hm(lv.s_lo)}-{hm(lv.s_hi - 1)})" if c["L"] != "pd" else f"  (previous session {ctx.days.index[ctx.days.index.get_loc(d) - 1].date()}; W = 09:30-09:44 width)"))
    if br is None:
        print("    ", x["status"]); return x
    mark = {}
    side = br.side
    print(f"    break {c['K']}: candle ending {hm(br.b)} closes {br.close * T} -> {'long' if side > 0 else 'short'}")
    f = x["flags"]
    j5 = int(np.searchsorted(P.tab[5]["i_last"], br.b, "right")) - 1
    print(f"    at the break: EMA200(5m) {P.ema200[j5]:.2f}  EMA9 {P.ema9[j5]:.2f}  EMA21 {P.ema21[j5]:.2f}  (5m bar ending "
          f"{hm(int(P.tab[5]['i_last'][j5]))})  VWAP {P.vwap[br.b]:.2f}  -> f_ema200 {f[0]}  f_vwap {f[1]}  f_ema921 {f[2]};"
          f"  fvg {x['fvg']};  0.7 W excursion bar " + ("none by the cut-off" if x["ext"] is None else hm(x["ext"])))
    mark[br.b] = "break candle ends"
    if x["ext"] is not None and c["D"] == "ext":
        mark[x["ext"]] = mark.get(x["ext"], "") + " excursion known"
    plan = x.get("plan")
    if plan is not None:
        if plan["kind"] == "close":
            mark[plan["touch"]] = mark.get(plan["touch"], "") + " touch"
            mark[plan["i"]] = mark.get(plan["i"], "") + " confirmation, entry at close"
            print(f"    conf: touch {hm(plan['touch'])}, confirmation {hm(plan['i'])} close {plan['px'] * T}, pullback extreme {plan['pull'] * T}")
        else:
            mark[plan["i"]] = mark.get(plan["i"], "") + " order placed at close"
            print(f"    limit {c['N']} at {plan['px'] * T}, placed at the close of {hm(plan['i'])}"
                  + (f"; zone candle {plan['zone_min']}m high {plan['zone_hi'] * T} low {plan['zone_lo'] * T}" if "zone_hi" in plan else ""))
    if c["N"] == "zone":
        z = gs.zone_candle(P, br)
        if z is not None:
            if z[3] == 1:
                print(f"    zone candle: 1-minute bar {hm(z[2])} high {z[0] * T} low {z[1] * T}")
            else:
                tb = P.tab[5]
                print(f"    zone candle: 5-minute candle {hm(int(tb['i_first'][z[2]]))}-{hm(int(tb['i_last'][z[2]]))} open {tb['o'][z[2]] * T}"
                      f" high {z[0] * T} low {z[1] * T} close {tb['c'][z[2]] * T}")
    if c["L"] != "pd" and (c["N"] == "poc" or profile):
        poc, val, vah, base, prof, den = lv.prof
        tot = sum(prof)
        inside = sum(prof[val - base:vah - base + 1])
        print(f"    profile of {hm(lv.s_lo)}-{hm(lv.s_hi - 1)}: poc {poc * T} ({prof[poc - base] / den:.2f} contracts)  value area "
              f"{val * T} .. {vah * T} holds {inside / tot * 100:.2f} % of {tot // den} contracts")
        if profile:
            for q in range(len(prof) - 1, -1, -1):
                px = base + q
                tag = "POC" if px == poc else ("VA" if val <= px <= vah else "")
                print(f"        {px * T:>9.2f}  {prof[q] / den:>9.3f}  {tag}")
    if x.get("o1") is not None:
        o = x["o1"]
        print(f"    order: {o['etype']} " + (f"at {o['price']} " if o["etype"] == "limit" else f"at the close of {hm(o['i'])} ")
              + f"stop {o['stop']}  target {o['target']}")
    for w in ("t1", "t2"):
        t = x.get(w)
        if t is not None:
            print(f"    {'first trade' if w == 't1' else 're-entry  '}: entry {hm(t['j'])} fill {t['entry']}  exit {hm(t['k'])} {t['exit']}"
                  f" ({t['reason']})  pnl {t['pnl']:+.2f}  R {t['R']:+.4f}  risk {t['risk_pts']}")
            mark[t["j"]] = mark.get(t["j"], "") + (" fill" if w == "t1" else " re-entry at close")
            mark[t["k"]] = mark.get(t["k"], "") + f" exit {t['reason']}"
    if "cancel_bar" in x:
        mark[x["cancel_bar"]] = "opens at / through the stop: limit cancelled"
    if "re_bar" in x and x["re_bar"] is not None:
        mark[x["re_bar"]] = "re-entry candle (skipped)"
    print("    ->", x["status"])
    if bars:
        last = max([k for k in mark if k <= x["cut"] + 400] + [br.b])
        lo = ix[570]
        hi_ = min(last + extra_bars, x["i_end"])
        segs = [(lo, min(hi_, lo + 400))]
        _bars(ctx, segs[0][0], segs[0][1], mark)
    return x


HAND = [
    # (title, day or None = drawn, combination, what to look for)
]


def _find(ctx, trades, setups, cname, want, rng, tries=4000):
    """A day, drawn at random (rng), on which explain() of the combination satisfies want(x)."""
    c = gg.parse(cname)
    days = gs.traded_days(ctx)
    for q in rng.permutation(len(days))[:tries]:
        x = explain(ctx, days[q], c)
        if want(x):
            return days[q]
    return None


def hand(ctx, trades, setups):
    """One seeded draw (numpy.default_rng(2026)) per description; prints the facts and the bars."""
    rng = np.random.default_rng(2026)
    st = lambda *w: (lambda x: x["status"] is not None and all(v in x["status"] for v in w))
    def has(key, reason=None, which="t1"):
        return lambda x: x.get(which) is not None and (reason is None or x[which]["reason"] == reason)
    cases = [
        ("1. or5, c1, D none, edge x near (0.25 W), 1.5R: a limit fill at the broken level",
         "Lor5.Kc1.Dnone.Nedge.Snear.X1.5R.W11.Eone.Fnone", has("t1"), {}),
        ("2. or15, c1, D fvg true, conf x near, hold, re-entry taken (pick 1)",
         "Lor15.Kc1.Dfvg.Nconf.Snear.Xhold.W11.Ere.Fema200", lambda x: x.get("t2") is not None, {}),
        ("3. or30, c15, D ext, zone (5-minute demand candle) x near, 3R",
         "Lor30.Kc15.Dext.Nzone.Snear.X3R.W12.Eone.Fnone", has("t1"), {}),
        ("4. pd, c5, conf x near, hold to the flat bar",
         "Lpd.Kc5.Dnone.Nconf.Snear.Xhold.W12.Eone.Fnone", has("t1", "time"), {}),
        ("5. or5, c5, poc x near (value-area low): the profile, point of control and value area",
         "Lor5.Kc5.Dnone.Npoc.Snear.X3R.W11.Eone.Fnone", has("t1"), {"profile": True}),
        ("6. or15, c15, poc x far stop, 1.5R target hit",
         "Lor15.Kc15.Dnone.Npoc.Sfar.X1.5R.W12.Eone.Fnone", has("t1", "TP"), {}),
        ("7. or30, c5, edge x mid stop, 2R",
         "Lor30.Kc5.Dnone.Nedge.Smid.X2R.W12.Eone.Fnone", has("t1"), {}),
        ("8. or15, c1, D ext, mid entry x near (midline - 0.25 W), order placed only once the excursion has traded",
         "Lor15.Kc1.Dext.Nmid.Snear.X2R.W12.Eone.Fnone", lambda x: x.get("t1") is not None and x["arm"] > x["br"].b, {}),
        ("9. a day rejected by fvg (c1: the breaking bar and the two before it leave no gap)",
         "Lor15.Kc1.Dfvg.Nconf.Snear.Xhold.W11.Ere.Fema200", st("rejected by fvg"), {"extra_bars": 2}),
        ("10. a day rejected by ext: price never trades 0.7 W beyond the level by the cut-off",
         "Lor15.Kc5.Dext.Nedge.Snear.X2R.W12.Eone.Fnone", st("never traded 0.7 W"), {"bars": False}),
        ("11. ext: a pullback that completes before the excursion is not an entry (the D none twin trades earlier)",
         "Lor5.Kc5.Dext.Nconf.Snear.X2R.W12.Eone.Fnone",
         lambda x: x.get("t1") is not None and x["arm"] > x["br"].b + 3, {}),
        ("12. a filter rejection: the break closes on the wrong side of the EMA(200)",
         "Lor15.Kc1.Dfvg.Nconf.Snear.Xhold.W11.Ere.Fema200", st("rejected by the filter"), {"bars": False}),
        ("13a. a limit cancelled because the stop price traded first (pd edge: placed once W is known, price already through the stop)",
         "Lpd.Kc1.Dnone.Nedge.Snear.X2R.W12.Eone.Fnone", st("cancelled"), {"extra_bars": 2}),
        ("13b. the same on an opening-range level (the only such day in sample, found by scanning every day)",
         "Lor15.Kc15.Dnone.Nedge.Snear.X2R.W12.Eone.Fnone", st("cancelled"), {"extra_bars": 2}),
        ("14. an order not placed because the stop is too close (poc entry with the mid stop)",
         "Lor15.Kc5.Dnone.Npoc.Smid.X2R.W12.Eone.Fnone", st("not placed"), {"bars": False}),
        ("15. zone above the breaking candle's close: no trade",
         "Lor5.Kc1.Dnone.Nzone.Snear.X2R.W12.Eone.Fnone", st("not beyond the breaking"), {"extra_bars": 1}),
        ("16. pd, c1, D ext, edge x near: break before 09:45, the order waits for W and for the excursion; re-entry rule",
         "Lpd.Kc1.Dext.Nedge.Snear.X2R.W12.Ere.Fnone",
         lambda x: x.get("t1") is not None and x["br"].b < x["lv"].w_i, {}),
        ("17. re-entry skipped: the reclaim close is within 2 ticks of the stop or beyond the target",
         "Lor15.Kc5.Dnone.Nconf.Snear.X1.5R.W12.Ere.Fnone", st("skipped"), {}),
        ("18. pick 6: or5, c1, fvg, zone (1-minute demand candle) x mid stop, hold, with a re-entry",
         "Lor5.Kc1.Dfvg.Nzone.Smid.Xhold.W12.Ere.Fnone", lambda x: x.get("t2") is not None, {}),
        ("19. pick 4: or5, c15, ext, mid x near, hold, ema921",
         "Lor5.Kc15.Dext.Nmid.Snear.Xhold.W12.Eone.Fema921", has("t1"), {}),
        ("20. short side: or30, c1, conf x far stop, 3R",
         "Lor30.Kc1.Dnone.Nconf.Sfar.X3R.W12.Eone.Fnone", lambda x: x.get("t1") is not None and x["br"].side < 0, {}),
    ]
    base = s_G11.VARIANTS["base"]["c"]
    fixed = {"21. base (pick 1), a trade printed by run.py --show: 2019-09-11": "2019-09-11",
             "22. base (pick 1), a trade printed by run.py --show: 2022-07-27 (held to the flat bar)": "2022-07-27",
             "23. base (pick 1), a trade printed by run.py --show: 2022-09-09 (the re-entry)": "2022-09-09"}
    cases += [(t, base, None, {}) for t in fixed]
    # The days of cases 1-20 were drawn once with numpy.default_rng(2026) (one draw per description, in this order;
    # 13a / 13b after the first version of 13 found no day) and are written down here so that the notes and this
    # print-out stay the same when a case is added. 13b is the only such day in sample (found by scanning every day).
    DAYS = {"1.": "2022-08-25", "2.": "2022-02-08", "3.": "2020-12-28", "4.": "2021-11-09", "5.": "2020-08-27",
            "6.": "2021-12-15", "7.": "2019-07-03", "8.": "2020-12-01", "9.": "2022-05-02", "10.": "2022-07-01",
            "11.": "2022-07-01", "12.": "2020-08-24", "13a.": "2020-07-14", "13b.": "2022-11-11", "14.": "2021-01-18",
            "15.": "2021-05-17", "16.": "2021-08-19", "17.": "2020-07-09", "18.": "2022-05-10", "19.": "2022-05-30",
            "20.": "2021-05-05"}
    for title, cname, want, kw in cases:
        tag = title.split(" ")[0]
        if title in fixed:
            d = pd.Timestamp(fixed[title])
        elif tag in DAYS:
            d = pd.Timestamp(DAYS[tag])
            assert want(explain(ctx, d, gg.parse(cname))), f"case {tag}: the day does not show what the title says"
        else:
            d = _find(ctx, trades, setups, cname, want, rng)
        if d is None:
            print(f"\n=== {title}\n    no such day found for {cname}")
            continue
        x = show(ctx, d, cname, title, **kw)
        # the file must hold exactly these trades
        c = gg.parse(cname)
        g = gg.pick(trades, c)
        g = g[g.day == pd.Timestamp(d)]
        want_n = int(x.get("t1") is not None) + int(x.get("t2") is not None)
        okf = len(g) == want_n and all(abs(float(g.pnl.iloc[q]) - x[w]["pnl"]) < 1e-9
                                       for q, w in enumerate([w for w in ("t1", "t2") if x.get(w) is not None]))
        print(f"    trade file: {len(g)} trade(s) of this combination on this day" + (" (same pnl)" if okf and want_n else "")
              + ("" if okf else "   <-- DIFFERS"))
        if c["D"] == "ext" and x.get("t1") is not None:
            tw = dict(c, D="none")
            y = explain(ctx, d, tw)
            if y.get("t1") is not None:
                print(f"    D none twin: decision bar {ctx.ts[y['o1']['i']].strftime('%H:%M')}, entry {ctx.ts[y['t1']['j']].strftime('%H:%M')} "
                      f"at {y['t1']['entry']}, stop {y['o1']['stop']}")
            else:
                print("    D none twin:", y["status"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", choices=["is", "full"], default="is")
    ap.add_argument("--eq11", action="store_true")
    ap.add_argument("--eq11-days", type=int, default=0)
    ap.add_argument("--recon", action="store_true")
    ap.add_argument("--neg", action="store_true")
    ap.add_argument("--slow", type=int, default=0)
    ap.add_argument("--rc", action="store_true")
    ap.add_argument("--counts", action="store_true")
    ap.add_argument("--hand", action="store_true")
    ap.add_argument("--show", nargs=2, metavar=("DAY", "COMBINATION"), help="explain one combination on one day")
    a = ap.parse_args()
    pd.set_option("display.width", 250)
    A = run.bars(a.phase)
    ctx = core.Ctx(A)
    trades, setups = pd.read_parquet(gs.path(a.phase)), pd.read_parquet(gs.path(a.phase, "setups"))
    bad = 0
    if a.counts:
        counts(ctx, trades, setups)
    if a.hand:
        hand(ctx, trades, setups)
    if a.show:
        show(ctx, a.show[0], a.show[1], "explain", profile=True)
    if a.slow:
        bad += slow(ctx, setups, trades, a.slow)
    if a.eq11:
        bad += eq11(ctx, trades, a.eq11_days)
    if a.recon:
        bad += recon(ctx, trades)
    if a.rc:
        bad += rc_checks(trades, setups)
    if a.neg:
        bad += negative(run.bars("is"))
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
