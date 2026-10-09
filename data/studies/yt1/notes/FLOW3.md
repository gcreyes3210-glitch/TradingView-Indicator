# FLOW3 - footprint and order flow at the hourly add (YT7_SPEC.md, Part 2)

File (new): `tools/yt1/flow3.py`. Nothing else edited (`core.py`, `ind.py`, `run.py`, `tt.py`, `cal_orb.py`, the `g9_*`
files, `s_G9.py`, `YT7_SPEC.md`, `flow1.py`, `flow2.py` untouched; `s_G10.py` / `notes/G10.md` not opened).
In-sample only: bars and order flow to 2022-12-30; no later data exists in the lab and none was looked for.

    python3 tools/yt1/flow3.py --phase is      -> is/FLOW3_trades.csv, is/FLOW3_table.csv, FLOW3_selected.json
    python3 tools/yt1/flow3.py --phase full    -> full/FLOW3_table.csv, full/FLOW3_oos.json, full/FLOW3_trades.csv
    python3 tools/yt1/flow3.py --check         the causality check below
    --dry-split DATE --dry-out DIR [--dry-min-side N]    code test of both phases on a made-up split, outside the lab

Trades come from running the modules on the phase's bars: `s_G9.trades(ctx, **s_G9.VARIANTS["base"])` (YT6 pick 1,
`T1.Wopen.Bnone.Enone.Mnone.Rsess_brk.Hnone.Snone.X2R.Npos`; the signal bar is the last field of each trade's tag), the
signal's row from `g9_grid.pick(g9_signals.build(ctx, tfs=(1,)), combo)` (protected level `prot`, first bar of the
CISD's run `a_run0`, the 18:00-08:29 session high / low `a_sessx`), and ORB v1.4 from
`core.run_orders(ctx, cal_orb.orders(ctx), skip_roll=False)`. No csv of another run is read.

## 1. Readings (R) - all fixed before the first in-sample table was printed

1. **(R) aligned.** An ORB trade "entered earlier that day and still open at the entry" = its fill bar is before the
   add's entry bar and its exit bar is at or after the entry bar, same side. ORB fills at a bar's close, so an ORB
   filled at the close of the 09:59 / 10:59 bar (the 5-minute close at 10:00:00 / 11:00:00) counts as entered before
   the hour's open. 13 of the 83 aligned in-sample trades are that case (column `orb_edge`); with the other reading
   there would be 70. The set as coded has 83 trades, 46 wins (55.4 %), net +5,116 $ = the figures in the spec's
   disclosure for 2019-2022.
2. **(R) decision bar** = the order's bar, the last 1-minute bar before the entry bar (09:59 on 143 trades, 10:59 on 64;
   never anything else). Decision time = its end. A 1-minute flow row is used when stamp + 1 min <= decision time, a
   5-minute footprint bar when stamp + 5 min <= decision time, a 30-second bar when stamp + 30 s <= decision time.
3. **(R) has_flow** = the day has NQ_flow_1m rows from 09:30 on, and every minute 09:30 -> decision has a row in
   NQ_flow_1m and in ES_flow_1m, every completed 5-minute bar of that span is in NQ_footprint_5m, and an NQ 30-second
   bar ends in the span. One pick 1 trade on a flow day fails it (2020-03-09, the circuit-breaker halt: NQ minutes
   76/90); it is not aligned.
4. **(R) delta and volume** are the tables' `delta` (buy - sell, unclassified volume not in it) and `volume` (buy +
   sell + unclassified; unclassified is 0.003 % of NQ volume) columns summed over the rows; `cum_delta` / `cum_volume`
   are not used because 19 in-sample flow days carry a stray 09:29 row (and a 09:25 footprint bar) that those columns
   include. Nothing stamped before 09:30 is used by any measure.
5. **(R) last15** = the 15 one-minute rows ending with the decision minute (09:45-09:59 or 10:45-10:59).
6. **(R) pull** is signed in the trade's direction like the other deltas; rows from max(run start, 09:30) through
   the signal bar. The run starts before 09:30 on 12 of the 125 trades with flow (5 of the 83 aligned).
7. **(R) vol_rel**: the average 15-minute volume = volume 09:30 -> decision / (minutes / 15) (2 or 6 blocks).
8. **(R) poc**: footprint volume at a price = buy + sell summed over the completed bars; ties -> the lowest price (the
   house rule in `tools/ivc_engine.py`; no tie occurred in sample); session range = highest - lowest footprint price;
   **decision close = the close of the last NQ 30-second bar that ends at or before the decision time** (stamped
   hh:59:30), an NQ price against an NQ point of control. With the MNQ close of the decision bar instead, `poc` would
   change by at most 0.055 and 2 of the 83 aligned trades would sit on the other side of the frozen threshold (NQ and
   MNQ last prices of the decision minute differ by 0 or 1 tick on 85 of the 125 trades and by up to 3.75 points).
9. **(R) stack** follows the house function `flow2.stack()` exactly: tick grid from the bar's lowest to its highest
   traded price with 0 / 0 at an untraded tick, so the lowest price cannot hold a buy imbalance and the highest
   cannot hold a sell imbalance (the spec sentence alone would allow them). Per side the largest run over the three
   bars; value = own side - other side. Checked against `flow2.stack` on all 375 bars: 0 differences; allowing the
   edge prices would change the value of 0 of 125 trades.
10. **(R) brk_delta / brk_share**: "beyond" is strict (price > overnight high for a long, price < overnight low for
    a short); `brk_delta` is signed in the trade's direction; `brk_share` is 0 (not missing) when nothing traded there.
    `brk_delta` was never missing in sample.
11. **(R) thresholds and ranking**: median = `numpy.median` of the non-missing values; a missing value is on neither
    side; ties in the ranking keep the spec table's order; equal win rates -> `high` (neither occurred).
12. **(R) permutation p** (full phase) = share of 20,000 shuffles of the side labels with a difference at least the
    observed one (house convention, `flow1.py`), a fresh `default_rng(1)` for each test.
13. **(R) combined** = trades on the favourable side of both picks against every other trade of the set (a trade
    missing one of the two measures is in "the rest").
14. **(R) periods**: in sample = entry day before 2023-01-01; out of sample = entry day from 2023-01-01 with flow.

### NQ / ES prices against MNQ trades
The trade, its signal bar, run start and the broken overnight level (18:00-08:29 high / low) come from the MNQ
continuous bars; times are matched by New York timestamp (flow index is tz-aware New York; DST handled by timestamps,
never by index arithmetic). The MNQ level is applied as it is to NQ footprint prices. Measured basis (NQ 1-minute close
from the 30-second bars minus MNQ 1-minute close, all 52,365 flow minutes): median |difference| 1 tick, 90 % within
2 ticks, but 4 to 8.5 points on six days (2020-12-14/15, 2021-06-14/15, 2021-09-13/14) - each is an MNQ roll day or the
day after, which pick 1 does not trade, so none carries a trade. Column `basis` in the trades file = the median
difference 09:30 -> decision for each trade: at most 1 tick in sample (0 on 110 of 125). Does one tick matter for
`brk_*`? Moving the level one tick either way changes `brk_delta` by a median 0.0003 (max 0.011) and `brk_share` by a
median 0.0015 (max 0.033); 1 to 3 aligned trades would cross the frozen `brk_delta` threshold, 0 to 2 the `brk_share`
one. A basis of points would matter; the `basis` column is there so the full phase can see it.

## 2. Coding errors found after first seeing results
None. Before the in-sample table was printed for the first time the eleven measures of all 125 trades were recomputed by
a second script (plain pandas filters on the raw tables, `flow2.stack` for the runs): 0 mismatches, largest difference
0.0 on every measure; `aligned` recomputed from entry / exit stamps: equal on all 207; the overnight level recomputed
from the bars: equal on all 207. No code or reading was changed after the table was printed.

## 3. Counts (in sample)
| | n |
|---|---|
| YT6 pick 1 trades | 207 |
| on order-flow days | 126 |
| with flow (covered 09:30 -> decision) | 125 |
| aligned (G10 base) | 83, all on flow days, all with flow (48 long, 35 short; decision 09:59 on 67, 10:59 on 16) |
| not aligned, with flow | 42 (ORB filled at or after the hour 40, ORB already closed 2, ORB open on the other side 0) |
| no ORB trade that day | 82 (one of them on a flow day: 2020-03-09) |
| aligned by year | 2019: 11, 2020: 15, 2021: 20, 2022: 37 |
| missing per measure, aligned | `since` 3 (signal bar = decision bar); every other measure 0 |
| missing per measure, all with flow | `since` 4; every other measure 0 |

Flow days 419; harness ORB days 410, all of them flow days. The 9 flow days without a harness ORB trade are 7 days
from 2019-06-03 to 06-18 (before the daily ATR exists, so the harness drops the order) and the two halt days
2020-03-09 / 03-12 (a 5-minute bar of the opening range is missing).

## 4. Worked examples (raw table rows, arithmetic by a separate script; "module" = flow3's value)

**Trade A, 2019-07-22 long.** MNQ bars: 09:43 O 7900.50 C 7898.00, 09:44 C 7896.75, 09:45 C 7895.25 (the down-close run,
first bar 09:43), 09:46 C 7897.50, 09:47 C 7901.25 > 7900.50 = the CISD (signal bar 09:47); protected low 7894.00 (low
of 09:46) > overnight high 7888.50 (18:00-08:29, made 08:20); stop 7893.75; lowest low 09:48-09:59 = 7899.00, so not
cancelled; entry at the 10:00 open 7914.50 + 1 tick = 7914.75; decision bar 09:59. ORB long filled at the close of
09:54, flat 16:04: open at 10:00, same side -> aligned.

           nq_delta  nq_volume  es_delta  es_volume last15 pull since
    09:30      -194       4054       953      10647
    09:31       202       2344      -279       5099
    09:32      -110       2666       211       6551
    09:33        64       1946       282       7818
    09:34      -123       1729      -559       6807
    09:35       -32       1972      -462       7796
    09:36      -138       2406       330       8210
    09:37         3       1767      -480       6416
    09:38      -169       1885      -199       8817
    09:39       166       1764       -68       4568
    09:40       212       2368       200       6254
    09:41       268       2276       744       4282
    09:42      -100       2122       265       5265
    09:43      -216       1118      -572       2634           x
    09:44       -34       1046       111       2291           x
    09:45      -180       1288      -421       2901      x    x
    09:46      -245       2015      -378       3624      x    x
    09:47       178       1920       216       3868      x    x
    09:48       198       1682       315       3643      x          x
    09:49       -80        900        30       4396      x          x
    09:50       192       1742       -47       3317      x          x
    09:51      -116       1090      -633       2037      x          x
    09:52      -290       1124      -497       2149      x          x
    09:53       -78        938       364       2200      x          x
    09:54       570       2128      1424       3646      x          x
    09:55       112       1828       -61       5007      x          x
    09:56        46       1650      -426       2468      x          x
    09:57      -165       1521      -394       3092      x          x
    09:58      -101       1093        83       2109      x          x
    09:59       117        979       119       3159      x          x

    cum     = +1 x -43 / 53361               = -0.000806   module -0.000806   (30 rows 09:30-09:59)
    last15  = +1 x 158 / 21898               = +0.007215   module +0.007215   (15 rows 09:45-09:59)
    pull    = +1 x -497 / 7387               = -0.067280   module -0.067280   (rows 09:43-09:47)
    since   = +1 x 405 / 16675               = +0.024288   module +0.024288   (rows 09:48-09:59)
    es_cum  = +1 x 171 / 141071              = +0.001212   module +0.001212
    div     = -0.000806 - (+0.001212)        = -0.002018   module -0.002018
    vol_rel = 21898 / (53361 / 2 = 26680.5)  =  0.820749   module  0.820749

    NQ footprint, completed 5-minute bars 09:30 -> decision (brk = rows priced above 7888.50):
            buy  sell    vol      low     high  brk_buy  brk_sell
    09:30  6289  6450  12739  7875.25  7889.75      214       160
    09:35  4812  4982   9794  7878.00  7891.00      612       320
    09:40  4530  4400   8930  7888.00  7900.75     4501      4351
    09:45  3838  3967   7805  7894.25  7904.75     3838      3967
    09:50  3650  3372   7022  7903.50  7913.00     3650      3372
    09:55  3540  3531   7071  7910.25  7916.25     3540      3531
    total 26659 26702  53361  7875.25  7916.25    16355     15701
    volume at price, top 4: 7885.00: 939, 7897.00: 831, 7885.50: 793, 7884.50: 791
    last NQ 30-second bar ending by 10:00: stamped 09:59:30, close 7914.25 (MNQ close of the 09:59 bar: 7914.25)

    poc       = (7914.25 - 7885.00) x +1 / (7916.25 - 7875.25 = 41.00) = +0.713415   module +0.713415
    brk_delta = +1 x (16355 - 15701) / (16355 + 15701)               = +0.020402   module +0.020402
    brk_share = (16355 + 15701) / 53361                              =  0.600738   module  0.600738

    stack: bar 09:45 longest buy run 0, sell run 2 | bar 09:50 buy 2, sell 0 | bar 09:55 buy 0, sell 0
    stack     = (2 - 2) x +1 = 0   module 0
    the buy run of 2, bar 09:50, prices 7912.00-7912.25 (buy at p against sell one tick below):
        7912.75  buy  27  sell   3   27 >= 3 x max(8, 1)  = 24     imbalance (a separate run of 1)
        7912.50  buy  52  sell   8   52 <  3 x max(19, 1) = 57
        7912.25  buy  25  sell  19   25 >= 3 x max(4, 1)  = 12     imbalance
        7912.00  buy 106  sell   4   106 >= 3 x max(28, 1) = 84    imbalance
        7911.75  buy  79  sell  28   79 <  3 x max(36, 1) = 108
    the sell run of 2, bar 09:45, prices 7894.75-7895.00 (sell at p against buy one tick above):
        7895.25  buy  48  sell  51   51 <  3 x max(26, 1) = 78
        7895.00  buy   7  sell 288   288 >= 3 x max(48, 1) = 144   imbalance
        7894.75  buy  25  sell  65   65 >= 3 x max(7, 1)  = 21     imbalance
        7894.50  buy  23  sell  28   28 <  3 x max(25, 1) = 75

**Trade B, 2019-07-25 short** (signs, the 09:30 bound, a level the whole session is beyond). Run starts 09:29, signal
bar 09:30, decision bar 09:59, overnight low 8003.50, ORB short 09:54 -> 16:04, aligned.

    cum     = -1 x -568 / 73334      = +0.007745   module +0.007745
    last15  = -1 x 1095 / 34699      = -0.031557   module -0.031557
    pull    = -1 x -347 / 3631       = +0.095566   module +0.095566   (the 09:30 row only: the run began 09:29, not used)
    since   = -1 x -221 / 69703      = +0.003171   module +0.003171   (rows 09:31-09:59)
    es_cum  = -1 x -5606 / 190870    = +0.029371   module +0.029371
    div     = +0.007745 - 0.029371   = -0.021625   module -0.021625
    vol_rel = 34699 / (73334 / 2)    =  0.946328   module  0.946328
    footprint 09:30-09:59: buy 36383, sell 36951, low 7945.25, high 7999.00; all of it below 8003.50
    volume at price, top: 7957.75: 1270; NQ close 09:59:30 bar 7962.75 (MNQ close of the 09:59 bar 7963.00)
    poc       = (7962.75 - 7957.75) x -1 / (7999.00 - 7945.25 = 53.75) = -0.093023   module -0.093023
    brk_delta = -1 x (36383 - 36951) / (36383 + 36951)               = +0.007745   module +0.007745
    brk_share = 73334 / 73334                                        =  1.000000   module  1.000000
    stack: bar 09:45 buy 0 / sell 2, bar 09:50 buy 0 / sell 2, bar 09:55 buy 5 / sell 0
    stack     = (5 - 2) x -1 = -3   module -3
    the buy run of 5, bar 09:55, prices 7955.50-7956.50:
        7956.75  buy 18  sell 37   18 <  3 x max(12, 1) = 36
        7956.50  buy 21  sell 12   21 >= 3 x max(1, 1)  = 3     imbalance
        7956.25  buy 26  sell  1   26 >= 3 x max(0, 1)  = 3     imbalance (floor 1 contract)
        7956.00  buy 55  sell  0   55 >= 3 x max(12, 1) = 36    imbalance
        7955.75  buy 47  sell 12   47 >= 3 x max(4, 1)  = 12    imbalance
        7955.50  buy 47  sell  4   47 >= 3 x max(12, 1) = 36    imbalance
        7955.25  buy 77  sell 12   77 <  3 x max(65, 1) = 195

When the whole session is beyond the level (`brk_share` = 1: 11 aligned trades, 22 of all with flow) `brk_delta` is
`cum` computed on the footprint (equal to it when no volume is unclassified, as here).

**Trade C, 2020-01-15 long** (no `since`). Signal bar 09:59 = decision bar: `since` missing (module NaN). The other ten
are computed (cum +0.020532, pull +0.040373 over 09:55-09:59, poc +0.253521, brk_delta +0.076950, brk_share 0.370825,
stack (2 - 1) x +1 = +1; all equal to the module). Its ORB trade filled at the close of 09:59 (reading 1).

## 5. Causality check (`python3 tools/yt1/flow3.py --check`)

    1. 125 trades with flow, 11 measures each, recomputed with every row ending after the trade's decision time deleted: IDENTICAL
       2019-07-10 L decision 09:59  context ends 2019-07-10 09:59  flow rows end 09:59  signal, level and 11 measures: identical
       2019-07-25 S decision 09:59  context ends 2019-07-25 09:59  flow rows end 09:59  signal, level and 11 measures: identical
       2019-09-11 L decision 10:59  context ends 2019-09-11 10:59  flow rows end 10:59  signal, level and 11 measures: identical
       ... (20 sampled trades, seed 5: 2019-09-19, 2019-12-26, 2020-01-31, 2020-08-19, 2021-02-22, 2021-04-01, 2021-05-06,
            2021-06-03, 2021-09-16, 2021-11-01, 2021-11-22, 2022-04-14, 2022-05-04, 2022-09-13, 2022-10-26, 2022-12-22,
            2022-12-29: all identical)
    2. 20 sampled trades rebuilt from bars and flow ending at the decision time: 20 identical, 0 different
    FLOW3 causality check: PASS

Part 1 deletes, per trade, every 1-minute flow row, footprint bar and 30-second bar that ends after its decision time
and measures on what is left. Part 2 builds a context from the MNQ bars of the 30 days up to and including the decision
bar (no later price bar exists in it; `Ctx.flow` then cuts every flow table at that bar's end as well), rebuilds the
signal there (same bar, side, stop, run start, overnight level required) and measures there. Negative control: a
version reading one row too many is caught by part 1 (one extra minute: `cum, last15, since, es_cum, div, vol_rel`
change on 125 / 125 trades; one extra footprint bar: `poc` 87, `brk_delta` 125, `brk_share` 104; one extra 30-second
bar: `poc` 124). `stack` and `pull` read rows chosen by exact stamp at or before the decision, so those leaks cannot
reach them. The trade's own fields (signal bar, run, level) come from `s_G9`, whose look-ahead tests are in notes/G9.md.

Other checks: the trades csv rebuilt in a fresh process has the stamped sha256; the full phase was dry-run on a
made-up split (2021-07-01, minimum 10 a side so that picks exist) written to a scratch directory and deleted: the
frozen-file stamp, "in-sample rows rebuilt = frozen file" and "in-sample table = frozen table" checks all came out
True, a deliberately altered frozen row was reported as NOT REPRODUCED, and nothing in `data/studies/yt1` was written
by it. The dry run's numbers were discarded and nothing was changed after it. `--phase full` run here stops with "no
out-of-sample bars in this data". The full phase computes no threshold and no pick: it reads them from the json.

## 6. In-sample output (`python3 tools/yt1/flow3.py --phase is`)

    FLOW3   phase is   bars 2019-06-02 18:00:00-04:00 -> 2022-12-30 16:59:00-05:00   in-sample = trades before 2023-01-01

    PRIMARY: aligned YT6 pick 1 trades with flow (G10 base trades on order-flow days): 83 trades, 46 wins, mean R +0.433, net +5116   (threshold = in-sample median; hi = at or above it; diff = win_hi - win_lo; eligible = at least 25 a side)
      measure threshold  n  missing  n_hi  wins_hi win_hi   R_hi net_hi  n_lo  wins_lo win_lo   R_lo net_lo   diff  eligible better  rank
          cum   +0.0183 83        0    42       24  0.571 +0.479  +2493    41       22  0.537 +0.386  +2624 +0.035      True   high     8
       last15   +0.0127 83        0    42       25  0.595 +0.490  +3038    41       21  0.512 +0.374  +2079 +0.083      True   high     6
         pull   +0.0237 83        0    42       23  0.548 +0.297  +1666    41       23  0.561 +0.572  +3450 -0.013      True    low    11
        since   +0.0135 80        3    40       25  0.625 +0.542  +3006    40       20  0.500 +0.366  +2078 +0.125      True   high     5
       es_cum   +0.0222 83        0    42       20  0.476 +0.279  +2021    41       26  0.634 +0.590  +3096 -0.158      True    low     3
          div   -0.0033 83        0    42       27  0.643 +0.645  +3134    41       19  0.463 +0.216  +1982 +0.179      True   high     2
      vol_rel   +0.8209 83        0    42       22  0.524 +0.310  +3242    41       24  0.585 +0.558  +1875 -0.062      True    low     7
          poc   +0.2674 83        0    42       26  0.619 +0.569  +3128    41       20  0.488 +0.293  +1989 +0.131      True   high     4
        stack   +2.0000 83        0    44       25  0.568 +0.433  +3078    39       21  0.538 +0.433  +2038 +0.030      True   high    10
    brk_delta   +0.0217 83        0    42       29  0.690 +0.788  +3188    41       17  0.415 +0.069  +1929 +0.276      True   high     1
    brk_share   +0.6948 83        0    42       24  0.571 +0.370  +3112    41       22  0.537 +0.497  +2004 +0.035      True   high     9

    picks (the two eligible measures with the largest absolute difference in win rate):
      pick 1: brk_delta  favourable side = high (>= +0.021688)   in sample: favourable n 42 win 0.690 R +0.788 | unfavourable n 41 win 0.415 R +0.069
      pick 2: div  favourable side = high (>= -0.003328)   in sample: favourable n 42 win 0.643 R +0.645 | unfavourable n 41 win 0.463 R +0.216
      both picks' favourable sides, in sample (description): n 29 win 0.793 R +1.051 net +2807 | the rest: n 54 win 0.426 R +0.101 net +2310

    SECONDARY (reported, no picks, no verdict): all YT6 pick 1 trades with flow, aligned or not; thresholds = in-sample medians of this wider set: 125 trades, 71 wins, mean R +0.481, net +8261
      measure threshold   n  missing  n_hi  wins_hi win_hi   R_hi net_hi  n_lo  wins_lo win_lo   R_lo net_lo   diff  eligible better  rank
          cum   +0.0150 125        0    63       36  0.571 +0.526  +4206    62       35  0.565 +0.434  +4054 +0.007      True   high     9
       last15   +0.0119 125        0    63       36  0.571 +0.477  +4044    62       35  0.565 +0.484  +4216 +0.007      True   high    10
         pull   +0.0238 125        0    63       32  0.508 +0.243  +2970    62       39  0.629 +0.722  +5292 -0.121      True    low     4
        since   +0.0093 121        4    61       38  0.623 +0.584  +4140    60       32  0.533 +0.432  +4122 +0.090      True   high     5
       es_cum   +0.0209 125        0    63       36  0.571 +0.534  +4637    62       35  0.565 +0.426  +3624 +0.007      True   high    11
          div   -0.0036 125        0    63       38  0.603 +0.566  +4252    62       33  0.532 +0.393  +4009 +0.071      True   high     6
      vol_rel   +0.8025 125        0    63       31  0.492 +0.252  +3690    62       40  0.645 +0.713  +4570 -0.153      True    low     2
          poc   +0.1863 125        0    63       37  0.587 +0.506  +4923    62       34  0.548 +0.454  +3338 +0.039      True   high     7
        stack   +1.0000 125        0    80       45  0.562 +0.450  +4426    45       26  0.578 +0.535  +3836 -0.015      True    low     8
    brk_delta   +0.0197 125        0    63       40  0.635 +0.681  +4461    62       31  0.500 +0.277  +3800 +0.135      True   high     3
    brk_share   +0.7498 125        0    63       41  0.651 +0.644  +6299    62       30  0.484 +0.315  +1962 +0.167      True   high     1

    sha256 of the trades csv: fb9a5e59e36e43b75b626aae29709044d0a444d3365dbefc9e86ed20ea3298de

No measure was set aside (every side has at least 39 trades). Frozen in `data/studies/yt1/FLOW3_selected.json`:
thresholds of all eleven measures for both blocks (full precision), the better in-sample side of each, the two picks
(`brk_delta` high, `div` high), counts, the rule text, sha256 of `is/FLOW3_trades.csv` and `is/FLOW3_table.csv`,
stamped 2026-10-09 18:57:46 UTC. The secondary block is labelled as such and carries no picks.

## 7. Odd things
- `stack` is an integer (-9 ... +16 among the aligned): 7 aligned trades sit exactly on its median 2, so its sides are
  44 / 39, and the wider set's median 1 gives 80 / 45.
- `brk_delta` and `cum` are the same number on the trades whose whole session is beyond the level (11 of 83 aligned).
- 19 in-sample flow days have a 09:29 row / 09:25 footprint bar / 09:29:30 bar with a few contracts; excluded.
- The lab's order flow ends with its bars (2022-12-30), so "a trade after the last flow day has no flow" could not be
  exercised as such; a day absent from the flow tables is handled the same way wherever it lies (81 in-sample pick 1
  trades are on such days: `on_flow_day` False, `has_flow` False, measures empty).
