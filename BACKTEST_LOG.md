# Backtest log and current state

Symbol MNQ1!, correlated ES1!, 5-minute chart, Deep Backtesting 365 days (2025-09-23 → 2026-09-21), Fixed 1 contract,
commission $1/contract, slippage 1 tick. Strategy file: `ICT_SMT_IFVG_strategy.pine` (regenerate with `python3 tools/make_strategy.py`).
Analysis of exports: the `Signal` column tag `L|5m|S63C|H13|M15|K15|D7|L10|T3|htf:15m|P:15m|sess:London|smt:Swing+`
= side, feed TF, score+grade, six components (HTF/SMT/Session/Displacement/Liquidity/Structure), HTF tags, primary zone, session, SMT source.

## Current baseline = Run C2 (net +1,312 / year, 93 trades, win 39 %, PF 1.15, max drawdown −3,068)

| Section | Input | Value |
|---|---|---|
| 1b | IFVG filter mode | Loose |
| 1c | Minimum IFVG Confluence Score | 0 (score is NOT used as a gate) |
| 2 | Require HTF FVG | on |
| 2 | HTF slots | #1 5m **off**, #2 15m on, #4 1H on, #6 4H on, #7 1D **off** (was on in Runs A/B, untested since), #3/#5/#8 off |
| 4 | Feed-TF swings | on |
| 4 | HTF swing highs/lows (major) | **off** |
| 4 | PDH/PDL | on; PWH/PWL off |
| 7 | Require SMT / confirmed SMT | on / on |
| 8 | Feeds | 2m, 3m, 5m, 15m on (only 15m runs on a 5m chart) |
| S | Quantity / Exit model / Time stop | Fixed 1 / TP1 / on (200 bars) |
| S | Breakeven | 0 (off) |
| S | Entry | Market at inversion close |

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

## Findings that held in every run and both halves of the year
* 5-minute HTF zones lose. 1H-swing-sweep SMTs lose. Breakeven at 1 R costs more winners than it saves.

## Findings that flipped between halves (regime, NOT to be gated on)
* Confluence score ≥ 70 (neutral, then −1,588), killzone sessions (mildly positive, then −1,771), displacement ≥ 12 (neutral, then −1,100),
  15m vs 1H+ zones (+1,234 vs +187, then −872 vs +762). Any of these would be curve fitting on 93 trades.

## Open experiments, in order
1. Partial exits (half at TP1, half at TP2; needs 2 contracts).
2. Daily HTF slot back on (was off since Run C by accident; 5 trades in Run A).
3. Optional limit-entry variant: CE limit but keep the original TP levels (Run E recomputed TPs from the smaller risk, so the winners were capped smaller).
4. Re-weight the confluence score from data only once ≥ 200 trades of the final mechanics exist; until then the gate stays at 0.
5. Second symbol (ES/MES with NQ correlated) for an independent sample.

## Pine limits (do not regress)
Script must stay under 550 local scopes and 80,000 compiled tokens; the file sits near ~470 scopes and just under the token cap.
`request.security` series are the main token cost. Do not add features without removing something.
