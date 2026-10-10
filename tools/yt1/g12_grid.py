#!/usr/bin/env python3
"""G12 grid - the 756 combinations of YT11_SPEC.md, Part 3, evaluated on the trades of g12_sim.py.

    python3 tools/yt1/g12_grid.py --phase is     bars to 2022-12-31 only (asserted): the grid, the registered
                                                 selection (G12_selected.json) and the in-sample tables
    python3 tools/yt1/g12_grid.py --phase full   every bar: out-of-sample scoring of the FROZEN picks (it never
                                                 selects: it stops if G12_selected.json is missing)

    evaluate(P, start, end)   one row per combination on the cash dates start..end, and the daily net matrix
    select(table)             three tiers by trades a day; pick 1 = highest t, pick 2 = largest net $ a day unless
                              it is pick 1 or pick 1's mirror
    pick_test(...)            the spec's "A pick passes" and "Beats ORB v1.4"
    reality_check(X)          White's reality check on a days x combinations matrix of net $ a day

Columns of a grid row (name = <G>.z<Z>.k<K>.<E>):
    n          trades                         orders   decisions at which the signal says trade (lim: limits placed)
    sessions   traded days with at least one decision of that holding time (the days it could trade)
    days       days with at least one trade   tpd      n / sessions
    gross, net totals in $                    gross_pt, net_pt   $ per trade      gross_pts  points per trade
    net_day    net / sessions                 win      % of trades with net > 0
    t          mean / standard error of the daily sum of gross P&L in units of 0.1 x ATR, over the sessions
               (a session without a trade counts 0; standard deviation with D - 1)
    dd         maximum drawdown in $ of the daily net over the sessions (<= 0)
    y<year>    net $ of the calendar year
"""
import argparse, hashlib, json, math, pathlib, sys, time
import numpy as np
import pandas as pd
sys.path.insert(0, str(pathlib.Path(__file__).parent))
import core
import g12_sim as gs

OOS_START = pd.Timestamp("2023-01-01")
OOS_YEARS = (2023, 2024, 2025, 2026)
TIERS = (("A", 100.0, math.inf), ("B", 30.0, 100.0), ("C", 10.0, 30.0))      # by trades a day: lo <= tpd < hi
P_PASS = 0.05 / 6
ADJ_Z = {0: (1,), 1: (0, 2), 2: (1,)}
COST_PTS = gs.COST["mkt"] / gs.PV                                             # 1.5 points
TICK_USD = gs.TICK * gs.PV                                                    # $0.50
SEL_PATH = core.OUT / "G12_selected.json"
HERE = pathlib.Path(__file__).parent


# ------------------------------------------------------------------ evaluation
class Daily:
    """rows = the rows of ctx.days that are sessions of the period (for any holding time), in date order;
    net[r, j] = net $ of combination j on that day (0 without a trade); sess[k] = positions into rows of the
    sessions of holding time k; day = their cash dates; names = the combinations (grid order)."""
    __slots__ = ("rows", "day", "net", "sess", "names")

    def series(self, nm):
        """The daily net of one combination over the sessions on which it could trade (days with a decision)."""
        s = self.sess[gs.parse(nm)["K"]]
        return pd.Series(self.net[s, self.names.index(nm)], index=pd.DatetimeIndex(self.day[s]))


def evaluate(P, start=None, end=None):
    """(table, Daily) on the cash dates start..end (inclusive; None = open). The table is indexed by name in
    combos() order."""
    D = P.ctx.days
    nd = len(D)
    inp = np.ones(nd, bool)
    if start is not None:
        inp &= np.asarray(D.index >= pd.Timestamp(start))
    if end is not None:
        inp &= np.asarray(D.index <= pd.Timestamp(end))
    all_ = gs.combos()
    names = [gs.name(c) for c in all_]
    assert len(all_) == gs.N_GRID and len(set(names)) == gs.N_GRID
    col = {nm: j for j, nm in enumerate(names)}
    G = len(all_)
    sess = {}
    for k in gs.KS:
        r = gs.sessions(P, k)
        sess[k] = r[inp[r]]
    union = np.unique(np.concatenate([sess[k] for k in gs.KS])) if nd else np.zeros(0, np.int64)
    yrs = sorted(set(int(y) for y in P.year[union]))
    y0 = yrs[0] if yrs else 0
    rowpos = np.full(nd, -1, np.int64)
    rowpos[union] = np.arange(len(union))
    net_m = np.zeros((len(union), G))
    n_, orders, sessions, days = (np.zeros(G, np.int64) for _ in range(4))
    gross, net, dd = np.zeros(G), np.zeros(G), np.zeros(G)
    gross_pt, net_pt, net_day, tt, win, tpd = (np.full(G, np.nan) for _ in range(6))
    by = np.zeros((G, len(yrs)))
    for g in gs.GS:
        for k in gs.KS:
            cell = P.cell(g, k)
            d = cell.dec.d
            pm = inp[d]
            srow = sess[k]
            S = len(srow)
            for z in gs.ZS:
                mo = gs.mask(cell, z, "ord") & pm
                for e in gs.ES_:
                    j = col[gs.name(dict(G=g, Z=z, K=k, E=e))]
                    m = (mo & cell.fill) if e == "lim" else mo
                    dm = d[m]
                    gr = cell.gross[m]
                    nt = gs.net_of(gr, e)
                    n = len(gr)
                    n_[j], orders[j], sessions[j] = n, int(mo.sum()), S
                    gross[j], net[j] = gr.sum(), nt.sum()
                    if S:
                        tpd[j] = n / S
                        net_day[j] = net[j] / S
                        dn = np.bincount(dm, weights=nt, minlength=nd)[srow]
                        net_m[rowpos[srow], j] = dn
                        dd[j] = core.max_dd(dn)
                        if n and S > 1:
                            du = np.bincount(dm, weights=gr / P.unit[dm], minlength=nd)[srow]
                            sd = du.std(ddof=1)
                            if sd > 0:
                                tt[j] = du.mean() / (sd / math.sqrt(S))
                    if n:
                        gross_pt[j], net_pt[j] = gross[j] / n, net[j] / n
                        win[j] = (nt > 0).mean() * 100
                        days[j] = len(np.unique(dm))
                        by[j] = np.bincount(P.year[dm] - y0, weights=nt, minlength=len(yrs))
    tb = pd.DataFrame({k: [c[k] for c in all_] for k in gs.ORDER})
    tb.insert(0, "name", names)
    tb["n"], tb["orders"], tb["sessions"], tb["days"], tb["tpd"] = n_, orders, sessions, days, tpd
    tb["gross"], tb["net"] = np.round(gross, 2), np.round(net, 2)
    tb["gross_pt"], tb["gross_pts"], tb["net_pt"], tb["net_day"] = gross_pt, gross_pt / gs.PV, net_pt, net_day
    tb["t"], tb["win"], tb["dd"] = tt, win, np.round(dd, 2)
    for q, yr in enumerate(yrs):
        tb[f"y{yr}"] = np.round(by[:, q], 2)
    dl = Daily()
    dl.rows, dl.day, dl.net, dl.names = union, P.day[union].astype("datetime64[ns]"), net_m, names
    dl.sess = {k: rowpos[sess[k]] for k in gs.KS}
    return tb.set_index("name"), dl


def write_grid(table, stem):
    p = pathlib.Path(str(stem) + ".csv")
    table.to_csv(p)
    return p


def read_grid(stem):
    return pd.read_csv(pathlib.Path(str(stem) + ".csv"), index_col="name", dtype={"G": str, "E": str})


def _sha(p):
    return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()


# ------------------------------------------------------------------ selection
def tier_of(tpd):
    if tpd == tpd:
        for nm, lo, hi in TIERS:
            if lo <= tpd < hi:
                return nm
    return ""


def tiers(table):
    return table.tpd.map(tier_of)


def _years(row):
    return {k[1:]: round(float(row[k]), 2) for k in row.index if k[:1] == "y" and k[1:].isdigit()}


def _f(x):
    return None if x is None or x != x else float(x)


def _record(row):
    return {"name": row.name, "combo": {"G": str(row.G), "Z": int(row.Z), "K": int(row.K), "E": str(row.E)},
            "n": int(row.n), "orders": int(row.orders), "sessions": int(row.sessions), "days": int(row.days),
            "tpd": _f(row.tpd), "gross": round(float(row.gross), 2), "net": round(float(row.net), 2),
            "gross_pt": _f(row.gross_pt), "gross_pts": _f(row.gross_pts), "net_pt": _f(row.net_pt),
            "net_day": _f(row.net_day), "t": _f(row.t), "win": _f(row.win), "dd": round(float(row.dd), 2),
            "by_year": _years(row)}


def select(table):
    """The registered selection. In each tier (by trades a day): pick 1 = the highest t; pick 2 = the tier's
    largest net $ a day, taken only if it is neither pick 1 nor pick 1's mirror (otherwise the tier has one pick).
    Ties: the grid's order. No sign condition: the spec states none."""
    tr = tiers(table)
    out = {"tiers": {}, "picks": []}
    for nm, lo, hi in TIERS:
        sub = table[(tr == nm).to_numpy()]
        info = {"trades_a_day": [lo, None if math.isinf(hi) else hi], "n": int(len(sub)),
                "n_mkt": int((sub.E == "mkt").sum()), "n_lim": int((sub.E == "lim").sum()),
                "n_gross_positive": int((sub.gross_pt > 0).sum()), "n_net_positive": int((sub.net_pt > 0).sum())}
        p1 = None
        if len(sub):
            by_t = sub.sort_values("t", ascending=False, kind="mergesort", na_position="last")
            if by_t.t.iloc[0] == by_t.t.iloc[0]:
                p1 = by_t.iloc[0]
                r = _record(p1)
                r.update(tier=nm, pick=1, id=f"{nm}1", how="highest t", mirror=gs.mirror(p1.name))
                out["picks"].append(r)
            top = sub.sort_values("net_day", ascending=False, kind="mergesort", na_position="last").iloc[0]
            r = _record(top)
            if p1 is not None and top.name == p1.name:
                r["status"] = "it is pick 1: the tier has no pick 2"
            elif p1 is not None and top.name == gs.mirror(p1.name):
                r["status"] = "it is pick 1's mirror: the tier has no pick 2"
            else:
                r["status"] = "pick 2"
                r2 = dict(r)
                r2.update(tier=nm, pick=2, id=f"{nm}2", how="largest net $ a day", mirror=gs.mirror(top.name))
                del r2["status"]
                out["picks"].append(r2)
            info["largest_net_day"] = r
        out["tiers"][nm] = info
    out["n_outside_tiers"] = int((tr == "").sum())
    return out


# ------------------------------------------------------------------ the reported tables
def gross_by_signal(table):
    """Gross points per trade of every signal at z >= 0, mkt, by holding time, next to the 1.5-point cost."""
    t = table[(table.Z == 0) & (table.E == "mkt")]
    p = t.pivot(index="G", columns="K", values="gross_pts").reindex(index=list(gs.GS), columns=list(gs.KS))
    p.columns = [f"k{k}" for k in p.columns]
    p["cost_pts"] = COST_PTS
    return p


def shares(table):
    n = len(table)
    out = {"n_grid": int(n), "with_a_trade": int((table.n > 0).sum()),
           "gross_positive": int((table.gross_pt > 0).sum()), "net_positive": int((table.net_pt > 0).sum())}
    out["share_gross_positive"], out["share_net_positive"] = out["gross_positive"] / n, out["net_positive"] / n
    for e in gs.ES_:
        s = table[table.E == e]
        out[e] = {"n": int(len(s)), "gross_positive": int((s.gross_pt > 0).sum()),
                  "net_positive": int((s.net_pt > 0).sum())}
    return out


def lim_table(table):
    """For every signal x strength x holding time: limits placed (= the mkt combination's trades), filled, the
    share filled, and the gross points per filled trade next to the gross points per trade of the same signal
    entered at the market."""
    key = ["G", "Z", "K"]
    m = table[table.E == "mkt"].reset_index().set_index(key)
    l = table[table.E == "lim"].reset_index().set_index(key).reindex(m.index)
    out = pd.DataFrame({"orders": l.orders, "filled": l.n, "mkt_n": m.n, "lim_gross_pts": l.gross_pts,
                        "mkt_gross_pts": m.gross_pts, "lim_net_pt": l.net_pt, "mkt_net_pt": m.net_pt})
    with np.errstate(divide="ignore", invalid="ignore"):
        out.insert(2, "fill_share", np.where(out.orders > 0, out.filled / out.orders.where(out.orders > 0), np.nan))
    out["lim_minus_mkt_pts"] = out.lim_gross_pts - out.mkt_gross_pts
    return out.reset_index()


def lim_pivots(lt):
    z0 = lt[lt.Z == 0]
    fill = z0.pivot(index="G", columns="K", values="fill_share").reindex(index=list(gs.GS), columns=list(gs.KS))
    diff = z0.pivot(index="G", columns="K", values="lim_gross_pts").reindex(index=list(gs.GS), columns=list(gs.KS))
    return fill, diff


def lim_by_z(lt):
    rows = []
    for z in gs.ZS:
        x = lt[lt.Z == z]
        o, f = x.orders.sum(), x.filled.sum()
        rows.append({"Z": z, "orders": int(o), "filled": int(f), "fill_share": f / o if o else np.nan,
                     "lim_gross_pts_per_filled": (x.lim_gross_pts * x.filled).sum() / f if f else np.nan})
    return pd.DataFrame(rows)


FMT = {"n": "{:.0f}".format, "orders": "{:.0f}".format, "sessions": "{:.0f}".format, "tpd": "{:.1f}".format,
       "gross_pt": "{:+.3f}".format, "gross_pts": "{:+.4f}".format, "net_pt": "{:+.3f}".format,
       "net_day": "{:+.1f}".format, "net": "{:+.0f}".format, "t": "{:+.2f}".format, "win": "{:.1f}".format,
       "dd": "{:.0f}".format}


def _show(tb, cols=("n", "tpd", "gross_pt", "gross_pts", "net_pt", "net_day", "net", "t", "win", "dd")):
    if not len(tb):
        return "  (none)"
    return tb[list(cols)].to_string(formatters={k: v for k, v in FMT.items() if k in cols})


def _pick_line(r):
    yr = " ".join(f"{y}:{v:+.0f}" for y, v in r["by_year"].items())
    return (f"  {r['id']}  {r['name']:<20} n {r['n']:>6}  a day {r['tpd']:>6.1f}  gross $/trade {r['gross_pt']:+.3f}"
            f" ({r['gross_pts']:+.4f} pts)  net $/trade {r['net_pt']:+.3f}  net $/day {r['net_day']:+.1f}"
            f"  t {r['t']:+.2f}  win {r['win']:.1f}  dd {r['dd']:.0f}  [{r['how']}]  | {yr}")


def _print_tables(tables, lt, label):
    """tables = {period label: grid}; lt = the lim table of the last period."""
    for lab, tb in tables.items():
        print(f"\ngross points per trade, z >= 0, mkt, by signal and holding time ({lab}); the cost is {COST_PTS} points")
        print(gross_by_signal(tb).to_string(float_format=lambda v: f"{v:+.3f}"))
    for lab, tb in tables.items():
        s = shares(tb)
        print(f"\n{lab}: of the {s['n_grid']} combinations {s['with_a_trade']} have a trade;"
              f" gross per trade positive {s['gross_positive']} ({s['share_gross_positive']:.1%});"
              f" net per trade positive {s['net_positive']} ({s['share_net_positive']:.1%})"
              f"   [mkt: gross {s['mkt']['gross_positive']} net {s['mkt']['net_positive']} of {s['mkt']['n']};"
              f" lim: gross {s['lim']['gross_positive']} net {s['lim']['net_positive']} of {s['lim']['n']}]")
    fill, lg = lim_pivots(lt)
    print(f"\nlim entries ({label}), z >= 0: share of limits filled, by signal and holding time")
    print(fill.to_string(float_format=lambda v: f"{v:.3f}"))
    print(f"lim entries ({label}), z >= 0: gross points per FILLED trade (the same signal's mkt trade is in the table above)")
    print(lg.to_string(float_format=lambda v: f"{v:+.3f}"))
    print(f"lim entries ({label}), every signal and holding time pooled, by strength (every signal is pooled with its"
          f" mirror, so the same orders at the market gross exactly 0: this is what the fill rule alone selects):")
    print(lim_by_z(lt).to_string(index=False, float_format=lambda v: f"{v:.4f}"))


# ------------------------------------------------------------------ phase is
def phase_is(out=core.OUT):
    import run
    t00 = time.time()
    ctx = core.Ctx(run.bars("is"))
    assert ctx.ts[-1] < core.IS_END, "in-sample bars reach into the out-of-sample window"
    P = gs.prep(ctx)
    assert ctx.extra("ES").index.max() < core.IS_END
    D = ctx.days
    assert D.index.max() < OOS_START
    table, dl = evaluate(P)
    d = out / "is"
    d.mkdir(parents=True, exist_ok=True)
    gp = write_grid(table, d / "G12_grid")
    print(f"G12 grid   phase is   bars {ctx.ts[0]} -> {ctx.ts[-1]}   cash days {len(D)}   traded days"
          f" {int(P.traded.sum())} ({D.index[P.traded].min().date()} -> {D.index[P.traded].max().date()})")
    print("holding time: sessions, decisions a day: " + "   ".join(
        f"k{k}: {len(dl.sess[k])}, {len(P.decisions(k).i) / max(len(dl.sess[k]), 1):.1f}" for k in gs.KS))
    tr = tiers(table)
    print(f"\ncombinations {len(table)}   with a trade {(table.n > 0).sum()}   tiers by trades a day: "
          + "   ".join(f"{nm} ({lo:.0f}{'+' if math.isinf(hi) else f' to under {hi:.0f}'}): {(tr == nm).sum()}"
                       for nm, lo, hi in TIERS) + f"   under 10 a day: {(tr == '').sum()}")
    for nm, _, _ in TIERS:
        sub = table[(tr == nm).to_numpy()]
        print(f"\ntier {nm}: {len(sub)} combinations ({(sub.E == 'mkt').sum()} mkt, {(sub.E == 'lim').sum()} lim);"
              f" gross per trade positive {(sub.gross_pt > 0).sum()}, net per trade positive {(sub.net_pt > 0).sum()}")
        print(" top 5 by t"); print(_show(sub.sort_values("t", ascending=False, kind="mergesort", na_position="last").head(5)))
        print(" top 5 by net $ a day"); print(_show(sub.sort_values("net_day", ascending=False, kind="mergesort").head(5)))
    sel = select(table)
    sel.update({"spec": "YT11_SPEC.md Part 3 (G12)", "phase": "is", "first_bar": str(ctx.ts[0]),
                "last_bar": str(ctx.ts[-1]), "first_day": str(D.index[P.traded].min().date()),
                "last_day": str(D.index[P.traded].max().date()), "n_traded_days": int(P.traded.sum()),
                "n_grid": int(len(table)), "shares": shares(table), "grid_file": gp.name, "sha256_grid": _sha(gp),
                "sha256_g12_sim": _sha(HERE / "g12_sim.py"), "sha256_g12_grid": _sha(HERE / "g12_grid.py")})
    p = out / "G12_selected.json"
    new = json.dumps(sel, indent=1)
    if p.exists() and p.read_text() != new:
        try:
            was = [r["name"] for r in json.loads(p.read_text())["picks"]]
        except Exception:
            was = None
        now = [r["name"] for r in sel["picks"]]
        print(f"\nNOTE: {p.name} existed with different content and is rewritten; the picks are "
              + ("the same as before" if was == now else f"DIFFERENT: before {was}"))
    p.write_text(new)
    print("\nthe registered selection (pick 1 = highest t of the daily gross in 0.1 x ATR; pick 2 = largest net $ a day"
          " unless it is pick 1 or pick 1's mirror)")
    for r in sel["picks"]:
        print(_pick_line(r))
    for nm, _, _ in TIERS:
        r = sel["tiers"][nm].get("largest_net_day")
        if r is None:
            print(f"  tier {nm}: no combination")
        elif r["status"] != "pick 2":
            print(f"  tier {nm}: the largest net $ a day is {r['name']} ({r['net_day']:+.1f}): {r['status']}")
    frames = []
    for r in sel["picks"]:
        df = gs.trades(P, r["name"])
        assert len(df) == r["n"] and abs(df.net.sum() - r["net"]) < 0.005
        df.insert(0, "pick", r["id"]); df.insert(1, "name", r["name"])
        frames.append(df)
    if frames:
        pd.concat(frames, ignore_index=True).to_parquet(d / "G12_pick_trades.parquet", index=False)
    gross_by_signal(table).to_csv(d / "G12_gross_by_signal.csv")
    lt = lim_table(table)
    lt.to_csv(d / "G12_lim.csv", index=False)
    (d / "G12_shares.json").write_text(json.dumps(shares(table), indent=1))
    _print_tables({"in sample": table}, lt, "in sample")
    print(f"\nwrote {gp}, {p}, is/G12_gross_by_signal.csv, is/G12_lim.csv, is/G12_shares.json, is/G12_pick_trades.parquet"
          f"   total {time.time() - t00:.0f}s")
    return table, sel


# ------------------------------------------------------------------ phase full
def orb_trades(ctx, start=None, end=None):
    """ORB v1.4 from cal_orb through the harness; trades whose cash day (entry date) is in [start, end]."""
    import cal_orb
    df = core.trades_df(core.run_orders(ctx, cal_orb.orders(ctx), skip_roll=False))
    df["day"] = pd.DatetimeIndex(df.entry_time).tz_localize(None).normalize() if len(df) else pd.Series(dtype="datetime64[ns]")
    if start is not None:
        df = df[df.day >= pd.Timestamp(start)]
    if end is not None:
        df = df[df.day <= pd.Timestamp(end)]
    return df.sort_values("entry_time").reset_index(drop=True)


def _net_dd(net, dd):
    if dd < 0:
        return net / -dd
    return math.inf if net > 0 else None


def daily_stats(daily, years):
    """Of a daily net series (index = cash dates): days, net, mean a day, max drawdown, net / max drawdown,
    net by calendar year."""
    x = daily.to_numpy(float)
    out = {"days": int(len(x)), "net": round(float(x.sum()), 2)}
    if not len(x):
        out.update(mean_day=None, dd=0.0, net_dd=None, by_year={int(y): 0.0 for y in years}, years_positive=0)
        return out
    yr = pd.DatetimeIndex(daily.index).year
    by = {int(y): round(float(x[yr == y].sum()), 2) for y in years}
    dd = core.max_dd(x)
    out.update(mean_day=float(x.mean()), dd=round(dd, 2), net_dd=_net_dd(float(x.sum()), dd), by_year=by,
               years_positive=int(sum(v > 0 for v in by.values())))
    return out


def neighbours(nm):
    """The next holding time down and up where they exist, and every adjacent strength level (z 1 has two); the
    same signal and entry."""
    c = gs.parse(nm)
    q = gs.KS.index(c["K"])
    out = [gs.name(dict(c, K=gs.KS[j])) for j in (q - 1, q + 1) if 0 <= j < len(gs.KS)]
    out += [gs.name(dict(c, Z=z)) for z in ADJ_Z[c["Z"]]]
    return out


def pick_test(nm, t_oos, dl, orb, years=OOS_YEARS):
    """The registered out-of-sample test of one frozen pick."""
    daily = dl.series(nm)
    out = daily_stats(daily, years)
    row = t_oos.loc[nm]
    out.update(n=int(row.n), tpd=_f(row.tpd), gross_pt=_f(row.gross_pt), gross_pts=_f(row.gross_pts),
               net_pt=_f(row.net_pt), net_day=_f(row.net_day), t=_f(row.t), win=_f(row.win))
    out["p"] = core.boot_p(daily.to_numpy(float), n=10000, seed=1)
    out["p_pass"] = P_PASS
    out["neighbours"] = [{"name": x, "n": int(t_oos.loc[x].n), "net": round(float(t_oos.loc[x].net), 2)}
                         for x in neighbours(nm)]
    ch = {"mean_net_day_positive": bool(out["mean_day"] is not None and out["mean_day"] > 0),
          "p": bool(out["p"] < P_PASS), "years": bool(out["years_positive"] >= 3),
          "neighbours": bool(all(x["net"] > 0 for x in out["neighbours"]))}
    out["checks"] = ch
    out["passes"] = bool(all(ch.values()))
    b = {"passes": out["passes"], "net_above_orb": bool(out["net"] > orb["net"]),
         "net_dd_above_orb": bool(out["net_dd"] is not None and orb["net_dd"] is not None
                                  and out["net_dd"] > orb["net_dd"])}
    out["beats_orb_checks"] = b
    out["beats_orb"] = bool(all(b.values()))
    return out


def _t_days(mean, ss, D):
    var = (ss - D * mean ** 2) / (D - 1)
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(var > 0, math.sqrt(D) * mean / np.sqrt(np.where(var > 0, var, 1.0)), np.nan)


def reality_check(X, names, n_boot=2000, seed=1):
    """White's reality check on X[d, j] = net $ of combination j on day d (0 without a trade), as YT5 defines it
    for this registry: each series is centred on its own mean, the D days are resampled with replacement n_boot
    times (the same days for every combination; rng.integers(0, D, D) per resample, numpy default_rng(seed)), and
    the largest day-level t across the grid (sqrt(D) x mean / sd, sd with D - 1, the resample's own sd) is recorded
    each time; p = the share of resamples whose largest t is at least the observed largest t.
    Also given from the same resamples: White's original statistic, the largest mean net $ a day (not divided by
    its standard deviation). A combination without a trade (a constant series) is left out of the largest t."""
    D, M = X.shape if X.ndim == 2 else (0, 0)
    if D < 2 or M == 0:
        return {"n_combinations": int(M), "n_days": int(D), "p": None, "p_mean": None}
    X = np.asarray(X, np.float64)
    mean = X.mean(axis=0)
    t_obs = _t_days(mean, (X ** 2).sum(axis=0), D)
    if np.isnan(t_obs).all():
        return {"n_combinations": int(M), "n_days": int(D), "p": None, "p_mean": None}
    rng = np.random.default_rng(seed)
    W = np.zeros((n_boot, D))
    for b in range(n_boot):
        W[b] = np.bincount(rng.integers(0, D, size=D), minlength=D)
    xc = X - mean
    mb = (W @ xc) / D
    tb = _t_days(mb, W @ (xc * xc), D)
    mx_t = np.nanmax(np.where(np.isnan(tb), -np.inf, tb), axis=1)
    mx_m = mb.max(axis=1)
    j, jm = int(np.nanargmax(t_obs)), int(np.argmax(mean))
    q = lambda v: {f"q{k}": float(np.quantile(v, k / 100)) for k in (50, 90, 95, 99)}
    return {"n_combinations": int(M), "n_with_a_trade": int((~np.isnan(t_obs)).sum()), "n_days": int(D),
            "n_boot": int(n_boot), "seed": int(seed),
            "t_obs_max": float(t_obs[j]), "t_obs_max_name": names[j], "boot_max_t": q(mx_t),
            "p": float((mx_t >= t_obs[j]).mean()),
            "mean_obs_max": float(mean[jm]), "mean_obs_max_name": names[jm], "boot_max_mean": q(mx_m),
            "p_mean": float((mx_m >= mean[jm]).mean())}


def spearman(a, b):
    """Spearman rank correlation of two aligned series over the rows where both exist (average ranks)."""
    m = a.notna() & b.notna()
    if m.sum() < 3:
        return float("nan"), int(m.sum())
    ra, rb = a[m].rank().to_numpy(), b[m].rank().to_numpy()
    if ra.std() == 0 or rb.std() == 0:
        return float("nan"), int(m.sum())
    return float(np.corrcoef(ra, rb)[0, 1]), int(m.sum())


def break_even(t_oos):
    """For the best gross-per-trade combination of each tier (tiers by this period's trades a day): the round-trip
    cost in ticks at which it would break even = its gross per trade in ticks ($0.50 a tick)."""
    tr = tiers(t_oos)
    out = []
    for nm, lo, hi in TIERS:
        sub = t_oos[(tr == nm).to_numpy() & (t_oos.n > 0).to_numpy()]
        if not len(sub):
            out.append({"tier": nm, "name": None})
            continue
        r = sub.sort_values("gross_pt", ascending=False, kind="mergesort").iloc[0]
        out.append({"tier": nm, "name": r.name, "n": int(r.n), "tpd": float(r.tpd), "gross_pt": float(r.gross_pt),
                    "gross_pts": float(r.gross_pts), "break_even_ticks": float(r.gross_pt / TICK_USD),
                    "house_cost_ticks": float(gs.COST[r.E] / TICK_USD), "net_pt": float(r.net_pt),
                    "net_day": float(r.net_day), "combinations_in_tier": int(len(sub))})
    return out


def _fmt(x, f="{:+.2f}"):
    return "n/a" if x is None or x != x else f.format(x)


def phase_full(out=core.OUT, oos_start=OOS_START, sel_path=None, bars_phase="full", dry=False, frozen_dir=None):
    """Scores the frozen picks out of sample. Reads G12_selected.json and the frozen in-sample grid; selects nothing."""
    import run
    t00 = time.time()
    sel_path = pathlib.Path(sel_path or SEL_PATH)
    if not sel_path.exists():
        raise SystemExit(f"{sel_path} is missing: the full phase never selects. Run  python3 tools/yt1/g12_grid.py"
                         f" --phase is  first (on bars to 2022-12-31) and freeze its output.")
    sel = json.loads(sel_path.read_text())                                  # frozen; never rewritten here
    frozen = read_grid(pathlib.Path(frozen_dir or (core.OUT / "is")) / "G12_grid")
    ctx = core.Ctx(run.bars(bars_phase))
    P = gs.prep(ctx)
    D = ctx.days
    oos_start = pd.Timestamp(oos_start)
    is_end = oos_start - pd.Timedelta(days=1)
    last = D.index[P.traded].max()
    years = OOS_YEARS if not dry else tuple(range(oos_start.year, last.year + 1))
    print(f"G12 grid   phase full{'  (DRY RUN on a made-up split: the numbers mean nothing)' if dry else ''}"
          f"   bars {ctx.ts[0]} -> {ctx.ts[-1]}   traded days {int(P.traded.sum())}   out of sample from {oos_start.date()}")
    for k, f in (("sha256_g12_sim", "g12_sim.py"), ("sha256_g12_grid", "g12_grid.py")):
        print(f"  {f} is {'the file stamped at the selection' if sel.get(k) == _sha(HERE / f) else 'NOT the file stamped at the selection'}")
    d = out / "full"
    d.mkdir(parents=True, exist_ok=True)
    (t_is, _), (t_oos, dl), (t_all, _) = evaluate(P, end=is_end), evaluate(P, start=oos_start), evaluate(P)
    p1, p2 = write_grid(t_oos, d / "G12_grid_oos"), write_grid(t_all, d / "G12_grid_full")
    ref = t_all if dry else t_is
    assert list(frozen.index) == list(ref.index)
    same = (frozen.n.to_numpy() == ref.n.to_numpy()) & (np.abs(frozen.net.to_numpy() - ref.net.to_numpy()) < 0.005)
    same = pd.Series(same, index=ref.index)
    print(f"in-sample grid rebuilt from these bars: {int(same.sum())} of {len(ref)} combinations have the frozen n and net $"
          + ("" if same.all() else "   <-- NOT ALL: the frozen grid is not reproduced"))
    n_oos = len(dl.rows)
    span = f"{pd.Timestamp(dl.day[0]).date()} -> {pd.Timestamp(dl.day[-1]).date()}" if n_oos else "none"
    print(f"out-of-sample sessions: {n_oos} ({span})   wrote {p1.name}, {p2.name}")
    if not n_oos:
        print("  NO OUT-OF-SAMPLE SESSIONS IN THESE BARS: every out-of-sample table below is empty")
    res = {"oos_start": str(oos_start.date()), "last_day": str(last.date()), "n_oos_sessions": int(n_oos),
           "is_grid_reproduced": int(same.sum()), "n_grid": int(len(ref)), "dry_run": bool(dry), "picks": []}

    # ---- ORB v1.4 on the same dates, through the harness
    orb = orb_trades(ctx, start=oos_start, end=last)
    od = orb.groupby("day").pnl.sum().sort_index() if len(orb) else pd.Series(dtype=float)
    so = daily_stats(od, years)
    so["n"] = int(len(orb))
    res["orb_v14"] = so
    print(f"\nORB v1.4 (cal_orb through the harness), {oos_start.date()} -> {last.date()}: n {so['n']}  net {so['net']:+.0f}"
          f"  max dd on daily P&L {so['dd']:.0f}  net / dd {_fmt(so['net_dd'])}  years {so['by_year']}")

    # ---- the frozen picks
    print(f"\nfrozen picks, out of sample. A pick passes if: mean net a day > 0 with p < {P_PASS:.5f} (one-sided bootstrap"
          f" of the daily net over days with a decision, 10,000 resamples, seed 1); 3 of 4 calendar years net positive;"
          f" neighbours net positive. Beats ORB v1.4 = a pass with more net $ and a larger net / max drawdown.")
    frames = []
    for r in sel["picks"]:
        v = pick_test(r["name"], t_oos, dl, so, years)
        v.update(id=r["id"], tier=r["tier"], pick=r["pick"], how=r["how"], name=r["name"],
                 is_tpd=r["tpd"], is_gross_pt=r["gross_pt"], is_net_pt=r["net_pt"], is_net_day=r["net_day"],
                 is_t=r["t"], is_reproduced=bool(same.get(r["name"], False)))
        res["picks"].append(v)
        print(f"  {r['id']} ({r['how']})  {r['name']}   in sample: a day {r['tpd']:.1f}  gross $/trade {r['gross_pt']:+.3f}"
              f"  net $/trade {r['net_pt']:+.3f}  net $/day {r['net_day']:+.1f}  t {r['t']:+.2f}"
              f"   frozen row reproduced: {v['is_reproduced']}")
        if not v["days"]:
            print("      no out-of-sample session -> no test")
            continue
        print(f"      out of sample: n {v['n']}  a day {_fmt(v['tpd'], '{:.1f}')}  gross $/trade {_fmt(v['gross_pt'], '{:+.3f}')}"
              f" ({_fmt(v['gross_pts'], '{:+.4f}')} pts)  net $/trade {_fmt(v['net_pt'], '{:+.3f}')}"
              f"  net $/day {_fmt(v['net_day'], '{:+.1f}')}  net {v['net']:+.0f}  p {v['p']:.5f}  years {v['by_year']}"
              f"  max dd {v['dd']:.0f}  net / dd {_fmt(v['net_dd'])}")
        print("      neighbours: " + "   ".join(f"{x['name']}: n {x['n']} net {x['net']:+.0f}" for x in v["neighbours"]))
        print(f"      -> {'PASSES' if v['passes'] else 'fails'}  {v['checks']}   beats ORB v1.4: {v['beats_orb']}"
              f"  {v['beats_orb_checks']}")
        df = gs.trades(P, r["name"])
        df = df[df.day >= oos_start]
        assert len(df) == v["n"] and abs(df.net.sum() - v["net"]) < 0.005
        df.insert(0, "pick", r["id"]); df.insert(1, "name", r["name"])
        frames.append(df)
    if frames:
        pd.concat(frames, ignore_index=True).to_parquet(d / "G12_pick_trades.parquet", index=False)
    if not sel["picks"]:
        print("  (the selection has no pick)")

    # ---- reported whatever the picks do
    gb = pd.concat({"is": gross_by_signal(frozen), "oos": gross_by_signal(t_oos)}, names=["period"])
    gb.to_csv(d / "G12_gross_by_signal.csv")
    lt = lim_table(t_oos)
    lt.to_csv(d / "G12_lim.csv", index=False)
    lim_table(t_all).to_csv(d / "G12_lim_full.csv", index=False)
    _print_tables({"in sample, frozen": frozen, "out of sample": t_oos}, lt, "out of sample")
    res["shares"] = {"is": shares(frozen), "oos": shares(t_oos), "full": shares(t_all)}

    oos_g = t_oos.gross_pt.where(t_oos.n > 0)
    rho, n_rho = spearman(frozen.gross_pt.where(frozen.n > 0), oos_g)
    rho_n, _ = spearman(frozen.net_day.where(frozen.n > 0), t_oos.net_day.where(t_oos.n > 0))
    res["spearman"] = {"gross_pt_is_vs_oos": rho, "n": n_rho, "net_day_is_vs_oos": rho_n}
    print(f"\nSpearman of gross $ per trade in sample against out of sample over the {n_rho} combinations with a trade in"
          f" both: {_fmt(rho, '{:+.3f}')}   (of net $ a day: {_fmt(rho_n, '{:+.3f}')})")

    rc = reality_check(dl.net, dl.names)
    res["reality_check"] = rc
    (d / "G12_reality.json").write_text(json.dumps(rc, indent=1))
    if rc.get("p") is None:
        print("\nreality check: no out-of-sample days")
    else:
        print(f"\nWhite's reality check on the out-of-sample net $ a day of all {rc['n_combinations']} ({rc['n_with_a_trade']}"
              f" with a trade), {rc['n_days']} days, {rc['n_boot']} day resamples, seed {rc['seed']}:")
        b = rc["boot_max_t"]
        print(f"  largest day-level t {rc['t_obs_max']:+.3f} ({rc['t_obs_max_name']}); resampled largest t: median {b['q50']:.3f}"
              f"  95% {b['q95']:.3f}  99% {b['q99']:.3f}   p = {rc['p']:.4f}")
        b = rc["boot_max_mean"]
        print(f"  largest mean net $ a day {rc['mean_obs_max']:+.2f} ({rc['mean_obs_max_name']}); resampled largest centred mean:"
              f" median {b['q50']:.2f}  95% {b['q95']:.2f}  99% {b['q99']:.2f}   p = {rc['p_mean']:.4f}")

    top = t_oos[t_oos.n > 0].sort_values("net", ascending=False, kind="mergesort").head(10)
    res["hindsight_top10_by_oos_net"] = [_record(r) for _, r in top.iterrows()]
    print(f"\nHINDSIGHT (the top 10 of {len(t_oos)} by out-of-sample net $; chosen after the fact, not a result):")
    print(_show(top))

    be = break_even(t_oos)
    res["break_even"] = be
    print("\nbest out-of-sample gross per trade in each tier (tiers by out-of-sample trades a day) and the round-trip"
          " cost in ticks at which it would break even (the house cost is 6 ticks at the market, 5 with a limit entry):")
    for x in be:
        if x["name"] is None:
            print(f"  tier {x['tier']}: no combination")
        else:
            print(f"  tier {x['tier']} ({x['combinations_in_tier']} combinations): {x['name']}  a day {x['tpd']:.1f}"
                  f"  gross $/trade {x['gross_pt']:+.3f} = {x['gross_pts']:+.4f} points -> breaks even at"
                  f" {x['break_even_ticks']:.2f} ticks a round trip (house cost {x['house_cost_ticks']:.0f});"
                  f" net $/trade {x['net_pt']:+.3f}  net $/day {x['net_day']:+.1f}")
    (d / "G12_oos.json").write_text(json.dumps(res, indent=1, default=str))
    print(f"\nwrote {d}/G12_oos.json, G12_gross_by_signal.csv, G12_lim.csv, G12_lim_full.csv, G12_reality.json"
          f"{', G12_pick_trades.parquet' if frames else ''}   total {time.time() - t00:.0f}s")
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", choices=["is", "full"], required=True)
    ap.add_argument("--out", help="code test only: write under this directory instead of data/studies/yt1")
    ap.add_argument("--dry-split", help="code test only (needs --out): run the full phase on the in-sample bars with a"
                                        " made-up split date")
    a = ap.parse_args()
    pd.set_option("display.width", 250)
    pd.set_option("display.max_columns", 40)
    out = pathlib.Path(a.out) if a.out else core.OUT
    if a.phase == "is":
        assert not a.dry_split
        phase_is(out)
    elif a.dry_split:
        assert a.out and out.resolve() != core.OUT.resolve() and core.OUT.resolve() not in out.resolve().parents, \
            "--dry-split needs --out outside data/studies/yt1 (a dry run never writes the real output directory)"
        phase_full(out=out, oos_start=pd.Timestamp(a.dry_split), bars_phase="is", dry=True)
    else:
        phase_full(out=out)


if __name__ == "__main__":
    main()
