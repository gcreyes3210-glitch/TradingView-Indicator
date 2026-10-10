#!/usr/bin/env python3
"""LEV1 levels (YT9_SPEC.md): every level of every cash day, each fixed from bars at or before its own `t_set`.

    levels(ctx, at_open=True)   one row per cash day x level (real, placebo, moving, block); see COLUMNS below
    moving_values(ctx)          the VWAP and its bands per 1-minute bar k: the value fixed at the close of the last
                                5-minute bar completed by the open of bar k
    profile(h, l, v)            Aceflw_Levels.pine's overnight profile (rows, POC, value area) on 1-minute bars
    profile_pine(h, l, v)       the same, transcribed line by line from the Pine script (the brute-force check)
    vwap5(ctx)                  18:00-anchored VWAP and sigma on 5-minute bars, as the script
    em_sd5(ctx)                 ta.stdev(log(close / close[1]), 2760) on 5-minute bars (population sd)

Codes (the spec's), in the fixed order used for ties and for printing:
    pdh pdl pdc pdm | pwh pwl | onh onl | ash asl | ldh ldl | prh prl | o18 o00 o0830 | vah poc val | r100 |
    orh orl | em1u em1d em2u em2d | vw vw1u vw1d vw2u vw2d          placebo of a static code X: 'X~'

COLUMNS
    date       cash date                          code / group / inst / lid   lid is unique within a day
                                                  (inst: r100 'up' / 'dn'; expected move = block start 'HHMM';
                                                  a placebo adds '+' / '-')
    value      the level (not rounded)            kind   static / moving / block
    t_set      index of the 1-minute bar at whose CLOSE the level is fixed; open_set=True: the level is fixed at the
               OPEN of bar t_set (it uses bars before t_set and that one open). Moving levels: t_set = -1 (marker), and
               `value` is the value at the start of the watch.
    w0, w1     first and last watched 1-minute bar (w0 > w1: never watched)
    b0, b1     expected-move bands: first and last 1-minute bar of the block (-1 otherwise)
    is_placebo, parent (the parent's code), dropped (placebo within 0.03 x ATR of a real static level known at its own
               watch start), near_later (a kept placebo within 0.03 x ATR of a real static level that is only fixed
               later: the opening range; it cannot be dropped without reading the future)
    used       static levels set before 09:30: price traded through the level between the time it was set and the
               09:29 bar (strictly on both sides of it, the price at the set time included)
               A placebo's t_set is the later of its parent's and the bar that fixes the day's ATR (the last bar
               before 18:00); its `used` is measured from the parent's set time, as the parent's.
    atr        the day's ATR (NaN = no ATR: no placebos that day)

at_open: the two levels that are DEFINED by the open of their first watched bar (r100: the 09:30 open; the centre of
an expected-move block that starts at or after 09:30: the block's first open) read that open. at_open=False replaces
that one number by the last close before it (pstart): the form the mirrored-future test compares; trades use True.

    python3 tools/yt1/lev1_levels.py --check        the unit checks quoted in notes/LEV1.md
    python3 tools/yt1/lev1_levels.py --causal 60    every sampled level recomputed with the future after its own
                                                    t_set mirrored (core._reflect); must come out identical
"""
import argparse, math, pathlib, sys, time
import numpy as np
import pandas as pd
sys.path.insert(0, str(pathlib.Path(__file__).parent))
import core
import ind

TICK = core.TICK
ROW_TICKS, VA_PCT = 4, 70.0                       # Aceflw_Levels.pine: rowTicks, vaPct
ROW = ROW_TICKS * TICK
EM_BLOCKS = (480, 600, 720, 840)                  # 08:00, 10:00, 12:00, 14:00 (minutes after midnight, New York)
EM_LEN = 120                                      # block length in minutes
EM_BAR = 5                                        # expected move and VWAP bands: 5-minute chart
EM_LOOK = int(10 * 1380 / EM_BAR)                 # emLook * 1380 / barMin = 2,760 five-minute bars
EM_SCALE = math.sqrt(EM_LEN / EM_BAR)             # sqrt(emH / barMin) = sqrt(24)
PLACEBO_S = 0.12                                  # placebo shift, x ATR
NEAR = 0.03                                       # placebo drop distance and cluster distance, x ATR
OPEN_TOD, OR_END, WATCH_END = 570, 585, 900       # 09:30; opening range 09:30-09:44; last watched bar = 15:00

ORDER = ["pdh", "pdl", "pdc", "pdm", "pwh", "pwl", "onh", "onl", "ash", "asl", "ldh", "ldl", "prh", "prl",
         "o18", "o00", "o0830", "vah", "poc", "val", "r100", "orh", "orl",
         "em1u", "em1d", "em2u", "em2d", "vw", "vw1u", "vw1d", "vw2u", "vw2d"]
RANK = {c: k for k, c in enumerate(ORDER)}
GROUP = {}
for _g, _cs in (("previous day", "pdh pdl pdc pdm"), ("previous week", "pwh pwl"), ("overnight", "onh onl"),
                ("Asia", "ash asl"), ("London", "ldh ldl"), ("pre-market", "prh prl"), ("opens", "o18 o00 o0830"),
                ("profile", "vah poc val"), ("round numbers", "r100"), ("opening range", "orh orl"),
                ("expected move", "em1u em1d em2u em2d"), ("VWAP bands", "vw vw1u vw1d vw2u vw2d")):
    for _c in _cs.split():
        GROUP[_c] = _g
STATIC = ORDER[:23]
BLOCK = ORDER[23:27]
MOVING = ORDER[27:]
EM_MULT = {"em1u": 1.0, "em1d": -1.0, "em2u": 2.0, "em2d": -2.0}
VW_MULT = {"vw": 0.0, "vw1u": 1.0, "vw1d": -1.0, "vw2u": 2.0, "vw2d": -2.0}


def pstart(ctx, at_open=True):
    """Array p with p[k] = the price at the start of a watch whose first bar is k: the open of bar k.
    at_open=False: the last close before bar k instead (nothing of bar k is read)."""
    if at_open:
        return ctx.O
    p = np.empty(ctx.n)
    p[0] = np.nan
    p[1:] = ctx.C[:-1]
    return p


# ------------------------------------------------------------------ overnight volume profile (Aceflw_Levels.pine)
def profile(h, l, v, row=ROW, va_pct=VA_PCT):
    """The script's profile on the given bars (the 1-minute bars of 18:00-09:29, in time order).
    f_addBar: a bar's volume is spread evenly over the rows floor((low - rowLo) / rowSize + 1e-9) ..
    floor((high - rowLo) / rowSize + 1e-9); rowLo starts at floor(first low / rowSize) * rowSize and moves down by
    whole rows when a lower low arrives. Each row receives its shares in bar order (np.add.at), as in the script.
    POC = the first row holding the largest volume. Value area: from the POC, add two rows above or two rows below
    at a time, whichever pair holds more (above on a tie), until 70 % of the volume is inside.
    Returns dict(vah, poc, val, vol, n, ip, up, dn, row_lo, rows) or None when the script would not compute one
    (rows <= 2 or no volume)."""
    h, l = np.asarray(h, float), np.asarray(l, float)
    v = np.nan_to_num(np.asarray(v, float))                  # nz(v)
    if len(h) == 0:
        return None
    lo0 = math.floor(l[0] / row) * row                       # onStart: rowLo := floor(low / rowSize) * rowSize
    r_lo = np.floor((l - lo0) / row + 1e-9).astype(np.int64)
    r_hi = np.floor((h - lo0) / row + 1e-9).astype(np.int64)
    shift = int(min(r_lo.min(), 0))                          # rows unshifted below the first bar's row
    row_lo = lo0 + shift * row
    i_lo, i_hi = r_lo - shift, r_hi - shift
    n = int(i_hi.max()) + 1
    cnt = i_hi - i_lo + 1
    share = v / cnt
    start = np.cumsum(cnt) - cnt
    tot = int(cnt.sum())
    idx = np.repeat(i_lo, cnt) + (np.arange(tot) - np.repeat(start, cnt))
    rows = np.zeros(n)
    np.add.at(rows, idx, np.repeat(share, cnt))              # unbuffered: each row adds its shares in bar order
    vol = float(v.sum())
    if not (n > 2 and vol > 0):
        return None
    ip = int(np.argmax(rows))                                # first maximum (the script's strict '>')
    best = float(rows[ip])
    target = vol * va_pct / 100.0
    acc, up, dn, guard = best, ip, ip, 0
    while acc < target and (up < n - 1 or dn > 0) and guard < 5000:
        guard += 1
        a_up = (rows[up + 1] + (rows[up + 2] if up + 2 <= n - 1 else 0.0)) if up + 1 <= n - 1 else -1.0
        a_dn = (rows[dn - 1] + (rows[dn - 2] if dn - 2 >= 0 else 0.0)) if dn - 1 >= 0 else -1.0
        if a_up >= a_dn and up < n - 1:
            steps = min(2, n - 1 - up)
            for k in range(1, steps + 1):
                acc += rows[up + k]
            up += steps
        elif dn > 0:
            steps = min(2, dn)
            for k in range(1, steps + 1):
                acc += rows[dn - k]
            dn -= steps
        else:
            break
    return dict(vah=row_lo + (up + 1) * row, poc=row_lo + (ip + 0.5) * row, val=row_lo + dn * row, vol=vol, n=n,
                ip=ip, up=up, dn=dn, row_lo=row_lo, rows=rows)


def profile_pine(h, l, v, row=ROW, va_pct=VA_PCT):
    """Line-by-line transcription of the Pine script's profile (array.unshift / push / set), for the brute-force
    check of profile(). Returns (vah, poc, val, profVol, n) or None."""
    rows, row_lo, prof_vol = [], None, 0.0

    def add_bar(lo0, hh, ll, vv):
        lo = lo0
        i_lo = int(math.floor((ll - lo) / row + 1e-9))
        if i_lo < 0:
            for _ in range(-i_lo):
                rows.insert(0, 0.0)
            lo = lo + i_lo * row
            i_lo = 0
        i_hi = int(math.floor((hh - lo) / row + 1e-9))
        while len(rows) <= i_hi:
            rows.append(0.0)
        share = (0.0 if vv != vv else vv) / (i_hi - i_lo + 1)
        for k in range(i_lo, i_hi + 1):
            rows[k] = rows[k] + share
        return lo

    for k in range(len(h)):
        if k == 0:
            rows.clear()
            row_lo = math.floor(l[0] / row) * row
            prof_vol = 0.0
        row_lo = add_bar(row_lo, float(h[k]), float(l[k]), float(v[k]))
        prof_vol += 0.0 if v[k] != v[k] else float(v[k])
    if not (len(rows) > 2 and prof_vol > 0):
        return None
    n = len(rows)
    ip, best = 0, -1.0
    for k in range(n):
        if rows[k] > best:
            best = rows[k]
            ip = k
    target = prof_vol * va_pct / 100.0
    acc, up, dn, guard = best, ip, ip, 0
    while acc < target and (up < n - 1 or dn > 0) and guard < 5000:
        guard += 1
        a_up = (rows[up + 1] + (rows[up + 2] if up + 2 <= n - 1 else 0.0)) if up + 1 <= n - 1 else -1.0
        a_dn = (rows[dn - 1] + (rows[dn - 2] if dn - 2 >= 0 else 0.0)) if dn - 1 >= 0 else -1.0
        if a_up >= a_dn and up < n - 1:
            steps = min(2, n - 1 - up)
            for k in range(1, steps + 1):
                acc += rows[up + k]
            up += steps
        elif dn > 0:
            steps = min(2, dn)
            for k in range(1, steps + 1):
                acc += rows[dn - k]
            dn -= steps
        else:
            break
    return (row_lo + (up + 1) * row, row_lo + (ip + 0.5) * row, row_lo + dn * row, prof_vol, n)


# ------------------------------------------------------------------ VWAP bands and expected move on 5-minute bars
def full_start(tod, open_min=1080):
    """The script's fullStart on a bar series: mod >= openMin and (na(mod[1]) or mod[1] < openMin or mod[1] > mod)."""
    tod = np.asarray(tod)
    prev = np.r_[-1, tod[:-1]]
    return (tod >= open_min) & ((prev < 0) | (prev < open_min) | (prev > tod))


def vwap5(ctx):
    """18:00-anchored VWAP of hlc3 x volume on 5-minute bars and its volume-weighted sd, as the script (sPV, sV,
    sPPV reset on fullStart; vwSd = sqrt(max(sPPV / sV - vwap^2, 0))): ind.session_vwap fed with the 5-minute bars
    and the script's fullStart. Returns a frame on the 5-minute index with vw, sd, new (reset bar)."""
    c = ctx.__dict__.setdefault("_lev1", {})
    if "vwap5" in c:
        return c["vwap5"]
    b = ctx.bars(EM_BAR)
    new = full_start((b.index.hour * 60 + b.index.minute).to_numpy())
    vw, sd = ind.session_vwap(b.high.to_numpy(float), b.low.to_numpy(float), b.close.to_numpy(float),
                              b.volume.to_numpy(float), new)
    out = pd.DataFrame({"vw": vw, "sd": sd, "new": new}, index=b.index)
    c["vwap5"] = out
    return out


def vwap5_check(ctx):
    """The same VWAP and sd computed another way (per-session cumulative sums in pandas), for the unit check."""
    b = ctx.bars(EM_BAR)
    new = full_start((b.index.hour * 60 + b.index.minute).to_numpy())
    sid = np.cumsum(new)
    tp = (b.high.to_numpy(float) + b.low.to_numpy(float) + b.close.to_numpy(float)) / 3
    v = b.volume.to_numpy(float)
    g = pd.DataFrame({"sid": sid, "v": v, "pv": tp * v, "ppv": tp * tp * v}).groupby("sid")
    sv, spv, sppv = g.v.cumsum().to_numpy(), g.pv.cumsum().to_numpy(), g.ppv.cumsum().to_numpy()
    vw = spv / sv
    sd = np.sqrt(np.maximum(sppv / sv - vw * vw, 0.0))
    vw[sid == 0] = np.nan
    sd[sid == 0] = np.nan
    return vw, sd


def last_done5(ctx):
    """For each 1-minute bar k: position of the last 5-minute bar that is complete by the clock when bar k opens
    (bucket open + 5 minutes <= time of bar k), or -1. Every 1-minute bar of that bucket is before bar k."""
    c = ctx.__dict__.setdefault("_lev1", {})
    if "done5" not in c:
        b = ctx.bars(EM_BAR)
        c["done5"] = np.asarray((b.index + pd.Timedelta(minutes=EM_BAR)).searchsorted(ctx.ts, "right")) - 1
    return c["done5"]


def moving_values(ctx):
    """{code: array over the 1-minute bars}: the VWAP level in force during bar k = the script's value at the close
    of the last completed 5-minute bar (last_done5). NaN where there is none."""
    c = ctx.__dict__.setdefault("_lev1", {})
    if "moving" not in c:
        w = vwap5(ctx)
        m = last_done5(ctx)
        ok = m >= 0
        vw = np.where(ok, w.vw.to_numpy()[np.maximum(m, 0)], np.nan)
        sd = np.where(ok, w.sd.to_numpy()[np.maximum(m, 0)], np.nan)
        c["moving"] = {code: vw + k * sd for code, k in VW_MULT.items()}
    return c["moving"]


def em_sd5(ctx):
    """ta.stdev(math.log(close / close[1]), 2760) on the 5-minute bars: population sd of the last 2,760 bar-to-bar
    log returns ending at each bar (ind.stdev). NaN until 2,760 returns exist."""
    c = ctx.__dict__.setdefault("_lev1", {})
    if "sd5" not in c:
        cl = ctx.bars(EM_BAR).close.to_numpy(float)
        with np.errstate(divide="ignore", invalid="ignore"):
            r = np.log(cl / np.r_[np.nan, cl[:-1]])
        c["sd5"] = ind.stdev(r, EM_LOOK)
    return c["sd5"]


# ------------------------------------------------------------------ the level table
def _weeks(ctx):
    """Trading weeks (Sunday 18:00 -> Friday 17:00) = the bars whose TRADING date falls in one Monday-Friday week.
    Returns (week id of each week, first bar, last bar, high, low)."""
    n = ctx.tdate.astype("int64")                            # days since 1970-01-01 (a Thursday)
    wid = (n + 3) // 7                                       # Monday starts a week; Sunday 18:00 has Monday's date
    u, first = np.unique(wid, return_index=True)
    last = np.r_[first[1:], ctx.n] - 1
    return u, first, last, np.maximum.reduceat(ctx.H, first), np.minimum.reduceat(ctx.L, first)


def levels(ctx, at_open=True):
    c = ctx.__dict__.setdefault("_lev1", {})
    key = ("levels", bool(at_open))
    if key in c:
        return c[key]
    O, H, L, C, V = ctx.O, ctx.H, ctx.L, ctx.C, ctx.V
    PS = pstart(ctx, at_open)
    D = ctx.days
    b5 = ctx.bars(EM_BAR)
    first5 = b5.i_first.to_numpy()
    sd5 = em_sd5(ctx)
    mv = moving_values(ctx)
    wk_id, wk_first, wk_last, wk_h, wk_l = _weeks(ctx)
    one = pd.Timedelta(days=1)
    rows = []
    prev = None                                              # previous cash day's (lo, hi) RTH span
    for d, i_open, i_end, atr in zip(D.index, D.i_open.to_numpy(), D.i_end.to_numpy(), D.atr.to_numpy()):
        i_open, i_end = int(i_open), int(i_end)
        w1 = min(ctx.span(d, OPEN_TOD, WATCH_END + 1)[1] - 1, i_end)
        real = []                                            # (code, inst, value, t_set, open_set, w0, w1)

        def add(code, value, t_set, open_set=False, inst="", w0=i_open, w1_=None):
            real.append((code, inst, float(value), int(t_set), bool(open_set), int(w0), int(w1 if w1_ is None else w1_)))

        # previous regular session (09:30-15:59 of the previous cash day): fixed at the close of its last bar
        if prev is not None:
            lo, hi = prev
            ph, pl, pc = H[lo:hi].max(), L[lo:hi].min(), C[hi - 1]
            add("pdh", ph, hi - 1); add("pdl", pl, hi - 1); add("pdc", pc, hi - 1); add("pdm", (ph + pl) / 2, hi - 1)
        prev = ctx.span(d, OPEN_TOD, 960)
        # previous trading week: the last week with bars before this cash day's week
        wd = (int(np.datetime64(d, "D").astype("int64")) + 3) // 7
        p = int(np.searchsorted(wk_id, wd, "left")) - 1
        if p >= 0:
            add("pwh", wk_h[p], wk_last[p]); add("pwl", wk_l[p], wk_last[p])
        # overnight 18:00 (previous calendar day) -> 09:29 and its three parts
        on0 = ctx.span(d - one, 1080, 1440)[0]
        a1 = ctx.span(d, 120, 480)[0]                        # first bar at or after 02:00
        l1 = ctx.span(d, 480, OPEN_TOD)[0]                   # first bar at or after 08:00
        if i_open > on0:
            add("onh", H[on0:i_open].max(), i_open - 1); add("onl", L[on0:i_open].min(), i_open - 1)
        for hi_c, lo_c, s0, s1 in (("ash", "asl", on0, a1), ("ldh", "ldl", a1, l1), ("prh", "prl", l1, i_open)):
            if s1 > s0:
                add(hi_c, H[s0:s1].max(), s1 - 1); add(lo_c, L[s0:s1].min(), s1 - 1)
        # opens of the 18:00, 00:00 and 08:30 one-minute bars (no such bar: no level)
        for code, k in (("o18", ctx.idx(d - one, 1080)), ("o00", ctx.idx(d, 0)), ("o0830", ctx.idx(d, 510))):
            if k is not None:
                add(code, O[int(k)], int(k), True)
        # Aceflw overnight profile on the 1-minute bars of 18:00-09:29
        if i_open > on0:
            pf = profile(H[on0:i_open], L[on0:i_open], V[on0:i_open])
            if pf is not None:
                add("vah", pf["vah"], i_open - 1); add("poc", pf["poc"], i_open - 1); add("val", pf["val"], i_open - 1)
        # round numbers: nearest multiples of 100 strictly above / below the 09:30 open
        p0 = PS[i_open]
        if p0 == p0:
            add("r100", math.floor(p0 / 100.0) * 100.0 + 100.0, i_open, True, "up")
            add("r100", math.ceil(p0 / 100.0) * 100.0 - 100.0, i_open, True, "dn")
        # opening range 09:30-09:44, watched from the first bar at or after 09:45
        lo, hi = ctx.span(d, OPEN_TOD, OR_END)
        if hi > lo:
            add("orh", H[lo:hi].max(), hi - 1, False, "", hi); add("orl", L[lo:hi].min(), hi - 1, False, "", hi)

        def used_of(value, t_set, open_set, memo={}):
            if t_set >= i_open:
                return False
            k = (t_set, open_set)
            if k not in memo:
                a = t_set + (0 if open_set else 1)
                ps = O[t_set] if open_set else C[t_set]
                memo[k] = (min(L[a:i_open].min(), ps), max(H[a:i_open].max(), ps)) if a < i_open else (ps, ps)
            lo_, hi_ = memo[k]
            return bool(lo_ < value < hi_)
        memo = {}
        for code, inst, value, t_set, open_set, w0, w1_ in real:
            rows.append((d, code, inst, GROUP[code], "static", value, t_set, open_set, w0, w1_, -1, -1, False, "",
                         used_of(value, t_set, open_set, memo), False, False, atr))
        # placebos: every static level +/- 0.12 x ATR; dropped if within 0.03 x ATR of a real static level that
        # exists when the placebo's own watch starts (the opening range does not exist at 09:30)
        if atr == atr:
            s, near = PLACEBO_S * atr, NEAR * atr
            vals = np.array([r[2] for r in real])
            w0s = np.array([r[5] for r in real])
            for code, inst, value, t_set, open_set, w0, w1_ in real:
                for sign, sg in ((1.0, "+"), (-1.0, "-")):
                    f = value + sign * s
                    dist = np.abs(vals - f)
                    known = w0s <= w0
                    dropped = bool((dist[known] <= near).any())
                    later = bool((dist[~known] <= near).any()) and not dropped
                    # a placebo is fixed once its parent and the day's ATR are (the ATR at the close of the last
                    # bar before 18:00); `used` is measured from the parent's set time, as for the parent
                    ts_f, os_f = (t_set, open_set) if t_set >= on0 - 1 else (on0 - 1, False)
                    rows.append((d, code + "~", inst + sg, GROUP[code], "static", f, ts_f, os_f, w0, w1_, -1, -1,
                                 True, code, used_of(f, t_set, open_set, memo), dropped, later, atr))
        # expected-move bands: one level per block and band
        for blk in EM_BLOCKS:
            lo, hi = ctx.span(d, blk, blk + EM_LEN)
            if hi <= lo:
                continue
            k5 = int(np.searchsorted(first5, lo, "right")) - 1   # the 5-minute bar that opens the block
            if k5 < 1 or not (sd5[k5 - 1] == sd5[k5 - 1]):
                continue
            first_watched = lo >= i_open                      # the block starts at or after 09:30
            centre = PS[lo] if first_watched else O[lo]       # emC := open of the block's first bar
            if not (centre == centre):
                continue
            sig = centre * sd5[k5 - 1] * EM_SCALE             # the 2,760 five-minute bars before the block
            w0 = max(lo, i_open)
            for code in BLOCK:
                rows.append((d, code, f"{blk // 60:02d}{blk % 60:02d}", GROUP[code], "block",
                             centre + EM_MULT[code] * sig, lo, True, w0, min(hi - 1, w1), lo, hi - 1, False, "",
                             False, False, False, atr))
        # VWAP and its bands: moving; `value` = the value in force during the 09:30 bar
        for code in MOVING:
            rows.append((d, code, "", GROUP[code], "moving", mv[code][i_open], -1, False, i_open, w1, -1, -1, False,
                         "", False, False, False, atr))
    cols = ["date", "code", "inst", "group", "kind", "value", "t_set", "open_set", "w0", "w1", "b0", "b1",
            "is_placebo", "parent", "used", "dropped", "near_later", "atr"]
    lv = pd.DataFrame(rows, columns=cols)
    lv.insert(3, "lid", lv.code + np.where(lv.inst != "", "." + lv.inst, ""))
    lv = lv[lv.value.notna()].reset_index(drop=True)
    c[key] = lv
    return lv


def ok_days(ctx):
    """Cash days of the study: not a roll day or the day after, and with a daily ATR (run_orders(skip_roll=2))."""
    D = ctx.days
    return [d for d in D.index if d not in ctx.roll2_dates and d not in ctx.noatr_dates]


# ------------------------------------------------------------------ unit checks
def _piv(lv, codes):
    x = lv[lv.code.isin(codes) & ~lv.is_placebo]
    return x.pivot(index="date", columns="code", values="value")


def unit_checks(ctx, seed=7):
    lv = levels(ctx)
    D = ctx.days
    out = []
    # 1. previous day and overnight against the day table
    pv = _piv(lv, ["pdh", "pdl", "pdc", "pdm", "onh", "onl", "ash", "asl", "ldh", "ldl", "prh", "prl"]).reindex(D.index)
    for c_ in ("pdh", "pdl", "pdc", "onh", "onl"):
        a, b = pv[c_].to_numpy(), D[c_].to_numpy(float)
        same = (a == b) | (np.isnan(a) & np.isnan(b))
        out.append(f"{c_} = day table's {c_}: {int(same.sum())} of {len(D)} days"
                   f" ({int(np.isnan(b).sum())} of them with neither)" + ("" if same.all() else "   <-- MISMATCH"))
    m = (pv.pdm.to_numpy() == ((D.pdh + D.pdl) / 2).to_numpy()) | pv.pdm.isna().to_numpy()
    out.append(f"pdm = (pdh + pdl) / 2 of the day table: {int(m.sum())} of {len(D)}")
    # 2. the three parts reproduce the overnight extremes
    hi3 = pv[["ash", "ldh", "prh"]].max(axis=1).to_numpy()
    lo3 = pv[["asl", "ldl", "prl"]].min(axis=1).to_numpy()
    full = pv[["ash", "ldh", "prh"]].notna().all(axis=1).to_numpy()
    out.append(f"max(ash, ldh, prh) = onh: {int((hi3 == pv.onh.to_numpy()).sum())} of {len(D)} days;  "
               f"min(asl, ldl, prl) = onl: {int((lo3 == pv.onl.to_numpy()).sum())} of {len(D)}"
               f"   (days with all three parts: {int(full.sum())})")
    # 3. profile: volume and ordering
    n_vol = n_ord = n_pf = n_none = 0
    one = pd.Timedelta(days=1)
    spans = {}
    for d, i_open in zip(D.index, D.i_open.to_numpy()):
        on0 = ctx.span(d - one, 1080, 1440)[0]
        spans[d] = (on0, int(i_open))
        pf = profile(ctx.H[on0:i_open], ctx.L[on0:i_open], ctx.V[on0:i_open]) if i_open > on0 else None
        if pf is None:
            n_none += 1
            continue
        n_pf += 1
        tod = ctx.tod[on0:i_open]
        assert ((tod >= 1080) | (tod < 570)).all() and (ctx.tdate[on0:i_open] == np.datetime64(d, "D")).all()
        m_ = (ctx.tdate == np.datetime64(d, "D")) & ((ctx.tod >= 1080) | (ctx.tod < 570))
        n_vol += bool(pf["vol"] == float(ctx.V[m_].sum()) and abs(pf["rows"].sum() - pf["vol"]) < 1e-6 * pf["vol"])
        n_ord += bool(pf["val"] <= pf["poc"] <= pf["vah"])
    out.append(f"profile: {n_pf} days with a profile ({n_none} without); total volume = summed 1-minute volume of "
               f"18:00-09:29 (bars selected by trading date and clock) and rows sum to it: {n_vol} of {n_pf};  "
               f"val <= poc <= vah: {n_ord} of {n_pf}")
    # 4. brute force (the Pine script line by line) on 5 days + on every day
    rng = np.random.default_rng(seed)
    days = [d for d in D.index if spans[d][1] > spans[d][0]]
    pick = sorted(rng.choice(len(days), 5, replace=False))
    for k in pick:
        d = days[k]
        a, b = spans[d]
        f, g = profile(ctx.H[a:b], ctx.L[a:b], ctx.V[a:b]), profile_pine(ctx.H[a:b], ctx.L[a:b], ctx.V[a:b])
        t = lv[(lv.date == d) & lv.code.isin(["vah", "poc", "val"]) & ~lv.is_placebo].set_index("code").value
        ok = g is not None and (f["vah"], f["poc"], f["val"], f["vol"], f["n"]) == g and \
            (t.vah, t.poc, t.val) == g[:3]
        out.append(f"  brute force {d.date()}: bars {b - a}, rows {g[4]}, volume {g[3]:.0f}  Pine transcription "
                   f"VAH {g[0]:.2f} POC {g[1]:.2f} VAL {g[2]:.2f}  |  levels() VAH {t.vah:.2f} POC {t.poc:.2f} VAL "
                   f"{t.val:.2f}  -> {'identical' if ok else 'DIFFERENT'}")
    same = 0
    for d in days:
        a, b = spans[d]
        f, g = profile(ctx.H[a:b], ctx.L[a:b], ctx.V[a:b]), profile_pine(ctx.H[a:b], ctx.L[a:b], ctx.V[a:b])
        same += (f is None and g is None) or (f is not None and g is not None and
                                              (f["vah"], f["poc"], f["val"], f["vol"], f["n"]) == g)
    out.append(f"  brute force on every day: identical on {same} of {len(days)}")
    # 5. expected move: three blocks by hand (independent 5-minute closes, numpy population sd)
    em = lv[(lv.code == "em1u") & lv.atr.notna()]
    em = em[em.date > D.index[40]]
    cl = ctx.a.close.resample("5min").last().dropna()        # independent of core.resample
    for k in sorted(rng.choice(len(em), 3, replace=False)):
        r = em.iloc[k]
        t0 = ctx.ts[int(r.b0)]
        blk = t0.floor("5min")
        prevc = cl[cl.index < blk].to_numpy()[-(EM_LOOK + 1):]
        ret = np.log(prevc[1:] / prevc[:-1])
        centre = ctx.O[int(r.b0)]
        sig = centre * float(np.sqrt(np.mean((ret - ret.mean()) ** 2))) * math.sqrt(24)
        out.append(f"  expected move {r.date.date()} block {r.inst}: first bar {t0.strftime('%H:%M')}, centre "
                   f"{centre:.2f}, {len(ret)} returns, sd {np.sqrt(np.mean((ret - ret.mean()) ** 2)):.8f}, by hand 1 sigma "
                   f"{sig:.4f}  |  levels() {r.value - centre:.4f}  -> diff {abs(sig - (r.value - centre)):.2e}")
    # 6. VWAP and bands: levels use ind.session_vwap on 5-minute bars anchored at 18:00; compared here with an
    #    independent per-session cumulative-sum computation, and with the 1-minute 09:30 values by hand on 3 days
    b = ctx.bars(EM_BAR)
    w = vwap5(ctx)
    tod = (b.index.hour * 60 + b.index.minute).to_numpy()
    vw, sd = vwap5_check(ctx)
    okm = ~np.isnan(vw)
    rth = okm & (tod >= 570) & (tod <= 900)
    out.append(f"VWAP on 5-minute bars: ind.session_vwap (new session = the script's fullStart, 18:00) against an "
               f"independent per-session cumulative sum: {int(okm.sum())} bars, max |diff| VWAP "
               f"{np.nanmax(np.abs(vw - w.vw.to_numpy())):.3e}, sigma {np.nanmax(np.abs(sd - w.sd.to_numpy())):.3e} "
               f"(09:30-15:00 bars: sigma {np.nanmax(np.abs(sd - w.sd.to_numpy())[rth]):.3e}); NaN pattern equal: "
               f"{bool((np.isnan(vw) == w.vw.isna().to_numpy()).all())}; sessions {int(w.new.sum())}, of which not "
               f"starting on an 18:00 bar: {int((w.new.to_numpy() & (tod != 1080)).sum())}")
    for k in sorted(rng.choice(len(D), 3, replace=False)):
        d = D.index[k]
        a5 = ctx.a[(ctx.a.index >= core.Ctx._wall(d - one, 1080)) & (ctx.a.index < core.Ctx._wall(d, 570))]
        r5 = a5.resample("5min").agg({"high": "max", "low": "min", "close": "last", "volume": "sum"}).dropna()
        tp_ = (r5.high + r5.low + r5.close) / 3
        m_ = float((tp_ * r5.volume).sum() / r5.volume.sum())
        s_ = float(np.sqrt(max((tp_ * tp_ * r5.volume).sum() / r5.volume.sum() - m_ * m_, 0.0)))
        t = lv[(lv.date == d) & (lv.code.isin(["vw", "vw2u"]))].set_index("code").value
        out.append(f"  VWAP by hand {d.date()} (5-minute bars 18:00-09:25, {len(r5)} bars): VWAP {m_:.4f} sigma {s_:.4f} "
                   f"|  levels() vw {t.vw:.4f}, (vw2u - vw) / 2 {(t.vw2u - t.vw) / 2:.4f}  -> diff "
                   f"{abs(m_ - t.vw):.2e}, {abs(s_ - (t.vw2u - t.vw) / 2):.2e}")
    mvv = moving_values(ctx)
    i5 = b.i_last.to_numpy()
    k = np.flatnonzero((ctx.tod == 575) & (ctx.dayn >= 0))    # 09:35 bars: the 09:30 5-minute bar has just closed
    m5 = np.searchsorted(b.i_first.to_numpy(), k, "right") - 2
    good = (i5[m5] == k - 1)
    out.append(f"moving value in force during the 09:35 bar = VWAP at the close of the 09:30 5-minute bar: "
               f"{int((mvv['vw'][k][good] == w.vw.to_numpy()[m5][good]).sum())} of {int(good.sum())} days;  "
               f"+2 sigma band likewise: {int((mvv['vw2u'][k][good] == (w.vw + 2 * w.sd).to_numpy()[m5][good]).sum())}")
    return out


def counts(ctx):
    lv = levels(ctx)
    ok = set(ok_days(ctx))
    x = lv[lv.date.isin(ok)]
    nd = len(ok)
    out = [f"study days {nd} (cash days {len(ctx.days)}, roll day or the day after {len(ctx.roll2_dates)}, "
           f"no ATR {len(ctx.noatr_dates)})"]
    real = x[~x.is_placebo]
    g = real.groupby("group", sort=False).size() / nd
    out.append("real levels per day by group: " + ", ".join(f"{k} {v:.2f}" for k, v in g.items()))
    pl = x[x.is_placebo]
    out.append(f"placebos: made {len(pl)}, dropped {int(pl.dropped.sum())}, kept {int((~pl.dropped).sum())} "
               f"({(~pl.dropped).sum() / nd:.1f} a day); kept ones within 0.03 x ATR of a later-fixed real static "
               f"level (the opening range): {int(pl.near_later.sum())}")
    out.append(f"static levels `used` (set before 09:30): real {int(real[real.kind == 'static'].used.sum())} of "
               f"{int((real.kind == 'static').sum())}, placebo {int(pl[~pl.dropped].used.sum())} of {int((~pl.dropped).sum())}")
    return out


def causal(ctx_bars, n=60, seed=3, back_days=40, fwd_days=3):
    """Each sampled level (stratified over the codes, placebos included) is recomputed on a window in which every bar
    after its own t_set is mirrored (core._reflect); its value must be identical. A level fixed at the OPEN of bar
    t_set is cut after bar t_set - 1 with that one open kept. Static levels watched from 09:30 are cut a second time
    after the last bar before 09:30 (the 09:30 open kept: it defines r100): value, `used` and `dropped` must be
    identical (a placebo exists or not only once every real level of its watch start is known). Opening-range
    placebos: `dropped` is compared at the first cut (09:44). Moving levels: the value in force during a sampled bar
    k, with everything after bar k - 1 mirrored."""
    full = core.Ctx(ctx_bars)
    lv = levels(full)
    ok = set(ok_days(full))
    x = lv[lv.date.isin(ok) & (lv.date > full.days.index[60]) & (lv.w0 <= lv.w1)]
    rng = np.random.default_rng(seed)
    codes = list(dict.fromkeys(x.code))
    per = max(1, n // len(codes))
    bad = tested = 0
    res = {}

    def run_cut(T, keep_open, date):
        end = max(T + pd.Timedelta(days=fwd_days), core.Ctx._wall(date, 0) + pd.Timedelta(days=2))
        w = ctx_bars[(ctx_bars.index >= T - pd.Timedelta(days=back_days)) & (ctx_bars.index < end)]
        m = core._reflect(w, T)
        if keep_open is not None:
            m.loc[keep_open, "open"] = w.loc[keep_open, "open"]
        return core.Ctx(w), core.Ctx(m)

    def row(l, r):
        a = l[(l.date == r.date) & (l.lid == r.lid)]
        return a.iloc[0] if len(a) == 1 else None

    for code in codes:
        xs = x[x.code == code]
        for k in rng.choice(len(xs), min(per, len(xs)), replace=False):
            r = xs.iloc[int(k)]
            i_open = int(full.days.i_open[r.date])
            if r.kind == "moving":
                kb = int(rng.integers(r.w0, r.w1 + 1))
                c0, c1 = run_cut(full.ts[kb - 1], None, r.date)
                t = full.ts[kb]
                v0, v1 = moving_values(c0)[code][int(c0.pos[t])], moving_values(c1)[code][int(c1.pos[t])]
                same = v0 == v1 and abs(v0 - moving_values(full)[code][kb]) < 1e-6
            else:
                ts_ = int(r.t_set)
                c0, c1 = run_cut(full.ts[ts_ - 1], full.ts[ts_], r.date) if r.open_set else run_cut(full.ts[ts_], None, r.date)
                a0, a1 = row(levels(c0), r), row(levels(c1), r)
                same = a0 is not None and a1 is not None and float(a0.value) == float(a1.value) \
                    and (r.is_placebo or abs(float(a0.value) - r.value) < 1e-6)
                if same and r.kind == "static" and int(r.w0) > i_open:
                    same = bool(a0.dropped) == bool(a1.dropped)
                if same and r.kind == "static" and int(r.w0) == i_open:
                    c0, c1 = run_cut(full.ts[i_open - 1], full.ts[i_open], r.date)
                    a0, a1 = row(levels(c0), r), row(levels(c1), r)
                    same = a0 is not None and a1 is not None and float(a0.value) == float(a1.value) \
                        and bool(a0.used) == bool(a1.used) and bool(a0.dropped) == bool(a1.dropped) \
                        and (r.is_placebo or bool(a0.used) == bool(r.used))   # a placebo's price moves with the ATR warm-up
            tested += 1
            bad += not same
            res.setdefault(code, []).append(bool(same))
    print("  " + "  ".join(f"{code} {sum(v)}/{len(v)}" for code, v in res.items()))
    print(f"level look-ahead test: {tested} levels, each recomputed with the future after its own t_set mirrored, "
          f"{bad} differ -> {'PASS' if bad == 0 else 'FAIL'}")
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
    lv = levels(ctx)
    print(f"LEV1 levels   bars {A.index[0]} -> {A.index[-1]}   rows {len(lv)}   [{time.time() - t0:.0f}s]")
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
