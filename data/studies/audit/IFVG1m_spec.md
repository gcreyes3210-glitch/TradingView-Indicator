# IFVG-1m: the trader's IFVG rule, pre-registered (from the audit answers)

Source: the trader's answers to the 17 questions in `selection_spec.md` (2026-09-24). Where an answer was "no set
rule", the value below is the one fixed for the run; it is written here BEFORE the run and is not tuned afterwards.
Neighbouring values are listed only as robustness checks, not as a search.

## Trader's answers, verbatim in substance
1. Inversion within ~5 bars of the gap forming: yes, no set rule, 5 bars is a fair limit.
2. Slow inversion lowers confidence rather than a hard cut; on the 5m a 25-minute inversion is "not a strong enough move"; would have taken a 1m inversion instead.
3. Newest gap against the move, no size or body test, but the gap "has to be big enough to see" without zooming.
4. Stacked gaps: the one whose inversion candle is strong; a 1m IFVG would have been preferred.
5. The FVG may form before the sweep; the inversion (IFVG) should be on the sweep candle or after it.
6. SMT: both pivot SMT and marked-level sweeps, mainly pivot SMT.
7. A gap older than ~30 minutes is not an IFVG; a gap does not survive a session break.
8. Sessions: NY AM 06:30–08:00 PT (09:30–11:00 ET); Asia 15:00–21:00 PT (18:00–00:00 ET) as a secondary interest.
9. audit_10 skipped for a ~100-point stop; would look for a lower-timeframe IFVG instead.
10. A close that barely clears the far edge is enough if the candle is strong.
11. A close ~80 % through the gap without a close beyond it is enough if the candle is strong.
12. The inversion close is the entry; no wait for SMT confirmation after the sweep.
13. 1m gaps, limit in bars; likes the V-shape reversal.
14. HTF zones: 15m, 1H, 4H, D, NDOG all count; either the gap or the sweep may overlap the zone.
15. SMT levels from 5m or 15m swings, 1 bar each side; 1m swings are noise.
16. Stops and targets: no fixed rule; wants to try opposite liquidity and 1:2 as well as 3 R.
17. Trade limits: try max 3 per day, stop after 1 win or 2 consecutive losses; skip a new signal while a trade is open (the "only if the open trade is stronger" comparison is not encodable and is replaced by always skip).

## The rule (MNQ 1m bars, ES 1m bars for SMT, Databento, house fills, $1/side + 1 tick)
**Session.** Primary: entries 09:30–11:00 ET, flat at 12:00 ET. Secondary report: entries 18:00–00:00 ET, flat at 02:00 ET. No entry within 10 minutes after the 18:00 reopen. All state (gaps, sweeps, SMTs) resets at the 17:00 halt.

**Gap.** A 1m FVG (bar[i-2].high < bar[i].low bullish; mirror bearish) with height ≥ 1.0 point (4 ticks). The gap may form before the sweep. A gap expires 30 bars after its third candle, or at the session break.

**Sweep + SMT (required).** Levels: 5m swing highs/lows with 1 bar each side (3-bar fractals), plus PDH/PDL. MNQ trades beyond the level (> 2 ticks) on a 5m bar while ES does not trade beyond its own corresponding level within ±1 5m bar. A pivot SMT (MNQ higher high / ES lower high on the same 5m swing, and the mirror) counts equally. The sweep bar on the 1m is the first 1m bar that trades beyond the level.

**Inversion = entry.** Against a bearish sweep (sweep of a high → short): the NEWEST bullish 1m FVG below the sweep extreme that is still alive; entry at the close of the first 1m bar, on or after the sweep bar, that either (a) closes below the gap's low, or (b) closes ≥ 80 % of the way down through the gap AND is a strong candle (body ≥ 60 % of range and range ≥ 1.0 × ATR(20) on 1m). The inversion bar must be within 5 bars of the gap's third candle (freshness) — a gap whose first inversion comes later is discarded and the next-newer gap is considered. Mirror for longs.

**HTF zone (required).** The gap or the sweep extreme overlaps an unfilled 15m, 1H, 4H or daily FVG or the NDOG, as the indicator defines them (Run I lifecycle, 50 % CE eligibility).

**Stop.** Sweep extreme + 2 ticks. Skip if the stop distance exceeds 2.0 × 5m ATR(14) (answer 9).

**Exits (three pre-registered variants, one run each).** T3: fixed 3 R. T2: fixed 2 R. TL: opposite liquidity = the nearest 5m 3-bar fractal beyond the entry on the profit side formed since the session open, skip if < 1.0 R away. All variants: flat at the session's flatten time.

**Trade management.** Max 3 entries per session; stop for the session after the first winner or after 2 consecutive losers; no new entry while a trade is open.

**Zone variants.** Z-all (15m/1H/4H/D/NDOG) is primary. Z-high (1H/4H/D only) is the only secondary, because the trader named it; it is NOT supported by IFVG7 (1D +0.074 R on 45 trades was not adopted), so it must pass on its own.

## Runs and criterion
Six runs (3 exits × 2 zone sets) on the NY AM session, full span 2019-06 → 2026-09. Criterion per run, fixed: ≥ 6 of 8 positive years, ≥ +0.05 R per trade, both halves (2019–2022, 2023–2026) non-negative, and the sign holding on the neighbours (freshness 3 and 8 bars; min gap 2 ticks and 2 points; stop cap 1.5 and 3.0 ATR). Six comparisons → a run counts only if its best-split shuffle p < 0.05/6. The Asia session is reported for the primary run only, not tested for adoption. Report per run: n, net, R/trade, win %, PF, DD, by year, long/short, by zone, by SMT type (pivot vs level), exit mix, how many sessions hit the 3-trade / 1-win / 2-loss stops, and a funnel: sweeps+SMT → gap alive → fresh inversion → HTF zone → stop cap → trades.

Not encoded, stated: "strong move" as a feeling, the V-shape, "stronger trade" comparison for overlapping signals, and visibility of a gap beyond the 1-point minimum. If the rule fails, the log must say which of these the trader believes carries the edge, for a forward trade journal to test.
