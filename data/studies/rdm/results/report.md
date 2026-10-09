# RDM — report

> **16 baseline trades in 7.3 years cannot support a verdict.** The numbers below describe what this coded reading did; they cannot tell a real edge from luck. Read every table with its n.

Coded reading of the Ryze Divergence Model as pre-registered in BACKTEST_LOG.md ("RDM"), with the logged amendment (early-close and holiday sessions excluded). MNQ for NQ, Databento 1m, 2019-06 → 2026-10-07, roll days excluded, $1 per side + 1 tick per fill, 1 MNQ. 8 runs, Bonferroni α = 0.05 / 8 = 0.00625.

## Detection funnel (baseline)

| Step | Count | Removed by this step |
|---|---|---|
| 1m SMT (sweep 09:14-14:59) | 34647 |  |
| validated on 5m | 1981 | 32666 |
| inverse-FVG candidate in the move | 1317 | 664 |
| close through the gap in the window (SMT known) | 568 | 749 |
| RSMT | 447 | 121 |
| not cancelled = setup | 53 | 394 |
| grade allowed (A; B in variant 1) | 27 | 26 |
| after the variant's setup filter | 27 | 0 |
| trades | 15 | 12 |
| skip: final target < 2R | 5 | |
| skip: no TP1 | 1 | |
| skip: no untaken session level beyond TP1 | 6 | |

Steps 1–6 count 1m SMT events of both grades. A step's removals: the event fails that condition. Skips are setups that reached the trade rules and were not taken.

## All runs

| Run | n | Win % | R / trade | $ / trade | Net $ | PF | Max DD (R) | Longest losing streak | 95 % CI mean R | p | Positive years | R 2019–22 (n) | R 2023–26 (n) | R first 70 % (n) | R last 30 % (n) | Neighbours R (pivot_len 2 / 4, n) | Passes |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| baseline | 15 | 66.7 | +0.508 | +11.7 | +175 | 1.68 | -2.13 | 2 | -0.221 to +1.335 | 0.099 | 4 of 8 | 0.628 (9) | 0.328 (6) | 0.583 (10) | 0.358 (5) | -0.735 (19) / 0.737 (8) | no |
| V1 Grade B included | 33 | 51.5 | +0.482 | +13.0 | +430 | 1.71 | -5.46 | 4 | -0.228 to +1.323 | 0.104 | 4 of 8 | 0.518 (16) | 0.447 (17) | 0.925 (20) | -0.2 (13) | -0.227 (35) / 0.091 (20) | no |
| V2 15m SMT required | 1 | 100.0 | +0.690 | +29.0 | +29 | None | 0.0 | 0 | +0.690 to +0.690 | 0.000 | 1 of 8 | None (0) | 0.69 (1) | None (0) | 0.69 (1) | None (0) / None (0) | no |
| V3 sweep takes an untaken session level | 0 | | | | | | | | | | | | | | | None / -1.035 | no |
| V4 stop at the most recent 1m swing | 16 | 62.5 | +0.668 | +10.1 | +161 | 1.6 | -2.13 | 2 | -0.231 to +1.715 | 0.082 | 4 of 8 | 0.876 (10) | 0.321 (6) | 0.813 (11) | 0.35 (5) | -0.75 (19) / 0.544 (11) | no |
| V5 skip 08:30 / 10:00 news days | 10 | 70.0 | +0.354 | +2.2 | +22 | 1.18 | -2.51 | 2 | -0.358 to +1.136 | 0.181 | 3 of 8 | 1.175 (5) | -0.467 (5) | 1.009 (6) | -0.629 (4) | -0.871 (15) / 0.833 (6) | no |
| V6 first trade of the day only | 15 | 66.7 | +0.508 | +11.7 | +175 | 1.68 | -2.13 | 2 | -0.221 to +1.335 | 0.099 | 4 of 8 | 0.628 (9) | 0.328 (6) | 0.583 (10) | 0.358 (5) | -0.735 (19) / 0.737 (8) | no |
| V7 zones of all fractions | 3 | 33.3 | -0.647 | -60.1 | -180 | 0.09 | -1.02 | 2 | -1.066 to +0.142 | 0.961 | 1 of 8 | None (0) | -0.647 (3) | None (0) | -0.647 (3) | -0.148 (5) / -0.88 (3) | no |

The 70 / 30 split cuts at 2024-07-22 (70 % of the 1796 eligible trading days).

## Baseline breakdowns (n is tiny; descriptive only)

- **By month:** 3 1 trades, -1.02 R · 4 3 trades, +0.03 R · 5 1 trades, +0.27 R · 6 1 trades, -1.28 R · 8 2 trades, +0.83 R · 9 1 trades, -1.07 R · 10 1 trades, +0.69 R · 11 3 trades, +1.18 R · 12 2 trades, +2.36 R
- **By weekday:** Fri 5 trades, +0.94 R · Mon 3 trades, +0.69 R · Thu 2 trades, +0.44 R · Tue 1 trades, -1.02 R · Wed 4 trades, +0.24 R
- **By hour:** 9 2 trades, +0.41 R · 11 2 trades, +1.62 R · 12 6 trades, +0.73 R · 13 4 trades, -0.24 R · 14 1 trades, +0.18 R
- **By side:** long 7 trades, +0.37 R · short 8 trades, +0.63 R
- **By exit:** BE 4 trades, +0.33 R · final target 1 trades, +1.84 R · flat 15:55 5 trades, +1.99 R · stop 5 trades, -1.10 R
- **By year:** 2019 2 trades, +0.81 R · 2020 1 trades, +0.99 R · 2021 4 trades, +0.87 R · 2022 2 trades, -0.22 R · 2024 5 trades, +0.61 R · 2026 1 trades, -1.07 R

Baseline trades: 2019-06-12 long -1.28 R (stop), 2019-12-23 short +2.89 R (flat 15:55), 2020-04-15 long +0.99 R (flat 15:55), 2021-05-24 short +0.27 R (BE), 2021-08-11 long +1.09 R (flat 15:55), 2021-11-11 long +0.30 R (BE), 2021-12-31 long +1.84 R (final target), 2022-03-15 long -1.02 R (stop), 2022-08-25 short +0.58 R (BE), 2024-04-03 short +0.18 R (BE), 2024-09-13 short -1.07 R (stop), 2024-10-18 long +0.69 R (flat 15:55), 2024-11-01 short +4.31 R (flat 15:55), 2024-11-08 short -1.06 R (stop), 2026-04-27 short -1.07 R (stop)

## Verdict (plain language)

**The sample does not support any conclusion.**
- **Baseline:** 15 trades in 7.3 years (16 before the holiday and early-close amendment), +0.51 R per trade, but the 95 % bootstrap interval runs from −0.22 to +1.34 R and p = 0.10.
- **Criterion:** it fails on 4 of 8 positive years, and one neighbour (`pivot_len` 2: 19 trades, −0.74 R) has the opposite sign.
- **No run passes the usual criterion,** and none comes near the Bonferroni level once runs with 0–3 trades are set aside. V2's p of 0.000 is one trade and means nothing.
- **Where the baseline's result comes from:** five trades held to 15:55 (+1.99 R on average) and one final target. Remove the single +4.31 R trade (2024-11-01) and the baseline drops to about +0.24 R on 14 trades.

"No edge shown" and "not enough data to tell" are both accurate. With about two trades a year, it would take decades of the same rule to resolve an edge of the size the course implies.

**The three assumptions most likely to change the result:**
1. **Which gap is the inverse-FVG trigger.** The coding takes the most recent 1m FVG against the trade in the move into the sweep. In the user's chart check the detection agreed on 4 of 10 trades, and 4 of the 6 disagreements were the gap or entry. Rejected setups would go and other entries would appear.
2. **The SMT definition and its timeframe.** The live-sweep reading on 1m swings (`pivot_len` 3), validated by a 5m sweep in the same bar, removes 32,666 of 34,647 1m SMT events. The neighbours (`pivot_len` 2 / 4) give −0.74 R on 19 and +0.74 R on 8 trades, so the result swings with the swing definition alone.
3. **The RSMT window and the cancel rule with 12-day zones.** About 34 sunrise zones are active at any time. The cancel rule (a close beyond a touched zone's far edge) removes 394 of 447 RSMT-qualified events, and with all fractions (V7) only 3 trades remain. A shorter zone life, or a cancel rule that reads only the zone actually reacted to, would change the count most.
