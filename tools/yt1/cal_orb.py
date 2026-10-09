#!/usr/bin/env python3
"""Calibration of the YT1 harness: ORB v1.4 rebuilt as YT1 orders and compared trade by trade with tools/orb_engine.py.
    python3 tools/yt1/cal_orb.py
"""
import sys, pathlib
import numpy as np, pandas as pd
sys.path.insert(0, str(pathlib.Path(__file__).parent)); sys.path.insert(0, str(pathlib.Path(__file__).parents[1]))
import core
import orb_engine


def orders(ctx):
    b = ctx.bars(5)
    out = []
    H, L, C = b.high.to_numpy(), b.low.to_numpy(), b.close.to_numpy()
    tod = (b.index.hour * 60 + b.index.minute).to_numpy()
    bd = b.index.tz_localize(None).normalize()
    il = b.i_last.to_numpy()
    for d, row in ctx.days.iterrows():
        m = np.flatnonzero((bd == d) & (tod >= 570) & (tod < 690))
        if len(m) < 4 or tod[m[0]] != 570:
            continue
        orb = m[tod[m] < 585]
        if len(orb) != 3:
            continue
        orh, orl = H[orb].max(), L[orb].min()
        rng = orh - orl
        if rng < 4 * core.TICK or not (orh > row.onh or orl < row.onl):
            continue
        # flat bar: the 5m bar that opens at 16:00 (its last 1m bar), or on early days the bar opening <= 10 min before the halt
        if not row.early:
            x = ctx.idx(d, "16:04")
        else:
            halt = row.end_tod + 11
            x = ctx.idx(d, (halt - 10) // 5 * 5 + 4)
        if x is None:
            continue
        for k in m[tod[m] >= 585]:
            if C[k] > orh + 2 * core.TICK + 0.15 * rng:
                out.append(dict(i=int(il[k]), side=1, etype="close", stop=orl - 2 * core.TICK, exit_i=x)); break
            if C[k] < orl - 2 * core.TICK - 0.15 * rng:
                out.append(dict(i=int(il[k]), side=-1, etype="close", stop=orh + 2 * core.TICK, exit_i=x)); break
    return out


if __name__ == "__main__":
    ctx = core.Ctx(core.load_bars("MNQ"))
    mine = core.trades_df(core.run_orders(ctx, orders(ctx), skip_roll=False))
    ref, _ = orb_engine.run(pd.read_parquet(core.BARS / "MNQ_5m.parquet"), start=pd.Timestamp("2019-06-01", tz=core.TZ)), None
    ref = ref if isinstance(ref, pd.DataFrame) else ref[0]
    print("harness:", len(mine), round(mine.pnl.sum(), 1), " engine:", len(ref), round(ref.pnl.sum(), 1) if "pnl" in ref else ref.columns.tolist())
    print(ref.columns.tolist()); print(ref.head(2).to_string())
