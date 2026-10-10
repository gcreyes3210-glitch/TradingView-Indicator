#!/usr/bin/env python3
"""LEV2 levels (YT10_SPEC.md): the hourly opens of MID1 and the volume-profile levels of VPN1, every level fixed from
bars at or before its own `t_set`. Built on lev1_levels (profile / profile_pine = Aceflw_Levels.pine's profile, the
trading weeks, the watch window, the placebo shift and distances).

    mid_levels(ctx)     one row per cash day x hourly open (o19 .. o23, o00, o01 .. o07) and the two placebos of o00
    vp_levels(ctx)      one row per cash day x profile level (13 profiles x vah / poc / val), their placebos, and the
                        aligned-POC levels apoc_rth / apoc_eth        (profs=[...]: only those profiles, no placebos)
    day_types(ctx)      one row per cash day: the five VAH / VAL of rth1..5 and eth1..5 and the aligned-value day type
    status(ctx)         one row per cash day x profile: built or why not, the sessions used

MID1. o<HH> = the open of the first 1-minute bar at or after HH:00 New York (19:00 .. 23:00 on the calendar day before
the cash day, 00:00 .. 07:00 on it) and before the 09:30 bar; `exact` = that bar is stamped HH:00, `late_min` = how
many minutes after HH:00 it is. Placebo of o00: o00 +/- 0.12 x ATR, dropped if within 0.03 x ATR of any hourly open.

VPN1 profiles (lev1_levels.profile over the concatenated 1-minute bars of the sessions, in time order: one profile on
the common 1-point grid):
    rth1 .. rth5   the last 1 .. 5 regular sessions (bars 09:30-15:59 of a calendar date) before today
    eth1 .. eth5   the last 1 .. 5 full sessions (bars 18:00-16:59 of a trading date) before today's trading date
                   a session with fewer than half its minutes (195 / 690 bars) is skipped over, the next earlier used
    rthw, ethw     every regular / full session of the previous trading week (lev1_levels._weeks), short ones included
    on             tonight, 18:00-09:29, exactly lev1's overnight profile
    A profile is not built when any of its bars is another contract than today's 09:30 bar (a roll inside its
    sessions or between them and today), when there are not enough earlier sessions, or when the script would not
    compute one (rows <= 2 or no volume).
Level codes <profile>_<vah|poc|val>; placebo '<code>~' with inst '+' / '-': the level +/- 0.12 x ATR, dropped if
within 0.03 x ATR of any of the day's real profile levels. apoc_rth / apoc_eth: on a day when the five POCs of
rth1..5 (eth1..5) span at most 0.06 x ATR, their mean rounded to the tick.

COLUMNS (lev1's, plus)
    date code inst lid group kind value t_set open_set w0 w1 b0 b1 is_placebo parent used dropped near_later atr
    t_set     bar at whose CLOSE the level is fixed (open_set=True: at the OPEN of bar t_set). A profile: its last bar.
              A placebo / aligned-POC level: the later of that and the bar that fixes the day's ATR (last bar < 18:00)
    t_end     the bar `crossed` is measured from: the profile's last bar / the hourly open's bar (a placebo: its parent's)
    crossed   (= used) price traded strictly on both sides of the level between t_end and the 09:29 bar
    VPN1: prof, N (1..5; 0 for rthw / ethw / on), stype (rth / eth / on), level, sessions ('|'-joined dates), n_sess,
          nbars, vol (profile volume), nrows.         MID1: hour (HHMM), exact, late_min

    python3 tools/yt1/lev2_levels.py --check        the unit checks quoted in notes/LEV2.md
    python3 tools/yt1/lev2_levels.py --causal 190   every sampled level recomputed (a) with the future after its own
                                                    t_set mirrored, (b) with the bars between t_set and 09:30 removed
"""
import argparse, pathlib, sys, time
import numpy as np
import pandas as pd
sys.path.insert(0, str(pathlib.Path(__file__).parent))
import core
import lev1_levels as LL

TICK = core.TICK
PLACEBO_S, NEAR = LL.PLACEBO_S, LL.NEAR                 # 0.12 and 0.03 x ATR, as YT9
OPEN_TOD, WATCH_END = LL.OPEN_TOD, LL.WATCH_END         # 09:30; last watched bar 15:00
ALIGN = 0.06                                            # aligned POCs: max - min <= 0.06 x ATR
HOURS = (19, 20, 21, 22, 23, 0, 1, 2, 3, 4, 5, 6, 7)
MID_CODES = [f"o{h:02d}" for h in HOURS]
MID = "o00"
NS = (1, 2, 3, 4, 5)
PROFS = [f"rth{n}" for n in NS] + [f"eth{n}" for n in NS] + ["rthw", "ethw", "on"]
LEVELS = ("vah", "poc", "val")
VP_CODES = [f"{p}_{l}" for p in PROFS for l in LEVELS]
APOC = ("apoc_rth", "apoc_eth")
RTH_HALF, ETH_HALF = 390 // 2, 1380 // 2                # a session with fewer bars than this is skipped over
ONE = pd.Timedelta(days=1)
W = core.Ctx._wall

BASE_COLS = ["date", "code", "inst", "group", "kind", "value", "t_set", "open_set", "w0", "w1", "b0", "b1",
             "is_placebo", "parent", "used", "dropped", "near_later", "atr", "t_end", "crossed"]
VP_COLS = BASE_COLS + ["prof", "N", "stype", "level", "sessions", "n_sess", "nbars", "vol", "nrows"]
MID_COLS = BASE_COLS + ["hour", "exact", "late_min"]


def family(prof):
    """Profile family: rth (rth1..5, rthw), eth (eth1..5, ethw), on."""
    return prof[:3] if prof[:3] in ("rth", "eth") else prof.split("_")[-1] if prof.startswith("apoc") else "on"


def n_of(prof):
    return int(prof[3]) if prof[3:].isdigit() else 0


def _cache(ctx):
    return ctx.__dict__.setdefault("_lev2", {})


def _crossed(ctx, value, t_end, open_set, i_open, memo):
    """Price traded strictly on both sides of `value` between the level's set time and the 09:29 bar (lev1's `used`:
    the price at the set time counts as the starting side)."""
    if t_end >= i_open:
        return False
    k = (t_end, open_set)
    if k not in memo:
        a = t_end + (0 if open_set else 1)
        ps = ctx.O[t_end] if open_set else ctx.C[t_end]
        memo[k] = (min(ctx.L[a:i_open].min(), ps), max(ctx.H[a:i_open].max(), ps)) if a < i_open else (ps, ps)
    lo, hi = memo[k]
    return bool(lo < value < hi)


def _finish(rows, cols):
    lv = pd.DataFrame(rows, columns=cols)
    lv.insert(3, "lid", lv.code + np.where(lv.inst != "", "." + lv.inst, ""))
    return lv


# ------------------------------------------------------------------ MID1: the hourly opens
def mid_levels(ctx):
    c = _cache(ctx)
    if "mid" in c:
        return c["mid"]
    O, ts = ctx.O, ctx.ts
    D = ctx.days
    rows = []
    for d, i_open, i_end, atr in zip(D.index, D.i_open.to_numpy(), D.i_end.to_numpy(), D.atr.to_numpy()):
        i_open, i_end = int(i_open), int(i_end)
        w1 = min(ctx.span(d, OPEN_TOD, WATCH_END + 1)[1] - 1, i_end)
        on0 = ctx.span(d - ONE, 1080, 1440)[0]
        memo, real = {}, []
        for h, code in zip(HOURS, MID_CODES):
            t = W(d - ONE if h >= 19 else d, h * 60)
            k = int(ts.searchsorted(t, "left"))               # the first bar at or after HH:00 ...
            if k >= i_open:                                   # ... and before the 09:30 bar
                continue
            late = int((ts[k] - t) / pd.Timedelta(minutes=1))
            v = float(O[k])
            cr = _crossed(ctx, v, k, True, i_open, memo)
            real.append((code, v, k, late))
            rows.append((d, code, "", "hourly open", "static", v, k, True, i_open, w1, -1, -1, False, "", cr, False,
                         False, atr, k, cr, h * 100, late == 0, late))
        if atr == atr:
            vals = np.array([r[1] for r in real])
            for code, v, k, late in real:
                if code != MID:
                    continue
                for sign, sg in ((1.0, "+"), (-1.0, "-")):
                    f = v + sign * PLACEBO_S * atr
                    dropped = bool((np.abs(vals - f) <= NEAR * atr).any())
                    ts_f, os_f = (k, True) if k >= on0 - 1 else (on0 - 1, False)
                    cr = _crossed(ctx, f, k, True, i_open, memo)
                    rows.append((d, code + "~", sg, "hourly open", "static", f, ts_f, os_f, i_open, w1, -1, -1, True,
                                 code, cr, dropped, False, atr, k, cr, 0, late == 0, late))
    c["mid"] = _finish(rows, MID_COLS)
    return c["mid"]


# ------------------------------------------------------------------ VPN1: sessions and profiles
def sessions(ctx):
    """{'rth': frame, 'eth': frame}, one row per session: key (calendar date / trading date, datetime64[D]), lo, hi
    (bars [lo, hi)), n, iid (the contract when the session holds one, else -1), wk (trading week id), ok (not short).
    rth = bars 09:30-15:59 of a calendar date; eth = bars 18:00-16:59 of a trading date (ctx.tdate)."""
    c = _cache(ctx)
    if "sess" in c:
        return c["sess"]
    tod, pos = ctx.tod, np.arange(ctx.n)
    out = {}
    for name, mask, key, half in (("rth", (tod >= OPEN_TOD) & (tod < 960), ctx.cdate, RTH_HALF),
                                  ("eth", (tod >= 1080) | (tod < 1020), ctx.tdate, ETH_HALF)):
        p, k = pos[mask], key[mask]
        u, first = np.unique(k, return_index=True)
        last = np.r_[first[1:], len(p)] - 1
        lo, hi = p[first], p[last] + 1
        assert ((hi - lo) == (last - first + 1)).all(), "a session's bars are not contiguous"
        iid = np.array([int(ctx.iid[a]) if (ctx.iid[a:b] == ctx.iid[a]).all() else -1 for a, b in zip(lo, hi)])
        dn = u.astype("datetime64[D]").astype("int64")
        out[name] = pd.DataFrame({"key": u.astype("datetime64[D]"), "dn": dn, "lo": lo, "hi": hi, "n": hi - lo,
                                  "iid": iid, "wk": (dn + 3) // 7, "ok": (hi - lo) >= half})
    c["sess"] = out
    return out


def composite(ctx, spans):
    """The script's profile over the bars of `spans` ([lo, hi) pairs in time order) taken as one bar series."""
    c = _cache(ctx).setdefault("pf", {})
    key = tuple(spans)
    if key not in c:
        if len(spans) == 1:
            lo, hi = spans[0]
            h, l, v = ctx.H[lo:hi], ctx.L[lo:hi], ctx.V[lo:hi]
        else:
            h, l, v = (np.concatenate([x[lo:hi] for lo, hi in spans]) for x in (ctx.H, ctx.L, ctx.V))
        c[key] = LL.profile(h, l, v)
    return c[key]


def _plan(ctx, profs):
    """For every cash day and wanted profile: (status, spans, session dates). status 'ok' or the reason it is not
    built ('history' = not enough earlier sessions, 'roll', 'none' = no bars)."""
    S = sessions(ctx)
    wk_id = LL._weeks(ctx)[0]
    D = ctx.days
    tab = {}
    for st in ("rth", "eth"):
        s = S[st]
        okx = np.flatnonzero(s.ok.to_numpy())
        tab[st] = dict(dn=s.dn.to_numpy(), lo=s.lo.to_numpy(), hi=s.hi.to_numpy(), iid=s.iid.to_numpy(),
                       wk=s.wk.to_numpy(), okx=okx, okdn=s.dn.to_numpy()[okx], key=s.key.to_numpy())
    plan = {}
    for d, i_open in zip(D.index, D.i_open.to_numpy()):
        i_open = int(i_open)
        dn = int(np.datetime64(d, "D").astype("int64"))
        iid0 = int(ctx.iid[i_open])
        day = {}
        for prof in profs:
            st = prof[:3] if prof != "on" else "on"
            if st == "on":
                on0 = ctx.span(d - ONE, 1080, 1440)[0]
                if not i_open > on0:
                    day[prof] = ("none", (), ())
                elif not (ctx.iid[on0:i_open] == iid0).all():
                    day[prof] = ("roll", ((on0, i_open),), (str(d.date()),))
                else:
                    day[prof] = ("ok", ((on0, i_open),), (str(d.date()),))
                continue
            t = tab[st]
            if prof.endswith("w"):                               # every session of the previous trading week
                p = int(np.searchsorted(wk_id, (dn + 3) // 7, "left")) - 1
                sel = np.flatnonzero(t["wk"] == wk_id[p]) if p >= 0 else np.zeros(0, int)
            else:                                                # the last N sessions that are not short
                n = n_of(prof)
                p = int(np.searchsorted(t["okdn"], dn, "left"))
                sel = t["okx"][p - n:p] if p >= n else np.zeros(0, int)
            if len(sel) == 0:
                day[prof] = ("history", (), ())
                continue
            spans = tuple((int(t["lo"][k]), int(t["hi"][k])) for k in sel)
            dates = tuple(str(t["key"][k])[:10] for k in sel)
            day[prof] = ("ok" if (t["iid"][sel] == iid0).all() else "roll", spans, dates)
        plan[d] = day
    return plan


def _vp(ctx, profs, placebos):
    D = ctx.days
    plan = _plan(ctx, profs)
    rows, stat = [], []
    for d, i_open, i_end, atr in zip(D.index, D.i_open.to_numpy(), D.i_end.to_numpy(), D.atr.to_numpy()):
        i_open, i_end = int(i_open), int(i_end)
        w1 = min(ctx.span(d, OPEN_TOD, WATCH_END + 1)[1] - 1, i_end)
        on0 = ctx.span(d - ONE, 1080, 1440)[0]
        memo, real, pocs = {}, [], {}
        for prof in profs:
            status, spans, dates = plan[d][prof]
            pf = composite(ctx, spans) if status == "ok" else None
            if status == "ok" and pf is None:
                status = "empty"
            ses = "|".join(dates)
            stat.append((d, prof, status, ses, len(spans)))
            if pf is None:
                continue
            t_end = spans[-1][1] - 1
            nb = sum(b - a for a, b in spans)
            meta = (prof, n_of(prof), family(prof), None, ses, len(spans), nb, pf["vol"], pf["n"])
            pocs[prof] = (pf["poc"], t_end, meta)
            for lvl in LEVELS:
                v = float(pf[lvl])
                cr = _crossed(ctx, v, t_end, False, i_open, memo)
                m = meta[:3] + (lvl,) + meta[4:]
                real.append((f"{prof}_{lvl}", v, t_end, m))
                rows.append((d, f"{prof}_{lvl}", "", family(prof), "static", v, t_end, False, i_open, w1, -1, -1, False,
                             "", cr, False, False, atr, t_end, cr) + m)
        if not (atr == atr):
            continue
        t_atr = on0 - 1                                          # the bar that fixes the day's ATR
        if placebos:
            vals = np.array([r[1] for r in real])
            for code, v, t_end, m in real:
                for sign, sg in ((1.0, "+"), (-1.0, "-")):
                    f = v + sign * PLACEBO_S * atr
                    dropped = bool((np.abs(vals - f) <= NEAR * atr).any())
                    cr = _crossed(ctx, f, t_end, False, i_open, memo)
                    rows.append((d, code + "~", sg, m[2], "static", f, max(t_end, t_atr), False, i_open, w1, -1, -1,
                                 True, code, cr, dropped, False, atr, t_end, cr) + m)
        for st in ("rth", "eth"):                                # aligned points of control
            ps = [pocs.get(f"{st}{n}") for n in NS]
            if any(p is None for p in ps):
                continue
            pv = np.array([p[0] for p in ps])
            if pv.max() - pv.min() <= ALIGN * atr:
                v = float(core.tick_round(float(pv.mean())))
                t_end = max(p[1] for p in ps)
                cr = _crossed(ctx, v, t_end, False, i_open, memo)
                m5 = ps[-1][2]
                rows.append((d, f"apoc_{st}", "", "aligned POC", "static", v, max(t_end, t_atr), False, i_open, w1, -1,
                             -1, False, "", cr, False, False, atr, t_end, cr, f"apoc_{st}", 5, st, "poc", m5[4], m5[5],
                             m5[6], np.nan, 0))
    lv = _finish(rows, VP_COLS)
    st = pd.DataFrame(stat, columns=["date", "prof", "status", "sessions", "n_sess"])
    return lv, st


def vp_levels(ctx, profs=None):
    """profs=None: all 13 profiles, the placebos and the aligned-POC levels. profs=[...]: only those profiles'
    levels (identical rows), no placebos; an aligned-POC level only when its five profiles are among them."""
    c = _cache(ctx)
    key = ("vp", None if profs is None else tuple(profs))
    if key not in c:
        c[key] = _vp(ctx, PROFS if profs is None else [p for p in PROFS if p in set(profs)], profs is None)
    return c[key][0]


def status(ctx):
    vp_levels(ctx)
    return _cache(ctx)[("vp", None)][1]


def day_types(ctx, at_open=True):
    """One row per cash day: p0 (the 09:30 open; at_open=False: the last close before it), atr, vah_<prof> / val_<prof>
    / poc_<prof> for rth1..5 and eth1..5, and the aligned-value day type
        type_rth, type_eth   'above' p0 > all five VAHs, 'below' p0 < all five VALs, 'inside' VAL <= p0 <= VAH for all
                             five, 'mixed' otherwise, '' when one of the five profiles is not built
        type_rth3            the same on rth1..3 only (the VA-trend neighbour)."""
    c = _cache(ctx)
    key = ("dt", bool(at_open))
    if key in c:
        return c[key]
    full = ("vp", None)
    want = [f"{st}{n}" for st in ("rth", "eth") for n in NS]
    lv = c[full][0] if full in c else vp_levels(ctx, want)
    x = lv[~lv.is_placebo & lv.prof.isin(want)]
    D = ctx.days
    out = pd.DataFrame({"p0": LL.pstart(ctx, at_open)[D.i_open.to_numpy()], "atr": D.atr.to_numpy()}, index=D.index)
    pv = x.pivot(index="date", columns="code", values="value").reindex(D.index)
    for p in want:
        for l in LEVELS:
            out[f"{l}_{p}"] = pv[f"{p}_{l}"].to_numpy() if f"{p}_{l}" in pv else np.nan
    p0 = out.p0.to_numpy()
    for name, st, ns in (("type_rth", "rth", NS), ("type_eth", "eth", NS), ("type_rth3", "rth", NS[:3])):
        vah = np.column_stack([out[f"vah_{st}{n}"].to_numpy() for n in ns])
        val = np.column_stack([out[f"val_{st}{n}"].to_numpy() for n in ns])
        built = ~(np.isnan(vah).any(axis=1) | np.isnan(val).any(axis=1) | np.isnan(p0))
        with np.errstate(invalid="ignore"):
            above = (p0[:, None] > vah).all(axis=1)
            below = (p0[:, None] < val).all(axis=1)
            inside = ((p0[:, None] >= val) & (p0[:, None] <= vah)).all(axis=1)
        out[name] = np.where(~built, "", np.where(above, "above", np.where(below, "below", np.where(inside, "inside", "mixed"))))
    c[key] = out
    return out


def ok_days(ctx):
    return LL.ok_days(ctx)


# ------------------------------------------------------------------ counts and unit checks
def counts(ctx):
    ok = set(ok_days(ctx))
    nd = len(ok)
    out = [f"study days {nd} (cash days {len(ctx.days)}, roll day or the day after {len(ctx.roll2_dates)}, "
           f"no ATR {len(ctx.noatr_dates)})"]
    m = mid_levels(ctx)
    ms = m[m.date.isin(ok)]
    r = ms[~ms.is_placebo]
    g = r.groupby("code", sort=False)
    out.append("MID1 hourly opens on study days: " + ", ".join(
        f"{c_} {len(x)} (exact bar missing {int((~x.exact).sum())}" + (f", latest by {int(x.late_min.max())} min" if (~x.exact).any() else "")
        + ")" for c_, x in ((c_, g.get_group(c_)) for c_ in MID_CODES if c_ in g.groups)))
    late = r[~r.exact]
    out.append(f"  hourly opens taken from a later bar: {len(late)} of {len(r)} level-days; late by 1-5 min "
               f"{int((late.late_min <= 5).sum())}, 6-59 min {int(((late.late_min > 5) & (late.late_min < 60)).sum())}, "
               f"60 min or more {int((late.late_min >= 60).sum())} (then equal to a later hour's open); crossed before "
               f"09:30: {int(r.crossed.sum())} of {len(r)} (o00: {int(r[r.code == MID].crossed.sum())} of {int((r.code == MID).sum())})")
    pl = ms[ms.is_placebo]
    out.append(f"  o00 placebos: made {len(pl)}, dropped {int(pl.dropped.sum())}, kept {int((~pl.dropped).sum())}")
    v = vp_levels(ctx)
    st = status(ctx)
    ss = st[st.date.isin(ok)]
    tb = ss.groupby(["prof", "status"], sort=False).size().unstack(fill_value=0).reindex(PROFS).fillna(0).astype(int)
    out.append("VPN1 profiles on study days (built / not built: roll, not enough earlier sessions, none): " + ", ".join(
        f"{p} {int(tb.loc[p].get('ok', 0))}/{int(tb.loc[p].get('roll', 0))}/{int(tb.loc[p].get('history', 0))}/"
        f"{int(tb.loc[p].get('none', 0) + tb.loc[p].get('empty', 0))}" for p in PROFS))
    vs = v[v.date.isin(ok)]
    real = vs[~vs.is_placebo & vs.prof.isin(PROFS)]
    per = real.groupby("date").size()
    out.append(f"  real profile levels {len(real)} ({len(real) / nd:.1f} a study day; days with all 39: {int((per == 39).sum())}, "
               f"with none: {nd - len(per)}); crossed before 09:30: {int(real.crossed.sum())}")
    pl = vs[vs.is_placebo]
    out.append(f"  placebos: made {len(pl)}, dropped {int(pl.dropped.sum())}, kept {int((~pl.dropped).sum())} "
               f"({(~pl.dropped).sum() / nd:.1f} a study day)")
    S = sessions(ctx)
    out.append(f"  sessions: regular {len(S['rth'])} (short, under {RTH_HALF} bars: {int((~S['rth'].ok).sum())}; holding two "
               f"contracts: {int((S['rth'].iid < 0).sum())}), full {len(S['eth'])} (short, under {ETH_HALF} bars: "
               f"{int((~S['eth'].ok).sum())}: {', '.join(str(k)[:10] for k in S['eth'].key[~S['eth'].ok])}; holding two contracts: "
               f"{int((S['eth'].iid < 0).sum())})")
    for a in APOC:
        x = vs[vs.code == a]
        five = ss[ss.prof.isin([f"{a[-3:]}{n}" for n in NS]) & (ss.status == "ok")].groupby("date").size()
        out.append(f"  aligned POCs {a}: {len(x)} study days of {int((five == 5).sum())} with all five profiles built")
    return out


def brute_parts(ctx, d, prof):
    """The bars of a profile selected with plain pandas time slices, independent of sessions() / _plan():
    ([frame per session], [session dates]) or None when there are not enough earlier sessions."""
    a = ctx.a
    parts, dates = [], []
    if prof == "on":
        parts, dates = [a.loc[W(d - ONE, 1080):W(d, 569)]], [d]
    elif prof in ("rthw", "ethw"):
        mon = d - pd.Timedelta(days=d.dayofweek)
        for k in range(7, 2, -1):                                     # Monday .. Friday of the previous week
            cday = mon - k * ONE
            x = a.loc[W(cday, 570):W(cday, 959)] if prof == "rthw" else a.loc[W(cday - ONE, 1080):W(cday, 1019)]
            if len(x):
                parts.append(x); dates.append(cday)
    else:
        n, cday, guard = int(prof[3]), d - ONE, 0
        while len(parts) < n and guard < 40:
            x = a.loc[W(cday, 570):W(cday, 959)] if prof.startswith("rth") else a.loc[W(cday - ONE, 1080):W(cday, 1019)]
            if len(x) >= (RTH_HALF if prof.startswith("rth") else ETH_HALF):
                parts.insert(0, x); dates.insert(0, cday)
            cday, guard = cday - ONE, guard + 1
        if len(parts) < n:
            return None
    return (parts, dates) if parts else None


def brute(ctx, d, prof):
    """A profile re-derived from brute_parts() with the Pine transcription (lev1_levels.profile_pine).
    Returns (vah, poc, val, vol, nrows, nbars, session dates, contracts) or None if not built."""
    pd_ = brute_parts(ctx, d, prof)
    if pd_ is None:
        return None
    parts, dates = pd_
    x = pd.concat(parts)
    ids = set(x.instrument_id.tolist()) | {int(ctx.a.instrument_id[W(d, 570)])}
    if len(ids) != 1:
        return None
    g = LL.profile_pine(x.high.to_numpy(float), x.low.to_numpy(float), x.volume.to_numpy(float))
    return None if g is None else g + (len(x), [str(q.date()) for q in dates], ids)


def unit_checks(ctx, seed=7):
    out = []
    D = ctx.days
    lv, st = vp_levels(ctx), status(ctx)
    real = lv[~lv.is_placebo & lv.prof.isin(PROFS)]
    piv = real.pivot(index="date", columns="code", values="value")
    # 1. every composite against the brute-force build on 8 days (all 13 profiles each)
    okd = [d for d, n in st[st.status == "ok"].groupby("date").size().items() if n == 13]
    rng = np.random.default_rng(seed)
    pick = [okd[k] for k in sorted(rng.choice(len(okd), 8, replace=False))]
    meta = real.drop_duplicates(["date", "prof"]).set_index(["date", "prof"])
    n_same = n_all = 0
    for d in pick:
        line = []
        for p in PROFS:
            g = brute(ctx, d, p)
            t = (piv.at[d, f"{p}_vah"], piv.at[d, f"{p}_poc"], piv.at[d, f"{p}_val"])
            m = meta.loc[(d, p)]
            same = g is not None and g[:3] == t and g[3] == m.vol and g[4] == m.nrows and g[5] == m.nbars \
                and "|".join(g[6]) == m.sessions
            n_all += 1
            n_same += bool(same)
            line.append(f"{p} {'=' if same else 'DIFFERENT'}")
        out.append(f"  brute force {d.date()} ({d.day_name()[:3]}): " + " ".join(line))
        for p in ("rth3", "eth5", "ethw"):
            g = brute(ctx, d, p)
            out.append(f"      {p}: sessions {g[6][0]}..{g[6][-1]} ({len(g[6])}), bars {g[5]}, rows {g[4]}, volume {g[3]:.0f}, "
                       f"Pine transcription VAH {g[0]:.2f} POC {g[1]:.2f} VAL {g[2]:.2f} | vp_levels VAH "
                       f"{piv.at[d, p + '_vah']:.2f} POC {piv.at[d, p + '_poc']:.2f} VAL {piv.at[d, p + '_val']:.2f}")
    out.insert(0, f"composite profiles against the brute-force build (sessions re-derived from time slices, bars "
                  f"concatenated, Pine transcription bar by bar; values, volume, rows, bars and session list compared): "
                  f"{n_same} of {n_all} identical on 8 days x 13 profiles")
    # 1b. brute force agrees on which profiles are NOT built, on 40 further days x 13 profiles
    days2 = [D.index[k] for k in sorted(rng.choice(len(D), 40, replace=False))]
    n_ok = n_tot = n_nb = 0
    stp = st.set_index(["date", "prof"]).status
    for d in days2:
        for p in PROFS:
            g = brute(ctx, d, p)
            built = stp[(d, p)] == "ok"
            n_tot += 1
            n_nb += not built
            n_ok += (g is None) == (not built) and (g is None or g[:3] == (piv.at[d, f"{p}_vah"], piv.at[d, f"{p}_poc"], piv.at[d, f"{p}_val"]))
    out.append(f"built / not built and the three values against the brute-force build on 40 random cash days x 13 "
               f"profiles: {n_ok} of {n_tot} agree ({n_nb} of them not built)")
    # 2. eth1's volume = the summed 1-minute volume of that session (bars selected by trading date and clock)
    e1 = meta.xs("eth1", level="prof")
    S = sessions(ctx)["eth"]
    n_v = n_r = 0
    for d, m in e1.iterrows():
        t = np.datetime64(m.sessions, "D")
        sel = (ctx.tdate == t) & ((ctx.tod >= 1080) | (ctx.tod < 1020))
        n_v += bool(m.vol == float(ctx.V[sel].sum()) and m.nbars == int(sel.sum()))
        srow = S[S.key == t].iloc[0]
        pf = composite(ctx, ((int(srow.lo), int(srow.hi)),))
        n_r += bool(abs(pf["rows"].sum() - pf["vol"]) < 1e-6 * pf["vol"])
    out.append(f"eth1: profile volume and bar count = the summed 1-minute volume and the number of bars of that trading "
               f"date's 18:00-16:59 bars: {n_v} of {len(e1)} days; its rows sum to that volume: {n_r} of {len(e1)}")
    r1 = meta.xs("rth1", level="prof")
    n_v = 0
    for d, m in r1.iterrows():
        x = ctx.a.loc[W(pd.Timestamp(m.sessions), 570):W(pd.Timestamp(m.sessions), 959)]
        n_v += bool(m.vol == float(x.volume.sum()) and m.nbars == len(x))
    out.append(f"rth1: profile volume and bar count = those of the previous cash day's 09:30-15:59 bars: {n_v} of {len(r1)} days")
    # 3. ordering
    n_ord = sum(int((piv[f"{p}_val"] <= piv[f"{p}_poc"]).sum() == piv[f"{p}_poc"].notna().sum() and
                    (piv[f"{p}_poc"] <= piv[f"{p}_vah"]).sum() == piv[f"{p}_poc"].notna().sum()) for p in PROFS)
    tot = int(sum(piv[f"{p}_poc"].notna().sum() for p in PROFS))
    bad = int(sum(((piv[f"{p}_val"] > piv[f"{p}_poc"]) | (piv[f"{p}_poc"] > piv[f"{p}_vah"])).sum() for p in PROFS))
    out.append(f"val <= poc <= vah: {tot - bad} of {tot} profiles ({n_ord} of 13 profile codes without an exception)")
    # 4. `on` = lev1's overnight profile
    l1 = LL.levels(ctx)
    p1 = l1[l1.code.isin(LEVELS) & ~l1.is_placebo].pivot(index="date", columns="code", values="value").reindex(D.index)
    mine = piv.reindex(D.index)
    built = mine["on_poc"].notna().to_numpy()
    eq = np.ones(len(D), bool)
    for l in LEVELS:
        eq &= (mine[f"on_{l}"].to_numpy() == p1[l].to_numpy())
    son = st[st.prof == "on"].set_index("date").status.reindex(D.index)
    out.append(f"on = lev1_levels' overnight profile (vah, poc, val): identical on {int((eq & built).sum())} of {int(built.sum())} "
               f"days on which it is built; not built on {int((~built).sum())} days ({son[~built].value_counts().to_dict()}; "
               f"lev1 builds one there: {int(p1.poc[~built].notna().sum())}); of the not-built days, study days: "
               f"{len(set(D.index[~built]) & set(ok_days(ctx)))}")
    # 5. hourly opens against the raw bars on 10 days
    ml = mid_levels(ctx)
    mr = ml[~ml.is_placebo]
    days = [D.index[k] for k in sorted(rng.choice(len(D), 10, replace=False))]
    n_same = n_all = 0
    for d in days:
        line = []
        for h, code in zip(HOURS, MID_CODES):
            t = W(d - ONE if h >= 19 else d, h * 60)
            x = ctx.a.loc[t:W(d, 569)]
            r = mr[(mr.date == d) & (mr.code == code)]
            if len(x) == 0:
                same, txt = len(r) == 0, "no bar"
            else:
                same = len(r) == 1 and float(r.value.iloc[0]) == float(x.open.iloc[0]) and ctx.ts[int(r.t_set.iloc[0])] == x.index[0]
                txt = f"{x.open.iloc[0]:.2f}" + ("" if x.index[0] == t else f"@{x.index[0].strftime('%H:%M')}")
            n_all += 1
            n_same += bool(same)
            line.append(f"{code} {txt}{'' if same else ' DIFFERENT'}")
        out.append(f"  hourly opens {d.date()}: " + " ".join(line))
    out.append(f"hourly opens against the raw bars (first bar of ctx.a at or after the wall-clock time and before 09:30): "
               f"{n_same} of {n_all} identical on 10 days x 13 hours")
    e = pd.DataFrame({"o": ml[(ml.code == MID) & ~ml.is_placebo].set_index("date").value})
    e["l1"] = l1[(l1.code == "o00") & ~l1.is_placebo].set_index("date").value
    out.append(f"o00 against lev1_levels' o00 (exact 00:00 bar only): equal on {int((e.o == e.l1).sum())} of {int(e.l1.notna().sum())} "
               f"days where lev1 has one; days with an o00 here and none in lev1 (00:00 bar missing): {int(e.l1.isna().sum())}")
    # 6. weekly profile: constant within a week, built from the week that ended the Friday before
    wk = real[real.prof.isin(["rthw", "ethw"])].copy()
    wk["wk"] = (wk.date.to_numpy().astype("datetime64[D]").astype("int64") + 3) // 7
    nun = wk.groupby(["wk", "code"]).value.nunique()
    last = pd.to_datetime(wk.sessions.str.split("|").str[-1])
    gap = (wk.date - pd.to_timedelta(wk.date.dt.dayofweek, unit="D") - last).dt.days
    out.append(f"weekly profiles: one value per week and code in {int((nun == 1).sum())} of {len(nun)} week-codes; the last "
               f"session used lies 3 days (Friday) before this week's Monday on {int((gap == 3).sum())} of {len(wk)} level-days "
               f"(otherwise {sorted(set(gap[gap != 3].tolist()))} days: a week without a Friday session)")
    # 7. the subset build gives the same rows as the full build
    sub = _vp(ctx, ["rth3", "eth5"], False)[0]
    a_ = real[real.prof.isin(["rth3", "eth5"])].reset_index(drop=True)
    out.append(f"vp_levels(profs=['rth3', 'eth5']) = the same rows of the full build: {bool(a_.equals(sub.reset_index(drop=True)))}")
    return out


def causal(ctx_bars, n=190, seed=3, back_days=45, fwd_days=3):
    """Each sampled level (stratified over the codes; placebos and aligned-POC levels included) is recomputed on a
    window (a) with every bar after its own t_set mirrored (core._reflect; a level fixed at the OPEN of bar t_set is
    cut after bar t_set - 1 with that one open kept), (b) with every bar after the last bar before 09:30 mirrored,
    (c) with the bars between t_set and the 09:30 bar removed and the rest mirrored. The value must be identical in
    (a) and (c) and, for a real level, equal to the full run's; in (b) value, `crossed` and `dropped` must be identical
    (a placebo is kept or dropped only once every real level of the day is known, 09:29 at the latest)."""
    full = core.Ctx(ctx_bars)
    ok = set(ok_days(full))
    ml, vl = mid_levels(full), vp_levels(full)
    rng = np.random.default_rng(seed)
    first = full.days.index[60]
    bad = tested = 0
    res = {}

    def lev(c, r, study):
        if study == "mid":
            l = mid_levels(c)
        elif r.is_placebo:
            l = vp_levels(c)
        elif r.code in APOC:
            l = vp_levels(c, [f"{r.stype}{k}" for k in NS])
        else:
            l = vp_levels(c, [r.prof])
        a = l[(l.date == r.date) & (l.lid == r.lid)]
        return a.iloc[0] if len(a) == 1 else None

    def window(T, date):
        end = max(T + pd.Timedelta(days=fwd_days), W(date, 0) + pd.Timedelta(days=2))
        return ctx_bars[(ctx_bars.index >= T - pd.Timedelta(days=back_days)) & (ctx_bars.index < end)]

    for study, lvs in (("mid", ml), ("vp", vl)):
        x = lvs[lvs.date.isin(ok) & (lvs.date > first)]
        codes = list(dict.fromkeys(x.code))
        per = max(1, n // (len(MID_CODES) + 1 + 2 * len(VP_CODES) + 2))
        for code in codes:
            xs = x[x.code == code]
            for k in rng.choice(len(xs), min(per, len(xs)), replace=False):
                r = xs.iloc[int(k)]
                ts_, i_open = int(r.t_set), int(full.days.i_open[r.date])
                depends_atr = bool(r.is_placebo or r.code in APOC)
                # (a) the future after t_set mirrored
                T = full.ts[ts_ - 1] if r.open_set else full.ts[ts_]
                w = window(T, r.date)
                m = core._reflect(w, T)
                if r.open_set:
                    m.loc[full.ts[ts_], "open"] = w.loc[full.ts[ts_], "open"]
                a0, a1 = lev(core.Ctx(w), r, study), lev(core.Ctx(m), r, study)
                wa, a0a = w, a0                                   # (c) is compared on this same window (same ATR warm-up)
                same = a0 is not None and a1 is not None and float(a0.value) == float(a1.value) \
                    and (depends_atr or float(a0.value) == float(r.value))
                # (b) the future after the last bar before 09:30 mirrored: value, crossed, dropped
                if same:
                    T = full.ts[i_open - 1]
                    w = window(T, r.date)
                    a0, a1 = lev(core.Ctx(w), r, study), lev(core.Ctx(core._reflect(w, T)), r, study)
                    same = a0 is not None and a1 is not None and float(a0.value) == float(a1.value) \
                        and bool(a0.crossed) == bool(a1.crossed) and bool(a0.dropped) == bool(a1.dropped) \
                        and (depends_atr or bool(a0.crossed) == bool(r.crossed))
                # (c) the bars after t_set and before the 09:30 bar removed, the 09:30 bar and later mirrored
                if same and ts_ < i_open - 1:
                    T = full.ts[ts_]
                    keep = (wa.index <= T) | (wa.index >= full.ts[i_open])
                    a1 = lev(core.Ctx(core._reflect(wa[keep], T)), r, study)
                    same = a1 is not None and float(a1.value) == float(a0a.value)
                tested += 1
                bad += not same
                res.setdefault(code, []).append(bool(same))
    grp = {}
    for code, v in res.items():
        g = code.split("_")[0] + ("~" if code.endswith("~") else "") if "_" in code else code
        grp.setdefault(g, []).extend(v)
    print("  " + "  ".join(f"{g} {sum(v)}/{len(v)}" for g, v in grp.items()))
    print(f"level look-ahead test: {tested} levels, each recomputed (a) with the future after its own t_set mirrored, "
          f"(b) with the future after 09:29 mirrored, (c) with the bars between t_set and 09:30 removed; {bad} differ "
          f"-> {'PASS' if bad == 0 else 'FAIL'}")
    return bad == 0


def main():
    import run
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--causal", type=int, default=0)
    a = ap.parse_args()
    A = run.bars("is")
    t0 = time.time()
    ctx = core.Ctx(A)
    ml = mid_levels(ctx)
    t1 = time.time()
    vl = vp_levels(ctx)
    print(f"LEV2 levels   bars {A.index[0]} -> {A.index[-1]}   MID1 rows {len(ml)} [{t1 - t0:.0f}s]   VPN1 rows {len(vl)} "
          f"[{time.time() - t1:.0f}s]")
    for line in counts(ctx):
        print(line)
    if a.check:
        for line in unit_checks(ctx):
            print(line)
    if a.causal:
        ok = causal(A, n=a.causal)
        sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
