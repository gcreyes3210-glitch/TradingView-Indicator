#!/usr/bin/env python3
"""LEV2 tables, the registered selection and the out-of-sample scoring (YT10_SPEC.md): MID1 and VPN1.

    python3 tools/yt1/lev2_tables.py --phase is     tables of 2019-06 -> 2022-12 from is/MID1_events.parquet,
                                                    is/VPN1_events.parquet, is/VPN1_daytypes.csv; the registered
                                                    selection -> data/studies/yt1/VPN1_selected.json
    python3 tools/yt1/lev2_tables.py --phase full   never re-selects: reads VPN1_selected.json, checks that the
                                                    in-sample tables rebuilt from the full files equal the frozen
                                                    ones, writes the tables for 2023-01-01 onward (_oos) and for the
                                                    full span (_full) into full/, gives the MID1 verdicts and scores
                                                    every pick out of sample -> full/LEV2_oos.json
    --dry-split DATE --dry-out DIR                  code test only: both phases on a made-up split inside the
                                                    in-sample files, written to DIR and nowhere else

An event = the first tap of a level by 15:00 (lev2_events): a tapped row. Every level is scored on its own: no
clusters, no "fresh" requirement. n_<v> = the trades of variant v (events whose order filled), win_<v> = share of
them that reached the target, R_<v> = mean R, net_<v> = net $. Placebo columns (pl_): the placebo levels of that
parent on the same side, with the placebo's own side, own `crossed` and own split value.
Trades: fade headline a04x3 (neighbours a08x3, a04x2; p20x3 as asked); break headline brk_a04 (neighbours brk_a08,
brk_a04x2).
"""
import argparse, json, math, pathlib, sys, time
import numpy as np
import pandas as pd
sys.path.insert(0, str(pathlib.Path(__file__).parent))
import core
import lev1_tables as LT
import lev2_levels as LV
import lev2_events as LE2

VARIANTS = LE2.VARIANTS
HEAD, ASKED, NB1, NB2 = LE2.HEAD, LE2.ASKED, LE2.NB1, LE2.NB2
BHEAD, BNB1, BNB2 = LE2.BHEAD, LE2.BNB1, LE2.BNB2
TRIO = {"fade": (HEAD, NB1, NB2), "break": (BHEAD, BNB1, BNB2)}
MID, MIDP = LV.MID, LV.MID + "~"
PROFS, LEVELS = LV.PROFS, LV.LEVELS
SIDES = ("R", "S")
TRADES = ("fade", "break")
MIN_CELL, MIN_STACK, MIN_APOC = 150, 100, 60          # in-sample events: a cell, a stacked bucket, the aligned POC
N_CELLS = 5
OOS_START = pd.Timestamp("2023-01-01")
OOS_YEARS = (2023, 2024, 2025, 2026)
ALL_YEARS = tuple(range(2019, 2027))
OOS_MIN_CELL, OOS_MIN_OTHER = 100, 60                 # out-of-sample events: picks 1-5, picks 6-8
MIN_R = 0.05
P_PICK = 0.05 / 8
P_MID_PASS, P_MID_CAND = 0.05 / 130, 0.05
MID_MIN_N = 100                                       # YT1's usual criterion: fewer trades = not enough data
SEL_NAME = "VPN1_selected.json"
CSV_TABLES = ("MID1_levels", "MID1_splits", "VPN1_reaction", "VPN1_stacked", "VPN1_byN", "VPN1_daytypes_table")
JSON_TABLES = ("VPN1_vatrend",)
vstats, two_prop_p, sha, csv_text, spearman = LT.vstats, LT.two_prop_p, LT.sha, LT.csv_text, LT.spearman


def allv(t, pre="", variants=VARIANTS):
    r = {}
    for v in variants:
        r.update(vstats(t, v, pre))
    return r


def versus(r, v):
    """Real against placebo for variant v, from a row holding both."""
    n1, n2 = r[f"n_{v}"], r[f"pl_n_{v}"]
    has = n1 > 0 and n2 > 0
    return {f"dwin_{v}": r[f"win_{v}"] - r[f"pl_win_{v}"] if has else np.nan,
            f"dR_{v}": r[f"R_{v}"] - r[f"pl_R_{v}"] if has else np.nan,
            f"pwin_{v}": two_prop_p(r[f"win_{v}"] * n1, n1, r[f"pl_win_{v}"] * n2, n2) if has else np.nan}


# ------------------------------------------------------------------ MID1
def mid_levels_table(ev):
    """Every hourly open and the midnight placebos: both sides and pooled, all variants. rank_* = the code's rank
    among the 13 hourly opens (1 = highest) on the pooled rows."""
    rows = []
    for code in LV.MID_CODES + [MIDP]:
        x = ev[ev.code == code]
        for side in ("all",) + SIDES:
            w = x if side == "all" else x[x.side == side]
            e = w[w.is_event]
            t = e[e.tapped]
            r = {"code": code, "side": side, "is_placebo": code.endswith("~"), "level_days": len(w),
                 "skipped": int(w.skipped.sum()), "watched": len(e), "events": len(t),
                 "crossed_events": int(t.crossed.sum())}
            r.update(allv(t))
            rows.append(r)
    tb = pd.DataFrame(rows)
    m = (tb.side == "all") & ~tb.is_placebo
    for name, col in (("rank_R", f"R_{HEAD}"), ("rank_win", f"win_{HEAD}"), ("rank_R_asked", f"R_{ASKED}"),
                      ("rank_R_break", f"R_{BHEAD}")):
        tb[name] = np.nan
        tb.loc[m, name] = tb.loc[m, col].rank(ascending=False, method="min")
    return tb


def _split_masks(x):
    """The registered splits of the midnight open: [(split, value, mask over x)]."""
    out = [("all", "all", pd.Series(True, index=x.index))]
    out += [("side", s, x.side == s) for s in ("S", "R")]
    out += [("time", b, x.bucket == b) for b in LE2.BUCKETS]
    out += [("dist", name, x.dbucket == name) for _, _, name in LE2.DIST_BINS]
    out += [("crossed", "yes", x.crossed), ("crossed", "no", ~x.crossed)]
    out += [("bias", rel, x.bias_rel == rel) for rel in ("with", "against", "none")]
    return out


def mid_splits(ev, code=MID):
    x, pl = ev[ev.code == code], ev[ev.code == code + "~"]
    rows = []
    for (split, value, m), (_, _, mp) in zip(_split_masks(x), _split_masks(pl)):
        w, pw = x[m], pl[mp]
        e, t = w[w.is_event], w[w.is_event & w.tapped]
        pt = pw[pw.is_event & pw.tapped]
        timed = split == "time"                               # a time bucket exists only for a tapped event
        r = {"split": split, "value": value, "level_days": np.nan if timed else len(w),
             "skipped": np.nan if timed else int(w.skipped.sum()), "watched": np.nan if timed else len(e),
             "events": len(t)}
        r.update(allv(t))
        r["pl_events"] = len(pt)
        for v in (HEAD, ASKED, BHEAD):
            r.update(vstats(pt, v, "pl_"))
        for v in (HEAD, ASKED):
            r.update(versus(r, v))
        rows.append(r)
    return pd.DataFrame(rows)


def mid_rows(ev, rel=None, code=MID):
    """The tapped event rows of the midnight open (rel: only that bias relation)."""
    t = ev[(ev.code == code) & ev.is_event & ev.tapped]
    return t if rel is None else t[t.bias_rel == rel]


def mid_verdict(ev, rel=None, years=ALL_YEARS, split=OOS_START):
    """The registered verdict on the full span, both sides pooled, headline fade (rel='with': the with-bias fade)."""
    t, pt = mid_rows(ev, rel), mid_rows(ev, rel, MIDP)
    f = t[t[f"f_{HEAD}"]]
    out = {"what": "midnight open, headline fade" + ("" if rel is None else f", bias relation '{rel}'"),
           "events": int(len(t)), "n": int(len(f))}
    if len(f) < MID_MIN_N:
        out["verdict"] = "not enough data"
        return out
    R = f[f"R_{HEAD}"].to_numpy(float)
    yr = f.date.dt.year
    by = {int(y): round(float(f[f"pnl_{HEAD}"][yr == y].sum()), 2) for y in years}
    byn = {int(y): int((yr == y).sum()) for y in years}
    h1, h2 = f[f.date < split], f[f.date >= split]
    nb = {v: vstats(t, v)[f"R_{v}"] for v in (NB1, NB2)}
    ps = vstats(pt, HEAD)
    brk = vstats(t, BHEAD)
    out.update(R=float(R.mean()), win=float(f[f"win_{HEAD}"].mean()), net=float(f[f"pnl_{HEAD}"].sum()),
               p=core.boot_p(R, n=10000, seed=1), by_year=by, n_by_year=byn,
               years_positive=int(sum(v > 0 for v in by.values())), years_traded=int(sum(v > 0 for v in byn.values())),
               R_h1=float(h1[f"R_{HEAD}"].mean()) if len(h1) else None, n_h1=int(len(h1)),
               R_h2=float(h2[f"R_{HEAD}"].mean()) if len(h2) else None, n_h2=int(len(h2)),
               neighbours={k: (None if v != v else float(v)) for k, v in nb.items()},
               asked={"n": vstats(t, ASKED)[f"n_{ASKED}"], "win": vstats(t, ASKED)[f"win_{ASKED}"], "R": vstats(t, ASKED)[f"R_{ASKED}"]},
               placebo={"events": int(len(pt)), "n": ps[f"n_{HEAD}"], "win": ps[f"win_{HEAD}"], "R": ps[f"R_{HEAD}"]},
               break_trade={"n": brk[f"n_{BHEAD}"], "win": brk[f"win_{BHEAD}"], "R": brk[f"R_{BHEAD}"], "net": brk[f"net_{BHEAD}"]})
    ch = {"years": out["years_positive"] >= 6, "R": out["R"] >= MIN_R,
          "halves": out["R_h1"] is not None and out["R_h2"] is not None and out["R_h1"] >= 0 and out["R_h2"] >= 0,
          "neighbours": all(v == v and v > 0 for v in nb.values()),
          "placebo": bool(ps[f"n_{HEAD}"]) and out["win"] > ps[f"win_{HEAD}"], "p": out["p"] < P_MID_PASS}
    out["checks"] = {k: bool(v) for k, v in ch.items()}
    rest = all(v for k, v in ch.items() if k != "p")
    out["verdict"] = "passes" if rest and ch["p"] else "candidate" if rest and out["p"] < P_MID_CAND else "fails"
    return out


# ------------------------------------------------------------------ VPN1
def real_rows(ev):
    return ev[~ev.is_placebo & ev.prof.isin(PROFS)]


def reaction(ev):
    """profile x level x side, for all events and split by `crossed`: fade and break numbers, and the placebo's."""
    real, plc = real_rows(ev), ev[ev.is_placebo]
    real, plc = real[real.is_event], plc[plc.is_event]
    gr = {k: g for k, g in real.groupby(["prof", "level", "side"], sort=False)}
    gp = {k: g for k, g in plc.groupby(["prof", "level", "side"], sort=False)}
    rows = []
    for st in ("all", "crossed", "uncrossed"):
        for prof in PROFS:
            for lvl in LEVELS:
                for side in SIDES:
                    w, pw = gr.get((prof, lvl, side)), gp.get((prof, lvl, side))
                    w = real.iloc[:0] if w is None else w
                    pw = plc.iloc[:0] if pw is None else pw
                    if st != "all":
                        w, pw = w[w.crossed == (st == "crossed")], pw[pw.crossed == (st == "crossed")]
                    t, pt = w[w.tapped], pw[pw.tapped]
                    r = {"prof": prof, "level": lvl, "side": side, "set": st, "family": LV.family(prof), "watched": len(w),
                         "events": len(t)}
                    r.update(allv(t))
                    r.update(pl_watched=len(pw), pl_events=len(pt))
                    for v in (HEAD, ASKED, BHEAD):
                        r.update(vstats(pt, v, "pl_"))
                    for v in (HEAD, ASKED):
                        r.update(versus(r, v))
                    rows.append(r)
    return pd.DataFrame(rows)


def cells(rt):
    """One row per profile x level x side x trade from the 'all' rows of the reaction table, in the fixed order
    (profile, level, side, trade) that breaks ties. head / nb1 / nb2 = the trade's headline and two neighbours."""
    a = rt[rt.set == "all"]
    rows = []
    for _, r in a.iterrows():
        for trade in TRADES:
            h, n1, n2 = TRIO[trade]
            d = {"prof": r.prof, "level": r.level, "side": r.side, "trade": trade, "family": r.family,
                 "events": int(r.events), "n": int(r[f"n_{h}"]), "win": r[f"win_{h}"], "R": r[f"R_{h}"], "net": r[f"net_{h}"],
                 "R_nb1": r[f"R_{n1}"], "R_nb2": r[f"R_{n2}"]}
            if trade == "fade":
                d.update(R_asked=r[f"R_{ASKED}"], win_asked=r[f"win_{ASKED}"], pl_events=int(r.pl_events),
                         pl_n=int(r[f"pl_n_{HEAD}"]), pl_win=r[f"pl_win_{HEAD}"], pl_R=r[f"pl_R_{HEAD}"])
            else:
                d.update(R_asked=r["R_brk_p20"], win_asked=r["win_brk_p20"], pl_events=int(r.pl_events),
                         pl_n=int(r[f"pl_n_{BHEAD}"]), pl_win=r[f"pl_win_{BHEAD}"], pl_R=r[f"pl_R_{BHEAD}"])
            rows.append(d)
    return pd.DataFrame(rows)


def stacked(ev):
    """Fade and break by the stacked-level count (real profile-level events), and the aligned-POC events."""
    real = real_rows(ev)
    real = real[real.is_event]
    ap = ev[ev.code.isin(LV.APOC) & ev.is_event]
    rows = []
    groups = [("stack", b, real[real.sbucket == b]) for b in LE2.SBUCKETS]
    groups += [("apoc", "apoc_rth", ap[ap.code == "apoc_rth"]), ("apoc", "apoc_eth", ap[ap.code == "apoc_eth"]),
               ("apoc", "apoc", ap)]
    for kind, key, w0 in groups:
        for side in ("all",) + SIDES:
            w = w0 if side == "all" else w0[w0.side == side]
            t = w[w.tapped]
            r = {"kind": kind, "key": key, "side": side, "watched": len(w), "events": len(t),
                 "distinct_orders": len(t.drop_duplicates(["date", "side", "px"])), "days": int(t.date.nunique())}
            r.update(allv(t))
            rows.append(r)
    return pd.DataFrame(rows)


def byn(ev):
    """Mean R by lookback N for rth and eth (sides pooled; level 'all' and each level), and `on` for reference."""
    real, plc = real_rows(ev), ev[ev.is_placebo]
    real, plc = real[real.is_event & real.tapped], plc[plc.is_event & plc.tapped]
    rows = []
    for prof in PROFS:
        st, n = LV.family(prof), ("w" if prof.endswith("w") else prof[3:] if prof != "on" else "-")
        for lvl in ("all",) + LEVELS:
            t = real[real.prof == prof] if lvl == "all" else real[(real.prof == prof) & (real.level == lvl)]
            pt = plc[plc.prof == prof] if lvl == "all" else plc[(plc.prof == prof) & (plc.level == lvl)]
            r = {"stype": st, "N": n, "prof": prof, "level": lvl, "events": len(t)}
            r.update(allv(t, variants=(HEAD, ASKED, NB1, NB2, BHEAD, "brk_p20")))
            r["pl_events"] = len(pt)
            for v in (HEAD, ASKED, BHEAD):
                r.update(vstats(pt, v, "pl_"))
            r.update(versus(r, HEAD))
            rows.append(r)
    return pd.DataFrame(rows)


def read_daytypes(path):
    dt = pd.read_csv(path, parse_dates=["date"])
    for c in dt.columns:
        if c.startswith("type_") or c.endswith("_side"):
            dt[c] = dt[c].fillna("")
    return dt


def _tstat(x, pre):
    """n, win (net > 0), mean R, net of a set of trades given as (R, pnl) columns."""
    n = len(x)
    return {f"{pre}n": n, f"{pre}win": float((x.iloc[:, 1] > 0).mean()) if n else np.nan,
            f"{pre}R": float(x.iloc[:, 0].mean()) if n else np.nan, f"{pre}net": float(x.iloc[:, 1].sum()) if n else 0.0}


def daytypes_table(dt):
    """For rth and eth, by day type (study days): the 09:30 -> flat-bar move in the accepted direction (up when the
    open is above all five value areas, down when below; 'inside', 'mixed' and 'all' have none and show the up move),
    ORB v1.4 on those days split by whether its trade agrees with the day type, and the VA-trend trade of the family."""
    s = dt[dt.study]
    rows = []
    for fam in ("rth", "eth"):
        col = f"type_{fam}"
        for typ in ("above", "below", "inside", "mixed", "", "all"):
            x = s if typ == "all" else s[s[col] == typ]
            sign = -1.0 if typ == "below" else 1.0
            mv = sign * x.move_up
            r = {"family": fam, "type": typ or "not built", "direction": "down" if typ == "below" else "up" if typ == "above" else "none (up shown)",
                 "days": len(x), "move_mean": float(mv.mean()) if len(x) else np.nan,
                 "move_median": float(mv.median()) if len(x) else np.nan, "hit": float((mv > 0).mean()) if len(x) else np.nan}
            o = x[x.orb_side != ""]
            r.update(_tstat(o[["orb_R", "orb_pnl"]], "orb_"))
            for nm, sd in (("long", "L"), ("short", "S")):
                r.update(_tstat(o[o.orb_side == sd][["orb_R", "orb_pnl"]], f"orb_{nm}_"))
            if typ in ("above", "below"):
                ag = o.orb_side == ("L" if typ == "above" else "S")
                r.update(_tstat(o[ag][["orb_R", "orb_pnl"]], "orb_agree_"))
                r.update(_tstat(o[~ag][["orb_R", "orb_pnl"]], "orb_disagree_"))
            else:
                r.update(_tstat(o.iloc[:0][["orb_R", "orb_pnl"]], "orb_agree_"))
                r.update(_tstat(o.iloc[:0][["orb_R", "orb_pnl"]], "orb_disagree_"))
            v = x[x[f"va_{fam}_side"] != ""] if typ != "all" else s[s[f"va_{fam}_side"] != ""]
            r.update(_tstat(v[[f"va_{fam}_R", f"va_{fam}_pnl"]], "va_"))
            rows.append(r)
    return pd.DataFrame(rows)


def va_stats(dt, which, years=ALL_YEARS):
    s = dt[dt.study & (dt[f"va_{which}_side"] != "")]
    R, pnl = s[f"va_{which}_R"].to_numpy(float), s[f"va_{which}_pnl"].to_numpy(float)
    yr = s.date.dt.year.to_numpy()
    out = {"which": which, "n": int(len(s))}
    if not len(s):
        return out
    L_, S_ = s[f"va_{which}_side"].to_numpy() == "L", s[f"va_{which}_side"].to_numpy() == "S"
    out.update(R=float(R.mean()), net=float(pnl.sum()), win=float((pnl > 0).mean()), p=core.boot_p(R, n=10000, seed=1),
               n_long=int(L_.sum()), R_long=float(R[L_].mean()) if L_.any() else None,
               n_short=int(S_.sum()), R_short=float(R[S_].mean()) if S_.any() else None,
               by_year={int(y): {"n": int((yr == y).sum()), "net": round(float(pnl[yr == y].sum()), 2),
                                 "R": float(R[yr == y].mean()) if (yr == y).any() else None} for y in years})
    return out


def vatrend(dt, years=ALL_YEARS):
    return {"rule": "VA-trend: at the 09:30 open, long above all five rth VAHs, short below all five VALs, no stop, "
                    "flat at the flat bar, R unit 0.1 x ATR; win = net > 0",
            "base": va_stats(dt, "rth", years), "nb1": va_stats(dt, "eth", years), "nb2": va_stats(dt, "rth3", years)}


def pooled(real, plc, variants=(HEAD, ASKED, BHEAD)):
    """Tapped real events against tapped placebo events. 'rows': every level row; 'distinct': each distinct order
    (date x side x price) once."""
    out = {}
    for name, a_, b_ in (("rows", real, plc), ("distinct", real.drop_duplicates(["date", "side", "px"]),
                                               plc.drop_duplicates(["date", "side", "px"]))):
        o = {}
        for v in variants:
            a, b = vstats(a_, v), vstats(b_, v)
            n1, n2 = a[f"n_{v}"], b[f"n_{v}"]
            has = n1 > 0 and n2 > 0
            o[v] = {"real_n": n1, "real_win": a[f"win_{v}"], "real_R": a[f"R_{v}"], "placebo_n": n2,
                    "placebo_win": b[f"win_{v}"], "placebo_R": b[f"R_{v}"],
                    "dwin": a[f"win_{v}"] - b[f"win_{v}"] if has else np.nan, "dR": a[f"R_{v}"] - b[f"R_{v}"] if has else np.nan,
                    "p_win": two_prop_p(a[f"win_{v}"] * n1, n1, b[f"win_{v}"] * n2, n2) if has else np.nan}
        out[name] = o
    return out


def pooled_all(mid, vp):
    t = lambda e: e[e.is_event & e.tapped]
    m, v = t(mid), t(vp)
    return {"MID1 o00": pooled(m[m.code == MID], m[m.code == MIDP]),
            "VPN1 39 levels": pooled(real_rows(v), v[v.is_placebo])}


def pooled_lines(po, label):
    out = []
    for study, d in po.items():
        for name in ("rows", "distinct"):
            for v, x in d[name].items():
                if not x["real_n"] or not x["placebo_n"]:
                    out.append(f"{label} {study:<14} real vs placebo [{name:<8}] {v:<8}: real n {x['real_n']}, placebo n {x['placebo_n']}")
                    continue
                out.append(f"{label} {study:<14} real vs placebo [{name:<8}] {v:<8}: real n {x['real_n']:>5} win {x['real_win']:.1%} "
                           f"R {x['real_R']:+.4f} | placebo n {x['placebo_n']:>5} win {x['placebo_win']:.1%} R {x['placebo_R']:+.4f}"
                           f" | diff win {x['dwin'] * 100:+.2f} pts, R {x['dR']:+.4f}, two-proportion p {x['p_win']:.4f}")
    return out


# ------------------------------------------------------------------ selection
def _num(x):
    return None if x is None or x != x else float(x)


def _trio(t, trade):
    out = {}
    for name, v in zip(("head", "nb1", "nb2"), TRIO[trade]):
        s = vstats(t, v)
        out[name] = {"variant": v, "n": int(s[f"n_{v}"]), "win": _num(s[f"win_{v}"]), "R": _num(s[f"R_{v}"]), "net": float(s[f"net_{v}"])}
    return out


def distinct(t, v, with_p=False):
    """The same trades with each distinct order (date x side x price) counted once: several profiles' levels at one
    price are one order. Reported beside the registered row counts; never used for a verdict."""
    u = t[t[f"f_{v}"]].drop_duplicates(["date", "side", "px"])
    out = {"n": int(len(u)), "win": _num(u[f"win_{v}"].mean()) if len(u) else None, "R": _num(u[f"R_{v}"].mean()) if len(u) else None,
           "net": float(u[f"pnl_{v}"].sum()), "days": int(u.date.nunique())}
    if with_p:
        out["p"] = core.boot_p(u[f"R_{v}"].to_numpy(float), n=10000, seed=1) if len(u) else None
    return out


def pick_rows(ev, pick):
    """The tapped event rows a pick counts (what s_L2 trades)."""
    e = ev[ev.is_event & ev.tapped]
    if pick["type"] == "cell":
        return e[(e.prof == pick["prof"]) & (e.level == pick["level"]) & (e.side == pick["side"]) & ~e.is_placebo]
    if pick["type"] == "stack":
        return e[~e.is_placebo & e.prof.isin(PROFS) & (e.sbucket == pick["bucket"])]
    if pick["type"] == "apoc":
        return e[e.code.isin(LV.APOC)]
    raise ValueError(pick["type"])


def placebo_rows(ev, pick):
    e = ev[ev.is_event & ev.tapped & ev.is_placebo]
    return e[(e.prof == pick["prof"]) & (e.level == pick["level"]) & (e.side == pick["side"])]


def select(ev, dt, rt, stk, years=ALL_YEARS):
    """The registered picks 1-8 with their in-sample numbers."""
    picks = []
    ct = cells(rt)
    el = ct[(ct.events >= MIN_CELL) & ct.R.notna()].copy()
    el["_o"] = np.arange(len(el))
    el = el.sort_values(["R", "_o"], ascending=[False, True], kind="mergesort")
    taken = set()
    for _, r in el.iterrows():                                   # picks 1-5: at most one per family x level x side x trade
        key = (r.family, r.level, r.side, r.trade)
        if key in taken:
            continue
        taken.add(key)
        p = {"pick": len(picks) + 1, "type": "cell", "sel": f"{r.prof}_{r.level}:{r.side}:{r.trade}", "prof": r.prof,
             "level": r.level, "side": r.side, "trade": r.trade, "family": r.family, "events": int(r.events)}
        p.update(_trio(pick_rows(ev, p), r.trade))
        pl = placebo_rows(ev, p)
        ps = vstats(pl, TRIO[r.trade][0])
        h = TRIO[r.trade][0]
        p["placebo"] = {"events": int(len(pl)), "n": int(ps[f"n_{h}"]), "win": _num(ps[f"win_{h}"]), "R": _num(ps[f"R_{h}"])}
        picks.append(p)
        if len(picks) == N_CELLS:
            break
    cnt = {"cells": int(len(ct)), "cells_eligible": int(len(el)), "cell_picks": len(picks)}
    # pick 6: the stacked-count bucket (1, 2, 3+) x trade with the highest headline mean R, >= 100 events
    best = None
    for b in LE2.SBUCKETS[1:]:
        r = stk[(stk.kind == "stack") & (stk.key == b) & (stk.side == "all")].iloc[0]
        for trade in TRADES:
            R = r[f"R_{TRIO[trade][0]}"]
            if r.events >= MIN_STACK and R == R and (best is None or R > best[0]):
                best = (float(R), b, trade, int(r.events))
    if best is not None:
        p = {"pick": 6, "type": "stack", "sel": f"stack{best[1]}:{best[2]}", "bucket": best[1], "trade": best[2], "events": best[3]}
        p.update(_trio(pick_rows(ev, p), best[2]))
        p["distinct_orders"] = distinct(pick_rows(ev, p), TRIO[best[2]][0])
        picks.append(p)
    # pick 7: the aligned-POC event (rth and eth together) x trade with the higher headline mean R, >= 60 events
    r = stk[(stk.kind == "apoc") & (stk.key == "apoc") & (stk.side == "all")].iloc[0]
    cnt["apoc_events"] = {k: int(stk[(stk.kind == "apoc") & (stk.key == k) & (stk.side == "all")].events.iloc[0])
                          for k in ("apoc_rth", "apoc_eth", "apoc")}
    if r.events >= MIN_APOC:
        Rf, Rb = r[f"R_{HEAD}"], r[f"R_{BHEAD}"]
        trade = "break" if (Rb == Rb and (Rf != Rf or Rb > Rf)) else "fade"
        p = {"pick": 7, "type": "apoc", "sel": f"apoc:{trade}", "trade": trade, "events": int(r.events)}
        p.update(_trio(pick_rows(ev, p), trade))
        p["distinct_orders"] = distinct(pick_rows(ev, p), TRIO[trade][0])
        picks.append(p)
    # pick 8: VA-trend
    va = vatrend(dt, years)
    picks.append({"pick": 8, "type": "vatrend", "sel": "VA-trend", "events": va["base"]["n"], "head": va["base"],
                  "nb1": va["nb1"], "nb2": va["nb2"]})
    return picks, cnt


def pick_line(p):
    if p["type"] == "vatrend":
        h = p["head"]
        f = lambda x: "-" if x.get("R") is None else f"{x['R']:+.4f}"
        return (f"  pick {p['pick']} [vatrend] {p['sel']:<22} trades {h['n']:>4}  win(net>0) " + ("-" if not h["n"] else f"{h['win']:.1%}")
                + f"  R {f(h)}  net {h.get('net', 0):+.0f}   nb1 (eth) n {p['nb1']['n']} R {f(p['nb1'])}   nb2 (rth N=1..3) n {p['nb2']['n']} R {f(p['nb2'])}")
    h = p["head"]
    f = lambda x: "-" if x["R"] is None else f"{x['R']:+.4f}"
    extra = ""
    if p.get("distinct_orders"):
        q = p["distinct_orders"]
        extra = f"   distinct orders {q['n']} on {q['days']} days: R " + ("-" if q["R"] is None else f"{q['R']:+.4f}") + f" net {q['net']:+.0f}"
    if p.get("placebo"):
        q = p["placebo"]
        extra = "   placebo " + ("-" if q["win"] is None else f"win {q['win']:.1%} R {q['R']:+.4f} (n {q['n']})")
    return (f"  pick {p['pick']} [{p['type']}] {p['sel']:<22} events {p['events']:>4}  {h['variant']}: n {h['n']:>4} win "
            + ("-" if h["win"] is None else f"{h['win']:.1%}") + f"  R {f(h)}  net {h['net']:+.0f}   {p['nb1']['variant']} R {f(p['nb1'])}"
            f"   {p['nb2']['variant']} R {f(p['nb2'])}{extra}")


# ------------------------------------------------------------------ build / write / show
def build(mid, vp, dt, years=ALL_YEARS):
    return {"MID1_levels": mid_levels_table(mid), "MID1_splits": mid_splits(mid), "VPN1_reaction": reaction(vp),
            "VPN1_stacked": stacked(vp), "VPN1_byN": byn(vp), "VPN1_daytypes_table": daytypes_table(dt),
            "VPN1_vatrend": vatrend(dt, years)}


def json_text(obj):
    return json.dumps(obj, indent=1, default=str)


def write(tabs, d, suffix=""):
    d.mkdir(parents=True, exist_ok=True)
    out = {}
    for k in CSV_TABLES:
        p = d / f"{k}{suffix}.csv"
        p.write_text(csv_text(tabs[k]))
        out[k] = sha(p)
    for k in JSON_TABLES:
        p = d / f"{k}{suffix}.json"
        p.write_text(json_text(tabs[k]))
        out[k] = sha(p)
    return out


_fmt = LT._fmt
MCOLS = ["code", "side", "level_days", "skipped", "watched", "events", f"n_{HEAD}", f"win_{HEAD}", f"R_{HEAD}", f"net_{HEAD}",
         f"win_{ASKED}", f"R_{ASKED}", f"net_{ASKED}", f"R_{NB1}", f"R_{NB2}", f"win_{BHEAD}", f"R_{BHEAD}", "R_brk_p20",
         "rank_R", "rank_win", "rank_R_asked", "rank_R_break"]
SCOLS = ["split", "value", "level_days", "skipped", "watched", "events", f"n_{HEAD}", f"win_{HEAD}", f"R_{HEAD}", f"net_{HEAD}",
         f"win_{ASKED}", f"R_{ASKED}", f"R_{NB1}", f"R_{NB2}", f"win_{BHEAD}", f"R_{BHEAD}", "R_brk_p20", "pl_events",
         f"pl_win_{HEAD}", f"pl_R_{HEAD}", f"dwin_{HEAD}", f"pwin_{HEAD}", f"pl_win_{ASKED}", f"pl_R_{ASKED}"]
RCOLS = ["prof", "level", "side", "watched", "events", f"n_{HEAD}", f"win_{HEAD}", f"R_{HEAD}", f"net_{HEAD}", f"win_{ASKED}",
         f"R_{ASKED}", f"R_{NB1}", f"R_{NB2}", f"win_{BHEAD}", f"R_{BHEAD}", "R_brk_p20", "pl_events", f"pl_win_{HEAD}",
         f"pl_R_{HEAD}", f"dwin_{HEAD}", f"dR_{HEAD}", f"pwin_{HEAD}", f"pl_R_{ASKED}", f"pl_R_{BHEAD}"]
KCOLS = ["kind", "key", "side", "watched", "events", "distinct_orders", "days", f"n_{HEAD}", f"win_{HEAD}", f"R_{HEAD}", f"net_{HEAD}",
         f"win_{ASKED}", f"R_{ASKED}", f"R_{NB1}", f"R_{NB2}", f"win_{BHEAD}", f"R_{BHEAD}", f"net_{BHEAD}", f"R_{BNB1}", f"R_{BNB2}"]
NCOLS = ["stype", "N", "level", "events", f"n_{HEAD}", f"win_{HEAD}", f"R_{HEAD}", f"net_{HEAD}", f"win_{ASKED}", f"R_{ASKED}",
         f"R_{NB1}", f"R_{NB2}", f"win_{BHEAD}", f"R_{BHEAD}", "pl_events", f"pl_win_{HEAD}", f"pl_R_{HEAD}", f"dwin_{HEAD}",
         f"pwin_{HEAD}", f"pl_R_{ASKED}", f"pl_R_{BHEAD}"]
DCOLS = ["family", "type", "direction", "days", "move_mean", "move_median", "hit", "orb_n", "orb_win", "orb_R", "orb_net",
         "orb_agree_n", "orb_agree_win", "orb_agree_R", "orb_agree_net", "orb_disagree_n", "orb_disagree_win",
         "orb_disagree_R", "orb_disagree_net", "va_n", "va_win", "va_R", "va_net"]


def _dfmt(tb):
    f = {}
    for c in DCOLS:
        if c.endswith("win") or c == "hit":
            f[c] = lambda x: "" if x != x else f"{x * 100:.1f}"
        elif c.endswith("_R") or c.startswith("move"):
            f[c] = lambda x: "" if x != x else f"{x:+.3f}"
        elif c.endswith("net"):
            f[c] = lambda x: f"{x:+.0f}"
    return tb[DCOLS].to_string(index=False, formatters=f)


def show(tabs, label, picks=None):
    ml = tabs["MID1_levels"]
    print(f"\n{label}: MID1, every hourly open and the midnight placebo (o00~), sides pooled (win in %; rank = among the 13 "
          f"hourly opens, 1 = highest; headline {HEAD}, asked {ASKED}, break {BHEAD})")
    print(_fmt(ml[ml.side == "all"], MCOLS))
    print(f"\n{label}: MID1 by side")
    print(_fmt(ml[ml.side != "all"], MCOLS[:-4]))
    print(f"\n{label}: MID1, the registered splits of the midnight open (pl_ = its placebos under the same split; dwin in "
          f"points; level_days counted before the skip rule)")
    print(_fmt(tabs["MID1_splits"], SCOLS))
    rt = tabs["VPN1_reaction"]
    a = rt[(rt.set == "all") & (rt[f"n_{HEAD}"] > 0)].copy()
    a["_o"] = np.arange(len(a))
    a = a.sort_values([f"R_{HEAD}", "_o"], ascending=[False, True], kind="mergesort")
    print(f"\n{label}: VPN1 reaction, profile x level x side, all events, sorted by the headline ({HEAD}) mean R: top 15 "
          f"of {len(a)} (cells with >= {MIN_CELL} events: {int((a.events >= MIN_CELL).sum())})")
    print(_fmt(a.head(15), RCOLS))
    print(f"\n{label}: VPN1 reaction, bottom 8")
    print(_fmt(a.tail(8), RCOLS))
    for st in ("crossed", "uncrossed"):
        x = rt[rt.set == st]
        t = {v: (x[f"n_{v}"] * x[f"R_{v}"]).sum() / max(x[f"n_{v}"].sum(), 1) for v in (HEAD, ASKED, BHEAD)}
        w = (x[f"n_{HEAD}"] * x[f"win_{HEAD}"]).sum() / max(x[f"n_{HEAD}"].sum(), 1)
        print(f"{label}: VPN1 all 78 profile-level-sides, {st}: events {int(x.events.sum())}, {HEAD} win {w:.1%} R {t[HEAD]:+.4f}, "
              f"{ASKED} R {t[ASKED]:+.4f}, {BHEAD} R {t[BHEAD]:+.4f}")
    bn = tabs["VPN1_byN"]
    print(f"\n{label}: VPN1 by lookback N (sides pooled; level 'all' = vah + poc + val)")
    print(_fmt(bn[bn.level == "all"], NCOLS))
    print(f"\n{label}: VPN1 by lookback N and level")
    print(_fmt(bn[bn.level != "all"], NCOLS[:14]))
    sk = tabs["VPN1_stacked"]
    print(f"\n{label}: VPN1 stacked-level count (other profiles with a level within 0.03 x ATR) and the aligned POCs")
    print(_fmt(sk, KCOLS))
    print(f"\n{label}: aligned-value day types (study days; move in ATR in the accepted direction; ORB v1.4 and VA-trend, win = net > 0)")
    print(_dfmt(tabs["VPN1_daytypes_table"]))
    va = tabs["VPN1_vatrend"]
    for k, nm in (("base", "VA-trend (rth, N=1..5)"), ("nb1", "neighbour 1 (eth, N=1..5)"), ("nb2", "neighbour 2 (rth, N=1..3)")):
        x = va[k]
        if not x["n"]:
            print(f"{label}: {nm}: no trades")
            continue
        print(f"{label}: {nm}: n {x['n']}  win(net>0) {x['win']:.1%}  R {x['R']:+.4f}  net {x['net']:+.0f}  p {x['p']:.4f}  long n {x['n_long']} R "
              + ("-" if x["R_long"] is None else f"{x['R_long']:+.4f}") + f"  short n {x['n_short']} R "
              + ("-" if x["R_short"] is None else f"{x['R_short']:+.4f}") + "  by year "
              + " ".join(f"{y}:{v['net']:+.0f}({v['n']})" for y, v in x["by_year"].items() if v["n"]))


def _load(d, end=None, start=None):
    mid = pd.read_parquet(d / "MID1_events.parquet")
    vp = pd.read_parquet(d / "VPN1_events.parquet")
    dt = read_daytypes(d / "VPN1_daytypes.csv")
    return mid, vp, dt


def _cut(x, lo=None, hi=None):
    m = pd.Series(True, index=x.index)
    if lo is not None:
        m &= x.date >= lo
    if hi is not None:
        m &= x.date < hi
    return x[m]


# ------------------------------------------------------------------ phases
def phase_is(out=core.OUT, src=None, end=None, quiet=False, years=ALL_YEARS):
    t0 = time.time()
    src = pathlib.Path(src or (core.OUT / "is"))
    mid, vp, dt = _load(src)
    if end is not None:
        mid, vp, dt = (_cut(x, hi=pd.Timestamp(end)) for x in (mid, vp, dt))
    assert max(mid.date.max(), vp.date.max()) < OOS_START, "the in-sample events reach into the out-of-sample window"
    print(f"LEV2 tables   phase is   MID1 events {len(mid)} rows, VPN1 events {len(vp)} rows, day types {len(dt)} rows   "
          f"{vp.date.min().date()} -> {vp.date.max().date()}   study days {vp.date.nunique()}")
    tabs = build(mid, vp, dt, years)
    hashes = write(tabs, out / "is")
    picks, cnt = select(vp, dt, tabs["VPN1_reaction"], tabs["VPN1_stacked"], years)
    po = pooled_all(mid, vp)
    if not quiet:
        show(tabs, "IN SAMPLE")
    mt = mid[mid.is_event & mid.tapped]
    vt = vp[vp.is_event & vp.tapped]
    sel = {"spec": "YT10_SPEC.md", "phase": "is", "first_day": str(vp.date.min().date()), "last_day": str(vp.date.max().date()),
           "study_days": int(vp.date.nunique()),
           "thresholds": {"min_events_cell": MIN_CELL, "n_cell_picks": N_CELLS, "min_events_stack_bucket": MIN_STACK,
                          "min_events_aligned_poc": MIN_APOC, "fade": list(TRIO["fade"]), "break": list(TRIO["break"]),
                          "oos_start": str(OOS_START.date()), "oos_min_events_picks_1_5": OOS_MIN_CELL,
                          "oos_min_events_picks_6_8": OOS_MIN_OTHER, "oos_min_R": MIN_R, "oos_p": P_PICK,
                          "oos_years_positive": "3 of 4", "mid1_p_pass": P_MID_PASS, "mid1_p_candidate": P_MID_CAND},
           "counts": dict(cnt, mid_level_days=int(len(mid)), mid_tapped=int(len(mt)), mid_o00_tapped=int((mt.code == MID).sum()),
                          vp_level_days=int(len(vp)), vp_tapped=int(len(vt)), vp_real_tapped=int(len(real_rows(vt)))),
           "picks": picks, "pooled": po,
           "sha256_events": {k: sha(src / k) for k in ("MID1_events.parquet", "VPN1_events.parquet", "VPN1_daytypes.csv")},
           "sha256_tables": hashes}
    p = out / SEL_NAME
    new = json_text(sel)
    if p.exists() and p.read_text() != new:
        print(f"\nNOTE: {p.name} existed with different content and is rewritten")
    p.write_text(new)
    print(f"\nVPN1 cells (profile x level x side x trade) {cnt['cells']}, with >= {MIN_CELL} events {cnt['cells_eligible']}; "
          f"aligned-POC events: rth {cnt['apoc_events']['apoc_rth']}, eth {cnt['apoc_events']['apoc_eth']}, together "
          f"{cnt['apoc_events']['apoc']} (pick 7 needs {MIN_APOC})")
    print("picks (frozen in " + str(p) + ")")
    for r in picks:
        print(pick_line(r))
    for n in range(1, 9):
        if n not in [r["pick"] for r in picks]:
            print(f"  pick {n}: none (the registered minimum number of in-sample events is not reached)")
    print()
    for line in pooled_lines(po, "IN SAMPLE"):
        print(line)
    print(f"\ntotal {time.time() - t0:.0f}s")
    return tabs, sel


def score_pick(vp_oos, dt_oos, pick, years=OOS_YEARS):
    """The registered out-of-sample test of one frozen pick."""
    out = {"pick": pick["pick"], "type": pick["type"], "sel": pick["sel"]}
    if pick["type"] == "vatrend":
        st = {k: va_stats(dt_oos, w, years) for k, w in (("base", "rth"), ("nb1", "eth"), ("nb2", "rth3"))}
        b = st["base"]
        out.update(events=b["n"], n=b["n"])
        if not b["n"]:
            out["verdict"] = "not enough data"
            return out
        by = {y: v["net"] for y, v in b["by_year"].items()}
        nb = {"eth": st["nb1"].get("R"), "rth N=1..3": st["nb2"].get("R")}
        out.update(R=b["R"], win=b["win"], net=b["net"], p=b["p"], by_year=by,
                   years_positive=int(sum(v > 0 for v in by.values())), neighbours=nb,
                   neighbour_n={"eth": st["nb1"]["n"], "rth N=1..3": st["nb2"]["n"]})
        ch = {"events": b["n"] >= OOS_MIN_OTHER, "R": b["R"] >= MIN_R, "p": b["p"] < P_PICK, "years": out["years_positive"] >= 3,
              "neighbours": all(v is not None and v > 0 for v in nb.values())}
    else:
        trade = pick["trade"]
        h, n1, n2 = TRIO[trade]
        t = pick_rows(vp_oos, pick)
        f = t[t[f"f_{h}"]]
        out.update(trade=trade, events=int(len(t)), n=int(len(f)))
        if len(f) == 0:
            out["verdict"] = "not enough data"
            return out
        R = f[f"R_{h}"].to_numpy(float)
        yr = f.date.dt.year
        by = {int(y): round(float(f[f"pnl_{h}"][yr == y].sum()), 2) for y in years}
        nb = {v: vstats(t, v)[f"R_{v}"] for v in (n1, n2)}
        out.update(R=float(R.mean()), win=float(f[f"win_{h}"].mean()), net=float(f[f"pnl_{h}"].sum()),
                   p=core.boot_p(R, n=10000, seed=1), by_year=by, years_positive=int(sum(v > 0 for v in by.values())),
                   neighbours={k: _num(v) for k, v in nb.items()})
        if pick["type"] != "cell":
            out["distinct_orders"] = distinct(t, h, with_p=True)
        need = OOS_MIN_CELL if pick["type"] == "cell" else OOS_MIN_OTHER
        ch = {"events": len(t) >= need, "R": out["R"] >= MIN_R, "p": out["p"] < P_PICK, "years": out["years_positive"] >= 3,
              "neighbours": all(v == v and v > 0 for v in nb.values())}
        if pick["type"] == "cell":
            ps = vstats(placebo_rows(vp_oos, pick), h)
            out["placebo"] = {"n": int(ps[f"n_{h}"]), "win": _num(ps[f"win_{h}"]), "R": _num(ps[f"R_{h}"])}
            if trade == "fade":                               # the placebo condition is registered for single-level fades
                ch["placebo"] = bool(ps[f"n_{h}"]) and out["win"] > ps[f"win_{h}"]
    out["checks"] = {k: bool(v) for k, v in ch.items()}
    out["verdict"] = "not enough data" if not ch["events"] else "counts" if all(ch.values()) else "does not count"
    return out


def _mid_line(v):
    if v["verdict"] == "not enough data":
        return f"  {v['what']}: events {v['events']}, trades {v['n']} -> not enough data"
    nb = ", ".join(f"{k} " + ("-" if x is None else f"{x:+.4f}") for k, x in v["neighbours"].items())
    pl, bk = v["placebo"], v["break_trade"]
    return (f"  {v['what']}: events {v['events']} n {v['n']}  win {v['win']:.1%}  R {v['R']:+.4f}  net {v['net']:+.0f}  p {v['p']:.5f}  "
            f"years {v['by_year']} ({v['years_positive']} of {v['years_traded']} traded years positive)  halves "
            + ("-" if v["R_h1"] is None else f"{v['R_h1']:+.4f}") + " / " + ("-" if v["R_h2"] is None else f"{v['R_h2']:+.4f}")
            + f"  neighbours {nb}  placebo " + ("-" if not pl["n"] else f"win {pl['win']:.1%} R {pl['R']:+.4f} (n {pl['n']})")
            + f"  | {ASKED} win " + ("-" if not v["asked"]["n"] else f"{v['asked']['win']:.1%} R {v['asked']['R']:+.4f}")
            + "  | break " + ("-" if not bk["n"] else f"win {bk['win']:.1%} R {bk['R']:+.4f} net {bk['net']:+.0f}")
            + f"  -> {v['verdict']}  {v['checks']}")


def phase_full(out=core.OUT, src=None, oos_start=OOS_START, sel_path=None, frozen_dir=None, oos_years=OOS_YEARS,
               all_years=ALL_YEARS, dry=False):
    """Reads VPN1_selected.json and the frozen in-sample tables; selects nothing."""
    t0 = time.time()
    sel = json.loads(pathlib.Path(sel_path or (core.OUT / SEL_NAME)).read_text())       # frozen; never rewritten here
    src = pathlib.Path(src or (core.OUT / "full"))
    for k in ("MID1_events.parquet", "VPN1_events.parquet", "VPN1_daytypes.csv"):
        if not (src / k).exists():
            raise SystemExit(f"{src / k} does not exist: run  python3 tools/yt1/lev2_events.py --phase full  first")
    mid, vp, dt = _load(src)
    oos_start = pd.Timestamp(oos_start)
    if vp.date.max() < oos_start:
        raise SystemExit("no out-of-sample days in these events files: the full phase cannot run here")
    print(f"LEV2 tables   phase full{'  (DRY RUN on a made-up split: the numbers mean nothing)' if dry else ''}   MID1 events "
          f"{len(mid)} rows, VPN1 events {len(vp)} rows   {vp.date.min().date()} -> {vp.date.max().date()}   out of sample from "
          f"{oos_start.date()}")
    fz = pathlib.Path(frozen_dir or (core.OUT / "is"))
    for k, h in sel["sha256_events"].items():
        if (fz / k).exists():
            print(f"frozen in-sample file {k}: sha256 " + ("as stamped in the selection file" if sha(fz / k) == h
                                                           else "DIFFERS from the stamp in the selection file"))
    IS = [_cut(x, hi=oos_start) for x in (mid, vp, dt)]
    OOS = [_cut(x, lo=oos_start) for x in (mid, vp, dt)]
    # ---- the in-sample tables rebuilt from the full files must equal the frozen ones
    t_is = build(*IS, years=all_years)
    same = {}
    for k in CSV_TABLES:
        same[k] = csv_text(t_is[k]) == (fz / f"{k}.csv").read_text()
    for k in JSON_TABLES:
        same[k] = json_text(t_is[k]) == (fz / f"{k}.json").read_text()
    print("in-sample tables rebuilt from these files against the frozen ones: "
          + ", ".join(f"{k} {'identical' if v else 'DIFFERENT'}" for k, v in same.items())
          + ("" if all(same.values()) else "   <-- the frozen tables are NOT reproduced"))
    again, _ = select(IS[1], IS[2], t_is["VPN1_reaction"], t_is["VPN1_stacked"], all_years)
    print("the selection rule applied to the rebuilt in-sample tables gives the frozen picks: "
          f"{[p['sel'] for p in again] == [p['sel'] for p in sel['picks']]} (the frozen file is what is scored)")
    d = out / "full"
    t_oos, t_all = build(*OOS, years=all_years), build(mid, vp, dt, years=all_years)
    write(t_oos, d, "_oos"); write(t_all, d, "_full")
    show(t_oos, "OUT OF SAMPLE")
    show(t_all, "FULL SPAN")
    res = {"oos_start": str(oos_start.date()), "last_day": str(vp.date.max().date()), "is_tables_reproduced": same,
           "p_pick": P_PICK, "p_mid_pass": P_MID_PASS}
    # ---- MID1 verdicts: full span, both sides pooled, headline fade; and the with-bias fade
    print(f"\nMID1 verdicts on the full span (headline {HEAD}, sides pooled): at least 6 of the 8 calendar years net positive, "
          f"mean R >= {MIN_R:+.2f}, both halves (before / from {oos_start.date()}) non-negative, {NB1} and {NB2} positive, win "
          f"rate above the placebo's, bootstrap p < {P_MID_PASS:.6f} to pass, p < {P_MID_CAND} for a candidate")
    res["mid1"] = {"pooled": mid_verdict(mid, None, all_years, oos_start), "with_bias": mid_verdict(mid, "with", all_years, oos_start),
                   "against_bias": mid_verdict(mid, "against", all_years, oos_start), "no_bias": mid_verdict(mid, "none", all_years, oos_start)}
    for k in ("pooled", "with_bias"):
        print(_mid_line(res["mid1"][k]))
    print("  reported beside them (no verdict is registered for these):")
    for k in ("against_bias", "no_bias"):
        print("  " + _mid_line(res["mid1"][k]))
    ml = t_all["MID1_levels"]
    m = ml[(ml.side == "all") & ~ml.is_placebo].set_index("code")
    res["mid1"]["rank_full_span"] = {k: int(m.loc[MID, k]) for k in ("rank_R", "rank_win", "rank_R_asked", "rank_R_break")}
    res["mid1"]["rank_oos"] = {k: int(v) for k, v in t_oos["MID1_levels"][lambda x: (x.side == "all") & (x.code == MID)].iloc[0][
        ["rank_R", "rank_win", "rank_R_asked", "rank_R_break"]].items()}
    print(f"  the midnight open among the 13 hourly opens, full span, sides pooled: rank {res['mid1']['rank_full_span']['rank_R']} by "
          f"{HEAD} mean R, {res['mid1']['rank_full_span']['rank_win']} by {HEAD} win rate, {res['mid1']['rank_full_span']['rank_R_asked']} by "
          f"{ASKED} mean R, {res['mid1']['rank_full_span']['rank_R_break']} by {BHEAD} mean R (out of sample: {res['mid1']['rank_oos']})")
    # ---- the frozen VPN1 picks
    print(f"\nfrozen VPN1 picks out of sample (events >= {OOS_MIN_CELL}, or {OOS_MIN_OTHER} for picks 6-8; headline mean R >= {MIN_R:+.2f}; "
          f"bootstrap p < {P_PICK:.5f}; at least 3 of the calendar years {', '.join(map(str, oos_years))} net positive; both "
          f"neighbours positive; a single-level fade: win rate above its placebo's)")
    res["picks"] = []
    for pk in sel["picks"]:
        v = score_pick(OOS[1], OOS[2], pk, oos_years)
        h = pk["head"]
        v["in_sample"] = {"events": pk["events"], "R": h.get("R"), "win": h.get("win")}
        res["picks"].append(v)
        if v.get("n"):
            nbs = ", ".join(f"{k} " + ("-" if x is None else f"{x:+.4f}") for k, x in v["neighbours"].items())
            pls = "" if "placebo" not in v else ("  placebo " + ("-" if not v["placebo"]["n"] else
                                                               f"win {v['placebo']['win']:.1%} R {v['placebo']['R']:+.4f} (n {v['placebo']['n']})"))
            if v.get("distinct_orders"):
                q = v["distinct_orders"]
                pls += (f"  [each distinct order once: n {q['n']} on {q['days']} days, R " + ("-" if q["R"] is None else f"{q['R']:+.4f}")
                        + f", net {q['net']:+.0f}, p " + ("-" if q.get("p") is None else f"{q['p']:.5f}") + "]")
            print(f"  pick {pk['pick']} [{pk['type']}] {pk['sel']:<22} events {v['events']:>4} n {v['n']:>4}  win {v['win']:.1%}  R {v['R']:+.4f}"
                  f"  net {v['net']:+.0f}  p {v['p']:.5f}  years {v['by_year']} ({v['years_positive']} positive)  neighbours {nbs}{pls}"
                  f"  -> {v['verdict']}  {v['checks']}   [in sample: events {pk['events']}, R "
                  + ("-" if h.get("R") is None else f"{h['R']:+.4f}") + "]")
        else:
            print(f"  pick {pk['pick']} [{pk['type']}] {pk['sel']}: no out-of-sample trades -> {v['verdict']}")
    for n in range(1, 9):
        if n not in [r["pick"] for r in sel["picks"]]:
            print(f"  pick {n}: none was made in sample")
    # ---- do the same cells stay on top?
    c_is, c_oos, c_all = cells(t_is["VPN1_reaction"]), cells(t_oos["VPN1_reaction"]), cells(t_all["VPN1_reaction"])
    key = ["prof", "level", "side", "trade"]
    j = c_is[key + ["events", "R"]].merge(c_oos[key + ["events", "R"]], on=key, suffixes=("_is", "_oos"))
    j1 = j[(j.events_is >= MIN_CELL) & j.R_oos.notna()]
    j2 = j1[j1.events_oos >= OOS_MIN_CELL]
    res["rank"] = {}
    for nm, jj, txt in (("cells", j1, f"the {len(j1)} cells with >= {MIN_CELL} in-sample events"),
                        ("cells_oos100", j2, f"the {len(j2)} of them with >= {OOS_MIN_CELL} out-of-sample events"),
                        ("fade_cells", j1[j1.trade == "fade"], "the fade cells among them"),
                        ("break_cells", j1[j1.trade == "break"], "the break cells among them")):
        rho = spearman(jj.R_is, jj.R_oos)
        res["rank"][nm] = {"cells": int(len(jj)), "spearman": _num(rho)}
        print(("\n" if nm == "cells" else "") + f"rank correlation (Spearman) of the cells' headline mean R, in sample against out of "
              f"sample, over {txt}: " + ("n/a" if rho != rho else f"{rho:+.3f}") + f" ({len(jj)} cells)")
    if len(j1):
        print(j1.to_string(index=False, formatters={"R_is": "{:+.4f}".format, "R_oos": "{:+.4f}".format}))
    # ---- longer lookbacks against shorter ones, both periods
    print("\nmean R by lookback N, in sample and out of sample (level 'all', sides pooled)")
    a, b = t_is["VPN1_byN"], t_oos["VPN1_byN"]
    nn = a[a.level == "all"][["stype", "N", "events", f"win_{HEAD}", f"R_{HEAD}", f"R_{ASKED}", f"R_{BHEAD}", f"pl_R_{HEAD}"]].merge(
        b[b.level == "all"][["stype", "N", "events", f"win_{HEAD}", f"R_{HEAD}", f"R_{ASKED}", f"R_{BHEAD}", f"pl_R_{HEAD}"]],
        on=["stype", "N"], suffixes=("_is", "_oos"))
    print(nn.to_string(index=False, float_format=lambda x: f"{x:+.4f}"))
    res["byN"] = json.loads(nn.to_json(orient="records"))
    # ---- real against placebo, pooled
    po_is, po_oos, po_all = pooled_all(IS[0], IS[1]), pooled_all(OOS[0], OOS[1]), pooled_all(mid, vp)
    res["pooled"] = {"is": po_is, "oos": po_oos, "full": po_all}
    print()
    for line in pooled_lines(po_is, "IN SAMPLE    ") + pooled_lines(po_oos, "OUT OF SAMPLE") + pooled_lines(po_all, "FULL SPAN    "):
        print(line)
    # ---- hindsight
    top = c_all.sort_values("net", ascending=False, kind="mergesort").head(10)
    res["hindsight_top10"] = json.loads(top.to_json(orient="records"))
    print("\nHINDSIGHT (chosen with the whole span in view; not a test): the 10 cells with the largest full-span net $ of "
          "their headline trade")
    print(top[key + ["events", "n", "win", "R", "net", "R_nb1", "R_nb2", "pl_win", "pl_R"]].to_string(
        index=False, formatters={"win": lambda x: f"{x * 100:.1f}", "pl_win": lambda x: "" if x != x else f"{x * 100:.1f}",
                                 "R": "{:+.4f}".format, "R_nb1": "{:+.4f}".format, "R_nb2": "{:+.4f}".format,
                                 "pl_R": lambda x: "" if x != x else f"{x:+.4f}", "net": "{:+.0f}".format}))
    d.mkdir(parents=True, exist_ok=True)
    (d / "LEV2_oos.json").write_text(json_text(res))
    print(f"\ntotal {time.time() - t0:.0f}s")
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", choices=["is", "full"], required=True)
    ap.add_argument("--dry-split", help="code test only: a made-up split date inside the in-sample files")
    ap.add_argument("--dry-out", help="code test only: directory for the dry run's files")
    a = ap.parse_args()
    pd.set_option("display.width", 400)
    pd.set_option("display.max_rows", 500)
    pd.set_option("display.max_columns", 80)
    if a.dry_split:
        assert a.dry_out, "--dry-split needs --dry-out (the real output directories are never written by a dry run)"
        o = pathlib.Path(a.dry_out).resolve()
        assert core.OUT.resolve() not in o.parents and o != core.OUT.resolve(), "a dry run may not write into the study folder"
        split = pd.Timestamp(a.dry_split)
        yrs = tuple(range(2019, 2023))
        if a.phase == "is":
            phase_is(out=o, end=split, quiet=True, years=yrs)
        else:
            phase_full(out=o, src=core.OUT / "is", oos_start=split, sel_path=o / SEL_NAME, frozen_dir=o / "is",
                       oos_years=tuple(range(split.year, 2023)), all_years=yrs, dry=True)
    elif a.phase == "is":
        phase_is()
    else:
        phase_full()


if __name__ == "__main__":
    main()
