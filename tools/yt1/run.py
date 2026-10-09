#!/usr/bin/env python3
"""Run one YT1 strategy module.

    python3 tools/yt1/run.py <ID> --phase is      bars cut at 2022-12-31 23:59 (asserted): the in-sample step
    python3 tools/yt1/run.py <ID> --phase full    every bar: only run after the in-sample step is logged
    python3 tools/yt1/run.py <ID> --check         look-ahead test (mirrored-future) on the in-sample bars, base variant
    python3 tools/yt1/run.py <ID> --show 8        print 8 random base trades (seed 3) for a hand check

A module tools/yt1/s_<ID>.py defines ID, NAME, VARIANTS (ordered dict: 'base', then the two neighbours 'nb1', 'nb2',
then any reported alternatives), orders(ctx, **params) -> list of order dicts (every candidate order, each built only
from bars up to its signal bar) and trades(ctx, **params) -> list of trade dicts from core.run_orders / core.simulate.
"""
import argparse, importlib, json, sys, pathlib, time
import numpy as np, pandas as pd
sys.path.insert(0, str(pathlib.Path(__file__).parent))
import core


def bars(phase, data_dir=None):
    path = (pathlib.Path(data_dir) / "MNQ_1m.parquet") if data_dir else None
    if phase == "is":
        a = core.load_bars("MNQ", cut=core.IS_END, path=path)
        assert a.index.max() < core.IS_END, "in-sample bars reach into the out-of-sample window"
    else:
        a = core.load_bars("MNQ", path=path)
    return a


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ident")
    ap.add_argument("--phase", choices=["is", "full"], default="is")
    ap.add_argument("--variants")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--show", type=int, default=0)
    ap.add_argument("--cuts", type=int, default=16)
    a = ap.parse_args()
    if a.ident.startswith("K-"):                              # a claim check: k_<ID>.measure(ctx) -> dict
        mod = importlib.import_module(f"k_{a.ident[2:]}")
        ctx = core.Ctx(bars(a.phase))
        res = mod.measure(ctx)
        d = core.OUT / a.phase
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{a.ident}.json").write_text(json.dumps(res, indent=1, default=str))
        print(f"{a.ident}  {mod.NAME}   phase {a.phase}   bars {ctx.ts[0]} -> {ctx.ts[-1]}")
        (mod.show if hasattr(mod, "show") else lambda r: print(json.dumps(r, indent=1, default=str)))(res)
        return
    mod = importlib.import_module(f"s_{a.ident}")
    names = list(mod.VARIANTS)
    assert names[:3] == ["base", "nb1", "nb2"], "VARIANTS must start with base, nb1, nb2"
    A = bars(a.phase)
    if a.check:
        p = mod.VARIANTS["base"]
        ok = core.causal_check(lambda c: mod.orders(c, **p), bars("is"), n_samples=a.cuts)
        print(f"{a.ident} look-ahead test: {'PASS' if ok else 'FAIL'}")
        sys.exit(0 if ok else 1)
    ctx = core.Ctx(A)
    todo = a.variants.split(",") if a.variants else names
    print(f"{a.ident}  {mod.NAME}   phase {a.phase}   bars {A.index[0]} -> {A.index[-1]}")
    res = {}
    for v in todo:
        t0 = time.time()
        df = core.trades_df(mod.trades(ctx, **mod.VARIANTS[v]))
        res[v] = core.save(a.ident, v, a.phase, df, extra=dict(params={k: str(x) for k, x in mod.VARIANTS[v].items()}))
        print(core.fmt_row(v, res[v]), f"  [{time.time() - t0:.0f}s]")
        if v == "base" and a.show and len(df):
            pick = df.sample(min(a.show, len(df)), random_state=3).sort_values("entry_time")
            print(pick[["sig_time", "entry_time", "exit_time", "side", "entry", "stop", "exit", "pnl", "R", "reason", "tag"]].to_string())
    if a.phase == "full" and all(k in res for k in ("base", "nb1", "nb2")):
        v = core.verdict(res["base"], [res["nb1"], res["nb2"]])
        print("verdict:", v["verdict"], v["checks"], f"(Bonferroni p < {v['bonf']:.5f})")
        (core.OUT / "full" / f"{a.ident}_verdict.json").write_text(json.dumps(v, indent=1))


if __name__ == "__main__":
    main()
