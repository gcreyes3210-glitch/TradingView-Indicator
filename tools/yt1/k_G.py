#!/usr/bin/env python3
"""K-G - TTrades claims about how MNQ candles behave (YT4_SPEC.md Part 1: claims A, B, C, F, G, I, J, K).

TTrades publishes no hit rates, so every measured rate stands next to a BASE RATE: the same outcome on the same
candle series without the condition. Nothing here places a trade. A condition never reads past the close of the
candle (or 5-minute bar) that completes it; an outcome looks forward by design.

Candles, built here from the 1-minute bars (all fixed before the first run, see notes/K-G.md):
  d18   the trading day 18:00 -> 17:00 (ctx.tdate; a stray bar stamped 17:00-17:59 belongs to no day)
  d00   the calendar day, midnight to midnight (the second daily reading)
  4h    opens 18:00, 22:00, 02:00, 06:00, 10:00, 14:00, each four clock hours
  1h    clock hours
  A candle counts when it holds at least half the minutes of its clock span (690 / 720 / 120 / 30). The series is
  the candles that count, in time order: "the next candle" is the next one that exists.
  Roll: a candle is a roll candle when the contract of its last bar differs from that of the previous candle's last
  bar. A roll candle and the candle after it are flagged, and a case is dropped when ANY candle it uses is flagged.
  "Trades above x" = a high >= x + 1 tick (below: a low <= x - 1 tick).

Rows: result["rows"]["<claim>.<series>.<side>.<outcome>.<base>"] = n, k, rate (the claim's cases), base_n, base_k,
base_rate, diff_pp, z, p (two-sided two-proportion z-test, pooled variance, claim against base).
side = long / short / both (both = the two sides' counts added, for the claim and for the base).
"""
import math
import numpy as np
import pandas as pd
import core

NAME = "TTrades candle claims A B C F G I J K, each rate next to its base rate"
T = core.TICK
N_FAMILIES = 14
SERIES = ("d18", "d00", "4h", "1h")
NOMINAL = dict(d18=1380, d00=1440, **{"4h": 240, "1h": 60})

LEGEND = {
    "A.<s>.<side>.beyond.all": "close(D) > high(D-1) [short: close(D) < low(D-1)] -> D+1 trades above high(D) "
                               "[below low(D)]. Base: every candle D.",
    "A.<s>.<side>.first.all": "same condition -> D+1 takes high(D) before low(D) [short: low before high], order read "
                              "from 1-minute bars; both in one 1-minute bar = neither (same_bar). Base: every candle.",
    "B.<s>.<side>.beyond.all": "short: high(D) > high(D-1), close(D) < high(D-1), low(D) >= low(D-1) -> D+1 trades "
                               "below low(D). long: the mirror -> D+1 trades above high(D). Base: every candle.",
    "B.<s>.<side>.first.all": "same condition -> D+1 takes low(D) before high(D) [long: high before low].",
    "C.<s>.<side>.<o>.all": "long: low(C2) < low(C1), low(C3) >= low(C2), close(C3) > max(open, close) of C2. "
                            "holds_mid: low(C4) >= midpoint of C3; beyond: high(C4) > high(C3); both. short: mirror. "
                            "Base: the same outcomes after every candle.",
    "C.<s>.<side>.<o>.closed_dir": "same rows, base = every candle that closed up (short: down).",
    "F.d18.long.ext_0800_0959.all": "days closing above their 18:00 open: the day's low is first printed 08:00-09:59. "
                                    "Base: all days. (short = high on days closing below the open: NOT in the spec.)",
    "G.4h.<side>.wick_in_1h.all": "4H candle closing up after an up-closing 4H candle: its low lies inside the "
                                  "high-low range of the last 1H candle before it opened. short: mirror with the "
                                  "high. Base: every 4H candle.",
    "I.<bias>_<open>.<side>.run_holds.<base>": "bias day (long = bullish) on which price trades below the open and a "
                                               "5-minute bar then closes back above it by the deadline -> the run's "
                                               "low is not traded through by 16:00. Base: the same event on no-bias "
                                               "days (nobias), on opposite-bias days (opp), on both (rest).",
    "J.<bias>.<side>.ext_order.all": "bullish-bias days: the 09:30-16:00 low is printed before the high (short: "
                                     "bearish days, high before low). Base: all days with a defined bias state.",
    "K.<s>.<side>.first.all": "inside day with close(D) > close(D-5) [short: <] -> D+1 takes high(D) before low(D) "
                              "[short: low before high]. Base: every day.",
}


# ------------------------------------------------------------------ statistics
def _ztest(k1, n1, k0, n0):
    """Two-sided two-proportion z-test with the pooled proportion. Returns (z, p) or (None, None)."""
    if not n1 or not n0:
        return None, None
    pool = (k1 + k0) / (n1 + n0)
    if pool <= 0 or pool >= 1:
        return None, None
    z = (k1 / n1 - k0 / n0) / math.sqrt(pool * (1 - pool) * (1 / n1 + 1 / n0))
    return z, math.erfc(abs(z) / math.sqrt(2))


def _stat(n, k, bn, bk, **extra):
    n, k, bn, bk = int(n), int(k), int(bn), int(bk)
    z, p = _ztest(k, n, bk, bn)
    r = dict(n=n, k=k, rate=round(k / n, 4) if n else None, base_n=bn, base_k=bk,
             base_rate=round(bk / bn, 4) if bn else None,
             diff_pp=round(100 * (k / n - bk / bn), 2) if n and bn else None,
             z=round(z, 3) if z is not None else None, p=float(f"{p:.3g}") if p is not None else None)
    r.update({a: int(b) for a, b in extra.items()})
    return r


def _put(rows, stem, outcome, base, sides):
    """sides = {"long": (cond, out, base_mask[, same]), "short": (...)}: adds the long, short and both rows.
    stem = "<claim>.<series>". same (optional) = mask of both-in-one-bar cases, counted on claim and base."""
    tot, ext = np.zeros(4, np.int64), np.zeros(2, np.int64)
    has_same = False
    for side in ("long", "short"):
        cond, out, bm = sides[side][:3]
        c = np.array([cond.sum(), (cond & out).sum(), bm.sum(), (bm & out).sum()], np.int64)
        e = {}
        if len(sides[side]) > 3:
            has_same = True
            sm = sides[side][3]
            e = dict(same_bar=(cond & sm).sum(), base_same_bar=(bm & sm).sum())
            ext += np.array([e["same_bar"], e["base_same_bar"]], np.int64)
        rows[f"{stem}.{side}.{outcome}.{base}"] = _stat(*c, **e)
        tot += c
    e = dict(same_bar=ext[0], base_same_bar=ext[1]) if has_same else {}
    rows[f"{stem}.both.{outcome}.{base}"] = _stat(*tot, **e)


# ------------------------------------------------------------------ candles
class _Ser:
    pass


def _sh(a, j):
    """a shifted so that out[k] = a[k - j] (j > 0: j candles earlier; j < 0: later). Edges: NaN / False."""
    if a.dtype == bool:
        out = np.zeros(len(a), bool)
    else:
        out = np.full(len(a), np.nan)
    if j > 0:
        out[j:] = a[:-j]
    elif j < 0:
        out[:j] = a[-j:]
    else:
        out[:] = a
    return out


def _series(ctx, key, nominal):
    """Candles = runs of equal `key` over the 1-minute bars, kept when they hold at least half of `nominal` minutes."""
    st = np.r_[0, np.flatnonzero(key[1:] != key[:-1]) + 1]
    en = np.r_[st[1:], ctx.n]                                   # exclusive
    hi, lo = np.maximum.reduceat(ctx.H, st), np.minimum.reduceat(ctx.L, st)
    keep = (en - st) * 2 >= nominal
    s = _Ser()
    s.groups, s.too_short = int(len(st)), int((~keep).sum())
    s.st, s.en = st[keep], en[keep]
    s.o, s.c, s.h, s.l = ctx.O[s.st], ctx.C[s.en - 1], hi[keep], lo[keep]
    s.m = len(s.st)
    li = ctx.iid[s.en - 1]
    s.roll = np.r_[False, li[1:] != li[:-1]]                    # contract changed since the previous candle's last bar
    s.x = s.roll | _sh(s.roll, 1)                               # left out: the roll candle and the one after it
    return s


def _elig(s, back, fwd):
    """Candles k for which k-back .. k+fwd all exist and none of them is flagged."""
    ok = np.ones(s.m, bool)
    ok[:back] = False
    if fwd:
        ok[max(s.m - fwd, 0):] = False
    for j in range(-fwd, back + 1):
        ok &= ~_sh(s.x, j)
    return ok


def _first_takes(ctx, s):
    """For every candle k: the first 1-minute bar of candle k+1 trading above high(k) / below low(k) (-1 = none)."""
    up, dn = np.full(s.m, -1, np.int64), np.full(s.m, -1, np.int64)
    H, L = ctx.H, ctx.L
    for k in range(s.m - 1):
        a, b = s.st[k + 1], s.en[k + 1]
        u = H[a:b] >= s.h[k] + T
        if u.any():
            up[k] = a + int(u.argmax())
        d = L[a:b] <= s.l[k] - T
        if d.any():
            dn[k] = a + int(d.argmax())
    s.up, s.dn = up, dn
    s.t_hi, s.t_lo = up >= 0, dn >= 0
    s.hi_first = s.t_hi & (~s.t_lo | (up < dn))
    s.lo_first = s.t_lo & (~s.t_hi | (dn < up))
    s.same = s.t_hi & s.t_lo & (up == dn)


def _conditions(s):
    """Claim A and B conditions on candle k against candle k-1 (NaN at the first candle -> False)."""
    ph, pl = _sh(s.h, 1), _sh(s.l, 1)
    s.a_up, s.a_dn = s.c > ph, s.c < pl
    s.b_dn = (s.h > ph) & (s.c < ph) & (s.l >= pl)              # failed run above: bearish
    s.b_up = (s.l < pl) & (s.c > pl) & (s.h <= ph)              # failed run below: bullish


def build(ctx):
    """The four candle series, with first-take indices and the A / B conditions."""
    td, cd, tod = ctx.tdate.astype("int64"), ctx.cdate.astype("int64"), ctx.tod.astype("int64")
    stray = ((tod >= 1020) & (tod < 1080)).astype("int64")      # 17:00-17:59: outside 18:00 -> 17:00
    keys = {"d18": td * 2 + stray, "d00": cd, "4h": td * 6 + ((tod + 360) % 1440) // 240, "1h": cd * 24 + tod // 60}
    S = {}
    for name in SERIES:
        s = _series(ctx, keys[name], NOMINAL[name])
        _first_takes(ctx, s)
        _conditions(s)
        S[name] = s
    return S


# ------------------------------------------------------------------ claims on candle series
def _claims_AB(rows, name, s, cnt):
    e = _elig(s, 1, 1)
    cnt[f"{name}.triples"] = int(e.sum())
    for cl, lg, sh in (("A", s.a_up, s.a_dn), ("B", s.b_up, s.b_dn)):
        _put(rows, f"{cl}.{name}", "beyond", "all", dict(long=(e & lg, s.t_hi, e), short=(e & sh, s.t_lo, e)))
        _put(rows, f"{cl}.{name}", "first", "all",
             dict(long=(e & lg, s.hi_first, e, s.same), short=(e & sh, s.lo_first, e, s.same)))


def _claim_C(rows, name, s, cnt):
    e = _elig(s, 2, 1)                                          # k = C3; C1 = k-2, C2 = k-1, C4 = k+1
    cnt[f"{name}.quads"] = int(e.sum())
    h1, l1, h2, l2 = _sh(s.h, 2), _sh(s.l, 2), _sh(s.h, 1), _sh(s.l, 1)
    o2, c2 = _sh(s.o, 1), _sh(s.c, 1)
    h4, l4 = _sh(s.h, -1), _sh(s.l, -1)
    mid = (s.h + s.l) / 2.0
    c_long = e & (l2 < l1) & (s.l >= l2) & (s.c > np.maximum(o2, c2))
    c_short = e & (h2 > h1) & (s.h <= h2) & (s.c < np.minimum(o2, c2))
    outs = dict(holds_mid=(l4 >= mid, h4 <= mid), beyond=(h4 >= s.h + T, l4 <= s.l - T))
    outs["both"] = (outs["holds_mid"][0] & outs["beyond"][0], outs["holds_mid"][1] & outs["beyond"][1])
    up, dn = e & (s.c > s.o), e & (s.c < s.o)
    for o, (ol, os_) in outs.items():
        _put(rows, f"C.{name}", o, "all", dict(long=(c_long, ol, e), short=(c_short, os_, e)))
        _put(rows, f"C.{name}", o, "closed_dir", dict(long=(c_long, ol, up), short=(c_short, os_, dn)))


def _claim_K(rows, name, s, cnt):
    e = _elig(s, 5, 1)
    cnt[f"{name}.K_windows"] = int(e.sum())
    inside = e & (s.h < _sh(s.h, 1)) & (s.l > _sh(s.l, 1))
    c5 = _sh(s.c, 5)
    cnt[f"{name}.K_inside_days"] = int(inside.sum())
    _put(rows, f"K.{name}", "first", "all",
         dict(long=(inside & (s.c > c5), s.hi_first, e, s.same), short=(inside & (s.c < c5), s.lo_first, e, s.same)))


def _claim_G(rows, ctx, s4, s1, cnt):
    e = _elig(s4, 1, 0)
    j = np.searchsorted(s1.en, s4.st, "right") - 1              # last 1H candle that ended before the 4H candle opened
    ok = j >= 0
    jj = np.where(ok, j, 0)
    one = (ctx.iid[s1.st[jj]] == ctx.iid[s4.st]) & (ctx.iid[s1.en[jj] - 1] == ctx.iid[s4.st])
    e &= ok & one
    cnt["4h.G_candles"] = int(e.sum())
    cnt["4h.G_1h_not_adjacent"] = int((e & (s1.en[jj] != s4.st)).sum())   # a gap (close, weekend) lies in between
    h1, l1 = s1.h[jj], s1.l[jj]
    up, dn = s4.c > s4.o, s4.c < s4.o
    _put(rows, "G.4h", "wick_in_1h", "all",
         dict(long=(e & up & _sh(up, 1), (s4.l >= l1) & (s4.l <= h1), e),
              short=(e & dn & _sh(dn, 1), (s4.h >= l1) & (s4.h <= h1), e)))


BLOCKS = [f"{h:02d}:00-{h + 1:02d}:59" for h in (18, 20, 22, 0, 2, 4, 6, 8, 10, 12, 14)] + ["16:00-16:59"]
BLOCK_MIN = [120] * 11 + [60]                                   # the last block is 16:00-16:59


def _claim_F(rows, ctx, s, cnt):
    e = ~s.x
    blk_lo, blk_hi = np.zeros(s.m, np.int64), np.zeros(s.m, np.int64)
    for k in range(s.m):
        a, b = s.st[k], s.en[k]
        t_lo = ctx.tod[a + int(ctx.L[a:b].argmin())]            # the first bar that printed the day's low
        t_hi = ctx.tod[a + int(ctx.H[a:b].argmax())]
        blk_lo[k], blk_hi[k] = ((t_lo + 360) % 1440) // 120, ((t_hi + 360) % 1440) // 120
    cnt["d18.F_days"] = int(e.sum())
    cnt["d18.F_first_bar_not_1800"] = int((e & (ctx.tod[s.st] != 1080)).sum())
    up, dn = e & (s.c > s.o), e & (s.c < s.o)
    cnt["d18.F_close_equals_open"] = int((e & (s.c == s.o)).sum())
    _put(rows, "F.d18", "ext_0800_0959", "all", dict(long=(up, blk_lo == 7, e), short=(dn, blk_hi == 7, e)))

    def dist(mask, blk):
        n = int(mask.sum())
        c = np.bincount(blk[mask], minlength=12)
        return dict(n=n, blocks={BLOCKS[i]: [int(c[i]), round(c[i] / n, 4) if n else None] for i in range(12)})
    return dict(minute_share={BLOCKS[i]: round(BLOCK_MIN[i] / 1380, 4) for i in range(12)},
                low=dict(all_days=dist(e, blk_lo), up_close_days=dist(up, blk_lo), down_close_days=dist(dn, blk_lo)),
                high=dict(all_days=dist(e, blk_hi), up_close_days=dist(up, blk_hi), down_close_days=dist(dn, blk_hi)))


# ------------------------------------------------------------------ claims on cash days (I, J)
def _bias(ctx, s, dates):
    """Per cash day of the day table: +1 / -1 / 0 from the last daily candle that closed before the day (against
    the candle before it), its kind, and whether the day is used (None = left out, with the reason)."""
    e = _elig(s, 1, 0)
    kind = np.where(s.a_up, "A_long", np.where(s.b_up, "B_long", np.where(s.a_dn, "A_short",
                    np.where(s.b_dn, "B_short", "none"))))
    val = np.where(s.a_up | s.b_up, 1, np.where(s.a_dn | s.b_dn, -1, 0))
    out = {}
    for d in ctx.days.index:
        j = int(np.searchsorted(dates, np.datetime64(d, "D"), "left")) - 1   # last candle dated before the cash day
        if d in ctx.roll2_dates:
            out[d] = (None, "roll_day_or_day_after")
        elif j < 1:
            out[d] = (None, "no_previous_candles")
        elif not e[j]:
            out[d] = (None, "bias_candle_flagged")
        else:
            out[d] = (int(val[j]), str(kind[j]))
    return out


def _run_event(ctx, b5, a0, i_dl, e16, side):
    """side +1: price trades below the open of bar a0 (from a0 on, before i_dl), then a 5-minute bar whose last
    minute is before i_dl and not before the first such trade closes above that open. Returns None, or
    (close-back bar's last 1-minute index, the run's extreme, True if that extreme is not traded through before e16).
    side -1: the mirror."""
    bf, bl, bc = b5
    X = ctx.O[a0]
    tr = (ctx.L[a0:i_dl] <= X - T) if side > 0 else (ctx.H[a0:i_dl] >= X + T)
    if not tr.any():
        return None
    r = a0 + int(tr.argmax())
    p0, p1 = int(np.searchsorted(bf, a0, "left")), int(np.searchsorted(bf, i_dl, "left"))
    back = (bl[p0:p1] >= r) & ((bc[p0:p1] > X) if side > 0 else (bc[p0:p1] < X))
    if not back.any():
        return None
    j = int(bl[p0 + int(back.argmax())])
    if side > 0:
        ext = float(ctx.L[a0:j + 1].min())
        through = bool((ctx.L[j + 1:e16] <= ext - T).any())
    else:
        ext = float(ctx.H[a0:j + 1].max())
        through = bool((ctx.H[j + 1:e16] >= ext + T).any())
    return j, ext, not through


OPENS = {"0930": ("09:30", "11:30"), "0830": ("08:30", "09:30")}


def day_table(ctx, S):
    """One row per cash day: the bias under both daily readings, the opposing-run events and the RTH order."""
    b = ctx.bars(5)
    b5 = (b.i_first.to_numpy(), b.i_last.to_numpy(), b.close.to_numpy(float))
    bias = {"d18": _bias(ctx, S["d18"], ctx.tdate[S["d18"].st]), "d00": _bias(ctx, S["d00"], ctx.cdate[S["d00"].st])}
    recs = []
    for d in ctx.days.index:
        r = dict(date=d)
        for bn in ("d18", "d00"):
            r[f"bias_{bn}"], r[f"kind_{bn}"] = bias[bn][d]
        a, e16 = ctx.span(d, "09:30", "16:00")
        ilo, ihi = int(ctx.L[a:e16].argmin()), int(ctx.H[a:e16].argmax())
        r["low_first"], r["high_first"], r["ext_same_bar"] = ilo < ihi, ihi < ilo, ilo == ihi
        for nm, (t0, t1) in OPENS.items():
            a0 = ctx.idx(d, t0)
            r[f"has_{nm}"] = a0 is not None
            for side, sn in ((1, "long"), (-1, "short")):
                ev = None
                if a0 is not None:
                    ev = _run_event(ctx, b5, int(a0), ctx.span(d, t0, t1)[1], e16, side)
                r[f"ev_{nm}_{sn}"] = ev is not None
                r[f"hold_{nm}_{sn}"] = bool(ev[2]) if ev else False
                r[f"j_{nm}_{sn}"] = int(ev[0]) if ev else -1
                r[f"ext_{nm}_{sn}"] = float(ev[1]) if ev else np.nan
        recs.append(r)
    return pd.DataFrame(recs).set_index("date")


def _claims_IJ(rows, D, cnt):
    for bn in ("d18", "d00"):
        bv = np.array([9 if v is None or v != v else int(v) for v in D[f"bias_{bn}"]])   # 9 = day left out
        used = bv != 9
        bull, bear, none = bv == 1, bv == -1, bv == 0
        kinds = D[f"kind_{bn}"].value_counts().to_dict()
        cnt[f"{bn}.bias_days"] = dict(cash_days=int(len(D)), used=int(used.sum()), bullish=int(bull.sum()),
                                      bearish=int(bear.sum()), none=int(none.sum()),
                                      kinds={k: int(v) for k, v in sorted(kinds.items())})
        lf, hf, sm = (D[c].to_numpy() for c in ("low_first", "high_first", "ext_same_bar"))
        _put(rows, f"J.{bn}", "ext_order", "all", dict(long=(bull, lf, used, sm), short=(bear, hf, used, sm)))
        for nm in OPENS:
            el, es = D[f"ev_{nm}_long"].to_numpy(), D[f"ev_{nm}_short"].to_numpy()
            hl, hs = D[f"hold_{nm}_long"].to_numpy(), D[f"hold_{nm}_short"].to_numpy()
            cnt[f"{bn}_{nm}.events"] = dict(
                days_without_open_bar=int((used & ~D[f"has_{nm}"].to_numpy()).sum()),
                long_event=dict(bullish=int((bull & el).sum()), none=int((none & el).sum()), bearish=int((bear & el).sum())),
                short_event=dict(bullish=int((bull & es).sum()), none=int((none & es).sum()), bearish=int((bear & es).sum())))
            for base, ml, ms in (("nobias", none, none), ("opp", bear, bull), ("rest", none | bear, none | bull)):
                _put(rows, f"I.{bn}_{nm}", "run_holds", base, dict(long=(bull & el, hl, ml & el), short=(bear & es, hs, ms & es)))


# ------------------------------------------------------------------ entry points
def measure(ctx):
    S = build(ctx)
    rows, cnt = {}, {}
    for name in SERIES:
        s = S[name]
        cnt[name] = dict(groups=s.groups, under_half_minutes=s.too_short, candles=int(s.m),
                         roll_candles=int(s.roll.sum()), flagged=int(s.x.sum()))
        _claims_AB(rows, name, s, cnt)
        _claim_C(rows, name, s, cnt)
        if name in ("d18", "d00"):
            _claim_K(rows, name, s, cnt)
    f_blocks = _claim_F(rows, ctx, S["d18"], cnt)
    _claim_G(rows, ctx, S["4h"], S["1h"], cnt)
    _claims_IJ(rows, day_table(ctx, S), cnt)
    order = {c: i for i, c in enumerate("ABCFGIJK")}
    rows = dict(sorted(rows.items(), key=lambda kv: order[kv[0][0]]))      # stable: by claim, then insertion order
    return dict(claim="TTrades candle claims (YT4_SPEC.md Part 1), each rate next to its base rate",
                span=f"{ctx.ts[0].date()} -> {ctx.ts[-1].date()}", key="<claim>.<series>.<side>.<outcome>.<base>",
                bonferroni=0.05 / N_FAMILIES, legend=LEGEND, counts=cnt, rows=rows, F_blocks=f_blocks)


def show(res):
    print(res["claim"], "  ", res["span"])
    c = res["counts"]
    for name in SERIES:
        x = c[name]
        print(f"  {name:<4} candles {x['candles']:>6} (under half their minutes {x['under_half_minutes']}, roll "
              f"{x['roll_candles']}, flagged {x['flagged']})   A/B triples {c[name + '.triples']}, C quads {c[name + '.quads']}")
    for bn in ("d18", "d00"):
        print(f"  bias {bn}: {c[bn + '.bias_days']}")
        for nm in OPENS:
            print(f"     {nm} events: {c[bn + '_' + nm + '.events']}")
    print(f"  F days {c['d18.F_days']} (first bar not 18:00: {c['d18.F_first_bar_not_1800']}, close = open: "
          f"{c['d18.F_close_equals_open']});  G 4H candles {c['4h.G_candles']} (bars between the 1H candle and the 4H open: "
          f"{c['4h.G_1h_not_adjacent']});  K inside days d18 {c['d18.K_inside_days']}, d00 {c['d00.K_inside_days']}")
    print(f"  * = p <= 0.05 / {N_FAMILIES} = {res['bonferroni']:.5f}")
    print(f"  {'key':<38} {'n':>6} {'k':>6} {'rate':>6}   {'base n':>6} {'base k':>6} {'base':>6}  {'diff pp':>7}  {'p':>8}")
    last = None
    for k, r in res["rows"].items():
        if k[0] != last:
            print()
            last = k[0]
        rate = f"{r['rate']:.1%}" if r["rate"] is not None else "   -  "
        base = f"{r['base_rate']:.1%}" if r["base_rate"] is not None else "   -  "
        diff = f"{r['diff_pp']:+.1f}" if r["diff_pp"] is not None else "  -  "
        p = f"{r['p']:.4f}" if r["p"] is not None else "   -   "
        star = "*" if r["p"] is not None and r["p"] <= res["bonferroni"] else " "
        same = f"   same bar {r['same_bar']} / {r['base_same_bar']}" if "same_bar" in r else ""
        print(f"  {k:<38} {r['n']:>6} {r['k']:>6} {rate:>6}   {r['base_n']:>6} {r['base_k']:>6} {base:>6}  {diff:>7}  {p:>8}{star}{same}")
    f = res["F_blocks"]
    print("\n  F: when the day's low / high is first printed, by 2-hour block (share of days; minutes = the block's share of the 1,380-minute day)")
    print(f"  {'block':<12} {'minutes':>7}   {'low all':>8} {'low up':>8} {'low down':>8}   {'high all':>8} {'high up':>8} {'high down':>9}")
    for b in BLOCKS:
        v = [f[w][g]["blocks"][b][1] for w in ("low", "high") for g in ("all_days", "up_close_days", "down_close_days")]
        print(f"  {b:<12} {f['minute_share'][b]:>7.1%}   {v[0]:>8.1%} {v[1]:>8.1%} {v[2]:>8.1%}   {v[3]:>8.1%} {v[4]:>8.1%} {v[5]:>9.1%}")
    print(f"  days: all {f['low']['all_days']['n']}, up-close {f['low']['up_close_days']['n']}, down-close {f['low']['down_close_days']['n']}")
