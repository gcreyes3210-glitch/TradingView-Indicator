# K-H - TTrades weekly and sequence claims L1, L2, L3, L4, claim check (`tools/yt1/k_H.py`)

Spec: `YT6_SPEC.md` Part 2. TTrades gives no hit rates, so there is no claimed figure: every measured rate stands
next to the base rate registered in the spec, with the difference and a two-sided two-proportion z-test (pooled
variance, `math.erfc`, the same function as `k_G.py`; checked against scipy). No pass / fail. The spec's threshold is
p < 0.05 / 8 = 0.00625; the printed table marks those rows with `*`.

Result keys: `rows["<claim>.<series>.<side>.<outcome>.<base>"]` = n, k, rate, base_n, base_k, base_rate, diff_pp, z, p.
series: `wk` (trading weeks), `day` (tt.daily candles). side = **the direction of the move the claim predicts**:
`long`, `short`, `both` (the two sides' counts added, claim and base alike). For L4 that means
`short` = the UP week whose Friday is claimed to retrace down (the version written in the spec) and `long` = the
DOWN week (the mirror). outcome and base names are explained in `legend` inside the JSON.

| key | condition | outcome | base |
|---|---|---|---|
| `L1.wk.<side>.beyond.all` | close(W) > high(W-1) [short: < low(W-1)] | W+1 trades above high(W) [below low(W)] | every week W |
| `L2.wk.<side>.beyond_w.all` | short: W trades above high(W-1), closes below it, does not trade below low(W-1); long: mirror | W+1 trades below low(W) [long: above high(W)] | every week W |
| `L2.wk.<side>.beyond_prev.all` | the same | W+1 trades below low(W-1) [long: above high(W-1)] | every week W, same outcome |
| `L3.day.<side>.cont.run12` | D is exactly the third continuation close in a row | close(D+1) beyond D's extreme | D exactly the first or second in a row |
| `L3.day.<side>.beyond.run12` | the same | D+1 trades beyond D's extreme | the same |
| `L4.wk.<side>.retrace20.day_before` | extreme of Mon-Thu first shown Mon or Tue, Thursday close in the top (bottom) quarter of the Mon-Thu range | Friday reaches 20 % of that range from the Mon-Thu high (low) | the same test on Mon-Wed -> Thursday |

## 1. Readings added beyond the spec text (R) - all fixed before the first run
Candles
- (R) Days = the rows of `tt.daily(ctx)`, unchanged, in time order. "The previous day", "D+1" = the neighbouring row:
  a holiday without a candle is skipped (as `tt.bias` does). The candle is dated by its 17:00 close.
- (R) Week = the daily candles dated Monday .. Friday of one calendar week (Monday's candle opens Sunday 18:00): open
  of the first, highest high, lowest low, close of the last. No candle is dated Saturday or Sunday (counted: 0).
- (R) W-1, W, W+1 are consecutive calendar weeks. A week of fewer than 4 candles is treated exactly like a roll week:
  it is left out and so is every comparison that uses it; it is never skipped over. (In-sample there is no such week.)
- (R) Roll: tt.daily's `roll` flag, as it is. A week holding a roll candle is left out for all four claims, also when
  the roll candle is its Monday (the whole week is then one contract) and also for L4, which only looks inside the week.
  tt.daily flags the very first candle of the data (nothing before it), so the first week (2019-06-03) is a roll week.
- (R) End of data: the last daily candle is dropped when the bars stop before its 17:00, and a week is left out when
  the bars stop before its Friday 17:00 ("the outcome uses the following week / day in full"). In-sample the bars end
  Friday 2022-12-30 16:59, so neither happens (both counted: 0).
- (R) "Trades above x" = high >= x + 1 tick, "trades below x" = low <= x - 1 tick (as K-G; on the 0.25 grid the same
  as > and <; no price is off the grid). "Closes above" = close > x. "Does not take W-1's low" = does not trade below it.

Claims
- L1, L2 (R): "Base: every week" = every week W for which W-1, W and W+1 are usable, i.e. exactly the set the claim's
  cases are drawn from; the base outcome is the claim's outcome (L2 `beyond_prev`: W+1 trades beyond W-1's extreme).
- L2 (R): the mirror is: W trades below low(W-1), closes back above it, does not trade above high(W-1) -> W+1 trades
  above high(W); also above high(W-1).
- L3 (R): "the third consecutive continuation close" = exactly the third: close(D-2) > high(D-3), close(D-1) >
  high(D-2), close(D) > high(D-1), and D-3 was NOT such a close. The base is exactly the first or exactly the second
  in a row. A fourth or later close in a row is in neither group (16 long / 2 short eligible days; their numbers are
  in the unregistered `L3_positions` table only). "Another continuation close" = close(D+1) > high(D).
- L3 (R): a case is used when D-4 .. D+1 all exist and none is a roll candle - one window for claim and base alike
  (D-4 is needed to know that D-3 was not a continuation close).
- L4 (R), "which days make Monday-Thursday when a week has a holiday": the week's candles DATED Monday, Tuesday,
  Wednesday, Thursday that exist. A missing Monday, Tuesday or Wednesday candle is simply absent from the range; no
  other day takes its place. The week is a case only if both its Thursday-dated and its Friday-dated candle exist.
  A holiday session that still trades (e.g. Memorial Day to 13:00) has a candle and counts as its weekday.
- L4 (R): "low was set on Monday or Tuesday" = the low of the Monday-Thursday range (not of the whole week: Friday is
  the outcome and is not known at Thursday's close); "set" = the first candle that shows it.
- L4 (R): "in the top quarter" = close(Thu) >= H - 0.25 R (edge included). "Trades down to at least 20 % of that range
  below the high" = low(Fri) <= H - 0.20 R: the level has to be reached, no extra tick. Integer ticks in the code.
- L4 (R): base = the candles dated Monday-Wednesday that exist; both the Wednesday- and the Thursday-dated candle
  must exist (Friday need not); the Mon-Wed low first shown Monday or Tuesday; Wednesday close >= H3 - 0.25 R3 ->
  low(Thu) <= H3 - 0.20 R3. Mirror for down weeks.
- L4 (R): side naming, see the top: `short` = up week / Friday down (as written), `long` = down week / Friday up.
- Not in the spec, added and labelled: `at_close` / `base_at_close` (cases whose condition-day close is already at or
  beyond the 20 % level) and the `L3_positions` table (eligible days by position in the run: n, k of both outcomes).

## 2. Exclusions (in-sample)
- Days: 926 tt.daily candles, 16 roll candles (2019-06-03 = first candle of the data, 2019-06-19, 2019-09-16,
  2019-12-16, 2020-03-17, 2020-06-17, 2020-09-16, 2020-12-14, 2021-03-17, 2021-06-14, 2021-09-13, 2021-12-13,
  2022-03-16, 2022-06-15, 2022-09-14, 2022-12-14). L3 uses 830 days; left out 96 = 5 at the edges (first 4, last 1) +
  91 with a roll candle in D-4 .. D+1.
- Weeks: 187 calendar weeks; 0 with fewer than 4 candles; 16 with a roll candle (2019-06-03, 2019-06-17, 2019-09-16,
  2019-12-16, 2020-03-16, 2020-06-15, 2020-09-14, 2020-12-14, 2021-03-15, 2021-06-14, 2021-09-13, 2021-12-13,
  2022-03-14, 2022-06-13, 2022-09-12, 2022-12-12); 0 unfinished; **171 usable** (8 of them with 4 candles).
- L1 / L2: 140 weeks W with W-1, W, W+1 usable. 31 usable weeks are left out because a neighbour is not usable: the
  30 weeks before / after a roll week and the last week (2022-12-26, no W+1 in these bars).
- L4 claim: 166 weeks; 5 usable weeks have no Friday candle (2020-04-06, 2020-12-21, 2020-12-28, 2021-12-20,
  2022-04-11). In 3 claim weeks the range has 3 candles (2019-12-23 and 2019-12-30: no Wednesday; 2022-12-26: no
  Monday). L4 base: 169 weeks; 2 have no Wednesday candle (2019-12-23, 2019-12-30); 1 range of 2 candles (2022-12-26).

## 3. Coding errors found after first seeing results
None. The module ran at the first attempt and was not edited afterwards; no definition, threshold or reading changed.

## 4. Hand check
Cases drawn with pandas `sample(random_state=3)` (two per side for each claim, plus base cases), the candles rebuilt
from the 1-minute bars by a separate groupby, the first 1-minute bar beyond a level read from the bars. All as the module.

L1 (close beyond the previous week's extreme -> next week trades beyond this week's)
- long, W = 2020-05-25: W-1 H 9510.50 L 9110.00 C 9422.75; W H 9604.00 L 9173.25 **C 9589.00** > 9510.50; W+1
  (2020-06-01) H 9846.75 L 9450.00: above 9604.00 first at 2020-06-01 13:25 -> yes.
- long, W = 2021-10-25: W-1 H 15483.75; W H 15869.00 L 15296.50 C 15869.00; W+1 H 16448.50: above at 10-31 18:00 -> yes.
- short, W = 2022-04-18: W-1 (4 candles, Good Friday) H 14379.75 L 13876.00 C 13894.00; W H 14298.00 L 13295.75
  **C 13308.00** < 13876.00; W+1 H 13584.50 L 12803.00: below 13295.75 first at 2022-04-24 18:03 -> yes.
- short, W = 2022-04-25: W-1 L 13295.75; W H 13584.50 L 12803.00 C 12892.50; W+1 L 12519.25: below 12803.00 at
  2022-05-02 07:55 -> yes.

L2 (failed run; outcome 1 = beyond W's extreme, outcome 2 = beyond W-1's extreme)
- long, W = 2020-07-20: W-1 H 11058.25 L 10358.75 C 10623.50; W H 11057.75 (<= 11058.25) L 10301.25 (< 10358.75)
  C 10463.00 (> 10358.75); W+1 H 10939.25 L 10400.50: never above 11057.75 nor 11058.25 -> no, no.
- long, W = 2022-02-21: W-1 H 14668.50 L 13906.00; W H 14198.00 L 13025.75 C 14191.25; W+1 H 14391.25: above 14198.00
  at 2022-02-28 10:41 -> yes; never above 14668.50 -> no.
- short, W = 2021-07-12: W-1 H 14883.75 L 14540.00; W H 14996.00 (> 14883.75) L 14657.25 (>= 14540.00) C 14670.75
  (< 14883.75); W+1 L 14444.25: below 14657.25 at 07-18 18:51 -> yes; below 14540.00 at 07-19 07:32 -> yes.
- short, W = 2022-08-15: W-1 H 13583.00 L 12963.25; W H 13740.50 L 13227.00 C 13249.75; W+1 L 12555.25: below 13227.00
  at 08-21 18:00 -> yes; below 12963.25 at 08-22 10:34 -> yes.

L3 (H / L / C of each day; outcome 1 = close beyond, outcome 2 = trades beyond)
- long claim, D = 2021-07-22: 07-19 14683.25 / 14444.25 / 14592.25 (not an up close: 07-16 high 14869.50);
  07-20 14782.25 / 14516.75 / **14727.50**; 07-21 14841.75 / 14666.75 / **14837.75**; 07-22 14982.75 / 14823.25 /
  **14976.25**; D+1 07-23 15117.50 / 14934.25 / 15093.00 -> close above 14982.75 yes; trades above yes (07-22 18:01).
- long claim, D = 2021-08-24: 08-19 high 14999.00 (close 14944.25 < 08-18 high 15037.00); 08-20 C 15095.00; 08-23 H
  15338.00 C 15328.75; 08-24 H 15384.00 C 15362.25; D+1 08-25 15397.00 / 15333.00 / 15365.75 -> close no; trades
  above 15384.00 yes (04:16).
- short claim, D = 2022-03-08: 03-03 L 13955.00 (not a down close); 03-04 L 13733.50 C 13802.75; 03-07 L 13265.00
  C 13270.50; 03-08 L 13105.25 C 13199.75; D+1 03-09 13822.50 / 13192.00 / 13772.25 -> no, no.
- short claim, D = 2022-06-13: 06-08 L 12579.00; 06-09 L 12255.50 C 12297.25; 06-10 L 11822.75 C 11861.75; 06-13
  L 11254.50 C 11331.25; D+1 06-14 11505.25 / 11204.75 / 11329.50 -> close no; trades below 11254.50 yes (10:30).
- base: long first, D = 2020-05-25 (Memorial Day candle, to 12:59): C 9532.50 > 05-22 high 9422.75, 05-22 not an up
  close; D+1 9604.00 / 9373.00 / 9412.50 -> no, yes. long second, D = 2020-12-29: 12-28 C 12842.00 > 12-24 high
  12724.00 (12-25 has no candle and is skipped), 12-29 C 12858.00 > 12855.75; D+1 H 12909.75 < 12918.25 -> no, no.
  short first, D = 2020-10-14: C 11943.25 < 12018.00; D+1 L 11737.00 C 11882.75 < 11901.75 -> yes, yes. short second,
  D = 2021-02-23: 02-22 C 13221.00 < 13534.25, 02-23 L 12757.50 C 13158.25 < 13215.00; D+1 L 12958.00 -> no, no.

L4 (H / L / C per day)
- short (up week), 2020-06-29: Mon 9997.25 / **9729.00** / 9986.00; Tue 10171.50 / 9940.00 / 10136.50; Wed 10309.00 /
  10075.75 / 10255.50; Thu **10422.50** / 10247.75 / **10350.25**. R 693.50, top quarter from 10249.125, level
  10283.80. Fri (to 12:59) low 10309.00 -> not reached.
- short, 2021-11-01: Mon low 15768.75, Thu high 16378.50, Thu close 16338.00 (top quarter from 16226.06), level
  16256.55; Fri 16448.50 / 16292.25 -> not reached.
- short, holiday week 2019-12-23 (no Wednesday candle; range = Mon, Tue, Thu): Mon 8743.50 / 8705.00 / 8728.50; Tue
  8736.00 / 8707.50 / 8730.00; Thu 8805.75 / 8726.00 / 8802.50. R 100.75, top quarter from 8780.56, level 8785.60;
  Fri low 8769.75 -> reached. (This week is not a base case: the base needs a Wednesday candle.)
- long (down week), 2020-03-09: Mon high 8418.25, Thu low 7131.75, Thu close 7161.75 (bottom quarter up to 7453.375),
  level 7389.05; Fri high 7980.00 -> reached.
- long, 2022-04-04: Tue high 15199.25, Thu low 14318.25, R 881.00, Thu close 14534.50 (bottom quarter up to 14538.50),
  level 14494.45: the close is already above it (`at_close`); Fri high 14642.50 -> reached.
- base short, 2019-09-09: Mon-Wed H 7899.75 (Wed) L 7744.25 (Tue), Wed close 7892.00 (top quarter from 7860.875),
  level 7868.65; Thu low 7886.75 -> not reached. base long, 2019-09-30: H 7841.50 (Tue) L 7525.50 (Wed), Wed close
  7554.50 (bottom quarter up to 7604.50), level 7588.70; Thu high 7660.00 -> reached.
- The eight usable weeks with 4 candles were printed: the five without a Friday candle are not claim cases and are
  base weeks; the two without a Wednesday are claim weeks (3-candle range) and not base weeks; 2022-12-26 (no Monday)
  is a claim week on Tue-Thu and a base week on Tue-Wed.

Second route for whole rows: daily candles rebuilt by a pandas groupby on trading date (equal to tt.daily: 926
candles, same highs, lows, closes, roll flags), weeks by groupby on the Monday, every claim recounted with pandas
shifts / pivot and float arithmetic: all 12 long / short rows reproduce n, k, base_n, base_k exactly. `both` =
long + short on every row; z and p equal scipy.

Conditions do not read the future: on five cuts (2020-02-05 11:29, 2020-11-13 16:59, 2021-08-19 16:59,
2022-05-11 16:59, 2022-10-03 03:10) the bars after the cut were replaced by the harness's mirrored future; every
weekly condition of every week closed by the cut, every daily run position of every day closed by the cut and every
L4 condition whose Thursday (base: Wednesday) had closed were identical; only later candles and outcomes changed.

Additivity: the module was run on bars cut at 2021-01-01, 2021-05-12 12:00, 2021-11-26 13:15 and 2022-04-15; every
case of the short run is a case of the long run with the same flags and outcomes, and no case wholly before the cut
is missing. A case is keyed by its condition week / day and exists only once its outcome week / day is complete, so
full-span counts minus these in-sample counts = the cases whose outcome week / day lies after 2022-12-30 (L1 / L2:
W from 2022-12-26; L3: D from 2022-12-30; L4: weeks from 2023-01-02).

## 5. For whoever reads the table
- L1, L2: the base is "every week", so the claim's weeks are part of the base (a subset against its superset); the
  base of a `both` row counts every week twice (once per side).
- L2: by the condition, week W has not traded beyond W-1's far extreme, so `beyond_prev` implies `beyond_w` for the
  claim's cases; in the base it does not (the base is every week).
- L3: the base is days 1 and 2 of a run, not all days; `L3_positions` gives position 0 (no continuation close) and
  4+ as well. `cont` implies `beyond`.
- L4: claim and base are two tests on overlapping weeks (not subset / superset, not independent samples).
- Sample sizes are small: L2 15 / 22 cases, L3 29 / 10, L4 20 / 60.
- tt.daily's candle of 2020-06-30 ends with a bar stamped 17:59 and the next one starts at 20:00 (seen in the hand
  check); used as tt.daily gives them.

## 6. Final in-sample output (2019-06-02 -> 2022-12-30)
```
K-H  TTrades weekly and sequence claims L1 L2 L3 L4, each rate next to its base rate   phase is   bars 2019-06-02 18:00:00-04:00 -> 2022-12-30 16:59:00-05:00
TTrades weekly and sequence claims (YT6_SPEC.md Part 2), each rate next to its base rate    2019-06-02 -> 2022-12-30
  day  candles 926 (roll 16, unfinished last candle dropped 0, dated Sat/Sun 0, prices off the tick grid 0)
       L3 days 830; left out {'total': 96, 'first_4_or_last_candle': 5, 'roll_candle_in_window': 91}
  week calendar weeks 187: fewer than 4 candles 0 [], with a roll candle 16 (both 0), unfinished 0; usable 171 (of them with 4 candles 8)
       roll weeks ['2019-06-03', '2019-06-17', '2019-09-16', '2019-12-16', '2020-03-16', '2020-06-15', '2020-09-14', '2020-12-14', '2021-03-15', '2021-06-14', '2021-09-13', '2021-12-13', '2022-03-14', '2022-06-13', '2022-09-12', '2022-12-12']
       L1 / L2 weeks W with W-1, W, W+1 usable: 140; usable but a neighbour is not: 31 (first / last week of the data 1)
       L4 claim weeks 166 (no Thursday or Friday candle 5 ['2020-04-06', '2020-12-21', '2020-12-28', '2021-12-20', '2022-04-11']; range of fewer than 4 candles 3); base weeks 169 (no Wednesday or Thursday candle 2 ['2019-12-23', '2019-12-30']; range of fewer than 3 candles 1)
  * = p < 0.05 / 8 = 0.00625
  key                                         n      k   rate   base n base k   base  diff pp         p

  L1.wk.long.beyond.all                      62     50  80.7%      140     84  60.0%    +20.6    0.0042*
  L1.wk.short.beyond.all                     26     20  76.9%      140     56  40.0%    +36.9    0.0005*
  L1.wk.both.beyond.all                      88     70  79.5%      280    140  50.0%    +29.6    0.0000*

  L2.wk.long.beyond_w.all                    15     12  80.0%      140     84  60.0%    +20.0    0.1290 
  L2.wk.short.beyond_w.all                   22     12  54.5%      140     56  40.0%    +14.6    0.1990 
  L2.wk.both.beyond_w.all                    37     24  64.9%      280    140  50.0%    +14.9    0.0890 
  L2.wk.long.beyond_prev.all                 15      8  53.3%      140     97  69.3%    -15.9    0.2090 
  L2.wk.short.beyond_prev.all                22      7  31.8%      140     53  37.9%     -6.0    0.5860 
  L2.wk.both.beyond_prev.all                 37     15  40.5%      280    150  53.6%    -13.0    0.1360 

  L3.day.long.cont.run12                     29     10  34.5%      224    102  45.5%    -11.1    0.2600 
  L3.day.short.cont.run12                    10      2  20.0%      169     54  31.9%    -11.9    0.4280 
  L3.day.both.cont.run12                     39     12  30.8%      393    156  39.7%     -8.9    0.2750 
  L3.day.long.beyond.run12                   29     19  65.5%      224    183  81.7%    -16.2    0.0410 
  L3.day.short.beyond.run12                  10      5  50.0%      169    118  69.8%    -19.8    0.1890 
  L3.day.both.beyond.run12                   39     24  61.5%      393    301  76.6%    -15.1    0.0378 

  L4.wk.long.retrace20.day_before            20     17  85.0%       33     28  84.9%     +0.1    0.9880    already there at the close 7 / 5
  L4.wk.short.retrace20.day_before           60     41  68.3%       64     46  71.9%     -3.5    0.6670    already there at the close 6 / 8
  L4.wk.both.retrace20.day_before            80     58  72.5%       97     74  76.3%     -3.8    0.5650    already there at the close 13 / 13

  L3 by position in the run (not registered, description): n, next day another continuation close, next day trades beyond
  long    0: 561 / 155 / 254 (28%, 45%)  1: 152 / 74 / 132 (49%, 87%)  2: 72 / 28 / 51 (39%, 71%)  3: 29 / 10 / 19 (34%, 66%)  4+: 16 / 5 / 14 (31%, 88%)
  short   0: 649 / 123 / 241 (19%, 37%)  1: 124 / 44 / 92 (35%, 74%)  2: 45 / 10 / 26 (22%, 58%)  3: 10 / 2 / 5 (20%, 50%)  4+: 2 / 0 / 2 (0%, 100%)
```
