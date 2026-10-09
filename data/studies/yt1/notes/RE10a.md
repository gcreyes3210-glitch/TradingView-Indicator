# RE10a — E10a first hour continuation, second independent coding

Module `tools/yt1/s_RE10a.py`, written from the spec text (E10a + Common rules) and research note entry 10 only. The
first coder's module, notes and results were not opened.

## 1. Readings made where the spec text did not settle something (one per line)
1. "The 10:29 close" is the close of the 1-minute bar stamped 10:29; the neighbours use the bars stamped 09:59 and 10:59.
2. "The 09:30 open" is the open of the 09:30 1-minute bar (`days.o930`).
3. A close exactly equal to the 09:30 open is no trade (one in-sample day at 10:29).
4. A day with no bar at the decision minute is no trade (none in-sample).
5. Early-close days are traded like any other day and closed at the harness flat bar (10 minutes before the halt).
6. No price stop, so R unit = 0.1 x that day's daily ATR(14) (`ctx.days.atr`).

Nothing else was added: market entry at that close (`etype='close'`), exit at the flat bar, one trade a day, roll
days and no-ATR days dropped by `core.run_orders`.

## 2. Coding errors found after first seeing results
None.

## 3. Hand check (bars printed from `ctx.a`)
- 2019-10-21: 09:30 open 7914.00; 10:29 close 7921.75 > open -> long 7921.75 + 0.25 = 7922.00; 15:59 close 7946.50
  -> exit 7946.25; (24.25 x 2) - 2 = +46.5 $; 0.1 x ATR = 12.889 -> +1.804 R. Matches.
- 2022-02-25: open 13995.25; 10:29 close 13991.25 < open -> short 13991.00; 15:59 close 14182.00 -> exit 14182.25;
  -384.5 $, -4.005 R. Matches.
- 2022-10-07: open 11345.75; 10:29 close 11245.00 -> short 11244.75; 15:59 close 11099.00 -> exit 11099.25; +289.0 $,
  +4.190 R. Matches.
- 2019-11-29 (early close): long at 10:29, closed at the 13:04 flat bar.
- Count: 926 cash days - 15 roll - 14 without ATR + 1 that is both - 1 with close = open = 897 trades. Matches.

## 4. Look-ahead test
`python3 tools/yt1/run.py RE10a --check` -> PASS (16 of 16; the harness's "not reproduced on the 150-day window"
remark is the daily ATR's warm-up changing `r_pts`).

## 5. Final in-sample output (`python3 tools/yt1/run.py RE10a --phase is --show 8`)
```
base                   n   897  net     +5663  R  +0.117  win  55.0  pf  1.07  dd    -7363  p 0.2179  yrs+ 2/4  h1 +0.117 h2 +nan  | +359 -3088 -202 +8594 +0 +0 +0 +0
nb1                    n   894  net     +2984  R  +0.055  win  53.8  pf  1.03  dd    -9448  p 0.3754  yrs+ 2/4  h1 +0.055 h2 +nan  | -12 -476 +244 +3228 +0 +0 +0 +0
nb2                    n   898  net     +1976  R  -0.002  win  52.2  pf  1.03  dd    -8147  p 0.4979  yrs+ 1/4  h1 -0.002 h2 +nan  | -344 -4041 -988 +7350 +0 +0 +0 +0
```
