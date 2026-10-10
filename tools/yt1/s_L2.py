#!/usr/bin/env python3
"""L2 - the YT10 trades as a standard harness module (YT10_SPEC.md): the fade / break at the first tap of the midnight
open (MID1), of a volume-profile level, of a stacked-count bucket or of the aligned POC (VPN1), and VA-trend. Built on
lev2_levels / lev2_events (events, orders_of, va_orders), so it trades exactly the events the tables count: every
level on its own, the first tap by 15:00 on study days, no cluster and no "fresh" requirement.

A variant (keyword arguments of orders / trades):
    kind   'mid'    code = an hourly open ('o00' = midnight; 'o00~' its placebos), side 'all' / 'R' / 'S',
                    rel = None or the bias relation 'with' / 'against' / 'none'
           'cell'   prof, level, side: one profile level on one side
           'stack'  bucket '0' / '1' / '2' / '3+': every real profile-level event with that stacked count, both sides
           'apoc'   the aligned-POC events (rth and eth), both sides
           'va'     VA-trend; which = 'rth' (the rule) / 'eth' / 'rth3' (its two neighbours)
    stop   p20 / a04 / a08        k   target in multiples of the stop distance        trade  'fade' or 'break'
           (a break has k = 3, or k = 2 with stop a04: the a04 x 2R neighbour of a break pick)

Orders. A level: ONE resting order per event, i = the last bar before 09:30, so that it rests during the 09:30 bar,
expiring on the 15:00 bar (the flat bar on a short day). VA-trend: a market order with i = the last bar before 09:30,
filled at the 09:30 open (etype 'open'), no stop, flat at the flat bar, R unit 0.1 x ATR.

The one number read after an order's bar i: the open of bar i + 1, the 09:30 open. It sets the side and the
0.04 x ATR skip of a level, and for VA-trend the day type (the open against the value areas of earlier sessions).
orders(ctx, ..., at_open=False), the default and what `run.py L2 --check` / core.causal_check call, replaces that
open by the last close before it, so everything the test compares comes from bars up to i; trades() uses
at_open=True. `s_L2.py --check` runs per variant (as s_L1):
    A  core.causal_check on the at_open=False orders
    B  the same test on the real (at_open=True) orders with that one open kept true and everything else after bar i
       mirrored (s_L1.check_true_open)
    --plain: also core.causal_check on the real orders, which mirrors that open too (it can only fail through it)

VARIANTS  base / nb1 / nb2        the midnight open, sides pooled: a04 x 3R, a08 x 3R, a04 x 2R
          mb / mb_nb1 / mb_nb2    the with-bias midnight fade
          p1 .. p8 (+ _nb1, _nb2) the frozen picks of data/studies/yt1/VPN1_selected.json (a placeholder until it exists)
          chk1 .. chk16           fixed before any table was built (see CHECKS)

    python3 tools/yt1/s_L2.py --check all [--plain]      the look-ahead tests
    python3 tools/yt1/s_L2.py --recon                    run.py's saved trades against the events files and the tables
"""
import argparse, json, pathlib, sys
import numpy as np
import pandas as pd
sys.path.insert(0, str(pathlib.Path(__file__).parent))
import core
import lev1_events as LE
import lev2_levels as LV
import lev2_events as LE2

ID = "L2"
NAME = "YT10: first tap of the midnight open / volume-profile levels after the open, and VA-trend"
SEL_PATH = core.OUT / "VPN1_selected.json"
PLACEHOLDER = dict(kind="cell", prof="rth1", level="poc", side="R")     # only until VPN1_selected.json exists
CHECKS = (                                                              # fixed up front (before any table was built)
    dict(kind="mid", code="o03"),                                       # 1  an hourly open other than midnight
    dict(kind="mid", code="o00~"),                                      # 2  the midnight placebos
    dict(kind="cell", prof="rth3", level="poc", side="R"),              # 3  an rth composite level
    dict(kind="cell", prof="eth5", level="val", side="S"),              # 4  an eth composite level
    dict(kind="cell", prof="rthw", level="vah", side="R"),              # 5  a weekly profile level
    dict(kind="cell", prof="on", level="poc", side="S"),                # 6  the `on` profile
    dict(kind="apoc"),                                                  # 7  the aligned-POC events
    dict(kind="stack", bucket="2"),                                     # 8  a stacked-count bucket
    dict(kind="cell", prof="eth2", level="vah", side="R", trade="break"),  # 9  the break trade (a04, 3R)
    dict(kind="va", which="rth"),                                       # 10 VA-trend
    dict(kind="va", which="eth"),                                       # 11 its neighbour 1
    dict(kind="va", which="rth3"),                                      # 12 its neighbour 2
    dict(kind="mid", code="o00", stop="p20"),                           # 13 the midnight open with the 20-point stop, 3R, as asked
    dict(kind="mid", code="o00", rel="against"),                        # 14 the fade against the bias
    dict(kind="cell", prof="rthw", level="val", side="S", trade="break", k=2),   # 15 the 2R break (a break pick's neighbour)
    dict(kind="mid", code="o00", trade="break"),                        # 16 the break at the midnight open
)
DEF = dict(kind="mid", code="o00", side="all", rel=None, prof=None, level=None, bucket=None, which="rth", stop="a04", k=3,
           trade="fade")


def _full(p):
    return dict(DEF, **p)


def _picks():
    if SEL_PATH.exists():
        return json.loads(SEL_PATH.read_text())["picks"]
    return [dict(pick=1, type="cell", trade="fade", **{k: v for k, v in PLACEHOLDER.items() if k != "kind"})]


def _pick_params(pk):
    """(base, nb1, nb2) keyword arguments of a frozen pick."""
    if pk["type"] == "vatrend":
        return tuple(dict(kind="va", which=w) for w in LE2.VA)
    if pk["type"] == "cell":
        b = dict(kind="cell", prof=pk["prof"], level=pk["level"], side=pk["side"], trade=pk["trade"])
    elif pk["type"] == "stack":
        b = dict(kind="stack", bucket=pk["bucket"], trade=pk["trade"])
    else:
        b = dict(kind="apoc", trade=pk["trade"])
    return b, dict(b, stop="a08"), dict(b, k=2)


def _variants():
    v = {"base": _full(dict()), "nb1": _full(dict(stop="a08")), "nb2": _full(dict(k=2)),
         "mb": _full(dict(rel="with")), "mb_nb1": _full(dict(rel="with", stop="a08")), "mb_nb2": _full(dict(rel="with", k=2))}
    for pk in _picks():
        n = int(pk["pick"])
        for name, p in zip((f"p{n}", f"p{n}_nb1", f"p{n}_nb2"), _pick_params(pk)):
            v[name] = _full(p)
    for n, p in enumerate(CHECKS, 1):
        v[f"chk{n}"] = _full(p)
    return v


VARIANTS = _variants()


def variant_name(stop="a04", k=3, trade="fade", **_):
    if trade == "break":
        assert int(k) == 3 or (int(k) == 2 and stop == "a04"), "a break has a 3R target (2R only with the a04 stop)"
        return LE2.BRK2 if int(k) == 2 else f"brk_{stop}"
    return f"{stop}x{int(k)}"


def rows_of(ev, kind="mid", code="o00", side="all", rel=None, prof=None, level=None, bucket=None, **_):
    """The event rows of a selection in an events frame (tapped or not): what the tables call its events."""
    e = ev[ev.is_event]
    if kind == "mid":
        e = e[e.code == code]
        if rel is not None:
            e = e[e.bias_rel == rel]
    elif kind == "cell":
        e = e[(e.code == f"{prof}_{level}")]
    elif kind == "stack":
        e = e[~e.is_placebo & e.prof.isin(LV.PROFS) & (e.sbucket == bucket)]
    elif kind == "apoc":
        e = e[e.code.isin(LV.APOC)]
    else:
        raise ValueError(kind)
    return e if side == "all" else e[e.side == side]


def _events(ctx, at_open, score=False, kind="mid", code="o00", prof=None, level=None, **_):
    if kind == "mid":
        return LE2.events(ctx, "mid", at_open=at_open, score=score, codes=[code])
    if kind == "cell":
        return LE2.events(ctx, "vp", at_open=at_open, score=score, profs=[prof], codes=[f"{prof}_{level}"])
    if kind == "apoc":
        return LE2.events(ctx, "vp", at_open=at_open, score=score, profs=[f"{s}{n}" for s in ("rth", "eth") for n in LV.NS],
                          codes=list(LV.APOC))
    return LE2.events(ctx, "vp", at_open=at_open, score=score)          # stack: every profile is needed for the count


def orders(ctx, at_open=False, **p):
    """Every order of the variant, each built from bars up to its own bar `i`; at_open=True (trades) reads in
    addition the open of the 09:30 bar, see the module docstring."""
    p = _full(p)
    assert p["trade"] in ("fade", "break") and p["stop"] in LE.STOPS
    if p["kind"] == "va":
        return LE2.va_orders(ctx, p["which"], at_open)
    v = variant_name(**p)
    out = []
    for r in rows_of(_events(ctx, at_open, **p), **p).itertuples(index=False):
        for o in LE2.orders_of(r, v):
            o["tag"] = f"{r.lid}|{r.side}|{r.date:%Y-%m-%d}"
            out.append(o)
    return out


def trades(ctx, **p):
    return core.run_orders(ctx, orders(ctx, at_open=True, **p), one_at_a_time=False, skip_roll=2)


# ------------------------------------------------------------------ look-ahead tests
def _label(p):
    if p["kind"] == "va":
        return f"VA-trend {p['which']:<14}"
    what = {"mid": p["code"] + (f" bias {p['rel']}" if p["rel"] else "") + (f":{p['side']}" if p["side"] != "all" else ""),
            "cell": f"{p['prof']}_{p['level']}:{p['side']}", "stack": f"stack {p['bucket']}", "apoc": "aligned POC"}[p["kind"]]
    return f"{what:<14} {variant_name(**p):<9}"


def run_checks(names, cuts=16, plain=False):
    import run
    from s_L1 import check_true_open
    A = run.bars("is")
    full = core.Ctx(A)
    bad = 0
    for v in names:
        p = VARIANTS[v]
        o0, o1 = orders(full, **p), orders(full, at_open=True, **p)
        k0 = {str(core._okey(full, x)) for x in o0}
        k1 = {str(core._okey(full, x)) for x in o1}
        other_day = sum(full.cdate[x["i"]] != full.cdate[x["i"] + 1] for x in o1)
        okA = core.causal_check(lambda cx, p=p: orders(cx, **p), A, n_samples=cuts, verbose=False)
        okB, n_od, n_s = check_true_open(lambda cx, p=p: orders(cx, at_open=True, **p), A, n_samples=cuts)
        line = (f"L2 {v:<8} {_label(p)} orders {len(o1):>6} (order bar on another calendar day than its 09:30 bar: {other_day})  "
                f"differ from the at_open=False orders: {len(k1 - k0):>4}  | A mirrored future, open replaced by the last close: "
                f"{'PASS' if okA else 'FAIL'} | B real orders, that open kept: {'PASS' if okB else 'FAIL'} ({n_s} bars)")
        bad += (not okA) + (not okB)
        if plain:
            okC = core.causal_check(lambda cx, p=p: orders(cx, at_open=True, **p), A, n_samples=cuts, verbose=False)
            line += f" | C real orders, plain test: {'PASS' if okC else 'FAIL (through the open of bar i + 1)'}"
        print(line, flush=True)
    return bad


# ------------------------------------------------------------------ reconciliation with the tables
def recon(phase="is"):
    """Each variant's trades as saved by `run.py L2 --phase <phase>` against the events files and the table row."""
    d = core.OUT / phase
    sfx = "" if phase == "is" else "_full"                   # the full phase writes <table>_full.csv
    mid, vp = pd.read_parquet(d / "MID1_events.parquet"), pd.read_parquet(d / "VPN1_events.parquet")
    import lev2_tables as LT2
    dt = LT2.read_daytypes(d / "VPN1_daytypes.csv")
    ml, ms = pd.read_csv(d / f"MID1_levels{sfx}.csv"), pd.read_csv(d / f"MID1_splits{sfx}.csv")
    rt, sk = pd.read_csv(d / f"VPN1_reaction{sfx}.csv"), pd.read_csv(d / f"VPN1_stacked{sfx}.csv", dtype={"key": str})
    va = json.loads((d / f"VPN1_vatrend{sfx}.json").read_text())
    bad = 0
    for v, p in VARIANTS.items():
        f = d / f"L2_{v}.csv"
        if not f.exists():
            print(f"L2 {v}: no saved run ({f.name})")
            bad += 1
            continue
        tr = pd.read_csv(f)
        n_r, net_r, R_r = len(tr), float(tr.pnl.sum()), float(tr.R.mean()) if len(tr) else float("nan")
        if p["kind"] == "va":
            s = dt[dt.study & (dt[f"va_{p['which']}_side"] != "")]
            a = np.c_[s[f"va_{p['which']}_pnl"].to_numpy(float), s[f"va_{p['which']}_R"].to_numpy(float)]
            x = va[{"rth": "base", "eth": "nb1", "rth3": "nb2"}[p["which"]]]
            n_t, R_t, net_t, where = x["n"], x.get("R"), x.get("net"), "vatrend.json"
        else:
            vn = variant_name(**p)
            rows = rows_of(mid if p["kind"] == "mid" else vp, **p)
            t = rows[rows.tapped & rows[f"f_{vn}"]]
            a = t[[f"pnl_{vn}", f"R_{vn}"]].to_numpy(float)
            if p["kind"] == "mid" and p["rel"] is not None:
                row, where = ms[(ms.split == "bias") & (ms.value == p["rel"])], "MID1_splits"
            elif p["kind"] == "mid":
                row, where = ml[(ml.code == p["code"]) & (ml.side == p["side"])], "MID1_levels"
            elif p["kind"] == "cell":
                row, where = rt[(rt.prof == p["prof"]) & (rt.level == p["level"]) & (rt.side == p["side"]) & (rt.set == "all")], "VPN1_reaction"
            else:
                key = p["bucket"] if p["kind"] == "stack" else "apoc"
                row, where = sk[(sk.kind == p["kind"]) & (sk.key == key) & (sk.side == "all")], "VPN1_stacked"
            ok_row = len(row) == 1 and not (p["kind"] == "mid" and p["rel"] is not None and (p["code"] != "o00" or p["side"] != "all"))
            n_t = int(row[f"n_{vn}"].iloc[0]) if ok_row else None
            R_t = float(row[f"R_{vn}"].iloc[0]) if ok_row else None
            net_t = float(row[f"net_{vn}"].iloc[0]) if ok_row else None
        n_e, net_e, R_e = len(a), float(a[:, 0].sum()) if len(a) else 0.0, float(a[:, 1].mean()) if len(a) else float("nan")
        same_trades = n_e == n_r and abs(net_e - net_r) < 0.005 and (n_e == 0 or abs(R_e - R_r) < 1e-9)
        if same_trades and n_e:
            b = tr[["pnl", "R"]].to_numpy(float)
            same_trades = bool(np.allclose(np.sort(a[:, 0]), np.sort(b[:, 0]), atol=0.005) and
                               np.allclose(np.sort(a[:, 1]), np.sort(b[:, 1]), atol=1e-9))
        same_table = n_t is not None and n_t == n_r and (n_r == 0 or (abs(net_t - net_r) < 0.01 and abs(R_t - R_r) < 1e-5))
        bad += not (same_trades and same_table)
        print(f"L2 {v:<8} {_label(p)} run.py: n {n_r:>4} net {net_r:>+10.2f} R {R_r:>+8.4f} | events file: n {n_e:>4} net "
              f"{net_e:>+10.2f} R {R_e:>+8.4f} -> {'same' if same_trades else 'DIFFERENT'} | table ({where}): n "
              f"{n_t} net {'-' if net_t is None else f'{net_t:+.2f}'} R {'-' if R_t is None else f'{R_t:+.4f}'} -> "
              f"{'same' if same_table else 'DIFFERENT'}")
    print(f"reconciliation: {len(VARIANTS)} variants, {bad} differ -> {'OK' if bad == 0 else 'NOT OK'}")
    return bad


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", help="variant names, comma separated, or 'all'")
    ap.add_argument("--cuts", type=int, default=16)
    ap.add_argument("--plain", action="store_true", help="also core.causal_check on the real (at_open=True) orders")
    ap.add_argument("--recon", action="store_true")
    ap.add_argument("--phase", choices=["is", "full"], default="is")
    a = ap.parse_args()
    bad = 0
    if a.check:
        names = list(VARIANTS) if a.check == "all" else a.check.split(",")
        bad += run_checks(names, a.cuts, a.plain)
    if a.recon:
        bad += recon(a.phase)
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
