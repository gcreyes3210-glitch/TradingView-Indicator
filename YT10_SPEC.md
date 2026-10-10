# YT10 — the midnight open (MID1) and volume profiles of the previous 1 to 5 sessions (VPN1), pre-registered 2026-10-09

Written before any YT10 code was run.

**The request.** (1) "Test midnight open levels … see if price reacts strongly after market open when it taps into
this level." (2) "Test Aceflw levels but … try different volume profiles and see which levels are the most
profitable. Use previous session volume profiles. Then the previous 2 sessions' volume profile. Then the previous 3 …
the furthest profile will be the weekly. See if there's an edge when they all align. Find the best strategy."

**Disclosed.** YT9 already scored the 00:00 open among its levels, attributed to the nearest level of a cluster
(413 events over the full span, fade with a 20-point stop and 3R: 21.5 % wins as support, 24.7 % as resistance,
both negative). The author has seen that, and all of 2023–2026 for 120 rules. YT9 also found that real levels
bounce less often than placebo levels. Fades at the previous day's value area failed in BACKTEST_LOG (VP1–VP5).

Method, data, fills, look-ahead test and order of work as `YT9_SPEC.md` and `YT1_SPEC.md`: every level is a price
fixed before it is tapped; the first tap from 09:30 to 15:00 is one event; the event is scored as a **fade** (limit at
the level against the tap, stop beyond it, target 1R / 2R / 3R) and as a **break** (with the move, same stop
distance, 3R). Stops `p20` = 20 points, `a04` = 0.04 × daily ATR, `a08` = 0.08 × ATR. Headline `a04` × 3R; `p20` × 3R
reported beside it. Side: **support** if the level is below the 09:30 open, **resistance** if above. A level within
0.04 × ATR of the 09:30 open is skipped that day. Roll days and the day after are left out. **In YT10 every level is
scored on its own every day** (no attribution to the nearest level of a cluster, and no "fresh" requirement; whether
price traded through the level before 09:30 is recorded and reported as a split).

# Part 1 — MID1, the midnight open

- **Level:** the open of the 00:00 one-minute bar, New York time (the first bar at or after 00:00 if it is missing).
- **Comparison family:** the opens of every other overnight hour, 19:00, 20:00 … 23:00, 01:00 … 07:00, scored the
  same way. If midnight is special it should stand out from the twelve other hourly opens. Also the two placebo
  levels at midnight open ± 0.12 × ATR.
- **Registered splits:** side; time of the tap (09:30–09:59, 10:00–11:29, 11:30–15:00); distance from the 09:30
  open (under 0.10, 0.10–0.25, 0.25–0.50, over 0.50 ATR, measured before the skip rule where it applies); whether
  price had already traded through it between 00:00 and 09:29; and **the ICT use**: the fade taken only in the
  direction of the daily bias (`tt.bias`: buy a tap of the midnight open from above on a bullish-bias day, sell a
  tap from below on a bearish-bias day), against the fade against the bias and on no-bias days.
- **Verdict for the midnight open as a reacting level** (full span, both sides pooled, headline fade): at least 6 of
  8 calendar years positive, mean R ≥ +0.05, both halves non-negative, the `a08` × 3R and `a04` × 2R neighbours
  positive, p < 0.05 / 130 to pass and p < 0.05 for a candidate (one-sided bootstrap, 10,000 resamples, seed 1),
  and a win rate above its placebo's. The same verdict is given for the with-bias fade. The break trade is reported
  beside both.

# Part 2 — VPN1, volume profiles of the previous N sessions

**Profiles.** Built as `Aceflw_Levels.pine` builds its overnight profile (1-minute bars, 4-tick rows on the common
1-point grid, each bar's volume spread evenly over the rows it spans, point of control and 70 % value area by the
script's rules), but over these bars:

| Code | Bars |
|---|---|
| `rth1` … `rth5` | the regular sessions (09:30–15:59) of the previous 1, 2, 3, 4, 5 cash days, as one profile |
| `eth1` … `eth5` | the full sessions (18:00–16:59) of the previous 1, 2, 3, 4, 5 trading days, as one profile |
| `rthw`, `ethw` | all regular / full sessions of the previous trading week (Sunday 18:00 → Friday 17:00) *(R: the second reading of "weekly"; `rth5` / `eth5` are the first)* |
| `on` | tonight's overnight session, 18:00–09:29 (the Aceflw profile YT9 used; here for comparison) |

Each gives three levels, `vah`, `poc`, `val`: 39 levels a day. A profile is not built if a contract roll falls
inside its sessions or between them and today *(R)*; a session with fewer than half its minutes is skipped over and
the next earlier one used *(R)*.

**Scoring.** Every level × side as the method above. Table: events, fade win rate and mean R (headline and
`p20` × 3R), break trade, placebo (the level ± 0.12 × ATR), by profile and level, for all events and split by whether
price had traded through the level since the profile ended.

**"When they all align."** Two readings, both registered:
1. **Stacked levels.** For each event, the number of *other profiles* (of the 13) with any of their three levels
   within 0.03 × ATR of the tapped level. Fade and break results by that count: 0, 1, 2, 3 or more. And the special
   case **aligned points of control**: days on which the POCs of `rth1` … `rth5` (likewise `eth1` … `eth5`) all lie
   within 0.06 × ATR of each other; the event is the first tap of their average, rounded to the tick.
2. **Aligned value.** The 09:30 open against the value areas of N = 1 … 5: above all five VAHs, below all five VALs,
   inside all five, or mixed (for `rth` and for `eth`). For each day type: the 09:30 → flat-bar move in the
   "accepted" direction (up when above all, down when below all) in ATR units and its hit rate; ORB v1.4's results
   on those days, split by whether its trade agrees with the day type. Description, plus one registered trade:
   **`VA-trend`** = at the 09:30 open, long when the open is above all five `rth` VAHs, short when below all five
   VALs, no stop, flat at the flat bar, R unit 0.1 × ATR (neighbours: the same on `eth`, and N = 1 … 3 only).

**Finding the best strategy: selection on 2019-06 → 2022-12, test on 2023-01 → 2026-10, run once.**
- Cells = profile × level × side × trade (fade or break) with at least 150 in-sample events. **Picks 1–5:** the
  highest in-sample headline mean R, taking at most one cell per profile family (`rth`, `eth`, `on`) × level × side ×
  trade until five are taken, so the picks are not five lookbacks of one level.
- **Picks 6–7:** the stacked-level count bucket (1, 2, 3 or more) × trade with the highest in-sample headline mean R
  among buckets with at least 100 events, and the aligned-POC event × trade with the higher mean R (if it has at
  least 60 events).
- **Pick 8:** `VA-trend`.
- **A pick counts** if, out of sample: at least 100 events (60 for picks 6–8); headline mean R ≥ +0.05 with
  p < 0.05 / 8; 3 of 4 calendar years positive; both neighbours positive (`a08` × 3R and `a04` × 2R; for `VA-trend`
  its two registered neighbours); and, for single-level fades, a win rate above the placebo's.
- Reported whatever the picks do: the rank correlation of the cells' mean R between the two periods; whether longer
  lookbacks react more than shorter ones (mean R by N, both periods); the pooled real-against-placebo comparison;
  the full-span top 10 cells by net dollars, labelled as hindsight.

**Not possible with this data:** Aceflw's own profile windows where they differ from these, and its options levels.

Nothing here is adopted into the traded rule whatever the result.
