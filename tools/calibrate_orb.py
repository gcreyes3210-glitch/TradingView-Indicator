#!/usr/bin/env python3
"""Compare the local ORB engine with a TradingView 'List of trades' export, trade by trade, and track the shadow rules
on the live trades (the weekly forward-test check).

    python3 tools/calibrate_orb.py [export.csv] [--bars data/bars/MNQ_5m.parquet] [--live 2026-09-23] [--show]

Calibration: the export's 'Date and time' is in the chart timezone (America/Los_Angeles) and is converted to New York;
trades are matched on (New York entry date, side), then compared on entry time, prices, exit and PnL, over the window
covered by both the export and the bars. v1.4 exits early-close days 10 minutes before the halt (reason 'early'), so
against a v1.3 export those trades differ in exit by design.

Forward test (--live, default the forward-test start 2026-09-23): for every export trade entered on or after that date,
whether each ORB8 filter would have skipped it, and the retail-sales flag — shadow rules, tracked and NOT traded:
    F1  previous cash day's range in the top tercile of the 60 cash days before it
    F2  overnight (18:00-09:30) range wider than the previous cash day's range
    F3  |09:30 gap| < 0.5 x the 09:30-09:45 opening-range width
    ORB8 skip = F1 or F2 or F3        retail = Census advance retail-sales release day (data/events.csv)
Then the running shadow lines (trades taken, trades ORB8 / retail would have skipped, net of the skipped trades) and a
ready-to-paste row for the "Forward test" table in BACKTEST_LOG.md. Flags need bars (and events.csv) that reach the
trade date; otherwise they print as n/a. Last, the forward bias log score (tools/bias_log.py, data/forward/bias_log.csv).
"""
import sys, collections
import numpy as np
import pandas as pd
sys.path.insert(0, __import__("os").path.dirname(__file__))
from orb_engine import run

TZ = "America/New_York"
FORWARD_START = "2026-09-23"


def load_tv(path):
    rows = pd.read_csv(path, encoding="utf-8-sig")
    tr = collections.defaultdict(dict)
    for _, r in rows.iterrows():
        t = pd.Timestamp(r["Date and time"]).tz_localize("America/Los_Angeles").tz_convert(TZ)
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


def shadow_flags(bars, events="data/events.csv"):
    """Per cash-session date: F1, F2, F3 (ORB8 filters) and retail, from the 5m bars and the event calendar."""
    tod = bars.index.hour * 60 + bars.index.minute
    rth = bars[(tod >= 570) & (tod < 960)]
    g = rth.groupby(rth.index.date)
    rng = g.high.max() - g.low.min()
    prev_rng = rng.shift(1)
    top_cut = prev_rng.shift(1).rolling(60).quantile(2 / 3)
    gap = g.open.first() - g.close.last().shift(1)
    o = bars[(tod >= 570) & (tod < 585)]
    or_w = o.groupby(o.index.date).high.max() - o.groupby(o.index.date).low.min()
    on = bars[(tod >= 1080) | (tod < 570)]
    sessions = np.array(sorted(rng.index))
    cal = np.array(on.index.date)
    k = np.where(on.index.hour >= 18, np.searchsorted(sessions, cal, side="right"),
                 np.searchsorted(sessions, cal, side="left"))
    ok = k < len(sessions)
    on_g = on[ok].groupby(sessions[k[ok]])
    on_w = on_g.high.max() - on_g.low.min()          # overnight range, by the session it precedes
    f = pd.DataFrame(index=sessions)
    f["F1"] = (prev_rng > top_cut).astype(object).where(prev_rng.notna() & top_cut.notna())
    f["F2"] = (on_w.reindex(sessions) > prev_rng).astype(object).where(prev_rng.notna())
    f["F3"] = (gap.abs() < 0.5 * or_w.reindex(sessions)).astype(object).where(gap.notna())
    f["ORB8"] = f[["F1", "F2", "F3"]].apply(lambda r: True if (r == True).any() else (np.nan if r.isna().any() else False),  # noqa: E712
                                            axis=1)
    if events is None:
        return f
    ev = pd.read_csv(events)
    retail = set(pd.to_datetime(ev[ev.type == "retail_sales"].date).dt.date)
    ev_end = pd.to_datetime(ev.date).max().date()
    f["retail"] = [(d in retail) if d <= ev_end else np.nan for d in sessions]
    return f


def shadow_report(tv, flags, since):
    live = tv[tv.entry_time >= pd.Timestamp(since, tz=TZ)].copy()
    print(f"\n==== forward test: {len(live)} live trades since {since} ====")
    if live.empty:
        return
    for c in ("F1", "F2", "F3", "ORB8", "retail"):
        live[c] = [flags[c].get(d, np.nan) if d in flags.index else np.nan for d in live.day]
    fmt = lambda v: "n/a" if pd.isna(v) else ("SKIP" if v else "-")
    print(f"{'date':<11}{'side':<5}{'exit':<7}{'net':>8}   F1    F2    F3    ORB8  retail")
    for _, r in live.iterrows():
        print(f"{str(r.day):<11}{r.side:<5}{r.reason:<7}{r.pnl:>+8.1f}   " +
              "  ".join(f"{fmt(r[c]):<4}" for c in ("F1", "F2", "F3", "ORB8", "retail")))
    row = []
    for c, name in (("ORB8", "ORB8"), ("retail", "retail-sales")):
        known = live[live[c].notna()]
        sk = known[known[c].astype(bool)]
        line = (f"taken {len(live)}, {name} would skip {len(sk)}, net of skipped {sk.pnl.sum():+,.0f}"
                + (f" ({len(live) - len(known)} n/a)" if len(known) < len(live) else ""))
        print(f"shadow {name}: {line}")
        row.append(line)
    if "F1" in live:
        print("  ORB8 by filter (a trade can fail several): " +
              "  ".join(f"{c} {int(live[c].eq(True).sum())} trades {live[live[c].eq(True)].pnl.sum():+,.0f}"
                        for c in ("F1", "F2", "F3")))
    print(f"\nlog row: | week to {live.day.max()} | {len(live)} | {live.pnl.sum():+,.0f} | {row[0]} | {row[1]} |")


if __name__ == "__main__":
    opts = {"--bars", "--live"}                        # options that take a value
    argv = sys.argv[1:]
    args = [a for i, a in enumerate(argv) if not a.startswith("--") and (i == 0 or argv[i - 1] not in opts)]
    path = args[0] if args else "data/tradingview/ORB4_MNQ_2020-2026.csv"
    bars_path = sys.argv[sys.argv.index("--bars") + 1] if "--bars" in sys.argv else "data/bars/MNQ_5m.parquet"
    since = sys.argv[sys.argv.index("--live") + 1] if "--live" in sys.argv else FORWARD_START

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
    early = both.reason_loc == "early"
    print(f"  of the matches: same entry bar {int(same_t.sum())}  same entry price {int((both.entry_tv == both.entry_loc).sum())}  "
          f"same exit reason {int((both.reason_tv == both.reason_loc).sum())}  same exit price {int((both.exit_tv == both.exit_loc).sum())}  "
          f"PnL within $1 {int(((both.pnl_tv - both.pnl_loc).abs() <= 1).sum())}  same OR width {int(((both.or_w_tv - both.or_w_loc).abs() < 0.051).sum())}")
    if early.any():
        print(f"  early-close trades (engine v1.4 'early' exit): {int(early.sum())}; exit matches on the other trades: "
              f"reason {int((both.reason_tv == both.reason_loc)[~early].sum())} / price "
              f"{int((both.exit_tv == both.exit_loc)[~early].sum())} of {int((~early).sum())}")

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

    shadow_report(tv, shadow_flags(bars), since)
    import bias_log
    bias_log.report()
