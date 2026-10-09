# YT4 — TTrades: claim checks and trade rules, pre-registered 2026-10-09 (each part before its code was run)

Source: TTrades (@TTrades_edu). Sourcing notes: `data/studies/yt1/research/G_ttrades_concepts.md` (six videos) and
`H_ttrades_strategies.md` (second pass). TTrades publishes no hit rates, only "I expect" statements, so every claim
below is measured next to a **base rate**: the same outcome on all candles or all days, with no condition.
**Data, engine, fills, days not traded, order of work:** as `YT1_SPEC.md`. In-sample (to 2022-12-31) first.

## Part 1 — claim checks (K-G; registered before any YT4 code)
Candles: **daily** = the trading day 18:00 → 17:00 New York (reported a second time on midnight-to-midnight days);
**4H** = candles opening 18:00, 22:00, 02:00, 06:00, 10:00, 14:00; **1H** = clock hours. A candle needs at least half
its minutes to count. Contract-roll days and the candle after them are left out. "Trades above x" = at least 1 tick.

- **A — continuation close.** close(D) > high(D−1) → D+1 trades above high(D). Mirror for lows. Also: D+1 takes
  high(D) before low(D). Base: the same outcomes on every day. Daily; also 4H and 1H candles (claim D's wording).
- **B — failed run.** high(D) > high(D−1), close(D) < high(D−1), and low(D) ≥ low(D−1) → D+1 trades below low(D);
  also whether D+1 takes low(D) before high(D). Mirror. Base: every day. Daily; also 4H and 1H.
- **C — candle 3 closure.** C2 is a swing low: low(C2) < low(C1) and low(C3) ≥ low(C2). C3 closes above
  max(open, close) of C2. Outcomes: low(C4) ≥ midpoint of C3's range; high(C4) > high(C3); both. Mirror. Base: the
  same outcomes after every candle, and after every candle that closed up (down for the mirror). 4H, 1H, daily.
- **F — when the low forms.** Share of days whose 18:00 → 17:00 low is printed 08:00–09:59, on all days and on days
  that close above their 18:00 open; the full distribution by 2-hour block next to it.
- **G — the 4H wick.** For a 4H candle that closes up after an up-closing 4H candle: share whose low lies inside the
  high-low range of the last 1H candle before it opened. Mirror. Base: every 4H candle (its low against that range).
- **I — opposing run.** Bias from A and B at the daily close (bullish = closed above the previous high, or ran the
  previous low and closed back inside; bearish = the mirrors; else none). On bullish days: price trades below the
  09:30 open, then a 5-minute bar closes back above it (by 11:30). Outcome: the run's low is not traded through by
  16:00. Mirror on bearish days. Base: the same event on no-bias days and on days where the bias points the other way.
  Repeated with the 08:30 open (run and close-back by 09:30).
- **J — bullish-day order.** On bullish-bias days: the 09:30–16:00 low is printed before the high. Mirror. Base: all days.
- **K — inside day.** high(D) < high(D−1), low(D) > low(D−1), close(D) > close(D−5) → D+1 takes high(D) before
  low(D). Mirror for a downtrend. Base: all days.
Each rate is reported with its count, its base rate, the difference and a two-proportion p-value. 14 claim families:
a difference with p > 0.05 / 14 is read as no difference.

## Part 2 — trade rules (G1–G7; registered after Part 1's in-sample numbers were seen, before any Part 2 code)
His models leave the point of interest, the entry choice and the session to the trader. Each rule below is the model
with those gaps closed by a stated reading *(R)*; sourcing and his wording are in `H_ttrades_strategies.md`.
Building blocks are his own definitions, coded once in `tools/yt1/tt.py`:
- **Daily candle** = the trading day 18:00 → 17:00. "Candle 1" is the last one completed before the cash day,
  "candle 2" the one before it. **EQ** = the midpoint of candle 1's high and low.
- **Bias:** bullish if candle 1 closed above candle 2's high (`cont`), or ran candle 2's low and closed back above it
  without taking its high (`fail`). Bearish mirrors. Otherwise none. No bias across a contract roll.
- **Candle 2 closure** (reversal): a candle that trades below the previous candle's low and closes back above that low.
  **Candle 3 closure:** the previous candle is a swing low so far (lower low than the one before it, not undercut by
  this one) and this candle closes above the previous candle's body. Bearish mirrors.
- **CISD:** a close above the opening price of the first candle of the latest run of down-close candles, the first
  such close since that run. Its **protected low** = the lowest low from the start of that run through the CISD bar.
- **Unless a rule says otherwise:** entry at the CISD bar's close; stop 1 tick beyond the protected low (high); target
  2R; flat at the flat bar; one trade a day; "the morning" = signal bars closing after 08:30 and by 11:00 (his New York
  AM window); **neighbours = targets 1.5R and 3R.** Long side written, short mirrors.
- **Criterion:** the usual criterion of YT1 with the level counted over everything tried so far:
  p < 0.05 / 90 = 0.00056. Candidate = every criterion but that level, with p < 0.05. Under 100 trades = not enough data.

- **G1 — the daily bias on its own** *(R: a tester's rule, to see whether the bias carries anything by itself)*. Bias
  bullish → long at the 09:30 open, bearish → short; no stop; flat bar. R unit 0.1 × daily ATR.
  **Neighbours: `cont` days only; `fail` days only.**
- **G2 — candle 4 continuation** ("TTrades Fractal Model - Candle 4", https://www.youtube.com/watch?v=5fnFOh5YuM0).
  Daily gate: candle 2 is a swing low (lower low than the candle before it, not undercut by candle 1) and candle 1
  closed above candle 2's body *(R: "strong closure" = his candle 3 closure)*. Void once price trades below EQ after
  18:00. Trigger: the first 3-minute bullish CISD of the morning whose protected low is at or above EQ.
  **Neighbours: 5-minute and 1-minute trigger bars.**
- **G3 — EQ continuation day** ("Easy Daily Bias: A Mechanical Trading Framework",
  https://www.youtube.com/watch?v=-KKuZb5Z5aU). `cont` days only. Respect *(R)*: no clock-hour candle since 18:00 has
  closed below EQ. Trigger: the first 5-minute bullish CISD of the morning that closes above EQ.
  **Reported:** `pdh` = target candle 1's high instead of 2R, no trade if it is nearer than 1R.
- **G4 — Fractal Model day trade** ("TTrades Playbook, Fractal Model Fundamentals",
  https://www.youtube.com/watch?v=TNybDCtwBnc; "The Only Trading Strategy You Need For 2026",
  https://www.youtube.com/watch?v=9AL41xON3hA). Bias required. Hourly gate: the first clock-hour candle opening 06:00 …
  09:00 that is a bullish candle 2 or candle 3 closure with its low inside candle 1's range, and on `cont` days at or
  above EQ *(R: his point of interest reduced to "inside yesterday's range, in the defended half")*. After that hour
  closes: the first 5-minute bullish CISD confirms; **entry at the close of the second** (his continuation), bars
  closing by 11:30. **Reported:** `first` = entry at the first CISD; `retest` = limit at the opening price the second
  CISD closed through, resting 30 minutes.
- **G5 — 4-hour power of three** ("Trading The 4 Hour Power Of Three", https://www.youtube.com/watch?v=FAKWJ-1NlLE).
  Bias required. Gate: the 4-hour candle that has just closed (06:00–09:59 or 10:00–13:59) is a candle 2 closure in
  the bias direction. Trade the next 4-hour candle (10:00 or 14:00): the first 15-minute CISD in the bias direction on
  a bar that opens inside it *(R: "let the wick form, trade the body"; his shallow-wick judgement is not applied)*.
  Exit at that 4-hour candle's last bar or the flat bar. One trade per 4-hour candle.
- **G6 — scalping model** ("TTrades Scalping Model", https://www.youtube.com/watch?v=eywpZT3z6GQ). Bias required. Gate:
  a clock-hour candle opening 08:00 … 14:00 that is a candle 2 or candle 3 closure in the bias direction. In the next
  hour: one of its first two 15-minute candles is a candle 2 closure in that direction *(R)*; then the first 1-minute
  CISD in that direction after that 15-minute candle closes, from 09:30 on. Exit at the hour's last bar. One trade per
  hour, one position at a time.
- **G7 — Silver Bullet, no daily bias** ("ICT Silver Bullet Strategy - No Daily Bias | With Backtest!",
  https://www.youtube.com/watch?v=o0v4KQxZbpU). Range = the 09:00–09:59 high and low. Raid = the first 1-minute bar
  from 10:00 to trade beyond one side; trade against it. Confirmation (short): a 1-minute close below the latest
  3-bar swing low that was confirmed before the bar holding the raid's high. The other side raided first → no trade.
  Entry: limit at the near edge of the latest bearish 1-minute FVG between the raid's high and the confirmation bar
  *(R: he also uses breakers and order blocks)*; none → no trade; resting to 10:59. Stop beyond the raid's extreme.
  Target: the far side of the range. Stop to entry once 3R has traded. Flat bar *(R: he holds overnight)*.
  **Neighbours: limit at the gap's midpoint; at its far edge.**
