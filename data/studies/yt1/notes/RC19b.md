# RC19b — second, independent coding of C19b (TRADING RUSH single trigger: Keltner)

Module: `tools/yt1/s_RC19b.py`. Written from the spec text (C19a–e entry, Family C common frame, Common rules) and
research note block 18 only. No `s_C*` / `s_E*` module, no other note and nothing in `data/studies/yt1/is/` was opened.

## 1. Readings added beyond the spec text (one per line; each is a place a comparison could differ)
1. Keltner: basis = EMA(20) of the close, bands = basis ± 2 × ATR(10), ATR being Wilder's average of the true range (`ind.keltner(n=20, mult=2.0, atr_len=10)`).
2. "Opens and closes above the upper Keltner": the bar's open AND its close are both strictly above the band value of that same bar (the value computed with that bar's close, as drawn on a chart), not the previous bar's band.
3. "After one that did not": the bar immediately before it in the 24-hour series did not both open and close above its own upper band. So the signal is the first bar of a run; a second bar of the same run is not a signal. The bar before may lie before 09:30. It must have a band value (warm-up only).
4. Close > EMA200 is tested at the signal bar, strictly. Short = the mirror: open and close strictly below the lower band after a bar that did not, close < EMA200.
5. Window: the bar's clock closing time (open time + N minutes) is 09:35 to 15:00, both ends included. 5-minute bars opening 09:30 … 14:55; 3-minute bars opening 09:33 … 14:57 (the 09:30 3-minute bar closes at 09:33 and is out); 15-minute bars opening 09:30 … 14:45.
6. Swing stop: the 10 consecutive bars k−9 … k of the 24-hour series (they can include bars before 09:30), lowest low − 1 tick for a long, highest high + 1 tick for a short.
7. Target: close ± 1.5 × |close − stop|, put on the tick grid with `core.tick_round(x, "nearest")`. A raw target exactly half-way between two ticks goes to the even tick (that function uses Python's `round`). This is not a rare case: 763 of the 1,492 base orders have a raw target on a half tick, so a coder who rounds halves another way would differ by one tick on those targets.
8. An order is produced on every qualifying bar, long or short. One position at a time across both sides, no daily cap. A signal in the opposite direction does not close an open trade; it is skipped.
9. Neighbours: EMA 20 / ATR 10 / EMA 200 and the 10-bar swing are counted in bars of the variant's timeframe.
10. Nothing from the article that the spec does not state is coded (no daily 9-EMA "good market" filter).

## 2. Coding errors found after first seeing results
None. The module was run once and not changed.

## 3. Hand check (5-minute bars, EMA, ATR and bands rebuilt separately with pandas, not `ind.py`)
- 2019-10-22 short, signal bar 11:25 (decision 11:29): open 7939.50 < lower band 7939.65, close 7935.25 < band, close < EMA200 7956.20; the 11:20 bar opened at 7944.00 above its band 7941.46. Stop = 10-bar high 7969.00 + 1 tick = 7969.25. Entry 7935.00. Target 7935.25 − 1.5 × 34.00 = 7884.25; first touch is the 15:47 bar (open 7887.00, low 7883.25), fill 7884.50. P&L +99.0, R +1.445. Matches.
- 2021-07-02 long, signal bar 13:00 (13:04): open 14688.25 and close 14688.75 > upper band 14685.01, close > EMA200; the 12:55 bar opened at 14680.25 below its band 14683.60. Stop = 14663.00 − 1 tick = 14662.75. Entry 14689.00. Target 14688.75 + 1.5 × 26.00 = 14727.75, touched at 15:50 (high 14728.00), fill 14727.50. P&L +75.0. Matches.
- 2021-11-17 long, signal bar 11:50 (11:54): open 16374.50 and close 16377.75 > band 16372.70; the 11:45 bar opened at 16368.25 below its band 16369.72. Stop = 16336.25 − 1 tick = 16336.00. Raw target 16440.375 → 16440.50 (half tick, to the even tick). Stop touched at 12:19 (open 16338.25, low 16335.50), fill 16335.75. P&L −86.5. Matches.
- 2021-03-24 short, signal bar 09:35 (09:39): open 13035.75 and close 13017.25 < band 13046.43, close < EMA200 13073.05; the 09:30 bar opened above its band. Stop = 13093.50 + 1 tick = 13093.75 (the 10-bar high comes from a pre-market bar). Target 12902.50, touched at 13:11, fill 12902.75. Matches.
- 2019-08-01, one-position rule: orders at 09:39 (long), 13:34, 14:09 and 14:29 (shorts). The long was stopped at 13:40, so the 13:34 short was skipped and the 14:09 short was taken (stop 8000.00 = 7999.75 + 1 tick, target 7597.50 not reached, flat at 15:59: 7812.50 + 1 tick = 7812.75, P&L +50.0). Matches.
- Counts: 1,492 candidate orders, 815 trades (392 long, 423 short; 430 time, 232 stop, 153 target); signal minutes run 09:34 … 14:59; at most 3 trades in a day; no trade on a roll day or the day after.

## 4. Final in-sample output
```
RC19b  Keltner (20, 2 x ATR10) open-and-close outside + EMA200 (second coder)   phase is   bars 2019-06-02 18:00:00-04:00 -> 2022-12-30 16:59:00-05:00
base                   n   815  net    +11920  R  +0.091  win  52.1  pf  1.21  dd    -2658  p 0.0034  yrs+ 4/4  h1 +0.091 h2 +nan  | +562 +197 +1587 +9574 +0 +0 +0 +0
nb1                    n  1128  net     +8520  R  +0.065  win  49.0  pf  1.11  dd    -3516  p 0.0157  yrs+ 3/4  h1 +0.065 h2 +nan  | +640 -1856 +1307 +8428 +0 +0 +0 +0
nb2                    n   409  net     +9666  R  +0.085  win  56.2  pf  1.36  dd    -1456  p 0.0043  yrs+ 3/4  h1 +0.085 h2 +nan  | -1 +1264 +1878 +6524 +0 +0 +0 +0
```
`python3 tools/yt1/run.py RC19b --check`: **PASS** (16 of 16 cuts identical under a mirrored future).
