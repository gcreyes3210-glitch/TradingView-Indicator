#!/usr/bin/env python3
"""K-H - TTrades weekly and sequence claims (YT6_SPEC.md Part 2: claims L1, L2, L3, L4).

TTrades publishes no hit rates, so every measured rate stands next to the BASE RATE registered in the spec. Nothing
here places a trade. A condition reads completed candles only (the condition week / day has closed before the
outcome week / day opens); the outcome reads the following week / day in full, by design.

Candles (all fixed before the first run, see notes/K-H.md):
  day   the trading-day candles of tt.daily (18:00 -> 17:00, dated by the 17:00 close), in time order: "the previous
        day" / "the next day" is the neighbouring candle that exists (a holiday without a candle is skipped). The
        last candle is dropped when the data stops before its 17:00.
  week  the trading week Sunday 18:00 -> Friday 17:00 = the daily candles dated Monday .. Friday of one calendar
        week: open of the first, highest high, lowest low, close of the last.
  A week is USABLE when it has at least 4 daily candles, none of them a roll candle (tt.daily's roll flag), and the
  data reaches its Friday 17:00. W-1, W, W+1 are consecutive calendar weeks; a comparison is left out when any week
  it uses is not usable (a week of fewer than 4 candles is treated like a roll week: it is never skipped over).
  "Trades above x" = a high >= x + 1 tick (below: a low <= x - 1 tick). "Closes above x": close > x.

side = the direction of the move the claim predicts: long / short / both (both = the two sides' counts added, for
the claim and for the base).
Rows: result["rows"]["<claim>.<series>.<side>.<outcome>.<base>"] = n, k, rate (the claim's cases), base_n, base_k,
base_rate, diff_pp, z, p (two-sided two-proportion z-test, pooled variance, claim against base). n, k, base_n,
base_k are plain counts of cases, each case keyed by its condition week / day, so they add up across time.
"""
import math
import numpy as np
import pandas as pd
import core
import tt

NAME = "TTrades weekly and sequence claims L1 L2 L3 L4, each rate next to its base rate"
T = core.TICK
N_TESTS = 8
WD = ("Mon", "Tue", "Wed", "Thu", "Fri")

LEGEND = {
    "side": "the direction of the move the claim predicts. L1 long = close above the previous week's high; L2 short "
            "= failed run above the previous week's high; L3 long = closes above the previous day's high; L4 short = "
            "UP week whose Friday is claimed to retrace down (the version written in the spec), L4 long = DOWN week "
            "whose Friday is claimed to retrace up (the mirror).",
    "L1.wk.<side>.beyond.all": "long: close(W) > high(W-1) -> W+1 trades above high(W). short: close(W) < low(W-1) -> "
                               "W+1 trades below low(W). Base: every week W (with W-1, W, W+1 usable).",
    "L2.wk.<side>.beyond_w.all": "short: W trades above high(W-1), close(W) < high(W-1), W does not trade below "
                                 "low(W-1) -> W+1 trades below low(W). long: W trades below low(W-1), close(W) > "
                                 "low(W-1), W does not trade above high(W-1) -> W+1 trades above high(W). Base: every "
                                 "week W.",
    "L2.wk.<side>.beyond_prev.all": "same condition -> short: W+1 trades below low(W-1); long: W+1 trades above "
                                    "high(W-1). Base: every week W, the same outcome.",
    "L3.day.<side>.cont.run12": "long: day D is exactly the third consecutive day that closes above the previous "
                                "day's high (D-3 did not) -> close(D+1) > high(D). short: mirror with lows. Base: "
                                "days D that are exactly the first or the second such close in a row. A fourth or "
                                "later close in a row is in neither group. Cases: D-4 .. D+1 exist, none a roll candle.",
    "L3.day.<side>.beyond.run12": "same cases -> long: D+1 trades above high(D); short: D+1 trades below low(D).",
    "L4.wk.<side>.retrace20.day_before": (
        "'Monday-Thursday' = the week's daily candles DATED Monday, Tuesday, Wednesday, Thursday (trading date = the "
        "date of the 17:00 close; the Monday candle opens Sunday 18:00) THAT EXIST. A missing Monday, Tuesday or "
        "Wednesday candle (holiday) is simply absent from the range: no other day takes its place. The week is a "
        "case only when BOTH its Thursday-dated and its Friday-dated candle exist (no Thursday or no Friday candle = "
        "no case). H, L = highest high / lowest low of those Monday-Thursday candles, R = H - L. "
        "short (up week, as written): the first of those candles to show L is dated Monday or Tuesday, and "
        "close(Thursday) >= H - 0.25 R -> low(Friday) <= H - 0.20 R. long (down week, mirror): the first candle to "
        "show H is dated Monday or Tuesday, and close(Thursday) <= L + 0.25 R -> high(Friday) >= L + 0.20 R. "
        "Base (base_n, base_k) = the same test one day earlier: 'Monday-Wednesday' = the candles dated Monday, "
        "Tuesday, Wednesday that exist, both the Wednesday-dated and the Thursday-dated candle must exist (Friday "
        "need not), extreme first shown Monday or Tuesday, Wednesday close in the top (bottom) quarter of that range "
        "-> Thursday trades down (up) to 20 % of that range from its high (low). Usable weeks only. at_close / "
        "base_at_close = cases in which the condition day's close is already at or beyond the level."),
    "L3_positions": "not registered, description only: eligible days by their position in a run of continuation "
                    "closes in the side's direction (0 = not such a close, 4+ = fourth or later), with the two L3 "
                    "outcomes on the next day.",
}


# ------------------------------------------------------------------ statistics (as k_G.py)
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
    """sides = {"long": (n, k, base_n, base_k[, extras]), "short": (...)}: adds the long, short and both rows."""
    tot, ext = np.zeros(4, np.int64), {}
    for side in ("long", "short"):
        c = np.array(sides[side][:4], np.int64)
        e = sides[side][4] if len(sides[side]) > 4 else {}
        rows[f"{stem}.{side}.{outcome}.{base}"] = _stat(*c, **e)
        tot += c
        for a, b in e.items():
            ext[a] = ext.get(a, 0) + int(b)
    rows[f"{stem}.both.{outcome}.{base}"] = _stat(*tot, **ext)


def _sh(a, j):
    """a shifted so that out[k] = a[k - j] (j > 0: j candles earlier; j < 0: later). Edges: NaN / False."""
    out = np.zeros(len(a), bool) if a.dtype == bool else np.full(len(a), np.nan)
    if j > 0:
        out[j:] = a[:-j]
    elif j < 0:
        out[:j] = a[-j:]
    else:
        out[:] = a
    return out


def _wall(date, hour=17):
    return (pd.Timestamp(date).normalize() + pd.Timedelta(hours=hour)).tz_localize(core.TZ)


# ------------------------------------------------------------------ candles
def days(ctx):
    """tt.daily's candles (a copy), in order, without the last one when the data stops before its 17:00.
    Returns (DataFrame, number of candles dropped as unfinished)."""
    D = tt.daily(ctx).copy()
    dropped = 0
    if len(D) and ctx.cut < _wall(D.index[-1]):
        D, dropped = D.iloc[:-1], 1
    D["roll"] = D.roll.astype(bool)
    return D, dropped


def weeks(ctx):
    """One row per calendar week (indexed by its Monday) from the first to the last week that holds a daily candle.
    n = daily candles dated Monday .. Friday; open / high / low / close; roll = holds a roll candle; unfinished = the
    data stops before its Friday 17:00; usable; h0..h4 / l0..l4 / c0..c4 = the candle dated Monday .. Friday (NaN =
    no such candle). Also returns the number of candles dated Saturday or Sunday (they belong to no week)."""
    D, _ = days(ctx)
    wd = D.index.dayofweek.to_numpy()
    mon = (D.index - pd.to_timedelta(wd, unit="D")).normalize()
    inw = wd <= 4
    grid = pd.date_range(mon[inw].min(), mon[inw].max(), freq="7D")
    W = pd.DataFrame(index=grid, columns=["n", "open", "high", "low", "close", "roll"], dtype=float)
    W["n"], W["roll"] = 0, False
    for x in "hlc":
        for j in range(5):
            W[f"{x}{j}"] = np.nan
    pos = {m: i for i, m in enumerate(grid)}
    n = np.zeros(len(grid), int)
    o, h, l, c = (np.full(len(grid), np.nan) for _ in range(4))
    roll = np.zeros(len(grid), bool)
    day = {x: np.full((len(grid), 5), np.nan) for x in "hlc"}
    for k in range(len(D)):                                     # candles are in time order
        if not inw[k]:
            continue
        i, r = pos[mon[k]], D.iloc[k]
        if n[i] == 0:
            o[i], h[i], l[i] = r.open, r.high, r.low
        else:
            h[i], l[i] = max(h[i], r.high), min(l[i], r.low)
        c[i] = r.close
        n[i] += 1
        roll[i] |= bool(r.roll)
        day["h"][i, wd[k]], day["l"][i, wd[k]], day["c"][i, wd[k]] = r.high, r.low, r.close
    W["n"], W["open"], W["high"], W["low"], W["close"], W["roll"] = n, o, h, l, c, roll
    for x in "hlc":
        for j in range(5):
            W[f"{x}{j}"] = day[x][:, j]
    W["unfinished"] = [ctx.cut < _wall(m + pd.Timedelta(days=4)) for m in grid]
    W["short"] = W.n < 4
    W["usable"] = ~W.short & ~W.roll & ~W.unfinished
    return W, int((~inw).sum())


# ------------------------------------------------------------------ L1, L2: weeks
def week_cases(W):
    """Adds to the week table: e (W-1, W, W+1 all usable), the L1 / L2 conditions on week W and the outcomes in W+1."""
    u = W.usable.to_numpy()
    h, l, c = (W[k].to_numpy(float) for k in ("high", "low", "close"))
    ph, pl, nh, nl = _sh(h, 1), _sh(l, 1), _sh(h, -1), _sh(l, -1)
    e = u & _sh(u, 1) & _sh(u, -1)
    X = W.copy()
    X["e"] = e
    X["l1_long"] = e & (c > ph)
    X["l1_short"] = e & (c < pl)
    X["l2_short"] = e & (h >= ph + T) & (c < ph) & ~(l <= pl - T)      # failed run above: bearish
    X["l2_long"] = e & (l <= pl - T) & (c > pl) & ~(h >= ph + T)       # failed run below: bullish
    X["up_w"], X["dn_w"] = nh >= h + T, nl <= l - T                     # W+1 trades above high(W) / below low(W)
    X["up_prev"], X["dn_prev"] = nh >= ph + T, nl <= pl - T             # W+1 trades above high(W-1) / below low(W-1)
    return X


def _claims_L12(rows, X, cnt):
    e = X.e.to_numpy()
    u = X.usable.to_numpy()
    bad_nb = u & ~e
    idx = np.arange(len(X))
    cnt["wk.triples"] = int(e.sum())
    cnt["wk.usable_but_neighbour_not"] = dict(
        total=int(bad_nb.sum()), first_or_last_week_of_data=int((bad_nb & ((idx == 0) | (idx == len(X) - 1))).sum()),
        weeks=[str(d.date()) for d in X.index[bad_nb]])

    def c4(cond, out):
        cond, out = X[cond].to_numpy(), X[out].to_numpy()
        return int(cond.sum()), int((cond & out).sum()), int(e.sum()), int((e & out).sum())
    _put(rows, "L1.wk", "beyond", "all", dict(long=c4("l1_long", "up_w"), short=c4("l1_short", "dn_w")))
    _put(rows, "L2.wk", "beyond_w", "all", dict(long=c4("l2_long", "up_w"), short=c4("l2_short", "dn_w")))
    _put(rows, "L2.wk", "beyond_prev", "all", dict(long=c4("l2_long", "up_prev"), short=c4("l2_short", "dn_prev")))


# ------------------------------------------------------------------ L3: days
def _run(flag):
    """Length of the run of consecutive True ending at each position."""
    out = np.zeros(len(flag), int)
    for k in range(len(flag)):
        out[k] = (out[k - 1] + 1 if k else 1) if flag[k] else 0
    return out


def day_cases(D):
    """Adds to the day table: up / dn (continuation close against the previous candle), run_up / run_dn (position in
    the run), e (D-4 .. D+1 exist and none is a roll candle), and the outcomes on D+1."""
    h, l, c = (D[k].to_numpy(float) for k in ("high", "low", "close"))
    roll = D.roll.to_numpy(bool)
    up, dn = c > _sh(h, 1), c < _sh(l, 1)
    e = np.ones(len(D), bool)
    e[:4] = False
    e[max(len(D) - 1, 0):] = False
    for j in range(-1, 5):
        e &= ~_sh(roll, j)
    X = D.copy()
    X["up"], X["dn"], X["run_up"], X["run_dn"], X["e"] = up, dn, _run(up), _run(dn), e
    X["cont_up"], X["cont_dn"] = _sh(up, -1), _sh(dn, -1)               # close(D+1) beyond D's extreme
    X["beyond_up"], X["beyond_dn"] = _sh(h, -1) >= h + T, _sh(l, -1) <= l - T
    return X


def _claim_L3(rows, X, cnt):
    e = X.e.to_numpy()
    roll = X.roll.to_numpy(bool)
    idx = np.arange(len(X))
    edge = (idx < 4) | (idx >= len(X) - 1)
    cnt["day.L3_days"] = int(e.sum())
    cnt["day.L3_left_out"] = dict(total=int((~e).sum()), first_4_or_last_candle=int(edge.sum()),
                                  roll_candle_in_window=int((~e & ~edge).sum()))
    pos_tab = {}
    for side, run, oc, ob in (("long", "run_up", "cont_up", "beyond_up"), ("short", "run_dn", "cont_dn", "beyond_dn")):
        r, cont, bey = X[run].to_numpy(), X[oc].to_numpy(), X[ob].to_numpy()
        pos_tab[side] = {}
        for name, m in (("0", r == 0), ("1", r == 1), ("2", r == 2), ("3", r == 3), ("4+", r >= 4)):
            m = e & m
            pos_tab[side][name] = dict(n=int(m.sum()), k_cont=int((m & cont).sum()), k_beyond=int((m & bey).sum()))
    for o, kk in (("cont", "k_cont"), ("beyond", "k_beyond")):
        sides = {}
        for side in ("long", "short"):
            p = pos_tab[side]
            sides[side] = (p["3"]["n"], p["3"][kk], p["1"]["n"] + p["2"]["n"], p["1"][kk] + p["2"][kk])
        _put(rows, "L3.day", o, "run12", sides)
    return pos_tab


# ------------------------------------------------------------------ L4: inside the week
def _ticks(x):
    return int(round(x / T))


def l4_case(w, last, out):
    """w = a row of the week table. last = the weekday (0 = Monday) whose close is tested, out = the outcome weekday.
    None when either candle is missing. Else a dict: used (weekdays in the range), H, L (ticks), and per side
    (condition, outcome, the condition day's close already at or beyond the level). Integer ticks throughout:
    top quarter: 4 (close - L) >= 3 R; down to 20 % below the high: 5 (H - low) >= R."""
    if np.isnan(w[f"c{last}"]) or np.isnan(w[f"c{out}"]):
        return None
    used = [d for d in range(last + 1) if not np.isnan(w[f"c{d}"])]
    hi = {d: _ticks(w[f"h{d}"]) for d in used}
    lo = {d: _ticks(w[f"l{d}"]) for d in used}
    H, L = max(hi.values()), min(lo.values())
    R = H - L
    if R <= 0:
        return None
    d_lo = min(d for d in used if lo[d] == L)                   # the first candle that shows the range's low
    d_hi = min(d for d in used if hi[d] == H)
    c, oh, ol = _ticks(w[f"c{last}"]), _ticks(w[f"h{out}"]), _ticks(w[f"l{out}"])
    return dict(used=used, H=H, L=L, d_lo=d_lo, d_hi=d_hi,
                short=(d_lo <= 1 and 4 * (c - L) >= 3 * R, 5 * (H - ol) >= R, 5 * (H - c) >= R),
                long=(d_hi <= 1 and 4 * (H - c) >= 3 * R, 5 * (oh - L) >= R, 5 * (c - L) >= R))


def l4_table(W):
    """One row per usable week: the claim test (Thursday -> Friday) and the base test (Wednesday -> Thursday)."""
    recs = []
    for m, w in W[W.usable].iterrows():
        r = dict(week=m)
        for tag, last, out in (("claim", 3, 4), ("base", 2, 3)):
            x = l4_case(w, last, out)
            r[f"{tag}_ok"] = x is not None
            r[f"{tag}_days"] = len(x["used"]) if x else 0
            for side in ("long", "short"):
                cond, o, at = x[side] if x else (False, False, False)
                r[f"{tag}_{side}"], r[f"{tag}_{side}_out"], r[f"{tag}_{side}_at"] = bool(cond), bool(o), bool(at)
        recs.append(r)
    return pd.DataFrame(recs).set_index("week")


def _claim_L4(rows, W, cnt):
    L = l4_table(W)
    cnt["wk.L4"] = dict(
        usable_weeks=int(len(L)),
        claim_weeks=int(L.claim_ok.sum()), claim_no_thursday_or_friday_candle=int((~L.claim_ok).sum()),
        claim_weeks_range_of_fewer_than_4_candles=int((L.claim_ok & (L.claim_days < 4)).sum()),
        base_weeks=int(L.base_ok.sum()), base_no_wednesday_or_thursday_candle=int((~L.base_ok).sum()),
        base_weeks_range_of_fewer_than_3_candles=int((L.base_ok & (L.base_days < 3)).sum()),
        weeks_not_a_claim_case=[str(d.date()) for d in L.index[~L.claim_ok]],
        weeks_not_a_base_case=[str(d.date()) for d in L.index[~L.base_ok]])
    sides = {}
    for side in ("long", "short"):
        c, b = L[f"claim_{side}"].to_numpy(), L[f"base_{side}"].to_numpy()
        sides[side] = (c.sum(), (c & L[f"claim_{side}_out"].to_numpy()).sum(),
                       b.sum(), (b & L[f"base_{side}_out"].to_numpy()).sum(),
                       dict(at_close=(c & L[f"claim_{side}_at"].to_numpy()).sum(),
                            base_at_close=(b & L[f"base_{side}_at"].to_numpy()).sum()))
    _put(rows, "L4.wk", "retrace20", "day_before", sides)


# ------------------------------------------------------------------ entry points
def measure(ctx):
    D, unfinished_day = days(ctx)
    W, weekend = weeks(ctx)
    rows, cnt = {}, {}
    off_grid = int(sum((np.abs(D[k] / T - np.rint(D[k] / T)) > 1e-6).sum() for k in ("open", "high", "low", "close")))
    cnt["day"] = dict(candles=int(len(D)), roll_candles=int(D.roll.sum()), last_candle_unfinished_dropped=unfinished_day,
                      dated_saturday_or_sunday=weekend, prices_off_the_tick_grid=off_grid,
                      roll_dates=[str(d.date()) for d in D.index[D.roll]])
    sh, ro = W.short.to_numpy(), W.roll.to_numpy()
    cnt["wk"] = dict(calendar_weeks=int(len(W)), fewer_than_4_candles=int(sh.sum()), with_roll_candle=int(ro.sum()),
                     both=int((sh & ro).sum()), unfinished_at_end_of_data=int(W.unfinished.sum()),
                     usable=int(W.usable.sum()), usable_with_4_candles=int((W.usable & (W.n == 4)).sum()),
                     weeks_fewer_than_4=[f"{d.date()} ({int(n)})" for d, n in zip(W.index[sh], W.n[sh])],
                     weeks_with_roll=[str(d.date()) for d in W.index[ro]])
    _claims_L12(rows, week_cases(W), cnt)
    pos_tab = _claim_L3(rows, day_cases(D), cnt)
    _claim_L4(rows, W, cnt)
    return dict(claim="TTrades weekly and sequence claims (YT6_SPEC.md Part 2), each rate next to its base rate",
                span=f"{ctx.ts[0].date()} -> {ctx.ts[-1].date()}", key="<claim>.<series>.<side>.<outcome>.<base>",
                bonferroni=0.05 / N_TESTS, legend=LEGEND, counts=cnt, rows=rows, L3_positions=pos_tab)


def show(res):
    print(res["claim"], "  ", res["span"])
    c = res["counts"]
    d, w, l4 = c["day"], c["wk"], c["wk.L4"]
    print(f"  day  candles {d['candles']} (roll {d['roll_candles']}, unfinished last candle dropped "
          f"{d['last_candle_unfinished_dropped']}, dated Sat/Sun {d['dated_saturday_or_sunday']}, prices off the tick "
          f"grid {d['prices_off_the_tick_grid']})")
    print(f"       L3 days {c['day.L3_days']}; left out {c['day.L3_left_out']}")
    print(f"  week calendar weeks {w['calendar_weeks']}: fewer than 4 candles {w['fewer_than_4_candles']} "
          f"{w['weeks_fewer_than_4']}, with a roll candle {w['with_roll_candle']} (both {w['both']}), unfinished "
          f"{w['unfinished_at_end_of_data']}; usable {w['usable']} (of them with 4 candles {w['usable_with_4_candles']})")
    print(f"       roll weeks {w['weeks_with_roll']}")
    nb = c["wk.usable_but_neighbour_not"]
    print(f"       L1 / L2 weeks W with W-1, W, W+1 usable: {c['wk.triples']}; usable but a neighbour is not: "
          f"{nb['total']} (first / last week of the data {nb['first_or_last_week_of_data']})")
    print(f"       L4 claim weeks {l4['claim_weeks']} (no Thursday or Friday candle {l4['claim_no_thursday_or_friday_candle']} "
          f"{l4['weeks_not_a_claim_case']}; range of fewer than 4 candles {l4['claim_weeks_range_of_fewer_than_4_candles']}); "
          f"base weeks {l4['base_weeks']} (no Wednesday or Thursday candle {l4['base_no_wednesday_or_thursday_candle']} "
          f"{l4['weeks_not_a_base_case']}; range of fewer than 3 candles {l4['base_weeks_range_of_fewer_than_3_candles']})")
    print(f"  * = p < 0.05 / {N_TESTS} = {res['bonferroni']:.5f}")
    print(f"  {'key':<38} {'n':>6} {'k':>6} {'rate':>6}   {'base n':>6} {'base k':>6} {'base':>6}  {'diff pp':>7}  {'p':>8}")
    last = None
    for k, r in res["rows"].items():
        if k[:2] != last:
            print()
            last = k[:2]
        rate = f"{r['rate']:.1%}" if r["rate"] is not None else "   -  "
        base = f"{r['base_rate']:.1%}" if r["base_rate"] is not None else "   -  "
        diff = f"{r['diff_pp']:+.1f}" if r["diff_pp"] is not None else "  -  "
        p = f"{r['p']:.4f}" if r["p"] is not None else "   -   "
        star = "*" if r["p"] is not None and r["p"] < res["bonferroni"] else " "
        at = f"   already there at the close {r['at_close']} / {r['base_at_close']}" if "at_close" in r else ""
        print(f"  {k:<38} {r['n']:>6} {r['k']:>6} {rate:>6}   {r['base_n']:>6} {r['base_k']:>6} {base:>6}  {diff:>7}  {p:>8}{star}{at}")
    print("\n  L3 by position in the run (not registered, description): n, next day another continuation close, next "
          "day trades beyond")
    for side in ("long", "short"):
        t = res["L3_positions"][side]
        print(f"  {side:<6}" + "".join(
            f"  {p}: {v['n']} / {v['k_cont']} / {v['k_beyond']}" + (f" ({v['k_cont'] / v['n']:.0%}, {v['k_beyond'] / v['n']:.0%})" if v["n"] else "")
            for p, v in t.items()))
