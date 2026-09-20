# ICT SMT + IFVG in HTF FVG (Pine Script v5)

`ICT_SMT_IFVG.pine` is the full indicator. Paste it into the TradingView Pine editor and add it to the chart.

## What changed in this version

| Feature | Input group | Where in the script |
|---|---|---|
| Stop loss (Sweep High/Low or IFVG High/Low), TP by fixed RR and/or HTF swing, entry/SL/TP lines that follow price and mark hits | `10 · Risk` | `f_onSignal()` (risk module) and the "trade plans" loop in `MAIN` |
| Position sizing: `contracts = Account risk / (stop distance in points x point value)`, shown in the ▲/▼ tooltip, the plan label and the "Last position" table row | `10 · Risk` | `f_onSignal()` |
| SMT label shapes on/off, SMT label size, Buy/Sell mark size | `0 · Display & debug` | `method draw()` and `f_onSignal()` |
| Higher-timeframe SMTs and signals on lower charts (e.g. 3m BUY and 15m SMT on a 1m chart), tagged with their timeframe | `9 · Multi-timeframe feeds` | `FEEDS` section, `f_runEngine()` |
| HTF FVG boxes anchored on the historical candle where the 3-candle gap formed, extend-with-price or fixed width | `2 · HTF FVG` | `f_addHtf()` and section A of `MAIN` |

## 1. Stop loss / take profit

* `Stop loss mode`
  * **Sweep High/Low**: the chart market's extreme of the SMT sweep leg. The engine tracks it in `SMTSetup.sweepExt` (lowest low for a bullish setup, highest high for a bearish one, updated every feed bar until the signal fires).
  * **IFVG High/Low**: bottom of the IFVG box for a long, top for a short.
  * `Stop loss buffer (ticks)` is added beyond the level.
* `Take profit mode`
  * **Fixed RR**: TP1 and TP2 at `entry ± risk × RR` (TP2 RR = 0 disables TP2).
  * **HTF swing**: `f_swingTarget()` picks the nearest unswept opposing liquidity beyond the entry from the engine's reference pool (HTF swing, PDH/PDL, Asia, London), then a feed swing, then the last HTF pivot.
  * **Fixed RR + HTF swing** draws all of them.
* Entry is the close of the signal candle. The gray dashed line is the entry, red is the stop, green the RR targets, blue the swing target. The plan label at the right end shows the status (`OPEN`, `TP1 ✓`, `STOPPED`, `DONE`, `EXPIRED`). Lines stop extending once the plan closes; the oldest plans are deleted past `Trade plans kept on the chart`.

## 2. Position sizing

```
risk per contract = |entry - stop| (points) × Point value ($)
contracts         = floor(Account risk / risk per contract)
```

* `Account risk ($)` and `Point value ($ per 1.0 point per contract)` are the two inputs (MNQ 2, NQ 20, MES 5, ES 50).
* `Use the symbol's own point value` swaps in `syminfo.pointvalue`.
* If one contract already risks more than the account risk the label says so and shows 0 contracts.

## 3. SMT visual clean-up

* `Show SMT label shapes` OFF switches the label to `label.style_none` with the text in the SMT color. The connector line, tooltip, table logs, alerts and the state machine do not change.
* `SMT label size` and `Buy/Sell mark size`: Tiny / Small / Normal / Large.

## 4. Multi-timeframe feeds

The engine is now one function, `f_runEngine(Engine e, Feed f)`. A `Feed` is one closed candle of one timeframe for both markets (OHLC, the two-bar-back high/low for FVGs, pivots, sync windows, ATR, and the correlated market's tick size). An `Engine` holds that timeframe's state (hidden FVGs, IFVGs, SMT setups, reference pool, counters, logs).

* The chart feed runs on every confirmed chart bar exactly as before.
* Feeds #1–#4 (defaults 2m, 3m, 5m, 15m) are fetched with `request.security(..., [open[1], high[1], ...], lookahead_on)`, so they only ever see closed candles. Each runs when its own candle closes (`isNew`), and its bar counts (confirmation bars, lifetime, IFVG age) are counted in its own candles via `Engine.idx`.
* A feed is skipped when it is not higher than the chart timeframe, so on a 5m chart the 2m and 3m feeds are off automatically.
* Buy/Sell only fire from entry timeframes (30s, 1m, 2m, 3m, 5m). A 15m feed still produces SMTs, which is what makes a 15m SMT visible on the 1m chart when `Minimum timeframe for SMT display` is 15.
* Everything a feed draws is time-anchored (`xloc.bar_time`), so it lands on the right candle of the lower chart. Labels read `SMT [15m] · PDL`, `▲ BUY 3m`, and IFVG boxes carry the feed name. Feed marks appear on the first chart bar after the feed candle closes (one lower-TF bar later than the same signal on the feed's own chart), and the tooltip says so.
* Alerts: the `alertcondition`s fire for any feed. For the timeframe and contract count use "Any alert() function call": the message is built dynamically.

## 5. HTF FVG anchoring

`request.security` now also returns `time[3]`, `time[2]` and `time_close[1]` for each HTF slot: the open time of candle 1, the open time of candle 2 (the gap candle) and the close time of candle 3 (the last closed HTF bar). The box is created with those times:

```pine
int leftT  = htfAnchor == "Candle 1 (first of the 3)" ? tA : tM
int rightT = htfExtendMode == "Extend with price" ? time + fvgExtend * chartMs : tcC
box.new(left = leftT, top = lC, right = rightT, bottom = hA, xloc = xloc.bar_time, ...)
```

Why time and not `bar_index`: an HTF candle has no bar index on a lower chart, and `request.security` cannot return one. `xloc.bar_time` maps a timestamp to the chart bar that contains it, which is exactly the candle where the gap formed, on any chart timeframe. In "Extend with price" the right edge is moved to the current bar every bar and frozen at mitigation; in "Fixed to the 3 candles" the box covers candle 1/2 through the close of candle 3 and never moves. IFVG boxes use the same anchoring (`Anchor IFVG box at` chooses the inversion candle or the original gap candle).
