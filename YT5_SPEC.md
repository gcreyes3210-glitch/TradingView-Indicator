# YT5 — combinations of TTrades confluences, pre-registered 2026-10-09 (written before any YT5 code was run)

**The question.** "Try combinations of TTrades confluences and see which one is the most profitable."

**Why it is set up this way.** A grid of several thousand combinations always has a "most profitable" member, and
the top of any such grid is mostly luck. So the search is done on **2019-06 → 2022-12 only**, the picks are made by
the rule below before the later bars are opened, and the picks are then run **once** on **2023-01 → 2026-10**.
The answer to the question is the out-of-sample result of the picks, not the top of a table.

**What was already known when this was written (disclosed).** YT4's seven fixed readings (G1–G7) had been run on the
full span and all failed; so had the claim checks. The grid below is symmetric (every confluence has an "off" level)
and no level was chosen because of those results, but the author had seen them.

**Data, engine, fills, R, look-ahead test, order of work:** exactly as `YT1_SPEC.md`. Roll days and the day after are
not traded. Building blocks are `tools/yt1/tt.py` as registered in YT4 (`daily`, `bias`, `cisd`, `closure2`,
`closure3`) plus `cisd_ex`, which is `cisd` with the index of the run's first candle added.

## The frame (same for every combination)

- **Signal:** a CISD on clock-aligned bars of the trigger timeframe, on the continuous 24-hour series. The trade is in
  the CISD's direction (bullish CISD → long). Decision at the close of the CISD bar.
- **Entry** at that bar's close. **Stop** 1 tick beyond the protected low (high). **Target 2R.** Flat at the flat bar.
- **One trade a day per combination:** the first signal of the day, inside the combination's window, that meets all
  of its confluences. Later signals that day are ignored.
- Exits are not part of the grid. The neighbours of a combination are the same combination with targets 1.5R and 3R.

## The confluences (long side written; short is the mirror). Each is known at the signal bar's close.

| Code | Confluence | Levels |
|---|---|---|
| **T** | Trigger timeframe | `1`, `5`, `15` minutes |
| **W** | Window: the signal bar's last 1-minute bar is at | `am` 08:30–10:59 · `open` 09:30–10:59 · `sb` 10:00–10:59 · `pm` 13:30–14:59 |
| **B** | Daily bias (`tt.bias`) agrees with the trade | `none` (not used) · `any` · `cont` (bias from a continuation close) · `fail` (bias from a failed run) |
| **E** | Where the entry is against EQ, the midpoint of candle 1 (the last completed daily candle) | `none` · `disc` signal close below EQ (long in discount) · `prem` signal close above EQ (EQ held) |
| **O** | Against the daily open (the 18:00 open of the current trading day) | `none` · `below` signal close below the open (the long is bought under the open) |
| **R** | Liquidity raid: the protected low is below the level and the signal bar closes back above it | `none` · `pd` level = candle 1's low · `sess` level = the lowest low from 18:00 to 08:29 today |
| **H** | Higher-timeframe closure: the last completed candle before the decision is a candle 2 or candle 3 closure in the trade's direction | `none` · `h1` clock-hour candle · `h4` 4-hour candle (18:00, 22:00, 02:00, 06:00, 10:00, 14:00) |
| **S** | SMT divergence with ES: of the two markets, exactly one made a lower low on the run than in the 120 minutes before the run began | `none` · `smt` |

Details *(R = a reading, his videos do not fix it)*:
- A higher-timeframe candle counts once its last 1-minute bar has closed at or before the decision bar; one with fewer
  than half its minutes is not used (H is then false).
- **S**, long: run = from the first 1-minute bar of the first candle of the down-close run (`cisd_ex`) through the
  decision bar. Reference = the 120 minutes of 1-minute bars ending just before the run begins *(R)*. NQ lower low =
  MNQ's lowest low on the run < MNQ's lowest low in the reference; ES likewise on ES 1-minute bars over the same
  clock times. `smt` = one is true and the other false. Missing ES bars in either span → false.
- **E, R** use candle 1's high and low from `tt.bias`; where those are missing (roll) the confluence is false.
- **R** `sess` in the `pm` window uses the same 18:00–08:29 low *(R)*.
- A confluence at `none` places no condition. With `B = none` there is no daily direction; the CISD alone sets it.

**Grid:** 3 × 4 × 4 × 3 × 2 × 3 × 3 × 2 = **5,184 combinations.**

## Selection, on bars to 2022-12-31 only

1. **Eligible:** at least 150 in-sample trades.
2. **Rank** eligible combinations by the t-statistic of mean R (mean ÷ standard error).
3. **Picks:** go down the ranking and take a combination unless more than half of its trades are also trades of one
   already taken (same day, same entry bar, same side; share measured on the smaller of the two); stop at **5 picks**.
   A pick must have positive mean R; if fewer than 5 qualify, there are fewer picks.
4. Also recorded, with no test attached: the eligible combination with the largest in-sample net dollars.
5. **Luck check (White's reality check)** on the in-sample grid: each eligible combination's daily R series is
   centred on its own mean, days are resampled with replacement 2,000 times (seed 1), and the largest t-statistic
   across the grid is recorded each time. p = the share of resamples whose largest t is at least the observed
   largest t. This says whether the best of the grid is better than the best of that many no-edge rules.

The picks, their in-sample numbers and the ranking are frozen and stamped before the later bars are run.

## The out-of-sample test, 2023-01-01 → 2026-10, run once

For each pick, on its out-of-sample trades only:
- **Passes:** at least 100 trades; mean R ≥ +0.05; at least 3 of the 4 calendar years (2023, 2024, 2025, 2026) net
  positive; both neighbours (1.5R, 3R) have positive mean R; p < 0.05 / 95 = 0.00053 (one-sided bootstrap of mean
  R > 0, 10,000 resamples, seed 1; 95 = the 90 rules tried before this plus these 5).
- **Candidate:** the same with p < 0.05 / 5 = 0.01.
- **Not enough data:** under 100 out-of-sample trades. Otherwise **fails**.

Reported alongside, described as description and not as tests:
- **Does in-sample rank predict anything?** Spearman rank correlation between in-sample and out-of-sample mean R
  across the eligible combinations; the out-of-sample mean R of the in-sample top 10 % against the whole grid.
- **Each confluence on its own:** for every level of every confluence, the average of mean R over the combinations
  using it, in-sample and out-of-sample.
- **Hindsight table:** the full-span top of the grid by net dollars and by t, with the reality-check p for the full
  span. This is the literal "most profitable combination"; it is the top of 5,184 and is labelled as such.

Nothing here is adopted into the traded rule whatever the result; a pass or a candidate would go to a second coder's
re-code and the ORB overlap check, as in YT1.
