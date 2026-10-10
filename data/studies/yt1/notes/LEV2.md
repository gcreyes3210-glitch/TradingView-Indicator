# LEV2 - the midnight open (MID1) and volume profiles of the previous 1 to 5 sessions (VPN1) (YT10_SPEC.md)

Files (all new): `tools/yt1/lev2_levels.py` (levels, unit checks, level look-ahead test), `tools/yt1/lev2_events.py`
(events and scoring through `core.simulate`, day types, VA-trend, ORB by day), `tools/yt1/lev2_tables.py` (tables,
selection, the later out-of-sample scoring), `tools/yt1/s_L2.py` (standard harness module, look-ahead tests,
reconciliation), `tools/yt1/lev2_verify.py` (the hand checks and counts quoted here). `core.py`, `ind.py`, `run.py`,
`tt.py`, `cal_orb.py`, every `lev1_*` file, `s_L1.py`, `Aceflw_Levels.pine` and the specs were not edited. Imported
unchanged: `lev1_levels.profile` / `profile_pine` / `_weeks` / `pstart` / `ok_days` and its constants,
`lev1_events.order_of` / `px_grid` / `stop_pts`, `lev1_tables.vstats` / `two_prop_p` / `spearman`,
`s_L1.check_true_open`, `tt.bias`, `cal_orb.orders`. In-sample only (bars to 2022-12-30); no later bar exists in the
lab and none was looked for.

Outputs: `data/studies/yt1/is/MID1_events.parquet` (12,287 rows), `is/VPN1_events.parquet` (63,345 rows),
`is/VPN1_daytypes.csv` (926 cash days), `is/MID1_levels.csv`, `is/MID1_splits.csv`, `is/VPN1_reaction.csv`,
`is/VPN1_stacked.csv`, `is/VPN1_byN.csv`, `is/VPN1_daytypes_table.csv`, `is/VPN1_vatrend.json`,
`data/studies/yt1/VPN1_selected.json` (picks 1-8 with their in-sample numbers, thresholds, counts, sha256 of the
three event files and the seven tables), `is/L2_<variant>.csv|json` from the standard runner. Nothing was written to
`data/studies/yt1/full/`.

## 1. Readings (R) - all fixed before any table was built

Common to both studies

1. **Event.** As YT9 with the registered changes: every level row of a study day is its own event (no cluster, no
   lead, no "fresh" filter). Price at the start = the OPEN of the 09:30 bar (registered: "side is set by the 09:30
   open"). Resistance if the level is above it, support if below; a level exactly at the open has no side and is
   skipped (65 level-days). Skipped = |level - open| <= 0.04 x ATR ("within" means <=, as LEV1). Watch = the 09:30
   bar to the bar stamped 15:00 inclusive, or to the flat bar on a short day. Tap = the first watched bar with
   high >= order price (resistance) / low <= order price (support).
2. **Orders** exactly as LEV1 (`lev1_events.order_of`): order price = the level on the tick grid, resistance up /
   support down; one resting order from the last bar before 09:30 (`i`), expiring on the last watched bar; fade =
   limit, stop d beyond, target k x d; break = stop order with the move, stop d on the other side, target 3 x d;
   d = 20 points / 0.04 / 0.08 x ATR on the tick grid (at least 2 ticks). Win = the target was reached.
3. **A 13th variant, `brk_a04x2`** = the break with the a04 stop and a 2R target. The spec's pick rule names the
   neighbours "a08 x 3R and a04 x 2R" for every pick, and a pick may be a break; lev1 scores no 2R break, so it is
   scored here for every event and used only as that neighbour (four of the five cell picks turned out to be breaks).
4. **`crossed`** = between the level's set time and the 09:29 bar price traded strictly on both sides of the level
   (LEV1's `used`; the price at the set time is the starting side). Set time: an hourly open = the open of its bar; a
   profile = the close of its last bar ("since the profile ended"); `on` ends at 09:29 and is never crossed. A
   placebo is measured from its parent's set time with its own price. A split only, never a filter.
5. **Placebos** = level +/- 0.12 x ATR; side, skip and `crossed` from the placebo's own price; dropped if within
   0.03 x ATR (<=) of a real level of its own study that day: MID1 the 13 hourly opens, VPN1 the (up to) 39 profile
   levels. MID1 has placebos for the midnight open only (the spec registers "the two placebo levels at midnight
   open"). The aligned-POC level has no placebo and is not in the drop set (the spec defines none).
6. **Every level on its own means repeated trades.** Profiles of different lookbacks often share a level to the
   tick (13,052 of the 33,246 real VPN1 level-days share their exact price with another profile's level that day);
   each is its own event, so one order is counted in several cells and several times in a stacked bucket: the
   10,302 real tapped events are 7,711 distinct orders (date x side x price); the "3 or more" bucket's 4,522 events
   are 2,493 distinct orders on 536 days. The registered numbers (tables, selection, verdicts) count rows. Beside
   them: `distinct_orders` in the stacked table and in picks 6-7, and the pooled real-against-placebo lines both by
   rows and by distinct orders. **A bootstrap p computed on rows treats the repeats as independent trades.**

MID1

7. **Hourly open** = the open of the first 1-minute bar at or after HH:00 and before the 09:30 bar (19:00-23:00 on
   the calendar day before the cash day, 00:00-07:00 on it). No other limit on how late that bar may be: on
   2020-07-01 the evening session started at 20:00, so `o19` = `o20` that day. Exact bar missing on 21 of 11,492
   level-days (list in section 4); the 00:00 bar on 4 study days (00:01 each time).
8. **Distance buckets** [0, 0.10), [0.10, 0.25), [0.25, 0.50), [0.50, inf) x ATR of |level - 09:30 open|. "Measured
   before the skip rule": a bucket's `level_days` counts every level-day, its `skipped` those within 0.04 x ATR
   (all in the first bucket), its events the rest.
9. **Bias relation** (`tt.bias`, unchanged): `with` = the fade is in the bias direction (support on a bullish day =
   buy a tap from above; resistance on a bearish day = sell a tap from below), `against` = the other two
   combinations, `none` = bias 0. The placebo row under a bias / side / time / distance / crossed split = the
   midnight placebos with that value of their own.
10. **Verdict.** "6 of 8 calendar years positive" = net $ > 0 (house convention); halves = mean R before / from
    2023-01-01; neighbours positive = mean R > 0; placebo condition = the fade's win rate above the win rate of the
    midnight placebos (for the with-bias verdict: of the with-bias placebos). Fewer than 100 trades = "not enough
    data" (YT1's usual criterion; cannot bind for the two registered verdicts). The against-bias and no-bias fades
    are printed beside them without a registered verdict.

VPN1

11. **Sessions.** Regular session = the bars 09:30-15:59 of a calendar date; full session = the bars 18:00-16:59
    of a trading date (`ctx.tdate`; two stray bars stamped 17:59 in the data are in no session). "Previous N" = the
    last N sessions strictly before today (today's trading date, i.e. tonight, excluded) that are not short. Short
    = fewer than half the minutes: under 195 / 690 bars. In sample no regular session is short (the smallest has
    198 bars; 29 holiday or half-day sessions of 198-225 bars count as sessions, as the harness counts those days
    as cash days) and one full session is (2020-03-16, 571 bars). Not enough earlier sessions in the data = no
    profile.
12. **Composite** = `lev1_levels.profile` run once over the concatenated 1-minute bars of the sessions in time
    order (so the rows receive their shares in bar order, exactly as the script would if its session were those
    bars); the rows sit on whole points whatever the first bar is, which is the common 1-point grid.
13. **Weekly** (`rthw`, `ethw`) = every bar of the regular / full sessions whose date lies in the previous trading
    week (`lev1_levels._weeks`: the last Monday-Friday week with bars before this week), short sessions included
    (the spec says "all ... sessions of the previous trading week"; the skip-over rule is for counting back N).
14. **Roll rule** = every bar of the profile must be the contract of today's 09:30 bar. In this data the contract
    changes at 20:00 / 19:00 New York on the evening before the roll day, i.e. INSIDE that night's session. So on
    a roll day R `on` is not built (15 cash days, none a study day), and on study days: rth1, rth2, eth1 and `on`
    always exist; rthN is missing on R+2 .. R+N-1, ethN on R+2 .. R+N; the weekly profiles for the rest of the
    roll week and the whole following week (study days without: rth3 15, rth4 30, rth5 45, eth2 15, eth3 30,
    eth4 45, eth5 60, rthw 69, ethw 101).
15. **`on`** = lev1's overnight profile, unchanged (no short-session rule: there is no earlier "tonight").
16. **Stacked count** of a real profile-level event = the number of other profiles built that day with at least
    one of their three levels within 0.03 x ATR (<=) of this level's price. Counted for every real level, whatever
    the other level's side or skip. Buckets 0, 1, 2, 3+; both sides together.
17. **Aligned POCs** need all five profiles built; max - min <= 0.06 x ATR; level = `core.tick_round(mean)`; fixed
    at the later of the profiles' end and the bar that fixes the ATR; `crossed` from the profiles' end. Code
    `apoc_rth` / `apoc_eth`; a day can have both (49 days), then two events (9 of the 102 tapped events repeat an
    order).
18. **Pick 7** reads "the aligned-POC event x trade with the higher mean R (if it has at least 60 events)" as ONE
    event class, rth and eth aligned POCs together, x two trades (fade, break): "higher" of two. 102 tapped events
    together (rth 57, eth 45). Under the other reading (each family apart, four candidates) neither reaches 60 and
    pick 7 would not exist; that reading was not used and no number was looked at before choosing.
19. **Day types** need all five profiles; `above` = open > all five VAHs, `below` = open < all five VALs, `inside`
    = VAL <= open <= VAH for all five, `mixed` otherwise, `not built` when a profile is missing. Table on study
    days. Accepted direction: up for `above`, down for `below`; `inside`, `mixed`, `not built` and `all` have none
    and show the up move. Move = (close of the flat bar - 09:30 open) / ATR; hit = move > 0.
20. **ORB by day type**: `cal_orb.orders` through `core.run_orders(skip_roll=False)` as given, each trade put on
    its cash day; agrees = long on an `above` day, short on a `below` day. 395 of its 410 in-sample trades fall on
    study days.
21. **VA-trend**: a market order decided on the last bar before 09:30 (`i`), filled at the 09:30 open (`etype
    'open'`), long on `above` / short on `below` of the rth day type, no stop, flat at the flat bar, R unit
    0.1 x ATR, study days only. Neighbour 1 = the eth day type; neighbour 2 = rth with N = 1..3. Its win = net > 0.
22. **Selection.** Cell = profile x level x side x trade; its events = its tapped events (all, crossed or not);
    headline mean R = `a04x3` for a fade, `brk_a04` for a break. 156 cells, 48 with >= 150 events. Ranked by
    headline mean R (ties: the fixed order profile, level, side, trade), taking a cell unless its family (rth =
    rth1..5 and rthw, eth = eth1..5 and ethw, on) x level x side x trade is already taken. Pick 6 = among the
    buckets 1, 2, 3+ (rows, both sides) with >= 100 events x {fade, break}. Out of sample "3 of 4 calendar years
    positive" = net $ > 0; the placebo condition is applied to cell picks whose trade is the fade ("single-level
    fades"); a break cell's placebo is reported.
23. **Rank correlation** = Spearman over the cells with >= 150 in-sample events and at least one out-of-sample
    trade; also given for those with >= 100 out-of-sample events and for fades and breaks apart.

## 2. One line per level and split

| what | how | fixed at (`t_set`) |
|---|---|---|
| `o00` | open of the first bar at or after 00:00 (before 09:30) | that bar's open |
| `o19`..`o23`, `o01`..`o07` | the same at HH:00; 19:00-23:00 on the previous calendar day | that bar's open |
| `o00~` | `o00` +/- 0.12 x ATR; dropped within 0.03 x ATR of any hourly open | as `o00` |
| `rthN_vah/poc/val` | `lev1_levels.profile` over the 09:30-15:59 bars of the last N regular sessions before today | last bar of the newest session |
| `ethN_...` | the same over the 18:00-16:59 bars of the last N trading dates before today's | last bar of the newest session |
| `rthw_...`, `ethw_...` | the same over every regular / full session of the previous Monday-Friday trading week | last bar of that week's last session |
| `on_...` | lev1's overnight profile, 18:00-09:29 | last bar before 09:30 |
| `<code>~` | the level +/- 0.12 x ATR; dropped within 0.03 x ATR of any real profile level of the day | later of the parent's and the last bar before 18:00 (ATR) |
| `apoc_rth`, `apoc_eth` | mean of the five POCs on the tick grid when max - min <= 0.06 x ATR | later of the profiles' end and the ATR bar |
| side / skip | level against the 09:30 open; skipped when within 0.04 x ATR | 09:30 open |
| time split | stamp of the tap bar: 09:30-09:59, 10:00-11:29, 11:30-15:00 | |
| distance split | abs(level - 09:30 open) / ATR in [0, .10), [.10, .25), [.25, .50), [.50, inf) | |
| crossed | low < level < high over the bars from the set time to 09:29 (set price included) | 09:29 |
| bias split | `tt.bias`: support and +1 or resistance and -1 = with; the reverse = against; 0 = none | previous 17:00 |
| stacked count | other built profiles with a level within 0.03 x ATR | 09:29 |
| day type | 09:30 open against the five VAH / VAL of rth1..5 (eth1..5): above / below / inside / mixed | 09:30 open |
| VA-trend | above: buy the 09:30 open; below: sell it; flat at the flat bar; R unit 0.1 x ATR | 09:30 open |

## 3. Unit checks of the levels (`python3 tools/yt1/lev2_levels.py --check`)

```
composite profiles against the brute-force build (sessions re-derived from time slices, bars concatenated, Pine transcription bar by bar; values, volume, rows, bars and session list compared): 104 of 104 identical on 8 days x 13 profiles
  brute force 2020-04-07 (Tue): rth1 = rth2 = rth3 = rth4 = rth5 = eth1 = eth2 = eth3 = eth4 = eth5 = rthw = ethw = on =
      rth3: sessions 2020-04-02..2020-04-06 (3), bars 1170, rows 692, volume 1082784, Pine transcription VAH 7620.00 POC 7543.50 VAL 7437.00 | vp_levels VAH 7620.00 POC 7543.50 VAL 7437.00
      eth5: sessions 2020-03-31..2020-04-06 (5), bars 6828, rows 725, volume 3053855, Pine transcription VAH 7804.00 POC 7569.50 VAL 7379.00 | vp_levels VAH 7804.00 POC 7569.50 VAL 7379.00
      ethw: sessions 2020-03-30..2020-04-03 (5), bars 6829, rows 621, volume 3172717, Pine transcription VAH 7726.00 POC 7569.50 VAL 7413.00 | vp_levels VAH 7726.00 POC 7569.50 VAL 7413.00
  brute force 2021-07-06 (Tue): rth1 = rth2 = rth3 = rth4 = rth5 = eth1 = eth2 = eth3 = eth4 = eth5 = rthw = ethw = on =
      rth3: sessions 2021-07-01..2021-07-05 (3), bars 990, rows 259, volume 865123, Pine transcription VAH 14652.00 POC 14543.50 VAL 14470.00 | vp_levels VAH 14652.00 POC 14543.50 VAL 14470.00
      eth5: sessions 2021-06-29..2021-07-05 (5), bars 6659, rows 261, volume 2323618, Pine transcription VAH 14572.00 POC 14547.50 VAL 14483.00 | vp_levels VAH 14572.00 POC 14547.50 VAL 14483.00
      ethw: sessions 2021-06-28..2021-07-02 (5), bars 6900, rows 396, volume 2706093, Pine transcription VAH 14568.00 POC 14547.50 VAL 14463.00 | vp_levels VAH 14568.00 POC 14547.50 VAL 14463.00
  brute force 2021-08-24 (Tue): rth1 = rth2 = rth3 = rth4 = rth5 = eth1 = eth2 = eth3 = eth4 = eth5 = rthw = ethw = on =
      rth3: sessions 2021-08-19..2021-08-23 (3), bars 1170, rows 576, volume 1923701, Pine transcription VAH 15339.00 POC 15319.50 VAL 14933.00 | vp_levels VAH 15339.00 POC 15319.50 VAL 14933.00
      eth5: sessions 2021-08-17..2021-08-23 (5), bars 6900, rows 628, volume 4379824, Pine transcription VAH 15093.00 POC 14982.50 VAL 14866.00 | vp_levels VAH 15093.00 POC 14982.50 VAL 14866.00
      ethw: sessions 2021-08-16..2021-08-20 (5), bars 6900, rows 429, volume 4484613, Pine transcription VAH 15063.00 POC 14982.50 VAL 14890.00 | vp_levels VAH 15063.00 POC 14982.50 VAL 14890.00
  brute force 2021-11-11 (Thu): rth1 = rth2 = rth3 = rth4 = rth5 = eth1 = eth2 = eth3 = eth4 = eth5 = rthw = ethw = on =
      rth3: sessions 2021-11-08..2021-11-10 (3), bars 1170, rows 498, volume 2676339, Pine transcription VAH 16286.00 POC 16211.50 VAL 15907.00 | vp_levels VAH 16286.00 POC 16211.50 VAL 15907.00
      eth5: sessions 2021-11-04..2021-11-10 (5), bars 6900, rows 552, volume 5444071, Pine transcription VAH 16394.00 POC 16351.50 VAL 16173.00 | vp_levels VAH 16394.00 POC 16351.50 VAL 16173.00
      ethw: sessions 2021-11-01..2021-11-05 (5), bars 6900, rows 681, volume 4253740, Pine transcription VAH 16317.00 POC 15954.50 VAL 15776.00 | vp_levels VAH 16317.00 POC 15954.50 VAL 15776.00
  brute force 2022-03-09 (Wed): rth1 = rth2 = rth3 = rth4 = rth5 = eth1 = eth2 = eth3 = eth4 = eth5 = rthw = ethw = on =
      rth3: sessions 2022-03-04..2022-03-08 (3), bars 1170, rows 877, volume 3554511, Pine transcription VAH 13996.00 POC 13783.50 VAL 13385.00 | vp_levels VAH 13996.00 POC 13783.50 VAL 13385.00
      eth5: sessions 2022-03-02..2022-03-08 (5), bars 6900, rows 1287, volume 8039767, Pine transcription VAH 14330.00 POC 14047.50 VAL 13509.00 | vp_levels VAH 14330.00 POC 14047.50 VAL 13509.00
      ethw: sessions 2022-02-28..2022-03-04 (5), bars 6900, rows 701, volume 7932923, Pine transcription VAH 14261.00 POC 14046.50 VAL 13978.00 | vp_levels VAH 14261.00 POC 14046.50 VAL 13978.00
  brute force 2022-05-25 (Wed): rth1 = rth2 = rth3 = rth4 = rth5 = eth1 = eth2 = eth3 = eth4 = eth5 = rthw = ethw = on =
      rth3: sessions 2022-05-20..2022-05-24 (3), bars 1170, rows 564, volume 4108556, Pine transcription VAH 12039.00 POC 11742.50 VAL 11678.00 | vp_levels VAH 12039.00 POC 11742.50 VAL 11678.00
      eth5: sessions 2022-05-18..2022-05-24 (5), bars 6900, rows 1103, volume 9138774, Pine transcription VAH 12046.00 POC 11917.50 VAL 11709.00 | vp_levels VAH 12046.00 POC 11917.50 VAL 11709.00
      ethw: sessions 2022-05-16..2022-05-20 (5), bars 6900, rows 1103, volume 8760990, Pine transcription VAH 12577.00 POC 12326.50 VAL 11930.00 | vp_levels VAH 12577.00 POC 12326.50 VAL 11930.00
  brute force 2022-08-11 (Thu): rth1 = rth2 = rth3 = rth4 = rth5 = eth1 = eth2 = eth3 = eth4 = eth5 = rthw = ethw = on =
      rth3: sessions 2022-08-08..2022-08-10 (3), bars 1170, rows 457, volume 2849914, Pine transcription VAH 13420.00 POC 13371.50 VAL 13061.00 | vp_levels VAH 13420.00 POC 13371.50 VAL 13061.00
      eth5: sessions 2022-08-04..2022-08-10 (5), bars 6900, rows 457, volume 6359930, Pine transcription VAH 13374.00 POC 13287.50 VAL 13153.00 | vp_levels VAH 13374.00 POC 13287.50 VAL 13153.00
      ethw: sessions 2022-08-01..2022-08-05 (5), bars 6900, rows 570, volume 6552966, Pine transcription VAH 13226.00 POC 12927.50 VAL 12855.00 | vp_levels VAH 13226.00 POC 12927.50 VAL 12855.00
  brute force 2022-10-10 (Mon): rth1 = rth2 = rth3 = rth4 = rth5 = eth1 = eth2 = eth3 = eth4 = eth5 = rthw = ethw = on =
      rth3: sessions 2022-10-05..2022-10-07 (3), bars 1170, rows 679, volume 3044709, Pine transcription VAH 11722.00 POC 11596.50 VAL 11322.00 | vp_levels VAH 11722.00 POC 11596.50 VAL 11322.00
      eth5: sessions 2022-10-03..2022-10-07 (5), bars 6900, rows 841, volume 7308442, Pine transcription VAH 11722.00 POC 11585.50 VAL 11301.00 | vp_levels VAH 11722.00 POC 11585.50 VAL 11301.00
      ethw: sessions 2022-10-03..2022-10-07 (5), bars 6900, rows 841, volume 7308442, Pine transcription VAH 11722.00 POC 11585.50 VAL 11301.00 | vp_levels VAH 11722.00 POC 11585.50 VAL 11301.00
built / not built and the three values against the brute-force build on 40 random cash days x 13 profiles: 520 of 520 agree (48 of them not built)
eth1: profile volume and bar count = the summed 1-minute volume and the number of bars of that trading date's 18:00-16:59 bars: 895 of 895 days; its rows sum to that volume: 895 of 895
rth1: profile volume and bar count = those of the previous cash day's 09:30-15:59 bars: 910 of 910 days
val <= poc <= vah: 11228 of 11228 profiles (13 of 13 profile codes without an exception)
on = lev1_levels' overnight profile (vah, poc, val): identical on 911 of 911 days on which it is built; not built on 15 days ({'roll': 15}; lev1 builds one there: 15); of the not-built days, study days: 0
  hourly opens 2020-04-15: o19 8689.50 o20 8673.75 o21 8666.25 o22 8667.00 o23 8642.75 o00 8655.50 o01 8668.50 o02 8637.50 o03 8654.75 o04 8593.25 o05 8584.00 o06 8581.50 o07 8587.50
  hourly opens 2020-09-15: o19 11314.00 o20 11297.50 o21 11264.50 o22 11289.75 o23 11298.75 o00 11302.50 o01 11328.75 o02 11332.50 o03 11322.25 o04 11330.00 o05 11349.00 o06 11392.00 o07 11387.75
  hourly opens 2021-03-24: o19 13035.00 o20 13029.25 o21 13048.00 o22 13039.75 o23 13040.50 o00 13060.25 o01 13048.75 o02 13032.25 o03 13040.50 o04 13043.25 o05 13130.00 o06 13121.25 o07 13102.75
  hourly opens 2021-05-05: o19 13521.50 o20 13524.75 o21 13557.00 o22 13571.00 o23 13579.00 o00 13574.00 o01 13574.50 o02 13559.25 o03 13542.25 o04 13568.25 o05 13591.50 o06 13599.75 o07 13616.50
  hourly opens 2021-07-23: o19 14976.50 o20 14971.50 o21 14991.75 o22 14980.25 o23 14970.50 o00 14972.50 o01 14973.25 o02 14972.50 o03 14983.00 o04 14992.00 o05 14997.75 o06 15005.50 o07 15001.25
  hourly opens 2021-08-09: o19 15054.25 o20 15021.75 o21 15028.50 o22 15032.25 o23 15044.50 o00 15043.75 o01 15048.25 o02 15050.00 o03 15047.25 o04 15078.50 o05 15103.00 o06 15099.75 o07 15109.25
  hourly opens 2021-09-21: o19 15002.25 o20 15029.00 o21 15039.25 o22 15047.25 o23 15070.75 o00 15082.75 o01 15086.50 o02 15059.50 o03 15072.50 o04 15147.50 o05 15138.75 o06 15124.25 o07 15127.00
  hourly opens 2021-11-12: o19 16064.75 o20 16078.00 o21 16087.00 o22 16061.50 o23 16057.50 o00 16055.25 o01 16064.25 o02 16038.75 o03 16050.00 o04 16069.50 o05 16045.50 o06 16059.75 o07 16065.75
  hourly opens 2021-12-31: o19 16437.75 o20 16377.00 o21 16420.00 o22 16402.50 o23 16395.00 o00 16409.00 o01 16415.50 o02 16410.00 o03 16419.50 o04 16418.50 o05 16413.00 o06 16401.25 o07 16384.00
  hourly opens 2022-07-12: o19 11880.75 o20 11903.75 o21 11814.00 o22 11824.00 o23 11816.75 o00 11815.25 o01 11807.25 o02 11806.50 o03 11811.25 o04 11804.50 o05 11817.75 o06 11807.25 o07 11820.00
hourly opens against the raw bars (first bar of ctx.a at or after the wall-clock time and before 09:30): 130 of 130 identical on 10 days x 13 hours
o00 against lev1_levels' o00 (exact 00:00 bar only): equal on 917 of 917 days where lev1 has one; days with an o00 here and none in lev1 (00:00 bar missing): 9
weekly profiles: one value per week and code in 1005 of 1005 week-codes; the last session used lies 3 days (Friday) before this week's Monday on 4677 of 4836 level-days (otherwise [4] days: a week without a Friday session)
vp_levels(profs=['rth3', 'eth5']) = the same rows of the full build: True
```

All 13 profiles of the 8 days agree with the brute-force build (sessions picked by plain time slices, bars
concatenated, `lev1_levels.profile_pine` bar by bar): the three values, the volume, the number of rows and bars and
the session list. On 40 further random cash days x 13 profiles the brute-force build also agrees on which profiles
are NOT built (48 of 520).

Level look-ahead test (`python3 tools/yt1/lev2_levels.py --causal 190`): two levels of every code (13 hourly opens,
the midnight placebo, 39 profile levels, 39 placebo codes, the two aligned-POC codes), each recomputed on a window in
which (a) every bar after the level's own `t_set` is mirrored (`core._reflect`, as `lev1_levels.causal`; a level
fixed at a bar's open keeps that one open), (b) every bar after the last bar before 09:30 is mirrored (value,
`crossed` and `dropped` must be identical: a placebo is kept or dropped once every real level of the day is known,
09:29 at the latest), and (c) the bars between `t_set` and the 09:30 bar are REMOVED and the rest mirrored (the
09:30 bar has to exist for the cash day to exist; mirroring alone cannot show a dependence on how many bars come
later, removal can). Real levels must also equal the full run's value.

```
  o19 2/2  o20 2/2  o21 2/2  o22 2/2  o23 2/2  o00 2/2  o01 2/2  o02 2/2  o03 2/2  o04 2/2  o05 2/2  o06 2/2  o07 2/2  o00~ 2/2  rth1 6/6  rth2 6/6  rth3 6/6  rth4 6/6  rth5 6/6  eth1 6/6  eth2 6/6  eth3 6/6  eth4 6/6  eth5 6/6  rthw 6/6  ethw 6/6  on 6/6  rth1~ 6/6  rth2~ 6/6  rth3~ 6/6  rth4~ 6/6  rth5~ 6/6  eth1~ 6/6  eth2~ 6/6  eth3~ 6/6  eth4~ 6/6  eth5~ 6/6  rthw~ 6/6  ethw~ 6/6  on~ 6/6  apoc 4/4
level look-ahead test: 188 levels, each recomputed (a) with the future after its own t_set mirrored, (b) with the future after 09:29 mirrored, (c) with the bars between t_set and 09:30 removed; 0 differ -> PASS
```

## 4. Counts (`python3 tools/yt1/lev2_events.py --phase is`, `python3 tools/yt1/lev2_verify.py --extra`)

```
LEV2 events   phase is   bars 2019-06-02 18:00:00-04:00 -> 2022-12-30 16:59:00-05:00
study days 884 (cash days 926, roll day or the day after 30, no ATR 14)
MID1 hourly opens on study days: o19 884 (exact bar missing 6, latest by 60 min), o20 884 (exact bar missing 0), o21 884 (exact bar missing 0), o22 884 (exact bar missing 1, latest by 1 min), o23 884 (exact bar missing 0), o00 884 (exact bar missing 4, latest by 1 min), o01 884 (exact bar missing 1, latest by 2 min), o02 884 (exact bar missing 1, latest by 2 min), o03 884 (exact bar missing 2, latest by 6 min), o04 884 (exact bar missing 0), o05 884 (exact bar missing 1, latest by 1 min), o06 884 (exact bar missing 3, latest by 4 min), o07 884 (exact bar missing 2, latest by 33 min)
  hourly opens taken from a later bar: 21 of 11492 level-days; late by 1-5 min 18, 6-59 min 2, 60 min or more 1 (then equal to a later hour's open); crossed before 09:30: 11347 of 11492 (o00: 876 of 884)
  o00 placebos: made 1768, dropped 973, kept 795
VPN1 profiles on study days (built / not built: roll, not enough earlier sessions, none): rth1 884/0/0/0, rth2 884/0/0/0, rth3 869/15/0/0, rth4 854/30/0/0, rth5 839/45/0/0, eth1 884/0/0/0, eth2 869/15/0/0, eth3 854/30/0/0, eth4 839/45/0/0, eth5 824/60/0/0, rthw 815/69/0/0, ethw 783/101/0/0, on 884/0/0/0
  real profile levels 33246 (37.6 a study day; days with all 39: 783, with none: 0); crossed before 09:30: 11509
  placebos: made 66492, dropped 36600, kept 29892 (33.8 a study day)
  sessions: regular 926 (short, under 195 bars: 0; holding two contracts: 0), full 927 (short, under 690 bars: 1: 2020-03-16; holding two contracts: 15)
  aligned POCs apoc_rth: 110 study days of 839 with all five profiles built
  aligned POCs apoc_eth: 97 study days of 824 with all five profiles built
MID1: study days 884; level-days 12287; skipped (within 0.04 x ATR of the 09:30 open) 1754; events (watched) 10533; tapped 6507 (61.8%); crossed before 09:30 among tapped 6237 (95.9%)
  real         level-days  11492  events   9800  tapped   6121 (62.5%)  S 3223 / R 2898  by time 0930 3750, 1000 1570, 1130 801
  placebo      level-days    795  events    733  tapped    386 (52.7%)  S 201 / R 185  by time 0930 203, 1000 114, 1130 69
  fill bar = tap bar: 6507 tapped events x 13 variants = 84591 orders; filled on the tap bar 84591; filled on another bar 0; not filled 0 (events with at least one unfilled variant: 0); untapped events whose resting headline order filled: 0 of 4026; distinct orders (date x side x price) among the tapped events: 6357
wrote /home/claude/work/yt1/lab/data/studies/yt1/is/MID1_events.parquet (12287 rows) [6s]
VPN1: study days 884; level-days 63345; skipped (within 0.04 x ATR of the 09:30 open) 2684; events (watched) 60661; tapped 17840 (29.4%); crossed before 09:30 among tapped 8288 (46.5%)
  real         level-days  33246  events  31343  tapped  10302 (32.9%)  S 5500 / R 4802  by time 0930 5085, 1000 3123, 1130 2094
  placebo      level-days  29892  events  29118  tapped   7436 (25.5%)  S 3936 / R 3500  by time 0930 3291, 1000 2356, 1130 1789
  aligned POC  level-days    207  events    200  tapped    102 (51.0%)  S 55 / R 47  by time 0930 51, 1000 32, 1130 19
  fill bar = tap bar: 17840 tapped events x 13 variants = 231920 orders; filled on the tap bar 231920; filled on another bar 0; not filled 0 (events with at least one unfilled variant: 0); untapped events whose resting headline order filled: 0 of 42821; distinct orders (date x side x price) among the tapped events: 13529
wrote /home/claude/work/yt1/lab/data/studies/yt1/is/VPN1_events.parquet (63345 rows) [19s, 2 process(es)]
day types on the 884 study days: rth: above 192, below 94, inside 87, mixed 466, not built 45; eth: above 178, below 90, inside 89, mixed 467, not built 60; rth3: above 233, below 132, inside 139, mixed 365, not built 15
VA-trend trades: rth 286, eth 268, rth3 365; ORB v1.4 trades on study days 395 (on all cash days 410)
wrote /home/claude/work/yt1/lab/data/studies/yt1/is/VPN1_daytypes.csv (926 rows) [1s]
total 34s
```

```
cash days whose last bar before 09:30 lies on another calendar day: 0 of 926; last bar before 09:30 stamped 09:29 on 921
MID1: level-days 12287; 09:30 open != last close before it on 9061 (median |diff| 0.25 points, max 119.25); the side differs between the two on 67 level-days, the 0.04 x ATR skip on 70; level exactly at the open (no side): 28
VPN1: level-days 63345; 09:30 open != last close before it on 46714 (median |diff| 0.25 points, max 119.25); the side differs between the two on 96 level-days, the 0.04 x ATR skip on 102; level exactly at the open (no side): 37
VPN1 real level-days 33246: distinct prices per day 25062; level-days sharing their exact price with another profile's level 13052; on the tick grid 33246
VPN1 real tapped events 10302: distinct orders (date x side x price) 7711; by stacked count 0: 2029 rows / 2029 orders, 1: 2191 rows / 1937 orders, 2: 1560 rows / 1252 orders, 3+: 4522 rows / 2493 orders
VPN1 profile x level x side: 78; tapped events per cell min 50 median 119 max 390; with >= 150: 24
aligned POCs rth: study days with five profiles 839; (max - min) / ATR median 0.585; <= 0.06: 110; both rth and eth aligned on the same day: 49
aligned POCs eth: study days with five profiles 824; (max - min) / ATR median 0.575; <= 0.06: 97; both rth and eth aligned on the same day: 49
hourly opens taken from a later bar on study days: 2019-07-03 o00 +1 min; 2019-07-05 o19 +2 min; 2019-07-08 o19 +1 min; 2019-07-10 o19 +1 min; 2019-07-11 o19 +1 min; 2019-07-16 o00 +1 min; 2019-09-11 o00 +1 min; 2019-09-13 o22 +1 min; 2019-10-07 o00 +1 min; 2020-03-09 o01 +2 min; 2020-03-09 o03 +2 min; 2020-03-09 o06 +2 min; 2020-03-09 o07 +1 min; 2020-03-18 o02 +2 min; 2020-03-18 o03 +6 min; 2020-03-18 o05 +1 min; 2020-03-18 o06 +4 min; 2020-03-18 o07 +33 min; 2020-03-20 o06 +1 min; 2020-03-23 o19 +2 min; 2020-07-01 o19 +60 min
midnight open: watched 761, bias +1 / -1 / 0 days 350 / 286 / 125; with 306, against 330, none 125
tapped events: MID1: tapped by the 09:30 bar itself 554, tap bar opening at or beyond the order price 3; VPN1: tapped by the 09:30 bar itself 991, tap bar opening at or beyond the order price 3
```

Per cash day there are 13 hourly opens and up to 39 profile levels. The 0.04 x ATR skip removes 1,754 of the
12,287 MID1 level-days (hourly opens lie near the 09:30 open) and 2,684 of the 63,345 VPN1 ones. A real profile
level is tapped by 15:00 on 32.9 % of its watched days, a profile placebo on 25.5 %, an hourly open on 62.5 %.
The side under the two readings of "the price at the start" (09:30 open, or the last close before it) differs on 67
MID1 and 96 VPN1 level-days.

## 5. Fill bar = tap bar

Every event's orders were given to `core.simulate` as in reading 2 (one order resting from the last bar before
09:30). MID1: 6,507 tapped events x 13 variants = 84,591 orders, all filled on the tap bar, none on another bar, none
unfilled; none of the 4,026 never-tapped events' resting headline order filled. VPN1: 17,840 tapped events x 13 =
231,920 orders, all filled on the tap bar, none on another bar, none unfilled; none of the 42,821 never-tapped
events' resting headline order filled. A tap bar that opens at or beyond the order price (a gap through the level)
occurs 3 times in each study; the fade then fills at that open, as the house rule says. 554 MID1 and 991 VPN1
events are tapped by the 09:30 bar itself. No order bar lies on another calendar day than its 09:30 bar (the last
bar before 09:30 is the 09:29 bar on 921 of 926 cash days, an earlier bar of the same morning on the other 5).

Cross-check against YT9's files (`is/LEV1_events.parquet`, another code path for the event): on the 880 days where
lev1 has an `o00` (it needs the exact 00:00 bar) the value, order price, side, skip, tap bar and `used` / `crossed`
are identical on all 880, and the R of `a04x3`, `p20x3`, `a08x1`, `brk_a04`, `brk_p20` is identical on all 201
events lev1 scored (there the event had to be the lead of its cluster). `on_vah` / `on_poc` / `on_val` against
lev1's `vah` / `poc` / `val`: value, side and tap bar identical on 884 of 884 days each, R identical on the 241 / 219
/ 248 events lev1 scored.

## 6. Hand checks (`python3 tools/yt1/lev2_verify.py`)

Each level is re-derived below from plain time slices of the bars (hourly opens: the first bar at or after the
stamp; profiles: the session slices, concatenated, through the Pine transcription `profile_pine`; not with
`mid_levels` / `vp_levels`), then `crossed`, the 09:30 open and side, the bars around the tap and the trades. All 16
levels agree with the events file, every trade agrees with it, the bias of events 3 and 4 is re-derived from the two
daily candles, the stacked counts of 10 and 11 from the other profiles' levels, and the two VA-trend days from the
five value areas. Events were drawn with a fixed seed inside each category.

```
### 1 midnight open, support tap: 2019-11-29 (Fri) o00
  level:
    first bar at or after 11-29 00:00: the bar stamped 11-29 00:00, open 8424.25
  -> by hand 8424.2500; events file 8424.2500 (same); fixed at 11-29 00:00 (open); from then to 09:29 price ranged 8411.00..8440.00 (starting at 8424.25): traded through the level True; events file crossed True
  09:30 open 8429.00 (bar 09:30 O 8429.00); ATR 81.14; level below by 4.75 = 0.059 ATR (skip at or under 0.04; bucket <0.10) -> support; order price 8424.25; watch 09:30..13:04
  tap bar 09:32 (bucket 0930); lowest low of the watch before it 8425.25 (above the order price)
  a04x3: order i=09:29 buy limit 8424.25 stop 8421.00 target 8434.00 (d = 3.25) -> fill 09:32 at 8424.50, exit 09:58 at 8433.75 (TP), pnl +16.50, R +2.357   [events file: R +2.357 TP]
  p20x3: order i=09:29 buy limit 8424.25 stop 8404.25 target 8484.25 (d = 20.00) -> fill 09:32 at 8424.50, exit 13:04 at 8417.00 (time), pnl -17.00, R -0.420   [events file: R -0.420 time]
  brk_a04: order i=09:29 sell stop 8424.25 stop 8427.50 target 8414.50 (d = 3.25) -> fill 09:32 at 8424.00, exit 09:38 at 8427.75 (SL), pnl -9.50, R -1.357   [events file: R -1.357 SL]
      09:30  O 8429.00  H 8430.75  L 8425.25  C 8428.25
      09:31  O 8428.00  H 8429.75  L 8425.75  C 8428.50
      09:32  O 8428.25  H 8429.00  L 8424.00  C 8426.25   <- tap
      09:33  O 8426.25  H 8426.75  L 8424.00  C 8424.50
      09:34  O 8424.50  H 8427.25  L 8423.50  C 8426.25
      09:35  O 8426.25  H 8427.00  L 8423.25  C 8425.00
      09:36  O 8424.75  H 8425.25  L 8422.00  C 8424.50
      09:37  O 8425.00  H 8426.75  L 8424.00  C 8426.00
      09:38  O 8425.50  H 8430.25  L 8424.75  C 8430.00
      09:39  O 8430.25  H 8433.00  L 8429.25  C 8431.25
      09:40  O 8431.00  H 8431.00  L 8426.75  C 8427.50
      09:41  O 8427.50  H 8429.00  L 8424.50  C 8424.50
      09:42  O 8424.25  H 8425.00  L 8422.25  C 8423.50
      ... exit bar 09:58  O 8433.25  H 8436.25  L 8432.25  C 8435.75   <- exit TP (a04x3)

### 2 midnight open, resistance tap: 2020-02-03 (Mon) o00
  level:
    first bar at or after 02-03 00:00: the bar stamped 02-03 00:00, open 9070.75
  -> by hand 9070.7500; events file 9070.7500 (same); fixed at 02-03 00:00 (open); from then to 09:29 price ranged 9025.25..9088.00 (starting at 9070.75): traded through the level True; events file crossed True
  09:30 open 9041.50 (bar 09:30 O 9041.50); ATR 130.30; level above by 29.25 = 0.224 ATR (skip at or under 0.04; bucket 0.10-0.25) -> resistance; order price 9070.75; watch 09:30..15:00
  tap bar 09:35 (bucket 0930); highest high of the watch before it 9069.50 (below the order price)
  a04x3: order i=09:29 sell limit 9070.75 stop 9076.00 target 9055.00 (d = 5.25) -> fill 09:35 at 9070.50, exit 09:35 at 9076.25 (SL), pnl -13.50, R -1.227   [events file: R -1.227 SL]
  p20x3: order i=09:29 sell limit 9070.75 stop 9090.75 target 9010.75 (d = 20.00) -> fill 09:35 at 9070.50, exit 09:36 at 9091.00 (SL), pnl -43.00, R -1.062   [events file: R -1.062 SL]
  brk_a04: order i=09:29 buy stop 9070.75 stop 9065.50 target 9086.50 (d = 5.25) -> fill 09:35 at 9071.00, exit 09:35 at 9086.25 (TP), pnl +28.50, R +2.591   [events file: R +2.591 TP]
      09:33  O 9060.25  H 9068.75  L 9057.75  C 9065.25
      09:34  O 9065.00  H 9069.50  L 9061.50  C 9069.50
      09:35  O 9069.50  H 9086.50  L 9069.50  C 9086.50   <- tap

### 3 midnight open, fade with the bias: 2022-02-17 (Thu) o00
  level:
    first bar at or after 02-17 00:00: the bar stamped 02-17 00:00, open 14486.75
  -> by hand 14486.7500; events file 14486.7500 (same); fixed at 02-17 00:00 (open); from then to 09:29 price ranged 14446.00..14583.50 (starting at 14486.75): traded through the level True; events file crossed True
  09:30 open 14462.75 (bar 09:30 O 14462.75); ATR 421.47; level above by 24.00 = 0.057 ATR (skip at or under 0.04; bucket <0.10) -> resistance; order price 14486.75; watch 09:30..15:00
  daily bias (tt.bias): candle 1 = trading date 2022-02-16 high 14668.50 low 14381.00 close 14593.50; candle 2 = 2022-02-15 high 14615.00 low 14223.25; high1 > high2, close1 < high2, low1 >= low2 -> bearish; tt.bias = -1 ('fail'), its candle-1 levels h 14668.50 l 14381.00 c 14593.50, candle 2 h 14615.00 l 14223.25
  -> the fade is a short: with the bias (events file bias -1, bias_rel with)
  tap bar 09:35 (bucket 0930); highest high of the watch before it 14485.50 (below the order price)
  a04x3: order i=09:29 sell limit 14486.75 stop 14503.50 target 14436.50 (d = 16.75) -> fill 09:35 at 14486.50, exit 09:46 at 14436.75 (TP), pnl +97.50, R +2.868   [events file: R +2.868 TP]
  p20x3: order i=09:29 sell limit 14486.75 stop 14506.75 target 14426.75 (d = 20.00) -> fill 09:35 at 14486.50, exit 09:46 at 14427.00 (TP), pnl +117.00, R +2.889   [events file: R +2.889 TP]
  brk_a04: order i=09:29 buy stop 14486.75 stop 14470.00 target 14537.00 (d = 16.75) -> fill 09:35 at 14487.00, exit 09:36 at 14469.75 (SL), pnl -36.50, R -1.074   [events file: R -1.074 SL]
      09:33  O 14463.00  H 14478.50  L 14450.25  C 14473.50
      09:34  O 14473.25  H 14478.75  L 14452.50  C 14471.75
      09:35  O 14472.00  H 14488.50  L 14462.50  C 14471.75   <- tap
      09:36  O 14471.25  H 14482.75  L 14464.25  C 14472.75
      09:37  O 14473.25  H 14486.00  L 14467.75  C 14474.75
      09:38  O 14474.50  H 14475.00  L 14459.25  C 14464.50
      09:39  O 14463.75  H 14493.25  L 14463.00  C 14488.75
      09:40  O 14488.50  H 14496.00  L 14476.25  C 14485.75
      09:41  O 14486.25  H 14487.00  L 14473.00  C 14477.25
      09:42  O 14476.50  H 14487.75  L 14468.50  C 14473.75
      09:43  O 14474.00  H 14484.50  L 14464.50  C 14477.50
      09:44  O 14477.50  H 14486.00  L 14471.50  C 14475.75
      09:45  O 14475.75  H 14482.50  L 14454.25  C 14456.00
      ... exit bar 09:46  O 14456.00  H 14456.50  L 14423.25  C 14425.00   <- exit TP (a04x3)

### 4 midnight open, fade against the bias: 2021-06-21 (Mon) o00
  level:
    first bar at or after 06-21 00:00: the bar stamped 06-21 00:00, open 14003.00
  -> by hand 14003.0000; events file 14003.0000 (same); fixed at 06-21 00:00 (open); from then to 09:29 price ranged 13991.75..14126.75 (starting at 14003.00): traded through the level True; events file crossed True
  09:30 open 14051.50 (bar 09:30 O 14051.50); ATR 206.04; level below by 48.50 = 0.235 ATR (skip at or under 0.04; bucket 0.10-0.25) -> support; order price 14003.00; watch 09:30..15:00
  daily bias (tt.bias): candle 1 = trading date 2021-06-18 high 14205.75 low 14010.00 close 14018.00; candle 2 = 2021-06-17 high 14199.25 low 13842.00; high1 > high2, close1 < high2, low1 >= low2 -> bearish; tt.bias = -1 ('fail'), its candle-1 levels h 14205.75 l 14010.00 c 14018.00, candle 2 h 14199.25 l 13842.00
  -> the fade is a long: against the bias (events file bias -1, bias_rel against)
  tap bar 09:32 (bucket 0930); lowest low of the watch before it 14025.00 (above the order price)
  a04x3: order i=09:29 buy limit 14003.00 stop 13994.75 target 14027.75 (d = 8.25) -> fill 09:32 at 14003.25, exit 09:33 at 13994.50 (SL), pnl -19.50, R -1.147   [events file: R -1.147 SL]
  p20x3: order i=09:29 buy limit 14003.00 stop 13983.00 target 14063.00 (d = 20.00) -> fill 09:32 at 14003.25, exit 09:35 at 13982.75 (SL), pnl -43.00, R -1.062   [events file: R -1.062 SL]
  brk_a04: order i=09:29 sell stop 14003.00 stop 14011.25 target 13978.25 (d = 8.25) -> fill 09:32 at 14002.75, exit 09:33 at 14011.50 (SL), pnl -19.50, R -1.147   [events file: R -1.147 SL]
      09:30  O 14051.50  H 14072.25  L 14042.00  C 14070.75
      09:31  O 14070.50  H 14071.75  L 14025.00  C 14025.50
      09:32  O 14025.00  H 14025.75  L 14001.00  C 14002.50   <- tap
      09:33  O 14002.25  H 14012.50  L 13994.50  C 14006.75   <- exit SL (a04x3)

### 5 hourly-open comparison level: 2021-08-12 (Thu) o05
  level:
    first bar at or after 08-12 05:00: the bar stamped 08-12 05:00, open 15007.75
  -> by hand 15007.7500; events file 15007.7500 (same); fixed at 08-12 05:00 (open); from then to 09:29 price ranged 14984.75..15035.00 (starting at 15007.75): traded through the level True; events file crossed True
  09:30 open 14999.75 (bar 09:30 O 14999.75); ATR 168.46; level above by 8.00 = 0.047 ATR (skip at or under 0.04; bucket <0.10) -> resistance; order price 15007.75; watch 09:30..15:00
  tap bar 10:19 (bucket 1000); highest high of the watch before it 15005.25 (below the order price)
  a04x3: order i=09:29 sell limit 15007.75 stop 15014.50 target 14987.50 (d = 6.75) -> fill 10:19 at 15007.50, exit 10:20 at 15014.75 (SL), pnl -16.50, R -1.179   [events file: R -1.179 SL]
  p20x3: order i=09:29 sell limit 15007.75 stop 15027.75 target 14947.75 (d = 20.00) -> fill 10:19 at 15007.50, exit 10:30 at 15028.00 (SL), pnl -43.00, R -1.062   [events file: R -1.062 SL]
  brk_a04: order i=09:29 buy stop 15007.75 stop 15001.00 target 15028.00 (d = 6.75) -> fill 10:19 at 15008.00, exit 10:30 at 15027.75 (TP), pnl +37.50, R +2.679   [events file: R +2.679 TP]
      10:17  O 14980.50  H 14991.00  L 14978.25  C 14990.25
      10:18  O 14990.00  H 14997.75  L 14989.75  C 14996.00
      10:19  O 14996.50  H 15009.00  L 14995.50  C 15008.00   <- tap
      10:20  O 15008.00  H 15018.00  L 15007.75  C 15009.75   <- exit SL (a04x3)

### 6 rth3 level: 2021-08-18 (Wed) rth3_val
  level:
    session 2021-08-13 (Fri): 390 bars 08-13 09:30..08-13 15:59, high 15141.50 low 15068.00 volume 373113
    session 2021-08-16 (Mon): 390 bars 08-16 09:30..08-16 15:59, high 15136.50 low 14917.00 volume 642871
    session 2021-08-17 (Tue): 390 bars 08-17 09:30..08-17 15:59, high 15057.75 low 14897.00 volume 808167
    as one profile (Pine transcription, bar by bar): 1170 bars, 245 rows of 1.00 from 14897.00, volume 1824151; POC row 216 [15113.00, 15114.00) holds 19491.9 (next largest 17446.5); value area rows 72..244 hold 1288944.5 = 70.7%; VAH 15142.00 POC 15113.50 VAL 14969.00; contract(s) [3601]
  -> by hand 14969.0000; events file 14969.0000 (same); fixed at 08-17 15:59 (close); from then to 09:29 price ranged 14951.75..15028.25 (starting at 14999.75): traded through the level True; events file crossed True
  09:30 open 14978.75 (bar 09:30 O 14978.75); ATR 170.81; level below by 9.75 = 0.057 ATR (skip at or under 0.04; bucket <0.10) -> support; order price 14969.00; watch 09:30..15:00
  tap bar 09:30 = the 09:30 bar (bucket 0930)
  a04x3: order i=09:29 buy limit 14969.00 stop 14962.25 target 14989.25 (d = 6.75) -> fill 09:30 at 14969.25, exit 09:31 at 14989.00 (TP), pnl +37.50, R +2.679   [events file: R +2.679 TP]
  p20x3: order i=09:29 buy limit 14969.00 stop 14949.00 target 15029.00 (d = 20.00) -> fill 09:30 at 14969.25, exit 09:56 at 15028.75 (TP), pnl +117.00, R +2.889   [events file: R +2.889 TP]
  brk_a04: order i=09:29 sell stop 14969.00 stop 14975.75 target 14948.75 (d = 6.75) -> fill 09:30 at 14968.75, exit 09:30 at 14976.00 (SL), pnl -16.50, R -1.179   [events file: R -1.179 SL]
      09:29  O 14975.25  H 14979.75  L 14973.25  C 14978.75
      09:30  O 14978.75  H 14989.25  L 14964.25  C 14982.75   <- tap
      09:31  O 14982.00  H 15001.75  L 14975.75  C 15000.75   <- exit TP (a04x3)

### 7 eth5 level: 2022-01-03 (Mon) eth5_val
  level:
    session 2021-12-27 (Mon): 1380 bars 12-26 18:00..12-27 16:59, high 16580.75 low 16304.25 volume 559704
    session 2021-12-28 (Tue): 1380 bars 12-27 18:00..12-28 16:59, high 16658.50 low 16453.25 volume 784150
    session 2021-12-29 (Wed): 1380 bars 12-28 18:00..12-29 16:59, high 16564.00 low 16387.75 volume 652084
    session 2021-12-30 (Thu): 1380 bars 12-29 18:00..12-30 16:59, high 16567.50 low 16411.25 volume 560321
    session 2021-12-31 (Fri): 1380 bars 12-30 18:00..12-31 16:59, high 16464.00 low 16313.25 volume 551130
    as one profile (Pine transcription, bar by bar): 6900 bars, 355 rows of 1.00 from 16304.00, volume 3107389; POC row 234 [16538.00, 16539.00) holds 25338.4 (next largest 23555.1); value area rows 124..258 hold 2179549.7 = 70.1%; VAH 16563.00 POC 16538.50 VAL 16428.00; contract(s) [7575]
  -> by hand 16428.0000; events file 16428.0000 (same); fixed at 12-31 16:59 (close); from then to 09:29 price ranged 16333.50..16452.50 (starting at 16333.50): traded through the level True; events file crossed True
  09:30 open 16382.75 (bar 09:30 O 16382.75); ATR 292.90; level above by 45.25 = 0.154 ATR (skip at or under 0.04; bucket 0.10-0.25) -> resistance; order price 16428.00; watch 09:30..15:00
  tap bar 09:31 (bucket 0930); highest high of the watch before it 16413.00 (below the order price)
  a04x3: order i=09:29 sell limit 16428.00 stop 16439.75 target 16392.75 (d = 11.75) -> fill 09:31 at 16427.75, exit 09:33 at 16440.00 (SL), pnl -26.50, R -1.104   [events file: R -1.104 SL]
  p20x3: order i=09:29 sell limit 16428.00 stop 16448.00 target 16368.00 (d = 20.00) -> fill 09:31 at 16427.75, exit 09:34 at 16448.25 (SL), pnl -43.00, R -1.062   [events file: R -1.062 SL]
  brk_a04: order i=09:29 buy stop 16428.00 stop 16416.25 target 16463.25 (d = 11.75) -> fill 09:31 at 16428.25, exit 09:37 at 16463.00 (TP), pnl +67.50, R +2.812   [events file: R +2.812 TP]
      09:29  O 16380.25  H 16385.75  L 16379.00  C 16382.75
      09:30  O 16382.75  H 16413.00  L 16378.50  C 16406.00
      09:31  O 16405.75  H 16438.50  L 16397.75  C 16427.75   <- tap
      09:32  O 16427.25  H 16437.25  L 16421.00  C 16429.25
      09:33  O 16429.25  H 16444.25  L 16428.75  C 16440.50   <- exit SL (a04x3)

### 8 weekly level: 2019-07-24 (Wed) rthw_vah
  level:
    session 2019-07-15 (Mon): 390 bars 07-15 09:30..07-15 15:59, high 7992.00 low 7961.25 volume 121261
    session 2019-07-16 (Tue): 390 bars 07-16 09:30..07-16 15:59, high 7987.25 low 7924.00 volume 156063
    session 2019-07-17 (Wed): 390 bars 07-17 09:30..07-17 15:59, high 7962.25 low 7908.25 volume 150684
    session 2019-07-18 (Thu): 390 bars 07-18 09:30..07-18 15:59, high 7932.25 low 7845.25 volume 200136
    session 2019-07-19 (Fri): 390 bars 07-19 09:30..07-19 15:59, high 7974.75 low 7848.75 volume 210284
    as one profile (Pine transcription, bar by bar): 1950 bars, 148 rows of 1.00 from 7845.00, volume 838428; POC row 93 [7938.00, 7939.00) holds 14206.0 (next largest 13078.7); value area rows 61..139 hold 589297.6 = 70.3%; VAH 7985.00 POC 7938.50 VAL 7906.00; contract(s) [8084]
  -> by hand 7985.0000; events file 7985.0000 (same); fixed at 07-19 15:59 (close); from then to 09:29 price ranged 7815.00..7985.75 (starting at 7853.25): traded through the level True; events file crossed True
  09:30 open 7940.00 (bar 09:30 O 7940.00); ATR 101.56; level above by 45.00 = 0.443 ATR (skip at or under 0.04; bucket 0.25-0.50) -> resistance; order price 7985.00; watch 09:30..15:00
  tap bar 10:32 (bucket 1000); highest high of the watch before it 7983.50 (below the order price)
  a04x3: order i=09:29 sell limit 7985.00 stop 7989.00 target 7973.00 (d = 4.00) -> fill 10:32 at 7984.75, exit 10:37 at 7989.25 (SL), pnl -11.00, R -1.294   [events file: R -1.294 SL]
  p20x3: order i=09:29 sell limit 7985.00 stop 8005.00 target 7925.00 (d = 20.00) -> fill 10:32 at 7984.75, exit 14:55 at 8005.25 (SL), pnl -43.00, R -1.062   [events file: R -1.062 SL]
  brk_a04: order i=09:29 buy stop 7985.00 stop 7981.00 target 7997.00 (d = 4.00) -> fill 10:32 at 7985.25, exit 10:51 at 7980.75 (SL), pnl -11.00, R -1.294   [events file: R -1.294 SL]
      10:30  O 7977.50  H 7983.00  L 7977.50  C 7979.25
      10:31  O 7979.00  H 7983.50  L 7977.75  C 7983.50
      10:32  O 7983.50  H 7986.00  L 7983.25  C 7985.00   <- tap
      10:33  O 7985.25  H 7987.00  L 7983.25  C 7984.00
      10:34  O 7984.00  H 7985.50  L 7983.75  C 7985.00
      10:35  O 7985.50  H 7988.75  L 7984.00  C 7986.50
      10:36  O 7986.75  H 7986.75  L 7983.75  C 7986.00
      10:37  O 7986.00  H 7991.25  L 7986.00  C 7989.25   <- exit SL (a04x3)

### 9 aligned-POC day: 2021-03-29 (Mon) apoc_eth
  level:
    eth1: sessions 2021-03-26..2021-03-26 (1), 1365 bars, volume 1235454, VAH 12860.00 POC 12825.50 VAL 12769.00
    eth2: sessions 2021-03-25..2021-03-26 (2), 2730 bars, volume 2747703, VAH 12839.00 POC 12816.50 VAL 12720.00
    eth3: sessions 2021-03-24..2021-03-26 (3), 4095 bars, volume 3936525, VAH 12873.00 POC 12816.50 VAL 12646.00
    eth4: sessions 2021-03-23..2021-03-26 (4), 5460 bars, volume 5144869, VAH 13011.00 POC 12816.50 VAL 12638.00
    eth5: sessions 2021-03-22..2021-03-26 (5), 6825 bars, volume 6090716, VAH 13023.00 POC 12816.50 VAL 12642.00
    the five POCs 12825.50, 12816.50, 12816.50, 12816.50, 12816.50: max - min = 9.00 <= 0.06 x ATR = 19.78; mean 12818.3000 -> on the tick grid 12818.25
  -> by hand 12818.2500; events file 12818.2500 (same); fixed at 03-26 16:59 (close); from then to 09:29 price ranged 12807.00..12986.25 (starting at 12961.25): traded through the level True; events file crossed True
  09:30 open 12941.25 (bar 09:30 O 12941.25); ATR 329.68; level below by 123.00 = 0.373 ATR (skip at or under 0.04; bucket 0.25-0.50) -> support; order price 12818.25; watch 09:30..15:00
  tap bar 10:09 (bucket 1000); lowest low of the watch before it 12827.25 (above the order price)
  a04x3: order i=09:29 buy limit 12818.25 stop 12805.00 target 12858.00 (d = 13.25) -> fill 10:09 at 12818.50, exit 10:14 at 12857.75 (TP), pnl +76.50, R +2.833   [events file: R +2.833 TP]
  p20x3: order i=09:29 buy limit 12818.25 stop 12798.25 target 12878.25 (d = 20.00) -> fill 10:09 at 12818.50, exit 10:36 at 12878.00 (TP), pnl +117.00, R +2.889   [events file: R +2.889 TP]
  brk_a04: order i=09:29 sell stop 12818.25 stop 12831.50 target 12778.50 (d = 13.25) -> fill 10:09 at 12818.00, exit 10:10 at 12831.75 (SL), pnl -29.50, R -1.093   [events file: R -1.093 SL]
      10:07  O 12848.00  H 12848.75  L 12835.50  C 12843.25
      10:08  O 12843.75  H 12850.00  L 12836.00  C 12841.00
      10:09  O 12840.75  H 12841.50  L 12818.25  C 12830.25   <- tap
      10:10  O 12830.75  H 12835.25  L 12821.25  C 12832.00
      10:11  O 12832.00  H 12838.75  L 12827.00  C 12830.75
      10:12  O 12830.75  H 12836.50  L 12816.25  C 12828.75
      10:13  O 12828.50  H 12855.75  L 12826.50  C 12854.75
      10:14  O 12855.00  H 12869.25  L 12854.50  C 12858.50   <- exit TP (a04x3)

### 10 stacked event (two or more other profiles): 2020-01-06 (Mon) eth3_poc
  level:
    session 2019-12-31 (Tue): 1342 bars 12-30 18:00..12-31 16:59, high 8772.00 low 8692.25 volume 114101
    session 2020-01-02 (Thu): 1364 bars 01-01 18:00..01-02 16:59, high 8901.50 low 8769.25 volume 170416
    session 2020-01-03 (Fri): 1365 bars 01-02 18:00..01-03 16:59, high 8907.75 low 8735.25 volume 315021
    as one profile (Pine transcription, bar by bar): 4071 bars, 216 rows of 1.00 from 8692.00, volume 599538; POC row 126 [8818.00, 8819.00) holds 10297.1 (next largest 9950.7); value area rows 80..166 hold 419716.9 = 70.0%; VAH 8859.00 POC 8818.50 VAL 8772.00; contract(s) [8196]
  -> by hand 8818.5000; events file 8818.5000 (same); fixed at 01-03 16:59 (close); from then to 09:29 price ranged 8723.00..8810.25 (starting at 8810.25): traded through the level False; events file crossed False
  09:30 open 8739.00 (bar 09:30 O 8739.00); ATR 89.63; level above by 79.50 = 0.887 ATR (skip at or under 0.04; bucket >=0.50) -> resistance; order price 8818.50; watch 09:30..15:00
    rth1  vah 8838.00, poc 8821.50, val 8813.00   nearest 3.00 (0.033 ATR)
    rth2  vah 8845.00, poc 8828.50, val 8814.00   nearest 4.50 (0.050 ATR)
    rth3  vah 8857.00, poc 8828.50, val 8806.00   nearest 10.00 (0.112 ATR)
    rth4  vah 8889.00, poc 8828.50, val 8736.00   nearest 10.00 (0.112 ATR)
    rth5  vah 8889.00, poc 8828.50, val 8744.00   nearest 10.00 (0.112 ATR)
    eth1  vah 8856.00, poc 8821.50, val 8797.00   nearest 3.00 (0.033 ATR)
    eth2  vah 8857.00, poc 8818.50*, val 8800.00   nearest 0.00 (0.000 ATR)  <- within 0.03 x ATR
    eth4  vah 8859.00, poc 8818.50*, val 8740.00   nearest 0.00 (0.000 ATR)  <- within 0.03 x ATR
    eth5  vah 8859.00, poc 8828.50, val 8748.00   nearest 10.00 (0.112 ATR)
    rthw  vah 8889.00, poc 8828.50, val 8736.00   nearest 10.00 (0.112 ATR)
    ethw  vah 8859.00, poc 8818.50*, val 8740.00   nearest 0.00 (0.000 ATR)  <- within 0.03 x ATR
    on    vah 8774.00, poc 8747.50, val 8731.00   nearest 44.50 (0.497 ATR)
  stacked count by hand: 3 other profiles with a level within 0.03 x ATR = 2.69 of 8818.50 (events file stack 3, bucket 3+); profiles built that day: 13
  tap bar 10:22 (bucket 1000); highest high of the watch before it 8814.75 (below the order price)
  a04x3: order i=09:29 sell limit 8818.50 stop 8822.00 target 8808.00 (d = 3.50) -> fill 10:22 at 8818.25, exit 10:32 at 8808.25 (TP), pnl +18.00, R +2.400   [events file: R +2.400 TP]
  p20x3: order i=09:29 sell limit 8818.50 stop 8838.50 target 8758.50 (d = 20.00) -> fill 10:22 at 8818.25, exit 14:11 at 8838.75 (SL), pnl -43.00, R -1.062   [events file: R -1.062 SL]
  brk_a04: order i=09:29 buy stop 8818.50 stop 8815.00 target 8829.00 (d = 3.50) -> fill 10:22 at 8818.75, exit 10:22 at 8814.75 (SL), pnl -10.00, R -1.333   [events file: R -1.333 SL]
      10:20  O 8810.50  H 8813.25  L 8808.00  C 8809.25
      10:21  O 8809.25  H 8814.75  L 8809.25  C 8812.50
      10:22  O 8812.50  H 8818.50  L 8812.25  C 8815.00   <- tap
      10:23  O 8815.00  H 8817.75  L 8814.00  C 8816.25
      10:24  O 8816.25  H 8816.75  L 8812.50  C 8813.50
      10:25  O 8813.25  H 8814.75  L 8812.50  C 8814.00
      10:26  O 8814.25  H 8815.25  L 8813.25  C 8813.50
      10:27  O 8813.50  H 8814.50  L 8812.50  C 8813.00
      10:28  O 8812.75  H 8815.00  L 8812.50  C 8814.25
      10:29  O 8814.00  H 8817.75  L 8813.75  C 8817.00
      10:30  O 8816.75  H 8818.00  L 8814.50  C 8814.75
      10:31  O 8815.00  H 8816.75  L 8810.50  C 8811.00
      10:32  O 8811.25  H 8811.25  L 8807.25  C 8807.75   <- exit TP (a04x3)

### 11 a level with no other profile near (count 0): 2021-01-06 (Wed) rth4_val
  level:
    session 2020-12-30 (Wed): 390 bars 12-30 09:30..12-30 15:59, high 12909.75 low 12820.50 volume 398190
    session 2020-12-31 (Thu): 390 bars 12-31 09:30..12-31 15:59, high 12895.50 low 12796.25 volume 312005
    session 2021-01-04 (Mon): 390 bars 01-04 09:30..01-04 15:59, high 12941.25 low 12522.00 volume 779531
    session 2021-01-05 (Tue): 390 bars 01-05 09:30..01-05 15:59, high 12802.00 low 12650.50 volume 591848
    as one profile (Pine transcription, bar by bar): 1560 bars, 420 rows of 1.00 from 12522.00, volume 2081574; POC row 330 [12852.00, 12853.00) holds 20435.6 (next largest 19840.2); value area rows 200..386 hold 1471392.1 = 70.7%; VAH 12909.00 POC 12852.50 VAL 12722.00; contract(s) [6227]
  -> by hand 12722.0000; events file 12722.0000 (same); fixed at 01-05 15:59 (close); from then to 09:29 price ranged 12491.25..12844.50 (starting at 12791.50): traded through the level True; events file crossed True
  09:30 open 12598.00 (bar 09:30 O 12598.00); ATR 189.75; level above by 124.00 = 0.653 ATR (skip at or under 0.04; bucket >=0.50) -> resistance; order price 12722.00; watch 09:30..15:00
    rth1  vah 12772.00, poc 12741.50, val 12707.00   nearest 15.00 (0.079 ATR)
    rth2  vah 12801.00, poc 12728.50, val 12632.00   nearest 6.50 (0.034 ATR)
    rth3  vah 12841.00, poc 12728.50, val 12612.00   nearest 6.50 (0.034 ATR)
    rth5  vah 12917.00, poc 12852.50, val 12738.00   nearest 16.00 (0.084 ATR)
    eth1  vah 12780.00, poc 12741.50, val 12693.00   nearest 19.50 (0.103 ATR)
    eth2  vah 12801.00, poc 12728.50, val 12612.00   nearest 6.50 (0.034 ATR)
    eth3  vah 12907.00, poc 12846.50, val 12696.00   nearest 26.00 (0.137 ATR)
    eth4  vah 12907.00, poc 12852.50, val 12712.00   nearest 10.00 (0.053 ATR)
    eth5  vah 12917.00, poc 12852.50, val 12730.00   nearest 8.00 (0.042 ATR)
    rthw  vah 12871.00, poc 12852.50, val 12818.00   nearest 96.00 (0.506 ATR)
    ethw  vah 12877.00, poc 12852.50, val 12814.00   nearest 92.00 (0.485 ATR)
    on    vah 12658.00, poc 12629.50, val 12527.00   nearest 64.00 (0.337 ATR)
  stacked count by hand: 0 other profiles with a level within 0.03 x ATR = 5.69 of 12722.00 (events file stack 0, bucket 0); profiles built that day: 13
  tap bar 10:34 (bucket 1000); highest high of the watch before it 12719.50 (below the order price)
  a04x3: order i=09:29 sell limit 12722.00 stop 12729.50 target 12699.50 (d = 7.50) -> fill 10:34 at 12721.75, exit 10:38 at 12729.75 (SL), pnl -18.00, R -1.161   [events file: R -1.161 SL]
  p20x3: order i=09:29 sell limit 12722.00 stop 12742.00 target 12662.00 (d = 20.00) -> fill 10:34 at 12721.75, exit 10:45 at 12742.25 (SL), pnl -43.00, R -1.062   [events file: R -1.062 SL]
  brk_a04: order i=09:29 buy stop 12722.00 stop 12714.50 target 12744.50 (d = 7.50) -> fill 10:34 at 12722.25, exit 10:46 at 12744.25 (TP), pnl +42.00, R +2.710   [events file: R +2.710 TP]
      10:32  O 12711.00  H 12718.75  L 12709.25  C 12717.75
      10:33  O 12717.75  H 12719.50  L 12713.25  C 12715.00
      10:34  O 12714.75  H 12724.25  L 12713.75  C 12716.25   <- tap
      10:35  O 12716.50  H 12721.75  L 12716.00  C 12718.25
      10:36  O 12718.25  H 12725.25  L 12714.75  C 12718.75
      10:37  O 12719.00  H 12723.00  L 12715.75  C 12722.00
      10:38  O 12722.25  H 12734.00  L 12718.50  C 12733.00   <- exit SL (a04x3)

### 12 the `on` profile: 2022-09-26 (Mon) on_val
  level:
    session 2022-09-26 (Mon): 930 bars 09-25 18:00..09-26 09:29, high 11422.25 low 11256.50 volume 509071
    as one profile (Pine transcription, bar by bar): 930 bars, 167 rows of 1.00 from 11256.00, volume 509071; POC row 58 [11314.00, 11315.00) holds 5921.9 (next largest 5799.6); value area rows 38..114 hold 356428.8 = 70.0%; VAH 11371.00 POC 11314.50 VAL 11294.00; contract(s) [20332]
  -> by hand 11294.0000; events file 11294.0000 (same); fixed at 09-26 09:29 (close); from then to 09:29 price ranged 11352.75..11352.75 (starting at 11352.75): traded through the level False; events file crossed False
  09:30 open 11352.50 (bar 09:30 O 11352.50); ATR 325.67; level below by 58.50 = 0.180 ATR (skip at or under 0.04; bucket 0.10-0.25) -> support; order price 11294.00; watch 09:30..15:00
  tap bar 13:59 (bucket 1130); lowest low of the watch before it 11300.25 (above the order price)
  a04x3: order i=09:29 buy limit 11294.00 stop 11281.00 target 11333.00 (d = 13.00) -> fill 13:59 at 11294.25, exit 14:02 at 11332.75 (TP), pnl +75.00, R +2.830   [events file: R +2.830 TP]
  p20x3: order i=09:29 buy limit 11294.00 stop 11274.00 target 11354.00 (d = 20.00) -> fill 13:59 at 11294.25, exit 14:04 at 11353.75 (TP), pnl +117.00, R +2.889   [events file: R +2.889 TP]
  brk_a04: order i=09:29 sell stop 11294.00 stop 11307.00 target 11255.00 (d = 13.00) -> fill 13:59 at 11293.75, exit 14:00 at 11307.25 (SL), pnl -29.00, R -1.094   [events file: R -1.094 SL]
      13:57  O 11325.50  H 11330.75  L 11317.50  C 11318.00
      13:58  O 11317.75  H 11319.25  L 11306.00  C 11310.00
      13:59  O 11309.75  H 11311.00  L 11293.25  C 11298.25   <- tap
      14:00  O 11298.50  H 11311.50  L 11293.75  C 11306.75
      14:01  O 11307.00  H 11328.25  L 11306.75  C 11326.00
      14:02  O 11325.75  H 11345.75  L 11325.50  C 11342.00   <- exit TP (a04x3)

### 13 a profile placebo: 2021-07-15 (Thu) rth3_val~.+ (placebo)
  level:
    session 2021-07-12 (Mon): 390 bars 07-12 09:30..07-12 15:59, high 14888.75 low 14802.25 volume 424216
    session 2021-07-13 (Tue): 390 bars 07-13 09:30..07-13 15:59, high 14994.50 low 14833.75 volume 612912
    session 2021-07-14 (Wed): 390 bars 07-14 09:30..07-14 15:59, high 14996.00 low 14862.00 volume 628191
    as one profile (Pine transcription, bar by bar): 1170 bars, 195 rows of 1.00 from 14802.00, volume 1665319; POC row 151 [14953.00, 14954.00) holds 13260.8 (next largest 13188.5); value area rows 45..165 hold 1179896.8 = 70.9%; VAH 14968.00 POC 14953.50 VAL 14847.00; contract(s) [3601]
    parent rth3_val = 14847.00; placebo = parent + 0.12 x ATR (20.42)
  -> by hand 14867.4169; events file 14867.4169 (same); fixed at 07-14 16:59 (close); from then to 09:29 price ranged 14864.00..14962.50 (starting at 14894.50): traded through the level True; events file crossed True
  09:30 open 14893.00 (bar 09:30 O 14893.00); ATR 170.14; level below by 25.58 = 0.150 ATR (skip at or under 0.04; bucket 0.10-0.25) -> support; order price 14867.25; watch 09:30..15:00
  tap bar 09:31 (bucket 0930); lowest low of the watch before it 14878.75 (above the order price)
  a04x3: order i=09:29 buy limit 14867.25 stop 14860.50 target 14887.50 (d = 6.75) -> fill 09:31 at 14867.50, exit 09:31 at 14860.25 (SL), pnl -16.50, R -1.179   [events file: R -1.179 SL]
  p20x3: order i=09:29 buy limit 14867.25 stop 14847.25 target 14927.25 (d = 20.00) -> fill 09:31 at 14867.50, exit 09:34 at 14847.00 (SL), pnl -43.00, R -1.062   [events file: R -1.062 SL]
  brk_a04: order i=09:29 sell stop 14867.25 stop 14874.00 target 14847.00 (d = 6.75) -> fill 09:31 at 14867.00, exit 09:32 at 14874.25 (SL), pnl -16.50, R -1.179   [events file: R -1.179 SL]
      09:29  O 14896.75  H 14897.00  L 14888.75  C 14893.00
      09:30  O 14893.00  H 14902.00  L 14878.75  C 14882.75
      09:31  O 14882.75  H 14887.25  L 14856.25  C 14858.25   <- tap

### 14 a midnight placebo: 2019-09-13 (Fri) o00~.- (placebo)
  level:
    first bar at or after 09-13 00:00: the bar stamped 09-13 00:00, open 7935.00
    parent o00 = 7935.00; placebo = parent - 0.12 x ATR (16.48)
  -> by hand 7918.5192; events file 7918.5192 (same); fixed at 09-13 00:00 (open); from then to 09:29 price ranged 7906.50..7958.25 (starting at 7935.00): traded through the level True; events file crossed True
  09:30 open 7909.00 (bar 09:30 O 7909.00); ATR 137.34; level above by 9.52 = 0.069 ATR (skip at or under 0.04; bucket <0.10) -> resistance; order price 7918.75; watch 09:30..15:00
  tap bar 09:53 (bucket 0930); highest high of the watch before it 7918.25 (below the order price)
  a04x3: order i=09:29 sell limit 7918.75 stop 7924.25 target 7902.25 (d = 5.50) -> fill 09:53 at 7918.50, exit 09:58 at 7902.50 (TP), pnl +30.00, R +2.609   [events file: R +2.609 TP]
  p20x3: order i=09:29 sell limit 7918.75 stop 7938.75 target 7858.75 (d = 20.00) -> fill 09:53 at 7918.50, exit 15:59 at 7893.50 (time), pnl +48.00, R +1.185   [events file: R +1.185 time]
  brk_a04: order i=09:29 buy stop 7918.75 stop 7913.25 target 7935.25 (d = 5.50) -> fill 09:53 at 7919.00, exit 09:55 at 7913.00 (SL), pnl -14.00, R -1.217   [events file: R -1.217 SL]
      09:51  O 7915.50  H 7918.00  L 7913.50  C 7916.75
      09:52  O 7916.75  H 7918.25  L 7915.25  C 7915.25
      09:53  O 7915.25  H 7919.75  L 7914.25  C 7919.50   <- tap
      09:54  O 7919.75  H 7921.00  L 7916.25  C 7916.50
      09:55  O 7916.00  H 7916.50  L 7911.50  C 7915.25
      09:56  O 7915.50  H 7915.50  L 7909.50  C 7909.50
      09:57  O 7909.75  H 7909.75  L 7903.00  C 7905.75
      09:58  O 7905.75  H 7906.00  L 7898.25  C 7902.50   <- exit TP (a04x3)

### 15 a level that is never tapped: 2021-05-11 (Tue) rth2_poc
  level:
    session 2021-05-07 (Fri): 390 bars 05-07 09:30..05-07 15:59, high 13810.50 low 13661.75 volume 742695
    session 2021-05-10 (Mon): 390 bars 05-10 09:30..05-10 15:59, high 13657.75 low 13352.25 volume 860700
    as one profile (Pine transcription, bar by bar): 780 bars, 459 rows of 1.00 from 13352.00, volume 1603395; POC row 375 [13727.00, 13728.00) holds 9979.1 (next largest 9803.4); value area rows 151..458 hold 1131852.0 = 70.6%; VAH 13811.00 POC 13727.50 VAL 13503.00; contract(s) [9485]
  -> by hand 13727.5000; events file 13727.5000 (same); fixed at 05-10 15:59 (close); from then to 09:29 price ranged 13065.50..13368.25 (starting at 13356.25): traded through the level False; events file crossed False
  09:30 open 13113.75 (bar 09:30 O 13113.75); ATR 239.04; level above by 613.75 = 2.568 ATR (skip at or under 0.04; bucket >=0.50) -> resistance; order price 13727.50; watch 09:30..15:00
  never tapped: highest high of the watch 13375.75, lowest low 13083.75

### 16 a level skipped as too near the open: 2019-11-13 (Wed) o00
  level:
    first bar at or after 11-13 00:00: the bar stamped 11-13 00:00, open 8247.00
  -> by hand 8247.0000; events file 8247.0000 (same); fixed at 11-13 00:00 (open); from then to 09:29 price ranged 8220.00..8262.75 (starting at 8247.00): traded through the level True; events file crossed True
  09:30 open 8243.50 (bar 09:30 O 8243.50); ATR 95.16; level above by 3.50 = 0.037 ATR (skip at or under 0.04; bucket <0.10) -> resistance SKIPPED; order price 8247.00; watch 09:30..15:00

### 17 VA-trend long (open above all five value areas): 2021-07-02 (Fri)
    rth1: sessions 2021-07-01..2021-07-01 (1), 390 bars, volume 457542: VAH 14556.00 POC 14543.50 VAL 14507.00   [day-types file: VAH 14556.00 VAL 14507.00]
    rth2: sessions 2021-06-30..2021-07-01 (2), 780 bars, volume 883175: VAH 14562.00 POC 14547.50 VAL 14527.00   [day-types file: VAH 14562.00 VAL 14527.00]
    rth3: sessions 2021-06-29..2021-07-01 (3), 1170 bars, volume 1308169: VAH 14562.00 POC 14547.50 VAL 14515.00   [day-types file: VAH 14562.00 VAL 14515.00]
    rth4: sessions 2021-06-28..2021-07-01 (4), 1560 bars, volume 1687985: VAH 14562.00 POC 14547.50 VAL 14497.00   [day-types file: VAH 14562.00 VAL 14497.00]
    rth5: sessions 2021-06-25..2021-07-01 (5), 1950 bars, volume 2166932: VAH 14566.00 POC 14547.50 VAL 14465.00   [day-types file: VAH 14566.00 VAL 14465.00]
  09:30 open 14629.50; highest VAH 14566.00, lowest VAL 14465.00 -> by hand 'above' (day-types file 'above'); ATR 170.85, R unit 0.1 x ATR = 17.09 points
  order: i = 09:29 (the last bar before 09:30), buy at the next open, no stop, flat bar 15:59 -> fill 09:30 at 14629.75 (open 14629.50 + 1 tick), exit 15:59 at 14714.50 (close 14714.75 - 1 tick, time), pnl +167.50, R = pnl / (0.1 x ATR x $2) = +4.9019   [day-types file: side L R +4.9019 pnl +167.50; move_up +0.4990 ATR]
      09:29  O 14631.50  H 14633.75  L 14629.25  C 14629.25
      09:30  O 14629.50  H 14637.50  L 14625.75  C 14628.00
      09:31  O 14627.50  H 14636.00  L 14619.25  C 14632.75
      ...
      15:59  O 14713.50  H 14717.25  L 14710.00  C 14714.75
  ORB v1.4 that day: no trade

### 18 VA-trend short (open below all five): 2022-05-12 (Thu)
    rth1: sessions 2022-05-11..2022-05-11 (1), 390 bars, volume 1504579: VAH 12443.00 POC 12280.50 VAL 12102.00   [day-types file: VAH 12443.00 VAL 12102.00]
    rth2: sessions 2022-05-10..2022-05-11 (2), 780 bars, volume 3187144: VAH 12469.00 POC 12280.50 VAL 12190.00   [day-types file: VAH 12469.00 VAL 12190.00]
    rth3: sessions 2022-05-09..2022-05-11 (3), 1170 bars, volume 4499571: VAH 12469.00 POC 12286.50 VAL 12222.00   [day-types file: VAH 12469.00 VAL 12222.00]
    rth4: sessions 2022-05-06..2022-05-11 (4), 1560 bars, volume 6058135: VAH 12633.00 POC 12286.50 VAL 12148.00   [day-types file: VAH 12633.00 VAL 12148.00]
    rth5: sessions 2022-05-05..2022-05-11 (5), 1950 bars, volume 7576770: VAH 12791.00 POC 12286.50 VAL 12148.00   [day-types file: VAH 12791.00 VAL 12148.00]
  09:30 open 11790.75; highest VAH 12791.00, lowest VAL 12102.00 -> by hand 'below' (day-types file 'below'); ATR 479.39, R unit 0.1 x ATR = 47.94 points
  order: i = 09:29 (the last bar before 09:30), sell at the next open, no stop, flat bar 15:59 -> fill 09:30 at 11790.50 (open 11790.75 - 1 tick), exit 15:59 at 11948.25 (close 11948.00 + 1 tick, time), pnl -317.50, R = pnl / (0.1 x ATR x $2) = -3.3115   [day-types file: side S R -3.3115 pnl -317.50; move_up +0.3280 ATR]
      09:29  O 11795.00  H 11796.50  L 11784.25  C 11791.50
      09:30  O 11790.75  H 11852.25  L 11784.25  C 11850.00
      09:31  O 11850.00  H 11874.75  L 11841.00  C 11842.00
      ...
      15:59  O 11947.50  H 11956.75  L 11932.00  C 11948.00
  ORB v1.4 that day: L R -1.006 pnl -438.50
```


## 7. Reconciliation (`python3 tools/yt1/run.py L2 --phase is`, then `python3 tools/yt1/s_L2.py --recon`)

Every variant's trades as saved by the standard runner against (a) the events file (or the day-types file for
VA-trend), trade by trade (sorted P&L and R), and (b) the table row (events, net $, mean R):

```
L2 base     o00            a04x3     run.py: n  461 net    -657.00 R  -0.0947 | events file: n  461 net    -657.00 R  -0.0947 -> same | table (MID1_levels): n 461 net -657.00 R -0.0947 -> same
L2 nb1      o00            a08x3     run.py: n  461 net    +614.00 R  -0.0137 | events file: n  461 net    +614.00 R  -0.0137 -> same | table (MID1_levels): n 461 net +614.00 R -0.0137 -> same
L2 nb2      o00            a04x2     run.py: n  461 net    -250.50 R  -0.0617 | events file: n  461 net    -250.50 R  -0.0617 -> same | table (MID1_levels): n 461 net -250.50 R -0.0617 -> same
L2 mb       o00 bias with  a04x3     run.py: n  194 net    -401.50 R  -0.0888 | events file: n  194 net    -401.50 R  -0.0888 -> same | table (MID1_splits): n 194 net -401.50 R -0.0888 -> same
L2 mb_nb1   o00 bias with  a08x3     run.py: n  194 net    +447.50 R  +0.0342 | events file: n  194 net    +447.50 R  +0.0342 -> same | table (MID1_splits): n 194 net +447.50 R +0.0342 -> same
L2 mb_nb2   o00 bias with  a04x2     run.py: n  194 net     -13.00 R  -0.0038 | events file: n  194 net     -13.00 R  -0.0038 -> same | table (MID1_splits): n 194 net -13.00 R -0.0038 -> same
L2 p1       eth1_val:S     brk_a04   run.py: n  209 net    +740.00 R  +0.2123 | events file: n  209 net    +740.00 R  +0.2123 -> same | table (VPN1_reaction): n 209 net +740.00 R +0.2123 -> same
L2 p1_nb1   eth1_val:S     brk_a08   run.py: n  209 net    +394.50 R  +0.0132 | events file: n  209 net    +394.50 R  +0.0132 -> same | table (VPN1_reaction): n 209 net +394.50 R +0.0132 -> same
L2 p1_nb2   eth1_val:S     brk_a04x2 run.py: n  209 net    +881.50 R  +0.1543 | events file: n  209 net    +881.50 R  +0.1543 -> same | table (VPN1_reaction): n 209 net +881.50 R +0.1543 -> same
L2 p2       rth3_val:S     brk_a04   run.py: n  154 net    +269.50 R  +0.1940 | events file: n  154 net    +269.50 R  +0.1940 -> same | table (VPN1_reaction): n 154 net +269.50 R +0.1940 -> same
L2 p2_nb1   rth3_val:S     brk_a08   run.py: n  154 net    +506.50 R  +0.1177 | events file: n  154 net    +506.50 R  +0.1177 -> same | table (VPN1_reaction): n 154 net +506.50 R +0.1177 -> same
L2 p2_nb2   rth3_val:S     brk_a04x2 run.py: n  154 net    -187.00 R  -0.0061 | events file: n  154 net    -187.00 R  -0.0061 -> same | table (VPN1_reaction): n 154 net -187.00 R -0.0061 -> same
L2 p3       on_poc:S       brk_a04   run.py: n  206 net    +199.00 R  +0.0354 | events file: n  206 net    +199.00 R  +0.0354 -> same | table (VPN1_reaction): n 206 net +199.00 R +0.0354 -> same
L2 p3_nb1   on_poc:S       brk_a08   run.py: n  206 net   +1599.50 R  +0.1942 | events file: n  206 net   +1599.50 R  +0.1942 -> same | table (VPN1_reaction): n 206 net +1599.50 R +0.1942 -> same
L2 p3_nb2   on_poc:S       brk_a04x2 run.py: n  206 net    -425.50 R  -0.1151 | events file: n  206 net    -425.50 R  -0.1151 -> same | table (VPN1_reaction): n 206 net -425.50 R -0.1151 -> same
L2 p4       rth2_poc:S     brk_a04   run.py: n  173 net    +412.50 R  +0.0052 | events file: n  173 net    +412.50 R  +0.0052 -> same | table (VPN1_reaction): n 173 net +412.50 R +0.0052 -> same
L2 p4_nb1   rth2_poc:S     brk_a08   run.py: n  173 net   +1720.00 R  +0.0638 | events file: n  173 net   +1720.00 R  +0.0638 -> same | table (VPN1_reaction): n 173 net +1720.00 R +0.0638 -> same
L2 p4_nb2   rth2_poc:S     brk_a04x2 run.py: n  173 net    -313.00 R  -0.1642 | events file: n  173 net    -313.00 R  -0.1642 -> same | table (VPN1_reaction): n 173 net -313.00 R -0.1642 -> same
L2 p5       rth3_poc:S     a04x3     run.py: n  150 net     +50.00 R  +0.0000 | events file: n  150 net     +50.00 R  +0.0000 -> same | table (VPN1_reaction): n 150 net +50.00 R +0.0000 -> same
L2 p5_nb1   rth3_poc:S     a08x3     run.py: n  150 net    -427.00 R  -0.0730 | events file: n  150 net    -427.00 R  -0.0730 -> same | table (VPN1_reaction): n 150 net -427.00 R -0.0730 -> same
L2 p5_nb2   rth3_poc:S     a04x2     run.py: n  150 net     +56.00 R  +0.0062 | events file: n  150 net     +56.00 R  +0.0062 -> same | table (VPN1_reaction): n 150 net +56.00 R +0.0062 -> same
L2 p6       stack 3+       brk_a04   run.py: n 4522 net   +1803.50 R  +0.0082 | events file: n 4522 net   +1803.50 R  +0.0082 -> same | table (VPN1_stacked): n 4522 net +1803.50 R +0.0082 -> same
L2 p6_nb1   stack 3+       brk_a08   run.py: n 4522 net  +27083.50 R  +0.1284 | events file: n 4522 net  +27083.50 R  +0.1284 -> same | table (VPN1_stacked): n 4522 net +27083.50 R +0.1284 -> same
L2 p6_nb2   stack 3+       brk_a04x2 run.py: n 4522 net   -1931.00 R  -0.0460 | events file: n 4522 net   -1931.00 R  -0.0460 -> same | table (VPN1_stacked): n 4522 net -1931.00 R -0.0460 -> same
L2 p7       aligned POC    a04x3     run.py: n  102 net    +259.00 R  +0.1232 | events file: n  102 net    +259.00 R  +0.1232 -> same | table (VPN1_stacked): n 102 net +259.00 R +0.1232 -> same
L2 p7_nb1   aligned POC    a08x3     run.py: n  102 net    +959.50 R  +0.0980 | events file: n  102 net    +959.50 R  +0.0980 -> same | table (VPN1_stacked): n 102 net +959.50 R +0.0980 -> same
L2 p7_nb2   aligned POC    a04x2     run.py: n  102 net    +277.00 R  +0.0671 | events file: n  102 net    +277.00 R  +0.0671 -> same | table (VPN1_stacked): n 102 net +277.00 R +0.0671 -> same
L2 p8       VA-trend rth            run.py: n  286 net  -11493.50 R  -0.6743 | events file: n  286 net  -11493.50 R  -0.6743 -> same | table (vatrend.json): n 286 net -11493.50 R -0.6743 -> same
L2 p8_nb1   VA-trend eth            run.py: n  268 net  -10270.00 R  -0.7667 | events file: n  268 net  -10270.00 R  -0.7667 -> same | table (vatrend.json): n 268 net -10270.00 R -0.7667 -> same
L2 p8_nb2   VA-trend rth3           run.py: n  365 net  -12455.50 R  -0.6882 | events file: n  365 net  -12455.50 R  -0.6882 -> same | table (vatrend.json): n 365 net -12455.50 R -0.6882 -> same
L2 chk1     o03            a04x3     run.py: n  473 net   -1352.00 R  -0.1864 | events file: n  473 net   -1352.00 R  -0.1864 -> same | table (MID1_levels): n 473 net -1352.00 R -0.1863 -> same
L2 chk2     o00~           a04x3     run.py: n  386 net   -1935.50 R  -0.2565 | events file: n  386 net   -1935.50 R  -0.2565 -> same | table (MID1_levels): n 386 net -1935.50 R -0.2565 -> same
L2 chk3     rth3_poc:R     a04x3     run.py: n  133 net    +278.50 R  +0.0176 | events file: n  133 net    +278.50 R  +0.0176 -> same | table (VPN1_reaction): n 133 net +278.50 R +0.0176 -> same
L2 chk4     eth5_val:S     a04x3     run.py: n  112 net    -327.50 R  -0.2365 | events file: n  112 net    -327.50 R  -0.2365 -> same | table (VPN1_reaction): n 112 net -327.50 R -0.2365 -> same
L2 chk5     rthw_vah:R     a04x3     run.py: n   84 net    -586.00 R  -0.4145 | events file: n   84 net    -586.00 R  -0.4145 -> same | table (VPN1_reaction): n 84 net -586.00 R -0.4145 -> same
L2 chk6     on_poc:S       a04x3     run.py: n  206 net    -855.00 R  -0.2467 | events file: n  206 net    -855.00 R  -0.2467 -> same | table (VPN1_reaction): n 206 net -855.00 R -0.2467 -> same
L2 chk7     aligned POC    a04x3     run.py: n  102 net    +259.00 R  +0.1232 | events file: n  102 net    +259.00 R  +0.1232 -> same | table (VPN1_stacked): n 102 net +259.00 R +0.1232 -> same
L2 chk8     stack 2        a04x3     run.py: n 1560 net   -5270.50 R  -0.2160 | events file: n 1560 net   -5270.50 R  -0.2160 -> same | table (VPN1_stacked): n 1560 net -5270.50 R -0.2160 -> same
L2 chk9     eth2_vah:R     brk_a04   run.py: n  165 net     +92.50 R  -0.0272 | events file: n  165 net     +92.50 R  -0.0272 -> same | table (VPN1_reaction): n 165 net +92.50 R -0.0272 -> same
L2 chk10    VA-trend rth            run.py: n  286 net  -11493.50 R  -0.6743 | events file: n  286 net  -11493.50 R  -0.6743 -> same | table (vatrend.json): n 286 net -11493.50 R -0.6743 -> same
L2 chk11    VA-trend eth            run.py: n  268 net  -10270.00 R  -0.7667 | events file: n  268 net  -10270.00 R  -0.7667 -> same | table (vatrend.json): n 268 net -10270.00 R -0.7667 -> same
L2 chk12    VA-trend rth3           run.py: n  365 net  -12455.50 R  -0.6882 | events file: n  365 net  -12455.50 R  -0.6882 -> same | table (vatrend.json): n 365 net -12455.50 R -0.6882 -> same
L2 chk13    o00            p20x3     run.py: n  461 net    -413.00 R  -0.0221 | events file: n  461 net    -413.00 R  -0.0221 -> same | table (MID1_levels): n 461 net -413.00 R -0.0221 -> same
L2 chk14    o00 bias against a04x3     run.py: n  194 net    -108.00 R  -0.0559 | events file: n  194 net    -108.00 R  -0.0559 -> same | table (MID1_splits): n 194 net -108.00 R -0.0559 -> same
L2 chk15    rthw_val:S     brk_a04x2 run.py: n   73 net    -630.00 R  -0.3898 | events file: n   73 net    -630.00 R  -0.3898 -> same | table (VPN1_reaction): n 73 net -630.00 R -0.3898 -> same
L2 chk16    o00            brk_a04   run.py: n  461 net   -2919.50 R  -0.2566 | events file: n  461 net   -2919.50 R  -0.2566 -> same | table (MID1_levels): n 461 net -2919.50 R -0.2566 -> same
reconciliation: 46 variants, 0 differ -> OK
```


The runner's own lines (its `win` is "net > 0", the tables' is "target reached"; its p is the bootstrap on the rows,
see reading 6 for p6; its `verdict` line on a full run is YT1's usual criterion on base / nb1 / nb2 and is NOT the
registered MID1 verdict, which has its own p level, the placebo condition and is printed by `lev2_tables.py
--phase full`):

```
L2  YT10: first tap of the midnight open / volume-profile levels after the open, and VA-trend   phase is   bars 2019-06-02 18:00:00-04:00 -> 2022-12-30 16:59:00-05:00
base                   n   461  net      -657  R  -0.095  win  26.9  pf  0.92  dd    -1298  p 0.8763  yrs+ 0/4  h1 -0.095 h2 +nan  | -232 -188 -26 -210 +0 +0 +0 +0   [2s]
                     sig_time                entry_time                 exit_time side     entry      stop      exit   pnl         R reason               tag
103 2020-05-01 09:29:00-04:00 2020-05-01 09:31:00-04:00 2020-05-01 09:32:00-04:00    S   8814.50   8828.25   8828.50 -30.0 -1.090909     SL  o00|R|2020-05-01
107 2020-05-13 09:29:00-04:00 2020-05-13 09:34:00-04:00 2020-05-13 09:34:00-04:00    L   9087.50   9075.75   9075.50 -26.0 -1.106383     SL  o00|S|2020-05-13
164 2020-10-15 09:29:00-04:00 2020-10-15 09:53:00-04:00 2020-10-15 10:03:00-04:00    S  11877.00  11889.50  11840.75  70.5  2.820000     TP  o00|R|2020-10-15
190 2020-12-18 09:29:00-05:00 2020-12-18 09:52:00-05:00 2020-12-18 09:53:00-05:00    L  12726.50  12718.50  12718.25 -18.5 -1.156250     SL  o00|S|2020-12-18
370 2022-04-27 09:29:00-04:00 2022-04-27 09:30:00-04:00 2022-04-27 09:32:00-04:00    S  13065.75  13083.00  13083.25 -37.0 -1.072464     SL  o00|R|2022-04-27
381 2022-05-20 09:29:00-04:00 2022-05-20 09:35:00-04:00 2022-05-20 09:36:00-04:00    L  11981.75  11962.50  11962.25 -41.0 -1.064935     SL  o00|S|2022-05-20
nb1                    n   461  net      +614  R  -0.014  win  27.1  pf  1.04  dd    -1442  p 0.5646  yrs+ 3/4  h1 -0.014 h2 +nan  | -373 +482 +50 +454 +0 +0 +0 +0   [0s]
nb2                    n   461  net      -250  R  -0.062  win  36.9  pf  0.96  dd     -735  p 0.8252  yrs+ 1/4  h1 -0.062 h2 +nan  | -220 -284 +284 -30 +0 +0 +0 +0   [0s]
mb                     n   194  net      -402  R  -0.089  win  26.8  pf  0.89  dd     -564  p 0.7571  yrs+ 1/4  h1 -0.089 h2 +nan  | -52 -290 +124 -184 +0 +0 +0 +0   [0s]
mb_nb1                 n   194  net      +448  R  +0.034  win  28.4  pf  1.07  dd    -1090  p 0.3991  yrs+ 2/4  h1 +0.034 h2 +nan  | -182 +330 +694 -394 +0 +0 +0 +0   [0s]
mb_nb2                 n   194  net       -13  R  -0.004  win  38.7  pf  1.00  dd     -339  p 0.5101  yrs+ 1/4  h1 -0.004 h2 +nan  | -22 -235 +288 -44 +0 +0 +0 +0   [0s]
p1                     n   209  net      +740  R  +0.212  win  34.9  pf  1.22  dd     -478  p 0.0476  yrs+ 3/4  h1 +0.212 h2 +nan  | +179 -69 +306 +324 +0 +0 +0 +0   [1s]
p1_nb1                 n   209  net      +394  R  +0.013  win  27.8  pf  1.06  dd    -1270  p 0.4672  yrs+ 2/4  h1 +0.013 h2 +nan  | +71 -342 -265 +930 +0 +0 +0 +0   [0s]
p1_nb2                 n   209  net      +882  R  +0.154  win  44.5  pf  1.32  dd     -400  p 0.0631  yrs+ 4/4  h1 +0.154 h2 +nan  | +83 +122 +51 +626 +0 +0 +0 +0   [0s]
p2                     n   154  net      +270  R  +0.194  win  34.4  pf  1.11  dd     -637  p 0.0948  yrs+ 2/4  h1 +0.194 h2 +nan  | -79 +228 +390 -270 +0 +0 +0 +0   [1s]
p2_nb1                 n   154  net      +506  R  +0.118  win  30.5  pf  1.10  dd     -883  p 0.2038  yrs+ 3/4  h1 +0.118 h2 +nan  | +74 -320 +118 +634 +0 +0 +0 +0   [0s]
p2_nb2                 n   154  net      -187  R  -0.006  win  39.0  pf  0.92  dd     -496  p 0.5246  yrs+ 2/4  h1 -0.006 h2 +nan  | -132 +14 +215 -284 +0 +0 +0 +0   [0s]
p3                     n   206  net      +199  R  +0.035  win  30.1  pf  1.06  dd     -573  p 0.3853  yrs+ 3/4  h1 +0.035 h2 +nan  | -74 +214 +14 +46 +0 +0 +0 +0   [1s]
p3_nb1                 n   206  net     +1600  R  +0.194  win  32.0  pf  1.25  dd     -752  p 0.0601  yrs+ 3/4  h1 +0.194 h2 +nan  | +150 +1083 -98 +464 +0 +0 +0 +0   [0s]
p3_nb2                 n   206  net      -426  R  -0.115  win  35.0  pf  0.87  dd     -544  p 0.8775  yrs+ 1/4  h1 -0.115 h2 +nan  | -146 -134 +66 -212 +0 +0 +0 +0   [0s]
p4                     n   173  net      +412  R  +0.005  win  29.5  pf  1.14  dd     -394  p 0.4837  yrs+ 2/4  h1 +0.005 h2 +nan  | -80 +116 -42 +419 +0 +0 +0 +0   [1s]
p4_nb1                 n   173  net     +1720  R  +0.064  win  28.9  pf  1.33  dd     -948  p 0.3161  yrs+ 2/4  h1 +0.064 h2 +nan  | -256 +280 -414 +2110 +0 +0 +0 +0   [0s]
p4_nb2                 n   173  net      -313  R  -0.164  win  33.5  pf  0.88  dd     -521  p 0.9354  yrs+ 1/4  h1 -0.164 h2 +nan  | -136 -111 -170 +104 +0 +0 +0 +0   [0s]
p5                     n   150  net       +50  R  +0.000  win  29.3  pf  1.02  dd     -286  p 0.4970  yrs+ 2/4  h1 +0.000 h2 +nan  | -112 +169 +50 -56 +0 +0 +0 +0   [1s]
p5_nb1                 n   150  net      -427  R  -0.073  win  25.3  pf  0.92  dd    -1220  p 0.6906  yrs+ 2/4  h1 -0.073 h2 +nan  | -131 +365 +260 -921 +0 +0 +0 +0   [0s]
p5_nb2                 n   150  net       +56  R  +0.006  win  39.3  pf  1.02  dd     -358  p 0.4739  yrs+ 1/4  h1 +0.006 h2 +nan  | -30 +184 -2 -96 +0 +0 +0 +0   [0s]
p6                     n  4522  net     +1804  R  +0.008  win  29.7  pf  1.02  dd    -5096  p 0.3755  yrs+ 1/4  h1 +0.008 h2 +nan  | -716 -695 -1338 +4552 +0 +0 +0 +0   [10s]
p6_nb1                 n  4522  net    +27084  R  +0.128  win  31.2  pf  1.19  dd    -6832  p 0.0000  yrs+ 3/4  h1 +0.128 h2 +nan  | +444 +3400 -2300 +25538 +0 +0 +0 +0   [4s]
p6_nb2                 n  4522  net     -1931  R  -0.046  win  37.7  pf  0.97  dd    -6810  p 0.9837  yrs+ 1/4  h1 -0.046 h2 +nan  | -1648 -3046 -1211 +3975 +0 +0 +0 +0   [4s]
p7                     n   102  net      +259  R  +0.123  win  32.4  pf  1.15  dd     -256  p 0.2360  yrs+ 3/4  h1 +0.123 h2 +nan  | -14 +87 +72 +114 +0 +0 +0 +0   [1s]
p7_nb1                 n   102  net      +960  R  +0.098  win  29.4  pf  1.31  dd     -702  p 0.2939  yrs+ 2/4  h1 +0.098 h2 +nan  | -104 +932 +162 -30 +0 +0 +0 +0   [0s]
p7_nb2                 n   102  net      +277  R  +0.067  win  41.2  pf  1.19  dd     -256  p 0.3127  yrs+ 2/4  h1 +0.067 h2 +nan  | -48 +330 -74 +68 +0 +0 +0 +0   [0s]
p8                     n   286  net    -11494  R  -0.674  win  52.1  pf  0.70  dd   -12292  p 0.9805  yrs+ 1/4  h1 -0.674 h2 +nan  | +304 -4001 -1954 -5843 +0 +0 +0 +0   [0s]
p8_nb1                 n   268  net    -10270  R  -0.767  win  51.9  pf  0.72  dd   -11338  p 0.9869  yrs+ 1/4  h1 -0.767 h2 +nan  | +28 -4031 -2266 -4002 +0 +0 +0 +0   [0s]
p8_nb2                 n   365  net    -12456  R  -0.688  win  51.5  pf  0.74  dd   -14377  p 0.9887  yrs+ 1/4  h1 -0.688 h2 +nan  | +82 -6726 -3091 -2721 +0 +0 +0 +0   [0s]
chk1                   n   473  net     -1352  R  -0.186  win  24.5  pf  0.84  dd    -1544  p 0.9919  yrs+ 0/4  h1 -0.186 h2 +nan  | -328 -104 -297 -623 +0 +0 +0 +0   [1s]
chk2                   n   386  net     -1936  R  -0.257  win  22.8  pf  0.73  dd    -2036  p 0.9990  yrs+ 0/4  h1 -0.257 h2 +nan  | -142 -722 -554 -516 +0 +0 +0 +0   [1s]
chk3                   n   133  net      +278  R  +0.018  win  29.3  pf  1.12  dd     -272  p 0.4711  yrs+ 2/4  h1 +0.018 h2 +nan  | -138 +150 -36 +302 +0 +0 +0 +0   [0s]
chk4                   n   112  net      -328  R  -0.236  win  23.2  pf  0.84  dd     -764  p 0.9316  yrs+ 1/4  h1 -0.236 h2 +nan  | -77 -302 -312 +364 +0 +0 +0 +0   [1s]
chk5                   n    84  net      -586  R  -0.414  win  19.0  pf  0.63  dd     -964  p 0.9915  yrs+ 1/4  h1 -0.414 h2 +nan  | -58 -415 -337 +224 +0 +0 +0 +0   [1s]
chk6                   n   206  net      -855  R  -0.247  win  22.8  pf  0.78  dd     -979  p 0.9845  yrs+ 0/4  h1 -0.247 h2 +nan  | -86 -348 -134 -286 +0 +0 +0 +0   [0s]
chk7                   n   102  net      +259  R  +0.123  win  32.4  pf  1.15  dd     -256  p 0.2360  yrs+ 3/4  h1 +0.123 h2 +nan  | -14 +87 +72 +114 +0 +0 +0 +0   [0s]
chk8                   n  1560  net     -5270  R  -0.216  win  23.7  pf  0.82  dd    -7391  p 1.0000  yrs+ 1/4  h1 -0.216 h2 +nan  | -1170 -4176 -888 +964 +0 +0 +0 +0   [2s]
chk9                   n   165  net       +92  R  -0.027  win  28.5  pf  1.03  dd     -444  p 0.5832  yrs+ 2/4  h1 -0.027 h2 +nan  | -78 -111 +38 +244 +0 +0 +0 +0   [1s]
chk10                  n   286  net    -11494  R  -0.674  win  52.1  pf  0.70  dd   -12292  p 0.9805  yrs+ 1/4  h1 -0.674 h2 +nan  | +304 -4001 -1954 -5843 +0 +0 +0 +0   [0s]
chk11                  n   268  net    -10270  R  -0.767  win  51.9  pf  0.72  dd   -11338  p 0.9869  yrs+ 1/4  h1 -0.767 h2 +nan  | +28 -4031 -2266 -4002 +0 +0 +0 +0   [0s]
chk12                  n   365  net    -12456  R  -0.688  win  51.5  pf  0.74  dd   -14377  p 0.9887  yrs+ 1/4  h1 -0.688 h2 +nan  | +82 -6726 -3091 -2721 +0 +0 +0 +0   [0s]
chk13                  n   461  net      -413  R  -0.022  win  27.8  pf  0.97  dd    -1976  p 0.6134  yrs+ 1/4  h1 -0.022 h2 +nan  | -188 +577 -449 -353 +0 +0 +0 +0   [0s]
chk14                  n   194  net      -108  R  -0.056  win  27.8  pf  0.97  dd     -784  p 0.6813  yrs+ 2/4  h1 -0.056 h2 +nan  | -107 +185 +2 -188 +0 +0 +0 +0   [0s]
chk15                  n    73  net      -630  R  -0.390  win  26.0  pf  0.50  dd     -646  p 0.9940  yrs+ 0/4  h1 -0.390 h2 +nan  | -36 -144 -208 -242 +0 +0 +0 +0   [1s]
chk16                  n   461  net     -2920  R  -0.257  win  22.8  pf  0.67  dd    -3080  p 0.9992  yrs+ 0/4  h1 -0.257 h2 +nan  | -136 -666 -548 -1568 +0 +0 +0 +0   [0s]
```


## 8. Look-ahead

`python3 tools/yt1/run.py L2 --check`: **PASS** (base, 16 sampled order bars).
`python3 tools/yt1/s_L2.py --check all --plain`: test A 46 of 46 PASS, test B 46 of 46 PASS, test C 39 of 46 PASS.

- Every order's bar `i` is the last bar before 09:30, so `core.causal_check` cuts the future right there and
  mirrors everything from the 09:30 bar on. An order that used any bar of its own watch (a level or profile reaching
  into the session, the day's later range, the outcome of the tap, a flat bar chosen by the day's end) would come out
  different. The ATR, the placebo drop, the stacked count (it decides which
  orders a stacked variant has), the alignment of the POCs, the bias (it decides which orders the with-bias
  variant has) and the day type are all part of what is compared, because they decide which orders exist.
- The one number read after bar `i` is the open of bar `i + 1`, the 09:30 open: registered as what sets the side
  and the skip of a level, and for VA-trend it is the price the value areas are compared with (the day type) and
  the fill. **Test A** (what `run.py --check` runs) is `core.causal_check`, unchanged, on `orders(at_open=False)`:
  that open replaced by the last close before it, so every number compared comes from bars up to `i`; for VA-trend
  the day type is then "last close before 09:30 against the five value areas", which uses only prior-session
  profiles and that close. **Test B** is the same test on the real orders (`at_open=True`, what `trades()` trades)
  with that single open kept true in the mirrored future (`s_L1.check_true_open`). **Test C** is
  `core.causal_check`, unchanged, on the real orders: it mirrors that open too, so it fails where the open matters
  for a sampled day (a level changes side or crosses the 0.04 x ATR skip, a day changes type), and only there (B
  differs from C by that one number and passes): the three stacked-bucket picks and chk8 (12,461 / 4,644 orders,
  some sampled day always has one that flips), chk2 (the midnight placebo) and VA-trend on eth (p8_nb1 = chk11).
- "differ" below = the number of real orders that are not among the `at_open=False` orders (a different side, or
  skipped under one reading only): at most 9 of 12,461.
- The levels themselves are tested apart from the orders in section 3, each cut at its own `t_set` (the rth
  profiles at the previous 15:59, the weekly ones the Friday before, an hourly open at its own bar).

| variant | selection | trade | orders | differ | A | B (sampled bars) | C plain, real orders |
|---|---|---|---|---|---|---|---|
| base | o00 | a04x3 | 761 | 2 | PASS | PASS (16) | PASS |
| nb1 | o00 | a08x3 | 761 | 2 | PASS | PASS (16) | PASS |
| nb2 | o00 | a04x2 | 761 | 2 | PASS | PASS (16) | PASS |
| mb | o00 bias with | a04x3 | 306 | 1 | PASS | PASS (16) | PASS |
| mb_nb1 | o00 bias with | a08x3 | 306 | 1 | PASS | PASS (16) | PASS |
| mb_nb2 | o00 bias with | a04x2 | 306 | 1 | PASS | PASS (16) | PASS |
| p1 | eth1_val:S | brk_a04 | 633 | 1 | PASS | PASS (16) | PASS |
| p1_nb1 | eth1_val:S | brk_a08 | 633 | 1 | PASS | PASS (16) | PASS |
| p1_nb2 | eth1_val:S | brk_a04x2 | 633 | 1 | PASS | PASS (16) | PASS |
| p2 | rth3_val:S | brk_a04 | 675 | 0 | PASS | PASS (16) | PASS |
| p2_nb1 | rth3_val:S | brk_a08 | 675 | 0 | PASS | PASS (16) | PASS |
| p2_nb2 | rth3_val:S | brk_a04x2 | 675 | 0 | PASS | PASS (16) | PASS |
| p3 | on_poc:S | brk_a04 | 307 | 7 | PASS | PASS (16) | PASS |
| p3_nb1 | on_poc:S | brk_a08 | 307 | 7 | PASS | PASS (16) | PASS |
| p3_nb2 | on_poc:S | brk_a04x2 | 307 | 7 | PASS | PASS (16) | PASS |
| p4 | rth2_poc:S | brk_a04 | 475 | 0 | PASS | PASS (16) | PASS |
| p4_nb1 | rth2_poc:S | brk_a08 | 475 | 0 | PASS | PASS (16) | PASS |
| p4_nb2 | rth2_poc:S | brk_a04x2 | 475 | 0 | PASS | PASS (16) | PASS |
| p5 | rth3_poc:S | a04x3 | 469 | 0 | PASS | PASS (16) | PASS |
| p5_nb1 | rth3_poc:S | a08x3 | 469 | 0 | PASS | PASS (16) | PASS |
| p5_nb2 | rth3_poc:S | a04x2 | 469 | 0 | PASS | PASS (16) | PASS |
| p6 | stack 3+ | brk_a04 | 12461 | 9 | PASS | PASS (16) | FAIL |
| p6_nb1 | stack 3+ | brk_a08 | 12461 | 9 | PASS | PASS (16) | FAIL |
| p6_nb2 | stack 3+ | brk_a04x2 | 12461 | 9 | PASS | PASS (16) | FAIL |
| p7 | aligned POC | a04x3 | 200 | 0 | PASS | PASS (16) | PASS |
| p7_nb1 | aligned POC | a08x3 | 200 | 0 | PASS | PASS (16) | PASS |
| p7_nb2 | aligned POC | a04x2 | 200 | 0 | PASS | PASS (16) | PASS |
| p8 | VA-trend rth | market at the 09:30 open | 286 | 2 | PASS | PASS (16) | PASS |
| p8_nb1 | VA-trend eth | market at the 09:30 open | 268 | 1 | PASS | PASS (16) | FAIL |
| p8_nb2 | VA-trend rth3 | market at the 09:30 open | 365 | 3 | PASS | PASS (16) | PASS |
| chk1 | o03 | a04x3 | 758 | 5 | PASS | PASS (16) | PASS |
| chk2 | o00~ | a04x3 | 733 | 3 | PASS | PASS (16) | FAIL |
| chk3 | rth3_poc:R | a04x3 | 358 | 0 | PASS | PASS (16) | PASS |
| chk4 | eth5_val:S | a04x3 | 640 | 1 | PASS | PASS (16) | PASS |
| chk5 | rthw_vah:R | a04x3 | 440 | 0 | PASS | PASS (16) | PASS |
| chk6 | on_poc:S | a04x3 | 307 | 7 | PASS | PASS (16) | PASS |
| chk7 | aligned POC | a04x3 | 200 | 0 | PASS | PASS (16) | PASS |
| chk8 | stack 2 | a04x3 | 4644 | 2 | PASS | PASS (16) | FAIL |
| chk9 | eth2_vah:R | brk_a04 | 524 | 0 | PASS | PASS (16) | PASS |
| chk10 | VA-trend rth | market at the 09:30 open | 286 | 2 | PASS | PASS (16) | PASS |
| chk11 | VA-trend eth | market at the 09:30 open | 268 | 1 | PASS | PASS (16) | FAIL |
| chk12 | VA-trend rth3 | market at the 09:30 open | 365 | 3 | PASS | PASS (16) | PASS |
| chk13 | o00 | p20x3 | 761 | 2 | PASS | PASS (16) | PASS |
| chk14 | o00 bias against | a04x3 | 330 | 0 | PASS | PASS (16) | PASS |
| chk15 | rthw_val:S | brk_a04x2 | 599 | 0 | PASS | PASS (16) | PASS |
| chk16 | o00 | brk_a04 | 761 | 2 | PASS | PASS (16) | PASS |

## 9. Coding errors found and fixed

- Before any event was built: the session list of a profile was stored as `2020-04-02T00:00:00|...` instead of
  dates, so the unit check that compares it with the brute-force session list failed for every composite (values,
  volume, rows and bars agreed). Now plain dates. No level changed.
- Before any table was built: variant (c) of the level look-ahead test compared a placebo's value across two
  windows with different starts (a different ATR warm-up), which failed 50 of the 78 sampled placebos; it now
  compares on one window (138 of 188 before, 188 of 188 after). The test was wrong, not the levels.
- `lev2_verify.py` (the hand-check printer): `frame.stack` is a pandas method, the column has to be read as
  `frame["stack"]`.
- After the first table was printed nothing in a level, an event, a table or the selection rule was changed. One
  thing was added: `distinct_orders` (each repeated order once) in picks 6 and 7 of `VPN1_selected.json` and beside
  those picks in the full phase's print. The picks are the same; the three event files and the seven tables are
  byte-identical before and after (and after a rebuild with 2 processes).

Harness and existing modules: no bug found. Two things a reader should know: (1) `tt.bias` reads the roll flag of
today's own trading-day candle, which is built from the whole trading date; in this data a contract changes only
at 20:00 / 19:00 on the evening before a roll day, the flag can only be set on a roll day, and roll days are not
study days, so no study-day bias depends on a later bar (the look-ahead tests of `mb` pass). (2) `core.boot_p`
treats the trades it is given as independent; for a stacked-bucket pick they are not (reading 6).

## 10. Full phase (not run here)

`lev2_events.py --phase full` refuses to run in the lab (no bars after 2022-12-31) and `lev2_tables.py --phase
full` stops because `full/MID1_events.parquet` does not exist. Order of work later:

```
python3 tools/yt1/lev2_events.py --phase full     # full/MID1_events.parquet, VPN1_events.parquet, VPN1_daytypes.csv
python3 tools/yt1/lev2_tables.py --phase full     # checks, _oos and _full tables, verdicts -> full/LEV2_oos.json
python3 tools/yt1/run.py L2 --phase full && python3 tools/yt1/s_L2.py --recon --phase full
```

`lev2_tables.py --phase full` never re-selects: it reads `VPN1_selected.json`, checks the stamped sha256 of the
frozen in-sample event files, rebuilds the seven in-sample tables from the full files and compares them with the
frozen ones (text equality), applies the selection rule again only to report whether it gives the frozen picks,
writes every table for 2023-01-01 onward (`_oos`) and for the full span (`_full`), prints the two registered MID1
verdicts (full span, sides pooled, headline fade; and the with-bias fade; years, R, halves, a08x3 and a04x2,
bootstrap p against 0.05 / 130 and 0.05, win rate above the placebo's; the break trade, the 20-point stop and the
against-bias / no-bias fades beside them) and where midnight ranks among the 13 hourly opens, scores every frozen
pick out of sample (events, mean R, p < 0.05 / 8, 3 of 4 years, both neighbours, the placebo for a fade cell), gives
the Spearman correlation of the cells' mean R between the periods, mean R by N for both periods, pooled real against
placebo for both periods and the full span, and the full-span top 10 cells by net $ labelled as hindsight.

It was dry-tested on a made-up split inside the in-sample files (`lev2_tables.py --phase is --dry-split 2021-07-01
--dry-out <scratch>` then `--phase full` with the same arguments): the in-sample tables rebuilt from the whole
files equalled the frozen ones (7 of 7 identical), the selection rule gave the frozen picks (on that short sample
only four cells have 150 events and picks 5 and 7 do not exist, which the code reports as "none"), the MID1
verdicts, the rank line, the pick verdicts, the Spearman lines, the by-N table, the pooled lines and the hindsight
table printed. The scratch directory was deleted; the study folder's files were byte-identical before and after
(sha256 of the selection file, the three event files and the seven tables). `s_L2.py --recon --phase full` reads
the `_full` tables.

## 11. Run times (2 cores, nothing else running)

Levels: MID1 2 s, VPN1 4 s. `lev2_events.py --phase is`: 34 s in all with 2 processes (MID1 events 6 s, VPN1 events
19 s, day types / VA-trend / ORB 1 s, the rest loading and levels); with 1 process MID1 11 s and VPN1 39 s, and the
frames are identical (`lev2_events.py --same`). `lev2_tables.py --phase is` 3 s. `run.py L2 --phase is` 40 s for the
46 variants; `--recon` 3 s. Unit checks 15 s; level look-ahead test (188 levels) 2 min 20 s; hand checks 10 s;
`run.py L2 --check` 14 s; tests A + B + C for the 46 variants 41 minutes of CPU (21 minutes of wall time in two
processes; the stacked-bucket variants, which need all 13 profiles on every window, are the slow ones).

## 12. Printed in-sample output (`python3 tools/yt1/lev2_tables.py --phase is`)

```
LEV2 tables   phase is   MID1 events 12287 rows, VPN1 events 63345 rows, day types 926 rows   2019-06-21 -> 2022-12-30   study days 884

IN SAMPLE: MID1, every hourly open and the midnight placebo (o00~), sides pooled (win in %; rank = among the 13 hourly opens, 1 = highest; headline a04x3, asked p20x3, break brk_a04)
code side  level_days  skipped  watched  events  n_a04x3 win_a04x3 R_a04x3 net_a04x3 win_p20x3 R_p20x3 net_p20x3 R_a08x3 R_a04x2 win_brk_a04 R_brk_a04 R_brk_p20  rank_R  rank_win  rank_R_asked  rank_R_break
 o19  all         884       98      786     435      435      22.8  -0.249     -2170      20.9  -0.132     -2318  -0.145  -0.235        24.6    -0.178    -0.075    12.0      12.0          13.0           9.0
 o20  all         884       98      786     454      454      27.5  -0.060      -179      21.8  -0.078     -1427  -0.073  -0.085        24.4    -0.181    -0.100     3.0       3.0           9.0          10.0
 o21  all         884      104      780     459      459      25.9  -0.120      -677      22.4  -0.075     -1394  -0.120  -0.206        22.7    -0.254    -0.165     7.0       7.0           8.0          11.0
 o22  all         884      110      774     459      459      25.7  -0.122      -924      21.8  -0.099     -1835  -0.180  -0.104        27.5    -0.066    +0.032     8.0       8.0          11.0           5.0
 o23  all         884      122      762     462      462      24.9  -0.166     -1094      25.5  +0.055     +1026  -0.031  -0.112        27.9    -0.045    -0.075    10.0      10.0           1.0           2.0
 o00  all         884      123      761     461      461      26.7  -0.095      -657      23.0  -0.022      -413  -0.014  -0.062        22.6    -0.257    -0.159     5.0       6.0           2.0          12.0
 o01  all         884      123      761     468      468      26.7  -0.095      -400      22.4  -0.023      -440  -0.048  -0.051        22.4    -0.266    -0.131     6.0       5.0           3.0          13.0
 o02  all         884      118      766     467      467      21.4  -0.304     -2582      20.6  -0.110     -2079  -0.090  -0.226        25.3    -0.155    +0.016    13.0      13.0          12.0           8.0
 o03  all         884      126      758     473      473      24.3  -0.186     -1352      22.0  -0.052     -1000  -0.056  -0.167        27.9    -0.052    -0.013    11.0      11.0           7.0           3.0
 o04  all         884      156      728     478      478      25.3  -0.152     -1294      23.0  -0.031      -590  +0.011  -0.129        27.6    -0.060    +0.027     9.0       9.0           6.0           4.0
 o05  all         884      151      733     509      509      28.1  -0.034      +387      22.6  -0.025      -522  -0.045  -0.127        26.3    -0.105    -0.061     1.0       1.0           4.0           6.0
 o06  all         884      178      706     488      488      27.5  -0.067        +2      24.2  -0.030      -588  -0.015  -0.130        25.8    -0.134    +0.036     4.0       4.0           5.0           7.0
 o07  all         884      185      699     508      508      28.0  -0.052      +248      22.0  -0.095     -1962  -0.084  -0.134        28.7    -0.018    +0.116     2.0       2.0          10.0           1.0
o00~  all         795       62      733     386      386      22.5  -0.257     -1936      20.7  -0.106     -1663  -0.141  -0.176        28.0    -0.055    +0.001     NaN       NaN           NaN           NaN

IN SAMPLE: MID1 by side
code side  level_days  skipped  watched  events  n_a04x3 win_a04x3 R_a04x3 net_a04x3 win_p20x3 R_p20x3 net_p20x3 R_a08x3 R_a04x2 win_brk_a04 R_brk_a04 R_brk_p20
 o19    R         392       46      346     189      189      22.2  -0.255      -830      23.3  -0.091      -696  -0.161  -0.333        22.8    -0.235    -0.036
 o19    S         492       52      440     246      246      23.2  -0.244     -1340      19.1  -0.163     -1622  -0.133  -0.161        26.0    -0.134    -0.105
 o20    R         385       49      336     190      190      27.4  -0.061       +36      25.3  +0.000        +1  -0.030  -0.067        22.6    -0.246    -0.110
 o20    S         498       48      450     264      264      27.7  -0.059      -216      19.3  -0.134     -1428  -0.104  -0.097        25.8    -0.134    -0.092
 o21    R         401       48      353     213      213      26.8  -0.090      -491      20.7  -0.173     -1492  -0.138  -0.226        21.1    -0.308    -0.230
 o21    S         481       54      427     246      246      25.2  -0.146      -186      24.0  +0.010       +98  -0.104  -0.188        24.0    -0.207    -0.109
 o22    R         400       46      354     217      217      28.6  -0.021      -212      20.7  -0.164     -1442  -0.203  -0.016        24.9    -0.163    -0.047
 o22    S         483       63      420     242      242      23.1  -0.213      -712      22.7  -0.040      -393  -0.160  -0.184        29.8    +0.021    +0.104
 o23    R         394       53      341     212      212      32.5  +0.134      +948      27.8  +0.151     +1294  +0.002  +0.147        27.8    -0.040    -0.037
 o23    S         489       68      421     250      250      18.4  -0.421     -2042      23.6  -0.026      -268  -0.059  -0.331        28.0    -0.049    -0.107
 o00    R         395       55      340     209      209      27.8  -0.048      +116      25.4  +0.020      +168  +0.060  -0.026        22.5    -0.247    -0.145
 o00    S         487       66      421     252      252      25.8  -0.133      -772      21.0  -0.057      -581  -0.075  -0.092        22.6    -0.265    -0.170
 o01    R         403       48      355     219      219      29.2  +0.012      +422      21.9  -0.084      -743  -0.078  +0.002        21.0    -0.317    -0.150
 o01    S         478       72      406     249      249      24.5  -0.188      -821      22.9  +0.030      +304  -0.022  -0.099        23.7    -0.220    -0.114
 o02    R         416       55      361     217      217      19.8  -0.363     -1432      19.8  -0.180     -1583  -0.117  -0.315        24.9    -0.167    +0.072
 o02    S         464       59      405     250      250      22.8  -0.252     -1150      21.2  -0.049      -496  -0.067  -0.148        25.6    -0.143    -0.033
 o03    R         424       57      367     231      231      27.3  -0.070       -66      24.7  +0.058      +544  +0.095  -0.113        25.5    -0.143    -0.059
 o03    S         455       64      391     242      242      21.5  -0.297     -1286      19.4  -0.157     -1544  -0.201  -0.218        30.2    +0.034    +0.030
 o04    R         433       78      355     237      237      26.2  -0.115      -518      22.8  -0.028      -268  +0.018  -0.086        24.9    -0.158    -0.047
 o04    S         449       76      373     241      241      24.5  -0.188      -777      23.2  -0.033      -323  +0.005  -0.172        30.3    +0.037    +0.100
 o05    R         439       69      370     257      257      30.7  +0.070      +698      24.5  +0.042      +440  +0.010  -0.055        20.6    -0.312    -0.044
 o05    S         442       79      363     252      252      25.4  -0.140      -310      20.6  -0.094      -962  -0.102  -0.201        32.1    +0.107    -0.078
 o06    R         449       86      363     248      248      31.0  +0.074      +860      28.6  +0.118     +1182  +0.095  -0.051        24.6    -0.184    -0.016
 o06    S         433       90      343     240      240      23.8  -0.213      -858      19.6  -0.182     -1771  -0.129  -0.212        27.1    -0.082    +0.090
 o07    R         457       97      360     259      259      26.6  -0.102      -232      22.0  -0.092      -962  -0.040  -0.170        29.7    +0.026    +0.095
 o07    S         425       86      339     249      249      29.3  +0.001      +480      22.1  -0.099     -1000  -0.131  -0.096        27.7    -0.063    +0.139
o00~    R         373       33      340     185      185      23.8  -0.202      -768      20.5  -0.155     -1165  -0.070  -0.107        25.9    -0.139    -0.099
o00~    S         422       29      393     201      201      21.4  -0.307     -1167      20.9  -0.061      -498  -0.207  -0.239        29.9    +0.023    +0.094

IN SAMPLE: MID1, the registered splits of the midnight open (pl_ = its placebos under the same split; dwin in points; level_days counted before the skip rule)
  split     value  level_days  skipped  watched  events  n_a04x3 win_a04x3 R_a04x3 net_a04x3 win_p20x3 R_p20x3 R_a08x3 R_a04x2 win_brk_a04 R_brk_a04 R_brk_p20  pl_events pl_win_a04x3 pl_R_a04x3 dwin_a04x3 pwin_a04x3 pl_win_p20x3 pl_R_p20x3
    all       all       884.0    123.0    761.0     461      461      26.7  -0.095      -657      23.0  -0.022  -0.014  -0.062        22.6    -0.257    -0.159        386         22.5     -0.257       +4.1      0.164         20.7     -0.106
   side         S       487.0     66.0    421.0     252      252      25.8  -0.133      -772      21.0  -0.057  -0.075  -0.092        22.6    -0.265    -0.170        201         21.4     -0.307       +4.4      0.275         20.9     -0.061
   side         R       395.0     55.0    340.0     209      209      27.8  -0.048      +116      25.4  +0.020  +0.060  -0.026        22.5    -0.247    -0.145        185         23.8     -0.202       +4.0      0.370         20.5     -0.155
   time      0930         NaN      NaN      NaN     280      280      28.2  -0.042      +246      27.9  +0.116  +0.075  +0.006        21.1    -0.324    -0.197        203         22.2     -0.284       +6.0      0.133         23.2     -0.060
   time      1000         NaN      NaN      NaN     120      120      21.7  -0.269      -810      15.0  -0.249  -0.088  -0.257        25.8    -0.106    -0.062        114         22.8     -0.230       -1.1      0.834         18.4     -0.177
   time      1130         NaN      NaN      NaN      61       61      29.5  +0.008       -92      16.4  -0.210  -0.274  +0.011        23.0    -0.242    -0.176         69         23.2     -0.219       +6.3      0.413         17.4     -0.126
   dist     <0.10       284.0    123.0    161.0     135      135      30.4  +0.050      +118      23.7  +0.108  +0.052  -0.003        20.0    -0.353    -0.054         75         20.0     -0.371      +10.4      0.103         24.0     +0.027
   dist 0.10-0.25       300.0      0.0    300.0     199      199      26.6  -0.101       -80      25.1  +0.007  -0.045  -0.052        23.1    -0.240    -0.257        178         23.6     -0.209       +3.0      0.498         20.8     -0.097
   dist 0.25-0.50       214.0      0.0    214.0     105      105      22.9  -0.237      -592      18.1  -0.232  -0.082  -0.153        25.7    -0.126    -0.031        116         22.4     -0.260       +0.4      0.937         19.0     -0.170
   dist    >=0.50        86.0      0.0     86.0      22       22      22.7  -0.248      -104      22.7  -0.085  +0.190  -0.070        18.2    -0.441    -0.523         17         23.5     -0.225       -0.8      0.953         17.6     -0.365
crossed       yes       876.0    123.0    753.0     457      457      26.7  -0.094      -676      23.0  -0.025  -0.004  -0.065        22.5    -0.257    -0.161        196         23.5     -0.227       +3.2      0.387         23.0     -0.004
crossed        no         8.0      0.0      8.0       4        4      25.0  -0.207       +20      25.0  +0.250  -1.096  +0.278        25.0    -0.258    +0.096        190         21.6     -0.287       +3.4      0.869         18.4     -0.212
   bias      with       369.0     63.0    306.0     194      194      26.8  -0.089      -402      25.3  +0.067  +0.034  -0.004        22.7    -0.249    -0.014        156         23.1     -0.212       +3.7      0.424         19.2     -0.198
   bias   against       371.0     41.0    330.0     194      194      27.8  -0.056      -108      22.2  -0.082  -0.007  -0.040        19.6    -0.366    -0.322        158         24.7     -0.186       +3.2      0.505         22.2     -0.056
   bias      none       144.0     19.0    125.0      73       73      23.3  -0.214      -148      19.2  -0.099  -0.159  -0.273        30.1    +0.014    -0.111         72         16.7     -0.507       +6.6      0.319         20.8     -0.019

IN SAMPLE: VPN1 reaction, profile x level x side, all events, sorted by the headline (a04x3) mean R: top 15 of 78 (cells with >= 150 events: 24)
prof level side  watched  events  n_a04x3 win_a04x3 R_a04x3 net_a04x3 win_p20x3 R_p20x3 R_a08x3 R_a04x2 win_brk_a04 R_brk_a04 R_brk_p20  pl_events pl_win_a04x3 pl_R_a04x3 dwin_a04x3 dR_a04x3 pwin_a04x3 pl_R_p20x3 pl_R_brk_a04
eth4   vah    S      281      92       92      33.7  +0.169      +412      25.0  +0.139  +0.061  +0.218        16.3    -0.509    -0.419         49         18.4     -0.437      +15.3   +0.606      0.055     -0.298       -0.364
  on   vah    S      127      98       98      29.6  +0.065      +237      25.5  +0.039  +0.214  +0.041        29.6    +0.027    +0.067         97         17.5     -0.454      +12.1   +0.518      0.047     -0.217       +0.025
eth3   vah    S      288     108      108      30.6  +0.036      +247      15.7  -0.253  -0.099  +0.036        25.9    -0.144    -0.056         47         34.0     +0.163       -3.5   -0.127      0.668     +0.234       -0.736
rth5   vah    S      270      89       89      30.3  +0.034      +152      19.1  -0.072  +0.006  +0.164        23.6    -0.226    -0.217         55         23.6     -0.222       +6.7   +0.256      0.383     -0.069       +0.122
rth3   poc    R      358     133      133      29.3  +0.018      +278      23.3  -0.108  -0.082  -0.181        27.8    -0.036    +0.016         91         22.0     -0.269       +7.3   +0.287      0.220     +0.035       +0.288
rth3   poc    S      469     150      150      29.3  +0.000       +50      25.3  +0.081  -0.073  +0.006        26.7    -0.103    +0.127         87         21.8     -0.294       +7.5   +0.295      0.208     -0.073       +0.022
eth3   val    R      174      83       83      28.9  -0.001      +350      27.7  +0.055  -0.020  -0.108        24.1    -0.197    -0.012         57         22.8     -0.246       +6.1   +0.245      0.421     -0.161       +0.163
rth4   vah    R      542     145      145      29.0  -0.019      +154      22.1  +0.046  -0.051  -0.121        26.9    -0.079    +0.178        118         29.7     +0.024       -0.7   -0.043      0.902     -0.113       +0.053
eth5   vah    S      272      83       83      28.9  -0.025       -19      19.3  -0.009  -0.035  -0.024        25.3    -0.166    -0.183         52         25.0     -0.158       +3.9   +0.133      0.620     -0.257       -0.164
  on   poc    R      293     200      200      28.5  -0.029       +52      24.0  -0.019  -0.175  -0.073        28.5    -0.031    -0.078        213         26.8     -0.075       +1.7   +0.046      0.693     -0.172       -0.199
rth3   vah    R      554     166      166      28.3  -0.033      +222      24.7  +0.113  +0.017  -0.163        27.7    -0.070    +0.329        116         25.0     -0.163       +3.3   +0.130      0.537     -0.311       -0.216
rth4   vah    S      279     102      102      28.4  -0.041       +28      18.6  -0.149  -0.252  +0.021        22.5    -0.270    -0.145         65         21.5     -0.314       +6.9   +0.273      0.321     -0.099       -0.250
rth2   poc    S      475     173      173      27.7  -0.057      -412      21.4  -0.066  -0.122  -0.073        29.5    +0.005    +0.186        107         26.2     -0.115       +1.6   +0.058      0.773     -0.141       +0.141
eth3   poc    S      467     143      143      27.3  -0.080      -326      23.1  +0.009  -0.035  -0.038        29.4    +0.002    +0.179         82         25.6     -0.158       +1.7   +0.078      0.786     -0.044       +0.030
eth1   poc    S      470     217      217      26.7  -0.098      -606      23.5  +0.003  -0.031  -0.089        24.0    -0.204    -0.067        118         21.2     -0.311       +5.5   +0.213      0.262     -0.217       +0.055

IN SAMPLE: VPN1 reaction, bottom 8
prof level side  watched  events  n_a04x3 win_a04x3 R_a04x3 net_a04x3 win_p20x3 R_p20x3 R_a08x3 R_a04x2 win_brk_a04 R_brk_a04 R_brk_p20  pl_events pl_win_a04x3 pl_R_a04x3 dwin_a04x3 dR_a04x3 pwin_a04x3 pl_R_p20x3 pl_R_brk_a04
rthw   vah    R      440      84       84      19.0  -0.414      -586      14.3  -0.363  -0.533  -0.530        36.9    +0.316    +0.488         62         21.0     -0.323       -1.9   -0.092      0.774     -0.425       -0.409
eth1   val    S      633     209      209      18.7  -0.418     -1874      15.8  -0.325  -0.375  -0.376        34.9    +0.212    +0.036        172         30.2     +0.041      -11.6   -0.459      0.008     +0.198       -0.235
ethw   val    R      186      50       50      18.0  -0.428      -408      22.0  -0.193  -0.115  -0.310        30.0    +0.040    +0.165         31         32.3     +0.095      -14.3   -0.523      0.141     -0.031       -0.032
rth4   val    R      169      74       74      17.6  -0.441      -700      14.9  -0.455  -0.424  -0.415        24.3    -0.182    -0.264         60         30.0     +0.048      -12.4   -0.490      0.090     +0.481       -0.147
rth5   val    S      646     114      114      16.7  -0.494      -966      16.7  -0.335  -0.346  -0.503        25.4    -0.155    +0.237        114         27.2     -0.095      -10.5   -0.399      0.055     +0.114       -0.133
rthw   poc    R      311      70       70      14.3  -0.586      -859      11.4  -0.517  -0.327  -0.515        31.4    +0.074    +0.462         52         28.8     -0.010      -14.6   -0.576      0.049     -0.429       -0.084
rth5   val    R      167      74       74      13.5  -0.600      -978      10.8  -0.606  -0.500  -0.455        33.8    +0.184    +0.052         54         31.5     +0.111      -18.0   -0.712      0.014     +0.430       +0.028
ethw   poc    R      304      67       67      13.4  -0.615      -806      14.9  -0.406  -0.253  -0.309        23.9    -0.213    +0.309         45         31.1     +0.073      -17.7   -0.689      0.023     -0.331       -0.273
IN SAMPLE: VPN1 all 78 profile-level-sides, crossed: events 5374, a04x3 win 24.2% R -0.1974, p20x3 R -0.1379, brk_a04 R -0.0843
IN SAMPLE: VPN1 all 78 profile-level-sides, uncrossed: events 4928, a04x3 win 23.7% R -0.2129, p20x3 R -0.1472, brk_a04 R -0.0131

IN SAMPLE: VPN1 by lookback N (sides pooled; level 'all' = vah + poc + val)
stype N level  events  n_a04x3 win_a04x3 R_a04x3 net_a04x3 win_p20x3 R_p20x3 R_a08x3 R_a04x2 win_brk_a04 R_brk_a04  pl_events pl_win_a04x3 pl_R_a04x3 dwin_a04x3 pwin_a04x3 pl_R_p20x3 pl_R_brk_a04
  rth 1   all    1116     1116      22.8  -0.245     -4750      20.6  -0.122  -0.149  -0.216        26.2    -0.122        722         24.8     -0.171       -2.0      0.316     -0.068       -0.102
  rth 2   all     918      918      23.2  -0.232     -4528      19.4  -0.186  -0.147  -0.241        29.5    +0.009        620         23.4     -0.223       -0.2      0.933     -0.145       -0.061
  rth 3   all     796      796      26.3  -0.115     -1012      22.1  -0.067  -0.096  -0.147        28.3    -0.040        552         24.3     -0.191       +2.0      0.412     -0.139       -0.020
  rth 4   all     710      710      24.2  -0.197     -2206      19.9  -0.144  -0.239  -0.200        27.0    -0.084        521         25.5     -0.143       -1.3      0.601     -0.062       -0.018
  rth 5   all     644      644      22.2  -0.275     -3198      18.5  -0.211  -0.233  -0.210        27.2    -0.080        479         24.4     -0.187       -2.2      0.383     -0.073       -0.088
  eth 1   all    1047     1047      23.7  -0.216     -4227      20.7  -0.135  -0.155  -0.216        27.9    -0.051        682         25.4     -0.151       -1.7      0.426     -0.045       -0.072
  eth 2   all     848      848      24.6  -0.179     -3494      19.9  -0.168  -0.127  -0.197        27.6    -0.065        554         24.4     -0.191       +0.3      0.906     -0.201       -0.018
  eth 3   all     744      744      25.8  -0.133     -1398      21.1  -0.094  -0.098  -0.151        27.0    -0.088        494         26.9     -0.095       -1.1      0.662     -0.112       -0.080
  eth 4   all     668      668      24.4  -0.187     -1950      19.6  -0.164  -0.175  -0.193        29.2    +0.002        475         23.8     -0.216       +0.6      0.812     -0.105       -0.072
  eth 5   all     599      599      22.2  -0.272     -2864      18.2  -0.212  -0.218  -0.200        29.0    -0.005        438         27.2     -0.083       -5.0      0.066     -0.073       -0.202
  rth w   all     436      436      21.3  -0.319     -2319      18.8  -0.206  -0.213  -0.293        28.7    -0.030        346         23.7     -0.222       -2.4      0.430     -0.155       -0.139
  eth w   all     432      432      20.6  -0.346     -2889      18.5  -0.213  -0.212  -0.235        29.9    +0.020        345         26.7     -0.106       -6.1      0.047     -0.102       -0.124
   on -   all    1344     1344      26.1  -0.120     -2848      22.4  -0.071  -0.060  -0.140        27.9    -0.051       1208         24.8     -0.164       +1.4      0.430     -0.153       -0.102

IN SAMPLE: VPN1 by lookback N and level
stype N level  events  n_a04x3 win_a04x3 R_a04x3 net_a04x3 win_p20x3 R_p20x3 R_a08x3 R_a04x2 win_brk_a04 R_brk_a04
  rth 1   vah     380      380      21.8  -0.268     -1606      17.1  -0.256  -0.266  -0.179        25.3    -0.155
  rth 1   poc     392      392      25.3  -0.154     -1230      23.2  -0.023  -0.014  -0.169        24.5    -0.187
  rth 1   val     344      344      20.9  -0.324     -1912      21.5  -0.088  -0.174  -0.309        29.1    -0.010
  rth 2   vah     322      322      22.7  -0.246     -1346      19.9  -0.159  -0.087  -0.183        24.8    -0.172
  rth 2   poc     307      307      24.8  -0.176     -1617      19.5  -0.165  -0.142  -0.244        30.3    +0.043
  rth 2   val     289      289      22.1  -0.277     -1565      18.7  -0.238  -0.219  -0.300        33.9    +0.176
  rth 3   vah     279      279      26.2  -0.122      -437      22.9  +0.042  +0.037  -0.155        26.2    -0.128
  rth 3   poc     283      283      29.3  +0.008      +328      24.4  -0.007  -0.077  -0.082        27.2    -0.071
  rth 3   val     234      234      22.6  -0.256      -904      18.4  -0.269  -0.278  -0.216        32.1    +0.104
  rth 4   vah     247      247      28.7  -0.028      +181      20.6  -0.035  -0.134  -0.062        25.1    -0.158
  rth 4   poc     253      253      23.3  -0.231      -956      20.9  -0.134  -0.288  -0.227        29.2    +0.003
  rth 4   val     210      210      20.0  -0.356     -1430      17.6  -0.285  -0.302  -0.330        26.7    -0.101
  rth 5   vah     222      222      27.5  -0.085      -284      19.4  -0.107  -0.068  +0.003        25.7    -0.138
  rth 5   poc     234      234      22.6  -0.246      -970      20.9  -0.124  -0.250  -0.191        27.4    -0.073
  rth 5   val     188      188      15.4  -0.536     -1944      14.4  -0.442  -0.406  -0.484        28.7    -0.021
  eth 1   vah     354      354      23.2  -0.230     -1357      20.9  -0.128  -0.194  -0.158        27.7    -0.047
  eth 1   poc     379      379      26.4  -0.114     -1040      21.9  -0.074  -0.056  -0.178        24.3    -0.195
  eth 1   val     314      314      21.0  -0.324     -1830      19.1  -0.216  -0.231  -0.326        32.5    +0.118
  eth 2   vah     284      284      24.3  -0.187      -932      20.8  -0.095  +0.013  -0.205        27.1    -0.084
  eth 2   poc     294      294      25.2  -0.163     -1244      20.1  -0.166  -0.150  -0.189        25.9    -0.133
  eth 2   val     270      270      24.4  -0.187     -1317      18.9  -0.248  -0.247  -0.198        30.0    +0.028
  eth 3   vah     244      244      24.2  -0.203      -993      16.8  -0.200  -0.158  -0.168        30.3    +0.033
  eth 3   poc     264      264      26.9  -0.089      -477      22.0  -0.072  -0.063  -0.130        25.8    -0.129
  eth 3   val     236      236      26.3  -0.112       +72      24.6  -0.010  -0.074  -0.158        25.0    -0.166
  eth 4   vah     225      225      26.7  -0.106      -140      21.8  -0.030  -0.132  -0.095        26.2    -0.115
  eth 4   poc     241      241      22.0  -0.281     -1303      17.8  -0.237  -0.185  -0.252        31.5    +0.095
  eth 4   val     202      202      24.8  -0.164      -508      19.3  -0.227  -0.210  -0.233        29.7    +0.023
  eth 5   vah     195      195      23.1  -0.238      -865      18.5  -0.145  -0.189  -0.116        28.7    -0.017
  eth 5   poc     219      219      21.9  -0.287     -1143      17.8  -0.222  -0.188  -0.207        28.3    -0.036
  eth 5   val     185      185      21.6  -0.289      -856      18.4  -0.271  -0.284  -0.279        30.3    +0.046
  rth w   vah     158      158      22.8  -0.269      -590      13.3  -0.358  -0.348  -0.270        32.3    +0.118
  rth w   poc     155      155      19.4  -0.396     -1052      18.1  -0.241  -0.157  -0.322        27.1    -0.102
  rth w   val     123      123      22.0  -0.285      -678      26.8  +0.031  -0.110  -0.286        26.0    -0.129
  eth w   vah     156      156      22.4  -0.283      -953      19.9  -0.150  -0.272  -0.182        30.8    +0.063
  eth w   poc     156      156      19.2  -0.401     -1062      17.9  -0.178  -0.152  -0.214        26.3    -0.132
  eth w   val     120      120      20.0  -0.358      -874      17.5  -0.339  -0.214  -0.332        33.3    +0.160
   on -   vah     476      476      26.7  -0.093      -470      21.8  -0.096  -0.045  -0.169        28.8    -0.013
   on -   poc     406      406      25.6  -0.139      -804      23.6  -0.031  -0.113  -0.152        29.3    +0.003
   on -   val     462      462      26.0  -0.130     -1574      21.9  -0.079  -0.027  -0.099        25.8    -0.137

IN SAMPLE: VPN1 stacked-level count (other profiles with a level within 0.03 x ATR) and the aligned POCs
 kind      key side  watched  events  distinct_orders  days  n_a04x3 win_a04x3 R_a04x3 net_a04x3 win_p20x3 R_p20x3 R_a08x3 R_a04x2 win_brk_a04 R_brk_a04 net_brk_a04 R_brk_a08 R_brk_a04x2
stack        0  all     6877    2029             2029   745     2029      25.1  -0.160     -4977      22.7  -0.072  -0.113  -0.166        27.9    -0.050       -2547    +0.012      -0.129
stack        0    R     2788     925              925   475      925      25.6  -0.135     -1496      24.0  -0.043  -0.129  -0.199        29.1    -0.001        -270    +0.079      -0.059
stack        0    S     4089    1104             1104   500     1104      24.6  -0.180     -3480      21.6  -0.095  -0.101  -0.139        27.0    -0.091       -2276    -0.045      -0.189
stack        1  all     7361    2191             1937   610     2191      24.0  -0.204     -7943      21.3  -0.106  -0.149  -0.215        25.4    -0.152       -6680    -0.010      -0.135
stack        1    R     2977    1000              893   349     1000      22.9  -0.245     -4258      18.5  -0.228  -0.259  -0.256        26.0    -0.129       -2275    +0.055      -0.081
stack        1    S     4384    1191             1044   393     1191      24.9  -0.170     -3684      23.6  -0.003  -0.057  -0.182        24.9    -0.172       -4406    -0.065      -0.180
stack        2  all     4644    1560             1252   487     1560      23.7  -0.216     -5270      19.8  -0.164  -0.174  -0.216        27.2    -0.077       -2693    +0.018      -0.066
stack        2    R     2040     737              586   273      737      25.4  -0.147     -1782      21.7  -0.110  -0.087  -0.171        26.6    -0.092       -1832    -0.001      -0.104
stack        2    S     2604     823              666   285      823      22.1  -0.278     -3488      18.1  -0.211  -0.252  -0.257        27.7    -0.063        -860    +0.035      -0.031
stack       3+  all    12461    4522             2493   536     4522      23.6  -0.222    -19492      18.9  -0.185  -0.160  -0.194        29.5    +0.008       +1804    +0.128      -0.046
stack       3+    R     5612    2140             1211   295     2140      22.7  -0.251     -9960      18.6  -0.215  -0.177  -0.267        29.4    +0.014        +476    +0.125      +0.024
stack       3+    S     6849    2382             1282   329     2382      24.3  -0.196     -9532      19.2  -0.157  -0.144  -0.129        29.5    +0.003       +1328    +0.131      -0.109
 apoc apoc_rth  all      106      57               57    57       57      31.6  +0.097       +82      22.8  -0.079  +0.042  -0.005        33.3    +0.188        +244    -0.020      +0.097
 apoc apoc_rth    R       40      24               24    24       24      33.3  +0.169      +159      25.0  -0.074  +0.085  -0.156        29.2    +0.055         -47    -0.395      +0.325
 apoc apoc_rth    S       66      33               33    33       33      30.3  +0.045       -76      21.2  -0.082  +0.011  +0.105        36.4    +0.285        +292    +0.253      -0.069
 apoc apoc_eth  all       94      45               45    45       45      33.3  +0.156      +176      22.2  +0.018  +0.169  +0.158        22.2    -0.278        -354    -0.295      -0.167
 apoc apoc_eth    R       44      23               23    23       23      30.4  +0.063       +62      21.7  -0.012  -0.012  +0.020        17.4    -0.448        -220    -0.403      -0.108
 apoc apoc_eth    S       50      22               22    22       22      36.4  +0.253      +115      22.7  +0.049  +0.358  +0.303        27.3    -0.100        -133    -0.183      -0.230
 apoc     apoc  all      200     102               93    76      102      32.4  +0.123      +259      22.5  -0.036  +0.098  +0.067        28.4    -0.017        -109    -0.142      -0.020
 apoc     apoc    R       84      47               43    33       47      31.9  +0.117      +220      23.4  -0.044  +0.037  -0.070        23.4    -0.191        -268    -0.399      +0.113
 apoc     apoc    S      116      55               50    43       55      32.7  +0.128       +38      21.8  -0.030  +0.150  +0.184        32.7    +0.131        +158    +0.078      -0.133

IN SAMPLE: aligned-value day types (study days; move in ATR in the accepted direction; ORB v1.4 and VA-trend, win = net > 0)
family      type       direction  days move_mean move_median  hit  orb_n orb_win  orb_R orb_net  orb_agree_n orb_agree_win orb_agree_R orb_agree_net  orb_disagree_n orb_disagree_win orb_disagree_R orb_disagree_net  va_n va_win   va_R va_net
   rth     above              up   192    -0.054      +0.035 54.7     88    52.3 +0.165   +1528           44          54.5      +0.142         +1526              44             50.0         +0.187               +2   192   54.7 -0.612  -6348
   rth     below            down    94    -0.074      -0.072 46.8     49    34.7 -0.317   -5539           28          35.7      -0.359         -3508              21             33.3         -0.261            -2031    94   46.8 -0.802  -5146
   rth    inside none (up shown)    87    +0.073      +0.122 59.8     41    48.8 +0.063    +391            0           NaN         NaN            +0               0              NaN            NaN               +0     0    NaN    NaN     +0
   rth     mixed none (up shown)   466    +0.004      +0.039 51.7    194    54.1 +0.186   +8544            0           NaN         NaN            +0               0              NaN            NaN               +0     0    NaN    NaN     +0
   rth not built none (up shown)    45    +0.041      +0.089 62.2     23    39.1 -0.033     -29            0           NaN         NaN            +0               0              NaN            NaN               +0     0    NaN    NaN     +0
   rth       all none (up shown)   884    +0.007      +0.045 53.8    395    49.9 +0.093   +4894            0           NaN         NaN            +0               0              NaN            NaN               +0   286   52.1 -0.674 -11494
   eth     above              up   178    -0.048      +0.045 56.2     83    53.0 +0.210   +2845           43          58.1      +0.201         +2306              40             47.5         +0.218             +539   178   56.2 -0.553  -4656
   eth     below            down    90    -0.113      -0.142 43.3     46    37.0 -0.315   -4918           26          38.5      -0.348         -2778              20             35.0         -0.272            -2140    90   43.3 -1.190  -5614
   eth    inside none (up shown)    89    +0.030      +0.069 55.1     42    50.0 -0.007    +182            0           NaN         NaN            +0               0              NaN            NaN               +0     0    NaN    NaN     +0
   eth     mixed none (up shown)   467    +0.006      +0.037 51.8    196    52.6 +0.170   +6446            0           NaN         NaN            +0               0              NaN            NaN               +0     0    NaN    NaN     +0
   eth not built none (up shown)    60    -0.011      +0.057 56.7     28    42.9 +0.035    +339            0           NaN         NaN            +0               0              NaN            NaN               +0     0    NaN    NaN     +0
   eth       all none (up shown)   884    +0.007      +0.045 53.8    395    49.9 +0.093   +4894            0           NaN         NaN            +0               0              NaN            NaN               +0   268   51.9 -0.767 -10270
IN SAMPLE: VA-trend (rth, N=1..5): n 286  win(net>0) 52.1%  R -0.6743  net -11494  p 0.9805  long n 192 R -0.6119  short n 94 R -0.8019  by year 2019:+304(36) 2020:-4001(88) 2021:-1954(88) 2022:-5843(74)
IN SAMPLE: neighbour 1 (eth, N=1..5): n 268  win(net>0) 51.9%  R -0.7667  net -10270  p 0.9869  long n 178 R -0.5527  short n 90 R -1.1899  by year 2019:+28(32) 2020:-4031(86) 2021:-2266(77) 2022:-4002(73)
IN SAMPLE: neighbour 2 (rth, N=1..3): n 365  win(net>0) 51.5%  R -0.6882  net -12456  p 0.9887  long n 233 R -0.7576  short n 132 R -0.5656  by year 2019:+82(48) 2020:-6726(111) 2021:-3091(104) 2022:-2721(102)

VPN1 cells (profile x level x side x trade) 156, with >= 150 events 48; aligned-POC events: rth 57, eth 45, together 102 (pick 7 needs 60)
picks (frozen in /home/claude/work/yt1/lab/data/studies/yt1/VPN1_selected.json)
  pick 1 [cell] eth1_val:S:break       events  209  brk_a04: n  209 win 34.9%  R +0.2123  net +740   brk_a08 R +0.0132   brk_a04x2 R +0.1543   placebo win 23.3% R -0.2346 (n 172)
  pick 2 [cell] rth3_val:S:break       events  154  brk_a04: n  154 win 34.4%  R +0.1940  net +270   brk_a08 R +0.1177   brk_a04x2 R -0.0061   placebo win 29.2% R +0.0005 (n 137)
  pick 3 [cell] on_poc:S:break         events  206  brk_a04: n  206 win 30.1%  R +0.0354  net +199   brk_a08 R +0.1942   brk_a04x2 R -0.1151   placebo win 24.7% R -0.1834 (n 198)
  pick 4 [cell] rth2_poc:S:break       events  173  brk_a04: n  173 win 29.5%  R +0.0052  net +412   brk_a08 R +0.0638   brk_a04x2 R -0.1642   placebo win 32.7% R +0.1407 (n 107)
  pick 5 [cell] rth3_poc:S:fade        events  150  a04x3: n  150 win 29.3%  R +0.0000  net +50   a08x3 R -0.0730   a04x2 R +0.0062   placebo win 21.8% R -0.2945 (n 87)
  pick 6 [stack] stack3+:break          events 4522  brk_a04: n 4522 win 29.5%  R +0.0082  net +1804   brk_a08 R +0.1284   brk_a04x2 R -0.0460   distinct orders 2493 on 536 days: R +0.0109 net +984
  pick 7 [apoc] apoc:fade              events  102  a04x3: n  102 win 32.4%  R +0.1232  net +259   a08x3 R +0.0980   a04x2 R +0.0671   distinct orders 93 on 76 days: R +0.0379 net +162
  pick 8 [vatrend] VA-trend               trades  286  win(net>0) 52.1%  R -0.6743  net -11494   nb1 (eth) n 268 R -0.7667   nb2 (rth N=1..3) n 365 R -0.6882

IN SAMPLE MID1 o00       real vs placebo [rows    ] a04x3   : real n   461 win 26.7% R -0.0947 | placebo n   386 win 22.5% R -0.2565 | diff win +4.14 pts, R +0.1618, two-proportion p 0.1644
IN SAMPLE MID1 o00       real vs placebo [rows    ] p20x3   : real n   461 win 23.0% R -0.0221 | placebo n   386 win 20.7% R -0.1064 | diff win +2.27 pts, R +0.0843, two-proportion p 0.4271
IN SAMPLE MID1 o00       real vs placebo [rows    ] brk_a04 : real n   461 win 22.6% R -0.2566 | placebo n   386 win 28.0% R -0.0549 | diff win -5.42 pts, R -0.2018, two-proportion p 0.0698
IN SAMPLE MID1 o00       real vs placebo [distinct] a04x3   : real n   461 win 26.7% R -0.0947 | placebo n   386 win 22.5% R -0.2565 | diff win +4.14 pts, R +0.1618, two-proportion p 0.1644
IN SAMPLE MID1 o00       real vs placebo [distinct] p20x3   : real n   461 win 23.0% R -0.0221 | placebo n   386 win 20.7% R -0.1064 | diff win +2.27 pts, R +0.0843, two-proportion p 0.4271
IN SAMPLE MID1 o00       real vs placebo [distinct] brk_a04 : real n   461 win 22.6% R -0.2566 | placebo n   386 win 28.0% R -0.0549 | diff win -5.42 pts, R -0.2018, two-proportion p 0.0698
IN SAMPLE VPN1 39 levels real vs placebo [rows    ] a04x3   : real n 10302 win 24.0% R -0.2048 | placebo n  7436 win 24.9% R -0.1664 | diff win -0.97 pts, R -0.0385, two-proportion p 0.1390
IN SAMPLE VPN1 39 levels real vs placebo [rows    ] p20x3   : real n 10302 win 20.3% R -0.1423 | placebo n  7436 win 21.4% R -0.1124 | diff win -1.07 pts, R -0.0299, two-proportion p 0.0833
IN SAMPLE VPN1 39 levels real vs placebo [rows    ] brk_a04 : real n 10302 win 28.0% R -0.0503 | placebo n  7436 win 27.1% R -0.0820 | diff win +0.82 pts, R +0.0317, two-proportion p 0.2295
IN SAMPLE VPN1 39 levels real vs placebo [distinct] a04x3   : real n  7711 win 24.0% R -0.2015 | placebo n  5753 win 25.0% R -0.1605 | diff win -1.03 pts, R -0.0409, two-proportion p 0.1670
IN SAMPLE VPN1 39 levels real vs placebo [distinct] p20x3   : real n  7711 win 20.7% R -0.1383 | placebo n  5753 win 21.6% R -0.1138 | diff win -0.90 pts, R -0.0246, two-proportion p 0.2053
IN SAMPLE VPN1 39 levels real vs placebo [distinct] brk_a04 : real n  7711 win 27.6% R -0.0611 | placebo n  5753 win 26.5% R -0.1055 | diff win +1.18 pts, R +0.0444, two-proportion p 0.1291
```
