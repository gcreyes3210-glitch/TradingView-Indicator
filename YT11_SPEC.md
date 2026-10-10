# YT11 — trading 100+ times a day: the cost of it, whether the next minutes can be predicted, a frequency grid (G12) and eleven fixed rules (Q1–Q11), pre-registered 2026-10-09

Written before any YT11 code was run.

**The request.** "I see that some people place 100+ trades in one day. Look online and find strategies that you can
test to see if you can implement something like that."

**What was found** (`data/studies/yt1/research/M_hft_retail.md`, about 100 pages on how active retail traders do it;
`N_hft_quant.md`, 33 published sources read and 24 partly):
- No source states a complete mechanical rule together with 100+ trades a day and a record of results. The traders
  known to trade that often (pit-style scalpers, order-book traders) work by hand from the order book at exchange-member
  costs. The written guides that give numbers say 5 to 50 trades a day.
- The published evidence for index futures: once-a-day clock effects are worth 1.5 to 3 basis points before costs;
  the evidence for many trades a day is 0.04 to 0.9 basis points a trade. The house cost of one MNQ round trip
  (below) is 0.75 basis points at 20,000 and 0.50 at 30,000.
- So the batch has four parts: what trading that often costs here (Part 1); whether anything in the 1-minute bars
  predicts the next 1 to 30 minutes well enough to pay for a trade (Part 2); a grid of simple signals in which the
  number of trades a day is a dial from about 10 to 360 (Part 3); and the rules from the two notes that are stated
  well enough to code (Part 4).

**Disclosed.** The author has seen all of 2023–2026 for 130 rules and three grids, and knows that the only effect that
has held is continuation in the morning after the opening range breaks. The one earlier rule at this frequency, C17
(1-minute EMA pullback, 16,895 trades), lost 0.182 R a trade. Near relatives of Part 4 that failed before: VWR1 and
C15 (VWAP reversion and pullback), C13 and C19e (RSI reversion), IM1 (first half-hour predicts the last), RV (NQ / ES
ratio), ML1 (one classifier on opening features).

**Cost of a round trip, as always here:** 1 tick against each fill and $1 a side at one MNQ = 2 ticks + $2 = **$3.00 =
1.5 points = 6 ticks.** One hundred round trips a day cost $300 a day, about $75,000 a year. ORB v1.4 nets about
$2,850 a year.

Data, engine, house fills, R, look-ahead test and order of work as `YT1_SPEC.md`: code and in-sample results on bars
to 2022-12-31 only, frozen and stamped, then the full span once. Roll days are not traded. Times New York. "Out of
sample" = 2023-01-01 → 2026-10-07. Every result is reported with **trades per day** (trades ÷ sessions on which the
rule could trade), **gross** (before the $3.00) and **net**.

Shared definitions:
- **Session** = the regular session, 09:30 to the flat bar. **VWAP** = anchored at 09:30, Σ(hlc3 × volume) ÷ Σ volume
  on 1-minute bars, through the bar just closed. **VWAP sd** = √(Σ(volume × hlc3²) ÷ Σ volume − VWAP²), as
  `Aceflw_Levels.pine`.
- **s** = the standard deviation of the 390 most recent 1-minute close-to-close log returns of regular-session bars
  at or before the decision (returns inside a session only; the window runs back into earlier sessions).
- EMA, RSI, ADX, ATR, Bollinger: `tools/yt1/ind.py`, on the continuous 24-hour series of the stated timeframe.

# Part 1 — COST1, what the cost is next to the moves (description)

Per calendar year, regular session, MNQ: the median 1-minute high − low; the mean of |close(t + h) − close(t)| in
points for h = 1, 2, 3, 5, 10, 15, 30 minutes; that mean ÷ 1.5 points; the hit rate a coin-flip-sized bet over h
minutes needs to break even, 0.5 + 1.5 ÷ (2 × mean absolute move); and the dollars a year that 10, 50, 100 and 200
round trips a day cost. The same for MES with its own tick and point values (1.25 $ a tick, 5 $ a point: cost
2 ticks + $2 = 4.50 $ = 0.9 ES points). No verdict.

# Part 2 — PRED1, can the next few minutes be predicted from the bars?

- **Decisions:** closes of 1-minute bars every h minutes on the clock, from 10:30 until h minutes before the flat
  bar, for h = 1, 5, 15, 30. **Target:** the MNQ log return from that close to the close h minutes later ÷ (s × √h).
- **Inputs, all known at the decision** (returns ÷ (s × √window)): MNQ log returns over the last 1, 2, 5, 15, 30 and
  60 minutes; (close − VWAP) ÷ (close × s × √minutes since 09:30); the same distance from the session high so far
  and from the session low so far; ln(volume of the last 5 minutes ÷ mean 5-minute volume of the previous 60
  minutes); the ES log return minus the MNQ log return over the last 1 and the last 5 minutes, ÷ s; minutes since
  09:30 ÷ 390 and its square; (09:30 open − previous session's close) ÷ (close × s × √390).
- **Two models, fitted once on decisions to 2022-12-31, no tuning:** `ols` ordinary least squares with an intercept;
  `gbr` scikit-learn `HistGradientBoostingRegressor(max_iter=200, learning_rate=0.05, max_depth=3,
  min_samples_leaf=200, random_state=1)`. The fitted models are saved and stamped before any later bar is read.
- **Reported, in sample and out of sample, per model × h:** R² against a forecast of zero; correlation of forecast
  and outcome; share of decisions with the sign right; and two trades through the house fills (market at the
  decision close, on the forecast's side, out at the close h minutes later): `all` = every decision; `sel` = only
  when the forecast move, converted to points, is at least 1.5 (the cost). For each: trades a day, gross and net per
  trade, net per day, by year.
- **A model × h counts** if its `sel` trade, out of sample, has at least 100 trades, a positive mean net per day
  with p < 0.05 / 8 (one-sided bootstrap of the daily net over days with a decision, 10,000 resamples, seed 1) and
  3 of 4 calendar years net positive. Under 100 `sel` trades = "predicts nothing worth a trade".

# Part 3 — G12, the frequency grid (756 combinations)

**Decision:** the close of a 1-minute bar every k minutes on the clock, from the close of the 09:59 bar; the last
decision is the one whose exit is at or before the flat bar. A trade decided at bar t is closed at the close of the
bar k minutes later. No stop, no target. One position at a time by construction.

| Code | Choice | Levels |
|---|---|---|
| **G** | Signal: the side taken | `mom-L` the sign of close(t) − close(t − L) · `rev-L` the opposite · `es-L` the sign of (ES log return − MNQ log return) over the last L minutes (buy MNQ when it lags ES) · `esr-L` the opposite · `vw` long above VWAP, short below · `vwr` the opposite. L = 1, 5, 15, 30 minutes: 18 signals. A zero is no trade |
| **Z** | Strength needed | z ≥ 0, 1 or 2. `mom` / `rev`: z = \|L-minute log return\| ÷ (s × √L). `es` / `esr`: z = \|difference of the two L-minute log returns\| ÷ (s_d × √L), s_d = the standard deviation of the 1-minute difference over the same 390 bars as s. `vw` / `vwr`: z = \|close − VWAP\| ÷ VWAP sd |
| **K** | Holding time = time between decisions | 1, 2, 3, 5, 10, 15, 30 minutes |
| **E** | Entry | `mkt` at the decision bar's close, house fill · `lim` a limit at the decision bar's close price, live for the next 1-minute bar only, **filled only if that bar trades at least one tick through it**, at the limit price with no slippage on that fill and $1; if it is not filled there is no trade. The exit is always a house market fill. (This is the conservative convention for resting orders on bars; a real resting order also needs queue position, which bars cannot show.) |

- With `z ≥ 0` the grid trades 360, 180, 120, 72, 36, 24 and 12 times a day at k = 1, 2, 3, 5, 10, 15, 30.
- **Selection, on sessions to 2022-12-31 only.** Because 1.5 points was a far larger share of a move in 2019 than
  it is in 2026 (price 7,900 against 29,000), selection is by the quality of the signal, and the test is on money
  after costs. Three tiers by in-sample trades a day: **A** 100 or more, **B** 30 to under 100, **C** 10 to under
  30. In each tier: pick 1 = the highest t-statistic of the daily sum of gross P&L in units of 0.1 × ATR; pick 2 =
  the largest net dollars a day, if it is not pick 1 and not its mirror. Up to six picks. Frozen and stamped before
  later bars are run.
- **Out-of-sample test, run once. A pick passes** if: mean net per day > 0 with p < 0.05 / 6 (one-sided bootstrap of
  the daily net, 10,000 resamples, seed 1); 3 of 4 calendar years net positive; and its neighbours net positive (the
  next holding time down and up where they exist, and the adjacent strength level, same signal and entry).
  **Beats ORB v1.4** = a pass that out of sample has more net dollars and a larger net ÷ maximum drawdown (on daily
  P&L) than ORB v1.4 (`tools/yt1/cal_orb.py`) at one contract.
- **Reported whatever the picks do:** for every signal at `z ≥ 0`, `mkt`: gross points per trade by holding time in
  both periods, next to the 1.5-point cost; the share of the 756 combinations with positive gross and with positive
  net in each period; Spearman of gross per trade in sample against out of sample; for `lim` entries the share of
  orders filled and the gross per filled trade against the same signal's `mkt` trade; White's reality check on the
  out-of-sample net per day of all 756 (2,000 day resamples, seed 1) and the top 10 by out-of-sample net, labelled
  hindsight; and for the best out-of-sample gross combination in each tier, the round-trip cost in ticks at which it
  would break even.
- **Checks:** at least 2,000 `mkt` trades from six combinations replayed through `core.simulate`, to the cent; 30
  `lim` orders (filled and unfilled) checked by hand against the bars; the look-ahead test on six combinations.

# Part 4 — eleven fixed rules (usual order; usual criterion on the full span)

Criterion for each: at least 6 of 8 calendar years net positive, mean R ≥ +0.05, both halves non-negative, both
neighbours the same sign, p < 0.05 / 155 to pass and p < 0.05 for a candidate (one-sided bootstrap, 10,000 resamples,
seed 1), under 100 trades = not enough data. 1-minute MNQ bars unless stated. One position at a time. Long side
written; short mirrors. A rule with no stop uses 0.1 × daily ATR as its R unit. *(R = a reading the source leaves
open, fixed here.)*

- **Q1 — VWAP stop-and-reverse (N20, Zarattini and Aziz, published on QQQ; about 15 trades a day there).** At the
  close of the 09:30 bar: long if the close is above VWAP, short if below (equal: wait for the first close that
  differs). At every later 1-minute close on the other side of VWAP the position is closed and reversed at that
  close. Flat at the flat bar. Each leg is one trade with its own costs. No stop. Neighbours: decisions on 3-minute
  closes; on 5-minute closes.
- **Q2 — 1-minute VWAP with EMA 9 / 21, cross version (M14, AlgoTest).** At a close from 09:35 to 15:44: EMA(9)
  crosses above EMA(21) on that bar, the close is above VWAP and above both EMAs: buy at the close. Exit at the first
  close where EMA(9) crosses below EMA(21) or the close is below VWAP *(R: the source says to test its exits one at
  a time; these are its two price exits together)*, or the flat bar. No stop. Neighbours: exit on the EMA cross
  only; exit on the VWAP close only.
- **Q3 — 1-minute VWAP with EMA 9, pullback version (M14, Modern Scalping).** Up state at a close: close above VWAP
  and EMA(9) above EMA(21) *(R)*. Touch bar: its low is at or below EMA(9) and above EMA(21), with the up state at
  the previous close. Entry: the first bar from the touch bar to four bars after it *(R)* that closes above its open
  and above EMA(9) with the up state, no low at or below EMA(21) since the touch; buy at its close, 09:35 to 15:29.
  Stop 1 tick below the lowest low from the touch bar through the entry bar. Target 2R *(R: "one by two")*. Shorts
  mirrored *(R: the video is long only)*. Neighbours 1.5R and 3R. Reported: `long` only.
- **Q4 — EMA 9 / 21 cross with RSI and a volume surge, held three bars (M13, MetroTrade).** At a close in
  09:30–11:29 or 14:30–15:54 (the source's hours): EMA(9) crosses above EMA(21), RSI(14) above 50 and above its
  value one bar earlier, volume above 1.5 × the mean of the previous 20 bars *(R: "volume surge")*: buy at the
  close, exit at the close three bars later ("one to three bars of continuation"). No stop. Neighbours: one bar;
  five bars.
- **Q5 — Bollinger fade with an ADX filter, 5-minute bars (M15, CrossTrade; "3–8 trades per day").** Signal bar
  closing 09:50 to 15:25: ADX(14) at most 25; low at or below the lower band of Bollinger(20, 2); lower wick
  (min(open, close) − low) more than 1.5 × the body and the close above the low. Buy at the next bar's open. Stop
  1 × ATR(14) of 5-minute bars below the signal bar's low. Target the middle band's value at the signal bar's close
  *(R: fixed)*; no trade if that is not above the signal close. Exit at the close of the 15th bar after the entry
  bar if neither is hit. The source's "higher highs and higher lows over the last 20 bars" filter is not defined bar
  by bar and is left out *(R)*. Neighbours: band 2.5; ADX at most 20. Reported: `m1` the same rule on 1-minute bars;
  `noadx`.
- **Q6 — MNQ 5 / 30 / 200 EMA (M17, a TradingView script).** Set-up bar closing 09:30 to 15:44: close above EMA(5),
  EMA(30) and EMA(200). Buy stop 1 tick above its high, live for the next bar only *(R: "wait for the next candle to
  pass that level by 0.25")*. Stop 1 tick below the set-up bar's low. Target 3R. Short: close below all three; sell
  stop 1 tick below its low; stop 1 tick above its high *(R: the page's "300" read as 200)*. After any exit the next
  set-up bar is at least 5 bars later *(R: stands in for the page's blocks, which have no values)*. Neighbours 2R
  and 4R. Reported: `fresh` = only a set-up bar whose previous bar did not qualify on that side.
- **Q7 — momentum scalp with a tick bracket (M12a, El Trader Financiado).** 09:30–10:29. A bar closes above the
  session high so far (highs of earlier bars from 09:30) with volume above 1.5 × the mean of the previous 20 bars:
  buy at the close. Stop 6 ticks below the entry price, target 16 ticks above (the top of the source's 4–6 and
  8–16 ranges). "Strong delta" is left out (no order flow on most days). Neighbours: 4 / 8 ticks; 6 / 12 ticks.
  Reported: `x4` = 24 / 64 ticks.
- **Q8 — VWAP 2-sd reversion scalp with a tick bracket (M12b).** 11:00–13:59. A bar closes at or below VWAP − 2 ×
  VWAP sd and above its open *(R: "exhaustion signs")*: buy at the close. Stop 8 ticks below the bar's low. Target
  20 ticks above the entry price, or VWAP at the signal if nearer. Neighbours: 6-tick stop with a 10-tick target;
  2.5 sd. Reported: `x4` = stop 32 ticks below the low, target 80 ticks.
- **For Q7 and Q8, stated in advance:** 6 to 20 ticks is 1.5 to 5 points, smaller than a typical 1-minute bar of
  2026. A 1-minute bar that holds both the stop and the target counts as a stop (house rule), so these two rules
  are scored at their worst. Reported with them: the share of trades whose exit bar held both prices, and the result
  if every such trade had been a winner instead (the best case; the truth is between the two).
- **Q9 — the rest of the day predicts the last half-hour (N02, Baltussen and others; 2.72 basis points before costs
  in their equity futures).** At the close of the 15:29 bar: long if the close is above the previous regular
  session's close, short if below. Exit at the flat bar. Not on early-close days. No stop. Neighbours: decided at
  15:00; at 15:45. Reported: `big` = only when the move from the previous close is at least 0.5 × ATR.
- **Q10 — the overnight drift hour (N06, Boyarchenko and others, on ES; 1.48 basis points before costs).** Buy at the
  close of the 01:59 bar, sell at the close of the 02:59 bar, every trading day. No stop. Neighbours: 01:30–03:30;
  02:00–03:30. Reported: `eu` = 23:30–03:30 (N07); and the mean MNQ return of each of the 24 clock hours, in sample
  and on the full span (description).
- **Q11 — the lunch pattern (N11, Quantpedia, on SPY).** Short at the close of the 10:59 bar, out at the close of the
  11:59 bar; long there, out at the close of the 13:59 bar. Two trades a day, scored together. No stop. Neighbours:
  the long leg ending 12:59; the short leg starting 11:30. Reported: each leg alone.

**Read and not coded:** every hand method that works from the order book or the tape (M01–M03, M07, M10, M11, M12c);
resting-order systems that need a place in the queue (M04, N21; the `lim` entry of Part 3 is the bar version) and
methods that rely on simulator fills (M06); undisclosed or closed-source bots (M05, M09, M18, M21); rules whose
numbers are not given (M08's direction, M16, N24, M20); M19 (a VWAP-band reversal, the same family as VWR1, which
failed); the order-book and seconds-scale effects (N12–N17: the `es` signals of Part 3 are the 1-minute form of the
lead-lag); the cross-section-of-stocks effects (N04, N05, N10); a two-leg MNQ / ES pair (N23: the single-leg ratio
rule RV failed and two legs pay two round trips); families already tested (N01, N19, N22). N08's reversal-then-trend
by time scale is the `mom` / `rev` rows of Part 3; N18's models are Part 2.

**Outside the backtest, recorded before any result:** as the firms' own pages read on 2026-10-09 state it,
AquaFutures bans 100 or more trades a day; Tradeify and Funded Futures Family require over half of trades and profit
to come from holds longer than 10 seconds; Lucid flags accounts with half of profit from holds of 5 seconds or less;
Topstep prohibits "hundreds of rapid trades" and tight brackets that exploit simulator fills; Apex prohibits
high-frequency trading and, on the page read, any automation; My Funded Futures prohibits high-frequency trading. The
holds in this batch are 1 minute or longer, so the seconds rules are not the issue; the trade-count cap, the
automation bans and the firms' discretion are. A funded account may refuse a rule from this batch even if the
numbers were good.

Nothing here is adopted into the traded rule whatever the result.
