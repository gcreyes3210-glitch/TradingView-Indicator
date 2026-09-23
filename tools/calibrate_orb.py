#!/usr/bin/env python3
"""Compare the local ORB engine with a TradingView 'List of trades' export, trade by trade.

    python3 tools/calibrate_orb.py [data/tradingview/ORB4_MNQ_2020-2026.csv] [--bars data/bars/MNQ_5m.parquet]

The export's 'Date and time' is in the chart timezone (America/Los_Angeles); it is converted to New York.
Trades are matched on (New York entry date, side), then compared on entry time, prices, exit and PnL.
"""
import sys, collections
import pandas as pd
sys.path.insert(0, __import__("os").path.dirname(__file__))
from orb_engine import run

args = [a for a in sys.argv[1:] if not a.startswith("--")]
path = args[0] if args else "data/tradingview/ORB4_MNQ_2020-2026.csv"
bars_path = sys.argv[sys.argv.index("--bars") + 1] if "--bars" in sys.argv else "data/bars/MNQ_5m.parquet"


def load_tv(path):
    rows = pd.read_csv(path, encoding="utf-8-sig")
    tr = collections.defaultdict(dict)
    for _, r in rows.iterrows():
        t = pd.Timestamp(r["Date and time"]).tz_localize("America/Los_Angeles").tz_convert("America/New_York")
        d = tr[int(r["Trade number"])]
        if r["Type"].startswith("Entry"):
            tag = dict(x.split(":", 1) for x in r["Signal"].split("|")[2:] if ":" in x)
            d.update(side=r["Signal"][0], entry_time=t, entry=float(r["Price USD"]), or_w=float(tag["or"]),
                     on=tag["on"], pnl=float(r["Net PnL USD"]))
        else:
            d.update(exit_time=t, exit=float(r["Price USD"]), reason=r["Signal"])
    df = pd.DataFrame.from_dict(tr, orient="index").sort_index()
    df["day"] = df.entry_time.dt.date
    return df


def metrics(df):
    pnl = df.pnl
    eq = pnl.cumsum()
    gw, gl = pnl[pnl > 0].sum(), -pnl[pnl < 0].sum()
    return dict(n=len(df), net=round(pnl.sum()), win=round(100 * (pnl > 0).mean(), 1),
                pf=round(gw / gl, 2) if gl else None, dd=round((eq - eq.cummax()).min()),
                stops=int((df.reason == "SL").sum()), time=int((df.reason == "time").sum()))


tv = load_tv(path)
bars = pd.read_parquet(bars_path)
last_bar = bars.index[-1]
loc = run(bars)
loc["day"] = loc.entry_time.dt.date

# compare only the window both cover
lo, hi = tv.entry_time.min().date(), last_bar.date()
tvw = tv[(tv.day >= lo) & (tv.day <= hi) & (tv.exit_time <= last_bar)]
locw = loc[(loc.day >= lo) & (loc.day <= hi)]
print(f"window {lo} -> {hi}  (TradingView trades outside the bar data: {len(tv) - len(tvw)})")

m = tvw.reset_index().merge(locw, on=["day", "side"], how="outer", suffixes=("_tv", "_loc"), indicator=True)
both = m[m._merge == "both"]
print(f"\nTradingView {len(tvw)}  local {len(locw)}  same day+side {len(both)}  "
      f"TV only {int((m._merge == 'left_only').sum())}  local only {int((m._merge == 'right_only').sum())}")
same_t = both.entry_time_tv == both.entry_time_loc
print(f"  of the matches: same entry bar {int(same_t.sum())}  same entry price {int((both.entry_tv == both.entry_loc).sum())}  "
      f"same exit reason {int((both.reason_tv == both.reason_loc).sum())}  same exit price {int((both.exit_tv == both.exit_loc).sum())}  "
      f"PnL within $1 {int(((both.pnl_tv - both.pnl_loc).abs() <= 1).sum())}  same OR width {int(((both.or_w_tv - both.or_w_loc).abs() < 0.051).sum())}")

print("\n            " + "  ".join(f"{k:>7}" for k in metrics(tvw)))
for name, df in (("TradingView", tvw), ("local", locw)):
    print(f"{name:<12}" + "  ".join(f"{v:>7}" for v in metrics(df).values()))
print("\nper year (net):")
for y in sorted({d.year for d in tvw.day}):
    a = tvw[tvw.entry_time.dt.year == y].pnl.sum(); b = locw[locw.entry_time.dt.year == y].pnl.sum()
    print(f"  {y}  TV {a:+9,.0f}  local {b:+9,.0f}  diff {b - a:+8,.0f}")

if "--show" in sys.argv:  # unmatched trades and matches whose entry price differs
    diff = m[(m._merge != "both") | (m.entry_tv != m.entry_loc)]
    cols = ["day", "side", "_merge", "entry_time_tv", "entry_time_loc", "entry_tv", "entry_loc", "or_w_tv", "or_w_loc", "on_tv", "on_loc", "pnl_tv", "pnl_loc"]
    print(diff[cols].to_string())
