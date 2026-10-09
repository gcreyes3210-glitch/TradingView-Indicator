# YT3 — NQSimon's standard-deviation method, one mechanical reading, pre-registered 2026-10-09 (before any YT3 code)

Source: NQSimon (@nqsim0n), "how i made 54,772$ in 2 weeks (FULL STRATEGY)" https://www.youtube.com/watch?v=Xc6RWjw2Ego,
"how to use standard deviation to find precision entries" https://www.youtube.com/watch?v=G4ZE7filS28, "How I make 5
figures a month using Standard Deviation" https://www.youtube.com/watch?v=L10KJTdTUJQ. Sourcing notes:
`data/studies/yt1/research/F_nqsim0n.md`.

**What he states:** an accumulation, a manipulation that runs past it, and a reversal where the manipulation reaches
the −2 to −2.5 or the −3.5 to −4.5 "standard deviation" of a leg; a limit entry there in the New York morning; a
10-point stop; a target at the session high (low for shorts); no trade without a leg; stop trading once price runs
through the −4 zone.
**What he leaves to the eye, and the reading used here (R):** which leg, how the tool is anchored, the session clock
times, the daily bias, the daily-gap overlap and the order block or rejection block he enters on. None of his three
videos defines them and they disagree on the entry. So this tests ONE mechanical reading of his method, not his trading.
A fail here does not show his discretionary version fails; a pass would need his own chart check before it meant anything.

**Data, engine, fills, days not traded, R, order of work, look-ahead test:** as `YT1_SPEC.md`.

## N01 — Asia-range deviations, New York morning reversal
- **Leg (R):** the Asia range, 20:00–23:59 of the previous evening, wick high H to wick low L, W = H − L (the standard
  ICT form of the tool; he picks a 15-, 5- or 1-minute leg by eye). No trade if W < 10 points.
- **Manipulation side:** from 00:00, the first side of that range to trade at least 1 tick beyond it. Low first → longs
  only that day; high first → shorts only. Neither by 09:30 → no trade.
- **Levels (long day; shorts mirror above H):** Z2 = L − 2 W, Z4 = L − 4 W, Void = L − 4.5 W, each on the tick.
- **Entries:** a buy limit at Z2 and a buy limit at Z4, each resting 09:30 → 11:29 and each only if its level has not
  traded between 00:00 and 09:29 *(R: he enters at a lower-timeframe block inside the zone; the zone's first level
  stands in for it)*. Any unfilled order is cancelled once price trades at Void. One position at a time, at most 2 trades.
- **Stop:** 10 points from the entry price. **Target:** H (the session high). Otherwise the flat bar.
- **Neighbours:** stop 7.5 points, 15 points.
- **Reported:** `scaled` = stop 0.04 % of the entry price (10 points at 25,000) instead of 10 points; `bias` = longs
  only when the previous cash session closed above the high of the one before it, shorts only when it closed below
  the low of the one before it (his one stated bias example).

**Criterion:** the usual criterion of YT1 with the p-value level counted over everything tried so far,
p < 0.05 / 83 = 0.00060. Candidate = every criterion but that level, with p < 0.05. Under 100 trades = not enough data.
