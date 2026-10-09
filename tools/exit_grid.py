#!/usr/bin/env python3
"""Exit grid (observation only, pre-registered in BACKTEST_LOG.md, "Literature follow-ups"): the same entries and
initial stops of each closed family's primary run, re-simulated with 1 R / 2 R / 3 R targets and hold-to-close.

    python3 tools/exit_grid.py [--trades DIR]       DIR holds AMD1-1m.csv, OB1-1m.csv, OTE1-1m.csv, VWR1.csv, P2_base.csv
                                                    (fresh engine runs); IFVG-1m, L7 and ORB9-a are read from data/studies/

First every family is replayed with its own target and flatten time, and the share of trades whose exit (reason and
price) matches its engine is printed: the check that this re-simulator reads each family's entries, stops and fills
the way its engine does. House fills: 1 tick per fill, $1 per side, $2 / point; stop first; a bar opening beyond a
level fills at its open. Output data/studies/exit_grid/.
"""
import sys, pathlib
import numpy as np
import pandas as pd

TZ = "America/New_York"
TICK, PV, COMM = 0.25, 2.0, 1.0
OUT = pathlib.Path("data/studies/exit_grid")
G = sys.argv[sys.argv.index("--trades") + 1] if "--trades" in sys.argv else "data/studies/exit_grid/trades"

# family: file, bars, how risk's reference price relates to the recorded entry, whether the stop counts on the entry
# bar (limit / open entries) and the family's own flatten rule (see flat_bar)
FAM = {
    "AMD1-1m": dict(f=f"{G}/AMD1-1m.csv", tf=1, ref="entry-slip", eb=False, flat=("at", 720)),
    "OB1-1m": dict(f=f"{G}/OB1-1m.csv", tf=1, ref="entry-slip", eb=True, flat=("at", 720)),
    "OTE1-1m": dict(f=f"{G}/OTE1-1m.csv", tf=1, ref="entry-slip", eb=True, flat=("at", 720)),
    "IFVG-1m": dict(f="data/studies/ifvg_l7/attrib_IFVG-1m.csv", tf=1, ref="close", eb=False, flat=("before", 720)),
    "L7": dict(f="data/studies/ifvg_l7/L7.csv", tf=1, ref="close", eb=False, flat=("before", 720)),
    "P2 base": dict(f=f"{G}/P2_base.csv", tf=1, ref="p2", eb=True, flat=("before", 960, 10)),
    "VWR1": dict(f=f"{G}/VWR1.csv", tf=5, ref="entry-slip", eb=False, flat=("at", 960)),
    "ORB9-a": dict(f="data/studies/lit1/ORB9-a.csv", tf=1, ref="entry", eb=True, flat=("before", 960, 11)),
}


def bars(tf):
    b = pd.read_parquet(f"data/bars/MNQ_{tf}m.parquet")
    return b


def prep(name, cfg, b):
    t = pd.read_csv(cfg["f"])
    if "status" in t:
        t = t[t.entry.notna()]
    t = t.reset_index(drop=True)
    t["et"] = pd.to_datetime(t.entry_time, utc=True).dt.tz_convert(TZ)
    sg = np.where(t.side == "L", 1, -1)
    if cfg["ref"] == "entry-slip":
        ref = t.entry - sg * TICK
    elif cfg["ref"] == "close":
        ref = t.close
    elif cfg["ref"] == "p2":
        ref = t.stop + sg * t.risk           # P2 measures risk from O, the limit level
    else:
        ref = t.entry
    t["ref"], t["sg"] = ref, sg
    if "stop" not in t:                      # VWR1: stop on the tick, from the raw distance
        t["stop"] = np.round((t.ref - sg * t.risk) / TICK) * TICK
    own = t.tp if "tp" in t else (t.target if "target" in t else None)
    if name == "VWR1":
        own = np.round((t.ref + sg * t.rr * t.risk) / TICK) * TICK
    t["own_tp"] = own if own is not None else np.nan
    idx = b.index
    t["e"] = idx.searchsorted(t.et.to_numpy(), side="right") - 1            # the bar containing the entry
    return t


def flat_bar(b, tod, day_of, e, rule, tf):
    """Index of the flatten bar for the trade entered on bar e. rule = (mode, minute[, early offset]): "at" = the first
    bar opening at or after the minute, "before" = the last bar opening before it. On an early-close day (the session
    halts before 16:00) a rule with an offset exits on the last bar opening at or before halt - offset minutes;
    otherwise the session's last bar caps it."""
    d, n, last = day_of[e], len(tod), e
    while last + 1 < n and day_of[last + 1] == d and tod[last + 1] < 18 * 60:
        last += 1
    halt = tod[last] + tf
    if halt < 16 * 60 and len(rule) > 2:
        j = e
        while j + 1 <= last and tod[j + 1] <= halt - rule[2]:
            j += 1
        return j
    j = e
    if rule[0] == "at":
        while j < last and tod[j] < rule[1]:
            j += 1
        return j
    while j + 1 <= last and tod[j + 1] < rule[1]:
        j += 1
    return j


def sim(t, b, k=None, hold=False, own=False, rule=None, eb=False, tf=1):
    O, H, L, C = (b[c].to_numpy() for c in ("open", "high", "low", "close"))
    tod = (b.index.hour * 60 + b.index.minute).to_numpy()
    day_of = b.index.normalize().asi8
    out = []
    for r in t.itertuples():
        sg, e, stop = r.sg, r.e, r.stop
        if own:
            tgt = r.own_tp
        elif hold:
            tgt = np.nan
        else:
            tgt = round((r.ref + sg * k * r.risk) / TICK) * TICK
        f = flat_bar(b, tod, day_of, e, ("before", 960) if hold else rule, tf)
        res = None
        for q in range(e, f + 1):
            first = q == e
            if not first and sg * (O[q] - stop) <= 0:
                res = (O[q], "SL"); break
            if (not first or eb) and ((L[q] <= stop) if sg > 0 else (H[q] >= stop)):
                res = (stop, "SL"); break
            if not first and not np.isnan(tgt):
                if sg * (O[q] - tgt) >= 0:
                    res = (O[q], "TP"); break
                if (H[q] >= tgt) if sg > 0 else (L[q] <= tgt):
                    res = (tgt, "TP"); break
        if res is None:
            res = (C[f], "time")
        px = res[0] - sg * TICK
        pnl = sg * (px - r.entry) * PV - 2 * COMM
        out.append((px, res[1], pnl, pnl / (r.risk * PV)))
    x = t.copy()
    x["g_exit"], x["g_reason"], x["g_pnl"], x["g_R"] = zip(*out)
    return x


def row(x):
    y = x.et.dt.year
    return dict(n=len(x), R=round(x.g_R.mean(), 3), win=round(100 * (x.g_pnl > 0).mean(), 1),
                R_h1=round(x[y <= 2022].g_R.mean(), 3), R_h2=round(x[y >= 2023].g_R.mean(), 3), net=round(x.g_pnl.sum()))


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    B = {1: bars(1), 5: bars(5)}
    rows = []
    print("re-simulator check: own target and flatten time, exits matching the engine (reason and price)")
    for name, cfg in FAM.items():
        b = B[cfg["tf"]]
        t = prep(name, cfg, b)
        chk = sim(t, b, own=True, rule=cfg["flat"], eb=cfg["eb"], tf=cfg["tf"])
        keep = ~chk.reason.isin(["BE"])
        rs = chk.reason.replace({"early": "time"})
        m = keep & (rs == chk.g_reason) & (np.abs(chk.exit - chk.g_exit) < 1e-6)
        print(f"  {name:<8} {int(m.sum())} / {int(keep.sum())} match ({100 * m.sum() / keep.sum():.1f} %)"
              + f"; engine net {chk[keep].pnl.sum():+,.0f}, replay {chk[keep].g_pnl.sum():+,.0f}")
        if m.mean() < 0.95:
            bad = chk[keep & ~m].head(3)
            print(bad[["et", "side", "entry", "stop", "own_tp", "reason", "exit", "g_reason", "g_exit"]].to_string())
        for lab, kw in (("1 R", dict(k=1)), ("2 R", dict(k=2)), ("3 R", dict(k=3)), ("hold to close", dict(hold=True))):
            x = sim(t, b, rule=cfg["flat"], eb=cfg["eb"], tf=cfg["tf"], **kw)
            rows.append(dict(family=name, exit=lab, **row(x)))
        rows.append(dict(family=name, exit="own (replay)", **row(chk)))
    d = pd.DataFrame(rows)
    d.to_csv(OUT / "exit_grid.csv", index=False)
    print("\n" + d.to_string(index=False))


def amd_orb():
    """AMD1-1m held to 16:00, split by ORB v1.4 day and side (pre-registered observation)."""
    b = bars(1)
    cfg = FAM["AMD1-1m"]
    x = sim(prep("AMD1-1m", cfg, b), b, hold=True, rule=cfg["flat"], eb=cfg["eb"], tf=1)
    x["d"] = x.et.dt.tz_localize(None).dt.normalize()
    v = pd.read_csv("data/studies/lit1/v14.csv", parse_dates=["day"])
    vs = v.groupby("day").side.first()
    vp = v.groupby("day").pnl.sum()
    x["bucket"] = ["not an ORB day" if d not in vs.index else ("ORB day, same side" if vs[d] == sd else "ORB day, opposite side")
                   for d, sd in zip(x.d, x.side)]
    x["half"] = np.where(x.et.dt.year <= 2022, "2019-22", "2023-26")
    x.to_csv(OUT / "AMD1-1m_hold_orb.csv", index=False)
    print(f"AMD1-1m held to 16:00: n {len(x)}  net {x.g_pnl.sum():+,.0f}  R/trade {x.g_R.mean():+.3f}")
    for h in ("all", "2019-22", "2023-26"):
        g0 = x if h == "all" else x[x.half == h]
        print(f"\n  {h}: total n {len(g0)} net {g0.g_pnl.sum():+,.0f} R {g0.g_R.mean():+.3f}")
        for k in ("ORB day, same side", "ORB day, opposite side", "not an ORB day"):
            g = g0[g0.bucket == k]
            print(f"    {k:<24} n {len(g):>4}  net {g.g_pnl.sum():>+8,.0f}  R/trade {g.g_R.mean():+.3f}")
    a_ = x.groupby("d").g_pnl.sum()
    days = pd.DatetimeIndex(sorted(set(b.index[(b.index.hour * 60 + b.index.minute == 570)].tz_localize(None).normalize())))
    days = days[(days >= "2019-06-01") & (days <= v.day.max())]
    both = a_.index.intersection(vp.index)
    print(f"\n  daily P&L correlation with v1.4: all {len(days)} cash days (0 = no trade) "
          f"{np.corrcoef(a_.reindex(days, fill_value=0), vp.reindex(days, fill_value=0))[0, 1]:+.3f}; "
          f"{len(both)} days both traded {np.corrcoef(a_[both], vp[both])[0, 1]:+.3f}")
    red = all(x[(x.half == h) & (x.bucket == "ORB day, same side")].g_pnl.sum() >= x[x.half == h].g_pnl.sum()
              for h in ("2019-22", "2023-26"))
    print(f"  redundancy rule (same-side ORB-day net >= total net in both halves): {'REDUNDANT with ORB' if red else 'not redundant'}")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "amd-orb":
        amd_orb()
    else:
        main()
