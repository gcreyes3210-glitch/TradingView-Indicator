#!/usr/bin/env python3
"""FLOW3 - footprint and order flow at the hourly add (YT7_SPEC.md, Part 2).

    trades(ctx)            every YT6 pick 1 trade (s_G9 variant `base`, run on ctx's bars) with its signal bar, the
                           first bar of the CISD's run, the decision bar, the overnight level it broke, whether an
                           ORB v1.4 trade (cal_orb) was open on its side at the entry (`aligned` = a G10 base trade)
                           and whether the order-flow tables cover 09:30 -> decision (`has_flow`).
    measures(ctx, tr)      the eleven measures of the spec table for the trades with flow (NaN elsewhere / where the
                           spec says missing). Only rows that END at or before the decision time are read.
    python3 tools/yt1/flow3.py --phase is      trades to 2022-12-31: thresholds (in-sample medians), sides, the two
                                               picks -> is/FLOW3_trades.csv, is/FLOW3_table.csv, FLOW3_selected.json
    python3 tools/yt1/flow3.py --phase full    the frozen thresholds and picks on 2023-01-01 -> last flow day
                                               -> full/FLOW3_table.csv, full/FLOW3_oos.json. Selects nothing.
    python3 tools/yt1/flow3.py --check         the measures recomputed with every later row / bar deleted
    --dry-split DATE --dry-out DIR             code test only: both phases on a made-up split inside the data that is
                                               here, written to DIR (never to data/studies/yt1)

Times. Every bar and flow row is stamped with its OPEN time, New York. The decision bar is the last 1-minute bar
before the entry bar (stamped 09:59 or 10:59); the decision time is its end (10:00:00 / 11:00:00) = `end` below.
A 1-minute flow row is used when stamp + 1 min <= end, a 5-minute footprint bar when stamp + 5 min <= end, a
30-second bar when stamp + 30 s <= end; nothing stamped before 09:30 is used (19 in-sample days carry a 09:29 row).

Measures (side = +1 long / -1 short; N = NQ_flow_1m rows 09:30 -> decision; F = NQ_footprint_5m rows of the completed
5-minute bars 09:30 -> decision, volume = buy + sell). Readings marked (R) are listed in notes/FLOW3.md.
    cum        side x sum(delta) / sum(volume) over N
    last15     the same over the last 15 one-minute rows of N (decision minute - 14 ... decision minute)
    pull       the same over the rows from max(first bar of the CISD's run, 09:30) through the signal bar
    since      the same over the rows after the signal bar through the decision; NaN when the signal bar is the
               decision bar
    es_cum     cum on ES_flow_1m
    div        cum - es_cum
    vol_rel    volume of the last 15 rows / (volume of N / (minutes from 09:30 to the decision / 15))
    poc        (decision close - POC) x side / (highest - lowest price of F); POC = the price of F with the most
               volume (the lowest on ties, the house rule of tools/ivc_engine.py); decision close = the close of the
               last NQ 30-second bar that ends at or before the decision time (an NQ price against an NQ price)
    stack      over the last three completed footprint bars: the longest run of stacked buy imbalances in any of
               them and the longest run of sell imbalances in any of them (house definition, tools/flow2.py stack());
               value = the run on the trade's side minus the run against it
    brk_delta  rows of F priced beyond the broken overnight level (price > overnight high for a long, price <
               overnight low for a short): side x (buy - sell) / (buy + sell); NaN when nothing traded there
    brk_share  volume of those rows / volume of F
The overnight level is the 18:00 -> 08:29 high / low of the MNQ continuous bars (the level the YT6 signal tested),
used as it is on NQ prices; `basis` (median NQ - MNQ 1-minute close, 09:30 -> decision) is a diagnostic column.
"""
import argparse, hashlib, json, pathlib, sys, time
import numpy as np
import pandas as pd
sys.path.insert(0, str(pathlib.Path(__file__).parent))
import core
import run
import s_G9
import g9_grid
import g9_signals
import cal_orb

PICK1 = "T1.Wopen.Bnone.Enone.Mnone.Rsess_brk.Hnone.Snone.X2R.Npos"     # YT6 pick 1 (G9_selected.json)
MEASURES = ["cum", "last15", "pull", "since", "es_cum", "div", "vol_rel", "poc", "stack", "brk_delta", "brk_share"]
MIN_SIDE = 25                       # a measure with fewer trades on either side is set aside
N_PICKS = 2
N_SHUFFLE, SEED, P_MAX = 20000, 1, 0.05 / 2
OOS_START = pd.Timestamp("2023-01-01")
TICK = core.TICK
MIN_NS = 60 * 10 ** 9
SEL_NAME = "FLOW3_selected.json"
SECONDARY = ("SECONDARY (reported, no picks, no verdict): all YT6 pick 1 trades with flow, aligned or not; "
             "thresholds = in-sample medians of this wider set")
PRIMARY = "aligned YT6 pick 1 trades with flow (G10 base trades on order-flow days)"


def _ns(x):
    return pd.DatetimeIndex(x).as_unit("ns").asi8


def _stamp(ns):
    return pd.Timestamp(int(ns), tz="UTC").tz_convert(core.TZ)


# ------------------------------------------------------------------ the order-flow tables
class Tables:
    """The order-flow tables of a context as time-sorted arrays (times = UTC nanoseconds of the row's OPEN)."""

    def __init__(self, nq, es, fp, b30):
        self.nq_t, self.nq_d, self.nq_v = _ns(nq.index), nq.delta.to_numpy(float), nq.volume.to_numpy(float)
        self.es_t, self.es_d, self.es_v = _ns(es.index), es.delta.to_numpy(float), es.volume.to_numpy(float)
        if len(fp) > 1 and not (np.diff(_ns(fp.ts)) >= 0).all():
            fp = fp.sort_values(["ts", "price"], kind="mergesort")
        self.fp_t, self.fp_p = _ns(fp.ts), fp.price.to_numpy(float)
        self.fp_b, self.fp_s = fp.buy.to_numpy(float), fp.sell.to_numpy(float)
        self.b_t, self.b_c = _ns(b30.index), b30.close.to_numpy(float)
        for t in (self.nq_t, self.es_t, self.b_t):
            assert (np.diff(t) > 0).all(), "an order-flow table is not sorted by time / has a repeated stamp"

    @classmethod
    def of(cls, ctx):
        c = ctx.__dict__
        if "_flow3_tables" not in c:
            c["_flow3_tables"] = cls(ctx.flow("NQ_flow_1m"), ctx.flow("ES_flow_1m"), ctx.flow("NQ_footprint_5m"),
                                     ctx.flow("NQ_bars_30s"))
        return c["_flow3_tables"]

    def deleted_after(self, end):
        """A copy that holds no row ending after `end` (ns): what exists at that moment. For the causality check."""
        o = object.__new__(Tables)
        a = int(np.searchsorted(self.nq_t, end - MIN_NS, "right"))
        o.nq_t, o.nq_d, o.nq_v = self.nq_t[:a].copy(), self.nq_d[:a].copy(), self.nq_v[:a].copy()
        a = int(np.searchsorted(self.es_t, end - MIN_NS, "right"))
        o.es_t, o.es_d, o.es_v = self.es_t[:a].copy(), self.es_d[:a].copy(), self.es_v[:a].copy()
        a = int(np.searchsorted(self.fp_t, end - 5 * MIN_NS, "right"))
        o.fp_t, o.fp_p, o.fp_b, o.fp_s = (x[:a].copy() for x in (self.fp_t, self.fp_p, self.fp_b, self.fp_s))
        a = int(np.searchsorted(self.b_t, end - MIN_NS // 2, "right"))
        o.b_t, o.b_c = self.b_t[:a].copy(), self.b_c[:a].copy()
        return o

    # rows of the day's session that END at or before `end`
    def minutes(self, sym, t0, end):
        t, d, v = (self.nq_t, self.nq_d, self.nq_v) if sym == "NQ" else (self.es_t, self.es_d, self.es_v)
        a, b = int(np.searchsorted(t, t0, "left")), int(np.searchsorted(t, end - MIN_NS, "right"))
        return t[a:b], d[a:b], v[a:b]

    def footprint(self, t0, end):
        a, b = int(np.searchsorted(self.fp_t, t0, "left")), int(np.searchsorted(self.fp_t, end - 5 * MIN_NS, "right"))
        return self.fp_t[a:b], self.fp_p[a:b], self.fp_b[a:b], self.fp_s[a:b]

    def last_close(self, t0, end):
        """Close of the last NQ 30-second bar stamped at or after t0 that ends at or before `end` (NaN: none)."""
        a, b = int(np.searchsorted(self.b_t, t0, "left")), int(np.searchsorted(self.b_t, end - MIN_NS // 2, "right"))
        return float(self.b_c[b - 1]) if b > a else np.nan

    def minute_closes(self, t0, end):
        """(minute stamp, NQ close of that minute) from the 30-second bars that end at or before `end`."""
        a, b = int(np.searchsorted(self.b_t, t0, "left")), int(np.searchsorted(self.b_t, end - MIN_NS // 2, "right"))
        m = self.b_t[a:b] // MIN_NS * MIN_NS
        last = np.r_[m[1:] != m[:-1], True] if b > a else np.zeros(0, bool)
        return m[last], self.b_c[a:b][last]


# ------------------------------------------------------------------ trades
def signal_rows(ctx):
    """The day's one order row of YT6 pick 1 per cash day (g9_grid.pick on g9_signals.build), as s_G9.orders uses."""
    p = s_G9.VARIANTS["base"]
    assert p["c"] == PICK1 and p["nb"] == 0, "s_G9 `base` is not YT6 pick 1"
    combo, _, md = s_G9.params(p["c"], p["nb"])
    return g9_grid.pick(g9_signals.build(ctx, tfs=(combo["T"],)), combo, md=md)


def flow_cover(ctx, T, day, end):
    """(on_flow_day, has_flow, note) for a decision time `end` (ns) on cash date `day`.
    on_flow_day: NQ_flow_1m has a row stamped 09:30 or later on that date.
    has_flow:    every minute 09:30 -> decision has a row in NQ_flow_1m and in ES_flow_1m, every completed 5-minute
                 bar 09:30 -> decision is in NQ_footprint_5m, and an NQ 30-second bar ends in that span."""
    t0 = ctx._wall(day, 570).value
    t1 = ctx._wall(day, 960).value
    a, b = np.searchsorted(T.nq_t, [t0, t1])
    if b <= a:
        return False, False, ""
    n_min = int((end - t0) // MIN_NS)
    nq_t, _, _ = T.minutes("NQ", t0, end)
    es_t, _, _ = T.minutes("ES", t0, end)
    f_t = T.footprint(t0, end)[0]
    n_fp = len(np.unique(f_t))
    c = T.last_close(t0, end)
    why = []
    if len(nq_t) != n_min:
        why.append(f"NQ minutes {len(nq_t)}/{n_min}")
    if len(es_t) != n_min:
        why.append(f"ES minutes {len(es_t)}/{n_min}")
    if n_fp != n_min // 5:
        why.append(f"NQ footprint bars {n_fp}/{n_min // 5}")
    if c != c:
        why.append("no NQ 30-second bar")
    return True, not why, "; ".join(why)


def basis_of(ctx, T, day, end):
    """Median of (NQ 1-minute close - MNQ 1-minute close) over the minutes 09:30 -> decision that have both."""
    t0 = ctx._wall(day, 570).value
    m, c = T.minute_closes(t0, end)
    lo, hi = int(np.searchsorted(ctx._flow3_ns, t0, "left")), int(np.searchsorted(ctx._flow3_ns, end - MIN_NS, "right"))
    _, ia, ib = np.intersect1d(m, ctx._flow3_ns[lo:hi], return_indices=True)
    return float(np.median(c[ia] - ctx.C[lo:hi][ib])) if len(ia) else np.nan


def orb_trades(ctx):
    """ORB v1.4 inside the harness, as cal_orb's main runs it."""
    return core.trades_df(core.run_orders(ctx, cal_orb.orders(ctx), skip_roll=False))


def trades(ctx):
    """YT6 pick 1 trades on ctx's bars, one row each:
    day, side (L / S), sgn, sig_time (the CISD bar), run_time (first bar of the CISD's run), dec_time (the last
    1-minute bar before the entry bar; the decision time is its end), entry_time, entry, stop, level (the overnight
    high a long broke / low a short broke, 18:00 -> 08:29, MNQ), exit_time, exit, reason, pnl, R, win (pnl > 0),
    orb (none / later / closed / opposite / aligned), orb_side, orb_entry_time, orb_exit_time, orb_edge (ORB filled
    at the close of the bar just before the entry bar), aligned, on_flow_day, has_flow, flow_note, basis."""
    if "_flow3_ns" not in ctx.__dict__:
        ctx._flow3_ns = _ns(ctx.ts)
    T = Tables.of(ctx)
    t = core.trades_df(s_G9.trades(ctx, **s_G9.VARIANTS["base"]))
    rows = signal_rows(ctx).set_index("i")
    orb = orb_trades(ctx)
    orb_day = {}
    for o in orb.itertuples(index=False):
        d = ctx.cdate[o.j]
        assert d not in orb_day, "two ORB trades on one day"
        orb_day[d] = o
    out = []
    for r in t.itertuples(index=False):
        si = int(r.tag.split("|")[-1])                           # the signal (CISD) bar
        s = rows.loc[si]
        sgn = 1 if r.side == "L" else -1
        assert int(s.side) == sgn and float(s.stop) == float(r.stop) and si <= r.i < r.j
        level = float(s.a_sessx)
        assert (float(s.prot) - level) * sgn > 0, "the protected level is not beyond the overnight level"
        i0 = int(s.a_run0)
        assert i0 <= si
        day = pd.Timestamp(ctx.cdate[r.j])
        o = orb_day.get(ctx.cdate[r.j])
        if o is None:
            state = "none"
        elif not o.j < r.j:
            state = "later"                                      # ORB filled at or after the entry bar
        elif not o.k >= r.j:
            state = "closed"                                     # ORB's exit bar is before the entry bar
        else:
            state = "aligned" if o.side == r.side else "opposite"
        end = ctx._flow3_ns[r.i] + MIN_NS                        # the decision time: the end of the decision bar
        on_day, has, note = flow_cover(ctx, T, day, end)
        out.append(dict(
            day=day.strftime("%Y-%m-%d"), side=r.side, sgn=sgn, sig_time=ctx.ts[si], run_time=ctx.ts[i0],
            dec_time=ctx.ts[r.i], entry_time=r.entry_time, entry=r.entry, stop=r.stop, level=level,
            exit_time=r.exit_time, exit=r.exit, reason=r.reason, pnl=r.pnl, R=r.R, win=bool(r.pnl > 0),
            orb=state, orb_side=o.side if o is not None else "", orb_entry_time=o.entry_time if o is not None else pd.NaT,
            orb_exit_time=o.exit_time if o is not None else pd.NaT,
            orb_edge=bool(o is not None and o.j == r.j - 1), aligned=state == "aligned",
            on_flow_day=on_day, has_flow=has, flow_note=note,
            basis=basis_of(ctx, T, day, end) if has else np.nan))
    df = pd.DataFrame(out)
    for c in ("orb_entry_time", "orb_exit_time"):
        df[c] = pd.to_datetime(df[c], utc=True).dt.tz_convert(core.TZ)
    return df.sort_values("entry_time", kind="mergesort").reset_index(drop=True)


# ------------------------------------------------------------------ measures
def _ratio(d, v):
    s = v.sum()
    return float(d.sum() / s) if s > 0 else np.nan


def longest_runs(price, buy, sell):
    """(longest run of buy imbalances, longest run of sell imbalances) of one footprint bar, as tools/flow2.py stack():
    on the tick grid from the bar's lowest to its highest price (an untraded tick holds 0 / 0),
        buy imbalance at p   buy(p) >= 3 x max(sell(p - 1 tick), 1)     (not at the lowest price)
        sell imbalance at p  sell(p) >= 3 x max(buy(p + 1 tick), 1)     (not at the highest price)
    a run = imbalances of one kind at consecutive ticks."""
    if len(price) == 0:
        return 0, 0
    k = np.rint((price - price.min()) / TICK).astype(np.int64)
    b, s = np.zeros(int(k.max()) + 1), np.zeros(int(k.max()) + 1)
    np.add.at(b, k, buy)
    np.add.at(s, k, sell)
    out = []
    for imb in (np.r_[False, b[1:] >= 3 * np.maximum(s[:-1], 1)], np.r_[s[:-1] >= 3 * np.maximum(b[1:], 1), False]):
        best = cur = 0
        for v in imb:
            cur = cur + 1 if v else 0
            best = max(best, cur)
        out.append(best)
    return out[0], out[1]


def measure_one(T, sgn, t0, t_run, t_sig, t_dec, level, detail=None):
    """The eleven measures of one trade. Times are ns stamps (bar opens): t0 = 09:30 of the day, t_run = first bar of
    the CISD's run, t_sig = the signal bar, t_dec = the decision bar. `detail` (a dict) receives the intermediate
    totals, for the worked examples."""
    end = t_dec + MIN_NS
    n_min = (end - t0) // MIN_NS
    tm, d, v = T.minutes("NQ", t0, end)
    te, de, ve = T.minutes("ES", t0, end)
    l15 = tm >= end - 15 * MIN_NS
    pl = (tm >= max(t_run, t0)) & (tm <= t_sig)
    sn = tm > t_sig
    cum = sgn * _ratio(d, v)
    es_cum = sgn * _ratio(de, ve)
    avg15 = v.sum() / (n_min / 15.0)
    m = dict(cum=cum, last15=sgn * _ratio(d[l15], v[l15]), pull=sgn * _ratio(d[pl], v[pl]),
             since=sgn * _ratio(d[sn], v[sn]) if sn.any() else np.nan, es_cum=es_cum, div=cum - es_cum,
             vol_rel=float(v[l15].sum() / avg15) if avg15 > 0 else np.nan)
    ft, p, b, s = T.footprint(t0, end)
    vol = b + s
    traded = vol > 0
    close = T.last_close(t0, end)
    if traded.any():
        up, inv = np.unique(p[traded], return_inverse=True)
        pv = np.bincount(inv, weights=vol[traded])
        poc_px = float(up[int(pv.argmax())])                     # ascending prices: the lowest on ties
        rng = float(up[-1] - up[0])
        m["poc"] = (close - poc_px) * sgn / rng if rng > 0 else np.nan
        bey = (p > level) if sgn > 0 else (p < level)
        bb, bs = float(b[bey].sum()), float(s[bey].sum())
        m["brk_delta"] = sgn * (bb - bs) / (bb + bs) if bb + bs > 0 else np.nan
        m["brk_share"] = (bb + bs) / float(vol.sum())
    else:
        poc_px = rng = bb = bs = np.nan
        up, pv = np.zeros(0), np.zeros(0)
        m["poc"] = m["brk_delta"] = m["brk_share"] = np.nan
    runs = []
    for q in (3, 2, 1):                                          # the last three completed 5-minute bars
        w = ft == end - q * 5 * MIN_NS
        runs.append(longest_runs(p[w], b[w], s[w]))
    buy_run, sell_run = max(r[0] for r in runs), max(r[1] for r in runs)
    m["stack"] = float((buy_run - sell_run) * sgn)
    if detail is not None:
        detail.update(n_min=int(n_min), nq=(tm, d, v), es=(te, de, ve), l15=l15, pl=pl, sn=sn, avg15=avg15,
                      fp=(ft, p, b, s), close=close, poc_px=poc_px, range=rng, ties=int((pv == pv.max()).sum()) if len(pv) else 0,
                      lo=float(up[0]) if len(up) else np.nan, hi=float(up[-1]) if len(up) else np.nan,
                      brk_buy=bb, brk_sell=bs, fp_vol=float(vol.sum()), runs=runs, buy_run=buy_run, sell_run=sell_run)
    return m


def _times(ctx, r):
    day = pd.Timestamp(r.day)
    return (ctx._wall(day, 570).value, pd.Timestamp(r.run_time).value, pd.Timestamp(r.sig_time).value,
            pd.Timestamp(r.dec_time).value)


def measures(ctx, tr, tables=None, cut=False):
    """DataFrame (index of tr, columns MEASURES): the measures of every trade with has_flow, NaN for the others.
    cut=True: each trade is measured on a copy of the tables from which every row ending after its decision time has
    been deleted (the causality check); the result must equal the plain one."""
    T = tables or Tables.of(ctx)
    out = pd.DataFrame(np.nan, index=tr.index, columns=MEASURES)
    for ix, r in zip(tr.index, tr.itertuples(index=False)):
        if not r.has_flow:
            continue
        t0, t_run, t_sig, t_dec = _times(ctx, r)
        Tu = T.deleted_after(t_dec + MIN_NS) if cut else T
        m = measure_one(Tu, int(r.sgn), t0, t_run, t_sig, t_dec, float(r.level))
        out.loc[ix] = [m[k] for k in MEASURES]
    return out


def build(ctx):
    """trades(ctx) with the eleven measure columns."""
    tr = trades(ctx)
    return pd.concat([tr, measures(ctx, tr)], axis=1)


# ------------------------------------------------------------------ tables, selection
def _side(x):
    n, w = int(len(x)), int(x.win.sum())
    return dict(n=n, wins=w, win=w / n if n else np.nan, R=float(x.R.mean()) if n else np.nan,
                net=round(float(x.pnl.sum()), 2))


def split(df, m, thr):
    """(high, low) rows of df on measure m: high = at or above the threshold; a missing value is on neither side."""
    v = df[m].to_numpy(float)
    ok = ~np.isnan(v)
    return df[ok & (v >= thr)], df[ok & (v < thr)]


def table(df, thr, block, period):
    """One row per measure: the two sides of df at thresholds thr."""
    rows = []
    for m in MEASURES:
        hi, lo = split(df, m, thr[m])
        h, l = _side(hi), _side(lo)
        rows.append(dict(block=block, period=period, measure=m, threshold=thr[m], n=h["n"] + l["n"],
                         missing=int(len(df) - h["n"] - l["n"]),
                         n_hi=h["n"], wins_hi=h["wins"], win_hi=h["win"], R_hi=h["R"], net_hi=h["net"],
                         n_lo=l["n"], wins_lo=l["wins"], win_lo=l["win"], R_lo=l["R"], net_lo=l["net"],
                         diff=h["win"] - l["win"] if h["n"] and l["n"] else np.nan))
    return pd.DataFrame(rows)


def medians(df):
    """In-sample threshold of each measure: the median of its non-missing values."""
    out = {}
    for m in MEASURES:
        v = df[m].to_numpy(float)
        v = v[~np.isnan(v)]
        out[m] = float(np.median(v)) if len(v) else float("nan")
    return out


def rank(tb, min_side=MIN_SIDE):
    """Adds eligible (at least min_side trades on each side), better (the side with the higher win rate; `high` on a
    tie), abs_diff and rank (1 = largest absolute difference in win rate among the eligible; ties keep table order)."""
    tb = tb.copy()
    tb["eligible"] = (tb.n_hi >= min_side) & (tb.n_lo >= min_side)
    tb["better"] = np.where(tb.win_lo > tb.win_hi, "low", "high")
    tb["abs_diff"] = tb["diff"].abs()
    order = tb[tb.eligible].sort_values("abs_diff", ascending=False, kind="mergesort").index
    tb["rank"] = 0
    tb.loc[order, "rank"] = np.arange(1, len(order) + 1)
    return tb


def favourable(df, m, thr, side):
    """Boolean array: the trade is on the favourable side of measure m (False where the measure is missing)."""
    v = df[m].to_numpy(float)
    ok = ~np.isnan(v)
    return ok & ((v >= thr) if side == "high" else (v < thr))


def perm_p(win, fav, n=N_SHUFFLE, seed=SEED):
    """One-sided permutation p of (favourable win rate - unfavourable win rate): the share of n shuffles of the side
    labels whose difference is at least the observed one. With the side sizes fixed the difference grows with the
    number of wins on the favourable side, so the comparison is made on that count (no rounding)."""
    win, fav = np.asarray(win, bool), np.asarray(fav, bool)
    nf = int(fav.sum())
    if nf == 0 or nf == len(fav):
        return None
    obs = int(win[fav].sum())
    rng = np.random.default_rng(seed)
    hits = 0
    for _ in range(n // 2000):
        idx = rng.random((2000, len(win))).argsort(axis=1)[:, :nf]
        hits += int((win[idx].sum(axis=1) >= obs).sum())
    return hits / (n // 2000 * 2000)


def two_way(df, fav):
    """Favourable side against the rest: both sides' statistics, the difference in win rate and its permutation p."""
    f, u = _side(df[fav]), _side(df[~fav])
    diff = f["win"] - u["win"] if f["n"] and u["n"] else None
    return dict(fav=f, unfav=u, diff=diff, p=perm_p(df.win.to_numpy(), fav) if diff is not None else None)


def verdict(tw):
    """The registered verdict: counts if the difference is positive with p < 0.025 and the favourable side's mean R
    is above the unfavourable side's."""
    if tw["diff"] is None:
        return "does not count (a side is empty)"
    ok = tw["diff"] > 0 and tw["p"] < P_MAX and tw["fav"]["R"] > tw["unfav"]["R"]
    return "counts" if ok else "does not count"


# ------------------------------------------------------------------ output
CSV_DROP = ["sgn"]
FMT = {"threshold": "{:+.4f}".format, "win_hi": "{:.3f}".format, "win_lo": "{:.3f}".format, "R_hi": "{:+.3f}".format,
       "R_lo": "{:+.3f}".format, "net_hi": "{:+.0f}".format, "net_lo": "{:+.0f}".format, "diff": "{:+.3f}".format,
       "abs_diff": "{:.3f}".format}


def csv_text(df):
    return df.drop(columns=CSV_DROP, errors="ignore").to_csv(index=False, lineterminator="\n")


def sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


def show(tb, cols=None):
    cols = cols or ["measure", "threshold", "n", "missing", "n_hi", "wins_hi", "win_hi", "R_hi", "net_hi", "n_lo",
                    "wins_lo", "win_lo", "R_lo", "net_lo", "diff"] + [c for c in ("eligible", "better", "rank") if c in tb]
    return tb[cols].to_string(index=False, formatters=FMT)


def counts(df):
    al = df[df.aligned]
    c = dict(pick1_trades=int(len(df)), on_flow_days=int(df.on_flow_day.sum()), with_flow=int(df.has_flow.sum()),
             flow_day_not_covered=int((df.on_flow_day & ~df.has_flow).sum()),
             aligned=int(len(al)), aligned_on_flow_days=int(al.on_flow_day.sum()), aligned_with_flow=int(al.has_flow.sum()),
             orb_state={k: int(v) for k, v in df.orb.value_counts().items()},
             orb_state_with_flow={k: int(v) for k, v in df[df.has_flow].orb.value_counts().items()},
             orb_filled_on_the_bar_before_the_entry=int(df.orb_edge.sum()),
             aligned_with_orb_filled_on_the_bar_before_the_entry=int((df.orb_edge & df.aligned).sum()),
             decision_bar_not_hh59=int((pd.DatetimeIndex(df.dec_time).minute != 59).sum()),
             missing_aligned={m: int(al[al.has_flow][m].isna().sum()) for m in MEASURES},
             missing_all={m: int(df[df.has_flow][m].isna().sum()) for m in MEASURES})
    return c


def _jsonable(x):
    if isinstance(x, dict):
        return {k: _jsonable(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_jsonable(v) for v in x]
    if isinstance(x, (np.bool_, bool)):
        return bool(x)
    if isinstance(x, np.integer):
        return int(x)
    if isinstance(x, (float, np.floating)):
        return None if x != x else float(x)
    return x


def _block(tb):
    return {r.measure: {k: getattr(r, k) for k in tb.columns if k not in ("block", "period", "measure")}
            for r in tb.itertuples(index=False)}


def combined(df, picks):
    fav = np.ones(len(df), bool)
    for p in picks:
        fav &= favourable(df, p["measure"], p["threshold"], p["favourable"])
    return fav


# ------------------------------------------------------------------ phases
def phase_is(out=core.OUT, split_at=None, min_side=MIN_SIDE):
    """Search on the trades before the out-of-sample start. split_at (dry run only) = a made-up split date: the bars
    are cut there."""
    dry = split_at is not None
    if dry:
        end = pd.Timestamp(split_at)
        a = core.load_bars("MNQ", cut=end.tz_localize(core.TZ))
    else:
        end = OOS_START
        a = run.bars("is")
        assert min_side == MIN_SIDE
    ctx = core.Ctx(a)
    df = build(ctx)
    assert len(df) and pd.to_datetime(df.day).max() < end, "a trade at or after the end of the in-sample period"
    print(f"FLOW3   phase is{'  (DRY RUN on a made-up split: numbers mean nothing)' if dry else ''}   bars {ctx.ts[0]} -> "
          f"{ctx.ts[-1]}   in-sample = trades before {end.date()}")
    T = Tables.of(ctx)
    last_flow = str(_stamp(T.nq_t[-1]).date())
    c = counts(df)
    print("counts:", json.dumps(c))
    prim, sec = df[df.aligned & df.has_flow], df[df.has_flow]
    thr1, thr2 = medians(prim), medians(sec)
    t1 = rank(table(prim, thr1, "primary", "is"), min_side)
    t2 = rank(table(sec, thr2, "secondary", "is"), min_side)
    picks = []
    for r in t1[t1["rank"].between(1, N_PICKS)].sort_values("rank").itertuples(index=False):
        picks.append(dict(pick=int(r.rank), measure=r.measure, threshold=float(r.threshold), favourable=r.better,
                          is_diff_high_minus_low=float(r.diff), is_abs_diff=float(r.abs_diff),
                          is_fav=dict(n=int(r.n_hi if r.better == "high" else r.n_lo),
                                      win=float(r.win_hi if r.better == "high" else r.win_lo),
                                      R=float(r.R_hi if r.better == "high" else r.R_lo)),
                          is_unfav=dict(n=int(r.n_lo if r.better == "high" else r.n_hi),
                                        win=float(r.win_lo if r.better == "high" else r.win_hi),
                                        R=float(r.R_lo if r.better == "high" else r.R_hi))))
    t1["pick"] = t1["rank"].where(t1["rank"].between(1, N_PICKS), 0)
    t2["pick"] = 0
    print(f"\nPRIMARY: {PRIMARY}: {len(prim)} trades, {int(prim.win.sum())} wins, mean R {prim.R.mean():+.3f}, "
          f"net {prim.pnl.sum():+.0f}   (threshold = in-sample median; hi = at or above it; diff = win_hi - win_lo; "
          f"eligible = at least {min_side} a side)")
    print(show(t1))
    print("\npicks (the two eligible measures with the largest absolute difference in win rate):")
    for p in picks:
        print(f"  pick {p['pick']}: {p['measure']}  favourable side = {p['favourable']} "
              f"({'>=' if p['favourable'] == 'high' else '<'} {p['threshold']:+.6f})   in sample: favourable n "
              f"{p['is_fav']['n']} win {p['is_fav']['win']:.3f} R {p['is_fav']['R']:+.3f} | unfavourable n "
              f"{p['is_unfav']['n']} win {p['is_unfav']['win']:.3f} R {p['is_unfav']['R']:+.3f}")
    if len(picks) < N_PICKS:
        print(f"  only {len(picks)} eligible measure(s): fewer than {N_PICKS} picks")
    comb = None
    if picks:
        tw = two_way(prim, combined(prim, picks))
        comb = dict(fav=tw["fav"], rest=tw["unfav"], diff=tw["diff"])
        print(f"  both picks' favourable sides, in sample (description): n {tw['fav']['n']} win {tw['fav']['win']:.3f} "
              f"R {tw['fav']['R']:+.3f} net {tw['fav']['net']:+.0f} | the rest: n {tw['unfav']['n']} win "
              f"{tw['unfav']['win']:.3f} R {tw['unfav']['R']:+.3f} net {tw['unfav']['net']:+.0f}")
    print(f"\n{SECONDARY}: {len(sec)} trades, {int(sec.win.sum())} wins, mean R {sec.R.mean():+.3f}, net {sec.pnl.sum():+.0f}")
    print(show(t2))
    d = pathlib.Path(out) / "is"
    d.mkdir(parents=True, exist_ok=True)
    txt = csv_text(df)
    (d / "FLOW3_trades.csv").write_text(txt)
    ttxt = pd.concat([t1, t2], ignore_index=True).to_csv(index=False, lineterminator="\n")
    (d / "FLOW3_table.csv").write_text(ttxt)
    sel = dict(study="FLOW3 (YT7_SPEC.md, Part 2)", frozen=True, dry_run=dry,
               is_end=str((end - pd.Timedelta(days=1)).date()), oos_start=str(end.date()),
               bars=[str(ctx.ts[0]), str(ctx.ts[-1])], last_flow_day_in_this_data=last_flow,
               rule=dict(threshold="in-sample median of the measure over the block's trades", high="value >= threshold",
                         min_side=min_side, picks="the two eligible measures with the largest |win_hi - win_lo|; "
                         "favourable = the side with the higher in-sample win rate",
                         test=f"favourable - unfavourable win rate > 0 with one-sided permutation p < {P_MAX} "
                              f"({N_SHUFFLE} shuffles, seed {SEED}) and favourable mean R > unfavourable mean R"),
               counts=c, measures=MEASURES,
               primary=dict(label=PRIMARY, n=int(len(prim)), wins=int(prim.win.sum()), thresholds=thr1,
                            table=_block(t1), picks=picks, combined_in_sample=comb),
               secondary=dict(label=SECONDARY, n=int(len(sec)), wins=int(sec.win.sum()), thresholds=thr2,
                              table=_block(t2)),
               sha256={"is/FLOW3_trades.csv": sha(txt), "is/FLOW3_table.csv": sha(ttxt)},
               stamped_utc=pd.Timestamp.now("UTC").strftime("%Y-%m-%d %H:%M:%S"))
    sel = _jsonable(sel)
    for blk in ("primary", "secondary"):                      # thresholds must survive the JSON round trip exactly
        for m in MEASURES:
            v = (thr1 if blk == "primary" else thr2)[m]
            sel[blk]["thresholds"][m] = None if v != v else v
    p = pathlib.Path(out) / SEL_NAME
    p.write_text(json.dumps(sel, indent=1))
    back = json.loads(p.read_text())
    assert all(back["primary"]["thresholds"][m] == (None if thr1[m] != thr1[m] else thr1[m]) for m in MEASURES)
    print(f"\nwrote {d / 'FLOW3_trades.csv'} ({len(df)} trades), {d / 'FLOW3_table.csv'}, {p}")
    print(f"sha256 of the trades csv: {sel['sha256']['is/FLOW3_trades.csv']}")
    return sel


def _thr(block):
    return {m: (float("nan") if v is None else float(v)) for m, v in block["thresholds"].items()}


def phase_full(out=core.OUT, dry=False):
    """The frozen thresholds and picks on the later trades. Reads FLOW3_selected.json; computes no threshold and
    chooses nothing. dry: the made-up split of a dry-run json, on the in-sample bars."""
    out = pathlib.Path(out)
    sel = json.loads((out / SEL_NAME).read_text())                 # frozen; never rewritten here
    assert bool(sel.get("dry_run")) == dry, "a dry-run selection file can only be used by a dry run (and vice versa)"
    oos_start = pd.Timestamp(sel["oos_start"])
    assert dry or oos_start == OOS_START
    frozen_txt = (out / "is" / "FLOW3_trades.csv").read_text()
    file_ok = sha(frozen_txt) == sel["sha256"]["is/FLOW3_trades.csv"]
    ctx = core.Ctx(run.bars("is" if dry else "full"))
    if ctx.ts[-1].tz_localize(None) < oos_start:
        raise SystemExit("no out-of-sample bars in this data: the full phase cannot run here")
    df = build(ctx)
    day = pd.to_datetime(df.day)
    T = Tables.of(ctx)
    last_flow = str(_stamp(T.nq_t[-1]).date())
    print(f"FLOW3   phase full{'  (DRY RUN on a made-up split: numbers mean nothing)' if dry else ''}   bars {ctx.ts[0]} -> "
          f"{ctx.ts[-1]}   out of sample from {oos_start.date()} to the last flow day {last_flow}")
    d_is, d_oos = df[day < oos_start].reset_index(drop=True), df[day >= oos_start].reset_index(drop=True)

    # ---- the in-sample rows rebuilt from this data against the frozen in-sample files
    rebuilt_txt = csv_text(d_is)
    same_rows = rebuilt_txt == frozen_txt
    print(f"frozen in-sample trades file matches its stamp: {file_ok};  in-sample rows rebuilt from these bars equal "
          f"the frozen file: {same_rows}" + ("" if same_rows and file_ok else "   <-- NOT REPRODUCED"))
    if not same_rows:
        a, b = rebuilt_txt.split("\n"), frozen_txt.split("\n")
        diff = [k for k in range(max(len(a), len(b))) if (a[k] if k < len(a) else None) != (b[k] if k < len(b) else None)]
        print(f"   {len(a) - 2} rebuilt rows, {len(b) - 2} frozen rows, {len(diff)} lines differ; first:")
        for k in diff[:3]:
            print("    rebuilt:", a[k][:200] if k < len(a) else None)
            print("    frozen :", b[k][:200] if k < len(b) else None)
    thr = {"primary": _thr(sel["primary"]), "secondary": _thr(sel["secondary"])}
    sets = {"primary": lambda x: x[x.aligned & x.has_flow], "secondary": lambda x: x[x.has_flow]}
    tabs, same_tab = [], True
    for blk in ("primary", "secondary"):
        for per, dd in (("is", d_is), ("oos", d_oos)):
            tb = table(sets[blk](dd), thr[blk], blk, per)
            tb["better_is"] = [sel[blk]["table"][m]["better"] for m in tb.measure]
            tb["pick"] = [int(sel[blk]["table"][m]["pick"]) for m in tb.measure]
            sgn = np.where(tb.better_is == "high", 1.0, -1.0)
            tb["fav_minus_unfav"] = tb["diff"] * sgn             # the in-sample better side against the other
            tabs.append(tb)
            if per == "is":
                fr = sel[blk]["table"]
                for r in tb.itertuples(index=False):
                    f = fr[r.measure]
                    same_tab &= (r.n_hi, r.wins_hi, r.n_lo, r.wins_lo) == (f["n_hi"], f["wins_hi"], f["n_lo"], f["wins_lo"]) \
                        and abs(r.net_hi - f["net_hi"]) < 0.005 and abs(r.net_lo - f["net_lo"]) < 0.005
    print(f"in-sample table recomputed with the frozen thresholds equals the frozen table: {same_tab}"
          + ("" if same_tab else "   <-- NOT REPRODUCED"))
    tab = pd.concat(tabs, ignore_index=True)
    c_oos = counts(d_oos) if len(d_oos) else {}
    after = int((pd.to_datetime(d_oos.day) > pd.Timestamp(last_flow)).sum()) if len(d_oos) else 0
    print(f"out-of-sample counts: {json.dumps(c_oos)}   pick 1 trades after the last flow day: {after}")

    # ---- the registered test
    res = dict(study="FLOW3 (YT7_SPEC.md, Part 2)", dry_run=dry, oos_start=str(oos_start.date()), last_flow_day=last_flow,
               bars=[str(ctx.ts[0]), str(ctx.ts[-1])], frozen_file_matches_stamp=file_ok, is_rows_reproduced=same_rows,
               is_table_reproduced=bool(same_tab), counts_oos=c_oos, oos_trades_after_last_flow_day=after, picks=[])
    prim = sets["primary"](d_oos)
    prim_is = sets["primary"](d_is)
    print(f"\nPRIMARY out of sample: {len(prim)} aligned trades with flow, {int(prim.win.sum())} wins, mean R "
          + (f"{prim.R.mean():+.3f}" if len(prim) else "nan") + f", net {prim.pnl.sum():+.0f}")
    print(f"registered test (counts: favourable - unfavourable win rate > 0, p < {P_MAX}, favourable mean R above)")
    for p in sel["primary"]["picks"]:
        fav = favourable(prim, p["measure"], p["threshold"], p["favourable"])
        has = ~prim[p["measure"]].isna().to_numpy()
        tw = two_way(prim[has], fav[has])
        v = verdict(tw)
        res["picks"].append(dict(pick=p["pick"], measure=p["measure"], threshold=p["threshold"],
                                 favourable=p["favourable"], n=int(has.sum()), missing=int((~has).sum()),
                                 fav=tw["fav"], unfav=tw["unfav"], diff=tw["diff"], p=tw["p"], verdict=v,
                                 in_sample=dict(fav=p["is_fav"], unfav=p["is_unfav"])))
        f, u = tw["fav"], tw["unfav"]
        print(f"  pick {p['pick']}: {p['measure']} {'>=' if p['favourable'] == 'high' else '<'} {p['threshold']:+.6f}   "
              f"favourable n {f['n']} wins {f['wins']} win {f['win']:.3f} R {f['R']:+.3f} net {f['net']:+.0f} | "
              f"unfavourable n {u['n']} wins {u['wins']} win {u['win']:.3f} R {u['R']:+.3f} net {u['net']:+.0f} | diff "
              + (f"{tw['diff']:+.3f}  p {tw['p']:.4f}" if tw["diff"] is not None else "n/a") + f"  -> {v}"
              f"   [in sample: {p['is_fav']['win']:.3f} vs {p['is_unfav']['win']:.3f}]")
    if sel["primary"]["picks"]:
        res["combined"] = {}
        for per, dd in (("is", prim_is), ("oos", prim)):
            tw = two_way(dd, combined(dd, sel["primary"]["picks"]))
            res["combined"][per] = dict(both_favourable=tw["fav"], rest=tw["unfav"], diff=tw["diff"], p=tw["p"])
            f, u = tw["fav"], tw["unfav"]
            print(f"  both picks' favourable sides, {per} (reported, no verdict): n {f['n']} wins {f['wins']} win "
                  f"{f['win']:.3f} R {f['R']:+.3f} net {f['net']:+.0f} | the rest: n {u['n']} wins {u['wins']} win "
                  f"{u['win']:.3f} R {u['R']:+.3f} net {u['net']:+.0f} | diff "
                  + (f"{tw['diff']:+.3f}  p {tw['p']:.4f}" if tw["diff"] is not None else "n/a"))
    cols = ["measure", "threshold", "n", "missing", "n_hi", "wins_hi", "win_hi", "R_hi", "net_hi", "n_lo", "wins_lo",
            "win_lo", "R_lo", "net_lo", "diff", "better_is", "fav_minus_unfav", "pick"]
    fm = dict(FMT, fav_minus_unfav="{:+.3f}".format)
    for blk, lab in (("primary", "PRIMARY: " + PRIMARY), ("secondary", SECONDARY)):
        for per in ("is", "oos"):
            tb = tab[(tab.block == blk) & (tab.period == per)]
            print(f"\n{lab} - {per}, frozen thresholds (better_is = the side with the higher in-sample win rate; "
                  f"fav_minus_unfav = its win rate minus the other side's)")
            print(tb[cols].to_string(index=False, formatters=fm))
    d = out / "full"
    d.mkdir(parents=True, exist_ok=True)
    tab.to_csv(d / "FLOW3_table.csv", index=False, lineterminator="\n")
    (d / "FLOW3_trades.csv").write_text(csv_text(df))
    res["tables"] = {blk: {per: _block(tab[(tab.block == blk) & (tab.period == per)]) for per in ("is", "oos")}
                     for blk in ("primary", "secondary")}
    (d / "FLOW3_oos.json").write_text(json.dumps(_jsonable(res), indent=1))
    print(f"\nwrote {d / 'FLOW3_table.csv'}, {d / 'FLOW3_oos.json'}, {d / 'FLOW3_trades.csv'}")
    return res


# ------------------------------------------------------------------ causality check
def check(n_samples=20, seed=5, back_days=30):
    """1. Every trade with flow: the measures recomputed on tables from which every flow row, footprint bar and
          30-second bar ending after that trade's decision time has been deleted must equal the plain ones.
       2. n_samples trades with flow: a context is built from the MNQ bars of the back_days days up to and INCLUDING
          the decision bar (no later price bar exists in it, and core.Ctx.flow cuts every table at its last bar's
          end); the signal is rebuilt there (g9_signals.build -> g9_grid.pick) and must be the same bar with the same
          side, stop, run start and overnight level, and the measures computed there must equal the plain ones."""
    a = run.bars("is")
    ctx = core.Ctx(a)
    df = build(ctx)
    fl = df[df.has_flow]
    m0 = fl[MEASURES]
    m1 = measures(ctx, fl, cut=True)
    same = bool(((m0 == m1) | (m0.isna() & m1.isna())).all().all())
    print(f"1. {len(fl)} trades with flow, {len(MEASURES)} measures each, recomputed with every row ending after the "
          f"trade's decision time deleted: {'IDENTICAL' if same else 'DIFFERENT'}")
    rng = np.random.default_rng(seed)
    pick = fl.iloc[np.sort(rng.choice(len(fl), size=min(n_samples, len(fl)), replace=False))]
    bad = 0
    for r in pick.itertuples(index=False):
        dec = pd.Timestamp(r.dec_time)
        w = a[(a.index > dec - pd.Timedelta(days=back_days)) & (a.index <= dec)]
        c = core.Ctx(w)
        c._flow3_ns = _ns(c.ts)
        Tc = Tables.of(c)
        assert c.ts[-1] == dec and (len(Tc.nq_t) == 0 or Tc.nq_t[-1] <= dec.value)
        rows = signal_rows(c)
        s = rows[rows.date == pd.Timestamp(r.day)]
        ok = len(s) == 1
        if ok:
            s = s.iloc[0]
            ok = (c.ts[int(s.i)] == pd.Timestamp(r.sig_time) and int(s.side) == r.sgn and float(s.stop) == r.stop
                  and c.ts[int(s.a_run0)] == pd.Timestamp(r.run_time) and float(s.a_sessx) == r.level)
        on_day, has, _ = flow_cover(c, Tc, pd.Timestamp(r.day), dec.value + MIN_NS)
        ok = ok and has
        if ok:
            t0, t_run, t_sig, t_dec = _times(c, r)
            m = measure_one(Tc, int(s.side), t0, c.ts[int(s.a_run0)].value, c.ts[int(s.i)].value, t_dec, float(s.a_sessx))
            for k in MEASURES:
                x, y = m[k], getattr(r, k)
                ok = ok and (x == y or (x != x and y != y))
            ok = ok and basis_of(c, Tc, pd.Timestamp(r.day), dec.value + MIN_NS) == r.basis
        bad += not ok
        print(f"   {r.day} {r.side} decision {dec.strftime('%H:%M')}  context ends {c.ts[-1].strftime('%Y-%m-%d %H:%M')}  "
              f"flow rows end {_stamp(Tc.nq_t[-1]).strftime('%H:%M') if len(Tc.nq_t) else '-'}  "
              f"signal, level and 11 measures: {'identical' if ok else 'DIFFERENT'}")
    print(f"2. {len(pick)} sampled trades rebuilt from bars and flow ending at the decision time: "
          f"{len(pick) - bad} identical, {bad} different")
    print("FLOW3 causality check:", "PASS" if same and not bad else "FAIL")
    return same and not bad


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", choices=["is", "full"])
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--cuts", type=int, default=20)
    ap.add_argument("--dry-split", help="code test only: a made-up split date inside the data that is here")
    ap.add_argument("--dry-out", help="code test only: directory for the dry run's files")
    ap.add_argument("--dry-min-side", type=int, default=MIN_SIDE, help="code test only: minimum trades a side")
    a = ap.parse_args()
    pd.set_option("display.width", 250)
    if a.check:
        sys.exit(0 if check(a.cuts) else 1)
    assert a.phase, "--phase is|full or --check"
    if a.dry_split or a.dry_out:
        assert a.dry_split and a.dry_out, "--dry-split and --dry-out go together"
        o = pathlib.Path(a.dry_out).resolve()
        assert core.OUT.resolve() != o and core.OUT.resolve() not in o.parents and core.ROOT.resolve() not in o.parents, \
            "a dry run never writes inside the lab"
        if a.phase == "is":
            phase_is(out=o, split_at=a.dry_split, min_side=a.dry_min_side)
        else:
            phase_full(out=o, dry=True)
        return
    assert a.dry_min_side == MIN_SIDE
    if a.phase == "is":
        phase_is()
    else:
        phase_full()


if __name__ == "__main__":
    main()
