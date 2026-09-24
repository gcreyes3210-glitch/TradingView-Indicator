#!/usr/bin/env python3
"""Local bar-by-bar port of ICT_SMT_IFVG_strategy.pine at the Run I settings (SMT + IFVG in HTF FVG).

    python3 tools/ifvg_engine.py [--tf 5] [--start 2019-06-01] [--end 2026-09-22] [--tv-fills] [--out trades.csv]
    python3 tools/ifvg_engine.py --calibrate [--tv-fills]        (against data/tradingview/RunI_MNQ_2025-2026.csv)

Data: MNQ and ES 1-minute bars (data/bars/{MNQ,ES}_1m.parquet, Databento GLBX.MDP3 .v.0, New York time). The chart
is MNQ at --tf minutes (5 = Run I); ES ("CME_MINI:ES1!") is aligned bar for bar to the MNQ chart bars, a missing ES
bar repeating the last one (request.security gaps_off).

Run I settings ported (section numbers are the Pine input groups):
  1   raw FVG pool on the chart TF (bull: low > high two bars back), age in chart bars, inversion = first close
      beyond the far edge within 30 bars of forming (break buffer 0). The event direction is the most recently
      formed inverted gap; among that direction's inverted gaps the most recent (then the larger) is the anchor.
      Every same-direction inverted gap leaves the pool; gaps inverted after 30 bars are dropped.
  1b  Loose quality on the anchor only: gap >= 0.15 ATR(14), body / range >= 0.40 and range >= 0.40 ATR, where body
      and range are those of the candle that completes the gap (the third candle, as the Pine measures it).
      A failed anchor = no IFVG on that close. IFVG valid until a close back beyond it or 50 bars.
  2   HTF zones 15m, 1H, 4H (buckets from 18:00), D (18:00-17:00 trading day) and NDOG (17:00 close -> 18:00 open).
      A zone is created on the first chart bar of the HTF bar after the gap's third candle, removed when an HTF
      close of its own TF closes through the far edge (NDOG: a chart close), after 7 days, or beyond the newest 6 of
      its TF. Lifecycle on every chart bar (after the engine): touched / partial / CE 50 % hit, then DEFENDED as soon
      as a close is back on the defended side of the CE, FILLED when the far edge trades; DEFENDED / FILLED zones are
      no longer eligible. Selection engine (Auto): overlapping eligible zones form clusters and only the best of
      each cluster counts; score = 0.35 freshness + 0.20 PDH / PDL / PWH / PWL confluence (within 0.5 chart ATR)
      + 0.20 gap-candle displacement + 0.25 timeframe rank (log, 15m -> 1D), ties by freshness, TF, displacement,
      recency. An IFVG counts when an eligible selected zone overlaps it at the inversion close (direction free).
  3/4 SMT vs ES (tolerance 2 ticks each), each a setup that must be confirmed (3 bars after the sweep) and paired
      with a same-direction IFVG that inverts at or after the sweep and <= 10 bars after the leg's latest extreme:
        sweep SMTs at PDH / PDL (both markets' previous trading day) and at chart-TF 5/5 swing references of either
        market (the other market's extreme within +/- 3 bars; up to 10 unswept per side, dropped after 800 bars):
        one market takes the level and the other does not; the SMT dies if the other takes it later; a sweep while a
        same-direction SMT is developing joins that SMT;
        pivot SMTs: each new 5/5 pivot of either market against that track's previous pivot (<= 80 bars apart):
        one market makes the higher high / lower low and the other does not.
      Setups expire 30 bars after their latest extreme or after 7 days.
  7   A signal fires at the close of the first chart bar on which a confirmed, unused SMT and an unused IFVG pair
      (newest SMT first, newest IFVG first); both are consumed even when the strategy cannot take it.
  10  Stop = the chart market's extreme from the sweep bar (pivot SMT: the pivot) through the signal bar, 2 ticks
      beyond; target 3 R from the signal close; time stop: flat at the close of the 201st bar after entry.
  S   Market entry at the signal close, one position at a time (a signal while in a trade is skipped), 1 contract.
Fills: entry at the signal close + 1 tick slippage; the stop fills at the stop (or the open if the bar opens beyond
  it) - 1 tick; the target at the target (or a better open) - 1 tick (house rule) or with no slippage (--tv-fills,
  TradingView's limit fill); a bar touching both: stop first (house) or TradingView's open -> nearer extreme path
  (--tv-fills); time exit at the close - 1 tick. $1 commission per side, MNQ $2 / point. R = net / (risk x $2).
Not ported (no effect at Run I): the IFVG confluence score (min 0, only in the tag), displacement / MSS / key-level
  filters (off), HTF swings (off), PWH / PWL SMTs (off), the 2m / 3m / 5m escalation ladder (empty on a 5m chart; on
  a 3m chart the 5m ladder is not modelled), the 15m feed (its SMTs never pair with chart IFVGs).
"""
import sys, math, argparse, collections
import numpy as np
import pandas as pd

TZ = "America/New_York"
TICK, PV, COMM = 0.25, 2.0, 1.0
TOL = 2 * TICK
HZ_FRESH, HZ_TOUCHED, HZ_PARTIAL, HZ_CE50, HZ_DEFENDED, HZ_FILLED = range(6)
P = dict(min_gap_atr=0.15, min_body=0.40, min_range_atr=0.40, max_fvg_bars=30, ifvg_age=50, piv=5, sync=3,
         confirm=3, life=30, max_days=7, pair_bars=10, piv_gap=80, swing_refs=10, swing_age=800, sl_ticks=2, rr=3.0,
         time_bars=200, htf_days=7, htf_cap=6, slip=1, tv_fills=False,
         htf=(("15m", "15min"), ("1H", "1h"), ("4H", "4h"), ("1D", "1D")), ndog=True)
TF_SEC = {"15m": 900, "1H": 3600, "4H": 14400, "1D": 86400, "NDOG": 86400}
SESS = (("NY AM", 7 * 60, 10 * 60), ("London", 2 * 60, 5 * 60), ("NY PM", 13 * 60 + 30, 16 * 60), ("Other", 20 * 60, 24 * 60))


def trading_date(idx):
    return (idx + pd.Timedelta(hours=6)).normalize().tz_localize(None)


def resample(one, rule):
    return one.resample(rule, label="left", closed="left").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last"}).dropna(subset=["open"])


def htf_bars(one, name, rule):
    """HTF bars of one market from 1m bars; returns (bars, key per 1m bar-start timestamp -> bucket id)."""
    if name in ("15m", "1H"):
        return resample(one, rule)
    td = trading_date(one.index)
    if name == "1D":
        g = one.groupby(td)
        b = pd.DataFrame({"open": g.open.first(), "high": g.high.max(), "low": g.low.min(), "close": g.close.last(),
                          "t0": g.apply(lambda x: x.index[0])})
        return b.set_index("t0")
    naive = one.index.tz_localize(None)
    base = td - pd.Timedelta(hours=6)                     # 18:00 of the evening before the trading date
    k = ((naive - base) // pd.Timedelta(hours=4)).astype(int)
    key = pd.Series(td.astype("int64") // 10 ** 9 * 10 + k, index=one.index)
    g = one.groupby(key.to_numpy())
    b = pd.DataFrame({"open": g.open.first(), "high": g.high.max(), "low": g.low.min(), "close": g.close.last(),
                      "t0": g.apply(lambda x: x.index[0])})
    return b.set_index("t0").sort_index()


def rma_atr(h, l, c, n=14):
    pc = np.r_[np.nan, c[:-1]]
    tr = np.nanmax(np.c_[h - l, np.abs(h - pc), np.abs(l - pc)], axis=1)
    tr[0] = h[0] - l[0]
    out = np.full(len(tr), np.nan)
    if len(tr) >= n:
        out[n - 1] = tr[:n].mean()
        for i in range(n, len(tr)):
            out[i] = (out[i - 1] * (n - 1) + tr[i]) / n
    return out


def pivots(x, left, right, high=True):
    """ta.pivothigh / pivotlow: value at bar i for the pivot at i - right (strict on the left, not on the right)."""
    n = len(x)
    out = np.full(n, np.nan)
    for i in range(left + right, n):
        p = i - right
        v = x[p]
        l_ = x[p - left:p]
        r_ = x[p + 1:i + 1]
        if high and v > l_.max() and v >= r_.max():
            out[i] = v
        if not high and v < l_.min() and v <= r_.min():
            out[i] = v
    return out


def roll(x, n, fn):
    s = pd.Series(x)
    return (s.rolling(n, min_periods=n).max() if fn == "max" else s.rolling(n, min_periods=n).min()).to_numpy()


def shift(x, k):
    return np.r_[np.full(k, np.nan), x[:-k]] if k else x


class Zone:
    __slots__ = ("bull", "top", "bot", "tf", "sec", "ce", "born", "state", "eligible", "deep", "gapAtr", "rangeAtr",
                 "bodyR", "created", "t1")

    def __init__(s, bull, top, bot, tf, born, gapAtr, rangeAtr=None, bodyR=None, t1=None):
        s.bull, s.top, s.bot, s.tf, s.sec = bull, top, bot, tf, TF_SEC[tf]
        s.ce, s.born, s.state, s.eligible, s.deep = (top + bot) / 2, born, HZ_FRESH, True, 0.0
        s.gapAtr, s.rangeAtr, s.bodyR, s.created, s.t1 = gapAtr, rangeAtr, bodyR, born, t1


class Setup:
    __slots__ = ("bull", "name", "sweeper", "sweepBar", "legBar", "legExt", "sweepExt", "active", "confirmed", "dead",
                 "expired", "used", "detect", "piv", "fail", "ref", "lvl", "lvl_i")

    def __init__(s, bull, name, sweeper, bar, legExt, sweepExt, detect, piv=False, fail=None, lvl=None, lvl_i=None):
        s.bull, s.name, s.sweeper, s.sweepBar, s.legBar = bull, name, sweeper, bar, bar
        s.legExt, s.sweepExt, s.detect, s.piv, s.fail, s.lvl, s.lvl_i = legExt, sweepExt, detect, piv, fail, lvl, lvl_i
        s.active, s.confirmed, s.dead, s.expired, s.used = True, False, False, False, False


class Ref:
    __slots__ = ("name", "high", "kind", "a", "b", "bar", "state", "cur")

    def __init__(s, name, high, kind, a=None, b=None, bar=None, state=3):
        s.name, s.high, s.kind, s.a, s.b, s.bar, s.state, s.cur = name, high, kind, a, b, bar, state, None


def load(tf, one_a=None, one_b=None):
    one_a = pd.read_parquet("data/bars/MNQ_1m.parquet") if one_a is None else one_a
    one_b = pd.read_parquet("data/bars/ES_1m.parquet") if one_b is None else one_b
    rule = f"{tf}min"
    a = resample(one_a, rule)
    b = resample(one_b, rule).reindex(a.index).ffill()
    return one_a, one_b, a, b


def run(one_a, one_b, a, b, tf=5, start=None, end=None, **over):
    p = {**P, **over}
    ts = a.index
    n = len(a)
    O, H, L, C = (a[k].to_numpy() for k in ("open", "high", "low", "close"))
    HB, LB = b.high.to_numpy(), b.low.to_numpy()
    tsec = (ts.tz_convert("UTC").astype("int64") // 10 ** 9).to_numpy()
    tod = (ts.hour * 60 + ts.minute).to_numpy()
    atr = rma_atr(H, L, C)
    pv, sync = p["piv"], min(p["sync"], p["piv"])
    post = max(pv - sync, 1)
    phA, plA = pivots(H, pv, pv, True), pivots(L, pv, pv, False)
    phB, plB = pivots(HB, pv, pv, True), pivots(LB, pv, pv, False)
    winHiA, winLoA = shift(roll(H, 2 * sync + 1, "max"), pv - sync), shift(roll(L, 2 * sync + 1, "min"), pv - sync)
    winHiB, winLoB = shift(roll(HB, 2 * sync + 1, "max"), pv - sync), shift(roll(LB, 2 * sync + 1, "min"), pv - sync)
    postHiA, postLoA = roll(H, post, "max"), roll(L, post, "min")
    postHiB, postLoB = roll(HB, post, "max"), roll(LB, post, "min")

    # ---- daily / weekly references (previous completed bar) and HTF slots ----
    td = trading_date(ts)
    dA = htf_bars(one_a, "1D", None)
    dB = htf_bars(one_b, "1D", None)
    dA.index, dB.index = trading_date(dA.index), trading_date(dB.index)
    posA = np.searchsorted(dA.index.to_numpy(), td.to_numpy()) - 1
    posB = np.searchsorted(dB.index.to_numpy(), td.to_numpy()) - 1
    pdA = np.c_[dA.high.to_numpy()[posA], dA.low.to_numpy()[posA]]
    pdB = np.c_[dB.high.to_numpy()[posB], dB.low.to_numpy()[posB]]
    pdA[posA < 0], pdB[posB < 0] = np.nan, np.nan
    wk = dA.index.to_period("W-SUN")
    gw = dA.groupby(wk)
    wkH, wkL = gw.high.max(), gw.low.min()
    wpos = np.searchsorted(wkH.index.to_timestamp().to_numpy(), td.to_period("W-SUN").to_timestamp().to_numpy()) - 1
    pwH = np.where(wpos >= 0, wkH.to_numpy()[wpos], np.nan)
    pwL = np.where(wpos >= 0, wkL.to_numpy()[wpos], np.nan)
    new_day = np.r_[False, td[1:] != td[:-1]]

    slots = []
    for name, rule in p["htf"]:
        hb = htf_bars(one_a, name, rule)
        hh, hl, hc, ho = (hb[k].to_numpy() for k in ("high", "low", "close", "open"))
        hatr = rma_atr(hh, hl, hc)
        bk = np.searchsorted(hb.index.to_numpy(), ts.to_numpy(), side="right") - 1   # HTF bar containing chart bar
        isnew = np.r_[False, bk[1:] != bk[:-1]]
        slots.append((name, bk, isnew, ho, hh, hl, hc, hatr, hb.index))

    # ---- state ----
    zones = []
    raw = []            # [formBar, dir, top, bot, gapAtr, bodyR, rangeAtr, formT]
    ifvgs = []          # dicts
    setups = []
    refs = [Ref("PDH", True, 0), Ref("PDL", False, 0)]
    tracks = {k: [None, None, None, None] for k in ("HiA", "LoA", "HiB", "LoB")}   # pA, pB, bar, chart index
    pos = None
    trades, cnt = [], collections.Counter()
    slip = p["slip"] * TICK
    t_start = start.value // 10 ** 9 if start is not None else -1
    t_end = end.value // 10 ** 9 if end is not None else 1 << 62
    tsMin, tsMax = 900.0, 86400.0

    def sess_name(i):
        m = tod[i]
        for nm, s0, s1 in SESS:
            if s0 <= m < s1:
                return nm
        return ""

    def select(i):
        """Selection engine at bar i (memoryless): marks each zone selected / not."""
        prox = 0.5 * (atr[i] if not np.isnan(atr[i]) else 0.0)
        lv = [(pdA[i, 0], 1.0), (pdA[i, 1], 1.0), (pwH[i], 1.0), (pwL[i], 1.0),
              ((pdA[i, 0] + pdA[i, 1]) / 2, 0.5), ((pwH[i] + pwL[i]) / 2, 0.5)]
        cands = [z for z in zones if z.eligible]
        sc = {}
        for z in cands:
            base = (1.0, 0.8, 0.55, 0.3)[z.state] if z.state <= HZ_CE50 else 0.0
            fr = base * (1 - 0.5 * z.deep)
            pts = sum(w for v, w in lv if not np.isnan(v) and z.bot - prox <= v <= z.top + prox)
            cf = min(1.0, pts / 2.0)
            parts = [min(1, max(0, x)) for x in ((z.gapAtr / 0.75) if z.gapAtr is not None else None,
                                                  (z.rangeAtr / 2.0) if z.rangeAtr is not None else None,
                                                  z.bodyR) if x is not None and not (isinstance(x, float) and np.isnan(x))]
            ds = sum(parts) / len(parts) if parts else 0.0
            tfs = min(1, max(0, math.log(z.sec / tsMin) / math.log(tsMax / tsMin)))
            sc[id(z)] = (0.35 * fr + 0.2 * cf + 0.2 * ds + 0.25 * tfs, fr, z.sec, ds, z.created)
        comp = {}
        c = 0
        for z in cands:
            if id(z) in comp:
                continue
            comp[id(z)] = c
            stack = [z]
            while stack:
                zj = stack.pop()
                for zk in cands:
                    if id(zk) not in comp and max(zj.bot, zk.bot) < min(zj.top, zk.top):
                        comp[id(zk)] = c
                        stack.append(zk)
            c += 1
        best = {}
        for z in cands:
            k = comp[id(z)]
            if k not in best or sc[id(z)] > sc[id(best[k])]:     # tuple order = score, then the tie chain
                best[k] = z
        return {id(z) for z in best.values()}

    def zone_update(i):
        o, h, l, c = O[i], H[i], L[i], C[i]
        for z in zones:
            if not z.eligible:
                continue
            gh = max(z.top - z.bot, TICK)
            pen = (z.top - l) / gh if z.bull else (h - z.bot) / gh
            z.deep = max(z.deep, min(1.0, pen))
            if z.state >= HZ_FILLED:
                continue
            touched = l <= z.top if z.bull else h >= z.bot
            ce_hit = l <= z.ce if z.bull else h >= z.ce
            filled = l <= z.bot if z.bull else h >= z.top
            if filled:
                z.state = HZ_FILLED
                z.eligible = False
                continue
            if z.state < HZ_DEFENDED:
                if ce_hit and z.state < HZ_CE50:
                    z.state = HZ_CE50
                elif touched and z.state < HZ_CE50:
                    z.state = HZ_PARTIAL if z.bot <= c <= z.top else max(z.state, HZ_TOUCHED)
                if z.state == HZ_CE50 and (c > z.ce if z.bull else c < z.ce):
                    z.state = HZ_DEFENDED
                    z.eligible = False

    def close_pos(i, px, reason):
        nonlocal pos
        sg = pos["sgn"]
        pnl = sg * (px - pos["entry"]) * PV - 2 * COMM
        trades.append({**{k: v for k, v in pos.items() if k != "sgn"}, "exit_time": ts[i], "exit": px,
                       "reason": reason, "pnl": pnl, "R": pnl / (pos["risk"] * PV), "bars": i - pos["bar"]})
        pos = None

    idx = 0
    for i in range(n):
        # ---------- open position: exits inside this bar (broker emulator, before the script runs) ----------
        if pos is not None and i > pos["bar"]:
            sg, st, tp = pos["sgn"], pos["stop"], pos["tp"]
            o = O[i]
            hit_s = (L[i] <= st) if sg > 0 else (H[i] >= st)
            hit_t = (H[i] >= tp) if sg > 0 else (L[i] <= tp)
            gap_s = (o <= st) if sg > 0 else (o >= st)
            gap_t = (o >= tp) if sg > 0 else (o <= tp)
            if hit_s and hit_t and not gap_s and not gap_t:
                if p["tv_fills"]:
                    from orb_engine import _path
                    pts = _path(O[i], H[i], L[i], C[i])
                    k = next(k for k in range(4) if ((pts[k] <= st) if sg > 0 else (pts[k] >= st)) or
                             ((pts[k] >= tp) if sg > 0 else (pts[k] <= tp)))
                    hit_s = (pts[k] <= st) if sg > 0 else (pts[k] >= st)
                hit_t = not hit_s
            if gap_s:
                close_pos(i, o - sg * slip, "SL")
            elif gap_t:
                close_pos(i, o - (0 if p["tv_fills"] else sg * slip), "TP")
            elif hit_s:
                close_pos(i, st - sg * slip, "SL")
            elif hit_t:
                close_pos(i, tp - (0 if p["tv_fills"] else sg * slip), "TP")

        # ---------- A. HTF zones: expire, invalidate, add, NDOG ----------
        t = tsec[i]
        zones = [z for z in zones if t - z.born <= p["htf_days"] * 86400]
        for name, bk, isnew, ho, hh, hl, hc, hatr, hix in slots:
            if isnew[i] and bk[i] >= 1:
                cC = hc[bk[i] - 1]
                zones = [z for z in zones if not (z.tf == name and (cC < z.bot if z.bull else cC > z.top))]
        if p["ndog"]:
            zones = [z for z in zones if not (z.tf == "NDOG" and (C[i] < z.bot if z.bull else C[i] > z.top))]
        for name, bk, isnew, ho, hh, hl, hc, hatr, hix in slots:
            k = bk[i] - 1
            if isnew[i] and k >= 2:
                hC_, lC_, hA_, lA_ = hh[k], hl[k], hh[k - 2], hl[k - 2]
                a2 = hatr[k - 1]
                rng2 = max(hh[k - 1] - hl[k - 1], TICK)
                ra = rng2 / a2 if a2 > 0 else None
                br = abs(hc[k - 1] - ho[k - 1]) / rng2
                made = False
                if lC_ > hA_:
                    zones.append(Zone(True, lC_, hA_, name, t, (lC_ - hA_) / a2 if a2 > 0 else None, ra, br, hix[k - 2])); made = True
                if hC_ < lA_:
                    zones.append(Zone(False, lA_, hC_, name, t, (lA_ - hC_) / a2 if a2 > 0 else None, ra, br, hix[k - 2])); made = True
                if made:
                    same = [z for z in zones if z.tf == name]
                    if len(same) > p["htf_cap"]:
                        drop = {id(z) for z in same[:len(same) - p["htf_cap"]]}
                        zones = [z for z in zones if id(z) not in drop]
        if p["ndog"] and new_day[i] and i > 0 and O[i] != C[i - 1]:
            up = O[i] > C[i - 1]
            top, bot = (O[i], C[i - 1]) if up else (C[i - 1], O[i])
            zones.append(Zone(up, top, bot, "NDOG", t, (top - bot) / atr[i] if atr[i] > 0 else None, t1=ts[i]))
            same = [z for z in zones if z.tf == "NDOG"]
            if len(same) > p["htf_cap"]:
                drop = {id(z) for z in same[:len(same) - p["htf_cap"]]}
                zones = [z for z in zones if id(z) not in drop]

        # ---------- engine ----------
        sig = None
        # C1. PDH / PDL armed on a new previous-day pair
        if i > 0 and not np.isnan(pdA[i, 0]) and not np.isnan(pdB[i, 0]) and \
                (np.isnan(pdA[i - 1, 0]) or np.isnan(pdB[i - 1, 0]) or (pdA[i] != pdA[i - 1]).any() or (pdB[i] != pdB[i - 1]).any()):
            for r, a_, b_ in ((refs[0], pdA[i, 0], pdB[i, 0]), (refs[1], pdA[i, 1], pdB[i, 1])):
                if r.state == 1 and r.cur is not None:
                    r.cur.dead = True
                r.a, r.b, r.bar, r.state, r.cur = a_, b_, idx, 0, None
        idx += 1
        piv_i = idx - pv
        # C2. feed-TF swing references
        def add_ref(high, a_, b_):
            for q in refs:
                if q.kind == 1 and q.high == high and q.state == 0 and abs(q.a - a_) <= TOL and abs(q.b - b_) <= TOL:
                    return
            refs.append(Ref("Swing", high, 1, a_, b_, piv_i, 0))
            kept = 0
            for q in reversed(list(refs)):
                if q.kind == 1 and q.high == high:
                    kept += 1
                    if kept > p["swing_refs"] and q.state != 1:
                        refs.remove(q)
        for high, anchorA, piv, win, pst in ((True, True, phA[i], winHiB[i], postHiB[i]), (False, True, plA[i], winLoB[i], postLoB[i]),
                                             (True, False, phB[i], winHiA[i], postHiA[i]), (False, False, plB[i], winLoA[i], postLoA[i])):
            if not (np.isnan(piv) or np.isnan(win) or np.isnan(pst)) and ((pst <= win + TOL) if high else (pst >= win - TOL)):
                add_ref(high, piv if anchorA else win, win if anchorA else piv)
        # C3. pivot SMT tracks
        for key, high, vA, vB, pA_, pB_ in (("HiA", True, phA[i], winHiB[i], postHiA[i], postHiB[i]),
                                            ("LoA", False, plA[i], winLoB[i], postLoA[i], postLoB[i]),
                                            ("HiB", True, winHiA[i], phB[i], postHiA[i], postHiB[i]),
                                            ("LoB", False, winLoA[i], plB[i], postLoA[i], postLoB[i])):
            if np.isnan(vA) or np.isnan(vB):
                continue
            tr = tracks[key]
            if tr[0] is not None and piv_i > tr[2] and piv_i - tr[2] <= p["piv_gap"]:
                sg = 1 if high else -1
                aB = sg * (vA - tr[0]) > TOL
                bB = sg * (vB - tr[1]) > TOL
                aT = not np.isnan(pA_) and sg * (pA_ - tr[0]) > TOL
                bT = not np.isnan(pB_) and sg * (pB_ - tr[1]) > TOL
                sw = 1 if (aB and not bB and not bT) else 2 if (bB and not aB and not aT) else 0
                if sw:
                    bull = not high
                    dup = any(q.piv and q.bull == bull and not q.dead and not q.expired and abs(q.sweepBar - piv_i) <= pv
                              for q in setups)
                    if not dup:
                        sA = ("LL" if sw == 1 else "HL") if bull else ("HH" if sw == 1 else "LH")
                        sB = ("LL" if sw == 2 else "HL") if bull else ("HH" if sw == 2 else "LH")
                        setups.append(Setup(bull, f"Pivot {sA}/{sB}", sw, piv_i, vA if sw == 1 else vB, vA, t,
                                            piv=True, fail=tr[1] if sw == 1 else tr[0], lvl=tr[0], lvl_i=tr[3]))
            tracks[key] = [vA, vB, piv_i, i - pv]
        # D. sweep SMT state machine
        devBull = devBear = None
        for q in setups:
            if q.active and not q.dead:
                if q.bull:
                    devBull = q
                else:
                    devBear = q
        for r in refs:
            if r.state == 0:
                tkA = (H[i] > r.a + TOL) if r.high else (L[i] < r.a - TOL)
                tkB = (HB[i] > r.b + TOL) if r.high else (LB[i] < r.b - TOL)
            else:
                tkA = tkB = False
            sw = 1 if tkA else 2
            bull = not r.high
            ex = devBull if bull else devBear
            cs = r.cur
            if tkA and tkB:
                r.state = 3
            elif tkA or tkB:
                if ex is not None:
                    r.state = 3
                else:
                    ext = (H[i] if r.high else L[i]) if sw == 1 else (HB[i] if r.high else LB[i])
                    ns = Setup(bull, r.name, sw, idx, ext, H[i] if r.high else L[i], t, lvl=r.a)
                    ns.ref = r
                    setups.append(ns)
                    r.cur, r.state = ns, 1
                    if bull:
                        devBull = ns
                    else:
                        devBear = ns
            elif r.state == 1:
                if cs is None:
                    r.state = 3
                elif cs.dead or cs.expired:
                    cs.active, r.state = False, 3
                else:
                    other = ((HB[i] > r.b + TOL) if r.high else (LB[i] < r.b - TOL)) if cs.sweeper == 1 else \
                            ((H[i] > r.a + TOL) if r.high else (L[i] < r.a - TOL))
                    if other:
                        cs.active, r.state, cs.dead = False, 3, True
                    else:
                        swx = (H[i] if r.high else L[i]) if cs.sweeper == 1 else (HB[i] if r.high else LB[i])
                        if (swx > cs.legExt) if r.high else (swx < cs.legExt):
                            cs.legExt, cs.legBar = swx, idx
                        conf_now = not cs.confirmed and idx - cs.sweepBar >= p["confirm"]
                        if conf_now:
                            cs.confirmed = True
                        if cs.confirmed and not conf_now and idx - cs.legBar >= p["confirm"]:
                            cs.active, r.state = False, 3
        # D2. pivot SMT state machine
        for ps in setups:
            if ps.piv and ps.active and not ps.dead and not ps.expired:
                hi = not ps.bull
                if ps.sweeper == 1:
                    o_t = (HB[i] > ps.fail + TOL) if hi else (LB[i] < ps.fail - TOL)
                else:
                    o_t = (H[i] > ps.fail + TOL) if hi else (L[i] < ps.fail - TOL)
                if o_t:
                    ps.active, ps.dead = False, True
                else:
                    px = (H[i] if hi else L[i]) if ps.sweeper == 1 else (HB[i] if hi else LB[i])
                    if (px > ps.legExt) if hi else (px < ps.legExt):
                        ps.legExt, ps.legBar = px, idx
                    conf_now = not ps.confirmed and idx - ps.sweepBar >= p["confirm"]
                    if conf_now:
                        ps.confirmed = True
                    if ps.confirmed and not conf_now and idx - ps.legBar >= p["confirm"]:
                        ps.active = False
        refs = [q for q in refs if not (q.kind != 0 and q.state != 1 and (q.state == 3 or (q.kind == 1 and idx - q.bar > p["swing_age"])))]

        # B. IFVG engine
        raw = [f for f in raw if idx - f[0] <= p["max_fvg_bars"]]       # older gaps can never invert usefully
        a_ = atr[i] if atr[i] > 0 else TICK
        if i >= 2:
            rng = max(H[i] - L[i], TICK)
            body = abs(C[i] - O[i]) / rng
            if L[i] > H[i - 2]:
                raw.append([idx, 1, L[i], H[i - 2], (L[i] - H[i - 2]) / a_, body, rng / a_, ts[i - 1]])
            if H[i] < L[i - 2]:
                raw.append([idx, -1, L[i - 2], H[i], (L[i - 2] - H[i]) / a_, body, rng / a_, ts[i - 1]])
        c = C[i]
        inv = [f for f in raw if (c > f[2] if f[1] == -1 else c < f[3])]
        if inv:
            pick = max(inv, key=lambda f: (f[7], f[2] - f[3]))
            same = [f for f in inv if f[1] == pick[1]]
            anc = max(same, key=lambda f: (f[7], f[2] - f[3]))
            raw = [f for f in raw if not any(f is g for g in same)]
            if anc[4] >= p["min_gap_atr"] and anc[5] >= p["min_body"] and anc[6] >= p["min_range_atr"]:
                bull = anc[1] == -1
                top, bot = anc[2], anc[3]
                sel = select(i)
                match = [z for z in zones if z.eligible and id(z) in sel and top >= z.bot and bot <= z.top]
                prim, zb = "", None
                if match:
                    zb = max(match, key=lambda z: (z.sec, z.created, -abs(c - z.ce)))
                    prim = zb.tf
                ifvgs.append(dict(bull=bull, top=top, bot=bot, inv=idx, inv_i=i, htf="+".join(sorted({z.tf for z in match})),
                                  prim=prim, used=False, fvg_t=anc[7], sess=sess_name(i),
                                  zone_top=zb.top if zb else None, zone_bot=zb.bot if zb else None,
                                  zone_t=zb.t1 if zb else None))
                cnt["ifvg"] += 1
                cnt["ifvg_in_htf"] += bool(match)
            else:
                cnt["ifvg_rejected"] += 1
        ifvgs = [z for z in ifvgs if not ((c < z["bot"]) if z["bull"] else (c > z["top"])) and idx - z["inv"] <= p["ifvg_age"]]

        # E. setups: sweep extreme, expiry
        keep = []
        for se in setups:
            if not se.dead and not se.expired:
                if not se.used:
                    se.sweepExt = min(se.sweepExt, L[i]) if se.bull else max(se.sweepExt, H[i])
                if idx - se.legBar > p["life"] or (t - se.detect) / 86400.0 > p["max_days"]:
                    se.expired = True
            if not (se.dead or se.expired):
                keep.append(se)
        setups = keep

        # F. pairing
        for sf in reversed(setups):
            if sf.used or not sf.confirmed:
                continue
            for zf in reversed(ifvgs):
                if zf["bull"] == sf.bull and not zf["used"] and zf["inv"] >= sf.sweepBar and zf["inv"] - sf.legBar <= p["pair_bars"] \
                        and zf["htf"] != "":
                    sf.used = zf["used"] = True
                    sig = (sf, zf)
                    break
            if sig:
                break

        # lifecycle after the engine
        zone_update(i)

        # ---------- strategy ----------
        if sig is not None and t_start <= t <= t_end:
            sf, zf = sig
            cnt["signals"] += 1
            if pos is not None:
                cnt["skipped_in_trade"] += 1
            else:
                sg = 1 if sf.bull else -1
                stop = sf.sweepExt - sg * p["sl_ticks"] * TICK
                risk = max(abs(c - stop), TICK)
                stop = c - sg * risk
                pos = dict(side="L" if sf.bull else "S", sgn=sg, bar=i, entry_time=ts[i], signal_close=c,
                           entry=c + sg * slip, stop=stop, tp=c + sg * p["rr"] * risk, risk=risk, smt=sf.name,
                           smt_sweeper="MNQ" if sf.sweeper == 1 else "ES", zone=zf["prim"], zones=zf["htf"],
                           sess=zf["sess"], ifvg_top=zf["top"], ifvg_bot=zf["bot"], ifvg_fvg_t=zf["fvg_t"],
                           ifvg_inv_t=ts[zf["inv_i"]], sweep_bar_t=ts[max(i - (idx - sf.sweepBar), 0)],
                           zone_top=zf["zone_top"], zone_bot=zf["zone_bot"], zone_t=zf["zone_t"], smt_level=sf.lvl,
                           smt_level_t=ts[sf.lvl_i] if sf.lvl_i is not None else None, sweep_ext=sf.sweepExt)
        if pos is not None and i - pos["bar"] > p["time_bars"]:
            close_pos(i, C[i] - pos["sgn"] * slip, "time")
    if pos is not None:
        close_pos(n - 1, C[n - 1] - pos["sgn"] * slip, "open")
    return pd.DataFrame(trades), cnt


def load_tv(path="data/tradingview/RunI_MNQ_2025-2026.csv"):
    r = pd.read_csv(path, encoding="utf-8-sig")
    tr = collections.defaultdict(dict)
    for _, x in r.iterrows():
        t = pd.Timestamp(x["Date and time"]).tz_localize("America/Los_Angeles").tz_convert(TZ)
        d = tr[int(x["Trade number"])]
        if x["Type"].startswith("Entry"):
            parts = x["Signal"].split("|")
            tag = dict(q.split(":", 1) for q in parts if ":" in q)
            d.update(side=parts[0], entry_time=t, entry=float(x["Price USD"]), pnl=float(x["Net PnL USD"]),
                     zone=tag.get("P", ""), smt=tag.get("smt", "").rstrip("+~"), sess=tag.get("sess", ""))
        else:
            d.update(exit_time=t, exit=float(x["Price USD"]), reason=x["Signal"])
    return pd.DataFrame.from_dict(tr, orient="index").sort_index()


def summary(tr, label):
    from orb_engine import stats
    s = stats(tr)
    print(f"{label}: " + "  ".join(f"{k} {v}" for k, v in s.items()))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--tf", type=int, default=5)
    ap.add_argument("--start", default="2019-06-01")
    ap.add_argument("--end", default="2026-09-22")
    ap.add_argument("--tv-fills", action="store_true")
    ap.add_argument("--calibrate", action="store_true")
    ap.add_argument("--out")
    ap.add_argument("--ndog", default="on")
    ap.add_argument("--daily", default="on")
    a = ap.parse_args()
    sys.path.insert(0, "tools")
    one_a, one_b, A, B = load(a.tf)
    kw = dict(tv_fills=a.tv_fills)
    if a.calibrate:
        tv = load_tv()
        s0, s1 = pd.Timestamp("2025-09-23", tz=TZ), pd.Timestamp("2026-09-22", tz=TZ)
        m = (one_a.index >= s0 - pd.Timedelta(days=1)) & (one_a.index < s1 + pd.Timedelta(days=1))
        tr, cnt = run(one_a, one_b, A, B, tf=a.tf, start=s0, end=s1, **kw)
        tr = tr[(tr.entry_time >= s0) & (tr.entry_time < s1)]
        print(dict(cnt))
        summary(tv, "TradingView Run I")
        summary(tr, "engine, same window")
        mt = tv.merge(tr, on=["entry_time", "side"], how="outer", suffixes=("_tv", "_py"), indicator=True)
        both = mt[mt._merge == "both"]
        print(f"entries matched (same bar, same side): {len(both)} of TV {len(tv)} / engine {len(tr)}")
        if len(both):
            print(f"  on matched trades: same exit reason {int((both.reason_tv.str[:2].str.upper() == both.reason_py.str[:2].str.upper()).sum())}, "
                  f"TV net {both.pnl_tv.sum():+,.0f} vs engine {both.pnl_py.sum():+,.0f}; "
                  f"entry price diff max {abs(both.entry_tv - both.entry_py).max():.2f}")
            print(f"  zone tag agrees {int((both.zone_tv == both.zone_py).sum())}, SMT tag agrees {int((both.smt_tv == both.smt_py).sum())}")
        if a.out:
            mt.to_csv(a.out, index=False)
    else:
        tr, cnt = run(one_a, one_b, A, B, tf=a.tf, start=pd.Timestamp(a.start, tz=TZ), end=pd.Timestamp(a.end, tz=TZ), **kw)
        print(dict(cnt))
        from orb_engine import report
        report(tr, groups=("side", "reason", "zone", "sess"))
        if a.out:
            tr.to_csv(a.out, index=False)
