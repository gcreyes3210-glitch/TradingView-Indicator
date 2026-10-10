# YT9 — which levels react: first tap after the open, every level, with placebo levels (LEV1), pre-registered 2026-10-09

Written before any YT9 code was run.

**The request.** "See what levels get the most reaction after market open … previous day highs / lows, Asia highs and
lows, London highs and lows etc. Check Aceflw levels too. Price should have a strong reaction after tapping the
level, the first time after market open. Track which levels have the best possibilities for trades. It could be a
20 point stop loss at the level and a 1:3 RR or something like that. Try all combinations of levels."

**How it is answered.** Every level is a price fixed before it is tapped. On each day the first tap of each level
from 09:30 is one event, and the event is scored as a trade against the tap (a fade): limit at the level, stop
beyond it, target a multiple of the stop. **"Strong reaction" = the target is reached before the stop**, so the win
rate of that trade is the reaction rate. Each level is compared with **placebo levels**: the same level shifted to a
price with no meaning, so that an ordinary bounce off nothing is not counted as a reaction to the level.

**Disclosed.** Fades at the overnight high / low, the previous day's levels and value areas have failed in this log
before (BACKTEST_LOG "overnight high / low rejection", VP1–VP5, YT8 H3). The author has seen all of 2023–2026 for 112
rules. This study measures and ranks; it is not expected to find a rule.

Data, engine, fills, look-ahead test and order of work as `YT1_SPEC.md`. Roll days and the day after are left out.
All times New York. ATR = the daily ATR(14) of the day table (known before the session).

## Why two stop sizes

Twenty points is 0.04 × the daily ATR in 2026 and was 0.17 × ATR in 2019 (price 7,900 then, 28,800 now). A fixed
20-point stop is therefore a different trade in each year. Both are run: **`p20`** = 20 points as asked, and
**`a04`** = 0.04 × ATR (20 points at 2026 volatility, about 5 points in 2019), which is the same trade every year
and is the one used for ranking. A wider `a08` = 0.08 × ATR is the neighbour.

## The levels

Static levels, fixed before 09:30 unless stated:

| Group | Codes | Definition |
|---|---|---|
| Previous day | `pdh` `pdl` `pdc` `pdm` | High, low, close and midpoint of the previous regular session (09:30–15:59) |
| Previous week | `pwh` `pwl` | High and low of the previous trading week (Sunday 18:00 → Friday 17:00) |
| Overnight | `onh` `onl` | High and low of 18:00–09:29 (Aceflw's OVN HIGH / LOW) |
| Asia | `ash` `asl` | High and low of 18:00–01:59 *(R)* |
| London | `ldh` `ldl` | High and low of 02:00–07:59 *(R)* |
| Pre-market | `prh` `prl` | High and low of 08:00–09:29 *(R)* |
| Opens | `o18` `o00` `o0830` | Open of the 18:00, 00:00 and 08:30 one-minute bars |
| Aceflw overnight profile | `vah` `poc` `val` | Volume profile of 18:00–09:29 built as `Aceflw_Levels.pine` builds it: 1-minute bars, 4-tick rows, each bar's volume spread evenly over the rows it spans, value area 70 %, with that script's point-of-control and value-area rules |
| Round numbers | `r100` | The nearest multiples of 100 points above and below the 09:30 open |
| Opening range | `orh` `orl` | High and low of 09:30–09:44; watched from 09:45 |
| Aceflw expected move | `em1u` `em1d` `em2u` `em2d` | As `Aceflw_Levels.pine` on a 5-minute chart, realised volatility: blocks start at 08:00, 10:00, 12:00, 14:00; centre = the block's first open; 1σ = centre × standard deviation of 5-minute log returns over the previous 2,760 five-minute bars × √24; bands at ±1σ and ±2σ, fixed for the block. Each block's band is its own level, watched from the later of 09:30 and the block's start until the block ends |

Moving levels *(the value used is the one at the close of the last completed 5-minute bar)*:

| Group | Codes | Definition |
|---|---|---|
| Aceflw VWAP | `vw` `vw1u` `vw1d` `vw2u` `vw2d` | VWAP anchored at 18:00 on 5-minute bars (hlc3 × volume) and its ±1σ, ±2σ volume-weighted bands, as the script |

**Placebo levels.** For every static level L of the day, two fakes at L + s and L − s with s = 0.12 × ATR, dropped
if within 0.03 × ATR of any real static level. A fake carries its parent's code (e.g. `pdh~`). Moving levels and the
expected-move bands have no placebo (their own ±1σ against ±2σ and the block structure are the comparison).

## The event: first tap after the open

- Watch from the 09:30 bar (or from when the level exists) to 15:00. A level within 0.04 × ATR of the price at the
  start of the watch is skipped that day (it is already being traded at).
- The level is **resistance** if it is above the price at the start of the watch and **support** if below.
- The tap = the first 1-minute bar whose high reaches a resistance level or whose low reaches a support level. For a
  moving level, the bar's range must reach the value fixed at the last completed 5-minute close.
- **Fresh / used:** a static level that price traded through between the time it was set and 09:30 is `used`
  (for example the Asia high taken out in London). Reported separately; ranking uses fresh events only.
- **Confluence:** two or more real static levels within 0.03 × ATR of each other on the same side form a cluster;
  the level nearest the price is the one tapped, and the event is tagged with every level type in the cluster.

## Scoring each event (house fills: limit fills on a touch one tick worse; 1 tick slippage per fill; $1 a side)

- **Fade:** short at a resistance level, long at a support level, limit at the level. Stop `p20` / `a04` / `a08`
  beyond the level. Target 1R, 2R or 3R. Flat at the flat bar. Nine variants; **headline `a04` × 3R**, and
  `p20` × 3R as asked.
- **Break (the mirror question):** entered with the move at the same price, same stop distance on the other side,
  target 3R. Reported next to the fade so each level shows which way it tends to resolve.
- Also recorded per event: the largest move away from the level and the largest move through it in the next 30
  minutes, in ATR units; the time of the tap (09:30–09:59, 10:00–11:29, 11:30–15:00); the distance of the level from
  the 09:30 open in ATR units.

## Tables

1. **Reaction by level:** for every level code × resistance / support, fresh events: events, fade win rate and mean R
   for the headline and for `p20` × 3R, the placebo's win rate and mean R, the difference, and the break trade.
2. **Draw:** for every static level code, the share of days it is tapped by 15:00 by distance from the 09:30 open
   (under 0.1, 0.1–0.25, 0.25–0.5, 0.5–1.0 ATR), next to the placebo's share at the same distance.
3. **Combinations:** every pair of level codes that share a cluster on at least 60 in-sample days: events, fade win
   rate and mean R; and the same by the number of levels in the cluster (1, 2, 3 or more).
4. The same three tables by time of tap and for `used` levels, reported as description.

## Selection (2019-06 → 2022-12 only) and test (2023-01 → 2026-10, run once)

- **Picks:** the 5 level code × side cells with the highest in-sample mean R of the headline fade among cells with
  at least 150 fresh in-sample events, and the 3 pairs with the highest among pairs with at least 60. Frozen and
  stamped before the later bars are run.
- **A pick counts as a reacting level** if, out of sample: at least 100 events (40 for a pair); headline fade mean R
  ≥ +0.05 with p < 0.05 / 8 (one-sided bootstrap, 10,000 resamples, seed 1); 3 of 4 calendar years positive; the
  `a08` × 3R and `a04` × 2R neighbours positive; and its win rate above its placebo's. A pair has no placebo
  condition.
- Reported whatever the picks do: the rank correlation of the level cells' mean R between the two periods (do the
  same levels stay on top?), and whether real levels as a whole beat their placebos (pooled difference in win rate
  and mean R, with a two-proportion p).

**Not possible with this data:** Aceflw's options levels (Vol Trigger, Call Wall, gamma flip) and its implied-vol
band; there is no historical options data in the folder. The footprint cells are not levels.

Nothing here is adopted into the traded rule whatever the result.
