#!/usr/bin/env python3
"""Databento GLBX.MDP3 ohlcv-1m DBN file -> data/bars/ Parquet (America/New_York).

    python3 tools/build_bars.py MNQ_ohlcv1m.dbn.zst MNQ

Writes <SYM>_1m.parquet and <SYM>_5m.parquet. 5m bars are stamped with their open time:
the 09:30 bar covers 09:30:00-09:34:59 (same as TradingView). instrument_id is kept so that
contract rolls can be traced (continuous .v.0 = front by volume, no back-adjustment).
"""
import sys, pathlib, databento as db, pandas as pd

src, sym = sys.argv[1], sys.argv[2]
out = pathlib.Path(__file__).resolve().parent.parent / "data" / "bars"
out.mkdir(parents=True, exist_ok=True)

df = db.DBNStore.from_file(src).to_df(price_type="float", pretty_ts=True, map_symbols=False)
df = df[["instrument_id", "open", "high", "low", "close", "volume"]]
df.index = df.index.tz_convert("America/New_York")
df.index.name = "ts"
df.to_parquet(out / f"{sym}_1m.parquet")

b5 = df.resample("5min", label="left", closed="left").agg(
    {"instrument_id": "last", "open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
).dropna(subset=["open"])
b5["instrument_id"] = b5["instrument_id"].astype("uint32")
b5.to_parquet(out / f"{sym}_5m.parquet")
print(f"1m {len(df):,} bars  5m {len(b5):,} bars  {df.index[0]} -> {df.index[-1]}")
print("instrument changes:", int((df["instrument_id"] != df["instrument_id"].shift()).sum()) - 1)
