#!/usr/bin/env python3
"""G11 grid - the 25,920 combinations of YT8_SPEC.md (Part 1) evaluated on the trade file of g11_sim.py.

    combos() / name(c) / parse(s)   the grid and its names, e.g. Lor15.Kc5.Dext.Nconf.Snear.X2R.W11.Eone.Fnone
    pick(trades, combo)             that combination's trades: the simulated trades of its (L, K, D, N, S, X) cell,
                                    restricted by the cut-off (W 11: entries by 11:00 only), by re-entry (E one keeps
                                    trade 1 only) and by the side filter (F other than none keeps a day only if the
                                    flag is true; a rejected day has no trade at all)
    evaluate(trades, start, end)    one row per combination: n, days traded, net $, total R, mean R, sd, t, win %,
                                    net by calendar year, max drawdown in $ on the trade sequence
    select(table, trades)           the registered selection: eligible = at least 215 trades; picks 1-5 by t with the
                                    overlap rule on (day, side); pick 6 = the eligible combination with the largest
                                    total R if it is not already a pick
    reality_check(trades, table)    White's reality check on the daily R series of the eligible combinations
    level_table(tables, names)      each level of each of the nine choices: average of mean R over the combinations

    python3 tools/yt1/g11_grid.py --phase is     in-sample grid, selection (G11_selected.json), reality check, levels
    python3 tools/yt1/g11_grid.py --phase full   out-of-sample scoring of the FROZEN picks (never re-selects)
"""
import argparse, hashlib, itertools, json, math, pathlib, re, sys, time
import numpy as np
import pandas as pd
sys.path.insert(0, str(pathlib.Path(__file__).parent))
import core
import g11_sim as gs

ORDER = ("L", "K", "D", "N", "S", "X", "W", "E", "F")
LEVELS = {"L": gs.LS, "K": gs.KS, "D": gs.DS, "N": gs.NS, "S": gs.SS, "X": gs.XS, "W": ("11", "12"),
          "E": ("one", "re"), "F": ("none", "ema200", "vwap", "ema921")}
CELL = ORDER[:6]                    # what is simulated; W, E, F only select among a cell's trades
N_GRID = 25920
MIN_TRADES = 215                    # eligibility: 60 trades a year in sample
MIN_TRADES_FULL = 430               # the hindsight tables on the full span
MAX_PICKS = 5                       # picks by t; pick 6 = the largest total R
OOS_START = pd.Timestamp("2023-01-01")
OOS_YEARS = (2023, 2024, 2025, 2026)
P_PASS, P_CAND = 0.05 / 112, 0.05 / 6
MIN_TRADES_YEAR = 60                # "beats ORB v1.4", condition (c)
ADJ_X = {"1.5R": "2R", "2R": "3R", "3R": "2R", "hold": "3R"}
OTHER_W = {"11": "12", "12": "11"}
SEL_PATH = core.OUT / "G11_selected.json"
_NAME = re.compile(r"^L(\w+)\.K(\w+)\.D(\w+)\.N(\w+)\.S(\w+)\.X([\w.]+)\.W(\d+)\.E(\w+)\.F(\w+)$")


# ------------------------------------------------------------------ the grid
def exists(c):
    return gs.exists(c["L"], c["N"], c["S"])


def combos():
    """The 25,920 combinations as dicts with keys L K D N S X W E F, in the order of the spec's table (the first
    listed level first; F varies fastest)."""
    return [c for c in (dict(zip(ORDER, v)) for v in itertools.product(*(LEVELS[k] for k in ORDER))) if exists(c)]


def name(c):
    return ".".join(f"{k}{c[k]}" for k in ORDER)


def parse(s):
    m = _NAME.match(s)
    assert m, f"not a combination: {s}"
    c = dict(zip(ORDER, m.groups()))
    assert all(c[k] in LEVELS[k] for k in ORDER), f"unknown level in {s}"
    assert exists(c), f"{s}: this level x entry x stop does not exist"
    return c


def neighbour(c, nb):
    """The combination itself (nb 0), with the other cut-off (nb 1), with the adjacent target (nb 2: 1.5R -> 2R,
    2R -> 3R, 3R -> 2R, hold -> 3R)."""
    c = dict(c)
    if nb == 1:
        c["W"] = OTHER_W[c["W"]]
    elif nb == 2:
        c["X"] = ADJ_X[c["X"]]
    else:
        assert nb == 0
    return c


def _period(trades, start=None, end=None):
    m = np.ones(len(trades), bool)
    if start is not None:
        m &= (trades.day >= pd.Timestamp(start)).to_numpy()
    if end is not None:
        m &= (trades.day <= pd.Timestamp(end)).to_numpy()
    return trades if m.all() else trades[m]


def pick(trades, combo, start=None, end=None):
    """The trades of one combination (rows of the trade file, in time order)."""
    t = _period(trades, start, end)
    m = np.ones(len(t), bool)
    for k in CELL:
        m &= (t[k] == combo[k]).to_numpy()
    if combo["W"] == "11":
        m &= t.in11.to_numpy()
    if combo["E"] == "one":
        m &= (t.which == 1).to_numpy()
    if combo["F"] != "none":
        m &= t["f_" + combo["F"]].to_numpy()
    return t[m].sort_values(["day", "which"], kind="mergesort")


class Cells:
    """The period's trades as arrays, grouped by cell, for fast selection. sel(combo) -> positions into the arrays
    (time order within the cell)."""

    def __init__(self, trades, start=None, end=None):
        t = _period(trades, start, end)
        code = np.zeros(len(t), np.int64)
        for k in CELL:
            cat = t[k].astype(pd.CategoricalDtype(list(LEVELS[k])))
            assert not cat.isna().any()
            code = code * len(LEVELS[k]) + cat.cat.codes.to_numpy()
        order = np.lexsort((t.which.to_numpy(), t.day.to_numpy(), code))
        self.t = t = t.iloc[order]
        code = code[order]
        self.day = t.day.to_numpy().astype("datetime64[D]").astype(np.int64)
        self.year = t.day.dt.year.to_numpy()
        self.side, self.which, self.in11 = t.side.to_numpy(), t.which.to_numpy(), t.in11.to_numpy(bool)
        self.pnl, self.R = t.pnl.to_numpy(float), t.R.to_numpy(float)
        self.flag = {f: t["f_" + f].to_numpy(bool) for f in LEVELS["F"][1:]}
        u, first = np.unique(code, return_index=True)
        self._span = {int(c): (int(a), int(b)) for c, a, b in zip(u, first, np.r_[first[1:], len(code)])}

    @staticmethod
    def code(c):
        x = 0
        for k in CELL:
            x = x * len(LEVELS[k]) + LEVELS[k].index(c[k])
        return x

    def span(self, c):
        return self._span.get(self.code(c), (0, 0))

    def mask(self, a, b, W, E, F):
        m = np.ones(b - a, bool)
        if W == "11":
            m &= self.in11[a:b]
        if E == "one":
            m &= self.which[a:b] == 1
        if F != "none":
            m &= self.flag[F][a:b]
        return m

    def sel(self, c):
        a, b = self.span(c)
        return a + np.flatnonzero(self.mask(a, b, c["W"], c["E"], c["F"]))


def _years(t):
    return list(range(int(t.day.dt.year.min()), int(t.day.dt.year.max()) + 1)) if len(t) else []


def evaluate(trades, start=None, end=None, cells=None):
    """One row per combination on the cash dates start..end, indexed by name, in combos() order: the levels,
    n (trades), days (days traded), net ($), totR (sum of R), mR (mean R), sd, t = mean / (sd / sqrt(n)),
    win (% of trades with pnl > 0), dd (max drawdown in $ on the trade sequence, <= 0), y<year> = net $ of the
    calendar year."""
    cl = cells or Cells(trades, start, end)
    yrs = _years(cl.t)
    y0 = yrs[0] if yrs else 0
    all_ = combos()
    G = len(all_)
    assert G == N_GRID
    n_, days = np.zeros(G, np.int32), np.zeros(G, np.int32)
    net, totR, dd = np.zeros(G), np.zeros(G), np.zeros(G)
    mR, sd, tt_, win = (np.full(G, np.nan) for _ in range(4))
    by = np.zeros((G, len(yrs)))
    for g, c in enumerate(all_):
        p = cl.sel(c)
        n = len(p)
        n_[g] = n
        if not n:
            continue
        r, pl = cl.R[p], cl.pnl[p]
        days[g] = int((cl.which[p] == 1).sum())
        net[g], totR[g], mR[g] = pl.sum(), r.sum(), r.mean()
        win[g] = (pl > 0).mean() * 100
        dd[g] = core.max_dd(pl)
        if n > 1:
            sd[g] = r.std(ddof=1)
            if sd[g] > 0:
                tt_[g] = mR[g] / (sd[g] / math.sqrt(n))
        by[g] = np.bincount(cl.year[p] - y0, weights=pl, minlength=len(yrs))
    tb = pd.DataFrame({k: [c[k] for c in all_] for k in ORDER})
    tb.insert(0, "name", [name(c) for c in all_])
    tb["n"], tb["days"], tb["net"], tb["totR"], tb["mR"], tb["sd"], tb["t"], tb["win"], tb["dd"] = \
        n_, days, np.round(net, 2), totR, mR, sd, tt_, win, np.round(dd, 2)
    for q, yr in enumerate(yrs):
        tb[f"y{yr}"] = np.round(by[:, q], 2)
    return tb.set_index("name")


def eligible(table, min_n=MIN_TRADES):
    """Eligible combinations in ranking order: t descending, ties in the grid's order (the first listed level first)."""
    e = table[table.n >= min_n].copy()
    e = e.sort_values("t", ascending=False, kind="mergesort", na_position="last")
    e["rank"] = np.arange(1, len(e) + 1)
    return e


def _record(row):
    d = {"name": row.name, "combo": {k: str(row[k]) for k in ORDER}, "n": int(row.n), "days": int(row.days),
         "net": round(float(row.net), 2), "totR": float(row.totR), "R": float(row.mR), "sd": float(row.sd),
         "t": float(row.t), "win": float(row.win), "dd": round(float(row.dd), 2),
         "by_year": {k[1:]: round(float(row[k]), 2) for k in row.index if k.startswith("y") and k[1:].isdigit()}}
    if "rank" in row.index and row["rank"] == row["rank"]:
        d["rank"] = int(row["rank"])
    return d


def _dayside(cl, c):
    """The (day, side) pairs a combination trades, as sorted integers day * 2 + (side > 0)."""
    p = cl.sel(c)
    return np.unique(cl.day[p] * 2 + (cl.side[p] > 0))


def select(table, trades, start=None, end=None, min_n=MIN_TRADES, max_picks=MAX_PICKS, cells=None):
    """The registered selection. Eligible = at least min_n trades; ranked by t; going down the ranking a combination
    is taken unless more than half of the days it trades are days a pick already taken trades on the same side (the
    share is measured on the smaller of the two day sets); a pick must have positive mean R; at most max_picks. Then
    pick 6 = the eligible combination with the largest total R (ties: the grid's order) if it is not already a pick.
    `trades`, start, end must be the ones `table` was evaluated on."""
    cl = cells or Cells(trades, start, end)
    e = eligible(table, min_n)
    picks, taken, skipped, n_skipped = [], [], [], 0
    for nm, row in e.iterrows():
        if len(picks) >= max_picks:
            break
        if not (row.mR > 0 and row.t > 0):
            break                                    # the ranking is by t: nothing below has a positive mean R
        k = _dayside(cl, parse(nm))
        assert len(k) == row.days, "the table and the trade file disagree"
        clash = None
        for pn, pk in taken:
            share = len(np.intersect1d(k, pk, assume_unique=True)) / min(len(k), len(pk))
            if share > 0.5:
                clash = (pn, share)
                break
        if clash:
            n_skipped += 1
            if len(skipped) < 200:
                skipped.append({"name": nm, "rank": int(row["rank"]), "overlaps": clash[0], "share": round(clash[1], 4)})
            continue
        taken.append((nm, k))
        rec = _record(row)
        rec.update(pick=len(picks) + 1, how="t")
        picks.append(rec)
    big = e.sort_values("totR", ascending=False, kind="mergesort").iloc[0] if len(e) else None
    largest = None
    if big is not None:
        largest = _record(big)
        same = next((p["pick"] for p in picks if p["name"] == big.name), None)
        k = _dayside(cl, parse(big.name))
        largest["same_as_pick"] = same
        largest["day_overlap_with_picks"] = [
            {"pick": p["pick"], "share": round(len(np.intersect1d(k, pk, assume_unique=True)) / min(len(k), len(pk)), 4)}
            for p, (_, pk) in zip(picks, taken)]
        if same is None:
            rec = dict(largest)
            rec.update(pick=6, how="largest total R")
            picks.append(rec)
    return {"min_trades": min_n, "n_grid": int(len(table)), "n_with_a_trade": int((table.n > 0).sum()),
            "n_eligible": int(len(e)), "n_eligible_positive": int((e.mR > 0).sum()), "picks": picks,
            "n_skipped_for_overlap": n_skipped, "skipped_for_overlap_first_200": skipped,
            "largest_total_R": largest}


# ------------------------------------------------------------------ White's reality check
def period_days(setups, start=None, end=None):
    """The traded cash days of the period (every day of the set-up file: the day filter of run_orders(skip_roll=2))."""
    d = np.unique(setups.day.to_numpy().astype("datetime64[D]"))
    if start is not None:
        d = d[d >= np.datetime64(pd.Timestamp(start), "D")]
    if end is not None:
        d = d[d <= np.datetime64(pd.Timestamp(end), "D")]
    return d.astype(np.int64)


def _daily(cl, names, days, dtype=np.float32):
    """X[d, j] = the sum of R of combination names[j] over its trades of day d, 0 on a day without a trade."""
    X = np.zeros((len(days), len(names)), dtype)
    for j, nm in enumerate(names):
        p = cl.sel(parse(nm))
        row = np.searchsorted(days, cl.day[p])
        assert (days[row] == cl.day[p]).all(), "a trade on a day that is not in the day list"
        X[:, j] = np.bincount(row, weights=cl.R[p], minlength=len(days))
    return X


def _t_days(mean, ss, D):
    """t of a daily series of D days from its mean and its sum of squares: sqrt(D) * mean / sd, sd with D - 1."""
    var = (ss - D * mean ** 2) / (D - 1)
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(var > 0, math.sqrt(D) * mean / np.sqrt(np.where(var > 0, var, 1.0)), np.nan)


def reality_check(trades, table, days, n_boot=2000, seed=1, start=None, end=None, min_n=MIN_TRADES, chunk=4096,
                  cells=None, names=None, dtype=np.float32, return_max=False):
    """White's reality check as YT5 / YT6 (the statistic of g9_grid.reality_check). For each eligible combination j
    the daily series x_j (sum of R per cash day, 0 on a day without a trade) over the D traded days of the period.
    The statistic, observed and resampled alike, is the day-level t  t_j = sqrt(D) * mean(x_j) / sd(x_j)  (sd with
    D - 1) and the grid's largest t_j. Observed: on x_j as it is (float64). Resampled: each x_j centred on its own
    mean, D days drawn with replacement (the same days for every combination; rng.integers(0, D, D) per resample,
    numpy default_rng(seed)), t_j recomputed with the resample's own sd; computed in `dtype` over column chunks.
    p = share of resamples whose largest t is at least the observed largest t."""
    t0 = time.time()
    cl = cells or Cells(trades, start, end)
    e = eligible(table, min_n)
    names = list(e.index) if names is None else list(names)
    days = np.asarray(days, np.int64)
    D = len(days)
    if not names or D < 2:
        return {"n_eligible": len(names), "n_days": int(D), "p": None}
    X = _daily(cl, names, days, dtype)
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
                        "series (sum of the day's R, 0 on days without a trade)",
           "t_obs_max": float(t_obs[j]), "t_obs_max_name": names[j],
           "t_trade_max": float(e.t.iloc[0]) if len(e) else None, "t_trade_max_name": e.index[0] if len(e) else None,
           "boot_max_t": dict(mean=float(mx.mean()), min=float(mx.min()), max=float(mx.max()), **q),
           "p": float((mx >= t_obs[j]).mean()), "dtype": np.dtype(dtype).name, "chunk": int(chunk),
           "matrix_MB": round(X.nbytes / 1e6, 1), "seconds": round(time.time() - t0, 1)}
    if return_max:
        out["_mx"], out["_t_obs"] = mx, t_obs
    return out


# ------------------------------------------------------------------ tables
def level_means(table, names=None):
    """{(choice, level): (average of mean R, number of combinations, average trades)} over the combinations in
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


def level_table(tables, min_names=None):
    """Each choice on its own: for every level, the average of mean R over the combinations using it.
    tables = {label: table}; min_names = the combinations averaged over (default: all with at least one trade)."""
    lm = {lab: level_means(tb, min_names) for lab, tb in tables.items()}
    out = []
    for k in ORDER:
        for lv in LEVELS[k]:
            row = {"choice": k, "level": str(lv)}
            for lab in tables:
                row[f"combos_{lab}"], row[f"R_{lab}"], row[f"trades_{lab}"] = lm[lab][(k, lv)][1], lm[lab][(k, lv)][0], lm[lab][(k, lv)][2]
            out.append(row)
    return pd.DataFrame(out)


def _show(tb, cols=("n", "days", "net", "totR", "mR", "t", "win", "dd")):
    f = {"n": "{:.0f}".format, "days": "{:.0f}".format, "net": "{:+.0f}".format, "totR": "{:+.1f}".format,
         "mR": "{:+.4f}".format, "t": "{:+.2f}".format, "win": "{:.1f}".format, "sd": "{:.3f}".format,
         "dd": "{:.0f}".format}
    return tb[list(cols)].to_string(formatters={k: v for k, v in f.items() if k in cols})


def write_grid(table, stem):
    p = pathlib.Path(str(stem) + ".csv")
    table.to_csv(p)
    return p


def read_grid(stem):
    """A grid written by write_grid. The level 'none' stays a string, W stays a string, empty cells are NaN."""
    return pd.read_csv(pathlib.Path(str(stem) + ".csv"), index_col="name", keep_default_na=False, na_values=[""],
                       dtype={k: str for k in ORDER})


def _sha(p):
    return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()


def _selfcheck(trades, cl, start=None, end=None, n=160, seed=0):
    """pick() and the grouped selection must give the same trades: checked on n random combinations."""
    all_ = combos()
    assert len(all_) == N_GRID and len({name(c) for c in all_}) == N_GRID
    assert all(parse(name(c)) == c for c in all_)
    rng = np.random.default_rng(seed)
    for q in rng.choice(len(all_), size=n, replace=False):
        c = all_[q]
        a = pick(trades, c, start, end)
        p = cl.sel(c)
        assert len(a) == len(p) and np.array_equal(a.pnl.to_numpy(), cl.pnl[p]) and \
            np.array_equal(a.day.to_numpy().astype("datetime64[D]").astype(np.int64), cl.day[p]), name(c)
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
    return (f"  pick {r['pick']}  rank {r.get('rank', 0):>5}  {r['name']:<50} n {r['n']:>4}  days {r['days']:>4}"
            f"  net {r['net']:>+8.0f}  totR {r['totR']:>+7.1f}  R {r['R']:+.4f}  t {r['t']:+.2f}  win {r['win']:.1f}"
            f"  dd {r['dd']:.0f}")


# ------------------------------------------------------------------ phases
def phase_is(out=core.OUT):
    t00 = time.time()
    tp, sp = gs.path("is"), gs.path("is", "setups")
    trades, setups = pd.read_parquet(tp), pd.read_parquet(sp)
    assert trades.day.max() < OOS_START and trades.exit_time.max() < core.IS_END, \
        "the in-sample trade file reaches into the out-of-sample window"
    days = period_days(setups)
    print(f"G11 grid   phase is   trades {len(trades)}   {trades.day.min().date()} -> {trades.day.max().date()}"
          f"   traded days {len(days)}")
    cl = Cells(trades)
    print(f"pick() agrees with the grouped selection on {_selfcheck(trades, cl)} random combinations")
    t0 = time.time()
    table = evaluate(trades, cells=cl)
    t_eval = time.time() - t0
    assert len(table) == N_GRID and list(table.index) == [name(c) for c in combos()]
    (out / "is").mkdir(parents=True, exist_ok=True)
    gp = write_grid(table, out / "is" / "G11_grid")
    e = eligible(table)
    print(f"\ncombinations {len(table)}   cells {len(gs.cells())}   with a trade {(table.n > 0).sum()}"
          f"   eligible (>= {MIN_TRADES} trades) {len(e)}   eligible with mean R > 0: {(e.mR > 0).sum()}"
          f"   [grid evaluated in {t_eval:.0f}s, written to {gp.name} {gp.stat().st_size / 1e6:.1f} MB]")
    for k in ORDER:
        print(f"  eligible by {k}: " + "  ".join(f"{lv} {int((e[k].astype(str) == lv).sum())}" for lv in LEVELS[k]))
    print("\ntop 20 eligible by t")
    print(_show(e.head(20)))
    sel = select(table, trades, cells=cl)
    sel.update({"spec": "YT8_SPEC.md", "phase": "is", "first_day": str(trades.day.min().date()),
                "last_day": str(trades.day.max().date()), "n_days": int(len(days)), "n_trades_file": int(len(trades)),
                "grid_file": gp.name, "sha256_grid": _sha(gp), "sha256_trades": _sha(tp), "sha256_setups": _sha(sp)})
    p = out / "G11_selected.json"
    new = json.dumps(sel, indent=1)
    if p.exists() and p.read_text() != new:
        print(f"\nNOTE: {p.name} existed with different content and is rewritten")
    p.write_text(new)
    print("\npicks (rank = place in the eligible ranking by t; picks 1-5 by t with the overlap rule on (day, side); "
          "pick 6 = the largest total R if not already a pick)")
    for r in sel["picks"]:
        print(_pick_line(r) + f"   [{r['how']}]")
    sk = sel["skipped_for_overlap_first_200"]
    print(f"  passed over for overlap before the last pick by t: {sel['n_skipped_for_overlap']}"
          + (f"   (first: rank {sk[0]['rank']} {sk[0]['name']} shares {sk[0]['share']:.3f} with {sk[0]['overlaps']})" if sk else ""))
    r = sel["largest_total_R"]
    if r is not None:
        print(f"\nlargest total R among eligible: {r['name']}  n {r['n']}  days {r['days']}  net {r['net']:+.0f}"
              f"  totR {r['totR']:+.1f}  R {r['R']:+.4f}  t {r['t']:+.2f}  rank {r['rank']}"
              + (f"   (it is pick {r['same_as_pick']}: there is no pick 6)" if r["same_as_pick"] else "   (pick 6)")
              + f"   day overlap with the picks by t: {r['day_overlap_with_picks']}")
    rc = reality_check(trades, table, days, cells=cl)
    (out / "is" / "G11_reality.json").write_text(json.dumps({k: v for k, v in rc.items() if k != "seconds"}, indent=1))
    _print_rc(rc)
    lt = level_table({"is": table}, min_names=e.index)
    lt.to_csv(out / "is" / "G11_levels.csv", index=False)
    print(f"\neach choice on its own: average of mean R over the {len(e)} eligible combinations using the level")
    print(lt.to_string(index=False, formatters={"R_is": "{:+.4f}".format, "trades_is": "{:.0f}".format}))
    print(f"\ntotal {time.time() - t00:.0f}s")
    return table, sel, rc


def _span_years(first, last):
    return ((pd.Timestamp(last) - pd.Timestamp(first)).days + 1) / 365.25


def _stats(tr, years=OOS_YEARS, span_years=None, boot=True):
    """n, net, total R, mean R, win, max drawdown, net / max drawdown, bootstrap p and net by calendar year of a set
    of trades in time order (columns day, R, pnl)."""
    n = len(tr)
    out = {"n": int(n)}
    if span_years:
        out["trades_per_year"] = n / span_years
    if n == 0:
        return out
    yr = pd.DatetimeIndex(tr.day).year
    by = {int(y): round(float(tr.pnl[yr == y].sum()), 2) for y in years}
    dd = core.max_dd(tr.pnl.to_numpy())
    net = float(tr.pnl.sum())
    out.update(net=round(net, 2), totR=float(tr.R.sum()), R=float(tr.R.mean()), win=float((tr.pnl > 0).mean() * 100),
               dd=round(dd, 2), net_dd=(net / -dd if dd < 0 else None), by_year=by,
               years_positive=int(sum(v > 0 for v in by.values())))
    if boot:
        out["p"] = core.boot_p(tr.R.to_numpy(), n=10000, seed=1)
    return out


def orb_trades(ctx, start=None, end=None):
    """ORB v1.4 from cal_orb through the harness, as registered; trades whose cash day is in [start, end]."""
    import cal_orb
    df = core.trades_df(core.run_orders(ctx, cal_orb.orders(ctx), skip_roll=False))
    df["day"] = pd.DatetimeIndex(df.entry_time).tz_localize(None).normalize()
    if start is not None:
        df = df[df.day >= pd.Timestamp(start)]
    if end is not None:
        df = df[df.day <= pd.Timestamp(end)]
    return df.sort_values("entry_time").reset_index(drop=True)


def _daily_pnl(tr):
    return tr.groupby("day").pnl.sum() if len(tr) else pd.Series(dtype=float)


def against_orb(tr, orb):
    """Description only: a pick's days against ORB's, and the two together day by day."""
    side = tr[tr.which == 1].set_index("day").side if len(tr) else pd.Series(dtype=float)
    oside = orb.set_index("day").side.map({"L": 1, "S": -1})
    shared = side.index.intersection(oside.index)
    on = tr[tr.day.isin(oside.index)]
    off = tr[~tr.day.isin(oside.index)]
    both = _daily_pnl(tr).add(_daily_pnl(orb), fill_value=0.0).sort_index()
    dd = core.max_dd(both.to_numpy())
    net = float(both.sum())
    return {"pick_days": int(len(side)), "orb_days": int(len(oside)), "shared_days": int(len(shared)),
            "same_side_share": float((side[shared] == oside[shared]).mean()) if len(shared) else None,
            "n_on_orb_days": int(len(on)), "net_on_orb_days": round(float(on.pnl.sum()), 2),
            "R_on_orb_days": float(on.R.mean()) if len(on) else None,
            "n_off_orb_days": int(len(off)), "net_off_orb_days": round(float(off.pnl.sum()), 2),
            "R_off_orb_days": float(off.R.mean()) if len(off) else None,
            "together_net": round(net, 2), "together_dd": round(dd, 2),
            "together_net_dd": (net / -dd if dd < 0 else None),
            "daily_pnl_corr_on_shared_days": (float(np.corrcoef(_daily_pnl(tr)[shared], _daily_pnl(orb)[shared])[0, 1])
                                              if len(shared) > 2 else None)}


def pick_verdict(trades, combo_name, start, span_years, orb_stats, years=OOS_YEARS):
    """The registered out-of-sample test of one frozen pick, on its trades from `start` on."""
    c = parse(combo_name)
    out = _stats(pick(trades, c, start=start), years, span_years)
    nbs = []
    for nb in (1, 2):
        cn = neighbour(c, nb)
        s = _stats(pick(trades, cn, start=start), years, span_years, boot=False)
        nbs.append({"nb": nb, "name": name(cn), "n": s["n"], "net": s.get("net"), "R": s.get("R")})
    out["neighbours"] = nbs
    n = out["n"]
    out["p_pass"], out["p_candidate"] = P_PASS, P_CAND
    if n == 0:
        out["verdict"], out["beats_orb"] = "fails", False
        out["checks"] = {"n": False}
        return out
    ch = {"n": n >= 100, "R": out["R"] >= 0.05, "years": out["years_positive"] >= 3,
          "neighbours": all(x["R"] is not None and x["R"] > 0 for x in nbs)}
    out["checks"] = {k: bool(v) for k, v in ch.items()}
    p = out["p"]
    if all(ch.values()) and p < P_PASS:
        out["verdict"] = "passes"
    elif all(ch.values()) and p < P_CAND:
        out["verdict"] = "candidate"
    else:
        out["verdict"] = "fails"
    b = {"candidate_or_pass": out["verdict"] in ("passes", "candidate"),
         "total_R_above_orb": bool(orb_stats.get("totR") is not None and out["totR"] > orb_stats["totR"]),
         "net_dd_above_orb": bool(out["net_dd"] is not None and orb_stats.get("net_dd") is not None
                                  and out["net_dd"] > orb_stats["net_dd"]),
         "trades_per_year": bool(out["trades_per_year"] >= MIN_TRADES_YEAR)}
    out["beats_orb_checks"] = b
    out["beats_orb"] = bool(all(b.values()))
    return out


def _fmt(x, f="{:+.4f}"):
    return "nan" if x is None or x != x else f.format(x)


def phase_full(out=core.OUT, trades_path=None, setups_path=None, oos_start=OOS_START, sel_path=None, dry=False,
               bars_phase="full", frozen_dir=None, min_full=MIN_TRADES_FULL):
    """Scores the frozen picks out of sample. Reads G11_selected.json and the frozen in-sample grid; selects nothing."""
    from scipy.stats import spearmanr
    import run
    t00 = time.time()
    sel = json.loads(pathlib.Path(sel_path or SEL_PATH).read_text())               # frozen; never rewritten here
    tp = pathlib.Path(trades_path or gs.path("full"))
    sp = pathlib.Path(setups_path or gs.path("full", "setups"))
    if not tp.exists():
        raise SystemExit(f"{tp} does not exist: run  python3 tools/yt1/g11_sim.py --phase full  first")
    trades, setups = pd.read_parquet(tp), pd.read_parquet(sp)
    oos_start = pd.Timestamp(oos_start)
    is_end = oos_start - pd.Timedelta(days=1)
    last = setups.day.max()
    if last < oos_start:
        raise SystemExit("no out-of-sample bars in this trade file: the full phase cannot run here")
    years = OOS_YEARS if not dry else tuple(range(oos_start.year, last.year + 1))
    span_years = _span_years(oos_start, last)
    print(f"G11 grid   phase full{'  (DRY RUN on a made-up split: numbers mean nothing)' if dry else ''}"
          f"   trades {len(trades)}   {setups.day.min().date()} -> {last.date()}   out of sample from {oos_start.date()}"
          f" ({span_years:.2f} years)")
    d = out / "full"
    d.mkdir(parents=True, exist_ok=True)
    t_is, t_oos, t_all = evaluate(trades, end=is_end), evaluate(trades, start=oos_start), evaluate(trades)
    p1, p2 = write_grid(t_oos, d / "G11_grid_oos"), write_grid(t_all, d / "G11_grid_full")
    print(f"wrote {p1.name}, {p2.name}")
    frozen = read_grid(pathlib.Path(frozen_dir or (core.OUT / "is")) / "G11_grid")
    assert list(frozen.index) == list(t_is.index)
    same = (frozen.n.to_numpy() == t_is.n.to_numpy()) & (np.abs(frozen.net.to_numpy() - t_is.net.to_numpy()) < 0.005)
    same = pd.Series(same, index=t_is.index)
    print(f"in-sample grid rebuilt from the full-span trades: {int(same.sum())} of {len(t_is)} combinations have the "
          f"frozen n and net $" + ("" if same.all() else "   <-- NOT ALL: the frozen grid is not reproduced"))
    if dry:                                          # the comparison itself, on a period the frozen grid does cover
        s2 = (frozen.n.to_numpy() == t_all.n.to_numpy()) & (np.abs(frozen.net.to_numpy() - t_all.net.to_numpy()) < 0.005)
        print(f"(dry run: the split is made up, so the line above cannot be complete; the frozen grid against the whole "
              f"in-sample file: {int(s2.sum())} of {len(t_all)})")
    res = {"oos_start": str(oos_start.date()), "last_day": str(last.date()), "span_years": span_years, "picks": [],
           "is_grid_reproduced": int(same.sum()), "n_grid": int(len(t_is)), "dry_run": bool(dry)}

    # ---- ORB v1.4 on the same dates, through the harness
    ctx = core.Ctx(run.bars(bars_phase))
    orb = orb_trades(ctx, start=oos_start, end=last)
    so = _stats(orb, years, span_years)
    res["orb_v14"] = so
    print(f"\nORB v1.4 (cal_orb through the harness) {oos_start.date()} -> {last.date()}: n {so['n']}"
          f"  per year {so['trades_per_year']:.1f}  net {so.get('net', 0):+.0f}  total R {_fmt(so.get('totR'), '{:+.1f}')}"
          f"  mean R {_fmt(so.get('R'))}  win {_fmt(so.get('win'), '{:.1f}')}  max dd {_fmt(so.get('dd'), '{:.0f}')}"
          f"  net / dd {_fmt(so.get('net_dd'), '{:.2f}')}  p {_fmt(so.get('p'), '{:.5f}')}  years {so.get('by_year')}")

    import s_G11
    print(f"\nfrozen picks, out of sample (passes: p < {P_PASS:.6f}; candidate: p < {P_CAND:.4f}; beats ORB v1.4: candidate"
          f" or pass, total R above ORB's, net / max drawdown above ORB's, at least {MIN_TRADES_YEAR} trades a year)")
    for r in sel["picks"]:
        v = pick_verdict(trades, r["name"], oos_start, span_years, so, years)
        tr = pick(trades, parse(r["name"]), start=oos_start)
        hd = core.trades_df(s_G11.trades(ctx, c=r["name"], nb=0))
        hd = hd[pd.DatetimeIndex(hd.entry_time).tz_localize(None).normalize() >= oos_start]
        v["harness_agrees"] = bool(len(hd) == len(tr) and abs(hd.pnl.sum() - tr.pnl.sum()) < 0.005)
        v["vs_orb"] = against_orb(tr, orb)
        v.update(pick=r["pick"], how=r["how"], name=r["name"], is_n=r["n"], is_R=r["R"], is_t=r["t"],
                 is_totR=r["totR"], is_rank=r.get("rank"), is_reproduced=bool(same.get(r["name"], False)))
        res["picks"].append(v)
        print(f"  pick {r['pick']} ({r['how']})  {r['name']}")
        if not v["n"]:
            print("      no out-of-sample trades -> fails")
            continue
        print(f"      n {v['n']}  per year {v['trades_per_year']:.1f}  net {v['net']:+.0f}  total R {v['totR']:+.1f}"
              f"  mean R {v['R']:+.4f}  win {v['win']:.1f}  max dd {v['dd']:.0f}  net / dd {_fmt(v['net_dd'], '{:.2f}')}"
              f"  p {v['p']:.5f}  years {v['by_year']}")
        print("      neighbours: " + "   ".join(f"{x['name']}: n {x['n']}  net {_fmt(x['net'], '{:+.0f}')}  R {_fmt(x['R'])}"
                                                for x in v["neighbours"]))
        print(f"      -> {v['verdict']}  {v['checks']}   beats ORB v1.4: {v['beats_orb']}  {v.get('beats_orb_checks')}"
              f"   [ORB: total R {_fmt(so.get('totR'), '{:+.1f}')}  net / dd {_fmt(so.get('net_dd'), '{:.2f}')}  net {so.get('net', 0):+.0f}]")
        print(f"      in sample: n {r['n']}  R {r['R']:+.4f}  t {r['t']:+.2f}  total R {r['totR']:+.1f}"
              f"   frozen row reproduced: {v['is_reproduced']}   harness agrees out of sample: {v['harness_agrees']}")
        o = v["vs_orb"]
        print(f"      against ORB: days {o['pick_days']} / ORB {o['orb_days']} / shared {o['shared_days']}"
              f"  same side on shared days {_fmt(o['same_side_share'], '{:.3f}')}"
              f"  on ORB days n {o['n_on_orb_days']} net {o['net_on_orb_days']:+.0f} R {_fmt(o['R_on_orb_days'])}"
              f"  off ORB days n {o['n_off_orb_days']} net {o['net_off_orb_days']:+.0f} R {_fmt(o['R_off_orb_days'])}"
              f"  | ORB + pick: net {o['together_net']:+.0f}  max dd {o['together_dd']:.0f}  net / dd {_fmt(o['together_net_dd'], '{:.2f}')}")
    r = sel.get("largest_total_R")
    if r is not None and r.get("same_as_pick"):
        print(f"  (the largest in-sample total R is pick {r['same_as_pick']}: there is no separate pick 6)")

    # ---- does in-sample rank predict anything? (description, not a test)
    e = eligible(frozen)
    j = pd.DataFrame({"R_is": e.mR, "t_is": e.t, "R_oos": t_oos.mR.reindex(e.index), "n_oos": t_oos.n.reindex(e.index)})
    jj = j[j.n_oos > 0]
    rho, rho_p = spearmanr(jj.R_is, jj.R_oos) if len(jj) > 2 else (np.nan, np.nan)
    top = j.head(int(math.ceil(len(e) * 0.10)))
    top = top[top.n_oos > 0]
    anyt = t_oos[t_oos.n > 0]
    res["rank"] = {"n_eligible": int(len(e)), "n_with_oos_trades": int(len(jj)), "spearman_R_is_vs_R_oos": float(rho),
                   "spearman_p": float(rho_p), "top10pct_n": int(len(top)),
                   "top10pct_R_oos": float(top.R_oos.mean()) if len(top) else None,
                   "eligible_R_oos": float(jj.R_oos.mean()) if len(jj) else None,
                   "eligible_share_positive": float((jj.R_oos > 0).mean()) if len(jj) else None,
                   "whole_grid_R_oos": float(anyt.mR.mean()) if len(anyt) else None, "whole_grid_combos": int(len(anyt))}
    k = res["rank"]
    print(f"\nSpearman of mean R in sample against out of sample over the {k['n_with_oos_trades']} in-sample-eligible "
          f"combinations with an out-of-sample trade: {k['spearman_R_is_vs_R_oos']:+.3f}")
    print(f"  out-of-sample mean R, averaged over combinations: in-sample top 10 % by t ({k['top10pct_n']}) "
          f"{_fmt(k['top10pct_R_oos'])}   all eligible {_fmt(k['eligible_R_oos'])}   every combination with a trade "
          f"({k['whole_grid_combos']}) {_fmt(k['whole_grid_R_oos'])}")

    # ---- each choice on its own, both periods, over the in-sample-eligible combinations
    lt = level_table({"is": frozen, "oos": t_oos}, min_names=e.index)
    lt.to_csv(d / "G11_levels.csv", index=False)
    print("\neach choice on its own: average of mean R over the in-sample-eligible combinations using the level")
    print(lt.to_string(index=False, formatters={"R_is": "{:+.4f}".format, "R_oos": "{:+.4f}".format,
                                                "trades_is": "{:.0f}".format, "trades_oos": "{:.0f}".format}))

    # ---- hindsight: the top of the full-span grid (the top of 25,920, labelled as such)
    ea = eligible(t_all, min_full)
    by_r = ea.sort_values("totR", ascending=False, kind="mergesort").head(10)
    print(f"\nHINDSIGHT (full span, the top of {N_GRID:,}; {len(ea)} with >= {min_full} trades): top 10 by total R")
    print(_show(by_r))
    print("HINDSIGHT: top 10 by t")
    print(_show(ea.head(10)))
    rc = reality_check(trades, t_all, period_days(setups), min_n=min_full)
    (d / "G11_reality_full.json").write_text(json.dumps({k: v for k, v in rc.items() if k != "seconds"}, indent=1))
    if rc.get("p") is not None:
        _print_rc(rc, "full-span reality check")
    res["hindsight"] = {"min_trades": int(min_full), "by_total_R": [_record(r) for _, r in by_r.iterrows()],
                        "by_t": [_record(r) for _, r in ea.head(10).iterrows()],
                        "reality_check": {k: v for k, v in rc.items() if k != "seconds"}}
    (d / "G11_oos.json").write_text(json.dumps(res, indent=1, default=str))
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
        split = pd.Timestamp(a.dry_split)
        phase_full(out=o, trades_path=gs.path("is"), setups_path=gs.path("is", "setups"), oos_start=split, dry=True,
                   bars_phase="is", min_full=MIN_TRADES_FULL)
    else:
        phase_full()


if __name__ == "__main__":
    main()
