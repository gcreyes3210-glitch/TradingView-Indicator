#!/usr/bin/env python3
"""Compare tools/vp80_engine.py (TradingView fill rules, no slippage as in the Pine script) with the VP2y TradingView trade export, trade by trade.

    python3 tools/calibrate_vp80.py [data/tradingview/VP2y_MNQ_2023-2026.csv] [--show]

Export times are the chart timezone (America/Los_Angeles) and are converted to New York; trades are matched on
(New York entry date, side). The engine runs over the export's date range.
"""
import sys, collections
import pandas as pd
sys.path.insert(0, __import__("os").path.dirname(__file__))
from vp80_engine import run, TZ
from orb_engine import stats

args = [a for a in sys.argv[1:] if not a.startswith("--")]
path = args[0] if args else "data/tradingview/VP2y_MNQ_2023-2026.csv"
rows = pd.read_csv(path, encoding="utf-8-sig")
tr = collections.defaultdict(dict)
for _, r in rows.iterrows():
    t = pd.Timestamp(r["Date and time"]).tz_localize("America/Los_Angeles").tz_convert(TZ)
    d = tr[int(r["Trade number"])]
    if r["Type"].startswith("Entry"):
        d.update(side=r["Signal"][0], entry_time=t, entry=float(r["Price USD"]), pnl=float(r["Net PnL USD"]))
    else:
        d.update(exit_time=t, exit=float(r["Price USD"]), reason=r["Signal"])
tv = pd.DataFrame.from_dict(tr, orient="index").sort_index()
tv["day"] = tv.entry_time.dt.date
lo, hi = tv.entry_time.min().normalize(), tv.exit_time.max() + pd.Timedelta(days=1)
loc, _ = run(pd.read_parquet("data/bars/MNQ_5m.parquet"), pd.read_parquet("data/bars/MNQ_1m.parquet"),
             start=pd.Timestamp("2023-09-22", tz=TZ), end=hi, tv_fills=True, slip_ticks=0)
loc["day"] = loc.entry_time.dt.date
m = tv.reset_index().merge(loc, on=["day", "side"], how="outer", suffixes=("_tv", "_loc"), indicator=True)
b = m[m._merge == "both"]
print(f"TradingView {len(tv)}  local {len(loc)}  same day+side {len(b)}  TV only {(m._merge == 'left_only').sum()}  "
      f"local only {(m._merge == 'right_only').sum()}")
print(f"  of the matches: same entry bar {(b.entry_time_tv == b.entry_time_loc).sum()}  same entry price "
      f"{(b.entry_tv == b.entry_loc).sum()}  same exit reason {(b.reason_tv == b.reason_loc).sum()}  same exit price "
      f"{(b.exit_tv == b.exit_loc).sum()}  PnL within $1 {((b.pnl_tv - b.pnl_loc).abs() <= 1).sum()}")
for n, t in (("TradingView", tv), ("local", loc)):
    t = t.assign(reason=t.reason)
    print(f"{n:<12}" + "  ".join(f"{k} {v}" for k, v in stats(t).items()))
if "--show" in sys.argv:
    d = m[(m._merge != "both") | (m.entry_tv != m.entry_loc) | (m.exit_tv != m.exit_loc)]
    print(d[["day", "side", "_merge", "entry_time_tv", "entry_time_loc", "entry_tv", "entry_loc", "exit_tv", "exit_loc",
             "reason_tv", "reason_loc", "pnl_tv", "pnl_loc"]].to_string())
