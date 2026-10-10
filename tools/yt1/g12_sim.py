#!/usr/bin/env python3
"""G12 simulator - the frequency grid of YT11_SPEC.md, Part 3: signals and vectorised trades of the 756 combinations.

    python3 tools/yt1/g12_sim.py --phase is                       decision / trade counts of every combination
    python3 tools/yt1/g12_sim.py --phase is --combo mom-5.z1.k10.mkt [--show 12] [--csv out.csv]
                                                                 the trades of one combination

A combination is G x Z x K x E, named  <G>.z<Z>.k<K>.<E>  (mom-5.z1.k10.mkt, vwr.z0.k30.lim):
18 signals x 3 strengths x 7 holding times x 2 entries = 756, in the order of the spec's table (E varies fastest).

Everything below is the ONE place where a decision, a signal, a strength, a fill or a P&L of G12 is defined.
g12_grid.py evaluates it, g12_verify.py replays it through core.simulate and re-derives it the slow way.

Clock        "k minutes later / L minutes earlier" is always the bar STAMPED that many minutes away (looked up by
             its time, never by position). A minute without a bar is simply missing.
Session      the regular session of a cash day of ctx.days: the 09:30 bar .. the flat bar days.i_end (15:59, or the
             bar ending 10 minutes before an early close).
Decision     the close of the bar stamped 09:59 + m x k minutes (m = 0, 1, ...) for which the exit minute
             (decision + k) is at or before the flat bar's minute. It is a decision only if both the decision bar
             and the exit bar exist (a missing minute: no decision, nothing is carried to another bar).
             Not on contract-roll days and not on days without a daily ATR (the days core.run_orders drops).
Exit         the close of the bar stamped k minutes after the decision. No stop, no target. The next decision is at
             that same close, so there is one position at a time by construction.
s            ind.stdev (population standard deviation, as ta.stdev) of the 390 most recent 1-minute log returns
             ln(close[b] / close[b-1]) at or before the decision, where a return counts only if b and b-1 are in
             the same session, b-1 is stamped one minute before b and both are the same contract. The window runs
             back into earlier sessions (every session of ctx.days, traded or not). Fewer than 390: no value.
s_d          the same statistic of the 1-minute difference (ES log return - MNQ log return) at those same 390
             bars; a bar at which ES has no 1-minute return (ES minute missing at b or b-1) is left out of the
             standard deviation.
VWAP, sd     ind.session_vwap anchored at the 09:30 bar: sum(hlc3 x volume) / sum(volume) through the bar just
             closed; sd = sqrt(sum(volume x hlc3^2) / sum(volume) - VWAP^2).
G  mom-L     side = sign(close[t] - close[t-L])                      z = |ln(close[t] / close[t-L])| / (s sqrt(L))
   rev-L     the opposite side, same z
   es-L      d = ln(ES[t] / ES[t-L]) - ln(MNQ[t] / MNQ[t-L]); side = sign(d) (long MNQ when it lags ES)
                                                                     z = |d| / (s_d sqrt(L))
   esr-L     the opposite side, same z
   vw        side = sign(close[t] - VWAP[t])                         z = |close[t] - VWAP[t]| / VWAP sd[t]
   vwr       the opposite side, same z
             ES bars come from ctx.extra("ES") and are matched to MNQ bars by timestamp. A side of 0, a missing
             bar at t-L (MNQ, or ES for es / esr), a contract change between t-L and t, or a z that cannot be
             computed is no trade at that decision.
Z            the trade is taken when z >= 0, 1 or 2.
E  mkt       in at close[t], out at close[t+k], house fills: 1 tick against each fill, $1 a side, $2 a point:
             net = side x (close[t+k] - close[t]) x 2 - 3.00   (= core.simulate(etype="close", exit_i=...).pnl)
   lim       a limit at close[t] for the bar stamped t+1 only. Filled only if that bar trades at least one tick
             through it (long: low <= close[t] - 0.25; short: high >= close[t] + 0.25), at close[t], no slippage,
             $1. Not filled (or no bar at t+1): no trade. Out at close[t+k] with a house market fill (1 tick
             against, $1):  net = side x (close[t+k] - close[t]) x 2 - 2.50.  With k = 1 the fill and the exit are
             on the same bar.
gross        side x (close[t+k] - close[t]) x $2: the price difference before any slippage or commission, from the
             decision close (mkt) = the limit price (lim).
unit         the day's 0.1 x daily ATR(14) (days.atr) in dollars: 0.1 x atr x $2.
Readings beyond the spec text are listed in notes/G12.md.
"""
import argparse, math, pathlib, sys, time
import numpy as np
import pandas as pd
sys.path.insert(0, str(pathlib.Path(__file__).parent))
import core
import ind

TICK, PV, COMM, SLIP = core.TICK, core.PV, core.COMM, core.SLIP
COST = {"mkt": 2 * SLIP * PV + 2 * COMM, "lim": SLIP * PV + 2 * COMM}      # $3.00 and $2.50 a round trip
LAGS = (1, 5, 15, 30)
FAMILIES = ("mom", "rev", "es", "esr", "vw", "vwr")
GS = tuple(f"{f}-{L}" for f in ("mom", "rev", "es", "esr") for L in LAGS) + ("vw", "vwr")
ZS = (0, 1, 2)
KS = (1, 2, 3, 5, 10, 15, 30)
ES_ = ("mkt", "lim")
ORDER = ("G", "Z", "K", "E")
N_GRID = 756
OPEN = 570                 # 09:30
FIRST = 599                # the 09:59 bar: the first decision is at its close
WIN = 390                  # returns in s and s_d
_MIRROR = {"mom": "rev", "rev": "mom", "es": "esr", "esr": "es", "vw": "vwr", "vwr": "vw"}
_BASE = {"mom": "mom", "rev": "mom", "es": "es", "esr": "es", "vw": "vw", "vwr": "vw"}


# ------------------------------------------------------------------ the grid and its names
def split(G):
    """'mom-15' -> ('mom', 15); 'vw' -> ('vw', None)."""
    f, _, L = G.partition("-")
    assert G in GS, f"unknown signal {G}"
    return f, (int(L) if L else None)


def combos():
    """The 756 combinations as dicts G, Z, K, E in the spec table's order (the first listed level first; E fastest)."""
    return [dict(G=g, Z=z, K=k, E=e) for g in GS for z in ZS for k in KS for e in ES_]


def name(c):
    return f"{c['G']}.z{c['Z']}.k{c['K']}.{c['E']}"


def parse(s):
    p = s.split(".")
    assert len(p) == 4 and p[1][:1] == "z" and p[2][:1] == "k", f"not a combination: {s}"
    c = dict(G=p[0], Z=int(p[1][1:]), K=int(p[2][1:]), E=p[3])
    assert c["G"] in GS and c["Z"] in ZS and c["K"] in KS and c["E"] in ES_, f"unknown level in {s}"
    return c


def mirror_signal(G):
    f, L = split(G)
    return _MIRROR[f] if L is None else f"{_MIRROR[f]}-{L}"


def mirror(s):
    """The mirror of a combination: the opposite signal with the same Z, K and E."""
    c = parse(s)
    return name(dict(c, G=mirror_signal(c["G"])))


# ------------------------------------------------------------------ per-context preparation
class Decisions:
    """The decisions of one holding time: i = decision bar, x = exit bar (k minutes later), d = row of ctx.days,
    i1 = the bar after the decision bar, nx = True when it is stamped one minute after the decision."""
    __slots__ = ("k", "i", "x", "d", "i1", "nx")


class Cell:
    """One signal on the decisions of one holding time: side (+1 / -1 / 0), z, gross $ of a trade taken there
    (side x (close[x] - close[i]) x $2), fill = the limit of the `lim` entry would be filled."""
    __slots__ = ("dec", "side", "z", "gross", "fill")


class Prep:
    """Per-bar arrays, each causal bar by bar (the value at bar b uses bars stamped at or before b):
    tmin (minutes since the epoch), sess (row of ctx.days of a regular-session bar, else -1), lc (ln close),
    s, sd (s_d), vwap, vsd, and ES closes matched by timestamp (les = ln close, esid = contract id; NaN = no bar)."""

    def __init__(self, ctx):
        self.ctx = ctx
        n = ctx.n
        self.tmin = ctx.ts.tz_convert("UTC").tz_localize(None).to_numpy().astype("datetime64[m]").astype(np.int64)
        assert n < 2 or (np.diff(self.tmin) > 0).all(), "bars are not strictly increasing in time"
        D = ctx.days
        self.io, self.ie = D.i_open.to_numpy(np.int64), D.i_end.to_numpy(np.int64)
        assert (ctx.tod[self.io] == OPEN).all() and (self.ie > self.io).all()
        self.atr = D.atr.to_numpy(float)
        self.unit = 0.1 * self.atr * PV                                   # dollars
        self.traded = ~D.roll.to_numpy(bool) & ~np.isnan(self.atr)        # as core.run_orders(skip_roll=True)
        assert set(D.index[~self.traded]) == set(ctx.roll_dates) | set(ctx.noatr_dates)
        self.day = D.index.to_numpy().astype("datetime64[D]")
        self.year = D.index.year.to_numpy()
        sess = np.full(n, -1, np.int32)
        for q in range(len(D)):                                           # one pass over days, not over bars
            sess[self.io[q]:self.ie[q] + 1] = q
        self.sess = sess
        with np.errstate(divide="ignore", invalid="ignore"):
            self.lc = np.log(ctx.C)
        # ---- s: the 390 most recent in-session 1-minute returns at or before each bar
        ok = np.zeros(n, bool)
        if n > 1:
            ok[1:] = (sess[1:] >= 0) & (sess[1:] == sess[:-1]) & (np.diff(self.tmin) == 1) & (ctx.iid[1:] == ctx.iid[:-1])
        self.ret_ok = ok
        self._pos = pos = np.flatnonzero(ok)
        self._rv = rv = self.lc[pos] - self.lc[pos - 1]
        self._cnt = cnt = np.cumsum(ok)
        self._has = has = cnt >= WIN
        self.s = np.full(n, np.nan)
        if len(rv) >= WIN:
            self.s[has] = ind.stdev(rv, WIN)[cnt[has] - 1]
        self.vwap, self.vsd = ind.session_vwap(ctx.H, ctx.L, ctx.C, ctx.V, ctx.tod == OPEN)
        self._lag, self._dec, self._sig, self._es = {}, {}, None, None

    # -- the second market, loaded only when an es / esr signal is asked for
    def _load_es(self):
        if self._es is None:
            ctx = self.ctx
            x = ctx.extra("ES")
            assert x.index.is_unique, "ES bars: duplicate timestamps"
            x = x.reindex(ctx.ts)                                          # matched by timestamp; NaN = no ES bar
            with np.errstate(divide="ignore", invalid="ignore"):
                les = np.log(x.close.to_numpy(float))
            esid = x.instrument_id.to_numpy(float)
            pos, cnt, has = self._pos, self._cnt, self._has
            d1 = (les[pos] - les[pos - 1]) - self._rv                      # NaN where ES has no bar at b or b-1
            d1[esid[pos] != esid[pos - 1]] = np.nan                        # ... or changed contract (NaN != NaN too)
            sd = np.full(ctx.n, np.nan)
            if len(d1) >= WIN:
                sd[has] = pd.Series(d1).rolling(WIN, min_periods=2).std(ddof=0).to_numpy()[cnt[has] - 1]
            self._es = (les, esid, sd)
        return self._es

    @property
    def les(self):
        return self._load_es()[0]

    @property
    def esid(self):
        return self._load_es()[1]

    @property
    def sd(self):
        return self._load_es()[2]

    def lag(self, L):
        """For every bar: the position of the bar stamped L minutes earlier, or -1 when that minute has no bar."""
        if L not in self._lag:
            t = self.tmin
            p = np.searchsorted(t, t - L)
            self._lag[L] = np.where(t[p] == t - L, p, -1)
        return self._lag[L]

    def signal(self, G):
        """(side, z) of signal G at every 1-minute bar, as if a decision were made at its close.
        side int8 in {+1, -1, 0}; z float, NaN where there is no side or z cannot be computed."""
        f, L = split(G)
        base = _BASE[f] if L is None else f"{_BASE[f]}-{L}"
        if self._sig is None or self._sig[0] != base:
            ctx = self.ctx
            with np.errstate(divide="ignore", invalid="ignore"):
                if L is None:
                    d = ctx.C - self.vwap
                    z = np.abs(d) / self.vsd
                else:
                    p = self.lag(L)
                    ok = p >= 0
                    q = np.where(ok, p, 0)
                    ok &= ctx.iid[q] == ctx.iid
                    if _BASE[f] == "mom":
                        d = np.where(ok, ctx.C - ctx.C[q], np.nan)
                        z = np.abs(self.lc - self.lc[q]) / (self.s * math.sqrt(L))
                    else:
                        ok &= self.esid[q] == self.esid                    # False where either ES bar is missing
                        d = np.where(ok, (self.les - self.les[q]) - (self.lc - self.lc[q]), np.nan)
                        z = np.abs(d) / (self.sd * math.sqrt(L))
                side = np.sign(d)
            side = np.where(np.isnan(side), 0, side).astype(np.int8)
            z = np.where(side != 0, z, np.nan)
            self._sig = (base, side, z)
        _, side, z = self._sig
        return (side if f == _BASE[f] else (-side).astype(np.int8)), z

    def decisions(self, k, traded_only=True):
        """The decisions of holding time k on the traded days (traded_only=False: on every cash day of ctx.days,
        for the replay through core.run_orders, which drops the untraded days itself)."""
        key = (k, traded_only)
        if key not in self._dec:
            assert k in KS
            t, n = self.tmin, self.ctx.n
            rows = np.flatnonzero(self.traded) if traded_only else np.arange(len(self.io))
            t0 = t[self.io[rows]] + (FIRST - OPEN)                         # the 09:59 minute of each day
            cnt = np.maximum((t[self.ie[rows]] - t0) // k, 0)              # decisions whose exit is by the flat bar
            d = np.repeat(rows, cnt)
            m = np.arange(int(cnt.sum())) - np.repeat(np.cumsum(cnt) - cnt, cnt)
            td = np.repeat(t0, cnt) + m * k
            i = np.minimum(np.searchsorted(t, td), max(n - 1, 0))
            x = np.minimum(np.searchsorted(t, td + k), max(n - 1, 0))
            keep = (t[i] == td) & (t[x] == td + k) if n else np.zeros(0, bool)
            dec = Decisions()
            dec.k, dec.i, dec.x, dec.d = k, i[keep], x[keep], d[keep]
            assert (self.sess[dec.i] == dec.d).all() and (self.sess[dec.x] == dec.d).all() and (dec.x > dec.i).all()
            dec.i1 = dec.i + 1                                             # exists: the exit bar is after i
            dec.nx = t[dec.i1] == t[dec.i] + 1
            self._dec[key] = dec
        return self._dec[key]

    def cell(self, G, k, traded_only=True):
        ctx = self.ctx
        dec = self.decisions(k, traded_only)
        side, z = self.signal(G)
        c = Cell()
        c.dec, c.side, c.z = dec, side[dec.i], z[dec.i]
        ref = ctx.C[dec.i]
        c.gross = c.side * (ctx.C[dec.x] - ref) * PV
        c.fill = dec.nx & np.where(c.side > 0, ctx.L[dec.i1] <= ref - TICK, ctx.H[dec.i1] >= ref + TICK) & (c.side != 0)
        return c


def prep(ctx):
    c = ctx.__dict__
    if "_g12_prep" not in c:
        c["_g12_prep"] = Prep(ctx)
    return c["_g12_prep"]


def mask(cell, Z, E):
    """The decisions of a cell at which combination (Z, E) has a trade; E 'ord' = at which it places an order."""
    with np.errstate(invalid="ignore"):
        m = (cell.side != 0) & (cell.z >= Z)
    if E == "lim":
        m = m & cell.fill
    else:
        assert E in ("mkt", "ord")
    return m


def net_of(gross, E):
    return gross - COST[E]


def trades(P, nm, traded_only=True, all_orders=False):
    """The trades of one combination, in time order: day (cash date), i / x (decision and exit bar positions),
    sig_time, exit_time, side, z, ref (decision close = the limit price), exit_px (exit close), gross, net ($),
    unit (the day's 0.1 x ATR in $). all_orders=True (lim only): every order, with `filled`; an unfilled order
    has net NaN."""
    c = parse(nm)
    cell = P.cell(c["G"], c["K"], traded_only)
    m = mask(cell, c["Z"], "ord" if all_orders else c["E"])
    ctx, d = P.ctx, cell.dec
    i, x, row = d.i[m], d.x[m], d.d[m]
    gross = cell.gross[m]
    df = pd.DataFrame({"day": P.day[row].astype("datetime64[ns]"), "i": i, "x": x, "sig_time": ctx.ts[i],
                       "exit_time": ctx.ts[x], "side": cell.side[m].astype(int), "z": cell.z[m], "ref": ctx.C[i],
                       "exit_px": ctx.C[x], "gross": gross, "net": net_of(gross, c["E"]), "unit": P.unit[row]})
    if all_orders:
        df["filled"] = cell.fill[m] if c["E"] == "lim" else True
        df["i1"], df["next_is_t1"] = d.i1[m], d.nx[m]
        df.loc[~df.filled, "net"] = np.nan
    return df


def orders(P, nm):
    """core.simulate keyword arguments of every order of an `mkt` combination on every cash day (core.run_orders
    drops roll days and days without an ATR itself; use one_at_a_time=False: a trade ends on the bar at whose close
    the next one may start). Used by g12_verify only: the grid's P&L is the arithmetic above."""
    c = parse(nm)
    assert c["E"] == "mkt", "only a market entry is a core.simulate order"
    cell = P.cell(c["G"], c["K"], traded_only=False)
    m = mask(cell, c["Z"], "mkt")
    d = cell.dec
    r = 0.1 * P.atr[d.d[m]]
    return [dict(i=int(i), side=int(s), etype="close", exit_i=int(x), r_pts=(float(q) if q == q else None))
            for i, s, x, q in zip(d.i[m], cell.side[m], d.x[m], r)]


def sessions(P, k, traded_only=True):
    """Rows of ctx.days with at least one decision of holding time k: the sessions on which it could trade."""
    return np.unique(P.decisions(k, traded_only).d)


# ------------------------------------------------------------------ command line
def main():
    import run as runner
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", choices=["is", "full"], required=True)
    ap.add_argument("--combo")
    ap.add_argument("--show", type=int, default=12)
    ap.add_argument("--csv")
    a = ap.parse_args()
    pd.set_option("display.width", 250)
    t0 = time.time()
    ctx = core.Ctx(runner.bars(a.phase))
    if a.phase == "is":
        assert ctx.ts[-1] < core.IS_END
    P = prep(ctx)
    print(f"G12 sim   phase {a.phase}   bars {ctx.ts[0]} -> {ctx.ts[-1]}   cash days {len(ctx.days)}"
          f"   traded {int(P.traded.sum())}   prepared in {time.time() - t0:.0f}s")
    if a.combo:
        df = trades(P, a.combo)
        print(f"{a.combo}: {len(df)} trades on {df.day.nunique()} days   gross {df.gross.sum():+.2f}   net {df.net.sum():+.2f}")
        if len(df):
            print(df.sample(min(a.show, len(df)), random_state=3).sort_values("i").to_string())
        if a.csv:
            df.to_csv(a.csv, index=False)
        return
    print("decisions and sessions by holding time:")
    for k in KS:
        d = P.decisions(k)
        print(f"  k {k:>2}  decisions {len(d.i):>7}  sessions {len(np.unique(d.d)):>5}  a day {len(d.i) / max(len(np.unique(d.d)), 1):.1f}")
    rows = []
    for g in GS:
        for k in KS:
            cell = P.cell(g, k)
            for z in ZS:
                rows.append((g, z, k, int(mask(cell, z, "mkt").sum()), int(mask(cell, z, "lim").sum())))
    t = pd.DataFrame(rows, columns=["G", "Z", "K", "mkt", "lim"])
    print("trades by signal x strength, summed over holding times (mkt / lim):")
    print(t.groupby(["G", "Z"], sort=False)[["mkt", "lim"]].sum().unstack().to_string())
    print(f"total {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
