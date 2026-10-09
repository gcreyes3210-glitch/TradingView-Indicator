# YT1 — strategies taught on YouTube, pre-registered 2026-10-08 (written before any YT1 strategy code was run)

**What this is.** 53 trade rules and 13 published-claim checks collected from YouTube videos (sourcing notes with every
URL: `data/studies/yt1/research/*.md`). Rules already closed in `BACKTEST_LOG.md` were left out. Nothing is adopted from
this section; a rule that passes is a candidate for a shadow flag only.

**Data.** Databento MNQ 1-minute bars, 2019-06-03 → 2026-10-07 (ES 1-minute bars where a rule needs a second market).
Order-flow rules (family D) use the NQ 5-minute footprint and 1-minute delta, which exist only 09:30–11:35 on the days
ORB v1.4 traded (876 days to 2026-09-22): a selected sample, and reported as such.

**Engine.** `tools/yt1/core.py` (calibrated before this entry was written: ORB v1.4 rebuilt on it reproduces 877 of
orb_engine's 879 trades to the cent, the two others are 2020 circuit-breaker opens; Literature's ORB9-a reproduces
1,876 of 1,876 trades to the cent). One module per rule, `tools/yt1/s_<ID>.py`; claim checks `tools/yt1/k_<ID>.py`.

## Common rules (apply to every entry unless the entry says otherwise)
- **House fills.** 1 tick against every fill (market, stop, limit, target, time exit), $1 per side, $2 / point, one
  contract (scale-outs are fractions of one contract). A bar opening beyond a level fills at its open. After the fill
  bar, a bar touching both stop and target is a stop. On the fill bar of a resting order the path is open → nearer
  extreme → farther extreme → close. A market entry is at the close of the signal bar and nothing happens in that bar.
- **Bars.** N-minute bars are built from the 1-minute bars, aligned to the clock, stamped at their open. "A bar closing
  by 11:00" means its last minute is 10:59 or earlier. Times are New York.
- **Flat.** Every open trade is closed at the close of the 15:59 bar (early-close days: the bar ending 10 minutes before
  the halt, as v1.4). No order rests past it.
- **Days not traded.** Contract-roll days (the front contract changed since the previous cash day) and days without a
  daily ATR(14). Family C also skips the cash day after a roll (its indicators carry the roll jump).
- **One trade per day** unless the entry says otherwise. "First signal" means the first in time on either side.
- **Buffers.** "Beyond X" for a stop means 1 tick beyond X.
- **R targets.** Target = entry price ± k × |entry price − stop| before slippage, rounded to the tick.
- **FVG.** Bullish at bar k when low[k] > high[k−2]; the gap is (high[k−2], low[k]); candles 1, 2, 3 are k−2, k−1, k.
  Bearish mirror. Any size ≥ 1 tick. "Near edge" = the edge price reaches first on a return (bullish: low[k]).
- **R.** net ÷ (|fill − stop| × $2). A rule with no stop uses 0.1 × daily ATR(14) as its R unit (Literature's unit)
  unless the entry names another.
- **Readings.** Where a video leaves a step open, the reading used is marked *(R)*. Readings were fixed here, before
  any result.

## Criterion and order of work
- **Usual criterion** (each of the 53 trade rules, on 2019-06 → 2026-10): ≥ 6 of 8 calendar years net positive;
  ≥ +0.05 R per trade; both halves (2019–2022, 2023–2026) non-negative in R per trade; the sign of R per trade holding
  on both neighbours; and p < **0.05 / 53 = 0.00094** (one-sided bootstrap of mean R > 0, 10,000 resamples, seed 1).
  Fewer than 100 trades in the span = **not enough data**, no verdict.
- **Candidate** (logged, not adopted): everything above except the Bonferroni level, with p < 0.05. With 53 rules
  about 2–3 would reach p < 0.05 by luck alone, so a candidate is a lead, not a result.
- **Walk-forward.** Step 1: every rule is coded and run on bars cut at 2022-12-31 23:59 (asserted), and those results
  are written to `data/studies/yt1/is/` and committed before any 2023–2026 bar is read by any YT1 code. Step 2: the
  same code, unchanged, on the full span. A rule changed after step 1 for any reason other than a logged coding error
  is void. No parameter is tuned at either step; the two neighbours are fixed below.
- **Look-ahead test** (every rule, before step 2): the rule is re-run on bars cut at six random mid-session times; every
  trade that had exited five days before a cut must be identical to the full run's.
- **Anything that passes or is a candidate** is re-coded from this text by a second coder who has not seen the first
  code, and compared trade by trade; its daily P&L is set against ORB v1.4's (overlap, correlation, combined
  return-to-drawdown), because the log's earlier candidates turned out to be ORB again.
- **Claim checks** (K entries) reproduce a published probability with the video's own event definition; they have no
  pass / fail, the measured rate is reported next to the claimed one, in-sample first.

---
## Family A — ICT time models (7 rules)

### A01 — JadeCap Silver Bullet
Source: "Simple ICT Silver Bullet Strategy | 70% Win Rate", JadeCap, https://www.youtube.com/watch?v=_EQFJ_TLV58
- **Ranges:** Asia 20:00–23:59 (previous evening), London 02:00–04:59, the 09:00–09:59 hour. Each has a high and a low.
- **Sweep:** a level is swept at the first 1-minute bar that trades ≥ 1 tick beyond it, counted from 00:00 for Asia,
  05:00 for London, 10:00 for the 09:00 hour.
- **Direction** at any moment = against the most recently swept level (a high → short, a low → long); no level swept
  yet = no trade.
- **Signal:** 5-minute bars. The first FVG in the trade direction whose three bars all open at or after 10:00 and whose
  third bar closes by 11:00 *(R: an FVG pointing the other way is passed over)*.
- **Entry:** limit at the gap's near edge, resting until the 10:59 bar. **Stop:** beyond candle 1's extreme.
  **Target:** 2R.
- **Neighbours:** target 1.5R, 3R. **Reported:** `pm` = the same in 14:00–15:00.

### A02 — Casper 5-minute candle + 1-minute FVG break
Source: "Scalping Became Easy When I Realized This", Casper SMC, https://www.youtube.com/watch?v=liDi8vaNAjQ ;
"The Simplest 1-Minute Scalping Strategy For Beginners", https://www.youtube.com/watch?v=iGS7JvTfSzc
- **Range:** high / low of 09:30–09:34.
- **Signal:** 1-minute bars 09:35 → 10:59. A bullish FVG whose three bars are all 09:35 or later and at least one of
  which closes above the range high → long at the close of candle 3. Bearish mirror. First signal of the day.
- **Stop:** beyond the low (high) of the first of those three bars that closed outside the range. **Target:** 2R.
- **Neighbours:** 1.5R, 3R. **Reported:** `c1030` entries to 10:29; `bar2` stop beyond candle 2's extreme.

### A03 — Casper 30-minute range, sweep and FVG back inside
Source: "This ICT Strategy Works Everyday (Stupid Simple And Proven)", Casper SMC, https://www.youtube.com/watch?v=IjCFyPGlS88
- **Range:** high / low of 09:30–09:59. 5-minute bars from 10:00, signal bars closing by 11:00.
- **Signal (short):** after a 5-minute bar has traded above the range high, the first bearish FVG whose third bar
  closes below the range high and at least one of whose three bars traded above it *(R: "back into the range")*.
  Enter at the close of candle 3. Long mirror at the range low. First signal of the day.
- **Stop:** beyond the highest candle body (max of open, close) from the first sweep bar through candle 3
  (lowest body for longs). **Target:** 2R. **Neighbours:** 1.5R, 3R.

### A05 — Candle Range Theory on the 05:00–09:00 candle
Source: "The CRT Trading Strategy That Actually Works", Raghee Horner, https://www.youtube.com/watch?v=6-2WXJFyBhE
- **Range:** high / low of 05:00–08:59; Mid = their average.
- **Signal:** 5-minute bars from 09:30 closing by 12:00. Short at the close of the first bar with high > range high and
  close < range high; long mirror *(R: "moves outside and fails" = trades beyond and closes back inside)*. First signal
  of the day; skipped if the close is already past Mid.
- **Stop:** beyond the extreme since 09:30. **Exit:** half at Mid, half at the opposite boundary.
- **Neighbours:** all at Mid; all at the opposite boundary.
- **Reported:** `pdc` = shorts only below the previous cash close, longs only above (her optional filter).

### A09 — ICT Silver Bullet, first FVG in the hour with the midnight-open side rule
Source: "2023 ICT Mentorship - ICT Silver Bullet Time Based Trading Model", The Inner Circle Trader,
https://www.youtube.com/watch?v=tRq1hyGGtl4 ; the side rule and 3-minute chart from Mulham Trading,
https://www.youtube.com/watch?v=POyd5Quw0WY
- **Signal:** 3-minute bars. The first FVG whose three bars open at or after 10:00 and whose third closes by 11:00,
  counted only if bullish with its top below the midnight open (the 00:00 bar's open) or bearish with its bottom above.
- **Entry:** limit at the near edge, resting until 10:59. **Stop:** beyond candle 1's extreme.
  **Target:** 2R *(R: ICT's target is a discretionary liquidity level)*.
- **Neighbours:** 1.5R, 3R. **Reported:** `pm` 14:00–15:00; `nofilter` first FVG of either direction.

### A10 — First presented FVG after 09:30
Source: "ICT First Presented Fair Value Gap", South On Sunday, https://www.youtube.com/watch?v=RfYblXoAX_c ;
ICT, https://www.youtube.com/watch?v=y63zsrLCcCw
- **Signal:** 1-minute bars. The first FVG, either direction, whose three bars are 09:30 or later and whose third bar
  is 09:59 or earlier. Enter with the gap at the close of candle 3 ("as soon as the gap is confirmed, I'm in").
- **Stop:** beyond candle 1's extreme *(R: his "five points" is one example)*. **Exit:** no target, flat bar.
- **Neighbours:** the same on 2-minute and 3-minute bars.
- **Reported:** `ce` = limit at the gap's midpoint resting to 10:59, same stop, 2R (ICT's version); `2R` = immediate
  entry with a 2R target.

### A14 — Candle Range Theory, hourly
Source: "Candle Range Theory (CRT) Trading Model", Smart Risk, https://www.youtube.com/watch?v=lGwCPn0i6ic
- **Range candle:** each clock hour 08:00 … 13:00. **Sweep candle:** the next hour, when it trades beyond exactly one
  extreme of the range candle and closes back inside its range.
- **Signal:** in the 60 minutes after the sweep candle closes, the first 5-minute FVG against the sweep whose three
  bars open after that close. **Entry:** limit at the near edge, resting to the end of those 60 minutes.
- **Stop:** beyond the sweep candle's extreme. **Exit:** half at 1R, half at the range candle's opposite extreme; no
  trade if that extreme is nearer than 1R. At most 2 trades a day, one at a time.
- **Neighbours:** all at 1R; all at the opposite extreme.
- **Reported:** `mkt` = market at the sweep candle's close, same stop, target the opposite extreme.

---
## Family B — opening range, session range and level retests (9 rules)

### B01 — Quick Flip Scalper
Source: 'The "ONE CANDLE" Scalping Strategy I Will Use For Life', ProRealAlgos, https://www.youtube.com/watch?v=XFtayhPIdEs
- **Box:** high / low of 09:30–09:44. Traded only if box height ≥ 0.25 × daily ATR(14). Red opening candle (09:44
  close < 09:30 open) → longs below the box only; green → shorts above only; equal → none.
- **Signal:** 5-minute bars opening 09:45 … 10:55 whose body lies entirely outside the box on the trade side and which
  are a hammer (lower wick ≥ 2 × body, upper wick ≤ body, range ≥ 4 ticks) or a bullish engulfing (up bar after a
  down bar, close ≥ previous open, open ≤ previous close); mirror for shorts *(R: the pattern sizes)*.
- **Entry:** the next 5-minute bar's open. **Stop:** beyond the signal bar's extreme. **Target:** the far side of the
  box. First signal only.
- **Neighbours:** threshold 0.20, 0.30 × ATR.

### B03 — Casper 5-minute range, break and wick retest, midpoint stop
Source: "The 5 Minute Scalping Strategy (That Actually Works)", Casper SMC, https://www.youtube.com/watch?v=nBOLIrNX_PU
- **Range:** the 09:30 5-minute bar. **Break:** the first later 5-minute close outside it sets the side for the day.
- **Signal:** a later 5-minute bar that trades back to the broken edge (low ≤ range high for longs) and closes outside
  it → enter at its close. A close back inside the range before that cancels the day. Signal bars close by 11:00.
- **Stop:** beyond the range midpoint. **Target:** 2R. **Neighbours:** 1.5R, 3R. **Reported:** `c1300` signals to 13:00.

### B04 — Jooviers Gems London box
Source: "How I'd Make $250/Day Trading If I Had To Start Over", Jooviers Gems (transcript
https://sozai.app/transcript/make-250-day-trading-start-over/); coded by Eddy Pips Trading,
https://www.youtube.com/watch?v=8Lhfo2urf58
- **Box:** high / low of 04:00–08:59; void if 09:00–09:29 trades outside it.
- **Signal:** the first 5-minute close outside the box from 09:30, closing by 11:00 → enter at that close.
- **Stop:** beyond the breakout bar's opposite extreme. **Target:** 2R.
- **Neighbours:** box from 03:00, from 05:00.

### B05 — Scarface first-candle break and retest (rules from ports; his own videos could not be read)
Source: 'My Simple 5 Minute "First Candle" Scalping Strategy', Scarface Trades, https://www.youtube.com/watch?v=FEmD-hK1-yU
- **Range:** 09:30–09:34. 1-minute bars. The first close outside the range (09:35 or later) sets the side.
  **Zone** = the last opposite-colour 1-minute bar (09:30 or later) before that breakout bar.
- **Entry:** limit at the broken range edge, resting from the bar after the breakout to 10:59.
- **Stop:** beyond the zone bar's extreme; if that is not beyond the entry, the breakout bar's; else no trade.
  **Target:** 2R. **Neighbours:** 1.5R, 3R.

### B06 — Pre-market high / low break and retest (playbook attributed to Scarface Trades; no video)
Source: https://www.tradezella.com/playbooks/break-retest-playbook
- As B05 with the level = the 04:00–09:29 high / low and the breakout = the first 1-minute close beyond it from 09:30.
  **Neighbours:** 1.5R, 3R.

### B07 — DR / IDR defining range, trade the confirmation
Source: "How to Trade DR BASICS - DR IDR Trading Strategy Backtest (Part 1)", TheMas7er,
https://www.youtube.com/watch?v=gejIU96PFKY ; rule text from LuxAlgo / TradingView descriptions
- **DR:** high / low of 09:30–10:29. **Signal:** the first 5-minute close beyond the DR, on bars opening 10:30 or later
  and closing by 15:00 → enter at that close.
- **Stop:** beyond the opposite DR extreme (the rule's own invalidation). **Exit:** flat bar.
- **Neighbours:** DR ending 10:14, ending 10:44.
- **Reported:** `port` = stop 0.5 × IDR height beyond the opposite IDR side and target 0.5 × IDR height beyond the
  near IDR side (IDR = highest / lowest 5-minute body in the window), the "DR/IDR Break .5 TP" script.

### B08 — edgeful initial-balance retracement entry
Source: "NQ initial balance (IB) trading strategy backed by edgeful", https://www.youtube.com/watch?v=x-R4VxV-7K4
- **IB:** 09:30–10:29, height W. Long set-up: the IB low was set before the IB high, the 10:29 close is in the top
  quarter of the IB, and it is above the 09:30 open. Short mirror. Same-minute extremes = no trade.
- **Entry:** limit one quarter of W back from the IB high, resting 10:30 → 14:59, cancelled if the target trades first.
- **Stop:** beyond the IB midpoint. **Target:** IB high + 0.2 W.
- **Neighbours:** target the IB high; IB high + 0.5 W.
- **Reported:** `opt2` = limit at the midpoint, stop beyond the IB low, same target.

### B09 — IB75 (Dan Cooke)
Source: "How Simple Trading Made Me $30K in Payouts", Dan Cooke, https://www.youtube.com/watch?v=7JZcwahgGgY
- **Set-up:** the 10:29 close lies in the quarter of the IB next to the extreme that was set first.
- **Entry:** limit one quarter of W from that extreme, resting 10:30 → 14:59. **Target:** that extreme.
  **Stop:** beyond the IB midpoint *(R: from the blog's one example)*.
- **Filter:** no trade if the 18:00-anchored VWAP at 10:29 lies between entry and target.
- **Neighbours:** stop at 0.40 W, 0.60 W from that extreme. **Reported:** `novwap`.

### B14 — IB breakout with VWAP side and a 1.5 × IB target (TradingView script by samjNQ; no video)
Source: https://fr.tradingview.com/script/yc6JyC1T-Initial-Balance-Breakout-samjNQ-v3/
- **Signal:** 5-minute bars opening 10:30 … 14:25. Long at the first close above the IB high that is also above the
  09:30-anchored VWAP; short mirror. One trade per direction per day, one at a time.
- **Stop:** beyond the opposite IB level. **Target:** 1.5 W beyond the broken level.
- **Neighbours:** 1.0 W, 2.0 W.

---
## Family C — indicator rules (19 rules)
**Common frame** *(R: the videos test 30-minute forex or gold and say "any timeframe")*: 5-minute MNQ bars, indicators
on the continuous 24-hour series; signals on bars closing 09:35 → 15:00; entry at the signal bar's close; one position
at a time, any number a day; long and short mirrored. **Swing stop** = beyond the lowest low (highest high) of the last
10 bars including the signal bar. **Neighbours** = the same rule on 3-minute and 15-minute bars, unless stated.

- **C01 — MACD + 200 EMA.** "I risked MACD Trading Strategy 100 TIMES", TRADING RUSH,
  https://www.youtube.com/watch?v=nmffSjdZbWQ. Long: close > EMA200 and MACD(12, 26, 9) crosses above its signal with
  both lines below zero. Swing stop, 1.5R.
- **C02 — 8-55 EMA pullback on NQ (long only, as the script ships).** TradersPost,
  https://www.youtube.com/watch?v=61mYTkmM8XU ; code
  https://github.com/TradersPost/pinescript/blob/master/strategies/8-55-EMA-Crossover-NQ-Futures-Strategy.pinescript.
  Bullish = EMA55 ≥ EMA165 and EMA8 > EMA55. Long when bullish, a low was below EMA55 within the last 6 bars and the
  close is above EMA8; signal bars opening 10:00 … 15:50. Exit: trailing stop at the highest (bar high × 0.9925) since
  entry, or a bar that turns bearish (EMA55 ≤ EMA165 and EMA8 < EMA55), or the flat bar *(R: the script holds
  overnight; a flat-by-close account cannot)*. No initial stop.
- **C03 — Triple Supertrend + Stochastic RSI + 200 EMA.** TradeSmart re-test,
  https://www.youtube.com/watch?v=xAi5qzVn3eM. Supertrend (12, 3), (11, 2), (10, 1); Stochastic RSI (3, 3, 14, 14).
  Long: close > EMA200, %K crosses above %D with the previous %K below 20, at least two Supertrends up. Stop: the
  second Supertrend line below the close, counting from the close. 1.5R.
- **C04 — Donchian(20) + 200 EMA.** "TESTING Best Trend Following Strategy Ever 100 TIMES", TRADING RUSH,
  https://www.youtube.com/watch?v=icYe2SS3-4M. Long: the upper band rises on this bar, the latest band move before it
  was the lower band falling, close > EMA200. Stop: beyond the lower band. 1.5R.
- **C05 — Supertrend(10, 3) flip + 200 EMA.** TRADING RUSH,
  https://tradingrush.net/supertrend-indicator-tested-100-times-so-you-dont-have-to/. Long: Supertrend turns up on
  this bar and close > EMA200. Stop: the Supertrend line. 1.5R.
- **C06 — EMA 8 / 14 / 50 + Stochastic RSI + ATR bracket.** "76% Win Rate ... 3 EMA + Stochastic RSI + ATR", Trade Pro,
  https://www.youtube.com/watch?v=7NM7bR2mL7U. Long: EMA8 > EMA14 > EMA50 and %K crosses above %D. Stop 3 × ATR(14),
  target 2 × ATR(14) from entry.
- **C07 — MACD + Parabolic SAR + 200 EMA.** TradeSmart re-test, https://www.youtube.com/watch?v=4uyPRdXPQ8w. Long:
  MACD histogram crosses above zero, close > EMA200, SAR (0.02, 0.02, 0.2) below the bar. Stop: the SAR value. Target
  1.5R; also exits at the close of a bar giving the opposite signal. **Neighbours: 1R and 2R** (the two written
  versions disagree between them).
- **C08 — Bollinger upper-band breakout + 200 MA (long only, as tested).** "I TESTED Highest Win Rate Strategy 200
  TIMES", TRADING RUSH, https://tradingrush.net/i-tested-highest-win-rate-strategy-200-times-unbelievable/. Long: close
  > SMA200, close crosses above the upper band (20, 2), and the previous trading day closed above its 9-day EMA.
  Swing stop, 1.5R.
- **C09 — Stochastic + RSI + MACD.** "Most Effective Stochastic + RSI + MACD Trading Strategy", Data Trader,
  https://www.youtube.com/watch?v=hh3BKTFE1dc. Stochastic (14, 3, 3) with both lines under 20 arms a long; either line
  over 80 disarms it. While armed: enter at the first bar with RSI(14) > 50 and MACD > signal where one of those two
  became true on that bar. Swing stop, 1.5R.
- **C10 — 9 / 20 EMA "Bone Zone" first pullback (5-minute only; stated for stocks).** Kunal Desai,
  https://www.youtube.com/watch?v=O5ejsxNKC2c. Trend up *(R)* = EMA9 > EMA20 after at least 3 consecutive bars with
  low > EMA9. First pullback = the first later bar with low ≤ EMA9. Enter at the close of the first up bar, from that
  bar on, that closes at or above EMA20, provided no bar since the touch closed below EMA20 (that ends the set-up for
  the day). Signal bars closing 09:45 → 11:00. Stop: beyond the pullback's low. Target 3R. One per direction per day.
  **Neighbours: 2R, 4R.**
- **C12 — TTM Squeeze fire (rules from a written guide; the Simpler Trading video was not readable).**
  https://www.youtube.com/watch?v=inFv7x77bxQ. **15-minute bars.** Squeeze on = Bollinger (20, 2) inside Keltner
  (20, 1.5 × ATR20). Fire = the first squeeze-off bar after ≥ 6 on bars. Momentum = 20-bar linear regression of close
  − average(midpoint of the 20-bar high / low, SMA20). Long: momentum > 0 and rising, close > SMA20. Stop: beyond the
  squeeze run's low. Exit: the first bar whose momentum falls, or the flat bar. Signal bars closing 09:45 → 15:00.
  **Neighbours: 10-minute, 30-minute bars.**
- **C13 — Connors RSI + 200 MA.** "I took 200 Trades with Faster RSI", TRADING RUSH,
  https://tradingrush.net/i-tested-crsi-trading-strategy-200-times/. CRSI (3, 2, 100). Long: close > SMA200 and CRSI
  crosses back above 10; short: close < SMA200 and CRSI crosses below 90. Swing stop, 1.5R.
- **C15 — VWAP trend-day first pullback (written guides; no video).**
  https://affordableindicators.com/articles/vwap-trading-strategy-futures/. VWAP anchored 09:30 with its
  volume-weighted standard deviation. Run = 10 consecutive 5-minute closes above VWAP. First pullback = the first later
  bar with low ≤ VWAP + 4 ticks. Enter at the close of the first bar, among that bar and the next three, that closes
  above VWAP and above its open; a close below VWAP first ends the set-up. Stop: the pullback's low − 0.5 × ATR(14).
  Exit: half at the farther of VWAP + 1 sd and 1R, half at the farther of VWAP + 2 sd and 2R. One per direction per
  day. **Neighbours: run of 8, of 12.**
- **C17 — NQ 1-minute 9 / 20 / 50 EMA pullback (TradingView script; no video).**
  https://it.tradingview.com/script/GoDPj2pd-NQ-EMA-Pullback-Strategy-1min. **1-minute bars**, signals closing
  09:45–11:30 and 13:30–15:30. Trend up: EMA9 > EMA20 > EMA50 and close > EMA50. Touch: a bar with low ≤ EMA20. Enter
  at the close of the first up bar closing above EMA9 within 5 bars of the touch with the trend intact throughout.
  Stop: the nearer of beyond the low since the touch and beyond EMA50. Target 2R. **Neighbours: 1.5R, 3R.**
- **C19a–e — TRADING RUSH single triggers** ("I Tested 7000 TRADES with 38 Trading Strategies",
  https://tradingrush.net/i-tested-7000-trades-with-38-trading-strategies/), each with close > EMA200, swing stop, 1.5R,
  mirrored for shorts *(R: the article is long-only on gold)*:
  - **C19a Ichimoku:** conversion (9) crosses above base (26), close above the cloud.
  - **C19b Keltner:** a bar that opens and closes above the upper Keltner (20, 2 × ATR10) after one that did not.
  - **C19c DMI:** +DI(14) crosses above −DI(14).
  - **C19d Stochastic:** %K (14, 3, 3) crosses above %D with both under 20.
  - **C19e RSI:** RSI(14) crosses back above 30.

---
## Family D — order flow (3 rules, on the 09:30–11:35 footprint sample)
**Common.** NQ 5-minute footprint bars opening 09:30 … 11:25. Buy imbalance at price p: buy[p] ≥ 3 × sell[p − 1 tick]
and buy[p] ≥ 10 contracts; sell imbalance mirror *(R: the 10-contract floor; videos quote ES sizes)*. Trades are filled
on MNQ 1-minute bars at the footprint's prices. One position at a time.

- **D03 — Stacked-imbalance pullback.** "Step 5. Finding Entry Points Using Order Flow", ATAS,
  https://www.youtube.com/watch?v=_iaRFHcy0Nc. Signal bar: an up bar with three or more buy imbalances on consecutive
  prices, upper wick ≤ 25 % of its range, positive delta. Entry: limit 1 tick above the top of the highest such stack,
  resting to 11:59. Stop: 2 ticks below the stack's bottom. Target 2R *(R: the video gives no stop or target)*. Mirror.
  **Neighbours: ratio 2.5, 4.**
- **D05 — Absorption candle, POC in the wick, delta flip, at a level.** "How I Time Reversals Using Footprint
  Absorption", Thraxx, https://www.youtube.com/watch?v=k41nIqVZaTg. Long: the bar's low is within 0.05 × daily ATR of
  (or through) the previous day's RTH low or the overnight low; the bar's highest-volume price is below its body; its
  delta is positive and the previous bar's negative. Entry: limit 1 point above that price, resting 15 minutes. Stop:
  beyond the bar's low. Target 2R. Mirror at the highs. **Neighbours: 0.025, 0.10 × ATR.** **Reported:** `nolevel`.
- **D06 — Trapped traders.** "The ONLY Order Flow Trading Guide You'll Ever Need", Trader Dale,
  https://www.youtube.com/watch?v=o3nfhz_M9j0. Bar N has a buy imbalance in its top 3 price rows; bar N+1 closes below
  the lowest such imbalance price → short at that close. Stop: beyond the higher of the two bars' highs. Target 2R.
  Mirror. *(R: Dale uses it only at his own levels; tested here on its own.)* **Neighbours: top 2, top 4 rows.**

---
## Family E — statistics and calendar (15 rules)

- **E01 — NQ Stats Hour Stats, fade the first breach.** https://youtu.be/aQzDN7jXXyc ; https://nqstats.com/hour_stats.html.
  Hours 09:00 … 15:00 that open strictly inside the previous hour's range. Sell limit 1 tick above the previous
  hour's high and buy limit 1 tick below its low, resting for the hour's first 20 minutes; the first to fill is the
  trade; the level must be ≥ 0.10 % of price from the hour's open *(R: his "about 20 points")*. Target: the hour's
  open. No stop (the study has none); exit at the close of the hour's last bar. R unit = entry to the hour's open. One
  per hour. **Neighbours: 0.05 %, 0.15 %.** **Reported:** `stop1` = a stop the same distance beyond the entry.
- **E02 — NQ Stats IB breaks, trade the bias** *(R: the study gives no entry)*. https://youtu.be/24P7rsb9P_8. At the
  10:29 close: long if the close is above the IB midpoint and the IB low was set before the high; short mirror.
  Target: 1 tick beyond the IB high. Stop: beyond the IB low. **Neighbours: IB ending 10:14, 10:44.**
- **E04 — NQ Stats Noon Curve** *(R: entry)*. https://youtu.be/Gpg23dwy2Tk. Q1 = 08:00–09:59, Q2 = 10:00–11:59. At the
  11:59 close: long if Q2 traded above Q1's high and not below Q1's low; short mirror. Stop: beyond Q2's low. No
  target. **Neighbours: decision at 11:29, at 12:29.**
- **E05 — NQ Stats ALN sessions** *(R: entry)*. https://youtu.be/zamNJBcD77c. Asia 20:00–01:59, London 02:00–07:59. At
  the 07:59 close: if London's high is above Asia's and London's low is inside Asia's range → long, target 1 tick
  beyond London's high, stop beyond London's low; the mirror pattern → short. **Neighbours: entry at the 08:29 close,
  at the 09:29 close** (no trade if target or stop traded first).
- **E06 — NQ Stats AM TBR, fade toward the 08:00 open.** https://youtu.be/xlfoh4FoBP0. SD = 20-day sample standard
  deviation of prior sessions' % change, reading fixed by K-E06. After the first touch of the 08:00 open ± 0.25 SD
  between 08:00 and 09:59: limit at ± 0.44 SD on that side, resting to 09:59. Target: the 08:00 open. Stop: beyond
  ± 1.0 SD. Exit at the 11:59 close. **Neighbours: entry at 0.35, 0.55 SD.** **Reported:** `atlevel` entry at 0.25 SD.
- **E08 — Outside-open reversal (edgeful; stated on RTY).** https://www.youtube.com/watch?v=OC02PShWJ8I. The 09:30 open
  is above the previous RTH high by ≥ 0.05 × daily ATR → short at the 09:30 open; target that high; stop half the
  target distance above the entry. Mirror below the previous low. **Neighbours: stop one third of, equal to, the
  target distance.**
- **E09 — Noise-area intraday momentum.** Zarattini, Aziz, Barbon, "Beat the Market"; "Intraday Momentum Trading
  Strategy Explained", WaveLabs, https://www.youtube.com/watch?v=NEE_jHYgCx8. sigma(t) = 14-day average of
  |close(t) ÷ 09:30 open − 1| at the same minute. Upper = max(09:30 open, previous close) × (1 + sigma), lower mirror.
  Decisions only at the closes ending HH:00 and HH:30, 10:00 → 15:30: flat and above the upper → long; long and below
  max(upper, 09:30 VWAP) → out (and short if also below the lower). Mirror. Each position is one trade.
  **Neighbours: 7, 28 days.** **Reported:** `opp` = stop only at the opposite boundary.
- **E10a — First hour continuation.** edgeful, https://www.youtube.com/watch?v=CvROXyEI19A. At the 10:29 close: long
  if above the 09:30 open, short if below. No stop, flat bar. **Neighbours: 09:59, 10:59.**
- **E10b — 15:00 continuation.** edgeful, https://www.youtube.com/watch?v=lypEidePlzw. At the 14:59 close: long if
  above the 09:30 open and above the middle of the day's range so far; short mirror. Stop: beyond the 09:30 open.
  **Neighbours: 14:29, 15:29.**
- **E11 — Larry Williams open ± prior range.** "Larry Williams Momentum Intraday Breakout Strategy", StatOasis,
  https://www.youtube.com/watch?v=JbmD7sFqRXI ; 0.25 factor and bracket from WH SelfInvest. W = previous RTH range.
  From the 09:30 bar's close: buy stop at the 09:30 open + 0.25 W, sell stop at − 0.25 W, resting to 15:00; the first
  to fill only. Stop and target 0.5 W from the entry. **Neighbours: 0.20, 0.30.** **Reported:** `lw1` = ± 1.0 W, no
  stop, exit 15:00, no Monday longs, no Monday / Friday shorts (the video's crude-oil version).
- **E12 — Larry Williams Oops (long only, end-of-day exit, as tested in the video).** StatOasis,
  https://www.youtube.com/watch?v=7Pv_eDxXWxI. The 09:30 open is below the previous RTH low → buy stop at that low
  from the 09:30 bar's close to 15:00. No stop. **Neighbours: gap ≥ 0.05, ≥ 0.10 × daily ATR.**
  **Reported:** `both` with the short mirror.
- **E13 — Crabel stretch after a 2-day narrow range.** "TOBY CRABEL - SECRET Trading Strategies", Jack Corsellis,
  https://www.youtube.com/watch?v=Etak6NOCXYU. RTH days. Set-up: the last two days' combined range is the narrowest
  two-day range of the last 20 days. Stretch = 10-day average of min(open − low, high − open). From the 09:30 bar's
  close: buy stop at the open + stretch, sell stop at − stretch, to 15:00; the first to fill is the trade and the
  other level is its stop. 60 minutes after the fill the stop moves to the entry price *(R)*.
  **Neighbours: 0.75, 1.25 × stretch.** **Reported:** `nr3` (three-day range, 20 days).
- **E15 — Camarilla pivots (stated on QQQ).** "Day Trading With Accuracy: Camarilla Pivots", Xtrades,
  https://www.youtube.com/watch?v=vZfzVRrUCbg. From the previous RTH high H, low L, close C, W = H − L: R3 / S3 =
  C ± 1.1 W ÷ 4, R4 / S4 = C ± 1.1 W ÷ 2, R5 = (H ÷ L) × C, S5 = C − (R5 − C). 5-minute bars, signals closing by 15:00,
  each set-up once a day, one position at a time: (1) a bar with low ≤ S3 closing above S3 → long, stop S4, target R3;
  (2) first close above R4 → long, stop R3, target R5; (3) first close below S4 → short, stop S3, target S5; (4) a bar
  with high ≥ R3 closing below R3 → short, stop R4, target S3. One test, the four pooled.
  **Neighbours: 3-minute, 15-minute bars.**
- **E19 — Turnaround Tuesday, the cash session only** *(R: the video holds from Monday's close for days)*. Quantified
  Strategies, https://www.youtube.com/watch?v=SjAVW7jgwuQ. Monday's RTH close below Friday's → long Tuesday's 09:30
  open to the flat bar. No stop. **Neighbours: Monday's close below Friday's low; any down day → next day.**
- **E20 — Turn of the month, the cash sessions only** *(R)*. Quantified Strategies,
  https://www.youtube.com/watch?v=AX8g8iy1CJE. Long 09:30 open → flat bar on the last 4 trading days of a month and
  the first 3 of the next. No stop. **Neighbours: last 3 + first 2; last 5 + first 4.**

---
## Claim checks (13; measured rate next to the published one, in-sample first)
- **K-A12 — ICT opening-range gap.** https://www.youtube.com/watch?v=uIvlS330qrA. Gap = the previous day's 16:14 close
  to the 09:30 open. Share of days on which the gap's midpoint trades between 09:30 and 10:00, and by 16:00, by gap
  size (20–75, 75–120, > 120 points, and the same as a % of price at 2025 levels). Claimed: about 70 %.
- **K-B07 — DR rule.** After the first 5-minute close beyond the 09:30–10:29 range, share of days on which the opposite
  extreme is not traded through by 16:00. Claimed: 80 %. Also for the body (IDR) version.
- **K-E01 — Hour Stats.** Share of first breaches of the previous hour's high / low after which the hour's open trades
  before the hour ends; by hour 08–15 and by 20-minute segment. Claimed: 61.5 % overall, 13:00 first segment 71 %,
  09:00 first segment 87.4 %.
- **K-E02 — IB breaks.** IB high / low broken by 12:00 and by 16:00, unfiltered and by the two conditions. Claimed:
  both bullish conditions → high by noon 74.0 %, by close 84.0 %; both bearish → low 67.9 %, 78.0 %; either side by
  close 96.1 %.
- **K-E04 — Noon Curve.** 08:00–16:00 high and low on opposite sides of noon (claimed 72.81 %); and, without the
  video's conditioning on that outcome, P(afternoon makes the high | Q2 broke Q1's high only) and the low mirror
  (claimed 82.12 %, 72.42 % conditional).
- **K-E05 — ALN.** Pattern frequencies and the share of New York sessions (08:00–16:00) breaking London's high / low by
  pattern. Claimed: P3 80.8 % / 65.5 %, P4 68.6 % / 75.0 %, P1 71.5 % / 70.4 %.
- **K-E06 — AM TBR.** Two readings of the SD (trading-day close-to-close % change; 08:00 → 12:00 % change). The reading
  whose in-sample touch rate of ± 0.25 SD between 08:00 and 12:00 is nearer the published 98.9 % is the one E06 uses.
  Reported: touch rate, reversion to the 08:00 open by 12:00 overall and by touch half-hour. Claimed: 74 %; 08:xx 79 %.
- **K-E07 — RTH breaks.** https://youtu.be/6Ud_wOmO-Tk. Open above the previous RTH high: closes above it (claimed
  69.9 %), does not trade the previous RTH low (88.1 %). Open below: 59.5 %, 90.4 %. Open inside: neither side 17.7 %,
  one 74.0 %, both 8.3 %.
- **K-E10 — First hour and 15:00.** Green first hour → the day closes above its open (claimed 76–79 %), and the part a
  trade can take: P(16:00 close > 10:30 price | green first hour). Same for red, and for the 15:00 rule (claimed
  about 90 % on YM / ES).
- **K-E16 — News-candle data high / low.** "The ONLY 5 Nasdaq Setups You Should Be Taking", EzTrades,
  https://www.youtube.com/watch?v=KYxaAlEHPs0. 08:30 releases (CPI, NFP, PPI, retail sales, GDP, PCE): the 08:30
  5-minute bar's high and low; after one is traded through, share of days on which the other is traded through by
  16:00. Claimed: about 85 %.
- **K-D07 — Unfinished auctions** (Trader Dale). 5-minute footprint bars that set a new session high: share whose high
  is traded through by 11:35, split by unfinished (both buy and sell volume at the high price) and finished (no sell
  volume there). Low mirror.
- **K-D15 — Exhaustion prints** (Orderflows, https://www.youtube.com/watch?v=vCeSd0xc3RU). New-session-high bars whose
  total volume at the high price is ≤ 9 contracts against the rest: share whose high holds for the next six bars.
- **K-D08 — Delta divergence** (Trader Dale, https://www.youtube.com/watch?v=W4LfdqGupAs). New-session-high up bars
  with negative delta against the rest: mean move over the next six bars in units of the bar-range average.

## Found and not coded (with the reason)
Turtle Soup in the macro windows (range and "equal highs" undefined, fixed point sizes); Turtle Soup with CISD, TJR's
2026 model, the Asian-range "Golden Bullet", ICT Unicorn, TTrades' Silver Bullet (each is the sweep → structure shift →
FVG shape the log closed as AMD / OB / OTE, with a discretionary bias or target); New Day Opening Gap (no entry or
stop); JJ Simon's Fair Value Theory, Trade with Pat, QuantCrawler's ORB (timeframe or parameters not stated); UT Bot +
STC, EMA 9 / 21 + VWAP, the 8 / 13 EMA NQ script (settings or exits missing, fixed-point targets); TradingLab's
absorption model, Fabio Valentini's and Carmine Rosato's LVN models, Trader Yush's value-area fade, Axia's false break
(need individual trade sizes, an order book, or a ladder read the 5-minute footprint cannot give; the value-area fade
is also close to the tested VP fade); Trader Dale's volume-accumulation set-ups, Forrest Knight's profile edges,
opening types, naked POC, single prints (no mechanical definition in any source); StatOasis' 21,287-ORB study (filter
formulas not stated); the multi-day holds (Monday 04:00 → Wednesday 14:00, three lower closes overnight) except as the
cash-session legs in E19 / E20; the macro-window tag on the logged IFVG and AMD trades; the remaining 33 TRADING RUSH
single triggers.
