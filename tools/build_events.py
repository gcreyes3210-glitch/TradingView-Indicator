#!/usr/bin/env python3
"""Build data/events.csv (date, type, time_ny, note) for 2019-06-01 .. 2026-09-22 from official release records.

    python3 tools/build_events.py RAW_DIR [--out data/events.csv]

RAW_DIR holds the pages below, saved as fetched (bls.gov refuses scripted requests, so its three release-history
pages are taken from the Internet Archive's copies, e.g. https://web.archive.org/web/2026id_/<url>):
    fomc.html, fomc2019.html, fomc2020.html   federalreserve.gov/monetarypolicy/fomccalendars.htm, fomchistorical2019/2020.htm
    wb_cpi.html, wb_empsit.html, wb_ppi.html  bls.gov/bls/news-release/{cpi,empsit,ppi}.htm (archived release list,
                                              dates from the archive file names cpi_MMDDYYYY.htm)
    wb_sched_cpi.html                         bls.gov/schedule/news_release/cpi.htm (the Sep 2026 CPI date)
    gdp.json                                  bea.gov/news/archive, title 'Advance Estimate' (published dates; the NIPA
                                              data-archive folder dates are posting dates, often a day or more late)
    pce.json                                  bea.gov/news/archive, title 'Personal Income and Outlays' (published dates)
    bea2026.json                              bea.gov/news/schedule/full (2026 schedule rows: date, time, title)
    marts_dates.xls                           census.gov/retail/marts/www/MARTSreleasedates.xls (advance retail sales
                                              release dates, by release month)
opex is the standard rule (third Friday; the preceding business day when that Friday is an exchange holiday), and
early_close comes from the MNQ bars: an RTH day whose session stops before 16:00 (last bar followed by a halt).
"""
import sys, re, json, html, calendar, datetime as dt
import pandas as pd

raw = sys.argv[1]
out = sys.argv[sys.argv.index("--out") + 1] if "--out" in sys.argv else "data/events.csv"
LO, HI = dt.date(2019, 6, 1), dt.date(2026, 9, 22)
ev = []


def add(d, typ, t, note=""):
    if LO <= d <= HI:
        ev.append(dict(date=d.isoformat(), type=typ, time_ny=t, note=note))


def rd(name):
    return open(f"{raw}/{name}", encoding="utf-8", errors="ignore").read()


MONTHS = {m: i for i, m in enumerate(calendar.month_name) if m}

# ---- FOMC: the second (decision) day of each scheduled meeting; notation votes are not decision days
s = rd("fomc.html")
for m in re.finditer(r'<h4><a id="\d+">(\d{4}) FOMC Meetings</a></h4>(.*?)(?=<h4><a id=|\Z)', s, re.S):
    y = int(m.group(1))
    for mon, days in re.findall(r'fomc-meeting__month[^>]*><strong>([^<]+)</strong>.*?fomc-meeting__date[^>]*>([^<]+)<',
                                m.group(2), re.S):
        days = html.unescape(days).strip()
        if "notation" in days:
            continue
        mon_last = mon.split("/")[-1]
        day = int(re.findall(r"\d+", days)[-1])
        add(dt.date(y, MONTHS[mon_last] if len(mon_last) > 3 else list(calendar.month_abbr).index(mon_last), day),
            "FOMC", "14:00", "scheduled meeting, statement 14:00")
for y, f in ((2019, "fomc2019.html"), (2020, "fomc2020.html")):
    t = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", rd(f))))
    for mon, days, uns in re.findall(r"((?:January|February|March|April|May|June|July|August|September|October|November|"
                                     r"December)(?:/[A-Z][a-z]+)?) (\d{1,2}(?:-\d{1,2})?) (\(unscheduled\) )?Meeting", t):
        mon_last = mon.split("/")[-1]
        day = int(days.split("-")[-1])
        d = dt.date(y, MONTHS[mon_last], day)
        if uns:
            if d == dt.date(2020, 3, 2):       # statement released March 3, 2020, 10:00 ET (emergency 50 bp cut)
                add(dt.date(2020, 3, 3), "FOMC", "10:00", "unscheduled; statement released 10:00")
            else:                                # March 15, 2020 (Sunday), statement 17:00 ET
                add(d, "FOMC", "17:00", "unscheduled; Sunday, no cash session")
        else:
            add(d, "FOMC", "14:00", "scheduled meeting, statement 14:00")

# ---- BLS: CPI, Employment Situation (NFP), PPI from the archived release file names
for f, key, typ in (("wb_cpi.html", "cpi", "CPI"), ("wb_empsit.html", "empsit", "NFP"), ("wb_ppi.html", "ppi", "PPI")):
    for mo, da, yr in sorted(set(re.findall(key + r"_(\d{2})(\d{2})(\d{4})\.htm", rd(f)))):
        add(dt.date(int(yr), int(mo), int(da)), typ, "08:30", "BLS release archive")
t = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", rd("wb_sched_cpi.html"))))
for mon, day, yr in re.findall(r"[A-Z][a-z]+ \d{4} ([A-Z][a-z]{2,3})\. ?(\d{1,2}), (\d{4}) 08:30 AM", t):
    d = dt.datetime.strptime(f"{mon[:3]} {day} {yr}", "%b %d %Y").date()
    if not any(e["date"] == d.isoformat() and e["type"] == "CPI" for e in ev) and d <= HI:
        add(d, "CPI", "08:30", "BLS CPI release schedule")

# ---- BEA: GDP advance estimates and PCE (Personal Income and Outlays) from the news archive + the 2026 schedule
for d, title in json.load(open(f"{raw}/gdp.json")):
    add(dt.date.fromisoformat(d), "GDP_advance", "08:30", title)
sched = json.load(open(f"{raw}/bea2026.json"))
pce = {dt.date.fromisoformat(d): title for d, title in json.load(open(f"{raw}/pce.json")) if "Data Update" not in title}
for d, t, title in sched:                       # schedule rows after the archive's last entry
    dd = dt.datetime.strptime(f"{d} 2026", "%B %d %Y").date()
    if "Personal Income and Outlays" in title and dd not in pce:
        pce[dd] = title
times = {dt.datetime.strptime(f"{d} 2026", "%B %d %Y").date(): dt.datetime.strptime(t, "%I:%M %p").strftime("%H:%M")
         for d, t, title in sched if "Personal Income and Outlays" in title}
for d, title in sorted(pce.items()):
    add(d, "PCE", times.get(d, "08:30"), title)

# ---- Census: advance retail sales (release-month table; '**' = shutdown-delayed; '1, 18' = two releases that month)
x = pd.read_excel(f"{raw}/marts_dates.xls", header=None)
for _, r in x.iterrows():
    if not re.fullmatch(r"\d{4}", str(r[0]).strip()):
        continue
    y = int(str(r[0]).strip())
    for mon in range(1, 13):
        v = r[mon]
        if pd.isna(v):
            continue
        for day in re.findall(r"\d+", str(v)):
            add(dt.date(y, mon, int(day)), "retail_sales", "08:30",
                "Census MARTS release dates" + (" (shutdown-delayed)" if "**" in str(v) else ""))

# ---- opex: third Friday (preceding business day if an exchange holiday); quad witching in Mar / Jun / Sep / Dec
EXCH_HOLIDAY_FRIDAYS = {dt.date(2022, 4, 15): "Good Friday", dt.date(2025, 4, 18): "Good Friday",
                        dt.date(2026, 6, 19): "Juneteenth"}
for y in range(2019, 2027):
    for mo in range(1, 13):
        fridays = [d for d in (dt.date(y, mo, k) for k in range(1, 22)) if d.weekday() == 4]
        d = fridays[2]
        note = "quad witching" if mo in (3, 6, 9, 12) else "monthly"
        if d in EXCH_HOLIDAY_FRIDAYS:
            note += f"; moved to Thursday ({EXCH_HOLIDAY_FRIDAYS[d]})"
            d -= dt.timedelta(days=1)
        add(d, "opex", "09:30", note + "; AM-settled index options settle at the open")

# ---- early close: from the bars (RTH day whose session halts before 16:00)
b = pd.read_parquet("data/bars/MNQ_5m.parquet")
tod = b.index.hour * 60 + b.index.minute
nxt = b.index.to_series().shift(-1)
halt = (nxt - b.index.to_series()) > pd.Timedelta(minutes=30)
last = b[halt & (tod >= 570) & (tod < 955)]
for ts in last.index:
    d = ts.date()
    if not ((b.index.date == d) & (tod == 570)).any():
        continue
    end = (ts + pd.Timedelta(minutes=5)).strftime("%H:%M")
    # CME equity futures stop at 13:15 ET on NYSE half days and at 13:00 ET on exchange holidays with a Globex session
    add(d, "early_close", end, "NYSE half day" if end == "13:15" else "exchange holiday: CME Globex-only session")

df = pd.DataFrame(ev).drop_duplicates(["date", "type"]).sort_values(["date", "type"])
df.to_csv(out, index=False)
print(df.groupby("type").size().to_string())
print("weekend dates:", df[pd.to_datetime(df.date).dt.weekday > 4][["date", "type"]].values.tolist())
