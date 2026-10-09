#!/usr/bin/env python3
"""G7 - TTrades Silver Bullet, no daily bias (YT4_SPEC.md, Part 2). Short side described; longs are the mirror.

Range = the 09:00-09:59 high and low. Raid = the first 1-minute bar from 10:00 to trade beyond one side; the trade is
against it. Confirmation (short): the first 1-minute close below the latest 3-bar swing low (ind.fractal_low, 1 bar
each side) that was confirmed before the bar holding the raid's high. If the other side of the range is traded
through before that close: no trade. Entry: sell limit at the near edge of the latest bearish 1-minute fair value gap
whose three candles lie between the bar holding the raid's high and the confirmation bar (both included); none: no
trade. The limit rests to the 10:59 bar. Stop 1 tick beyond the raid's high. Target: the far side of the range. Stop
to entry once 3R has traded. Flat bar. One order a day. Neighbours: limit at the gap's midpoint; at its far edge.

Readings (R), all fixed before the first run - see notes/G7.md.
"""
import numpy as np
import core
import ind

ID = "G7"
NAME = "TTrades Silver Bullet, no daily bias (raid of the 09:00 hour, 1m swing break, limit at the 1m FVG)"
VARIANTS = {
    "base": dict(edge="near"),
    "nb1": dict(edge="mid"),
    "nb2": dict(edge="far"),
}
T = core.TICK


def _latest(x):
    """out[k] = the latest non-NaN value of x at or before k (NaN if none yet)."""
    pos = np.where(np.isnan(x), -1, np.arange(len(x)))
    pos = np.maximum.accumulate(pos)
    return np.where(pos >= 0, x[np.maximum(pos, 0)], np.nan)


def _setups(ctx):
    """One entry per day whose raid was confirmed and left a gap: everything but the limit's place inside the gap.
    Cached on the context (the same for every variant). Also keeps counts of where each day's setup ended (for the
    notes; not used by the rule)."""
    if getattr(ctx, "_g7_setups", None) is not None:
        return ctx._g7_setups
    H, L, C = ctx.H, ctx.L, ctx.C
    out = []
    cnt = dict(days=0, no_raid=0, raid_both_same_bar=0, raid_high=0, raid_low=0, other_side_first=0,
               no_confirmation=0, no_swing_known=0, no_gap=0, setups=0)
    for d, day in ctx.days.iterrows():
        r0, r1 = ctx.span(d, "09:00", "10:00")
        w0, w1 = ctx.span(d, "10:00", "11:00")          # the window; its last bar (10:59) is the limit's last bar
        if r1 <= r0 or w1 <= w0:
            continue
        cnt["days"] += 1
        rh, rl = H[r0:r1].max(), L[r0:r1].min()
        up, dn = H[w0:w1] > rh, L[w0:w1] < rl           # trades beyond a side = at least one tick
        hit = up | dn
        if not hit.any():
            cnt["no_raid"] += 1
            continue
        r = w0 + int(hit.argmax())                      # the raid bar
        if up[r - w0] and dn[r - w0]:                   # both sides in one bar: no first side
            cnt["raid_both_same_bar"] += 1
            continue
        side = -1 if up[r - w0] else 1                  # trade against the raid
        cnt["raid_high" if side < 0 else "raid_low"] += 1
        # 1-minute bars since this trading day's 18:00 open. 3-bar swings: the value sits on the bar confirming it
        s0 = int(np.searchsorted(ctx.tdate, np.datetime64(d, "D"), "left"))
        hw, lw = H[s0:w1], L[s0:w1]
        sw = _latest(ind.fractal_low(lw) if side < 0 else ind.fractal_high(hw))
        gap = ind.fvg_bear(hw, lw) if side < 0 else ind.fvg_bull(hw, lw)     # completed at its third candle
        ext, e, conf, void, known = None, None, None, False, False
        for c in range(r, w1 - 1):                      # a confirmation at 10:59 leaves the limit no bar to rest on
            if (L[c] < rl) if side < 0 else (H[c] > rh):
                void = True                             # the other side raided before the confirmation
                break
            if ext is None or ((H[c] > ext) if side < 0 else (L[c] < ext)):
                ext, e = (H[c] if side < 0 else L[c]), c    # the raid's extreme and the (first) bar holding it
            lvl = sw[e - 1 - s0] if e - 1 >= s0 else np.nan  # latest swing confirmed before bar e opened
            if lvl != lvl:
                continue
            known = True
            if (C[c] < lvl) if side < 0 else (C[c] > lvl):
                conf = c
                break
        if void:
            cnt["other_side_first"] += 1
            continue
        if conf is None:
            cnt["no_swing_known" if (r < w1 - 1 and not known) else "no_confirmation"] += 1
            continue
        g = None
        for k in range(conf, e + 1, -1):                # latest gap with candles k-2, k-1, k inside [e, conf]
            if gap[k - s0]:
                g = k
                break
        if g is None:
            cnt["no_gap"] += 1
            continue
        near, far = (H[g], L[g - 2]) if side < 0 else (L[g], H[g - 2])
        cnt["setups"] += 1
        out.append(dict(i=int(conf), side=side, near=float(near), far=float(far), ext=float(ext),
                        target=float(rl if side < 0 else rh), expire=int(w1 - 1), exit_i=int(day.i_end),
                        raid=int(r), e=int(e), g=int(g), level=float(lvl), rh=float(rh), rl=float(rl)))
    ctx._g7_setups = (out, cnt)
    return ctx._g7_setups


def orders(ctx, edge="near"):
    out = []
    for s in _setups(ctx)[0]:
        side = s["side"]
        if edge == "near":
            price = s["near"]
        elif edge == "far":
            price = s["far"]
        else:
            price = core.tick_round((s["near"] + s["far"]) / 2.0, "down" if side > 0 else "up")
        stop = s["ext"] - side * T                      # 1 tick beyond the raid's extreme
        target = s["target"]                            # the far side of the range
        if side * (target - price) <= 0:                # the entry is already at / past the target: nothing to trade
            continue
        out.append(dict(i=s["i"], side=side, etype="limit", price=float(price), expire=s["expire"],
                        stop=float(stop), target=float(target),
                        be_trigger=float(price + side * 3.0 * abs(price - stop)),
                        exit_i=s["exit_i"], tag="S" if side < 0 else "L"))
    return out


def trades(ctx, **p):
    return core.run_orders(ctx, orders(ctx, **p), max_per_day=1)
