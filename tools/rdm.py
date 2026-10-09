#!/usr/bin/env python3
"""RDM: the Ryze Divergence Model, as pre-registered in BACKTEST_LOG.md ("RDM").

    python3 tools/rdm.py summary        stage 1: data inspection -> data/studies/rdm/results/data_summary.md

Data: Databento MNQ ("NQ") and ES 1m bars, New York time, aligned on MNQ's minutes; 5m / 15m bars built from 1m.
Zones: data/studies/rdm/zones.csv (verified reconstruction of the Ryze indicator).
"""
import sys, pathlib, collections
import numpy as np
import pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from ifvg_engine import trading_date

TZ = "America/New_York"
ROOT = pathlib.Path("data/studies/rdm")
RES = ROOT / "results"
ZONE_DAYS = 12
P = dict(pivot_len=3, rsmt_window=5, entry_window=15, zone_days=ZONE_DAYS)
AGG = {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}


def load():
    nq = pd.read_parquet("data/bars/MNQ_1m.parquet")
    es = pd.read_parquet("data/bars/ES_1m.parquet")
    return nq, es


def bars(x, k):
    return x.resample(f"{k}min", label="left", closed="left").agg(AGG).dropna(subset=["open"])


def roll_days(nq, es):
    """Trading days on which either market's instrument changes."""
    out = {}
    for nm, x in (("NQ", nq), ("ES", es)):
        td = trading_date(x.index)
        g = pd.Series(x.instrument_id.to_numpy(), index=td).groupby(level=0).agg(["first", "last"])
        ch = (g["first"] != g["last"]) | (g["first"] != g["last"].shift(1))
        ch.iloc[0] = False
        out[nm] = set(g.index[ch])
    return out


def zones(symbol, fractions=(0.0,)):
    z = pd.read_csv(ROOT / "zones.csv")
    z = z[(z.symbol == symbol) & z.fraction.isin(fractions)].copy()
    z["event"] = pd.to_datetime(z.event_time_et).dt.tz_localize(TZ, ambiguous="NaT", nonexistent="shift_forward")
    z["live_from"] = z.event.dt.floor("min") + pd.Timedelta(minutes=1)          # known at the event candle's close
    z["zid"] = z.city + "|" + z.fraction.astype(str) + "|" + z.created_date
    return z.dropna(subset=["event"])


def active_until(z, tdays):
    """Each zone is active for ZONE_DAYS trading days from its event: until the start of the trading day ZONE_DAYS later."""
    tdays = pd.DatetimeIndex(sorted(tdays))
    k = tdays.searchsorted(trading_date(pd.DatetimeIndex(z.event)).to_numpy())
    end_day = tdays[np.minimum(k + ZONE_DAYS, len(tdays) - 1)]
    return (end_day - pd.Timedelta(hours=6)).tz_localize(TZ)                       # 18:00 the evening before


def summary():
    RES.mkdir(parents=True, exist_ok=True)
    nq, es = load()
    L = []
    w = L.append
    w("# RDM — stage 1 data summary\n")
    for nm, x in (("NQ (MNQ)", nq), ("ES", es)):
        td = trading_date(x.index)
        w(f"- **{nm}**: {len(x):,} 1m bars, {x.index[0]} → {x.index[-1]}, {pd.Index(td).nunique():,} trading days, "
          f"{x.instrument_id.nunique()} contracts")
    common = nq.index.intersection(es.index)
    w(f"- **Alignment**: {len(common):,} minutes in both; NQ minutes without ES {len(nq.index.difference(es.index)):,}; "
      f"ES minutes without NQ {len(es.index.difference(nq.index)):,}")
    tod = nq.index.hour * 60 + nq.index.minute
    cash = nq[(tod >= 570) & (tod < 960)]
    per = cash.groupby(cash.index.date).size()
    w(f"- **Cash-session coverage (09:30–15:59, NQ)**: {len(per):,} days; median {per.median():.0f} bars/day; "
      f"days with < 390 bars {int((per < 390).sum())} (early closes and gaps)")
    for k in (5, 15):
        w(f"- **{k}m bars**: NQ {len(bars(nq, k)):,}, ES {len(bars(es, k)):,}")
    R = roll_days(nq, es)
    both = R["NQ"] & R["ES"]
    w(f"- **Roll days** (instrument change in the trading day, flagged and excluded): NQ {len(R['NQ'])}, ES {len(R['ES'])}, "
      f"union {len(R['NQ'] | R['ES'])} (same day for both on {len(both)}; NQ and ES on different days on "
      f"{len(R['NQ'] ^ R['ES'])})")
    # price jump at the roll: NQ/ES log-ratio change across the roll minute
    lr = np.log(nq.close.reindex(common)) - np.log(es.close.reindex(common))
    tdc = trading_date(common)
    day_med = lr.groupby(tdc).median()
    jumps = day_med.diff().abs()
    rd = sorted(R["NQ"] | R["ES"])
    w(f"- **NQ/ES ratio jump** (day-median log ratio, change from the previous day): on roll days median "
      f"{jumps.reindex(rd).median() * 1e4:.1f} bp, max {jumps.reindex(rd).max() * 1e4:.1f} bp; on other days median "
      f"{jumps.drop(rd, errors='ignore').median() * 1e4:.1f} bp")
    ev = pd.read_csv("data/events.csv")
    news = ev[ev.time_ny.isin(["08:30", "10:00"]) & ~ev.type.isin(["opex", "early_close"])]
    w(f"- **News days (08:30 / 10:00 ET releases, variant 5)**: {news.date.nunique():,} days "
      f"({', '.join(f'{k} {v}' for k, v in news.type.value_counts().items())})")
    w(f"- **Early-close days**: {ev[ev.type == 'early_close'].date.nunique()}")
    # zones
    tdays = pd.Index(trading_date(nq.index)).unique()
    for frac, lab in (((0.0,), "sunrise only (primary)"), ((0.0, 0.25, 0.5, 0.75, 1.0), "all fractions (variant 7)")):
        for sym, x in (("MNQ", nq), ("ES", es)):
            z = zones(sym, frac)
            z["until"] = active_until(z, tdays)
            # active zones at each day's 09:30 and the share of 09:30-15:00 1m bars touching an active zone
            samp = x[(tod_ := (x.index.hour * 60 + x.index.minute)) >= 570]
            samp = samp[(samp.index.hour * 60 + samp.index.minute) < 900]
            days = pd.Index(samp.index.normalize().unique())
            take = days[np.linspace(0, len(days) - 1, min(150, len(days))).astype(int)]     # 150 days spread over the span
            n_act, n_near, touch = [], [], []
            for d in take:
                t0 = d + pd.Timedelta(hours=9, minutes=30)
                a_ = z[(z.live_from <= t0) & (z.until > t0)]
                px = x.close.asof(t0)
                n_act.append(len(a_)); n_near.append(int(((a_.zone_low <= px * 1.01) & (a_.zone_high >= px * 0.99)).sum()))
                day = samp.loc[d: d + pd.Timedelta(hours=23)]
                lo_, hi_ = day.low.to_numpy()[:, None], day.high.to_numpy()[:, None]
                act = z[(z.live_from <= day.index[-1]) & (z.until > day.index[0])]
                hit = (lo_ <= act.zone_high.to_numpy()[None, :]) & (hi_ >= act.zone_low.to_numpy()[None, :])
                touch.append(hit.any(axis=1).mean() if hit.size else 0.0)
            w(f"- **Zones, {lab}, {sym}**: {len(z):,} zones; at 09:30 on average {np.mean(n_act):.1f} active "
              f"(12 trading days), {np.mean(n_near):.1f} within ±1 % of price; {100 * np.mean(touch):.1f} % of 09:30–15:00 "
              f"1m bars touch at least one active zone (150 sampled days)")
    w("\n**Parameters (defaults, pre-registered):** " + ", ".join(f"{k} {v}" for k, v in P.items()))
    txt = "\n".join(L)
    (RES / "data_summary.md").write_text(txt + "\n")
    print(txt)


# =============================================================== detection primitives (unit-tested in tests/test_rdm.py)
TICK, PV, COMM = 0.25, 2.0, 1.0


def pivots(h, l, n):
    """Swing flags: ph[i] if h[i] > the n highs before and >= the n highs after (mirror for pl). A pivot at i is known
    only at the close of bar i + n."""
    m = len(h)
    ph, pl = np.zeros(m, bool), np.zeros(m, bool)
    for i in range(n, m - n):
        if h[i] > h[i - n:i].max() and h[i] >= h[i + 1:i + n + 1].max():
            ph[i] = True
        if l[i] < l[i - n:i].min() and l[i] <= l[i + 1:i + n + 1].min():
            pl[i] = True
    return ph, pl


def smt_events(hx, lx, hy, ly, n):
    """Live-sweep SMT with X as the sweeping market, on one trading day's bars. Bearish (dir -1) at bar t: the first bar
    since X's latest confirmed swing high p (confirmed at p + n <= t - 1) whose high exceeds it, while Y's highs over
    p+1..t stay at or below Y's corresponding high (its highest high over p-1..p+1). Bullish (dir +1) is the mirror.
    Returns a list of (t, dir, p)."""
    ph, pl = pivots(hx, lx, n)
    m = len(hx)
    out = []
    for d, piv, X, Y in ((-1, ph, hx, hy), (1, pl, lx, ly)):
        latest, swept = None, True
        for t in range(m):
            c = t - 1 - n                              # a pivot at c becomes known at the close of bar t - 1
            if c >= 0 and piv[c]:
                latest, swept = c, False
            if latest is None or swept:
                continue
            beyond = X[t] > X[latest] if d < 0 else X[t] < X[latest]
            if not beyond:
                continue
            swept = True
            p = latest
            ref = Y[max(p - 1, 0):p + 2]
            win = Y[p + 1:t + 1]
            fails = win.max() <= ref.max() if d < 0 else win.min() >= ref.min()
            if fails:
                out.append((t, d, p))
    return out


def fvgs(h, l):
    """Fair value gaps by their third candle i: bullish (+1) if l[i] > h[i-2], zone (h[i-2], l[i]); bearish (-1) if
    h[i] < l[i-2], zone (h[i], l[i-2]). Returns a list of (i, dir, bottom, top)."""
    out = []
    for i in range(2, len(h)):
        if l[i] > h[i - 2]:
            out.append((i, 1, h[i - 2], l[i]))
        if h[i] < l[i - 2]:
            out.append((i, -1, h[i], l[i - 2]))
    return out


def zone_touch(bar_lo, bar_hi, bar_t, z_lo, z_hi, z_from, z_until, z_id):
    """Zone IDs touched by bars (range overlapping a zone that is active at the bar's time)."""
    if len(bar_lo) == 0 or len(z_lo) == 0:
        return set()
    act = (z_from[None, :] <= bar_t[:, None]) & (z_until[None, :] > bar_t[:, None])
    ov = (bar_lo[:, None] <= z_hi[None, :]) & (bar_hi[:, None] >= z_lo[None, :])
    hit = (act & ov).any(axis=0)
    return set(np.asarray(z_id)[hit])


# =============================================================== engine
D = {}


def prep():
    """Aligned 1m NQ / ES (ES on NQ's minutes; a missing ES minute is a flat bar at its last close), 5m / 15m bar maps,
    trading days, roll / news / early-close days, zones with their activity windows."""
    if D:
        return D
    nq, es = load()
    es = es.reindex(nq.index)
    c = es.close.ffill()
    miss = es.close.isna()
    for k in ("open", "high", "low"):
        es[k] = es[k].where(~miss, c)
    es["close"] = c
    es = es.bfill()
    ts = nq.index
    td = trading_date(ts)
    tdi = pd.factorize(td)[0]
    tdays = pd.DatetimeIndex(pd.unique(td))
    R = roll_days(nq, es.assign(instrument_id=es.instrument_id.ffill()))
    roll = R["NQ"] | R["ES"]
    ev = pd.read_csv("data/events.csv")
    news = set(ev[ev.time_ny.isin(["08:30", "10:00"]) & ~ev.type.isin(["opex", "early_close"])].date)
    early = {r.date: r.time_ny for r in ev[ev.type == "early_close"].itertuples()}
    tod = (ts.hour * 60 + ts.minute).to_numpy()
    D.update(ts=ts, td=td, tdi=tdi, tdays=tdays, tod=tod, roll=roll, news=news, early=early,
             N={k: nq[k].to_numpy() for k in ("open", "high", "low", "close")},
             E={k: es[k].to_numpy() for k in ("open", "high", "low", "close")},
             day_first=np.r_[0, np.flatnonzero(np.diff(tdi)) + 1])
    D["day_last"] = np.r_[D["day_first"][1:] - 1, len(ts) - 1]
    for k in (5, 15):
        key = ts.floor(f"{k}min")
        new = np.r_[True, key[1:] != key[:-1]]
        first = np.flatnonzero(new)
        D[f"of{k}"] = np.cumsum(new) - 1
        D[f"first{k}"], D[f"last{k}"] = first, np.r_[first[1:] - 1, len(ts) - 1]
    for frac_key, fr in (("sun", (0.0,)), ("all", (0.0, 0.25, 0.5, 0.75, 1.0))):
        for sym in ("MNQ", "ES"):
            z = zones(sym, fr)
            z["until"] = active_until(z, tdays)
            D[f"z_{sym}_{frac_key}"] = dict(lo=z.zone_low.to_numpy(), hi=z.zone_high.to_numpy(),
                                             frm=ts.searchsorted(z.live_from.to_numpy()), unt=ts.searchsorted(z.until.to_numpy()),
                                             zid=z.zid.to_numpy())
    return D


def agg_bars(x, i0, i1, k):
    """k-minute bars (clock-aligned) of 1m arrays x over [i0, i1]: H, L and the 1m index of each bar's first / last bar."""
    of, fi, la = D[f"of{k}"], D[f"first{k}"], D[f"last{k}"]
    b0, b1 = of[i0], of[i1]
    idx = np.arange(b0, b1 + 1)
    f_, l_ = np.maximum(fi[idx], i0), np.minimum(la[idx], i1)
    H = np.array([x["high"][a:b + 1].max() for a, b in zip(f_, l_)])
    L = np.array([x["low"][a:b + 1].min() for a, b in zip(f_, l_)])
    return H, L, f_, l_


def session_levels(i0, d):
    """Completed NQ session highs / lows usable on trading day d: previous day's Asia, London, NY; today's Asia, London.
    Returns list of (name, kind 'high'/'low', price, end 1m index)."""
    ts, N = D["ts"], D["N"]
    out = []
    day = D["tdays"][d]
    for dd, names in ((d - 1, ("Asia", "London", "NY")), (d, ("Asia", "London"))):
        if dd < 0:
            continue
        base = D["tdays"][dd].tz_localize(TZ)
        spans = {"Asia": (base - pd.Timedelta(hours=6), base + pd.Timedelta(hours=2)),
                 "London": (base + pd.Timedelta(hours=2), base + pd.Timedelta(hours=9, minutes=30)),
                 "NY": (base + pd.Timedelta(hours=9, minutes=30), base + pd.Timedelta(hours=16))}
        for nm in names:
            a_, b_ = ts.searchsorted(spans[nm][0]), ts.searchsorted(spans[nm][1]) - 1
            if b_ < a_:
                continue
            out.append((f"{nm} {'prev' if dd < d else 'today'}", "high", N["high"][a_:b_ + 1].max(), b_))
            out.append((f"{nm} {'prev' if dd < d else 'today'}", "low", N["low"][a_:b_ + 1].min(), b_))
    return out


def untaken(level, kind, end, t):
    """True if NQ has not traded through the level between its session's end and bar t."""
    if t <= end:
        return True
    seg = D["N"]["high"][end + 1:t + 1] if kind == "high" else D["N"]["low"][end + 1:t + 1]
    return not ((seg > level).any() if kind == "high" else (seg < level).any())


def setups_day(d, p, F=None):
    """All setups of trading day d (triggers 09:30-15:00) with every field the trade rules and variants need.
    F (a Counter) collects the detection funnel: how many 1m SMT events survive each condition."""
    F = F if F is not None else collections.Counter()
    i0, i1 = D["day_first"][d], D["day_last"][d]
    ts, tod, N, E = D["ts"], D["tod"], D["N"], D["E"]
    n = p["pivot_len"]
    sl = slice(i0, i1 + 1)
    nh, nl, eh, el = N["high"][sl], N["low"][sl], E["high"][sl], E["low"][sl]
    ev1 = [(i0 + t, dd, i0 + pp, "NQ") for t, dd, pp in smt_events(nh, nl, eh, el, n)] + \
          [(i0 + t, dd, i0 + pp, "ES") for t, dd, pp in smt_events(eh, el, nh, nl, n)]
    htf = {}
    for k in (5, 15):
        NH, NL, f_, l_ = agg_bars(N, i0, i1, k)
        EH, EL, _, _ = agg_bars(E, i0, i1, k)
        evk = {}
        for X, (xh, xl, yh, yl) in (("NQ", (NH, NL, EH, EL)), ("ES", (EH, EL, NH, NL))):
            for t, dd, pp in smt_events(xh, xl, yh, yl, n):
                evk[(f_[t], dd, X)] = l_[t]               # keyed by the k-bar's first 1m index -> its last 1m index
        htf[k] = evk
    ph1, pl1 = pivots(nh, nl, n)
    gaps = fvgs(nh, nl)
    zk = "all" if p.get("all_fractions") else "sun"
    ZN, ZE = D[f"z_MNQ_{zk}"], D[f"z_ES_{zk}"]
    zsel = {nm: np.flatnonzero((Z["frm"] <= i1) & (Z["unt"] > i0)) for nm, Z in (("N", ZN), ("E", ZE))}
    levels = session_levels(i0, d)
    out = []
    tod_ = D["tod"]
    for t1, dd, pp, X in ev1:
        if not (9 * 60 + 14 <= tod_[t1] <= 14 * 60 + 59):
            continue                                       # a sweep that cannot reach the 09:30-15:00 trigger window
        F["1 1m SMT (sweep 09:14-14:59)"] += 1
        f5 = D["first5"][D["of5"][t1]]
        if (f5, dd, X) not in htf[5]:
            continue                                       # not validated on 5m
        F["2 validated on 5m"] += 1
        known5 = htf[5][(f5, dd, X)]
        f15 = D["first15"][D["of15"][t1]]
        has15 = (f15, dd, X) in htf[15]
        known15 = htf[15].get((f15, dd, X))
        side = dd                                          # bearish SMT (dd -1) -> short (side -1)
        # inverse FVG: most recent NQ gap against the trade in the move into the sweep
        piv = pl1 if side < 0 else ph1                     # the last confirmed NQ 1m swing low before a short's sweep
        conf = [i0 + c for c in np.flatnonzero(piv) if i0 + c + n <= t1]
        start = conf[-1] if conf else i0
        g = [x for x in gaps if x[1] == -side and start < i0 + x[0] <= t1]
        if not g:
            continue
        F["3 inverse-FVG candidate in the move"] += 1
        gi, _, gbot, gtop = g[-1]
        far = gbot if side < 0 else gtop
        # trigger
        tmax = min(i1, t1 + p["entry_window"])
        trig, cancel, sets, closed, rsmt_any = None, False, None, False, False
        for te in range(t1, tmax + 1):
            if not (9 * 60 + 29 <= tod[te] <= 14 * 60 + 59):
                continue
            if (N["close"][te] < far) if side < 0 else (N["close"][te] > far):
                if te < known5 or (p.get("req15") and (known15 is None or te < known15)):
                    continue
                closed = True
                w0, w1 = max(t1 - p["rsmt_window"], i0), min(t1 + p["rsmt_window"], te)
                bt = np.arange(w0, w1 + 1)
                sN = zone_touch(N["low"][w0:w1 + 1], N["high"][w0:w1 + 1], bt, ZN["lo"][zsel["N"]], ZN["hi"][zsel["N"]],
                                ZN["frm"][zsel["N"]], ZN["unt"][zsel["N"]], ZN["zid"][zsel["N"]])
                sE = zone_touch(E["low"][w0:w1 + 1], E["high"][w0:w1 + 1], bt, ZE["lo"][zsel["E"]], ZE["hi"][zsel["E"]],
                                ZE["frm"][zsel["E"]], ZE["unt"][zsel["E"]], ZE["zid"][zsel["E"]])
                if sN == sE or not (sN or sE):
                    continue
                rsmt_any = True
                # cancel: a close beyond the far edge of a zone in the difference, on its own symbol, before entry
                for sym, only, Z, X_ in (("N", sN - sE, ZN, N), ("E", sE - sN, ZE, E)):
                    for zid in only:
                        j = zsel[sym][np.flatnonzero(Z["zid"][zsel[sym]] == zid)[0]]
                        edge = Z["hi"][j] if side < 0 else Z["lo"][j]
                        lo_, hi_ = X_["low"][w0:w1 + 1], X_["high"][w0:w1 + 1]
                        touch0 = w0 + int(np.argmax((lo_ <= Z["hi"][j]) & (hi_ >= Z["lo"][j])))
                        cl = X_["close"][touch0:te + 1]
                        if ((cl > edge) if side < 0 else (cl < edge)).any():
                            cancel = True
                if cancel:
                    break
                trig, sets = te, (sN, sE)
                break
        F["4 close through the gap in the window (SMT known)"] += int(closed)
        F["5 RSMT"] += int(rsmt_any)
        if trig is None or cancel or trig + 1 > i1:
            continue
        F["6 not cancelled = setup"] += 1
        ext = (N["high"][t1:trig + 1].max() if side < 0 else N["low"][t1:trig + 1].min())
        took = [lv for lv in levels if lv[1] == ("high" if side < 0 else "low") and
                ((N["high"][t1] > lv[2]) if side < 0 else (N["low"][t1] < lv[2])) and untaken(lv[2], lv[1], lv[3], t1 - 1)]
        out.append(dict(t1=t1, trig=trig, side=side, grade="A" if X == "NQ" else "B", p=pp, X=X, has15=has15,
                        gap=(i0 + gi, gbot, gtop), ext=ext, zN=sorted(sets[0]), zE=sorted(sets[1]),
                        took_level=bool(took), day=d))
    return out


def trade(su, p, levels, piv5):
    """Entry, stop, targets for setup su; returns a dict, or a skip reason string."""
    N, ts, tod = D["N"], D["ts"], D["tod"]
    side, trig = su["side"], su["trig"]
    e_i = trig + 1
    entry = N["open"][e_i] + side * TICK
    if p.get("swing_stop"):
        ph1, pl1 = piv5["p1"]
        i0 = D["day_first"][su["day"]]
        n = p["pivot_len"]
        cand = [i0 + c for c in np.flatnonzero(ph1 if side < 0 else pl1) if i0 + c + n <= trig]
        cand = [c for c in cand if (N["high"][c] > entry if side < 0 else N["low"][c] < entry)]
        if not cand:
            return "no 1m swing beyond the entry"
        c = cand[-1]
        stop = (N["high"][c] + TICK) if side < 0 else (N["low"][c] - TICK)
    else:
        stop = su["ext"] + TICK if side < 0 else su["ext"] - TICK
    risk = side * (entry - stop)                       # long: entry - stop; short: stop - entry
    if risk <= 0:
        return "stop on the wrong side of the entry"
    # TP1: nearest untaken confirmed NQ 5m swing beyond the entry (current and previous trading day)
    sw_t, sw_px, sw_kind = piv5["t"], piv5["px"], piv5["kind"]
    want = "low" if side < 0 else "high"
    ok = (sw_kind == want) & (piv5["conf"] <= trig) & ((sw_px < entry) if side < 0 else (sw_px > entry))
    tp1 = None
    for j in np.flatnonzero(ok)[np.argsort(np.abs(sw_px[ok] - entry))] if ok.any() else []:
        if untaken(sw_px[j], want, sw_t[j], trig):
            tp1 = sw_px[j]; break
    if tp1 is None:
        return "no TP1"
    lv = [x for x in levels if x[1] == want and ((x[2] < tp1) if side < 0 else (x[2] > tp1)) and untaken(x[2], x[1], x[3], trig)]
    if not lv:
        return "no untaken session level beyond TP1"
    fin = max(lv, key=lambda x: x[2])[2] if side < 0 else min(lv, key=lambda x: x[2])[2]
    if abs(fin - entry) < 2 * risk:
        return "final target < 2R"
    return dict(e_i=e_i, entry=entry, stop=stop, risk=risk, tp1=tp1, final=fin)


def flat_bar(d):
    """1m index whose open is the flatten time: 15:55, or 10 minutes before an early halt."""
    i0, i1 = D["day_first"][d], D["day_last"][d]
    day = D["tdays"][d].strftime("%Y-%m-%d")
    tod = D["tod"]
    tgt = 15 * 60 + 55
    if day in D["early"]:
        h, m = map(int, D["early"][day].split(":"))
        tgt = h * 60 + m - 10
    k = i0 + np.searchsorted(np.where((tod[i0:i1 + 1] >= 9 * 60) & (tod[i0:i1 + 1] < 18 * 60), tod[i0:i1 + 1], -1), tgt)
    return min(k, i1)


def manage(tr, side, flat_i, opp_triggers):
    """Thirds: 1/3 at TP1 (stop to the entry after), 2/3 at the final target; stop first; a bar opening beyond a level
    fills at its open; exit the remainder at the next bar's open after an opposite trigger, or at the flatten bar's open."""
    N = D["N"]
    O, H, L = N["open"], N["high"], N["low"]
    e, stop, risk = tr["entry"], tr["stop"], tr["risk"]
    rem, tp1_done, legs = 3, False, []
    opp = [o for o in opp_triggers if o >= tr["e_i"]]
    q = tr["e_i"]
    why = None
    while q < flat_i and rem > 0:
        if opp and q == opp[0] + 1:
            legs.append((rem, O[q] - side * TICK, "opposite setup")); rem = 0; break
        first = q == tr["e_i"]
        o = O[q]
        if not first and side * (o - stop) <= 0:
            legs.append((rem, o - side * TICK, "BE" if tp1_done else "stop")); rem = 0; break
        if (L[q] <= stop) if side > 0 else (H[q] >= stop):
            legs.append((rem, stop - side * TICK, "BE" if tp1_done else "stop")); rem = 0; break
        for lvl_name in ("tp1", "final"):
            if rem == 0 or (lvl_name == "tp1" and tp1_done) or (lvl_name == "final" and not tp1_done):
                continue
            lv = tr[lvl_name]
            gap = (not first) and side * (o - lv) >= 0
            if gap or ((H[q] >= lv) if side > 0 else (L[q] <= lv)):
                px = (o if gap else lv) - side * TICK
                if lvl_name == "tp1":
                    legs.append((1, px, "TP1")); rem -= 1; tp1_done = True; stop = e
                else:
                    legs.append((rem, px, "final target")); rem = 0
        q += 1
    if rem > 0:
        legs.append((rem, O[flat_i] - side * TICK, "flat 15:55"))
    pts = sum(k / 3 * side * (px - e) for k, px, _ in legs)
    usd = pts * PV - 2 * COMM
    return dict(pts=pts, usd=usd, R=usd / (risk * PV), exit=legs[-1][2], legs=legs,
                exit_i=q if rem == 0 else flat_i)


def pivots5(d, n):
    """Confirmed NQ 5m swings of trading days d-1 and d (time of the pivot bar's last 1m index, confirmation index)."""
    i0 = D["day_first"][max(d - 1, 0)]
    i1 = D["day_last"][d]
    H, L, f_, l_ = agg_bars(D["N"], i0, i1, 5)
    ph, pl = pivots(H, L, n)
    t, px, kind, conf = [], [], [], []
    for j in np.flatnonzero(ph):
        t.append(l_[j]); px.append(H[j]); kind.append("high"); conf.append(l_[j + n])
    for j in np.flatnonzero(pl):
        t.append(l_[j]); px.append(L[j]); kind.append("low"); conf.append(l_[j + n])
    i0d = D["day_first"][d]
    p1 = pivots(D["N"]["high"][i0d:i1 + 1], D["N"]["low"][i0d:i1 + 1], n)
    return dict(t=np.array(t), px=np.array(px), kind=np.array(kind), conf=np.array(conf), p1=p1)


def run(p, label="baseline"):
    """One run. p: parameters + variant switches (grade_b, req15, took_level, swing_stop, skip_news, first_only,
    all_fractions)."""
    prep()
    trades, funnel = [], collections.Counter()
    for d in range(1, len(D["tdays"])):
        day = D["tdays"][d]
        ds = day.strftime("%Y-%m-%d")
        if day in D["roll"] or ds in D["early"] or (p.get("skip_news") and ds in D["news"]):
            continue                                       # roll days; early-close / holiday sessions (amendment)
        tod = D["tod"]
        i0, i1 = D["day_first"][d], D["day_last"][d]
        if not ((tod[i0:i1 + 1] >= 570) & (tod[i0:i1 + 1] < 900)).any():
            continue
        S = setups_day(d, p, funnel)
        S = [s_ for s_ in S if p.get("grade_b") or s_["grade"] == "A"]
        funnel["7 grade allowed (A; B in variant 1)"] += len(S)
        if p.get("req15"):
            S = [s_ for s_ in S if s_["has15"]]
        if p.get("took_level"):
            S = [s_ for s_ in S if s_["took_level"]]
        funnel["8 after the variant's setup filter"] += len(S)
        if not S:
            continue
        levels = session_levels(i0, d)
        piv5 = pivots5(d, p["pivot_len"])
        flat_i = flat_bar(d)
        busy_until, n_today = -1, 0
        for su in sorted(S, key=lambda x: x["trig"]):
            if su["trig"] < busy_until or su["trig"] + 1 >= flat_i:
                funnel["skip: a trade already open"] += 1
                continue
            if p.get("first_only") and n_today >= 1:
                funnel["skip: not the day's first trade (variant 6)"] += 1
                continue
            tr = trade(su, p, levels, piv5)
            if isinstance(tr, str):
                funnel["skip: " + tr] += 1
                continue
            opp = [x["trig"] for x in S if x["side"] == -su["side"] and x["trig"] > su["trig"]]
            m = manage(tr, su["side"], flat_i, opp)
            funnel["9 trades"] += 1
            n_today += 1
            busy_until = m["exit_i"]
            trades.append(dict(day=ds, sweep_time=D["ts"][su["t1"]], trigger_time=D["ts"][su["trig"]],
                               entry_time=D["ts"][tr["e_i"]], direction="long" if su["side"] > 0 else "short",
                               grade=su["grade"], smt15=su["has15"], took_level=su["took_level"],
                               zones_NQ=";".join(su["zN"]), zones_ES=";".join(su["zE"]), entry=tr["entry"],
                               stop=tr["stop"], risk_pts=tr["risk"], tp1=tr["tp1"], final=tr["final"],
                               exit_reason=m["exit"], legs=" | ".join(f"{k}/3 {px:.2f} {w}" for k, px, w in m["legs"]),
                               pts=m["pts"], usd=m["usd"], R=m["R"], t1=su["t1"], trig=su["trig"], p_ref=su["p"],
                               sweeper=su["X"], gap_i=su["gap"][0], gap_bot=su["gap"][1], gap_top=su["gap"][2]))
    T = pd.DataFrame(trades)
    return T, funnel


def charts(T, n=10, seed=11):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle
    out = ROOT / "charts"; out.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(seed)
    pick = T.iloc[np.sort(rng.choice(len(T), size=min(n, len(T)), replace=False))]
    ts = D["ts"]
    zfull = {sym: zones(sym) for sym in ("MNQ", "ES")}
    key = []
    for c, r in enumerate(pick.itertuples(), 1):
        e_i = int(r.trig) + 1
        a_ = max(min(int(r.p_ref) - 10, int(r.gap_i) - 5), int(r.t1) - 90)
        idx = np.arange(a_, e_i)                           # cut at entry: bars up to the trigger bar
        fig, axes = plt.subplots(2, 1, figsize=(17, 11), sharex=True)
        side = 1 if r.direction == "long" else -1
        for ax, nm, X, sym, zset in ((axes[0], "NQ (MNQ)", D["N"], "MNQ", r.zones_NQ), (axes[1], "ES", D["E"], "ES", r.zones_ES)):
            for k, i in enumerate(idx):
                o, h, l, cc = X["open"][i], X["high"][i], X["low"][i], X["close"][i]
                col = "#26a69a" if cc >= o else "#ef5350"
                ax.plot([k, k], [l, h], color=col, lw=0.8)
                ax.add_patch(Rectangle((k - 0.35, min(o, cc)), 0.7, max(abs(cc - o), 0.05), color=col, lw=0))
            lo_, hi_ = X["low"][idx].min(), X["high"][idx].max()
            # zones active at the sweep and near the window's prices; touched ones (this market) solid
            z = zfull[sym]
            t_sw = ts[int(r.t1)]
            z = z[(z.live_from <= t_sw) & (z.zone_high >= lo_ - 0.002 * lo_) & (z.zone_low <= hi_ + 0.002 * hi_)]
            touched = set(zset.split(";")) if isinstance(zset, str) and zset else set()
            for zz in z.itertuples():
                tch = zz.zid in touched
                ax.add_patch(Rectangle((-0.5, zz.zone_low), len(idx), max(zz.zone_high - zz.zone_low, 0.25),
                                       color="#7e57c2", alpha=0.35 if tch else 0.10, lw=1 if tch else 0))
                ax.text(len(idx) - 0.5, zz.zone_high, f" {zz.city} sunrise {zz.created_date}{' (touched)' if tch else ''}",
                        fontsize=7, color="#5e35b1")
            # SMT: the reference swing and the sweep
            pr, t1 = int(r.p_ref) - a_, int(r.t1) - a_
            sweeper = (r.sweeper == "NQ") == (nm != "ES")
            ref_px = (X["high"] if side < 0 else X["low"])[max(int(r.p_ref) - (0 if sweeper else 1), 0):int(r.p_ref) + (1 if sweeper else 2)]
            ref = ref_px.max() if side < 0 else ref_px.min()
            ax.plot([pr, t1], [ref, ref], color="#1565c0", lw=1.4, ls="--")
            ax.text(pr, ref, f" {'swing' if sweeper else 'corresponding'} {'high' if side < 0 else 'low'} {ref:,.2f}",
                    fontsize=8, color="#1565c0", va="bottom" if side < 0 else "top")
            ax.axvline(t1, color="#1565c0", lw=0.7, ls=":")
            ax.text(t1, hi_ if side < 0 else lo_, f" sweep bar {ts[int(r.t1)]:%H:%M} ({'sweeps' if sweeper else 'fails'})",
                    fontsize=8, color="#1565c0", va="top" if side < 0 else "bottom")
            if nm != "ES":
                gi = int(r.gap_i) - a_
                ax.add_patch(Rectangle((gi - 2.5, r.gap_bot), len(idx) - gi + 2, r.gap_top - r.gap_bot, color="#ffb300", alpha=0.35))
                ax.text(gi - 2, r.gap_top if side < 0 else r.gap_bot, " 1m FVG (to invert)", fontsize=8, color="#e65100")
                ax.plot(len(idx) - 1, X["close"][int(r.trig)], "o", color="black", ms=6)
                for lvl, lab, col in ((r.entry, "entry (next open)", "black"), (r.stop, "stop", "#c62828"),
                                      (r.tp1, "TP1 (5m swing)", "#2e7d32"), (r.final, "final (session level)", "#1b5e20")):
                    ax.axhline(lvl, color=col, lw=1, ls="-" if lab == "stop" else "--")
                    ax.text(len(idx) + 0.5, lvl, f" {lab} {lvl:,.2f}", fontsize=8, color=col, va="center")
                lo_, hi_ = min(lo_, r.stop, r.tp1), max(hi_, r.stop, r.tp1)
            ax.set_ylim(lo_ - 0.03 * (hi_ - lo_), hi_ + 0.03 * (hi_ - lo_))
            ax.set_title(f"{nm} 1m · zones (purple; solid = touched in the RSMT window by this market)", fontsize=9, loc="left")
            ax.grid(alpha=0.15)
        ticks = [k for k, i in enumerate(idx) if ts[i].minute % 5 == 0]
        axes[1].set_xticks(ticks, [ts[idx[k]].strftime("%H:%M") for k in ticks], fontsize=7, rotation=90)
        axes[1].set_xlim(-1, len(idx) + 14)
        fig.suptitle(f"rdm_{c:02d} · {r.day} · {r.direction.upper()} · grade {r.grade} (sweeper {r.sweeper}) · "
                     f"15m SMT {'yes' if r.smt15 else 'no'} · zones NQ [{r.zones_NQ}] vs ES [{r.zones_ES}] · cut at entry, outcome hidden",
                     fontsize=10)
        fig.tight_layout()
        fig.savefig(out / f"rdm_{c:02d}.png", dpi=85)
        plt.close(fig)
        key.append(dict(id=f"rdm_{c:02d}", day=r.day, entry_time=r.entry_time, direction=r.direction, grade=r.grade))
    pd.DataFrame(key).to_csv(out / "charts_key.csv", index=False)
    pd.DataFrame(dict(id=[k["id"] for k in key], detection_is_right="", note="")).to_csv(out / "answers.csv", index=False)
    print(f"{len(key)} charts in {out}")


def stage2():
    RES.mkdir(parents=True, exist_ok=True)
    T, f = run(dict(P))
    T.drop(columns=["usd", "R", "pts", "exit_reason", "legs"]).to_csv(RES / "stage2_baseline_setups.csv", index=False)
    print("baseline detection funnel: " + " | ".join(f"{k} {v}" for k, v in f.items()))
    print(f"baseline trades {len(T)} on {T.day.nunique() if len(T) else 0} days; long {int((T.direction == 'long').sum())}, "
          f"short {int((T.direction == 'short').sum())}; with 15m SMT {int(T.smt15.sum())}")
    charts(T)
    return T, f


RUNS = [("baseline", {}), ("V1 Grade B included", dict(grade_b=True)), ("V2 15m SMT required", dict(req15=True)),
        ("V3 sweep takes an untaken session level", dict(took_level=True)),
        ("V4 stop at the most recent 1m swing", dict(swing_stop=True)), ("V5 skip 08:30 / 10:00 news days", dict(skip_news=True)),
        ("V6 first trade of the day only", dict(first_only=True)), ("V7 zones of all fractions", dict(all_fractions=True))]
ALPHA = 0.05 / 8


def stats(T, all_days):
    if len(T) == 0:
        return dict(n=0)
    R = T.R.to_numpy()
    y = pd.to_datetime(T.day).dt.year
    by = T.groupby(y).usd.sum()
    years = range(2019, 2027)
    eq = np.cumsum(R)
    streak = mx = 0
    for r in R:
        streak = streak + 1 if r < 0 else 0
        mx = max(mx, streak)
    rng = np.random.default_rng(1)
    boots = R[rng.integers(0, len(R), size=(10000, len(R)))].mean(axis=1)
    gw, gl = T.usd[T.usd > 0].sum(), -T.usd[T.usd < 0].sum()
    cut = sorted(all_days)[int(0.7 * len(all_days))]
    first70, last30 = T[T.day < cut], T[T.day >= cut]
    h1, h2 = T[y <= 2022], T[y >= 2023]
    m = lambda x: round(x.R.mean(), 3) if len(x) else None
    return dict(n=len(T), win=round(100 * (T.usd > 0).mean(), 1), R=round(R.mean(), 3), exp_usd=round(T.usd.mean(), 1),
                pts=round(T.pts.mean(), 2), net=round(T.usd.sum()), pf=round(gw / gl, 2) if gl else None,
                ddR=round((eq - np.maximum.accumulate(eq)).min(), 2), lose_streak=mx,
                ci=(round(np.quantile(boots, 0.025), 3), round(np.quantile(boots, 0.975), 3)),
                p=float((boots <= 0).mean()), pos_years=int(sum(by.get(k, 0) > 0 for k in years)),
                R_h1=m(h1), n_h1=len(h1), R_h2=m(h2), n_h2=len(h2), R_70=m(first70), n_70=len(first70),
                R_30=m(last30), n_30=len(last30), cut=cut)


def report():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    RES.mkdir(parents=True, exist_ok=True)
    prep()
    all_days = [d.strftime("%Y-%m-%d") for d in D["tdays"][1:] if d not in D["roll"] and d.strftime("%Y-%m-%d") not in D["early"]]
    rows, allT, funnels = [], [], {}
    for name, v in RUNS:
        T, f = run({**P, **v}, name)
        funnels[name] = f
        nb = [stats(run({**P, **v, "pivot_len": k}, name)[0], all_days) for k in (2, 4)]
        s_ = stats(T, all_days)
        if len(T):
            T.insert(0, "run", name); allT.append(T)
        ok = (s_.get("n", 0) > 0 and s_["pos_years"] >= 6 and s_["R"] >= 0.05 and (s_["R_h1"] or -1) >= 0 and
              (s_["R_h2"] or -1) >= 0 and all(x.get("n", 0) > 0 and np.sign(x["R"]) == np.sign(s_["R"]) for x in nb) and s_["p"] < ALPHA)
        rows.append(dict(run=name, **s_, nb2=nb[0].get("R"), nb4=nb[1].get("R"), nb2_n=nb[0].get("n"), nb4_n=nb[1].get("n"),
                         passes=ok))
        print(f"{name}: " + "  ".join(f"{k} {x}" for k, x in rows[-1].items() if k != "run"))
    S_ = pd.DataFrame(rows)
    TT = pd.concat(allT, ignore_index=True)
    TT.drop(columns=["t1", "trig", "p_ref", "gap_i"]).to_csv(RES / "trades.csv", index=False)
    S_.to_csv(RES / "summary.csv", index=False)
    # equity curves
    fig, ax = plt.subplots(figsize=(13, 6))
    for name, g in TT.groupby("run", sort=False):
        ax.plot(pd.to_datetime(g.day), g.R.cumsum(), lw=2.2 if name == "baseline" else 1, label=f"{name} ({len(g)})",
                marker="o" if name == "baseline" else None, ms=4)
    ax.axhline(0, color="gray", lw=0.6); ax.set_ylabel("cumulative R"); ax.legend(fontsize=8); ax.grid(alpha=0.2)
    ax.set_title("RDM equity in R, baseline and the 7 variants (each one change from the baseline)", loc="left", fontsize=10)
    fig.tight_layout(); fig.savefig(RES / "equity.png", dpi=90); plt.close(fig)
    # report.md
    B = TT[TT.run == "baseline"]
    L = ["# RDM — report", "",
         "> **16 baseline trades in 7.3 years cannot support a verdict.** The numbers below describe what this coded reading did; "
         "they cannot tell a real edge from luck. Read every table with its n.", "",
         "Coded reading of the Ryze Divergence Model as pre-registered in BACKTEST_LOG.md (\"RDM\"), with the logged amendment "
         "(early-close and holiday sessions excluded). MNQ for NQ, Databento 1m, 2019-06 → 2026-10-07, roll days excluded, "
         "$1 per side + 1 tick per fill, 1 MNQ. 8 runs, Bonferroni α = 0.05 / 8 = 0.00625.", "",
         "## Detection funnel (baseline)", "", "| Step | Count | Removed by this step |", "|---|---|---|"]
    fb = funnels["baseline"]
    order = sorted([k for k in fb if k[0].isdigit()])
    prev = None
    for k in order:
        L.append(f"| {k[2:]} | {fb[k]} | {'' if prev is None else prev - fb[k]} |"); prev = fb[k]
    for k in sorted(k for k in fb if k.startswith("skip")):
        L.append(f"| {k} | {fb[k]} | |")
    L += ["", "Steps 1–6 count 1m SMT events of both grades. A step's removals: the event fails that condition. "
          "Skips are setups that reached the trade rules and were not taken.", "",
          "## All runs", "",
          "| Run | n | Win % | R / trade | $ / trade | Net $ | PF | Max DD (R) | Longest losing streak | 95 % CI mean R | p | Positive years | R 2019–22 (n) | R 2023–26 (n) | R first 70 % (n) | R last 30 % (n) | Neighbours R (pivot_len 2 / 4, n) | Passes |",
          "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        if r.get("n", 0) == 0:
            L.append(f"| {r['run']} | 0 | | | | | | | | | | | | | | | {r['nb2']} / {r['nb4']} | no |"); continue
        L.append(f"| {r['run']} | {r['n']} | {r['win']} | {r['R']:+.3f} | {r['exp_usd']:+.1f} | {r['net']:+,} | {r['pf']} | {r['ddR']} | "
                 f"{r['lose_streak']} | {r['ci'][0]:+.3f} to {r['ci'][1]:+.3f} | {r['p']:.3f} | {r['pos_years']} of 8 | "
                 f"{r['R_h1']} ({r['n_h1']}) | {r['R_h2']} ({r['n_h2']}) | {r['R_70']} ({r['n_70']}) | {r['R_30']} ({r['n_30']}) | "
                 f"{r['nb2']} ({r['nb2_n']}) / {r['nb4']} ({r['nb4_n']}) | {'**yes**' if r['passes'] else 'no'} |")
    L += ["", f"The 70 / 30 split cuts at {rows[0].get('cut')} (70 % of the {len(all_days)} eligible trading days).", ""]
    if len(B):
        L += ["## Baseline breakdowns (n is tiny; descriptive only)", ""]
        Bt = B.assign(et=pd.to_datetime(B.entry_time, utc=True).dt.tz_convert(TZ))
        for lab, col in (("month", Bt.et.dt.month), ("weekday", Bt.et.dt.day_name().str[:3]), ("hour", Bt.et.dt.hour),
                         ("side", Bt.direction), ("exit", Bt.exit_reason), ("year", Bt.et.dt.year)):
            L.append(f"- **By {lab}:** " + " · ".join(f"{k} {len(g)} trades, {g.R.mean():+.2f} R" for k, g in Bt.groupby(col)))
        L += ["", "Baseline trades: " + ", ".join(f"{r.day} {r.direction} {r.R:+.2f} R ({r.exit_reason})" for r in B.itertuples()), ""]
    (RES / "report.md").write_text("\n".join(L) + "\n")
    print("\n".join(L))
    return rows, funnels


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "summary"
    if cmd == "summary":
        summary()
    elif cmd == "stage2":
        stage2()
    elif cmd == "report":
        report()
