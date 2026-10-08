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


def target(W, nm, t, d, e, DI):
    """Nearest untapped zone ahead acting against d on index nm at 1m t from price e, and whether the path is clear."""
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
    return tg, between.empty


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


if __name__ == "__main__":
    opt = lambda k, d: type(d)(sys.argv[sys.argv.index(k) + 1]) if k in sys.argv else d
    cmd = sys.argv[1] if len(sys.argv) > 1 else "v0"
    if cmd == "v0":
        run_v0(opt("--swing", 3))
