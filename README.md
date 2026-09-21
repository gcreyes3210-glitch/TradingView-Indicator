# ICT SMT + IFVG in HTF FVG (Pine Script v5)

> The script header is `//@version=5`. All Phase 1 code uses constructs that are valid in both v5 and v6; the version line was left unchanged to avoid an unverifiable migration.

`ICT_SMT_IFVG.pine` is the full indicator. Paste it into the TradingView Pine editor and add it to the chart.

## Phase 3 + fixes (this version)

| Change | Input group | Where |
|---|---|---|
| HTF Direction Filter (OFF / REQUIRE SAME DIRECTION / ALLOW OPPOSITE DIRECTION), default OFF | `11 · Phase 3` | `IFVGZone.primaryBull` set at IFVG formation via `f_htfPrimaryBull()`, gate `dirOkP3` in section F |
| Objective displacement events per feed (body ≥ x ATR, body/range ≥ y, close vs open, N consecutive candles, optional swing break), filter OFF / OPTIONAL / REQUIRED, default OFF | `11 · Phase 3` | block `P3` before section B of `f_runEngine()`, `Engine.lastBull/BearDispBar/Time`, snapshot into `IFVGZone.dispBar/dispTime/dispOk`, gate `dispOkP3` |
| Sweep → SMT → confirmation → displacement → IFVG sequence filter with windows, default OFF | `11 · Phase 3` | `SMTSetup.sweepTime/sweepPrice/sweptLevel/confirmBar/confirmTime`, gate `seqOkP3` in section F, `Engine.lastSeq` |
| **Bug fix**: SMT age in days now expires the SMT itself | `3 · SMT engine` → `Max SMT age (days, 0 = OFF)` | `SMTSetup.detectTime` (fixed at detection), age test in section E on every feed bar |
| Session time zone input with DST-aware IANA zones, default `America/Los_Angeles`; session defaults converted to Pacific | `5 · Time` | `i_timeZone`, `tz`, `f_inSession()` |

**SMT expiry bug, cause.** The old day check `time - se.legTime > smtMaxDays * dayMs` sat in the `else` branch of `if keepHistory`, so with the default `Keep marks on past bars = ON` it never ran; it only deleted labels, never marked the setup expired; and it used `legTime`, which moves to each new sweep extreme. Fix: `detectTime` is stored once at creation, `ageDays = (time - detectTime) / 86400000.0`, and `ageDays > smtMaxDays` sets `expired` (and `ageExpired`) in the same place `smtLifeBars` does, on every feed bar, then the setup is removed from `e.setups` in the existing reverse loop. `expired` is already required false by section F, by the confirmation path and by the debug "live" pick, so an expired SMT cannot confirm, pair, fire or count in the sequence.

## Phase 2 (previous version)

| Feature | Input | Where in the script |
|---|---|---|
| First retest tracking: `firstRetestAvailable`, `firstRetestUsed`, `retestCount`, `wasOutside` | `Require First HTF FVG Retest` (default OFF) | `HtfFVG` fields, Phase 2a block at the end of `f_hzUpdate()`, `f_hzRetestOk()` |
| Age in the zone's own timeframe bars: `createdBar`, `createdTime`, `tfSec`, `ageBars`, `ageExpired` | `Max HTF FVG Age (own-TF bars, 0 = OFF)` (default OFF) | `f_slotSec()`, Phase 2b block in `f_hzUpdate()`, `f_hzAgeOk()` |
| Composed eligibility `lifecycle AND age AND first retest` | — | `f_hzEligible()` (same call sites as Phase 1: `f_htfContain`, `f_htfOverlap`, `f_markHtfUsed`) |
| Primary HTF context among overlapping eligible zones | — | `f_hzBetter()`, `f_htfPrimaryIdx()`, `f_htfPrimaryTag()`, `IFVGZone.primaryTag`, `HtfFVG.isPrimary` |
| HTF zone debug table | `Show HTF zone debug table` (default OFF) | end of the `TABLES` section |

* **First retest** = the first bar whose range overlaps the zone after at least one bar was fully outside the zone (`high < bottom` or `low > top`) since creation. The creation bar never counts. It is consumed (`firstRetestUsed = true`) when price leaves the zone again; later returns are not first retests.
* **Age** = `floor((time - createdTime) / (tfSec * 1000))` where `tfSec` is the slot's own timeframe length (NDOG: 86400). `createdTime` is the chart bar that added the zone (first bar after the HTF candle closed). Exceeding the max sets `ageExpired` only; state and box are untouched.
* **Priority** when several eligible zones overlap the candidate box: higher timeframe, then more recent creation, then smaller distance from the reference price to the CE, then more recent first touch. The primary is written on the IFVG box (`P:1H`) and in the signal tooltip; it never removes or filters other zones, and the Buy/Sell test still accepts any eligible zone.

## Phase 1 enhanced (previous version)

| Feature | Input group | Where in the script |
|---|---|---|
| HTF FVG / NDOG lifecycle: `FRESH -> TOUCHED -> PARTIALLY_MITIGATED -> CE_50_MITIGATED -> DEFENDED / FILLED -> INVALIDATED`, fixed 50% CE, first-touch / first-CE-hit tracking, HTF-confluence eligibility | `2 · HTF FVG` | `HtfFVG` type, `HZ_*` constants, `f_hzUpdate()` / `f_hzSetState()`, the "HTF zone lifecycle" loop in `MAIN` |
| `50% CE Rejection Method` (Wick Rejection / Close Back Across CE / Displacement Away From CE / Close + Displacement) | `2 · HTF FVG` | `f_hzUpdate()` |
| NDOG (New Day Opening Gap) as an HTF zone, slot 9, read from the chart's own confirmed bars | `2 · HTF FVG` | `f_addNdog()`, `newDay` in `DATA`, `f_invalidateHtf(9, …)` |
| `Max Bars from FVG to Inversion`: an FVG inverted later than this is expired (no IFVG box, no signal) on every feed | `1 · IFVG` | inversion loop in `f_runEngine()` (`rf.age > maxFvgToIfvgBars`) |
| Retention in days: `Remove SMT marks after (days)`, `Remove Buy/Sell marks after (days)`, `HTF FVG / NDOG max age (days)` | `3 · SMT engine`, `8 · Buy / Sell signal`, `2 · HTF FVG` | `SigMark.markTime`, `SMTSetup.legTime`, `HtfFVG.bornT`, `f_expireHtfByDays()` |
| SMT label de-duplication by extreme edge: SMTs anchored to the same high / low share one label | `3 · SMT engine` | `SmtAnchor` type, `f_anchor*()`, `method draw()` |

### How eligibility reaches the signal

`f_htfContain()` is called once when an IFVG forms and its result is frozen into `IFVGZone.htfTag`; section F of the engine then tests `htfOkF = not requireHTF or zf.htfTag != ""`. That call (and the SMT "tap" in `f_htfOverlap()`) now skips zones that are not eligible, so a DEFENDED / FILLED / INVALIDATED zone can still be on the chart while an IFVG inside it no longer counts. The lifecycle loop runs **after** the engines on each confirmed chart bar, so an IFVG that forms on the very bar that defends a zone still pairs; from the next bar on the zone is out. Set `Only ELIGIBLE zones count for HTF confluence` OFF to restore the old "every zone in the list counts" behaviour.

State rules (all on confirmed chart bars, CE = `(top + bottom) / 2` of the original gap):

* **TOUCHED**: a wick enters the gap. **PARTIALLY_MITIGATED**: a bar closes inside the gap without reaching the CE.
* **CE_50_MITIGATED**: a wick reaches the CE. `firstTouch*` and `firstCEHit*` are set once and never overwritten.
* **DEFENDED**: after the CE hit, the selected rejection method is satisfied. Eligibility off.
* **FILLED**: a wick trades through the far side of the gap. Eligibility off, box stays (existing rules).
* **INVALIDATED**: the existing `HTF FVG is removed when price` rule (still evaluated on that slot's own closed candle, on chart bars for NDOG) removes the zone as before.

Not changed: LTF IFVG detection and inversion logic, the SMT detection algorithm, Buy/Sell entry conditions, alerts, the MTF feeds, and every `request.security` call (no new lookahead requests were added; the NDOG uses `time("D")` and the chart's own `open` / `close[1]`).

## What changed in the previous version

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
