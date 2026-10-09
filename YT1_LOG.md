# YT1 — results (run 2026-10-08 → 2026-10-09; rules pre-registered in `YT1_SPEC.md` before any code)

**Verdict: none of the 53 rules passes.** 47 fail, 1 has too few trades (B09, 58), and 5 are candidates by the
pre-registered definition (every criterion met except the Bonferroni level 0.00094, with p < 0.05): **E09, C19b,
E10a, C02, E12**. Eight rules reach p < 0.05 where chance alone gives two or three; seven are trend or breakout
rules and the eighth (E12) is long only. Three of the five candidates (E09, C19b, E10a) make their money on the days ORB v1.4 trades and on ORB's side.
Nothing is adopted.
A second batch, **YT2** (29 more single-indicator triggers, section at the end), was registered and run afterwards: all 29 fail.

Engine `tools/yt1/` (calibrated to `orb_engine` and `lit1`, see the spec). Order of work as registered: 53 modules
written and run by coders who had only bars to 2022-12-31 (`data/studies/yt1/YT1_step1_in_sample.md`, stamped in
`IS_STAMP.txt`), then the unchanged modules on every bar, once (`python3 tools/yt1/run.py <ID> --phase full`; the run
script checks the module hashes against the stamp first). 89,742 base trades in all.

## Step 2 — full span, 2019-06-03 → 2026-10-07
R is per trade after costs; p is the one-sided bootstrap; "Years +" counts calendar years with a positive net out of
those traded; "R nb1 / nb2" are the two neighbours fixed in the spec.

| ID | Rule | n | Net $ | R / trade | Win % | PF | Max DD $ | p | Years + | R 2019-22 / 2023-26 | R nb1 / nb2 | Verdict | Fails on |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| A01 | JadeCap Silver Bullet | 567 | -494 | +0.009 | 37.2 | 0.98 | -3,406 | 0.4293 | 4/8 | -0.018 / +0.037 | -0.019 / +0.021 | fails | years, r, halves, neighbours, p |
| A02 | Casper 5-minute candle + 1-minute FVG break | 1844 | -5,821 | -0.122 | 32.3 | 0.92 | -7,700 | 0.9999 | 3/8 | -0.144 / -0.101 | -0.135 / -0.130 | fails | years, r, halves, p |
| A03 | Casper 30-minute range, sweep and FVG back inside | 552 | +1,914 | -0.025 | 38.0 | 1.05 | -4,702 | 0.6780 | 3/8 | +0.050 / -0.093 | -0.009 / -0.027 | fails | years, r, halves, p |
| A05 | Candle Range Theory on the 05:00-09:00 candle | 1355 | -5,492 | -0.094 | 38.7 | 0.90 | -6,348 | 0.9964 | 2/8 | -0.069 / -0.117 | -0.078 / -0.109 | fails | years, r, halves, p |
| A09 | ICT Silver Bullet, first FVG with the midnight-open side rule | 1029 | -4,252 | -0.037 | 34.6 | 0.91 | -6,496 | 0.8052 | 3/8 | -0.024 / -0.051 | -0.059 / -0.035 | fails | years, r, halves, p |
| A10 | First presented FVG after 09:30 | 1850 | +8,848 | +0.059 | 23.5 | 1.07 | -6,116 | 0.1395 | 6/8 | +0.113 / +0.009 | +0.023 / +0.081 | fails | p |
| A14 | Candle Range Theory, hourly | 496 | +2,015 | -0.054 | 39.1 | 1.11 | -1,897 | 0.8735 | 3/8 | -0.194 / +0.073 | -0.046 / -0.060 | fails | years, r, halves, p |
| B01 | Quick Flip Scalper (15m box >= x ATR, reversal candle outside the box) | 310 | +132 | +0.006 | 18.7 | 1.01 | -2,730 | 0.4959 | 3/8 | -0.240 / +0.225 | -0.015 / +0.160 | fails | years, r, halves, neighbours, p |
| B03 | Casper 5-minute range, break and wick retest, midpoint stop | 776 | -5,680 | -0.078 | 33.2 | 0.88 | -5,911 | 0.9457 | 2/8 | -0.084 / -0.073 | -0.066 / -0.020 | fails | years, r, halves, p |
| B04 | Jooviers Gems London box (04:00-08:59), first 5m close outside from 09:30 | 998 | -12,066 | -0.058 | 34.0 | 0.81 | -13,460 | 0.9119 | 2/8 | -0.016 / -0.100 | -0.046 / -0.042 | fails | years, r, halves, p |
| B05 | Scarface first-candle break and retest | 1720 | -4,400 | -0.070 | 34.2 | 0.94 | -6,748 | 0.9819 | 2/8 | -0.111 / -0.032 | -0.081 / -0.071 | fails | years, r, halves, p |
| B06 | Pre-market high / low break and retest | 1533 | -14,711 | -0.152 | 32.0 | 0.78 | -15,336 | 1.0000 | 0/8 | -0.126 / -0.176 | -0.164 / -0.167 | fails | years, r, halves, p |
| B07 | DR / IDR 09:30-10:29, first 5m close beyond, stop the opposite DR extreme, flat bar | 1672 | +9,776 | +0.019 | 52.4 | 1.07 | -6,908 | 0.1580 | 5/8 | +0.019 / +0.019 | +0.029 / +0.015 | fails | years, r, p |
| B08 | edgeful IB retracement: limit 1/4 W back from the IB extreme, stop beyond the midpoint | 635 | -790 | +0.017 | 39.4 | 0.97 | -3,044 | 0.3680 | 4/8 | +0.020 / +0.015 | -0.021 / +0.084 | fails | years, r, neighbours, p |
| B09 | IB75 (Dan Cooke): limit 1/4 W from the first-set IB extreme, target that extreme, VWAP filter | 58 | -678 | -0.175 | 44.8 | 0.67 | -1,134 | 0.9224 | 3/8 | +0.113 / -0.484 | -0.288 / -0.135 | not enough data |  |
| B14 | IB breakout (samjNQ): 5m close beyond the IB on the VWAP side, stop the other IB level, target k x W | 1793 | +11,296 | +0.029 | 53.5 | 1.08 | -6,074 | 0.0450 | 5/8 | +0.036 / +0.022 | +0.019 / +0.027 | fails | years, r, p |
| C01 | MACD + 200 EMA | 1257 | +10,188 | +0.051 | 46.4 | 1.13 | -5,496 | 0.0483 | 6/8 | +0.129 / -0.023 | +0.019 / +0.025 | fails | halves, p |
| C02 | 8-55 EMA pullback, long only, 0.75 % trailing stop | 1179 | +8,996 | +0.158 | 47.8 | 1.12 | -3,886 | 0.0248 | 6/8 | +0.205 / +0.111 | +0.162 / +0.184 | candidate | p |
| C03 | Triple Supertrend + Stochastic RSI + 200 EMA | 2021 | -2,692 | -0.020 | 43.7 | 0.98 | -5,798 | 0.7854 | 3/8 | +0.009 / -0.048 | -0.018 / +0.055 | fails | years, r, halves, neighbours, p |
| C04 | Donchian(20) + 200 EMA | 1880 | -21,483 | -0.042 | 44.6 | 0.86 | -24,106 | 0.9668 | 1/8 | -0.007 / -0.075 | +0.006 / +0.014 | fails | years, r, halves, neighbours, p |
| C05 | Supertrend(10, 3) flip + 200 EMA | 1555 | -2,749 | +0.027 | 48.3 | 0.98 | -8,265 | 0.1404 | 4/8 | +0.059 / -0.002 | -0.007 / +0.054 | fails | years, r, halves, neighbours, p |
| C06 | EMA 8 / 14 / 50 + Stochastic RSI + ATR bracket | 5002 | -4,236 | -0.005 | 58.8 | 0.98 | -8,408 | 0.6967 | 2/8 | -0.009 / -0.002 | -0.016 / +0.000 | fails | years, r, halves, neighbours, p |
| C07 | MACD + Parabolic SAR + 200 EMA | 2618 | +4,158 | +0.013 | 43.9 | 1.02 | -10,917 | 0.2769 | 4/8 | +0.069 / -0.039 | -0.014 / +0.005 | fails | years, r, halves, neighbours, p |
| C08 | Bollinger upper-band breakout + 200 SMA + daily 9 EMA (long only) | 1015 | +3,514 | +0.029 | 48.7 | 1.06 | -3,304 | 0.1787 | 5/8 | +0.020 / +0.037 | +0.006 / +0.071 | fails | years, r, p |
| C09 | Stochastic (14,3,3) arm + RSI(14) > 50 + MACD > signal | 2478 | +10,163 | -0.000 | 44.3 | 1.06 | -9,828 | 0.5055 | 5/8 | -0.005 / +0.004 | -0.025 / +0.009 | fails | years, r, halves, neighbours, p |
| C10 | 9 / 20 EMA "Bone Zone" first pullback | 960 | -3,651 | -0.095 | 27.1 | 0.91 | -7,776 | 0.9613 | 3/8 | -0.056 / -0.131 | -0.103 / -0.026 | fails | years, r, halves, p |
| C12 | TTM Squeeze fire (BB 20/2 inside KC 20/1.5xATR20, >= 6 on bars) | 325 | +4,466 | +0.002 | 41.2 | 1.27 | -1,481 | 0.4739 | 4/8 | -0.018 / +0.023 | +0.032 / +0.060 | fails | years, r, halves, p |
| C13 | Connors RSI (3, 2, 100) out of the extreme + 200 SMA | 1679 | -8,948 | -0.183 | 37.7 | 0.84 | -9,070 | 1.0000 | 1/8 | -0.264 / -0.117 | -0.242 / -0.183 | fails | years, r, halves, p |
| C15 | VWAP (09:30 anchor) trend-day first pullback | 823 | -4,744 | -0.141 | 33.0 | 0.84 | -4,977 | 0.9999 | 1/8 | -0.103 / -0.176 | -0.111 / -0.141 | fails | years, r, halves, p |
| C17 | NQ 1-minute 9/20/50 EMA pullback | 16895 | -46,466 | -0.182 | 33.8 | 0.86 | -46,814 | 1.0000 | 0/8 | -0.204 / -0.162 | -0.187 / -0.188 | fails | years, r, halves, p |
| C19a | TRADING RUSH Ichimoku cross above the cloud + EMA200 | 1749 | -5,152 | -0.008 | 46.5 | 0.96 | -13,546 | 0.6274 | 3/8 | +0.036 / -0.050 | +0.008 / +0.051 | fails | years, r, halves, neighbours, p |
| C19b | TRADING RUSH Keltner (20, 2 x ATR10) open-and-close outside + EMA200 | 1632 | +18,001 | +0.066 | 50.8 | 1.13 | -5,490 | 0.0018 | 8/8 | +0.091 / +0.040 | +0.059 / +0.069 | candidate | p |
| C19c | TRADING RUSH DMI(14) +DI / -DI cross + EMA200 | 2856 | -13,981 | -0.039 | 43.3 | 0.92 | -15,478 | 0.9721 | 2/8 | -0.015 / -0.061 | -0.055 / +0.028 | fails | years, r, halves, neighbours, p |
| C19d | TRADING RUSH Stochastic(14,3,3) cross under 20 / over 80 + EMA200 | 1532 | -1,732 | -0.082 | 41.7 | 0.96 | -4,754 | 0.9956 | 3/8 | -0.122 / -0.043 | -0.110 / -0.054 | fails | years, r, halves, p |
| C19e | TRADING RUSH RSI(14) back above 30 / below 70 + EMA200 | 192 | -2,952 | -0.141 | 38.5 | 0.72 | -4,456 | 0.9517 | 1/8 | -0.142 / -0.139 | -0.116 / -0.020 | fails | years, r, halves, p |
| D03 | Stacked-imbalance pullback (ATAS) | 1782 | -7,556 | -1.351 | 17.1 | 0.10 | -7,556 | 1.0000 | 0/8 | -1.272 / -1.413 | -1.316 / -1.375 | fails | years, r, halves, p |
| D05 | Absorption candle, POC in the wick, delta flip, at a level (Thraxx) | 786 | -2,361 | -0.184 | 33.6 | 0.81 | -2,532 | 0.9998 | 1/8 | -0.190 / -0.179 | -0.184 / -0.188 | fails | years, r, halves, p |
| D06 | Trapped traders (Trader Dale) | 2468 | +11,988 | -0.024 | 36.5 | 1.11 | -3,818 | 0.8111 | 6/8 | -0.046 / -0.004 | -0.048 / -0.011 | fails | r, halves, p |
| E01 | NQ Stats Hour Stats: fade the first breach of the previous hour's high / low to the hour's open | 2779 | -19,378 | -0.119 | 62.8 | 0.82 | -20,586 | 1.0000 | 0/8 | -0.120 / -0.117 | -0.118 / -0.113 | fails | years, r, halves, p |
| E02 | NQ Stats IB breaks: at the IB close, with the midpoint / first-extreme bias, target the IB extreme | 1517 | -7,346 | -0.025 | 75.0 | 0.88 | -7,510 | 0.9681 | 1/8 | -0.028 / -0.022 | -0.028 / -0.032 | fails | years, r, halves, p |
| E04 | NQ Stats Noon Curve: at the noon close, with Q2's one-sided break of Q1, stop beyond Q2's other extreme | 1460 | +5,304 | -0.010 | 42.2 | 1.06 | -5,394 | 0.6061 | 6/8 | -0.025 / +0.004 | -0.014 / +0.086 | fails | r, halves, neighbours, p |
| E05 | NQ Stats ALN sessions: partial engulf of Asia by London, trade to the London extreme it points to | 1319 | -4,124 | -0.089 | 57.0 | 0.92 | -7,202 | 0.9635 | 3/8 | -0.118 / -0.061 | -0.095 / -0.085 | fails | years, r, halves, p |
| E06 | AM TBR: after the first touch of the 08:00 open +/- 0.25 SD, limit at k SD, target the 08:00 open | 1260 | -7,296 | -0.044 | 54.0 | 0.91 | -8,121 | 0.9669 | 2/8 | -0.053 / -0.036 | -0.034 / -0.033 | fails | years, r, halves, p |
| E08 | Outside-open reversal: 09:30 open beyond the previous RTH range by >= 0.05 ATR, fade to that level | 643 | +2,436 | -0.038 | 35.3 | 1.06 | -3,187 | 0.7566 | 3/8 | +0.012 / -0.088 | -0.053 / +0.011 | fails | years, r, halves, neighbours, p |
| E09 | Noise-area intraday momentum: half-hourly closes beyond open/prior-close x (1 +/- sigma), VWAP trailing exit | 1627 | +21,238 | +0.204 | 40.7 | 1.25 | -3,998 | 0.0015 | 7/8 | +0.173 / +0.235 | +0.201 / +0.189 | candidate | p |
| E10a | First hour continuation: at the 10:29 close, with the side of the 09:30 open, no stop, flat bar | 1852 | +22,968 | +0.208 | 54.5 | 1.13 | -7,610 | 0.0193 | 6/8 | +0.117 / +0.293 | +0.059 / +0.044 | candidate | p |
| E10b | 15:00 continuation: at the 14:59 close, with the side of the 09:30 open and of the range middle, stop beyond the open | 1558 | +5,489 | -0.005 | 48.1 | 1.09 | -6,208 | 0.5973 | 4/8 | +0.041 / -0.050 | +0.098 / -0.033 | fails | years, r, halves, neighbours, p |
| E11 | Larry Williams open +/- 0.25 x previous RTH range, stop orders to 15:00, first to fill, bracket 0.5 W | 1769 | +14,790 | +0.043 | 53.5 | 1.09 | -6,597 | 0.0180 | 5/8 | +0.033 / +0.052 | +0.061 / +0.040 | fails | years, r, p |
| E12 | Larry Williams Oops: open below the previous RTH low, buy stop at that low to 15:00, no stop, flat bar | 175 | +5,224 | +0.547 | 56.6 | 1.33 | -3,342 | 0.0430 | 6/8 | +0.553 / +0.542 | +0.468 / +0.622 | candidate | p |
| E13 | Crabel stretch after a 2-day narrow range: stop orders at the open +/- stretch, other level is the stop, BE after 60 min | 128 | +394 | +0.066 | 25.0 | 1.06 | -1,680 | 0.2197 | 5/8 | +0.107 / +0.029 | +0.097 / +0.033 | fails | years, p |
| E15 | Camarilla pivots: S3 / R3 rejection and R4 / S4 breakout, four set-ups pooled | 3025 | +6,998 | +0.023 | 47.8 | 1.03 | -11,228 | 0.0985 | 3/8 | +0.051 / -0.002 | +0.028 / +0.001 | fails | years, r, halves, p |
| E19 | Turnaround Tuesday, cash session: down Monday -> long Tuesday 09:30 open to the flat bar | 142 | +2,528 | +0.173 | 50.7 | 1.15 | -3,436 | 0.3373 | 7/8 | -0.103 / +0.510 | +0.881 / +0.261 | fails | halves, p |
| E20 | Turn of the month, cash sessions: long 09:30 open to the flat bar on the last N and first M trading days | 616 | +9,602 | +0.112 | 55.0 | 1.12 | -5,751 | 0.3158 | 5/8 | -0.165 / +0.370 | +0.082 / +0.102 | fails | years, halves, p |

## The five candidates
Second coder = the rule written again from the spec text by a coder who had not seen the first module, compared on
entry time and side. Drift = each trade's points against the average move of the same clock window, same side, on
every cash day of that calendar year. ORB = `orb_engine.run` from 2019-06-01 (879 trades, +20,900, return-to-drawdown
5.38 in dollars). "ORB + rule" = one contract of each, return-to-drawdown in dollars.

| ID | Rule | n | Net $ | R | p | Max DD $ | 2023–26 only: n · R · p · years + | Second coder: same entries · net · p | Excess over drift | Daily corr. with ORB | On ORB days | Off ORB days | ORB + rule ret / DD |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| E09 | Noise-area intraday momentum (Zarattini, Aziz, Barbon) | 1,627 | +21,238 | +0.204 | 0.0015 | -3,998 | 810 · +0.235 · p 0.013 · 4/4 | 1,597 of 1,627 · +21,224 · p 0.0026 | +7.4 of +7.5 pts · p 0.001 | +0.46 | +20,104 (+0.34 R) | +1,134 (+0.05 R, p 0.331) | 7.54 |
| C19b | Keltner channel breakout + 200 EMA (TRADING RUSH) | 1,632 | +18,001 | +0.066 | 0.0018 | -5,490 | 817 · +0.040 · p 0.101 · 4/4 | 1,632 of 1,632 · +18,001 · p 0.0018 | +6.3 of +6.5 pts · p 0.015 | +0.42 | +21,442 (+0.12 R) | -3,440 (+0.01 R, p 0.387) | 5.33 |
| E10a | First-hour continuation (edgeful) | 1,852 | +22,968 | +0.208 | 0.0193 | -7,610 | 955 · +0.294 · p 0.022 · 4/4 | 1,852 of 1,852 · +22,968 · p 0.0193 | +7.0 of +7.2 pts · p 0.019 | +0.40 | +17,820 (+0.36 R) | +5,148 (+0.07 R, p 0.292) | 5.04 |
| C02 | 8-55 EMA pullback, long only (TradersPost) | 1,179 | +8,996 | +0.158 | 0.0248 | -3,886 | 591 · +0.111 · p 0.178 · 3/4 | 1,178 of 1,179 · +8,942 · p 0.0256 | +3.4 of +4.8 pts · p 0.096 | +0.09 | +2,574 (+0.09 R) | +6,422 (+0.21 R, p 0.024) | 7.25 |
| E12 | Larry Williams Oops, long only (StatOasis) | 175 | +5,224 | +0.547 | 0.0430 | -3,342 | 97 · +0.542 · p 0.073 · 4/4 | 175 of 175 · +5,224 · p 0.0430 | +12.7 of +15.9 pts · p 0.123 | +0.10 | -194 (-0.13 R) | +5,418 (+1.00 R, p 0.002) | 7.35 |

Reading:
- **E09** is the strongest result of the run: p 0.0015 (second coder 0.0026) against the 0.00094 level, 7 of 8 years,
  both halves and both neighbours positive at the same size, 2023–2026 alone +0.235 R (p 0.013, 4 of 4 years), and the
  result is not market drift (p 0.001). It is also the rule nearest to ORB: 89 % same side on shared days, +20,104 of
  its +21,238 on ORB's trade days, +0.047 R (p 0.33) on the others. Unlike VP2y in COMBO1, adding it does not lower
  return-to-drawdown (7.54 against 5.38 for ORB alone), because it enters later and exits on its own signal. It has no
  price stop: its exits are checked on the half hour, the worst trade is −650 $ and the worst day −689 $ per MNQ.
- **C19b** has 8 of 8 positive years but earns nothing off ORB's days (−3,440 $, +0.01 R) and leaves return-to-drawdown
  where ORB alone has it (5.33). It is ORB's trend-day effect entered a different way.
- **E10a** likewise (+0.07 R off ORB's days, p 0.29; combined 5.04, below ORB alone), and its neighbours at 09:59 and
  10:59 are a quarter of its size.
- **C02** and **E12** are long only. Neither is distinguishable from the index's own drift over the same clock windows
  (p 0.096 and 0.123). C02's 2023–2026 half is +0.11 R (p 0.18) with 2026 negative; E12 has 175 trades and 2,986 $ of
  its 5,224 $ in 2026. E12's profit is on the days ORB does not trade (+1.00 R on 105 trades), which is the one thing
  here worth a note for the balance-day question, on too few trades to act on.
- The two smallest p-values (E09, C19b) would survive a 10 % false-discovery cut across the 53. That cut was not
  registered, so it is information, not a verdict.

## Claim checks
The published session statistics reproduce almost to the decimal. The rules built on them lose all the same, because
a hit rate says nothing about the size of the misses: Hour Stats reverts 63.9 % of the time and E01 loses 0.12 R per
trade; the IB high is reached 84.5 % of the time and E02 loses 0.02 R with a 75 % win rate.

| Claim | Published | Measured 2019-06 → 2026-10 | n |
|---|---|---|---|
| K-A12 ICT opening-range gap, 20–75 points: midpoint trades 09:30–10:00 | about 70 % | 68.5 % (by 16:00: 83.7 %) | 691 |
| K-A12 same, 75–120 points / over 120 points | "either direction" / "keeps going" | 44.7 % / 24.5 % | 302 / 473 |
| K-B07 DR rule: opposite extreme holds after a 5-minute close outside the 09:30–10:29 range | 80 % | 82.0 % (body range: 73.5 %) | 1760 |
| K-E01 Hour Stats: hour's open trades after the first breach of the previous hour | 61.5 % | 63.9 % | 13,123 |
| K-E01 13:00 hour, first 20 minutes / 09:00 hour, first 20 minutes | 71 % / 87.4 % | 72.3 % / 88.1 % | 1,157 / 1,006 |
| K-E02 IB closes above its midpoint and the low came first: high broken by noon / by close | 74.0 % / 84.0 % | 74.6 % / 84.5 % | 823 |
| K-E02 either IB side broken by the close | 96.1 % | 96.2 % | 1897 |
| K-E04 Noon Curve: 08:00–16:00 high and low on opposite sides of noon | 72.81 % | 72.3 % | 1833 |
| K-E04 afternoon makes the high after Q2 broke Q1's high only, as a trader sees it at noon | 82.12 % (published only for days that end as opposite-side days) | 67.7 % | 762 |
| K-E04 afternoon makes the low after Q2 broke Q1's low only, at noon | 72.42 % (same conditioning) | 55.1 % | 689 |
| K-E05 ALN pattern P3: New York breaks London's high / low | 80.8 % / 65.5 % | 79.8 % / 66.1 % | 785 |
| K-E05 pattern P4: New York breaks London's high / low | 68.6 % / 75.0 % | 68.2 % / 73.9 % | 567 |
| K-E06 AM TBR: sessions touching the 08:00 open ± 0.25 SD by noon (SD of 08:00 → 12:00 change) | 98.9 % | 99.0 % (close-to-close SD: 95.7 %) | 1872 |
| K-E06 those that return to the 08:00 open by noon / first touch in the 08:00 hour | 74 % / 79 % | 75.5 % / 80.6 % | 1186 in the 08:00 hour |
| K-E07 open above the previous RTH high: closes above it / previous low not traded | 69.9 % / 88.1 % | 70.3 % / 88.2 % | 475 |
| K-E07 open inside the previous range: neither / one / both sides broken | 17.7 / 74.0 / 8.3 % | 18.1 / 73.3 / 8.6 % | 1099 |
| K-E10 green first hour: the day closes above its open | 76–79 % | 75.8 % | 985 |
| K-E10 green first hour: the day closes above the 10:30 price (what a trade can take) | not published | 60.2 % (red first hour, closes below: 49.7 %) | 985 / 910 |
| K-E10 above the open at 15:00: closes above the open | about 90 % | 89.6 % | 1002 |
| K-E10 above the open at 15:00: closes above the 15:00 price | not published | 52.3 % | 1002 |
| K-E16 news candle: after one side of the 08:30 bar is taken, the other is taken the same day | about 85 % | 67.4 % | 439 |
| K-D07 unfinished auction at a new session extreme is traded through by 11:35 (against finished) | direction only | 84.5 % against 84.4 % | 938 / 6463 |
| K-D15 exhaustion print (≤ 9 contracts at the extreme) holds six bars (against the rest) | direction only | 20.7 % against 20.1 % | 5,315 / 2,096 |
| K-D08 delta divergence at a new session high: move over the next six bars (against other new-high up bars) | lower | +0.22 against +0.10 bar-ranges: higher, not lower | 434 / 2,608 |

## Corrections and readings logged during the run
- **Harness, before the in-sample table was fixed:** clock times on the two daylight-saving Sundays a year were an
  hour off (no trade count changed); the Parabolic SAR put its dot inside the bar on turn bars (C07 in-sample: 1,253
  trades, +0.061 R before; 1,251, +0.069 R after). Both were reported by coders with evidence, neither from a result.
- **No trade-rule module was changed after its first run**, by any coder. Each coder's added readings are in
  `data/studies/yt1/notes/<ID>.md`. The ones that move a number: B06 falls back to the breakout bar when there is no
  zone bar (228 of 740 in-sample trades; without them −0.094 R on 512); E01's limits rest from HH:01 because the hour's
  open is not known at HH:00; family D takes resting limits in fill order and any number a day; E20 uses a fixed
  holiday list, so holiday half-sessions are not turn-of-month days; E08 reads the 09:30 open it trades at, so it
  fails the strict look-ahead test and passes when only that print is exempt.
- **Family D** runs on the footprint sample only (the ORB trade days, 09:30–11:35), with prices from NQ applied to MNQ
  (within 2 ticks on 93 % of bars); on six days around three rolls the two are different contract months (8 base
  trades). D03's −1.35 R is cost: its stop averages six ticks and a round trip costs six (two of slippage, four of commission).
- **Second coders:** C19b, E10a and E12 identical trade for trade; C02 1,178 of 1,179 entries (the trailing stop's
  tick rounding differs); E09 1,597 of 1,627 (which days count toward the 14-day average on short sessions).

## Where this leaves things
- ORB v1.4 stays the one traded rule. Nothing from YT1 is adopted.
- **E09 is logged as a candidate for a shadow flag** in the weekly check, on the same terms as ORB-add: tracked, not
  traded, and judged on live occurrences. Whether to add it is the user's decision; no Pine has been written.
- The trend / breakout rules are where the p < 0.05 results sit (E09, C19b, E11, E10a, C02, B14, C01, plus the
  long-only E12); every reversal, retest, fair-value-gap, order-flow and session-statistic rule tested here fails, as
  the earlier families did.

---
# YT2 — the remaining TRADING RUSH single triggers (rules in `YT2_SPEC.md`, registered 2026-10-09 after YT1's results were known)

**Verdict: all 29 fail; there is no candidate.** Level 0.05 / (53 + 29) = 0.00061. Four reach p < 0.05 (T27 0.014,
T29 0.025, T08 0.032, T07 0.040) where chance gives one or two, and none of the four meets the other criteria: T08 and
T27 are under +0.05 R, T07 has five positive years and is under +0.05 R, T29 is negative in 2023–2026.
65,318 base trades. Frame `tools/yt1/frame_t.py` (reproduces C19b to the cent); order of work as YT1
(`data/studies/yt1/YT2_step1_in_sample.md` logged first, module hashes in `YT2_IS_STAMP.txt`); every module passes the
look-ahead test; the one change after a first run was a floating-point fix in T02, T03 and T10–T12 (an indicator value
of exactly zero was coming out as ±1e-14); every trade list is identical before and after.

The two triggers that led in-sample did not carry: **T29** (MACD cross after Stochastic under 20) was +0.134 R, p 0.0009
on 2019–2022 and −0.015 R on 2023–2026; **T26** (Know Sure Thing) was +0.105 R, p 0.0068 and then −0.015 R. C01 in
YT1 did the same (+0.129 R, p 0.0016, then −0.023 R). A MACD cross with the 200 EMA is not an edge on MNQ at 5 minutes.

| ID | Rule | n | Net $ | R / trade | Win % | PF | Max DD $ | p | Years + | R 2019-22 / 2023-26 | R nb1 / nb2 | Verdict | Fails on |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| T01 | TRADING RUSH RSI(14) crosses 50 + EMA200 | 3645 | -13,474 | -0.041 | 42.2 | 0.94 | -17,760 | 0.9850 | 1/8 | -0.018 / -0.063 | -0.056 / +0.016 | fails | years, r, halves, neighbours, p |
| T02 | TRADING RUSH Awesome Oscillator (5, 34) zero cross + EMA200 | 1936 | +6,072 | +0.016 | 47.3 | 1.04 | -7,018 | 0.2464 | 5/8 | +0.060 / -0.025 | -0.014 / +0.041 | fails | years, r, halves, neighbours, p |
| T03 | TRADING RUSH Awesome Oscillator third rising bar below zero + EMA200 | 1637 | +4,091 | -0.004 | 45.6 | 1.04 | -4,870 | 0.5522 | 5/8 | +0.051 / -0.054 | -0.031 / +0.032 | fails | years, r, halves, neighbours, p |
| T04 | TRADING RUSH CMO(9) crosses -50 / +50 + EMA200 | 2352 | -7,000 | -0.088 | 40.7 | 0.92 | -12,898 | 0.9997 | 1/8 | -0.133 / -0.043 | -0.134 / -0.022 | fails | years, r, halves, p |
| T05 | TRADING RUSH CMO(9) zero cross + EMA200 | 4307 | -9,900 | -0.019 | 43.1 | 0.96 | -15,642 | 0.8716 | 4/8 | +0.004 / -0.040 | -0.029 / +0.024 | fails | years, r, halves, neighbours, p |
| T06 | TRADING RUSH Williams %R(14) crosses -80 / -20 + EMA200 | 4290 | -3,584 | -0.062 | 41.0 | 0.98 | -8,332 | 0.9998 | 3/8 | -0.071 / -0.053 | -0.080 / -0.002 | fails | years, r, halves, p |
| T07 | TRADING RUSH TRIX(18) zero cross + EMA200 | 1421 | +3,224 | +0.045 | 48.2 | 1.03 | -6,432 | 0.0400 | 5/8 | +0.070 / +0.021 | +0.026 / +0.012 | fails | years, r, p |
| T08 | TRADING RUSH PPO(12, 26) zero cross + EMA200 | 1690 | +7,784 | +0.047 | 48.7 | 1.06 | -5,882 | 0.0319 | 6/8 | +0.077 / +0.019 | +0.022 / +0.028 | fails | r, p |
| T09 | TRADING RUSH Fisher Transform(9) crosses its trigger below zero + EMA200 | 4158 | -10,782 | -0.046 | 41.9 | 0.95 | -13,999 | 0.9952 | 2/8 | -0.025 / -0.067 | -0.062 / +0.021 | fails | years, r, halves, neighbours, p |
| T10 | TRADING RUSH RVI(10) crosses its signal below zero + EMA200 | 3615 | -5,972 | -0.066 | 42.2 | 0.96 | -10,398 | 0.9995 | 3/8 | -0.045 / -0.085 | -0.085 / +0.023 | fails | years, r, halves, neighbours, p |
| T11 | TRADING RUSH RVI(10) crosses its signal above zero + EMA200 | 2619 | +10,612 | +0.023 | 46.7 | 1.06 | -3,875 | 0.1263 | 5/8 | +0.044 / +0.003 | -0.013 / +0.003 | fails | years, r, neighbours, p |
| T12 | TRADING RUSH Chaikin Money Flow(20) zero cross + EMA200 | 3285 | -5,244 | -0.030 | 43.9 | 0.97 | -9,982 | 0.9374 | 5/8 | -0.009 / -0.051 | -0.045 / +0.019 | fails | years, r, halves, neighbours, p |
| T13 | TRADING RUSH Chaikin Oscillator (3, 10) zero cross + EMA200 | 3695 | -8,270 | -0.008 | 43.5 | 0.96 | -10,396 | 0.6702 | 3/8 | +0.020 / -0.035 | -0.044 / +0.005 | fails | years, r, halves, neighbours, p |
| T14 | TRADING RUSH Williams fractal breakout (close beyond the latest confirmed fractal) + EMA200 | 3444 | -7,106 | -0.007 | 45.5 | 0.97 | -16,552 | 0.6490 | 4/8 | +0.017 / -0.028 | -0.006 / +0.034 | fails | years, r, halves, neighbours, p |
| T15 | TRADING RUSH Schaff Trend Cycle (10, 23, 50) crosses 25 / 75 + EMA200 | 2749 | -6,138 | -0.001 | 44.8 | 0.97 | -9,447 | 0.5186 | 3/8 | +0.039 / -0.038 | +0.000 / +0.019 | fails | years, r, halves, neighbours, p |
| T16 | TRADING RUSH SMA50 crosses SMA200 + EMA200 | 896 | -5,894 | -0.051 | 42.7 | 0.90 | -6,580 | 0.9258 | 2/8 | -0.060 / -0.042 | -0.063 / +0.093 | fails | years, r, halves, neighbours, p |
| T17 | TRADING RUSH WMA50 crosses WMA200, stop at WMA200 + EMA200 | 1162 | -68 | -0.023 | 44.2 | 1.00 | -4,885 | 0.7747 | 3/8 | +0.015 / -0.061 | -0.006 / +0.062 | fails | years, r, halves, neighbours, p |
| T18 | TRADING RUSH DEMA50 crosses DEMA200 + EMA200 | 1139 | -2,487 | -0.016 | 46.1 | 0.97 | -6,252 | 0.7143 | 5/8 | +0.003 / -0.034 | -0.013 / +0.079 | fails | years, r, halves, neighbours, p |
| T19 | TRADING RUSH TEMA50 crosses TEMA200 + EMA200 | 1230 | -651 | +0.010 | 48.6 | 0.99 | -9,229 | 0.3668 | 4/8 | +0.040 / -0.019 | +0.049 / +0.096 | fails | years, r, halves, p |
| T20 | TRADING RUSH Hull MA(100) crosses SMA200 + EMA200 | 1050 | +1,290 | -0.039 | 44.2 | 1.02 | -5,166 | 0.8804 | 5/8 | -0.027 / -0.050 | -0.016 / +0.039 | fails | years, r, halves, neighbours, p |
| T21 | TRADING RUSH McGinley Dynamic(9) crosses McGinley Dynamic(21) + EMA200 | 1457 | +4,750 | +0.033 | 47.6 | 1.04 | -6,332 | 0.1035 | 6/8 | +0.058 / +0.009 | +0.030 / +0.038 | fails | r, p |
| T22 | TRADING RUSH open-and-close outside the SMA20 high / low channel + EMA200 | 3263 | -14,466 | -0.015 | 44.5 | 0.94 | -17,680 | 0.7925 | 2/8 | -0.005 / -0.026 | -0.013 / +0.016 | fails | years, r, halves, neighbours, p |
| T23 | TRADING RUSH RSI crosses 70 / 30 with ADX >= 25, stop at EMA21 + EMA200 | 1725 | +4,680 | +0.039 | 45.7 | 1.04 | -3,979 | 0.0774 | 5/8 | +0.025 / +0.053 | +0.021 / +0.045 | fails | years, r, p |
| T24 | TRADING RUSH close crosses the Bollinger middle after RSI < 30 / > 70 + EMA200 | 355 | +4,646 | +0.084 | 49.0 | 1.17 | -2,206 | 0.0655 | 6/8 | +0.089 / +0.079 | -0.001 / +0.002 | fails | neighbours, p |
| T25 | TRADING RUSH RSI crosses 70 / 30 with a green / red Ichimoku cloud + EMA200 | 1298 | +46 | +0.020 | 48.5 | 1.00 | -6,467 | 0.2226 | 5/8 | +0.018 / +0.022 | +0.033 / +0.050 | fails | years, r, p |
| T26 | TRADING RUSH Know Sure Thing crosses its signal on the far side of zero + EMA200 | 1320 | +6,510 | +0.042 | 47.5 | 1.07 | -6,354 | 0.0688 | 6/8 | +0.105 / -0.015 | +0.008 / +0.059 | fails | r, halves, p |
| T27 | TRADING RUSH RSI crosses 70 / 30 with Supertrend, stop at the Supertrend line (no EMA200) | 2216 | +3,298 | +0.048 | 48.3 | 1.02 | -6,611 | 0.0136 | 6/8 | +0.063 / +0.034 | +0.043 / +0.070 | fails | r, p |
| T28 | TRADING RUSH MACD crosses its signal with Supertrend + EMA200 | 2098 | -686 | -0.007 | 44.4 | 0.99 | -6,935 | 0.6250 | 4/8 | -0.000 / -0.013 | -0.008 / +0.058 | fails | years, r, halves, neighbours, p |
| T29 | TRADING RUSH MACD crosses its signal after Stochastic < 20 / > 80, bar clear of EMA200 | 1266 | +13,272 | +0.058 | 47.2 | 1.17 | -5,879 | 0.0252 | 6/8 | +0.134 / -0.015 | +0.018 / +0.000 | fails | halves, p |

Settings are TradingView's built-in defaults where the article gives none; each coder's formula and how it was checked
are in `data/studies/yt1/notes/YT2_T01-T15.md` and `YT2_T16-T29.md`. Readings that matter: T14's fractal is strict on
both sides (TradingView's built-in also accepts equal highs to the left, about 4 % more fractals); T15 is the standard
Schaff recursion (TradingView has no built-in); the article is long-only on gold and shorts here are the mirror.

**Not sourced in this run** (the web-search allowance ran out; titles and links are in
`data/studies/yt1/research/B_session_range.md`, "Not written up", and `C_indicators.md`, "Leads"): previous-day
high / low break and retest, the "8AM model", first one-minute-candle rules, other Asian-range and London-open
breakouts, three 15-minute ORB videos, Trader Kane's Lab Model, Daxton Trades' 1-trade-a-day setup, Heikin-Ashi and
"AI-built" strategy videos.

---
# YT3 — NQSimon's standard-deviation method, one mechanical reading (rules in `YT3_SPEC.md`, registered 2026-10-09)

**Verdict: N01 fails.** 425 trades, −2,763 $, **−0.317 R per trade**, win 7.3 %, PF 0.69, 2 of 8 positive years,
p 0.97; 2019–2022 −0.316 R, 2023–2026 −0.318 R; neighbours (stop 7.5 / 15 points) −0.372 / −0.233 R. Level
0.05 / 83. Exits: 394 stops, 18 targets, 13 flat-bar. The average winner is +203 $ (about 10 R) and the average loser
−23 $, so the rule needs about 11 % winners to break even and gets 7 %.
Reported: `scaled` (stop 0.04 % of price) −0.291 R; `bias` (his one stated bias example) 100 trades, −0.127 R, p 0.65.
In-sample first (167 trades, −0.316 R), look-ahead test passed, module not changed after its first run
(`data/studies/yt1/notes/N01.md`).

**What this does and does not show.** The rule tested is: Asia range 20:00–23:59 as the leg; the first side taken
after midnight sets the direction; limit orders at 2 and 4 range-widths beyond that side, 09:30–11:29; 10-point stop;
target the far side of the Asia range. The 10-point stop, the −2 / −4 zones, the New York morning and the session
target are his. The leg, the tool's anchoring, the clock times and the entry price are readings, because his three
videos do not define them and disagree on the entry (`data/studies/yt1/research/F_nqsim0n.md`). He also requires a
daily bias, a daily fair-value gap at the zone and a lower-timeframe block to enter on, all chosen by eye. So this
closes the mechanical reading, not his discretionary trading. The way to test his version is the agreement audit used
for IFVG-1m: cut 10 charts at the 09:30 decision, have the user mark the leg and the zone he would use, and see whether
the code picks the same ones before any further run.

**TTrades.** Tested in YT4, below.

---
# YT4 — TTrades (@TTrades_edu): candle claims and seven mechanical readings of his models (rules in `YT4_SPEC.md`, registered 2026-10-09)

**Verdict: all seven rules fail (G1–G7), none is a candidate.** Level 0.05 / 90. Two of his candle statistics are
real and held in 2023–2026 (A and G below); neither turns into a trade here, for the reason under "Why".
In-sample first (stamp `YT4_IS_STAMP.txt`), full span run once, every module passed the look-ahead test and none was
changed after its first run. Notes per rule in `data/studies/yt1/notes/G1.md … G7.md`, `K-G.md`.

## Rules, full span 2019-06 → 2026-10 (house fills)

| ID | Rule | Trades | Net $ | R / trade | Win % | PF | Max DD $ | p | + years | R 2019–22 | R 2023–26 | Neighbours R | Verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| G1 | Daily bias alone: 09:30 open → flat bar, no stop (R = 0.1 ATR) | 1,498 | −15,274 | −0.247 | 49.1 | 0.92 | −27,192 | 0.96 | 2 / 8 | −0.438 | −0.060 | −0.390 / −0.007 | fails |
| G2 | Candle 4 continuation: daily candle 3 closure, EQ held, morning 3m CISD | 242 | −2,562 | −0.168 | 31.8 | 0.70 | −3,180 | 0.97 | 1 / 8 | −0.210 | −0.119 | −0.059 / −0.158 | fails |
| G3 | EQ continuation day: hourly closes respect EQ, morning 5m CISD above EQ | 662 | −2,952 | −0.097 | 34.0 | 0.89 | −5,040 | 0.96 | 2 / 8 | −0.247 | +0.056 | −0.122 / −0.094 | fails |
| G4 | Fractal Model day trade: hourly closure inside candle 1, second 5m CISD | 791 | −3,408 | −0.143 | 32.7 | 0.89 | −4,126 | 1.00 | 1 / 8 | −0.178 | −0.108 | −0.095 / −0.194 | fails |
| G5 | 4-hour power of three: 4H candle 2 closure, 15m CISD in the next 4H candle | 657 | +303 | +0.008 | 44.7 | 1.01 | −2,002 | 0.42 | 4 / 8 | +0.022 | −0.006 | +0.009 / +0.027 | fails |
| G6 | Scalping model: 1H closure, 15m candle 2 closure, 1m CISD in the next hour | 1,532 | −9,942 | −0.217 | 33.7 | 0.72 | −9,953 | 1.00 | 0 / 8 | −0.268 | −0.164 | −0.220 / −0.215 | fails |
| G7 | Silver Bullet without a daily bias: raid of the 09:00 hour, 1m swing break, limit at the 1m FVG | 611 | −2,546 | −0.031 | 25.9 | 0.92 | −8,401 | 0.66 | 3 / 8 | +0.047 | −0.109 | −0.057 / −0.083 | fails |

Reported variants (no verdict): G1 on `fail` days only 558 trades, +1,855 $, −0.007 R; G3 `pdh` (target candle 1's
high) 301 trades, −354 $, −0.080 R; G4 `first` (first CISD, no confirmation) 830 trades, −9,546 $, −0.161 R; G4
`retest` (limit at the opening price closed through) 651 trades, +2,033 $ but −0.113 R (the dollars come from the
wider-stop trades; per unit of risk it loses), p 0.98. Full table `data/studies/yt1/yt4_full_table.md`, variants `yt4_full_variants.csv`.

G5 is the only rule not clearly negative: 657 trades for +303 $, i.e. zero. G6, the highest-frequency one, lost in
every one of the eight years.

## Claim checks (each rate next to the base rate; `yt4_claims_table.csv`)

| Claim | 2019–22 | 2023–26 | Base rate | Holds? |
|---|---|---|---|---|
| **A** A day that closes beyond the previous day's high / low → the next day trades beyond that day's high / low | 76.2 % (n 470) | 73.5 % (n 465) | 50.4 % | **Yes**, both halves, also on 4H (69.5 %) and 1H (69.2 %) |
| A, order: next day takes that extreme before the opposite one | 73.8 % | 71.8 % | 44.0 % | **Yes** |
| **B** A day that runs the previous extreme and closes back inside → the next day takes the other side | 66.7 % (n 267) | 58.9 % (n 285) | 50.4 % | Yes, weaker out of sample (+8.5 pp, p 0.008) |
| **C** Candle 3 closure → candle 4 expands, against candles that simply closed the same way | 4H 66.2 % | 4H 60.7 % | 65.6 % | **No**: no better than any up-close candle (daily +0.0 pp, 4H −2.3 pp, 1H +0.7 pp) |
| C, candle 4 holds the near half of candle 3 | daily 42.4 % | daily 37.2 % | 33.8 % | Small (+6.0 pp daily, +2.9 pp 4H over the span) |
| **F** The day's low is set 08:00–09:59 on up days (high on down days) | 17.4 % | 18.1 % | 13.8 % | Small (+4.0 pp); more up-day lows are set 18:00–21:59 (39 %) than in any other four hours |
| **G** In a 4H candle continuing the trend, the wick sits inside the last 1H candle's range | 57.3 % | 58.3 % | 30.8 % | **Yes**, +27 pp both halves |
| **I** The run against the bias that closes back over the 08:30 / 09:30 open holds for the day | 32.3 % / 10.8 % | 31.0 % / 14.5 % | 32.4 % / 14.3 % | **No** difference from other days |
| **J** On bullish-bias days the cash-session low comes before the high | 49.7 % | 47.2 % | 50.0 % | **No** |
| **K** Inside day in a trend → next day continues | 57.5 % (n 87) | 49.1 % (n 108) | 44.0 % | Not established (in-sample +13 pp, out of sample +5 pp, p 0.28) |

## Why a 75 % statistic does not make a trade (description, measured after the result; not a test)

On the 1,459 bias days, the previous day's extreme was taken on 70.7 %. On **55.7 % it had already been taken before
09:30**; only 15.1 % of days took it for the first time in the cash session. From the 09:30 open to the close, price
moved in the bias direction on 49.7 % of days, mean −3.7 points. So claim A is true and almost all of it is used up
overnight: it describes where price goes between 18:00 and the open, and says nothing about the session this account
trades. That is the same pattern as the NQ Stats / edgeful hit rates in YT1: the published number reproduces, the
trade built on it does not pay.

## Readings, corrections and limits

- His point of interest, session and entry are discretionary. Each rule closes those gaps with a stated reading
  (`YT4_SPEC.md` Part 2, the coders' "(R)" lists in the notes). This closes these seven mechanical readings, not his
  trading by eye. Models that need a hand-marked higher-timeframe zone (order block, fair value gap on the weekly or
  daily chart, SMT divergence against ES) were not coded.
- `tools/yt1/tt.py`: the roll exclusion in `bias` depends on the roll day's candle having at least 690 bars; one
  day (2020-03-16, 571 bars after limit-down halts) keeps a bias. The harness drops that day as a roll day, so no trade
  is affected. Not changed after registration.
- G2 skips days whose three daily candles include a roll candle (coder's reading, at most 9 trades).
- G4's window runs from the hourly gate's close to 11:30 with no 08:30 floor, as registered; 125 of 389 in-sample
  entries are before 08:30.
- G7: 192 of 630 in-sample confirmed raids have no fair value gap and are no trade.
- Count of things tried, for the next batch: 53 (YT1) + 29 (YT2) + 1 (YT3) + 7 (YT4) = 90 rules, 14 + 13 claim checks.

---
# YT5 — combinations of TTrades confluences: 5,184-combination grid, searched on 2019–2022, picks tested on 2023–2026 (rules in `YT5_SPEC.md`, registered 2026-10-09)

**Verdict: all five picks fail out of sample; no combination is a candidate.** The grid as a whole loses: of the
624 combinations with at least 150 in-sample trades, 89 had a positive mean R in-sample, and the best of them is
weaker than the best that many no-edge rules produce by luck (reality check p = 0.9995 in-sample, 0.9985 full span).
Selection frozen before the later bars were run (`YT5_IS_STAMP.txt`); the in-sample grid rebuilt from the full-span
signals reproduces the frozen n and net for all 5,184 combinations; the five picks reconcile to the cent with the
standard runner; every pick and eight check combinations covering every confluence level passed the look-ahead test.
Notes: `data/studies/yt1/notes/G8.md`.

**Frame.** A CISD on 1-, 5- or 15-minute bars is the entry, in its own direction; stop beyond the protected low /
high, target 2R, flat at the flat bar, the first qualifying signal of the day. Confluences switched on and off:
window (08:30–11:00, 09:30–11:00, 10:00–11:00, 13:30–15:00), daily bias (any / continuation / failed run), entry in
discount or premium of the previous day's range, entry under the daily open, a raid of the previous day's or the
overnight low, a 1-hour or 4-hour candle 2 / 3 closure in the direction, SMT divergence with ES.

## The five picks (ranked on 2019–2022, tested once on 2023–2026)

| Pick | Combination | In-sample: trades, net $, R | Out of sample: trades, net $, R | p (OOS) | + years (OOS) | Neighbours R (OOS) | Verdict |
|---|---|---|---|---|---|---|---|
| 1 | 15m CISD, 13:30–15:00, entry above EQ, 4H closure | 314, +5,066, +0.113 | 297, −7,494, −0.105 | 0.95 | 0 / 4 | −0.096 / −0.038 | fails |
| 2 | 15m CISD, 13:30–15:00, entry above EQ, 1H closure | 248, +3,626, +0.113 | 270, −2,124, −0.069 | 0.86 | 2 / 4 | −0.051 / −0.012 | fails |
| 3 | 5m CISD, 09:30–11:00, entry in discount and under the daily open, 4H closure | 214, +3,824, +0.137 | 234, +2,415, +0.070 | 0.23 | 3 / 4 | +0.066 / +0.073 | fails (p) |
| 4 | 15m CISD, 08:30–11:00, entry in discount and under the daily open, 4H closure | 152, +924, +0.143 | 159, +1,624, +0.058 | 0.28 | 3 / 4 | −0.018 / −0.048 | fails (p, neighbours) |
| 5 | 15m CISD, 10:00–11:00, raid of the overnight low / high | 173, +2,941, +0.107 | 224, −2,656, −0.064 | 0.83 | 1 / 4 | −0.076 / −0.072 | fails |

The combination with the most in-sample dollars (15m CISD, 13:30–15:00, 4H closure: 447 trades, +6,408 $) made
−7,018 $ on 445 trades out of sample.

Pick 3 is the only one that kept its sign with both neighbours: full span 448 trades, +6,239 $, +0.102 R, 6 of 8
years, max drawdown −2,130 $, p 0.061. That is short of the candidate bar on the full span as well (p < 0.05), and it
was the third-best of a searched grid, so it is logged as the nearest miss and nothing more.

## The literal answer, in hindsight (top of 5,184 over the full span; this is selection, not evidence)

| | Combination | Trades | Net $ | R / trade | t |
|---|---|---|---|---|---|
| Most dollars | 1m CISD, 08:30–11:00, raid of the previous day's low / high and close back inside | 741 | +8,085 | +0.066 | 1.26 |
| 2nd | 5m CISD, 09:30–11:00, 4H closure | 1,456 | +7,274 | +0.054 | 1.49 |
| 3rd | 5m CISD, 09:30–11:00, under the daily open, 4H closure | 625 | +6,793 | +0.072 | 1.31 |
| Highest t | 15m CISD, 13:30–15:00, failed-run bias, entry above EQ | 213 | +1,426 | +0.159 | 1.96 |

With 1,165 combinations of 150+ trades, the largest t expected from rules with no edge is about 2.9 (95 % of the
time below 3.65). The observed 1.95 is well under that. +8,085 $ over 7.3 years on one micro contract is also less
than half of what the YT1 candidates E09 (+21,238 $) and C19b (+18,001 $) showed, with a weaker t.

## What the grid says about each confluence (average mean R over the combinations using it; description)

| Confluence | Level | 2019–22 | 2023–26 |
|---|---|---|---|
| Trigger | 1m / 5m / 15m | −0.156 / −0.102 / −0.029 | −0.120 / −0.055 / −0.039 |
| Window | am / open / sb / pm | −0.128 / −0.094 / −0.080 / −0.158 | −0.102 / −0.065 / −0.083 / −0.080 |
| Daily bias | none / any / cont / fail | −0.095 / −0.138 / −0.132 / −0.154 | −0.067 / −0.097 / −0.126 / −0.068 |
| EQ | none / discount / premium | −0.112 / −0.108 / −0.126 | −0.078 / −0.071 / −0.105 |
| Daily open | none / under it | −0.112 / −0.120 | −0.076 / −0.099 |
| Raid | none / previous day / overnight | −0.120 / −0.036 / −0.110 | −0.091 / −0.047 / −0.049 |
| HTF closure | none / 1H / 4H | −0.126 / −0.108 / −0.096 | −0.071 / −0.104 / −0.098 |
| SMT with ES | none / smt | −0.103 / −0.179 | −0.086 / −0.075 |

- No level averages above zero in either half. Requiring the **daily bias** made the average worse in both halves.
- The **previous-day raid** and the **15-minute trigger** were the least negative in both halves. The 1-minute trigger
  is the worst: its stops are a few points, so one tick of slippage and the commission are a large share of R.
- In-sample rank carried some information (Spearman +0.32 between in-sample and out-of-sample mean R; the in-sample
  top 10 % averaged −0.014 R out of sample against −0.084 for all eligible), but it ranks "less negative", and the
  top decile's average is still below zero.

## Readings and limits

- Exits were fixed (2R, protected-low stop, flat bar); targets at liquidity, partials and break-even moves were not
  searched, to keep the grid from becoming an exit optimiser. Hand-marked zones (order blocks, weekly / daily fair
  value gaps) are not in the grid.
- Readings: SMT reference window 120 minutes; overnight low frozen at 08:29 for every window; higher-timeframe
  candles are clock blocks, counted once complete; E and the previous-day raid are false on the third day after a roll
  (16 traded days; the roll day and the day after are not traded at all).
- The out-of-sample years had been run 90 times before on other rules, and the author had seen YT4's results when
  writing the grid.
- Count of things tried, for the next batch: 53 + 29 + 1 + 7 + 5 = 95 rules (plus this 5,184-combination in-sample
  search), 27 claim checks.

---
# YT6 — the TTrades confluences YT5 left out: 230,850-combination grid and the weekly claims (rules in `YT6_SPEC.md`, registered 2026-10-09)

**Verdict: all six picks fail the registered out-of-sample test; none is a candidate.** Two came close and are the
strongest TTrades-derived results so far: pick 1 and pick 2 were positive in all four out-of-sample years with both
neighbours positive, at p 0.088 and p 0.025 against a bar of 0.0083 (0.05 / 6). The grid as a whole still loses and
its top is no better than luck (reality check p = 0.91 in-sample, 0.66 full span).
Selection frozen before the later bars were run (`YT6_IS_STAMP.txt`); the in-sample grid rebuilt from the full-span
signals reproduces the frozen n and net for all 230,850 combinations; YT5's 5,184 combinations are reproduced exactly
inside this grid; picks reconcile to the cent with the standard runner. Notes: `data/studies/yt1/notes/G9.md`.

**Added to YT5's grid:** the London window (02:00–04:59, flat 08:29); bias invalidation (trade against the daily bias
after an hourly close through the previous day's EQ); entry under the 00:00 open, or under both the 00:00 and 08:30
opens; "failure to manipulate" (the CISD's protected low sits above the previous day's high or the overnight high
that price has broken; mirror for shorts); targets at the previous day's high / low or at the nearest liquidity at
least 1R away; a retest entry (limit at the price the CISD closed through, 30 minutes); a positional entry (market
at the open of the next clock hour if the stop has not traded).

## The six picks (ranked on 2019–2022, tested once on 2023–2026)

| Pick | Combination | In-sample: trades, net $, R | Out of sample: trades, net $, R | p (OOS) | + years (OOS) | Neighbours R (OOS) | Verdict |
|---|---|---|---|---|---|---|---|
| 1 | 1m CISD 09:30–11:00 holding above the broken overnight high (below the low for shorts); enter at the next hour's open; 2R | 207, +7,966, +0.278 | 255, +7,342, +0.114 | 0.088 | 4 / 4 | +0.026 / +0.096 | fails (p) |
| 2 | 15m CISD 08:30–11:00 with SMT divergence against ES; limit at the retest; target the previous day's high / low | 157, +4,303, +0.716 | 137, +5,873, +0.491 | 0.025 | 4 / 4 | +0.431 / +0.515 | fails (p) |
| 3 | 5m CISD 09:30–11:00 holding above the previous day's high, 1H closure; 2R | 193, +5,175, +0.266 | 202, +2,008, +0.055 | 0.28 | 3 / 4 | −0.005 / +0.130 | fails |
| 4 | 5m CISD 10:00–11:00, bias invalidation, entry beyond EQ; 2R | 192, +4,493, +0.259 | 215, +1,706, +0.002 | 0.49 | 2 / 4 | −0.001 / +0.068 | fails |
| 5 | 5m CISD 09:30–11:00 holding above the broken overnight high, entry above EQ; next hour's open; 2R | 225, +6,424, +0.204 | 244, +189, +0.022 | 0.39 | 3 / 4 | −0.062 / +0.077 | fails |
| 6 | Consensus (best level of each confluence, relaxed until 150 trades): 15m CISD 09:30–11:00 after a raid of the previous day's low / high; 2R | 163, −4,968, −0.130 | 215, −4,910, −0.085 | 0.88 | 1 / 4 | −0.098 / −0.098 | fails |

The combination with the most in-sample dollars (1m CISD 08:30–11:00, discount, 1H closure, retest, previous-day
target: 609 trades, +8,296 $) made −502 $ on 640 trades out of sample.

## The two near misses, full span (description; both were selected in-sample, so full-span p-values are flattering)

| | Pick 1 | Pick 2 |
|---|---|---|
| Trades / net $ / R per trade | 462 / +15,308 / +0.188 | 294 / +10,176 / +0.611 |
| Positive years / max drawdown | 7 of 8 / −1,310 $ | 8 of 8 / −1,551 $ |
| Win % / average win / average loss | 46 % / +175 $ / −89 $ | 32 % / +257 $ / −70 $ |
| Median stop distance | 45 points | 32 points |
| With one more tick of slippage per side | +14,847 $ | +9,882 $ |
| Trades on ORB v1.4 trade days, same side as ORB | 291 of 462, 92 % | 119 of 294, 56 % |
| Net on ORB days / off ORB days | +14,511 $ / +798 $ | +6,517 $ / +3,659 $ |
| Daily P&L correlation with ORB / with E09 | 0.41 / 0.40 | 0.13 / 0.09 |
| ORB + pick: net, max drawdown, return ÷ drawdown (ORB alone 5.38) | +36,209 $, −4,213 $, 8.6 | +31,076 $, −3,426 $, 9.1 |

- **Pick 1 is the opening-range / momentum effect again.** It trades the same side as ORB on 92 % of shared days (97 %
  with E09) and earns almost nothing on days ORB does not trade. It is a continuation entry after the overnight range
  breaks, taken at 10:00 or 11:00. Its 1.5R neighbour is close to zero out of sample.
- **Pick 2 is the more independent one.** About 40 trades a year; it agrees with ORB's side only 56 % of the time and
  over a third of its profit is on non-ORB days. Its edge rests on a low win rate with large winners (target at the
  previous day's extreme), and its out-of-sample p of 0.025 is about what one of six no-edge picks reaches one time
  in seven.
- Neither met the bar that was set before the test. Neither has had a second coder's re-code.

## The grid as a whole

- 8,435 of 230,850 combinations had 150+ in-sample trades; 1,366 of those were positive in-sample. Largest in-sample
  t 2.88 against a luck median of 3.26. Full span: 19,139 combinations of 150+ trades, largest t 3.34 (15m CISD, SMT,
  discount, previous-day target, retest: 221 trades, +9,258 $) against a luck median of 3.47, p 0.66. The most
  dollars in hindsight is pick 1.
- In-sample rank carried a little information (Spearman +0.26; the in-sample top 10 % averaged −0.060 R out of sample
  against −0.118 for all eligible). The top decile's average is still negative.

| Confluence | Level | 2019–22 | 2023–26 |
|---|---|---|---|
| Trigger | 1m / 5m / 15m | −0.177 / −0.119 / −0.046 | −0.154 / −0.072 / −0.072 |
| Window | London / am / open / sb / pm | −0.172 / −0.132 / −0.125 / −0.076 / −0.200 | −0.128 / −0.135 / −0.087 / −0.137 / −0.105 |
| Daily bias | none / any / cont / fail / invalidation | −0.113 / −0.190 / −0.200 / −0.240 / −0.102 | −0.101 / −0.148 / −0.155 / −0.175 / −0.048 |
| EQ | none / discount / premium | −0.142 / −0.100 / −0.182 | −0.111 / −0.108 / −0.142 |
| Opens | none / 18:00 / 00:00 / 00:00 and 08:30 | −0.151 / −0.121 / −0.135 / −0.166 | −0.112 / −0.115 / −0.132 / −0.126 |
| Raid / break | none / pd raid / session raid / pd break held / session break held | −0.143 / −0.083 / −0.121 / −0.227 / −0.148 | −0.119 / −0.121 / −0.082 / −0.180 / −0.122 |
| HTF closure | none / 1H / 4H | −0.147 / −0.141 / −0.130 | −0.108 / −0.130 / −0.140 |
| SMT with ES | none / smt | −0.143 / −0.138 | −0.123 / −0.086 |
| Target | 2R / previous day / nearest liquidity | −0.144 / −0.113 / −0.166 | −0.112 / −0.115 / −0.128 |
| Entry | close / retest / positional | −0.127 / −0.192 / −0.087 | −0.104 / −0.171 / −0.053 |

No level averages above zero in either half. Trading with the daily bias is worse than without it in both halves;
trading against it after an invalidation is the least bad bias level. The midnight and 08:30 opens do not help. The
London window is no better than New York. The retest entry is the worst entry on average (it fills on the trades
that come back); the positional entry is the least bad. The previous-day raid, least negative in YT5, did not hold
out of sample here.

## Weekly and sequence claims (`yt6_claims_table.csv`; threshold p < 0.05 / 8 = 0.006)

| Claim | 2019–22 | 2023–26 | Base rate | Holds? |
|---|---|---|---|---|
| **L1** A week that closes beyond the previous week's high / low → the next week trades beyond that week's extreme | 79.5 % (n 88) | 74.4 % (n 82) | 50.9 % | **Yes**, both halves |
| **L2** A week that runs the previous week's extreme and closes back inside → the next week takes that week's other side | 64.9 % (n 37) | 66.7 % (n 51) | 50.9 % | Leaning yes (+15 pp, p 0.008 full span, just short of the threshold) |
| L2 as he words it: "the previous week's low is the draw" (next week trades beyond the *previous* week's other side) | 40.5 % | 35.3 % | 52.8 % | **No**, it happens less often than usual |
| **L3** After three continuation closes in a row the run tends to end (a fourth continuation close) | 30.8 % (n 39) | 22.0 % (n 41) | 37.2 % | Not established (−11 pp, p 0.052) |
| **L4** Friday retraces 20 % of the week's range after a Monday / Tuesday low | 72.5 % (n 80) | 67.1 % (n 82) | 73.8 % (same test on Thursday) | **No**: Friday is no different from Thursday |

L1 is the weekly version of claim A in YT4 and has the same limit: it says where the next week trades at some point,
not what the cash session does.

## Readings and limits

- Positional entries with a 2R target: the target depends on the fill at the next bar's open, so the mirrored-future
  test is run with the target attached after the fill (the same exception as `s_Z00`); with that, every pick, its
  neighbours and 13 check combinations covering every level pass. Five deliberately planted look-ahead errors were
  each caught.
- Limit orders fill on a touch, one tick worse than the limit (house rule).
- Readings: London trades flat at 08:29; session levels are 18:00–01:59 for London and 18:00–08:29 otherwise; the
  00:00 / 08:30 open is the first bar at or after that minute; hour candles under 30 minutes are ignored for the
  invalidation; in the consensus fallback each confluence changes once.
- The out-of-sample years had been run on 95 rules before this, and the author had seen YT5's out-of-sample
  per-confluence table when writing this grid.
- Count of things tried, for the next batch: 53 + 29 + 1 + 7 + 5 + 6 = 101 rules (plus two in-sample grid searches,
  5,184 and 230,850 combinations), 31 claim checks.

---
# YT7 — the hourly add to an open ORB trade (G10) and the footprint study on it (FLOW3) (rules in `YT7_SPEC.md`, registered 2026-10-09)

**Verdict.** **G10 is a candidate found in hindsight; forward test required.** It meets every part of the usual
criterion except the p level (0.0006 against 0.05 / 102 = 0.00049), but the rule was found by splitting YT6's pick 1
after its results were known on both halves, so that p-value is not a test. **FLOW3: neither footprint pick counts.**
The first one, net aggressive volume beyond the broken overnight level, missed by the narrowest margin (difference in
win rate +24 points out of sample, p 0.0258 against 0.025) with the same direction and size as in-sample; it is
logged as a lead for forward tracking, not a filter. Nothing is adopted.

## G10 — full span 2019-06 → 2026-10 (house fills)

The rule: the day's first 1-minute CISD between 09:30 and 10:59 whose protected low is above the overnight high
(18:00–08:29; mirror for shorts); enter at the open of the next clock hour unless the stop has traded; stop 1 tick
beyond the protected low; target 2R; **taken only if an ORB v1.4 trade entered earlier that day is still open on the
same side.** It is a separate position with its own stop and target.

| Variant | Trades | Net $ | R / trade | Win % | PF | Max DD $ | p | + years | R 2019–22 | R 2023–26 |
|---|---|---|---|---|---|---|---|---|---|---|
| **base** (2R) | 194 | +10,354 | +0.322 | 52.6 | 1.95 | −1,239 | 0.0006 | 7 / 8 | +0.433 | +0.239 |
| nb1 (1.5R) | 194 | +8,336 | +0.232 | 55.2 | 1.81 | −1,239 | 0.0023 | 6 / 8 | +0.314 | +0.171 |
| nb2 (3R) | 194 | +11,961 | +0.372 | 49.0 | 2.06 | −1,239 | 0.0004 | 7 / 8 | +0.395 | +0.355 |
| `retry` (a later signal may be used) | 256 | +10,897 | +0.255 | 50.0 | 1.74 | −1,626 | 0.0011 | 6 / 8 | +0.367 | +0.164 |
| `alone` (the signal when ORB is not open on its side) | 268 | +4,954 | +0.090 | 41.8 | 1.44 | −1,000 | 0.14 | 5 / 8 | +0.174 | +0.018 |
| `naive` benchmark (second contract on the hour whenever ORB is open, ORB's stop, no target) | 774 | +17,566 | +0.100 | 48.2 | 1.28 | −2,651 | 0.018 | 6 / 8 | +0.103 | +0.097 |

- **Re-code:** a second coder wrote G10 from the text without the YT6 code. The signal matches YT6's pick 1 on 207 of
  207 in-sample trades in every field, and base reproduces the disclosed 83 trades / +5,116 $. Look-ahead test passed
  for all seven variants (the 2R target is attached after the fill, as in YT6); a planted leak was caught.
- **What the signal adds over "ORB is still in":** per trade, about three times the naive add (+0.32 R against
  +0.10 R; +53 $ against +23 $) with half the drawdown, on a quarter of the trades. The naive add makes more
  dollars in total because it trades four times as often with a wider stop.
- **Without ORB the signal has nothing** out of sample (`alone` +0.018 R in 2023–2026).
- Average win +208 $, average loss −118 $ (realised 1.76 : 1). One reading carries 13 of the 194 trades: an ORB
  entry at the 09:59 / 10:59 close counts as "entered earlier" than the hour's open.
- It is the same edge as ORB v1.4, sized up on the days ORB is holding beyond the overnight range. Both positions lose
  together on a reversal.

## FLOW3 — footprint and order flow at the add (searched on 2019–2022, tested once on 2023–2026)

193 of the 194 base trades are on order-flow days (83 in-sample, 110 out of sample). Eleven measures at the last
minute before the entry, each split at its in-sample median; the two with the largest in-sample difference in win
rate were the picks.

| Pick | Favourable side | 2019–22: favourable vs not | 2023–26: favourable vs not | Difference (OOS) | p (OOS) | Verdict |
|---|---|---|---|---|---|---|
| 1 `brk_delta` ≥ +0.0217 | Of the volume traded beyond the broken overnight level since 09:30, buyers out-hit sellers by at least 2.2 % (longs; mirror for shorts) | 69.0 % (42) vs 41.5 % (41) | **56.1 % (82) vs 32.1 % (28)** | +24.0 pts | 0.0258 | does not count (level 0.025) |
| 2 `div` ≥ −0.0033 | NQ's delta share minus ES's | 64.3 % (42) vs 46.3 % (41) | 50.0 % (62) vs 50.0 % (48) | 0.0 pts | 0.58 | does not count |

Pick 1 by the numbers: favourable side, full span 124 trades, 75 wins (60.5 %), +8,874 $; unfavourable side 69
trades, 26 wins (37.7 %), +1,293 $, and −636 $ on 28 trades out of sample. Mean R out of sample +0.380 against
−0.233. Realised reward to risk is about 1.5 : 1 on the favourable side, so the gain is in the win rate, not in the
size of the winners. Both picks together (reported): 79.3 % of 29 in-sample, 57.1 % of 49 out of sample.

Every measure with the frozen thresholds (win rate high side vs low side; description):

| Measure | 2019–22 | 2023–26 |
|---|---|---|
| `cum` NQ delta ÷ volume since 09:30 | 57.1 % vs 53.7 % | 56.8 % vs 36.1 % |
| `last15` last 15 minutes | 59.5 % vs 51.2 % | 56.4 % vs 34.4 % |
| `since` from the signal to the entry | 62.5 % vs 50.0 % | 59.5 % vs 28.1 % |
| `pull` during the pullback | 54.8 % vs 56.1 % | 50.7 % vs 48.8 % |
| `es_cum` ES delta ÷ volume | 47.6 % vs 63.4 % | 54.2 % vs 45.1 % |
| `div` NQ − ES | 64.3 % vs 46.3 % | 50.0 % vs 50.0 % |
| `vol_rel` recent volume | 52.4 % vs 58.5 % | 53.5 % vs 43.6 % |
| `poc` price against the point of control | 61.9 % vs 48.8 % | 56.7 % vs 42.0 % |
| `stack` stacked imbalances | 56.8 % vs 53.8 % | 50.8 % vs 48.9 % |
| `brk_delta` | 69.0 % vs 41.5 % | 56.1 % vs 32.1 % |
| `brk_share` share of volume beyond the level | 57.1 % vs 53.7 % | 53.2 % vs 45.8 % |

- The measures that say "aggressive flow agrees with the trade" (`cum`, `last15`, `since`, `brk_delta`, `poc`) all
  point the same way in 2023–2026, more strongly than in 2019–2022. FLOW1 saw the same thing on ORB itself: flow
  agreeing with the breakout helped only in the recent half. `brk_delta` is the one that shows up in both halves.
- Stacked imbalances and delta during the pullback, the two most "footprint-pattern" measures, show nothing.
- The out-of-sample split is uneven (82 / 28) because net buying beyond the level was higher in 2023–2026 than the
  in-sample median; the unfavourable side is the weakest quarter of days.
- Small samples throughout. The miss at p 0.0258 is a miss; it is also one of two picks, and the reading that it is a
  real effect rests on 28 unfavourable trades.

## Readings and limits

- NQ order flow against MNQ trades: the basis is at most one tick on every trade with flow; moving the level one tick
  moves 1–3 trades across the `brk_delta` threshold.
- `poc` uses the NQ 30-second close at the decision; `stack` follows FLOW2's definition; deltas are summed from 09:30
  (19 days carry a stray 09:29 row). All measures are unchanged when every flow row and bar after the decision is
  deleted.
- Order flow exists only on ORB trade days, 09:30–11:34, to 2026-09-22.
- Count of things tried: 102 rules (G10 added), two grid searches, 31 claim checks, FLOW3's eleven measures.
