#!/usr/bin/env python3
"""Zone reconstruction for the Ryze indicator (ARZ v2.6a): candidate rules, rendered for visual comparison.

    python3 tools/rdm_zones.py render [--days 2026-10-06 2026-10-07 2026-10-08]

Hypothesis under test: for each city (New York, London, Tokyo) and day, approximate sunrise and sunset (the classic
almanac algorithm), times taken at a fixed UTC-5 offset (no daylight saving), day length = sunset - sunrise or 12 hours,
event times at sunrise + f x day length for f in 0, 0.25, 0.5, 0.75, 1.0. A zone is the high / low of the candle on a
fixed timeframe whose open is at or before the event time and whose next open is after it. Candidate timeframes 1, 5,
15, 30, 60 minutes; zenith 90.833 deg (with atmospheric refraction) or 90 deg (without).

Event dates: each city's events for its local dates D-1, D and D+1 are computed as true instants; the chart for
trading day D (18:00 the evening before to 17:00) shows the ones that fall inside it. An indicator that wraps the
algorithm's UTC hour modulo 24 into the same date would put Tokyo's events about one day later, which is within a
minute of the next local date's true event, so both readings appear on the same chart.
Two readings of "converted to UTC-5 with no daylight saving": (instant) the event's true moment, drawn where it falls on
the New York chart; (clock) the UTC-5 clock reading placed at that clock time on the New York chart, which during
daylight saving puts every event one hour earlier. Charts *_clock.png use the second reading.
Nothing here builds zones.csv: that waits for observed zones that match, or a visual confirmation.
"""
import sys, math, pathlib
import numpy as np
import pandas as pd

TZ = "America/New_York"
CITIES = {"NY": (40.7128, -74.0060), "London": (51.5074, -0.1278), "Tokyo": (35.6762, 139.6503)}
FRACS = (0.0, 0.25, 0.5, 0.75, 1.0)
TFS = (1, 5, 15, 30, 60)
OUT = pathlib.Path("data/studies/rdm")
UTC_M5 = "Etc/GMT+5"                     # fixed UTC-5, no daylight saving


def sun_ut(date, lat, lon, zenith, rising):
    """UTC hour (0-24, may wrap) of sunrise / sunset on calendar date `date` (Almanac for Computers, 1990)."""
    n = date.timetuple().tm_yday
    lng_hour = lon / 15.0
    t = n + ((6 if rising else 18) - lng_hour) / 24.0
    M = 0.9856 * t - 3.289
    L = (M + 1.916 * math.sin(math.radians(M)) + 0.020 * math.sin(math.radians(2 * M)) + 282.634) % 360
    RA = math.degrees(math.atan(0.91764 * math.tan(math.radians(L)))) % 360
    RA = (RA + (math.floor(L / 90) * 90 - math.floor(RA / 90) * 90)) / 15.0
    sin_dec = 0.39782 * math.sin(math.radians(L))
    cos_dec = math.cos(math.asin(sin_dec))
    cos_h = (math.cos(math.radians(zenith)) - sin_dec * math.sin(math.radians(lat))) / (cos_dec * math.cos(math.radians(lat)))
    H = (360 - math.degrees(math.acos(cos_h))) if rising else math.degrees(math.acos(cos_h))
    T = H / 15.0 + RA - 0.06571 * t - 6.622
    return (T - lng_hour) % 24


def sun_instant(local_date, lat, lon, zenith, rising):
    """True UTC instant of the event on the city's local date (the algorithm's UTC hour placed on the right UTC day)."""
    ut = sun_ut(local_date, lat, lon, zenith, rising)
    base = pd.Timestamp(local_date).tz_localize("UTC")
    t = base + pd.Timedelta(hours=ut)
    approx_local_noon = base + pd.Timedelta(hours=12 - lon / 15.0)        # the event lies within ~12 h of local noon
    while t - approx_local_noon > pd.Timedelta(hours=12):
        t -= pd.Timedelta(days=1)
    while approx_local_noon - t > pd.Timedelta(hours=12):
        t += pd.Timedelta(days=1)
    return t


def events(day, refraction=True, twelve=False):
    """All event instants (UTC) from local dates day-1 .. day+1 for every city: list of (city, local date, f, instant)."""
    zen = 90.833 if refraction else 90.0
    out = []
    for city, (lat, lon) in CITIES.items():
        for dd in (-1, 0, 1):
            ld = (pd.Timestamp(day) + pd.Timedelta(days=dd)).date()
            rise = sun_instant(ld, lat, lon, zen, True)
            length = pd.Timedelta(hours=12) if twelve else sun_instant(ld, lat, lon, zen, False) - rise
            for f in FRACS:
                out.append((city, ld, f, rise + f * length))
    return out


def candle(bars, t):
    """The bar whose open is at or before t and whose next open is after it."""
    i = bars.index.searchsorted(t, side="right") - 1
    if i < 0 or i + 1 >= len(bars):
        return None
    return bars.index[i], bars.high.iloc[i], bars.low.iloc[i]


def render(days, clock=False):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle
    a = pd.read_parquet("data/bars/MNQ_1m.parquet")
    agg = {"open": "first", "high": "max", "low": "min", "close": "last"}
    TFB = {k: (a if k == 1 else a.resample(f"{k}min", label="left", closed="left").agg(agg).dropna()) for k in TFS}
    b5 = TFB[5]
    out = OUT / "render"; out.mkdir(parents=True, exist_ok=True)
    colors = {"NY": "#1565c0", "London": "#2e7d32", "Tokyo": "#c62828"}
    rows = []
    for day in days:
        d0 = pd.Timestamp(day).tz_localize(TZ)
        w0, w1 = d0 - pd.Timedelta(hours=6), d0 + pd.Timedelta(hours=17)          # 18:00 the evening before -> 17:00
        x = b5[(b5.index >= w0) & (b5.index < w1)]
        if x.empty:
            print(f"{day}: no bars"); continue
        for tf in TFS:
            fig, axes = plt.subplots(2, 2, figsize=(26, 15))
            for ax, (twelve, refr) in zip(axes.flat, ((False, True), (False, False), (True, True), (True, False))):
                for k, (o, h, l, c) in enumerate(zip(x.open, x.high, x.low, x.close)):
                    col = "#26a69a" if c >= o else "#ef5350"
                    ax.plot([k, k], [l, h], color=col, lw=0.6)
                    ax.add_patch(Rectangle((k - 0.35, min(o, c)), 0.7, max(abs(c - o), 0.05), color=col, lw=0))
                xof = lambda t_: (t_ - x.index[0]) / pd.Timedelta(minutes=5)
                lo_, hi_ = x.low.min(), x.high.max()
                for city, ld, f, inst in events(day, refraction=refr, twelve=twelve):
                    t_ny = inst.tz_convert(UTC_M5).tz_localize(None).tz_localize(TZ) if clock else inst.tz_convert(TZ)
                    if not (w0 <= t_ny < w1):
                        continue
                    cd = candle(TFB[tf], t_ny)
                    if cd is None:
                        continue
                    t_open, zh, zl = cd
                    col = colors[city]
                    xs = xof(t_ny)
                    ax.add_patch(Rectangle((xs, zl), len(x) - xs, max(zh - zl, 0.25), color=col, alpha=0.18, lw=0))
                    ax.plot([xs, xs], [zl, zh], color=col, lw=2)
                    ax.text(xs, zh, f" {city} {f:g} ({ld:%m-%d}) {t_ny:%H:%M}", fontsize=7, color=col, va="bottom", clip_on=True)
                    rows.append(dict(day=day, tf=tf, reading="clock" if clock else "instant", day_length="12h" if twelve else "sunset", refraction=refr, city=city,
                                     local_date=ld, fraction=f, event_ny=t_ny.strftime("%Y-%m-%d %H:%M:%S"),
                                     event_utc_m5=inst.tz_convert(UTC_M5).strftime("%Y-%m-%d %H:%M:%S"),
                                     candle_open_ny=t_open.strftime("%Y-%m-%d %H:%M"), zone_high=zh, zone_low=zl))
                ticks = [k for k, t_ in enumerate(x.index) if t_.minute == 0 and t_.hour % 2 == 0]
                ax.set_xticks(ticks, [x.index[k].strftime("%H:%M") for k in ticks], fontsize=7)
                ax.set_xlim(-1, len(x) + 2)
                ax.set_ylim(lo_ - 0.02 * (hi_ - lo_), hi_ + 0.05 * (hi_ - lo_))
                ax.set_title(f"day length = {'sunrise + 12 h' if twelve else 'sunrise to sunset'} · "
                             f"{'with' if refr else 'without'} refraction (zenith {90.833 if refr else 90.0})", fontsize=10, loc="left")
                ax.grid(alpha=0.15)
            fig.suptitle(f"Ryze zone candidates · MNQ 5m, trading day {day} (18:00 the evening before -> 17:00 New York time) · "
                         f"zone = high/low of the {tf}m candle covering each event · label: city, fraction of the day "
                         f"length, city's local date, event time (New York) · blue NY, green London, red Tokyo · "
                         f"{'CLOCK reading: UTC-5 clock time placed at that New York clock time' if clock else 'INSTANT reading: true event time'}", fontsize=11)
            fig.tight_layout()
            fig.savefig(out / f"rdm_{day}_{tf}m{'_clock' if clock else ''}.png", dpi=80)
            plt.close(fig)
        print(f"{day}: {len(TFS)} charts")
    R = pd.DataFrame(rows)
    f = out / "candidate_zones.csv"
    if clock and f.exists():
        R = pd.concat([pd.read_csv(f), R], ignore_index=True)
    R.to_csv(f, index=False)
    print(f"{len(R)} candidate zones listed in {out / 'candidate_zones.csv'}")
    return R


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "render"
    days = sys.argv[sys.argv.index("--days") + 1:] if "--days" in sys.argv else ["2026-10-06", "2026-10-07", "2026-10-08"]
    if cmd == "render":
        render(days)
        render(days, clock=True)
