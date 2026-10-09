#!/usr/bin/env python3
"""G8 grid - the 5,184 combinations of YT5_SPEC.md evaluated on the signal file of g8_signals.py.

    combos() / name(c) / parse(s)       the grid and its names, e.g. T5.Wam.Bany.Enone.Obelow.Rsess.Hh1.Snone
    pick(sig, combo)                    the rows a combination trades: every confluence true, tradable, first per day
    evaluate(sig, start, end)           one row per combination (n, net $, mean R, sd, t, win %, R at 1.5R / 3R, years)
    select(table, sig)                  the registered selection (>= 150 trades, rank by t, overlap rule, 5 picks)
    reality_check(sig, table)           White's reality check on the daily R series of the eligible combinations

    python3 tools/yt1/g8_grid.py --phase is     in-sample grid, selection (G8_selected.json) and reality check
    python3 tools/yt1/g8_grid.py --phase full   out-of-sample scoring of the FROZEN picks (never re-selects)
"""
import argparse, hashlib, itertools, json, math, pathlib, sys
import numpy as np
import pandas as pd
sys.path.insert(0, str(pathlib.Path(__file__).parent))
import core
import g8_signals

ORDER = ("T", "W", "B", "E", "O", "R", "H", "S")
LEVELS = {"T": (1, 5, 15), "W": ("am", "open", "sb", "pm"), "B": ("none", "any", "cont", "fail"),
          "E": ("none", "disc", "prem"), "O": ("none", "below"), "R": ("none", "pd", "sess"),
          "H": ("none", "h1", "h4"), "S": ("none", "smt")}
COLUMN = {("W", "am"): "w_am", ("W", "open"): "w_open", ("W", "sb"): "w_sb", ("W", "pm"): "w_pm",
          ("E", "disc"): "e_disc", ("E", "prem"): "e_prem", ("O", "below"): "o_below", ("R", "pd"): "r_pd",
          ("R", "sess"): "r_sess", ("H", "h1"): "h_h1", ("H", "h4"): "h_h4", ("S", "smt"): "s_smt"}
MIN_TRADES = 150                    # eligibility
MAX_PICKS = 5
OOS_START = pd.Timestamp("2023-01-01")
OOS_YEARS = (2023, 2024, 2025, 2026)
N_RULES = 95                        # 90 rules tried before this plus these 5
SEL_PATH = core.OUT / "G8_selected.json"


# ------------------------------------------------------------------ the grid
def combos():
    """The 5,184 combinations as dicts with keys T, W, B, E, O, R, H, S, in the order of the spec's table."""
    return [dict(zip(ORDER, v)) for v in itertools.product(*(LEVELS[k] for k in ORDER))]


def name(c):
    return ".".join(f"{k}{c[k]}" for k in ORDER)


def parse(s):
    parts = s.split(".")
    assert len(parts) == len(ORDER) and all(p[0] == k for p, k in zip(parts, ORDER)), f"not a combination: {s}"
    c = {k: (int(p[1:]) if k == "T" else p[1:]) for p, k in zip(parts, ORDER)}
    assert all(c[k] in LEVELS[k] for k in ORDER), f"unknown level in {s}"
    return c


def _cond(sig, key, level):
    """Boolean array for one confluence level, or None when the level places no condition."""
    if key == "T":
        return sig.tf.to_numpy() == level
    if key == "B":
        if level == "none":
            return None
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


def pick(sig, combo, start=None, end=None):
    """The rows of `sig` traded by one combination: signals of its timeframe inside its window that meet every
    confluence (and are tradable, when `sig` carries outcomes), the first of each cash day."""
    s = _period(sig, start, end)
    m = np.ones(len(s), bool)
    for k in ORDER:
        c = _cond(s, k, combo[k])
        if c is not None:
            m &= c
    s = s[m]
    return s[~s.date.duplicated(keep="first")]


def _scan(s):
    """Yield (combo, positions in s) for every combination, in combos() order. s = _period(...) output."""
    day = s.date.to_numpy().astype("datetime64[D]").astype(np.int64)
    tf = s.tf.to_numpy()
    rest = [k for k in ORDER if k not in ("T", "W")]
    for t in LEVELS["T"]:
        mt = tf == t
        for w in LEVELS["W"]:
            idx = np.flatnonzero(mt & s[COLUMN[("W", w)]].to_numpy(bool))
            sub = s.iloc[idx]
            d = day[idx]
            cond = {(k, lv): _cond(sub, k, lv) for k in rest for lv in LEVELS[k]}
            for v in itertools.product(*(LEVELS[k] for k in rest)):
                m = None
                for k, lv in zip(rest, v):
                    c = cond[(k, lv)]
                    if c is not None:
                        m = c if m is None else m & c
                loc = np.arange(len(idx)) if m is None else np.flatnonzero(m)
                if len(loc):
                    dd = d[loc]
                    loc = loc[np.r_[True, dd[1:] != dd[:-1]]]          # the first of each day
                yield dict(zip(ORDER, (t, w) + v)), idx[loc]


def _years(s):
    return list(range(int(s.date.dt.year.min()), int(s.date.dt.year.max()) + 1)) if len(s) else []


def evaluate(sig, start=None, end=None):
    """One row per combination on the cash dates start..end: n, net (2R, $), mR (mean R at 2R), sd, t = mean / (sd /
    sqrt(n)), win (% of trades with pnl > 0), mR15 / mR30 (mean R at 1.5R / 3R), net15 / net30, and y<year> = net $
    of that calendar year. Indexed by name, in combos() order. (The columns T W B E O R H S are the levels.)"""
    s = _period(sig, start, end)
    R, pnl = s.R20.to_numpy(), s.pnl20.to_numpy()
    R15, R30, p15, p30 = s.R15.to_numpy(), s.R30.to_numpy(), s.pnl15.to_numpy(), s.pnl30.to_numpy()
    yrs = _years(s)
    y = s.date.dt.year.to_numpy() - (yrs[0] if yrs else 0)
    rows = []
    for c, pos in _scan(s):
        n = len(pos)
        r = R[pos]
        mean = r.mean() if n else np.nan
        sd = r.std(ddof=1) if n > 1 else np.nan
        t = mean / (sd / math.sqrt(n)) if n > 1 and sd > 0 else np.nan
        by = np.bincount(y[pos], weights=pnl[pos], minlength=len(yrs)) if n else np.zeros(len(yrs))
        rows.append([name(c)] + [c[k] for k in ORDER] + [
            n, pnl[pos].sum(), mean, sd, t, (pnl[pos] > 0).mean() * 100 if n else np.nan,
            R15[pos].mean() if n else np.nan, R30[pos].mean() if n else np.nan, p15[pos].sum(), p30[pos].sum()]
            + list(by))
    cols = ["name"] + list(ORDER) + ["n", "net", "mR", "sd", "t", "win", "mR15", "mR30", "net15", "net30"] + [f"y{k}" for k in yrs]
    return pd.DataFrame(rows, columns=cols).set_index("name")


def eligible(table, min_n=MIN_TRADES):
    """Eligible combinations in ranking order: t descending, ties by name."""
    e = table[table.n >= min_n].copy()
    e["_name"] = e.index
    e = e.sort_values(["t", "_name"], ascending=[False, True], kind="mergesort", na_position="last").drop(columns="_name")
    e["rank"] = np.arange(1, len(e) + 1)
    return e


def _keys(rows):
    """Trade identity for the overlap rule: same day, same entry bar, same side (the bar fixes the day)."""
    return set(zip(rows.i.to_numpy().tolist(), rows.side.to_numpy().tolist()))


def _record(row):
    d = {"name": row.name, "combo": {k: (int(row[k]) if k == "T" else str(row[k])) for k in ORDER},
         "n": int(row.n), "net": round(float(row.net), 2), "R": float(row.mR), "sd": float(row.sd), "t": float(row.t),
         "win": float(row.win), "R15": float(row.mR15), "R30": float(row.mR30), "net15": round(float(row.net15), 2),
         "net30": round(float(row.net30), 2),
         "by_year": {k[1:]: round(float(row[k]), 2) for k in row.index if k.startswith("y") and k[1:].isdigit()}}
    if "rank" in row.index:
        d["rank"] = int(row["rank"])
    return d


def select(table, sig, start=None, end=None, min_n=MIN_TRADES, max_picks=MAX_PICKS):
    """The registered selection. Eligible = at least min_n trades; ranked by t; going down the ranking a combination
    is taken unless more than half of its trades (share measured on the smaller of the two trade sets) are trades of
    one already taken; a pick must have positive mean R; at most max_picks. Also the eligible combination with the
    largest net dollars. `sig`, start, end must be the ones `table` was evaluated on."""
    e = eligible(table, min_n)
    picks, taken, skipped = [], [], []
    for nm, row in e.iterrows():
        if len(picks) >= max_picks:
            break
        if not (row.mR > 0 and row.t > 0):
            break                                    # the ranking is by t: nothing below has a positive mean R
        k = _keys(pick(sig, parse(nm), start, end))
        assert len(k) == row.n, "the table and the signal file disagree"
        clash = None
        for pn, pk in taken:
            share = len(k & pk) / min(len(k), len(pk))
            if share > 0.5:
                clash = (pn, share)
                break
        if clash:
            skipped.append({"name": nm, "rank": int(row["rank"]), "overlaps": clash[0], "share": round(clash[1], 4)})
            continue
        taken.append((nm, k))
        rec = _record(row)
        rec["pick"] = len(picks) + 1
        picks.append(rec)
    big = e.sort_values("net", ascending=False, kind="mergesort").iloc[0] if len(e) else None
    return {"min_trades": min_n, "n_grid": int(len(table)), "n_eligible": int(len(e)),
            "n_eligible_positive": int((e.mR > 0).sum()), "picks": picks, "skipped_for_overlap": skipped,
            "largest_net": _record(big) if big is not None else None}


# ------------------------------------------------------------------ White's reality check
def _daily(sig, names, start=None, end=None):
    """(days, X): X[d, j] = the 2R R of combination names[j] on day d, 0 on a day without a trade. Days = the cash
    dates of the period on which at least one tradable signal exists (the days any combination could trade)."""
    s = _period(sig, start, end)
    days = np.unique(s.date.to_numpy().astype("datetime64[D]"))
    drow = np.searchsorted(days, s.date.to_numpy().astype("datetime64[D]"))
    R = s.R20.to_numpy()
    col = {n: j for j, n in enumerate(names)}
    X = np.zeros((len(days), len(names)))
    for c, pos in _scan(s):
        j = col.get(name(c))
        if j is not None:
            X[drow[pos], j] = R[pos]
    return days, X


def _t_days(mean, ss, D):
    """t of a daily series of D days from its mean and its sum of squares: sqrt(D) * mean / sd, sd with D - 1."""
    var = (ss - D * mean ** 2) / (D - 1)
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(var > 0, math.sqrt(D) * mean / np.sqrt(np.where(var > 0, var, 1.0)), np.nan)


def reality_check(sig, table, n_boot=2000, seed=1, start=None, end=None, min_n=MIN_TRADES, chunk=200):
    """White's reality check as registered. For each eligible combination j the daily series x_j (2R R per cash day,
    0 on a day without a trade) over the D days of the period. The statistic, for the observed and for every
    resampled series alike, is the day-level t  t_j = sqrt(D) * mean(x_j) / sd(x_j)  (sd with D - 1), and the grid's
    largest t_j. Observed: on x_j as it is. Resampled: each x_j centred on its own mean over the D days, D days
    drawn with replacement (the same days for every combination), t_j recomputed with the resample's own sd.
    p = share of resamples whose largest t is at least the observed largest t."""
    e = eligible(table, min_n)
    names = list(e.index)
    days, X = _daily(sig, names, start, end)
    D = len(days)
    if not names or D < 2:
        return {"n_eligible": len(names), "n_days": D, "p": None}
    mean = X.mean(axis=0)
    t_obs = _t_days(mean, (X ** 2).sum(axis=0), D)
    j = int(np.nanargmax(t_obs))
    Xc = X - mean
    Xc2 = Xc ** 2
    rng = np.random.default_rng(seed)
    mx = np.empty(n_boot)
    for b0 in range(0, n_boot, chunk):
        nb = min(chunk, n_boot - b0)
        W = np.zeros((nb, D))
        for b in range(nb):
            W[b] = np.bincount(rng.integers(0, D, size=D), minlength=D)      # how often each day is drawn
        tb = _t_days((W @ Xc) / D, W @ Xc2, D)
        mx[b0:b0 + nb] = np.nanmax(tb, axis=1)
    q = {f"q{k}": float(np.quantile(mx, k / 100)) for k in (5, 25, 50, 75, 90, 95, 99)}
    return {"n_eligible": len(names), "n_days": int(D), "n_boot": int(n_boot), "seed": int(seed),
            "statistic": "largest day-level t over the eligible combinations: sqrt(D) * mean / sd of the daily 2R R "
                         "series (0 on days without a trade)",
            "t_obs_max": float(t_obs[j]), "t_obs_max_name": names[j],
            "t_trade_max": float(e.t.iloc[0]), "t_trade_max_name": names[0],
            "boot_max_t": dict(mean=float(mx.mean()), min=float(mx.min()), max=float(mx.max()), **q),
            "p": float((mx >= t_obs[j]).mean())}


# ------------------------------------------------------------------ tables
def level_table(tables, min_names=None):
    """Each confluence on its own: for every level, the average of mean R over the combinations using it.
    tables = {label: table}; min_names = the combinations averaged over (default: all with at least one trade)."""
    out = []
    for k in ORDER:
        for lv in LEVELS[k]:
            row = {"confluence": k, "level": str(lv)}
            for lab, tb in tables.items():
                t = tb if min_names is None else tb.loc[tb.index.intersection(min_names)]
                t = t[(t[k].astype(str) == str(lv)) & (t.n > 0)]
                row[f"combos_{lab}"] = int(len(t))
                row[f"R_{lab}"] = float(t.mR.mean()) if len(t) else np.nan
                row[f"trades_{lab}"] = float(t.n.mean()) if len(t) else np.nan
            out.append(row)
    return pd.DataFrame(out)


def _show(tb, cols=("n", "net", "mR", "t", "win", "mR15", "mR30")):
    f = {"n": "{:.0f}".format, "net": "{:+.0f}".format, "mR": "{:+.4f}".format, "t": "{:+.2f}".format,
         "win": "{:.1f}".format, "mR15": "{:+.4f}".format, "mR30": "{:+.4f}".format, "sd": "{:.3f}".format}
    return tb[list(cols)].to_string(formatters={k: v for k, v in f.items() if k in cols})


def read_grid(p):
    """A grid CSV written by evaluate(): the level 'none' stays a string, empty cells are NaN."""
    return pd.read_csv(p, index_col="name", keep_default_na=False, na_values=[""])


def _sha(p):
    return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()


def _selfcheck(sig, start=None, end=None, n=120, seed=0):
    """pick() and the vectorised scan must give the same rows: checked on n random combinations."""
    s = _period(sig, start, end)
    want = {name(c): s.index[pos].to_numpy() for c, pos in _scan(s)}
    assert len(want) == 5184
    rng = np.random.default_rng(seed)
    for nm in rng.choice(sorted(want), size=n, replace=False):
        assert np.array_equal(pick(sig, parse(nm), start, end).index.to_numpy(), want[nm]), nm
    return n


# ------------------------------------------------------------------ phases
def phase_is(out=core.OUT):
    sig = pd.read_parquet(g8_signals.path("is"))
    assert sig.date.max() < OOS_START, "the in-sample signal file reaches into the out-of-sample window"
    print(f"G8 grid   phase is   signals {len(sig)}   {sig.date.min().date()} -> {sig.date.max().date()}")
    print(sig.groupby("tf").agg(signals=("i", "size"), tradable=("tradable", "sum")).to_string())
    print(f"pick() agrees with the vectorised scan on {_selfcheck(sig)} random combinations")
    table = evaluate(sig)
    assert len(table) == 5184
    (out / "is").mkdir(parents=True, exist_ok=True)
    table.to_csv(out / "is" / "G8_grid.csv")
    e = eligible(table)
    print(f"\ncombinations {len(table)}   with a trade {(table.n > 0).sum()}   eligible (>= {MIN_TRADES} trades) {len(e)}"
          f"   eligible with mean R > 0: {(e.mR > 0).sum()}")
    print("\ntop 20 eligible by t")
    print(_show(e.head(20)))
    sel = select(table, sig)
    sel.update({"spec": "YT5_SPEC.md", "phase": "is", "first_day": str(sig.date.min().date()),
                "last_day": str(sig.date.max().date()), "n_signals": int(len(sig)),
                "sha256_grid_csv": _sha(out / "is" / "G8_grid.csv"),
                "sha256_signals": _sha(g8_signals.path("is"))})
    p = out / "G8_selected.json"
    new = json.dumps(sel, indent=1)
    if p.exists() and p.read_text() != new:
        print(f"\nNOTE: {p.name} existed with different content and is rewritten")
    p.write_text(new)
    print("\npicks (rank = place in the eligible ranking by t)")
    for r in sel["picks"]:
        print(f"  pick {r['pick']}  rank {r['rank']:>4}  {r['name']:<46} n {r['n']:>4}  net {r['net']:>+8.0f}  R {r['R']:+.4f}"
              f"  t {r['t']:+.2f}  win {r['win']:.1f}  R15 {r['R15']:+.4f}  R30 {r['R30']:+.4f}")
    print(f"  passed over for overlap before the last pick: {len(sel['skipped_for_overlap'])}")
    r = sel["largest_net"]
    print(f"largest net $ among eligible: {r['name']}  n {r['n']}  net {r['net']:+.0f}  R {r['R']:+.4f}  t {r['t']:+.2f}"
          f"  rank {r['rank']}")
    rc = reality_check(sig, table)
    (out / "is" / "G8_reality.json").write_text(json.dumps(rc, indent=1))
    b = rc["boot_max_t"]
    print(f"\nreality check: {rc['n_eligible']} combinations, {rc['n_days']} days, {rc['n_boot']} resamples, seed {rc['seed']}")
    print(f"  observed largest t (day-level) {rc['t_obs_max']:+.3f}  ({rc['t_obs_max_name']});"
          f"  trade-level largest t {rc['t_trade_max']:+.3f}  ({rc['t_trade_max_name']})")
    print(f"  resampled largest t: median {b['q50']:.3f}  90% {b['q90']:.3f}  95% {b['q95']:.3f}  99% {b['q99']:.3f}"
          f"  max {b['max']:.3f}     p = {rc['p']:.4f}")
    lt = level_table({"is": table}, min_names=e.index)
    lt.to_csv(out / "is" / "G8_levels.csv", index=False)
    print(f"\neach confluence on its own: average of mean R over the {len(e)} eligible combinations using the level")
    print(lt.to_string(index=False, formatters={"R_is": "{:+.4f}".format, "trades_is": "{:.0f}".format}))
    return table, sel, rc


def pick_verdict(sig, combo, start, years=OOS_YEARS, n_rules=N_RULES):
    """The registered out-of-sample test of one frozen pick, on its trades from `start` on."""
    tr = pick(sig, combo, start=start)
    n = len(tr)
    df = pd.DataFrame({"entry_time": tr.time, "side": np.where(tr.side > 0, "L", "S"), "pnl": tr.pnl20, "R": tr.R20,
                       "risk_pts": tr.risk_pts, "reason": tr.reason.astype(str)})
    s = core.summary(df)                                             # the house summary: bootstrap p, by year
    out = {"n": int(n)}
    if n == 0:
        out["verdict"] = "not enough data"
        return out
    yr = tr.date.dt.year
    by = {int(y): round(float(tr.pnl20[yr == y].sum()), 2) for y in years}
    p = core.boot_p(tr.R20.to_numpy())                               # 10,000 resamples, seed 1
    assert p == s["p"]
    out.update(net=round(float(tr.pnl20.sum()), 2), R=float(tr.R20.mean()), win=float((tr.pnl20 > 0).mean() * 100),
               R15=float(tr.R15.mean()), R30=float(tr.R30.mean()), p=p, by_year=by,
               years_positive=int(sum(v > 0 for v in by.values())))
    ch = {"n": n >= 100, "R": out["R"] >= 0.05, "years": out["years_positive"] >= 3,
          "neighbours": out["R15"] > 0 and out["R30"] > 0}
    out["checks"] = {k: bool(v) for k, v in ch.items()}
    out["p_pass"], out["p_candidate"] = 0.05 / n_rules, 0.05 / MAX_PICKS
    if n < 100:
        out["verdict"] = "not enough data"
    elif all(ch.values()) and p < out["p_pass"]:
        out["verdict"] = "passes"
    elif all(ch.values()) and p < out["p_candidate"]:
        out["verdict"] = "candidate"
    else:
        out["verdict"] = "fails"
    return out


def phase_full(out=core.OUT, sig_path=None, oos_start=OOS_START, sel_path=None, dry=False):
    """Scores the frozen picks out of sample. Reads G8_selected.json and the frozen in-sample grid; selects nothing."""
    from scipy.stats import spearmanr
    sel = json.loads(pathlib.Path(sel_path or SEL_PATH).read_text())               # frozen; never rewritten here
    sig = pd.read_parquet(sig_path or g8_signals.path("full"))
    oos_start = pd.Timestamp(oos_start)
    is_end = oos_start - pd.Timedelta(days=1)
    if sig.date.max() < oos_start:
        raise SystemExit("no out-of-sample bars in this signal file: the full phase cannot run here")
    print(f"G8 grid   phase full{'  (DRY RUN on a made-up split: numbers mean nothing)' if dry else ''}"
          f"   signals {len(sig)}   {sig.date.min().date()} -> {sig.date.max().date()}   out of sample from {oos_start.date()}")
    d = out / "full"
    d.mkdir(parents=True, exist_ok=True)
    t_is, t_oos, t_all = evaluate(sig, end=is_end), evaluate(sig, start=oos_start), evaluate(sig)
    t_oos.to_csv(d / "G8_grid_oos.csv")
    t_all.to_csv(d / "G8_grid_full.csv")
    frozen = read_grid(out / "is" / "G8_grid.csv")
    same = (frozen.n.reindex(t_is.index) == t_is.n) & ((frozen.net.reindex(t_is.index) - t_is.net).abs() < 0.005)
    print(f"in-sample grid rebuilt from the full-span signals: {int(same.sum())} of {len(t_is)} combinations have the "
          f"frozen n and net $")
    res = {"oos_start": str(oos_start.date()), "last_day": str(sig.date.max().date()), "picks": [],
           "is_grid_reproduced": int(same.sum())}

    print("\nfrozen picks, out of sample")
    for r in sel["picks"]:
        v = pick_verdict(sig, r["combo"], oos_start)
        v.update(pick=r["pick"], name=r["name"], is_n=r["n"], is_R=r["R"], is_t=r["t"], is_rank=r["rank"],
                 is_reproduced=bool(same.get(r["name"], False)))
        res["picks"].append(v)
        if v["n"]:
            print(f"  pick {r['pick']}  {r['name']:<46} n {v['n']:>4}  net {v['net']:>+8.0f}  R {v['R']:+.4f}  p {v['p']:.5f}"
                  f"  R15 {v['R15']:+.4f}  R30 {v['R30']:+.4f}  years {v['by_year']}  -> {v['verdict']}  {v.get('checks')}"
                  f"   [in sample: n {r['n']}  R {r['R']:+.4f}  t {r['t']:+.2f}]")
        else:
            print(f"  pick {r['pick']}  {r['name']}  no out-of-sample trades -> {v['verdict']}")
    r = sel["largest_net"]
    if r is not None:
        v = pick_verdict(sig, r["combo"], oos_start)
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
    lt.to_csv(d / "G8_levels.csv", index=False)
    print(f"\neach confluence on its own: average of mean R over the in-sample-eligible combinations using the level")
    print(lt.to_string(index=False, formatters={"R_is": "{:+.4f}".format, "R_oos": "{:+.4f}".format,
                                                "trades_is": "{:.0f}".format, "trades_oos": "{:.0f}".format}))

    # ---- hindsight: the top of the full-span grid (the top of 5,184, labelled as such)
    ea = eligible(t_all)
    print(f"\nHINDSIGHT (full span, top of 5,184; {len(ea)} with >= {MIN_TRADES} trades): top 10 by net $")
    print(_show(ea.sort_values("net", ascending=False, kind="mergesort").head(10)))
    print("HINDSIGHT: top 10 by t")
    print(_show(ea.head(10)))
    rc = reality_check(sig, t_all)
    (d / "G8_reality_full.json").write_text(json.dumps(rc, indent=1))
    if rc.get("p") is not None:
        b = rc["boot_max_t"]
        print(f"full-span reality check: {rc['n_eligible']} combinations, {rc['n_days']} days: observed largest t "
              f"{rc['t_obs_max']:+.3f} ({rc['t_obs_max_name']}), resampled median {b['q50']:.3f}  95% {b['q95']:.3f}"
              f"   p = {rc['p']:.4f}")
    res["hindsight"] = {"by_net": [_record(r) for _, r in ea.sort_values("net", ascending=False, kind="mergesort").head(10).iterrows()],
                        "by_t": [_record(r) for _, r in ea.head(10).iterrows()], "reality_check": rc}
    (d / "G8_oos.json").write_text(json.dumps(res, indent=1, default=str))
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", choices=["is", "full"], required=True)
    ap.add_argument("--dry-split", help="code test only: run the full phase on a made-up split date")
    ap.add_argument("--dry-out", help="code test only: directory for the dry run's files")
    a = ap.parse_args()
    pd.set_option("display.width", 250)
    if a.phase == "is":
        phase_is()
    elif a.dry_split:
        assert a.dry_out, "--dry-split needs --dry-out (the real output directory is never written by a dry run)"
        o = pathlib.Path(a.dry_out)
        (o / "is").mkdir(parents=True, exist_ok=True)
        (o / "is" / "G8_grid.csv").write_bytes((core.OUT / "is" / "G8_grid.csv").read_bytes())
        phase_full(out=o, sig_path=g8_signals.path("is"), oos_start=a.dry_split, dry=True)
    else:
        phase_full()


if __name__ == "__main__":
    main()
