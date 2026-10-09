# YT8 — Jdub Trades, Trade with Pat, Fabio Valentini, Matt Owen: break-and-retest grid and four fixed rules, pre-registered 2026-10-09

Written before any YT8 code was run.

**The request.** "Go through every video in these channels and create a strategy that beats ORB v1.4. Try every single
combination of strategies." Also stated: about 30 trades a year is too few.

**What was actually read** (`data/studies/yt1/research/I_jdub.md`, `J_fabervaale.md`, `K_mattowen.md`, `L_playlist.md`):
- **Jdub Trades (@JdubTrades):** 39 videos read, 7 partly, of 70 found; the channel has about 440 uploads, most of the
  rest daily live streams. No playlist could be listed.
- **Trade with Pat** (the linked playlist "My 2026 ORB Scalping Strategy", 19 videos): the playlist's list could not be
  read; 34 of his videos read by targeted questions, about 23 more identified and not read.
- **Fabio Valentini (@fabervaaleEng):** 10 of 13 long-form videos read, plus 7 interviews and platform videos; 3
  long-form, 1 live stream and 13 Shorts not identified.
- **Matt Owen (@mattowentrades):** 6 of 206 uploads read, plus one interview. He calls his trading "very discretionary";
  his set-ups are in a paid group and every entry needs an order book or 20-tick footprint bars. **Nothing of his is
  coded here.** His one price-only idea (break and retest of the pre-market high) is YT1's B06, which failed.

So this is not every video, and it says which ones.

**What the three codable sources share.** One family: a level breaks with a candle close, price comes back to it, the
entry is on the retest with a stop close by and a fixed target. Jdub and Pat teach it on the opening range and on the
previous day's range; Fabio's only bar-codable new idea is the same thing with the entry at the opening range's own
point of control. The grid below is that family with each creator's menu of choices crossed. It starts from the same
break ORB v1.4 trades, so the question it answers is whether a retest entry with a near stop and a target does
better than ORB's entry at the close with a far stop and no target.

**Disclosed.** 2023–2026 has now been run on 102 rules and two grids; the author has seen all of it, including that
the best results so far are continuation trades in the first 90 minutes on ORB days.

Data, engine, fills, R, look-ahead test and order of work as `YT1_SPEC.md`. Roll days and the day after not traded.
All times New York. Long side written; short mirrors.

# Part 1 — the break-and-retest grid (G11)

**The day's set-up:** the first break of the level by the break rule, on either side, is the day's only set-up; its
side is the trade's side. Everything is decided at bar closes; orders rest from the next bar.

| Code | Choice | Levels |
|---|---|---|
| **L** | Level | `or5` high / low of 09:30–09:34 · `or15` of 09:30–09:44 · `or30` of 09:30–09:59 · `pd` high / low of the previous regular session (09:30–15:59), watched from 09:30 |
| **K** | Break | the first `c1` 1-minute · `c5` 5-minute · `c15` 15-minute candle that closes beyond the level, among candles that open after the level is complete |
| **D** | Displacement | `none` · `fvg` a 1-minute fair value gap in the break's direction among the 1-minute bars of the breaking candle and the two before it (Jdub's "gap rule") · `ext` the order is only placed once price has traded 0.7 × W beyond the level (Pat's number), W = the level's own width for `or*`, the 09:30–09:44 width for `pd` |
| **N** | Entry | `edge` limit at the broken level · `conf` after a 1-minute bar touches the level, the first 1-minute bar (that one or later) that closes above the previous bar's high, entry at its close (Jdub's confirmation candle) · `zone` limit at the high of the demand candle = the last down-close candle that closed before the breaking candle's close, on 1-minute bars for `c1`, 5-minute bars otherwise, looking back at most 12 candles (Pat) · `mid` limit at the range midline · `poc` limit at the opening range's point of control (Fabio) |
| **S** | Stop | `near`: `conf` 1 tick beyond the pullback's low (touch bar through confirmation bar); `zone` 1 tick below the demand candle's low; `poc` 1 tick below the range's value-area low; `edge` 0.25 × W inside the level; `mid` 0.25 × W below the midline · `mid` 1 tick below the range midline · `far` 2 ticks beyond the far side of the range (ORB's stop) |
| **X** | Target | `1.5R` · `2R` · `3R` · `hold` no target |
| **W** | Cut-off | no entry after `11:00` · `12:00` |
| **E** | Re-entry | `one` trade a day · `re` Jdub's "84 % rule": if the first trade is stopped before the cut-off, the first K-type candle that closes back beyond the level before the cut-off is entered at its close with the original stop price and the original target price; once only |
| **F** | Side filter at the breaking candle's close | `none` · `ema200` close above the EMA(200) of 5-minute closes · `vwap` close above the VWAP anchored at 09:30 · `ema921` 5-minute EMA(9) above EMA(21) |

Details *(R = a reading; the videos do not fix it)*:
- `mid` and `poc` entries and `mid` and `far` stops exist only for the opening-range levels; `mid` entry with `mid`
  stop does not exist. **25,920 combinations.**
- A day's order whose stop is not at least 2 ticks beyond its entry price, or whose target is already passed at entry,
  is not placed. A resting limit is cancelled if the stop price trades first. All trades are flat at the flat bar.
- Opening-range profile for `poc` *(R)*: each 1-minute bar's volume spread evenly over its ticks from low to high;
  point of control = the tick with the most volume (lowest on ties); value area = 70 % of the volume, grown outward
  from the point of control one tick at a time toward the larger neighbour.
- A limit is placed only if it is below the breaking candle's close (a `zone` above it is no trade).
- "Touches the level" for `conf`: a 1-minute low at or below the level, on a bar after the breaking candle.
- If the filter rejects the break there is no trade that day. With `ext`, a pullback that completes before the
  extension has traded is not an entry.
- `re`: the re-entry must still be at least 2 ticks beyond the stop and short of the target; `hold` re-enters with the
  original stop only.

**Selection, on bars to 2022-12-31 only.** Eligible = at least 215 in-sample trades (60 a year). Picks 1–5: by the
t-statistic of mean R, skipping a combination when more than half the days it trades are days of a pick already
taken on the same side (share of the smaller set); positive mean R required. Pick 6: the eligible combination with
the largest in-sample total R, if not already a pick. White's reality check as YT5 (2,000 resamples, seed 1). Frozen
and stamped before the later bars are run.

**Out-of-sample test, 2023-01-01 → 2026-10, run once.** For each pick, on out-of-sample trades:
- **Passes:** at least 100 trades; mean R ≥ +0.05; 3 of 4 calendar years net positive; both neighbours positive mean R
  (the other cut-off; the adjacent target: 1.5R→2R, 2R→3R, 3R→2R, hold→3R); p < 0.05 / 112 (one-sided bootstrap,
  10,000 resamples, seed 1). **Candidate:** the same with p < 0.05 / 6. Otherwise fails.
- **Beats ORB v1.4** (the question asked): a candidate or a pass that, on 2023-01-01 → 2026-10, has (a) a larger
  total R than ORB v1.4, (b) a larger net ÷ maximum drawdown than ORB v1.4, both at one contract, and (c) at least 60
  trades a year. ORB v1.4 is `tools/yt1/cal_orb.py` through the harness on the same dates.
- Reported as description: net dollars against ORB's; each pick's days and side against ORB's; ORB + pick together;
  Spearman of in-sample against out-of-sample mean R; the per-level table for both periods; the full-span hindsight
  top 10 with its reality check, labelled as the top of 25,920.

# Part 2 — four fixed rules (usual order: in-sample first, then the full span once)

Criterion for each: the usual one on the full span (6 of 8 years positive, mean R ≥ +0.05, both halves non-negative,
both neighbours the same sign, p < 0.05 / 112 to pass, p < 0.05 for a candidate, under 100 trades = not enough data).

- **H1 — Pat's manipulation-candle fade.** The 09:30–09:44 candle counts if its high − low is larger than the average
  true range of the previous 96 fifteen-minute bars *(R: simple average, the candle itself excluded)*. After a
  down-close candle: buy limit at its low; after an up-close candle: sell limit at its high *(R: his "buys at the
  bottom and sells at the top")*. The limit rests 09:45–11:59 *(R)*. Target = 38.2 % of the candle's range back from
  the entry edge. Stop = the target distance ÷ 1.5 beyond the entry *(R: his "about a 1.5")*. One trade a day.
  Neighbours: stop = target distance ÷ 1.0 and ÷ 2.0.
- **H2 — Pat's 01:00–05:00 candle.** Range = high and low of 01:00–04:59. On 5-minute bars from 05:00: at least three
  consecutive closes outside the range on one side, then the first close back inside it, by 11:00 *(R)*, is entered
  at that close against the excursion. Stop 1 tick beyond the excursion's extreme. Target the far side of the range.
  One trade a day. Neighbours: at least two and at least four closes outside.
- **H3 — the previous-day box, edges only (Pat's Model D, Jdub's rejection play).** Only on days whose 09:30 open is
  inside the previous regular session's range. From 09:30 to 11:00: after a 1-minute bar touches the previous
  session's low, the first 1-minute bar (that one or later) that closes above the previous bar's high and above that
  low is entered long at its close; mirror at the high. First such trade of the day only. Stop 1 tick beyond the
  lowest low from the touch through the entry bar. Target 2R. Neighbours 1.5R and 3R.
- **H4 — Fabio's opening-range break with a volume condition (bars only).** Range 09:30–09:59. The first 5-minute
  candle from 10:00 to 11:25 whose open and close are both beyond the range *(R: "the body of the candle closing
  above the range")* and whose volume is larger than the previous 5-minute candle's is entered at its close. Stop 1
  tick beyond that candle's low. Target 1R (his plain test). One trade a day. Neighbours: target 2R; and stop 2
  ticks beyond the far side of the range with a 1R target.

**Read and not coded:** everything of Matt Owen's (above); Fabio's trend, mean-reversion, absorption and "Effort"
models (need individual trade sizes, an order book or his closed indicator; already set aside in YT1); his
"protection level" target (no formula published); Jdub's higher-timeframe and micro-trend models and Pat's
supply/demand and trend-line models (structure chosen by eye); Jdub's opening-print trade with a daily-close bias
(the same bias YT4–YT7 found says nothing after 09:30); Pat's 08:00–09:15 fade (taught with no stop and adding to
losers).

Nothing here is adopted into the traded rule whatever the result.
