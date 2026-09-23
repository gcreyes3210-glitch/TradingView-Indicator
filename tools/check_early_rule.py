#!/usr/bin/env python3
"""Check ORB_strategy.pine v1.4's early-close calendar against the halts in the bars.

    python3 tools/check_early_rule.py

Re-implements the script's rule (half days 13:15 ET: day after Thanksgiving, Dec 24 Mon-Thu unless it is the observed
Christmas, Jul 3 Mon-Thu unless it is the observed Independence Day; holidays with a 13:00 futures halt: MLK, Presidents',
Memorial, Juneteenth from 2022, Independence Day, Labor Day, Thanksgiving, Christmas — fixed dates moved to Friday /
Monday when on a weekend) and compares it, for every cash-session day in data/bars/MNQ_5m.parquet, with the halt read
from the bars (the engine's rule: the session stops before 16:00 with a gap of more than 30 minutes).
"""
import calendar, datetime as dt
import pandas as pd


def nth(y, m, n, weekday):                      # weekday: Monday = 0
    days = [d for d in range(1, calendar.monthrange(y, m)[1] + 1) if dt.date(y, m, d).weekday() == weekday]
    return days[n - 1] if n > 0 else days[-1]


def obs(y, m, d):
    w = dt.date(y, m, d).weekday()
    return d - 1 if w == 5 else d + 1 if w == 6 else d


def pine_halt(day):
    y, m, d, wd = day.year, day.month, day.day, day.weekday()
    thanksgiving = m == 11 and d == nth(y, 11, 4, 3)
    xmas = m == 12 and d == obs(y, 12, 25)
    july4 = m == 7 and d == obs(y, 7, 4)
    june19 = y >= 2022 and m == 6 and d == obs(y, 6, 19)
    half = (m == 11 and d == nth(y, 11, 4, 3) + 1) or (m == 12 and d == 24 and wd <= 3 and not xmas) or \
           (m == 7 and d == 3 and wd <= 3 and not july4)
    hol = (m == 1 and d == nth(y, 1, 3, 0)) or (m == 2 and d == nth(y, 2, 3, 0)) or (m == 5 and d == nth(y, 5, -1, 0)) \
        or june19 or july4 or (m == 9 and d == nth(y, 9, 1, 0)) or thanksgiving or xmas
    return "13:15" if half else "13:00" if hol else None


b = pd.read_parquet("data/bars/MNQ_5m.parquet")
tod = b.index.hour * 60 + b.index.minute
days = sorted(set(b.index[tod == 570].date))
gap = b.index.to_series().shift(-1) - b.index.to_series()
halt_bars = b[(gap > pd.Timedelta(minutes=30)).values & (tod >= 570) & (tod < 955)]
bar_halt = {}
for ts in halt_bars.index:
    bar_halt.setdefault(ts.date(), (ts + pd.Timedelta(minutes=5)).strftime("%H:%M"))
rows = [(d, bar_halt.get(d), pine_halt(d)) for d in days]
diff = [r for r in rows if r[1] != r[2]]
print(f"cash-session days in the bars: {len(days)}; early closes in the bars: {len(bar_halt)}; "
      f"flagged by the v1.4 rule: {sum(1 for r in rows if r[2])}; agree: {len(rows) - len(diff)}")
for d, bh, ph in diff:
    print(f"  {d} ({calendar.day_abbr[d.weekday()]}): bars halt {bh or 'none (full session)'}   v1.4 rule {ph or 'none'}")
