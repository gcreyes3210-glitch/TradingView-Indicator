# Backtest log and current state

Symbol MNQ1!, correlated ES1!, 5-minute chart, Deep Backtesting 365 days (2025-09-23 → 2026-09-21), Fixed 1 contract,
commission $1/contract, slippage 1 tick. Strategy file: `ICT_SMT_IFVG_strategy.pine` (regenerate with `python3 tools/make_strategy.py`).
Analysis of exports: the `Signal` column tag `L|5m|S63C|H13|M15|K15|D7|L10|T3|htf:15m|P:15m|sess:London|smt:Swing+`
= side, feed TF, score+grade, six components (HTF/SMT/Session/Displacement/Liquidity/Structure), HTF tags, primary zone, session, SMT source.

## Current baseline = Run I (net +3,105 / year, 95 trades, win 33 %, PF 1.32, max drawdown −1,912; Run G without the daily slot: +2,885, DD −3,055)

| Section | Input | Value |
|---|---|---|
| 1b | IFVG filter mode | Loose |
| 1c | Minimum IFVG Confluence Score | 0 (score is NOT used as a gate) |
| 2 | Require HTF FVG | on |
| 2 | HTF slots | #1 5m **off**, #2 15m on, #4 1H on, #6 4H on, #7 1D on (Run I; unproven, 5 trades), #3/#5/#8 off |
| 4 | Feed-TF swings | on |
| 4 | HTF swing highs/lows (major) | **off** |
| 4 | PDH/PDL | on; PWH/PWL off |
| 7 | Require SMT / confirmed SMT | on / on |
| 8 | Feeds | 2m, 3m, 5m, 15m on (only 15m runs on a 5m chart) |
| S | Quantity / Exit model / Time stop | Fixed 1 / TP2 / on (200 bars) — since Run G |
| 10 | TP1 / TP2 risk:reward | 2.0 / 3.0 (4.0 tested in Run H, no gain) |
| S | Breakeven | 0 (off) |
| S | Entry | Market at inversion close |

## From-scratch checklist (if the inputs reset)
Change from default: 1b filter mode Loose · 1c min score 0 · 2 HTF #1 (5m) off, #7 (D) on · 3 correlated symbol = the OTHER index (ES1! on an MNQ chart, NQ1! on an MES chart) · 5 HTF swing highs/lows off · 10 point value 2 (MNQ) or 5 (MES) · S quantity Fixed 1 contract, exit model TP2, entry Market at inversion close, breakeven 0.
Confirm default: Require HTF FVG on; #2 15m, #4 1H, #6 4H on, #3/#5/#8 off; NDOG on; selection Auto Engine; pivot SMT on; feed swings on; PDH/PDL on, PWH/PWL off; key-level filter off; Require SMT on + confirmed on, max 10 bars SMT→IFVG; feeds 2m/3m/5m/15m on; section 9 filters OFF; stop Sweep High/Low + 2 ticks, TP1 2.0, TP2 3.0, time stop 200 bars on; reverse off.
Debug check before export: "Last IFVG in" = 15m 1H 4H 1D NDOG, "SMT live" names the correlated symbol, STRATEGY row shows closed trades.

## Runs

| Run | Change vs previous | n | Net | Verdict |
|---|---|---|---|---|
| A | zones 15m+ (5m slot off), all SMT sources, min score 0 | 110 | −193 | baseline before SMT-source fix |
| B | A + 5m zones on | 235 | −6,538 | 5m zones: 172 trades, −6,594, losing in both halves → **5m slot stays off** |
| C | A − PDH/PDL (HTF-swing toggle had not applied) | 109 | −466 | PDH sweeps were +716 in A → PDH/PDL stay **on** |
| C (2nd) | A − 1H swing SMTs + breakeven 1.0 R | 95 | +674 | 1H swing SMTs lost −1,211 on the 20 removed trades → **off**. Breakeven: rescued 16 stops (+2,126) but cut 8 winners (−2,934) and 3 time-exit winners (−475) → **off** |
| C2 | C without breakeven | 93 | +1,312 | **current baseline** |
| D | C2 − 15m zones (1H/4H/NDOG only) | 30 | −396 | higher zones alone lose and are too few → **15m slot stays on** |
| E | C2 + Entry = Limit at IFVG 50 % (CE), 12-bar validity | 80 | +545 | PF 1.09 (C2 1.15), max DD −2,624 (C2 −3,068), avg win 191 vs 281, avg loss 123 vs 154. 18 C2 trades never filled and those were +2,410 in C2 (10 wins). Older half +992 / newer −447. Limit entry trims losses but misses the best runners → **market entry stays** |
| F | C2 + Exit = Half at TP1, rest at TP2 (2 contracts) | 93 | +2,099 per contract | Same 93 trades as C2. PF 1.24 (C2 1.15), max DD −2,979 (−3,068), both halves positive (+1,408 / +691). 24 of the 31 TP1 winners ran on to TP2 (+1,583 extra), 4 reversed to stop after TP1 (−696), 3 time-exit (−102) → **new baseline**. Raw 2-contract net +4,198, DD −5,958 |
| G | F mechanics but Exit = TP2 only (3 R), 1 contract | 93 | +2,885 | Matches the estimate from F legs exactly. PF 1.31, win 34%, max DD −3,055, both halves positive (+1,394 / +1,491), longest losing streak 10. 5 stop-outs had reached 2 R first (−537) → **new baseline** |
| H | G but TP2 = 4 R | 93 | +2,820 | Flat vs G: PF 1.30, win 32%, DD −2,900. 17 of the 24 3 R winners reached 4 R (+1,668), 2 reversed to stop (−994), 5 ran out of time short of 4 R (−738). Net effect ≈ 0 → **stay at 3 R** |
| I | G + HTF slot 7 (Daily) on | 95 | +3,105 | 5 new daily-zone trades: 1 win (+1,050), 4 stops (−501). 3 4H trades displaced (+330). Net +220, all from one trade. PF 1.32, DD −1,912 (the June win cushions the June–July streak). Too few trades to judge → **left on (design intent), unproven** |
| J | Run I settings on **MES1!** (correlated NQ1!), quantity was Risk-module (1–23 ct) so results normalised per contract | 114 | −688 per contract | **Does not transfer.** Win 32%, PF 0.88, both halves negative (−615 / −73). Longs +378 (44% win), shorts −1,066 (23% win). By zone: 15m −455, 4H −338, 1D −188, 1H +81, NDOG +212. Raw risk-sized net −7,738 |
| K | Run I settings on MNQ, **prior year** (2024-09-22 → 2025-09-22), Fixed 1 ct | 86 | −2,028 | **Out of sample fails.** Win 29%, PF 0.72, both halves negative (−1,377 / −652), max DD −2,380, longest losing streak 9. Longs +24, shorts −2,052. 15m zones −720, 1H −512. No sub-group is positive in all three samples (I, J, K) |
| L | Run I settings, **Long only**, three samples | 51 / 42 / 51 | +1,092 / +144 / +119 | NQ this yr PF 1.19, NQ prior yr PF 1.04, ES this yr PF 1.05. Never negative, but two of three are flat: 144 trades, +1,355 total, about +9 per trade. Removing shorts removes the losses, it does not create an edge → **not tradeable on its own; shorts confirmed as the losing side** |
| M | Run I settings, Both directions, **Daily bias gate = Midnight NY open**, three samples | 45 / 38 / 62 | +1,935 / −2,534 / +835 | NQ this yr PF 1.45, NQ prior yr PF 0.39 (worst run of the series, both sides negative), ES this yr PF 1.31. Both current-year samples improve, the prior year collapses: the gate keeps trades already moving with the day and drops fresh reversals, which works only in a trending year → **rejected** (a filter that loses 2,500 in one of two years is not a filter) |
| M2 | Run I settings, Both directions, **Daily bias gate = Previous day close**, MNQ 2024-09-22 → 2026-09-20 | 82 (35 / 47) | −828 (−2,616 / +1,789) | Same shape as the midnight gate: prior yr PF 0.32, this yr PF 1.37, both sides lose in the prior year → **rejected** |
| N | Run I settings on the **1-minute chart** (1m IFVGs, ladder 2m→3m→5m, SMT from all feeds), MNQ 2024-09-22 → 2026-09-22 | 388 (209 / 179) | −2,676 (−304 / −2,373) | Win 26%, PF 0.82, max DD −3,555, avg win 124 / avg loss 53. Prior yr PF 0.95, this yr PF 0.73. Longs −40, shorts −2,636. Exits 275 stop / 71 target / 42 time. Every 365-day test before this used 5m IFVGs only; the 1m IFVG entry is worse on both years → **lower timeframes rejected** |

## Findings that held in every run and both halves of the year
* 5-minute HTF zones lose. 1H-swing-sweep SMTs lose. Breakeven at 1 R costs more winners than it saves.
* **The NQ edge did not transfer to ES/MES (Run J) and did not hold on the prior NQ year (Run K).** Runs C2→I were tuned on one symbol-year and that is the only sample where the rules make money. Across I, J, K: longs were ≥ 0 in all three (+1,495 / +378 / +24), shorts were −1,066 and −2,052 in two of three. Pivot SMTs were positive in both NQ years but negative on ES. Nothing else repeats.
* Across every variant, the 2025-09 → 2026-09 year is the profitable one and 2024-09 → 2025-09 is not, on both symbols and with every gate. The year, not the symbol or the filter, decides the result. That is the definition of no edge.
* Timeframe note: all 365-day runs A–M used 5-minute IFVGs (on a 5m chart the 2m/3m feeds are off and the ladder is empty; the 15m feed only supplies SMTs). Run N tested the 1-minute IFVG entry over two years and it lost on both.
* **Conclusion of this pass: the current signal set has no demonstrated edge on 5m or 1m.** The exit work (3 R target, no breakeven, market entry) is sound mechanics and carries over, but the entry rules need a different idea, not more filters.

## Findings that flipped between halves (regime, NOT to be gated on)
* Confluence score ≥ 70 (neutral, then −1,588), killzone sessions (mildly positive, then −1,771), displacement ≥ 12 (neutral, then −1,100),
  15m vs 1H+ zones (+1,234 vs +187, then −872 vs +762). Any of these would be curve fitting on 93 trades.

## Open experiments, in order
1. (done: L long-only = flat, M midnight bias = rejected)
1. Optional limit-entry variant: CE limit but keep the original TP levels (Run E recomputed TPs from the smaller risk, so the winners were capped smaller).
4. Re-weight the confluence score only once an entry rule survives all three samples; until then the gate stays at 0.

## Pine limits (do not regress)
Script must stay under 550 local scopes and 80,000 compiled tokens; the file sits near ~470 scopes and just under the token cap.
`request.security` series are the main token cost. Do not add features without removing something.

---
# VP Value Area Fade (`VP_ValueArea_strategy.pine`)
Rule set v1: profile 18:00→09:30 NY, VA 70 %, 1-pt rows · trade 09:30→12:00 NY · excursion ≥ 2 pts beyond VAH/VAL then a close back inside → entry toward POC · stop = excursion extreme + 2 pts · min RR 0.8 · max risk 50 pts · one trade per side per day · flat at 12:00.
**Status (2026-09-22): VP2y is the forward-test candidate on MNQ.** Frequency/win-rate variants VP3a, VP3b and VP4 were all rejected on three years; the overnight-profile, open-outside, far-edge version is the only one that holds. Rule: overnight profile 18:00→09:30 NY, open outside the 70 % value area, six 5-minute closes back inside, enter toward the far edge, stop = edge + 0.25 × VA width, entries 09:30–12:00 NY, hold to 16:00, one trade a day. NQ three years: 58 trades, +1,667 per contract, PF 1.43, DD −700, every year positive. ES same rule: +184, PF 1.10, two of three years positive. Alerts are built into the strategy file (input 'Fire alert() messages').
Every variant is judged on MNQ two years (2024-09-22 → 2026-09-22) and MES two years before any single trade is looked at.

| Run | Change | n | Net | Verdict |
|---|---|---|---|---|
| VP1 | v1 as above, MNQ 5m, 2024-01 → 2026-09 (test-window default start) | 181 | −861 | Win 34%, PF 0.85, DD −1,671. Every year negative (PF 0.85 / 0.91 / 0.79). Avg loss 49, avg win 81: stops small as designed, win rate far below the 60 % a value-area fade should give. No slice positive (best: VA width 60–120 PF 1.03, RR 1–2 PF 0.98). First 5m close back inside value is too early → **rejected** |
| VP1-ES | same on MES | 198 | −1,388 | PF 0.77, years 0.97 / 1.08 / 0.41. Open-below days +431 (24 trades) is the only positive slice, and it is 'above' that was positive on NQ → noise. **Consistent non-edge on both symbols** |

## VP 80 % Rule (`VP_80Rule_strategy.pine`) — v2
v2.1 (2026-09-22): the finished profile's levels now activate at the start of the next Trade window instead of at the profile's end, so Profile session 0930-1600 gives the PREVIOUS RTH day's value area (Dalton's original rule). Overnight mode is unchanged (profile end and window start coincide).
Profile check 2026-09-22: strategy VAH 30,866 / POC 30,771 / VAL 30,749 vs Aceflw ONVP 30,845 / 30,776.5 / 30,753 (POC and VAL within a row or two; VAH ~20 pts higher, methodology difference, accepted).
Rule set: same overnight profile · RTH open must be outside value · after `acceptBars` (6 × 5m = 30 min) consecutive closes back inside value, enter toward the far edge · stop = edge + 0.25 × VA width · min RR 0.8 · max risk 1 × VA width · one trade per day · flat at 12:00. All thresholds relative to the value-area width.

| Run | Change | n | Net | Verdict |
|---|---|---|---|---|
| VP2 | v2 defaults, MNQ 5m, 2023-09-22 → 2026-09-22 | 58 | +1,088 | Win 52%, PF 1.42, max DD −475, longest losing streak 6. **All three years ≥ 0**: +416 (PF 1.53) / +31 (PF 1.03) / +641 (PF 2.04). Longs +662 / shorts +426, open-above +426 / open-below +662. Exits: 24 time / 19 stop / 15 target → the far edge is often not reached by 12:00. ~19 trades a year: small sample, first positive multi-year result of the project. Awaiting ES |
| VP2x | v2, Trade window 0930-1600 (entries and hold through the session), MNQ | 83 | +1,652 | Win 47%, PF 1.31, DD −700. Years +386 (PF 1.25) / +864 (PF 1.42) / +402 (PF 1.24). Time exits down to 8 (from 24). Shorts +1,473 / longs +178. The 25 entries after 12:00 ET net about zero; the gain comes from letting morning trades run |
| VP2y | v2, **Entry window 0930-1200, Trade window 0930-1600**, MNQ | 58 | +1,667 | Same 58 entries as VP2, held through the session. Win 47%, PF 1.43, DD −700, years +328 (PF 1.27) / +946 (PF 1.67) / +393 (PF 1.30). Exits 30 stop / 25 target / 3 time. Avg win 207, avg loss 126. **Best NQ variant: the 12:00 cut-off was costing winners; afternoon entries add nothing** → candidate for forward test |
| VP3a | VP2y + 'Only when the RTH open is outside value' OFF (any morning excursion + acceptance), MNQ | 160 | +133 | PF 1.01, DD −2,378, years +762 / +186 / −814. Open-outside days +1,035 (63), open-inside days −902 (97, PF 0.87). The information is in the open, not in the acceptance pattern → **rejected** |
| VP3a-ES | same on MES | 195 | +645 | PF 1.10, years +90 / +10 / +502, losing streak 13. Inside-open days +545 here vs −902 on NQ: the two symbols disagree on the sign → noise. Generalised setup stays rejected |
| VP3b | VP2y + Target = POC, min RR 0 (first attempt with min RR 0.8 skipped 37 of 58 entries and was discarded), MNQ | 65 | +186 | Win 66% but avg win 82 vs avg loss 152: PF 1.06, DD −1,196, year 3 −766. The far-edge target is what pays on NQ → **rejected** |
| VP3b-ES | same on MES | 60 | +476 | Win 67%, PF 1.35, years +3 / +505 / −32. Better than the far edge on ES (narrow value areas), worse on NQ: the two symbols disagree → not adopted as the rule |
| VP4 | VP2y rule against the **previous RTH day's** value area (Profile session 0930-1600, v2.1), MNQ | 71 | −934 | PF 0.80, DD −2,102, years +184 / −1,175 / +57, 16 time exits. Same mechanics, different reference profile, edge gone. **The edge is specific to the overnight (Asia+London) value area at the NY open** → rejected |
| VP4-ES | same on MES | 18 | −300 | Win 22%, PF 0.47, 10-trade losing streak. ES opens outside its previous RTH value area far less often and the rule fails when it does. Confirms the NQ rejection |
| VP2y-ES | Entry 0930-1200, hold to 1600, MES | 53 | +184 | PF 1.10, years −29 (0.95) / +163 (1.36) / +50 (1.06). Best ES variant, still thin. Longs +236 / shorts −52 |
| VP2x-ES | v2, Trade window 0930-1600, MES | 75 | −78 | PF 0.97, years −205 (PF 0.76) / +112 (PF 1.15) / +16 (PF 1.02). Afternoon entries (12:00–16:00 ET) −261 on 22 trades. ES stays flat under both windows |
| VP2-ES | same on MES | 53 | +22 | Win 49%, PF 1.02, DD −325. Years +152 (PF 1.47) / +136 (PF 1.55) / −268 (PF 0.45). Longs +255 (63% win), shorts −233 (35%). 26 of 53 exits were the 12:00 flatten. Flat overall, 2 of 3 years positive. **Across both symbols 5 of 6 symbol-years ≥ 0 → lead worth one structural test (full-session window), not a system** |

## Opening Range Breakout (`ORB_strategy.pine`) — v1
Why: VP2y is the only rule that survived three years on both symbols, but ~20 trades a year is too few to trade or to learn from (user, 2026-09-22). ORB is the highest-frequency principled intraday rule (one trade most days) and needs no indicator or profile. Tested on MNQ first; ES only if a result needs a second symbol to settle it.
Rule set (v1 defaults): opening range = 09:30–09:45 NY (three 5m bars) · entry = first 5m close beyond the range ± 2 ticks inside 09:45–11:30 · stop = other side of the range · target = 2R · one breakout per side, max 1 trade a day · flat at 16:00 · $1 commission per side + 1 tick slippage per order.
Tag: `L|ORB|or:42|pd:18|on:inside|gap:+35|ent:close|risk:46|rr:2|n:1|h:9|m:50|dow:2` (or = range width pts, pd = width as % of previous RTH day range, on = opening range vs overnight range, gap = open − previous close). Slice with `python3 tools/analyze_tags.py export.csv`.
**Status 2026-09-22: ORB4 settings (15-min range, close-beyond entry, stop at the other side, hold to close, opening range must break the overnight range) are the forward-test candidate.** Full 2020-01 → 2026-09 MNQ record: 821 trades, +21,182, PF 1.28, DD −3,198, one losing year (2020).
Planned variants, one change each, in this order: stop-order entry (ent:stop) · 09:30–10:00 range · no target (hold to close) · 1R / 3R · max 2 trades (reversal after a stop-out) · then any filter the tags justify (pd, open location, gap).

| Run | Change | n | Net | Verdict |
|---|---|---|---|---|
| ORB5 | ORB4 settings, **out-of-sample**: MNQ from the start of TradingView's 5m history (2020-01-07) to 2026-09-22; only the part before 2022-09-22 is new data | 330 (OOS) | +3,844 | **Survives, at a reduced edge.** OOS: win 51%, PF 1.12, DD −3,198, avg +0.11 R (in-sample +0.15 R). Calendar years: 2020 −1,263 (PF 0.85, the COVID year, 99 trades) / 2021 +2,509 (PF 1.29) / 2022 to Sep +2,598 (PF 1.18). 22 of 27 quarters positive over the full 6.7 years; 4 of the 5 losing quarters are in 2020–Q1 2021. Full run 2020-01 → 2026-09: 821 trades, +21,182, PF 1.28, DD −3,198, +0.14 R per trade, longs +10,640 / shorts +10,542. → **forward test with alerts.** Note for the next variants (30-min range, stop-order entry): they are now variations on a rule that already works, judged on the full 6.7-year window |
| ORB4 | ORB3 + Opening range vs overnight range = 'Range must break the overnight range' (Min close beyond the edge was left at 0.15, so this is ORB3 filtered, not ORB2), MNQ, four years | 491 | +17,338 | **Reproduces the ORB3 split exactly.** Win 50%, PF 1.38, DD −3,143, avg +0.15 R, streak 8. Years +3,282 (PF 1.34) / +4,082 (1.43) / +5,427 (1.52) / +4,546. 14 of 17 quarters and 31 of 49 months positive, worst month −1,426. Longs +7,752 / shorts +9,586 (first rule in the project where shorts pull their weight). 162 stops / 329 time exits, median trade −0.02 R, p90 +1.6 R, best +8.2 R: a trend-day rule that pays from the tail. Break days with a gap < 0.5 × range are flat (−576, 148) but not consistently negative → not filtered. Break-direction-only leaves money on the table (against-break +5,452). **Candidate; needs unseen data: ORB5 = same settings, MNQ 2019-06-01 → 2022-09-22** |
| ORB3 | ORB2 + Min close beyond the edge 0.15 × range, MNQ, four years | 936 | +10,345 | PF 1.11, DD −8,174, years +4,752 (1.26) / +5,722 (1.31) / +2,506 (1.10) / −2,634. A wash: the filter does not remove the tentative days, it delays the entry to a later, worse-priced bar (1008 → 936 trades). The ORB2 split measured 'the FIRST breakout bar was decisive', which is a different rule (skip the side otherwise), not tested. Filter stays available, back to 0. **The new `on` tag is the finding**: opening range that breaks the overnight high/low +17,338 (491, win 50%, PF 1.38, DD −3,143, avg +0.15 R, **years +3,282 / +4,082 / +5,427 / +4,546**) vs opening range inside the overnight range −6,993 (445, PF 0.86, −2,922 and −7,180 in the last two years). Holds for both sides (topBreak longs +7,038 / shorts +4,738; botBreak +714 / +4,848) and both entry hours. Break days with a gap < 0.5 × range are flat (−576, 148). → v1.2 adds the overnight-range filter; next run ORB4 = ORB2 + 'Range must break the overnight range' |
| ORB2 | ORB1 with Target = None (hold to close), MNQ, four years | 1008 | +8,988 | PF 1.09, DD −9,364, years +4,713 (1.24) / +3,886 (1.19) / +3,892 (1.16) / −3,503; in R +18 / +26 / +6 / −5. Same as ORB1 within noise: the 2R target neither helps nor hurts, the exit is not where the edge is. Two splits hold across both runs and, for the first, every year: **breakout bars that close ≥ 0.15 × range beyond the edge +13,311 (493, avg +0.12 R, years +3,969 / +3,074 / +6,356 / −87) vs tentative breakouts −4,323 (515, negative in years 3 and 4)**; days with a gap ≥ 0.5 × range +14,758 vs small-gap days −5,770 (positive 3 of 4 years, year 4 −2,837). Shorts +1,884 vs longs +7,104. → v1.1 adds 'Min close beyond the edge (x range width)'; next run ORB3 = ORB2 + 0.15 |
| ORB1 | v1 defaults, MNQ 5m, **2022-09-22 → 2026-09-22 (four years)** | 1008 | +9,582 | Win 45%, PF 1.10, DD −9,935, avg +0.05 R per trade. Years (Sep→Sep): +4,032 (PF 1.21) / +3,338 (1.17) / +6,346 (1.26) / **−4,300 (0.88)**; in R units +14 / +18 / +16 / −3, so year 4 is flat in R and the dollar loss is the 2× larger ranges (avg risk 85 → 162 pts). Exits 428 stop / 421 time / 159 target: the 2R target is hit 16% of the time, the hold-to-close exits contribute +40,684 of gross profit. Breakouts on the 09:45–09:55 bars +10,748 (630), later ones −1,166 (378). Big breakout bars (risk > 1.15 × range) +11,304 vs small ones −1,722. Longs +6,480 / shorts +3,102. Wednesday +2,282, Thursday −3,048, Friday +7,159 (n≈200 each, noise-level). 'open' tag was always 'inside' by construction (fixed: tag now records where the range sits vs the overnight range). Verdict: **small positive edge, too thin to trade at 1 tick slippage; the value is in early, strong breakouts held to the close** → next single change: no target |

## VWAP Reversion (`VWAP_Reversion_strategy.pine`) — v1
Why: ORB4/ORB5 showed breakouts lose on the ~55 % of days whose opening range stays inside the overnight range. Those are rotation days; the VWAP sigma bands are the natural tool for them, and a rule that trades them would complement ORB rather than overlap it (one regime filter, two strategies).
Rule set (v1 defaults): balance days only · VWAP anchored at 09:30 · arm on a 5m close beyond ±2σ, enter on the first close back inside · stop = excursion extreme ± 0.5σ · target VWAP · min RR 1.0 · one per side per day · entries 10:00–15:00, flat 16:00 · $1/side + 1 tick slippage.

| Run | Change | n | Net | Verdict |
|---|---|---|---|---|
| VWR1 | v1 defaults, MNQ 5m, 2020-01-07 → 2026-09-22 | | | awaiting export |
