#!/usr/bin/env python3
"""IFVG-1m: the trader's IFVG rule on MNQ 1-minute bars (pre-registered in data/studies/audit/IFVG1m_spec.md).

    python3 tools/ifvg1m_engine.py all                     every run, neighbour and the Asia report (the logged result)
    python3 tools/ifvg1m_engine.py run [--exit T3|T2|TL] [--zones all|high] [--session ny|asia] [--fresh 5]
                                       [--min-gap 1.0] [--cap 2.0] [--out trades.csv]
    python3 tools/ifvg1m_engine.py charts [--n 10] [--seed 11]      1m charts of random primary-run trades, cut at entry
    python3 tools/ifvg1m_engine.py esdist trades.csv [--out with_es.csv]   ES distance from its level at the sweep bar

Data: MNQ and ES 1m bars (data/bars/{MNQ,ES}_1m.parquet, Databento, New York time); ES aligned to the MNQ minutes
(a missing ES minute repeats the last). 5m bars are the 1m bars in 5-minute buckets. Zone windows are cached in
data/bars/ifvg1m_zones.parquet (git-ignored).

The rule, as written in the spec, with the readings this file had to choose (also in BACKTEST_LOG.md, "IFVG-1m"):
  Session  NY AM: entries on 1m bars opening 09:30-10:59, flat at the close of the last bar before 12:00.
           Asia: entries 18:10-23:59, flat at the close of the last bar before 02:00. All state resets at the
           17:00 halt: a trading session runs 18:00 -> 17:00 and nothing crosses it.
  Levels   MNQ 5m 3-bar fractals of the session (high > the bar before, >= the bar after; known at the close of the
           bar after) and the previous trading day's MNQ high / low. ES's corresponding level: its highest high
           (lowest low) over the same three 5m bars, or ES's own previous-day high / low.
  Sweep+SMT  Level: the first 1m bar whose high trades > level + 2 ticks (the sweep bar; the level is then used up).
           It is an SMT when ES does not trade > its level + 2 ticks within the 5m bar before, the 5m bar of, and
           the 5m bar after the sweep. Reading: as known at each minute - ES taking it at or before the sweep minute
           means no SMT; ES taking it later in that window ends the SMT from that minute (a trade already entered
           stands). Pivot: two consecutive session fractal highs where MNQ's is > 2 ticks higher and ES's
           corresponding high is not > 2 ticks higher (mirror for lows); the sweep bar is the first 1m bar beyond
           MNQ's earlier fractal; it can be used from the close of the 5m bar that confirms the new fractal.
           Only MNQ as the market that trades beyond (the spec's wording). A pivot SMT ends when ES later trades
           > 2 ticks beyond its own earlier swing high (low), as the indicator's pivot SMT does.
           Setup lifetime (not in the spec; the indicator's): 30 1m bars after the sweep leg's latest extreme.
  Gap      1m FVG (bar[i-2].high < bar[i].low bullish, mirror bearish), height >= min gap, all three candles in
           the session. Against a high sweep (short) the gaps are bullish, below the sweep extreme.
  Inversion  First 1m close that is below the gap's low, or at least 80 % of the way down through it on a strong
           bearish candle (body >= 60 % of range, range >= ATR(20) of 1m, RMA). A gap's first inversion uses it up.
           It counts only on or after the sweep bar and within `fresh` bars of the gap's third candle, so the
           30-bar gap expiry never binds; the newest such gap is the one taken. Mirror for longs.
  Zone     The gap overlaps, or the sweep extreme lies inside, an eligible HTF zone (ZoneBook from ifvg_engine.py on
           the 1m chart: Run I lifecycle and 50 % CE eligibility, 7-day / close-through / 6-per-TF removal). The
           indicator's cluster-selection engine is not applied (the spec names lifecycle and CE eligibility only).
  Stop     Sweep extreme through the entry bar + 2 ticks; skipped if farther than cap x ATR(14) of the last closed
           5m bar. A signal (inversion + setup + zone + stop cap) uses up every live setup of its direction.
  Exits    T3 3 R, T2 2 R, TL the nearest 5m fractal beyond the entry on the profit side formed since the session
           open (09:30 / 18:00; known by the entry bar), skipped if none or < 1 R. All flat at the flatten time.
  Management  Max 3 entries per session, stop after the first winner (net > 0) or after 2 consecutive losers
           (net < 0), no entry while a trade is open. Signals outside the entry window use up their setup, no trade.
Fills (house): entry at the signal close + 1 tick; stop / target at their price - 1 tick (the open if the bar opens
beyond); stop first on a bar touching both; flatten at the close - 1 tick; $1 per side; MNQ $2 / point.
"""
import sys, pathlib, collections
import numpy as np
import pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from ifvg_engine import ZoneBook, P as P5, rma_atr, trading_date, htf_bars

TZ = "America/New_York"
TICK, PV, COMM = 0.25, 2.0, 1.0
TOL = 2 * TICK
ZONES_ALL = ("15m", "1H", "4H", "1D", "NDOG")
ZONES_HIGH = ("1H", "4H", "1D")
PRIMARY = dict(fresh=5, min_gap=1.0, cap=2.0)
NEIGHBOURS = (("fresh", 3), ("fresh", 8), ("min_gap", 0.5), ("min_gap", 2.0), ("cap", 1.5), ("cap", 3.0))
SESSIONS = dict(ny=dict(entry=(9 * 60 + 30, 11 * 60), flat=12 * 60, open=9 * 60 + 30, loop=8 * 60 + 30),
                asia=dict(entry=(18 * 60 + 10, 24 * 60), flat=2 * 60, open=18 * 60, loop=18 * 60))
CACHE = pathlib.Path("data/bars/ifvg1m_zones.parquet")
S = {}          # loaded data


def load():
    if S:
        return S
    a = pd.read_parquet("data/bars/MNQ_1m.parquet")
    b = pd.read_parquet("data/bars/ES_1m.parquet").reindex(a.index).ffill()
    ts = a.index
    O, H, L, C = (a[k].to_numpy() for k in ("open", "high", "low", "close"))
    td = trading_date(ts)
    tdi = pd.factorize(td)[0]
    b5key = ts.floor("5min")
    k5 = pd.factorize(b5key)[0]                       # 5m bucket per 1m bar (buckets are in time order)
    g = pd.DataFrame({"k": k5, "i": np.arange(len(ts))}).groupby("k").i
    first5, last5 = g.min().to_numpy(), g.max().to_numpy()
    H5 = pd.Series(H).groupby(k5).max().to_numpy(); L5 = pd.Series(L).groupby(k5).min().to_numpy()
    C5 = pd.Series(C).groupby(k5).last().to_numpy()
    HB, LB = b.high.to_numpy(), b.low.to_numpy()
    HB5 = pd.Series(HB).groupby(k5).max().to_numpy(); LB5 = pd.Series(LB).groupby(k5).min().to_numpy()
    S.update(a=a, ts=ts, O=O, H=H, L=L, C=C, HB=HB, LB=LB, td=td, tdi=tdi, k5=k5, first5=first5, last5=last5,
             H5=H5, L5=L5, HB5=HB5, LB5=LB5, sess5=tdi[first5], atr5=rma_atr(H5, L5, C5),
             atr1=rma_atr_n(H, L, C, 20), tod=(ts.hour * 60 + ts.minute).to_numpy())
    rng = np.maximum(H - L, 1e-9)
    body = np.abs(C - O)
    strong = (body >= 0.6 * rng) & (rng >= S["atr1"])
    S["strong_bear"], S["strong_bull"] = strong & (C < O), strong & (C > O)
    S["zones"] = zones()
    return S


def rma_atr_n(h, l, c, n):
    pc = np.r_[np.nan, c[:-1]]
    tr = np.nanmax(np.c_[h - l, np.abs(h - pc), np.abs(l - pc)], axis=1)
    tr[0] = h[0] - l[0]
    return pd.Series(tr).ewm(alpha=1 / n, adjust=False).mean().to_numpy()


def zones():
    if CACHE.exists():
        return pd.read_parquet(CACHE)
    one = S["a"]
    book = ZoneBook(one, S["ts"], S["O"], S["H"], S["L"], S["C"], rma_atr(S["H"], S["L"], S["C"]), P5["htf"],
                    P5["ndog"], P5["htf_days"], P5["htf_cap"], record=True)
    for i in range(len(S["ts"])):
        book.pre(i)
        book.post(i)
    w = book.windows().drop(columns=["t1"])
    w.to_parquet(CACHE)
    return w


def sweeps():
    """All SMT setups: dict(dir, kind, sweep, active, dies, lvl, sess)."""
    if "setups" in S:
        return S["setups"]
    H, L, HB, LB = S["H"], S["L"], S["HB"], S["LB"]
    H5, L5, HB5, LB5, first5, last5, sess5 = S["H5"], S["L5"], S["HB5"], S["LB5"], S["first5"], S["last5"], S["sess5"]
    tdi, n = S["tdi"], len(H)
    starts = np.r_[0, np.flatnonzero(np.diff(tdi)) + 1]
    ends = np.r_[starts[1:], n]                      # session s = 1m bars [starts[s], ends[s])
    # previous trading day's high / low, both markets
    dH = pd.Series(H).groupby(tdi).max().to_numpy(); dL = pd.Series(L).groupby(tdi).min().to_numpy()
    dHB = pd.Series(HB).groupby(tdi).max().to_numpy(); dLB = pd.Series(LB).groupby(tdi).min().to_numpy()
    s5 = np.r_[0, np.flatnonzero(np.diff(sess5)) + 1]
    e5 = np.r_[s5[1:], len(sess5)]
    out = []

    def es_check(j, lvlB, high, s):
        """None = no SMT; else the 1m bar at which ES takes its level inside the window (or None if it never does)."""
        k = S["k5"][j]
        a = first5[k - 1] if k - 1 >= 0 and sess5[k - 1] == sess5[k] else starts[s]
        b = last5[k + 1] if k + 1 < len(sess5) and sess5[k + 1] == sess5[k] else last5[k]
        x = (HB[a:b + 1] > lvlB + TOL) if high else (LB[a:b + 1] < lvlB - TOL)
        hit = np.flatnonzero(x)
        if len(hit) == 0:
            return "ok", None
        m = a + hit[0]
        return ("no", None) if m <= j else ("ok", m)

    def first_beyond(a, b, lvl, high):
        x = (H[a:b] > lvl + TOL) if high else (L[a:b] < lvl - TOL)
        h = np.flatnonzero(x)
        return a + h[0] if len(h) else None

    for s in range(len(starts)):
        a1, b1 = starts[s], ends[s]
        sidx = tdi[a1]
        levels = []                                   # (price, esPrice, high, from_1m, kind)
        if s > 0:
            levels.append((dH[sidx - 1], dHB[sidx - 1], True, a1, "PDH"))
            levels.append((dL[sidx - 1], dLB[sidx - 1], False, a1, "PDL"))
        ks = np.arange(s5[s], e5[s])
        fr_hi, fr_lo = [], []
        for p in ks[1:-1]:
            if H5[p] > H5[p - 1] and H5[p] >= H5[p + 1]:
                fr_hi.append(p)
                if p + 2 < e5[s]:
                    levels.append((H5[p], HB5[p - 1:p + 2].max(), True, first5[p + 2], "swing"))
            if L5[p] < L5[p - 1] and L5[p] <= L5[p + 1]:
                fr_lo.append(p)
                if p + 2 < e5[s]:
                    levels.append((L5[p], LB5[p - 1:p + 2].min(), False, first5[p + 2], "swing"))
        for lvl, lvlB, high, fr, kind in levels:
            j = first_beyond(fr, b1, lvl, high)
            if j is None:
                continue
            st, dies = es_check(j, lvlB, high, s)
            if st == "ok":
                out.append(dict(dir="S" if high else "L", kind=kind, sweep=j, active=j, dies=dies, lvl=lvl, lvlB=lvlB, sess=s))
        for frs, high in ((fr_hi, True), (fr_lo, False)):
            for q, p in zip(frs, frs[1:]):
                A0, A1 = (H5[q], H5[p]) if high else (L5[q], L5[p])
                B0 = HB5[q - 1:q + 2].max() if high else LB5[q - 1:q + 2].min()
                B1 = HB5[p - 1:p + 2].max() if high else LB5[p - 1:p + 2].min()
                sg = 1 if high else -1
                if sg * (A1 - A0) > TOL and not sg * (B1 - B0) > TOL and p + 1 < e5[s]:
                    j = first_beyond(first5[q + 1], last5[p] + 1, A0, high)
                    if j is not None:
                        # ends when ES trades beyond its own earlier swing (the indicator's pivot-SMT invalidation)
                        a2 = last5[p + 1] + 1
                        xb = (HB[a2:b1] > B0 + TOL) if high else (LB[a2:b1] < B0 - TOL)
                        hb = np.flatnonzero(xb)
                        out.append(dict(dir="S" if high else "L", kind="pivot", sweep=j, active=last5[p + 1],
                                        dies=a2 + hb[0] if len(hb) else None, lvl=A0, lvlB=B0, sess=s))
    d = pd.DataFrame(out).sort_values(["sess", "active", "sweep"]).reset_index(drop=True)
    S["setups"] = d
    S["starts"], S["ends"] = starts, ends
    return d


def fractals_since(j, open_i, sess, high):
    """5m fractal prices of the session formed at or after 1m bar open_i and known (confirmed) by 1m bar j."""
    H5, L5, first5, last5, sess5 = S["H5"], S["L5"], S["first5"], S["last5"], S["sess5"]
    k0, k1 = S["k5"][open_i], S["k5"][j]
    out = []
    for p in range(max(k0, 1), k1):
        if p + 1 >= len(H5) or sess5[p - 1] != sess5[p] or sess5[p + 1] != sess5[p] or last5[p + 1] > j:
            continue
        if high and H5[p] > H5[p - 1] and H5[p] >= H5[p + 1]:
            out.append(H5[p])
        if not high and L5[p] < L5[p - 1] and L5[p] <= L5[p + 1]:
            out.append(L5[p])
    return out


def signals(fresh=5, min_gap=1.0, cap=2.0, zset=ZONES_ALL, session="ny"):
    """Every signal (inversion + live setup + zone + stop cap) and the funnel counts."""
    load(); setups = sweeps()
    O, H, L, C, tod, ts = S["O"], S["H"], S["L"], S["C"], S["tod"], S["ts"]
    starts, ends = S["starts"], S["ends"]
    sb, sB = S["strong_bear"], S["strong_bull"]
    zw = S["zones"]
    zw = zw[zw.tf.isin(zset)]
    zf, ze, zt, zb, ztf = (zw[c].to_numpy() for c in ("first", "end", "top", "bot", "tf"))
    cfg = SESSIONS[session]
    e0, e1 = cfg["entry"]
    by_sess = {s: g for s, g in setups.groupby("sess")}
    sigs, funnel = [], collections.Counter()
    for s in range(len(starts)):
        a1, b1 = starts[s], ends[s]
        t = tod[a1:b1]
        # a session's minutes run 18:00 -> 23:59 -> 00:00 -> 16:59, so windows are found by value, not by sorting
        win = np.flatnonzero((t >= e0) & (t < e1))
        if session == "ny":
            m = np.flatnonzero((t >= cfg["loop"]) & (t < 18 * 60))
            lo = a1 + m[0] if len(m) else None
        else:
            lo = a1
        if lo is None or len(win) == 0:
            continue
        w0, w1 = a1 + win[0], a1 + win[-1]
        g = by_sess.get(s)
        live = []
        pend = [] if g is None else g.to_dict("records")
        for x in pend:                                # NaN (no ES take in the window) -> None
            x["dies"] = None if pd.isna(x["dies"]) else int(x["dies"])
        pend = [x for x in pend if x["active"] <= w1]
        pi = 0
        zm = (zf <= w1) & (ze > lo)
        zz = (zf[zm], ze[zm], zt[zm], zb[zm], ztf[zm])
        gaps = {"S": [], "L": []}                     # alive gaps: [third_i, top, bot]
        for j in range(lo, w1 + 1):
            inwin = j >= w0
            # setups becoming active
            while pi < len(pend) and pend[pi]["active"] <= j:
                x = pend[pi]; pi += 1
                seg = H[x["sweep"]:j + 1] if x["dir"] == "S" else L[x["sweep"]:j + 1]
                e = int(np.argmax(seg) if x["dir"] == "S" else np.argmin(seg))
                x.update(ext=seg[e], ext_j=x["sweep"] + e, used=False, gap=False, inv=False, zone=False, cnt=False)
                live.append(x)
            # extend extremes, expire
            for x in live:
                if x["used"]:
                    continue
                if x["sweep"] <= j and j > x["ext_j"]:
                    if x["dir"] == "S" and H[j] > x["ext"]:
                        x["ext"], x["ext_j"] = H[j], j
                    elif x["dir"] == "L" and L[j] < x["ext"]:
                        x["ext"], x["ext_j"] = L[j], j
            live = [x for x in live if not x["used"] and j - x["ext_j"] <= 30 and (x["dies"] is None or j < x["dies"])]
            if inwin:
                for x in live:
                    if not x["cnt"]:
                        x["cnt"] = True; funnel["1 sweep+SMT"] += 1; funnel["1 sweep+SMT [" + ("pivot" if x["kind"] == "pivot" else "level") + "]"] += 1
                    if not x["gap"]:
                        gl = gaps["S" if x["dir"] == "S" else "L"]
                        if any((q[1] <= x["ext"]) if x["dir"] == "S" else (q[2] >= x["ext"]) for q in gl):
                            x["gap"] = True; funnel["2 gap alive"] += 1; funnel["2 gap alive [" + ("pivot" if x["kind"] == "pivot" else "level") + "]"] += 1
            # inversions on this close
            ev = {}
            for d in ("S", "L"):
                keep = []
                for q in gaps[d]:
                    i, top, bot = q
                    if d == "S":          # bullish gap, broken downward
                        inv = C[j] < bot or (C[j] <= top - 0.8 * (top - bot) and sb[j])
                    else:
                        inv = C[j] > top or (C[j] >= bot + 0.8 * (top - bot) and sB[j])
                    if inv:
                        if j - i <= fresh and (d not in ev or i > ev[d][0]):
                            ev[d] = q
                    elif j - i < 30:                  # a gap expires 30 bars after its third candle
                        keep.append(q)
                gaps[d] = keep
            for d, q in ev.items():
                i, top, bot = q
                cand = [x for x in live if x["dir"] == d and x["sweep"] <= j and
                        ((top <= x["ext"]) if d == "S" else (bot >= x["ext"]))]
                if not cand:
                    continue
                x = max(cand, key=lambda x: (x["active"], x["sweep"]))
                if inwin and not x["inv"]:
                    x["inv"] = True; funnel["3 fresh inversion"] += 1; funnel["3 fresh inversion [" + ("pivot" if x["kind"] == "pivot" else "level") + "]"] += 1
                ext = x["ext"]
                m = (zz[0] <= j) & (zz[1] > j) & (((zz[2] >= bot) & (zz[3] <= top)) | ((zz[3] <= ext) & (zz[2] >= ext)))
                if not m.any():
                    continue
                if inwin and not x["zone"]:
                    x["zone"] = True; funnel["4 HTF zone"] += 1; funnel["4 HTF zone [" + ("pivot" if x["kind"] == "pivot" else "level") + "]"] += 1
                sgn = -1 if d == "S" else 1
                stop = ext - sgn * TOL
                risk = sgn * (C[j] - stop)
                k = S["k5"][j]
                a5 = S["atr5"][k] if ts[j].minute % 5 == 4 else S["atr5"][k - 1]
                if risk <= 0 or risk > cap * a5:
                    continue
                for y in live:
                    if y["dir"] == d and y["sweep"] <= j:
                        y["used"] = True
                if inwin:
                    funnel["5 stop cap"] += 1; funnel["5 stop cap [" + ("pivot" if x["kind"] == "pivot" else "level") + "]"] += 1
                tfs = set(zz[4][m])
                sigs.append(dict(sess=s, j=j, entry_time=ts[j], side=d, stop=stop, risk=risk, close=C[j], smt=x["kind"],
                                 smt_type="pivot" if x["kind"] == "pivot" else "level", sweep_j=x["sweep"], ext=ext,
                                 lvl=x["lvl"], lvlB=x["lvlB"], gap_i=i, gap_top=top, gap_bot=bot, inwin=inwin,
                                 zone=max(tfs, key=lambda z: ("15m", "NDOG", "1H", "4H", "1D").index(z)),
                                 zones="+".join(sorted(tfs))))
            # new gap completed on this bar (its three candles in the session)
            if j - 2 >= a1:
                if L[j] - H[j - 2] >= min_gap and L[j] > H[j - 2]:
                    gaps["S"].append([j, L[j], H[j - 2]])
                if L[j - 2] - H[j] >= min_gap and H[j] < L[j - 2]:
                    gaps["L"].append([j, L[j - 2], H[j]])
    return pd.DataFrame(sigs), funnel


def flat_bar(j, session):
    """Index of the last 1m bar before the flatten time for the session of entry bar j."""
    tod, tdi = S["tod"], S["tdi"]
    fl = SESSIONS[session]["flat"]
    k = j
    n = len(tod)
    if session == "ny":
        while k + 1 < n and tdi[k + 1] == tdi[j] and tod[k + 1] < fl:
            k += 1
    else:
        while k + 1 < n and tdi[k + 1] == tdi[j] and (tod[k + 1] >= 18 * 60 or tod[k + 1] < fl):
            k += 1
    return k


def trades(sig, exit_="T3", session="ny"):
    """Session management and exits over a signal list."""
    O, H, L, C, ts = S["O"], S["H"], S["L"], S["C"], S["ts"]
    out, stops = [], collections.Counter()
    if sig.empty:
        return pd.DataFrame(), stops
    for s, g in sig[sig.inwin].groupby("sess"):
        n_ent, losers, done, busy_until = 0, 0, False, -1
        for r in g.itertuples():
            if done or r.j <= busy_until:
                continue
            sgn = 1 if r.side == "L" else -1
            if exit_ == "TL":
                t_ = S["tod"][S["starts"][s]:S["ends"][s]]
                open_i = S["starts"][s] if session == "asia" else \
                    S["starts"][s] + int(np.flatnonzero((t_ >= SESSIONS["ny"]["open"]) & (t_ < 18 * 60))[0])
                fr = fractals_since(r.j, open_i, s, r.side == "L")
                fr = [f for f in fr if sgn * (f - r.close) > 0]
                if not fr:
                    stops["TL no level"] += 1; continue
                tp = min(fr) if sgn > 0 else max(fr)
                if sgn * (tp - r.close) < 1.0 * r.risk:
                    stops["TL < 1 R"] += 1; continue
            else:
                tp = r.close + sgn * (3 if exit_ == "T3" else 2) * r.risk
            f = flat_bar(r.j, session)
            entry = r.close + sgn * TICK
            res = None
            for q in range(r.j + 1, f + 1):
                o = O[q]
                if sgn * (o - r.stop) <= 0:
                    res = (q, o - sgn * TICK, "SL"); break
                if sgn * (o - tp) >= 0:
                    res = (q, o - sgn * TICK, "TP"); break
                if (L[q] <= r.stop) if sgn > 0 else (H[q] >= r.stop):
                    res = (q, r.stop - sgn * TICK, "SL"); break
                if (H[q] >= tp) if sgn > 0 else (L[q] <= tp):
                    res = (q, tp - sgn * TICK, "TP"); break
            if res is None:
                res = (f, C[f] - sgn * TICK, "time")
            pnl = sgn * (res[1] - entry) * PV - 2 * COMM
            out.append({**r._asdict(), "tp": tp, "entry": entry, "exit_time": ts[res[0]], "exit": res[1],
                        "reason": res[2], "pnl": pnl, "R": pnl / (r.risk * PV)})
            busy_until = res[0]
            n_ent += 1
            if pnl > 0:
                done = True; stops["stopped: 1 win"] += 1
            else:
                losers = losers + 1 if pnl < 0 else 0
                if losers >= 2:
                    done = True; stops["stopped: 2 losses"] += 1
            if n_ent >= 3 and not done:
                done = True; stops["stopped: 3 trades"] += 1
    t = pd.DataFrame(out).drop(columns=["Index"], errors="ignore")
    return t, stops


def summary(t):
    if t.empty:
        return dict(n=0)
    y = t.entry_time.dt.year
    eq = t.pnl.cumsum()
    gw, gl = t.pnl[t.pnl > 0].sum(), -t.pnl[t.pnl < 0].sum()
    h1, h2 = t[y <= 2022], t[y >= 2023]
    return dict(n=len(t), net=round(t.pnl.sum()), R=round(t.R.mean(), 3), win=round(100 * (t.pnl > 0).mean(), 1),
                pf=round(gw / gl, 2) if gl else None, dd=round((eq - eq.cummax()).min()),
                pos_years=int((t.groupby(y).pnl.sum() > 0).sum()), years=int(y.nunique()),
                R_h1=round(h1.R.mean(), 3) if len(h1) else None, R_h2=round(h2.R.mean(), 3) if len(h2) else None)


def report(t, stops, funnel, label):
    s = summary(t)
    print(f"\n==== {label}: " + "  ".join(f"{k} {v}" for k, v in s.items()))
    if t.empty:
        return s
    y = t.entry_time.dt.year
    for name, col in (("year", y), ("side", t.side), ("zone", t.zone), ("smt", t.smt_type), ("exit", t.reason)):
        print(f"  by {name}: " + " | ".join(f"{k}: n {len(g)} net {g.pnl.sum():+,.0f} R {g.R.mean():+.3f}" for k, g in t.groupby(col)))
    print("  funnel: " + " -> ".join(f"{k[2:]} {v}" for k, v in sorted(funnel.items()) if "[" not in k) + f" -> trades {len(t)}")
    for typ in ("level", "pivot"):
        print(f"    {typ} SMTs: " + " -> ".join(f"{k[2:].split(' [')[0]} {v}" for k, v in sorted(funnel.items()) if f"[{typ}]" in k))
    print("  sessions: " + ", ".join(f"{k} {v}" for k, v in stops.items()))
    return s


def passes(s, neigh):
    ok_years = s.get("pos_years", 0) >= 6
    ok_r = s.get("R", -1) >= 0.05
    ok_h = (s.get("R_h1") or -1) >= 0 and (s.get("R_h2") or -1) >= 0
    ok_n = all((x.get("R", -1) > 0) for x in neigh)
    return ok_years and ok_r and ok_h and ok_n, dict(years=ok_years, R=ok_r, halves=ok_h, neighbours=ok_n)


def run_all(outdir):
    outdir = pathlib.Path(outdir); outdir.mkdir(parents=True, exist_ok=True)
    load(); sweeps()
    rows = []
    for zname, zset in (("Z-all", ZONES_ALL), ("Z-high", ZONES_HIGH)):
        base_sig, fun = signals(**PRIMARY, zset=zset)
        neigh_sig = {nb: signals(**{**PRIMARY, nb[0]: nb[1]}, zset=zset)[0] for nb in NEIGHBOURS}
        for ex in ("T3", "T2", "TL"):
            t, st = trades(base_sig, ex)
            t.to_csv(outdir / f"IFVG1m_{ex}_{zname}.csv", index=False)
            s = report(t, st, fun, f"{ex} {zname}")
            nb = []
            for key, sg in neigh_sig.items():
                tn, _ = trades(sg, ex)
                sn = summary(tn)
                nb.append(sn)
                print(f"    neighbour {key[0]}={key[1]}: " + "  ".join(f"{k} {v}" for k, v in sn.items()))
            ok, parts = passes(s, nb)
            print(f"  criterion: {'PASS' if ok else 'fail'} {parts}")
            rows.append(dict(run=f"{ex} {zname}", **s, **{f"crit_{k}": v for k, v in parts.items()}, passes=ok))
    sig, fun = signals(**PRIMARY, zset=ZONES_ALL, session="asia")
    t, st = trades(sig, "T3", session="asia")
    t.to_csv(outdir / "IFVG1m_T3_Z-all_asia.csv", index=False)
    report(t, st, fun, "Asia (report only) T3 Z-all")
    pd.DataFrame(rows).to_csv(outdir / "IFVG1m_summary.csv", index=False)
    print(pd.DataFrame(rows).to_string(index=False))


def charts(n=10, seed=11, out="data/studies/ifvg1m_charts"):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle
    load(); sweeps()
    sig, _ = signals(**PRIMARY, zset=ZONES_ALL)
    t, _ = trades(sig, "T3")
    rng = np.random.default_rng(seed)
    pick = t.iloc[np.sort(rng.choice(len(t), size=n, replace=False))]
    out = pathlib.Path(out); out.mkdir(parents=True, exist_ok=True)
    O, H, L, C, HB, LB, ts = S["O"], S["H"], S["L"], S["C"], S["HB"], S["LB"], S["ts"]
    zw = S["zones"]
    key = []
    for c, r in enumerate(pick.itertuples(), 1):
        j = r.j
        s0 = max(min(j - 60, r.sweep_j - 10), S["starts"][r.sess])
        idx = np.arange(s0, j + 1)
        X = lambda k: k - s0
        fig, (ax, bx) = plt.subplots(2, 1, figsize=(16, 10), sharex=True, gridspec_kw=dict(height_ratios=[3, 1.3]))
        for ax_, o_, h_, l_, c_ in ((ax, O, H, L, C), (bx, None, HB, LB, None)):
            for k in idx:
                if o_ is not None:
                    col = "#26a69a" if c_[k] >= o_[k] else "#ef5350"
                    ax_.plot([X(k)] * 2, [l_[k], h_[k]], color=col, lw=0.8)
                    ax_.add_patch(Rectangle((X(k) - 0.35, min(o_[k], c_[k])), 0.7, max(abs(c_[k] - o_[k]), 0.05), color=col, lw=0))
                else:
                    ax_.plot([X(k)] * 2, [l_[k], h_[k]], color="#546e7a", lw=1.2)
        nv = len(idx)
        gi = r.gap_i
        ax.add_patch(Rectangle((X(gi - 2) - 0.5, r.gap_bot), nv - X(gi - 2) + 0.5, r.gap_top - r.gap_bot, color="#ffb300", alpha=0.45))
        ax.text(X(gi - 2), r.gap_top if r.side == "S" else r.gap_bot, f" 1m gap {ts[gi - 1]:%H:%M} (middle candle)",
                fontsize=8, color="#e65100", va="bottom" if r.side == "S" else "top", weight="bold")
        ax.axhline(r.lvl, color="#1565c0", ls="-.", lw=1)
        ax.text(0, r.lvl, f" swept level ({r.smt}) {r.lvl:,.2f}", fontsize=8, color="#1565c0", va="bottom")
        if r.sweep_j >= s0:
            ax.axvline(X(r.sweep_j), color="#1565c0", lw=0.6, ls=":")
            ax.text(X(r.sweep_j), ax.get_ylim()[1], f" sweep bar {ts[r.sweep_j]:%H:%M}", fontsize=8, color="#1565c0", va="top")
        ax.axhline(r.stop, color="#c62828", lw=1.2)
        ax.text(nv + 0.5, r.stop, f" stop {r.stop:,.2f}", fontsize=8, color="#c62828", va="center")
        ax.plot(X(j), r.close, ">" if r.side == "L" else "<", color="black", ms=11)
        ax.text(nv + 0.5, r.close, f" entry {'LONG' if r.side == 'L' else 'SHORT'} {r.close:,.2f} (inversion close {ts[j]:%H:%M})", fontsize=8, va="center")
        zz = zw[(zw["first"] <= j) & (zw["end"] > j) & (((zw.top >= r.gap_bot) & (zw.bot <= r.gap_top)) | ((zw.bot <= r.ext) & (zw.top >= r.ext)))]
        lo_, hi_ = min(L[idx].min(), r.lvl, r.stop), max(H[idx].max(), r.lvl, r.stop)
        lo_, hi_ = lo_ - 0.05 * (hi_ - lo_), hi_ + 0.05 * (hi_ - lo_)
        for z in zz.itertuples():
            ax.add_patch(Rectangle((-0.5, max(z.bot, lo_)), nv + 0.5, min(z.top, hi_) - max(z.bot, lo_), color="#7e57c2", alpha=0.08))
            ax.text(nv + 0.5, min(max(z.bot, lo_), hi_), f" {z.tf} zone {z.bot:,.2f}-{z.top:,.2f}", fontsize=7, color="#5e35b1")
        ax.set_ylim(lo_, hi_)
        bx.axhline(r.lvlB, color="#1565c0", ls="-.", lw=1)
        bx.text(0, r.lvlB, f" ES corresponding level {r.lvlB:,.2f}", fontsize=8, color="#1565c0", va="bottom")
        blo, bhi = min(LB[idx].min(), r.lvlB), max(HB[idx].max(), r.lvlB)
        bx.set_ylim(blo - 0.05 * (bhi - blo), bhi + 0.05 * (bhi - blo))
        bx.set_title("ES 1m (high-low) for the SMT", fontsize=9, loc="left")
        ticks = [k for k in range(nv) if ts[s0 + k].minute % 5 == 0]
        bx.set_xticks(ticks, [ts[s0 + k].strftime("%H:%M") for k in ticks], fontsize=7, rotation=90)
        ax.set_xlim(-1, nv + 16)
        ax.set_title(f"ifvg1m_{c:02d} · {ts[j]:%Y-%m-%d %a} · {'LONG' if r.side == 'L' else 'SHORT'} · SMT {r.smt} · zone {r.zones} · "
                     f"MNQ 1m, cut at the entry bar · outcome hidden", fontsize=10)
        ax.grid(alpha=0.2); bx.grid(alpha=0.2)
        fig.tight_layout()
        fig.savefig(out / f"ifvg1m_{c:02d}.png", dpi=95)
        plt.close(fig)
        key.append(dict(id=f"ifvg1m_{c:02d}", entry_time=ts[j], side=r.side, smt=r.smt, gap_mid=ts[gi - 1], sweep=ts[r.sweep_j]))
    pd.DataFrame(key).to_csv(out / "charts_key.csv", index=False)
    pd.DataFrame(dict(id=[k["id"] for k in key], gap_is_mine="", entry_is_mine="", note="")).to_csv(out / "answers.csv", index=False)
    print(f"{len(key)} charts in {out}")


def es_distance(t):
    """How far ES was from its corresponding level on the sweep bar, on the side it failed to take: ES points
    (level - ES high for a high sweep, ES low - level for a low sweep; positive = ES short of its level) and the
    same in ATR(14) of ES's last closed 5m bar."""
    load()
    b = pd.read_parquet("data/bars/ES_1m.parquet").reindex(S["ts"]).ffill()
    C5 = pd.Series(b.close.to_numpy()).groupby(S["k5"]).last().to_numpy()
    atrB5 = rma_atr(S["HB5"], S["LB5"], C5)
    j = t.sweep_j.to_numpy().astype(int)
    short = (t.side == "S").to_numpy()
    d = np.where(short, t.lvlB - S["HB"][j], S["LB"][j] - t.lvlB)
    k = S["k5"][j]
    a = np.where(S["ts"][j].minute % 5 == 4, atrB5[k], atrB5[k - 1])
    return t.assign(es_dist_pts=np.round(d, 2), es_dist_atr=np.round(d / a, 3))


if __name__ == "__main__":
    opt = lambda k, d: type(d)(sys.argv[sys.argv.index(k) + 1]) if k in sys.argv else d
    cmd = sys.argv[1] if len(sys.argv) > 1 else "all"
    if cmd == "all":
        run_all(opt("--outdir", "data/studies/ifvg1m"))
    elif cmd == "esdist":
        t = es_distance(pd.read_csv(sys.argv[2], parse_dates=["entry_time"]))
        t["tercile"] = pd.qcut(t.es_dist_atr, 3, labels=["near", "mid", "far"])
        for k, g in t.groupby("tercile", observed=True):
            print(f"{k:<5} n {len(g):>3}  ES distance {g.es_dist_pts.min():.2f}-{g.es_dist_pts.max():.2f} pts / "
                  f"{g.es_dist_atr.min():.2f}-{g.es_dist_atr.max():.2f} ATR  net {g.pnl.sum():+8,.0f}  R/trade {g.R.mean():+.3f}  "
                  f"by year R " + " ".join(f"{v:+.2f}" for v in g.groupby(pd.to_datetime(g.entry_time, utc=True).dt.year).R.mean()))
        if "--out" in sys.argv:
            t.to_csv(opt("--out", ""), index=False)
    elif cmd == "charts":
        charts(opt("--n", 10), opt("--seed", 11))
    else:
        zset = ZONES_HIGH if opt("--zones", "all") == "high" else ZONES_ALL
        sess = opt("--session", "ny")
        sig, fun = signals(opt("--fresh", 5), opt("--min-gap", 1.0), opt("--cap", 2.0), zset, sess)
        t, st = trades(sig, opt("--exit", "T3"), sess)
        report(t, st, fun, "run")
        if "--out" in sys.argv:
            t.to_csv(opt("--out", ""), index=False)
