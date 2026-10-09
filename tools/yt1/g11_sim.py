#!/usr/bin/env python3
"""G11 simulator - the break-and-retest family of YT8_SPEC.md, Part 1: every (L, K, D, N, S, X) cell on every day.

    python3 tools/yt1/g11_sim.py --phase is|full [--procs 2]     writes data/studies/yt1/<phase>/G11_trades.parquet
                                                                 (and G11_setups.parquet: one row per day x L x K)
    python3 tools/yt1/g11_sim.py --phase is --time-sample 24     times 24 evenly spaced days, writes nothing

The set-up functions below (prep, day_ix, level, find_break, fvg_flag, filter_flags, arm_bar, entry_plan, stop_ticks,
first_order, reentry_order) are the ONE place where a level, a break, an entry, a stop, a target or a re-entry is
defined; sim_day() here and s_G11.orders() both call them. Every fill, exit and P&L is core.simulate's.

All prices are handled as integer ticks (price / 0.25) until an order is written, so no comparison or rounding
depends on floating point. Long side written; shorts mirror. Times are New York wall-clock (ctx.span).

The day        09:30 bar .. the last 1-minute bar that CLOSES by the cut-off (12:00 here: the 11:59 bar). "No entry
               after the cut-off" = the entry bar (the bar at whose close a close entry is made, or on which a limit
               fills) must close at or before the cut-off, so a resting limit expires with the 11:59 (10:59) bar.
L  level       or5 / or15 / or30: highest high / lowest low of the 1-minute bars 09:30-09:34 / -09:44 / -09:59;
               pd: days.pdh / days.pdl (previous cash session 09:30-15:59). W = high - low for or*, the 09:30-09:44
               width for pd (known at the close of the last bar of 09:30-09:44).
K  break       the first clock-aligned 1- / 5- / 15-minute candle whose bucket opens at or after the level is complete
               (09:35 / 09:45 / 10:00; pd: 09:30) and whose close is strictly beyond the level (above the high: long;
               below the low: short). Decision bar b = the candle's last 1-minute bar. One break a day, either side.
D  fvg         ind.fvg_bull / fvg_bear true on a 1-minute bar k whose three bars k-2, k-1, k all lie among the
               1-minute bars of the breaking candle and of the two K-type candles before it. False: no trade.
   ext         e = the first bar at whose close W is known and a 1-minute high since the level was complete (pd: since
               09:30) is >= level + 0.7 W. Arm bar a = max(b, e); without ext a = b. Limits rest from a + 1, a touch
               counts from a + 1.
N  edge        buy limit at the broken level (pd: placed at max(a, the bar at whose close W is known), its stop needs W)
   conf        touch = first bar after a with low <= level; confirmation = first bar c >= touch with close > high of
               bar c - 1; market at close[c]
   zone        demand candle = the last candle with close < open among the 12 candles that closed before b (1-minute
               bars for c1, 5-minute bars for c5 / c15); buy limit at its high
   mid         buy limit at the range midline (a half-tick midline: the tick below for a long, above for a short)
   poc         buy limit at the opening range's point of control
               A limit is placed only if it is strictly below the breaking candle's close.
S  near        conf: lowest low touch..c - 1 tick; zone: demand low - 1 tick; poc: value-area low - 1 tick;
               edge: level - 0.25 W; mid: midline - 0.25 W (off-grid prices: the next tick away from the entry)
   mid         1 tick below the midline (half-tick midline: the tick below it, then 1 tick)
   far         range low - 2 ticks
               An order whose stop is not at least 2 ticks beyond its entry price is not placed (no trade that day).
X  target      core.tick_round(entry + k x |entry - stop|), entry = the limit price or the confirmation close;
               hold: none.  A resting limit is cancelled when the stop price trades (cancel_lo / cancel_hi).
E  re-entry    after a first trade that ended 'SL' on a bar closing by the cut-off: the first K-type candle whose last
               1-minute bar is after the stop-out bar and by the cut-off, and whose close is beyond the level, is
               entered at its close with the first trade's stop and target PRICES, unless that close is less than 2
               ticks beyond the stop or at / beyond the target (then there is no re-entry). Once.
F  flags       at b: f_ema200 close[b] > EMA(200) of 5-minute closes; f_ema921 EMA(9) > EMA(21) (the last 5-minute bar
               complete at b, continuous 24-hour series, ind.ema); f_vwap close[b] > ind.session_vwap anchored at the
               09:30 bar (sum of (h + l + c) / 3 x volume over sum of volume, 1-minute bars 09:30 .. b).
Readings (R) are listed in notes/G11.md.
"""
import argparse, math, os, pathlib, sys, time
import numpy as np
import pandas as pd
sys.path.insert(0, str(pathlib.Path(__file__).parent))
import core
import ind

T = core.TICK
LS = ("or5", "or15", "or30", "pd")
KS = ("c1", "c5", "c15")
DS = ("none", "fvg", "ext")
NS = ("edge", "conf", "zone", "mid", "poc")
SS = ("near", "mid", "far")
XS = ("1.5R", "2R", "3R", "hold")
OR_MIN = {"or5": 5, "or15": 15, "or30": 30}
K_MIN = {"c1": 1, "c5": 5, "c15": 15}
XK = {"1.5R": 1.5, "2R": 2.0, "3R": 3.0, "hold": None}
OPEN = 570                                   # 09:30
CUT = {"11": 660, "12": 720}                 # the cut-offs, minutes after midnight
MARKS = (570, 575, 585, 600, 660, 720)       # the clock minutes a day is cut at
ZONE_LOOKBACK = 12
EXT_NUM, EXT_DEN = 7, 10                     # 0.7 x W
VA_NUM, VA_DEN = 7, 10                       # value area = 70 % of the volume
MIN_STOP_TICKS = 2
REASONS = ("SL", "TP", "time")


def exists(L, N, S):
    """mid / poc entries and mid / far stops exist only for the opening-range levels; mid entry x mid stop does not."""
    if L == "pd":
        return N in ("edge", "conf", "zone") and S == "near"
    return not (N == "mid" and S == "mid")


def triples():
    """The 45 valid (L, N, S)."""
    return [(L, N, S) for L in LS for N in NS for S in SS if exists(L, N, S)]


def cells():
    """The 1,620 valid (L, K, D, N, S, X) in the grid's order."""
    return [(L, K, D, N, S, X) for L in LS for K in KS for D in DS for N in NS for S in SS for X in XS
            if exists(L, N, S)]


# ------------------------------------------------------------------ per-context preparation
class Prep:
    """Tick-integer copies of the bars, the K-candle tables, the 5-minute EMAs, the 09:30 VWAP and the 1-minute
    fair-value-gap flags. Everything here is causal bar by bar (value at k uses bars <= k)."""

    def __init__(self, ctx):
        self.ctx = ctx
        for x in (ctx.O, ctx.H, ctx.L, ctx.C):
            assert (x * 4 == np.round(x * 4)).all(), "prices off the 0.25 tick grid"
        self.Ot, self.Ht, self.Lt, self.Ct = (np.round(x * 4).astype(np.int64) for x in (ctx.O, ctx.H, ctx.L, ctx.C))
        assert (ctx.V == np.round(ctx.V)).all(), "volume is not whole contracts"
        self.fvg_up = ind.fvg_bull(ctx.H, ctx.L)
        self.fvg_dn = ind.fvg_bear(ctx.H, ctx.L)
        self.tab = {}
        for m in (5, 15):
            b = ctx.bars(m)
            self.tab[m] = dict(
                o=np.round(b.open.to_numpy(float) * 4).astype(np.int64),
                h=np.round(b.high.to_numpy(float) * 4).astype(np.int64),
                l=np.round(b.low.to_numpy(float) * 4).astype(np.int64),
                c=np.round(b.close.to_numpy(float) * 4).astype(np.int64),
                i_first=b.i_first.to_numpy(np.int64), i_last=b.i_last.to_numpy(np.int64),
                tod=(b.index.hour * 60 + b.index.minute).to_numpy())
        c5 = ctx.bars(5).close.to_numpy(float)
        self.ema200, self.ema9, self.ema21 = ind.ema(c5, 200), ind.ema(c5, 9), ind.ema(c5, 21)
        self.vwap, _ = ind.session_vwap(ctx.H, ctx.L, ctx.C, ctx.V, ctx.tod == OPEN)
        self._ix = {}

    def ix(self, d):
        """{minute: position of the first 1-minute bar at or after that New York clock minute on calendar date d}."""
        if d not in self._ix:
            self._ix[d] = {m: self.ctx.span(d, m, m)[0] for m in MARKS}
        return self._ix[d]


def prep(ctx):
    c = ctx.__dict__
    if "_g11_prep" not in c:
        c["_g11_prep"] = Prep(ctx)
    return c["_g11_prep"]


# ------------------------------------------------------------------ levels
def profile(P, s_lo, s_hi):
    """Volume profile of the 1-minute bars s_lo .. s_hi - 1: each bar's volume spread evenly over its ticks from low
    to high inclusive (exact: integers over a common denominator). Returns (poc, val, vah, base, prof, den):
    poc = the tick with the most volume (the lowest on ties); value area = grown from the poc one tick at a time
    toward the side whose next tick holds more volume (equal: the lower tick; a side that has reached the end of the
    profile is not available) until it holds at least 70 % of the volume; prof[q] / den = volume at tick base + q."""
    lo = [int(x) for x in P.Lt[s_lo:s_hi]]
    hi = [int(x) for x in P.Ht[s_lo:s_hi]]
    vol = [int(x) for x in P.ctx.V[s_lo:s_hi]]
    nt = [h - l + 1 for l, h in zip(lo, hi)]
    den = math.lcm(*nt)
    base, top = min(lo), max(hi)
    diff = [0] * (top - base + 2)
    for l, h, v, n in zip(lo, hi, vol, nt):
        w = v * (den // n)
        diff[l - base] += w
        diff[h - base + 1] -= w
    prof, run = [], 0
    for x in diff[:-1]:
        run += x
        prof.append(run)
    best = max(prof)
    q = prof.index(best)                                   # the lowest tick on ties
    total = sum(prof)
    assert total == den * sum(vol)
    a = z = q
    acc = prof[q]
    while acc * VA_DEN < VA_NUM * total:
        dn_ok, up_ok = a > 0, z < len(prof) - 1
        if dn_ok and (not up_ok or prof[a - 1] >= prof[z + 1]):
            a -= 1
            acc += prof[a]
        else:
            z += 1
            acc += prof[z]
    return base + q, base + a, base + z, base, prof, den


class Level:
    """One level of one day, in ticks. hi / lo = the level's two sides; W = the width used by `ext` and the 0.25 W
    stops; w_i = the 1-minute bar at whose close W is known; first_tod = the first clock minute a break candle may
    open at; i0 = the first 1-minute bar at or after it; watch0 = the first bar whose high / low counts toward the
    0.7 W excursion; mid2 = hi + lo (the midline is mid2 / 2 ticks); poc / val / vah: the opening range's profile."""
    __slots__ = ("name", "hi", "lo", "W", "w_i", "first_tod", "i0", "watch0", "mid2", "s_lo", "s_hi", "_P", "_prof")

    @property
    def prof(self):
        if self._prof is None:
            self._prof = profile(self._P, self.s_lo, self.s_hi)
        return self._prof

    @property
    def poc(self):
        return self.prof[0]

    @property
    def val(self):
        return self.prof[1]

    @property
    def vah(self):
        return self.prof[2]


def level(P, d, day, L):
    """The level L of cash day d (a row of ctx.days), or None when it does not exist (no bar in its range; no
    previous session)."""
    ix = P.ix(d)
    lv = Level()
    lv.name, lv._P, lv._prof = L, P, None
    if L == "pd":
        if not (day.pdh == day.pdh and day.pdl == day.pdl):
            return None
        s_lo, s_hi = ix[OPEN], ix[OPEN + 15]
        if s_hi <= s_lo:
            return None
        lv.hi, lv.lo = int(round(day.pdh * 4)), int(round(day.pdl * 4))
        lv.W = int(P.Ht[s_lo:s_hi].max() - P.Lt[s_lo:s_hi].min())
        lv.first_tod, lv.i0, lv.watch0 = OPEN, s_lo, s_lo
    else:
        m = OR_MIN[L]
        s_lo, s_hi = ix[OPEN], ix[OPEN + m]
        if s_hi <= s_lo:
            return None
        lv.hi, lv.lo = int(P.Ht[s_lo:s_hi].max()), int(P.Lt[s_lo:s_hi].min())
        lv.W = lv.hi - lv.lo
        lv.first_tod, lv.i0, lv.watch0 = OPEN + m, s_hi, s_hi
    lv.w_i = s_hi - 1
    lv.s_lo, lv.s_hi = s_lo, s_hi
    lv.mid2 = lv.hi + lv.lo
    return lv


# ------------------------------------------------------------------ the break
class Break:
    __slots__ = ("b", "side", "row", "close", "K")


def find_break(P, lv, K, cut):
    """The day's set-up: the first K candle whose bucket opens at or after lv.first_tod, whose last 1-minute bar is
    at or before `cut`, and whose close is strictly beyond the level. None when there is none."""
    if lv.i0 > cut:
        return None
    if K == "c1":
        c = P.Ct[lv.i0:cut + 1]
        r0 = lv.i0
        il = None
    else:
        tb = P.tab[K_MIN[K]]
        r0 = int(np.searchsorted(tb["i_first"], lv.i0, "left"))
        r1 = int(np.searchsorted(tb["i_last"], cut, "right"))
        if r1 <= r0:
            return None
        assert tb["tod"][r0] >= lv.first_tod, "a break candle that opens before the level is complete"
        c = tb["c"][r0:r1]
        il = tb["i_last"]
    hit = np.flatnonzero((c > lv.hi) | (c < lv.lo))
    if not len(hit):
        return None
    q = int(hit[0])
    br = Break()
    br.K, br.row = K, r0 + q
    br.b = int(br.row if il is None else il[br.row])
    br.close = int(c[q])
    br.side = 1 if br.close > lv.hi else -1
    assert br.close == P.Ct[br.b]
    return br


def fvg_flag(P, br):
    """D fvg: a 1-minute fair value gap in the break's direction whose three bars are all among the 1-minute bars of
    the breaking candle and of the two K-type candles before it."""
    if br.K == "c1":
        s0 = br.b - 2
    else:
        if br.row < 2:
            return False
        s0 = int(P.tab[K_MIN[br.K]]["i_first"][br.row - 2])
    if s0 < 0:
        return False
    f = P.fvg_up if br.side > 0 else P.fvg_dn
    return bool(f[s0 + 2:br.b + 1].any())


def filter_flags(P, br):
    """(f_ema200, f_vwap, f_ema921) at the breaking candle's close, each True when it agrees with the break's side."""
    ctx = P.ctx
    j5 = int(np.searchsorted(P.tab[5]["i_last"], br.b, "right")) - 1      # last 5-minute bar complete at b
    c = ctx.C[br.b]
    s = br.side
    if j5 < 0:
        e200 = e9 = e21 = np.nan
    else:
        e200, e9, e21 = P.ema200[j5], P.ema9[j5], P.ema21[j5]
    vw = P.vwap[br.b]
    return (bool(s * (c - e200) > 0), bool(s * (c - vw) > 0), bool(s * (e9 - e21) > 0))


def ext_bar(P, lv, side, cut):
    """D ext: the first 1-minute bar e <= cut at whose close W is known and price has traded 0.7 W beyond the level
    on a bar from lv.watch0 on. None when there is none."""
    if side > 0:
        thr = EXT_DEN * lv.hi + EXT_NUM * lv.W
        def reached(lo, hi):
            return np.flatnonzero(P.Ht[lo:hi] * EXT_DEN >= thr)
    else:
        thr = EXT_DEN * lv.lo - EXT_NUM * lv.W
        def reached(lo, hi):
            return np.flatnonzero(P.Lt[lo:hi] * EXT_DEN <= thr)
    if lv.w_i >= lv.watch0 and lv.w_i <= cut and len(reached(lv.watch0, lv.w_i + 1)):
        return int(lv.w_i)
    lo = max(lv.watch0, lv.w_i + 1)
    if lo > cut:
        return None
    h = reached(lo, cut + 1)
    return int(lo + h[0]) if len(h) else None


def arm_bar(P, lv, br, D, cut):
    """The bar at whose close the day's order may first be placed: b, or with D ext max(b, e). None: never."""
    if D != "ext":
        return br.b
    e = ext_bar(P, lv, br.side, cut)
    return None if e is None else max(br.b, e)


# ------------------------------------------------------------------ entries, stops, orders
def zone_candle(P, br):
    """N zone: (high, low, row, minutes) of the last down-close candle (up-close for a short) among the 12 candles
    that closed before the breaking candle's close: 1-minute bars for c1, 5-minute bars otherwise. None: no candle."""
    if br.K == "c1":
        o, h, l, c, q, m = P.Ot, P.Ht, P.Lt, P.Ct, br.b - 1, 1
    else:
        tb = P.tab[5]
        o, h, l, c, m = tb["o"], tb["h"], tb["l"], tb["c"], 5
        q = int(np.searchsorted(tb["i_last"], br.b, "left")) - 1
    for r in range(q, max(q - ZONE_LOOKBACK, -1), -1):
        if (c[r] < o[r]) if br.side > 0 else (c[r] > o[r]):
            return int(h[r]), int(l[r]), r, m
    return None


def entry_plan(P, lv, br, N, a, cut):
    """The day's entry for style N once the order may be placed at the close of bar a. Returns a dict
        kind 'limit': i (decision bar: the limit rests from i + 1), px (limit price, ticks)
        kind 'close': i (the confirmation bar), px (its close, ticks), touch, pull (extreme of touch .. i, ticks)
    plus zone_hi / zone_lo for N zone; or None when there is no order that day."""
    s = br.side
    level_px = lv.hi if s > 0 else lv.lo
    if N == "conf":
        if a + 1 > cut:
            return None
        t = np.flatnonzero(P.Lt[a + 1:cut + 1] <= level_px) if s > 0 else np.flatnonzero(P.Ht[a + 1:cut + 1] >= level_px)
        if not len(t):
            return None
        t = a + 1 + int(t[0])
        cf = (P.Ct[t:cut + 1] > P.Ht[t - 1:cut]) if s > 0 else (P.Ct[t:cut + 1] < P.Lt[t - 1:cut])
        cf = np.flatnonzero(cf)
        if not len(cf):
            return None
        c = t + int(cf[0])
        pull = int(P.Lt[t:c + 1].min()) if s > 0 else int(P.Ht[t:c + 1].max())
        return dict(kind="close", i=c, px=int(P.Ct[c]), touch=t, pull=pull)
    plan = dict(kind="limit", i=a)
    if N == "edge":
        px = level_px
        if lv.name == "pd":
            plan["i"] = max(a, lv.w_i)                     # its stop (0.25 W) is not known before
    elif N == "mid":
        px = lv.mid2 // 2 if s > 0 else -((-lv.mid2) // 2)
    elif N == "poc":
        px = lv.poc
    elif N == "zone":
        z = zone_candle(P, br)
        if z is None:
            return None
        plan["zone_hi"], plan["zone_lo"], plan["zone_row"], plan["zone_min"] = z
        px = z[0] if s > 0 else z[1]
    else:
        raise ValueError(N)
    if s * (br.close - px) <= 0:
        return None                                        # a limit is placed only below the breaking candle's close
    if plan["i"] >= cut:
        return None                                        # it could not fill on a bar closing by the cut-off
    plan["px"] = int(px)
    return plan


def stop_ticks(lv, side, N, S, plan):
    """The stop price in ticks for entry style N and stop rule S."""
    if S == "far":
        return lv.lo - 2 if side > 0 else lv.hi + 2
    if S == "mid":
        return lv.mid2 // 2 - 1 if side > 0 else -((-lv.mid2) // 2) + 1
    if N == "conf":
        return plan["pull"] - side
    if N == "zone":
        return plan["zone_lo"] - 1 if side > 0 else plan["zone_hi"] + 1
    if N == "poc":
        return lv.val - 1 if side > 0 else lv.vah + 1
    if N == "edge":                                        # level -/+ 0.25 W, in quarter ticks, rounded away
        return (4 * lv.hi - lv.W) // 4 if side > 0 else -((-(4 * lv.lo + lv.W)) // 4)
    if N == "mid":                                         # midline -/+ 0.25 W
        return (2 * lv.mid2 - lv.W) // 4 if side > 0 else -((-(2 * lv.mid2 + lv.W)) // 4)
    raise ValueError((N, S))


def target_price(entry, stop, side, X):
    k = XK[X]
    return None if k is None else float(core.tick_round(entry + side * k * abs(entry - stop)))


def first_order(side, plan, stop_t, X, cut, i_end):
    """core.simulate keyword arguments of the day's first order, or None when the stop is not at least 2 ticks
    beyond the entry price (the order is not placed)."""
    if side * (plan["px"] - stop_t) < MIN_STOP_TICKS:
        return None
    entry, stop = plan["px"] * T, stop_t * T
    o = dict(i=int(plan["i"]), side=int(side), stop=float(stop), target=target_price(entry, stop, side, X),
             exit_i=int(i_end))
    if plan["kind"] == "close":
        o["etype"] = "close"
    else:
        o.update(etype="limit", price=float(entry), expire=int(cut))
        o["cancel_lo" if side > 0 else "cancel_hi"] = float(stop)
    return o


def reentry_bar(P, lv, K, side, k1, cut):
    """The re-entry candle after a stop-out on bar k1: the last 1-minute bar of the first K-type candle that ends
    after k1 and at or before `cut` and closes beyond the level. None when there is none."""
    level_px = lv.hi if side > 0 else lv.lo
    if k1 + 1 > cut:
        return None
    if K == "c1":
        c = P.Ct[k1 + 1:cut + 1]
        h = np.flatnonzero(c > level_px) if side > 0 else np.flatnonzero(c < level_px)
        return k1 + 1 + int(h[0]) if len(h) else None
    tb = P.tab[K_MIN[K]]
    r0 = int(np.searchsorted(tb["i_last"], k1, "right"))
    r1 = int(np.searchsorted(tb["i_last"], cut, "right"))
    if r1 <= r0:
        return None
    c = tb["c"][r0:r1]
    h = np.flatnonzero(c > level_px) if side > 0 else np.flatnonzero(c < level_px)
    return int(tb["i_last"][r0 + int(h[0])]) if len(h) else None


def reentry_order(P, lv, K, side, t1, o1, cut):
    """core.simulate keyword arguments of the re-entry after first trade t1 (a core.simulate result) of order o1, or
    None: the first trade was not stopped on a bar closing by the cut-off; no candle closes back beyond the level by
    the cut-off; or that close is less than 2 ticks beyond the original stop or at / beyond the original target."""
    if t1 is None or t1["reason"] != "SL" or t1["k"] > cut:
        return None
    i2 = reentry_bar(P, lv, K, side, int(t1["k"]), cut)
    if i2 is None:
        return None
    px = int(P.Ct[i2])
    stop_t = int(round(o1["stop"] * 4))
    if side * (px - stop_t) < MIN_STOP_TICKS:
        return None
    if o1["target"] is not None and side * (int(round(o1["target"] * 4)) - px) <= 0:
        return None
    return dict(i=int(i2), side=int(side), etype="close", stop=o1["stop"], target=o1["target"], exit_i=o1["exit_i"])


def day_frame(P, d, day, cut_tod):
    """(cut, i_end): the last 1-minute bar that closes by the cut-off, and the flat bar. cut < the 09:30 bar: no day."""
    ix = P.ix(d)
    return ix[cut_tod] - 1, int(day.i_end)


def traded_days(ctx):
    """The cash days core.run_orders(..., skip_roll=2) trades: not a roll day or the day after, with a daily ATR."""
    return [d for d in ctx.days.index if d not in ctx.roll2_dates and d not in ctx.noatr_dates]


# ------------------------------------------------------------------ one day, every cell
ROW = np.dtype([("day", "i4"), ("side", "i1"), ("L", "i1"), ("K", "i1"), ("D", "i1"), ("N", "i1"), ("S", "i1"),
                ("X", "i1"), ("which", "i1"), ("i", "i4"), ("j", "i4"), ("k", "i4"), ("b", "i4"), ("entry_px", "f8"),
                ("entry", "f8"), ("stop", "f8"), ("target", "f8"), ("exit", "f8"), ("reason", "i1"), ("pnl", "f8"),
                ("R", "f8"), ("risk_pts", "f8"), ("f_ema200", "?"), ("f_vwap", "?"), ("f_ema921", "?")])
SET = np.dtype([("day", "i4"), ("L", "i1"), ("K", "i1"), ("side", "i1"), ("b", "i4"), ("close", "f8"),
                ("level_hi", "f8"), ("level_lo", "f8"), ("W", "f8"), ("d_fvg", "?"), ("ext_i", "i4"),
                ("f_ema200", "?"), ("f_vwap", "?"), ("f_ema921", "?"), ("poc", "f8"), ("val", "f8"), ("vah", "f8")])


def sim_day(P, d, day, cut_tod=720, only=None):
    """Every valid (L, K, D none / ext, N, S, X) on cash day d under a cut-off at cut_tod: the first trade and, when
    it was stopped by the cut-off, the re-entry. Returns (trade rows, set-up rows) as lists of tuples in ROW / SET
    order. D fvg is not simulated: it is the D none trade on the days whose fvg flag is true (added by run()).
    only = an optional set of (L, K, D, N, S, X) to restrict to."""
    ctx = P.ctx
    cut, i_end = day_frame(P, d, day, cut_tod)
    dn = int(np.datetime64(d, "D").astype(np.int64))
    rows, sets = [], []
    for li, L in enumerate(LS):
        lv = level(P, d, day, L)
        for ki, K in enumerate(KS):
            br = find_break(P, lv, K, cut) if lv is not None else None
            if br is None:
                sets.append((dn, li, ki, 0, -1, np.nan, lv.hi * T if lv else np.nan, lv.lo * T if lv else np.nan,
                             lv.W * T if lv else np.nan, False, -1, False, False, False, np.nan, np.nan, np.nan))
                continue
            fl = filter_flags(P, br)
            fv = fvg_flag(P, br)
            e = ext_bar(P, lv, br.side, cut)
            pv = (lv.poc * T, lv.val * T, lv.vah * T) if L != "pd" else (np.nan, np.nan, np.nan)
            sets.append((dn, li, ki, br.side, br.b, br.close * T, lv.hi * T, lv.lo * T, lv.W * T, fv,
                         -1 if e is None else e, fl[0], fl[1], fl[2]) + pv)
            for D in ("none", "ext"):
                di = DS.index(D)
                a = arm_bar(P, lv, br, D, cut)
                if a is None:
                    continue
                for ni, N in enumerate(NS):
                    if not exists(L, N, "near"):
                        continue
                    plan = entry_plan(P, lv, br, N, a, cut)
                    if plan is None:
                        continue
                    for si, S in enumerate(SS):
                        if not exists(L, N, S):
                            continue
                        st = stop_ticks(lv, br.side, N, S, plan)
                        for xi, X in enumerate(XS):
                            if only is not None and (L, K, D, N, S, X) not in only:
                                continue
                            o = first_order(br.side, plan, st, X, cut, i_end)
                            if o is None:
                                break                      # the stop test does not depend on the target
                            t1 = core.simulate(ctx, **o)
                            if t1 is None:
                                if only is None:
                                    break                  # whether and where an order fills does not depend on the target
                                continue
                            key = (dn, br.side, li, ki, di, ni, si, xi)
                            tg = np.nan if o["target"] is None else o["target"]
                            rows.append(key + (1, o["i"], t1["j"], t1["k"], br.b, plan["px"] * T, t1["entry"], o["stop"],
                                               tg, t1["exit"], REASONS.index(t1["reason"]), t1["pnl"], t1["R"],
                                               t1["risk_pts"]) + fl)
                            o2 = reentry_order(P, lv, K, br.side, t1, o, cut)
                            if o2 is None:
                                continue
                            t2 = core.simulate(ctx, **o2)
                            if t2 is None:
                                continue
                            rows.append(key + (2, o2["i"], t2["j"], t2["k"], br.b, ctx.C[o2["i"]], t2["entry"],
                                               o2["stop"], tg, t2["exit"], REASONS.index(t2["reason"]), t2["pnl"],
                                               t2["R"], t2["risk_pts"]) + fl)
    return rows, sets


def _sim_days(P, days, cut_tod=720, only=None):
    R, S = [], []
    D = P.ctx.days
    for d in days:
        r, s = sim_day(P, d, D.loc[d], cut_tod, only)
        if r:
            R.append(np.array(r, dtype=ROW))
        S.append(np.array(s, dtype=SET))
    return (np.concatenate(R) if R else np.zeros(0, ROW)), (np.concatenate(S) if S else np.zeros(0, SET))


_FORK = {}


def _worker(q):
    P, chunks, cut_tod = _FORK["a"]
    os.nice(5)
    return _sim_days(P, chunks[q], cut_tod)


def simulate_days(ctx, days, cut_tod=720, procs=1):
    """ROW / SET arrays for the given cash days (structured numpy arrays, rows ordered by day, then cell)."""
    P = prep(ctx)
    days = list(days)
    if procs > 1 and len(days) > 8:
        import multiprocessing as mp
        nch = 8 * procs
        chunks = [days[q::nch] for q in range(nch)]            # interleaved: every chunk spans the whole period
        _FORK["a"] = (P, chunks, cut_tod)
        with mp.get_context("fork").Pool(procs) as pool:
            parts = pool.map(_worker, range(nch), chunksize=1)
        _FORK.clear()
        rows = np.concatenate([p[0] for p in parts])
        sets = np.concatenate([p[1] for p in parts])
    else:
        rows, sets = _sim_days(P, days, cut_tod)
    return rows, sets


def add_fvg(rows, sets):
    """Adds the D fvg cells: the D none trades of the (day, L, K) whose fvg flag is true."""
    ok = sets[sets["d_fvg"]]
    key = set(zip(ok["day"].tolist(), ok["L"].tolist(), ok["K"].tolist()))
    none = rows[rows["D"] == DS.index("none")]
    m = np.fromiter(((a, b, c) in key for a, b, c in zip(none["day"].tolist(), none["L"].tolist(), none["K"].tolist())),
                    bool, len(none))
    f = none[m].copy()
    f["D"] = DS.index("fvg")
    return np.concatenate([rows, f])


def frame(ctx, rows):
    """The trade file: one row per trade, ordered by cell (grid order), day, which."""
    rows = rows[np.lexsort((rows["which"], rows["day"], rows["X"], rows["S"], rows["N"], rows["D"], rows["K"], rows["L"]))]
    ts, tod = ctx.ts, ctx.tod
    df = pd.DataFrame({
        "day": rows["day"].astype("datetime64[D]").astype("datetime64[ns]"),
        "side": rows["side"],
        "L": pd.Categorical.from_codes(rows["L"], LS), "K": pd.Categorical.from_codes(rows["K"], KS),
        "D": pd.Categorical.from_codes(rows["D"], DS), "N": pd.Categorical.from_codes(rows["N"], NS),
        "S": pd.Categorical.from_codes(rows["S"], SS), "X": pd.Categorical.from_codes(rows["X"], XS),
        "which": rows["which"], "i": rows["i"], "j": rows["j"], "k": rows["k"], "b": rows["b"],
        "sig_time": ts[rows["i"]], "entry_time": ts[rows["j"]], "exit_time": ts[rows["k"]],
        "entry_px": rows["entry_px"], "entry": rows["entry"], "stop": rows["stop"], "target": rows["target"],
        "exit": rows["exit"], "reason": pd.Categorical.from_codes(rows["reason"], REASONS),
        "pnl": rows["pnl"], "R": rows["R"], "risk_pts": rows["risk_pts"],
        "f_ema200": rows["f_ema200"], "f_vwap": rows["f_vwap"], "f_ema921": rows["f_ema921"],
        "in11": tod[rows["j"]] < CUT["11"]})
    assert (tod[rows["j"]] < CUT["12"]).all(), "an entry after 12:00"
    assert (ctx.cdate[rows["j"]].astype("datetime64[D]") == rows["day"].astype("datetime64[D]")).all()
    return df


def setups_frame(ctx, sets):
    sets = sets[np.lexsort((sets["K"], sets["L"], sets["day"]))]
    df = pd.DataFrame({k: sets[k] for k in SET.names})
    df["day"] = sets["day"].astype("datetime64[D]").astype("datetime64[ns]")
    df["L"] = pd.Categorical.from_codes(sets["L"], LS)
    df["K"] = pd.Categorical.from_codes(sets["K"], KS)
    df["b_time"] = pd.Series(ctx.ts[np.maximum(sets["b"], 0)]).where(pd.Series(sets["b"] >= 0))
    return df


def path(phase, what="trades"):
    return core.OUT / phase / f"G11_{what}.parquet"


def run(ctx, procs=2, cut_tod=720, days=None):
    days = traded_days(ctx) if days is None else days
    rows, sets = simulate_days(ctx, days, cut_tod, procs)
    rows = add_fvg(rows, sets)
    return frame(ctx, rows), setups_frame(ctx, sets)


def main():
    import run as runner
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", choices=["is", "full"], required=True)
    ap.add_argument("--procs", type=int, default=2, help="worker processes (1 or 2)")
    ap.add_argument("--time-sample", type=int, default=0, help="time this many evenly spaced days; writes nothing")
    a = ap.parse_args()
    assert a.procs in (1, 2)
    t0 = time.time()
    ctx = core.Ctx(runner.bars(a.phase))
    P = prep(ctx)
    days = traded_days(ctx)
    print(f"G11 sim   phase {a.phase}   bars {ctx.ts[0]} -> {ctx.ts[-1]}   traded days {len(days)}   "
          f"cells {len(cells())} ({len(triples())} valid L x N x S)   prepared in {time.time() - t0:.0f}s", flush=True)
    if a.time_sample:
        pick = [days[q] for q in np.linspace(0, len(days) - 1, a.time_sample).astype(int)]
        t1 = time.time()
        rows, _ = _sim_days(P, pick)
        dt = time.time() - t1
        print(f"{len(pick)} days in {dt:.1f}s, {len(rows)} trades (D none / ext) -> about {dt / len(pick) * len(days) / 60:.1f}"
              f" minutes for {len(days)} days in one process, {dt / len(pick) * len(days) / 120:.1f} in two")
        return
    t1 = time.time()
    df, st = run(ctx, a.procs)
    t_sim = time.time() - t1
    if a.phase == "is":
        assert df.exit_time.max() < core.IS_END and df.day.max() < pd.Timestamp("2023-01-01")
    p = path(a.phase)
    p.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(p, index=False)
    st.to_parquet(path(a.phase, "setups"), index=False)
    print(f"simulated in {t_sim:.0f}s ({a.procs} process{'es' if a.procs > 1 else ''})   wrote {p}   {len(df)} trades"
          f"   {p.stat().st_size / 1e6:.1f} MB   total {time.time() - t0:.0f}s")
    report(df, st)


def report(df, st):
    pd.set_option("display.width", 250)
    print(f"days {st.day.nunique()}   set-ups (day x L x K with a break by 12:00) {(st.side != 0).sum()} of {len(st)}")
    g = st.assign(brk=st.side != 0).groupby(["L", "K"], observed=True)
    print(pd.DataFrame({"days_with_break": g.brk.sum(), "long": g.side.apply(lambda s: int((s > 0).sum())),
                        "short": g.side.apply(lambda s: int((s < 0).sum())), "fvg": g.d_fvg.sum(),
                        "ext_by_cut": g.ext_i.apply(lambda s: int((s >= 0).sum())),
                        "f_ema200": g.f_ema200.sum(), "f_vwap": g.f_vwap.sum(), "f_ema921": g.f_ema921.sum()}).to_string())
    n = df.groupby(["L", "K", "D", "N", "S", "X"], observed=True).size()
    print(f"cells with a trade {len(n)} of {len(cells())}   trades per cell: min {n.min()}  median {n.median():.0f}  max {n.max()}"
          f"   first trades {(df.which == 1).sum()}  re-entries {(df.which == 2).sum()}   entries by 11:00 {df.in11.sum()}")
    print("first trades per (N, S), summed over L, K, D, X:")
    print(df[df.which == 1].groupby(["N", "S"], observed=True).size().unstack().to_string())


if __name__ == "__main__":
    main()
