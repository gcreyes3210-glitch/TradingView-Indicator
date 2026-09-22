# Backtest loop

TradingView has no API for running Pine scripts, so the loop is: TradingView runs, you export, Claude analyses and adjusts.

## Files

* `ICT_SMT_IFVG.pine` – the indicator (single source of truth).
* `ICT_SMT_IFVG_strategy.pine` – generated strategy twin. Regenerate after any indicator change: `python3 tools/make_strategy.py`.
* Group `S · Strategy (backtest only)` – test window, quantity, exit model, time stop, reversal.

## One round

1. Paste `ICT_SMT_IFVG_strategy.pine` into the Pine editor, add it to the chart symbol you trade (entry timeframe 1m–5m, correlated symbol set in section 3).
2. Section 10: set `Account risk` and `Point value` for that symbol (MNQ = 2, NQ = 20, MES = 5, ES = 50). With `Quantity = Risk module contracts` a signal whose sizing gives 0 contracts is skipped.
3. Set the **test window**. First pass: in-sample, e.g. the first 70 % of the available history.
4. Strategy Tester → **List of Trades** → export (the download icon) → CSV. The `Signal` column carries the tag, e.g.
   `L|3m|S86A|H23|M15|K15|D12|L10|T8|htf:5m+15m|P:15m|sess:NY AM|smt:Pivot LL/HL+`
   (score + grade, then HTF / SMT / session (K) / displacement / liquidity / structure points, HTF tags, primary zone, session, SMT type; `+` confirmed, `~` developing).
5. Also export **Performance Summary** (or paste net profit, profit factor, max drawdown, trade count) and note every input you changed from default.
6. Upload / paste the CSV here. Claude splits winners vs losers by score component, session, SMT type, HTF timeframe and proposes a settings change or a code change.
7. Apply, re-run on the **same** in-sample window until the change is worth keeping.
8. Confirm on the **out-of-sample** window (the remaining 30 %). Keep only changes that also hold there. A change that helps in-sample and hurts out-of-sample is overfitting – revert it.

## Notes

* Deep Backtesting (paid plans) extends the history the tester sees; free plans get limited 1m history, so 3m / 5m entries test further back.
* The strategy uses `process_orders_on_close`: the entry fills at the close of the signal candle, the same price the indicator's entry line uses.
* Commission and slippage defaults ($1 per contract, 1 tick) live in the `strategy()` header of the generated file; change them in `tools/make_strategy.py`.
