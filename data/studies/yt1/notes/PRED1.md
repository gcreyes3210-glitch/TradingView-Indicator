# PRED1 - can the next few minutes be predicted from the bars? (YT11_SPEC.md, Part 2)

File (new): `tools/yt1/pred1.py`. Nothing else edited (`core.py`, `ind.py`, `run.py` untouched). In-sample only: bars to
2022-12-30; no later data exists in the lab and none was looked for.

    python3 tools/yt1/pred1.py --phase is      -> PRED1_models.joblib, PRED1_ols.json (coefficients + stamp),
                                                  is/PRED1_report.csv, is/PRED1_dropped.csv
    python3 tools/yt1/pred1.py --phase full    -> full/PRED1_report_oos.csv, full/PRED1_report_full.csv,
                                                  full/PRED1_verdict.csv / .json, full/PRED1_dropped.csv  (never fits)
    python3 tools/yt1/pred1.py --verify        -> last line PASS / FAIL
    --dry-split DATE --dry-out DIR             code test of both phases on a made-up split, outside the lab

Every figure below is IN-SAMPLE: the models were fitted on the same decisions they are scored on. For `gbr` in
particular (200 trees on 9,674 rows at h = 30, see reading 16) the in-sample fit says nothing about prediction.

## 1. Readings added beyond the spec text (all fixed before the first model was fitted)

1. **Decision clock.** "Closes of 1-minute bars every h minutes on the clock, from 10:30" is read as the *closes* being
   on the clock: the first decision is the close at 10:30:00 = the bar stamped 10:29, then every h minutes; the last
   is the bar stamped h minutes before the flat bar, so on a full day its exit is the flat bar's close (h = 1:
   10:29 ... 15:58, 330 a day; h = 5: 10:29 ... 15:54, 66; h = 15: 10:29 ... 15:44, 22; h = 30: 10:29 ... 15:29, 11).
   This is the same clock as Part 3's grid ("from the close of the 09:59 bar") and follows the common rule that a
   bar "closing by 11:00" has 10:59 as its last minute. The other reading (bars *stamped* 10:30, 10:30 + h, ...)
   would move every decision one minute later and end h = 5 / 15 / 30 at 15:50 / 15:30 / 15:00. One constant
   (`FIRST_CLOSE`) holds it.
2. **s.** Standard deviation with the mean removed and divisor 390 (the form of the spec's own VWAP sd) of the 390
   most recent returns ln(close k / close k-1) where bars k-1 and k are in the same session (09:30 bar -> flat bar of
   a row of `ctx.days`) and stamped one minute apart. So the 09:30 bar has no return, a return across a missing
   minute is not counted, and a full session gives 389 returns: the window always reaches into the previous session.
   Roll days and early-close days (to their flat bar) are part of the window; only decisions are barred on roll days.
   Missing until 390 returns exist.
3. **"w minutes earlier" / "h minutes later"** = the close of the bar stamped exactly that many minutes away, found by
   timestamp on the 24-hour series (the 60-minute return at 10:30:00 starts at the close of the 09:29 bar). If that
   minute has no bar the value is missing; nothing is carried forward.
4. **Minutes since 09:30** are counted at the decision bar's close: bar stamped 10:29 -> 60; the flat bar would be 390.
5. **Session high / low so far** = highest high / lowest low from the 09:30 bar through the decision bar.
   `hi_d` = (close - high) / (close x s x sqrt(minutes)) <= 0, `lo_d` >= 0.
6. **Volume input.** Volume of the bars stamped in the last 5 minutes (t-4 ... t) over one twelfth of the volume of
   the bars stamped in the 60 minutes before those (t-64 ... t-5); a minute without a bar adds nothing; missing if
   either sum is zero (never happened).
7. **ES inputs** are divided by s as the item says, not by s x sqrt(window) as the heading's bracket would give for
   the 5-minute one (a constant factor sqrt(5): no effect on either model's forecasts). ES close of the same minute
   via `ctx.extra("ES")`, aligned by timestamp; both ES bars and both MNQ bars must exist.
8. **Previous session's close** = the close of the previous session's flat bar (the spec's "session" ends at the flat
   bar), i.e. `C[i_end]` of the previous row of `ctx.days`; it differs from `pdc` only after an early-close day.
9. **Gap input** uses the decision bar's close in the denominator, like the other distance inputs.
10. **Days.** Roll days and days without a daily ATR are used for nothing (not fitted on, not scored): 28 of the 926
    in-sample cash days; 898 are used. Early-close days are used up to their flat bar.
11. **Dropped decisions.** A decision bar with any missing input, no s, or no bar h minutes later is dropped and
    counted (`is/PRED1_dropped.csv`, with the first thing missing). A grid minute with no bar at all is not a decision
    (counted separately).
12. **Fit sample** = every kept decision on a used day to 2022-12-30, one fit per model and horizon. Target and
    forecast are in units of s x sqrt(h).
13. **Fit statistics.** R2 against zero = 1 - sum((y - f)^2) / sum(y^2) on the scaled target; correlation = Pearson;
    sign right = share of kept decisions with forecast x outcome > 0, so an outcome of exactly zero counts as not
    right (2.9 % of 1-minute outcomes are zero). `sign_right_nonzero` in the csv leaves those out.
14. **Trades.** Side = sign of the forecast (a forecast of exactly 0 would be no trade; none occurred). Gross =
    side x (close h later - close) x $2; net = gross - $3.00. `sel`: |forecast| x s x sqrt(h) x close >= 1.5.
    Trades of one horizon never overlap (each exits at the next decision close), and each pays its own cost.
15. **Per day.** "Trades a day" and "net per day" divide by the days with at least one kept decision at that horizon
    (898 in sample for every h); the bootstrap (`core.boot_p`, 10,000 resamples, seed 1) is over the same days, a day
    without a `sel` trade counting 0. By-year figures use the decision's calendar year. The verdict's "3 of 4
    calendar years" are 2023, 2024, 2025, 2026.
16. **gbr.** The constructor is exactly the registered call, so scikit-learn's default `early_stopping="auto"`
    applies: with more than 10,000 rows it holds out 10 % and stops after 10 rounds without improvement. It stopped
    at 20 (h = 1), 50 (h = 5) and 63 (h = 15) trees; h = 30 has 9,674 rows, under the 10,000 switch, so it ran all 200
    trees with no hold-out. Not changed (that would be a hyper-parameter choice); it is why the h = 30 in-sample
    fit looks so much better than the others.
17. **OLS t-statistics.** Classical (equal-variance) t and a heteroskedasticity-robust t (HC1) are both given;
    both describe the fit sample. Targets of one horizon do not overlap.
18. **Threads.** `OMP_NUM_THREADS=1` is set by the script (shared machine; a second `--phase is` run reproduced
    the models file byte for byte, same sha256).
19. **Verdict wording.** If the data holds no out-of-sample decision at all (the lab), the verdict column says "no
    out-of-sample decisions in this data: no verdict" rather than "predicts nothing worth a trade".
20. **Harness replay** passes `r_pts = 0.1 x daily ATR` (the registry's R unit for a rule without a stop);
    `core.simulate` needs one. R is not reported.

Not expressible / not used: `core.run_orders` with its default `one_at_a_time=True` would drop every second trade
(a signal bar equal to the previous exit bar is skipped), so the replay calls it with `one_at_a_time=False`; the roll /
ATR day filter is the harness's own.

## 2. Coding errors found after first seeing results

None. Before any model was fitted (no result existed) one error was fixed: an `assert` in `decisions()` tripped inside
`--verify` because the harness's mirrored future can hold prices at or below zero (2 x reference - price); the assert
became a "target missing" drop reason, which cannot occur on real prices. The reports of the first and the last
`--phase is` run are byte-identical.

## 3. What `--verify` showed (final file, in-sample bars)

    1. 2400 trades (1089 of them sel trades; by horizon {1: 600, 5: 600, 15: 600, 30: 600}) replayed through
       core.run_orders -> core.simulate(etype='close', exit_i=the bar h minutes later): 2400 agree to the cent on
       entry, exit, bars and net P&L, 0 differ
       roll / no-ATR days: 28; decisions here on those days 0; of 28 probe orders on them run_orders kept 0
    2. 349 decisions (50 of them dropped ones), 15 inputs + s + target each, recomputed one at a time from the bar
       table: 0 values differ (largest absolute difference 2.51e-13)
    3. cut 2019-10-24 12:24: truncated bars -> 33616 input rows at or before the cut (116 on the cut day) IDENTICAL;
       mirrored future -> 37167 decision rows at or before the cut IDENTICAL (340992 later rows changed); control caught
    3. cut 2019-12-12 14:23: 44955 rows (235 on the cut day) IDENTICAL; mirrored 51860 IDENTICAL; control caught
    3. cut 2021-01-19 12:33: 136650 rows (125) IDENTICAL; mirrored 168542 IDENTICAL; control caught
    3. cut 2021-05-06 10:59: 161522 rows (31) IDENTICAL; mirrored 200348 IDENTICAL; control caught
    3. cut 2022-03-03 11:23: 231065 rows (55) IDENTICAL; mirrored 289180 IDENTICAL; control caught
    3. cut 2022-10-03 11:11: 280274 rows (43) IDENTICAL; mirrored 351665 IDENTICAL; control caught
    PASS  PRED1 --verify: trade replay to the cent, plain recomputation of the inputs, and the look-ahead test on 6
    truncated / mirrored cuts all agree

- Look-ahead, truncation: the bars are cut after a random minute of a random used session (every later bar deleted,
  ES too via `ctx.extra`), the inputs are recomputed from scratch, and every input row at or before the cut (all
  15 inputs and s, at every session bar from 10:29 on, a superset of the decision bars of all four horizons) must be
  bit-identical to the full run's. A control column that reads 5 bars ahead is caught at every cut. On truncated bars
  the harness's day table does not know the cut day yet (it needs 150 session bars) or puts its flat bar 10 minutes
  before the last bar, so the input code treats the last calendar date of the data as a session still running
  (`sessions_of`); which bars are decisions still comes from `ctx.days` only.
- Look-ahead, mirrored future (the harness's own test, `Ctx(a, scramble_after=T)`): decision rows at or before the
  cut identical, targets identical where the exit bar is at or before the cut, later rows changed.
- Outside `--verify`, once: all 756,004 `all` trades (2 models x 4 horizons) were run through `core.run_orders`:
  0 differ, and the net totals of every `all` and `sel` row equal the report. The OLS coefficients equal
  scikit-learn's `LinearRegression` to 1e-14. Three `sel` trades (2020-03-18 11:24 h5, 2020-05-14 11:29 h15,
  2022-06-14 11:29 h30) were checked by hand against printed bars: fills, net, r5, VWAP / high / low distances,
  volume ratio, ES input, gap, target, forecast move in points all as the spec says.
- `--phase full` on the lab data runs end to end (no out-of-sample decision, empty report, "no verdict"; the rebuilt
  in-sample report equals the frozen one). Its test files were removed from `data/studies/yt1/full/` so that no lab
  output sits where the real one will be written. With no saved models it exits with a message and fits nothing. A
  dry run on a made-up split (2021-07-01, written outside the lab) exercised the non-empty out-of-sample path and
  the verdict code; its numbers mean nothing and are not reported.

## 4. In-sample summary (bars 2019-06-02 -> 2022-12-30; 898 used days, first 2019-06-21)

Decisions (decision bars on used days / kept / dropped):

    h  1: 290911 / 290802 / 109   first missing: r60 45, r15 17, r30 15, r5 11, r1 9, r2 6, no bar 1 min later 4, es1 1, es5 1;  24 grid minutes had no bar
    h  5:  58182 /  58153 /  29   r60 12, r30 4, no bar 5 min later 3, r15 3, r1 3, r5 2, es1 1, es5 1;  5 grid minutes had no bar
    h 15:  19385 /  19373 /  12   r60 7, r1 1, es5 1, no bar 15 min later 1, r5 1, r30 1;  1
    h 30:   9681 /   9674 /   7   r60 5, no bar 30 min later 1, r30 1;  1

OLS coefficients, IN-SAMPLE (target and inputs in units of s; t = classical, thc = HC1):

        input     b_h1   t_h1 thc_h1     b_h5  t_h5 thc_h5    b_h15 t_h15 thc_h15    b_h30 t_h30 thc_h30
    intercept -0.00806  -0.65  -0.62 -0.02424 -0.86  -0.81 -0.03996 -0.85   -0.80 -0.04299 -0.66   -0.63
           r1 +0.04416 +13.98  +9.71 +0.02244 +2.95  +2.17 -0.01228 -0.92   -0.68 -0.04075 -2.17   -1.70
           r2 -0.02389  -7.80  -5.69 -0.01615 -2.23  -1.61 +0.01176 +0.92   +0.75 +0.01973 +1.08   +0.92
           r5 -0.01000  -3.02  -2.24 -0.02820 -3.82  -2.90 -0.04808 -3.68   -3.06 -0.05567 -2.97   -2.49
          r15 +0.00265  +0.89  +0.72 -0.00231 -0.34  -0.28 +0.04183 +3.61   +3.03 +0.04240 +2.59   +2.11
          r30 +0.00258  +0.80  +0.66 +0.00324 +0.44  +0.37 -0.01278 -1.02   -0.85 -0.00476 -0.27   -0.22
          r60 +0.00445  +1.44  +1.25 +0.00925 +1.32  +1.15 +0.00993 +0.85   +0.74 +0.00343 +0.21   +0.18
       vwap_d -0.00978  -0.75  -0.66 -0.01731 -0.59  -0.51 -0.02379 -0.48   -0.42 -0.00538 -0.08   -0.07
         hi_d +0.01019  +1.58  +1.44 +0.02218 +1.51  +1.40 +0.03441 +1.38   +1.29 +0.03570 +1.01   +0.95
         lo_d +0.00319  +0.53  +0.45 +0.00607 +0.44  +0.37 +0.01397 +0.60   +0.53 +0.00528 +0.16   +0.15
         vol5 +0.00003  +0.01  +0.00 -0.00953 -0.78  -0.64 +0.01909 +0.89   +0.80 +0.04367 +1.40   +1.31
          es1 +0.00608  +1.04  +0.83 +0.02649 +1.93  +1.59 +0.01529 +0.65   +0.52 +0.00966 +0.29   +0.23
          es5 -0.00745  -2.60  -2.08 -0.03032 -4.68  -3.86 -0.02436 -2.13   -1.83 -0.04166 -2.52   -2.16
          tod +0.04197  +1.10  +1.01 +0.11031 +1.27  +1.16 +0.20734 +1.42   +1.29 +0.29324 +1.43   +1.31
         tod2 -0.02811  -0.87  -0.79 -0.07292 -0.98  -0.90 -0.15933 -1.25   -1.14 -0.24022 -1.29   -1.20
          gap +0.00230  +1.08  +1.05 +0.00508 +1.04  +1.02 +0.00918 +1.10   +1.08 +0.01313 +1.10   +1.08
    n h1: 290802  h5: 58153  h15: 19373  h30: 9674   in-sample R2 against zero h1: +0.00103  h5: +0.00100  h15: +0.00258  h30: +0.00465

gbr: 20 trees (h 1), 50 (h 5), 63 (h 15), all stopped early on the 10 % hold-out; 200 trees (h 30), no hold-out.

Report, IN-SAMPLE (`is/PRED1_report.csv`; trades a day and net per day are per day with a decision; p = one-sided
bootstrap of the daily net; gross and net in $ per trade):

    model  h version  n_decisions  days  r2_zero    corr sign_right  trades trades_per_day   win gross_per_trade net_per_trade net_per_day net_total p_boot_day net_2019 net_2020 net_2021 net_2022
      ols  1     all       290802   898 +0.00103 +0.0321     0.4927  290802         323.83 0.340          +0.284        -2.716     -879.49   -789786     1.0000  -126840  -206775  -234786  -221386
      ols  1     sel       290802   898 +0.00103 +0.0321     0.4927     155           0.17 0.535          +7.690        +4.690       +0.81      +727     0.1320      +26     +454      +58     +190
      ols  5     all        58153   898 +0.00100 +0.0316     0.5011   58153          64.76 0.429          +0.671        -2.329     -150.81   -135424     1.0000   -23449   -37731   -49060   -25185
      ols  5     sel        58153   898 +0.00100 +0.0316     0.5011     822           0.92 0.495          +3.044        +0.044       +0.04       +36     0.4950      -43     -586      -25     +690
      ols 15     all        19373   898 +0.00258 +0.0507     0.5081   19373          21.57 0.466          +1.497        -1.503      -32.43    -29125     1.0000    -8807    -9140   -12850    +1671
      ols 15     sel        19373   898 +0.00258 +0.0507     0.5081    3537           3.94 0.513          +6.728        +3.728      +14.68    +13184     0.0013     -235    +1630    +2588    +9200
      ols 30     all         9674   898 +0.00465 +0.0681     0.5168    9674          10.77 0.486          +3.766        +0.766       +8.25     +7410     0.1351    -3808    +3864    -4166   +11520
      ols 30     sel         9674   898 +0.00465 +0.0681     0.5168    3877           4.32 0.509          +6.977        +3.977      +17.17    +15420     0.0012     -546    +2702    +2996   +10269
      gbr  1     all       290802   898 +0.00138 +0.0468     0.4931  290802         323.83 0.340          +0.311        -2.689     -870.75   -781934     1.0000  -125106  -210609  -228168  -218050
      gbr  1     sel       290802   898 +0.00138 +0.0468     0.4931      39           0.04 0.487          +8.872        +5.872       +0.26      +229     0.2587       +0     +264      -77      +42
      gbr  5     all        58153   898 +0.00594 +0.1076     0.5151   58153          64.76 0.442          +1.751        -1.249      -80.88    -72628     1.0000   -21125   -15137   -26828    -9539
      gbr  5     sel        58153   898 +0.00594 +0.1076     0.5151    1079           1.20 0.551         +12.273        +9.273      +11.14    +10006     0.0000     +136    +2138    +2360    +5372
      gbr 15     all        19373   898 +0.01296 +0.1441     0.5332   19373          21.57 0.490          +4.060        +1.060      +22.88    +20545     0.0027    -3762    +4698    +1202   +18406
      gbr 15     sel        19373   898 +0.01296 +0.1441     0.5332    3508           3.91 0.564         +14.403       +11.403      +44.55    +40002     0.0000     +771    +5554   +12822   +20855
      gbr 30     all         9674   898 +0.04752 +0.2798     0.5768    9674          10.77 0.543         +12.766        +9.766     +105.21    +94477     0.0000    +2521   +26791   +24730   +40434
      gbr 30     sel         9674   898 +0.04752 +0.2798     0.5768    5203           5.79 0.589         +20.238       +17.238      +99.88    +89690     0.0000    +3776   +24991   +22566   +38356

`sign_right_nonzero` (zero outcomes left out): ols 0.5073 / 0.5076 / 0.5112 / 0.5201, gbr 0.5077 / 0.5217 / 0.5365 /
0.5805 for h = 1 / 5 / 15 / 30.

Frozen: `PRED1_models.joblib` sha256 `cc1424b4ac12beaa75ff108e08e6135fd3f8fce8325324a2640b270feac6d471`, stamped
2026-10-10 04:31:47 UTC in `PRED1_ols.json` (scikit-learn 1.9.1, numpy 2.5.3, pandas 3.0.5, joblib 1.6.0, Python 3.13).
`--phase full` refuses a models file whose sha256 is not the stamped one, and warns if scikit-learn differs.
