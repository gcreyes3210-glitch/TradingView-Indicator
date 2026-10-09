# YT2 — the remaining TRADING RUSH single triggers, pre-registered 2026-10-09 (written before any YT2 code was run)

**What this is.** 29 more indicator triggers from one source, the TRADING RUSH "38 strategies" video and its companion
videos (article versions: https://tradingrush.net/i-tested-7000-trades-with-38-trading-strategies/ and the per-indicator
pages listed in `data/studies/yt1/research/C_indicators.md`, blocks 1, 5, 9, 13 and 18). YT1 tested five of that set
(C19a–e) and left the rest unrun; this batch runs them. It was written after YT1's results were known, so it is logged
as a separate batch and is not a re-test of anything in YT1.

**Prior.** Low. The creator's own win rates for these triggers sit near the 40 % break-even of a 1.5R target outside
his hand-picked "extremely good" periods, and his articles state almost no indicator settings. Every setting below is
the TradingView built-in default *(R)* unless the article gives a number.

**Data, engine, fills, days not traded, R, order of work, look-ahead test:** exactly as `YT1_SPEC.md`.

**Frame** (`tools/yt1/frame_t.py`, checked before this entry: it reproduces C19b's 815 in-sample trades to the cent):
5-minute MNQ bars, indicators on the continuous 24-hour series; signal bars closing 09:35 → 15:00; long only when
close > EMA200 and short only when close < EMA200 unless the entry says "no EMA filter"; entry at the signal bar's
close; **swing stop** = 1 tick beyond the lowest low (highest high) of the last 10 bars including the signal bar,
unless the entry names its own stop level, which is used (1 tick beyond it) when it is on the losing side of the
entry and replaced by the swing stop when it is not; target 1.5R; flat at the flat bar; one position at a time, any
number a day; a bar signalling both sides is no trade; roll days and the day after skipped. The article is long-only
on gold; shorts are the mirror *(R)*. **Neighbours:** the same rule on 3-minute and 15-minute bars.

**Criterion.** The usual criterion of YT1, with the p-value level counted over both batches:
**p < 0.05 / (53 + 29) = 0.00061.** Candidate = every criterion but that level, with p < 0.05. Fewer than 100 trades =
not enough data. With 29 rules, one or two reaching p < 0.05 is what chance gives.

"Crosses above x" = above x on this bar and at or below x on the previous bar. Long side is written; short mirrors.

| ID | Trigger (long) | Settings |
|---|---|---|
| T01 | RSI crosses above 50 | RSI(14) |
| T02 | Awesome Oscillator crosses above zero | AO = SMA5 − SMA34 of (high + low) / 2 |
| T03 | AO below zero and this is its third consecutive rising bar (the bar before the three was not rising) | as T02 |
| T04 | Chande Momentum Oscillator crosses above −50 | CMO(9) |
| T05 | CMO crosses above 0 | CMO(9) |
| T06 | Williams %R crosses above −80 | %R(14) |
| T07 | TRIX crosses above zero | TRIX(18) = 1-bar % change of a triple EMA(18) of log close |
| T08 | PPO crosses above zero | PPO = (EMA12 − EMA26) ÷ EMA26 |
| T09 | Fisher Transform crosses above its trigger (its own previous value) with both below zero | Fisher(9) on (high + low) / 2 |
| T10 | Relative Vigor Index crosses above its signal with both below zero | RVI(10), signal = its 4-bar symmetric weighted average (1, 2, 2, 1) |
| T11 | RVI crosses above its signal with both above zero | as T10 |
| T12 | Chaikin Money Flow crosses above zero | CMF(20) |
| T13 | Chaikin Oscillator crosses above zero | EMA3 − EMA10 of the accumulation / distribution line |
| T14 | Close above the high of the latest confirmed up fractal, on the first bar to do so | Williams fractal: a high above the two highs before and the two after; known two bars later *(R: "breaks above the fractal")* |
| T15 | Schaff Trend Cycle crosses above 25 (short: below 75) | STC(10, 23, 50): MACD(23, 50) → 10-bar stochastic → smoothed by 0.5 → 10-bar stochastic → smoothed by 0.5 |
| T16 | SMA50 crosses above SMA200 | |
| T17 | WMA50 crosses above WMA200. Own stop: the WMA200 value on the cross bar | |
| T18 | DEMA50 crosses above DEMA200 | DEMA = 2 × EMA − EMA of EMA |
| T19 | TEMA50 crosses above TEMA200 | TEMA = 3 × EMA − 3 × EMA(EMA) + EMA(EMA(EMA)) |
| T20 | Hull MA(100) crosses above SMA200 | |
| T21 | McGinley Dynamic(9) crosses above McGinley Dynamic(21) | MD = MD₋₁ + (close − MD₋₁) ÷ (n × (close ÷ MD₋₁)⁴), seeded with the first close |
| T22 | A bar that opens and closes above the SMA20 of highs, after one that did not (short: below the SMA20 of lows) | |
| T23 | RSI crosses above 70 with ADX ≥ 25. Own stop: EMA21 | RSI(14), ADX(14, 14) |
| T24 | Close crosses above the Bollinger middle band with RSI below 30 on at least one of the previous 10 bars *(R: "recently")* | BB(20, 2), RSI(14) |
| T25 | RSI crosses above 70 with a green cloud (span A above span B at this bar) | RSI(14); Ichimoku (9, 26, 52, 26), cloud as C19a |
| T26 | Know Sure Thing crosses above its signal with both below zero | KST: ROC 10 / 15 / 20 / 30 smoothed by SMA 10 / 10 / 10 / 15, weights 1 / 2 / 3 / 4, signal SMA9 |
| T27 | RSI crosses above 70 while Supertrend is up. **No EMA filter.** Own stop: the Supertrend line | RSI(14), Supertrend(10, 3) |
| T28 | MACD crosses above its signal while Supertrend is up | MACD(12, 26, 9), Supertrend(10, 3) |
| T29 | MACD crosses above its signal with Stochastic %K below 20 on at least one of the previous 10 bars and the bar's low above EMA200 | MACD(12, 26, 9), Stochastic(14, 3, 3) |

**Left out:** the zero-lag MACD trigger (no agreed definition of the indicator and none in the article), and the
"87 % win rate" MACD variants (multi-entry scaling with 0.25–0.5R targets, which the harness's one-position frame
does not express).
