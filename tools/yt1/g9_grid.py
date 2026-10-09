#!/usr/bin/env python3
"""G9 grid - the 230,850 combinations of YT6_SPEC.md (Part 1) evaluated on the signal file of g9_signals.py.

    combos() / name(c) / parse(s)      the grid and its names, e.g. T5.Wam.Bnone.Enone.Mmid.Rpd.Hh4.Snone.Xliq.Nretest
    pick(sig, combo)                   the day's one ORDER of a combination: the first signal of each cash day, inside
                                       the window, that meets every confluence and the target's qualification (on
                                       tradable days when `sig` carries outcomes). Its trade = that row's outcome for
                                       (X, N) where the order filled.
    evaluate(sig, start, end)          one row per combination: n (trades = filled orders), orders, net $, mean R, sd,
                                       t, win %, net by calendar year
    select(table, sig)                 the registered selection: picks 1-5 by t with the overlap rule on orders, pick 6
                                       the consensus combination, and the eligible combination with the largest net $
    reality_check(sig, table)          White's reality check on the daily R series of the eligible combinations
    level_table(tables, names)         each level of each confluence: average of mean R over the combinations using it

    python3 tools/yt1/g9_grid.py --phase is     in-sample grid, selection (G9_selected.json), reality check, levels
    python3 tools/yt1/g9_grid.py --phase full   out-of-sample scoring of the FROZEN picks (never re-selects)
"""
import argparse, hashlib, itertools, json, math, pathlib, sys, time
import numpy as np
import pandas as pd
sys.path.insert(0, str(pathlib.Path(__file__).parent))
import core
import g9_signals

ORDER = ("T", "W", "B", "E", "M", "R", "H", "S", "X", "N")
LEVELS = {"T": (1, 5, 15), "W": ("ldn", "am", "open", "sb", "pm"), "B": ("none", "any", "cont", "fail", "inv"),
          "E": ("none", "disc", "prem"), "M": ("none", "d18", "mid", "both"),
          "R": ("none", "pd", "sess", "pd_brk", "sess_brk"), "H": ("none", "h1", "h4"), "S": ("none", "smt"),
          "X": ("2R", "pdx", "liq"), "N": ("close", "retest", "pos")}
COLUMN = {("W", "ldn"): "w_ldn", ("W", "am"): "w_am", ("W", "open"): "w_open", ("W", "sb"): "w_sb", ("W", "pm"): "w_pm",
          ("B", "inv"): "b_inv", ("E", "disc"): "e_disc", ("E", "prem"): "e_prem",
          ("M", "d18"): "m_d18", ("M", "mid"): "m_mid", ("M", "both"): "m_both",
          ("R", "pd"): "r_pd", ("R", "sess"): "r_sess", ("R", "pd_brk"): "r_pd_brk", ("R", "sess_brk"): "r_sess_brk",
          ("H", "h1"): "h_h1", ("H", "h4"): "h_h4", ("S", "smt"): "s_smt"}
ORDER9 = ORDER[:-1]                 # what fixes the day's order; N only decides how it is entered
N_GRID = 230850
MIN_TRADES = 150                    # eligibility
MAX_PICKS = 5                       # picks by t; pick 6 is the consensus combination
OOS_START = pd.Timestamp("2023-01-01")
OOS_YEARS = (2023, 2024, 2025, 2026)
P_PASS, P_CAND = 0.05 / 101, 0.05 / 6
SEL_PATH = core.OUT / "G9_selected.json"
CSV_LIMIT = 60e6                    # the grid is written as CSV unless the CSV would be larger than this


# ------------------------------------------------------------------ the grid
def exists(c):
    """`M both` does not exist in the London window (the 08:30 open is in the future)."""
    return not (c["W"] == "ldn" and c["M"] == "both")


def combos():
    """The 230,850 combinations as dicts with keys T W B E M R H S X N, in the order of the spec's table (the first
    listed level first; N varies fastest)."""
    return [c for c in (dict(zip(ORDER, v)) for v in itertools.product(*(LEVELS[k] for k in ORDER))) if exists(c)]


def name(c):
    return ".".join(f"{k}{c[k]}" for k in ORDER)


def parse(s):
    parts = s.split(".")
    assert len(parts) == len(ORDER) and all(p[0] == k for p, k in zip(parts, ORDER)), f"not a combination: {s}"
    c = {k: (int(p[1:]) if k == "T" else p[1:]) for p, k in zip(parts, ORDER)}
    assert all(c[k] in LEVELS[k] for k in ORDER), f"unknown level in {s}"
    assert exists(c), f"{s}: M both does not exist in the London window"
    return c


def _cond(sig, key, level, md="100"):
    """Boolean array for one confluence level, or None when the level places no condition on the signal."""
    if key == "T":
        return sig.tf.to_numpy() == level
    if key == "N":
        return None
    if key == "X":
        return None if level == "2R" else sig[f"q_{level}_{md}"].to_numpy(bool)
    if key == "B" and level in ("any", "cont", "fail"):
        agree = sig.bias.to_numpy() == 1
        return agree if level == "any" else agree & (sig.kind.astype(str).to_numpy() == level)
    if level == "none":
        return None
    return sig[COLUMN[(key, level)]].to_numpy(bool)


def _period(sig, start=None, end=None):
    """Rows inside [start, end] (cash dates, both inclusive) that are tradable (when the column is there), in the
    order that defines 'first': by decision bar, a long before a short on the same bar."""
    m = np.ones(len(sig), bool)
    if "tradable" in sig.columns:
        m &= sig.tradable.to_numpy(bool)
    if start is not None:
        m &= (sig.date >= pd.Timestamp(start)).to_numpy()
    if end is not None:
        m &= (sig.date <= pd.Timestamp(end)).to_numpy()
    s = sig[m]
    return s.sort_values(["tf", "i", "side"], ascending=[True, True, False], kind="mergesort")


def pick(sig, combo, start=None, end=None, md="100"):
    """The orders of one combination: signals of its timeframe inside its window that meet every confluence and
    qualify for its target at minimum distance md (and are tradable, when `sig` carries outcomes), the first of each
    cash day. One row = the day's one order; whether it became a trade is the row's f_<X>_<N> column."""
    s = _period(sig, start, end)
    m = np.ones(len(s), bool)
    for k in ORDER:
        c = _cond(s, k, combo[k], md)
        if c is not None:
            m &= c
    s = s[m]
    return s[~s.date.duplicated(keep="first")]


def trades_of(sig, combo, start=None, end=None):
    """The filled orders of a combination with their outcome columns renamed R, pnl, risk_pts."""
    r = pick(sig, combo, start, end)
    X, N = combo["X"], combo["N"]
    r = r[r[g9_signals.ocol("f", X, N)].to_numpy(bool)]
    return r.assign(R=r[g9_signals.ocol("R", X, N)], pnl=r[g9_signals.ocol("pnl", X, N)],
                    risk_pts=r[g9_signals.ocol("risk", X, N)])


class Scan:
    """The period's tradable signals in 'first' order, with the level masks of every (T, W) subset, for fast order
    sets. orders(combo) -> positions (into self.s) of the day's one order of each day; scan() yields every order set
    of the grid in combos() order (one per T W B E M R H S X: the order does not depend on N)."""

    def __init__(self, sig, start=None, end=None):
        self.s = s = _period(sig, start, end)
        self.day = s.date.to_numpy().astype("datetime64[D]").astype(np.int64)
        self.tf = s.tf.to_numpy()
        self._sub = {}

    def sub(self, t, w):
        if (t, w) not in self._sub:
            idx = np.flatnonzero((self.tf == t) & self.s[COLUMN[("W", w)]].to_numpy(bool))
            part = self.s.iloc[idx]
            cond = {(k, lv): _cond(part, k, lv) for k in ORDER9[2:] for lv in LEVELS[k]}
            self._sub[(t, w)] = (idx, self.day[idx], cond)
        return self._sub[(t, w)]

    @staticmethod
    def _first(idx, d, m):
        loc = np.arange(len(idx)) if m is None else np.flatnonzero(m)
        if len(loc):
            dd = d[loc]
            loc = loc[np.r_[True, dd[1:] != dd[:-1]]]                  # the first of each day
        return idx[loc]

    def orders(self, c):
        idx, d, cond = self.sub(c["T"], c["W"])
        m = None
        for k in ORDER9[2:]:
            x = cond[(k, c[k])]
            if x is not None:
                m = x if m is None else m & x
        return self._first(idx, d, m)

    def scan(self):
        def both(a, b):
            return b if a is None else a if b is None else a & b
        for t in LEVELS["T"]:
            for w in LEVELS["W"]:
                idx, d, cond = self.sub(t, w)
                for b in LEVELS["B"]:
                    m1 = cond[("B", b)]
                    for e in LEVELS["E"]:
                        m2 = both(m1, cond[("E", e)])
                        for mm in LEVELS["M"]:
                            if w == "ldn" and mm == "both":
                                continue
                            m3 = both(m2, cond[("M", mm)])
                            for r in LEVELS["R"]:
                                m4 = both(m3, cond[("R", r)])
                                for h in LEVELS["H"]:
                                    m5 = both(m4, cond[("H", h)])
                                    for sm in LEVELS["S"]:
                                        m6 = both(m5, cond[("S", sm)])
                                        for x in LEVELS["X"]:
                                            m7 = both(m6, cond[("X", x)])
                                            yield (t, w, b, e, mm, r, h, sm, x), self._first(idx, d, m7)


def _years(s):
    return list(range(int(s.date.dt.year.min()), int(s.date.dt.year.max()) + 1)) if len(s) else []


def evaluate(sig, start=None, end=None, scan=None):
    """One row per combination on the cash dates start..end, indexed by name, in combos() order:
    T W B E M R H S X N (the levels), orders (the day's one order, filled or not), n (trades = filled orders),
    net ($), mR (mean R), sd, t = mean / (sd / sqrt(n)), win (% of trades with pnl > 0), y<year> = net $ of the
    calendar year."""
    sc = scan or Scan(sig, start, end)
    s = sc.s
    oc = {(X, N): (s[g9_signals.ocol("R", X, N)].to_numpy(), s[g9_signals.ocol("pnl", X, N)].to_numpy(),
                   s[g9_signals.ocol("f", X, N)].to_numpy(bool)) for X in LEVELS["X"] for N in LEVELS["N"]}
    yrs = _years(s)
    y = s.date.dt.year.to_numpy() - (yrs[0] if yrs else 0)
    G = N_GRID
    lev = [[] for _ in ORDER]
    names = []
    orders, n_ = np.zeros(G, np.int32), np.zeros(G, np.int32)
    net, mR, sd, tt_, win = (np.full(G, np.nan) for _ in range(5))
    by = np.zeros((G, len(yrs)))
    g = 0
    for key, pos in sc.scan():
        X = key[-1]
        for N in LEVELS["N"]:
            R, pnl, f = oc[(X, N)]
            p = pos[f[pos]] if N != "close" else pos
            n = len(p)
            if N == "close":
                assert f[pos].all()
            orders[g], n_[g] = len(pos), n
            if n:
                r, pl = R[p], pnl[p]
                net[g], mR[g] = pl.sum(), r.mean()
                win[g] = (pl > 0).mean() * 100
                if n > 1:
                    sd[g] = r.std(ddof=1)
                    if sd[g] > 0:
                        tt_[g] = mR[g] / (sd[g] / math.sqrt(n))
                by[g] = np.bincount(y[p], weights=pl, minlength=len(yrs))
            else:
                net[g] = 0.0
            for q, v in enumerate(key + (N,)):
                lev[q].append(v)
            g += 1
    assert g == G, f"{g} combinations scanned, {G} registered"
    d = {k: lev[q] for q, k in enumerate(ORDER)}
    tb = pd.DataFrame(d)
    tb.insert(0, "name", [".".join(f"{k}{v}" for k, v in zip(ORDER, row)) for row in zip(*lev)])
    tb["orders"], tb["n"], tb["net"], tb["mR"], tb["sd"], tb["t"], tb["win"] = orders, n_, net, mR, sd, tt_, win
    for q, yr in enumerate(yrs):
        tb[f"y{yr}"] = by[:, q]
    return tb.set_index("name")


def eligible(table, min_n=MIN_TRADES):
    """Eligible combinations in ranking order: t descending, ties in the grid's order (the first listed level first)."""
    e = table[table.n >= min_n].copy()
    e = e.sort_values("t", ascending=False, kind="mergesort", na_position="last")
    e["rank"] = np.arange(1, len(e) + 1)
    return e


def _keys(sc, pos):
    """Order identity for the overlap rule: same day, decision bar and side (the bar fixes the day)."""
    return np.unique(sc.s.i.to_numpy()[pos].astype(np.int64) * 2 + (sc.s.side.to_numpy()[pos] > 0))


def _record(row):
    d = {"name": row.name, "combo": {k: (int(row[k]) if k == "T" else str(row[k])) for k in ORDER},
         "n": int(row.n), "orders": int(row.orders), "net": round(float(row.net), 2), "R": float(row.mR),
         "sd": float(row.sd), "t": float(row.t), "win": float(row.win),
         "by_year": {k[1:]: round(float(row[k]), 2) for k in row.index if k.startswith("y") and k[1:].isdigit()}}
    if "rank" in row.index and row["rank"] == row["rank"]:
        d["rank"] = int(row["rank"])
    return d


def level_means(table, names=None):
    """{(confluence, level): (average of mean R, number of combinations, average trades)} over the combinations in
    `names` (default: every combination with a trade) that use the level."""
    t = table if names is None else table.loc[table.index.intersection(names)]
    t = t[t.n > 0]
    out = {}
    for k in ORDER:
        col = t[k].astype(str)
        for lv in LEVELS[k]:
            x = t[(col == str(lv)).to_numpy()]
            out[(k, lv)] = (float(x.mR.mean()) if len(x) else np.nan, int(len(x)), float(x.n.mean()) if len(x) else np.nan)
    return out


def consensus(table, min_n=MIN_TRADES):
    """Pick 6 as registered ('Selection', step 3). Returns (name or None, log lines, structured record).
    For every confluence the level with the highest in-sample average of mean R over the eligible combinations using
    it (ties -> the level listed first). While that combination has fewer than min_n in-sample trades: among the
    confluences not yet changed, the one whose chosen level beats its first-listed level by the smallest margin is set
    to its first-listed level (T and W: 'first-listed' is replaced by the level with the second-highest average, for
    the margin and for the new level); repeat. A combination that is not in the grid (W ldn x M both) has no trades."""
    e = eligible(table, min_n)
    lm = level_means(table, e.index)
    avg = {kl: v[0] for kl, v in lm.items()}
    log, chosen, second = [], {}, {}
    for k in ORDER:
        best = None
        for lv in LEVELS[k]:                                         # listed order; strictly greater replaces
            a = avg[(k, lv)]
            if a == a and (best is None or a > avg[(k, best)]):
                best = lv
        if best is None:
            best = LEVELS[k][0]
        chosen[k] = best
        rest = [lv for lv in LEVELS[k] if lv != best and avg[(k, lv)] == avg[(k, lv)]]
        second[k] = max(rest, key=lambda lv: avg[(k, lv)]) if rest else None      # max(): the first listed on ties
        log.append(f"  {k}: " + "  ".join(f"{lv} {avg[(k, lv)]:+.4f} ({lm[(k, lv)][1]})" for lv in LEVELS[k])
                   + f"   -> {best}")
    changed, steps = [], []
    while True:
        c = dict(chosen)
        nm = name(c)
        n = int(table.n[nm]) if exists(c) else 0
        steps.append({"name": nm, "in_grid": bool(exists(c)), "n": n})
        log.append(f"  combination {nm}: " + (f"{n} in-sample trades" if exists(c) else "not in the grid (W ldn x M both): no trades")
                   + (f" >= {min_n}: this is pick 6" if n >= min_n else f" < {min_n}"))
        if n >= min_n:
            return nm, log, {"levels": {f"{k}:{lv}": avg[(k, lv)] for k in ORDER for lv in LEVELS[k]},
                             "steps": steps, "changed": changed}
        cands = []
        for q, k in enumerate(ORDER):
            if k in [x["confluence"] for x in changed]:
                continue
            alt = second[k] if k in ("T", "W") else LEVELS[k][0]
            if alt is None or alt == chosen[k]:
                continue
            a = avg[(k, alt)]
            margin = avg[(k, chosen[k])] - a if a == a else float("inf")
            cands.append((margin, q, k, alt))
        if not cands:
            log.append("  no confluence left to change: there is no pick 6")
            return None, log, {"levels": {f"{k}:{lv}": avg[(k, lv)] for k in ORDER for lv in LEVELS[k]},
                               "steps": steps, "changed": changed}
        log.append("    margins of the chosen level over its first-listed level (T, W: over the second-highest): "
                   + "  ".join(f"{k} {m:+.4f}" for m, _, k, _ in cands))
        margin, _, k, alt = min(cands)
        log.append(f"    smallest margin: {k} ({chosen[k]} -> {alt}, margin {margin:+.4f})")
        changed.append({"confluence": k, "from": str(chosen[k]), "to": str(alt), "margin": float(margin)})
        chosen[k] = alt


def select(table, sig, start=None, end=None, min_n=MIN_TRADES, max_picks=MAX_PICKS, scan=None):
    """The registered selection. Eligible = at least min_n trades; ranked by t; going down the ranking a combination
    is taken unless more than half of its ORDERS (same day, decision bar and side; share measured on the smaller of the
    two order sets) are orders of one already taken; a pick must have positive mean R; at most max_picks. Then pick 6
    = the consensus combination (a pick whatever its sign), and, recorded with no test, the eligible combination with
    the largest net dollars. `sig`, start, end must be the ones `table` was evaluated on."""
    sc = scan or Scan(sig, start, end)
    e = eligible(table, min_n)
    picks, taken, skipped = [], [], []
    for nm, row in e.iterrows():
        if len(picks) >= max_picks:
            break
        if not (row.mR > 0 and row.t > 0):
            break                                    # the ranking is by t: nothing below has a positive mean R
        k = _keys(sc, sc.orders(parse(nm)))
        assert len(k) == row.orders, "the table and the signal file disagree"
        clash = None
        for pn, pk in taken:
            share = len(np.intersect1d(k, pk, assume_unique=True)) / min(len(k), len(pk))
            if share > 0.5:
                clash = (pn, share)
                break
        if clash:
            skipped.append({"name": nm, "rank": int(row["rank"]), "overlaps": clash[0], "share": round(clash[1], 4)})
            continue
        taken.append((nm, k))
        rec = _record(row)
        rec.update(pick=len(picks) + 1, how="t")
        picks.append(rec)
    cname, clog, crec = consensus(table, min_n)
    if cname is not None:
        row = e.loc[cname]
        rec = _record(row)
        k = _keys(sc, sc.orders(parse(cname)))
        ov = [{"pick": p["pick"], "share": round(len(np.intersect1d(k, pk, assume_unique=True)) / min(len(k), len(pk)), 4)}
              for p, (_, pk) in zip(picks, taken)]
        rec.update(pick=6, how="consensus", same_as_pick=next((p["pick"] for p in picks if p["name"] == cname), None),
                   order_overlap_with_picks=ov)
        picks.append(rec)
    big = e.sort_values("net", ascending=False, kind="mergesort").iloc[0] if len(e) else None
    return {"min_trades": min_n, "n_grid": int(len(table)), "n_with_a_trade": int((table.n > 0).sum()),
            "n_eligible": int(len(e)), "n_eligible_positive": int((e.mR > 0).sum()), "picks": picks,
            "skipped_for_overlap": skipped, "consensus": dict(crec, name=cname, log=clog),
            "largest_net": _record(big) if big is not None else None}


# ------------------------------------------------------------------ White's reality check
def _daily(sc, table, names, dtype=np.float32):
    """(days, X): X[d, j] = the R of combination names[j] on day d, 0 on a day without a trade. Days = the cash
    dates of the period on which at least one tradable signal exists (the days any combination could trade)."""
    s = sc.s
    days = np.unique(sc.day)
    drow = np.searchsorted(days, sc.day)
    col = {n: j for j, n in enumerate(names)}
    X = np.zeros((len(days), len(names)), dtype)
    oc = {(x, N): (s[g9_signals.ocol("R", x, N)].to_numpy(), s[g9_signals.ocol("f", x, N)].to_numpy(bool))
          for x in LEVELS["X"] for N in LEVELS["N"]}
    for key, pos in sc.scan():                                        # one order set, three entries
        base = ".".join(f"{k}{v}" for k, v in zip(ORDER9, key))
        for N in LEVELS["N"]:
            j = col.get(f"{base}.N{N}")
            if j is None:
                continue
            R, f = oc[(key[-1], N)]
            p = pos[f[pos]]
            X[drow[p], j] = R[p]
    return days, X


def _t_days(mean, ss, D):
    """t of a daily series of D days from its mean and its sum of squares: sqrt(D) * mean / sd, sd with D - 1."""
    var = (ss - D * mean ** 2) / (D - 1)
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(var > 0, math.sqrt(D) * mean / np.sqrt(np.where(var > 0, var, 1.0)), np.nan)


def reality_check(sig, table, n_boot=2000, seed=1, start=None, end=None, min_n=MIN_TRADES, chunk=4096, scan=None,
                  names=None, dtype=np.float32, return_max=False):
    """White's reality check as registered (the statistic of g8_grid.reality_check). For each eligible combination j
    the daily series x_j (R per cash day, 0 on a day without a trade) over the D days of the period. The statistic,
    observed and resampled alike, is the day-level t  t_j = sqrt(D) * mean(x_j) / sd(x_j)  (sd with D - 1) and the
    grid's largest t_j. Observed: on x_j as it is (float64). Resampled: each x_j centred on its own mean over the D
    days, D days drawn with replacement (the same days for every combination; rng.integers(0, D, D) per resample,
    numpy default_rng(seed)), t_j recomputed with the resample's own sd; computed in `dtype` over column chunks.
    p = share of resamples whose largest t is at least the observed largest t."""
    t0 = time.time()
    sc = scan or Scan(sig, start, end)
    e = eligible(table, min_n)
    names = list(e.index) if names is None else list(names)
    days, X = _daily(sc, table, names, dtype)
    D = len(days)
    if not names or D < 2:
        return {"n_eligible": len(names), "n_days": D, "p": None}
    rng = np.random.default_rng(seed)
    W = np.zeros((n_boot, D), dtype)
    for b in range(n_boot):
        W[b] = np.bincount(rng.integers(0, D, size=D), minlength=D)      # how often each day is drawn
    mx = np.full(n_boot, -np.inf)
    t_obs = np.empty(len(names))
    for a in range(0, len(names), chunk):
        x64 = X[:, a:a + chunk].astype(np.float64)
        mean = x64.mean(axis=0)
        t_obs[a:a + chunk] = _t_days(mean, (x64 ** 2).sum(axis=0), D)
        xc = (x64 - mean).astype(dtype)
        tb = _t_days((W @ xc) / dtype(D), W @ (xc * xc), D)
        mx = np.maximum(mx, np.nanmax(np.where(np.isnan(tb), -np.inf, tb), axis=1))
        del x64, xc, tb
    j = int(np.nanargmax(t_obs))
    q = {f"q{k}": float(np.quantile(mx, k / 100)) for k in (5, 25, 50, 75, 90, 95, 99)}
    out = {"n_eligible": len(names), "n_days": int(D), "n_boot": int(n_boot), "seed": int(seed),
           "statistic": "largest day-level t over the eligible combinations: sqrt(D) * mean / sd of the daily R "
                        "series (0 on days without a trade)",
           "t_obs_max": float(t_obs[j]), "t_obs_max_name": names[j],
           "t_trade_max": float(e.t.iloc[0]) if len(e) else None, "t_trade_max_name": e.index[0] if len(e) else None,
           "boot_max_t": dict(mean=float(mx.mean()), min=float(mx.min()), max=float(mx.max()), **q),
           "p": float((mx >= t_obs[j]).mean()), "dtype": np.dtype(dtype).name, "chunk": int(chunk),
           "matrix_MB": round(X.nbytes / 1e6, 1), "seconds": round(time.time() - t0, 1)}
    if return_max:
        out["_mx"], out["_t_obs"] = mx, t_obs
    return out


# ------------------------------------------------------------------ tables
def level_table(tables, min_names=None):
    """Each confluence on its own: for every level, the average of mean R over the combinations using it.
    tables = {label: table}; min_names = the combinations averaged over (default: all with at least one trade)."""
    lm = {lab: level_means(tb, min_names) for lab, tb in tables.items()}
    out = []
    for k in ORDER:
        for lv in LEVELS[k]:
            row = {"confluence": k, "level": str(lv)}
            for lab in tables:
                row[f"combos_{lab}"], row[f"R_{lab}"], row[f"trades_{lab}"] = lm[lab][(k, lv)][1], lm[lab][(k, lv)][0], lm[lab][(k, lv)][2]
            out.append(row)
    return pd.DataFrame(out)


def _show(tb, cols=("n", "orders", "net", "mR", "t", "win")):
    f = {"n": "{:.0f}".format, "orders": "{:.0f}".format, "net": "{:+.0f}".format, "mR": "{:+.4f}".format,
         "t": "{:+.2f}".format, "win": "{:.1f}".format, "sd": "{:.3f}".format}
    return tb[list(cols)].to_string(formatters={k: v for k, v in f.items() if k in cols})


def write_grid(table, stem):
    """Writes the grid as <stem>.csv, or as <stem>.parquet when the CSV would be larger than CSV_LIMIT. Returns the
    path written (a stale file of the other format is removed)."""
    csv, pq = pathlib.Path(str(stem) + ".csv"), pathlib.Path(str(stem) + ".parquet")
    table.to_csv(csv)
    if csv.stat().st_size > CSV_LIMIT:
        csv.unlink()
        table.to_parquet(pq)
        return pq
    if pq.exists():
        pq.unlink()
    return csv


def read_grid(stem):
    """A grid written by write_grid (either format). In the CSV the level 'none' stays a string, empty cells are NaN."""
    csv, pq = pathlib.Path(str(stem) + ".csv"), pathlib.Path(str(stem) + ".parquet")
    if pq.exists():
        return pd.read_parquet(pq)
    return pd.read_csv(csv, index_col="name", keep_default_na=False, na_values=[""])


def _sha(p):
    return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()


def _selfcheck(sig, sc, start=None, end=None, n=120, seed=0):
    """pick() and the vectorised scan must give the same orders: checked on n random combinations."""
    all_ = combos()
    assert len(all_) == N_GRID
    rng = np.random.default_rng(seed)
    for q in rng.choice(len(all_), size=n, replace=False):
        c = all_[q]
        assert np.array_equal(pick(sig, c, start, end).index.to_numpy(), sc.s.index[sc.orders(c)].to_numpy()), name(c)
    return n


def _print_rc(rc, label="reality check"):
    b = rc["boot_max_t"]
    print(f"\n{label}: {rc['n_eligible']} combinations, {rc['n_days']} days, {rc['n_boot']} resamples, seed {rc['seed']}"
          f"   ({rc['dtype']}, {rc['matrix_MB']} MB day matrix, column chunks of {rc['chunk']}, {rc['seconds']}s)")
    print(f"  observed largest t (day-level) {rc['t_obs_max']:+.3f}  ({rc['t_obs_max_name']});"
          f"  trade-level largest t {rc['t_trade_max']:+.3f}  ({rc['t_trade_max_name']})")
    print(f"  resampled largest t: median {b['q50']:.3f}  90% {b['q90']:.3f}  95% {b['q95']:.3f}  99% {b['q99']:.3f}"
          f"  max {b['max']:.3f}     p = {rc['p']:.4f}")


def _pick_line(r):
    return (f"  pick {r['pick']}  rank {r.get('rank', 0):>6}  {r['name']:<56} n {r['n']:>4}  orders {r['orders']:>4}"
            f"  net {r['net']:>+8.0f}  R {r['R']:+.4f}  t {r['t']:+.2f}  win {r['win']:.1f}")


def neighbours(ctx, combo_name, start=None, end=None):
    """The two registered neighbours of a combination through the harness module (s_G9.trades): target 2R -> 1.5R
    and 3R; pdx / liq -> minimum distance 0.75R and 1.5R. Trades with a decision date inside [start, end]."""
    import s_G9
    out = []
    for nb in (1, 2):
        df = core.trades_df(s_G9.trades(ctx, c=combo_name, nb=nb))
        d = pd.DatetimeIndex(df.sig_time).tz_localize(None).normalize()
        m = np.ones(len(df), bool)
        if start is not None:
            m &= d >= pd.Timestamp(start)
        if end is not None:
            m &= d <= pd.Timestamp(end)
        df = df[m]
        out.append({"nb": nb, "what": s_G9.nb_label(combo_name, nb), "n": int(len(df)),
                    "net": round(float(df.pnl.sum()), 2), "R": float(df.R.mean()) if len(df) else None})
    return out


# ------------------------------------------------------------------ phases
def phase_is(out=core.OUT, with_neighbours=True):
    t00 = time.time()
    sig = pd.read_parquet(g9_signals.path("is"))
    assert sig.date.max() < OOS_START, "the in-sample signal file reaches into the out-of-sample window"
    print(f"G9 grid   phase is   signals {len(sig)}   {sig.date.min().date()} -> {sig.date.max().date()}")
    print(sig.groupby("tf").agg(signals=("i", "size"), tradable=("tradable", "sum")).to_string())
    sc = Scan(sig)
    print(f"pick() agrees with the vectorised scan on {_selfcheck(sig, sc)} random combinations")
    t0 = time.time()
    table = evaluate(sig, scan=sc)
    t_eval = time.time() - t0
    assert len(table) == N_GRID and list(table.index) == [name(c) for c in combos()]
    (out / "is").mkdir(parents=True, exist_ok=True)
    gp = write_grid(table, out / "is" / "G9_grid")
    e = eligible(table)
    print(f"\ncombinations {len(table)}   order sets {len(table) // 3}   with a trade {(table.n > 0).sum()}"
          f"   eligible (>= {MIN_TRADES} trades) {len(e)}   eligible with mean R > 0: {(e.mR > 0).sum()}"
          f"   [grid evaluated in {t_eval:.0f}s, written to {gp.name} {gp.stat().st_size / 1e6:.1f} MB]")
    print("eligible by timeframe:", e.groupby("T").size().to_dict(), "  by window:", e.groupby("W").size().to_dict(),
          "  by target:", e.groupby("X").size().to_dict(), "  by entry:", e.groupby("N").size().to_dict())
    print("\ntop 20 eligible by t")
    print(_show(e.head(20)))
    sel = select(table, sig, scan=sc)
    if with_neighbours:
        import run
        ctx = core.Ctx(run.bars("is"))
        for r in sel["picks"]:
            r["neighbours_is"] = neighbours(ctx, r["name"])
    sel.update({"spec": "YT6_SPEC.md", "phase": "is", "first_day": str(sig.date.min().date()),
                "last_day": str(sig.date.max().date()), "n_signals": int(len(sig)),
                "grid_file": gp.name, "sha256_grid": _sha(gp), "sha256_signals": _sha(g9_signals.path("is"))})
    p = out / "G9_selected.json"
    new = json.dumps(sel, indent=1)
    if p.exists() and p.read_text() != new:
        print(f"\nNOTE: {p.name} existed with different content and is rewritten")
    p.write_text(new)
    print("\npicks (rank = place in the eligible ranking by t; picks 1-5 by t with the overlap rule, pick 6 = consensus)")
    for r in sel["picks"]:
        print(_pick_line(r) + (f"   [{r['how']}" + (f", the same combination as pick {r['same_as_pick']}" if r.get("same_as_pick") else "") + "]"))
        if "neighbours_is" in r:
            print("          neighbours: " + "   ".join(f"{x['what']}: n {x['n']}  net {x['net']:+.0f}  R "
                                                        + (f"{x['R']:+.4f}" if x["R"] is not None else "nan") for x in r["neighbours_is"]))
    sk = sel["skipped_for_overlap"]
    print(f"  passed over for overlap before the last pick by t: {len(sk)}" + (f"   (first: rank {sk[0]['rank']} {sk[0]['name']} "
          f"shares {sk[0]['share']:.3f} with {sk[0]['overlaps']})" if sk else ""))
    print("\nconsensus construction (pick 6): average of mean R over the eligible combinations using each level (count)")
    for line in sel["consensus"]["log"]:
        print(line)
    r = sel["largest_net"]
    print(f"\nlargest net $ among eligible: {r['name']}  n {r['n']}  orders {r['orders']}  net {r['net']:+.0f}  R {r['R']:+.4f}"
          f"  t {r['t']:+.2f}  rank {r['rank']}")
    rc = reality_check(sig, table, scan=sc)
    (out / "is" / "G9_reality.json").write_text(json.dumps({k: v for k, v in rc.items() if k != "seconds"}, indent=1))
    _print_rc(rc)
    lt = level_table({"is": table}, min_names=e.index)
    lt.to_csv(out / "is" / "G9_levels.csv", index=False)
    print(f"\neach confluence on its own: average of mean R over the {len(e)} eligible combinations using the level")
    print(lt.to_string(index=False, formatters={"R_is": "{:+.4f}".format, "trades_is": "{:.0f}".format}))
    print(f"\ntotal {time.time() - t00:.0f}s")
    return table, sel, rc


def _oos_stats(tr, years=OOS_YEARS):
    """n, net, mean R, win, bootstrap p and net by calendar year of a set of trades (columns date, R, pnl)."""
    n = len(tr)
    out = {"n": int(n)}
    if n == 0:
        return out
    yr = tr.date.dt.year
    by = {int(y): round(float(tr.pnl[yr == y].sum()), 2) for y in years}
    out.update(net=round(float(tr.pnl.sum()), 2), R=float(tr.R.mean()), win=float((tr.pnl > 0).mean() * 100),
               p=core.boot_p(tr.R.to_numpy()), by_year=by, years_positive=int(sum(v > 0 for v in by.values())))
    return out


def pick_verdict(sig, ctx, combo_name, start, years=OOS_YEARS):
    """The registered out-of-sample test of one frozen pick, on its trades from `start` on. The neighbours come from
    the harness module on the bars (ctx); the pick's own trades from the signal file, cross-checked with the harness."""
    import s_G9
    tr = trades_of(sig, parse(combo_name), start=start)
    out = _oos_stats(tr, years)
    n = out["n"]
    hd = core.trades_df(s_G9.trades(ctx, c=combo_name, nb=0))
    hd = hd[pd.DatetimeIndex(hd.sig_time).tz_localize(None).normalize() >= pd.Timestamp(start)]
    out["harness_agrees"] = bool(len(hd) == n and abs(hd.pnl.sum() - tr.pnl.sum()) < 0.005)
    nb = neighbours(ctx, combo_name, start=start)
    out["neighbours"] = nb
    if n == 0:
        out["verdict"] = "not enough data"
        return out
    ch = {"n": n >= 100, "R": out["R"] >= 0.05, "years": out["years_positive"] >= 3,
          "neighbours": all(x["R"] is not None and x["R"] > 0 for x in nb)}
    out["checks"] = {k: bool(v) for k, v in ch.items()}
    out["p_pass"], out["p_candidate"] = P_PASS, P_CAND
    p = out["p"]
    if n < 100:
        out["verdict"] = "not enough data"
    elif all(ch.values()) and p < P_PASS:
        out["verdict"] = "passes"
    elif all(ch.values()) and p < P_CAND:
        out["verdict"] = "candidate"
    else:
        out["verdict"] = "fails"
    return out


def phase_full(out=core.OUT, sig_path=None, oos_start=OOS_START, sel_path=None, dry=False, bars_phase="full",
               frozen_dir=None):
    """Scores the frozen picks out of sample. Reads G9_selected.json and the frozen in-sample grid; selects nothing."""
    from scipy.stats import spearmanr
    import run
    t00 = time.time()
    sel = json.loads(pathlib.Path(sel_path or SEL_PATH).read_text())               # frozen; never rewritten here
    sp = pathlib.Path(sig_path or g9_signals.path("full"))
    if not sp.exists():
        raise SystemExit(f"{sp} does not exist: run  python3 tools/yt1/g9_signals.py --phase full  first")
    sig = pd.read_parquet(sp)
    oos_start = pd.Timestamp(oos_start)
    is_end = oos_start - pd.Timedelta(days=1)
    if sig.date.max() < oos_start:
        raise SystemExit("no out-of-sample bars in this signal file: the full phase cannot run here")
    print(f"G9 grid   phase full{'  (DRY RUN on a made-up split: numbers mean nothing)' if dry else ''}"
          f"   signals {len(sig)}   {sig.date.min().date()} -> {sig.date.max().date()}   out of sample from {oos_start.date()}")
    d = out / "full"
    d.mkdir(parents=True, exist_ok=True)
    t_is, t_oos, t_all = evaluate(sig, end=is_end), evaluate(sig, start=oos_start), evaluate(sig)
    p1, p2 = write_grid(t_oos, d / "G9_grid_oos"), write_grid(t_all, d / "G9_grid_full")
    print(f"wrote {p1.name}, {p2.name}")
    frozen = read_grid(pathlib.Path(frozen_dir or (core.OUT / "is")) / "G9_grid")
    assert list(frozen.index) == list(t_is.index)
    same = (frozen.n.to_numpy() == t_is.n.to_numpy()) & (np.abs(frozen.net.to_numpy() - t_is.net.to_numpy()) < 0.005)
    same = pd.Series(same, index=t_is.index)
    print(f"in-sample grid rebuilt from the full-span signals: {int(same.sum())} of {len(t_is)} combinations have the "
          f"frozen n and net $" + ("" if same.all() else "   <-- NOT ALL: the frozen grid is not reproduced"))
    if dry:                                          # the comparison itself, on a period the frozen grid does cover
        s2 = (frozen.n.to_numpy() == t_all.n.to_numpy()) & (np.abs(frozen.net.to_numpy() - t_all.net.to_numpy()) < 0.005)
        print(f"(dry run: the split is made up, so the line above cannot be complete; the frozen grid against the whole "
              f"in-sample file: {int(s2.sum())} of {len(t_all)})")
    res = {"oos_start": str(oos_start.date()), "last_day": str(sig.date.max().date()), "picks": [],
           "is_grid_reproduced": int(same.sum()), "n_grid": int(len(t_is))}
    ctx = core.Ctx(run.bars(bars_phase))

    print(f"\nfrozen picks, out of sample (passes: p < {P_PASS:.6f}; candidate: p < {P_CAND:.4f})")
    for r in sel["picks"]:
        v = pick_verdict(sig, ctx, r["name"], oos_start)
        v.update(pick=r["pick"], how=r["how"], name=r["name"], is_n=r["n"], is_R=r["R"], is_t=r["t"],
                 is_rank=r.get("rank"), is_reproduced=bool(same.get(r["name"], False)))
        res["picks"].append(v)
        nbs = "   ".join(f"{x['what']}: n {x['n']} R " + (f"{x['R']:+.4f}" if x["R"] is not None else "nan") for x in v["neighbours"])
        if v["n"]:
            print(f"  pick {r['pick']} ({r['how']})  {r['name']:<56} n {v['n']:>4}  net {v['net']:>+8.0f}  R {v['R']:+.4f}"
                  f"  p {v['p']:.5f}  years {v['by_year']}  neighbours [{nbs}]  -> {v['verdict']}  {v.get('checks')}"
                  f"   [in sample: n {r['n']}  R {r['R']:+.4f}  t {r['t']:+.2f}]   harness agrees: {v['harness_agrees']}")
        else:
            print(f"  pick {r['pick']} ({r['how']})  {r['name']}  no out-of-sample trades -> {v['verdict']}")
    r = sel["largest_net"]
    if r is not None:
        v = _oos_stats(trades_of(sig, parse(r["name"]), start=oos_start))
        v.update(name=r["name"], is_n=r["n"], is_net=r["net"], is_R=r["R"], note="recorded, no test attached")
        res["largest_net"] = v
        print(f"  largest in-sample net $ (no test attached): {r['name']}  out of sample n {v['n']}  net {v.get('net', 0):+.0f}"
              f"  R {v.get('R', float('nan')):+.4f}   [in sample: n {r['n']}  net {r['net']:+.0f}]")

    # ---- does in-sample rank predict anything? (description, not a test)
    e = eligible(frozen)
    j = pd.DataFrame({"R_is": e.mR, "t_is": e.t, "R_oos": t_oos.mR.reindex(e.index), "n_oos": t_oos.n.reindex(e.index)})
    jj = j[j.n_oos > 0]
    rho, rho_p = spearmanr(jj.R_is, jj.R_oos) if len(jj) > 2 else (np.nan, np.nan)
    top = j.head(int(math.ceil(len(e) * 0.10)))                      # e is in ranking order (t descending)
    top = top[top.n_oos > 0]
    anyt = t_oos[t_oos.n > 0]
    res["rank"] = {"n_eligible": int(len(e)), "n_with_oos_trades": int(len(jj)), "spearman_R_is_vs_R_oos": float(rho),
                   "spearman_p": float(rho_p), "top10pct_n": int(len(top)), "top10pct_R_oos": float(top.R_oos.mean()),
                   "top10pct_share_positive": float((top.R_oos > 0).mean()),
                   "eligible_R_oos": float(jj.R_oos.mean()), "eligible_share_positive": float((jj.R_oos > 0).mean()),
                   "whole_grid_R_oos": float(anyt.mR.mean()), "whole_grid_combos": int(len(anyt))}
    k = res["rank"]
    print(f"\ndoes in-sample rank predict anything?  Spearman (mean R in sample vs out of sample, {k['n_with_oos_trades']}"
          f" eligible combinations) {k['spearman_R_is_vs_R_oos']:+.3f}")
    print(f"  out-of-sample mean R, averaged over combinations: in-sample top 10 % by t ({k['top10pct_n']}) "
          f"{k['top10pct_R_oos']:+.4f}   all eligible {k['eligible_R_oos']:+.4f}   every combination with a trade "
          f"({k['whole_grid_combos']}) {k['whole_grid_R_oos']:+.4f}")

    # ---- each confluence on its own, both periods, over the in-sample-eligible combinations
    lt = level_table({"is": frozen, "oos": t_oos}, min_names=e.index)
    lt.to_csv(d / "G9_levels.csv", index=False)
    print(f"\neach confluence on its own: average of mean R over the in-sample-eligible combinations using the level")
    print(lt.to_string(index=False, formatters={"R_is": "{:+.4f}".format, "R_oos": "{:+.4f}".format,
                                                "trades_is": "{:.0f}".format, "trades_oos": "{:.0f}".format}))

    # ---- hindsight: the top of the full-span grid (the top of 230,850, labelled as such)
    ea = eligible(t_all)
    print(f"\nHINDSIGHT (full span, top of {N_GRID:,}; {len(ea)} with >= {MIN_TRADES} trades): top 10 by net $")
    print(_show(ea.sort_values("net", ascending=False, kind="mergesort").head(10)))
    print("HINDSIGHT: top 10 by t")
    print(_show(ea.head(10)))
    rc = reality_check(sig, t_all)
    (d / "G9_reality_full.json").write_text(json.dumps({k: v for k, v in rc.items() if k != "seconds"}, indent=1))
    if rc.get("p") is not None:
        _print_rc(rc, "full-span reality check")
    res["hindsight"] = {"by_net": [_record(r) for _, r in ea.sort_values("net", ascending=False, kind="mergesort").head(10).iterrows()],
                        "by_t": [_record(r) for _, r in ea.head(10).iterrows()],
                        "reality_check": {k: v for k, v in rc.items() if k != "seconds"}}
    (d / "G9_oos.json").write_text(json.dumps(res, indent=1, default=str))
    print(f"\ntotal {time.time() - t00:.0f}s")
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", choices=["is", "full"], required=True)
    ap.add_argument("--dry-split", help="code test only: run the full phase on a made-up split date inside the in-sample data")
    ap.add_argument("--dry-out", help="code test only: directory for the dry run's files")
    a = ap.parse_args()
    pd.set_option("display.width", 250)
    pd.set_option("display.max_colwidth", 80)
    if a.phase == "is":
        phase_is()
    elif a.dry_split:
        assert a.dry_out, "--dry-split needs --dry-out (the real output directory is never written by a dry run)"
        o = pathlib.Path(a.dry_out)
        assert core.OUT not in o.resolve().parents and o.resolve() != core.OUT
        phase_full(out=o, sig_path=g9_signals.path("is"), oos_start=a.dry_split, dry=True, bars_phase="is")
    else:
        phase_full()


if __name__ == "__main__":
    main()
