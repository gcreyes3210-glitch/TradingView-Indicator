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
| M | Run I settings, Both directions, **Daily bias gate = Midnight NY open** | 45 / 38 | +1,935 / −2,534 | NQ this yr PF 1.45, NQ prior yr PF 0.39 (worst run of the series, both sides negative). The gate keeps trades already moving with the day and drops the fresh reversals, so it removes winners in a mean-reverting year and keeps late entries in a trending one → **rejected** |

## Findings that held in every run and both halves of the year
* 5-minute HTF zones lose. 1H-swing-sweep SMTs lose. Breakeven at 1 R costs more winners than it saves.
* **The NQ edge did not transfer to ES/MES (Run J) and did not hold on the prior NQ year (Run K).** Runs C2→I were tuned on one symbol-year and that is the only sample where the rules make money. Across I, J, K: longs were ≥ 0 in all three (+1,495 / +378 / +24), shorts were −1,066 and −2,052 in two of three. Pivot SMTs were positive in both NQ years but negative on ES. Nothing else repeats.
* **Conclusion of this pass: the current signal set has no demonstrated edge.** The exit work (3 R target, no breakeven, market entry) is sound mechanics and carries over, but the entry rules need a different idea, not more filters.

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
