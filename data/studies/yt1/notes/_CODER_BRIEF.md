# Brief for a YT1 coder

## What this is
A trader asked for as many YouTube-taught day-trading strategies as possible to be backtested on MNQ futures while he
sleeps. The rules were written down in advance in `YT1_SPEC.md` (pre-registered: the text was fixed before any code
ran). You are one of several coders, each turning a handful of those rules into code on a shared, already-calibrated
harness. Someone else runs your code afterwards on data you cannot see. What matters is that your code does exactly
what the spec text says, with no knowledge of the future, so that the result (most likely a loss, and that is a
perfectly good answer) can be trusted.

## Where you work
Everything is in `/home/claude/work/yt1/lab` (run commands from there). The data in `lab/data` stops at 2022-12-31 on
purpose: that is the in-sample period. Do not look for, read or reference any other data directory on this machine.

- `YT1_SPEC.md`: read "Common rules" and "Criterion and order of work" in full, then your own entries.
- `data/studies/yt1/research/*.md`: the sourcing notes behind each entry, for background when a spec line is terse.
- `tools/yt1/core.py`: the harness. Read the module docstring, `Ctx`, `simulate` and `run_orders` docstrings.
- `tools/yt1/ind.py`: indicators (TradingView definitions). Use these rather than writing your own where one exists.
- `tools/yt1/s_Z00.py`: the pattern every module follows. Read it first.
- `tools/yt1/run.py`: how modules are run.

## What to deliver for each rule
`tools/yt1/s_<ID>.py` (for example `s_A01.py`, `s_C19a.py`) defining:
- `ID`, `NAME`
- `VARIANTS`: a dict whose first three keys are `base`, `nb1`, `nb2` (the rule and its two neighbours, in the order
  the spec lists the neighbours), followed by any "Reported" alternatives under the names the spec gives them.
  Each value is the keyword arguments for that variant.
- `orders(ctx, **params)`: returns every candidate order as a dict of `core.simulate` keyword arguments.
- `trades(ctx, **params)`: returns trade dicts, normally `core.run_orders(ctx, orders(ctx, **params), ...)`.

And `notes/<ID>.md`: short, with (1) any reading you had to add beyond the spec text, (2) any coding error you found
and fixed after first seeing results, and what the numbers were before and after, (3) what your hand check of trades
showed, (4) the final in-sample output lines pasted from the run.

For a claim check (K entries): `tools/yt1/k_<ID>.py` (for example `k_E01.py`) with `NAME` and `measure(ctx) -> dict`
(JSON-serialisable: counts and rates, with the claimed figure next to each measured one), run with
`python3 tools/yt1/run.py K-E01 --phase is`, plus a `notes/K-<ID>.md`.

## The steps, for each rule
1. Write the module from the spec text alone. Decide every reading before you run anything.
2. `python3 tools/yt1/run.py <ID> --phase is --show 8`
3. Hand-check at least three of the printed trades: print the bars around each (`ctx.a.loc[...]`) and confirm the
   signal, entry price, stop, target and exit are what the spec says. Fix coding errors; record them in the notes.
4. `python3 tools/yt1/run.py <ID> --check` must print PASS. It mirrors the future after a sample of your own signal
   bars and requires your orders up to that bar to be unchanged. A FAIL means some part of an order reads the future.
5. Write the notes file.

## Rules that are not negotiable
- **Never change a rule, a parameter or a reading because of a result.** No tuning, no "it works better if". A losing
  rule stays losing. If a rule produces few or no trades, check your code against the spec once, then report it as is.
- **Causality.** An order's `i` is the 1-minute bar at whose close the decision is made. Nothing after that close may
  feed the order: not the signal, not the stop, not the target. The one exception is written in `s_Z00.py`. Day-table
  columns `rth_h`, `rth_l`, `rth_c` describe the whole day and are unknown during it. An N-minute bar is known only at
  the close of its last 1-minute bar (`i_last`). An indicator value at bar k may use bars up to k only.
- **The harness does the fills.** Never compute an entry fill, an exit or a P&L yourself. If a rule needs something
  `simulate` cannot express, say so in the notes and code the nearest expressible form; do not work around it.
- **Do not edit** `core.py`, `ind.py`, `run.py` or another coder's files. A helper you need goes in your own module.
  If you think the harness is wrong, write the evidence in your notes and carry on.
- If the spec is ambiguous, take the most literal reading and record it. If the spec seems impossible as written,
  code it as written and say what happened.
- The machine has 2 CPU cores shared by several coders: run one Python process at a time, keep a run under about two
  minutes (loop over days or vectorise; never loop in Python over all 1.3 million bars for every variant if you can
  avoid it), and do not leave background processes.

## Things the harness already does for you
- `core.run_orders` drops orders signalled on contract-roll days and on days without a daily ATR (family C: pass
  `skip_roll=2` to also drop the day after a roll), enforces one position at a time, and can cap trades per day.
- `exit_i=int(day.i_end)` is the flat bar (15:59, or early on short days). An order signalled at or after it is dropped.
- `ctx.bars(N)` gives N-minute bars with `i_last`; `ctx.idx(date, "10:59")` and `ctx.span(date, "09:30", "10:30")`
  find bars by time and return None / an empty span when a minute has no bar. Never do index arithmetic across time.
- `ctx.extra("ES")` and `ctx.flow("NQ_footprint_5m")` load a second market or the order-flow tables safely. Never read
  those files directly.
- `core.tick_round(x, "down" | "up" | "nearest")` puts a computed level on the 0.25 tick grid.
- When two resting orders compete ("the first to fill is the trade"): `orders()` returns both; in `trades()` simulate
  each with `core.simulate` and keep the one with the smaller fill bar `j` (same bar: take neither), then respect
  roll / ATR days yourself via `ctx.roll_dates` and `ctx.noatr_dates`.

## Your final message
Only: the IDs you completed; for each, the in-sample `base` line (n, R per trade, p), whether `--check` passed, and
any deviation from the spec text in one line. No other commentary.
