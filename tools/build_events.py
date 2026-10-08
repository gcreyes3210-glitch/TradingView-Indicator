#!/usr/bin/env python3
"""Build data/events.csv (date, type, time_ny, note) for 2019-06-01 .. --hi (default 2026-09-22) from official release
records and published schedules, and data/events_coverage.csv (type, covered_through): the last date each type's
sources reach. A date after a type's covered_through is unknown for that type, not a non-event day.

    python3 tools/build_events.py RAW_DIR [--out data/events.csv] [--hi 2027-12-31]

RAW_DIR holds the pages below, saved as fetched (bls.gov refuses scripted requests, so its three release-history
pages are taken from the Internet Archive's copies, e.g. https://web.archive.org/web/2026id_/<url>):
    fomc.html, fomc2019.html, fomc2020.html   federalreserve.gov/monetarypolicy/fomccalendars.htm, fomchistorical2019/2020.htm
    wb_cpi.html, wb_empsit.html, wb_ppi.html  bls.gov/bls/news-release/{cpi,empsit,ppi}.htm (archived release list,
                                              dates from the archive file names cpi_MMDDYYYY.htm)
    wb_sched_cpi.html                         bls.gov/schedule/news_release/cpi.htm (scheduled CPI dates)
    wb_sched_ppi.html, wb_sched_empsit.html   bls.gov/schedule/news_release/{ppi,empsit}.htm (optional; scheduled dates)
    gdp.json                                  bea.gov/news/archive, title 'Advance Estimate' (published dates; the NIPA
                                              data-archive folder dates are posting dates, often a day or more late)
    pce.json                                  bea.gov/news/archive, title 'Personal Income and Outlays' (published dates)
    bea2026.json                              bea.gov/news/schedule/full (2026 schedule rows: date, time, title)
    marts_dates.xls                           census.gov/retail/marts/www/MARTSreleasedates.xls (advance retail sales
                                              release dates, by release month)
    census_cal.html                           census.gov/economic-indicators/calendar-listview.html (optional; scheduled
                                              advance retail sales dates beyond the xls)
gdp.json, pce.json and bea2026.json are optional: without them the GDP_advance and PCE rows are carried over unchanged
from the existing --out file, and their coverage stays where it was.
opex is the standard rule (third Friday; the preceding business day when that Friday is an exchange holiday), and
early_close comes from the MNQ bars: an RTH day whose session stops before 16:00 (last bar followed by a halt).
"""
import sys, re, json, html, calendar, datetime as dt
import pandas as pd

raw = sys.argv[1]
out = sys.argv[sys.argv.index("--out") + 1] if "--out" in sys.argv else "data/events.csv"
LO = dt.date(2019, 6, 1)
HI = dt.date.fromisoformat(sys.argv[sys.argv.index("--hi") + 1]) if "--hi" in sys.argv else dt.date(2026, 9, 22)
ev = []
cover = {}                                      # type -> last date its sources reach


def add(d, typ, t, note=""):
    if LO <= d <= HI:
        ev.append(dict(date=d.isoformat(), type=typ, time_ny=t, note=note))


def seen(typ, d):
    cover[typ] = max(cover.get(typ, d), d)


def rd(name):
    return open(f"{raw}/{name}", encoding="utf-8", errors="ignore").read()


MONTHS = {m: i for i, m in enumerate(calendar.month_name) if m}
os_path = __import__("os").path

# ---- FOMC: the second (decision) day of each scheduled meeting; notation votes are not decision days
s = rd("fomc.html")
for m in re.finditer(r'<h4><a id="\d+">(\d{4}) FOMC Meetings</a></h4>(.*?)(?=<h4><a id=|\Z)', s, re.S):
    y = int(m.group(1))
    seen("FOMC", dt.date(y, 12, 31))
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
        d = dt.date(int(yr), int(mo), int(da))
        if d <= dt.date.today():                # the archive page can link releases that are only scheduled
            add(d, typ, "08:30", "BLS release archive")
            seen(typ, d)
for key, typ in (("cpi", "CPI"), ("ppi", "PPI"), ("empsit", "NFP")):
    if not os_path.exists(f"{raw}/wb_sched_{key}.html"):
        continue
    t = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", rd(f"wb_sched_{key}.html"))))
    for mon, day, yr in re.findall(r"[A-Z][a-z]+ \d{4} ([A-Z][a-z]{2,3})\. ?(\d{1,2}), (\d{4}) 08:30 AM", t):
        d = dt.datetime.strptime(f"{mon[:3]} {day} {yr}", "%b %d %Y").date()
        seen(typ, d)
        if not any(e["date"] == d.isoformat() and e["type"] == typ for e in ev):
            add(d, typ, "08:30", f"BLS {typ} release schedule")

# ---- BEA: GDP advance estimates and PCE (Personal Income and Outlays) from the news archive + the 2026 schedule
if not os_path.exists(f"{raw}/gdp.json"):           # no BEA sources: carry the existing rows and coverage
    old = pd.read_csv(out, dtype=str, keep_default_na=False)
    for _, r in old[old.type.isin(["GDP_advance", "PCE"])].iterrows():
        add(dt.date.fromisoformat(r.date), r.type, r.time_ny, r.note)
    oc = pd.read_csv(out.replace("events.csv", "events_coverage.csv")) if os_path.exists(
        out.replace("events.csv", "events_coverage.csv")) else None
    for typ in ("GDP_advance", "PCE"):
        c = oc[oc.type == typ].covered_through if oc is not None else []
        seen(typ, dt.date.fromisoformat(c.iloc[0]) if len(c) else dt.date(2026, 9, 22))
    print("BEA sources absent: GDP_advance and PCE rows carried over from", out)
else:
  for d, title in json.load(open(f"{raw}/gdp.json")):
    add(dt.date.fromisoformat(d), "GDP_advance", "08:30", title)
    seen("GDP_advance", dt.date.fromisoformat(d))
  sched = json.load(open(f"{raw}/bea2026.json"))
  pce = {dt.date.fromisoformat(d): title for d, title in json.load(open(f"{raw}/pce.json")) if "Data Update" not in title}
  for d, t, title in sched:                     # schedule rows after the archive's last entry
    dd = dt.datetime.strptime(f"{d} 2026", "%B %d %Y").date()
    if "Personal Income and Outlays" in title and dd not in pce:
        pce[dd] = title
  times = {dt.datetime.strptime(f"{d} 2026", "%B %d %Y").date(): dt.datetime.strptime(t, "%I:%M %p").strftime("%H:%M")
           for d, t, title in sched if "Personal Income and Outlays" in title}
  for d, title in sorted(pce.items()):
    add(d, "PCE", times.get(d, "08:30"), title)
    seen("PCE", d)

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
            seen("retail_sales", dt.date(y, mon, int(day)))
if os_path.exists(f"{raw}/census_cal.html"):
    t = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " | ", rd("census_cal.html"))))
    for d, tm in re.findall(r"Advance Monthly Sales for Retail and Food Services \| \| \| (\w+ \d+, \d{4}) \| \| (8:30 AM)", t):
        d = dt.datetime.strptime(d, "%B %d, %Y").date()
        seen("retail_sales", d)
        if not any(e["date"] == d.isoformat() and e["type"] == "retail_sales" for e in ev):
            add(d, "retail_sales", "08:30", "Census economic indicator calendar")

# ---- opex: third Friday (preceding business day if an exchange holiday); quad witching in Mar / Jun / Sep / Dec
EXCH_HOLIDAY_FRIDAYS = {dt.date(2022, 4, 15): "Good Friday", dt.date(2025, 4, 18): "Good Friday",
                        dt.date(2026, 6, 19): "Juneteenth", dt.date(2027, 6, 18): "Juneteenth observed"}
for y in range(2019, HI.year + 1):
    for mo in range(1, 13):
        fridays = [d for d in (dt.date(y, mo, k) for k in range(1, 22)) if d.weekday() == 4]
        d = fridays[2]
        note = "quad witching" if mo in (3, 6, 9, 12) else "monthly"
        if d in EXCH_HOLIDAY_FRIDAYS:
            note += f"; moved to Thursday ({EXCH_HOLIDAY_FRIDAYS[d]})"
            d -= dt.timedelta(days=1)
        add(d, "opex", "09:30", note + "; AM-settled index options settle at the open")
cover["opex"] = HI                              # a rule, known for every date

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
cover["early_close"] = b.index[-1].date() - dt.timedelta(days=1)    # last complete day in the bars

df = pd.DataFrame(ev).drop_duplicates(["date", "type"]).sort_values(["date", "type"])
df.to_csv(out, index=False)
cv = pd.DataFrame([dict(type=k, covered_through=min(v, HI).isoformat()) for k, v in sorted(cover.items())])
cv.to_csv(out.replace("events.csv", "events_coverage.csv"), index=False)
print(cv.to_string(index=False))
print(df.groupby("type").size().to_string())
print("weekend dates:", df[pd.to_datetime(df.date).dt.weekday > 4][["date", "type"]].values.tolist())
