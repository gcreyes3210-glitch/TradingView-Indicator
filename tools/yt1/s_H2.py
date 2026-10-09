#!/usr/bin/env python3
"""H2 - Pat's 01:00-05:00 candle (YT8_SPEC.md, Part 2).

Spec text:
  Range = high and low of 01:00-04:59. On 5-minute bars from 05:00: at least three consecutive closes outside the
  range on one side, then the first close back inside it, by 11:00 (R), is entered at that close against the
  excursion. Stop 1 tick beyond the excursion's extreme. Target the far side of the range. One trade a day.
  Neighbours: at least two and at least four closes outside.

Readings added (fixed before the first run; see notes/H2.md):
  * range = the 1-minute bars stamped 01:00 ... 04:59 of the cash day's calendar date (whatever bars exist).
  * 5-minute bars = the clock-aligned bars that open 05:00 ... 10:55 ("by 11:00" = the entry candle has closed by
    11:00). "Consecutive" = consecutive bars of that series (a 5-minute bucket with no trade is not a bar).
  * "outside" is strict: close > range high (above) or close < range low (below). A close exactly on an edge is
    inside: it ends a run, and after a long-enough run it is the close back inside.
  * the close back inside must be the bar directly after the run. A run that jumps to the other side without a close
    inside is not a signal; the bar that closed on the other side starts a new run there.
  * the excursion = the bars of the run plus the entry bar; its extreme = their highest high (run above) / lowest low.
  * every such signal before 11:00 is an order; "one trade a day" = the first that is a trade. A signal whose target
    is not beyond its entry price is no trade (not an order), and a later signal that day may still trade.
"""
import numpy as np
import core

ID = "H2"
NAME = "Pat's 01:00-05:00 candle: >= N 5m closes outside, enter the first close back inside"
VARIANTS = {
    "base": dict(n_out=3),
    "nb1": dict(n_out=2),
    "nb2": dict(n_out=4),
}


def orders(ctx, n_out=3):
    b = ctx.bars(5)
    bh, bl, bc = b.high.to_numpy(float), b.low.to_numpy(float), b.close.to_numpy(float)
    bi_first, bi_last = b.i_first.to_numpy(), b.i_last.to_numpy()
    T = core.TICK
    out = []
    for d, day in ctx.days.iterrows():
        r0, r1 = ctx.span(d, "01:00", "05:00")          # the range's 1-minute bars
        if r1 <= r0:
            continue
        rh, rl = float(ctx.H[r0:r1].max()), float(ctx.L[r0:r1].min())
        s0, s1 = ctx.span(d, "05:00", "11:00")
        if s1 <= s0:
            continue
        m0 = int(np.searchsorted(bi_first, s0, "left")) # 5-minute bars opening 05:00 ..
        m1 = int(np.searchsorted(bi_first, s1, "left")) # .. 10:55
        run_side, run_len, run_start = 0, 0, -1
        for m in range(m0, m1):
            c = bc[m]
            st = 1 if c > rh else -1 if c < rl else 0
            if st != 0:
                if st == run_side:
                    run_len += 1
                else:
                    run_side, run_len, run_start = st, 1, m
                continue
            if run_len >= n_out:                        # the first close back inside, directly after the run
                side = -run_side
                if run_side > 0:
                    stop, target = float(bh[run_start:m + 1].max()) + T, rl
                else:
                    stop, target = float(bl[run_start:m + 1].min()) - T, rh
                if (target - c) * side > 0:             # the target must be beyond the entry
                    out.append(dict(i=int(bi_last[m]), side=side, etype="close", stop=stop, target=float(target),
                                    exit_i=int(day.i_end), tag=f"{'S' if side < 0 else 'L'}{run_len}"))
            run_side, run_len, run_start = 0, 0, -1
    return out


def trades(ctx, **p):
    return core.run_orders(ctx, orders(ctx, **p), max_per_day=1, skip_roll=2)
