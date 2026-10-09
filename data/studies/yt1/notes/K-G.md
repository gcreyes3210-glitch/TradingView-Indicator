# K-G - TTrades candle claims A, B, C, F, G, I, J, K, claim check (`tools/yt1/k_G.py`)

Spec: `YT4_SPEC.md` Part 1. TTrades gives no hit rates, so there is no claimed figure: every measured rate stands
next to a base rate (the same outcome on the same candle series without the condition), with the difference and a
two-sided two-proportion z-test (pooled variance, `math.erfc`; checked against scipy). No pass / fail. The spec reads
a difference with p > 0.05 / 14 = 0.00357 as no difference; the printed table marks p <= 0.00357 with `*`.

Result keys: `rows["<claim>.<series>.<side>.<outcome>.<base>"]` = n, k, rate, base_n, base_k, base_rate, diff_pp, z, p.
series: `d18` (daily 18:00 -> 17:00), `d00` (daily midnight to midnight), `4h`, `1h`; for I `<bias series>_<open>`.
side: `long`, `short`, `both` (the two sides' counts added, claim and base alike, so a `both` base counts every
candle twice). outcome and base names are explained in `legend` inside the JSON.

## 1. Readings added beyond the spec text (all fixed before the first run)
Candles
- "At least half its minutes" = half of the candle's clock span: 690 of 1,380 (d18), 720 of 1,440 (d00), 120 of 240
  (4H, also for the 14:00 candle, which can only hold 180), 30 of 60 (1H). In-sample this drops 1 trading day
  (2020-03-16, 571 minutes), 190 calendar days, 10 4H candles and 53 1H candles.
- d00 = the calendar day. A Sunday holds 18:00-23:59 only (360 minutes) and is therefore not a candle: Sunday evening
  belongs to no d00 candle and Monday's candle follows Friday's.
- d18: two stray bars stamped 17:59 belong to no trading day (the day is 18:00 -> 17:00). In the 4H series such a bar
  falls in the 14:00 candle (four clock hours), in d00 in its calendar day.
- The series is the candles that count, in time order; D-1, D+1, D-5, C1..C4 are positions in that series.
- Roll: a roll candle = the contract of its last bar differs from that of the previous candle's last bar. The roll
  candle and the candle after it are flagged and a case is dropped when any candle it uses is flagged (A, B: D-1, D,
  D+1; C: C1..C4; K: D-5..D+1; G: the 4H candle and the one before, and the 1H candle must be the same contract;
  F: the day itself). The base is counted on exactly the same eligible set as the claim.
- "Trades above x" = high >= x + 0.25; "takes" the same. Closes above / below: strict.
- Order inside the next candle: the first 1-minute bar trading above high(D) against the first trading below low(D).
  Same 1-minute bar = neither side (the case stays in the denominator); counted as `same_bar` / `base_same_bar`.

Claims
- A, B, K `first`: "takes high(D) before low(D)" is also true when only the high is taken.
- B long = the mirror (low(D) < low(D-1), close(D) > low(D-1), high(D) <= high(D-1) -> D+1 trades above high(D)).
- C: base "every candle" = every candle as C3 with C1..C4 unflagged; "closed up" = close(C3) > open(C3).
- F: the low is "printed" at the FIRST 1-minute bar that shows the day's low. Day closes above its 18:00 open =
  close > open of the candle's first bar (1 day's first bar is not 18:00; 1 day closes at its open and is in neither
  group). The spec names no base for F: the row compares days that close up (claim) with all days (base); the block
  table gives each block's share of the day's minutes as a reference. **The spec lists no mirror for F**: the
  `short` row (high first printed 08:00-09:59 on days closing below the open) and the `both` row were added
  because the task asked for both sides of every claim; only `F.d18.long` is the registered one.
- G: "the last 1H candle before it opened" = the last 1H candle of the series that ended before the 4H candle's
  first bar (for the 18:00 candle that is the 16:00 hour, on Sunday Friday's). "Inside" includes the edges.
- I, bias: A's and B's conditions exactly, on the last daily candle dated before the cash day against the one before
  it. Bullish = close > previous high, or (low < previous low, close > previous low, high <= previous high); bearish
  = the mirrors; they cannot overlap. An outside day that closes back inside has no bias (B's third clause). Days
  left out: roll day and the day after (the harness's `roll2_dates`), and days whose two bias candles include a
  flagged one.
- I, event (long): from the 09:30 bar on, a 1-minute bar trades >= 1 tick below the 09:30 open; then the first
  5-minute bar (`ctx.bars(5)`) whose last minute is not earlier than that bar, that ends by 11:30 and closes above
  the open. The run and the close-back may be the same 5-minute bar. Run's low = lowest low from 09:30 through the
  close-back bar. Outcome = no later bar before 16:00 trades >= 1 tick below it. One event per day and side. The
  08:30 version: run and close-back in 08:30-09:29, outcome to 16:00. Both the long and the short event are looked
  for on every day; the claim is the event in the bias direction.
- I, base: the spec's two bases are reported separately (`nobias`, `opp`) and together (`rest`).
- J: low before high = the first bar at the 09:30-16:00 low is earlier than the first bar at the high. Base "all
  days" = all days with a bias state (bullish, bearish or none), i.e. the same days left out as in I.
- I and J are also reported with the bias taken from d00 candles (the spec's "reported a second time on
  midnight-to-midnight days" read as applying wherever the daily candle is used). F is 18:00 -> 17:00 only, as the
  spec says.
- Early-close days are kept; "by 16:00" then ends at the halt.

## 2. Coding errors found after first seeing results
- Before any number was printed: the first run stopped on a Python error in the counts dictionary (a duplicated
  keyword). Fixed; no definition involved.
- After the first table: the label of the last block of the F table read "16:00-17:59"; it is 16:00-16:59. Label
  only; the rerun is identical to the first table in every number.
No definition, threshold or reading was changed after the first run.

## 3. Hand check
- Claim A (d18), five cases printed with the candles D-1, D, D+1 rebuilt by pandas (groupby trading date) and the
  first 1-minute bars of D+1 beyond high(D) / low(D): long 2019-11-15 (close 8323.75 > 8285.25; high 8323.75 taken
  2019-11-18 02:14, low never), 2019-11-18 (8334.25 > 8323.75; high 8366.00 taken 04:51 next day, low never),
  2022-02-28 (14217.75 > 14198.00; high 14292.50 taken 02:06, low never); short 2021-12-31 (close 16333.50 <
  16411.25; next day took the HIGH 16464.00 at 09:37 before the low 16313.25 at 09:50: counted as below-low yes,
  low-first no), 2022-03-31 (14917.25 < 15012.00; low 14855.50 taken 09:50 next day, high never). All as the module.
- Claim I (bias d18), five cases with the two bias candles, the open, the first 1-minute bar through it, the
  5-minute bars up to the close-back and the extreme afterwards: 2019-07-11 09:30 long (bias: 7926.50 > 7858.75;
  open 7939.75, 09:30 bar low 7934.00, first 5-minute bar closes 7943.00, run low 7930.00, broken 10:30 -> fails),
  2022-02-11 09:30 short (14696.25 < 14740.00; open 14700.25, run high 14750.50, second 5-minute bar closes
  14683.25, broken 09:46 -> fails), 2020-10-13 08:30 long (run low 12193.75, broken 08:43 -> fails), 2021-08-23
  09:30 long (run low 15124.75, lowest later price 15145.25 -> holds), 2020-07-17 08:30 short (run high 10625.00,
  broken 08:41 -> fails). All as the module.
- Second route for whole rows: the d18 series equals a pandas groupby (926 candles) and A.d18 `beyond` counts
  recomputed with shifts; the 4H and 1H series equal `core.resample` (240 minutes offset 120; 60 minutes) and
  C.4h (long holds_mid with both bases, short both), G (plus five G cases read by eye), K.d18, F (pandas idxmin)
  and J.d18 (pandas idxmin / idxmax, extremes equal to the day table's rth_h / rth_l) all reproduce the module's
  counts exactly.
- Conditions do not read the future: on six random cuts (11:29 of a cash day, 60 days of bars before, 7 after) the
  future was replaced by the harness's mirrored one; every candle closed by the cut, every A / B condition, every
  bias and every I event (bar, run extreme) up to that day was identical; only outcomes changed.

## 4. For whoever reads the table
- Where the base is "every candle / day" the claim's cases are part of the base, so the test is of a subset against
  its superset; the complement is base minus claim, from the counts given.
- C is the only family with a second base. Against every candle the differences are +11 to +27 points; against
  candles that closed the same way they are -1 to +9 points and only C.4h.long (holds_mid, both) is below 0.00357.
- I: the literal event is frequent (about 80 % of bias days) and small: 57-65 % of events complete inside the first
  5-minute bar; the median run is 16-23 points at 09:30 and about 5 points at 08:30.
- A p printed as 0 is below the smallest float (A.1h.both.first).

## 5. Final in-sample output (2019-06-02 -> 2022-12-30)
```
K-G  TTrades candle claims A B C F G I J K, each rate next to its base rate   phase is   bars 2019-06-02 18:00:00-04:00 -> 2022-12-30 16:59:00-05:00
TTrades candle claims (YT4_SPEC.md Part 1), each rate next to its base rate    2019-06-02 -> 2022-12-30
  d18  candles    926 (under half their minutes 3, roll 15, flagged 30)   A/B triples 864, C quads 848
  d00  candles    926 (under half their minutes 190, roll 15, flagged 30)   A/B triples 864, C quads 848
  4h   candles   5521 (under half their minutes 10, roll 15, flagged 30)   A/B triples 5459, C quads 5443
  1h   candles  21151 (under half their minutes 53, roll 15, flagged 30)   A/B triples 21089, C quads 21073
  bias d18: {'cash_days': 926, 'used': 863, 'bullish': 416, 'bearish': 320, 'none': 127, 'kinds': {'A_long': 284, 'A_short': 185, 'B_long': 132, 'B_short': 135, 'bias_candle_flagged': 31, 'no_previous_candles': 2, 'none': 127, 'roll_day_or_day_after': 30}}
     0930 events: {'days_without_open_bar': 0, 'long_event': {'bullish': 334, 'none': 106, 'bearish': 282}, 'short_event': {'bullish': 347, 'none': 96, 'bearish': 258}}
     0830 events: {'days_without_open_bar': 1, 'long_event': {'bullish': 328, 'none': 99, 'bearish': 244}, 'short_event': {'bullish': 321, 'none': 99, 'bearish': 248}}
  bias d00: {'cash_days': 926, 'used': 872, 'bullish': 416, 'bearish': 323, 'none': 133, 'kinds': {'A_long': 285, 'A_short': 191, 'B_long': 131, 'B_short': 132, 'bias_candle_flagged': 22, 'no_previous_candles': 2, 'none': 133, 'roll_day_or_day_after': 30}}
     0930 events: {'days_without_open_bar': 0, 'long_event': {'bullish': 340, 'none': 109, 'bearish': 281}, 'short_event': {'bullish': 341, 'none': 104, 'bearish': 263}}
     0830 events: {'days_without_open_bar': 1, 'long_event': {'bullish': 333, 'none': 100, 'bearish': 246}, 'short_event': {'bullish': 323, 'none': 105, 'bearish': 249}}
  F days 896 (first bar not 18:00: 1, close = open: 1);  G 4H candles 5475 (bars between the 1H candle and the 4H open: 13);  K inside days d18 87, d00 93
  * = p <= 0.05 / 14 = 0.00357
  key                                         n      k   rate   base n base k   base  diff pp         p

  A.d18.long.beyond.all                     285    230  80.7%      864    489  56.6%    +24.1    0.0000*
  A.d18.short.beyond.all                    185    128  69.2%      864    383  44.3%    +24.9    0.0000*
  A.d18.both.beyond.all                     470    358  76.2%     1728    872  50.5%    +25.7    0.0000*
  A.d18.long.first.all                      285    224  78.6%      864    450  52.1%    +26.5    0.0000*   same bar 0 / 1
  A.d18.short.first.all                     185    123  66.5%      864    316  36.6%    +29.9    0.0000*   same bar 1 / 1
  A.d18.both.first.all                      470    347  73.8%     1728    766  44.3%    +29.5    0.0000*   same bar 1 / 2
  A.d00.long.beyond.all                     281    210  74.7%      864    474  54.9%    +19.9    0.0000*
  A.d00.short.beyond.all                    189    128  67.7%      864    388  44.9%    +22.8    0.0000*
  A.d00.both.beyond.all                     470    338  71.9%     1728    862  49.9%    +22.0    0.0000*
  A.d00.long.first.all                      281    207  73.7%      864    431  49.9%    +23.8    0.0000*   same bar 0 / 1
  A.d00.short.first.all                     189    124  65.6%      864    330  38.2%    +27.4    0.0000*   same bar 1 / 1
  A.d00.both.first.all                      470    331  70.4%     1728    761  44.0%    +26.4    0.0000*   same bar 1 / 2
  A.4h.long.beyond.all                     1552   1117  72.0%     5459   2834  51.9%    +20.1    0.0000*
  A.4h.short.beyond.all                    1155    737  63.8%     5459   2412  44.2%    +19.6    0.0000*
  A.4h.both.beyond.all                     2707   1854  68.5%    10918   5246  48.0%    +20.4    0.0000*
  A.4h.long.first.all                      1552   1083  69.8%     5459   2488  45.6%    +24.2    0.0000*   same bar 1 / 4
  A.4h.short.first.all                     1155    715  61.9%     5459   2025  37.1%    +24.8    0.0000*   same bar 1 / 4
  A.4h.both.first.all                      2707   1798  66.4%    10918   4513  41.3%    +25.1    0.0000*   same bar 2 / 8
  A.1h.long.beyond.all                     5526   3843  69.5%    21089  10489  49.7%    +19.8    0.0000*
  A.1h.short.beyond.all                    4477   2948  65.8%    21089   9372  44.4%    +21.4    0.0000*
  A.1h.both.beyond.all                    10003   6791  67.9%    42178  19861  47.1%    +20.8    0.0000*
  A.1h.long.first.all                      5526   3737  67.6%    21089   9355  44.4%    +23.3    0.0000*   same bar 6 / 27
  A.1h.short.first.all                     4477   2884  64.4%    21089   8177  38.8%    +25.6    0.0000*   same bar 6 / 27
  A.1h.both.first.all                     10003   6621  66.2%    42178  17532  41.6%    +24.6    0.0000*   same bar 12 / 54

  B.d18.long.beyond.all                     132     91  68.9%      864    489  56.6%    +12.3    0.0074 
  B.d18.short.beyond.all                    135     87  64.4%      864    383  44.3%    +20.1    0.0000*
  B.d18.both.beyond.all                     267    178  66.7%     1728    872  50.5%    +16.2    0.0000*
  B.d18.long.first.all                      132     87  65.9%      864    450  52.1%    +13.8    0.0030*   same bar 0 / 1
  B.d18.short.first.all                     135     85  63.0%      864    316  36.6%    +26.4    0.0000*   same bar 0 / 1
  B.d18.both.first.all                      267    172  64.4%     1728    766  44.3%    +20.1    0.0000*   same bar 0 / 2
  B.d00.long.beyond.all                     131     90  68.7%      864    474  54.9%    +13.8    0.0029*
  B.d00.short.beyond.all                    131     82  62.6%      864    388  44.9%    +17.7    0.0002*
  B.d00.both.beyond.all                     262    172  65.6%     1728    862  49.9%    +15.8    0.0000*
  B.d00.long.first.all                      131     84  64.1%      864    431  49.9%    +14.2    0.0024*   same bar 0 / 1
  B.d00.short.first.all                     131     79  60.3%      864    330  38.2%    +22.1    0.0000*   same bar 0 / 1
  B.d00.both.first.all                      262    163  62.2%     1728    761  44.0%    +18.2    0.0000*   same bar 0 / 2
  B.4h.long.beyond.all                      734    441  60.1%     5459   2834  51.9%     +8.2    0.0000*
  B.4h.short.beyond.all                     772    442  57.2%     5459   2412  44.2%    +13.1    0.0000*
  B.4h.both.beyond.all                     1506    883  58.6%    10918   5246  48.0%    +10.6    0.0000*
  B.4h.long.first.all                       734    416  56.7%     5459   2488  45.6%    +11.1    0.0000*   same bar 0 / 4
  B.4h.short.first.all                      772    403  52.2%     5459   2025  37.1%    +15.1    0.0000*   same bar 0 / 4
  B.4h.both.first.all                      1506    819  54.4%    10918   4513  41.3%    +13.1    0.0000*   same bar 0 / 8
  B.1h.long.beyond.all                     3218   1986  61.7%    21089  10489  49.7%    +12.0    0.0000*
  B.1h.short.beyond.all                    3339   1954  58.5%    21089   9372  44.4%    +14.1    0.0000*
  B.1h.both.beyond.all                     6557   3940  60.1%    42178  19861  47.1%    +13.0    0.0000*
  B.1h.long.first.all                      3218   1822  56.6%    21089   9355  44.4%    +12.3    0.0000*   same bar 5 / 27
  B.1h.short.first.all                     3339   1805  54.1%    21089   8177  38.8%    +15.3    0.0000*   same bar 1 / 27
  B.1h.both.first.all                      6557   3627  55.3%    42178  17532  41.6%    +13.8    0.0000*   same bar 6 / 54

  C.d18.long.holds_mid.all                  111     56  50.4%      848    203  23.9%    +26.5    0.0000*
  C.d18.short.holds_mid.all                 101     34  33.7%      848     98  11.6%    +22.1    0.0000*
  C.d18.both.holds_mid.all                  212     90  42.4%     1696    301  17.8%    +24.7    0.0000*
  C.d18.long.holds_mid.closed_dir           111     56  50.4%      466    199  42.7%     +7.8    0.1400 
  C.d18.short.holds_mid.closed_dir          101     34  33.7%      381     95  24.9%     +8.7    0.0781 
  C.d18.both.holds_mid.closed_dir           212     90  42.4%      847    294  34.7%     +7.7    0.0360 
  C.d18.long.beyond.all                     111     87  78.4%      848    479  56.5%    +21.9    0.0000*
  C.d18.short.beyond.all                    101     71  70.3%      848    376  44.3%    +26.0    0.0000*
  C.d18.both.beyond.all                     212    158  74.5%     1696    855  50.4%    +24.1    0.0000*
  C.d18.long.beyond.closed_dir              111     87  78.4%      466    365  78.3%     +0.1    0.9900 
  C.d18.short.beyond.closed_dir             101     71  70.3%      381    252  66.1%     +4.2    0.4300 
  C.d18.both.beyond.closed_dir              212    158  74.5%      847    617  72.9%     +1.7    0.6210 
  C.d18.long.both.all                       111     54  48.6%      848    200  23.6%    +25.1    0.0000*
  C.d18.short.both.all                      101     34  33.7%      848     97  11.4%    +22.2    0.0000*
  C.d18.both.both.all                       212     88  41.5%     1696    297  17.5%    +24.0    0.0000*
  C.d18.long.both.closed_dir                111     54  48.6%      466    196  42.1%     +6.6    0.2080 
  C.d18.short.both.closed_dir               101     34  33.7%      381     94  24.7%     +9.0    0.0689 
  C.d18.both.both.closed_dir                212     88  41.5%      847    290  34.2%     +7.3    0.0481 
  C.d00.long.holds_mid.all                  104     48  46.2%      848    204  24.1%    +22.1    0.0000*
  C.d00.short.holds_mid.all                 110     35  31.8%      848    100  11.8%    +20.0    0.0000*
  C.d00.both.holds_mid.all                  214     83  38.8%     1696    304  17.9%    +20.9    0.0000*
  C.d00.long.holds_mid.closed_dir           104     48  46.2%      464    184  39.7%     +6.5    0.2230 
  C.d00.short.holds_mid.closed_dir          110     35  31.8%      382     97  25.4%     +6.4    0.1800 
  C.d00.both.holds_mid.closed_dir           214     83  38.8%      846    281  33.2%     +5.6    0.1250 
  C.d00.long.beyond.all                     104     79  76.0%      848    464  54.7%    +21.2    0.0000*
  C.d00.short.beyond.all                    110     75  68.2%      848    381  44.9%    +23.2    0.0000*
  C.d00.both.beyond.all                     214    154  72.0%     1696    845  49.8%    +22.1    0.0000*
  C.d00.long.beyond.closed_dir              104     79  76.0%      464    343  73.9%     +2.0    0.6670 
  C.d00.short.beyond.closed_dir             110     75  68.2%      382    252  66.0%     +2.2    0.6650 
  C.d00.both.beyond.closed_dir              214    154  72.0%      846    595  70.3%     +1.6    0.6400 
  C.d00.long.both.all                       104     45  43.3%      848    200  23.6%    +19.7    0.0000*
  C.d00.short.both.all                      110     35  31.8%      848     99  11.7%    +20.1    0.0000*
  C.d00.both.both.all                       214     80  37.4%     1696    299  17.6%    +19.8    0.0000*
  C.d00.long.both.closed_dir                104     45  43.3%      464    180  38.8%     +4.5    0.3990 
  C.d00.short.both.closed_dir               110     35  31.8%      382     96  25.1%     +6.7    0.1620 
  C.d00.both.both.closed_dir                214     80  37.4%      846    276  32.6%     +4.8    0.1880 
  C.4h.long.holds_mid.all                   647    276  42.7%     5443   1172  21.5%    +21.1    0.0000*
  C.4h.short.holds_mid.all                  593    156  26.3%     5443    729  13.4%    +12.9    0.0000*
  C.4h.both.holds_mid.all                  1240    432  34.8%    10886   1901  17.5%    +17.4    0.0000*
  C.4h.long.holds_mid.closed_dir            647    276  42.7%     2929   1065  36.4%     +6.3    0.0027*
  C.4h.short.holds_mid.closed_dir           593    156  26.3%     2506    659  26.3%     +0.0    0.9960 
  C.4h.both.holds_mid.closed_dir           1240    432  34.8%     5435   1724  31.7%     +3.1    0.0341 
  C.4h.long.beyond.all                      647    464  71.7%     5443   2824  51.9%    +19.8    0.0000*
  C.4h.short.beyond.all                     593    357  60.2%     5443   2406  44.2%    +16.0    0.0000*
  C.4h.both.beyond.all                     1240    821  66.2%    10886   5230  48.0%    +18.2    0.0000*
  C.4h.long.beyond.closed_dir               647    464  71.7%     2929   2008  68.6%     +3.2    0.1150 
  C.4h.short.beyond.closed_dir              593    357  60.2%     2506   1526  60.9%     -0.7    0.7560 
  C.4h.both.beyond.closed_dir              1240    821  66.2%     5435   3534  65.0%     +1.2    0.4280 
  C.4h.long.both.all                        647    255  39.4%     5443   1053  19.4%    +20.1    0.0000*
  C.4h.short.both.all                       593    137  23.1%     5443    647  11.9%    +11.2    0.0000*
  C.4h.both.both.all                       1240    392  31.6%    10886   1700  15.6%    +16.0    0.0000*
  C.4h.long.both.closed_dir                 647    255  39.4%     2929    962  32.8%     +6.6    0.0014*
  C.4h.short.both.closed_dir                593    137  23.1%     2506    583  23.3%     -0.2    0.9330 
  C.4h.both.both.closed_dir                1240    392  31.6%     5435   1545  28.4%     +3.2    0.0257 
  C.1h.long.holds_mid.all                  2459    891  36.2%    21073   4038  19.2%    +17.1    0.0000*
  C.1h.short.holds_mid.all                 2290    663  28.9%    21073   2990  14.2%    +14.8    0.0000*
  C.1h.both.holds_mid.all                  4749   1554  32.7%    42146   7028  16.7%    +16.1    0.0000*
  C.1h.long.holds_mid.closed_dir           2459    891  36.2%    10955   3694  33.7%     +2.5    0.0175 
  C.1h.short.holds_mid.closed_dir          2290    663  28.9%     9999   2750  27.5%     +1.4    0.1620 
  C.1h.both.holds_mid.closed_dir           4749   1554  32.7%    20954   6444  30.8%     +2.0    0.0081 
  C.1h.long.beyond.all                     2459   1692  68.8%    21073  10487  49.8%    +19.0    0.0000*
  C.1h.short.beyond.all                    2290   1420  62.0%    21073   9365  44.4%    +17.6    0.0000*
  C.1h.both.beyond.all                     4749   3112  65.5%    42146  19852  47.1%    +18.4    0.0000*
  C.1h.long.beyond.closed_dir              2459   1692  68.8%    10955   7338  67.0%     +1.8    0.0812 
  C.1h.short.beyond.closed_dir             2290   1420  62.0%     9999   6227  62.3%     -0.3    0.8120 
  C.1h.both.beyond.closed_dir              4749   3112  65.5%    20954  13565  64.7%     +0.8    0.3020 
  C.1h.long.both.all                       2459    819  33.3%    21073   3729  17.7%    +15.6    0.0000*
  C.1h.short.both.all                      2290    606  26.5%    21073   2756  13.1%    +13.4    0.0000*
  C.1h.both.both.all                       4749   1425  30.0%    42146   6485  15.4%    +14.6    0.0000*
  C.1h.long.both.closed_dir                2459    819  33.3%    10955   3403  31.1%     +2.2    0.0305 
  C.1h.short.both.closed_dir               2290    606  26.5%     9999   2531  25.3%     +1.1    0.2550 
  C.1h.both.both.closed_dir                4749   1425  30.0%    20954   5934  28.3%     +1.7    0.0202 

  F.d18.long.ext_0800_0959.all              495     82  16.6%      896    111  12.4%     +4.2    0.0309 
  F.d18.short.ext_0800_0959.all             400     74  18.5%      896    119  13.3%     +5.2    0.0148 
  F.d18.both.ext_0800_0959.all              895    156  17.4%     1792    230  12.8%     +4.6    0.0014*

  G.4h.long.wick_in_1h.all                 1594    937  58.8%     5475   1874  34.2%    +24.6    0.0000*
  G.4h.short.wick_in_1h.all                1169    646  55.3%     5475   1492  27.3%    +28.0    0.0000*
  G.4h.both.wick_in_1h.all                 2763   1583  57.3%    10950   3366  30.7%    +26.6    0.0000*

  I.d18_0930.long.run_holds.nobias          334    122  36.5%      106     39  36.8%     -0.3    0.9610 
  I.d18_0930.short.run_holds.nobias         258     69  26.7%       96     28  29.2%     -2.4    0.6500 
  I.d18_0930.both.run_holds.nobias          592    191  32.3%      202     67  33.2%     -0.9    0.8130 
  I.d18_0930.long.run_holds.opp             334    122  36.5%      282     85  30.1%     +6.4    0.0946 
  I.d18_0930.short.run_holds.opp            258     69  26.7%      347    101  29.1%     -2.4    0.5230 
  I.d18_0930.both.run_holds.opp             592    191  32.3%      629    186  29.6%     +2.7    0.3090 
  I.d18_0930.long.run_holds.rest            334    122  36.5%      388    124  32.0%     +4.6    0.1970 
  I.d18_0930.short.run_holds.rest           258     69  26.7%      443    129  29.1%     -2.4    0.5000 
  I.d18_0930.both.run_holds.rest            592    191  32.3%      831    253  30.4%     +1.8    0.4660 
  I.d18_0830.long.run_holds.nobias          328     41  12.5%       99     15  15.2%     -2.6    0.4930 
  I.d18_0830.short.run_holds.nobias         248     21   8.5%       99     12  12.1%     -3.6    0.2950 
  I.d18_0830.both.run_holds.nobias          576     62  10.8%      198     27  13.6%     -2.9    0.2740 
  I.d18_0830.long.run_holds.opp             328     41  12.5%      244     36  14.8%     -2.2    0.4350 
  I.d18_0830.short.run_holds.opp            248     21   8.5%      321     45  14.0%     -5.5    0.0403 
  I.d18_0830.both.run_holds.opp             576     62  10.8%      565     81  14.3%     -3.6    0.0684 
  I.d18_0830.long.run_holds.rest            328     41  12.5%      343     51  14.9%     -2.4    0.3730 
  I.d18_0830.short.run_holds.rest           248     21   8.5%      420     57  13.6%     -5.1    0.0472 
  I.d18_0830.both.run_holds.rest            576     62  10.8%      763    108  14.1%     -3.4    0.0650 
  I.d00_0930.long.run_holds.nobias          340    122  35.9%      109     39  35.8%     +0.1    0.9850 
  I.d00_0930.short.run_holds.nobias         263     75  28.5%      104     32  30.8%     -2.2    0.6690 
  I.d00_0930.both.run_holds.nobias          603    197  32.7%      213     71  33.3%     -0.7    0.8590 
  I.d00_0930.long.run_holds.opp             340    122  35.9%      281     88  31.3%     +4.6    0.2310 
  I.d00_0930.short.run_holds.opp            263     75  28.5%      341     94  27.6%     +0.9    0.7960 
  I.d00_0930.both.run_holds.opp             603    197  32.7%      622    182  29.3%     +3.4    0.1970 
  I.d00_0930.long.run_holds.rest            340    122  35.9%      390    127  32.6%     +3.3    0.3460 
  I.d00_0930.short.run_holds.rest           263     75  28.5%      445    126  28.3%     +0.2    0.9540 
  I.d00_0930.both.run_holds.rest            603    197  32.7%      835    253  30.3%     +2.4    0.3390 
  I.d00_0830.long.run_holds.nobias          333     43  12.9%      100     15  15.0%     -2.1    0.5910 
  I.d00_0830.short.run_holds.nobias         249     21   8.4%      105     15  14.3%     -5.8    0.0961 
  I.d00_0830.both.run_holds.nobias          582     64  11.0%      205     30  14.6%     -3.6    0.1670 
  I.d00_0830.long.run_holds.opp             333     43  12.9%      246     34  13.8%     -0.9    0.7500 
  I.d00_0830.short.run_holds.opp            249     21   8.4%      323     44  13.6%     -5.2    0.0526 
  I.d00_0830.both.run_holds.opp             582     64  11.0%      569     78  13.7%     -2.7    0.1620 
  I.d00_0830.long.run_holds.rest            333     43  12.9%      346     49  14.2%     -1.2    0.6350 
  I.d00_0830.short.run_holds.rest           249     21   8.4%      428     59  13.8%     -5.3    0.0375 
  I.d00_0830.both.run_holds.rest            582     64  11.0%      774    108  14.0%     -3.0    0.1050 

  J.d18.long.ext_order.all                  416    224  53.8%      863    467  54.1%     -0.3    0.9280    same bar 0 / 0
  J.d18.short.ext_order.all                 320    142  44.4%      863    396  45.9%     -1.5    0.6430    same bar 0 / 0
  J.d18.both.ext_order.all                  736    366  49.7%     1726    863  50.0%     -0.3    0.9020    same bar 0 / 0
  J.d00.long.ext_order.all                  416    222  53.4%      872    472  54.1%     -0.8    0.7970    same bar 0 / 0
  J.d00.short.ext_order.all                 323    138  42.7%      872    400  45.9%     -3.1    0.3310    same bar 0 / 0
  J.d00.both.ext_order.all                  739    360  48.7%     1744    872  50.0%     -1.3    0.5580    same bar 0 / 0

  K.d18.long.first.all                       44     33  75.0%      800    419  52.4%    +22.6    0.0034*   same bar 0 / 1
  K.d18.short.first.all                      43     17  39.5%      800    291  36.4%     +3.2    0.6750    same bar 0 / 1
  K.d18.both.first.all                       87     50  57.5%     1600    710  44.4%    +13.1    0.0168    same bar 0 / 2
  K.d00.long.first.all                       49     33  67.3%      800    401  50.1%    +17.2    0.0192    same bar 0 / 1
  K.d00.short.first.all                      44     20  45.5%      800    303  37.9%     +7.6    0.3140    same bar 0 / 1
  K.d00.both.first.all                       93     53  57.0%     1600    704  44.0%    +13.0    0.0143    same bar 0 / 2

  F: when the day's low / high is first printed, by 2-hour block (share of days; minutes = the block's share of the 1,380-minute day)
  block        minutes    low all   low up low down   high all  high up high down
  18:00-19:59     8.7%      16.3%    29.1%     0.5%      10.8%     1.4%     22.5%
  20:00-21:59     8.7%       7.1%    12.1%     1.0%       4.7%     1.2%      9.0%
  22:00-23:59     8.7%       1.8%     2.6%     0.8%       1.2%     0.4%      2.2%
  00:00-01:59     8.7%       1.7%     2.2%     1.0%       1.9%     0.4%      3.8%
  02:00-03:59     8.7%       5.8%     8.7%     2.2%       6.0%     2.2%     10.8%
  04:00-05:59     8.7%       3.5%     4.9%     1.8%       4.2%     1.8%      7.2%
  06:00-07:59     8.7%       2.7%     3.8%     1.2%       4.1%     2.4%      6.2%
  08:00-09:59     8.7%      12.4%    16.6%     7.0%      13.3%     9.1%     18.5%
  10:00-11:59     8.7%      17.0%    14.5%    20.0%      13.7%    12.5%     15.0%
  12:00-13:59     8.7%       9.0%     3.2%    16.2%       5.4%     7.7%      2.5%
  14:00-15:59     8.7%      15.3%     2.0%    31.8%      19.3%    33.1%      2.2%
  16:00-16:59     4.3%       7.5%     0.2%    16.5%      15.3%    27.7%      0.0%
  days: all 896, up-close 495, down-close 400
```
