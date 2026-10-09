#!/usr/bin/env python3
"""RDM: the Ryze Divergence Model, as pre-registered in BACKTEST_LOG.md ("RDM").

    python3 tools/rdm.py summary        stage 1: data inspection -> data/studies/rdm/results/data_summary.md

Data: Databento MNQ ("NQ") and ES 1m bars, New York time, aligned on MNQ's minutes; 5m / 15m bars built from 1m.
Zones: data/studies/rdm/zones.csv (verified reconstruction of the Ryze indicator).
"""
import sys, pathlib
import numpy as np
import pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from ifvg_engine import trading_date

TZ = "America/New_York"
ROOT = pathlib.Path("data/studies/rdm")
RES = ROOT / "results"
ZONE_DAYS = 12
P = dict(pivot_len=3, rsmt_window=5, entry_window=15, zone_days=ZONE_DAYS)
AGG = {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}


def load():
    nq = pd.read_parquet("data/bars/MNQ_1m.parquet")
    es = pd.read_parquet("data/bars/ES_1m.parquet")
    return nq, es


def bars(x, k):
    return x.resample(f"{k}min", label="left", closed="left").agg(AGG).dropna(subset=["open"])


def roll_days(nq, es):
    """Trading days on which either market's instrument changes."""
    out = {}
    for nm, x in (("NQ", nq), ("ES", es)):
        td = trading_date(x.index)
        g = pd.Series(x.instrument_id.to_numpy(), index=td).groupby(level=0).agg(["first", "last"])
        ch = (g["first"] != g["last"]) | (g["first"] != g["last"].shift(1))
        ch.iloc[0] = False
        out[nm] = set(g.index[ch])
    return out


def zones(symbol, fractions=(0.0,)):
    z = pd.read_csv(ROOT / "zones.csv")
    z = z[(z.symbol == symbol) & z.fraction.isin(fractions)].copy()
    z["event"] = pd.to_datetime(z.event_time_et).dt.tz_localize(TZ, ambiguous="NaT", nonexistent="shift_forward")
    z["live_from"] = z.event.dt.floor("min") + pd.Timedelta(minutes=1)          # known at the event candle's close
    z["zid"] = z.city + "|" + z.fraction.astype(str) + "|" + z.created_date
    return z.dropna(subset=["event"])


def active_until(z, tdays):
    """Each zone is active for ZONE_DAYS trading days from its event: until the start of the trading day ZONE_DAYS later."""
    tdays = pd.DatetimeIndex(sorted(tdays))
    k = tdays.searchsorted(trading_date(pd.DatetimeIndex(z.event)).to_numpy())
    end_day = tdays[np.minimum(k + ZONE_DAYS, len(tdays) - 1)]
    return (end_day - pd.Timedelta(hours=6)).tz_localize(TZ)                       # 18:00 the evening before


def summary():
    RES.mkdir(parents=True, exist_ok=True)
    nq, es = load()
    L = []
    w = L.append
    w("# RDM — stage 1 data summary\n")
    for nm, x in (("NQ (MNQ)", nq), ("ES", es)):
        td = trading_date(x.index)
        w(f"- **{nm}**: {len(x):,} 1m bars, {x.index[0]} → {x.index[-1]}, {pd.Index(td).nunique():,} trading days, "
          f"{x.instrument_id.nunique()} contracts")
    common = nq.index.intersection(es.index)
    w(f"- **Alignment**: {len(common):,} minutes in both; NQ minutes without ES {len(nq.index.difference(es.index)):,}; "
      f"ES minutes without NQ {len(es.index.difference(nq.index)):,}")
    tod = nq.index.hour * 60 + nq.index.minute
    cash = nq[(tod >= 570) & (tod < 960)]
    per = cash.groupby(cash.index.date).size()
    w(f"- **Cash-session coverage (09:30–15:59, NQ)**: {len(per):,} days; median {per.median():.0f} bars/day; "
      f"days with < 390 bars {int((per < 390).sum())} (early closes and gaps)")
    for k in (5, 15):
        w(f"- **{k}m bars**: NQ {len(bars(nq, k)):,}, ES {len(bars(es, k)):,}")
    R = roll_days(nq, es)
    both = R["NQ"] & R["ES"]
    w(f"- **Roll days** (instrument change in the trading day, flagged and excluded): NQ {len(R['NQ'])}, ES {len(R['ES'])}, "
      f"union {len(R['NQ'] | R['ES'])} (same day for both on {len(both)}; NQ and ES on different days on "
      f"{len(R['NQ'] ^ R['ES'])})")
    # price jump at the roll: NQ/ES log-ratio change across the roll minute
    lr = np.log(nq.close.reindex(common)) - np.log(es.close.reindex(common))
    tdc = trading_date(common)
    day_med = lr.groupby(tdc).median()
    jumps = day_med.diff().abs()
    rd = sorted(R["NQ"] | R["ES"])
    w(f"- **NQ/ES ratio jump** (day-median log ratio, change from the previous day): on roll days median "
      f"{jumps.reindex(rd).median() * 1e4:.1f} bp, max {jumps.reindex(rd).max() * 1e4:.1f} bp; on other days median "
      f"{jumps.drop(rd, errors='ignore').median() * 1e4:.1f} bp")
    ev = pd.read_csv("data/events.csv")
    news = ev[ev.time_ny.isin(["08:30", "10:00"]) & ~ev.type.isin(["opex", "early_close"])]
    w(f"- **News days (08:30 / 10:00 ET releases, variant 5)**: {news.date.nunique():,} days "
      f"({', '.join(f'{k} {v}' for k, v in news.type.value_counts().items())})")
    w(f"- **Early-close days**: {ev[ev.type == 'early_close'].date.nunique()}")
    # zones
    tdays = pd.Index(trading_date(nq.index)).unique()
    for frac, lab in (((0.0,), "sunrise only (primary)"), ((0.0, 0.25, 0.5, 0.75, 1.0), "all fractions (variant 7)")):
        for sym, x in (("MNQ", nq), ("ES", es)):
            z = zones(sym, frac)
            z["until"] = active_until(z, tdays)
            # active zones at each day's 09:30 and the share of 09:30-15:00 1m bars touching an active zone
            samp = x[(tod_ := (x.index.hour * 60 + x.index.minute)) >= 570]
            samp = samp[(samp.index.hour * 60 + samp.index.minute) < 900]
            days = pd.Index(samp.index.normalize().unique())
            take = days[np.linspace(0, len(days) - 1, min(150, len(days))).astype(int)]     # 150 days spread over the span
            n_act, n_near, touch = [], [], []
            for d in take:
                t0 = d + pd.Timedelta(hours=9, minutes=30)
                a_ = z[(z.live_from <= t0) & (z.until > t0)]
                px = x.close.asof(t0)
                n_act.append(len(a_)); n_near.append(int(((a_.zone_low <= px * 1.01) & (a_.zone_high >= px * 0.99)).sum()))
                day = samp.loc[d: d + pd.Timedelta(hours=23)]
                lo_, hi_ = day.low.to_numpy()[:, None], day.high.to_numpy()[:, None]
                act = z[(z.live_from <= day.index[-1]) & (z.until > day.index[0])]
                hit = (lo_ <= act.zone_high.to_numpy()[None, :]) & (hi_ >= act.zone_low.to_numpy()[None, :])
                touch.append(hit.any(axis=1).mean() if hit.size else 0.0)
            w(f"- **Zones, {lab}, {sym}**: {len(z):,} zones; at 09:30 on average {np.mean(n_act):.1f} active "
              f"(12 trading days), {np.mean(n_near):.1f} within ±1 % of price; {100 * np.mean(touch):.1f} % of 09:30–15:00 "
              f"1m bars touch at least one active zone (150 sampled days)")
    w("\n**Parameters (defaults, pre-registered):** " + ", ".join(f"{k} {v}" for k, v in P.items()))
    txt = "\n".join(L)
    (RES / "data_summary.md").write_text(txt + "\n")
    print(txt)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "summary"
    if cmd == "summary":
        summary()
