#!/usr/bin/env python3
"""Generate ICT_SMT_IFVG_strategy.pine from ICT_SMT_IFVG.pine.

The indicator stays the single source of truth.  This script only
  * swaps the indicator() header for strategy(),
  * adds a 'S · Strategy (backtest)' input group (date range, quantity, exit model, reversal),
  * places orders from the risk module's numbers right after each Buy/Sell,
  * tags every entry with the compact score tag so the exported trade list carries
    score, the six components, session, HTF zone and SMT type.
Run:  python3 tools/make_strategy.py
"""
import re, sys, pathlib
root = pathlib.Path(__file__).resolve().parent.parent
src = (root / "ICT_SMT_IFVG.pine").read_text()

def rep(old, new, count=1):
    global src
    if src.count(old) != count:
        sys.exit(f"anchor not found ({src.count(old)}x): {old[:80]!r}")
    src = src.replace(old, new)

rep('indicator("ICT SMT + IFVG in HTF FVG", shorttitle = "ICT SMT/IFVG", overlay = true, max_boxes_count = 500, max_labels_count = 500, max_lines_count = 500)',
    'strategy("ICT SMT + IFVG in HTF FVG · Strategy", shorttitle = "ICT SMT/IFVG STRAT", overlay = true, max_boxes_count = 500, max_labels_count = 500, max_lines_count = 500, pyramiding = 0, calc_on_every_tick = false, process_orders_on_close = true, initial_capital = 25000, default_qty_type = strategy.fixed, default_qty_value = 1, commission_type = strategy.commission.cash_per_contract, commission_value = 1.0, slippage = 1, margin_long = 0, margin_short = 0)')

# strategy counters next to the last-plan array, and a STRATEGY row in the debug table
rep("var array<float> lastPlan = array.new_float(6, na)\n", "var array<float> lastPlan = array.new_float(6, na)\nvar int stratOrders = 0\nvar int stratSkipped = 0\n// open position memory for the breakeven rule: [entry, stop, tp1, tp2, tpMain, qty, half-model flag, breakeven done]\nvar array<float> posMem = array.new_float(8, na)\nvar string posOid = \"\"\nvar string pendOid = \"\"\nvar int pendBar = na\n")
rep("        var table dbgTable = table.new(position.bottom_right, 2, 12, border_width = 1)", "        var table dbgTable = table.new(position.bottom_right, 2, 13, border_width = 1)")
rep("        table.cell(dbgTable, 1, 11, ifvgDbgTxt, bgcolor = grayBg, text_color = color.white)",
    "        table.cell(dbgTable, 1, 11, ifvgDbgTxt, bgcolor = grayBg, text_color = color.white)\n"
    "        table.cell(dbgTable, 0, 12, \"STRATEGY\", bgcolor = color.gray, text_color = color.white)\n"
    "        table.cell(dbgTable, 1, 12, \"orders submitted \" + str.tostring(stratOrders) + \" · skipped (window / qty / position) \" + str.tostring(stratSkipped) + \" · closed trades \" + str.tostring(strategy.closedtrades) + \" · open \" + str.tostring(strategy.opentrades) + \" · equity \" + str.tostring(strategy.equity, \"#.##\"), bgcolor = grayBg, text_color = color.white)")

# strategy inputs, right before the TYPES section
rep("// ============================== TYPES ==============================", '''grpStrat = "S · Strategy (backtest only)"
s_from       = input.time(timestamp("2024-01-01T00:00:00"), "Test window start", group = grpStrat, tooltip = "Entries are only taken inside the window. Tune settings on one window (in-sample), then re-run on a later window the tuning never saw (out-of-sample) and keep only changes that hold up there.")
s_to         = input.time(timestamp("2030-01-01T00:00:00"), "Test window end", group = grpStrat)
s_qtyMode    = input.string("Risk module contracts", "Quantity", options = ["Risk module contracts", "Fixed 1 contract", "Fixed 2 contracts"], group = grpStrat, tooltip = "Risk module contracts = the count from section 10 (Account risk / (stop distance x point value)). 0 contracts = the signal is skipped, so set Account risk and Point value for the symbol you test. Fixed 2 contracts is needed for the Half at TP1, rest at TP2 exit model.")
s_exitModel  = input.string("TP1", "Exit model", options = ["TP1", "TP2", "Swing TP (fallback TP1)", "Half at TP1, rest at TP2", "Stop / time only"], group = grpStrat, tooltip = "Which of the risk module's targets closes the trade. Every model uses the section 10 stop. Half at TP1 needs at least 2 contracts. Stop / time only = no target, the trade runs until the stop or the time stop.")
s_timeStop   = input.bool(true, "Time stop = 'Close an open trade plan after' bars", group = grpStrat, tooltip = "Closes the position at market after the section 10 'Close an open trade plan after (chart bars)' input.")
s_allowRev   = input.bool(false, "Opposite signal reverses an open position", group = grpStrat, tooltip = "Off: a signal against the open position is ignored. On: the position is closed and reversed.")
s_entryMode  = input.string("Market at inversion close", "Entry", options = ["Market at inversion close", "Limit at IFVG 50% (CE)"], group = grpStrat, tooltip = "Market: fills at the close of the inversion candle (the indicator's entry). Limit at CE: a limit order at the IFVG's 50% level, cancelled if not filled within the bars below. Stop = the risk module's stop; targets are re-computed from the limit price with the section 10 risk:reward ratios.")
s_limitBars  = input.int(12, "  limit valid for (chart bars)", minval = 1, group = grpStrat, tooltip = "A limit entry that is not filled within this many bars is cancelled.")
s_beR        = input.float(0.0, "Move stop to breakeven after x R (0 = off)", minval = 0.0, step = 0.25, group = grpStrat, tooltip = "Once a confirmed bar has moved this many risk units (entry to stop distance) in the trade's favour, the stop is moved to the entry price. 0 = off.")
s_useAlerts  = input.bool(false, "Fire strategy order alerts", group = grpStrat, tooltip = "Adds strategy order events to 'Any alert() function call' alerts (for broker / webhook forwarding). The indicator alerts stay as they are.")

// ============================== TYPES ==============================''')

# orders right after the indicator handled the signal
rep('''            string summary = f_onSignal(s)
            lastSigBar := bar_index
''', '''            string summary = f_onSignal(s)
            // ---------- strategy twin: orders from the risk module's numbers, tagged with the score components ----------
            bool inWindow = time >= s_from and time <= s_to
            float lastPlanSl = array.get(lastPlan, 1)
            float lastPlanTp1 = array.get(lastPlan, 2)
            float lastPlanTp2 = array.get(lastPlan, 3)
            float lastPlanTpSw = array.get(lastPlan, 4)
            int qty = s_qtyMode == "Fixed 1 contract" ? 1 : s_qtyMode == "Fixed 2 contracts" ? 2 : int(nz(array.get(lastPlan, 5), 0))
            bool sameSideOpen = s.isBull ? strategy.position_size > 0 : strategy.position_size < 0
            bool otherSideOpen = s.isBull ? strategy.position_size < 0 : strategy.position_size > 0
            bool canEnter = inWindow and qty > 0 and not sameSideOpen and (not otherSideOpen or s_allowRev)
            if not canEnter
                stratSkipped += 1
            if canEnter
                stratOrders += 1
                string oid = (s.isBull ? "L" : "S") + "|" + s.tag
                if otherSideOpen
                    strategy.close_all(comment = "reverse")
                // entry price: the inversion close (market) or the IFVG 50% level (limit); targets follow the entry price
                bool limitMode = s_entryMode == "Limit at IFVG 50% (CE)" and not na(s.ifvgCe)
                float entryPx = limitMode ? s.ifvgCe : s.entry
                float riskL = math.abs(entryPx - lastPlanSl)
                lastPlanTp1 := limitMode ? (s.isBull ? entryPx + riskL * tp1RR : entryPx - riskL * tp1RR) : lastPlanTp1
                lastPlanTp2 := limitMode ? (tp2RR > 0 ? (s.isBull ? entryPx + riskL * tp2RR : entryPx - riskL * tp2RR) : na) : lastPlanTp2
                float tpMain = s_exitModel == "TP2" ? (na(lastPlanTp2) ? lastPlanTp1 : lastPlanTp2) : s_exitModel == "Swing TP (fallback TP1)" ? (na(lastPlanTpSw) ? lastPlanTp1 : lastPlanTpSw) : lastPlanTp1
                if pendOid != ""
                    strategy.cancel(pendOid)
                strategy.entry(oid, s.isBull ? strategy.long : strategy.short, qty = qty, limit = limitMode ? entryPx : na, comment = oid, alert_message = s_useAlerts ? "ENTRY " + oid : na)
                pendOid := limitMode ? oid : ""
                pendBar := bar_index
                bool halfModel = s_exitModel == "Half at TP1, rest at TP2" and qty >= 2 and not na(lastPlanTp2)
                posOid := oid
                array.set(posMem, 0, entryPx)
                array.set(posMem, 1, lastPlanSl)
                array.set(posMem, 2, lastPlanTp1)
                array.set(posMem, 3, lastPlanTp2)
                array.set(posMem, 4, s_exitModel == "Stop / time only" ? na : tpMain)
                array.set(posMem, 5, qty)
                array.set(posMem, 6, halfModel ? 1 : 0)
                array.set(posMem, 7, 0)
                if s_exitModel == "Half at TP1, rest at TP2" and qty >= 2 and not na(lastPlanTp2)
                    int half = int(math.floor(qty / 2))
                    strategy.exit("x1|" + oid, from_entry = oid, qty = half, stop = lastPlanSl, limit = lastPlanTp1, comment_profit = "TP1", comment_loss = "SL")
                    strategy.exit("x2|" + oid, from_entry = oid, qty = qty - half, stop = lastPlanSl, limit = lastPlanTp2, comment_profit = "TP2", comment_loss = "SL")
                else if s_exitModel == "Stop / time only" or na(tpMain)
                    strategy.exit("x|" + oid, from_entry = oid, stop = lastPlanSl, comment_loss = "SL")
                else
                    strategy.exit("x|" + oid, from_entry = oid, stop = lastPlanSl, limit = tpMain, comment_profit = "TP", comment_loss = "SL")
            lastSigBar := bar_index
''')

# time stop: after the plans loop, inside the confirmed-bar block
rep('''    // ---------- signal marks clean-up ----------''', '''    // ---------- strategy twin: unfilled limit entries expire ----------
    if pendOid != "" and strategy.position_size != 0
        pendOid := ""
    if pendOid != "" and bar_index - pendBar > s_limitBars
        strategy.cancel(pendOid)
        pendOid := ""

    // ---------- strategy twin: breakeven (re-issues the exit orders with the stop at the entry price) ----------
    if s_beR > 0 and strategy.position_size != 0 and strategy.opentrades > 0 and nz(array.get(posMem, 7), 0) == 0
        float pEntry = array.get(posMem, 0)
        float pSl = array.get(posMem, 1)
        float pRisk = math.abs(pEntry - pSl)
        bool pLong = strategy.position_size > 0
        bool beHit = pLong ? high >= pEntry + s_beR * pRisk : low <= pEntry - s_beR * pRisk
        if beHit and bar_index > strategy.opentrades.entry_bar_index(strategy.opentrades - 1)
            array.set(posMem, 7, 1)
            int pQty = int(nz(array.get(posMem, 5), 1))
            if nz(array.get(posMem, 6), 0) == 1
                int pHalf = int(math.floor(pQty / 2))
                strategy.exit("x1|" + posOid, from_entry = posOid, qty = pHalf, stop = pEntry, limit = array.get(posMem, 2), comment_profit = "TP1", comment_loss = "BE")
                strategy.exit("x2|" + posOid, from_entry = posOid, qty = pQty - pHalf, stop = pEntry, limit = array.get(posMem, 3), comment_profit = "TP2", comment_loss = "BE")
            else if na(array.get(posMem, 4))
                strategy.exit("x|" + posOid, from_entry = posOid, stop = pEntry, comment_loss = "BE")
            else
                strategy.exit("x|" + posOid, from_entry = posOid, stop = pEntry, limit = array.get(posMem, 4), comment_profit = "TP", comment_loss = "BE")

    // ---------- strategy twin: time stop ----------
    if s_timeStop and strategy.position_size != 0 and strategy.opentrades > 0
        int openedBar = strategy.opentrades.entry_bar_index(strategy.opentrades - 1)
        if bar_index - openedBar > tradeMaxBars
            strategy.close_all(comment = "time")

    // ---------- signal marks clean-up ----------''')

# the version annotation must stay on line 1
src = src.replace("//@version=5\n", "//@version=5\n// GENERATED by tools/make_strategy.py from ICT_SMT_IFVG.pine - do not edit by hand: edit the indicator and regenerate.\n", 1)
(root / "ICT_SMT_IFVG_strategy.pine").write_text(src)
print("wrote ICT_SMT_IFVG_strategy.pine")
