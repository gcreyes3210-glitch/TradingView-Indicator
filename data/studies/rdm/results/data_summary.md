# RDM — stage 1 data summary

- **NQ (MNQ)**: 2,593,975 1m bars, 2019-06-02 18:00:00-04:00 → 2026-10-08 09:33:00-04:00, 1,902 trading days, 31 contracts
- **ES**: 2,596,464 1m bars, 2019-06-02 18:00:00-04:00 → 2026-10-08 09:33:00-04:00, 1,902 trading days, 31 contracts
- **Alignment**: 2,592,757 minutes in both; NQ minutes without ES 1,218; ES minutes without NQ 3,707
- **Cash-session coverage (09:30–15:59, NQ)**: 1,898 days; median 390 bars/day; days with < 390 bars 71 (early closes and gaps)
- **5m bars**: NQ 519,516, ES 519,706
- **15m bars**: NQ 173,222, ES 173,266
- **Roll days** (instrument change in the trading day, flagged and excluded): NQ 30, ES 30, union 42 (same day for both on 18; NQ and ES on different days on 24)
- **NQ/ES ratio jump** (day-median log ratio, change from the previous day): on roll days median 48.4 bp, max 147.4 bp; on other days median 27.1 bp
- **News days (08:30 / 10:00 ET releases, variant 5)**: 469 days (retail_sales 103, NFP 90, PPI 90, CPI 90, PCE 86, GDP_advance 28, FOMC 1)
- **Early-close days**: 64
- **Zones, sunrise only (primary), MNQ**: 5,602 zones; at 09:30 on average 33.9 active (12 trading days), 11.1 within ±1 % of price; 37.0 % of 09:30–15:00 1m bars touch at least one active zone (150 sampled days)
- **Zones, sunrise only (primary), ES**: 5,606 zones; at 09:30 on average 34.0 active (12 trading days), 14.9 within ±1 % of price; 39.2 % of 09:30–15:00 1m bars touch at least one active zone (150 sampled days)
- **Zones, all fractions (variant 7), MNQ**: 27,984 zones; at 09:30 on average 168.9 active (12 trading days), 54.6 within ±1 % of price; 83.5 % of 09:30–15:00 1m bars touch at least one active zone (150 sampled days)
- **Zones, all fractions (variant 7), ES**: 27,991 zones; at 09:30 on average 169.0 active (12 trading days), 73.8 within ±1 % of price; 85.8 % of 09:30–15:00 1m bars touch at least one active zone (150 sampled days)

**Parameters (defaults, pre-registered):** pivot_len 3, rsmt_window 5, entry_window 15, zone_days 12
