# YT6 — the TTrades confluences not yet tested, pre-registered 2026-10-09 (written before any YT6 code was run)

**What this is.** YT5 searched 5,184 combinations of his confluences and its five picks failed out of sample. This
batch adds the pieces YT5 left out: the midnight and 08:30 opens, the London window, targets at liquidity, the retest
and positional entries, the bias invalidation, the "failure to manipulate" continuation, and his weekly claims.

**Method, same as YT5.** Search on bars to 2022-12-31 only; picks made by the rule below; picks run once on
2023-01 → 2026-10. Data, engine, fills, R, look-ahead test and order of work as `YT1_SPEC.md`; roll days and the day
after not traded; building blocks `tools/yt1/tt.py` unchanged.

**Disclosed.** When this was written the author had seen YT5's full-span results, including its per-confluence table
for 2023–2026 (the previous-day raid and the 15-minute trigger least negative, the daily bias worse than no bias). The
2023–2026 bars have now been run on 95 rules. The grid below keeps every YT5 level and adds levels; none is removed
because of those results.

# Part 1 — the grid

## Frame

- **Signal:** a CISD on clock-aligned 1-, 5- or 15-minute bars of the continuous series; the trade is in the CISD's
  direction; decision at the close of the CISD bar. **Stop** 1 tick beyond the protected low (high).
- **One order a day per combination:** the first signal of the day, inside the combination's window, that meets all
  its confluences and its target rule. If that order does not fill or is cancelled there is no trade that day.
- **Flat:** the flat bar; trades of the London window are flat at 08:29 *(R)*.

## Confluences (long side written; short mirrors). `cand1` = the last completed daily candle (18:00 → 17:00).

| Code | Confluence | Levels |
|---|---|---|
| **T** | Trigger timeframe | `1` · `5` · `15` minutes |
| **W** | Window: last 1-minute bar of the signal bar at | `ldn` 02:00–04:59 · `am` 08:30–10:59 · `open` 09:30–10:59 · `sb` 10:00–10:59 · `pm` 13:30–14:59 |
| **B** | Daily bias | `none` · `any` · `cont` · `fail` (as YT5: bias agrees with the trade) · `inv` **invalidation**: there is a daily bias, a completed clock-hour candle since 18:00 has closed beyond cand1's EQ against it (below EQ for a bullish bias), and the trade is against the bias |
| **E** | Entry against cand1's EQ | `none` · `disc` · `prem` (as YT5) |
| **M** | Opens: signal close below the open (long) | `none` · `d18` the 18:00 open · `mid` the 00:00 open · `both` the 00:00 open and the 08:30 open |
| **R** | Raid or break of a level. `pd` levels = cand1's low and high; `sess` levels = the lowest low and highest high from 18:00 to 08:29 (from 18:00 to 01:59 for the `ldn` window) | `none` · `pd` · `sess` **raid**: the protected low is below the low level and the signal bar closes back above it · `pd_brk` · `sess_brk` **failure to manipulate**: the protected low of this bullish CISD is above the high level (price broke the high and the pullback that this CISD ends held above it) |
| **H** | Higher-timeframe closure in the trade's direction | `none` · `h1` · `h4` (as YT5) |
| **S** | SMT divergence with ES | `none` · `smt` (as YT5) |
| **X** | Target | `2R` · `pdx` cand1's high · `liq` the nearest of {cand1's high; the session high used by R `sess`; today's high since 18:00 up to the decision bar} that is at least 1R above the signal close. For `pdx` and `liq` the signal qualifies only if the level is at least 1R above the signal close (R = signal close − stop) |
| **N** | Entry | `close` at the signal bar's close · `retest` limit at the opening price the CISD closed through, resting 30 minutes, cancelled if the stop price trades first · `pos` **positional**: market at the open of the next clock-hour candle, cancelled if the stop price trades before then or the open is at or beyond the target |

Details *(R)*:
- `M both` does not exist in the `ldn` window (the 08:30 open is in the future); those combinations are dropped.
- `M mid` uses the open of the 00:00 one-minute bar; a signal before 00:00 cannot use it (not possible in these windows).
- For `2R` with `retest` or `pos`, 2R is measured from the actual entry price. Level targets stay where they are.
- `B inv`: the hourly close beyond EQ may be any completed hour candle since 18:00, at or before the decision bar.
- `R sess` and `sess_brk` use only the finished session range: a signal in the `am` window at 08:30 or later uses
  18:00–08:29; nothing in the range is later than the decision bar.
- Everything else as the YT5 details (higher-timeframe candles complete, SMT reference 120 minutes, roll handling).

**Grid:** 3 × 5 × 5 × 3 × 4 × 5 × 3 × 2 × 3 × 3 = 243,000, less the `ldn` × `both` combinations (12,150) =
**230,850 combinations.**

## Selection, on bars to 2022-12-31 only

1. **Eligible:** at least 150 in-sample trades.
2. **Picks 1–5:** rank eligible combinations by the t-statistic of mean R; go down the ranking, skipping a combination
   when more than half of its orders are orders of one already taken (same day, decision bar and side; share of the
   smaller set); positive mean R required; stop at 5.
3. **Pick 6, the consensus combination:** for every confluence take the level with the highest in-sample average of
   mean R over the eligible combinations using it (ties → the level listed first above). If that combination has
   fewer than 150 in-sample trades, set to its first-listed level the confluence whose chosen level beats its
   first-listed level by the smallest margin (T and W: the level with the second-highest average instead), and repeat
   until it has 150 (if it never does, there is no pick 6). It is a pick whatever the sign of its in-sample mean R.
4. Recorded with no test: the eligible combination with the largest in-sample net dollars.
5. **Luck check:** White's reality check as YT5 (2,000 resamples of days, seed 1, largest t across eligible
   combinations).

Picks, ranking and the per-level table are frozen and stamped before the later bars are run.

## Out-of-sample test, 2023-01-01 → 2026-10, run once

For each pick, on out-of-sample trades only:
- **Passes:** at least 100 trades; mean R ≥ +0.05; at least 3 of the 4 calendar years net positive; both neighbours
  positive mean R; p < 0.05 / 101 (one-sided bootstrap of mean R > 0, 10,000 resamples, seed 1).
- **Candidate:** the same with p < 0.05 / 6 = 0.0083. Under 100 trades: not enough data. Otherwise fails.
- **Neighbours:** target `2R` → 1.5R and 3R; target `pdx` / `liq` → the minimum distance 0.75R and 1.5R instead of 1R.

Reported as description: Spearman correlation of in-sample and out-of-sample mean R over eligible combinations; the
out-of-sample average of the in-sample top 10 %; the per-level table for both periods; the full-span hindsight top
10 by net dollars and by t with the full-span reality check, labelled as the top of 230,850.

# Part 2 — weekly and sequence claims (K-H), each rate next to a base rate; in-sample first, then full span

Weeks are trading weeks (Sunday 18:00 → Friday 17:00) built from the daily candles of `tt.daily`; a week needs at
least 4 daily candles; weeks containing a roll candle are flagged and left out. Threshold: p < 0.05 / 8 (two-sided
two-proportion test), reported in-sample, 2023–2026 and full span.

- **L1 — weekly continuation:** week W closes above week W−1's high → week W+1 trades above week W's high (mirror
  for lows). Base: every week.
- **L2 — weekly failed run:** week W trades above week W−1's high, closes back below it and does not take W−1's low →
  week W+1 trades below week W's low; also recorded: week W+1 trades below week W−1's low ("the previous week's low
  is the draw"). Mirror for lows. Base: every week.
- **L3 — three in a row:** day D is the third consecutive continuation close in one direction (each closes beyond
  the previous day's extreme) → day D+1 is another continuation close in that direction; and D+1 trades beyond D's
  extreme. Base: days that are the first or second continuation close in a row.
- **L4 — Friday retrace:** weeks whose low was set on Monday or Tuesday and whose Thursday close is in the top
  quarter of the Monday–Thursday range → Friday trades down to at least 20 % of that range below the
  Monday–Thursday high. Mirror for down weeks. Base: the same test one day earlier (low set Monday or Tuesday,
  Wednesday close in the top quarter of the Monday–Wednesday range → Thursday trades down 20 % of that range).

Nothing here is adopted into the traded rule whatever the result.
