#!/usr/bin/env python3
"""LEV2 hand checks (YT10): prints, for chosen events, the bars the level comes from (re-derived here with plain pandas
time slices and the Pine transcription, not with vp_levels / mid_levels), the 09:30 open, the bars around the tap and
the trades core.simulate makes, next to the events file's numbers.

    python3 tools/yt1/lev2_verify.py            the fixed set of events quoted in notes/LEV2.md
    python3 tools/yt1/lev2_verify.py --extra    a few descriptive counts behind the readings (no trade results)
"""
import argparse, pathlib, sys
import numpy as np
import pandas as pd
sys.path.insert(0, str(pathlib.Path(__file__).parent))
import core
import tt
import lev1_levels as LL
import lev1_events as LE
import lev2_levels as LV
import lev2_events as LE2
import lev2_tables as LT2

W = core.Ctx._wall
ONE = pd.Timedelta(days=1)


def prof_text(ctx, d, prof, indent="    "):
    """(brute result, text): the sessions of a profile with their bars and volume, and the profile's totals."""
    parts, dates = LV.brute_parts(ctx, d, prof)
    g = LV.brute(ctx, d, prof)
    x = pd.concat(parts)
    f = LL.profile(x.high.to_numpy(float), x.low.to_numpy(float), x.volume.to_numpy(float))
    lines = [f"{indent}session {q.date()} ({q.day_name()[:3]}): {len(p)} bars {p.index[0].strftime('%m-%d %H:%M')}..{p.index[-1].strftime('%m-%d %H:%M')}, "
             f"high {p.high.max():.2f} low {p.low.min():.2f} volume {int(p.volume.sum())}" for p, q in zip(parts, dates)]
    inside = f["rows"][f["dn"]:f["up"] + 1].sum()
    lines.append(f"{indent}as one profile (Pine transcription, bar by bar): {g[5]} bars, {g[4]} rows of 1.00 from {f['row_lo']:.2f}, volume "
                 f"{g[3]:.0f}; POC row {f['ip']} [{f['row_lo'] + f['ip']:.2f}, {f['row_lo'] + f['ip'] + 1:.2f}) holds {f['rows'][f['ip']]:.1f} "
                 f"(next largest {np.sort(f['rows'])[-2]:.1f}); value area rows {f['dn']}..{f['up']} hold {inside:.1f} = "
                 f"{inside / g[3]:.1%}; VAH {g[0]:.2f} POC {g[1]:.2f} VAL {g[2]:.2f}; contract(s) {sorted(g[7])}")
    return g, "\n".join(lines)


def derive(ctx, r):
    """The level of row r from the bars, written out independently of mid_levels / vp_levels. Returns (value, text)."""
    a, d = ctx.a, r.date
    code = r.parent if r.is_placebo else r.code
    if r.study == "mid":
        h = int(code[1:3])
        t = W(d - ONE if h >= 19 else d, h * 60)
        x = a.loc[t:W(d, 569)]
        v = float(x.open.iloc[0])
        txt = f"    first bar at or after {t.strftime('%m-%d %H:%M')}: the bar stamped {x.index[0].strftime('%m-%d %H:%M')}, open {v:.2f}"
    elif code in LV.APOC:
        st = code[-3:]
        pocs, lines = [], []
        for n in LV.NS:
            g, _ = prof_text(ctx, d, f"{st}{n}")
            pocs.append(g[1])
            lines.append(f"    {st}{n}: sessions {g[6][0]}..{g[6][-1]} ({len(g[6])}), {g[5]} bars, volume {g[3]:.0f}, VAH {g[0]:.2f} POC {g[1]:.2f} VAL {g[2]:.2f}")
        v = core.tick_round(float(np.mean(pocs)))
        lines.append(f"    the five POCs {', '.join(f'{p:.2f}' for p in pocs)}: max - min = {max(pocs) - min(pocs):.2f} <= 0.06 x ATR = "
                     f"{0.06 * r.atr:.2f}; mean {np.mean(pocs):.4f} -> on the tick grid {v:.2f}")
        txt = "\n".join(lines)
    else:
        prof, lvl = code.split("_")
        g, txt = prof_text(ctx, d, prof)
        v = g[{"vah": 0, "poc": 1, "val": 2}[lvl]]
    if r.is_placebo:
        sgn = 1 if r.inst.endswith("+") else -1
        txt += f"\n    parent {code} = {v:.2f}; placebo = parent {'+' if sgn > 0 else '-'} 0.12 x ATR ({0.12 * r.atr:.2f})"
        v = v + sgn * 0.12 * r.atr
    return float(v), txt


def bars_text(ctx, lo, hi, mark=None):
    return "\n".join(f"      {ctx.ts[k].strftime('%H:%M')}  O {ctx.O[k]:.2f}  H {ctx.H[k]:.2f}  L {ctx.L[k]:.2f}  C {ctx.C[k]:.2f}"
                     + (f"   <- {mark[k]}" if mark and k in mark else "") for k in range(lo, hi + 1))


def bias_text(ctx, d):
    b = tt.bias(ctx).loc[d]
    T = tt.daily(ctx)
    p = T.index.searchsorted(d, "left")
    c1, c2 = T.index[p - 1], T.index[p - 2]
    x1 = ctx.a.loc[W(c1 - ONE, 1080):W(c1, 1079)]
    x2 = ctx.a.loc[W(c2 - ONE, 1080):W(c2, 1079)]
    rule = {(1, "cont"): "close1 > high2 -> bullish", (-1, "cont"): "close1 < low2 -> bearish",
            (1, "fail"): "low1 < low2, close1 > low2, high1 <= high2 -> bullish", (-1, "fail"): "high1 > high2, close1 < high2, low1 >= low2 -> bearish"}
    return (f"  daily bias (tt.bias): candle 1 = trading date {c1.date()} high {x1.high.max():.2f} low {x1.low.min():.2f} close {x1.close.iloc[-1]:.2f}; "
            f"candle 2 = {c2.date()} high {x2.high.max():.2f} low {x2.low.min():.2f}; "
            + (rule.get((int(b.bias), b.kind), "no rule applies -> none") if b.kind != "roll" else "roll -> none")
            + f"; tt.bias = {int(b.bias):+d} ('{b.kind}'), its candle-1 levels h {b.h1:.2f} l {b.l1:.2f} c {b.c1:.2f}, candle 2 h {b.h2:.2f} l {b.l2:.2f}")


def explain(ctx, r, title, variants=(LE2.HEAD, LE2.ASKED, LE2.BHEAD), allvp=None, show_bias=False):
    d = r.date
    v, txt = derive(ctx, r)
    print(f"\n### {title}: {d.date()} ({d.day_name()[:3]}) {r.lid}{' (placebo)' if r.is_placebo else ''}")
    print(f"  level:\n{txt}")
    t_end = int(r.t_end)
    x = ctx.a.iloc[t_end + (0 if r.study == 'mid' else 1):int(r.w0)]
    start = ctx.O[t_end] if r.study == "mid" else ctx.C[t_end]
    lo_, hi_ = (min(x.low.min(), start), max(x.high.max(), start)) if len(x) else (start, start)
    print(f"  -> by hand {v:.4f}; events file {r.value:.4f} ({'same' if abs(v - r.value) < 1e-6 else 'DIFFERENT'}); fixed at "
          f"{ctx.ts[int(r.t_set)].strftime('%m-%d %H:%M')} ({'open' if r.study == 'mid' else 'close'}); from then to 09:29 price ranged "
          f"{lo_:.2f}..{hi_:.2f} (starting at {start:.2f}): traded through the level {lo_ < v < hi_}; events file crossed {r.crossed}")
    w0, w1 = int(r.w0), int(r.w1)
    side = 1 if r.side == "R" else -1
    print(f"  09:30 open {r.p0:.2f} (bar {ctx.ts[w0].strftime('%H:%M')} O {ctx.O[w0]:.2f}); ATR {r.atr:.2f}; level "
          f"{'above' if side > 0 else 'below'} by {abs(r.value - r.p0):.2f} = {abs(r.value - r.p0) / r.atr:.3f} ATR (skip at or under 0.04; "
          f"bucket {r.dbucket}) -> {'resistance' if side > 0 else 'support'}{' SKIPPED' if r.skipped else ''}; order price {r.px:.2f}; watch "
          f"{ctx.ts[w0].strftime('%H:%M')}..{ctx.ts[w1].strftime('%H:%M')}")
    if show_bias:
        print(bias_text(ctx, d))
        print(f"  -> the fade is a {'long' if side < 0 else 'short'}: {r.bias_rel} the bias (events file bias {r.bias:+d}, bias_rel {r.bias_rel})")
    if allvp is not None:
        day = allvp[(allvp.date == d) & ~allvp.is_placebo & allvp.prof.isin(LV.PROFS)]
        near = 0.03 * r.atr
        hits = []
        for p in LV.PROFS:
            q = day[day.prof == p]
            if p == r.prof or len(q) == 0:
                continue
            dd = (q.value - r.value).abs()
            lv = ", ".join(f"{a_.level} {a_.value:.2f}{'*' if abs(a_.value - r.value) <= near else ''}" for a_ in q.itertuples())
            hits.append(bool((dd <= near).any()))
            print(f"    {p:<5} {lv}   nearest {dd.min():.2f} ({dd.min() / r.atr:.3f} ATR){'  <- within 0.03 x ATR' if hits[-1] else ''}")
        print(f"  stacked count by hand: {sum(hits)} other profiles with a level within 0.03 x ATR = {near:.2f} of {r.value:.2f} "
              f"(events file stack {r['stack']}, bucket {r.sbucket}); profiles built that day: {day.prof.nunique()}")
    if r.skipped:
        return
    if not r.tapped:
        seg = slice(w0, w1 + 1)
        print(f"  never tapped: highest high of the watch {ctx.H[seg].max():.2f}, lowest low {ctx.L[seg].min():.2f}")
        return
    tap = int(r.tap)
    if tap > w0:
        before = ctx.H[w0:tap].max() if side > 0 else ctx.L[w0:tap].min()
        print(f"  tap bar {ctx.ts[tap].strftime('%H:%M')} (bucket {r.bucket}); {'highest high' if side > 0 else 'lowest low'} of the watch before it "
              f"{before:.2f} ({'below' if side > 0 else 'above'} the order price)")
    else:
        print(f"  tap bar {ctx.ts[tap].strftime('%H:%M')} = the 09:30 bar (bucket {r.bucket})")
    dist = LE.stop_pts(r.atr)
    t_head = None
    for vn in variants:
        o = LE2.orders_of(r, vn)[0]
        t = core.simulate(ctx, **o)
        t_head = t if vn == variants[0] else t_head
        print(f"  {vn}: order i={ctx.ts[o['i']].strftime('%H:%M')} {'sell' if o['side'] < 0 else 'buy'} {o['etype']} {o['price']:.2f} "
              f"stop {o['stop']:.2f} target {o['target']:.2f} (d = {dist[LE2.stop_of(vn)]:.2f}) -> "
              + ("no fill" if t is None else f"fill {t['entry_time'].strftime('%H:%M')} at {t['entry']:.2f}, exit "
                 f"{t['exit_time'].strftime('%H:%M')} at {t['exit']:.2f} ({t['reason']}), pnl {t['pnl']:+.2f}, R {t['R']:+.3f}")
              + f"   [events file: R {getattr(r, 'R_' + vn):+.3f} {getattr(r, 'why_' + vn)}]")
    k_end = min(t_head["k"] if t_head else tap, tap + 10)
    mark = {tap: "tap"}
    if t_head is not None and t_head["k"] != tap:
        mark[t_head["k"]] = f"exit {t_head['reason']} ({variants[0]})"
    print(bars_text(ctx, max(tap - 2, w0 - 1), k_end, mark)
          + (f"\n      ... exit bar {ctx.ts[t_head['k']].strftime('%H:%M')}  O {ctx.O[t_head['k']]:.2f}  H {ctx.H[t_head['k']]:.2f}  L "
             f"{ctx.L[t_head['k']]:.2f}  C {ctx.C[t_head['k']]:.2f}   <- exit {t_head['reason']} ({variants[0]})"
             if t_head is not None and t_head["k"] > k_end else ""))


def explain_va(ctx, dt, d, title):
    r = dt[dt.date == d].iloc[0]
    D = ctx.days
    i_open, i_end, atr = int(D.i_open[d]), int(D.i_end[d]), float(D.atr[d])
    print(f"\n### {title}: {d.date()} ({d.day_name()[:3]})")
    vah, val = [], []
    for n in LV.NS:
        g = LV.brute(ctx, d, f"rth{n}")
        vah.append(g[0]); val.append(g[2])
        print(f"    rth{n}: sessions {g[6][0]}..{g[6][-1]} ({len(g[6])}), {g[5]} bars, volume {g[3]:.0f}: VAH {g[0]:.2f} POC {g[1]:.2f} VAL {g[2]:.2f}"
              f"   [day-types file: VAH {r[f'vah_rth{n}']:.2f} VAL {r[f'val_rth{n}']:.2f}]")
    o = ctx.O[i_open]
    typ = "above" if all(o > v for v in vah) else "below" if all(o < v for v in val) else \
        "inside" if all(lo <= o <= hi for lo, hi in zip(val, vah)) else "mixed"
    print(f"  09:30 open {o:.2f}; highest VAH {max(vah):.2f}, lowest VAL {min(val):.2f} -> by hand '{typ}' (day-types file '{r.type_rth}'); "
          f"ATR {atr:.2f}, R unit 0.1 x ATR = {0.1 * atr:.2f} points")
    od = [x for x in LE2.va_orders(ctx, "rth") if x["tag"].endswith(d.strftime("%Y-%m-%d"))]
    if not od:
        print("  no VA-trend order that day")
        return
    t = core.simulate(ctx, **od[0])
    print(f"  order: i = {ctx.ts[od[0]['i']].strftime('%H:%M')} (the last bar before 09:30), {'buy' if od[0]['side'] > 0 else 'sell'} at the next open, "
          f"no stop, flat bar {ctx.ts[i_end].strftime('%H:%M')} -> fill {t['entry_time'].strftime('%H:%M')} at {t['entry']:.2f} (open {o:.2f} "
          f"{'+' if od[0]['side'] > 0 else '-'} 1 tick), exit {t['exit_time'].strftime('%H:%M')} at {t['exit']:.2f} (close {ctx.C[i_end]:.2f} "
          f"{'-' if od[0]['side'] > 0 else '+'} 1 tick, {t['reason']}), pnl {t['pnl']:+.2f}, R = pnl / (0.1 x ATR x $2) = {t['R']:+.4f}"
          f"   [day-types file: side {r.va_rth_side} R {r.va_rth_R:+.4f} pnl {r.va_rth_pnl:+.2f}; move_up {r.move_up:+.4f} ATR]")
    print(bars_text(ctx, i_open - 1, i_open + 1) + "\n      ...\n" + bars_text(ctx, i_end, i_end))
    print(f"  ORB v1.4 that day: " + ("no trade" if r.orb_side == "" else f"{r.orb_side} R {r.orb_R:+.3f} pnl {r.orb_pnl:+.2f}"))


def chosen(mid, vp, seed=11):
    rng = np.random.default_rng(seed)
    m = mid[mid.is_event & mid.tapped & ~mid.is_placebo]
    v = vp[vp.is_event & vp.tapped]
    real = v[~v.is_placebo & v.prof.isin(LV.PROFS)]

    def one(f):
        return f.iloc[int(rng.integers(len(f)))]
    o00 = m[m.code == "o00"]
    return [
        ("1 midnight open, support tap", one(o00[o00.side == "S"]), {}),
        ("2 midnight open, resistance tap", one(o00[o00.side == "R"]), {}),
        ("3 midnight open, fade with the bias", one(o00[o00.bias_rel == "with"]), dict(show_bias=True)),
        ("4 midnight open, fade against the bias", one(o00[o00.bias_rel == "against"]), dict(show_bias=True)),
        ("5 hourly-open comparison level", one(m[m.code != "o00"]), {}),
        ("6 rth3 level", one(real[real.prof == "rth3"]), {}),
        ("7 eth5 level", one(real[real.prof == "eth5"]), {}),
        ("8 weekly level", one(real[real.prof.isin(["rthw", "ethw"])]), {}),
        ("9 aligned-POC day", one(v[v.code.isin(LV.APOC)]), {}),
        ("10 stacked event (two or more other profiles)", one(real[real["stack"] >= 2]), dict(stack=True)),
        ("11 a level with no other profile near (count 0)", one(real[real["stack"] == 0]), dict(stack=True)),
        ("12 the `on` profile", one(real[real.prof == "on"]), {}),
        ("13 a profile placebo", one(v[v.is_placebo]), {}),
        ("14 a midnight placebo", one(mid[mid.is_event & mid.tapped & mid.is_placebo]), {}),
        ("15 a level that is never tapped", one(vp[vp.is_event & ~vp.tapped & ~vp.is_placebo & vp.prof.isin(LV.PROFS)]), {}),
        ("16 a level skipped as too near the open", one(mid[mid.skipped & (mid.code == "o00")]), {}),
    ]


def extra(ctx, mid, vp, dt):
    """Descriptive counts behind the readings (no trade results)."""
    D = ctx.days
    io = D.i_open.to_numpy()
    other = int((ctx.cdate[io - 1] != ctx.cdate[io]).sum())
    print(f"cash days whose last bar before 09:30 lies on another calendar day: {other} of {len(D)}; last bar before 09:30 "
          f"stamped 09:29 on {int((ctx.tod[io - 1] == 569).sum())}")
    for name, ev in (("MID1", mid), ("VPN1", vp)):
        alt = ctx.C[ev.w0.to_numpy() - 1]
        val, atr, p0 = ev.value.to_numpy(), ev.atr.to_numpy(), ev.p0.to_numpy()
        so, sc = np.sign(val - p0), np.sign(val - alt)
        ko, kc = ~(np.abs(val - p0) > LE2.SKIP * atr), ~(np.abs(val - alt) > LE2.SKIP * atr)
        print(f"{name}: level-days {len(ev)}; 09:30 open != last close before it on {int((p0 != alt).sum())} (median |diff| "
              f"{np.median(np.abs(p0 - alt)):.2f} points, max {np.abs(p0 - alt).max():.2f}); the side differs between the two on "
              f"{int((so != sc).sum())} level-days, the 0.04 x ATR skip on {int((ko != kc).sum())}; level exactly at the open (no side): {int((so == 0).sum())}")
    real = vp[~vp.is_placebo & vp.prof.isin(LV.PROFS)]
    dup = real.groupby(["date", "value"]).size()
    print(f"VPN1 real level-days {len(real)}: distinct prices per day {len(dup)}; level-days sharing their exact price with another "
          f"profile's level {int(dup[dup > 1].sum())}; on the tick grid {int((np.abs(real.value * 4 - np.round(real.value * 4)) < 1e-9).sum())}")
    t = real[real.is_event & real.tapped]
    print(f"VPN1 real tapped events {len(t)}: distinct orders (date x side x price) {len(t.drop_duplicates(['date', 'side', 'px']))}; by "
          f"stacked count " + ", ".join(f"{b}: {int((t.sbucket == b).sum())} rows / {len(t[t.sbucket == b].drop_duplicates(['date', 'side', 'px']))} orders"
                                         for b in LE2.SBUCKETS))
    ct = LT2.cells(LT2.reaction(vp))
    ev150 = ct[ct.trade == "fade"]
    print(f"VPN1 profile x level x side: {len(ev150)}; tapped events per cell min {int(ev150.events.min())} median "
          f"{int(ev150.events.median())} max {int(ev150.events.max())}; with >= 150: {int((ev150.events >= 150).sum())}")
    s = dt[dt.study]
    for fam in ("rth", "eth"):
        sp = s[[f"poc_{fam}{n}" for n in LV.NS]]
        ok = sp.notna().all(axis=1)
        rng_ = (sp.max(axis=1) - sp.min(axis=1)) / s.atr
        print(f"aligned POCs {fam}: study days with five profiles {int(ok.sum())}; (max - min) / ATR median {rng_[ok].median():.3f}; "
              f"<= 0.06: {int((rng_[ok] <= 0.06).sum())}; both rth and eth aligned on the same day: "
              f"{int(vp[vp.code.isin(LV.APOC)].groupby('date').size().eq(2).sum())}")
    m = mid[~mid.is_placebo]
    late = m[m.late_min > 0]
    print("hourly opens taken from a later bar on study days: " + "; ".join(f"{r.date.date()} {r.code} +{r.late_min} min" for r in late.itertuples()))
    e = mid[(mid.code == "o00") & mid.is_event]
    print(f"midnight open: watched {len(e)}, bias +1 / -1 / 0 days {int((e.bias > 0).sum())} / {int((e.bias < 0).sum())} / {int((e.bias == 0).sum())}; "
          f"with {int((e.bias_rel == 'with').sum())}, against {int((e.bias_rel == 'against').sum())}, none {int((e.bias_rel == 'none').sum())}")
    gap = [(n, int((x.tap == x.w0).sum()), int(((x.side == "R") & (ctx.O[x.tap.to_numpy()] >= x.px)).sum() + ((x.side == "S") & (ctx.O[x.tap.to_numpy()] <= x.px)).sum()))
           for n, x in (("MID1", mid[mid.tapped]), ("VPN1", vp[vp.tapped]))]
    print("tapped events: " + "; ".join(f"{n}: tapped by the 09:30 bar itself {a}, tap bar opening at or beyond the order price {b}" for n, a, b in gap))


def main():
    import run
    ap = argparse.ArgumentParser()
    ap.add_argument("--extra", action="store_true")
    a = ap.parse_args()
    pd.set_option("display.width", 250)
    ctx = core.Ctx(run.bars("is"))
    d = core.OUT / "is"
    mid, vp = pd.read_parquet(d / "MID1_events.parquet"), pd.read_parquet(d / "VPN1_events.parquet")
    dt = LT2.read_daytypes(d / "VPN1_daytypes.csv")
    if a.extra:
        extra(ctx, mid, vp, dt)
        return
    for title, r, kw in chosen(mid, vp):
        explain(ctx, r, title, allvp=vp if kw.get("stack") else None, show_bias=kw.get("show_bias", False))
    rng = np.random.default_rng(5)
    s = dt[dt.study & (dt.va_rth_side != "")]
    for k, nm in ((int(rng.integers(len(s[s.va_rth_side == 'L']))), "L"), (int(rng.integers(len(s[s.va_rth_side == 'S']))), "S")):
        explain_va(ctx, dt, s[s.va_rth_side == nm].date.iloc[k], f"{17 if nm == 'L' else 18} VA-trend {'long (open above all five value areas)' if nm == 'L' else 'short (open below all five)'}")


if __name__ == "__main__":
    main()
