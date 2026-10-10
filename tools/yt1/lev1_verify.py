#!/usr/bin/env python3
"""LEV1 hand checks: prints, for chosen events, the bars the level comes from (re-derived here with plain pandas
time slices, not with lev1_levels), the start of the watch, the bars around the tap and the trade core.simulate makes.

    python3 tools/yt1/lev1_verify.py            the fixed set of events quoted in notes/LEV1.md
    python3 tools/yt1/lev1_verify.py --extra    a few descriptive counts behind the readings
"""
import argparse, pathlib, sys
import numpy as np
import pandas as pd
sys.path.insert(0, str(pathlib.Path(__file__).parent))
import core
import lev1_levels as LL
import lev1_events as LE

W = core.Ctx._wall
ONE = pd.Timedelta(days=1)


def _hl(a):
    return f"{len(a)} bars {a.index[0].strftime('%m-%d %H:%M')}..{a.index[-1].strftime('%m-%d %H:%M')}: high {a.high.max():.2f} low {a.low.min():.2f} last close {a.close.iloc[-1]:.2f}"


def derive(ctx, r):
    """The level of row r from the bars, written out independently of lev1_levels. Returns (value, text)."""
    a, d = ctx.a, r.date
    code = r.parent if r.is_placebo else r.code
    if code in ("pdh", "pdl", "pdc", "pdm"):
        p = ctx.days.index[ctx.days.index.get_loc(d) - 1]
        x = a.loc[W(p, 570):W(p, 959)]
        v = {"pdh": x.high.max(), "pdl": x.low.min(), "pdc": x.close.iloc[-1], "pdm": (x.high.max() + x.low.min()) / 2}[code]
        txt = f"previous cash day {p.date()} 09:30-15:59, {_hl(x)}"
    elif code in ("pwh", "pwl"):
        mon = d - pd.Timedelta(days=d.dayofweek)                          # Monday of this week
        x = a.loc[W(mon - 8 * ONE, 1080):W(mon - 3 * ONE, 1019)]          # previous Sunday 18:00 -> Friday 16:59
        v = x.high.max() if code == "pwh" else x.low.min()
        txt = f"previous week, {_hl(x)}"
    elif code in ("onh", "onl", "ash", "asl", "ldh", "ldl", "prh", "prl"):
        t0, t1 = {"on": (W(d - ONE, 1080), W(d, 569)), "as": (W(d - ONE, 1080), W(d, 119)), "ld": (W(d, 120), W(d, 479)),
                  "pr": (W(d, 480), W(d, 569))}[code[:2]]
        x = a.loc[t0:t1]
        v = x.high.max() if code.endswith("h") else x.low.min()
        txt = f"{code[:2]} session, {_hl(x)}"
    elif code in ("o18", "o00", "o0830"):
        t = {"o18": W(d - ONE, 1080), "o00": W(d, 0), "o0830": W(d, 510)}[code]
        v = a.open[t]
        txt = f"open of the bar stamped {t.strftime('%m-%d %H:%M')}"
    elif code in ("vah", "poc", "val"):
        x = a.loc[W(d - ONE, 1080):W(d, 569)]
        g = LL.profile_pine(x.high.to_numpy(), x.low.to_numpy(), x.volume.to_numpy(float))
        f = LL.profile(x.high.to_numpy(), x.low.to_numpy(), x.volume.to_numpy(float))
        v = {"vah": g[0], "poc": g[1], "val": g[2]}[code]
        inside = f["rows"][f["dn"]:f["up"] + 1].sum()
        txt = (f"profile of {len(x)} one-minute bars 18:00-09:29 (Pine transcription): {g[4]} rows of 1.00 from "
               f"{f['row_lo']:.2f}, volume {g[3]:.0f}; POC row {f['ip']} [{f['row_lo'] + f['ip']:.2f}, {f['row_lo'] + f['ip'] + 1:.2f}) holds "
               f"{f['rows'][f['ip']]:.1f} (next largest {np.sort(f['rows'])[-2]:.1f}); value area rows {f['dn']}..{f['up']} hold "
               f"{inside:.1f} = {inside / g[3]:.1%} of the volume; "
               f"VAH {g[0]:.2f} POC {g[1]:.2f} VAL {g[2]:.2f}")
    elif code == "r100":
        o = a.open[W(d, 570)]
        v = np.floor(o / 100) * 100 + 100 if r.inst.startswith("up") else np.ceil(o / 100) * 100 - 100
        txt = f"09:30 open {o:.2f}: nearest multiple of 100 strictly {'above' if r.inst.startswith('up') else 'below'}"
    elif code in ("orh", "orl"):
        x = a.loc[W(d, 570):W(d, 584)]
        v = x.high.max() if code == "orh" else x.low.min()
        txt = f"opening range, {_hl(x)}"
    elif code in LL.BLOCK:
        blk = int(r.inst[:2]) * 60 + int(r.inst[2:])
        t0 = a.loc[W(d, blk):W(d, blk + 119)].index[0]                  # first bar of the block
        cl = a.close.resample("5min").last().dropna()
        prevc = cl[cl.index < t0.floor("5min")].to_numpy()[-(LL.EM_LOOK + 1):]
        ret = np.log(prevc[1:] / prevc[:-1])
        sd = float(np.sqrt(np.mean((ret - ret.mean()) ** 2)))
        centre = a.open[t0]
        v = centre + LL.EM_MULT[code] * centre * sd * np.sqrt(24)
        txt = (f"block {r.inst}: centre = open of the {t0.strftime('%H:%M')} bar {centre:.2f}; population sd of the {len(ret)} "
               f"five-minute log returns before it {sd:.8f}; 1 sigma = centre x sd x sqrt(24) = {centre * sd * np.sqrt(24):.4f}; "
               f"band = centre {LL.EM_MULT[code]:+.0f} sigma")
    else:                                                                 # VWAP bands: value in force during a bar
        k = int(r.tap) if r.tapped else int(r.w0)
        t = ctx.ts[k]
        x = a.loc[W(d - ONE, 1080):t.floor("5min") - pd.Timedelta(minutes=1)]   # through the last completed 5-minute bar
        b = x.resample("5min").agg({"high": "max", "low": "min", "close": "last", "volume": "sum"}).dropna()
        tp = (b.high + b.low + b.close) / 3
        m = float((tp * b.volume).sum() / b.volume.sum())
        sd = float(np.sqrt(max((tp * tp * b.volume).sum() / b.volume.sum() - m * m, 0)))
        v = m + LL.VW_MULT[code] * sd
        txt = (f"{len(b)} five-minute bars 18:00 .. {b.index[-1].strftime('%H:%M')} (the last one completed before the "
               f"{t.strftime('%H:%M')} bar): VWAP {m:.4f}, sigma {sd:.4f}; level = VWAP {LL.VW_MULT[code]:+.0f} sigma")
    if r.is_placebo:
        sgn = 1 if r.inst.endswith("+") else -1
        txt += f"; parent {code} = {v:.2f}; placebo = parent {'+' if sgn > 0 else '-'} 0.12 x ATR ({0.12 * r.atr:.2f})"
        v = v + sgn * 0.12 * r.atr
    return float(v), txt


def bars_text(ctx, lo, hi, mark=None):
    out = []
    for k in range(lo, hi + 1):
        out.append(f"      {ctx.ts[k].strftime('%H:%M')}  O {ctx.O[k]:.2f}  H {ctx.H[k]:.2f}  L {ctx.L[k]:.2f}  C {ctx.C[k]:.2f}"
                   + (f"   <- {mark[k]}" if mark and k in mark else ""))
    return "\n".join(out)


def explain(ctx, ev, r, title, variants=(LE.HEAD, "p20x3")):
    d = r.date
    v, txt = derive(ctx, r)
    lvl = float(LL.moving_values(ctx)[r.code][int(r.tap)]) if (r.kind == "moving" and r.tapped) else r.value
    print(f"\n### {title}: {d.date()} {r.lid} ({r.group}{', placebo' if r.is_placebo else ''})")
    print(f"  level: {txt}")
    print(f"  -> by hand {v:.4f}; table {lvl:.4f} ({'same' if abs(v - lvl) < 1e-6 else 'DIFFERENT'}); set at "
          f"{'(moving)' if r.t_set < 0 else ctx.ts[int(r.t_set)].strftime('%m-%d %H:%M')}; used {r.used}")
    w0, w1 = int(r.w0), int(r.w1)
    side = 1 if r.side == "R" else -1
    print(f"  watch {ctx.ts[w0].strftime('%H:%M')}..{ctx.ts[w1].strftime('%H:%M')}; price at the start (open of the "
          f"{ctx.ts[w0].strftime('%H:%M')} bar) {r.p0:.2f}; ATR {r.atr:.2f}; level {'above' if side > 0 else 'below'} by "
          f"{abs(r.value - r.p0):.2f} = {abs(r.value - r.p0) / r.atr:.3f} ATR (skip under 0.04) -> "
          f"{'resistance' if side > 0 else 'support'}; order price {r.px:.2f}; cluster {r.cl_codes} ({r.cl_n}), lead {r.lead}")
    if r.cl_n > 1:
        day = ev[(ev.date == d) & (ev.cid == r.cid)]
        print("  cluster members: " + ", ".join(f"{q.code} {q.value:.2f}{' (lead)' if q.lead else ''}" for q in day.itertuples())
              + f"; 0.03 x ATR = {0.03 * r.atr:.2f}")
    if r.is_placebo:
        day = ev[(ev.date == d) & (ev.kind == "static") & ~ev.is_placebo & (ev.w0 <= r.w0)]
        near = day.iloc[(day.value - r.value).abs().argsort()[:1]]
        print(f"  nearest real static level known at the start: {near.code.iloc[0]} {near.value.iloc[0]:.2f}, "
              f"{abs(near.value.iloc[0] - r.value):.2f} away (dropped within {0.03 * r.atr:.2f})")
    if not r.tapped:
        seg = slice(w0, w1 + 1)
        print(f"  never tapped: highest high of the watch {ctx.H[seg].max():.2f}, lowest low {ctx.L[seg].min():.2f}")
        return
    tap = int(r.tap)
    before = (ctx.H[w0:tap].max() if side > 0 else ctx.L[w0:tap].min()) if tap > w0 else np.nan
    print(f"  tap bar {ctx.ts[tap].strftime('%H:%M')} (bucket {r.bucket}); {'highest high' if side > 0 else 'lowest low'} of the watch "
          f"before it {before:.2f} ({'below' if side > 0 else 'above'} the order price)" if tap > w0 else
          f"  tap bar {ctx.ts[tap].strftime('%H:%M')} = the first watched bar (bucket {r.bucket})")
    dist = LE.stop_pts(r.atr)
    for vn in variants:
        if r.kind == "moving":
            o = LE.order_of(tap - 1, side, r.px, dist[LE.stop_of(vn)], vn, tap, int(r.exit_i))
        else:
            o = LE.orders_of(ctx, r, vn)[0]
        t = core.simulate(ctx, **o)
        print(f"  {vn}: order i={ctx.ts[o['i']].strftime('%H:%M')} {'sell' if o['side'] < 0 else 'buy'} {o['etype']} {o['price']:.2f} "
              f"stop {o['stop']:.2f} target {o['target']:.2f} (d = {dist[LE.stop_of(vn)]:.2f}) -> "
              + ("no fill" if t is None else f"fill {t['entry_time'].strftime('%H:%M')} at {t['entry']:.2f}, exit "
                 f"{t['exit_time'].strftime('%H:%M')} at {t['exit']:.2f} ({t['reason']}), pnl {t['pnl']:+.2f}, R {t['R']:+.3f}")
              + f"   [events file: R {getattr(r, 'R_' + vn):+.3f} {getattr(r, 'why_' + vn)}]")
    t = core.simulate(ctx, **(LE.order_of(tap - 1, side, r.px, dist["a04"], LE.HEAD, tap, int(r.exit_i)) if r.kind == "moving"
                              else LE.orders_of(ctx, r, LE.HEAD)[0]))
    k_end = min(t["k"] if t else tap, tap + 12)
    mark = {tap: "tap"}
    if t is not None and t["k"] != tap:
        mark[t["k"]] = f"exit {t['reason']}"
    print(bars_text(ctx, max(tap - 2, w0 - 1), k_end, mark)
          + (f"\n      ... exit bar {ctx.ts[t['k']].strftime('%H:%M')}  O {ctx.O[t['k']]:.2f}  H {ctx.H[t['k']]:.2f}  L "
             f"{ctx.L[t['k']]:.2f}  C {ctx.C[t['k']]:.2f}   <- exit {t['reason']}" if t is not None and t["k"] > k_end else ""))
    print(f"  30 minutes from the tap: largest move away {r.away30:.3f} ATR, through {r.thru30:.3f} ATR; distance from the "
          f"09:30 open {r.dist_open:.3f} ATR")


def chosen(ev, seed=11):
    rng = np.random.default_rng(seed)
    e = ev[ev.is_event]
    t = e[e.tapped]
    real = t[~t.is_placebo]

    def one(m, frame=None):
        f = (real if frame is None else frame)[m]
        return f.iloc[int(rng.integers(len(f)))]
    return [
        ("1 previous-day level", one((real.code == "pdh") & real.fresh & (real.cl_n == 1))),
        ("2 Asia / London level that is used", one(real.code.isin(["ash", "asl", "ldh", "ldl"]) & ~real.fresh)),
        ("3 profile level", one(real.code.isin(["vah", "poc", "val"]) & (real.cl_n == 1))),
        ("4 expected-move band inside its block", one((real.kind == "block") & real.inst.isin(["1000", "1200"]))),
        ("5 VWAP band", one((real.kind == "moving") & (real.code != "vw"))),
        ("6 opening-range level", one(real.code.isin(["orh", "orl"]))),
        ("7 placebo", one(t.is_placebo & t.fresh, t)),
        ("8 cluster of two levels", one((real.cl_n == 2) & real.first_lead & (real.kind == "static"))),
        ("9 stopped fade", one((real.kind == "static") & (real["why_" + LE.HEAD] == "SL") & real.fresh)),
        ("10 3R winner", one((real.kind == "static") & (real["why_" + LE.HEAD] == "TP") & real.fresh)),
        ("11 round number tapped by the 09:30 bar itself", one((real.code == "r100") & (real.tap == real.w0))),
        ("12 an event that is never tapped", one((e.code == "pdl") & ~e.tapped & (e.kind == "static"), e)),
        ("13 previous-week level", one(real.code.isin(["pwh", "pwl"]))),
        ("14 the one event whose a04 order is not filled", one(t.nofill > 0, t)),
    ]


def extra(ctx, ev, lv):
    """Descriptive counts behind the readings (no trade results)."""
    O, C = ctx.O, ctx.C
    w0 = ev.w0.to_numpy()
    alt = C[w0 - 1]                                              # the other reading of 'price at the start'
    val, atr, p0 = ev.value.to_numpy(), ev.atr.to_numpy(), ev.p0.to_numpy()
    side_o = np.sign(val - p0)
    side_c = np.sign(val - alt)
    skip_o = ~(np.abs(val - p0) > LE.SKIP * atr)
    skip_c = ~(np.abs(val - alt) > LE.SKIP * atr)
    fixed = ~((ev.code.isin(["r100", "r100~"])) | ((ev.kind == "block") & (ev.inst != "0800"))).to_numpy()
    print(f"level-days {len(ev)}; open of the first watched bar != last close before it on {int((p0 != alt).sum())} "
          f"(median |diff| {np.median(np.abs(p0 - alt)):.2f} points, max {np.abs(p0 - alt).max():.2f})")
    print(f"  among levels not defined by that open ({int(fixed.sum())}): side differs between the two readings on "
          f"{int(((side_o != side_c) & fixed).sum())} level-days (of which watched under either reading: "
          f"{int(((side_o != side_c) & fixed & ~(skip_o & skip_c)).sum())}); the near-skip differs on {int(((skip_o != skip_c) & fixed).sum())}")
    e = ev[ev.is_event]
    orr = e[e.code.isin(["orh", "orl"])]
    day = ev[(ev.kind == "static") & ~ev.is_placebo & ~ev.skipped & ~ev.code.isin(["orh", "orl"])]
    n_near = n_un = 0
    for r in orr.itertuples():
        dd = day[(day.date == r.date) & (day.side == r.side)]
        m = (dd.value - r.value).abs() <= LL.NEAR * r.atr
        n_near += bool(m.any())
        n_un += bool((m & (~dd.tapped | (dd.tap >= r.w0))).any())
    print(f"opening-range events {len(orr)}: with a watched 09:30 real static level within 0.03 x ATR on the same side "
          f"{n_near}, of which with one still untapped at 09:45 {n_un} (these are separate events; the opening range "
          f"joins no cluster)")
    b = lv[(lv.kind == "block") & lv.atr.notna()]
    sd5 = LL.em_sd5(ctx)
    b5 = ctx.bars(5)
    k5 = np.searchsorted(b5.i_first.to_numpy(), b.b0.to_numpy(), "right") - 1
    rel = np.abs(sd5[k5] / sd5[k5 - 1] - 1)
    print(f"expected move: sd over the 2,760 bars before the block against the script's value on the block's first bar "
          f"(one bar later): median relative difference {np.nanmedian(rel):.2e}, max {np.nanmax(rel):.2e}")
    st = lv[(lv.kind == "static") & ~lv.is_placebo]
    print("static levels off the tick grid: " + str(int((np.abs(st.value * 4 - np.round(st.value * 4)) > 1e-9).sum()))
          + f" of {len(st)} (pdm only: {int(((np.abs(st.value * 4 - np.round(st.value * 4)) > 1e-9) & (st.code == 'pdm')).sum())})")
    print("days by number of expected-move blocks with bands: "
          + str(lv[(lv.code == 'em1u')].groupby('date').size().value_counts().sort_index().to_dict()))
    # the Pine script keeps accumulating when no bar lies between two overnight sessions
    D = ctx.days
    n_join = 0
    for d in D.index:
        on0 = ctx.span(d - ONE, 1080, 1440)[0]
        if on0 > 0:
            t_prev = ctx.tod[on0 - 1]
            n_join += bool(t_prev >= 1080 or t_prev < 570)
    print(f"cash days whose overnight session directly follows another overnight bar (the script would not restart "
          f"its profile there): {n_join}")
    tied = e[(e.kind == "static") & ~e.is_placebo & e.lead & (e.cl_n > 1)]
    print(f"tied leads: clusters with more than one lead {int((tied.groupby('cid').size() > 1).sum())}")


def main():
    import run
    ap = argparse.ArgumentParser()
    ap.add_argument("--extra", action="store_true")
    a = ap.parse_args()
    pd.set_option("display.width", 250)
    ctx = core.Ctx(run.bars("is"))
    ev = pd.read_parquet(core.OUT / "is" / "LEV1_events.parquet")
    if a.extra:
        extra(ctx, ev, LL.levels(ctx))
        return
    for title, r in chosen(ev):
        explain(ctx, ev, r, title)


if __name__ == "__main__":
    main()
