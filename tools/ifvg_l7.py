#!/usr/bin/env python3
"""IFVG-L7: IFVG-1m (tools/ifvg1m_engine.py, T3 Z-all) with the Aceflw level set as the sweep levels
(pre-registered in BACKTEST_LOG.md, "IFVG-L7").

    python3 tools/ifvg_l7.py all            L7 and L7-noHTF with neighbours (freshness 3 / 8), CSVs to data/studies/ifvg_l7/
    python3 tools/ifvg_l7.py charts         10 random L7 trades cut at the entry bar (data/studies/ifvg_l7_charts/)

Only two things differ from IFVG-1m: the setup list (sweeps of the levels below, SMT against ES's own level of the
same type on the same 5m bar, no pivot SMTs) and the trade limit (the first trade of each session only).
Levels, per trading day (18:00 -> 17:00), on MNQ and, computed the same way, on ES:
  ONVP VAH / POC / VAL  1m bars 18:00-09:29, 4-tick rows, volume spread evenly low -> high, 70 % value area grown two
                        rows at a time toward the larger side (up on a tie), as Aceflw_Levels.pine. Live from 09:30.
  ONH / ONL             high / low of the same bars. Live from 09:30. One-sided (ONH up only, ONL down only).
  VWAP, +-1 / +-2 sigma anchored 18:00, hlc3 x volume of 1m bars; the level on bar j is the value through bar j-1.
                        Live from 09:30.
  PDH / PDL             previous trading day's high / low, as IFVG-1m. Live from 18:00. One-sided.
Two-sided levels (VAH, POC, VAL, VWAP and bands): a high sweep needs the previous close below the level, a low sweep
the previous close above it. Sweep = first bar beyond by > 2 ticks; at most one sweep per level per direction per
session. SMT: ES does not trade > 2 ticks beyond its own level on the sweep's 5m bar, as known at each minute.
"""
import sys, pathlib, subprocess
import numpy as np
import pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import ifvg1m_engine as E

TOL, ROW, VA = E.TOL, 1.0, 0.70
OUT = pathlib.Path("data/studies/ifvg_l7")
_trades = E.trades                               # IFVG-1m's management; L7 keeps the session's first trade
TYPES = ["PDH", "PDL", "ONH", "ONL", "VAH", "POC", "VAL", "VWAP", "VWAP+1s", "VWAP-1s", "VWAP+2s", "VWAP-2s"]


def profile(h, l, v):
    """VAH, POC, VAL of bars (h, l, v) as Aceflw_Levels.pine: rows of ROW points on an absolute grid."""
    lo = np.floor(l / ROW + 1e-9).astype(int)
    hi = np.floor(h / ROW + 1e-9).astype(int)
    base = lo.min()
    rows = np.zeros(hi.max() - base + 1)
    for a, b, x in zip(lo - base, hi - base, v):
        rows[a:b + 1] += x / (b - a + 1)
    n, tot = len(rows), rows.sum()
    if n < 3 or tot <= 0:
        return np.nan, np.nan, np.nan
    ip = int(np.argmax(rows))
    acc, up, dn = rows[ip], ip, ip
    while acc < tot * VA and (up < n - 1 or dn > 0):
        aU = rows[up + 1] + (rows[up + 2] if up + 2 <= n - 1 else 0.0) if up + 1 <= n - 1 else -1.0
        aD = rows[dn - 1] + (rows[dn - 2] if dn - 2 >= 0 else 0.0) if dn - 1 >= 0 else -1.0
        if aU >= aD and up < n - 1:
            st = min(2, n - 1 - up); acc += rows[up + 1:up + 1 + st].sum(); up += st
        elif dn > 0:
            st = min(2, dn); acc += rows[dn - st:dn].sum(); dn -= st
        else:
            break
    return (base + up + 1) * ROW, (base + ip + 0.5) * ROW, (base + dn) * ROW


def vwap_bands(h, l, c, v, tdi):
    """Per 1m bar: VWAP and sigma through that bar, anchored at the session start (18:00)."""
    p = (h + l + c) / 3
    g = pd.DataFrame({"pv": p * v, "v": v, "ppv": p * p * v}).groupby(tdi).cumsum()
    vw = (g.pv / g.v).to_numpy()
    sd = np.sqrt(np.maximum((g.ppv / g.v).to_numpy() - vw * vw, 0))
    return vw, sd


def setups():
    S = E.load()
    H, L, C, HB, LB, tdi, tod, k5 = S["H"], S["L"], S["C"], S["HB"], S["LB"], S["tdi"], S["tod"], S["k5"]
    first5, last5 = S["first5"], S["last5"]
    n = len(H)
    V = S["a"].volume.to_numpy().astype(float)
    es = pd.read_parquet("data/bars/ES_1m.parquet").reindex(S["ts"])
    VB = es.volume.fillna(0).to_numpy().astype(float)       # a missing ES minute adds no volume
    CB = es.close.ffill().to_numpy()
    starts = np.r_[0, np.flatnonzero(np.diff(tdi)) + 1]
    ends = np.r_[starts[1:], n]
    vw, sd = vwap_bands(H, L, C, V, tdi)
    vwB, sdB = vwap_bands(HB, LB, CB, VB, tdi)
    mov = {"VWAP": (vw, vwB)}
    for k, m in (("+1s", 1), ("-1s", -1), ("+2s", 2), ("-2s", -2)):
        mov["VWAP" + k] = (vw + m * sd, vwB + m * sdB)
    dH = pd.Series(H).groupby(tdi).max().to_numpy(); dL = pd.Series(L).groupby(tdi).min().to_numpy()
    dHB = pd.Series(HB).groupby(tdi).max().to_numpy(); dLB = pd.Series(LB).groupby(tdi).min().to_numpy()
    out, lv_rows = [], []

    def es_check(j, lvB_at, high):
        """SMT as known at each minute over the sweep's 5m bar: ('no', None) or ('ok', minute ES takes it later)."""
        k = k5[j]
        for m in range(first5[k], last5[k] + 1):
            x = (HB[m] > lvB_at(m) + TOL) if high else (LB[m] < lvB_at(m) - TOL)
            if x:
                return ("no", None) if m <= j else ("ok", m)
        return "ok", None

    for s in range(len(starts)):
        a1, b1 = starts[s], ends[s]
        t = tod[a1:b1]
        rth = np.flatnonzero((t >= 570) & (t < 1080))
        lv = []                                       # (type, mnq(j), es(j), high?, low?, from)
        sidx = tdi[a1]
        if s > 0:
            lv.append(("PDH", lambda j, x=dH[sidx - 1]: x, lambda j, x=dHB[sidx - 1]: x, True, False, a1))
            lv.append(("PDL", lambda j, x=dL[sidx - 1]: x, lambda j, x=dLB[sidx - 1]: x, False, True, a1))
        if len(rth) and rth[0] > 30:
            o = a1 + rth[0]                           # the 09:30 bar
            on = slice(a1, o)
            m3, b3 = profile(H[on], L[on], V[on]), profile(HB[on], LB[on], VB[on])
            lv_rows.append(dict(sess=s, date=str(S["td"][o])[:10], VAH=m3[0], POC=m3[1], VAL=m3[2], ONH=H[on].max(), ONL=L[on].min(),
                                VAH_es=b3[0], POC_es=b3[1], VAL_es=b3[2], ONH_es=HB[on].max(), ONL_es=LB[on].min()))
            lv.append(("ONH", lambda j, x=H[on].max(): x, lambda j, x=HB[on].max(): x, True, False, o))
            lv.append(("ONL", lambda j, x=L[on].min(): x, lambda j, x=LB[on].min(): x, False, True, o))
            for name, x, y in zip(("VAH", "POC", "VAL"), m3, b3):
                if not (np.isnan(x) or np.isnan(y)):
                    lv.append((name, lambda j, x=x: x, lambda j, y=y: y, True, True, o))
            for name, (m_, b_) in mov.items():
                lv.append((name, lambda j, m_=m_: m_[j - 1], lambda j, b_=b_: b_[j - 1], True, True, o))
        for name, f, fB, can_hi, can_lo, fr in lv:
            two = can_hi and can_lo
            js = np.arange(max(fr, a1 + 1), b1)
            if not len(js):
                continue
            Lj = np.broadcast_to(np.asarray(f(js), dtype=float), js.shape)
            for high, ok in ((True, can_hi), (False, can_lo)):
                if not ok:
                    continue
                hit = (H[js] > Lj + TOL) if high else (L[js] < Lj - TOL)
                if two:
                    hit &= (C[js - 1] < Lj) if high else (C[js - 1] > Lj)
                h = np.flatnonzero(hit)
                if not len(h):
                    continue
                j = js[h[0]]
                st, dies = es_check(j, fB, high)
                if st == "ok":
                    out.append(dict(dir="S" if high else "L", kind=name, sweep=j, active=j, dies=dies,
                                    lvl=float(f(j)), lvlB=float(fB(j)), sess=s))
    d = pd.DataFrame(out).sort_values(["sess", "active", "sweep"]).reset_index(drop=True)
    S["setups"], S["starts"], S["ends"] = d, starts, ends
    return d, pd.DataFrame(lv_rows)


def one_per_day(sig):
    t, _ = _trades(sig, "T3")
    if t.empty:
        return t
    return t.sort_values("j").groupby("sess", sort=False).head(1).sort_values("j").reset_index(drop=True)


def show(t, funnel, label):
    s = E.summary(t)
    print(f"\n==== {label}: " + "  ".join(f"{k} {v}" for k, v in s.items()))
    y = t.entry_time.dt.year
    for name, col in (("year", y), ("side", t.side), ("level type", t.smt), ("zone", t.zone), ("exit", t.reason)):
        print(f"  by {name}: " + " | ".join(f"{k}: n {len(g)} net {g.pnl.sum():+,.0f} R {g.R.mean():+.3f}" for k, g in t.groupby(col)))
    print("  funnel: " + " -> ".join(f"{k[2:]} {v}" for k, v in sorted(funnel.items()) if "[" not in k))
    return s


def run_all():
    OUT.mkdir(parents=True, exist_ok=True)
    d, lv = setups()
    lv.to_csv(OUT / "levels.csv", index=False)
    d.to_csv(OUT / "setups.csv", index=False)
    print(f"setups (sweep + SMT): {len(d)}  by type: " + ", ".join(f"{k} {v}" for k, v in d.kind.value_counts().items()))
    rows = []
    for name, zr in (("L7", True), ("L7-noHTF", False)):
        sig, fun = E.signals(**E.PRIMARY, zset=E.ZONES_ALL, zone_req=zr)
        t = one_per_day(sig)
        fun = dict(fun); fun["6 signals in window"] = int(sig.inwin.sum()); fun["7 trades (1 per day)"] = len(t)
        t.to_csv(OUT / f"{name}.csv", index=False)
        s = show(t, fun, name)
        print("  by level type, setups (all hours) -> trades: " + ", ".join(
            f"{k} {int(((d.kind == k)).sum())} -> {int((t.smt == k).sum())}" for k in TYPES))
        nb = []
        for f in (3, 8):
            tn = one_per_day(E.signals(**{**E.PRIMARY, "fresh": f}, zset=E.ZONES_ALL, zone_req=zr)[0])
            sn = E.summary(tn); nb.append(sn)
            print(f"    neighbour fresh={f}: " + "  ".join(f"{k} {v}" for k, v in sn.items()))
        ok, parts = E.passes(s, nb)
        print(f"  criterion (before the shuffle test): {'PASS' if ok else 'fail'} {parts}")
        rows.append(dict(run=name, **s, **{f"crit_{k}": v for k, v in parts.items()}, passes=ok,
                         nb3_R=nb[0].get("R"), nb8_R=nb[1].get("R")))
        sp = "side,smt,zone" if zr else "side,smt"
        print(subprocess.run([sys.executable, "tools/split_check.py", str(OUT / f"{name}.csv"), "--splits", sp],
                             capture_output=True, text=True).stdout)
    pd.DataFrame(rows).to_csv(OUT / "summary.csv", index=False)
    print(pd.DataFrame(rows).to_string(index=False))


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "all"
    if cmd == "all":
        run_all()
    elif cmd == "charts":
        setups()
        E.trades = lambda sig, ex="T3", session="ny": (one_per_day(sig), {})
        E.charts(10, 11, out="data/studies/ifvg_l7_charts", prefix="l7")
