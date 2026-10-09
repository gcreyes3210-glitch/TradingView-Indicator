# YT7 — the hourly add to an open ORB trade (G10) and a footprint study on it (FLOW3), pre-registered 2026-10-09

Written before any YT7 code was run.

**Where this comes from, disclosed.** YT6's pick 1 failed its out-of-sample test (p 0.088). Split afterwards by what
ORB v1.4 was doing, its trades looked like this on the full span: with ORB already open on the same side 194 trades,
52.6 % wins, +10,354 $ (55 % and +5,116 $ in 2019–2022, 50 % and +5,238 $ in 2023–2026); on days ORB never traded
171 trades, 38 % wins, +798 $. **So the rule in Part 1 was found by looking at all the data, both halves. There is no
untouched data left to test it on.** Part 1 can only check that the rule is coded right (a second coder, from this
text alone), how it behaves at its neighbours, and whether the signal adds anything beyond "ORB is still open". The
real test is forward tracking. Part 2 is different: no order-flow number has been looked at for these trades, so a
split into 2019–2022 (search) and 2023–2026 (test) is clean for the footprint question.

Data, engine, fills, R, look-ahead test and order of work as `YT1_SPEC.md`. Roll days and the day after not traded.

# Part 1 — G10, the hourly add

**ORB v1.4** is the traded rule as `tools/orb_engine.py` defines it, taken inside the harness from
`tools/yt1/cal_orb.py` (`orders(ctx)` through `core.run_orders`): one trade a day, entry at a 5-minute close between
09:45 and 11:30, stop at the other side of the 09:30–09:45 range, no target, flat at the flat bar.

**The signal (YT6 pick 1, unchanged; long side written, short mirrors):**
- Overnight high = the highest high from 18:00 to 08:29 of the current trading day.
- On 1-minute bars of the continuous series, a bullish CISD (`tt.cisd`) whose bar is one of 09:30 … 10:59 and whose
  protected low is above the overnight high. The **first** such signal of the day, long or short, is the day's signal.
- Order: buy at the open of the first 1-minute bar of the next clock hour (10:00 or 11:00). Cancelled if price trades
  at or below the stop price between the signal bar's close and that open.
- Stop 1 tick below the protected low. Target 2R from the fill price. Flat at the flat bar.

**G10 base:** take the day's signal only if, at that hour's open, an ORB v1.4 trade entered earlier that day is still
open and is on the same side. One add a day. The add is its own position: its own stop and target; it does not move
or close when ORB exits.

- **Neighbours:** target 1.5R and 3R.
- **Reported, no verdict:**
  - `retry`: if the day's first signal is cancelled or is not aligned at its hour, the next signal of the day
    (same definition, bars to 10:59) may be used; still one add a day.
  - `alone`: the signal on days when ORB has no open same-side trade at that hour (everything base leaves out).
  - `naive` **benchmark:** no signal at all. At 10:00, or at 11:00 if ORB entered at or after 10:00, if ORB is open:
    enter at that open on ORB's side with ORB's stop, no target, exit when ORB exits. This is "second contract on
    the hour whenever ORB is still in".
- **Criterion (reported with the disclosure above):** the usual one on the full span — at least 6 of 8 calendar years
  net positive, mean R ≥ +0.05, both halves non-negative, both neighbours the same sign, p < 0.05 / 102 for a pass
  and p < 0.05 for a candidate (one-sided bootstrap, 10,000 resamples, seed 1). Whatever it says, the status of G10
  can be at most **"candidate found in hindsight, forward test required"**.
- **Second coder:** written from this text, `tt.py`, `core.py` and `cal_orb.py` only, without opening the YT6 grid
  code. Afterwards its base trades are compared with the YT6 pick 1 trades that meet the same ORB condition; every
  difference is listed and explained, and the code is changed only for a misreading of this text.

# Part 2 — FLOW3, footprint and order flow at the add

**Trades:** G10 base trades (as produced by the YT6 implementation plus the ORB condition) whose date is one of the
order-flow days (`data/flow`, NQ and ES, 09:30–11:34, to 2026-09-22). **Decision time** = the end of the last
1-minute bar before the entry (09:59 or 10:59). Nothing after it is used.

**Measures.** Deltas use the CME aggressor flag; every signed measure is in the trade's direction (for a long,
positive = aggressive buying / price above). All are ratios, so one threshold can be carried across years.

| Code | Measure |
|---|---|
| `cum` | NQ delta ÷ NQ volume, 09:30 → decision |
| `last15` | NQ delta ÷ volume over the last 15 minutes before the decision |
| `pull` | NQ delta ÷ volume during the pullback the signal ended: from the first 1-minute bar of the CISD's run (not before 09:30) through the signal bar |
| `since` | NQ delta ÷ volume from the minute after the signal bar to the decision (missing if there is no such minute) |
| `es_cum` | ES delta ÷ ES volume, 09:30 → decision |
| `div` | `cum` − `es_cum` |
| `vol_rel` | NQ volume in the last 15 minutes ÷ the average 15-minute volume from 09:30 to the decision (unsigned) |
| `poc` | (decision close − session point of control) × side ÷ session range; point of control = the price with the most NQ volume in the completed 5-minute footprint bars 09:30 → decision; session range = high − low of those bars |
| `stack` | In the last three completed 5-minute footprint bars: the longest run of stacked diagonal imbalances on the trade's side minus the longest against it (buy imbalance at price p: buy volume at p ≥ 3 × sell volume one tick below, floor 1 contract; sell imbalance the mirror; a run = consecutive ticks; the larger of the three bars is used for each side) |
| `brk_delta` | Of the NQ footprint volume traded beyond the broken overnight level (above the overnight high for a long), 09:30 → decision: (buy − sell) ÷ (buy + sell). Missing if none traded there |
| `brk_share` | Share of the session's NQ footprint volume, 09:30 → decision, that traded beyond the broken overnight level |

**Search, 2019-06 → 2022-12 only.** For each measure the threshold is its in-sample median over the trades; "high"
= at or above it. Recorded for both sides: n, wins, win rate, mean R, net. Measures with fewer than 25 trades on
either side are set aside. **Picks:** the two measures with the largest absolute difference in win rate between the
sides; the favourable side of each is the one with the higher in-sample win rate. Thresholds, sides and picks are
frozen and stamped before the later data is read.

**Test, 2023-01 → 2026-09-22, run once.** For each pick, with the frozen threshold and side: favourable-side win
rate minus unfavourable-side win rate. **It counts** if the difference is positive with p < 0.025 (0.05 / 2;
one-sided permutation of the side labels, 20,000 shuffles, seed 1) and the favourable side's mean R is above the
unfavourable side's. Otherwise it does not count.

Reported with it: every measure in both periods with the frozen thresholds; the two picks combined (trades on both
favourable sides); the same table for all YT6 pick 1 trades on order-flow days whether aligned or not.

**Power, stated in advance.** About 80 in-sample and about 110 out-of-sample trades, so about 55 a side in the test.
A true difference in win rate has to be around 20 points before this test is likely to see it; a smaller real
effect will read as "does not count". A measure that counts here is a lead for forward tracking, not a filter.

Nothing here is adopted into the traded rule whatever the result.
