#!/usr/bin/env python3
"""ACE1: Aceflw brief levels, Calls and setups on MNQ 1m (pre-registered in BACKTEST_LOG.md, "ACE1").

    python3 tools/ace1.py parse          setups and Calls as parsed (no bars used)
    python3 tools/ace1.py check          contract check: brief OVN High / Low vs MNQ 18:00-09:29
    python3 tools/ace1.py all            Tests 1-3, tables to stdout, detail CSVs to data/studies/ace1/

Prices in the briefs are NQ; MNQ trades the same prices. Tick 0.25, 1 MNQ = $2/pt, house fills.
"""
import re, sys, math, pathlib
import numpy as np, pandas as pd
from powell_engine import rma_atr

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "studies" / "ace1"
TICK, PV, COMM = 0.25, 2.0, 1.0
L1_TYPES = ["val", "poc", "vah", "vwap", "vwap_sigma_up", "vwap_sigma_dn", "on_high", "on_low", "gamma_wall",
            "put_wall", "call_wall", "vol_trigger", "draw_up", "draw_down"]
GROUPS = {"gex (gamma/put/call wall, vol trigger)": ["gamma_wall", "put_wall", "call_wall", "vol_trigger"],
          "value area (val/poc/vah)": ["val", "poc", "vah"]}
NUM = re.compile(r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d{4,6}(?:\.\d+)?")
# Aceflw on a different contract from Databento's front month (roll), amendment of 2026-10-08: excluded, not counted
CONTRACT_MISMATCH = {"2026-09-15", "2026-09-16", "2026-09-17"}
CALLS = {  # sentence prefix -> (class, direction, strict)
    "Below value in short-gamma → breakdown continuation": ("dir", -1, True),
    "Above value in short-gamma → breakout continuation": ("dir", 1, True),
    "Below value in long-gamma → value-retest SHORT": ("dir", -1, False),
    "Above value in long-gamma → value-retrace LONG": ("dir", 1, False),
    "Balanced inside value in long-gamma": ("nondir", 0, "balanced"),
    "Inside value in short-gamma → respect breaks": ("nondir", 0, "respect breaks"),
}


def binom_p(k, n, p0):
    """One-sided exact binomial P(X >= k), X ~ Bin(n, p0)."""
    return sum(math.comb(n, i) * p0 ** i * (1 - p0) ** (n - i) for i in range(k, n + 1))


def num(s):
    return float(s.replace(",", ""))


def prices_outside_parens(s):
    s = re.sub(r"\([^)]*\)", " ", s or "")
    return [num(m) for m in NUM.findall(s)]


def load_briefs():
    b = pd.read_csv(ROOT / "data" / "aceflw" / "briefs.csv", dtype=str)
    b["px"] = b.price.map(lambda s: num(s) if isinstance(s, str) and "–" not in s and NUM.fullmatch(s) else np.nan)
    return b


# ---------------------------------------------------------------- parsing
def parse_setups(b):
    rows = []
    for _, r in b[b.item_type == "setup"].iterrows():
        f = {k.strip(): v.strip() for k, v in (p.split(":", 1) for p in r.note.split(" | ") if ":" in p)}
        zone = sorted(num(m) for m in NUM.findall(r.price))
        d = f.get("direction", "").upper()
        if d not in ("LONG", "SHORT"):
            hits = {w for w in ("LONG", "SHORT") if w in r.label.upper()}
            d = hits.pop() if len(hits) == 1 else ""
        conv = f.get("conviction", "")
        cl = conv.lower()
        bucket = ("High" if cl.startswith("high") else "Low" if cl.startswith("low") or cl.startswith("medium-low")
                  else "Medium" if cl.startswith("medium") else "none")
        watch = bool(re.search(r"watch|not armed", (r.label + " " + conv).lower()))
        st = prices_outside_parens(f.get("stop", ""))
        rows.append(dict(date=r.date, brief=r.brief, label=r.label, zone_lo=zone[0], zone_hi=zone[-1],
                         direction=d, stop=st[0] if st else np.nan, chain=prices_outside_parens(f.get("target", "")),
                         conviction=conv, bucket=bucket, watch=watch))
    return pd.DataFrame(rows)


def call_class(note):
    for k, v in CALLS.items():
        if note.startswith(k):
            return v
    raise ValueError(f"unclassified Call: {note}")


# ---------------------------------------------------------------- bars
def load_bars():
    one = pd.read_parquet(ROOT / "data" / "bars" / "MNQ_1m.parquet")
    b5 = pd.read_parquet(ROOT / "data" / "bars" / "MNQ_5m.parquet")
    atr5 = pd.Series(rma_atr(b5.high.to_numpy(), b5.low.to_numpy(), b5.close.to_numpy()), index=b5.index)
    return one, atr5


def session(one, d):
    """1m bars 09:29..15:59 of New York date d (09:29 row first, used for 'price at 09:30')."""
    t0 = pd.Timestamp(f"{d} 09:29", tz="America/New_York")
    x = one.loc[t0: t0 + pd.Timedelta(minutes=390)]
    assert x.index[0] == t0 and x.index[2] == t0 + pd.Timedelta(minutes=2), f"missing opening bars on {d}"
    return x


def atr_before(atr5, ts):
    """ATR of the last 5m bar closed at or before ts (the open of the 1m bar in question)."""
    k = atr5.index.searchsorted(ts - pd.Timedelta(minutes=5), side="right") - 1
    return atr5.iloc[k]


def contract_check(b, one):
    rows = []
    for d in sorted(b.date.unique()):
        pm = b[(b.date == d) & (b.brief == "premarket")]
        hi, lo = pm[pm.item_type == "on_high"].px.iloc[0], pm[pm.item_type == "on_low"].px.iloc[0]
        t1 = pd.Timestamp(f"{d} 09:29", tz="America/New_York")
        t0 = (t1 - pd.Timedelta(days=1)).normalize() + pd.Timedelta(hours=18)
        if t1.dayofweek == 0:
            t0 -= pd.Timedelta(days=2)
        x = one.loc[t0:t1]
        rows.append(dict(date=d, brief_hi=hi, mnq_hi=x.high.max(), brief_lo=lo, mnq_lo=x.low.min(),
                         d_hi=hi - x.high.max(), d_lo=lo - x.low.min(), bars=len(x),
                         instr=x.instrument_id.iloc[-1] if len(x) else None))
    c = pd.DataFrame(rows)
    c["flag"] = (c.d_hi.abs() > 10) | (c.d_lo.abs() > 10) | (c.bars == 0)
    c["kind"] = np.where(~c.flag, "", np.where(c.date.isin(CONTRACT_MISMATCH), "contract", "level"))
    return c


# ---------------------------------------------------------------- Test 1
def react(x, a, L, atr):
    """x: session arrays (o,h,l,c) with index 0 = 09:29 bar. Returns dict for level L, or touched=False."""
    o, h, l, c = a
    band = 2 * TICK
    hit = np.flatnonzero((l[1:] <= L + band) & (h[1:] >= L - band))
    if not len(hit):
        return dict(touched=False)
    t = hit[0] + 1
    prev = c[t - 1]
    if abs(prev - L) <= band and t == 1:
        return dict(touched=True, at_open=True)
    side = 1 if prev > L else -1                      # +1 approached from above
    r = dict(touched=True, at_open=False, side=side, t=t, atr=atr(x.index[t]))
    for m in (15, 30):
        if t + m < len(c):
            r[f"rej{m}"] = (c[t + m] - L) * side > 0
    if t + 30 < len(c):
        ex = (h[t + 1:t + 31].max() - L) if side > 0 else (L - l[t + 1:t + 31].min())
        r["exc30"] = ex / r["atr"]
    return r


def test1(b, one, atr5, days, nrand=50, nperm=10000, seed=1):
    rng = np.random.default_rng(seed)
    lv = b[(b.brief == "premarket") & b.item_type.isin(L1_TYPES) & b.px.notna() & b.date.isin(days)]
    real, rand = [], []
    for d, g in lv.groupby("date"):
        x = session(one, d)
        a = (x.open.to_numpy(), x.high.to_numpy(), x.low.to_numpy(), x.close.to_numpy())
        op = a[0][1]
        atr = lambda ts: atr_before(atr5, ts)
        for i, r in g.iterrows():
            dist = abs(r.px - op)
            real.append(dict(id=i, date=d, type=r.item_type, label=r.label, level=r.px, dist=dist,
                             **react(x, a, r.px, atr)))
            for k in range(nrand):
                L = op + rng.choice([-1, 1]) * dist * (1 + rng.uniform(-0.1, 0.1))
                L = round(L / TICK) * TICK
                rand.append(dict(id=i, k=k, type=r.item_type, level=L, **react(x, a, L, atr)))
    R, Z = pd.DataFrame(real), pd.DataFrame(rand)
    for df in (R, Z):
        for col in ("at_open", "side", "t", "atr", "rej15", "rej30", "exc30"):
            if col not in df:
                df[col] = np.nan
    return R, Z


def t1_stats(R, Z, ids, nperm, rng):
    r, z = R[R.id.isin(ids)], Z[Z.id.isin(ids)]
    rv = r[r.touched & (r.at_open != True)]
    zv = z[z.touched & (z.at_open != True)]
    out = dict(n=len(r), touched=int(r.touched.sum()), at_open=int((r.at_open == True).sum()),
               touch_rate=r.touched.mean(), touch_base=z.touched.mean(),
               n15=int(rv.rej15.notna().sum()), rej15=rv.rej15.dropna().astype(float).mean(),
               base15=zv.rej15.dropna().astype(float).mean(),
               n30=int(rv.rej30.notna().sum()), rej30=rv.rej30.dropna().astype(float).mean(),
               base30=zv.rej30.dropna().astype(float).mean(),
               exc30=rv.exc30.dropna().mean(), base_exc30=zv.exc30.dropna().mean())
    # permutation: each resample takes one random level per real level
    ids = list(r.id)
    k = rng.integers(0, Z.k.max() + 1, size=(nperm, len(ids)))
    zz = z.set_index(["id", "k"]).sort_index()
    valid = (zz.touched & (zz.at_open != True))
    rej = zz.rej30.where(valid).astype(float)
    exc = zz.exc30.where(valid).astype(float)
    rej_m = np.array([rej.loc[i].to_numpy() for i in ids]).T      # (50, n)
    exc_m = np.array([exc.loc[i].to_numpy() for i in ids]).T
    pick_r = rej_m[k, np.arange(len(ids))]
    pick_e = exc_m[k, np.arange(len(ids))]
    pr, pe = np.nanmean(pick_r, axis=1), np.nanmean(pick_e, axis=1)
    out["p_rej30"] = (1 + np.sum(pr >= out["rej30"])) / (1 + nperm) if out["n30"] else np.nan
    out["p_exc30"] = (1 + np.sum(pe >= out["exc30"])) / (1 + nperm) if out["n30"] else np.nan
    return out


# ---------------------------------------------------------------- Test 2
def test2(b, one, days):
    rows = []
    for d in days:
        x = session(one, d)
        c = x.close.to_numpy()
        for br in ("premarket", "postopen"):
            g = b[(b.date == d) & (b.brief == br)]
            note = g[g.item_type == "call"].note.iloc[0]
            cls, dirn, sub = call_class(note)
            start = c[0] if br == "premarket" else c[1]
            end = c[-1]
            val, vah = g[g.item_type == "val"].px.iloc[0], g[g.item_type == "vah"].px.iloc[0]
            rows.append(dict(date=d, brief=br, cls=cls, dirn=dirn, sub=sub, start=start, end=end,
                             up=end > start, inside=val <= end <= vah, val=val, vah=vah))
    return pd.DataFrame(rows)


def t2_report(T):
    lines = []
    for br, g in T.groupby("brief", sort=False):
        u = g.up.mean()
        base_in = g.inside.mean()
        lines.append(f"\n{br}: {len(g)} days scored · up sessions {g.up.sum()}/{len(g)} = {u:.1%} · "
                     f"16:00 close inside VAL–VAH {g.inside.sum()}/{len(g)} = {base_in:.1%}")
        lines.append(f"| Calls (n = {len(g)} days) | n | hits | hit % | expected % | one-sided p |")
        lines.append("|---|---|---|---|---|---|")
        for name, s in [("directional, strict + broad", g[g.cls == "dir"]),
                        ("directional, strict only", g[(g.cls == "dir") & (g["sub"] == True)]),
                        ("directional, broad only", g[(g.cls == "dir") & (g["sub"] == False)])]:
            if not len(s):
                lines.append(f"| {name} | 0 | | | | |"); continue
            hit = ((s.dirn > 0) & s.up) | ((s.dirn < 0) & ~s.up & (s.end != s.start))
            p0 = np.mean(np.where(s.dirn > 0, u, 1 - u))
            p = binom_p(int(hit.sum()), len(s), p0)
            nu, nd = int((s.dirn > 0).sum()), int((s.dirn < 0).sum())
            lines.append(f"| {name} ({nu} up / {nd} down) | {len(s)} | {int(hit.sum())} | {hit.mean():.1%} | {p0:.1%} | {p:.3f} |")
        for name, s in [("non-directional, both", g[g.cls == "nondir"]),
                        ("  balanced → fade edges", g[g["sub"] == "balanced"]),
                        ("  respect breaks", g[g["sub"] == "respect breaks"])]:
            if not len(s):
                lines.append(f"| {name} | 0 | | | | |"); continue
            p = binom_p(int(s.inside.sum()), len(s), base_in)
            lines.append(f"| {name} (close inside VAL–VAH) | {len(s)} | {int(s.inside.sum())} | {s.inside.mean():.1%} | {base_in:.1%} | {p:.3f} |")
    return "\n".join(lines)


# ---------------------------------------------------------------- Test 3
def sim_setup(s, x, variant):
    """One setup on session bars x (row 0 = 09:29). Returns dict."""
    if np.isnan(s.stop):
        return dict(unscorable=True)
    o, h, l, c = (x[k].to_numpy() for k in ("open", "high", "low", "close"))
    t0 = 1 if s.brief == "premarket" else 2               # 09:30 bar / 09:31 bar
    sgn = 1 if s.direction == "LONG" else -1
    ref = o[t0]
    if s.zone_lo <= ref <= s.zone_hi:
        fi, edge, fill = t0, ref, ref
    else:
        edge = s.zone_hi if ref > s.zone_hi else s.zone_lo
        above = ref > edge
        hit = np.flatnonzero((l[t0:] <= edge) if above else (h[t0:] >= edge))
        if not len(hit):
            return dict(filled=False)
        fi = hit[0] + t0
        fill = min(o[fi], edge) if above else max(o[fi], edge)   # opening beyond the limit fills at the open
    entry = fill + sgn * TICK                              # 1 tick slippage
    stop = s.stop
    risk = (entry - stop) * sgn
    if not risk >= TICK:
        return dict(filled=True, unscorable=True)
    chain = [p for p in s.chain if (p - entry) * sgn >= TICK]
    tgt = (chain[0] if variant == "T1" else chain[-1]) if chain else np.nan
    exit_px, why, xi = None, None, None
    for i in range(fi, len(c)):
        if (l[i] <= stop) if sgn > 0 else (h[i] >= stop):
            gap = (o[i] <= stop) if sgn > 0 else (o[i] >= stop)
            exit_px, why, xi = (o[i] if gap and i > fi else stop), "stop", i
            break
        if i > fi and not np.isnan(tgt) and ((h[i] >= tgt) if sgn > 0 else (l[i] <= tgt)):
            gap = (o[i] >= tgt) if sgn > 0 else (o[i] <= tgt)
            exit_px, why, xi = (o[i] if gap else tgt), "target", i
            break
    if exit_px is None:
        exit_px, why, xi = c[-1], "time", len(c) - 1
    exit_px -= sgn * TICK
    pts = (exit_px - entry) * sgn
    net = pts * PV - 2 * COMM
    return dict(filled=True, unscorable=False, fill_time=x.index[fi].strftime("%H:%M"), entry=entry, target=tgt,
                exit=exit_px, why=why, exit_time=x.index[xi].strftime("%H:%M"), risk_pts=risk, net=net,
                R=net / (risk * PV))


def test3(S, one, days):
    rows = []
    for _, s in S.iterrows():
        base = s.to_dict()
        base["chain"] = " → ".join(f"{p:,.2f}" for p in s.chain)
        if s.date not in days:
            rows.append(dict(base, variant="T1", excluded=True)); rows.append(dict(base, variant="T-last", excluded=True))
            continue
        x = session(one, s.date)
        for v in ("T1", "T-last"):
            if not s.direction:
                rows.append(dict(base, variant=v, excluded=False, filled=np.nan, unscorable=True)); continue
            rows.append(dict(base, variant=v, excluded=False, **sim_setup(s, x, v)))
    return pd.DataFrame(rows)


def t3_table(T, title):
    lines = [f"\n{title}", "| Bucket | setups | unscorable | filled | net $ | R/trade | total R | win % | stops / targets / time |",
             "|---|---|---|---|---|---|---|---|---|"]
    def row(name, g):
        sc = g[g.filled == True]
        un = int((g.unscorable == True).sum())
        tr = sc[sc.unscorable == False]
        if not len(tr):
            return f"| {name} | {len(g)} | {un} | {len(tr)} | | | | | |"
        w = tr.why.value_counts()
        return (f"| {name} | {len(g)} | {un} | {len(tr)} | {tr.net.sum():+,.0f} | {tr.R.mean():+.3f} | {tr.R.sum():+.1f} | "
                f"{(tr.net > 0).mean():.0%} | {w.get('stop', 0)} / {w.get('target', 0)} / {w.get('time', 0)} |")
    lines.append(row("all", T))
    for k in ("High", "Medium", "Low", "none"):
        lines.append(row(k, T[T.bucket == k]))
    lines.append(row("watch-only flagged", T[T.watch]))
    lines.append(row("armed (not watch-only)", T[~T.watch]))
    return "\n".join(lines)


# ---------------------------------------------------------------- main
def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "all"
    b = load_briefs()
    S = parse_setups(b)
    if cmd == "parse":
        pd.set_option("display.width", 250); pd.set_option("display.max_rows", 500)
        print(S[["date", "brief", "zone_lo", "zone_hi", "direction", "stop", "chain", "bucket", "watch"]].to_string())
        for n in b[b.item_type == "call"].note.unique():
            print(call_class(n), "|", n)
        return
    one, atr5 = load_bars()
    C = contract_check(b, one)
    OUT.mkdir(parents=True, exist_ok=True)
    C.to_csv(OUT / "contract_check.csv", index=False)
    print(f"bars end {one.index[-1]}")
    print(C.to_string(index=False))
    if cmd == "check":
        return
    nlev = int((C.kind == "level").sum())
    if nlev > 5:
        sys.exit(f"{nlev} level-mismatch days flagged > 5: stopping before the tests, as pre-registered")
    days = sorted(C.date[~C.flag])
    nosess = [d for d in days if pd.Timestamp(f"{d} 15:59", tz="America/New_York") not in one.index]
    days = [d for d in days if d not in nosess]           # bars end before the session close (data licence)
    print(f"\nscored days: {len(days)} of {len(C)}; excluded, level mismatch ({nlev}): "
          f"{', '.join(C.date[C.kind == 'level']) or 'none'}; excluded, contract mismatch: "
          f"{', '.join(C.date[C.kind == 'contract']) or 'none'}; excluded, no session bars: {', '.join(nosess) or 'none'}")

    # Test 1
    R, Z = test1(b, one, atr5, days)
    R.to_csv(OUT / "test1_levels.csv", index=False)
    rng = np.random.default_rng(1)
    rows = []
    for ty in L1_TYPES:
        rows.append(dict(type=ty, **t1_stats(R, Z, set(R.id[R.type == ty]), 10000, rng)))
    for gname, tys in GROUPS.items():
        rows.append(dict(type=gname, **t1_stats(R, Z, set(R.id[R.type.isin(tys)]), 10000, rng)))
    T1 = pd.DataFrame(rows)
    T1.to_csv(OUT / "test1_summary.csv", index=False)
    print(f"\nTEST 1 — pre-market level reactions, MNQ 1m, {len(days)} days, 50 random levels per real level")
    print("| Type | levels | touched (rate · base) | at open | rejection 15m (base) | n30 | rejection 30m (base) | p | excursion 30m ATR (base) | p |")
    print("|---|---|---|---|---|---|---|---|---|---|")
    for _, r in T1.iterrows():
        a = 0.05 / 14 if r.type in L1_TYPES else 0.05 / 2
        star = lambda p: f"{p:.4f}" + (" ✓" if p < a else "")
        print(f"| {r.type} | {r.n} | {r.touched} ({r.touch_rate:.0%} · {r.touch_base:.0%}) | {r.at_open} | "
              f"{r.rej15:.0%} ({r.base15:.0%}) | {r.n30} | {r.rej30:.0%} ({r.base30:.0%}) | {star(r.p_rej30)} | "
              f"{r.exc30:.2f} ({r.base_exc30:.2f}) | {star(r.p_exc30)} |")

    # Test 2
    T2 = test2(b, one, days)
    T2.to_csv(OUT / "test2_calls.csv", index=False)
    print(f"\nTEST 2 — the Call, {len(days)} days")
    print(t2_report(T2))

    # Test 3
    T3 = test3(S, one, set(days))
    T3.to_csv(OUT / "test3_setups.csv", index=False)
    print(f"\nTEST 3 — setups, {len(days)} days")
    for br in ("premarket", "postopen"):
        for v in ("T1", "T-last"):
            g = T3[(T3.brief == br) & (T3.variant == v) & (T3.excluded == False)]
            print(t3_table(g, f"{br}, target {v} (n = {len(g)} setups over {len(days)} days)"))


if __name__ == "__main__":
    main()
