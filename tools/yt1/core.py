#!/usr/bin/env python3
"""YT1 shared harness: data, day table, order simulation with the house fills, statistics, look-ahead test.

Every YT1 strategy is a module tools/yt1/s_<ID>.py that builds ORDERS from information available at the close of a
1-minute bar and hands them to simulate() / run_orders() here. Strategy code never computes a fill or a P&L itself.

House fills (BACKTEST_LOG.md, "Literature" / "SIX"), MNQ 1-minute bars, New York time:
    1 tick of slippage against every fill (market, stop, limit, target, time exit), $1 commission per side,
    $2 per point, 1 contract. A bar that opens beyond a stop / target / resting order fills at its open.
    On a bar after the fill bar that touches both the stop and a target, the stop is taken.
    On the fill bar of a resting order the bar's path is open -> nearer extreme -> farther extreme -> close
    (TradingView's assumption, as in orb_engine's stop-order mode): only what the path reaches after the fill counts.
    A market entry at a bar's close has nothing happen in that bar.
Timing contract (what makes a strategy causal):
    an order carries i = the index of the 1-minute bar at whose CLOSE the decision is made. Everything used to build
    the order must be known at that close. etype 'close' fills at close[i]; 'open' fills at open[i+1]; 'stop' and
    'limit' rest from bar i+1 through bar `expire` inclusive.
"""
import json, math, pathlib, zlib
import numpy as np
import pandas as pd

TZ = "America/New_York"
TICK, PV, COMM, SLIP = 0.25, 2.0, 1.0, 0.25
START = pd.Timestamp("2019-06-03", tz=TZ)
IS_END = pd.Timestamp("2023-01-01", tz=TZ)          # in-sample = bars strictly before this
ROOT = pathlib.Path(__file__).resolve().parents[2]
BARS = ROOT / "data" / "bars"
FLOW = ROOT / "data" / "flow"
OUT = ROOT / "data" / "studies" / "yt1"
N_TESTS = 53                                         # trade rules registered in YT1_SPEC.md; Bonferroni = 0.05 / N_TESTS


def tick_round(x, how="nearest"):
    q = x / TICK
    q = math.floor(q + 1e-9) if how == "down" else math.ceil(q - 1e-9) if how == "up" else round(q)
    return q * TICK


def hhmm(s):
    h, m = s.split(":")
    return int(h) * 60 + int(m)


# ------------------------------------------------------------------ data
def load_bars(sym="MNQ", cut=None, path=None):
    """1-minute bars of `sym` (MNQ, ES, MES), New York time, from START. cut = exclusive end timestamp."""
    a = pd.read_parquet(path or BARS / f"{sym}_1m.parquet")
    a = a[a.index >= START - pd.Timedelta(days=1)]
    if cut is not None:
        a = a[a.index < cut]
        assert a.index.max() < cut, "bars reach past the cut"
    return a


def resample(a, minutes, offset_min=0):
    """N-minute bars from 1-minute bars, buckets aligned to the clock (plus offset_min), stamped with their open time.
    Columns open/high/low/close/volume plus i_first / i_last = positions (in `a`) of the first / last 1-minute bar in
    the bucket. A signal on a bucket is known at the close of 1-minute bar i_last."""
    pos = pd.Series(np.arange(len(a)), index=a.index)
    key = (a.index - pd.Timedelta(minutes=offset_min)).floor(f"{minutes}min") + pd.Timedelta(minutes=offset_min)
    g = a.groupby(key)
    out = pd.DataFrame({"open": g.open.first(), "high": g.high.max(), "low": g.low.min(), "close": g.close.last(),
                        "volume": g.volume.sum(), "i_first": pos.groupby(key).first(),
                        "i_last": pos.groupby(key).last()})
    return out


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


def _reflect(a, after):
    """Bars with every price after `after` mirrored around the last close at or before it (highs and lows swap) and
    volume halved: the future is replaced by a different one. Used only by the look-ahead test."""
    a = a.copy()
    m = a.index > after
    if not m.any() or m.all():
        return a
    ref = float(a.close[~m].iloc[-1])
    o, h, l, c = (a[k].to_numpy(float).copy() for k in ("open", "high", "low", "close"))
    a.loc[m, "open"], a.loc[m, "close"] = 2 * ref - o[m], 2 * ref - c[m]
    a.loc[m, "high"], a.loc[m, "low"] = 2 * ref - l[m], 2 * ref - h[m]
    a["volume"] = a["volume"].astype(float)
    a.loc[m, "volume"] = np.floor(a.loc[m, "volume"] * 0.5) + 1
    return a


def _reflect_flow(f, after):
    f = f.copy()
    if "ts" in f.columns:                                   # footprint rows: swap the two sides after the cut
        m = (f.ts > after).to_numpy()
        b, s_ = f.buy.to_numpy().copy(), f.sell.to_numpy().copy()
        f.loc[m, "buy"], f.loc[m, "sell"] = s_[m], b[m]
        return f
    m = f.index > after
    if "buy" in f.columns:
        b, s_ = f.buy.to_numpy().copy(), f.sell.to_numpy().copy()
        f.loc[m, "buy"], f.loc[m, "sell"] = s_[m], b[m]
        f.loc[m, "delta"] = -f.loc[m, "delta"]
        f.loc[m, "cum_delta"] = -f.loc[m, "cum_delta"]
        return f
    return _reflect(f, after)                               # 30-second bars


class Ctx:
    """Bars as arrays plus a per-cash-day table. Build with Ctx(load_bars(...)).

    Arrays (one value per 1-minute bar): ts (DatetimeIndex), O H L C V, tod (minutes after midnight, New York),
    cdate (calendar date as datetime64[D]), tdate (trading date: 18:00 belongs to the next day), iid (contract id).
    days: DataFrame indexed by cash date (Timestamp, naive) with
        i_open    position of the 09:30 bar            i_last   position of the last tradable RTH bar (15:59, or the
        i_end     i_last (the flat bar)                         bar ending 10 minutes before an early close)
        early     True on early-close days             roll     True when the front contract changed since the
        o930      09:30 open                                    previous cash day (those days are not traded)
        rth_h, rth_l, rth_c   this day's 09:30-16:00 high / low / last close  (NOT known until the day ends)
        pdh, pdl, pdc         previous cash day's RTH high / low / close
        onh, onl              overnight 18:00 -> 09:29 high / low (known at 09:30)
        atr       daily ATR(14) on 18:00->17:00 trading-day bars through the previous trading day
        dow       0 = Monday                           n        running number of the cash day
        ev        frozenset of event types that day (FOMC, CPI, NFP, PPI, PCE, retail_sales, GDP_advance, opex)
    """

    def __init__(self, a, events_csv=None, scramble_after=None):
        self.scramble_after = scramble_after
        if scramble_after is not None:
            a = _reflect(a, scramble_after)
        self.a = a
        self.ts = a.index
        self.O, self.H, self.L, self.C = (a[k].to_numpy(float) for k in ("open", "high", "low", "close"))
        self.V = a["volume"].to_numpy(float)
        self.iid = a["instrument_id"].to_numpy()
        self.n = len(a)
        self.tod = (self.ts.hour * 60 + self.ts.minute).to_numpy()
        naive = self.ts.tz_localize(None)
        self.cdate = naive.normalize().to_numpy().astype("datetime64[D]")
        self.tdate = (naive + pd.Timedelta(hours=6)).normalize().to_numpy().astype("datetime64[D]")
        self.pos = pd.Series(np.arange(self.n), index=self.ts)
        self._rs = {}
        self._extra = {}
        self.cut = self.ts[-1] + pd.Timedelta(minutes=1)     # nothing at or after this time may be read
        self._build_days(events_csv or ROOT / "data" / "events.csv")

    # -- helpers
    def idx(self, date, hm):
        """Position of the 1-minute bar stamped date hh:mm, or None if that minute has no bar."""
        return self.pos.get(self._wall(date, hm))

    @staticmethod
    def _wall(date, hm):
        """New York wall-clock time hh:mm on a calendar date (correct on daylight-saving Sundays too)."""
        t = pd.Timestamp(date).normalize() + pd.Timedelta(minutes=hhmm(hm) if isinstance(hm, str) else int(hm))
        return t.tz_localize(TZ, nonexistent="shift_forward", ambiguous=True)


    def span(self, date, hm0, hm1):
        """Positions [lo, hi) of the 1-minute bars with hm0 <= time < hm1 on calendar `date` (may be empty)."""
        t0, t1 = self._wall(date, hm0), self._wall(date, hm1)
        return int(self.ts.searchsorted(t0, "left")), int(self.ts.searchsorted(t1, "left"))

    def bars(self, minutes, offset_min=0):
        k = (minutes, offset_min)
        if k not in self._rs:
            self._rs[k] = resample(self.a, minutes, offset_min)
        return self._rs[k]

    def extra(self, sym):
        """1-minute bars of another market (ES, MES) up to this context's cut. Never read other files directly."""
        if sym not in self._extra:
            x = load_bars(sym, cut=self.cut)
            x = x[x.index >= self.ts[0]]
            if self.scramble_after is not None:
                x = _reflect(x, self.scramble_after)
            self._extra[sym] = x
        return self._extra[sym]

    def flow(self, name):
        """Order-flow table up to this context's cut. Names: NQ_flow_1m, ES_flow_1m (index ts: buy, sell, volume,
        trades, delta, cum_delta, cum_volume per minute, 09:30-11:34 on the ORB days only), NQ_footprint_5m,
        ES_footprint_5m (columns ts = 5-minute bar open, price, buy, sell), NQ_bars_30s (index ts, OHLCV)."""
        if name not in self._extra:
            f = pd.read_parquet(FLOW / f"{name}.parquet")
            if "ts" in f.columns:
                f = f[f.ts + pd.Timedelta(minutes=5) <= self.cut]        # only completed 5-minute bars
                f = f[f.ts >= self.ts[0]]
            else:
                f = f[(f.index < self.cut) & (f.index >= self.ts[0])]
            if self.scramble_after is not None:
                f = _reflect_flow(f, self.scramble_after)
            self._extra[name] = f
        return self._extra[name]

    def _build_days(self, events_csv):
        a, tod = self.a, self.tod
        rth = (tod >= 570) & (tod < 960)
        cd = pd.DatetimeIndex(self.cdate)
        r = a[rth]
        rcd = cd[rth]
        g = r.groupby(rcd)
        D = pd.DataFrame({"n_bars": g.size(), "o930": g.open.first(), "rth_h": g.high.max(), "rth_l": g.low.min(),
                          "rth_c": g.close.last()})
        posr = pd.Series(np.arange(self.n)[rth], index=rcd)
        D["i_first"] = posr.groupby(level=0).first()
        D["i_lastbar"] = posr.groupby(level=0).last()
        D["t_first"] = pd.Series(tod[rth], index=rcd).groupby(level=0).first()
        D["t_last"] = pd.Series(tod[rth], index=rcd).groupby(level=0).last()
        D = D[(D.t_first == 570) & (D.n_bars >= 150)]          # a real cash session that starts at 09:30
        ev = pd.read_csv(events_csv)
        early = ev[ev.type == "early_close"].set_index("date").time_ny
        halt = pd.Series([early.get(d.strftime("%Y-%m-%d")) for d in D.index], index=D.index)
        # bars are the truth where the calendar is silent: a session whose last RTH bar is before 15:59
        D["early"] = halt.notna() | (D.t_last < 959)
        end_tod = []
        for d, row in D.iterrows():
            if not row.early:
                end_tod.append(959)
            else:
                h = halt[d]
                hm = hhmm(h) if isinstance(h, str) else int(row.t_last) + 1
                end_tod.append(hm - 11)                      # the bar ending 10 minutes before the halt
        D["end_tod"] = end_tod
        i_open, i_last = [], []
        for d, row in D.iterrows():
            i0 = self.idx(d, 570)
            lo, hi = self.span(d, 570, int(row.end_tod) + 1)
            i_open.append(i0 if i0 is not None else -1)
            i_last.append(hi - 1 if hi > lo else -1)
        D["i_open"], D["i_last"] = i_open, i_last
        D["i_end"] = D.i_last
        D = D[(D.i_open >= 0) & (D.i_last > D.i_open)]
        D["pdh"], D["pdl"], D["pdc"] = D.rth_h.shift(1), D.rth_l.shift(1), D.rth_c.shift(1)
        # overnight 18:00 -> 09:29, keyed by trading date (= the cash date it leads into)
        on = (tod >= 1080) | (tod < 570)
        og = a[on].groupby(pd.DatetimeIndex(self.tdate)[on])
        D["onh"], D["onl"] = og.high.max().reindex(D.index), og.low.min().reindex(D.index)
        # daily ATR(14) on trading-day bars, value through the previous trading day
        tg = a.groupby(pd.DatetimeIndex(self.tdate))
        T = pd.DataFrame({"h": tg.high.max(), "l": tg.low.min(), "c": tg.close.last()})
        T["atr"] = rma_atr(T.h.to_numpy(), T.l.to_numpy(), T.c.to_numpy())
        D["atr"] = T.atr.shift(1).reindex(D.index)
        iid_open = pd.Series(self.iid[D.i_open.to_numpy()], index=D.index)
        D["roll"] = (iid_open != iid_open.shift(1)) & iid_open.shift(1).notna()
        D["dow"] = D.index.dayofweek
        D["n"] = np.arange(len(D))
        evs = ev[ev.type != "early_close"].groupby("date").type.apply(frozenset)
        D["ev"] = [evs.get(d.strftime("%Y-%m-%d"), frozenset()) for d in D.index]
        D = D[D.index >= START.tz_localize(None).normalize()]
        self.days = D
        # per-bar: the running number of the cash day the bar's calendar date belongs to (-1 if none)
        dn = pd.Series(D.n.to_numpy(), index=D.index).reindex(cd).to_numpy()
        self.dayn = np.where(np.isnan(dn), -1, dn).astype(int)
        self.day_index = D.index
        self.roll_dates = set(D.index[D.roll])
        self.roll2_dates = set(D.index[D.roll | D.roll.shift(1, fill_value=False)])
        self.noatr_dates = set(D.index[D.atr.isna()])


# ------------------------------------------------------------------ order simulation
def _path(o, h, l, c):
    """TradingView's intrabar path: open -> nearer extreme -> farther extreme -> close."""
    return (o, h, l, c) if (h - o) < (o - l) else (o, l, h, c)


def simulate(ctx, i, side, etype="close", price=None, expire=None, stop=None, target=None, parts=None,
             exit_i=None, be_trigger=None, be_after_part=False, trail=None, exit_sig=None, cancel_hi=None,
             cancel_lo=None, cancel_sig=None, r_pts=None, tag=None):
    """Simulate one order. Returns a trade dict, or None if the order never fills (or runs past the data).

    i          signal bar (decision at its close).           side   +1 long, -1 short
    etype      'close'  fill at close[i]
               'open'   fill at open[i+1]
               'stop'   resting stop order at `price` (buy stop above / sell stop below), bars i+1 .. expire
               'limit'  resting limit order at `price` (buy limit below / sell limit above), bars i+1 .. expire
    stop       protective stop price (None = no stop).       target full-exit target price (None = none)
    parts      [(price, fraction), ...] scale-outs; fractions must sum to <= 1, any remainder runs to stop / exit.
               (use either target or parts)
    exit_i     bar at whose close whatever is left is closed (the flat bar). Required.
    be_trigger price which, once traded, moves the stop to the entry price from the NEXT bar on.
    be_after_part  True: after the first scale-out the stop moves to the entry price from the next bar on.
    trail      array (len n): trail[k] = stop level known at the close of bar k, applied from bar k+1; it only ever
               tightens the stop. NaN = no value.
    exit_sig   bool array: at the close of the first bar k > fill bar (or k >= fill bar for a resting-order fill ...
               k > fill bar in all cases) with exit_sig[k] the trade is closed at close[k].
    cancel_hi / cancel_lo   a resting order is cancelled when a bar's high >= cancel_hi / low <= cancel_lo before it
               fills (checked bar by bar; if the same bar would also fill, the path decides which comes first).
    cancel_sig bool array: the resting order is cancelled at the close of the first bar k >= i+1 with cancel_sig[k].
    r_pts      the R unit in points for a trade without a stop (otherwise R = |fill - stop|).
    """
    O, H, L, C, n = ctx.O, ctx.H, ctx.L, ctx.C, ctx.n
    assert side in (1, -1) and exit_i is not None
    assert not (target is not None and parts), "use target or parts"
    exit_i = int(exit_i)
    if i >= n - 1 or exit_i >= n:
        return None
    sl = SLIP * side

    def beyond(px, level):              # px is at/through `level` in the trade's favour
        return px >= level if side > 0 else px <= level

    def against(px, level):             # px is at/through `level` against the trade
        return px <= level if side > 0 else px >= level

    # ---- entry
    j = None                            # fill bar
    path_after = None                   # remaining path points on the fill bar (resting orders only)
    if etype == "close":
        if i >= exit_i:
            return None
        j, raw = i, C[i]
    elif etype == "open":
        j = i + 1
        if j > exit_i:
            return None
        raw = O[j]
        path_after = list(_path(O[j], H[j], L[j], C[j]))      # whole bar is live
    else:
        assert price is not None and expire is not None
        last = min(int(expire), exit_i, n - 1)
        is_stop = etype == "stop"
        up = (side > 0) == is_stop      # the order fills on an upward move (buy stop, sell limit)
        for k in range(i + 1, last + 1):
            p = _path(O[k], H[k], L[k], C[k])
            if cancel_hi is not None and O[k] >= cancel_hi or cancel_lo is not None and O[k] <= cancel_lo:
                return None                                   # the bar opens at / through a cancel level
            # gap at the open
            if (O[k] >= price) if up else (O[k] <= price):
                # stop order: fills at the open (worse); limit order: fills at the open (better than the limit)
                j, raw, path_after = k, O[k], list(p)
                break
            hit = None
            for s in range(3):
                x0, x1 = p[s], p[s + 1]
                lo, hi = min(x0, x1), max(x0, x1)
                c_hi = cancel_hi is not None and hi >= cancel_hi
                c_lo = cancel_lo is not None and lo <= cancel_lo
                f = (x1 >= price > x0) if up else (x1 <= price < x0)
                if f:
                    # a cancel level lying between the leg's start and the order price is reached first
                    if up and c_hi and cancel_hi < price or (not up) and c_lo and cancel_lo > price:
                        return None
                    hit = s
                    break
                if c_hi or c_lo:
                    return None
            if hit is not None:
                j, raw = k, price
                path_after = [price] + list(p[hit + 1:])
                break
            if cancel_sig is not None and cancel_sig[k]:
                return None
        if j is None:
            return None
    fill = raw + sl
    if stop is not None and not against(stop, raw - side * 1e-9):
        return None                     # stop on the wrong side of the fill: not a valid order
    risk = abs(fill - stop) if stop is not None else r_pts
    if risk is None or risk <= 0:
        return None
    todo = [(float(p), float(f)) for p, f in (parts or ([(target, 1.0)] if target is not None else []))]
    todo.sort(key=lambda x: x[0] * side)
    left, legs, cur_stop, be_next, be_done, reason = 1.0, [], stop, False, False, None
    entry_ref = raw

    def take(px, frac, why):
        nonlocal left, reason
        legs.append((px - sl, frac, why))
        left -= frac
        reason = why

    def run_levels(lo, hi, o_gap=None):
        """Bar (or path leg) with range lo..hi: stop first, then targets. o_gap = the bar's open for gap fills."""
        nonlocal left, be_next
        if cur_stop is not None:
            if o_gap is not None and against(o_gap, cur_stop):
                take(o_gap, left, "SL"); return
            if (lo <= cur_stop) if side > 0 else (hi >= cur_stop):
                take(cur_stop, left, "SL"); return
        while todo and left > 1e-9:
            px, fr = todo[0]
            if o_gap is not None and beyond(o_gap, px):
                fpx = o_gap
            elif (hi >= px) if side > 0 else (lo <= px):
                fpx = px
            else:
                break
            todo.pop(0)
            fr = min(fr, left)
            take(fpx, fr, "TP")
            if be_after_part:
                be_next = True
        if be_trigger is not None and ((hi >= be_trigger) if side > 0 else (lo <= be_trigger)):
            be_next = True

    # ---- the fill bar
    if path_after is not None and left > 1e-9:
        for s in range(len(path_after) - 1):
            x0, x1 = path_after[s], path_after[s + 1]
            going_fav = (x1 > x0) if side > 0 else (x1 < x0)
            if going_fav:
                while todo and left > 1e-9 and beyond(x1, todo[0][0]):
                    px, fr = todo.pop(0)
                    take(px, min(fr, left), "TP")
                    if be_after_part:
                        be_next = True
                if be_trigger is not None and beyond(x1, be_trigger):
                    be_next = True
            elif cur_stop is not None and against(x1, cur_stop):
                take(cur_stop, left, "SL")
            if left <= 1e-9:
                break
    k = j
    # ---- later bars
    while left > 1e-9:
        if k >= exit_i:
            take(C[k], left, "time")                          # filled on the flat bar itself
            break
        k += 1
        if k >= n:
            return None
        if be_next and not be_done:
            cur_stop = entry_ref if cur_stop is None else (max(cur_stop, entry_ref) if side > 0 else min(cur_stop, entry_ref))
            be_done = True
        if trail is not None:
            t = trail[k - 1]
            if t == t:
                cur_stop = t if cur_stop is None else (max(cur_stop, t) if side > 0 else min(cur_stop, t))
        run_levels(L[k], H[k], O[k])
        if left <= 1e-9:
            break
        if exit_sig is not None and exit_sig[k]:
            take(C[k], left, "sig")
            break
        if k == exit_i:
            take(C[k], left, "time")
            break
    pts = sum(side * (px - fill) * fr for px, fr, _ in legs)
    pnl = pts * PV - 2 * COMM
    avg_exit = sum(px * fr for px, fr, _ in legs)
    ts = ctx.ts
    return dict(sig_time=ts[i], entry_time=ts[j], exit_time=ts[k], side="L" if side > 0 else "S", i=int(i), j=int(j),
                k=int(k), entry=fill, exit=avg_exit, stop=stop if stop is not None else np.nan, risk_pts=risk,
                pnl=round(pnl, 2), R=pnl / (risk * PV), reason=reason, parts=len(legs), tag=tag or "")


def run_orders(ctx, orders, one_at_a_time=True, max_per_day=None, skip_roll=True):
    """Simulate a list of order dicts (keyword arguments of simulate, sorted here by signal bar).
    one_at_a_time: an order whose signal bar is at or before the previous trade's exit bar is skipped.
    max_per_day:   at most this many FILLED trades per cash day (by the signal bar's calendar date).
    skip_roll:     True drops orders signalled on a contract-roll cash day (the registry's rule); 2 also drops the
                   cash day after a roll (family C). Orders on days without a daily ATR are always dropped."""
    orders = sorted(orders, key=lambda o: o["i"])
    out, busy_until, per_day = [], -1, {}
    for o in orders:
        i = o["i"]
        d = ctx.cdate[i]
        if skip_roll and pd.Timestamp(d) in (ctx.roll2_dates if skip_roll == 2 else ctx.roll_dates):
            continue
        if pd.Timestamp(d) in ctx.noatr_dates or ctx.dayn[i] < 0:
            continue
        if one_at_a_time and i <= busy_until:
            continue
        if max_per_day is not None and per_day.get(d, 0) >= max_per_day:
            continue
        t = simulate(ctx, **o)
        if t is None:
            continue
        out.append(t)
        busy_until = t["k"]
        per_day[d] = per_day.get(d, 0) + 1
    return out


# ------------------------------------------------------------------ statistics
def trades_df(trades):
    cols = ["sig_time", "entry_time", "exit_time", "side", "i", "j", "k", "entry", "exit", "stop", "risk_pts", "pnl",
            "R", "reason", "parts", "tag"]
    return pd.DataFrame(trades, columns=cols)


def boot_p(R, n=10000, seed=1):
    """One-sided bootstrap p of mean R > 0 (share of resampled means <= 0), 10,000 resamples, seed 1."""
    R = np.asarray(R, float)
    if len(R) < 2:
        return 1.0
    rng = np.random.default_rng(seed)
    m = rng.choice(R, size=(n, len(R)), replace=True).mean(axis=1)
    return float((m <= 0).mean())


def max_dd(x):
    c = np.cumsum(x)
    return float((c - np.maximum.accumulate(np.r_[0, c])[1:]).min()) if len(c) else 0.0


def summary(df):
    """The house summary of a trade list."""
    if len(df) == 0:
        return dict(n=0)
    y = pd.DatetimeIndex(df.entry_time).year
    by = {}
    for yr in range(2019, 2027):
        d = df[y == yr]
        by[yr] = dict(n=int(len(d)), net=round(float(d.pnl.sum()), 0), R=round(float(d.R.mean()), 3) if len(d) else None)
    h1, h2 = df[y <= 2022], df[y >= 2023]
    w, l = df.pnl[df.pnl > 0].sum(), -df.pnl[df.pnl <= 0].sum()
    L_, S_ = df[df.side == "L"], df[df.side == "S"]
    return dict(
        n=int(len(df)), net=round(float(df.pnl.sum()), 0), R=round(float(df.R.mean()), 4),
        R_total=round(float(df.R.sum()), 1), win=round(float((df.pnl > 0).mean() * 100), 1),
        pf=round(float(w / l), 3) if l > 0 else None, dd=round(max_dd(df.pnl.to_numpy()), 0),
        dd_R=round(max_dd(df.R.to_numpy()), 1), p=boot_p(df.R.to_numpy()),
        years_pos=int(sum(1 for v in by.values() if v["n"] and v["net"] > 0)),
        years_traded=int(sum(1 for v in by.values() if v["n"])),
        R_h1=round(float(h1.R.mean()), 4) if len(h1) else None, n_h1=int(len(h1)),
        R_h2=round(float(h2.R.mean()), 4) if len(h2) else None, n_h2=int(len(h2)),
        R_long=round(float(L_.R.mean()), 4) if len(L_) else None, n_long=int(len(L_)),
        R_short=round(float(S_.R.mean()), 4) if len(S_) else None, n_short=int(len(S_)),
        avg_risk_pts=round(float(df.risk_pts.mean()), 2), by_year=by,
        reasons=df.reason.value_counts().to_dict())


def verdict(base, neighbours, n_tests=None, min_n=100):
    """The registry's criterion on a full-span base summary and its two neighbour summaries."""
    n_tests = n_tests or N_TESTS
    if base.get("n", 0) < min_n:
        return dict(verdict="not enough data", checks={}, bonf=0.05 / n_tests)
    ch = dict(
        years=base["years_pos"] >= 6,
        r=base["R"] >= 0.05,
        halves=(base["R_h1"] is not None and base["R_h2"] is not None and base["R_h1"] >= 0 and base["R_h2"] >= 0),
        neighbours=all(nb.get("n", 0) > 0 and (nb["R"] > 0) == (base["R"] > 0) for nb in neighbours) and len(neighbours) == 2,
        p=base["p"] < 0.05 / n_tests)
    if all(ch.values()):
        v = "passes"
    elif all(v for k, v in ch.items() if k != "p") and base["p"] < 0.05:
        v = "candidate"
    else:
        v = "fails"
    return dict(verdict=v, checks=ch, bonf=0.05 / n_tests)


def fmt_row(name, s):
    if not s.get("n"):
        return f"{name:<22} n 0"
    yr = " ".join(f"{(v['net'] if v['n'] else 0):+.0f}" for v in s["by_year"].values())
    return (f"{name:<22} n {s['n']:>5}  net {s['net']:>+9.0f}  R {s['R']:>+7.3f}  win {s['win']:>5.1f}  pf {s['pf'] or 0:>5.2f}"
            f"  dd {s['dd']:>8.0f}  p {s['p']:.4f}  yrs+ {s['years_pos']}/{s['years_traded']}"
            f"  h1 {s['R_h1'] if s['R_h1'] is not None else float('nan'):+.3f} h2 {s['R_h2'] if s['R_h2'] is not None else float('nan'):+.3f}  | {yr}")


# ------------------------------------------------------------------ look-ahead test
_SCALARS = ("side", "etype", "price", "stop", "target", "be_trigger", "cancel_hi", "cancel_lo", "r_pts")
_ARRAYS = ("trail", "exit_sig", "cancel_sig")


def _okey(ctx, o):
    def r(x):
        return None if x is None else round(float(x), 6)
    parts = tuple((r(p), r(f)) for p, f in (o.get("parts") or ()))
    return (ctx.ts[o["i"]],) + tuple(o.get(k) if k in ("side", "etype") else r(o.get(k)) for k in _SCALARS) + (parts,)


def causal_check(make_orders, a, n_samples=16, seed=5, back_days=150, fwd_days=7, verbose=True):
    """make_orders(Ctx) -> list of order dicts. For n_samples of the rule's own orders: the bars are windowed around
    the order's signal bar T, and the rule is run twice on that window, once as it is and once with everything after
    T replaced by a mirrored future (and, for a second market or order flow, likewise). Every order signalled at or
    before T must come out identical in the two runs, including the part of any trail / exit / cancel array up to T.
    A rule that reads even one bar past its signal bar fails."""
    full = Ctx(a)
    orders = make_orders(full)
    if not orders:
        print("  no orders to test")
        return False
    rng = np.random.default_rng(seed)
    t0 = a.index[0] + pd.Timedelta(days=back_days)
    cand = [o for o in orders if full.ts[o["i"]] > t0 and full.ts[o["i"]] < a.index[-1] - pd.Timedelta(days=fwd_days + 1)]
    if not cand:
        cand = orders
    picks = [cand[k] for k in sorted(rng.choice(len(cand), size=min(n_samples, len(cand)), replace=False))]
    bad = 0
    for o in picks:
        T = full.ts[o["i"]]
        w = a[(a.index >= T - pd.Timedelta(days=back_days)) & (a.index < T + pd.Timedelta(days=fwd_days))]
        c0, c1 = Ctx(w), Ctx(w, scramble_after=T)
        o0 = [x for x in make_orders(c0) if c0.ts[x["i"]] <= T]
        o1 = [x for x in make_orders(c1) if c1.ts[x["i"]] <= T]
        k0, k1 = sorted(map(str, (_okey(c0, x) for x in o0))), sorted(map(str, (_okey(c1, x) for x in o1)))
        same = k0 == k1
        why = "" if same else f"{len(k0)} orders with the true future, {len(k1)} with a mirrored future"
        if same:
            iT = int(c0.pos[T])
            for x0, x1 in zip(sorted(o0, key=lambda x: str(_okey(c0, x))), sorted(o1, key=lambda x: str(_okey(c1, x)))):
                for nm in _ARRAYS:
                    a0, a1 = x0.get(nm), x1.get(nm)
                    if (a0 is None) != (a1 is None) or (a0 is not None and not np.array_equal(
                            np.asarray(a0)[:iT + 1], np.asarray(a1)[:iT + 1], equal_nan=np.asarray(a0).dtype.kind == "f")):
                        same, why = False, f"{nm} array differs at or before the signal bar"
        here = str(_okey(full, o)) in k0
        if not same:
            bad += 1
            if verbose:
                print(f"  LOOK-AHEAD at {T}: {why}")
                d = sorted(set(k0) ^ set(k1))[:4]
                for x in d:
                    print("     ", x)
        elif verbose:
            print(f"  ok  {T}  {len(k0)} orders identical under a mirrored future" + ("" if here else "   (note: the sampled order is not reproduced on the 150-day window: long warm-up?)"))
    return bad == 0


def save(ident, variant, phase, df, extra=None):
    d = OUT / phase
    d.mkdir(parents=True, exist_ok=True)
    df.drop(columns=["i", "j", "k"], errors="ignore").to_csv(d / f"{ident}_{variant}.csv", index=False)
    s = summary(df)
    if extra:
        s.update(extra)
    (d / f"{ident}_{variant}.json").write_text(json.dumps(s, indent=1, default=str))
    return s
