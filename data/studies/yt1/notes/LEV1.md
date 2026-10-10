# LEV1 - which levels react: first tap after the open (YT9_SPEC.md)

Files (all new): `tools/yt1/lev1_levels.py` (levels, unit checks, level look-ahead test), `tools/yt1/lev1_events.py`
(events, order builder, scoring through `core.simulate`), `tools/yt1/lev1_tables.py` (tables, selection, the later
out-of-sample scoring), `tools/yt1/s_L1.py` (standard harness module, look-ahead tests, reconciliation),
`tools/yt1/lev1_verify.py` (the hand checks and counts quoted here). `core.py`, `ind.py`, `run.py`, `tt.py`, every
existing module, `Aceflw_Levels.pine` and the specs were not edited. In-sample only (bars to 2022-12-30); no later
bar exists in the lab and none was looked for.

Outputs: `data/studies/yt1/is/LEV1_levels.parquet` (85,117 rows), `is/LEV1_events.parquet` (57,653 rows),
`is/LEV1_reaction.csv`, `LEV1_draw.csv`, `LEV1_pairs.csv`, `LEV1_bytime.csv`, `LEV1_used.csv`,
`data/studies/yt1/LEV1_selected.json` (picks, thresholds, counts, sha256 of the events file and of the five tables),
`is/L1_<variant>.csv|json` from the standard runner. Nothing was written to `data/studies/yt1/full/`.

## 1. Readings (R) - all fixed before any table was built

1. **Price at the start of a watch** = the OPEN of the first watched 1-minute bar (09:30 for most levels, 09:45 for
   the opening range, the block's first bar for an expected-move block starting at 10:00 / 12:00 / 14:00). It sets
   the side, the 0.04 x ATR near-skip and the cluster. The order rests from that bar (`i` = the bar before it), so
   the order reads one number after its bar `i`: the open of bar `i + 1`. For `r100` and for the centre of a late
   expected-move block that open is the level's registered definition; for the other levels it is this reading.
   The other reading (last close before the bar) would differ on 139 of 43,672 level-days in the side (49 of them
   watched under either reading) and on 156 in the near-skip (open and previous close differ by a median of 0.25
   points). How the look-ahead test deals with it: section 8.
2. **Watch end**: the bar stamped 15:00 inclusive (the spec's buckets are bar stamps: 09:30-09:59, 10:00-11:29,
   11:30-15:00); on a short day the flat bar (12:49 or 13:04; 29 of the 884 study days). Expected-move bands: to the
   block's last bar (09:59, 11:59, 13:59) or 15:00.
3. **"Within" x ATR** means <= (near-skip 0.04, cluster 0.03, placebo drop 0.03).
4. **`used`** = between the time the level was set and the 09:29 bar price traded strictly on both sides of it (the
   price at the set time counts as the starting side): an Asia high is used when a later bar trades above it; an
   equal high does not use it. Levels set at 09:29 (overnight, pre-market, profile) or later are never used.
5. **Clusters** are formed when a watch starts, among the watched real static levels whose watch starts on that
   bar: same side, chained while neighbouring levels are within 0.03 x ATR (single linkage); levels skipped as too
   near are left out first. So the 09:30 levels (everything fixed before 09:30, plus `r100`) cluster with each
   other; **the opening-range levels join no cluster** (their watch starts at 09:45; merging them into clusters
   formed at 09:30 would change events already under way). Of the 1,411 opening-range events 797 have a watched
   09:30 level within 0.03 x ATR on the same side, 588 of them still untapped at 09:45: those are separate events.
6. **The tapped level of a cluster** = the level nearest the start price. Levels tied at that price (the overnight
   high made in Asia is both `onh` and `ash`) are all "the one tapped": the event counts in the cell of each tied
   level (1,088 clusters have more than one lead; 1,126 extra lead rows). Consequences: a fresh `ash` resistance
   event is always also an `onh` event (74 of 74); `onh:R` and `ldh:R` share 94 trades (of 260 and 159). Tables of
   clusters (pairs, by count, pooled) count each cluster once.
7. **Placebos.** Value = parent +/- 0.12 x ATR. Side and near-skip from the placebo's own price. `used` by the same
   rule as its parent, from the parent's set time. Dropped if within 0.03 x ATR of a real static level that exists
   when the placebo's own watch starts: a 09:30 placebo is checked against every real static level except the
   opening range (unknown at 09:30); an opening-range placebo against all. 1,248 of the 17,996 kept placebos lie
   within 0.03 x ATR of an opening-range level (column `near_later`). A placebo is its own event and never in a
   cluster; "the placebo's numbers for the same code x side" = placebos of that parent code whose own side it is.
8. **Order prices.** The limit / stop price is the level on the tick grid, rounded towards where price comes from
   (resistance up, support down): the first tick at which "high >= level" / "low <= level" is true (only `pdm`,
   placebos, expected-move and VWAP bands are off the grid). Stop = price +/- d, target = price -/+ k x d (YT1 common
   rule: from the entry price before slippage); a fill at a better open keeps both. d: 20 points; 0.04 / 0.08 x ATR
   to the nearest tick, at least 2 ticks. Win = the target was reached (exit reason TP); a time exit in profit is
   not a win.
9. **Expected move.** sd = population sd of the log returns of the 2,760 five-minute bars BEFORE the block's first
   bar (the spec's "previous 2,760 five-minute bars"). The script, run at bar close, would include the block's
   first bar itself, whose close is unknown when the block starts; the two differ by a median of 0.02 % of sigma
   (max 6.4 %). Returns run across session gaps, as on a chart. A block's first bar = the first 1-minute bar at or
   after its start; 29 short days have three blocks.
10. **VWAP levels (moving).** Value in force during bar k = the script's value at the close of the last 5-minute
    bar that is complete by the clock when bar k opens. The side is fixed from the value in force during the 09:30
    bar. Order: at the close of every bar k - 1 (k = 09:30 bar .. 15:00 bar) a one-bar order (`i = k - 1`,
    `expire = k`) at that value on the tick grid, with its stop and target from that price; the first one to fill is
    the event, and no order is placed after it. The VWAP resets on the script's `fullStart` (one session of 927 does
    not start on an 18:00 bar: 2020-06-30 20:00).
11. **Profile** is built per trading date from the 1-minute bars of 18:00-09:29. One cash day (2021-04-05) follows
    an overnight session with no bar between (Good Friday trading stopped at 09:14): the script would keep adding
    to the old profile there; here the profile, like `onh` / `onl`, is that night's only.
12. **Opens**: the bar stamped exactly 18:00 / 00:00 / 08:30; no such bar, no level (1, 4 and 2 study days).
13. **Previous week** = the bars whose trading date lies in the previous Monday-Friday week (Sunday 18:00 is
    Monday's trading date), so a Monday holiday neither starts a week nor ends one. Around a contract roll the
    previous week's bars are the earlier contract's (or both contracts'); they are taken as they are (roll days
    and the day after are not study days, the later days of that week are).
14. **30-minute numbers**: bars from the tap bar to the bar stamped 30 minutes later; through = farthest high (low)
    beyond the level; away = farthest low (high) on the other side, the tap bar counting by its close only.
15. **Tables.** Cell events = fresh tapped events; n, win and mean R are over the orders that filled. Draw: every
    watched real static level-day (leads and members, fresh and used), four distance buckets; days beyond 1 ATR are
    counted in `n_beyond_1atr`. Pairs: eligibility = days on which the two codes share a watched cluster (any
    freshness, tapped or not) >= 60, as the spec's table 3 says; the numbers = the fresh tapped events of those
    clusters, both sides together. **The three pair picks therefore rest on 8, 11 and 17 in-sample trades.** (Read
    as ">= 60 fresh events" the three would have been ldh+prh, onh+vah, onh+prh; not used.)
16. **Selection** ranks every real level code x side (expected-move and VWAP codes included) with >= 150 fresh
    tapped events. Three of the five cell picks (em2u:R, vw:S, em1u:R) have no placebo: in the full phase their
    placebo condition is reported as not judged. "3 of 4 calendar years positive" = net $ > 0 (house convention).

## 2. One line per level code

| code | how | fixed at (`t_set`) | watched |
|---|---|---|---|
| pdh pdl pdc pdm | high, low, last close, (high + low) / 2 of the previous cash day's 09:30-15:59 bars | its last bar | 09:30-15:00 |
| pwh pwl | high, low of the previous trading week (all bars) | that week's last bar | 09:30-15:00 |
| onh onl | high, low of 18:00 (previous calendar day) - 09:29 | last bar before 09:30 | 09:30-15:00 |
| ash asl | high, low of 18:00-01:59 | last bar before 02:00 | 09:30-15:00 |
| ldh ldl | high, low of 02:00-07:59 | last bar before 08:00 | 09:30-15:00 |
| prh prl | high, low of 08:00-09:29 | last bar before 09:30 | 09:30-15:00 |
| o18 o00 o0830 | open of the bar stamped 18:00 / 00:00 / 08:30 | that bar's open | 09:30-15:00 |
| vah poc val | `lev1_levels.profile`: the script's rows (4 ticks, floor((p - rowLo) / rowSize + 1e-9), volume spread evenly over the rows a bar spans, in bar order), POC = first largest row, value area 70 % two rows at a time (up on a tie); poc = rowLo + (ip + 0.5), vah = rowLo + up + 1, val = rowLo + dn | last bar before 09:30 | 09:30-15:00 |
| r100 | floor(open / 100) x 100 + 100 and ceil(open / 100) x 100 - 100 of the 09:30 open | the 09:30 bar's open | 09:30-15:00 |
| orh orl | high, low of 09:30-09:44 | last bar before 09:45 | 09:45-15:00 |
| em1u em1d em2u em2d | centre +/- 1, 2 x (centre x sd5 x sqrt(24)); centre = open of the block's first bar; sd5 = `ind.stdev` (population) of 5-minute log returns over the 2,760 bars before the block | the block's first bar's open | max(09:30, block start) to the block's end or 15:00 |
| vw vw1u vw1d vw2u vw2d | `ind.session_vwap` on 5-minute bars (hlc3 x volume, reset on the script's fullStart), VWAP +/- 1, 2 x its volume-weighted sd | moving: last completed 5-minute close | 09:30-15:00 |
| X~ | X +/- 0.12 x ATR, two per static level | the later of X's bar and the last bar before 18:00 (the ATR) | as X |

## 3. Unit checks of the levels (`python3 tools/yt1/lev1_levels.py --check`)

```
pdh = day table's pdh: 926 of 926 days (1 of them with neither)
pdl = day table's pdl: 926 of 926 days (1 of them with neither)
pdc = day table's pdc: 926 of 926 days (1 of them with neither)
onh = day table's onh: 926 of 926 days (0 of them with neither)
onl = day table's onl: 926 of 926 days (0 of them with neither)
pdm = (pdh + pdl) / 2 of the day table: 926 of 926
max(ash, ldh, prh) = onh: 926 of 926 days;  min(asl, ldl, prl) = onl: 926 of 926   (days with all three parts: 925)
profile: 926 days with a profile (0 without); total volume = summed 1-minute volume of 18:00-09:29 (bars selected by trading date and clock) and rows sum to it: 926 of 926;  val <= poc <= vah: 926 of 926
  brute force 2021-06-29: bars 930, rows 46, volume 104908  Pine transcription VAH 14497.00 POC 14484.50 VAL 14480.00  |  levels() VAH 14497.00 POC 14484.50 VAL 14480.00  -> identical
  brute force 2021-08-25: bars 930, rows 58, volume 104008  Pine transcription VAH 15370.00 POC 15363.50 VAL 15349.00  |  levels() VAH 15370.00 POC 15363.50 VAL 15349.00  -> identical
  brute force 2021-11-11: bars 930, rows 138, volume 238064  Pine transcription VAH 16080.00 POC 16023.50 VAL 15977.00  |  levels() VAH 16080.00 POC 16023.50 VAL 15977.00  -> identical
  brute force 2022-08-17: bars 930, rows 174, volume 262694  Pine transcription VAH 13672.00 POC 13647.50 VAL 13535.00  |  levels() VAH 13672.00 POC 13647.50 VAL 13535.00  -> identical
  brute force 2022-10-14: bars 930, rows 266, volume 626139  Pine transcription VAH 11225.00 POC 11144.50 VAL 11068.00  |  levels() VAH 11225.00 POC 11144.50 VAL 11068.00  -> identical
  brute force on every day: identical on 926 of 926
  expected move 2020-07-21 block 1000: first bar 10:00, centre 10943.25, 2760 returns, sd 0.00103062, by hand 1 sigma 55.2525  |  levels() 55.2525  -> diff 8.24e-13
  expected move 2020-08-07 block 1000: first bar 10:00, centre 11247.50, 2760 returns, sd 0.00082204, by hand 1 sigma 45.2955  |  levels() 45.2955  -> diff 1.17e-12
  expected move 2022-07-27 block 0800: first bar 08:00, centre 12270.25, 2760 returns, sd 0.00120044, by hand 1 sigma 72.1604  |  levels() 72.1604  -> diff 9.38e-13
VWAP on 5-minute bars: ind.session_vwap (new session = the script's fullStart, 18:00) against an independent per-session cumulative sum: 252566 bars, max |diff| VWAP 1.455e-11, sigma 2.744e-07 (09:30-15:00 bars: sigma 1.307e-08); NaN pattern equal: True; sessions 927, of which not starting on an 18:00 bar: 1
  VWAP by hand 2019-11-19 (5-minute bars 18:00-09:25, 186 bars): VWAP 8353.8338 sigma 14.7574 |  levels() vw 8353.8338, (vw2u - vw) / 2 14.7574  -> diff 1.82e-12, 1.01e-09
  VWAP by hand 2021-03-16 (5-minute bars 18:00-09:25, 186 bars): VWAP 13124.4477 sigma 26.9268 |  levels() vw 13124.4477, (vw2u - vw) / 2 26.9268  -> diff 3.64e-12, 3.87e-09
  VWAP by hand 2022-05-11 (5-minute bars 18:00-09:25, 186 bars): VWAP 12363.3960 sigma 126.4709 |  levels() vw 12363.3960, (vw2u - vw) / 2 126.4709  -> diff 5.46e-12, 4.71e-10
moving value in force during the 09:35 bar = VWAP at the close of the 09:30 5-minute bar: 925 of 925 days;  +2 sigma band likewise: 925
```

Level look-ahead test (`lev1_levels.py --causal 170`): three levels of every code, placebos included, each recomputed
on a window in which every bar after the level's own `t_set` is mirrored (`core._reflect`; a level fixed at a bar's
open keeps that one open; static 09:30 levels are cut a second time just before 09:30 for `used` and `dropped`;
a VWAP value is cut at the bar before the one it is in force for):

```
level look-ahead test: 165 levels, each recomputed with the future after its own t_set mirrored, 0 differ -> PASS
```

## 4. Counts (`lev1_events.py --phase is`, `lev1_verify.py --extra`)

```
LEV1 events   phase is   bars 2019-06-02 18:00:00-04:00 -> 2022-12-30 16:59:00-05:00   levels 85117 rows [3s]   events 57653 rows [17s, 2 process(es)]
study days 884 (cash days 926, roll day or the day after 30, no ATR 14)
real levels per day by group: previous day 4.00, previous week 2.00, overnight 2.00, Asia 2.00, London 2.00, pre-market 2.00, opens 2.99, profile 3.00, round numbers 2.00, opening range 2.00, expected move 15.87, VWAP bands 5.00
placebos: made 42418, dropped 24422, kept 17996 (20.4 a day); kept ones within 0.03 x ATR of a later-fixed real static level (the opening range): 1248
static levels `used` (set before 09:30): real 6881 of 21209, placebo 2799 of 17996
study days 884; level-days 57653; skipped near the start price 4142; watched 53511; events (cluster leads, placebos, block and moving levels) 47140; tapped 18398 (39.0%); fresh among tapped 15530 (84.4%)
  real static    events  12031  tapped   6040 (50.2%)  fresh events   8845  fresh tapped   4296
  placebo        events  17465  tapped   6736 (38.6%)  fresh events  14855  fresh tapped   5612
  expected move  events  13894  tapped   3092 (22.3%)  fresh events  13894  fresh tapped   3092
  VWAP bands     events   3750  tapped   2530 (67.5%)  fresh events   3750  fresh tapped   2530
real static: watched level-days 18402, clusters 10905 (1 level 7025, 2 levels 2036, 3 or more 1844); lead rows 12031 (of which tied leads beyond the first 1126); member rows that are not leads 6371
fill bar = tap bar: 18398 tapped events x 12 variants = 220776 orders; filled on the tap bar 220773; filled on another bar 0; not filled 3 (events with at least one unfilled variant: 1); untapped events whose resting headline order filled: 0 of 28742
  not filled by variant: {'p20x1': 0, 'p20x2': 0, 'p20x3': 0, 'a04x1': 1, 'a04x2': 1, 'a04x3': 1, 'a08x1': 0, 'a08x2': 0, 'a08x3': 0, 'brk_p20': 0, 'brk_a04': 0, 'brk_a08': 0}
wrote /home/claude/work/yt1/lab/data/studies/yt1/is/LEV1_levels.parquet and /home/claude/work/yt1/lab/data/studies/yt1/is/LEV1_events.parquet   total 20s
```
```
level-days 57653; open of the first watched bar != last close before it on 42395 (median |diff| 0.25 points, max 119.25)
  among levels not defined by that open (43672): side differs between the two readings on 139 level-days (of which watched under either reading: 49); the near-skip differs on 156
opening-range events 1411: with a watched 09:30 real static level within 0.03 x ATR on the same side 797, of which with one still untapped at 09:45 588 (these are separate events; the opening range joins no cluster)
expected move: sd over the 2,760 bars before the block against the script's value on the block's first bar (one bar later): median relative difference 1.85e-04, max 6.37e-02
static levels off the tick grid: 402 of 22195 (pdm only: 402)
days by number of expected-move blocks with bands: {3: 29, 4: 887}
cash days whose overnight session directly follows another overnight bar (the script would not restart its profile there): 1
tied leads: clusters with more than one lead 1088
```
Watch windows on full days: 09:30 levels 09:30..15:00; opening range 09:45 (later when minutes are missing, 09:50
at the latest)..15:00; expected-move blocks 09:30..09:59, 10:00..11:59, 12:00..13:59, 14:00..15:00. Tapped events by time of tap:
09:30-09:59 8,891; 10:00-11:29 5,687; 11:30-15:00 3,820. Taps on the first watched bar itself: 1,273 (846 of them
static levels tapped by the 09:30 bar). No order bar lies on another calendar day than its cash day.

## 5. Fill bar = tap bar

Every event's orders were given to `core.simulate` as written in reading 8 / 10 (static and block levels: one order
resting from the bar before the watch; VWAP levels: the one-bar orders). Of 18,398 tapped events x 12 variants =
220,776 orders, 220,773 filled on the tap bar, none on another bar, 3 did not fill: one event, 2020-03-09
`em2d.0800`, where the 09:34 bar (09:33 is missing, limit-down morning) opened at 7900.00, below the level 7914.75
and below the a04 stop 7902.75; `core.simulate` rejects an order whose fill is at or through its stop, so the three
a04 fades have no trade there (the a08 and p20 fades and the breaks filled at the open). None of the 28,742
never-tapped events' resting headline order filled, and none of the earlier one-bar orders of a VWAP event filled.
A tap bar that opens at or beyond the order price (a gap through the level) occurs 15 times (6 static, 2 block,
7 VWAP): the tap is that bar and the fade fills at its open, as the house rule says; never on the first watched bar.

## 6. Hand checks (`python3 tools/yt1/lev1_verify.py`)

Each level is re-derived below from plain time slices of the bars (not with `lev1_levels`), then the watch, the bars
around the tap and the trade. All 14 levels agree with the table; every trade agrees with the events file. Events 1
to 13 were drawn with a fixed seed inside each category; 14 is the one unfilled event.

```

### 1 previous-day level: 2020-01-13 pdh (previous day)
  level: previous cash day 2020-01-10 09:30-15:59, 390 bars 01-10 09:30..01-10 15:59: high 9042.50 low 8966.50 last close 8982.75
  -> by hand 9042.5000; table 9042.5000 (same); set at 01-10 15:59; used False
  watch 09:30..15:00; price at the start (open of the 09:30 bar) 9017.25; ATR 104.20; level above by 25.25 = 0.242 ATR (skip under 0.04) -> resistance; order price 9042.50; cluster pdh (1), lead True
  tap bar 11:17 (bucket 1000); highest high of the watch before it 9041.00 (below the order price)
  a04x3: order i=09:29 sell limit 9042.50 stop 9046.75 target 9029.75 (d = 4.25) -> fill 11:17 at 9042.25, exit 11:28 at 9047.00 (SL), pnl -11.50, R -1.278   [events file: R -1.278 SL]
  p20x3: order i=09:29 sell limit 9042.50 stop 9062.50 target 8982.50 (d = 20.00) -> fill 11:17 at 9042.25, exit 12:02 at 9062.75 (SL), pnl -43.00, R -1.062   [events file: R -1.062 SL]
      11:15  O 9035.25  H 9038.75  L 9035.00  C 9038.75
      11:16  O 9039.00  H 9041.00  L 9037.25  C 9040.25
      11:17  O 9040.25  H 9043.25  L 9039.50  C 9040.00   <- tap
      11:18  O 9040.00  H 9041.50  L 9039.25  C 9040.75
      11:19  O 9040.25  H 9040.75  L 9039.00  C 9040.75
      11:20  O 9041.00  H 9042.00  L 9037.50  C 9041.50
      11:21  O 9041.25  H 9041.50  L 9039.00  C 9039.00
      11:22  O 9039.00  H 9040.25  L 9038.00  C 9039.00
      11:23  O 9039.00  H 9040.50  L 9038.50  C 9038.50
      11:24  O 9038.75  H 9039.50  L 9038.00  C 9038.75
      11:25  O 9038.50  H 9039.00  L 9035.75  C 9036.00
      11:26  O 9036.25  H 9038.50  L 9036.25  C 9037.50
      11:27  O 9038.00  H 9039.50  L 9038.00  C 9038.25
      11:28  O 9038.00  H 9051.75  L 9034.25  C 9037.25   <- exit SL
  30 minutes from the tap: largest move away 0.082 ATR, through 0.089 ATR; distance from the 09:30 open 0.242 ATR

### 2 Asia / London level that is used: 2020-01-16 ash (Asia)
  level: as session, 480 bars 01-15 18:00..01-16 01:59: high 9083.25 low 9060.50 last close 9083.25
  -> by hand 9083.2500; table 9083.2500 (same); set at 01-16 01:59; used True
  watch 09:30..15:00; price at the start (open of the 09:30 bar) 9095.75; ATR 101.22; level below by 12.50 = 0.123 ATR (skip under 0.04) -> support; order price 9083.25; cluster ash (1), lead True
  tap bar 11:14 (bucket 1000); lowest low of the watch before it 9085.75 (above the order price)
  a04x3: order i=09:29 buy limit 9083.25 stop 9079.25 target 9095.25 (d = 4.00) -> fill 11:14 at 9083.50, exit 11:16 at 9079.00 (SL), pnl -11.00, R -1.294   [events file: R -1.294 SL]
  p20x3: order i=09:29 buy limit 9083.25 stop 9063.25 target 9143.25 (d = 20.00) -> fill 11:14 at 9083.50, exit 15:59 at 9137.75 (time), pnl +106.50, R +2.630   [events file: R +2.630 time]
      11:12  O 9092.25  H 9092.50  L 9086.25  C 9088.25
      11:13  O 9088.00  H 9089.50  L 9085.75  C 9089.50
      11:14  O 9089.50  H 9091.50  L 9082.75  C 9085.75   <- tap
      11:15  O 9085.75  H 9088.00  L 9082.50  C 9083.25
      11:16  O 9083.00  H 9084.00  L 9076.50  C 9080.50   <- exit SL
  30 minutes from the tap: largest move away 0.111 ATR, through 0.067 ATR; distance from the 09:30 open 0.123 ATR

### 3 profile level: 2022-02-14 val (profile)
  level: profile of 930 one-minute bars 18:00-09:29 (Pine transcription): 267 rows of 1.00 from 14030.00, volume 660604; POC row 217 [14247.00, 14248.00) holds 7838.6 (next largest 7802.2); value area rows 97..255 hold 463133.0 = 70.1% of the volume; VAH 14286.00 POC 14247.50 VAL 14127.00
  -> by hand 14127.0000; table 14127.0000 (same); set at 02-14 09:29; used False
  watch 09:30..15:00; price at the start (open of the 09:30 bar) 14208.50; ATR 440.37; level below by 81.50 = 0.185 ATR (skip under 0.04) -> support; order price 14127.00; cluster val (1), lead True
  tap bar 14:01 (bucket 1130); lowest low of the watch before it 14130.25 (above the order price)
  a04x3: order i=09:29 buy limit 14127.00 stop 14109.50 target 14179.50 (d = 17.50) -> fill 14:01 at 14127.25, exit 14:07 at 14109.25 (SL), pnl -38.00, R -1.070   [events file: R -1.070 SL]
  p20x3: order i=09:29 buy limit 14127.00 stop 14107.00 target 14187.00 (d = 20.00) -> fill 14:01 at 14127.25, exit 14:07 at 14106.75 (SL), pnl -43.00, R -1.062   [events file: R -1.062 SL]
      13:59  O 14163.25  H 14167.75  L 14138.25  C 14139.75
      14:00  O 14140.50  H 14169.25  L 14130.25  C 14156.75
      14:01  O 14156.25  H 14165.25  L 14127.00  C 14139.50   <- tap
      14:02  O 14139.50  H 14155.50  L 14134.75  C 14138.25
      14:03  O 14138.50  H 14144.00  L 14124.50  C 14141.75
      14:04  O 14141.50  H 14152.50  L 14128.25  C 14129.50
      14:05  O 14129.75  H 14140.50  L 14118.25  C 14133.00
      14:06  O 14133.00  H 14134.50  L 14110.50  C 14115.00
      14:07  O 14114.00  H 14120.50  L 14102.25  C 14117.00   <- exit SL
  30 minutes from the tap: largest move away 0.281 ATR, through 0.056 ATR; distance from the 09:30 open 0.185 ATR

### 4 expected-move band inside its block: 2021-05-03 em2d.1000 (expected move)
  level: block 1000: centre = open of the 10:00 bar 13873.75; population sd of the 2760 five-minute log returns before it 0.00055890; 1 sigma = centre x sd x sqrt(24) = 37.9866; band = centre -2 sigma
  -> by hand 13797.7769; table 13797.7769 (same); set at 05-03 10:00; used False
  watch 10:00..11:59; price at the start (open of the 10:00 bar) 13873.75; ATR 211.88; level below by 75.97 = 0.359 ATR (skip under 0.04) -> support; order price 13797.75; cluster em2d (1), lead True
  tap bar 11:12 (bucket 1000); lowest low of the watch before it 13803.75 (above the order price)
  a04x3: order i=09:59 buy limit 13797.75 stop 13789.25 target 13823.25 (d = 8.50) -> fill 11:12 at 13798.00, exit 11:25 at 13789.00 (SL), pnl -20.00, R -1.143   [events file: R -1.143 SL]
  p20x3: order i=09:59 buy limit 13797.75 stop 13777.75 target 13857.75 (d = 20.00) -> fill 11:12 at 13798.00, exit 11:26 at 13777.50 (SL), pnl -43.00, R -1.062   [events file: R -1.062 SL]
      11:10  O 13844.75  H 13845.50  L 13835.75  C 13838.00
      11:11  O 13838.00  H 13840.75  L 13803.75  C 13810.00
      11:12  O 13810.75  H 13813.50  L 13796.25  C 13800.00   <- tap
      11:13  O 13800.25  H 13805.00  L 13791.25  C 13797.00
      11:14  O 13797.00  H 13801.00  L 13794.50  C 13796.75
      11:15  O 13796.75  H 13807.50  L 13790.25  C 13804.25
      11:16  O 13804.50  H 13810.50  L 13801.75  C 13807.00
      11:17  O 13807.25  H 13807.75  L 13799.75  C 13802.50
      11:18  O 13802.75  H 13808.75  L 13802.75  C 13804.75
      11:19  O 13805.00  H 13805.25  L 13797.75  C 13803.75
      11:20  O 13803.50  H 13803.50  L 13791.25  C 13796.75
      11:21  O 13797.50  H 13812.75  L 13794.00  C 13810.50
      11:22  O 13811.00  H 13813.50  L 13803.00  C 13808.50
      11:23  O 13808.25  H 13810.50  L 13800.25  C 13804.00
      11:24  O 13804.00  H 13805.50  L 13797.75  C 13802.50
      ... exit bar 11:25  O 13802.25  H 13802.25  L 13783.50  C 13787.50   <- exit SL
  30 minutes from the tap: largest move away 0.095 ATR, through 0.104 ATR; distance from the 09:30 open 0.553 ATR

### 5 VWAP band: 2021-08-17 vw1d (VWAP bands)
  level: 187 five-minute bars 18:00 .. 09:30 (the last one completed before the 09:36 bar): VWAP 15056.5982, sigma 40.2350; level = VWAP -1 sigma
  -> by hand 15016.3632; table 15016.3632 (same); set at (moving); used False
  watch 09:30..15:00; price at the start (open of the 09:30 bar) 15017.00; ATR 165.66; level above by 25.28 = 0.153 ATR (skip under 0.04) -> resistance; order price 15016.50; cluster vw1d (1), lead True
  tap bar 09:36 (bucket 0930); highest high of the watch before it 15020.75 (below the order price)
  a04x3: order i=09:35 sell limit 15016.50 stop 15023.25 target 14996.25 (d = 6.75) -> fill 09:36 at 15016.25, exit 09:36 at 15023.50 (SL), pnl -16.50, R -1.179   [events file: R -1.179 SL]
  p20x3: order i=09:35 sell limit 15016.50 stop 15036.50 target 14956.50 (d = 20.00) -> fill 09:36 at 15016.25, exit 09:43 at 15036.75 (SL), pnl -43.00, R -1.062   [events file: R -1.062 SL]
      09:34  O 14993.75  H 15010.00  L 14992.25  C 15009.00
      09:35  O 15008.75  H 15010.50  L 14986.75  C 14998.25
      09:36  O 14997.75  H 15029.00  L 14994.25  C 15023.50   <- tap
  30 minutes from the tap: largest move away 0.408 ATR, through 0.158 ATR; distance from the 09:30 open 0.004 ATR

### 6 opening-range level: 2021-07-29 orh (opening range)
  level: opening range, 15 bars 07-29 09:30..07-29 09:44: high 15069.75 low 14982.25 last close 15056.50
  -> by hand 15069.7500; table 15069.7500 (same); set at 07-29 09:44; used False
  watch 09:45..15:00; price at the start (open of the 09:45 bar) 15056.75; ATR 193.12; level above by 13.00 = 0.067 ATR (skip under 0.04) -> resistance; order price 15069.75; cluster orh (1), lead True
  tap bar 09:46 (bucket 0930); highest high of the watch before it 15069.25 (below the order price)
  a04x3: order i=09:44 sell limit 15069.75 stop 15077.50 target 15046.50 (d = 7.75) -> fill 09:46 at 15069.50, exit 09:46 at 15077.75 (SL), pnl -18.50, R -1.156   [events file: R -1.156 SL]
  p20x3: order i=09:44 sell limit 15069.75 stop 15089.75 target 15009.75 (d = 20.00) -> fill 09:46 at 15069.50, exit 15:59 at 15035.25 (time), pnl +66.50, R +1.642   [events file: R +1.642 time]
      09:44  O 15062.25  H 15062.50  L 15053.00  C 15056.50
      09:45  O 15056.75  H 15069.25  L 15055.00  C 15069.25
      09:46  O 15069.00  H 15079.50  L 15068.75  C 15079.25   <- tap
  30 minutes from the tap: largest move away 0.251 ATR, through 0.050 ATR; distance from the 09:30 open 0.448 ATR

### 7 placebo: 2022-01-07 onl~.- (overnight, placebo)
  level: on session, 930 bars 01-06 18:00..01-07 09:29: high 15853.25 low 15624.50 last close 15757.00; parent onl = 15624.50; placebo = parent - 0.12 x ATR (37.42)
  -> by hand 15587.0762; table 15587.0762 (same); set at 01-07 09:29; used False
  watch 09:30..15:00; price at the start (open of the 09:30 bar) 15757.50; ATR 311.87; level below by 170.42 = 0.546 ATR (skip under 0.04) -> support; order price 15587.00; cluster onl~ (1), lead True
  nearest real static level known at the start: pdl 15598.50, 11.42 away (dropped within 9.36)
  tap bar 10:43 (bucket 1000); lowest low of the watch before it 15593.50 (above the order price)
  a04x3: order i=09:29 buy limit 15587.00 stop 15574.50 target 15624.50 (d = 12.50) -> fill 10:43 at 15587.25, exit 10:46 at 15574.25 (SL), pnl -28.00, R -1.098   [events file: R -1.098 SL]
  p20x3: order i=09:29 buy limit 15587.00 stop 15567.00 target 15647.00 (d = 20.00) -> fill 10:43 at 15587.25, exit 10:48 at 15566.75 (SL), pnl -43.00, R -1.062   [events file: R -1.062 SL]
      10:41  O 15630.25  H 15636.75  L 15610.75  C 15612.50
      10:42  O 15612.50  H 15613.00  L 15593.50  C 15594.00
      10:43  O 15593.75  H 15606.75  L 15582.50  C 15584.25   <- tap
      10:44  O 15584.50  H 15593.25  L 15583.50  C 15587.50
      10:45  O 15587.25  H 15589.75  L 15575.50  C 15579.75
      10:46  O 15580.25  H 15587.50  L 15573.00  C 15584.50   <- exit SL
  30 minutes from the tap: largest move away 0.020 ATR, through 0.246 ATR; distance from the 09:30 open 0.546 ATR

### 8 cluster of two levels: 2019-07-26 val (profile)
  level: profile of 918 one-minute bars 18:00-09:29 (Pine transcription): 36 rows of 1.00 from 7987.00, volume 35433; POC row 17 [8004.00, 8005.00) holds 2436.3 (next largest 2058.0); value area rows 15..31 hold 24842.6 = 70.1% of the volume; VAH 8019.00 POC 8004.50 VAL 8002.00
  -> by hand 8002.0000; table 8002.0000 (same); set at 07-26 09:29; used False
  watch 09:30..15:00; price at the start (open of the 09:30 bar) 7997.75; ATR 104.28; level above by 4.25 = 0.041 ATR (skip under 0.04) -> resistance; order price 8002.00; cluster poc+val (2), lead True
  cluster members: poc 8004.50, val 8002.00 (lead); 0.03 x ATR = 3.13
  tap bar 09:30 = the first watched bar (bucket 0930)
  a04x3: order i=09:29 sell limit 8002.00 stop 8006.25 target 7989.25 (d = 4.25) -> fill 09:30 at 8001.75, exit 09:30 at 8006.50 (SL), pnl -11.50, R -1.278   [events file: R -1.278 SL]
  p20x3: order i=09:29 sell limit 8002.00 stop 8022.00 target 7942.00 (d = 20.00) -> fill 09:30 at 8001.75, exit 09:34 at 8022.25 (SL), pnl -43.00, R -1.062   [events file: R -1.062 SL]
      09:29  O 8001.75  H 8003.50  L 7997.75  C 7997.75
      09:30  O 7997.75  H 8007.50  L 7994.50  C 8004.25   <- tap
  30 minutes from the tap: largest move away 0.029 ATR, through 0.312 ATR; distance from the 09:30 open 0.041 ATR

### 9 stopped fade: 2021-03-05 vah (profile)
  level: profile of 930 one-minute bars 18:00-09:29 (Pine transcription): 328 rows of 1.00 from 12305.00, volume 556361; POC row 115 [12420.00, 12421.00) holds 5278.0 (next largest 4946.2); value area rows 37..169 hold 390921.9 = 70.3% of the volume; VAH 12475.00 POC 12420.50 VAL 12342.00
  -> by hand 12475.0000; table 12475.0000 (same); set at 03-05 09:29; used False
  watch 09:30..15:00; price at the start (open of the 09:30 bar) 12583.00; ATR 332.66; level below by 108.00 = 0.325 ATR (skip under 0.04) -> support; order price 12475.00; cluster ash+pdc+vah (3), lead True
  cluster members: pdc 12471.50, ash 12474.00, vah 12475.00 (lead); 0.03 x ATR = 9.98
  tap bar 09:38 (bucket 0930); lowest low of the watch before it 12486.50 (above the order price)
  a04x3: order i=09:29 buy limit 12475.00 stop 12461.75 target 12514.75 (d = 13.25) -> fill 09:38 at 12475.25, exit 09:39 at 12461.50 (SL), pnl -29.50, R -1.093   [events file: R -1.093 SL]
  p20x3: order i=09:29 buy limit 12475.00 stop 12455.00 target 12535.00 (d = 20.00) -> fill 09:38 at 12475.25, exit 09:42 at 12454.75 (SL), pnl -43.00, R -1.062   [events file: R -1.062 SL]
      09:36  O 12510.00  H 12534.00  L 12504.25  C 12517.00
      09:37  O 12516.75  H 12518.25  L 12486.50  C 12492.75
      09:38  O 12493.00  H 12505.25  L 12472.25  C 12483.75   <- tap
      09:39  O 12483.75  H 12486.00  L 12458.25  C 12463.75   <- exit SL
  30 minutes from the tap: largest move away 0.150 ATR, through 0.349 ATR; distance from the 09:30 open 0.325 ATR

### 10 3R winner: 2020-01-15 pdh (previous day)
  level: previous cash day 2020-01-14 09:30-15:59, 390 bars 01-14 09:30..01-14 15:59: high 9095.00 low 9035.00 last close 9050.50
  -> by hand 9095.0000; table 9095.0000 (same); set at 01-14 15:59; used False
  watch 09:30..15:00; price at the start (open of the 09:30 bar) 9054.00; ATR 103.39; level above by 41.00 = 0.397 ATR (skip under 0.04) -> resistance; order price 9095.00; cluster pdh (1), lead True
  tap bar 10:46 (bucket 1000); highest high of the watch before it 9094.00 (below the order price)
  a04x3: order i=09:29 sell limit 9095.00 stop 9099.25 target 9082.25 (d = 4.25) -> fill 10:46 at 9094.75, exit 11:02 at 9082.50 (TP), pnl +22.50, R +2.500   [events file: R +2.500 TP]
  p20x3: order i=09:29 sell limit 9095.00 stop 9115.00 target 9035.00 (d = 20.00) -> fill 10:46 at 9094.75, exit 15:27 at 9035.25 (TP), pnl +117.00, R +2.889   [events file: R +2.889 TP]
      10:44  O 9092.50  H 9093.00  L 9089.75  C 9090.00
      10:45  O 9090.25  H 9093.75  L 9089.75  C 9092.75
      10:46  O 9093.25  H 9096.00  L 9093.25  C 9095.00   <- tap
      10:47  O 9094.75  H 9094.75  L 9091.00  C 9091.00
      10:48  O 9091.50  H 9094.00  L 9091.25  C 9091.50
      10:49  O 9091.75  H 9092.25  L 9089.00  C 9089.50
      10:50  O 9089.75  H 9090.50  L 9088.50  C 9090.00
      10:51  O 9089.75  H 9092.25  L 9089.50  C 9089.75
      10:52  O 9090.00  H 9090.50  L 9087.75  C 9089.75
      10:53  O 9090.00  H 9091.75  L 9089.25  C 9089.25
      10:54  O 9089.25  H 9089.75  L 9086.50  C 9088.75
      10:55  O 9089.00  H 9090.75  L 9088.75  C 9090.00
      10:56  O 9090.25  H 9093.75  L 9089.75  C 9091.25
      10:57  O 9091.00  H 9093.50  L 9090.50  C 9092.75
      10:58  O 9093.00  H 9093.50  L 9091.50  C 9092.50
      ... exit bar 11:02  O 9084.50  H 9085.50  L 9081.25  C 9082.75   <- exit TP
  30 minutes from the tap: largest move away 0.235 ATR, through 0.010 ATR; distance from the 09:30 open 0.397 ATR

### 11 round number tapped by the 09:30 bar itself: 2020-10-22 r100.up (round numbers)
  level: 09:30 open 11686.75: nearest multiple of 100 strictly above
  -> by hand 11700.0000; table 11700.0000 (same); set at 10-22 09:30; used False
  watch 09:30..15:00; price at the start (open of the 09:30 bar) 11686.75; ATR 284.94; level above by 13.25 = 0.047 ATR (skip under 0.04) -> resistance; order price 11700.00; cluster ash+onh+pdm+r100 (4), lead True
  cluster members: pdm 11704.75, onh 11701.50, ash 11701.50, r100 11700.00 (lead); 0.03 x ATR = 8.55
  tap bar 09:30 = the first watched bar (bucket 0930)
  a04x3: order i=09:29 sell limit 11700.00 stop 11711.50 target 11665.50 (d = 11.50) -> fill 09:30 at 11699.75, exit 09:30 at 11711.75 (SL), pnl -26.00, R -1.106   [events file: R -1.106 SL]
  p20x3: order i=09:29 sell limit 11700.00 stop 11720.00 target 11640.00 (d = 20.00) -> fill 09:30 at 11699.75, exit 09:31 at 11720.25 (SL), pnl -43.00, R -1.062   [events file: R -1.062 SL]
      09:29  O 11683.00  H 11687.75  L 11683.00  C 11686.50
      09:30  O 11686.75  H 11713.50  L 11684.75  C 11709.00   <- tap
  30 minutes from the tap: largest move away 0.150 ATR, through 0.083 ATR; distance from the 09:30 open 0.047 ATR

### 12 an event that is never tapped: 2022-09-05 pdl (previous day)
  level: previous cash day 2022-09-02 09:30-15:59, 390 bars 09-02 09:30..09-02 15:59: high 12462.00 low 12040.50 last close 12110.25
  -> by hand 12040.5000; table 12040.5000 (same); set at 09-02 15:59; used False
  watch 09:30..12:49; price at the start (open of the 09:30 bar) 12112.75; ATR 312.77; level below by 72.25 = 0.231 ATR (skip under 0.04) -> support; order price 12040.50; cluster pdl (1), lead True
  never tapped: highest high of the watch 12167.25, lowest low 12104.75

### 13 previous-week level: 2021-08-06 pwh (previous week)
  level: previous week, 6899 bars 07-25 18:00..07-30 16:59: high 15134.25 low 14774.50 last close 14967.25
  -> by hand 15134.2500; table 15134.2500 (same); set at 07-30 16:59; used True
  watch 09:30..15:00; price at the start (open of the 09:30 bar) 15109.00; ATR 175.78; level above by 25.25 = 0.144 ATR (skip under 0.04) -> resistance; order price 15134.25; cluster pwh (1), lead True
  tap bar 09:34 (bucket 0930); highest high of the watch before it 15129.50 (below the order price)
  a04x3: order i=09:29 sell limit 15134.25 stop 15141.25 target 15113.25 (d = 7.00) -> fill 09:34 at 15134.00, exit 09:34 at 15141.50 (SL), pnl -17.00, R -1.172   [events file: R -1.172 SL]
  p20x3: order i=09:29 sell limit 15134.25 stop 15154.25 target 15074.25 (d = 20.00) -> fill 09:34 at 15134.00, exit 10:55 at 15074.50 (TP), pnl +117.00, R +2.889   [events file: R +2.889 TP]
      09:32  O 15124.00  H 15128.75  L 15115.75  C 15121.75
      09:33  O 15121.75  H 15129.50  L 15115.00  C 15128.25
      09:34  O 15128.75  H 15143.00  L 15125.00  C 15142.50   <- tap
  30 minutes from the tap: largest move away 0.222 ATR, through 0.090 ATR; distance from the 09:30 open 0.144 ATR

### 14 the one event whose a04 order is not filled: 2020-03-09 em2d.0800 (expected move)
  level: block 0800: centre = open of the 08:06 bar 8093.25; population sd of the 2760 five-minute log returns before it 0.00225093; 1 sigma = centre x sd x sqrt(24) = 89.2465; band = centre -2 sigma
  -> by hand 7914.7570; table 7914.7570 (same); set at 03-09 08:06; used False
  watch 09:30..09:59; price at the start (open of the 09:30 bar) 8022.00; ATR 297.51; level below by 107.24 = 0.360 ATR (skip under 0.04) -> support; order price 7914.75; cluster em2d (1), lead True
  tap bar 09:34 (bucket 0930); lowest low of the watch before it 7922.75 (above the order price)
  a04x3: order i=09:12 buy limit 7914.75 stop 7902.75 target 7950.75 (d = 12.00) -> no fill   [events file: R +nan ]
  p20x3: order i=09:12 buy limit 7914.75 stop 7894.75 target 7974.75 (d = 20.00) -> fill 09:34 at 7900.25, exit 09:34 at 7894.50 (SL), pnl -13.50, R -1.227   [events file: R -1.227 SL]
      09:31  O 7923.00  H 7928.75  L 7922.75  C 7922.75
      09:32  O 7922.75  H 7922.75  L 7922.75  C 7922.75
      09:34  O 7900.00  H 7919.50  L 7801.00  C 7842.75   <- tap
  30 minutes from the tap: largest move away 0.608 ATR, through 0.382 ATR; distance from the 09:30 open 0.360 ATR
```

Previous week across a Monday holiday (Labor Day 2022-09-05 is a short cash day): Monday 09-05 and Tuesday 09-06
both have pwh 12659.00 = the high of 08-28 18:00 .. 09-02 16:59; Tuesday 2021-07-06 (after 07-05) has 14728.75 =
the high of 06-27 18:00 .. 07-02 16:59.

## 7. Reconciliation (`python3 tools/yt1/run.py L1 --phase is`, then `python3 tools/yt1/s_L1.py --recon`)

Every variant's trades as saved by the standard runner against (a) the events file and (b) the table row:

```
L1 base     em2u:R     a04x3    fresh run.py: n  320 net    +481.50 R  +0.0744 | events file: n  320 net    +481.50 R  +0.0744 -> same | table (reaction): n 320 net +481.50 R +0.0744 -> same
L1 nb1      em2u:R     a08x3    fresh run.py: n  320 net   +1850.00 R  +0.1409 | events file: n  320 net   +1850.00 R  +0.1409 -> same | table (reaction): n 320 net +1850.00 R +0.1409 -> same
L1 nb2      em2u:R     a04x2    fresh run.py: n  320 net     -75.00 R  -0.0102 | events file: n  320 net     -75.00 R  -0.0102 -> same | table (reaction): n 320 net -75.00 R -0.0102 -> same
L1 p2       onh:R      a04x3    fresh run.py: n  260 net     +36.00 R  -0.0300 | events file: n  260 net     +36.00 R  -0.0300 -> same | table (reaction): n 260 net +36.00 R -0.0300 -> same
L1 p2_nb1   onh:R      a08x3    fresh run.py: n  260 net   +1180.00 R  +0.0366 | events file: n  260 net   +1180.00 R  +0.0366 -> same | table (reaction): n 260 net +1180.00 R +0.0366 -> same
L1 p2_nb2   onh:R      a04x2    fresh run.py: n  260 net    -225.50 R  -0.0826 | events file: n  260 net    -225.50 R  -0.0826 -> same | table (reaction): n 260 net -225.50 R -0.0826 -> same
L1 p3       ldh:R      a04x3    fresh run.py: n  159 net    -269.50 R  -0.0791 | events file: n  159 net    -269.50 R  -0.0791 -> same | table (reaction): n 159 net -269.50 R -0.0791 -> same
L1 p3_nb1   ldh:R      a08x3    fresh run.py: n  159 net    +978.00 R  +0.0897 | events file: n  159 net    +978.00 R  +0.0897 -> same | table (reaction): n 159 net +978.00 R +0.0897 -> same
L1 p3_nb2   ldh:R      a04x2    fresh run.py: n  159 net    -601.00 R  -0.1592 | events file: n  159 net    -601.00 R  -0.1592 -> same | table (reaction): n 159 net -601.00 R -0.1592 -> same
L1 p4       vw:S       a04x3    fresh run.py: n  305 net     -80.50 R  -0.1711 | events file: n  305 net     -80.50 R  -0.1711 -> same | table (reaction): n 305 net -80.50 R -0.1711 -> same
L1 p4_nb1   vw:S       a08x3    fresh run.py: n  305 net    +631.00 R  -0.0697 | events file: n  305 net    +631.00 R  -0.0697 -> same | table (reaction): n 305 net +631.00 R -0.0697 -> same
L1 p4_nb2   vw:S       a04x2    fresh run.py: n  305 net    -652.50 R  -0.2047 | events file: n  305 net    -652.50 R  -0.2047 -> same | table (reaction): n 305 net -652.50 R -0.2047 -> same
L1 p5       em1u:R     a04x3    fresh run.py: n 1090 net   -2906.00 R  -0.1718 | events file: n 1090 net   -2906.00 R  -0.1718 -> same | table (reaction): n 1090 net -2906.00 R -0.1718 -> same
L1 p5_nb1   em1u:R     a08x3    fresh run.py: n 1090 net   -4222.00 R  -0.1259 | events file: n 1090 net   -4222.00 R  -0.1259 -> same | table (reaction): n 1090 net -4222.00 R -0.1259 -> same
L1 p5_nb2   em1u:R     a04x2    fresh run.py: n 1090 net   -3593.50 R  -0.1916 | events file: n 1090 net   -3593.50 R  -0.1916 -> same | table (reaction): n 1090 net -3593.50 R -0.1916 -> same
L1 p6       o00+pdh    a04x3    fresh run.py: n    8 net    +128.50 R  +0.6454 | events file: n    8 net    +128.50 R  +0.6454 -> same | table (pairs): n 8 net +128.50 R +0.6454 -> same
L1 p6_nb1   o00+pdh    a08x3    fresh run.py: n    8 net    +276.50 R  +0.8825 | events file: n    8 net    +276.50 R  +0.8825 -> same | table (pairs): n 8 net +276.50 R +0.8825 -> same
L1 p6_nb2   o00+pdh    a04x2    fresh run.py: n    8 net    +147.00 R  +0.6477 | events file: n    8 net    +147.00 R  +0.6477 -> same | table (pairs): n 8 net +147.00 R +0.6477 -> same
L1 p7       ldh+o0830  a04x3    fresh run.py: n   11 net    +119.00 R  +0.6122 | events file: n   11 net    +119.00 R  +0.6122 -> same | table (pairs): n 11 net +119.00 R +0.6122 -> same
L1 p7_nb1   ldh+o0830  a08x3    fresh run.py: n   11 net    +200.50 R  +0.3526 | events file: n   11 net    +200.50 R  +0.3526 -> same | table (pairs): n 11 net +200.50 R +0.3526 -> same
L1 p7_nb2   ldh+o0830  a04x2    fresh run.py: n   11 net     +28.00 R  +0.1722 | events file: n   11 net     +28.00 R  +0.1722 -> same | table (pairs): n 11 net +28.00 R +0.1722 -> same
L1 p8       o0830+prh  a04x3    fresh run.py: n   17 net    +172.50 R  +0.4791 | events file: n   17 net    +172.50 R  +0.4791 -> same | table (pairs): n 17 net +172.50 R +0.4791 -> same
L1 p8_nb1   o0830+prh  a08x3    fresh run.py: n   17 net    +106.00 R  +0.0967 | events file: n   17 net    +106.00 R  +0.0967 -> same | table (pairs): n 17 net +106.00 R +0.0967 -> same
L1 p8_nb2   o0830+prh  a04x2    fresh run.py: n   17 net    +156.50 R  +0.4180 | events file: n   17 net    +156.50 R  +0.4180 -> same | table (pairs): n 17 net +156.50 R +0.4180 -> same
L1 chk1     pdh:R      a04x3    fresh run.py: n   93 net    -449.00 R  -0.2573 | events file: n   93 net    -449.00 R  -0.2573 -> same | table (reaction): n 93 net -449.00 R -0.2573 -> same
L1 chk2     pwl:S      a04x3    fresh run.py: n   29 net    -122.00 R  -0.2019 | events file: n   29 net    -122.00 R  -0.2019 -> same | table (reaction): n 29 net -122.00 R -0.2019 -> same
L1 chk3     onh:R      a04x3    fresh run.py: n  260 net     +36.00 R  -0.0300 | events file: n  260 net     +36.00 R  -0.0300 -> same | table (reaction): n 260 net +36.00 R -0.0300 -> same
L1 chk4     asl:S      a04x3    fresh run.py: n  108 net    +212.00 R  -0.1311 | events file: n  108 net    +212.00 R  -0.1311 -> same | table (reaction): n 108 net +212.00 R -0.1311 -> same
L1 chk5     ldh:R      a04x3    fresh run.py: n  159 net    -269.50 R  -0.0791 | events file: n  159 net    -269.50 R  -0.0791 -> same | table (reaction): n 159 net -269.50 R -0.0791 -> same
L1 chk6     prl:S      a04x3    fresh run.py: n  308 net   -2190.00 R  -0.3388 | events file: n  308 net   -2190.00 R  -0.3388 -> same | table (reaction): n 308 net -2190.00 R -0.3388 -> same
L1 chk7     o0830:R    a04x3    fresh run.py: n    5 net     -78.00 R  -0.4245 | events file: n    5 net     -78.00 R  -0.4245 -> same | table (reaction): n 5 net -78.00 R -0.4245 -> same
L1 chk8     poc:S      a04x3    fresh run.py: n  115 net    -803.00 R  -0.2890 | events file: n  115 net    -803.00 R  -0.2890 -> same | table (reaction): n 115 net -803.00 R -0.2890 -> same
L1 chk9     r100:R     a04x3    fresh run.py: n  289 net   -1334.00 R  -0.2606 | events file: n  289 net   -1334.00 R  -0.2606 -> same | table (reaction): n 289 net -1334.00 R -0.2606 -> same
L1 chk10    orl:S      a04x3    fresh run.py: n  481 net   -4229.00 R  -0.3904 | events file: n  481 net   -4229.00 R  -0.3904 -> same | table (reaction): n 481 net -4229.00 R -0.3903 -> same
L1 chk11    em1u:R     a04x3    fresh run.py: n 1090 net   -2906.00 R  -0.1718 | events file: n 1090 net   -2906.00 R  -0.1718 -> same | table (reaction): n 1090 net -2906.00 R -0.1718 -> same
L1 chk12    vw1d:S     a04x3    fresh run.py: n  413 net   -1616.50 R  -0.2621 | events file: n  413 net   -1616.50 R  -0.2621 -> same | table (reaction): n 413 net -1616.50 R -0.2621 -> same
L1 chk13    pdh~:R     a04x3    fresh run.py: n  168 net    -716.50 R  -0.2490 | events file: n  168 net    -716.50 R  -0.2490 -> same | table (placebo columns): n 168 net -716.50 R -0.2490 -> same
L1 chk14    ash:R      a04x3    any   run.py: n  141 net    -197.50 R  -0.1178 | events file: n  141 net    -197.50 R  -0.1178 -> same | table (used (set any)): n 141 net -197.50 R -0.1178 -> same
L1 chk15    onl:S      brk_a04  fresh run.py: n  246 net    -359.50 R  -0.0536 | events file: n  246 net    -359.50 R  -0.0536 -> same | table (reaction): n 246 net -359.50 R -0.0536 -> same
L1 chk16    ash+onh    a04x3    fresh run.py: n  135 net    -241.00 R  -0.1854 | events file: n  135 net    -241.00 R  -0.1854 -> same | table (pairs): n 135 net -241.00 R -0.1854 -> same
L1 chk17    pdl:S      p20x3    fresh run.py: n  126 net   -2026.50 R  -0.3971 | events file: n  126 net   -2026.50 R  -0.3971 -> same | table (reaction): n 126 net -2026.50 R -0.3971 -> same
L1 chk18    vw:R       p20x1    fresh run.py: n  269 net    -344.50 R  -0.0317 | events file: n  269 net    -344.50 R  -0.0317 -> same | table (reaction): n 269 net -344.50 R -0.0317 -> same
L1 chk19    em2d:S     a08x3    fresh run.py: n  454 net    -846.00 R  -0.0740 | events file: n  454 net    -846.00 R  -0.0740 -> same | table (reaction): n 454 net -846.00 R -0.0740 -> same
reconciliation: 43 variants, 0 differ -> OK
```

The runner's own lines (its `win` is "net > 0", the tables' is "target reached"):

```
L1  LEV1 first tap after the open: the fade at one level (YT9)   phase is   bars 2019-06-02 18:00:00-04:00 -> 2022-12-30 16:59:00-05:00
base                   n   320  net      +482  R  +0.074  win  31.2  pf  1.09  dd     -652  p 0.2287  yrs+ 2/4  h1 +0.074 h2 +nan  | +172 -235 -48 +593 +0 +0 +0 +0   [3s]
nb1                    n   320  net     +1850  R  +0.141  win  30.9  pf  1.19  dd     -940  p 0.0775  yrs+ 4/4  h1 +0.141 h2 +nan  | +234 +547 +5 +1064 +0 +0 +0 +0   [0s]
nb2                    n   320  net       -75  R  -0.010  win  38.8  pf  0.98  dd     -736  p 0.5530  yrs+ 2/4  h1 -0.010 h2 +nan  | +67 -272 -44 +175 +0 +0 +0 +0   [0s]
p2                     n   260  net       +36  R  -0.030  win  28.5  pf  1.01  dd     -580  p 0.6102  yrs+ 2/4  h1 -0.030 h2 +nan  | -142 +60 +170 -50 +0 +0 +0 +0   [1s]
p2_nb1                 n   260  net     +1180  R  +0.037  win  28.1  pf  1.14  dd     -746  p 0.3761  yrs+ 3/4  h1 +0.037 h2 +nan  | -402 +502 +875 +205 +0 +0 +0 +0   [0s]
p2_nb2                 n   260  net      -226  R  -0.083  win  36.2  pf  0.94  dd     -547  p 0.8246  yrs+ 1/4  h1 -0.083 h2 +nan  | -110 -191 -48 +124 +0 +0 +0 +0   [0s]
p3                     n   159  net      -270  R  -0.079  win  27.0  pf  0.91  dd     -554  p 0.7251  yrs+ 0/4  h1 -0.079 h2 +nan  | -26 -118 -82 -44 +0 +0 +0 +0   [0s]
p3_nb1                 n   159  net      +978  R  +0.090  win  29.6  pf  1.19  dd     -598  p 0.2612  yrs+ 3/4  h1 +0.090 h2 +nan  | -160 +328 +70 +739 +0 +0 +0 +0   [0s]
p3_nb2                 n   159  net      -601  R  -0.159  win  33.3  pf  0.78  dd     -780  p 0.9242  yrs+ 0/4  h1 -0.159 h2 +nan  | -26 -374 -144 -58 +0 +0 +0 +0   [0s]
p4                     n   305  net       -80  R  -0.171  win  24.9  pf  0.98  dd     -894  p 0.9573  yrs+ 1/4  h1 -0.171 h2 +nan  | -127 -150 -366 +563 +0 +0 +0 +0   [1s]
p4_nb1                 n   305  net      +631  R  -0.070  win  25.9  pf  1.06  dd    -1450  p 0.7631  yrs+ 2/4  h1 -0.070 h2 +nan  | -292 +714 -764 +974 +0 +0 +0 +0   [0s]
p4_nb2                 n   305  net      -652  R  -0.205  win  32.1  pf  0.86  dd     -984  p 0.9949  yrs+ 1/4  h1 -0.205 h2 +nan  | -152 -214 -394 +109 +0 +0 +0 +0   [0s]
p5                     n  1090  net     -2906  R  -0.172  win  25.0  pf  0.85  dd    -3504  p 0.9996  yrs+ 0/4  h1 -0.172 h2 +nan  | -578 -1350 -844 -135 +0 +0 +0 +0   [1s]
p5_nb1                 n  1090  net     -4222  R  -0.126  win  25.9  pf  0.88  dd    -5142  p 0.9951  yrs+ 0/4  h1 -0.126 h2 +nan  | -506 -1666 -1224 -825 +0 +0 +0 +0   [1s]
p5_nb2                 n  1090  net     -3594  R  -0.192  win  32.6  pf  0.80  dd    -3859  p 1.0000  yrs+ 0/4  h1 -0.192 h2 +nan  | -516 -1494 -924 -660 +0 +0 +0 +0   [1s]
p6                     n     8  net      +128  R  +0.645  win  50.0  pf  2.66  dd      -49  p 0.1621  yrs+ 3/4  h1 +0.645 h2 +nan  | -16 +44 +60 +41 +0 +0 +0 +0   [0s]
p6_nb1                 n     8  net      +276  R  +0.882  win  62.5  pf  3.63  dd      -45  p 0.0748  yrs+ 3/4  h1 +0.882 h2 +nan  | +78 +202 -45 +41 +0 +0 +0 +0   [0s]
p6_nb2                 n     8  net      +147  R  +0.648  win  62.5  pf  4.00  dd      -49  p 0.1373  yrs+ 3/4  h1 +0.648 h2 +nan  | -16 +84 +39 +41 +0 +0 +0 +0   [0s]
p7                     n    11  net      +119  R  +0.612  win  45.5  pf  1.86  dd      -64  p 0.1854  yrs+ 3/4  h1 +0.612 h2 +nan  | +2 -8 +102 +24 +0 +0 +0 +0   [0s]
p7_nb1                 n    11  net      +200  R  +0.353  win  36.4  pf  1.72  dd     -280  p 0.2896  yrs+ 2/4  h1 +0.353 h2 +nan  | +116 -160 -119 +364 +0 +0 +0 +0   [0s]
p7_nb2                 n    11  net       +28  R  +0.172  win  45.5  pf  1.20  dd      -64  p 0.3881  yrs+ 2/4  h1 +0.172 h2 +nan  | -6 -28 +60 +1 +0 +0 +0 +0   [0s]
p8                     n    17  net      +172  R  +0.479  win  41.2  pf  1.69  dd     -106  p 0.1199  yrs+ 2/4  h1 +0.479 h2 +nan  | -28 +121 +123 -44 +0 +0 +0 +0   [0s]
p8_nb1                 n    17  net      +106  R  +0.097  win  29.4  pf  1.19  dd     -394  p 0.4100  yrs+ 2/4  h1 +0.097 h2 +nan  | +58 -4 -70 +122 +0 +0 +0 +0   [0s]
p8_nb2                 n    17  net      +156  R  +0.418  win  52.9  pf  1.78  dd      -48  p 0.1072  yrs+ 3/4  h1 +0.418 h2 +nan  | -2 +60 +67 +32 +0 +0 +0 +0   [0s]
chk1                   n    93  net      -449  R  -0.257  win  22.6  pf  0.75  dd     -588  p 0.9317  yrs+ 0/4  h1 -0.257 h2 +nan  | -29 -64 -38 -318 +0 +0 +0 +0   [0s]
chk2                   n    29  net      -122  R  -0.202  win  24.1  pf  0.77  dd     -246  p 0.7491  yrs+ 1/4  h1 -0.202 h2 +nan  | -6 +32 -138 -10 +0 +0 +0 +0   [0s]
chk3                   n   260  net       +36  R  -0.030  win  28.5  pf  1.01  dd     -580  p 0.6102  yrs+ 2/4  h1 -0.030 h2 +nan  | -142 +60 +170 -50 +0 +0 +0 +0   [0s]
chk4                   n   108  net      +212  R  -0.131  win  25.9  pf  1.12  dd     -368  p 0.7722  yrs+ 2/4  h1 -0.131 h2 +nan  | -182 +228 -103 +270 +0 +0 +0 +0   [0s]
chk5                   n   159  net      -270  R  -0.079  win  27.0  pf  0.91  dd     -554  p 0.7251  yrs+ 0/4  h1 -0.079 h2 +nan  | -26 -118 -82 -44 +0 +0 +0 +0   [0s]
chk6                   n   308  net     -2190  R  -0.339  win  20.8  pf  0.62  dd    -2257  p 1.0000  yrs+ 0/4  h1 -0.339 h2 +nan  | -81 -399 -448 -1262 +0 +0 +0 +0   [0s]
chk7                   n     5  net       -78  R  -0.424  win  20.0  pf  0.20  dd      -84  p 0.7373  yrs+ 1/4  h1 -0.424 h2 +nan  | -14 +20 -16 -67 +0 +0 +0 +0   [0s]
chk8                   n   115  net      -803  R  -0.289  win  21.7  pf  0.64  dd     -850  p 0.9698  yrs+ 1/4  h1 -0.289 h2 +nan  | -41 -336 +31 -457 +0 +0 +0 +0   [0s]
chk9                   n   289  net     -1334  R  -0.261  win  22.5  pf  0.76  dd    -1591  p 0.9967  yrs+ 1/4  h1 -0.261 h2 +nan  | -30 -824 -580 +99 +0 +0 +0 +0   [0s]
chk10                  n   481  net     -4229  R  -0.390  win  19.3  pf  0.56  dd    -4316  p 1.0000  yrs+ 0/4  h1 -0.390 h2 +nan  | -327 -1329 -880 -1694 +0 +0 +0 +0   [0s]
chk11                  n  1090  net     -2906  R  -0.172  win  25.0  pf  0.85  dd    -3504  p 0.9996  yrs+ 0/4  h1 -0.172 h2 +nan  | -578 -1350 -844 -135 +0 +0 +0 +0   [0s]
chk12                  n   413  net     -1616  R  -0.262  win  22.5  pf  0.79  dd    -1774  p 0.9993  yrs+ 0/4  h1 -0.262 h2 +nan  | -426 -202 -366 -621 +0 +0 +0 +0   [1s]
chk13                  n   168  net      -716  R  -0.249  win  23.2  pf  0.77  dd     -755  p 0.9761  yrs+ 1/4  h1 -0.249 h2 +nan  | -76 -389 +42 -294 +0 +0 +0 +0   [1s]
chk14                  n   141  net      -198  R  -0.118  win  26.2  pf  0.92  dd     -388  p 0.8087  yrs+ 1/4  h1 -0.118 h2 +nan  | -160 -56 +133 -115 +0 +0 +0 +0   [0s]
chk15                  n   246  net      -360  R  -0.054  win  28.0  pf  0.92  dd     -832  p 0.6859  yrs+ 1/4  h1 -0.054 h2 +nan  | -38 -226 -234 +138 +0 +0 +0 +0   [0s]
chk16                  n   135  net      -241  R  -0.185  win  24.4  pf  0.90  dd     -426  p 0.8991  yrs+ 2/4  h1 -0.185 h2 +nan  | -196 +38 +58 -141 +0 +0 +0 +0   [0s]
chk17                  n   126  net     -2026  R  -0.397  win  19.0  pf  0.54  dd    -2244  p 0.9987  yrs+ 0/4  h1 -0.397 h2 +nan  | -300 -465 -896 -366 +0 +0 +0 +0   [0s]
chk18                  n   269  net      -344  R  -0.032  win  51.7  pf  0.94  dd     -605  p 0.7011  yrs+ 1/4  h1 -0.032 h2 +nan  | -158 -58 +338 -467 +0 +0 +0 +0   [0s]
chk19                  n   454  net      -846  R  -0.074  win  26.0  pf  0.94  dd    -1998  p 0.8322  yrs+ 2/4  h1 -0.074 h2 +nan  | +31 -1178 -192 +493 +0 +0 +0 +0   [1s]
```

## 8. Look-ahead

`python3 tools/yt1/run.py L1 --check`: **PASS** (base, 16 sampled order bars).
`python3 tools/yt1/s_L1.py --check all --plain`: test A 43 of 43 PASS, test B 43 of 43 PASS, test C 31 of 43 PASS.

What each test is, and how it covers levels fixed at 09:30 and resting orders:

- A resting order's bar `i` is the last bar before its watch, so `core.causal_check` cuts the future right there
  (09:29 for the 09:30 levels, 09:44 for the opening range, 09:59 / 11:59 / 13:59 for the late expected-move
  blocks, every bar of the day for the VWAP orders) and mirrors everything after it. An order that used any bar of
  its own watch (a level that included the 09:30 bar, a profile or VWAP reaching past its bar, the day's later
  range, the outcome of the tap) would come out different. Freshness, the ATR, the placebo drop and the clusters
  are part of what is compared, because they decide which orders exist and at what price.
- The one thing an order reads after bar `i` is the open of bar `i + 1` (reading 1). **Test A** (what
  `run.py --check` runs) is `core.causal_check`, unchanged, on `orders(at_open=False)`: that open replaced by the
  last close before it, so every number compared comes from bars up to `i`. **Test B** is the same test on the real
  orders (`at_open=True`, what `trades()` trades) with that single open kept true in the mirrored future
  (`s_L1.check_true_open`, as `s_G9.check_true_open`). **Test C** is `core.causal_check`, unchanged, on the real
  orders: it mirrors that open too, so it fails wherever the open matters, and only there (B differs from C by that
  one number and passes).
- C fails for the expected-move variants (base, p5, chk11, chk19: the centre of a late block is the block's first
  open, so more than half of their orders move by a tick or two when the open is replaced), for chk9 (r100 is
  defined by the 09:30 open) and for p8 (one sampled day, 2020-03-12, a limit-down morning whose last bar before
  09:30 is 09:24: with the mirrored open the cluster is on the other side of the price). **For
  the base variant the form that passes `run.py --check` therefore differs from the traded orders in 1,884 of
  3,488 orders** (by the difference between a block's first open and the close before it); the traded orders
  pass B.
- The levels themselves are tested apart from the orders in section 3 (each cut at its own `t_set`, e.g. the Asia
  high at 01:59, not only at 09:29).

| variant | selection | trade | set | orders | first watched bars | real orders that differ from the at_open=False form | A | B (sampled bars) | C plain, real orders |
|---|---|---|---|---|---|---|---|---|---|
| base | em2u:R | a04x3 | fresh | 3488 | 09:30..14:00 | 1884 | PASS | PASS (16) | FAIL |
| nb1 | em2u:R | a08x3 | fresh | 3488 | 09:30..14:00 | 1884 | PASS | PASS (16) | FAIL |
| nb2 | em2u:R | a04x2 | fresh | 3488 | 09:30..14:00 | 1884 | PASS | PASS (16) | FAIL |
| p2 | onh:R | a04x3 | fresh | 470 | 09:30..09:30 | 0 | PASS | PASS (16) | PASS |
| p2_nb1 | onh:R | a08x3 | fresh | 470 | 09:30..09:30 | 0 | PASS | PASS (16) | PASS |
| p2_nb2 | onh:R | a04x2 | fresh | 470 | 09:30..09:30 | 0 | PASS | PASS (16) | PASS |
| p3 | ldh:R | a04x3 | fresh | 305 | 09:30..09:30 | 1 | PASS | PASS (16) | PASS |
| p3_nb1 | ldh:R | a08x3 | fresh | 305 | 09:30..09:30 | 1 | PASS | PASS (16) | PASS |
| p3_nb2 | ldh:R | a04x2 | fresh | 305 | 09:30..09:30 | 1 | PASS | PASS (16) | PASS |
| p4 | vw:S | a04x3 | fresh | 37825 | 09:30..15:00 | 333 | PASS | PASS (16) | PASS |
| p4_nb1 | vw:S | a08x3 | fresh | 37825 | 09:30..15:00 | 333 | PASS | PASS (16) | PASS |
| p4_nb2 | vw:S | a04x2 | fresh | 37825 | 09:30..15:00 | 333 | PASS | PASS (16) | PASS |
| p5 | em1u:R | a04x3 | fresh | 3410 | 09:30..14:00 | 1883 | PASS | PASS (16) | FAIL |
| p5_nb1 | em1u:R | a08x3 | fresh | 3410 | 09:30..14:00 | 1883 | PASS | PASS (16) | FAIL |
| p5_nb2 | em1u:R | a04x2 | fresh | 3410 | 09:30..14:00 | 1883 | PASS | PASS (16) | FAIL |
| p6 | o00+pdh | a04x3 | fresh | 19 | 09:30..09:30 | 1 | PASS | PASS (16) | PASS |
| p6_nb1 | o00+pdh | a08x3 | fresh | 19 | 09:30..09:30 | 1 | PASS | PASS (16) | PASS |
| p6_nb2 | o00+pdh | a04x2 | fresh | 19 | 09:30..09:30 | 1 | PASS | PASS (16) | PASS |
| p7 | ldh+o0830 | a04x3 | fresh | 15 | 09:30..09:30 | 0 | PASS | PASS (14) | PASS |
| p7_nb1 | ldh+o0830 | a08x3 | fresh | 15 | 09:30..09:30 | 0 | PASS | PASS (14) | PASS |
| p7_nb2 | ldh+o0830 | a04x2 | fresh | 15 | 09:30..09:30 | 0 | PASS | PASS (14) | PASS |
| p8 | o0830+prh | a04x3 | fresh | 24 | 09:30..09:30 | 2 | PASS | PASS (16) | FAIL |
| p8_nb1 | o0830+prh | a08x3 | fresh | 24 | 09:30..09:30 | 2 | PASS | PASS (16) | FAIL |
| p8_nb2 | o0830+prh | a04x2 | fresh | 24 | 09:30..09:30 | 2 | PASS | PASS (16) | FAIL |
| chk1 | pdh:R | a04x3 | fresh | 400 | 09:30..09:30 | 0 | PASS | PASS (16) | PASS |
| chk2 | pwl:S | a04x3 | fresh | 607 | 09:30..09:30 | 0 | PASS | PASS (16) | PASS |
| chk3 | onh:R | a04x3 | fresh | 470 | 09:30..09:30 | 0 | PASS | PASS (16) | PASS |
| chk4 | asl:S | a04x3 | fresh | 254 | 09:30..09:30 | 1 | PASS | PASS (16) | PASS |
| chk5 | ldh:R | a04x3 | fresh | 305 | 09:30..09:30 | 1 | PASS | PASS (16) | PASS |
| chk6 | prl:S | a04x3 | fresh | 405 | 09:30..09:30 | 8 | PASS | PASS (16) | PASS |
| chk7 | o0830:R | a04x3 | fresh | 8 | 09:30..09:30 | 0 | PASS | PASS (7) | PASS |
| chk8 | poc:S | a04x3 | fresh | 159 | 09:30..09:30 | 7 | PASS | PASS (16) | PASS |
| chk9 | r100:R | a04x3 | fresh | 541 | 09:30..09:30 | 6 | PASS | PASS (16) | FAIL |
| chk10 | orl:S | a04x3 | fresh | 717 | 09:45..09:49 | 0 | PASS | PASS (16) | PASS |
| chk11 | em1u:R | a04x3 | fresh | 3410 | 09:30..14:00 | 1883 | PASS | PASS (16) | FAIL |
| chk12 | vw1d:S | a04x3 | fresh | 87475 | 09:30..15:00 | 1 | PASS | PASS (16) | PASS |
| chk13 | pdh~:R | a04x3 | fresh | 782 | 09:30..09:30 | 0 | PASS | PASS (16) | PASS |
| chk14 | ash:R | a04x3 | any | 283 | 09:30..09:30 | 0 | PASS | PASS (16) | PASS |
| chk15 | onl:S | brk_a04 | fresh | 497 | 09:30..09:30 | 3 | PASS | PASS (16) | PASS |
| chk16 | ash+onh | a04x3 | fresh | 272 | 09:30..09:30 | 1 | PASS | PASS (16) | PASS |
| chk17 | pdl:S | p20x3 | fresh | 545 | 09:30..09:30 | 0 | PASS | PASS (16) | PASS |
| chk18 | vw:R | p20x1 | fresh | 24621 | 09:30..15:00 | 1 | PASS | PASS (16) | PASS |
| chk19 | em2d:S | a08x3 | fresh | 3479 | 09:30..14:00 | 1874 | PASS | PASS (16) | FAIL |

## 9. Coding errors found and fixed

- Before any table was built, the level look-ahead test failed for placebos of the previous-day and previous-week
  levels: their `t_set` was the parent's (15:59), but the day's ATR is only fixed at 17:00. `t_set` of a placebo is
  now the later of the two. No value changed.
- `lev1_verify.py` (the hand-check printer, not the study code) assumed an 08:00 bar exists; fixed for 2020-03-09.
- Nothing was changed after the first table was printed: the tables, the selection file and the runner's output
  are from one build (re-running `lev1_tables.py --phase is` rewrites byte-identical files).

Harness: no bug found. Two behaviours a reader should know: `core.simulate` returns no trade when a limit order's
fill (a gap open) is at or through its own stop (one event, section 5); `ind.session_vwap`'s sd comes from a
difference of large numbers and is noisy below about 1e-4 on the first bars of a session (irrelevant from 09:30).

## 10. Full phase (not run here)

`lev1_events.py --phase full` and `lev1_tables.py --phase full` refuse to run in the lab (no bars after 2022-12-31).
The full phase was dry-tested on a made-up split inside the in-sample events (`lev1_tables.py --phase is
--dry-split 2021-07-01 --dry-out <scratch>` then `--phase full` with the same arguments): the in-sample tables
rebuilt from the whole file equalled the frozen ones (5 of 5 identical), the selection rule gave the frozen picks,
the pick verdicts, the Spearman line and the pooled comparison for both periods printed. The scratch directory was
deleted; the study folder's files were byte-identical before and after. `s_L1.py --recon --phase full` reads the
`_full` tables.

## 11. Run times (2 cores, nothing else running)

Levels 3 s; events 17 s with 2 processes (39 s with 1; identical frames); tables 5 s; `run.py L1 --phase is` 16 s for
43 variants; `--recon` 2 s; unit checks 7 s; level look-ahead test 77 s; `run.py L1 --check` 18 s; tests A + B + C
about 65 s a variant (47 minutes of CPU for the 43, run two at a time).

## 12. Printed in-sample output (`python3 tools/yt1/lev1_tables.py --phase is`)

```
LEV1 tables   phase is   events file LEV1_events.parquet (57653 rows)   2019-06-21 -> 2022-12-30   study days 884

IN SAMPLE: reaction by level code x side, fresh events, sorted by the headline (a04x3) mean R (win in %, pl_ = placebo, dwin in points, pwin = two-proportion p)
 code side  watched  events  n_a04x3 win_a04x3 R_a04x3 net_a04x3  n_p20x3 win_p20x3 R_p20x3  pl_events pl_win_a04x3 pl_R_a04x3 dwin_a04x3 dR_a04x3 pwin_a04x3 pl_win_p20x3 pl_R_p20x3 R_brk_a04 R_brk_p20
  pdc    R        2       2        2      50.0  +0.849       +43        2     100.0  +2.889         47         25.5     -0.128      +24.5   +0.977      0.443         19.1     -0.102    -1.109    -1.062
  o18    S       11       2        2      50.0  +0.698        -4        2       0.0  -1.062         55         10.9     -0.718      +39.1   +1.416      0.098         20.0     -0.070    +0.767    +0.914
 em1d    R       46      24       24      41.7  +0.473      +216       24      41.7  +0.681          0          NaN        NaN        NaN      NaN        NaN          NaN        NaN    -0.498    -0.359
 em2d    R       20      11       11      36.4  +0.262       +47       11      18.2  -0.343          0          NaN        NaN        NaN      NaN        NaN          NaN        NaN    -0.794    -0.343
  vah    S       61      44       44      31.8  +0.105      +154       44      27.3  +0.055         41         17.1     -0.461      +14.7   +0.566      0.115         24.4     -0.083    +0.019    +0.022
 em2u    R     3488     320      320      31.2  +0.074      +482      320      27.5  +0.094          0          NaN        NaN        NaN      NaN        NaN          NaN        NaN    -0.144    -0.063
 vw1d    R      109     108      108      28.7  -0.011       +84      108      23.1  -0.065          0          NaN        NaN        NaN      NaN        NaN          NaN        NaN    -0.197    -0.131
  onh    R      470     260      260      28.5  -0.030       +36      260      23.5  -0.049        351         24.8     -0.162       +3.7   +0.132      0.308         23.1     -0.044    -0.011    +0.061
  pdm    S      225      60       60      26.7  -0.060      -116       60      18.3  -0.137        116         24.1     -0.201       +2.5   +0.141      0.713         28.4     +0.159    -0.142    -0.127
  ldh    R      305     159      159      27.0  -0.079      -270      159      22.6  -0.058        279         21.1     -0.305       +5.9   +0.225      0.160         21.9     -0.119    -0.076    +0.117
  poc    R      152     104      104      26.9  -0.101       -10      104      21.2  -0.113        118         28.8     -0.018       -1.9   -0.083      0.754         29.7     +0.190    -0.069    -0.077
  val    R       53      42       42      26.2  -0.129       -61       42      14.3  -0.435         51         23.5     -0.216       +2.7   +0.087      0.767         33.3     +0.255    -0.044    -0.039
  asl    S      254     108      108      25.9  -0.131      +212      108      24.1  +0.048        185         29.7     +0.018       -3.8   -0.150      0.486         25.4     +0.112    -0.320    -0.074
  pdm    R      120      40       40      25.0  -0.158      -109       40      17.5  -0.283         71         22.5     -0.212       +2.5   +0.054      0.768         23.9     -0.075    -0.447    -0.182
   vw    S      385     305      305      24.9  -0.171       -80      305      22.0  -0.034          0          NaN        NaN        NaN      NaN        NaN          NaN        NaN    -0.201    -0.019
 em1u    R     3410    1090     1090      24.7  -0.172     -2906     1090      19.8  -0.132          0          NaN        NaN        NaN      NaN        NaN          NaN        NaN    -0.160    -0.008
  prh    R      425     325      325      24.9  -0.173     -1014      325      23.4  -0.071        307         28.0     -0.040       -3.1   -0.133      0.379         23.8     -0.006    +0.008    +0.100
  vah    R      316     197      197      24.9  -0.178      -474      197      19.3  -0.219        247         20.2     -0.340       +4.6   +0.162      0.244         14.2     -0.388    -0.125    -0.127
  val    S      346     206      206      24.8  -0.180     -1091      206      21.4  -0.082        217         26.7     -0.104       -2.0   -0.076      0.643         25.3     +0.018    -0.157    +0.057
 em2d    S     3479     454      453      24.5  -0.194     -1509      454      22.2  -0.061          0          NaN        NaN        NaN      NaN        NaN          NaN        NaN    -0.191    -0.089
 em1d    S     3393    1160     1160      24.2  -0.197     -4536     1160      19.4  -0.152          0          NaN        NaN        NaN      NaN        NaN          NaN        NaN    -0.091    -0.041
  pwl    S      607      29       29      24.1  -0.202      -122       29      24.1  +0.053         51         23.5     -0.231       +0.6   +0.029      0.951         21.6     -0.154    +0.473    +0.246
 vw1u    R      542     394      394      23.6  -0.219     -1487      394      19.5  -0.149          0          NaN        NaN        NaN      NaN        NaN          NaN        NaN    -0.095    +0.001
  onl    S      497     246      246      23.2  -0.237      -627      246      23.2  -0.012        344         28.2     -0.041       -5.0   -0.196      0.170         26.2     +0.075    -0.054    -0.118
  ash    R      172      74       74      23.0  -0.249      -195       74      25.7  +0.099        155         25.2     -0.148       -2.2   -0.101      0.719         22.6     -0.012    -0.131    -0.023
  pdh    R      400      93       93      22.6  -0.257      -449       93      21.5  -0.108        168         22.0     -0.249       +0.6   -0.008      0.917         21.4     -0.029    +0.076    -0.035
 r100    R      541     289      289      22.1  -0.261     -1334      289      25.6  +0.023        372         22.8     -0.227       -0.7   -0.034      0.830         21.2     -0.137    -0.031    +0.248
 vw1d    S      616     413      413      22.5  -0.262     -1616      413      21.1  -0.093          0          NaN        NaN        NaN      NaN        NaN          NaN        NaN    +0.036    +0.057
 vw2u    R      805     440      440      22.3  -0.268     -2960      440      19.8  -0.209          0          NaN        NaN        NaN      NaN        NaN          NaN        NaN    -0.002    +0.050
  orh    R      694     502      502      22.1  -0.274     -2689      502      19.3  -0.169        276         20.3     -0.349       +1.8   +0.075      0.554         18.1     -0.250    -0.069    -0.026
 vw2d    S      816     443      443      22.1  -0.275     -1972      443      20.5  -0.138          0          NaN        NaN        NaN      NaN        NaN          NaN        NaN    +0.028    +0.064
   vw    R      315     269      269      21.9  -0.277     -1020      269      24.9  +0.018          0          NaN        NaN        NaN      NaN        NaN          NaN        NaN    -0.281    -0.106
 vw1u    S      151     147      147      21.8  -0.278     -1011      147      17.0  -0.238          0          NaN        NaN        NaN      NaN        NaN          NaN        NaN    -0.065    +0.061
  poc    S      159     115      115      21.7  -0.289      -803      115      19.1  -0.229        115         25.2     -0.154       -3.5   -0.135      0.534         25.2     +0.072    +0.118    +0.175
  pdl    S      545     126      126      21.4  -0.315      -750      126      13.5  -0.397        206         30.6     +0.043       -9.2   -0.359      0.069         22.3     -0.021    +0.054    +0.067
  prl    S      405     308      308      20.5  -0.339     -2190      308      17.9  -0.229        254         26.0     -0.127       -5.5   -0.212      0.121         27.6     +0.100    +0.094    -0.010
o0830    S        6       5        5      20.0  -0.343       +16        5      20.0  +0.165         89         33.7     +0.188      -13.7   -0.530      0.526         23.6     +0.004    -1.132    -0.141
  ldl    S      314     154      154      20.1  -0.364      -819      154      21.4  -0.002        249         25.7     -0.139       -5.6   -0.225      0.200         22.9     -0.087    +0.008    -0.073
 em2u    S       10       5        5      20.0  -0.383       -66        5       0.0  -0.785          0          NaN        NaN        NaN      NaN        NaN          NaN        NaN    +0.376    -0.272
  orl    S      717     481      481      19.1  -0.390     -4229      481      17.7  -0.209        253         23.7     -0.212       -4.6   -0.178      0.145         24.1     -0.048    +0.027    +0.012
 r100    S      545     286      286      18.5  -0.398     -1993      286      20.3  -0.179        364         25.8     -0.124       -7.3   -0.274      0.027         25.8     +0.026    +0.052    +0.084
 em1u    S       48      28       28      17.9  -0.415      -383       28      25.0  -0.074          0          NaN        NaN        NaN      NaN        NaN          NaN        NaN    -0.416    -0.215
o0830    R        8       5        5      20.0  -0.424       -78        5       0.0  -0.457        110         20.9     -0.318       -0.9   -0.107      0.961         20.0     -0.203    +0.382    +0.519
 vw2u    S        6       6        6      16.7  -0.455       -62        6       0.0  -1.079          0          NaN        NaN        NaN      NaN        NaN          NaN        NaN    +0.234    +0.261
  pwh    R      477      27       27      14.8  -0.596      -233       27      11.1  -0.360         50         16.0     -0.545       -1.2   -0.051      0.891         12.0     -0.444    +0.402    +0.316
  onl    R        1       1        1       0.0  -1.062       -42        1       0.0  -1.062         20         25.0     -0.165      -25.0   -0.897      0.567         25.0     -0.074    +2.888    +2.889
  asl    R        1       1        1       0.0  -1.062       -42        1       0.0  -1.062          7         28.6     +0.002      -28.6   -1.064      0.537         42.9     +0.631    +2.888    +2.889
  ldl    R        1       1        1       0.0  -1.062       -42        1       0.0  -1.062          9         33.3     +0.203      -33.3   -1.266      0.490         33.3     +0.255    +2.888    +2.889
  prl    R        1       1        1       0.0  -1.062       -42        1       0.0  -1.062         47         27.7     -0.020      -27.7   -1.042      0.538         23.4     -0.072    +2.888    +2.889
  o00    S        3       1        1       0.0  -1.139       -20        1       0.0  -1.062         44         18.2     -0.443      -18.2   -0.696      0.638         20.5     -0.108    -1.139    -1.062
 vw2d    R        5       5        5       0.0  -1.156      -119        5       0.0  -0.531          0          NaN        NaN        NaN      NaN        NaN          NaN        NaN    +1.185    +1.309
  o18    R        8       2        2       0.0  -1.286       -23        2      50.0  +1.568         28         21.4     -0.297      -21.4   -0.989      0.464         17.9     -0.159    -1.286    -0.728
  pdc    S        2       0        0       NaN     NaN        +0        0       NaN     NaN         61         19.7     -0.376        NaN      NaN        NaN         23.0     -0.125       NaN       NaN
  o00    R        1       0        0       NaN     NaN        +0        0       NaN     NaN         43         30.2     +0.057        NaN      NaN        NaN         23.3     +0.003       NaN       NaN

IN SAMPLE: draw, % of watched level-days tapped by 15:00 by distance from the 09:30 open (x ATR): level / its placebo (level-days of the level)
  pdh      <0.10:  82.8 /  82.6 ( 87)   0.10-0.25:  59.2 /  61.7 (211)   0.25-0.50:  40.1 /  36.8 (242)   0.50-1.00:  13.1 /  13.1 (191)
  pdl      <0.10:  90.6 /  87.0 ( 53)   0.10-0.25:  73.5 /  68.0 (147)   0.25-0.50:  35.5 /  38.6 (220)   0.50-1.00:  16.8 /  15.4 (310)
  pdc      <0.10:  85.4 /  92.0 (130)   0.10-0.25:  66.5 /  67.7 (263)   0.25-0.50:  44.6 /  41.9 (258)   0.50-1.00:  25.4 /  24.5 (122)
  pdm      <0.10:  88.5 /  94.7 ( 87)   0.10-0.25:  66.5 /  64.4 (227)   0.25-0.50:  47.4 /  35.2 (266)   0.50-1.00:  20.9 /  17.5 (196)
  pwh      <0.10:  83.8 /  57.1 ( 37)   0.10-0.25:  52.3 /  52.2 ( 86)   0.25-0.50:  34.6 /  31.7 (156)   0.50-1.00:  10.9 /   7.9 (201)
  pwl      <0.10:  93.3 /  88.9 ( 30)   0.10-0.25:  66.7 /  80.0 ( 42)   0.25-0.50:  38.2 /  37.9 ( 68)   0.50-1.00:  19.8 /  18.9 (131)
  onh      <0.10:  84.4 /  75.9 (147)   0.10-0.25:  65.8 /  64.5 (322)   0.25-0.50:  41.4 /  38.8 (232)   0.50-1.00:  15.1 /  20.0 ( 93)
  onl      <0.10:  88.0 /  88.6 (100)   0.10-0.25:  64.5 /  65.1 (301)   0.25-0.50:  40.0 /  41.8 (290)   0.50-1.00:  26.8 /  23.3 (138)
  ash      <0.10:  81.8 /  83.3 (137)   0.10-0.25:  67.1 /  59.0 (298)   0.25-0.50:  46.1 /  40.1 (219)   0.50-1.00:  22.0 /  21.5 ( 91)
  asl      <0.10:  86.9 /  80.8 (122)   0.10-0.25:  67.2 /  68.6 (250)   0.25-0.50:  39.6 /  41.8 (278)   0.50-1.00:  27.0 /  22.7 (137)
  ldh      <0.10:  85.3 /  82.6 (143)   0.10-0.25:  66.4 /  66.0 (339)   0.25-0.50:  43.8 /  39.8 (192)   0.50-1.00:  17.2 /  21.6 ( 64)
  ldl      <0.10:  81.8 /  88.6 (132)   0.10-0.25:  61.4 /  64.5 (347)   0.25-0.50:  45.1 /  42.5 (235)   0.50-1.00:  31.0 /  25.5 ( 71)
  prh      <0.10:  84.8 /  82.0 (310)   0.10-0.25:  72.5 /  65.0 (309)   0.25-0.50:  52.5 /  47.5 ( 61)   0.50-1.00:  15.8 /  35.0 ( 19)
  prl      <0.10:  84.0 /  92.2 (288)   0.10-0.25:  71.6 /  66.9 (310)   0.25-0.50:  53.4 /  49.2 ( 73)   0.50-1.00:  28.6 /  33.3 ( 14)
  o18      <0.10:  84.4 /  78.4 (154)   0.10-0.25:  66.9 /  68.0 (263)   0.25-0.50:  41.7 /  41.7 (240)   0.50-1.00:  23.7 /  19.8 (114)
  o00      <0.10:  83.8 /  94.3 (160)   0.10-0.25:  66.7 /  65.3 (297)   0.25-0.50:  49.1 /  48.8 (214)   0.50-1.00:  28.9 /  17.9 ( 76)
  o0830    <0.10:  81.7 /  85.9 (279)   0.10-0.25:  71.0 /  68.7 (231)   0.25-0.50:  58.8 /  48.5 ( 51)   0.50-1.00:  47.1 /  50.0 ( 17)
  vah      <0.10:  81.6 /  75.5 (223)   0.10-0.25:  65.0 /  61.5 (320)   0.25-0.50:  54.7 /  43.8 (128)   0.50-1.00:  28.3 /  29.2 ( 53)
  poc      <0.10:  84.6 /  86.4 (195)   0.10-0.25:  69.0 /  72.4 (242)   0.25-0.50:  51.7 /  55.1 (118)   0.50-1.00:  32.5 /  25.0 ( 40)
  val      <0.10:  83.1 /  75.8 (195)   0.10-0.25:  63.9 /  66.4 (310)   0.25-0.50:  46.7 /  45.4 (180)   0.50-1.00:  32.7 /  20.8 ( 55)
  r100     <0.10:  85.7 /  91.6 (293)   0.10-0.25:  68.2 /  63.8 (669)   0.25-0.50:  39.7 /  37.5 (458)   0.50-1.00:  16.1 /  15.4 (155)
  orh      <0.10:  65.2 /  62.5 (351)   0.10-0.25:  78.0 /  52.1 (264)   0.25-0.50:  84.1 /  61.5 ( 69)   0.50-1.00:  90.0 /  78.8 ( 10)
  orl      <0.10:  62.2 /  73.1 (360)   0.10-0.25:  69.3 /  50.2 (267)   0.25-0.50:  81.7 /  62.0 ( 82)   0.50-1.00:  62.5 /  70.6 (  8)

IN SAMPLE: pairs sharing a cluster on >= 60 in-sample days, and by number of levels in the cluster (fresh events)
      pair  cluster_days  watched  events  n_a04x3 win_a04x3 R_a04x3 net_a04x3 win_p20x3 R_p20x3 R_a08x3 R_a04x2 R_brk_a04
   o00+pdh            76       19       8        8      37.5  +0.645      +128      37.5  +1.065  +0.882  +0.648    -1.147
 ldh+o0830            88       15      11       11      45.5  +0.612      +119      18.2  -0.185  +0.353  +0.172    -0.797
 o0830+prh            93       24      17       17      41.2  +0.479      +172      35.3  +0.333  +0.097  +0.418    -0.673
   asl+pdc           141       37      17       17      41.2  +0.442      +172      23.5  +0.195  -0.008  +0.388    -0.693
   onh+pdh            77       39      21       21      38.1  +0.354      +128      19.0  +0.057  +0.265  -0.016    +0.187
 o0830+poc           141       59      47       47      38.3  +0.339      +315      29.8  +0.197  +0.181  +0.214    -0.077
   ldh+pdh            68       34      24       24      37.5  +0.334      +114      25.0  +0.246  +0.595  -0.030    -0.020
   onl+pdc            90       33      16       16      37.5  +0.330      +146      31.2  +0.521  +0.316  +0.331    -0.642
  onl+r100            91       75      50       50      36.0  +0.301      +504      40.0  +0.519  +0.054  +0.125    +0.063
  asl+r100            93       55      33       33      36.4  +0.289      +274      33.3  +0.255  -0.191  +0.197    -0.182
   asl+pdm            73       26      17       17      35.3  +0.247      +122      29.4  +0.246  -0.159  +0.248    -0.673
   ldh+prh           146       93      77       77      35.1  +0.224      +221      15.6  -0.387  -0.098  +0.034    -0.188
   ldl+pdc            80       27      11       11      36.4  +0.219       +41       0.0  -0.556  -0.873  +0.388    -0.828
o0830+r100           114       44      33       33      33.3  +0.190      +168      36.4  +0.441  +0.140  -0.046    -0.284
  poc+r100           100       64      44       44      31.8  +0.188      +310      34.1  +0.349  +0.074  +0.006    +0.124
   asl+o18           162       45      23       23      34.8  +0.167       +41      13.0  -0.180  -0.303  +0.471    -0.832
   ash+prh           102       62      51       51      33.3  +0.160      +234      17.6  -0.302  -0.286  +0.064    -0.458
 o0830+val            77       27      18       18      33.3  +0.157       +86      38.9  +0.475  +0.242  +0.150    -0.500
   ldl+o00           139       62      39       39      33.3  +0.144      +168      20.5  +0.051  -0.319  +0.494    -0.551
   poc+prh            75       43      34       34      32.4  +0.134       +96      23.5  -0.047  +0.163  +0.074    +0.141
   onh+vah           194      152      89       89      32.6  +0.125      +288      22.5  -0.028  -0.111  -0.029    -0.444
   onh+prh           267      219     168      168      32.1  +0.109      +487      21.4  -0.140  -0.104  +0.004    -0.031
   ldh+onh           416      325     195      195      31.8  +0.102      +455      18.5  -0.240  -0.108  -0.029    -0.175
   ldl+o18           105       48      28       28      32.1  +0.094       -22      10.7  -0.352  -0.567  +0.408    -0.598
   ldh+vah           287      181     114      114      31.6  +0.080      +182      20.2  -0.163  -0.052  -0.099    -0.337
   ash+o00            72       25      16       16      31.2  +0.060        +5      25.0  +0.133  -0.056  -0.066    -0.675
  pdh+r100            93       53      32       32      28.1  +0.057       +50      15.6  -0.198  -0.328  -0.125    +0.309
   prh+vah           207      145     114      114      30.7  +0.051       +82      21.9  -0.065  +0.001  -0.093    -0.027
   ash+pdh            83       24      10       10      30.0  +0.040       +48      20.0  +0.098  +0.146  -0.254    -0.744
   o00+pdc           112       23      13       13      30.8  +0.029       +21       7.7  -0.520  -0.782  +0.169    -0.576
   o00+poc           241      110      70       70      28.6  +0.017      +351      28.6  +0.150  -0.075  +0.110    -0.140
   o18+val           109       48      27       27      29.6  +0.016       -19       7.4  -0.700  -0.634  +0.271    -0.707
   pdh+vah            67       32      17       17      29.4  +0.016        -0      23.5  -0.023  -0.369  -0.271    -0.044
   ash+ldh           165       79      52       52      28.8  -0.005       +36      17.3  -0.241  -0.074  -0.118    -0.383
   o18+pdh           100       29      17       17      29.4  -0.008        -5      11.8  -0.299  -0.461  -0.293    -0.462
  o00+r100           117       56      38       38      26.3  -0.022       +42      23.7  +0.204  +0.075  +0.102    -0.298
 o0830+o18            68       11       7        7      28.6  -0.034        +4       0.0  -1.062  -1.076  +0.102    -0.033
  r100+val           113       75      54       54      27.8  -0.036       -18      25.9  +0.143  +0.085  +0.017    -0.035
   ash+vah           197      109      64       64      28.1  -0.043       -76      23.4  -0.064  +0.059  -0.089    -0.592
   o00+vah           113       58      42       42      28.6  -0.043      -122      19.0  -0.168  +0.126  -0.183    -0.412
 o0830+pdc            63        9       7        7      28.6  -0.045        -8       0.0  -1.062  -0.516  +0.093    -0.041
   ldh+pdc            77       29      18       18      27.8  -0.058       -30      11.1  -0.300  -0.178  -0.327    -0.272
   ldl+val           280      172     113      113      27.4  -0.073      -176      24.8  +0.107  -0.042  +0.074    -0.311
   ldh+o00            96       46      29       29      27.6  -0.074      -118      17.2  -0.259  +0.107  -0.341    -0.346
   onl+val           142      105      70       70      27.1  -0.075      -146      28.6  +0.177  -0.106  +0.038    -0.187
 o0830+vah           117       42      33       33      27.3  -0.091      -116       9.1  -0.650  -0.242  -0.091    +0.156
   o00+pdm            63       14      11       11      27.3  -0.101       +12      18.2  +0.132  +0.227  +0.695    -0.107
   pdc+val            86       33      22       22      27.3  -0.107      -112      18.2  -0.343  -0.189  -0.103    -0.274
   asl+val           161       77      46       46      26.1  -0.126      -160      17.4  -0.287  -0.472  +0.320    -0.125
   o00+o18           141       40      23       23      26.1  -0.128       -60      13.0  -0.412  -0.902  +0.121    -0.300
   asl+onl           486      340     158      158      25.9  -0.131       +21      22.2  -0.023  -0.173  -0.069    -0.285
   onh+pdc            62       15       8        8      25.0  -0.133       -31      12.5  -0.106  -0.031  -0.378    -0.131
   o00+val           148       61      43       43      25.6  -0.152       -93      23.3  +0.136  -0.221  +0.145    -0.332
  prh+r100           126       91      69       69      24.6  -0.155      -435      15.9  -0.421  -0.408  -0.183    +0.085
  pdl+r100            63       41      24       24      25.0  -0.155       -24      29.2  +0.320  +0.082  -0.400    -0.154
  r100+vah           125       86      62       62      24.2  -0.173      -285      17.7  -0.338  -0.337  -0.314    -0.315
   ash+poc            63       26      20       20      25.0  -0.177       -88      25.0  +0.010  +0.133  -0.130    -0.174
   ash+onh           395      272     135      135      24.4  -0.185      -241      23.0  -0.016  -0.049  -0.229    -0.267
   o18+onl           105       32      12       12      25.0  -0.193       -98       8.3  -0.186  -0.553  +0.791    -0.826
 o0830+prl            80       18      12       12      25.0  -0.207       -26      25.0  +0.253  +0.218  -0.206    -0.524
  pdm+r100            84       57      39       39      23.1  -0.219      -193      23.1  +0.070  -0.224  -0.145    -0.018
  ldh+r100           113       73      57       57      22.8  -0.231      -354      12.3  -0.529  -0.601  -0.350    -0.044
 o00+o0830            80       21      17       17      23.5  -0.241       -68      23.5  -0.132  -0.156  -0.131    -0.011
  ldl+r100           118       82      53       53      22.6  -0.242      -256      24.5  +0.028  -0.129  -0.132    +0.200
  prl+r100           104       75      59       59      22.0  -0.248      -406      27.1  +0.103  -0.264  -0.217    +0.020
 ash+o0830            77       17      13       13      23.1  -0.256       -17      23.1  -0.150  -0.171  -0.036    +0.038
   asl+ldl           129       62      39       39      23.1  -0.257      -214      15.4  -0.286  -0.610  +0.046    -0.151
   onl+prl           222      179     127      127      22.0  -0.273      -811      22.8  -0.134  -0.139  -0.257    +0.126
   pdc+pdh           107       27      18       18      22.2  -0.278       -48      16.7  -0.027  -0.178  -0.332    -0.062
   ldl+pdm            62       28      22       22      22.7  -0.282      -238      18.2  -0.044  -0.150  +0.167    -0.091
   prl+val           170      122      95       95      22.1  -0.284      -646      23.2  -0.068  -0.083  -0.282    +0.003
   o00+prh            65       34      27       27      22.2  -0.285      -180      18.5  -0.236  +0.117  -0.288    -0.284
   pdc+vah            88       38      23       23      21.7  -0.309      -260       8.7  -0.642  -0.224  -0.392    +0.047
   o18+pdc           316       66      41       41      22.0  -0.320      -392       2.4  -0.681  -0.486  -0.319    -0.310
   pdc+prl            62       31      24       24      20.8  -0.337      -192      12.5  -0.484  -0.418  -0.178    -0.334
  pdc+r100           118       51      34       34      20.6  -0.351      -336       8.8  -0.655  -0.536  -0.297    +0.226
   ldl+onl           345      265     152      152      19.7  -0.370     -1133      20.4  -0.057  -0.083  -0.275    -0.013
   o18+prh            67       32      26       26      19.2  -0.375      -244      19.2  -0.267  -0.264  -0.561    -0.067
   pdc+pdm            61       12      10       10      20.0  -0.408      -110       0.0  -0.405  -0.205  -0.014    -0.402
   ldl+prl           126       80      59       59      18.6  -0.413      -666      16.9  -0.313  -0.212  -0.145    -0.082
   o18+poc           112       35      22       22      18.2  -0.414      -232      18.2  -0.343  -0.524  -0.199    +0.480
  onh+r100            96       73      56       56      17.9  -0.414      -545      10.7  -0.578  -0.646  -0.328    +0.074
   o00+prl            80       43      32       32      18.8  -0.415      -304      18.8  -0.124  -0.360  -0.047    -0.291
   o18+prl            72       36      27       27      18.5  -0.458      -264       3.7  -0.681  -0.651  -0.201    -0.316
   asl+prl            69       40      29       29      17.2  -0.476      -384      13.8  -0.418  -0.395  -0.137    -0.198
  ash+r100           102       61      45       45      15.6  -0.511      -586      11.1  -0.490  -0.360  -0.404    -0.424
   o18+pdm            69       18      12       12      16.7  -0.538      -146       0.0  -0.514  -0.354  -0.208    -0.209
   pdc+prh            62       24      20       20      15.0  -0.553      -384       5.0  -0.777  -0.670  -0.697    -0.146
   ldh+o18            86       36      20       20      15.0  -0.560      -336       5.0  -0.610  -0.304  -0.703    -0.161
  o18+r100           118       50      34       34      14.7  -0.567      -418       5.9  -0.771  -0.878  -0.626    +0.812
   ash+pdc           101       23      15       15      13.3  -0.604      -192       6.7  -0.552  -0.517  -0.350    +0.175
   o18+vah            93       40      22       22      13.6  -0.605      -356       9.1  -0.661  -0.491  -0.605    -0.066
   poc+prl            81       47      32       32      12.5  -0.654      -498      15.6  -0.321  -0.580  -0.317    -0.041
   pdc+poc            71       18       9        9      11.1  -0.724      -142       0.0  -1.062  -1.078  -0.196    +1.016
   o18+onh            72       22       8        8       0.0  -1.160      -183      12.5  -0.157  -0.763  -1.160    -0.668
   ash+o18           116       28      11       11       0.0  -1.166      -239       9.1  -0.404  -0.853  -1.166    -0.457
   count=1          7025     5415    2305     2305      20.9  -0.323    -14396      19.3  -0.174  -0.155  -0.307    -0.013
   count=2          2036     1421     813      813      23.9  -0.203     -2830      21.4  -0.119  -0.081  -0.251    +0.034
  count=3+          1844      931     614      614      26.4  -0.108     -1002      22.8  -0.031  -0.063  -0.160    -0.123

cells 54, with >= 150 fresh events 22; pairs seen 207, with >= 60 cluster days 96, of which with a fresh trade 96
picks (frozen in /home/claude/work/yt1/lab/data/studies/yt1/LEV1_selected.json)
  pick 1 [cell] em2u:R         events  320  a04x3: n  320 win 31.2%  R +0.0744  net +482   a08x3 R +0.1409   a04x2 R -0.0102   p20x3 R +0.0939   no placebo
  pick 2 [cell] onh:R          events  260  a04x3: n  260 win 28.5%  R -0.0300  net +36   a08x3 R +0.0366   a04x2 R -0.0826   p20x3 R -0.0492   placebo win 24.8% R -0.1621
  pick 3 [cell] ldh:R          events  159  a04x3: n  159 win 27.0%  R -0.0791  net -270   a08x3 R +0.0897   a04x2 R -0.1592   p20x3 R -0.0582   placebo win 21.1% R -0.3046
  pick 4 [cell] vw:S           events  305  a04x3: n  305 win 24.9%  R -0.1711  net -80   a08x3 R -0.0697   a04x2 R -0.2047   p20x3 R -0.0344   no placebo
  pick 5 [cell] em1u:R         events 1090  a04x3: n 1090 win 24.7%  R -0.1718  net -2906   a08x3 R -0.1259   a04x2 R -0.1916   p20x3 R -0.1316   no placebo
  pick 6 [pair] o00+pdh        events    8  a04x3: n    8 win 37.5%  R +0.6454  net +128   a08x3 R +0.8825   a04x2 R +0.6477   p20x3 R +1.0648   cluster days 76
  pick 7 [pair] ldh+o0830      events   11  a04x3: n   11 win 45.5%  R +0.6122  net +119   a08x3 R +0.3526   a04x2 R +0.1722   p20x3 R -0.1852   cluster days 88
  pick 8 [pair] o0830+prh      events   17  a04x3: n   17 win 41.2%  R +0.4791  net +172   a08x3 R +0.0967   a04x2 R +0.4180   p20x3 R +0.3326   cluster days 93
IN SAMPLE pooled real vs placebo [unique] a04x3: real n  3732 win 22.5% R -0.2615 | placebo n  4835 win 24.8% R -0.1684 | diff win -2.30 pts, R -0.0931, two-proportion p 0.0130
IN SAMPLE pooled real vs placebo [unique] p20x3: real n  3732 win 20.3% R -0.1384 | placebo n  4835 win 23.0% R -0.0529 | diff win -2.62 pts, R -0.0856, two-proportion p 0.0036
IN SAMPLE pooled real vs placebo [rows  ] a04x3: real n  4296 win 22.8% R -0.2475 | placebo n  5612 win 25.0% R -0.1596 | diff win -2.15 pts, R -0.0879, two-proportion p 0.0132
IN SAMPLE pooled real vs placebo [rows  ] p20x3: real n  4296 win 20.7% R -0.1251 | placebo n  5612 win 23.2% R -0.0418 | diff win -2.50 pts, R -0.0833, two-proportion p 0.0030

total 5s
```
