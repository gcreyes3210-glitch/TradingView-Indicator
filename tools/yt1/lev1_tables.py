#!/usr/bin/env python3
"""LEV1 tables, selection and the out-of-sample scoring of the frozen picks (YT9_SPEC.md).

    python3 tools/yt1/lev1_tables.py --phase is     tables of 2019-06 -> 2022-12 from is/LEV1_events.parquet, the
                                                    registered selection -> data/studies/yt1/LEV1_selected.json
    python3 tools/yt1/lev1_tables.py --phase full   never re-selects: reads LEV1_selected.json, checks that the
                                                    in-sample tables rebuilt from full/LEV1_events.parquet equal the
                                                    frozen ones, writes the tables for 2023-01-01 onward and for the
                                                    full span into full/, scores every pick out of sample
    --dry-split DATE --dry-out DIR                  code test only: both phases on a made-up split inside the
                                                    in-sample events, written to DIR and nowhere else

What an "event" is here (see lev1_events.py): the first tap of a level by 15:00. A cell = level code x side; its
events = the tapped FRESH rows in which that code is a lead of its cluster (a level tied at the nearest price counts
in its own cell too). n_<v> = the trades of variant v (events whose order filled), win_<v> = share of them that
reached the target, R_<v> = mean R, net_<v> = net $. Placebo columns: the placebo levels of that parent code on the
same side (the placebo's own side and own freshness). Cluster tables (pairs, by count, pooled) count each cluster
once (its first lead).
"""
import argparse, hashlib, itertools, json, math, pathlib, sys, time
import numpy as np
import pandas as pd
sys.path.insert(0, str(pathlib.Path(__file__).parent))
import core
import lev1_levels as LL
import lev1_events as LE

HEAD, ASKED, NB1, NB2 = "a04x3", "p20x3", "a08x3", "a04x2"
VARIANTS = [HEAD, ASKED] + [v for v in LE.VARIANTS if v not in (HEAD, ASKED)]
MIN_CELL, MIN_PAIR = 150, 60                 # fresh in-sample events of a cell; in-sample cluster days of a pair
N_CELLS, N_PAIRS = 5, 3
OOS_START = pd.Timestamp("2023-01-01")
OOS_YEARS = (2023, 2024, 2025, 2026)
OOS_MIN_CELL, OOS_MIN_PAIR = 100, 40
MIN_R = 0.05
P_LEVEL = 0.05 / 8
DIST_BINS = ((0.0, 0.1, "<0.10"), (0.1, 0.25, "0.10-0.25"), (0.25, 0.5, "0.25-0.50"), (0.5, 1.0, "0.50-1.00"))
SEL_NAME = "LEV1_selected.json"
TABLES = ("reaction", "draw", "pairs", "bytime", "used")
REAL = LL.ORDER


def events_path(phase):
    return core.OUT / phase / "LEV1_events.parquet"


def sha(path_or_text):
    if isinstance(path_or_text, pathlib.Path):
        return hashlib.sha256(path_or_text.read_bytes()).hexdigest()
    return hashlib.sha256(path_or_text.encode()).hexdigest()


def csv_text(df):
    return df.to_csv(index=False, float_format="%.6f")


def two_prop_p(w1, n1, w2, n2):
    """Two-sided p of the difference between two proportions (pooled normal approximation)."""
    if n1 == 0 or n2 == 0:
        return np.nan
    p = (w1 + w2) / (n1 + n2)
    se = math.sqrt(p * (1 - p) * (1 / n1 + 1 / n2))
    if se == 0:
        return 1.0
    return math.erfc(abs(w1 / n1 - w2 / n2) / se / math.sqrt(2))


def vstats(df, v, pre=""):
    f = df[f"f_{v}"].to_numpy(bool)
    n = int(f.sum())
    if n == 0:
        return {f"{pre}n_{v}": 0, f"{pre}win_{v}": np.nan, f"{pre}R_{v}": np.nan, f"{pre}net_{v}": 0.0}
    return {f"{pre}n_{v}": n, f"{pre}win_{v}": float(df[f"win_{v}"].to_numpy(bool)[f].mean()),
            f"{pre}R_{v}": float(df[f"R_{v}"].to_numpy(float)[f].mean()),
            f"{pre}net_{v}": float(df[f"pnl_{v}"].to_numpy(float)[f].sum())}


def fresh_mask(ev, fresh):
    return ev.fresh if fresh == "fresh" else ~ev.fresh if fresh == "used" else pd.Series(True, index=ev.index)


# ------------------------------------------------------------------ table 1: reaction by level
def reaction(ev, fresh="fresh"):
    """One row per real level code x side."""
    e = ev[ev.is_event & fresh_mask(ev, fresh)]
    real, plc = e[~e.is_placebo], e[e.is_placebo]
    rows = []
    for code in REAL:
        for side in ("R", "S"):
            w = real[(real.code == code) & (real.side == side)]
            if len(w) == 0:
                continue
            t = w[w.tapped]
            r = {"code": code, "side": side, "group": LL.GROUP[code], "watched": len(w), "events": len(t)}
            for v in VARIANTS:
                r.update(vstats(t, v))
            pw = plc[(plc.parent == code) & (plc.side == side)]
            pt = pw[pw.tapped]
            r.update(pl_watched=len(pw), pl_events=len(pt))
            for v in (HEAD, ASKED):
                r.update(vstats(pt, v, "pl_"))
                n1, n2 = r[f"n_{v}"], r[f"pl_n_{v}"]
                has = n1 > 0 and n2 > 0
                r[f"dwin_{v}"] = r[f"win_{v}"] - r[f"pl_win_{v}"] if has else np.nan
                r[f"dR_{v}"] = r[f"R_{v}"] - r[f"pl_R_{v}"] if has else np.nan
                r[f"pwin_{v}"] = two_prop_p(r[f"win_{v}"] * n1, n1, r[f"pl_win_{v}"] * n2, n2) if has else np.nan
            rows.append(r)
    tb = pd.DataFrame(rows)
    if len(tb) == 0:
        return tb
    tb["_o"] = np.arange(len(tb))
    tb = tb.sort_values([f"R_{HEAD}", "_o"], ascending=[False, True], na_position="last", kind="mergesort")
    return tb.drop(columns="_o").reset_index(drop=True)


# ------------------------------------------------------------------ table 2: draw
def draw(ev, fresh="any", by_time=False):
    """Share of watched level-days tapped by 15:00, by distance of the level from the 09:30 open; every static code
    next to its placebo. by_time: the share tapped in each time bucket as well."""
    w = ev[(ev.kind == "static") & ~ev.skipped & fresh_mask(ev, fresh)]
    rows = []
    for code in LL.STATIC:
        a, b = w[(w.code == code) & ~w.is_placebo], w[w.is_placebo & (w.parent == code)]
        for lo, hi, name in DIST_BINS:
            x, y = a[(a.dist_open >= lo) & (a.dist_open < hi)], b[(b.dist_open >= lo) & (b.dist_open < hi)]
            r = {"code": code, "dist": name, "n": len(x), "tapped": float(x.tapped.mean()) if len(x) else np.nan,
                 "pl_n": len(y), "pl_tapped": float(y.tapped.mean()) if len(y) else np.nan,
                 "n_beyond_1atr": int((a.dist_open >= 1.0).sum())}
            if by_time:
                for bk in LE.BUCKETS:
                    r[f"tapped_{bk}"] = float((x.bucket == bk).mean()) if len(x) else np.nan
                    r[f"pl_tapped_{bk}"] = float((y.bucket == bk).mean()) if len(y) else np.nan
            rows.append(r)
    return pd.DataFrame(rows)


# ------------------------------------------------------------------ table 3: combinations
def clusters(ev):
    """One row per real static cluster that is watched (its first lead)."""
    return ev[ev.is_event & (ev.kind == "static") & ~ev.is_placebo & ev.first_lead]


def pair_days(ev):
    """{(a, b): number of days on which a and b share a watched cluster}, any freshness, tapped or not."""
    c = clusters(ev)
    c = c[c.cl_n >= 2]
    out = {}
    for d, codes in zip(c.date, c.cl_codes):
        for pr in itertools.combinations(codes.split("+"), 2):
            out.setdefault(pr, set()).add(d)
    return {k: len(v) for k, v in out.items()}


def has_pair(cl_codes, pair):
    a, b = pair
    return np.array([a in s and b in s for s in (x.split("+") for x in cl_codes)], bool) if len(cl_codes) else np.zeros(0, bool)


def pairs(ev, pair_list, fresh="fresh", days=None):
    """One row per pair in pair_list: cluster days (all), and the fade / break numbers of its fresh tapped events."""
    c = clusters(ev)
    c = c[c.cl_n >= 2]
    days = pair_days(ev) if days is None else days
    f = c[fresh_mask(c, fresh)]
    rows = []
    for pr in pair_list:
        w = f[has_pair(f.cl_codes.to_numpy(), pr)]
        t = w[w.tapped]
        r = {"pair": "+".join(pr), "cluster_days": int(days.get(tuple(pr), 0)), "watched": len(w), "events": len(t)}
        for v in VARIANTS:
            r.update(vstats(t, v))
        rows.append(r)
    tb = pd.DataFrame(rows)
    if len(tb) == 0:
        return tb
    tb["_o"] = np.arange(len(tb))
    tb = tb.sort_values([f"R_{HEAD}", "_o"], ascending=[False, True], na_position="last", kind="mergesort")
    return tb.drop(columns="_o").reset_index(drop=True)


def bycount(ev, fresh="fresh"):
    c = clusters(ev)
    f = c[fresh_mask(c, fresh)]
    rows = []
    for name, m in (("1", f.cl_n == 1), ("2", f.cl_n == 2), ("3+", f.cl_n >= 3)):
        w = f[m]
        t = w[w.tapped]
        r = {"pair": f"count={name}", "cluster_days": len(c[(c.cl_n == 1) if name == "1" else (c.cl_n == 2) if name == "2" else (c.cl_n >= 3)]),
             "watched": len(w), "events": len(t)}
        for v in VARIANTS:
            r.update(vstats(t, v))
        rows.append(r)
    return pd.DataFrame(rows)


def eligible_pairs(ev, min_days=MIN_PAIR):
    d = pair_days(ev)
    return sorted(k for k, v in d.items() if v >= min_days)


# ------------------------------------------------------------------ table 4: by time of tap, and used levels
SHORT = ["code", "side", "group", "watched", "events"] + [f"{w}_{v}" for v in (HEAD, ASKED, "brk_a04") for w in ("n", "win", "R", "net")] \
    + ["pl_events"] + [f"pl_{w}_{v}" for v in (HEAD, ASKED) for w in ("n", "win", "R")]
PSHORT = ["pair", "cluster_days", "watched", "events"] + [f"{w}_{v}" for v in (HEAD, ASKED, "brk_a04") for w in ("n", "win", "R", "net")]


def bytime(ev, pair_list):
    parts = []
    for bk in LE.BUCKETS:
        sub = ev[(ev.bucket == bk) | ~ev.tapped]             # untapped rows keep the 'watched' counts
        r = reaction(sub)
        if len(r):
            r = r[SHORT].copy()
            r.insert(0, "bucket", bk); r.insert(0, "table", "reaction")
            parts.append(r)
        p = pd.concat([pairs(sub, pair_list, days=pair_days(ev)), bycount(sub)], ignore_index=True)[PSHORT]
        p.insert(0, "bucket", bk); p.insert(0, "table", "pairs")
        parts.append(p)
    dr = draw(ev, by_time=True)
    dr.insert(0, "bucket", "all"); dr.insert(0, "table", "draw")
    parts.append(dr)
    return pd.concat(parts, ignore_index=True)


def used_tables(ev, pair_list):
    parts = []
    for st in ("used", "any"):
        r = reaction(ev, st)
        if len(r):
            r.insert(0, "set", st); r.insert(0, "table", "reaction")
            parts.append(r)
    dr = draw(ev, "used")
    dr.insert(0, "set", "used"); dr.insert(0, "table", "draw")
    parts.append(dr)
    p = pd.concat([pairs(ev, pair_list, "used"), bycount(ev, "used")], ignore_index=True)
    p.insert(0, "set", "used"); p.insert(0, "table", "pairs")
    parts.append(p)
    return pd.concat(parts, ignore_index=True)


# ------------------------------------------------------------------ pooled real against placebo
def pooled(ev, fresh="fresh"):
    """All fresh real static events against all fresh placebo events. 'unique': each cluster once and each distinct
    placebo order once (two placebos at one price are one trade); 'rows': every tied lead and every placebo."""
    e = ev[ev.is_event & ev.tapped & (ev.kind == "static") & fresh_mask(ev, fresh)]
    out = {}
    for name, real, plc in (("unique", e[~e.is_placebo & e.first_lead],
                             e[e.is_placebo].drop_duplicates(["date", "side", "px", "w0"])),
                            ("rows", e[~e.is_placebo], e[e.is_placebo])):
        o = {}
        for v in (HEAD, ASKED):
            a, b = vstats(real, v), vstats(plc, v)
            n1, n2 = a[f"n_{v}"], b[f"n_{v}"]
            o[v] = {"real_n": n1, "real_win": a[f"win_{v}"], "real_R": a[f"R_{v}"], "placebo_n": n2,
                    "placebo_win": b[f"win_{v}"], "placebo_R": b[f"R_{v}"],
                    "dwin": a[f"win_{v}"] - b[f"win_{v}"] if n1 and n2 else np.nan,
                    "dR": a[f"R_{v}"] - b[f"R_{v}"] if n1 and n2 else np.nan,
                    "p_win": two_prop_p(a[f"win_{v}"] * n1, n1, b[f"win_{v}"] * n2, n2) if n1 and n2 else np.nan}
        out[name] = o
    return out


def pooled_lines(po, label):
    out = []
    for name in ("unique", "rows"):
        for v in (HEAD, ASKED):
            x = po[name][v]
            out.append(f"{label} pooled real vs placebo [{name:<6}] {v}: real n {x['real_n']:>5} win {x['real_win']:.1%} "
                       f"R {x['real_R']:+.4f} | placebo n {x['placebo_n']:>5} win {x['placebo_win']:.1%} R {x['placebo_R']:+.4f}"
                       f" | diff win {x['dwin'] * 100:+.2f} pts, R {x['dR']:+.4f}, two-proportion p {x['p_win']:.4f}")
    return out


# ------------------------------------------------------------------ selection
def select(rt, pt, min_cell=MIN_CELL, min_pair=MIN_PAIR, n_cells=N_CELLS, n_pairs=N_PAIRS):
    """The registered picks: the n_cells cells with the highest headline mean R among cells with >= min_cell fresh
    events; the n_pairs pairs with the highest among pairs with >= min_pair cluster days. rt / pt are sorted by it."""
    picks = []
    el = rt[(rt.events >= min_cell) & rt[f"R_{HEAD}"].notna()]
    for _, r in el.head(n_cells).iterrows():
        d = {"pick": len(picks) + 1, "type": "cell", "sel": f"{r.code}:{r.side}", "code": r.code, "side": r.side,
             "group": r.group, "events": int(r.events)}
        for v in (HEAD, NB1, NB2, ASKED, "brk_a04"):
            d[v] = {"n": int(r[f"n_{v}"]), "win": float(r[f"win_{v}"]), "R": float(r[f"R_{v}"]), "net": float(r[f"net_{v}"])}
        d["placebo"] = None if not r.pl_events else {"events": int(r.pl_events), "n": int(r[f"pl_n_{HEAD}"]),
                                                    "win": float(r[f"pl_win_{HEAD}"]), "R": float(r[f"pl_R_{HEAD}"])}
        picks.append(d)
    n_cell_picks = len(picks)
    ep = pt[(pt.cluster_days >= min_pair) & pt[f"R_{HEAD}"].notna()] if len(pt) else pt
    for _, r in ep.head(n_pairs).iterrows():
        d = {"pick": N_CELLS + 1 + (len(picks) - n_cell_picks), "type": "pair", "sel": r.pair, "codes": r.pair.split("+"),
             "cluster_days": int(r.cluster_days), "events": int(r.events)}
        for v in (HEAD, NB1, NB2, ASKED, "brk_a04"):
            d[v] = {"n": int(r[f"n_{v}"]), "win": float(r[f"win_{v}"]) if r[f"n_{v}"] else None,
                    "R": float(r[f"R_{v}"]) if r[f"n_{v}"] else None, "net": float(r[f"net_{v}"])}
        picks.append(d)
    return picks, {"cells": int(len(rt)), "cells_eligible": int(len(el)), "pairs_seen": None,
                   "pairs_eligible": int(len(pt)), "pairs_with_trades": int(len(ep))}


def pick_rows(ev, pick, fresh="fresh"):
    """The tapped event rows a pick counts (what s_L1 trades)."""
    e = ev[ev.is_event & ev.tapped & fresh_mask(ev, fresh)]
    if pick["type"] == "cell":
        return e[(e.code == pick["code"]) & (e.side == pick["side"]) & ~e.is_placebo]
    c = e[(e.kind == "static") & ~e.is_placebo & e.first_lead & (e.cl_n >= 2)]
    return c[has_pair(c.cl_codes.to_numpy(), tuple(pick["codes"]))]


def _fmt(tb, cols, pct=()):
    f = {}
    for c in cols:
        if c in pct or c.startswith(("win_", "pl_win_", "tapped", "pl_tapped")):
            f[c] = lambda x: "" if x != x else f"{x * 100:.1f}"
        elif c.startswith(("R_", "pl_R_", "dR_")):
            f[c] = lambda x: "" if x != x else f"{x:+.3f}"
        elif c.startswith("dwin_"):
            f[c] = lambda x: "" if x != x else f"{x * 100:+.1f}"
        elif c.startswith("pwin_"):
            f[c] = lambda x: "" if x != x else f"{x:.3f}"
        elif c.startswith(("net_",)):
            f[c] = lambda x: f"{x:+.0f}"
    return tb[cols].to_string(index=False, formatters=f)


RCOLS = ["code", "side", "watched", "events", f"n_{HEAD}", f"win_{HEAD}", f"R_{HEAD}", f"net_{HEAD}", f"n_{ASKED}",
         f"win_{ASKED}", f"R_{ASKED}", "pl_events", f"pl_win_{HEAD}", f"pl_R_{HEAD}", f"dwin_{HEAD}", f"dR_{HEAD}",
         f"pwin_{HEAD}", f"pl_win_{ASKED}", f"pl_R_{ASKED}", "R_brk_a04", "R_brk_p20"]
PCOLS = ["pair", "cluster_days", "watched", "events", f"n_{HEAD}", f"win_{HEAD}", f"R_{HEAD}", f"net_{HEAD}",
         f"win_{ASKED}", f"R_{ASKED}", f"R_{NB1}", f"R_{NB2}", "R_brk_a04"]


def build(ev, pair_list):
    rt = reaction(ev)
    pt = pd.concat([pairs(ev, pair_list), bycount(ev)], ignore_index=True)
    return {"reaction": rt, "draw": draw(ev), "pairs": pt, "bytime": bytime(ev, pair_list),
            "used": used_tables(ev, pair_list)}


def write(tabs, d, suffix=""):
    d.mkdir(parents=True, exist_ok=True)
    out = {}
    for k in TABLES:
        p = d / f"LEV1_{k}{suffix}.csv"
        p.write_text(csv_text(tabs[k]))
        out[k] = sha(p)
    return out


def show(tabs, label):
    rt, pt = tabs["reaction"], tabs["pairs"]
    print(f"\n{label}: reaction by level code x side, fresh events, sorted by the headline ({HEAD}) mean R "
          f"(win in %, pl_ = placebo, dwin in points, pwin = two-proportion p)")
    print(_fmt(rt, RCOLS))
    dr = tabs["draw"]
    wide = dr.pivot(index="code", columns="dist", values="tapped").reindex(index=LL.STATIC, columns=[b[2] for b in DIST_BINS])
    wn = dr.pivot(index="code", columns="dist", values="n").reindex(index=LL.STATIC, columns=[b[2] for b in DIST_BINS])
    wp = dr.pivot(index="code", columns="dist", values="pl_tapped").reindex(index=LL.STATIC, columns=[b[2] for b in DIST_BINS])
    print(f"\n{label}: draw, % of watched level-days tapped by 15:00 by distance from the 09:30 open (x ATR): "
          f"level / its placebo (level-days of the level)")
    for code in LL.STATIC:
        print(f"  {code:<6}" + "".join(
            f"   {name}: " + ("   -  " if wide.loc[code, name] != wide.loc[code, name] else f"{wide.loc[code, name] * 100:5.1f}")
            + " / " + ("  -  " if wp.loc[code, name] != wp.loc[code, name] else f"{wp.loc[code, name] * 100:5.1f}")
            + f" ({int(wn.loc[code, name]):>3})" for _, _, name in DIST_BINS))
    print(f"\n{label}: pairs sharing a cluster on >= {MIN_PAIR} in-sample days, and by number of levels in the cluster "
          f"(fresh events)")
    print(_fmt(pt, PCOLS))


# ------------------------------------------------------------------ phases
def phase_is(out=core.OUT, ev_path=None, end=None, quiet=False):
    t0 = time.time()
    ep = pathlib.Path(ev_path or events_path("is"))
    ev = pd.read_parquet(ep)
    if end is not None:
        ev = ev[ev.date < pd.Timestamp(end)]
    assert ev.date.max() < OOS_START, "the in-sample events reach into the out-of-sample window"
    print(f"LEV1 tables   phase is   events file {ep.name} ({len(ev)} rows)   {ev.date.min().date()} -> {ev.date.max().date()}"
          f"   study days {ev.date.nunique()}")
    pl = eligible_pairs(ev)
    tabs = build(ev, pl)
    hashes = write(tabs, out / "is")
    if not quiet:
        show(tabs, "IN SAMPLE")
    picks, cnt = select(tabs["reaction"], tabs["pairs"][~tabs["pairs"].pair.str.startswith("count=")])
    cnt["pairs_seen"] = len(pair_days(ev))
    po = pooled(ev)
    e = ev[ev.is_event]
    sel = {"spec": "YT9_SPEC.md", "phase": "is", "first_day": str(ev.date.min().date()), "last_day": str(ev.date.max().date()),
           "study_days": int(ev.date.nunique()),
           "thresholds": {"min_fresh_events_cell": MIN_CELL, "min_cluster_days_pair": MIN_PAIR, "n_cells": N_CELLS,
                          "n_pairs": N_PAIRS, "headline": HEAD, "neighbours": [NB1, NB2], "oos_start": str(OOS_START.date()),
                          "oos_min_events_cell": OOS_MIN_CELL, "oos_min_events_pair": OOS_MIN_PAIR, "oos_min_R": MIN_R,
                          "oos_p": P_LEVEL},
           "counts": dict(cnt, level_days=int(len(ev)), events=int(len(e)), tapped=int(e.tapped.sum()),
                          fresh_tapped=int((e.tapped & e.fresh).sum())),
           "picks": picks, "pooled": po, "eligible_pairs": ["+".join(p) for p in pl],
           "sha256_events": sha(ep), "sha256_tables": hashes}
    p = out / SEL_NAME
    new = json.dumps(sel, indent=1)
    if p.exists() and p.read_text() != new:
        print(f"\nNOTE: {p.name} existed with different content and is rewritten")
    p.write_text(new)
    print(f"\ncells {cnt['cells']}, with >= {MIN_CELL} fresh events {cnt['cells_eligible']}; pairs seen {cnt['pairs_seen']}, with >= "
          f"{MIN_PAIR} cluster days {cnt['pairs_eligible']}, of which with a fresh trade {cnt['pairs_with_trades']}")
    print("picks (frozen in " + str(p) + ")")
    for r in picks:
        h = r[HEAD]
        extra = (f"placebo win {r['placebo']['win']:.1%} R {r['placebo']['R']:+.4f}" if r.get("placebo") else
                 "no placebo" if r["type"] == "cell" else f"cluster days {r['cluster_days']}")
        print(f"  pick {r['pick']} [{r['type']}] {r['sel']:<14} events {r['events']:>4}  {HEAD}: n {h['n']:>4} win "
              + (f"{h['win']:.1%}" if h["win"] is not None else "-") + "  R " + (f"{h['R']:+.4f}" if h["R"] is not None else "-")
              + f"  net {h['net']:+.0f}   {NB1} R " + (f"{r[NB1]['R']:+.4f}" if r[NB1]["R"] is not None else "-")
              + f"   {NB2} R " + (f"{r[NB2]['R']:+.4f}" if r[NB2]["R"] is not None else "-")
              + f"   {ASKED} R " + (f"{r[ASKED]['R']:+.4f}" if r[ASKED]["R"] is not None else "-") + f"   {extra}")
    for line in pooled_lines(po, "IN SAMPLE"):
        print(line)
    print(f"\ntotal {time.time() - t0:.0f}s")
    return tabs, sel


def spearman(a, b):
    a, b = pd.Series(a).rank().to_numpy(), pd.Series(b).rank().to_numpy()
    if len(a) < 3 or a.std() == 0 or b.std() == 0:
        return np.nan
    return float(np.corrcoef(a, b)[0, 1])


def score_pick(ev_oos, pick, years=OOS_YEARS):
    """The registered out-of-sample test of one frozen pick."""
    t = pick_rows(ev_oos, pick)
    f = t[t[f"f_{HEAD}"]]
    out = {"pick": pick["pick"], "type": pick["type"], "sel": pick["sel"], "events": int(len(t)), "n": int(len(f))}
    need = OOS_MIN_CELL if pick["type"] == "cell" else OOS_MIN_PAIR
    if len(f) == 0:
        out["verdict"] = "not enough data"
        return out
    R = f[f"R_{HEAD}"].to_numpy(float)
    yr = f.date.dt.year
    by = {int(y): round(float(f[f"pnl_{HEAD}"][yr == y].sum()), 2) for y in years}
    nb = {v: vstats(t, v)[f"R_{v}"] for v in (NB1, NB2)}
    out.update(R=float(R.mean()), win=float(f[f"win_{HEAD}"].mean()), net=float(f[f"pnl_{HEAD}"].sum()),
               p=core.boot_p(R, n=10000, seed=1), by_year=by, years_positive=int(sum(v > 0 for v in by.values())),
               neighbours={k: (None if v != v else float(v)) for k, v in nb.items()})
    ch = {"events": len(t) >= need, "R": out["R"] >= MIN_R, "p": out["p"] < P_LEVEL,
          "years": out["years_positive"] >= 3, "neighbours": all(v == v and v > 0 for v in nb.values())}
    if pick["type"] == "cell":
        e = ev_oos[ev_oos.is_event & ev_oos.tapped & ev_oos.fresh & ev_oos.is_placebo
                   & (ev_oos.parent == pick["code"]) & (ev_oos.side == pick["side"])]
        ps = vstats(e, HEAD)
        if ps[f"n_{HEAD}"]:
            out["placebo"] = {"n": ps[f"n_{HEAD}"], "win": ps[f"win_{HEAD}"], "R": ps[f"R_{HEAD}"]}
            ch["placebo"] = out["win"] > ps[f"win_{HEAD}"]
        else:
            out["placebo"] = None
            ch["placebo"] = None                      # no placebo for this code (expected move, VWAP): cannot be judged
    out["checks"] = {k: (None if v is None else bool(v)) for k, v in ch.items()}
    if not ch["events"]:
        out["verdict"] = "not enough data"
    elif all(v for v in ch.values() if v is not None):
        out["verdict"] = "reacting level" + (" (no placebo exists for this code: that condition was not judged)"
                                             if ch.get("placebo", True) is None else "")
    else:
        out["verdict"] = "not a reacting level"
    return out


def phase_full(out=core.OUT, ev_path=None, oos_start=OOS_START, sel_path=None, frozen_dir=None, years=OOS_YEARS, dry=False):
    """Scores the frozen picks out of sample. Reads LEV1_selected.json and the frozen in-sample tables; selects nothing."""
    t0 = time.time()
    sel = json.loads(pathlib.Path(sel_path or (core.OUT / SEL_NAME)).read_text())      # frozen; never rewritten here
    ep = pathlib.Path(ev_path or events_path("full"))
    if not ep.exists():
        raise SystemExit(f"{ep} does not exist: run  python3 tools/yt1/lev1_events.py --phase full  first")
    ev = pd.read_parquet(ep)
    oos_start = pd.Timestamp(oos_start)
    if ev.date.max() < oos_start:
        raise SystemExit("no out-of-sample days in this events file: the full phase cannot run here")
    print(f"LEV1 tables   phase full{'  (DRY RUN on a made-up split: the numbers mean nothing)' if dry else ''}   events "
          f"{len(ev)} rows   {ev.date.min().date()} -> {ev.date.max().date()}   out of sample from {oos_start.date()}")
    ev_is, ev_oos = ev[ev.date < oos_start], ev[ev.date >= oos_start]
    fe = pathlib.Path(frozen_dir or (core.OUT / "is")) / "LEV1_events.parquet"
    if fe.exists():
        print(f"frozen in-sample events file {fe.name}: sha256 " + ("as stamped in the selection file" if sha(fe) == sel["sha256_events"]
                                                                   else "DIFFERS from the stamp in the selection file"))
    pl = [tuple(p.split("+")) for p in sel["eligible_pairs"]]                           # the frozen pair list
    d = out / "full"
    # ---- the in-sample tables rebuilt from the full data must equal the frozen ones
    t_is = build(ev_is, eligible_pairs(ev_is))
    fz = pathlib.Path(frozen_dir or (core.OUT / "is"))
    same = {}
    for k in TABLES:
        same[k] = csv_text(t_is[k]) == (fz / f"LEV1_{k}.csv").read_text()
    print("in-sample tables rebuilt from this events file against the frozen CSVs: "
          + ", ".join(f"{k} {'identical' if v else 'DIFFERENT'}" for k, v in same.items())
          + ("" if all(same.values()) else "   <-- the frozen tables are NOT reproduced"))
    picks_again, _ = select(t_is["reaction"], t_is["pairs"][~t_is["pairs"].pair.str.startswith("count=")])
    print("the selection rule applied to the rebuilt in-sample tables gives the frozen picks: "
          f"{[p['sel'] for p in picks_again] == [p['sel'] for p in sel['picks']]} (the frozen file is what is scored)")
    t_oos, t_all = build(ev_oos, pl), build(ev, pl)
    write(t_oos, d, "_oos"); write(t_all, d, "_full")
    show(t_oos, "OUT OF SAMPLE")
    # ---- the frozen picks
    res = {"oos_start": str(oos_start.date()), "last_day": str(ev.date.max().date()), "is_tables_reproduced": same,
           "picks": [], "p_level": P_LEVEL}
    print(f"\nfrozen picks out of sample (events >= {OOS_MIN_CELL}, or {OOS_MIN_PAIR} for a pair; {HEAD} mean R >= {MIN_R:+.2f}; "
          f"bootstrap p < {P_LEVEL:.5f}; at least 3 of the calendar years {', '.join(map(str, years))} net positive; {NB1} and "
          f"{NB2} positive; win rate above the placebo's, not for pairs)")
    for pk in sel["picks"]:
        v = score_pick(ev_oos, pk, years)
        v["in_sample"] = {"events": pk["events"], "R": pk[HEAD]["R"], "win": pk[HEAD]["win"]}
        res["picks"].append(v)
        if v["n"]:
            nbs = ", ".join(f"{k} " + ("-" if x is None else f"{x:+.4f}") for k, x in v["neighbours"].items())
            pls = "-" if not v.get("placebo") else f"win {v['placebo']['win']:.1%} R {v['placebo']['R']:+.4f} (n {v['placebo']['n']})"
            print(f"  pick {pk['pick']} [{pk['type']}] {pk['sel']:<14} events {v['events']:>4} n {v['n']:>4}  win {v['win']:.1%}  R {v['R']:+.4f}"
                  f"  net {v['net']:+.0f}  p {v['p']:.5f}  years {v['by_year']} ({v['years_positive']} positive)  neighbours {nbs}"
                  f"  placebo {pls}  -> {v['verdict']}  {v['checks']}   [in sample: events {pk['events']}, R "
                  + (f"{pk[HEAD]['R']:+.4f}" if pk[HEAD]["R"] is not None else "-") + "]")
        else:
            print(f"  pick {pk['pick']} [{pk['type']}] {pk['sel']}: no out-of-sample trades -> {v['verdict']}")
    # ---- do the same levels stay on top?
    a = t_is["reaction"].set_index(["code", "side"])
    b = t_oos["reaction"].set_index(["code", "side"]) if len(t_oos["reaction"]) else a.iloc[:0]
    j = a[["events", f"R_{HEAD}"]].join(b[["events", f"R_{HEAD}"]], lsuffix="_is", rsuffix="_oos", how="inner")
    j = j[(j.events_is >= MIN_CELL) & (j.events_oos >= OOS_MIN_CELL)]
    rho = spearman(j[f"R_{HEAD}_is"], j[f"R_{HEAD}_oos"])
    res["rank"] = {"cells": int(len(j)), "spearman": None if rho != rho else rho}
    print(f"\nrank correlation (Spearman) of the cells' {HEAD} mean R, in sample against out of sample, over the {len(j)} cells "
          f"with >= {MIN_CELL} in-sample and >= {OOS_MIN_CELL} out-of-sample events: " + ("n/a" if rho != rho else f"{rho:+.3f}"))
    if len(j):
        print(j.reset_index().to_string(index=False, formatters={f"R_{HEAD}_is": "{:+.4f}".format, f"R_{HEAD}_oos": "{:+.4f}".format}))
    po_is, po_oos = pooled(ev_is), pooled(ev_oos)
    res["pooled"] = {"is": po_is, "oos": po_oos}
    print()
    for line in pooled_lines(po_is, "IN SAMPLE    ") + pooled_lines(po_oos, "OUT OF SAMPLE"):
        print(line)
    d.mkdir(parents=True, exist_ok=True)
    (d / "LEV1_oos.json").write_text(json.dumps(res, indent=1, default=str))
    print(f"\ntotal {time.time() - t0:.0f}s")
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", choices=["is", "full"], required=True)
    ap.add_argument("--dry-split", help="code test only: a made-up split date inside the in-sample events")
    ap.add_argument("--dry-out", help="code test only: directory for the dry run's files")
    a = ap.parse_args()
    pd.set_option("display.width", 320)
    pd.set_option("display.max_rows", 500)
    pd.set_option("display.max_columns", 60)
    if a.dry_split:
        assert a.dry_out, "--dry-split needs --dry-out (the real output directories are never written by a dry run)"
        o = pathlib.Path(a.dry_out).resolve()
        assert core.OUT.resolve() not in o.parents and o != core.OUT.resolve(), "a dry run may not write into the study folder"
        split = pd.Timestamp(a.dry_split)
        if a.phase == "is":
            phase_is(out=o, end=split, quiet=True)
        else:
            yrs = tuple(range(split.year, 2023))
            phase_full(out=o, ev_path=events_path("is"), oos_start=split, sel_path=o / SEL_NAME, frozen_dir=o / "is",
                       years=yrs, dry=True)
    elif a.phase == "is":
        phase_is()
    else:
        phase_full()


if __name__ == "__main__":
    main()
