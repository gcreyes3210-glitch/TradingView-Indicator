#!/usr/bin/env python3
"""K-Q78 - Q7 and Q8, the tick brackets against the 1-minute bar: how many trades ended on a bar that held both the
stop and the target, and what the result would be had each of those been a winner.

YT11_SPEC.md, Part 4, "For Q7 and Q8, stated in advance": 6 to 20 ticks is 1.5 to 5 points, smaller than a typical
1-minute bar of 2026. A 1-minute bar that holds both the stop and the target counts as a stop (house rule), so these
two rules are scored at their worst. Reported with them: the share of trades whose exit bar held both prices, and the
result if every such trade had been a winner instead (the best case; the truth is between the two).

For every variant of s_Q7 and of s_Q8, from that rule's own trades (module.trades; nothing is re-simulated):
  n           trades
  both        trades whose exit bar's low <= stop price <= high and low <= target price <= high. The stop and the
              target are the order's own prices (module.orders, matched to the trade by its signal bar); the exit bar
              is the trade's `k`. The house rule takes the stop on such a bar, so every one of them is a stop here.
  net_house   net $ as scored.
  net_best    net $ if every `both` trade had been a winner: that trade's net is replaced by the target outcome under
              the house fills = (|target - entry reference price| - 1 tick on each of the two fills) x $2 - $2.
              Entry reference price = the fill price less the 1-tick entry slippage = the signal bar's close.
Also given, as description: how the `both` bars opened. A bar that opens at or beyond the stop took the stop first
whatever came after, and a bar that opens at or beyond the target reached the target first; only the rest have an
unknown order inside the bar. The headline `both` / `net_best` are the spec's (all of them counted as winners).
"""
import numpy as np
import pandas as pd
import core
import s_Q7
import s_Q8

NAME = "Q7 / Q8: trades whose exit bar held both the stop and the target; house result against the best case"
STATED = ("a 1-minute bar that holds both the stop and the target counts as a stop, so Q7 and Q8 are scored at "
          "their worst; the best case counts every such trade as a winner; the truth is between the two")


def _one(ctx, mod, params):
    O, H, L = ctx.O, ctx.H, ctx.L
    ords = mod.orders(ctx, **params)
    by_i = {o["i"]: o for o in ords}
    assert len(by_i) == len(ords), "two orders on one signal bar"
    rows = []
    for t in mod.trades(ctx, **params):
        o = by_i[t["i"]]
        side = 1 if t["side"] == "L" else -1
        stop, target, k = float(o["stop"]), float(o["target"]), t["k"]
        assert stop == t["stop"] and o["side"] == side and k > t["j"]
        ref = t["entry"] - side * core.SLIP                          # the entry reference price (signal close)
        both = bool(L[k] <= stop <= H[k] and L[k] <= target <= H[k])
        win_net = round((abs(target - ref) - 2 * core.SLIP) * core.PV - 2 * core.COMM, 2)
        rows.append(dict(year=int(t["entry_time"].year), day=t["entry_time"].date(), pnl=t["pnl"], reason=t["reason"],
                         both=both, best=win_net if both else t["pnl"],
                         open_at_stop=bool(both and side * (O[k] - stop) <= 0),
                         open_at_target=bool(both and side * (O[k] - target) >= 0),
                         stop_ticks=abs(ref - stop) / core.TICK, target_ticks=abs(target - ref) / core.TICK))
    x = pd.DataFrame(rows)
    if not len(x):
        return dict(params=params, n=0)

    def block(g):
        nb = int(g.both.sum())
        return dict(n=int(len(g)), both=nb, both_share=round(nb / len(g), 4),
                    net_house=round(float(g.pnl.sum()), 2), net_best=round(float(g.best.sum()), 2))

    out = dict(params=params, **block(x))
    out.update(
        sessions_with_a_trade=int(x.day.nunique()),
        win_rate_house=round(float((x.pnl > 0).mean()), 4),
        win_rate_best=round(float((x.best > 0).mean()), 4),
        net_per_trade_house=round(float(x.pnl.mean()), 3), net_per_trade_best=round(float(x.best.mean()), 3),
        both_scored_as=x[x.both].reason.value_counts().to_dict(),
        both_bar_opened_at_or_beyond_stop=int(x.open_at_stop.sum()),
        both_bar_opened_at_or_beyond_target=int(x.open_at_target.sum()),
        both_order_inside_bar_unknown=int((x.both & ~x.open_at_stop & ~x.open_at_target).sum()),
        exits=x.reason.value_counts().to_dict(),
        mean_stop_ticks=round(float(x.stop_ticks.mean()), 2), mean_target_ticks=round(float(x.target_ticks.mean()), 2),
        by_year={int(y): block(g) for y, g in x.groupby("year")})
    return out


def measure(ctx):
    res = dict(stated_in_advance=STATED,
               span=f"{ctx.days.index[0].date()} -> {ctx.days.index[-1].date()}",
               cost_round_trip_usd=2 * core.SLIP * core.PV + 2 * core.COMM)
    for mod in (s_Q7, s_Q8):
        res[mod.ID] = {v: _one(ctx, mod, p) for v, p in mod.VARIANTS.items()}
    return res


def show(res):
    print(res["stated_in_advance"])
    print(f"span {res['span']}   round trip ${res['cost_round_trip_usd']:.2f}")
    for rid in ("Q7", "Q8"):
        for v, r in res[rid].items():
            if not r["n"]:
                print(f"{rid} {v:<5} n 0")
                continue
            print(f"{rid} {v:<5} n {r['n']:>5}  both in the exit bar {r['both']:>5} = {r['both_share']:.1%}"
                  f"  net house {r['net_house']:>+10.2f}  net best case {r['net_best']:>+10.2f}"
                  f"  win {r['win_rate_house']:.1%} -> {r['win_rate_best']:.1%}"
                  f"  (bar opened beyond the stop {r['both_bar_opened_at_or_beyond_stop']}, beyond the target "
                  f"{r['both_bar_opened_at_or_beyond_target']}, order unknown {r['both_order_inside_bar_unknown']})")
            print("          by year: " + "  ".join(
                f"{y} n {b['n']} both {b['both_share']:.0%} {b['net_house']:+.0f} / {b['net_best']:+.0f}"
                for y, b in r["by_year"].items()))
