# RDM — report

> **5 baseline trades in 7.3 years cannot support a verdict.** The numbers below describe what this coded reading did; they cannot tell a real edge from luck. Read every table with its n.

Coded reading of the Ryze Divergence Model as pre-registered in BACKTEST_LOG.md ("RDM"), with the logged amendments: (1) early-close and holiday sessions excluded; (2) the IFVG-1m inverse-FVG definition with entry at the inverting close (results-aware: made after the first report, commit 839290d). MNQ for NQ, Databento 1m, 2019-06 → 2026-10-07, roll days excluded, $1 per side + 1 tick per fill, 1 MNQ. 8 runs, Bonferroni α = 0.05 / 8 = 0.00625.

## Detection funnel (baseline)

| Step | Count | Removed by this step |
|---|---|---|
| 1m SMT (sweep 09:14-14:59) | 34647 |  |
| validated on 5m | 1981 | 32666 |
| inverse-FVG candidate (gap ≥ 1 pt) in the move | 1127 | 854 |
| fresh inversion (IFVG-1m, within 5 bars) in the window, SMT known | 82 | 1045 |
| RSMT | 69 | 13 |
| not cancelled = setup | 10 | 59 |
| grade allowed (A; B in variant 1) | 6 | 4 |
| after the variant's setup filter | 6 | 0 |
| trades | 5 | 1 |
| skip: final target < 2R | 1 | |

Steps 1–6 count 1m SMT events of both grades. A step's removals: the event fails that condition. Skips are setups that reached the trade rules and were not taken.

## All runs

| Run | n | Win % | R / trade | $ / trade | Net $ | PF | Max DD (R) | Longest losing streak | 95 % CI mean R | p | Positive years | R 2019–22 (n) | R 2023–26 (n) | R first 70 % (n) | R last 30 % (n) | Neighbours R (pivot_len 2 / 4, n) | Passes |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| baseline | 5 | 80.0 | +1.229 | +52.1 | +260 | 8.04 | -1.07 | 1 | -0.192 to +2.869 | 0.058 | 2 of 8 | 1.128 (2) | 1.296 (3) | 1.128 (2) | 1.296 (3) | -1.098 (5) / 0.618 (6) | no |
| V1 Grade B included | 9 | 55.6 | +0.352 | +21.2 | +191 | 2.55 | -2.14 | 2 | -0.626 to +1.557 | 0.295 | 2 of 8 | 0.354 (3) | 0.351 (6) | 0.354 (3) | 0.351 (6) | -0.531 (8) / 0.376 (8) | no |
| V2 15m SMT required | 1 | 100.0 | +0.711 | +29.5 | +30 | None | 0.0 | 0 | +0.711 to +0.711 | 0.000 | 1 of 8 | None (0) | 0.711 (1) | None (0) | 0.711 (1) | None (0) / None (0) | no |
| V3 sweep takes an untaken session level | 0 | | | | | | | | | | | | | | | None / -1.035 | no |
| V4 stop at the most recent 1m swing | 6 | 66.7 | +1.199 | +41.0 | +246 | 5.78 | -1.11 | 1 | -0.501 to +2.966 | 0.079 | 2 of 8 | 1.114 (3) | 1.284 (3) | 1.114 (3) | 1.284 (3) | -1.152 (5) / 0.222 (8) | no |
| V5 skip 08:30 / 10:00 news days | 4 | 75.0 | +0.474 | +13.6 | +54 | 2.47 | -1.07 | 1 | -0.627 to +1.538 | 0.153 | 1 of 8 | 1.128 (2) | -0.181 (2) | 1.128 (2) | -0.181 (2) | -1.098 (5) / 0.138 (4) | no |
| V6 first trade of the day only | 5 | 80.0 | +1.229 | +52.1 | +260 | 8.04 | -1.07 | 1 | -0.192 to +2.869 | 0.058 | 2 of 8 | 1.128 (2) | 1.296 (3) | 1.128 (2) | 1.296 (3) | -1.098 (5) / 0.618 (6) | no |
| V7 zones of all fractions | 0 | | | | | | | | | | | | | | | None / None | no |

The 70 / 30 split cuts at 2024-07-22 (70 % of the 1796 eligible trading days).

## Baseline breakdowns (n is tiny; descriptive only)

- **By month:** 9 1 trades, -1.07 R · 10 1 trades, +0.71 R · 11 2 trades, +2.28 R · 12 1 trades, +1.95 R
- **By weekday:** Fri 4 trades, +1.46 R · Thu 1 trades, +0.31 R
- **By hour:** 9 1 trades, +1.95 R · 11 2 trades, +1.59 R · 12 1 trades, +0.71 R · 13 1 trades, +0.31 R
- **By side:** long 3 trades, +0.99 R · short 2 trades, +1.59 R
- **By exit:** BE 1 trades, +0.31 R · final target 1 trades, +1.95 R · flat 15:55 2 trades, +2.48 R · stop 1 trades, -1.07 R
- **By year:** 2021 2 trades, +1.13 R · 2024 3 trades, +1.30 R

Baseline trades: 2021-11-11 long +0.31 R (BE), 2021-12-31 long +1.95 R (final target), 2024-09-13 short -1.07 R (stop), 2024-10-18 long +0.71 R (flat 15:55), 2024-11-01 short +4.25 R (flat 15:55)


## Change from the first report (amendment 2)

With the IFVG-1m inverse-FVG definition (gap ≥ 1 point, inversion within 5 bars of the gap, entry at the inverting close), the baseline falls **from 16 trades (15 after amendment 1) to 5**.
- **What stays:** all 5 were among the original 16, with the same sweep bars; every entry price differs, because entry is now at the inverting close.
- **What goes:** 11 drop out. The freshness rule does most of it: 1,127 gap candidates → 82 fresh inversions.
- **Against the user's round-1 chart check:** the 2 surviving charts (2021-12-31, 2024-10-18) are both ones the user marked right. The 8 that dropped are 2 the user marked right (2019-06-12, 2024-04-03) and all 6 marked wrong.
- **Charts:** the new set is `data/studies/rdm/charts/rdm_01…05.png`; only 5 trades exist, so only 5 can be shown. Round 1 is kept in `charts/round1/` with `answers_round1.csv`.
- **Caveat:** this amendment was made after the first report was seen, so it is not a blind test.

## Verdict (plain language)

**5 baseline trades in 7.3 years cannot support any verdict, and the original 16 could not either.**
- **Baseline:** +1.23 R per trade, but the 95 % bootstrap interval is −0.19 to +2.87 R, p = 0.058, and only 2 of 8 years have a trade that nets positive.
- **Concentration:** one trade (2024-11-01, +4.25 R held to 15:55) is most of it; the other four average +0.48 R.
- **Neighbours disagree:** `pivot_len` 2 gives −1.10 R on 5 trades and `pivot_len` 4 gives +0.62 R on 6.
- **No run passes the usual criterion.** V3 (session level) and V7 (all fractions) have no trades at all. V2's p of 0.000 is a single trade and means nothing.
- **Bottom line:** at well under one trade a year, this rule set would need decades to show whether it has an edge. On this coding the answer is **not enough data to tell**, and nothing is adopted.

**The three assumptions most likely to change the result:**
1. **The inverse-FVG rule itself.** Changing it from the most recent gap to the IFVG-1m freshness rule moved the baseline from 16 trades to 5. The trade count, and with it any conclusion, hangs on this one choice.
2. **The SMT definition and its timeframe.** The 1m live-sweep SMT validated by a 5m sweep in the same bar removes 32,666 of 34,647 SMT events, and the neighbours flip sign.
3. **The 12-day zone life and the RSMT cancel rule.** About 34 sunrise zones are active at any time; the cancel rule removes 59 of 69 RSMT-qualified setups here, and with all fractions (V7) nothing is left.
