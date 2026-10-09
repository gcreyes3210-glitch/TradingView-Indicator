#!/usr/bin/env python3
"""ORB v1.3 trades by scheduled event (data/events.csv), on the trade day and on the previous trading day.

    python3 tools/orb_engine.py --start 2019-06-01 --out t.csv && python3 tools/orb_events.py t.csv

Per event type and position (day / prev): trades, net, R per trade, net per calendar year, negative years, average
risk (points) and average absolute RTH range of the day, against days with no event of any type.
Pre-registered rule: a type becomes a skip filter only if it is negative in >= 6 of 8 calendar years AND the shuffle
test is below 5 %. Shuffle test: the type's labels are permuted among the trades within each calendar year 2,000
times; p = share of shuffles whose labelled trades have a mean R at or below the observed one (one-sided).
FOMC: for trades still open at 14:00 on FOMC days, what the position did from 14:00 (close of the 13:55 bar) to the exit.
"""
import sys
import numpy as np
import pandas as pd

TZ = "America/New_York"
t = pd.read_csv(sys.argv[1])
for c in ("entry_time", "exit_time"):
    t[c] = pd.to_datetime(t[c], utc=True).dt.tz_convert(TZ)
t["day"] = t.entry_time.dt.date
t["year"] = t.entry_time.dt.year
t["R"] = t.pnl / (t.risk * 2.0)
ev = pd.read_csv("data/events.csv", parse_dates=["date"])
ev["date"] = ev.date.dt.date
b = pd.read_parquet("data/bars/MNQ_5m.parquet")
tod = b.index.hour * 60 + b.index.minute
rth = b[(tod >= 570) & (tod < 960)]
g = rth.groupby(rth.index.date)
day_range = (g.high.max() - g.low.min())
sessions = sorted(day_range.index)
prev_session = dict(zip(sessions[1:], sessions[:-1]))
types = sorted(ev.type.unique())
by_date = ev.groupby("date").type.apply(set).to_dict()
t["ev_day"] = [by_date.get(d, set()) for d in t.day]
t["ev_prev"] = [by_date.get(prev_session.get(d), set()) for d in t.day]
t["range"] = [day_range.get(d, np.nan) for d in t.day]
none = t[t.ev_day.apply(len) == 0]
years = sorted(t.year.unique())
rng = np.random.default_rng(3)
print(f"{len(t)} trades, net {t.pnl.sum():+,.0f}, {t.R.mean():+.3f} R; days with no event of any type: {len(none)} trades, "
      f"{none.R.mean():+.3f} R, risk {none.risk.mean():.1f} pts, range {none.range.mean():.1f} pts\n")
rows = []
for pos in ("day", "prev"):
    for typ in types:
        mask = t[f"ev_{pos}"].apply(lambda s: typ in s).to_numpy()
        if mask.sum() == 0:
            continue
        x = t[mask]
        yn = x.groupby("year").pnl.sum()
        neg = int((yn < 0).sum())
        obs = x.R.mean()
        lab = pd.Series(mask, index=t.index)
        hits = 0
        for _ in range(2000):
            perm = lab.groupby(t.year).transform(lambda s: rng.permutation(s.to_numpy()))
            hits += t.R[perm.to_numpy()].mean() <= obs
        p = hits / 2000
        rows.append(dict(pos=pos, type=typ, n=len(x), net=round(x.pnl.sum()), R=round(obs, 3), neg_years=neg,
                         p=p, risk=round(x.risk.mean(), 1), range=round(x.range.mean(), 1),
                         filter="SKIP" if neg >= 6 and p < 0.05 else "-",
                         years=" ".join(f"{yn.get(y, 0):+.0f}" for y in years)))
r = pd.DataFrame(rows)
pd.set_option("display.width", 250)
print(r.to_string(index=False))

# FOMC afternoon: trades open at 14:00 on FOMC days
f = t[t.ev_day.apply(lambda s: "FOMC" in s)].copy()
out = []
for _, x in f.iterrows():
    d = x.day
    at14 = b[(b.index.date == d) & (tod == 13 * 60 + 55)]
    if x.exit_time.hour * 60 + x.exit_time.minute < 14 * 60 + 0 or at14.empty:
        continue
    px14 = at14.close.iloc[0]
    sgn = 1 if x.side == "L" else -1
    before = sgn * (px14 - x.entry) * 2.0
    after = sgn * (x.exit - px14) * 2.0
    out.append(dict(day=d, side=x.side, reason=x.reason, pnl=x.pnl, to_14=before, after_14=after, R_after=after / (x.risk * 2)))
o = pd.DataFrame(out)
print(f"\nFOMC days: {len(f)} trades, {len(o)} still open at 14:00 (the rest were stopped before the statement)")
if len(o):
    print(f"  open at 14:00: PnL up to 14:00 {o.to_14.sum():+,.0f} $, from 14:00 to exit {o.after_14.sum():+,.0f} $ "
          f"({o.R_after.mean():+.3f} R per trade), after-14:00 segment positive in {int((o.after_14 > 0).sum())} of {len(o)}; "
          f"exits after 14:00: {o.reason.value_counts().to_dict()}")
    o["year"] = pd.to_datetime(o.day).dt.year
    print("  after-14:00 $ by year: " + "  ".join(f"{y} {v:+.0f}" for y, v in o.groupby('year').after_14.sum().items()))
    stopped_before = f[f.exit_time.dt.hour * 60 + f.exit_time.dt.minute < 14 * 60]
    print(f"  stopped before 14:00: {len(stopped_before)} trades, {stopped_before.pnl.sum():+,.0f} $")
