# Episode-by-episode notes — Troop Bootcamp (Andrew Macre)

Companion to `mech_model_backtest_spec.md`. Paraphrased notes with source timestamps, one section per video: the 13 playlist videos first (Episodes 1–12, then 15), followed by Episodes 16, 13 and 14, which are on the channel but not in the playlist. Not a transcript. Caption spellings vary in the source: FFEG/FFG/FVG = FFVG; MAC/MEC = mech; sweat/sweep pointer = swept pointer.

## Ep 1 — Welcome to the Mech Model (dzFyrdrJ5pE, 45:49)
- Model: "macro mechanical model" ("mech"). Separate from his private "Squid" top/bottom model (not taught).
- Instruments: NQ + ES futures (MNQ / MES). He executes everything on MNQ even when the setup prints on ES ("correlated pointers") to standardise risk. [13:22-14:21]
- Charting: TradingView + CME live data. Paid FluxCharts "Troop" indicator toolkit said to be needed long-term. [7:05-7:48]
- Resting timeframe = 5-minute. No hourly/4h/daily/weekly bias at all. [27:33-27:55]
- Theory: market seeks consensus ("efficiency" = consolidation/agreement; "inefficiency" = displacement). "Total float" = injection or withdrawal of orders; "rate of change" = how fast participants switch sides. Model trades the symptoms of a rate-of-change shift after a total-float change. [21:01-28:13]
- Trade inefficient -> efficient; check RR between the two; risk is market-based; trim at efficiency, then extensions, final TP; then take the reverse when a new shift appears. [29:23-29:58]
- Many executions per day, no fixed RR, not one-trade-a-day. [30:07-31:36]
- News: do NOT trade during "paper deliveries" (scheduled data, e.g. 10:00 / 14:00) or "testimonies" (FOMC presser, speeches). DO trade news days outside those moments. Source: Forex Factory. [38:31-40:58]
- Sessions (New York time): pre-market 8:30-9:30; NY open 9:30; volume fades by 11:00-11:30; lunch 12-1 slow; pickup 2-4pm; settlement window 3:50-4:15pm = flat by 3:50, no trades. Asia opens 6pm (volume stacks 6/7/8pm), his cutoff 9pm; London 3am; London->premarket 3-8am. Beginners: skip Asia. [41:00-44:16]

## Ep 2 — Market Structure Introduction (QEpOjtyaVac, 32:42)
- External / "high-resistance" high (low): a swing high whose wick takes out / overlaps a prior high; it "contains" the highs beneath it. "Low-resistance" (simple) high/low: takes nothing out. [1:09-1:43, 4:24-4:47]
- Sweep = price trades through a prior high/low. Fail sweep = price fails to exceed the prior external high (makes a lower high) / fails to undercut the prior external low. [1:43-2:00, 3:45-4:09]
- Change in character = break AND CLOSE through an external low (bearish) / external high (bullish). [7:03-7:48]
- CISD (change in state of delivery) = fail sweep + change in character. Not a standalone entry — price is fractal. [7:15-8:26]
- Four states: consolidation, expansion, reversal, retracement. [2:39-2:55, 12:09]
- "Efficient delivery": every push is met by an immediate opposite retrace candle -> not worth trading. [8:34-9:26, 10:31-10:41]
- Consolidation = every strategy fires; if the same setup conditions keep repeating without follow-through, stop trading. [14:15-15:55, 19:19-19:35]
- Example chart: 9:30 open marked as "9:30 macro". [23:51-24:02]

## Ep 3 — Liquidity Fundamentals (H1pOJtRF9qk, 23:58)
- Liquidity = resting orders at highs/lows (wick extremes). Buy side above, sell side below. [2:19-3:22]
- After a high/low is taken: manipulation (reverse), continuation, or both (= consolidation). Never assume reversal. [2:57-5:33]
- High-resistance high/low absorbs earlier levels; harder to take. [5:47-7:19]
- Stops trigger -> become opposite-side orders -> cascade. [9:55-12:18]
- ONE local timeframe; every high and every low treated as equally able to start a move. No session-high/low bias, no HTF draw. [12:34-13:12, 17:39-18:32, 21:08-22:38]
- His OLD model (not mech): PDH / PDL / PD-equilibrium transitions. Abandoned as too coarse. [13:12-17:39]
- Entry confirmation comes from "pointers" and FFVGs. Many trades; skip consolidation. [22:26-22:51]

## Ep 4 — Inefficiencies 101 (p7QsVm_5pwY, 43:21)
- Three inefficiencies: fair value gap (FVG), volume imbalance (VI), standard gap. Read-the-market tools, NOT entries. [1:06-1:44, 5:08-5:34]
- FVG = 3-candle pattern: candle 1 "initiation", candle 2 "displacement", candle 3 "placement". Bullish gap = space between candle-1 high and candle-3 low (bearish mirrored). [18:21-19:51]
- Four reactions to an FVG [20:16-23:35]:
  - validation: price respects it and continues;
  - mitigation: trades through / fills it then carries on;
  - inversion: a candle CLOSES beyond the far side of the gap;
  - proper inversion: inversion that also leaves a NEW opposite FVG behind (stronger).
- State read: expansion = bullish FVGs validated + bearish FVGs properly inverted; consolidation = both sides validated and invalidated equally. [23:47-24:37]
- VI = gap between one candle's close and next candle's open (bodies don't meet); filled when a body spans it. In an efficient market it is erased immediately; a VI that survives = imbalance of orders that way. Use on 5m. [30:36-35:17, 38:14-39:32]
- Standard gap = session-close to session-open gap (e.g. NY close -> Asia open, "new open gap"). No bias toward gaps. Only relevant at all-time highs: do not trade inside never-before-traded gap space; gap may be a target only. [40:22-42:16]
- He says 60-70% of moves can be read with FVGs alone but chop destroys it. [27:23-27:36]

## Ep 5 — First Fair Value Gaps (nboI4w4TAEw, 20:38)
- FFVG ("first fair value gap") = his supply/demand zone, replaces the order block. Every sweep of a (high-resistance) low/high spawns a SET of FFVGs. [3:07-4:23]
- Construction: after the manipulation (sweep), take the FIRST FVG that prints on each of the 1m, 2m, 3m, 4m and 5m charts. Nested: 1m forms first; if respected a 2m forms, then 3m, 4m, 5m. [6:06-7:23, 8:56-9:20]
- 5m is the top timeframe because trades rarely last more than an hour. [4:23-5:01]
- IFFVG (inverse FFVG) = an FFVG that price has run through / inverted; it now acts for the other side. FFVG and IFFVG are used identically. [12:08-14:03, 15:57-16:22, 18:21-18:33]
- Trades = confirmations ("validations") of an FFVG/IFFVG, travelling to the next opposing FFVG set. Continuation trades THROUGH FFVGs are also taken. [8:29-8:43, 16:22-16:50, 18:21-18:33]
- "White space" = stretch of price with no FFVGs in the way = room to move = opportunity. [10:38-11:55]
- FFVG = where the "total float" change happens; pointer = the confirmation. Claim: every implied move is explained by an FFVG/IFFVG except macro. [14:16-14:55, 5:14-5:40]
- Chart on the minis (NQ/ES); keep FFVGs/IFFVGs on their own screen. [2:26-2:39]
- Indicator draws "tapped" and "untapped" FFVGs. [2:39-2:52]
- First payout Nov 2024. [19:12-19:25]

## Ep 6 — What is a Pointer? (qkVdu2j2z_E, 42:02)  *** ENTRY TRIGGER ***
- Problem solved: entering on a break of structure (close OVER a prior wick) creates a potential FVG and invites an immediate retrace, especially in consolidation. [3:41-6:30, 14:06-14:57]
- POINTER = a candle that CLOSES INSIDE THE WICK RANGE of the previous candle — not beyond the wick — while reacting to / moving away from an FFVG or IFFVG ("efficient validation"). He likens the look to an engulfing candle. [16:00-17:44, 40:48-41:00]
- Rule 1/2: every implied move starts (and ends) with a pointer reacting to an FFVG, unless macro/news driven. No pointer = no sustained move. [15:09-15:47, 19:41-19:54, 35:40-36:05]
- Pointer timeframes: 3m, 4m, 5m, 6m are the base entry timeframes for ~1-hour trades. 1m/2m pointers appear in consolidation; 7m exists. [18:21-19:13, 24:40-24:54]
- Check BOTH NQ and ES: a pointer on either counts. "SMT pointer" = pointer on one index and not the other. [20:31-21:23, 34:19-35:00, 39:30-40:10]
- Bare-bones exit = an opposite pointer validating the opposite FFVG. (Refined later.) [26:36-27:14, 28:31-28:44]
- Types named but deferred: weak pointers, swept pointers, continuation pointers, manipulation pointers, SMT pointers. ~13-14 pointer rules in total. [15:09, 24:02-24:14, 35:12-35:25]
- Volume with no pointer usually = accumulation. In a tight range the 3-6m may not print a pointer before the breakout; then enter on a continuation pointer. [35:52-36:32, 37:08-37:21]
- Don't trade London per his aside. [34:46-35:00]
- 70% of the model is context/rules, not the pointer pattern itself. [19:00-19:26]

## Ep 7 — Untapped First Fair Value Gaps (Nxx-DQvGWk4, 22:46)
- Untapped FFVG = an FFVG/IFFVG price has not come back to since it formed (price swung away hard). Separate paid indicator upgrade; he shows only lines for them. [0:53-1:46, 2:39-3:31]
- They are the DRAWS ON LIQUIDITY: the start and finish lines of trades, and how RR / trade length is judged. [3:31-4:11, 16:48-17:13]
- BIAS RULE: direction = direction of the latest pointer reacting to an untapped FFVG. Bias holds until a pointer reacts to a new / opposing untapped FFVG. Pointers off ordinary (tapped) FFVGs against you are not a full exit reason — trim only. [4:11-5:04, 6:09-7:27, 8:32-9:11]
- Claim: no true reversal or continuation without an untapped-FFVG pointer reaction. [6:22-6:47, 8:58-9:11]
- MINIMUM TARGET: after a valid pointer off an untapped FFVG, price is expected to reach at least the next opposing untapped FFVG ("additive trim principle" — detailed later). [11:35-12:24, 15:16-15:41]
- "Self-made draw": a manipulation creates a brand-new untapped set and a pointer reacts to it without needing an older one — very strong. [16:07-16:48]
- Read NQ and ES independently. Both pointing the same way off their untapped = trend; disagreeing = consolidation. Untapped can be shared across the two. [9:36-9:49, 17:13-18:30]
- Check distance ("white space") from entry to the next untapped on both indices before taking a trade. [18:30-19:21]
- PO3 (accumulation) trades: treat as "additive trim only" — small size, few points. [12:37-13:16]
- No trades held through 3:50pm; he also skipped Asia in the example. [10:28-10:43]
- On contract roll, the indicator's levels must be offset by the roll gap. [21:44-22:12]

## Ep 8 — Trading Swept Pointers (jya5Z7ecbYs, 27:36)
- Swept pointer = a pointer (close inside prior candle's wick range, off an FFVG/IFFVG) whose own wick ALSO sweeps a prior high/low in the direction of the trade. [2:48-4:57]
- Three outcomes at the swept extreme: expansion through it, reversal from it, consolidation. [5:11-5:37, 10:39-10:53]
- SWEPT POINTER TEST: it becomes a valid entry only once price trades through the swept pointer's high (bull) / low (bear). Any timeframe; in his example a wick through counted. If price reverses from that extreme instead, the entry is not valid -> reduce. [7:10-7:48, 9:20-9:45, 12:46-12:59]
- Sizing on a swept pointer: half size at the pointer close; the other half after the swept extreme breaks, or after price breaks out of the FFVG it is stuck inside. [7:35-8:01, 15:43-16:22, 19:26-20:18]
- Skip signal: a 1m FVG forming against you off the swept extreme. [13:11-13:50]
- You may feather down on a consolidated draw and feather back in if no opposite pointer has printed. You are only fully out (bias dead) when a pointer confirms the other direction. [10:12-10:39, 22:53-23:06]
- The FFVG being traded into decides success, not the pointer: needs room to the next FFVG; a thick stack of FFVGs ahead = poor trade. [6:43-7:10, 8:01-8:41, 16:48-17:28, 26:18-26:43]
- Additive trim principle preview: once the swept low breaks, price is expected to reach the next FFVG. [14:53-15:31]
- Structural invalidation in the example: a 3m "inefficient" close back over the IFFVG. [15:31-15:43]
- Nearly every full reversal has a swept pointer at its extreme; consolidations are made of repeated swept pointers. Best sequence: swept pointer -> untapped FFVG created -> ordinary pointer. [11:05-11:44, 20:32-22:15, 25:52-26:18]

## Ep 9 — Areas of Control (_rPsTctM_1U, 31:43)
- "Pointer range of control" (PROC; "ECR / efficient candle range" in his indicator) = the price range of the pointer candle that formed off an untapped FFVG (the bias-setting pointer). [2:09-2:48]
- Valid until a NEW pointer + untapped-FFVG combination prints against it. [2:48-3:01, 6:11-6:51, 13:01-13:15]
- Use 1: after trimming, re-add contracts with limit orders when price retraces back into the range. [3:40-4:17, 10:42-11:07]
- Use 2: enter an existing bias without a fresh pointer — e.g. a London-session pointer still valid, 9:30 retraces into its range, enter there. He says most "missed" big trades are exactly this into the 9:30 open. [5:07-5:57, 15:25-15:51]
- Use the FIRST pointer off the FIRST untapped; prefer the lowest-timeframe pointer for a tight range; a very wide ("fat") range is a valid entry but a poor refill zone. [8:22-8:47, 14:19-14:44, 20:10-20:22]
- Risk: price retraces deep into the range, builds a new untapped + opposite pointer -> the refill loses. [4:17-4:55, 14:44-14:57]
- Several ranges of control forming in quick succession = consolidation; don't refill there. [11:19-11:45, 16:16-16:43]
- Swept pointers only define a range once they pass the swept test. [9:39-10:42, 18:28-18:41]
- Full TP zone in example = the opposing untapped FFVGs. [10:04-10:28]
- Example of news filter: whole stretch skipped because news was delivering. [26:52-27:19]

## Ep 10 — Dealing with Accumulations / PO3 (prXZledaNIQ, 48:33)
- PO3 = "pointer rule of three": three or more pointers validating FFVGs on alternating sides (bull, bear, bull...) with no sustained move = accumulation confirmed. [5:54-6:45, 9:50-10:03, 17:25-17:51]
- Once PO3 is confirmed: NO trades until one of two things [12:13-12:40, 17:51-18:42]:
  (a) MANIPULATION: the accumulating index takes a high or low NOT associated with the chop range (an older, outside level), with an untapped FFVG + pointer there -> trade back toward/through the range. An SMT (only one of NQ/ES takes it) qualifies. [16:47-17:25, 34:57-35:48]
  (b) CONTINUATION (breakout): only if the pointer comes off an untapped FFVG, targets an untapped FFVG, and has nothing in between so an additive trim is possible. [18:29-19:35, 21:06-21:45]
- Mark PO3 highs/lows; do not use them later as manipulation levels. [39:03-39:53]
- Trading every pointer inside an accumulation loses or breaks even. [11:46-12:13]
- Needing 1m/2m pointers to find entries/exits = you're in a micro range; trades normally last 15-60 min on 3-6m pointers. [15:17-15:56]
- POINTER RULE: a pointer is expected to reach the next FFVG set if no FFVG/IFFVG lies in between; untapped goes to next untapped. FFVGs in the way are "traffic". [19:35-21:06]
- ADDITIVE TRIM (his stop-loss replacement) [22:51-24:50]:
  - Condition: clear space between the FFVG you entered from and the next FFVG set.
  - Action: add extra contracts (example: planned 10 -> take 20) and exit the extra at the next FFVG set with a limit order.
  - Purpose: that banked profit is the buffer so a reversal ends at break-even. No static stop loss.
  - Loses when the opposite pointer's spread is bigger than the buffer (example: +30 buffer vs 60-pt pointer).
- PAUSED ADDITIVE TRIM: one FFVG/IFFVG still in the way. Take half size at the pointer; when a candle on that FFVG's timeframe closes through it ("inefficient break", e.g. a 1m close through a 1m IFFVG, 4m through a 4m), add the rest with a limit TP at the next untapped FFVG set. Fewer FFVGs to flip = higher probability. [25:03-27:35, 29:23-30:01, 36:01-36:26, 40:07-40:57]
- Alternative de-risk on a swept pointer: use the swept pointer's low/high to cut the half position. [26:43-27:08]
- Exit remains: opposite pointer. If entry price == exit price the trade was pointless -> size down in chop. [13:44-14:24, 47:36-47:49]
- 9:30 "macro" excluded from analysis again; 3:50 window again. [41:10, 46:28-46:40]
- "EQ range" tool mentioned for anticipating chop (not defined here). [45:21-46:15]
- Prop context: Topstep XFA + Lucid accounts; payouts capped (~5k) so he sizes big early then goes for consistency. [2:31-3:35, 27:35-28:28]

## Ep 11 — Mechanical Techniques (T03D0lULTRY, 38:41)
- He backtests only 9:30-16:00 NY; does not trade the 9:30 open candle/window itself; done at the 3:50 window. [2:07-2:21, 2:59-3:14, 18:10-18:36, 33:20-33:33]
- SIZING "5-10 split" (contracts): 5 = weak/half, 10 = full, +10 extra on an additive trim. [4:22-4:47, 27:18-27:43]
- WEAK POINTERS (half size): SMT pointer (only one of NQ/ES), swept pointer, and a pointer printed after price already made the untapped->untapped transition. [4:07-4:35, 19:01-19:27]
- FULL SIZE: pointer off an untapped FFVG that is a plain (non-swept) pointer on BOTH indices ("correlated pointers"). [7:24-7:50, 13:51-14:17, 34:38-34:50]
- Pre-trade risk check: measure distance from entry to where an opposite pointer could form at the next opposing untapped FFVG (example 30-40 pts; another 85). Large = size down or skip. [4:47-5:51, 34:12-34:38]
- THREE TRIM TYPES [5:51-7:11]:
  1. at an untapped FFVG at/near the "EQ range" line — small fixed clip (2-3 of 5-10), done consistently;
  2. if the trade came from an SMT (one index swept a high/low, other didn't): the lows/highs associated with that swept level are longer targets — prefer the FFVG just before the level; [28:36-29:43]
  3. additive trims.
- Never add risk mid-trade unless an additive trim is available. [8:43-9:35]
- De-risk signal: a swept pointer against the position on either index -> drop to 1m; cut ~half if a 1m FVG forms or an inefficient break occurs; if the swept extreme breaks, cut. [9:35-10:14, 10:51-11:18, 22:41-23:06]
- FULL EXIT: pointer reacting to an untapped FFVG against you. A pointer off a tapped FFVG is not an exit. [7:11-7:24, 11:18-11:30, 28:10-28:24, 32:31-32:56]
- SKIP rules shown: swept pointer into a thick stack of FFVGs; no untapped reaction; PO3 until an outside high/low (e.g. "NY PM high") is taken; continuation without additive trim; FFVGs in the way on the OTHER index. [11:30-12:48, 14:43-15:22, 16:01-17:05, 30:33-31:10]
- Buffer-based discretion: small account buffer = only clean setups; large buffer = take every pointer. [24:09-24:47]
- Ignore IFFVGs created by news spikes. [33:45-33:59]
- Example P&L on this size: -$50, -$100, -$50; +$200, +$400-500; one day "passes an eval". [7:11, 13:39-13:51, 23:19-23:31, 28:10, 36:32-36:45]

## Ep 12 — Backtest with a Profitable Day Trader (YHTenCz5rNw, 1:01:53)
- Walk-through of one week (Mon 2 Mar - Fri 6 Mar 2026), 5m chart, bar replay, NQ with ES cross-checks, Forex Factory open. [2:23-3:39]
- News handling: red/orange 10:00 release -> no trade until it has delivered (~2 five-minute candles); scheduled speech (11:00) -> flat before it, resume ~1.5 h later; 8:30 release -> start at 9:30; yellow-folder items ignored. [3:27-4:06, 5:10-5:22, 13:22-14:03, 20:18-20:45, 31:25-31:52, 42:10-42:24]
- 9:30 open candle not traded. He also trades pre-market ~7:30/8:00-8:30 when no news, flat before the open. [4:20-5:10, 42:24-42:36, 52:25-52:53]
- "Mechanical in execution, discretionary in sizing and trims." [6:13-7:04]
- Low account balance -> skip weak continuations; decent balance -> take small and read the swept extreme. [6:52-7:29, 28:10-28:35, 31:00-31:25]
- Swept pointer handling as Ep 8: 5 contracts, mark the swept extreme, watch 1m; break -> revert to "pointers only" as exit condition (optionally add 5); 1m inefficiency against -> cut ~2; pointer off it -> exit. [7:29-8:20, 20:58-21:12, 33:11-33:39, 43:04-43:45]
- Opposite pointer on EITHER index, any of 3-6m (even an SMT pointer) used to close and optionally reverse. [8:20-8:59, 19:38-19:51, 25:05-25:18, 49:05-49:18]
- First target: untapped FFVG at EQ range on whichever index reaches it first; clip 2 contracts. [8:59-9:39, 21:12-21:39, 44:00-44:14, 46:56-47:10]
- Pointer reacting to a plain FFVG = no action, but watch for consolidation. Untapped = external liquidity, tapped = internal. [10:18-11:12]
- PO3 counter kept live ("PO3 is set to 2"); at 3 -> stop, wait for outside draw or additive-trim continuation. [8:47-8:59, 34:06-34:21, 35:16-35:45, 59:02-59:15]
- Continuation out of consolidation without an additive trim = low quality; shown losing $200. [27:16-29:01]
- Paused additive trim live: need 1m (and 3m) close through the IFFVG; repeated failures -> call PO3 and stop. [35:45-38:20, 40:28-41:08]
- Refill at entry price via range of control only if no opposite pointer on either index. [44:41-45:09, 55:12-55:51]
- "Self-made" untapped = freshly created 1m untapped. [55:25-56:17]
- Too many pointers after entry = bad; want inefficient (one-directional) price after entry. [24:28-25:05]
- Claimed week: Mon ~+$200, Tue +$1.6k (5 contracts, ~170 pts on one trade), Wed +$1.0k, Thu ~+$3k, Fri +$0.5k => $6.5-7.5k. Typical PO3 loss $27-$300. [9:39, 25:05-25:45, 41:08-41:21, 49:18-49:31, 59:15-59:29, 1:00:11-1:00:52]
- He counts win rate by whether the bias played out, not by P&L. [40:16-40:28]
- He states automated backtests of this are inaccurate and it must be done manually; plans a 100-trade manual backtest. [56:41-57:21]
- Prop context: Topstep XFA, buffer, 5 trading days for payout eligibility. [51:47-52:13, 1:00:26-1:00:52]

## Ep 15 — Equity Correlations and Divergences using PROC (8cFDRk1cQkY, 24:55)
- Each index (NQ, ES) carries its own current pointer range of control = its own bias, set by its latest pointer reacting to an untapped FFVG. [0:54-1:56]
- JOINED / correlated: both indices' ranges of control point the same way -> strong, tradable moves, full participation. [4:17-4:42, 6:39-7:07, 16:28-17:07, 19:08-19:21]
- DISJOINTED: one index prints a new untapped-pointer and the other does not (or they point opposite ways) -> the move tends to get faded when the lagging index pulls back into its own range of control. Skip or go light. This is why SMT/weak pointers get half size. [1:19-3:12, 20:37-21:46]
- PO3 = the two indices holding opposing ranges of control and swapping; breakouts happen when both correlate. [21:33-22:51]
- A pointer that is not reacting to an untapped FFVG ("structural" / fake) does NOT create a new range of control. [13:20-14:14, 14:39-14:53, 16:16-16:28]
- Prep: before the NY open know where each index's range of control sits to read the morning. [3:50-4:17]
- All-time highs: target the high, then stop. [7:20-7:45]
- Uses even contract counts (2/4/6/8/10) for easier trimming; example used 6. [6:51-7:07, 16:41-16:55]
- He repeatedly loses track of which pointers/untapped are valid in bar replay and says it is far easier live — a warning for any mechanical reconstruction. [5:21-6:14, 11:36-13:20, 23:04-23:31]
- Still to come per him: episodes on trims, sizing, prop firms; tools like standard deviation, VWAP, volume profile for trims. [0:26-0:40, 24:11-24:50]
- Dates used: 22 Apr, 9-10 Mar (2026). Indicator update extends untapped history. [0:40-0:54, 3:37-3:50, 7:58-8:12, 19:21-19:34]

## (NOT IN PLAYLIST) Ep 16 — How to trim winning trades using key levels (wd5IRl8eIrg, 55:30)
- Entry restated: a pointer reacting to an untapped FFVG sets the range of control, and it must appear on BOTH indices ("A+"); otherwise you trade against the grain. [1:06-1:45]
- Philosophy: conservative entering, liberal exiting. Trims reduce exposure; they are not exits. [2:37-3:31]
- TP1 = the first FFVG price meets after the new leg (frequently the same as the FFVG at EQ range). EQ range does not exist pre-market; it is fixed at the 9:30 open. [1:45-2:23, 3:58-4:52]
- Additive trim restated: once every FFVG in the way has been closed through, add contracts with a limit at the next FFVG. [5:06-5:57]
- TP2+ = untapped FFVGs that line up with BOTH [5:57-7:03, 19:22-20:26]:
  (a) a "break-of-structure deviation" level: fib tool anchored sweep extreme (0) -> break of structure (1), levels every 0.5 out to 4.5; can be drawn inverse off still-respected older structure; check both indices; redraw as new breaks form; [7:03-12:24]
  (b) a low-volume node on a volume profile (row size 2 ticks, value area 40, anchored to the session or day swing), NQ only. [12:24-19:22]
- Clip 2 contracts per trim; 10 -> 2/2/2 leaves ~4 runners. Use micros so there is always something to trim. [2:11-2:37, 25:04-25:17]
- Check: after a good trim price should stall; if it accelerates the trim logic was wrong. [22:48-23:13]
- Full exit unchanged: pointer against you off an untapped FFVG. [3:31-3:45, 27:18-27:31, 33:57-34:10]
- Don't hold through the 9:30 open on average. [27:31-27:43]
- He says the deviation levels have no real basis — only useful stacked on the rest. [21:29-22:08]
- Indicator has no untapped data at all-time highs / extreme lows. [30:13-30:40, 35:34-35:47]
- Example: pre-market entry ~8:30, ~150 NQ points to the open. [26:25-26:53]

## (NOT IN PLAYLIST) Ep 13 — Backtest with a Profitable Day Trader, part 2 (DqeL9On7204, 54:19)
- Bar replay, NQ 5m: Fri 9 Jan, then Mon 12 or Tue 13 Jan (he is unsure on screen), then Wed 14 Jan 2026. [3:08-3:33, 45:24-46:29]
- 10:00 news: waits ~2 candles after the release. [4:37-4:50]
- Continuation pointers: not taken inside PO3, and not added to an open trade unless risk can be managed (additive trim). [6:21-7:00]
- "We don't take swept pointers into untapped": a swept pointer whose path runs straight into an opposing untapped FFVG is skipped. [8:34-8:58, 10:26-11:04, 16:08-16:20, 52:03-52:16]
- Other-index veto: if the other index had pointers against at entry time, it was not an entry. One index pointing up while the other points down = no trade. [8:20-8:46, 31:20-31:47]
- A sweep of a high/low that belongs to the PO3 range does not count as the "outside" draw. [13:35-14:14]
- "Structural pointer" (no untapped reaction) is ignored. [15:31-16:08, 16:20-16:46]
- ALL-TIME HIGHS: no reference data above; target the high and stop. Only trade again if a self-made untapped + pointer appears. Trailing to break-even is "changing the strategy". [17:25-18:43]
- EQ RANGE (closest thing to a definition): derived from the session's range/volume, marks the equilibrium inside it; breaks down after big gaps/large sessions — then use an untapped FFVG near the PO3 area instead. [18:43-19:20]
- Additive trim sizing rule: "double my risk". Worked example: +$500 from one transition, leaving a 30-60 pt cushion. [35:59-36:50, 37:29-37:55, 38:45-38:59]
- Paused additive trim in practice: enter light, add when the 2m/3m/4m FFVG in the way is closed through, limit at next FFVG; gaps under ~10 pts are usually too fast to do it. [28:20-28:58, 29:24-29:36, 39:25-40:17]
- A swept pointer into the far edge of an FFVG on either index = de-risk signal. [37:55-38:33]
- Micros vs minis: MNQ/MES can print pointers NQ/ES don't. Trust the minis; backtest on minis and scale P&L by 1/10. [34:00-34:27]
- Buffer rule: under ~$2k drawdown be very selective; above ~$5k with a small split (4/8 or 5/10) take every pointer. [12:21-12:33, 25:18-25:44, 44:45-45:11]
- He was reading the wrong month's news calendar for part of the session (traded through 8:30/10:00/14:00 releases unknowingly). [45:11-46:17]
- He says outright the method can't be automated. [52:03-52:16]
- Claimed: day 1 ~break-even, day 2 ~+$1.4k (plus +$500 additive) then -$120, day 3 ~+$500; "4-4.5k" total. [23:04-23:17, 30:55, 41:46-42:25, 44:08-44:33, 49:35-49:49, 53:49-54:03]

## (NOT IN PLAYLIST) Ep 14 — I let my viewers trade my model in front of me (l2W-X6_Otpk, 1:27:25)
- Two Discord members bar-replay recent days on NQ/ES minis while he corrects them.
- WHAT COUNTS AS "REACTING TO AN UNTAPPED": the pointer should be the candle right after the tap — the wick that taps the untapped FFVG sits directly next to the pointer; a pointer several candles later doesn't count. The pointer's own range need not sit inside the zone. [46:12-47:05]
- Cross-timeframe: the tap can be on a 1m/2m FFVG while the pointer closes on the 5m. Commonest student error = missing low-timeframe taps. [9:30-9:55, 23:13-24:31, 37:05-37:31]
- Sequence seen repeatedly: price closes through an FFVG (creating untapped IFFVGs), comes back to tap them, pointer closes -> entry. [9:30-9:55, 20:39-21:06]
- Correlated 5m pointers on both -> 10 contracts; first trim ~3 at the untapped. NQ and ES contracts are not size-equivalent. [9:55-10:34]
- SMT target: if one index took a low and the other didn't, the opposite high (either index) is a strong target. [10:22-10:51]
- All-time high: take profit at the high, then wait for a self-made untapped. [11:06-11:44, 20:13-22:12]
- Swept pointer against you: trim only if the 1m inefficiency locks in; full close only on a pointer tapping an untapped. [13:10-14:00]
- PO3 after an outside high was taken and price still chops -> no trades back the other way; a "PO3-only trade" = pointer off untapped with a limit exit at the next untapped, nothing more. [18:16-20:13, 53:29-54:22, 56:07-56:46, 1:14:10-1:16:16]
- Backtest news convention: testimony = skip an hour; instant release = resume next candle. [36:52-37:05]
- Swept pointers: either never take them, or always take them at the pointer close and then test — no stop-entry waiting for the break. [31:23-32:13, 37:31-38:08]
- Never take a swept pointer into an untapped FFVG. [34:39-35:33]
- Breakout from consolidation = the last FFVG holding it gets closed through with white space beyond. [26:19-27:37, 35:33-36:14]
- Structural pointer (off a tapped FFVG) against you: optional light trim, re-add in the range of control; not an exit. [28:22-29:53]
- In a strong trend successive ranges of control stack (each pullback taps the FFVG at the last range and prints a new pointer). [59:43-1:00:08]
- Refill/limit-order techniques only if you watch the tape continuously. [1:02:38-1:03:17]
- Use even contract splits (2/4/6, 6/12). [54:34-55:14, 1:09:16-1:09:42]
- He wants ~100 pts of potential before bothering; skips 30-40 pt grinders. [47:46-48:36]
