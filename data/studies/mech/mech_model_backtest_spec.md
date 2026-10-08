# Andrew Macre "Mech Model" — backtest specification

Compiled from the Troop Bootcamp video series (YouTube, channel "Andrew Macre"). This is a rules summary written in my own words for the purpose of testing the method. It is not a transcript and contains no verbatim passages. Every rule carries a citation of the form `[E6 16:00]` = Episode 6, timestamp 16:00, so any line can be checked against the source video.

**Intended reader:** a coding agent (Claude Code) that will implement and backtest this, and the human reviewing its choices.

---

## 0. Read this first

1. **The author says this cannot be automated.** He states that automated backtests of it are inaccurate and that it must be tested by hand in bar replay `[E12 56:41]` `[E13 52:03]`. He describes it as mechanical in *entry* and discretionary in *sizing, trims, and which setups to skip* `[E12 6:13]` `[E14 2:06]`. Any coded backtest therefore tests **one interpretation** of the rules, not the method as he trades it. Report results that way.
2. **The core objects come from a paid indicator** (FluxCharts "Troop" toolkit, plus a separate "untapped" add-on) whose exact logic is not disclosed in the videos `[E1 4:07]` `[E7 0:53]`. The definitions in §3 are reconstructed from his verbal descriptions. Where two readings are possible I give both and mark a default.
3. **There is no stop-loss.** Risk is managed by size, by banking early partial profits ("additive trims"), and by exiting on an opposite signal `[E10 23:20]`. A backtest must track maximum adverse excursion per trade and should run a catastrophic-stop variant for comparison.
4. **All profit figures in the videos are the author's own unverified claims**, made on bar replay with hindsight corrections (he frequently rewinds, re-enters, and says where he "would have" exited). He sells the indicator and carries prop-firm affiliate codes. Treat §9 as sanity-check targets, not evidence.
5. **He often loses track himself** of which zones are tapped/untapped in replay `[E15 11:36]` `[E15 23:04]`, and in one session read the wrong month's news calendar `[E13 45:11]`. Expect the rules to be under-specified at the edges.

---

## 1. Source videos

Playlist "Troop Bootcamp" contains 13 videos (Episodes 1–12 and 15). Episodes 13, 14 and 16 exist on the channel but are not in the playlist; they are included here because they contain rules. No Episode 17 was found by search as of 8 Oct 2026. The channel also has older series that were not reviewed (a 31-video "Trading Bootcamp – Day N" playlist and a 12-video "Mentorship" playlist).

| Ep | Title | Length | Video ID | In playlist |
|---|---|---|---|---|
| 1 | Welcome to the Mech Model | 45:49 | dzFyrdrJ5pE | yes |
| 2 | Market Structure Introduction | 32:42 | QEpOjtyaVac | yes |
| 3 | Liquidity Fundamentals | 23:58 | H1pOJtRF9qk | yes |
| 4 | Inefficiencies 101 (FVGs, VIs, standard gaps) | 43:21 | p7QsVm_5pwY | yes |
| 5 | First Fair Value Gaps (Supply & Demand) | 20:38 | nboI4w4TAEw | yes |
| 6 | What is a Pointer? (entry condition) | 42:02 | qkVdu2j2z_E | yes |
| 7 | Untapped First Fair Value Gaps | 22:46 | Nxx-DQvGWk4 | yes |
| 8 | Trading Swept Pointers | 27:36 | jya5Z7ecbYs | yes |
| 9 | Areas of Control | 31:43 | _rPsTctM_1U | yes |
| 10 | Dealing with Accumulations (PO3) | 48:33 | prXZledaNIQ | yes |
| 11 | Mechanical Techniques | 38:41 | T03D0lULTRY | yes |
| 12 | Backtest with a Profitable Day Trader | 1:01:53 | YHTenCz5rNw | yes |
| 13 | Backtest with a Profitable Day Trader (part 2) | 54:19 | DqeL9On7204 | no |
| 14 | I let my viewers trade my model in front of me | 1:27:25 | l2W-X6_Otpk | no |
| 15 | Equity Correlations and Divergences using PROC | 24:55 | 8cFDRk1cQkY | yes |
| 16 | How to trim winning trades using key levels | 55:30 | wd5IRl8eIrg | no |

URL pattern: `https://www.youtube.com/watch?v=<Video ID>`

**Caption spelling note.** The source captions are auto-generated. The same term appears under many spellings: "FFEG / FFG / FVG / F50G / FFPG" all mean FFVG (first fair value gap); "MAC / MACD / MEC / mech" all mean the mech model; "sweat / swipe / swept / sweep pointer" and "sweep winner" all mean swept pointer; "on taps / untaps" means untapped FFVGs; "added a trim / out of the trim" means additive trim.

---

## 2. Instruments, data, timeframes

- **Markets:** Nasdaq-100 and S&P 500 futures. Signals are read on the minis (NQ, ES); he executes everything on the micro Nasdaq (MNQ) regardless of which index gave the signal `[E1 13:22]` `[E5 2:26]`. Micros can print signals the minis don't; trust the minis `[E13 34:00]`.
- **Both indices are required.** Every decision cross-checks NQ against ES `[E6 20:31]` `[E7 17:13]` `[E15 0:54]`.
- **Base chart:** 5-minute. No higher-timeframe bias of any kind `[E1 27:33]` `[E3 12:34]`.
- **Zone timeframes:** 1, 2, 3, 4, 5-minute `[E5 6:06]`.
- **Entry-signal timeframes:** 3, 4, 5, 6-minute as standard. 1–2 minute signals appear in chop and are a warning sign. 7-minute exists `[E6 18:21]` `[E10 15:17]`.
- **Trade duration:** typically 15–60 minutes `[E5 4:23]` `[E10 15:30]`.
- **Minimum data to backtest:** 1-minute OHLCV for NQ and ES over the same period, from which 2/3/4/5/6-minute bars are aggregated. Bar boundaries must match the charting platform's (TradingView anchors intraday futures bars to the session open at 18:00 New York, so for example a 4-minute bar straddles the 9:30 open as 9:28–9:32). **This alignment changes which candles qualify as "pointers" and must be stated as an assumption.**
- **Contract rolls:** zones do not carry across the quarterly roll gap; he manually offsets his indicator `[E7 21:44]`. Use back-adjusted continuous data or reset zones at roll.
- **All times below are New York time.**

---

## 3. Building blocks (definitions)

### 3.1 Sweeps and swing terminology `[E2]` `[E3]`
- **High-resistance (external) high/low:** a swing extreme whose wick took out a prior swing extreme `[E2 1:09]` `[E3 5:47]`.
- **Sweep:** price trades through a prior high/low. Buy-side = above, sell-side = below `[E3 3:10]`.
- **Fail sweep:** price fails to exceed the prior external extreme `[E2 1:43]`.
- **Change in character:** candle *close* through an external low/high. Fail sweep + change in character = "change in state of delivery". Background concept only — not an entry `[E2 7:03]`.
- No session-high/low or daily-level bias: any high or low can start a move `[E3 17:39]` `[E3 21:08]`.

*Ambiguity:* no pivot/fractal length is ever given. → parameter `SWING_N` (default: a 3-bar fractal on the 5m; test 2–5).

### 3.2 Fair value gap (FVG) `[E4 18:21]`
Three consecutive candles. Bullish FVG exists when candle 3's low is above candle 1's high; the zone is (candle-1 high, candle-3 low). Bearish is the mirror.

Reactions to an FVG `[E4 20:16]`:
- **validation** — price respects it and continues;
- **mitigation** — price trades through it and carries on;
- **inversion** — a candle *closes* beyond the far side;
- **proper inversion** — an inversion that also leaves a new opposite FVG.

### 3.3 First fair value gap (FFVG) — his supply/demand zone `[E5 3:07]`
After each sweep-type swing low (or high), the **first FVG to form on each of the 1, 2, 3, 4 and 5-minute charts** as price leaves that extreme. Up to five nested zones per swing, formed smallest timeframe first `[E5 6:06]` `[E5 8:56]`. Bullish FFVGs sit above a swept low (demand); bearish below a swept high (supply).

*Ambiguity:* how soon after the extreme the "first" FVG must appear, and whether every swing or only sweep-type swings qualify. → default: only swings that took out a prior swing; first FVG on each timeframe formed after the extreme bar and before the next opposing swing.

### 3.4 Inverse FFVG (IFFVG) `[E5 12:08]`
An FFVG that price has closed through. It then acts for the opposite side. FFVGs and IFFVGs are used identically `[E5 18:21]`. Ignore IFFVGs created by a news spike `[E11 33:45]`.

### 3.5 Tapped vs untapped `[E7]`
- **Untapped:** price has not traded back into the zone since it formed (or since it was inverted) `[E7 2:39]`.
- **Tap:** price trades into the zone.
- An FFVG that has just been closed through becomes an IFFVG that is itself *untapped* until price returns to it `[E9 8:09]` `[E14 9:30]`.
- **Self-made untapped:** a brand-new untapped set created by the current move (often 1-minute) `[E7 16:07]` `[E12 55:25]`.
- Untapped zones are the **draws on liquidity**: they define targets and set bias `[E7 3:31]` `[E7 16:48]`. Tapped zones are "traffic" in between `[E10 20:01]`.

### 3.6 Inefficient break `[E6 4:31]`
A candle that **closes beyond the previous candle's wick** (i.e. a close over the prior high or under the prior low). Applied to a zone: a candle on the zone's own timeframe closes through its far edge, which removes the zone `[E10 25:42]`.

### 3.7 Pointer — the entry trigger `[E6 16:00]`
A candle that **closes inside the wick of the previous candle** rather than beyond it, while moving away from an FFVG/IFFVG. He compares the look to an engulfing candle `[E6 17:19]`.

- **Reading A (default):** bullish pointer = close is above the previous candle's body top and at or below the previous candle's high. Bearish = close below the previous body bottom and at or above the previous low.
- **Reading B (looser):** any candle in the trade direction whose close does not exceed the previous candle's extreme.
- Engulfing comparison suggests the previous candle is normally the opposite colour. → optional filter `REQUIRE_OPPOSITE_PREV`.

A pointer not reacting to any zone is a **"structural pointer"** and is ignored `[E13 15:31]` `[E15 13:20]`.

### 3.8 Swept pointer `[E8 2:48]`
A pointer whose own wick also takes out a high (for a long) or low (for a short) in the trade direction before closing back inside the prior wick.
- **Swept-pointer test:** valid only once price subsequently trades through the pointer candle's own extreme. A wick through counted in his example. If price turns away from that extreme first, it failed `[E8 7:10]` `[E8 9:20]` `[E8 12:46]`.
- *Ambiguity:* whether "sweep" means beyond the immediately preceding candle only, or beyond an earlier swing. → default: pointer candle's high > previous candle's high (long).

### 3.9 Reaction to an untapped zone (the bias-setting signal) `[E7 4:11]` `[E14 46:12]`
A pointer **immediately following the tap** of an untapped FFVG/IFFVG, closing away from it. The tapping wick must be adjacent to the pointer candle; a pointer several candles after the tap does not qualify. The tap may be on a 1–2-minute zone while the pointer closes on a 3–6-minute bar `[E14 23:13]`.

→ default: zone first touched within the pointer bar or the bar before it, on either index.

### 3.10 Correlated vs SMT pointers `[E6 39:30]` `[E11 4:07]` `[E15]`
- **Correlated:** both NQ and ES print a same-direction pointer off their own untapped zones.
- **SMT pointer:** only one index prints it.
- Opposite-direction pointers on the two indices = no trade `[E13 31:20]`.
- *Ambiguity:* time tolerance. → default: other index prints a qualifying same-direction pointer on any 3–6m bar closing within ±1 five-minute bar.

### 3.11 Pointer range of control (PROC) `[E9]` `[E15]`
The price range of the bias-setting pointer candle (§3.9). One per index. Stays valid until a new opposite pointer-plus-untapped prints on that index `[E9 2:48]`. Swept pointers only establish one after passing the test `[E9 9:39]`.
- **Joined:** both indices' PROCs point the same way → strong conditions `[E15 6:39]`.
- **Disjointed:** they disagree, or only one index flipped → expect the move to fade `[E15 1:19]` `[E15 20:37]`.
- *Ambiguity:* high–low or body. → default: full high–low of the pointer candle.

### 3.12 PO3 — "pointer rule of three" (accumulation) `[E10 5:54]`
Three or more pointers validating zones on alternating sides without a sustained move. Counted live `[E12 8:47]`. The PO3 range is the span of those swings; its highs and lows are "associated with the chop" `[E10 16:47]`.
- *Ambiguity:* what resets the counter. → default: reset when price closes beyond the range and reaches the next untapped zone, or at session start.

### 3.13 Additive trim — the stop-loss substitute `[E10 22:51]` `[E13 35:59]`
- **Premise he asserts:** a pointer will reach the next FFVG set if no zone lies in between; an untapped reaction travels to the next untapped `[E10 19:35]` `[E7 11:35]`. He calls this guaranteed. **Test this claim directly — the whole risk model rests on it.**
- **Action:** when the path to the next FFVG set is clear on *both* indices `[E11 13:13]` `[E11 16:01]`, add contracts equal to the base size ("double my risk") and exit the added contracts with a limit at the next FFVG set.
- **Paused additive trim:** exactly one zone still blocks the path. Enter half; when a candle on that zone's timeframe closes through it, add the rest with the limit at the next untapped set `[E10 25:03]` `[E10 36:01]`. Gaps under roughly 10 NQ points are usually too fast to execute `[E13 29:24]`.
- Never add to an open trade otherwise `[E11 8:43]`.

### 3.14 EQ range `[E13 18:43]` `[E16 3:58]`
Never fully defined. Described as an indicator output built from the session (he says session volume) that marks the equilibrium inside the range; not available pre-market, appearing from the 9:30 open; unreliable after large gaps or very large sessions. Fallback he gives: use an untapped FFVG near the consolidation instead.
→ default: midpoint of the current session's high–low, recomputed each bar; "at EQ range" = nearest untapped FFVG to that midpoint in the trade direction.

### 3.15 Volume imbalances and standard gaps `[E4 30:36]` `[E4 40:22]`
Context only. A volume imbalance is a gap between one candle's close and the next open; a standard gap is a session-close-to-open gap. No bias toward either. Not needed for a first implementation.

---

## 4. Trading rules

### 4.1 When trading is allowed
| Rule | Detail | Source |
|---|---|---|
| Main window (what he backtests) | 9:30–15:50 | `[E11 2:07]` `[E12 4:20]` |
| Skip the 9:30 open candle | He calls it the "9:30 macro" and never trades it | `[E11 2:59]` `[E12 5:10]` |
| Hard flat time | Out by 15:50; no trading 15:50–16:15 | `[E1 42:33]` |
| Pre-market (live only) | Roughly 7:30/8:00–8:30 if no news; avoid holding through the open | `[E12 52:25]` `[E16 27:31]` |
| Other sessions | London from 03:00 and Asia from 18:00 are valid but de-emphasised; his own Asia cutoff is 21:00 | `[E1 41:30]` `[E1 43:22]` |
| Lunch | 12:00–13:00 slower, not excluded | `[E1 42:07]` |

### 4.2 News filter (Forex Factory)
- Never trade *during* a scheduled release or a speech; do trade news days `[E1 38:31]`.
- Red/orange-folder data release: no entries until it has printed — he waits about two 5-minute candles `[E12 5:10]` `[E13 4:37]`. In backtest: resume the next candle `[E14 36:52]`.
- Speeches/testimony (Fed chair, president): flat beforehand; resume 60–90 minutes later `[E12 13:22]` `[E14 36:52]`.
- 8:30 releases are covered by starting at 9:30 `[E12 42:10]`.
- Yellow-folder items ignored `[E12 20:18]`.
- Never hold a position through a release `[E10 2:56]`.

### 4.3 Entry
**Base signal:** a pointer (§3.7) on a 3–6-minute bar that is a reaction to an untapped FFVG/IFFVG (§3.9). Enter at the close of the pointer candle, in the direction away from the zone `[E6 28:18]` `[E7 4:11]`.

**Grades:**
| Grade | Conditions | Size |
|---|---|---|
| A+ / full | Plain (non-swept) pointer off an untapped zone on **both** indices | Full |
| Weak | SMT pointer (one index only) | Half |
| Weak | Swept pointer | Half at close; other half after it passes the test (§3.8) or after price closes out of the zone it is stuck in |
| Weak | Pointer printed after the untapped→untapped travel has already happened | Half |

Sources: `[E11 4:07]` `[E11 7:24]` `[E8 7:35]` `[E12 15:49]` `[E16 1:06]`. By Episode 16 he treats two-index agreement as close to mandatory.

**Second entry route — PROC retest:** with a valid PROC and no opposite pointer since, enter (or re-add) with a limit when price retraces into the PROC. This is how he explains moves that never print a fresh pointer, especially retraces into the 9:30 open off an overnight signal `[E9 5:07]` `[E9 15:25]`. Use the first pointer off the first untapped; prefer the lowest-timeframe pointer; avoid very wide ranges `[E9 8:22]` `[E9 20:10]`. He warns against placing these limits blindly: the risk is a deep retrace that builds a new untapped zone and flips the signal, and he reserves the technique for traders watching continuously `[E9 4:17]` `[E13 28:20]` `[E14 1:02:38]`.

### 4.4 Do not take the trade when
- The pointer is not reacting to an untapped zone (structural pointer) `[E15 13:20]`.
- It is a swept pointer running straight into an opposing untapped zone `[E13 8:34]` `[E14 34:39]`.
- It is a swept pointer into a thick stack of zones (many still to be closed through) `[E8 16:48]` `[E11 12:21]`.
- Zones lie in the path on the *other* index `[E11 16:01]`.
- The other index printed a pointer the other way, or the PROCs are disjointed `[E13 31:20]` `[E15 20:37]`.
- PO3 is active (see §4.8).
- Distance from entry to where an opposite pointer could form at the nearest opposing untapped is large relative to the account (examples: 30–40 and 85 NQ points) — size down or skip `[E11 4:47]` `[E11 34:12]`.
- Price is at all-time highs (§4.9).
- A release or speech is imminent.

### 4.5 Position size
- His demonstration scheme is a **"5–10 split"** on MNQ: 5 contracts weak, 10 full, +10 on an additive trim `[E11 4:22]` `[E11 27:18]`. He later recommends even splits (2/4/6, 6/12) so trims divide cleanly `[E14 54:34]` `[E15 6:51]`.
- Account-dependent discretion: with under ~$2,000 of drawdown room take only clean setups; with ~$5,000+ of cushion take every pointer `[E11 24:09]` `[E13 12:21]` `[E13 44:45]`.
- MNQ is $2 per index point per contract, so 5 contracts = $10/point, 10 = $20/point.

### 4.6 Managing an open trade
**Partial exits (trims).** Trims reduce exposure; they are never the full exit `[E16 2:37]`.
1. **TP1:** the first FFVG ahead after the new leg, which is often the untapped FFVG at EQ range. Clip a small fixed amount — 2 (sometimes 3) contracts of 5–10. Use whichever index reaches its zone first `[E11 5:51]` `[E12 8:59]` `[E16 1:45]`.
2. **SMT target:** if the trade started from a sweep that only one index made, the opposite swing extreme (either index) is a further target; exit at the FFVG just before it `[E11 6:32]` `[E11 28:36]` `[E14 10:22]`.
3. **Additive trims** (§3.13).
4. **Key-level trims (discretionary, Episode 16):** further 2-contract clips at untapped zones that coincide with both a break-of-structure deviation level (fib tool anchored sweep→break, 0.5 steps to 4.5) and a low-volume node on a session volume profile `[E16 5:57]`–`[E16 20:26]`. He concedes the deviation levels have no real basis `[E16 21:29]`. Leave out of a first implementation.

**De-risking.**
- A swept pointer *against* the position on either index: drop to the 1-minute. If a 1-minute FVG forms against you off that sweep, cut 1–2 contracts (roughly half on a weak position). If the swept extreme breaks your way, do nothing `[E11 9:35]` `[E12 7:29]` `[E14 13:10]`.
- A pointer against you off an already-tapped zone: optional light trim; not an exit `[E12 10:18]` `[E14 28:22]`.
- Several pointers printing right after entry is a bad sign; he wants one-directional price `[E12 24:28]`.

**Refill.** After trimming, re-add with a limit at the entry/PROC if price retraces there and no opposite pointer has printed on either index `[E9 3:40]` `[E12 44:41]`.

### 4.7 Full exit
1. **A pointer reacting to an untapped zone against the position**, on either index, any of the 3–6-minute bars (1–2-minute in chop). Close everything; optionally reverse `[E7 6:09]` `[E11 28:10]` `[E12 8:20]`.
2. **15:50** time stop.
3. **Before a release or speech.**
4. **PO3 declared** while in a marginal trade `[E12 34:06]`.

Bias itself only changes on (1). Until then he is still "looking for" the same direction even if flat `[E8 9:45]` `[E9 1:17]`.

### 4.8 PO3 mode
Once three alternating pointers confirm accumulation (§3.12), **no new trades** until one of:
- **(a) Outside manipulation:** the index takes a high or low that is *not* part of the PO3 range, with an untapped zone and a pointer there. A sweep made by only one index (SMT) qualifies `[E10 16:47]` `[E10 34:57]`. Levels that belong to the PO3 range do not `[E13 13:35]` `[E10 39:03]`.
- **(b) Breakout continuation:** a pointer off an untapped zone, targeting an untapped zone, with a clear path so an additive trim is available `[E10 18:29]` `[E10 21:06]`.

Optional "PO3-only trade": pointer off an untapped with a single limit exit at the next untapped, small size, nothing more `[E7 12:37]` `[E14 53:29]`.

He attributes essentially all losses to trading inside accumulation; typical loss cited $27–$300 on a 5-contract MNQ position `[E12 40:16]` `[E12 59:57]`.

### 4.9 All-time highs
Above prior all-time highs there are no zones to reference. Target the high and stop. Trade again only if a self-made untapped zone and pointer appear `[E13 17:25]` `[E14 11:06]` `[E15 7:20]`. Standard gaps matter only here: don't trade inside never-before-traded gap space `[E4 41:00]`.

---

## 5. What can and cannot be coded

| Component | Status |
|---|---|
| FVG, inversion, inefficient break | Fully objective |
| Pointer / swept pointer / swept test | Objective once Reading A/B and bar alignment are fixed |
| FFVG sets | Objective once swing definition (`SWING_N`) is fixed |
| Tapped / untapped state | Objective; needs careful state tracking on 5 timeframes × 2 indices |
| Reaction-to-untapped adjacency | Objective with a tolerance parameter |
| Correlated vs SMT | Objective with a time-tolerance parameter |
| PROC, joined/disjointed | Objective |
| PO3 counter and range | Mostly objective; reset rule is an assumption |
| Session and news filters | Objective given a historical calendar |
| Additive / paused additive trim | Objective |
| TP1 at EQ range | Needs the §3.14 assumption |
| "Thick stack of zones", "too wide", "looks choppy" | Subjective → parameterise (zone count in path; max PROC width) |
| Buffer-based "take it or skip it" | Subjective → run two modes: *selective* and *take-everything* |
| Deviation + low-volume-node trims | Subjective → omit initially |
| "I just don't like it" skips | Not codable. Expect the coded version to take trades he would pass on. |

---

## 6. Suggested defaults (my assumptions — vary them)

| Parameter | Default | Test range |
|---|---|---|
| `SWING_N` (fractal half-width, 5m) | 3 | 2–5 |
| Pointer reading | A | A, B |
| `REQUIRE_OPPOSITE_PREV` | off | on/off |
| Swept definition | beyond previous candle | previous candle / prior swing |
| Tap-to-pointer adjacency | same bar or previous bar | 0–2 bars |
| Correlation tolerance | ±1 five-minute bar | 0–2 |
| Entry timeframes | 3, 4, 5, 6m | 5m only; 3–6m |
| Intraday bar anchor | 18:00 session open | 18:00; 09:30 |
| PROC definition | pointer candle high–low | high–low; body |
| Max PROC width for refill | 25 NQ pts | 15–40 |
| "Thick stack" threshold | >2 zones in path | 1–4 |
| TP1 clip | 20% of position | 20–30% |
| Additive add | +100% of base | +50–100% |
| News lockout (release) | from T−5 min to T+10 min | to T+5…T+15 |
| News lockout (speech) | T−10 min to T+90 min | +60…+120 |
| Trading window | 09:35–15:50 | add 08:00–08:25 |
| Costs | your broker's/prop firm's actual MNQ commission per side + 1 tick (0.25 pt) slippage per side | 0–2 ticks |
| Catastrophic stop (comparison run only) | none | 40 / 60 / 100 NQ pts |

---

## 7. Suggested build order

Build in layers so each rule's contribution is measurable.

- **V0 — primitives and audit.** Aggregate bars; detect FVGs, FFVG sets, tapped state, IFFVGs, pointers on both indices. Before any P&L, export a labelled chart or table for the dates in §9 and compare visually with what he marks on screen. If the zones don't match, nothing downstream is meaningful.
- **V1 — core.** Enter on an untapped-reaction pointer (either index), fixed size; exit on opposite untapped-reaction pointer or 15:50. No trims.
- **V2 — quality.** Add correlated/SMT/swept grading and sizing, the swept-pointer test, and the skip rules in §4.4.
- **V3 — PO3 filter.** Add the counter and the two release conditions. Compare V2 vs V3 to see whether the filter does what he claims.
- **V4 — trims.** TP1, additive and paused additive trims, de-risk on opposing swept pointers.
- **V5 — PROC retest entries and refills.**

**Specific claims worth testing in isolation:**
1. After a qualifying pointer with a clear path, how often does price reach the next FFVG set before retracing through the entry? (He says always.)
2. Does a reversal ever occur without an untapped-reaction pointer on either index? (He says never, outside news.)
3. Win rate and expectancy of correlated vs SMT vs swept signals.
4. Distribution of adverse excursion with no stop.
5. Share of total loss occurring while the PO3 flag is on.

**Pitfalls.**
- **Look-ahead:** an FFVG only exists after its third candle closes; a pointer only exists at bar close; "first" FVG status must not use later bars. Swing confirmation needs `SWING_N` bars after the extreme.
- **Mixed timeframes:** evaluate everything on a 1-minute clock; a 5-minute pointer is known only at the 5-minute close.
- **Fills:** limit exits at zone edges should require trade-through, not touch, in at least one run.
- **Prop-firm realism:** his results assume trailing-drawdown accounts (he mentions about $2,000 of drawdown on the accounts he uses) and payout caps. Simulate a trailing-drawdown breach as account death, since a no-stop method is exposed to it.
- **Sample:** his on-screen sessions are a handful of days in January–June 2026, a strongly trending period at all-time highs. Test across different regimes.
- **Multiple testing:** with this many free parameters, fix the defaults first, hold out data, and report the spread across the parameter grid rather than the best cell.

**Report at minimum:** trades, win rate, average win/loss in points and dollars, expectancy per trade, profit factor, max drawdown, max adverse excursion distribution, time in trade, results by grade, by hour, by session, by PO3 state, with and without costs.

---

## 8. Open questions the videos do not answer

1. Exact pivot rule that qualifies a swing for an FFVG set.
2. Whether a pointer's "previous wick" test uses the body-to-extreme wick only (Reading A) or the whole candle range.
3. How long after formation an untouched zone stays relevant (he implies indefinitely; the indicator has a finite history).
4. Exact construction of EQ range.
5. How close in time two indices' pointers must be to count as correlated.
6. What resets the PO3 count.
7. Whether exits require the opposite pointer on the traded index or accept either (demonstrations accept either).
8. Stated but unpublished: "13 or 14" pointer rules `[E6 15:09]`; only some are covered. Episodes on sizing and prop-firm mechanics were promised and not found `[E15 0:26]`.
9. His separate private strategy ("Squid") is explicitly not taught and overlaps his live results from October 2025 on `[E1 1:12]` `[E1 15:05]` — his reported income is not attributable to this model alone.

---

## 9. On-screen sessions usable as sanity checks

Dates are 2026, New York session, NQ 5-minute with ES cross-checks. Outcomes are his statements on a 5–10 MNQ split and are unverified.

| Date | Episode | What he says happened |
|---|---|---|
| Mon 2 Mar | E12 | 10:00 release then 11:00 speech; small long then a short around the release, an afternoon long; about +$200 overall; says he missed the day's best long |
| Tue 3 Mar | E12 | No news; early long exited on a 3m pointer and re-entered, then ran ~170 pts on 5 contracts; about +$1,600; a later breakout continuation lost about $200 |
| Wed 4 Mar | E12 | 10:00 release; repeated failed swept pointers, PO3 called; later short; about +$1,000 |
| Thu 5 Mar | E12 | 8:30 release; long then shorts with a ~$500 additive trim; about +$3,000 |
| Fri 6 Mar | E12 | 8:30 release; PO3 early; one long; about +$500 |
| Fri 9 Jan | E13 | 8:30 and 10:00 releases; chop/PO3; about break-even; all-time high reached |
| Mon 12 or Tue 13 Jan (he is unsure on screen) | E13 | Shorts including a ~$500 additive trim; he puts the session near +$3,000, then −$120; afterwards realises he had been reading the wrong month's calendar and that 13 Jan had releases at 8:30, 10:00 and 14:00 |
| Wed 14 Jan | E13 | 8:30 release; long about +$500; a good short skipped; PO3 later |
| Mon 9 – Tue 10 Mar | E15 | PROC joined/disjointed demonstration; no managed trades |
| Wed 22 Apr | E15 | Joined bullish PROCs into all-time high |
| June (mid-month) | E16 | Pre-market long from about 8:30 into the open, ~150 NQ pts, trimmed at three levels |

Other dates in Episodes 9–11 are not identified on screen.

---

## 10. One-paragraph summary of the method

Mark the first fair value gap that forms on each of the 1–5-minute charts after every sweep-type swing on both NQ and ES; track which of those zones (and their inverted versions) have not been revisited. When price taps an untouched zone and the very next 3–6-minute candle closes back inside the prior candle's wick, moving away from the zone, that sets direction; take it full size if both indices do it cleanly, half size if only one does or if the candle also swept a high/low. Hold until the same pattern prints the other way, taking a small partial at the first zone ahead and adding temporary extra size whenever the path to the next zone is empty. Stop trading when three such signals alternate without follow-through, until price takes a level outside that range. Skip the 9:30 candle and scheduled news, be flat by 15:50, and use no stop-loss.
