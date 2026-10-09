# Candidate gap-selection rule from the agreement audit (for confirmation, not a run)

Source: your answers to the 20 Run I audit charts (MNQ **5-minute**, `answers.csv`, scored in `audit_scored.csv`;
features measured from the Databento 5m bars). Result: 6 same gap, 6 another gap, 8 would not trade. Twenty charts
is a small sample, so each pattern below is a hypothesis for you to confirm or correct. Nothing is backtested until you
have answered, and the rule is then written for the **1-minute** chart you trade (section 5).

Terms: *age* = bars from the gap's third candle to the first close through its far edge (the inversion);
*close beyond* = how far the inversion candle closes past the far edge, in ATR(14); ATR sizes are the gap's height.

## 1. The 6 gaps you agreed with (audit_02, 03, 11, 13, 14, 15)

| Chart | Side | SMT | Zone | Gap size (ATR) | Age (bars) | Close beyond (ATR) | Note |
|---|---|---|---|---|---|---|---|
| 02 | L | Swing | 4H | 1.03 | 7 | 1.50 | entry one bar earlier |
| 03 | L | PDL | 15m | 0.33 | 5 | 0.15 | "low confidence; took a while to inverse" |
| 11 | L | PDL | 15m | 0.71 | 4 | 1.68 | entry one bar earlier |
| 13 | L | Swing | 15m | 0.36 | 4 | 0.17 | |
| 14 | S | PDH | 1D | 0.64 | 2 | 1.29 | entry one bar earlier |
| 15 | L | Swing | 15m | 0.55 | 4 | 0.68 | |

What they have in common: **inverted within 2–7 bars of forming (median 4)**, and none has a pivot SMT in its TradingView tag: 3 are
PDH / PDL and 3 are swing sweeps (on audit_02 the local engine reads a pivot SMT where the tag says Swing). Gap size ranges from 0.33 to 1.03 ATR.

**Q1.** Is "the gap is closed through within about 5 bars of forming" part of your rule? If so, what is the limit on the
1-minute chart: 5 bars, or a fixed number of minutes?
**Q2.** audit_03 took 5 bars and you marked it low confidence. Where is your cut-off: 5 bars, or does a slow inversion
only lower your confidence?

## 2. The 6 gaps you preferred to the indicator's (audit_05, 07, 09, 12, 16, 20)

| Chart | Your gap | Indicator's gap | Your gap: size / age / close beyond | Indicator's: size / age / close beyond | Your entry vs the indicator's |
|---|---|---|---|---|---|
| 05 | 08:10 bull | 07:40 bull | 0.08 / 1 / 0.48 | 0.46 / 9 / 0.29 | 3 bars earlier |
| 07 | 01:15 bear | 01:10 bear | 0.19 / 2 / 1.09 | 1.35 / 9 / 0.56 | 6 bars earlier |
| 09 | 04:15 bull | 04:05 bull | 0.23 / 3 / 0.04 | 0.49 / 8 / 1.00 | 3 bars earlier |
| 12 | 20:10 bear | 20:05 bear | 0.34 / 2 / 1.12 | 0.51 / 4 / 0.53 | 1 bar earlier |
| 16 | 01:50 bull | 01:40 bull | 0.26 / 5 / 0.48 | 0.22 / 8 / 0.27 | 1 bar earlier |
| 20 | 03:25 bull | 03:05 bull | 0.45 / 3 / 0.14 | 0.47 / 13 / 0.31 | 6 bars earlier |

What your gap has that the indicator's did not, in all 6:
- **It formed later.** It is the newest gap against the move: 5 to 30 minutes after the indicator's.
- **It was closed through sooner:** age 1–5 bars (median 2.5), against 4–13 (median 8.5) for the indicator's gap.
- **So you enter earlier,** 1–6 bars before the indicator's entry.

What it does not need:
- **Size or body.** 4 of the 6 fail the Loose filter, so they were not drawn on the charts: 08:10, 4:15, 20:10 and 3:25
  were not printed labels. 08:10 is 0.08 ATR high, and 04:15, 20:10 and 03:25 fail the body or range test on the candle
  that completes the gap.
- **A strong inversion close.** On audit_09 the close was only 0.04 ATR beyond the edge.

**Q3.** Candidate rule: *take the most recent gap against the move that is closed through, with no minimum size and no
body filter.* Is that how you choose? If you do use a size or body test, what is it?
**Q4.** When two gaps are stacked (audit_07: 01:10 and 01:15, both bear gaps, the 01:15 one closed through 6 bars sooner), do you always take the
newer one, or the one whose far edge is closed through first?
**Q5.** The indicator only counts gaps that formed within 30 bars before the inversion. Does your rule need the gap to
form after the sweep? Where the sweep bar is known, your gaps formed 1 bar before to 3 bars after it (audit_05, 09, 12,
16). The indicator's gaps formed up to 7 bars before it.

## 3. The 8 days you would not trade (audit_01, 04, 06, 08, 10, 17, 18, 19)

On the same simulation basis the indicator made **+675** on these days (3 targets, 5 stops).

| Chart | SMT | Zone | Time | Indicator's gap size / age / close beyond | Possible reason |
|---|---|---|---|---|---|
| 01 | Swing | 15m | 03:35 | 0.17 / 5 / 0.23 | small gap, weak inversion close |
| 04 | **Pivot** | 15m | 08:30 | 0.66 / **14** / 1.97 | your note: "not an IFVG at all"; the gap formed at 20:30 the evening before, across the CME outage |
| 06 | Swing | **NDOG** | 18:20 | 0.33 / 3 / 0.37 | 20 minutes after the session open; NDOG zone; 8 opposing gaps in view |
| 08 | Swing | 15m | 04:55 | 0.43 / **9** / 0.24 | slow and weak inversion |
| 10 | Swing | 15m | 02:30 | 0.83 / 6 / 1.09 | not clear from the measures; 8 opposing gaps in view |
| 17 | **Pivot** | 15m | 14:30 | 0.32 / **12** / 0.05 | pivot SMT, slow and weak inversion |
| 18 | **Pivot** | 15m | 00:25 | 0.15 / **23** / 0.65 | pivot SMT, gap 2 hours old |
| 19 | Swing | 15m | 16:45 | 0.91 / **9** / 0.18 | 15 minutes before the 17:00 halt; slow and weak inversion |

What could disqualify a day, from these 8:
- **Age.** 5 of the 8 have an age of 9 or more, while no agreed or preferred gap is older than 7.
- **Pivot SMTs.** All 3 pivot-SMT trades among the 20 are here. Every PDH / PDL SMT (6) was taken.
- **A weak inversion close.** 5 of the 8 close ≤ 0.37 ATR beyond the edge, against 2 of the 6 agreed gaps.
- **Time of day.** One is at 18:20, just after the reopen, and one at 16:45, just before the halt.

**Q6.** Do you use the swing-to-swing "pivot" SMT at all, or only a sweep of a marked level (PDH / PDL, a prior swing
high or low)?
**Q7.** Is there a maximum gap age beyond which it is "not an IFVG at all" (audit_04)? Does a gap survive a session
break or a halt?
**Q8.** Do you avoid times of day: the first minutes after the 18:00 reopen, or the last 15–30 minutes before the
17:00 halt? Which other windows do you trade or skip (London, NY AM, NY PM, Asia)?
**Q9.** audit_10 has a strong, quick inversion and a swing SMT, yet you passed. What ruled it out: a busy chart (8
opposing gaps in view), the zone, the location in the range, or something else?
**Q10.** Is a close that only just clears the far edge (audit_09 at 0.04 ATR, audit_17 at 0.05 ATR) enough for you?

## 4. Entry timing: the three "one bar earlier" answers

| Chart | The bar before the indicator's entry |
|---|---|
| 02 | Closed at 24,870.75, **80 % through the gap** (far edge 24,872.50), not beyond it |
| 14 | Closed at 29,731.25, **98 % through the gap** (far edge 29,730.75), not beyond it |
| 11 | Closed beyond the gap: the inversion itself. The indicator waited one bar for the SMT to confirm (3 bars after the sweep) |

**Q11.** Do you enter on a close most of the way through the gap, without a close beyond it? If so, from what share of
the gap (80 %? the CE? within a few ticks of the far edge)?
**Q12.** Do you wait for anything after the sweep before entering (the indicator's 3-bar SMT confirmation), or is the
inversion close the entry?

## 5. Translating to the 1-minute chart (you trade 1m; these charts were 5m)

**Q13.** Are the gaps taken from 1m candles, with the rule above applied as written (newest gap, closed through
quickly)? And the "quickly" limit: in 1m bars or in minutes?
**Q14.** Which HTF zones must the gap sit in on the 1m: the same 15m / 1H / 4H / D FVGs and NDOG, or others (5m FVGs)?
Must the gap overlap the zone, or only the sweep?
**Q15.** SMT on the 1m: is it ES's failure to take the same level (PDH / PDL, a 1m or 5m swing) at the time MNQ takes it?
What swing size defines a level on the 1m (the indicator uses 5 bars each side)?
**Q16.** Stop and target: keep the sweep extreme + 2 ticks and a fixed 3 R, or do you use another target (the opposite
liquidity, a fixed R)? And do you close by time (the indicator: 200 bars, about 3.3 hours on 1m)?
**Q17.** How many trades a day at most, and do you skip a signal while a trade is open?

Once you answer, the answers become the pre-registered spec, and it runs once on the 1m bars with the usual criterion:
≥ 6 of 8 positive years, ≥ +0.05 R per trade, the sign holding on neighbouring timeframes, and a label-shuffle check on
the best split.
