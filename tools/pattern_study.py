#!/usr/bin/env python3
"""Pattern base-rate study, MNQ 5m and 1m, patterns completed on 09:30-16:00 bars, no strategy.

    python3 tools/pattern_study.py [--out data/studies/pattern_study.csv]

Patterns, decided at the close of bar t with no lookahead (bearish / bullish = the direction the pattern points):
    engulfing   bearish: bar t-1 up (C>O), bar t down, O_t >= C_t-1, C_t <= O_t-1, body_t > body_t-1; bullish mirror
    pin bar     bearish: upper wick >= 2 x body, open and close in the bar's lower third; bullish mirror
    inside bar  H_t < H_t-1 and L_t > L_t-1; split by the inside bar's own close (down = bearish, up = bullish)
    3-bar rev.  bearish: H_t-1 > H_t-2 and C_t < min(L_t-1, L_t-2); bullish mirror
    double top  the latest 3-bar fractal high of the day (centre m, usable from bar m+2), then the first later bar whose
                high is within 0.1 x the day's range so far of it; double bottom mirror; one touch per swing
Measured from C_t, in the pattern's direction: forward return after 6, 12, 24 bars in points and in trailing 20-bar ATR
(true range, bars t-19..t); 'reversal held' = price did not go beyond the pattern's extreme (bearish: its highest high;
bullish: its lowest low) within the next 24 bars. Forward windows must stay inside the same cash session.
Base rate: every 09:30-16:00 bar at the same time of day, measured the same way (extreme = the bar's own high / low),
averaged over the pattern's time-of-day mix.
Conditions: all; near the overnight extreme (bearish: pattern high within 0.25 x overnight width of the overnight high;
bullish: low within 0.25 x of the overnight low); at the VWAP 2-sigma band (bearish: high >= VWAP + 2 sigma, bullish:
low <= VWAP - 2 sigma; VWAP from 09:30, hlc3 x volume, sigma = volume-weighted std of hlc3).
Test (per comparison, for the 12-bar ATR excess over base): shuffle of the pattern label among bars of the same time of
day; p (one-sided, pattern better than base) from the shuffle distribution's exact mean and variance (normal
approximation, checked against explicit shuffles). Verdict rule: excess >= 0.1 ATR at 12 bars and p < 0.01 / (number of
comparisons) in both 2019-06..2022-12 and 2023-01..2026-09.
"""
import sys, math
import numpy as np
import pandas as pd
from numpy.lib.stride_tricks import sliding_window_view as swv

HORIZ = (6, 12, 24)
HALVES = (("2019-2022", 2019, 2022), ("2023-2026", 2023, 2026))
PATTERNS = ("engulfing", "pin", "inside", "3bar", "double")


def load(tf):
    one = pd.read_parquet("data/bars/MNQ_1m.parquet")
    if tf == 1:
        return one
    return one.resample(f"{tf}min", label="left", closed="left").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}).dropna(subset=["open"])


def features(b, tf):
    ts = b.index
    n = len(b)
    O, H, L, C, V = (b[k].to_numpy(float) for k in ("open", "high", "low", "close", "volume"))
    tod = np.asarray(ts.hour * 60 + ts.minute)
    date = np.asarray(ts.date)
    rth = (tod >= 570) & (tod < 960)
    # ATR 20 (trailing, includes t)
    pc = np.r_[np.nan, C[:-1]]
    tr = np.nanmax(np.c_[H - L, np.abs(H - pc), np.abs(L - pc)], axis=1)
    atr = pd.Series(tr).rolling(20).mean().to_numpy()
    # forward windows valid only inside the same cash session without a gap
    step = pd.Timedelta(minutes=tf)
    fwd = {}
    for k in HORIZ:
        j = np.arange(n) + k
        ok = j < n
        jj = np.where(ok, j, n - 1)
        ok &= (date[jj] == date) & (tod[jj] < 960) & ((ts[jj] - ts) <= k * step + pd.Timedelta(minutes=tf))
        fwd[k] = (np.where(ok, C[jj] - C, np.nan))
    Hn = swv(np.r_[H[1:], np.full(24, np.nan)], 24).max(axis=1)[:n]       # max high of bars t+1..t+24
    Ln = swv(np.r_[L[1:], np.full(24, np.nan)], 24).min(axis=1)[:n]
    ok24 = ~np.isnan(fwd[24])
    # day-so-far range, VWAP / sigma from 09:30, overnight range for the session
    d = pd.DataFrame({"date": date, "H": H, "L": L, "hlc": (H + L + C) / 3, "V": V, "rth": rth})
    r = d[d.rth]
    g = r.groupby("date")
    day_hi = np.full(n, np.nan); day_lo = np.full(n, np.nan)
    day_hi[rth] = g.H.cummax().to_numpy(); day_lo[rth] = g.L.cummin().to_numpy()
    cpv = (r.hlc * r.V).groupby(r.date).cumsum().to_numpy()
    cv = r.V.groupby(r.date).cumsum().to_numpy()
    cppv = (r.hlc ** 2 * r.V).groupby(r.date).cumsum().to_numpy()
    vw = np.full(n, np.nan); sg = np.full(n, np.nan)
    with np.errstate(invalid="ignore", divide="ignore"):
        vw[rth] = cpv / cv
        sg[rth] = np.sqrt(np.maximum(cppv / cv - (cpv / cv) ** 2, 0))
    sessions = np.array(sorted(set(date[rth])))
    onm = (tod >= 1080) | (tod < 570)
    k_ = np.where(tod >= 1080, np.searchsorted(sessions, date, side="right"), np.searchsorted(sessions, date, side="left"))
    okn = onm & (k_ < len(sessions))
    on = pd.DataFrame({"s": sessions[k_[okn]], "H": H[okn], "L": L[okn]}).groupby("s").agg(H=("H", "max"), L=("L", "min"))
    onH = pd.Series(date).map(on.H).to_numpy(float); onL = pd.Series(date).map(on.L).to_numpy(float)
    return dict(n=n, O=O, H=H, L=L, C=C, tod=tod, date=date, rth=rth, atr=atr, fwd=fwd, Hn=Hn, Ln=Ln, ok24=ok24,
                day_hi=day_hi, day_lo=day_lo, vw=vw, sg=sg, onH=onH, onL=onL, year=np.asarray(ts.year), ts=ts)


def detect(F):
    """{(pattern, 'bear'|'bull'): (indices t, extreme price)}"""
    O, H, L, C, rth, date, n = F["O"], F["H"], F["L"], F["C"], F["rth"], F["date"], F["n"]
    body = np.abs(C - O)
    rng = H - L
    up, dn = C > O, C < O
    p1 = np.r_[False, (rth[1:] & rth[:-1]) & (date[1:] == date[:-1])]                     # t-1 in the same session
    p2 = np.r_[False, False, p1[2:] & p1[1:-1]]
    sh = lambda a, k: np.r_[np.full(k, np.nan), a[:-k]]
    out = {}
    m = rth & p1 & dn & (sh(up.astype(float), 1) == 1) & (O >= sh(C, 1)) & (C <= sh(O, 1)) & (body > sh(body, 1))
    out[("engulfing", "bear")] = (np.flatnonzero(m), np.fmax(H, sh(H, 1)))
    m = rth & p1 & up & (sh(dn.astype(float), 1) == 1) & (O <= sh(C, 1)) & (C >= sh(O, 1)) & (body > sh(body, 1))
    out[("engulfing", "bull")] = (np.flatnonzero(m), np.fmin(L, sh(L, 1)))
    third = rng / 3
    upper_w, lower_w = H - np.fmax(O, C), np.fmin(O, C) - L
    m = rth & (rng > 0) & (upper_w >= 2 * body) & (np.fmax(O, C) <= L + third)
    out[("pin", "bear")] = (np.flatnonzero(m), H)
    m = rth & (rng > 0) & (lower_w >= 2 * body) & (np.fmin(O, C) >= H - third)
    out[("pin", "bull")] = (np.flatnonzero(m), L)
    ins = rth & p1 & (H < sh(H, 1)) & (L > sh(L, 1))
    out[("inside", "bear")] = (np.flatnonzero(ins & dn), H)
    out[("inside", "bull")] = (np.flatnonzero(ins & up), L)
    m = rth & p2 & (sh(H, 1) > sh(H, 2)) & (C < np.fmin(sh(L, 1), sh(L, 2)))
    out[("3bar", "bear")] = (np.flatnonzero(m), np.fmax(np.fmax(H, sh(H, 1)), sh(H, 2)))
    m = rth & p2 & (sh(L, 1) < sh(L, 2)) & (C > np.fmax(sh(H, 1), sh(H, 2)))
    out[("3bar", "bull")] = (np.flatnonzero(m), np.fmin(np.fmin(L, sh(L, 1)), sh(L, 2)))
    # double top / bottom: loop per session
    dt_i, dt_x, db_i, db_x = [], [], [], []
    idx = np.flatnonzero(rth)
    starts = np.r_[0, np.flatnonzero(date[idx][1:] != date[idx][:-1]) + 1, len(idx)]
    for a, b_ in zip(starts[:-1], starts[1:]):
        s = idx[a:b_]
        fh = fl = None                      # (price, centre) of the latest usable fractal; touched flag
        th = tl = False
        for q in range(len(s)):
            t = s[q]
            # fractal centred at q-2 becomes usable at bar q (confirmed at q-1, usable 2 bars after the centre)
            if q >= 3:
                c_ = s[q - 2]
                if H[c_] > H[s[q - 3]] and H[c_] > H[s[q - 1]]:
                    fh, th = (H[c_], c_), False
                if L[c_] < L[s[q - 3]] and L[c_] < L[s[q - 1]]:
                    fl, tl = (L[c_], c_), False
            tol = 0.1 * (F["day_hi"][t] - F["day_lo"][t])
            if fh is not None and not th and t > fh[1] + 1 and abs(H[t] - fh[0]) <= tol:
                dt_i.append(t); dt_x.append(max(H[t], fh[0])); th = True
            if fl is not None and not tl and t > fl[1] + 1 and abs(L[t] - fl[0]) <= tol:
                db_i.append(t); db_x.append(min(L[t], fl[0])); tl = True
    ext = np.full(n, np.nan); ext[dt_i] = dt_x
    out[("double", "bear")] = (np.array(dt_i, int), ext.copy())
    ext = np.full(n, np.nan); ext[db_i] = db_x
    out[("double", "bull")] = (np.array(db_i, int), ext)
    return out


def measure(F, side, idx, ext):
    """Directional forward returns (points, ATR) and held flags for bars idx."""
    s = -1 if side == "bear" else 1
    res = {}
    for k in HORIZ:
        f = s * F["fwd"][k][idx]
        res[f"f{k}"] = f
        res[f"a{k}"] = f / F["atr"][idx]
    held = (F["Hn"][idx] <= ext[idx]) if side == "bear" else (F["Ln"][idx] >= ext[idx])
    res["held"] = np.where(F["ok24"][idx], held.astype(float), np.nan)
    return res


def main():
    rows = []
    for tf in (5, 1):
        b = load(tf)
        F = features(b, tf)
        pats = detect(F)
        pool = np.flatnonzero(F["rth"] & ~np.isnan(F["fwd"][12]) & ~np.isnan(F["atr"]) & (F["atr"] > 0))
        base = {}
        for side in ("bear", "bull"):
            m = measure(F, side, pool, np.where(side == "bear", F["H"], F["L"]))
            base[side] = pd.DataFrame(m).assign(tod=F["tod"][pool], idx=pool, year=F["year"][pool])
        for (pat, side), (idx, ext) in pats.items():
            idx = idx[np.isin(idx, pool)]
            conds = {"all": np.ones(len(idx), bool),
                     "overnight": (np.abs(ext[idx] - F["onH"][idx]) <= 0.25 * (F["onH"][idx] - F["onL"][idx]))
                     if side == "bear" else (np.abs(ext[idx] - F["onL"][idx]) <= 0.25 * (F["onH"][idx] - F["onL"][idx])),
                     "vwap2s": (F["H"][idx] >= F["vw"][idx] + 2 * F["sg"][idx]) if side == "bear"
                     else (F["L"][idx] <= F["vw"][idx] - 2 * F["sg"][idx])}
            bs = base[side]
            tod_mean = bs.groupby("tod").mean(numeric_only=True)
            for cname, cm in conds.items():
                ii = idx[cm]
                if len(ii) < 30:
                    continue
                pm = pd.DataFrame(measure(F, side, ii, ext)).assign(tod=F["tod"][ii], year=F["year"][ii])
                row = dict(tf=f"{tf}m", pattern=pat, side=side, cond=cname, n=len(ii))
                for k in HORIZ:
                    row[f"pts{k}"] = pm[f"f{k}"].mean()
                    row[f"base_pts{k}"] = tod_mean[f"f{k}"].reindex(pm.tod).mean()
                    row[f"atr{k}"] = pm[f"a{k}"].mean()
                    row[f"base_atr{k}"] = tod_mean[f"a{k}"].reindex(pm.tod).mean()
                row["held"] = pm.held.mean()
                row["base_held"] = tod_mean.held.reindex(pm.tod).mean()
                row["excess12"] = row["atr12"] - row["base_atr12"]
                for hn, lo, hi in HALVES:
                    x = pm[(pm.year >= lo) & (pm.year <= hi)]
                    bsel = bs[(bs.year >= lo) & (bs.year <= hi)]
                    tm, tv = bsel.groupby("tod").a12.mean(), bsel.groupby("tod").a12.var()
                    exc = (x.a12 - tm.reindex(x.tod).to_numpy()).mean() if len(x) else np.nan
                    sd = math.sqrt(np.nansum(tv.reindex(x.tod).to_numpy()) / len(x) ** 2) if len(x) else np.nan
                    z = exc / sd if sd and sd > 0 else np.nan
                    row[f"n_{hn}"] = len(x)
                    row[f"excess12_{hn}"] = exc
                    row[f"p_{hn}"] = 0.5 * math.erfc(z / math.sqrt(2)) if z == z else np.nan
                rows.append(row)
        print(f"{tf}m done: {F['rth'].sum():,} cash-session bars", file=sys.stderr)
    R = pd.DataFrame(rows)
    ncomp = len(R)
    thr = 0.01 / ncomp
    R["passes"] = ((R["excess12_2019-2022"] >= 0.1) & (R["excess12_2023-2026"] >= 0.1) &
                   (R["p_2019-2022"] < thr) & (R["p_2023-2026"] < thr))
    R.attrs["ncomp"] = ncomp
    return R, thr


if __name__ == "__main__":
    R, thr = main()
    pd.set_option("display.width", 250, "display.max_columns", 40, "display.max_rows", 200)
    print(f"comparisons: {len(R)}  corrected threshold p < {thr:.2e}")
    cols = ["tf", "pattern", "side", "cond", "n", "pts12", "base_pts12", "atr6", "base_atr6", "atr12", "base_atr12",
            "atr24", "base_atr24", "held", "base_held", "excess12", "excess12_2019-2022", "p_2019-2022",
            "excess12_2023-2026", "p_2023-2026", "passes"]
    print(R[cols].round(4).to_string(index=False))
    if "--out" in sys.argv:
        R.to_csv(sys.argv[sys.argv.index("--out") + 1], index=False)
