#!/usr/bin/env python3
"""MECH: one coded reading of the Andrew Macre "mech model" (BACKTEST_LOG.md, "MECH"; spec in data/studies/mech/).

    python3 tools/mech.py v0 [--swing 3]        primitives, the Ep 12 week charts, claims 1 and 2
    python3 tools/mech.py v1 [--swing 3]        V1 core (and the 60-point catastrophic-stop variant), neighbours
    python3 tools/mech.py prop                  prop-firm simulation on V1
    python3 tools/mech.py charts                10 random V1 trades cut at entry

Data: MNQ and ES 1m (Databento, New York time). ES on the MNQ clock; a missing ES minute is a flat bar at the last
close. N-minute bars are counted from the 18:00 open of the trading day. Everything is evaluated on the 1m clock: a
bar is known at the close of its last minute, a swing at the close of the SWING_N-th bar after it, a zone at the later
of its third candle's close and its swing's confirmation.
"""
import sys, pathlib, collections
import numpy as np
import pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from ifvg_engine import trading_date, rma_atr

TZ = "America/New_York"
TICK, PV, COMM = 0.25, 2.0, 1.0
OUT = pathlib.Path("data/studies/mech")
ZONE_TFS, PTR_TFS = (1, 2, 3, 4, 5), (3, 4, 5, 6)
WIN0, WIN1 = 9 * 60 + 35, 15 * 60 + 50            # pointer bars open >= 09:35, close by 15:50
LIFE_DAYS, FFVG_WITHIN = 5, 120                    # zone life (trading days), minutes to find the first FVG
CAT = 60.0                                         # catastrophic stop and R unit, NQ points
S = {}


# ---------------------------------------------------------------- data
def load():
    if "ts" in S:
        return S
    a = pd.read_parquet("data/bars/MNQ_1m.parquet")
    e = pd.read_parquet("data/bars/ES_1m.parquet").reindex(a.index)
    c = e.close.ffill()
    miss = e.close.isna()
    for k in ("open", "high", "low"):
        e[k] = e[k].where(~miss, c)
    e["close"] = c
    e["instrument_id"] = e.instrument_id.ffill()
    ts = a.index
    td = trading_date(ts)
    tdi = pd.factorize(td)[0]
    off = ((ts.tz_localize(None) - (td - pd.Timedelta(hours=6))) // pd.Timedelta(minutes=1)).to_numpy().astype(int)
    tod = (ts.hour * 60 + ts.minute).to_numpy()
    day_first = np.r_[0, np.flatnonzero(np.diff(tdi)) + 1]
    S.update(ts=ts, td=td, tdi=tdi, off=off, tod=tod, day_first=day_first, n=len(ts),
             mk={"NQ": a, "ES": e.bfill()})
    ev = pd.read_csv("data/events.csv")
    S["early"] = set(ev[ev.type == "early_close"].date)
    S["lock"] = lockouts(ev, ts)
    return S


def lockouts(ev, ts):
    """1m index intervals [a, b) with no entries; an open trade is closed at a. Releases T-5..T+10, FOMC T-10..T+90."""
    out = []
    for r in ev[~ev.type.isin(["opex", "early_close"])].itertuples():
        h, m = map(int, r.time_ny.split(":"))
        t = pd.Timestamp(r.date).tz_localize(TZ) + pd.Timedelta(hours=h, minutes=m)
        lo, hi = (t - pd.Timedelta(minutes=10), t + pd.Timedelta(minutes=90)) if r.type == "FOMC" else \
            (t - pd.Timedelta(minutes=5), t + pd.Timedelta(minutes=10))
        if 9 * 60 + 30 <= h * 60 + m + 90 and h * 60 + m - 10 <= 16 * 60:
            out.append((ts.searchsorted(lo), ts.searchsorted(hi)))
    return sorted(out)


def tf_bars(x, k):
    """N-minute bars counted from the 18:00 open: arrays O, H, L, C, first / last 1m index, bar of each 1m bar."""
    key = S["tdi"].astype(np.int64) * 2000 + S["off"] // k
    new = np.r_[True, key[1:] != key[:-1]]
    first = np.flatnonzero(new)
    last = np.r_[first[1:] - 1, len(key) - 1]
    O, H, L, C = (x[c].to_numpy() for c in ("open", "high", "low", "close"))
    return dict(O=O[first], H=np.maximum.reduceat(H, first), L=np.minimum.reduceat(L, first), C=C[last],
                first=first, last=last, of=np.cumsum(new) - 1, tdi=S["tdi"][first])


# ---------------------------------------------------------------- one index: swings, FFVGs, zone phases, pointers
def build(name, swing_n=3):
    load()
    x = S["mk"][name]
    H1, L1 = x.high.to_numpy(), x.low.to_numpy()
    n = S["n"]
    epoch = np.cumsum(np.r_[True, x.instrument_id.to_numpy()[1:] != x.instrument_id.to_numpy()[:-1]])
    B = {k: tf_bars(x, k) for k in sorted(set(ZONE_TFS) | set(PTR_TFS))}
    for k, b in B.items():
        b["ep"] = epoch[b["first"]]
    b5 = B[5]
    # life end of a zone formed on trading day d: start of trading day d + LIFE_DAYS + 1, or the roll
    dfirst = S["day_first"]
    ep_end = np.r_[np.flatnonzero(np.diff(epoch)) + 1, n]
    ep_end_of = ep_end[np.searchsorted(ep_end, np.arange(n), side="right")]

    def life_end(i1m):
        d = S["tdi"][i1m] + LIFE_DAYS + 1
        return min(dfirst[d] if d < len(dfirst) else n, ep_end_of[i1m])

    # 5m fractals
    H5, L5, m5 = b5["H"], b5["L"], len(b5["H"])
    sw = []                                        # (bar p, is_high, price)
    for p in range(swing_n, m5 - swing_n):
        if b5["ep"][p - swing_n] != b5["ep"][p + swing_n]:
            continue
        if H5[p] > H5[p - swing_n:p].max() and H5[p] >= H5[p + 1:p + swing_n + 1].max():
            sw.append((p, True, H5[p]))
        if L5[p] < L5[p - swing_n:p].min() and L5[p] <= L5[p + 1:p + swing_n + 1].min():
            sw.append((p, False, L5[p]))
    hi_bars = np.array([p for p, h, _ in sw if h]); lo_bars = np.array([p for p, h, _ in sw if not h])
    # FVG flags per zone timeframe (three bars in one trading day)
    for k in ZONE_TFS:
        b = B[k]
        same = np.r_[False, False, (b["tdi"][2:] == b["tdi"][:-2])]
        b["fvg_bull"] = np.r_[False, False, b["L"][2:] > b["H"][:-2]] & same
        b["fvg_bear"] = np.r_[False, False, b["H"][2:] < b["L"][:-2]] & same
    zones, seen = [], set()
    prev = {True: None, False: None}
    for p, is_high, px in sw:
        last_px = prev[is_high]
        prev[is_high] = px
        if last_px is None or not ((px > last_px) if is_high else (px < last_px)):
            continue                                   # not sweep-type
        f0, f1 = b5["first"][p], b5["last"][p]
        ext = f0 + int(np.argmax(H1[f0:f1 + 1]) if is_high else np.argmin(L1[f0:f1 + 1]))
        conf = b5["last"][p + swing_n]
        opp = hi_bars if not is_high else lo_bars
        q = opp[np.searchsorted(opp, p, side="right")] if np.searchsorted(opp, p, side="right") < len(opp) else None
        deadline = min(b5["last"][q] if q is not None else n - 1,
                       S["ts"].searchsorted(S["ts"][ext] + pd.Timedelta(minutes=FFVG_WITHIN)) - 1)
        bull = not is_high                             # swing low -> bullish FFVGs (demand)
        for k in ZONE_TFS:
            b = B[k]
            b0 = b["of"][ext]
            iend = np.searchsorted(b["last"], deadline, side="right") - 1
            if iend < b0 + 2:
                continue
            fl = (b["fvg_bull"] if bull else b["fvg_bear"])[b0 + 2:iend + 1]
            h = np.flatnonzero(fl)
            if not len(h):
                continue
            i = b0 + 2 + h[0]
            if (k, i, bull) in seen:
                continue
            seen.add((k, i, bull))
            bot, top = (b["H"][i - 2], b["L"][i]) if bull else (b["H"][i], b["L"][i - 2])
            zones.append(dict(tf=k, i=i, bull=bull, bot=bot, top=top, form=b["last"][i], known=max(b["last"][i], conf),
                              ext=ext, swing=p))
    # lifecycle -> phases (act +1 = demand, -1 = supply) and tap events
    ph = []
    for z in zones:
        b = B[z["tf"]]
        end = life_end(z["form"])
        s1 = z["form"] + 1
        if s1 >= end:
            continue
        seg = (L1[s1:end] <= z["top"]) if z["bull"] else (H1[s1:end] >= z["bot"])
        tap1 = s1 + int(np.argmax(seg)) if seg.any() else end
        ib0, ib1 = z["i"] + 1, np.searchsorted(b["last"], end - 1, side="right")
        cl = b["C"][ib0:ib1]
        thr = (cl < z["bot"]) if z["bull"] else (cl > z["top"])
        inv_bar = ib0 + int(np.argmax(thr)) if thr.any() else None
        inv = b["last"][inv_bar] if inv_bar is not None else end
        act = 1 if z["bull"] else -1
        if z["known"] < inv:
            ph.append(dict(tf=z["tf"], act=act, bot=z["bot"], top=z["top"], start=z["known"], end=inv,
                           tap=tap1 if z["known"] <= tap1 < inv else None, untap_until=min(tap1, inv),
                           kind="FFVG", ext=z["ext"]))
        if inv_bar is not None:
            st = max(inv, z["known"])
            s2 = inv + 1
            seg = (H1[s2:end] >= z["bot"]) if z["bull"] else (L1[s2:end] <= z["top"])
            tap2 = s2 + int(np.argmax(seg)) if seg.any() else end
            cl = b["C"][inv_bar + 1:ib1]
            thr = (cl > z["top"]) if z["bull"] else (cl < z["bot"])
            rem = b["last"][inv_bar + 1 + int(np.argmax(thr))] if thr.any() else end
            if st < rem:
                ph.append(dict(tf=z["tf"], act=-act, bot=z["bot"], top=z["top"], start=st, end=rem,
                               tap=tap2 if st <= tap2 < rem else None, untap_until=min(tap2, rem),
                               kind="IFFVG", ext=z["ext"]))
    P = pd.DataFrame(ph)
    P["pid"] = np.arange(len(P))
    # pointers on 3-6m bars, untapped reactions
    taps = P[P.tap.notna()]
    tap_t = {d: np.sort(taps[taps.act == d].tap.to_numpy().astype(np.int64)) for d in (1, -1)}
    tap_p = {d: taps[taps.act == d].sort_values("tap").pid.to_numpy() for d in (1, -1)}
    ptrs = []
    tod = S["tod"]
    for m in PTR_TFS:
        b = B[m]
        O, H, L, C = b["O"], b["H"], b["L"], b["C"]
        ok = np.r_[False, b["tdi"][1:] == b["tdi"][:-1]]
        bull = ok & np.r_[False, (C[1:] > np.maximum(O[:-1], C[:-1])) & (C[1:] <= H[:-1])]
        bear = ok & np.r_[False, (C[1:] < np.minimum(O[:-1], C[:-1])) & (C[1:] >= L[:-1])]
        t_open, t_close = tod[b["first"]], tod[b["last"]]
        win = (t_open >= WIN0) & (t_close <= WIN1 - 1) & (t_open < 16 * 60)
        for d, fl in ((1, bull), (-1, bear)):
            for bi in np.flatnonzero(fl & win):
                lo_t, hi_t = b["first"][bi - 1], b["last"][bi]
                tt = tap_t[d]
                a_, z_ = np.searchsorted(tt, lo_t), np.searchsorted(tt, hi_t, side="right")
                if z_ > a_:
                    swept = (H[bi] > H[bi - 1]) if d > 0 else (L[bi] < L[bi - 1])
                    ptrs.append(dict(idx=name, tf=m, dir=d, t=hi_t, t0=b["first"][bi], hi=H[bi], lo=L[bi], close=C[bi],
                                     swept=bool(swept), pid=int(tap_p[d][z_ - 1]), tap=int(tt[z_ - 1])))
    Q = pd.DataFrame(ptrs).sort_values(["t", "tf"]).reset_index(drop=True)
    return dict(name=name, B=B, P=P, Q=Q, n_swings=len(sw), n_zones=len(zones), sw=sw, H1=H1, L1=L1,
                C1=x.close.to_numpy())


def build_all(swing_n=3):
    key = f"built{swing_n}"
    if key not in S:
        S[key] = {nm: build(nm, swing_n) for nm in ("NQ", "ES")}
    return S[key]


def signals(W):
    """All untapped-reaction pointers of both indices with their grade label (correlated within +-5 minutes)."""
    Q = pd.concat([W["NQ"]["Q"], W["ES"]["Q"]], ignore_index=True).sort_values(["t", "tf"]).reset_index(drop=True)
    ts = S["ts"]
    tm = ts[Q.t.to_numpy()]
    Q["time"] = tm
    corr, corr_known = [], []
    other_t = {(nm, d): np.sort(ts[Q[(Q.idx == nm) & (Q.dir == d)].t.to_numpy()].asi8) for nm in ("NQ", "ES") for d in (1, -1)}
    five = pd.Timedelta(minutes=5).value
    for r in Q.itertuples():
        arr = other_t[("ES" if r.idx == "NQ" else "NQ", r.dir)]
        t = r.time.value
        a_, b_ = np.searchsorted(arr, t - five), np.searchsorted(arr, t + five, side="right")
        corr.append(b_ > a_)
        b2 = np.searchsorted(arr, t, side="right")
        corr_known.append(b2 > a_)
    Q["correlated"], Q["corr_known"] = corr, corr_known
    Q["grade"] = np.where(Q.swept, "swept", np.where(Q.correlated, "correlated", "SMT"))
    return Q


def day_index(P):
    """trading day -> array of phase rows alive at some point that day."""
    tdi = S["tdi"]
    d0, d1 = tdi[P.start.to_numpy()], tdi[np.minimum(P.end.to_numpy() - 1, S["n"] - 1)]
    out = collections.defaultdict(list)
    for r, a_, b_ in zip(range(len(P)), d0, d1):
        for d in range(a_, b_ + 1):
            out[d].append(r)
    return {d: np.array(v) for d, v in out.items()}


def ok_day(t):
    return S["ts"][t].strftime("%Y-%m-%d") not in S["early"]


def in_lock(a_, b_):
    for lo, hi in S["lock"]:
        if lo < b_ and hi > a_:
            return True
    return False


def target(W, nm, t, d, e, DI, count=False):
    """Nearest untapped zone ahead acting against d on index nm at 1m t from price e, and whether the path is clear
    (count=True: the number of live zones in between instead of the flag)."""
    P = W[nm]["P"]
    rows = DI[nm].get(S["tdi"][t])
    if rows is None:
        return None, False
    x = P.iloc[rows]
    live = x[(x.start <= t) & (x.end > t)]
    if d > 0:
        c = live[(live.act == -1) & (live.untap_until > t) & (live.bot > e)]
        if c.empty:
            return None, False
        tg = c.bot.min()
        between = live[(live.bot >= e) & (live.bot < tg)]
    else:
        c = live[(live.act == 1) & (live.untap_until > t) & (live.top < e)]
        if c.empty:
            return None, False
        tg = c.top.max()
        between = live[(live.top <= e) & (live.top > tg)]
    return tg, (len(between) if count else between.empty)


def claims(W, Q):
    DI = {nm: day_index(W[nm]["P"]) for nm in ("NQ", "ES")}
    tod = S["tod"]
    # claim 1
    rows = []
    U = Q.drop_duplicates(["idx", "t", "dir"])
    for r in U.itertuples():
        if not ok_day(r.t):
            continue
        X, Y = W[r.idx], W["ES" if r.idx == "NQ" else "NQ"]
        e = X["C1"][r.t]
        tg, clear = target(W, r.idx, r.t, r.dir, e, DI)
        if tg is None or not clear:
            continue
        tgy, cleary = target(W, Y["name"], r.t, r.dir, Y["C1"][r.t], DI)
        if tgy is None or not cleary:
            continue
        end = r.t + 1
        while end < S["n"] and S["tdi"][end] == S["tdi"][r.t] and tod[end] <= 15 * 60 + 49:
            end += 1
        Hs, Ls = X["H1"][r.t + 1:end], X["L1"][r.t + 1:end]
        hit = (Hs >= tg) if r.dir > 0 else (Ls <= tg)
        back = (Ls < e) if r.dir > 0 else (Hs > e)
        ih = int(np.argmax(hit)) if hit.any() else None
        ib = int(np.argmax(back)) if back.any() else None
        res = "target first" if ih is not None and (ib is None or ih < ib) else \
            ("through entry first" if ib is not None else "neither by 15:50")
        # observation, not pre-registered: failure only beyond the pointer candle's far extreme (its range of control)
        far = (Ls < r.lo) if r.dir > 0 else (Hs > r.hi)
        ip = int(np.argmax(far)) if far.any() else None
        res_proc = "target first" if ih is not None and (ip is None or ih < ip) else \
            ("beyond pointer extreme first" if ip is not None else "neither by 15:50")
        rows.append(dict(idx=r.idx, tf=r.tf, dir=r.dir, t=r.t, dist=abs(tg - e), res=res, res_proc=res_proc,
                         lock=in_lock(r.t, end)))
    C1 = pd.DataFrame(rows)
    # claim 2: MNQ 5m reversals of >= 1 ATR
    b5 = W["NQ"]["B"][5]
    atr = rma_atr(b5["H"], b5["L"], b5["C"])
    sw = W["NQ"]["sw"]
    highs = np.array([p for p, h, _ in sw if h]); lows = np.array([p for p, h, _ in sw if not h])
    pt = {d: np.sort(Q[Q.dir == d].t.to_numpy()) for d in (1, -1)}
    rev = []
    for p, is_high, px in sw:
        opp = lows if is_high else highs
        j = np.searchsorted(opp, p, side="right")
        if j >= len(opp):
            continue
        q = opp[j]
        a_ = atr[p]
        d = -1 if is_high else 1
        mv = (px - b5["L"][q]) if is_high else (b5["H"][q] - px)
        if not np.isfinite(a_) or mv < a_:
            continue
        cl = b5["C"][p + 1:q + 1]
        reach = (px - cl >= a_) if is_high else (cl - px >= a_)
        if not reach.any():
            continue
        k = p + 1 + int(np.argmax(reach))
        f0, f1 = b5["first"][p], b5["last"][k]
        if b5["tdi"][p] != b5["tdi"][k] or tod[f0] < WIN0 or tod[f1] > WIN1 - 1 or not ok_day(f0) or k - 3 < 0:
            continue
        w0, w1 = b5["first"][k - 3], b5["last"][k]
        arr = pt[d]
        has = np.searchsorted(arr, w1, side="right") > np.searchsorted(arr, w0)
        rev.append(dict(p=p, k=k, dir=d, atr=a_, move=mv, has_ptr=bool(has), lock=in_lock(f0, w1), t=f0))
    C2 = pd.DataFrame(rev)
    return C1, C2


def week_charts(W, Q, days=("2026-03-02", "2026-03-03", "2026-03-04", "2026-03-05", "2026-03-06")):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle
    out = OUT / "v0_charts"; out.mkdir(parents=True, exist_ok=True)
    ts = S["ts"]
    for day in days:
        d0 = pd.Timestamp(day).tz_localize(TZ)
        w0, w1 = ts.searchsorted(d0 + pd.Timedelta(hours=8)), ts.searchsorted(d0 + pd.Timedelta(hours=16))
        fig, axes = plt.subplots(2, 1, figsize=(22, 13))
        for ax, nm in zip(axes, ("NQ", "ES")):
            b = W[nm]["B"][5]
            bi = np.flatnonzero((b["first"] >= w0) & (b["first"] < w1))
            for x_, i in enumerate(bi):
                o, h, l, c = b["O"][i], b["H"][i], b["L"][i], b["C"][i]
                col = "#26a69a" if c >= o else "#ef5350"
                ax.plot([x_, x_], [l, h], color=col, lw=0.8)
                ax.add_patch(Rectangle((x_ - 0.35, min(o, c)), 0.7, max(abs(c - o), 0.05), color=col, lw=0))
            xof = lambda t1: np.searchsorted(b["first"][bi], t1, side="right") - 1
            lo_, hi_ = b["L"][bi].min(), b["H"][bi].max()
            P = W[nm]["P"]
            live = P[(P.start < w1) & (P.end > w0) & (P.top >= lo_ - 20) & (P.bot <= hi_ + 20)]
            for z in live.itertuples():
                xa, xb = max(xof(max(z.start, w0)), 0), xof(min(z.end, w1) - 1)
                xu = xof(min(z.untap_until, w1) - 1)
                col = "#2e7d32" if z.act > 0 else "#c62828"
                if z.untap_until > max(z.start, w0):
                    ax.add_patch(Rectangle((xa - 0.5, z.bot), max(xu - xa + 1, 0.6), z.top - z.bot, color=col, alpha=0.30, lw=0))
                ax.add_patch(Rectangle((xa - 0.5, z.bot), xb - xa + 1, z.top - z.bot, fill=False, ec=col, alpha=0.35, lw=0.6,
                                       ls="-" if z.kind == "FFVG" else "--"))
                ax.text(xa - 0.4, z.top, f"{z.tf}{'' if z.kind == 'FFVG' else 'i'}", fontsize=5, color=col, va="bottom",
                        clip_on=True)
            q = Q[(Q.idx == nm) & (Q.t >= w0) & (Q.t < w1)].drop_duplicates(["t", "dir"])
            for r in q.itertuples():
                xx = xof(r.t)
                y = (b["L"][bi].min() if False else (r.lo - 0.0015 * (hi_ - lo_) * 10 if r.dir > 0 else r.hi + 0.0015 * (hi_ - lo_) * 10))
                ax.plot(xx, y, "^" if r.dir > 0 else "v", color="#1b5e20" if r.dir > 0 else "#b71c1c", ms=9)
                ax.text(xx, y, f" {r.tf}m{' S' if r.swept else ''}{' C' if r.correlated else ''}", fontsize=6,
                        va="top" if r.dir > 0 else "bottom")
            ax.set_ylim(lo_ - 0.03 * (hi_ - lo_), hi_ + 0.03 * (hi_ - lo_))
            ticks = [x_ for x_, i in enumerate(bi) if ts[b["first"][i]].minute % 30 == 0]
            ax.set_xticks(ticks, [ts[b["first"][bi[x_]]].strftime("%H:%M") for x_ in ticks], fontsize=7)
            ax.set_xlim(-1, len(bi))
            ax.axvline(xof(ts.searchsorted(d0 + pd.Timedelta(hours=9, minutes=30))) - 0.5, color="gray", lw=0.6, ls=":")
            ax.set_title(f"{nm if nm == 'ES' else 'NQ (MNQ prices)'} 5m · {day} · zones: green demand / red supply, "
                         f"filled = untapped, solid = FFVG, dashed = IFFVG, label = timeframe (i = inverse) · "
                         f"triangles = untapped-reaction pointers (tf, S = swept, C = correlated)", fontsize=9, loc="left")
            ax.grid(alpha=0.15)
        fig.tight_layout()
        fig.savefig(out / f"mech_v0_{day}.png", dpi=90)
        plt.close(fig)
    print(f"charts in {out}")


def run_v0(swing_n=3):
    OUT.mkdir(parents=True, exist_ok=True)
    W = build_all(swing_n)
    Q = signals(W)
    for nm in ("NQ", "ES"):
        w = W[nm]
        print(f"{nm}: swings {w['n_swings']}, FFVGs {w['n_zones']}, phases {len(w['P'])} "
              f"({(w['P'].kind == 'IFFVG').sum()} IFFVG), untapped-reaction pointers {len(w['Q'])}")
    U = Q.drop_duplicates(["idx", "t", "dir"])
    print(f"pointer events (index, minute, direction) {len(U)}: correlated {U.correlated.mean():.1%}, swept {U.swept.mean():.1%}")
    week_charts(W, Q)
    C1, C2 = claims(W, Q)
    C1.to_csv(OUT / "claim1.csv", index=False); C2.to_csv(OUT / "claim2.csv", index=False)
    print("\nCLAIM 1 (pointer with a clear path on both indices reaches the next untapped zone before trading through entry)")
    for lab, x in (("all", C1), ("outside news lockouts", C1[~C1.lock])):
        vc = x.res.value_counts()
        print(f"  {lab}: {len(x)} qualifying pointers; " + ", ".join(f"{k} {v} ({v / len(x):.1%})" for k, v in vc.items())
              + f"; median distance to target {x.dist.median():.1f} pts")
    for nm, g in C1.groupby("idx"):
        print(f"    {nm}: n {len(g)}, target first {(g.res == 'target first').mean():.1%}")
    vc = C1.res_proc.value_counts()
    print("  observation (not pre-registered): failure only beyond the pointer candle's far extreme: "
          + ", ".join(f"{k} {v} ({v / len(C1):.1%})" for k, v in vc.items()))
    rate = (C1.res == "target first").mean()
    print(f"  success rate {rate:.1%} -> " + ("ADDITIVE-TRIM PREMISE DOES NOT HOLD (< 60 %)" if rate < 0.60 else "at or above 60 %"))
    print("\nCLAIM 2 (5m reversals of >= 1 ATR without an untapped-reaction pointer in their direction in the prior 3 bars)")
    for lab, x in (("all", C2), ("outside news lockouts", C2[~C2.lock])):
        print(f"  {lab}: {len(x)} reversals; with a pointer {int(x.has_ptr.sum())} ({x.has_ptr.mean():.1%}), "
              f"without {int((~x.has_ptr).sum())} ({(~x.has_ptr).mean():.1%})")
    return W, Q, C1, C2


def sig_minutes(Q):
    """One signal per (minute, direction); a minute with both directions is dropped (indices disagree = no trade)."""
    rows = []
    for t, g in Q.groupby("t"):
        dirs = set(g.dir)
        if len(dirs) > 1 or not ok_day(t):
            continue
        d = dirs.pop()
        grade = "correlated" if (g.correlated & ~g.swept).any() else ("SMT" if (~g.swept).any() else "swept")
        rows.append(dict(t=t, dir=d, grade=grade, corr_known=bool((g.corr_known & ~g.swept).any()),
                         swept=bool(g.swept.all()), idx="+".join(sorted(set(g.idx)))))
    return pd.DataFrame(rows)


def lock_at(t):
    for lo, hi in S["lock"]:
        if lo <= t < hi:
            return True
    return False


def v1_trades(W, Q, stop=None):
    """V1: always in after a signal, reverse on an opposite signal, flat 15:50 / before a lockout; optional stop."""
    G = sig_minutes(Q)
    nq = W["NQ"]
    O1, H1, L1, C1 = S["mk"]["NQ"].open.to_numpy(), nq["H1"], nq["L1"], nq["C1"]
    tod, tdi = S["tod"], S["tdi"]
    locks = S["lock"]
    lock_starts = np.array([a for a, b in locks])
    out = []
    for day, g in G.groupby(tdi[G.t.to_numpy()]):
        # flat bar of the day: the 15:49 bar
        d0 = S["day_first"][day]
        d1 = S["day_first"][day + 1] if day + 1 < len(S["day_first"]) else S["n"]
        fl = np.flatnonzero(tod[d0:d1] == 15 * 60 + 49)
        if not len(fl):
            continue
        flat = d0 + fl[0]
        pos = None
        sigs = list(g.itertuples())

        def close(pos, x, px, why):
            d = pos["dir"]
            seg_l, seg_h = L1[pos["t"] + 1:x + 1], H1[pos["t"] + 1:x + 1]
            if len(seg_l):
                mae = (pos["entry"] - seg_l.min()) if d > 0 else (seg_h.max() - pos["entry"])
                mfe = (seg_h.max() - pos["entry"]) if d > 0 else (pos["entry"] - seg_l.min())
            else:
                mae = mfe = 0.0
            pnl = d * (px - pos["entry"]) * PV - 2 * COMM
            out.append(dict(entry_t=pos["t"], exit_t=x, dir=d, entry=pos["entry"], exit=px, why=why, pnl=pnl,
                            R=pnl / (CAT * PV), mae=max(mae, 0) if len(seg_l) else 0.0, mfe=max(mfe, 0) if len(seg_l) else 0.0,
                            grade=pos["grade"], corr_known=pos["corr_known"], idx=pos["idx"]))

        def run_until(pos, x_end):
            """advance an open trade to bar x_end (inclusive); returns (pos or None) after checking the stop."""
            if stop is None or pos is None:
                return pos
            d, sp = pos["dir"], pos["stop"]
            for j in range(pos["chk"], x_end + 1):
                if d * (O1[j] - sp) <= 0 and j > pos["t"]:
                    close(pos, j, O1[j] - d * TICK, "stop"); return None
                if (L1[j] <= sp) if d > 0 else (H1[j] >= sp):
                    close(pos, j, sp - d * TICK, "stop"); return None
            pos["chk"] = x_end + 1
            return pos

        def lock_between(a_, b_):
            k = np.searchsorted(lock_starts, a_, side="right")
            return lock_starts[k] if k < len(lock_starts) and lock_starts[k] <= b_ else None

        for r in sigs:
            if r.t >= flat:                            # no entry on or after the flat bar
                break
            if pos is not None:
                lk = lock_between(pos["t"], r.t)
                if lk is not None:
                    pos = run_until(pos, lk - 1)
                    if pos is not None:
                        close(pos, lk - 1, C1[lk - 1] - pos["dir"] * TICK, "news"); pos = None
                pos = run_until(pos, r.t)
            if lock_at(r.t):
                continue
            if pos is not None and r.dir == pos["dir"]:
                continue
            if pos is not None:
                close(pos, r.t, C1[r.t] - pos["dir"] * TICK, "opposite pointer")
            e = C1[r.t] + r.dir * TICK
            pos = dict(t=r.t, dir=r.dir, entry=e, grade=r.grade, corr_known=r.corr_known, idx=r.idx,
                       stop=(e - r.dir * stop) if stop else None, chk=r.t + 1)
        if pos is not None:
            lk = lock_between(pos["t"], flat)
            end = lk - 1 if lk is not None else flat
            pos = run_until(pos, end)
            if pos is not None:
                close(pos, end, C1[end] - pos["dir"] * TICK, "news" if lk is not None else "15:50")
    T = pd.DataFrame(out)
    T["et"] = S["ts"][T.entry_t.to_numpy()]
    T["side"] = np.where(T.dir > 0, "L", "S")
    return T


def summ(t):
    y = t.et.dt.year
    by = t.groupby(y).pnl.sum()
    eq = t.pnl.cumsum()
    gw, gl = t.pnl[t.pnl > 0].sum(), -t.pnl[t.pnl < 0].sum()
    return dict(n=len(t), net=round(t.pnl.sum()), R=round(t.R.mean(), 4), win=round(100 * (t.pnl > 0).mean(), 1),
                pf=round(gw / gl, 2) if gl else None, dd=round((eq - eq.cummax()).min()), pos_years=int((by > 0).sum()),
                years=int(y.nunique()), R_h1=round(t[y <= 2022].R.mean(), 4), R_h2=round(t[y >= 2023].R.mean(), 4))


def boot_p(R, n=10000, seed=1):
    R = np.asarray(R, dtype=float)
    rng = np.random.default_rng(seed)
    return float((R[rng.integers(0, len(R), size=(n, len(R)))].mean(axis=1) <= 0).mean())


def report_v1(name, T, nb, k_stages):
    s = summ(T)
    p = boot_p(T.R)
    alpha = 0.05 / k_stages
    parts = dict(years=s["pos_years"] >= 6, R=s["R"] >= 0.05, halves=s["R_h1"] >= 0 and s["R_h2"] >= 0,
                 neighbours=all(np.sign(x["R"]) == np.sign(s["R"]) and x["R"] != 0 for x in nb), p=p < alpha)
    print(f"\n==== {name}: " + "  ".join(f"{k} {v}" for k, v in s.items()) + f"  p {p:.4f} (alpha {alpha:.4f})")
    y = T.et.dt.year
    print("  by year (R, n, net): " + " | ".join(f"{k} {g.R.mean():+.3f} {len(g)} {g.pnl.sum():+,.0f}" for k, g in T.groupby(y)))
    print("  side: " + " | ".join(f"{k}: n {len(g)} net {g.pnl.sum():+,.0f} R {g.R.mean():+.3f}" for k, g in T.groupby("side")))
    print("  grade: " + " | ".join(f"{k}: n {len(g)} net {g.pnl.sum():+,.0f} R {g.R.mean():+.3f} win {100 * (g.pnl > 0).mean():.0f}%"
                                  for k, g in T.groupby("grade")))
    print("  hour: " + " | ".join(f"{k}: n {len(g)} R {g.R.mean():+.3f} net {g.pnl.sum():+,.0f}" for k, g in T.groupby(T.et.dt.hour)))
    print("  exits: " + ", ".join(f"{k} {v}" for k, v in T.why.value_counts().items()) +
          f"; minutes in trade median {np.median(T.exit_t - T.entry_t):.0f}")
    q = T.mae.quantile([.5, .75, .9, .95, .99])
    print("  MAE points: median {:.1f} / p75 {:.1f} / p90 {:.1f} / p95 {:.1f} / p99 {:.1f} / max {:.1f}; share > 40 {:.1%}, > 60 {:.1%}, > 100 {:.1%}".format(
        *q.values, T.mae.max(), (T.mae > 40).mean(), (T.mae > 60).mean(), (T.mae > 100).mean()))
    print("  neighbours (SWING_N 2 / 4) R: " + " / ".join(str(x["R"]) for x in nb))
    print(f"  criterion: {'PASS' if all(parts.values()) else 'fail'} {parts}")
    return dict(run=name, **s, p=p, nb=[x["R"] for x in nb], passes=all(parts.values()))


def minute_info(Q):
    """Per signal minute: reference index (NQ if it printed), its smallest-timeframe pointer (pid, hi, lo)."""
    info = {}
    for t, g in Q.groupby("t"):
        x = g[g.idx == "NQ"] if (g.idx == "NQ").any() else g
        r = x.sort_values("tf").iloc[0]
        info[t] = dict(ref=r.idx, pid=int(r.pid), hi=r.hi, lo=r.lo)
    return info


class PO3:
    """Pointer rule of three: 3 signals alternating in direction within 3 x 5m ATR -> on, with the range of NQ prices
    between the first and third; resets at the session start, or when NQ closes beyond the range and then touches an
    untapped zone beyond it."""
    def __init__(s, W, DI):
        s.W, s.DI, s.hist, s.on, s.day = W, DI, [], None, None
        b5 = W["NQ"]["B"][5]
        s.atr = rma_atr(b5["H"], b5["L"], b5["C"])
        s.of5 = b5["of"]

    def update(s, t, d):
        """Record signal (t, d); return the PO3 state at t (before this signal joins the count)."""
        day = S["tdi"][t]
        if day != s.day:
            s.day, s.hist, s.on = day, [], None
        if s.on is not None and s._reset(t):
            s.on, s.hist = None, []
        state = s.on
        s.hist.append((t, d))
        h = s.hist[-3:]
        if s.on is None and len(h) == 3 and h[0][1] == h[2][1] != h[1][1]:
            H1, L1, C1 = s.W["NQ"]["H1"], s.W["NQ"]["L1"], s.W["NQ"]["C1"]
            closes = [C1[x] for x, _ in h]
            a5 = s.atr[s.of5[t] - 1]
            if np.isfinite(a5) and max(closes) - min(closes) < 3 * a5:
                s.on = dict(t=t, hi=H1[h[0][0]:t + 1].max(), lo=L1[h[0][0]:t + 1].min())
        return state

    def _reset(s, t):
        o = s.on
        C1, H1, L1 = s.W["NQ"]["C1"], s.W["NQ"]["H1"], s.W["NQ"]["L1"]
        seg = C1[o["t"] + 1:t + 1]
        up, dn = seg > o["hi"], seg < o["lo"]
        for side, br in ((1, up), (-1, dn)):
            if not br.any():
                continue
            j = o["t"] + 1 + int(np.argmax(br))
            tg, _ = target(s.W, "NQ", j, side, C1[j], s.DI)
            if tg is None:
                continue
            hit = (H1[j + 1:t + 1] >= tg) if side > 0 else (L1[j + 1:t + 1] <= tg)
            if hit.any():
                return True
        return False


def v23_trades(W, Q, use_po3=False):
    """V2 (grades, 5/10 sizing, swept add, skip rules) and V3 (+ PO3 filter). No stop; exits as V1."""
    DI = {nm: day_index(W[nm]["P"]) for nm in ("NQ", "ES")}
    G = sig_minutes(Q)
    info = minute_info(Q)
    nq = W["NQ"]
    O1, H1, L1, C1 = S["mk"]["NQ"].open.to_numpy(), nq["H1"], nq["L1"], nq["C1"]
    ath = np.maximum.accumulate(H1)
    tod, tdi = S["tod"], S["tdi"]
    lock_starts = np.array([a for a, b in S["lock"]])
    latest = {nm: (Q[Q.idx == nm].t.to_numpy(), Q[Q.idx == nm].dir.to_numpy()) for nm in ("NQ", "ES")}
    po3 = PO3(W, DI)
    out, skips = [], collections.Counter()
    for day, g in G.groupby(tdi[G.t.to_numpy()]):
        d0 = S["day_first"][day]
        d1 = S["day_first"][day + 1] if day + 1 < len(S["day_first"]) else S["n"]
        fl = np.flatnonzero(tod[d0:d1] == 15 * 60 + 49)
        if not len(fl):
            continue
        flat = d0 + fl[0]
        pos, last_dir = None, None

        def close(pos, x, why):
            d = pos["dir"]
            px = C1[x] - d * TICK
            add_px = None
            if pos["add_at"] is not None:              # swept pointer: +5 when ITS index trades through its extreme
                hx, lx = W[pos["ref"]]["H1"], W[pos["ref"]]["L1"]
                seg = (hx[pos["t"] + 1:x + 1] > pos["add_at"]) if d > 0 else (lx[pos["t"] + 1:x + 1] < pos["add_at"])
                if seg.any():
                    j = pos["t"] + 1 + int(np.argmax(seg))
                    add_px = C1[j] + d * TICK            # filled on MNQ at that minute's close
            pnl = pos["n"] * (d * (px - pos["entry"]) * PV - 2 * COMM)
            n_tot = pos["n"]
            if add_px is not None:
                pnl += 5 * (d * (px - add_px) * PV - 2 * COMM); n_tot += 5
            sl, sh = L1[pos["t"] + 1:x + 1], H1[pos["t"] + 1:x + 1]
            mae = ((pos["entry"] - sl.min()) if d > 0 else (sh.max() - pos["entry"])) if len(sl) else 0.0
            out.append(dict(entry_t=pos["t"], exit_t=x, dir=d, entry=pos["entry"], exit=px, why=why, n=pos["n"],
                            added=add_px is not None, pnl=pnl, R=pnl / (n_tot * CAT * PV), mae=max(mae, 0),
                            grade=pos["grade"], po3=pos["po3"]))

        for r in g.itertuples():
            if r.t >= flat:
                break
            state = po3.update(r.t, r.dir)
            first_of_leg = last_dir != r.dir
            last_dir = r.dir
            if pos is not None:
                k = np.searchsorted(lock_starts, pos["t"], side="right")
                lk = lock_starts[k] if k < len(lock_starts) and lock_starts[k] <= r.t else None
                if lk is not None:
                    close(pos, lk - 1, "news"); pos = None
            if lock_at(r.t):
                continue
            if pos is not None and r.dir == pos["dir"]:
                continue
            if pos is not None:
                close(pos, r.t, "opposite pointer"); pos = None
            # skip rules
            inf = info[r.t]
            X, Y = inf["ref"], ("ES" if inf["ref"] == "NQ" else "NQ")
            ex = W[X]["C1"][r.t]
            tg, nbetw = target(W, X, r.t, r.dir, ex, DI, count=True)
            tgy, nby = target(W, Y, r.t, r.dir, W[Y]["C1"][r.t], DI, count=True)
            lt, ld = latest[Y]
            k = np.searchsorted(lt, r.t, side="right") - 1
            why = None
            if r.swept and tg is not None and (abs(tg - ex) <= 20 or nbetw > 2):
                why = "swept into an opposing untapped / thick stack"
            elif tgy is not None and nby > 0:
                why = "other index's path not clear"
            elif k >= 0 and ld[k] != r.dir:
                why = "other index pointing the other way"
            elif tg is not None and abs(tg - ex) > 85:
                why = "over 85 points to the opposing untapped"
            elif r.t > 0 and C1[r.t] > ath[r.t - 1]:
                why = "above the prior all-time high"
            elif use_po3 and state is not None:
                P = W[X]["P"]; z = P.iloc[inf["pid"]]
                outside = z.bot > state["hi"] or z.top < state["lo"]
                if not outside and not (tg is not None and nbetw == 0):
                    why = "PO3"
            if why:
                skips[why] += 1
                continue
            plain = not r.swept
            size = 10 if (plain and r.corr_known and first_of_leg) else 5
            add_at = (inf["hi"] if r.dir > 0 else inf["lo"]) if r.swept else None
            pos = dict(t=r.t, dir=r.dir, entry=C1[r.t] + r.dir * TICK, n=size, grade=r.grade, add_at=add_at,
                       po3=state is not None, ref=X)
        if pos is not None:
            k = np.searchsorted(lock_starts, pos["t"], side="right")
            lk = lock_starts[k] if k < len(lock_starts) and lock_starts[k] <= flat else None
            close(pos, lk - 1 if lk is not None else flat, "news" if lk is not None else "15:50")
    T = pd.DataFrame(out)
    T["et"] = S["ts"][T.entry_t.to_numpy()]
    T["side"] = np.where(T.dir > 0, "L", "S")
    return T, skips


def run_v23():
    W = build_all(3)
    Q = signals(W)
    res = {}
    for name, po in (("V2", False), ("V3", True)):
        T, sk = v23_trades(W, Q, use_po3=po)
        T.to_csv(OUT / f"{name.lower()}.csv", index=False)
        nbs = []
        for sn in (2, 4):
            Wn = build_all(sn)
            nbs.append(summ(v23_trades(Wn, signals(Wn), use_po3=po)[0]))
        row = report_v1(name + (" (V2 + PO3 filter)" if po else " (grades, 5/10 sizing, swept add, skip rules)"), T, nbs, 4)
        print(f"  contracts: " + ", ".join(f"{k}: {v}" for k, v in T.n.value_counts().items()) +
              f"; swept adds filled {int(T.added.sum())}; net per trade ${T.pnl.mean():+.1f}")
        print("  skips: " + ", ".join(f"{k} {v}" for k, v in sk.most_common()))
        res[name] = (T, row)
    T2 = res["V2"][0]
    loss = T2[T2.pnl < 0]
    print(f"\nV2 trades entered while PO3 was on: {int(T2.po3.sum())} of {len(T2)}; their net {T2[T2.po3].pnl.sum():+,.0f}; "
          f"share of V2's total loss inside PO3 {loss[loss.po3].pnl.sum() / loss.pnl.sum():.1%} "
          f"(share of V2 trades {T2.po3.mean():.1%})")
    pd.DataFrame([r for _, r in res.values()]).to_csv(OUT / "v23_summary.csv", index=False)
    return res


def run_prop(f="v1.csv"):
    """$50k account, $2,000 trailing drawdown on equity including open P&L (peak from each trade's best point, floor
    from its worst), trail locks at the starting balance; 10 MNQ on correlated plain (known at entry), 5 otherwise.
    One account started on every trading day; days counted in trading days with a trade."""
    T = pd.read_csv(OUT / f)
    T["et"] = pd.to_datetime(T.et, utc=True).dt.tz_convert(TZ)
    plain_corr = (T.grade != "swept") & T.corr_known
    n = np.where(plain_corr, 10, 5)
    pnl = n * T.pnl.to_numpy()                      # pnl per contract already includes costs
    worst = -n * T.mae.to_numpy() * PV
    best = n * T.mfe.to_numpy() * PV
    day = T.et.dt.date.to_numpy()
    starts = np.r_[0, np.flatnonzero(day[1:] != day[:-1]) + 1]
    res = []
    for s0 in starts:
        bal_before = 50000 + np.r_[0, np.cumsum(pnl[s0:])[:-1]]
        peak = np.maximum.accumulate(np.maximum(bal_before, bal_before + best[s0:]))
        peak_before = np.r_[50000, peak[:-1]]
        floor_before = np.minimum(np.maximum(peak_before, 50000) - 2000, 50000)
        dead = bal_before + worst[s0:] < floor_before
        if dead.any():
            k = s0 + int(np.argmax(dead))
            days = len(set(day[s0:k + 1]))
            res.append(dict(start=day[s0], died=True, days=days, trades=k - s0 + 1))
        else:
            res.append(dict(start=day[s0], died=False, days=len(set(day[s0:])), trades=len(pnl) - s0))
    R = pd.DataFrame(res)
    # observation, not pre-registered: end-of-day trailing (Topstep-style). The floor moves only with the end-of-day
    # balance peak; an account dies when intraday equity (balance + a trade's worst point) touches the floor.
    eod = []
    for s0 in starts:
        bal, peak_eod, cur_day, dead_at = 50000.0, 50000.0, day[s0], None
        for k in range(s0, len(pnl)):
            if day[k] != cur_day:
                peak_eod, cur_day = max(peak_eod, bal), day[k]
            floor = min(peak_eod - 2000, 50000)
            if bal + worst[k] < floor:
                dead_at = k; break
            bal += pnl[k]
        eod.append(dict(died=dead_at is not None,
                        days=len(set(day[s0:(dead_at if dead_at is not None else len(pnl) - 1) + 1]))))
    E = pd.DataFrame(eod)
    R["eod_died"], R["eod_days"] = E.died, E.days
    R.to_csv(OUT / "prop.csv", index=False)
    print(f"prop simulation on {f}: {len(R)} accounts (one per trading day), sizing 10 correlated plain / 5 otherwise "
          f"({(n == 10).mean():.1%} of trades at 10)")
    for w in (1, 5, 20, 60, 250):
        print(f"  dead within {w:>3} trading days: {((R.died) & (R.days <= w)).mean():.1%}")
    print(f"  ever dead: {R.died.mean():.1%}; median trading days to death (among deaths) {R[R.died].days.median():.0f}; "
          f"median trades to death {R[R.died].trades.median():.0f}")
    print("  observation (not pre-registered), end-of-day trailing: " + ", ".join(
        f"dead within {w} days {((R.eod_died) & (R.eod_days <= w)).mean():.1%}" for w in (1, 5, 20, 60, 250))
          + f"; ever {R.eod_died.mean():.1%}; median days to death {R[R.eod_died].eod_days.median():.0f}")
    for y, g in R.groupby(pd.to_datetime(R.start).dt.year):
        print(f"  starts in {y}: dead within 20 days {((g.died) & (g.days <= 20)).mean():.1%}, ever {g.died.mean():.1%}")


def v1_charts(n=10, seed=11):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle
    W = build_all(3)
    Q = signals(W)
    T = pd.read_csv(OUT / "v1.csv")
    rng = np.random.default_rng(seed)
    pick = T.iloc[np.sort(rng.choice(len(T), n, replace=False))]
    out = OUT / "v1_charts"; out.mkdir(parents=True, exist_ok=True)
    ts = S["ts"]
    key = []
    for c, r in enumerate(pick.itertuples(), 1):
        t = int(r.entry_t)
        w0 = ts.searchsorted(ts[t] - pd.Timedelta(minutes=150))
        fig, axes = plt.subplots(2, 1, figsize=(16, 11))
        for ax, nm in zip(axes, ("NQ", "ES")):
            x = S["mk"][nm].iloc[w0:t + 1]
            b = x.resample("5min", label="left", closed="left").agg(
                {"open": "first", "high": "max", "low": "min", "close": "last"}).dropna()
            for k, (o, h, l, cc) in enumerate(zip(b.open, b.high, b.low, b.close)):
                col = "#26a69a" if cc >= o else "#ef5350"
                ax.plot([k, k], [l, h], color=col, lw=0.8)
                ax.add_patch(Rectangle((k - 0.35, min(o, cc)), 0.7, max(abs(cc - o), 0.05), color=col, lw=0))
            lo_, hi_ = b.low.min(), b.high.max()
            xof = lambda i1: np.searchsorted(b.index.asi8, ts[i1].value, side="right") - 1
            P = W[nm]["P"]
            live = P[(P.start <= t) & (P.end > w0) & (P.top >= lo_ - 15) & (P.bot <= hi_ + 15)]
            for z in live.itertuples():
                xa, xb = max(xof(max(z.start, w0)), 0), len(b) - 1
                col = "#2e7d32" if z.act > 0 else "#c62828"
                filled = z.untap_until > t
                ax.add_patch(Rectangle((xa - 0.5, z.bot), xb - xa + 1, z.top - z.bot, color=col, alpha=0.25 if filled else 0.06,
                                       lw=0.6, ec=col, ls="-" if z.kind == "FFVG" else "--"))
                ax.text(xa - 0.4, z.top, f"{z.tf}{'' if z.kind == 'FFVG' else 'i'}", fontsize=6, color=col, va="bottom", clip_on=True)
            q = Q[(Q.idx == nm) & (Q.t >= w0) & (Q.t <= t)].drop_duplicates(["t", "dir"])
            for p_ in q.itertuples():
                xx = xof(p_.t)
                y = p_.lo if p_.dir > 0 else p_.hi
                ax.plot(xx, y, "^" if p_.dir > 0 else "v", color="#1b5e20" if p_.dir > 0 else "#b71c1c", ms=9)
                ax.text(xx, y, f" {p_.tf}m{' S' if p_.swept else ''}", fontsize=7, va="top" if p_.dir > 0 else "bottom")
            if nm == "NQ":
                ax.plot(len(b) - 1 + 0.6, r.entry, ">" if r.dir > 0 else "<", color="black", ms=12)
                ax.text(len(b), r.entry, f" entry {'LONG' if r.dir > 0 else 'SHORT'} {r.entry:,.2f}", fontsize=8, va="center")
            ax.set_ylim(lo_ - 0.04 * (hi_ - lo_), hi_ + 0.04 * (hi_ - lo_))
            ax.set_xticks(range(0, len(b), 3), [i.strftime("%H:%M") for i in b.index[::3]], fontsize=7)
            ax.set_xlim(-1, len(b) + 8)
            ax.set_title(f"{nm} 5m · zones filled = untapped at entry · triangles = untapped-reaction pointers", fontsize=9, loc="left")
            ax.grid(alpha=0.15)
        fig.suptitle(f"mech_v1_{c:02d} · {ts[t]:%Y-%m-%d %a %H:%M} · V1 {'LONG' if r.dir > 0 else 'SHORT'} · grade {r.grade} "
                     f"({r.idx}) · cut at entry · outcome hidden", fontsize=10)
        fig.tight_layout()
        fig.savefig(out / f"mech_v1_{c:02d}.png", dpi=85)
        plt.close(fig)
        key.append(dict(id=f"mech_v1_{c:02d}", entry_time=ts[t], dir=r.dir, grade=r.grade, idx=r.idx))
    pd.DataFrame(key).to_csv(out / "charts_key.csv", index=False)
    pd.DataFrame(dict(id=[k["id"] for k in key], setup_is_right="", note="")).to_csv(out / "answers.csv", index=False)
    print(f"{len(key)} charts in {out}")


def run_v1(k_stages=4):
    W = build_all(3)
    Q = signals(W)
    res = {}
    for st in (None, CAT):
        res[st] = v1_trades(W, Q, stop=st)
    nbs = {}
    for sn in (2, 4):
        Wn = build_all(sn)
        Qn = signals(Wn)
        for st in (None, CAT):
            nbs.setdefault(st, []).append(summ(v1_trades(Wn, Qn, stop=st)))
    rows = []
    for st, name in ((None, "V1 (no stop)"), (CAT, "V1 + 60-point catastrophic stop")):
        T = res[st]
        T.to_csv(OUT / ("v1.csv" if st is None else "v1_stop60.csv"), index=False)
        rows.append(report_v1(name, T, nbs[st], k_stages))
    pd.DataFrame(rows).to_csv(OUT / "v1_summary.csv", index=False)
    return res


if __name__ == "__main__":
    opt = lambda k, d: type(d)(sys.argv[sys.argv.index(k) + 1]) if k in sys.argv else d
    cmd = sys.argv[1] if len(sys.argv) > 1 else "v0"
    if cmd == "v0":
        run_v0(opt("--swing", 3))
    elif cmd == "v1":
        run_v1()
    elif cmd == "v23":
        run_v23()
    elif cmd == "prop":
        run_prop()
    elif cmd == "charts":
        v1_charts()
