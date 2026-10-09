# YT1 — walk-forward step 1: in-sample results, 2019-06-03 → 2022-12-30

Logged before any 2023–2026 bar was read by any YT1 strategy code. Every module was written and run by a coder who
had only bars to 2022-12-31, then re-run by the coordinator on the same cut bars (identical trade counts and R on
every rule). All 53 rules passed the mirrored-future look-ahead test except E08, which is built from the 09:30 open it
trades at and passes when only that print is exempt.

Two harness corrections were made between the first coders' runs and this table, both reported by coders with
evidence and neither based on a trade result: clock times on the two daylight-saving Sundays a year were an hour off
(changes no in-sample trade count in this table), and the Parabolic SAR put its dot inside the bar on turn bars
(C07: 1,253 trades, +0.061 R before; 1,251, +0.069 R after).

R is per trade after costs. "R nb1 / nb2" are the two pre-registered neighbours. Nothing here is a verdict: the
criterion needs the full span.

| ID | Rule | n | Net $ | R / trade | Win % | PF | p | R nb1 / nb2 | Net by year 2019 / 20 / 21 / 22 |
|---|---|---|---|---|---|---|---|---|---|
| A01 | JadeCap Silver Bullet | 288 | -1,489 | -0.018 | 35.8 | 0.89 | 0.5813 | -0.039 / +0.043 | +404 / +478 / -1448 / -923 |
| A02 | Casper 5-minute candle + 1-minute FVG break | 893 | -4,300 | -0.144 | 32.3 | 0.86 | 0.9992 | -0.167 / -0.153 | -542 / -1808 / -687 / -1264 |
| A03 | Casper 30-minute range, sweep and FVG back inside | 263 | +4,670 | +0.050 | 39.5 | 1.33 | 0.2700 | +0.067 / +0.068 | -508 / +3627 / +630 / +922 |
| A05 | Candle Range Theory on the 05:00-09:00 candle | 659 | -2,650 | -0.069 | 38.8 | 0.89 | 0.8904 | -0.065 / -0.074 | -547 / +487 / -1930 / -660 |
| A09 | ICT Silver Bullet, first FVG with the midnight-open side rule | 517 | -74 | -0.024 | 35.4 | 1.00 | 0.6480 | -0.058 / -0.056 | +215 / -198 / -1462 / +1371 |
| A10 | First presented FVG after 09:30 | 897 | +3,726 | +0.113 | 23.9 | 1.07 | 0.0755 | +0.051 / +0.099 | +84 / -2694 / +1010 / +5325 |
| A14 | Candle Range Theory, hourly | 236 | -974 | -0.194 | 35.6 | 0.88 | 0.9970 | -0.166 / -0.221 | -17 / -1142 / -291 / +476 |
| B01 | Quick Flip Scalper (15m box >= x ATR, reversal candle outside the box) | 146 | -1,447 | -0.240 | 14.4 | 0.76 | 0.8935 | -0.215 / -0.168 | -136 / -96 / -1112 / -102 |
| B03 | Casper 5-minute range, break and wick retest, midpoint stop | 354 | -2,614 | -0.084 | 33.3 | 0.86 | 0.8718 | -0.072 / +0.008 | -82 / -2093 / -678 / +240 |
| B04 | Jooviers Gems London box (04:00-08:59), first 5m close outside from 09:30 | 499 | -4,115 | -0.016 | 35.7 | 0.85 | 0.6006 | +0.013 / -0.009 | +218 / -2990 / +242 / -1585 |
| B05 | Scarface first-candle break and retest | 822 | -3,864 | -0.111 | 33.3 | 0.88 | 0.9882 | -0.111 / -0.102 | -1128 / -1706 / -1488 / +458 |
| B06 | Pre-market high / low break and retest | 740 | -4,745 | -0.126 | 33.4 | 0.82 | 0.9929 | -0.156 / -0.163 | -20 / -1569 / -2231 / -924 |
| B07 | DR / IDR 09:30-10:29, first 5m close beyond, stop the opposite DR extreme, flat bar | 804 | +4,360 | +0.019 | 55.0 | 1.07 | 0.2336 | +0.027 / +0.037 | -357 / -3947 / +1713 / +6951 |
| B08 | edgeful IB retracement: limit 1/4 W back from the IB extreme, stop beyond the midpoint | 292 | -156 | +0.020 | 39.7 | 0.99 | 0.3977 | -0.059 / +0.121 | +84 / -370 / -744 / +874 |
| B09 | IB75 (Dan Cooke): limit 1/4 W from the first-set IB extreme, target that extreme, VWAP filter | 30 | +162 | +0.113 | 60.0 | 1.23 | 0.2790 | -0.158 / +0.026 | -14 / +38 / +126 / +10 |
| B14 | IB breakout (samjNQ): 5m close beyond the IB on the VWAP side, stop the other IB level, target k x W | 863 | +6,754 | +0.036 | 56.0 | 1.11 | 0.0703 | +0.027 / +0.041 | -283 / -1957 / +3546 / +5448 |
| C01 | MACD + 200 EMA | 615 | +8,124 | +0.129 | 49.6 | 1.24 | 0.0016 | +0.071 / -0.023 | +916 / +3079 / +104 / +4025 |
| C02 | 8-55 EMA pullback, long only, 0.75 % trailing stop | 588 | +7,517 | +0.205 | 49.1 | 1.27 | 0.0281 | +0.181 / +0.250 | -338 / +3651 / +100 / +4104 |
| C03 | Triple Supertrend + Stochastic RSI + 200 EMA | 1006 | +1,999 | +0.009 | 44.7 | 1.04 | 0.4017 | -0.007 / +0.085 | -690 / +334 / -1310 / +3666 |
| C04 | Donchian(20) + 200 EMA | 899 | -5,238 | -0.007 | 46.9 | 0.92 | 0.5775 | +0.053 / +0.045 | +364 / -1097 / -1495 / -3010 |
| C05 | Supertrend(10, 3) flip + 200 EMA | 749 | +108 | +0.059 | 49.7 | 1.00 | 0.0536 | +0.018 / +0.041 | +1137 / +960 / +550 / -2538 |
| C06 | EMA 8 / 14 / 50 + Stochastic RSI + ATR bracket | 2446 | -3,352 | -0.009 | 59.6 | 0.97 | 0.7174 | -0.023 / +0.012 | -1144 / -3874 / -1930 / +3597 |
| C07 | MACD + Parabolic SAR + 200 EMA | 1251 | +8,170 | +0.069 | 46.4 | 1.12 | 0.0119 | +0.020 / +0.071 | +798 / +4026 / -2836 / +6181 |
| C08 | Bollinger upper-band breakout + 200 SMA + daily 9 EMA (long only) | 490 | +775 | +0.020 | 49.4 | 1.03 | 0.3321 | +0.027 / +0.041 | -290 / -1443 / +902 / +1606 |
| C09 | Stochastic (14,3,3) arm + RSI(14) > 50 + MACD > signal | 1188 | +5,970 | -0.005 | 44.0 | 1.08 | 0.5805 | -0.025 / +0.018 | +536 / +3152 / -464 / +2747 |
| C10 | 9 / 20 EMA "Bone Zone" first pullback | 457 | +330 | -0.056 | 28.0 | 1.02 | 0.7607 | -0.113 / +0.036 | +32 / +925 / -46 / -581 |
| C12 | TTM Squeeze fire (BB 20/2 inside KC 20/1.5xATR20, >= 6 on bars) | 165 | +400 | -0.018 | 39.4 | 1.05 | 0.6448 | -0.013 / +0.132 | -13 / -918 / +93 / +1238 |
| C13 | Connors RSI (3, 2, 100) out of the extreme + 200 SMA | 757 | -5,808 | -0.264 | 35.7 | 0.74 | 1.0000 | -0.282 / -0.145 | -312 / -3808 / -250 / -1438 |
| C15 | VWAP (09:30 anchor) trend-day first pullback | 402 | -1,570 | -0.103 | 34.3 | 0.87 | 0.9579 | -0.074 / -0.101 | -462 / -304 / -106 / -699 |
| C17 | NQ 1-minute 9/20/50 EMA pullback | 8074 | -20,232 | -0.204 | 34.3 | 0.85 | 1.0000 | -0.209 / -0.209 | -3369 / -4743 / -7385 / -4735 |
| C19a | TRADING RUSH Ichimoku cross above the cloud + EMA200 | 862 | +2,180 | +0.036 | 49.0 | 1.04 | 0.1323 | +0.002 / +0.069 | +131 / +2896 / -1056 / +208 |
| C19b | TRADING RUSH Keltner (20, 2 x ATR10) open-and-close outside + EMA200 | 815 | +11,920 | +0.091 | 52.1 | 1.21 | 0.0034 | +0.065 / +0.085 | +562 / +197 / +1587 / +9574 |
| C19c | TRADING RUSH DMI(14) +DI / -DI cross + EMA200 | 1353 | -5,001 | -0.015 | 44.8 | 0.93 | 0.6946 | -0.042 / -0.005 | +540 / -2998 / -2558 / +16 |
| C19d | TRADING RUSH Stochastic(14,3,3) cross under 20 / over 80 + EMA200 | 753 | -1,342 | -0.122 | 41.0 | 0.92 | 0.9974 | -0.102 / -0.158 | -491 / -1502 / +44 / +608 |
| C19e | TRADING RUSH RSI(14) back above 30 / below 70 + EMA200 | 101 | -2,331 | -0.142 | 38.6 | 0.60 | 0.8952 | -0.246 / -0.109 | -54 / -370 / -502 / -1404 |
| D03 | Stacked-imbalance pullback (ATAS) | 781 | -3,126 | -1.272 | 19.8 | 0.12 | 1.0000 | -1.267 / -1.270 | -249 / -601 / -1022 / -1254 |
| D05 | Absorption candle, POC in the wick, delta flip, at a level (Thraxx) | 363 | -1,060 | -0.190 | 33.9 | 0.80 | 0.9948 | -0.194 / -0.196 | -201 / -244 / -504 / -111 |
| D06 | Trapped traders (Trader Dale) | 1178 | +975 | -0.046 | 35.9 | 1.02 | 0.8718 | -0.071 / -0.049 | -1350 / -1534 / +2565 / +1294 |
| E01 | NQ Stats Hour Stats: fade the first breach of the previous hour's high / low to the hour's open | 1548 | -10,644 | -0.120 | 63.8 | 0.80 | 0.9979 | -0.152 / -0.112 | -662 / -2082 / -956 / -6944 |
| E02 | NQ Stats IB breaks: at the IB close, with the midpoint / first-extreme bias, target the IB extreme | 728 | -2,464 | -0.028 | 73.4 | 0.90 | 0.9247 | -0.051 / -0.060 | -310 / -1570 / -184 / -400 |
| E04 | NQ Stats Noon Curve: at the noon close, with Q2's one-sided break of Q1, stop beyond Q2's other extreme | 703 | +3,692 | -0.025 | 43.8 | 1.10 | 0.6821 | +0.023 / +0.065 | +384 / -1231 / +12 / +4528 |
| E05 | NQ Stats ALN sessions: partial engulf of Asia by London, trade to the London extreme it points to | 654 | -5,156 | -0.118 | 55.7 | 0.79 | 0.9942 | -0.112 / -0.077 | -407 / -4 / -1321 / -3424 |
| E06 | AM TBR: after the first touch of the 08:00 open +/- 0.25 SD, limit at k SD, target the 08:00 open | 611 | -2,893 | -0.053 | 53.5 | 0.91 | 0.9367 | -0.033 / -0.034 | -258 / -1028 / -1815 / +208 |
| E08 | Outside-open reversal: 09:30 open beyond the previous RTH range by >= 0.05 ATR, fade to that level | 325 | +502 | +0.012 | 36.9 | 1.03 | 0.4353 | -0.006 / +0.004 | -524 / +809 / -721 / +938 |
| E09 | Noise-area intraday momentum: half-hourly closes beyond open/prior-close x (1 +/- sigma), VWAP trailing exit | 817 | +8,610 | +0.173 | 39.4 | 1.24 | 0.0284 | +0.209 / +0.171 | -456 / +2114 / +2064 / +4888 |
| E10a | First hour continuation: at the 10:29 close, with the side of the 09:30 open, no stop, flat bar | 897 | +5,663 | +0.117 | 55.0 | 1.07 | 0.2179 | +0.055 / -0.002 | +359 / -3088 / -202 / +8594 |
| E10b | 15:00 continuation: at the 14:59 close, with the side of the 09:30 open and of the range middle, stop beyond the open | 762 | +9,916 | +0.041 | 50.1 | 1.42 | 0.0952 | +0.269 / +0.016 | -256 / +2006 / +2106 / +6058 |
| E11 | Larry Williams open +/- 0.25 x previous RTH range, stop orders to 15:00, first to fill, bracket 0.5 W | 859 | +6,201 | +0.033 | 53.4 | 1.09 | 0.1340 | +0.052 / +0.016 | +46 / -2516 / -434 / +9105 |
| E12 | Larry Williams Oops: open below the previous RTH low, buy stop at that low to 15:00, no stop, flat bar | 78 | +692 | +0.553 | 53.8 | 1.09 | 0.1590 | +0.190 / +0.528 | +182 / +2644 / -1878 / -254 |
| E13 | Crabel stretch after a 2-day narrow range: stop orders at the open +/- stretch, other level is the stop, BE after 60 min | 60 | +82 | +0.107 | 26.7 | 1.03 | 0.1946 | +0.123 / +0.109 | +366 / +632 / -4 / -910 |
| E15 | Camarilla pivots: S3 / R3 rejection and R4 / S4 breakout, four set-ups pooled | 1440 | +14,269 | +0.051 | 49.4 | 1.18 | 0.0238 | +0.058 / +0.028 | -47 / +2888 / +2808 / +8619 |
| E19 | Turnaround Tuesday, cash session: down Monday -> long Tuesday 09:30 open to the flat bar | 78 | -722 | -0.103 | 48.7 | 0.93 | 0.5603 | +0.317 / +0.454 | +446 / +44 / +735 / -1947 |
| E20 | Turn of the month, cash sessions: long 09:30 open to the flat bar on the last N and first M trading days | 298 | -361 | -0.165 | 53.0 | 0.99 | 0.6658 | +0.061 / +0.086 | -994 / +3251 / -3108 / +490 |
