#!/usr/bin/env python3
"""BIAS study: can the trader call the day's direction from the pre-open picture? (pre-registered, no rule change)

    python3 tools/bias_study.py make  [--seed 2409] [--out data/studies/bias]
    python3 tools/bias_study.py release2                   append the block 2 rows to answers.csv
    python3 tools/bias_study.py resolve                    fill draw_level from draw_ref (printed)
    python3 tools/bias_study.py score [--out data/studies/bias] [--block 1|2|all]
    python3 tools/bias_study.py features [--block 1]         computable features from the tags vs the calls

make: 40 trading days drawn at random, 5 per calendar year 2019-2026 (numpy default_rng(seed)), from days that have
    a 09:30 bar, at least 60 earlier trading days in the data, and the same front contract at the previous cash close,
    at 09:29 and at the day's cash close (no roll inside the scored move). Randomly split into block 1 and block 2.
    One PNG per day (random 6-digit name), four panels of MNQ built from the 1m bars and cut at 09:30 New York
    (the last bar shown is the one forming at 09:29):
        Daily   60 completed trading days (18:00-17:00) + today's bar so far
        4-hour  last 10 trading days, 4h buckets from 18:00, + the bar forming
        1-hour  last 5 trading days
        15-min  the previous session and today's overnight (from the previous day's 18:00 open to 09:29)
    Each panel: prior-day high / low (previous trading day, 18:00-17:00), prior-day settlement (last 1m close before
    16:00 - CME's settlement is a 30-second VWAP, not in the data), overnight high / low (18:00-09:29), the 09:29
    close, and every FVG of that panel's timeframe formed in the window and not traded through by 09:29, labelled
    with its timeframe. No date anywhere on the chart. Key <out>/key.csv (id, block, date), never printed.
    Charts in <out>/block1/ and <out>/block2/. Answer template <out>/answers.csv (block 1 rows first; block 2 rows
    are appended when block 2 is released): id, bias (long / short / none), confidence (1-3), draw_level (a price),
    reasons (semicolon-separated short tags).
score (pre-registered in BACKTEST_LOG.md "BIAS study" before any answer):
    direction   = the day's cash close (last 1m close before 16:00) vs the previous day's cash close
    hit rate    of the long / short calls; null = each call is right with the base rate of its direction over the
                SAME scored dates (share of up days for a long call, of down days for a short call); one-sided
                p = Poisson-binomial P(hits >= observed) under that null; 'none' calls are counted, not scored
    confidence 3 calls alone, same test
    draw_level  share of days (with a level given) where MNQ traded to the level between 09:30 and 15:59
                (at or above it if it is above the 09:29 close, at or below it if below)
    reasons     hit rate per reason tag (a call counts under every tag it lists)
"""
import sys, pathlib
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from ifvg_engine import trading_date

TZ = "America/New_York"
opt = lambda k, d: type(d)(sys.argv[sys.argv.index(k) + 1]) if k in sys.argv else d
OUT = pathlib.Path(opt("--out", "data/studies/bias"))
UP, DN = "#26a69a", "#ef5350"
CLR = {"D": "#6a1b9a", "4H": "#1565c0", "1H": "#00838f", "15m": "#ef6c00"}


def one_min():
    one = pd.read_parquet("data/bars/MNQ_1m.parquet")
    one["td"] = trading_date(one.index)
    m = one.index.hour * 60 + one.index.minute
    one["tod"] = m
    return one


def cash_close(one):
    c = one[(one.tod >= 570) & (one.tod < 960)]
    g = c.groupby(c.index.date)
    return pd.DataFrame({"close": g.close.last(), "inst": g.instrument_id.last()}).set_index(pd.to_datetime(list(g.groups)).sort_values())


def eligible(one):
    cc = cash_close(one)
    days = sorted(set(one.td))
    pos = {d: k for k, d in enumerate(days)}
    out = []
    for k in range(1, len(cc)):
        d = cc.index[k]
        if d not in pos or pos[d] < 60 or cc.index[k - 1] != days[pos[d] - 1]:
            continue
        pre = one[(one.index >= pd.Timestamp(f"{d.date()} 09:29", tz=TZ)) & (one.index < pd.Timestamp(f"{d.date()} 09:30", tz=TZ))]
        if len(pre) == 0 or not ((one.index == pd.Timestamp(f"{d.date()} 09:30", tz=TZ)).any()):
            continue
        if not (cc.inst.iloc[k - 1] == pre.instrument_id.iloc[0] == cc.inst.iloc[k]):
            continue
        out.append(d)
    return out


def bars(x, rule=None, key=None):
    agg = {"open": "first", "high": "max", "low": "min", "close": "last"}
    if key is not None:
        g = x.groupby(key)
        b = g.agg(agg)
        b["t0"] = g.apply(lambda y: y.index[0])
        return b.set_index("t0").sort_index()
    return x.resample(rule, label="left", closed="left").agg(agg).dropna(subset=["open"])


def fvgs(b, last_px_path):
    """Unfilled 3-bar gaps of bars b (not traded through by any later bar of b)."""
    H, L = b.high.to_numpy(), b.low.to_numpy()
    out = []
    for i in range(2, len(b)):
        if L[i] > H[i - 2]:
            bot, top = H[i - 2], L[i]
            if not (L[i + 1:] <= bot).any():
                out.append((i - 1, bot, top, True))
        if H[i] < L[i - 2]:
            bot, top = H[i], L[i - 2]
            if not (H[i + 1:] >= top).any():
                out.append((i - 1, bot, top, False))
    return out


def panel(ax, b, name, levels, xlabels):
    n = len(b)
    for i, (o, h, l, c) in enumerate(zip(b.open, b.high, b.low, b.close)):
        col = UP if c >= o else DN
        ax.plot([i, i], [l, h], color=col, lw=0.8)
        ax.add_patch(Rectangle((i - 0.35, min(o, c)), 0.7, max(abs(c - o), 1e-6), color=col, lw=0, alpha=0.6 if i == n - 1 else 1))
    lo, hi = b.low.min(), b.high.max()
    for y, *_ in levels:
        lo, hi = min(lo, y), max(hi, y)
    gap = 0.03 * (hi - lo)                              # minimum spacing between text labels
    placed = []
    for k, bot, top, bull in fvgs(b, None):
        ax.add_patch(Rectangle((k - 0.5, bot), n - k, top - bot, color=CLR[name], alpha=0.16, lw=0))
        y = (bot + top) / 2
        if all(abs(y - q) >= gap for q in placed):      # thin the labels, not the gaps
            ax.text(n - 0.3, y, f"{name} FVG", fontsize=6, color=CLR[name], va="center")
            placed.append(y)
    used = []
    for y, lab, col, ls in sorted(levels, key=lambda z: -z[0]):
        ax.axhline(y, color=col, ls=ls, lw=0.9)
        yy = y
        while any(abs(yy - q) < gap for q in used):
            yy -= gap
        used.append(yy)
        ax.annotate(f" {lab} {y:,.2f}", (0, y), xytext=(0, yy), fontsize=7, color=col, va="center",
                    arrowprops=dict(arrowstyle="-", color=col, lw=0.4) if yy != y else None)
    pad = 0.04 * (hi - lo)
    ax.set_ylim(lo - pad, hi + pad)
    ax.set_xlim(-1, n + 6)
    ticks = list(range(0, n, max(1, n // 8)))
    ax.set_xticks(ticks, [xlabels[i] for i in ticks] if xlabels is not None else [""] * len(ticks), fontsize=7)
    ax.set_title(f"{name}" + ("  (last bar = forming, cut at 09:30)" if name != "15m" else "  (to 09:29)"), fontsize=9, loc="left")
    ax.grid(alpha=0.2)


def render(one, d, path, ident):
    cut = pd.Timestamp(f"{d.date()} 09:30", tz=TZ)
    x = one[one.index < cut]
    days = sorted(set(x.td))
    today = days[-1]
    prev = days[-2]
    pday = x[x.td == prev]
    pdh, pdl = pday.high.max(), pday.low.min()
    settle = pday[pday.tod < 960].close.iloc[-1]
    on = x[x.td == today]
    onh, onl = on.high.max(), on.low.min()
    last = x.close.iloc[-1]
    levels = [(pdh, "PDH", "#37474f", "--"), (pdl, "PDL", "#37474f", "--"), (settle, "prior settlement", "#8d6e63", ":"),
              (onh, "ON high", "#7e57c2", "-."), (onl, "ON low", "#7e57c2", "-."), (last, "09:29 close", "black", "-")]
    dD = bars(x[x.td.isin(days[-61:])], key=x.td[x.td.isin(days[-61:])])
    x4 = x[x.td.isin(days[-10:])]
    naive = x4.index.tz_localize(None)
    base = x4.td - pd.Timedelta(hours=6)
    k4 = x4.td.astype("int64") // 10 ** 9 * 10 + ((naive - base.to_numpy()) // pd.Timedelta(hours=4)).astype(int)
    d4 = bars(x4, key=k4.to_numpy())
    d1 = bars(x[x.td.isin(days[-5:])], "1h")
    d15 = bars(x[x.td.isin(days[-2:])], "15min")
    fig, axs = plt.subplots(2, 2, figsize=(18, 11))
    panel(axs[0, 0], dD, "D", levels, None)
    panel(axs[0, 1], d4, "4H", levels, [t.strftime("%a %H:%M") for t in d4.index])
    panel(axs[1, 0], d1, "1H", levels, [t.strftime("%a %H:%M") for t in d1.index])
    panel(axs[1, 1], d15, "15m", levels, [t.strftime("%H:%M") for t in d15.index])
    fig.suptitle(f"{ident} · MNQ · cut at 09:30 New York · no date shown · shaded boxes = unfilled FVGs of that panel's "
                 f"timeframe", fontsize=12)
    fig.tight_layout()
    fig.savefig(path, dpi=85)
    plt.close(fig)


def make():
    rng = np.random.default_rng(opt("--seed", 2409))
    one = one_min()
    el = pd.DatetimeIndex(eligible(one))
    picks = []
    for y in range(2019, 2027):
        pool = el[el.year == y]
        picks += list(pool[np.sort(rng.choice(len(pool), size=5, replace=False))])
    order = rng.permutation(len(picks))
    ids = rng.choice(np.arange(100000, 1000000), size=len(picks), replace=False)
    OUT.mkdir(parents=True, exist_ok=True)
    key = []
    for pos, k in enumerate(order):
        d = picks[k]
        block = 1 if pos < 20 else 2
        ident = str(ids[pos])
        (OUT / f"block{block}").mkdir(exist_ok=True)
        render(one, d, OUT / f"block{block}" / f"{ident}.png", ident)
        key.append(dict(id=ident, block=block, date=d.date()))
    k = pd.DataFrame(key)
    k.to_csv(OUT / "key.csv", index=False)
    kb = k[k.block == 1].sort_values("id")          # block 2 rows are appended when block 2 is released
    pd.DataFrame(dict(id=kb.id, bias="", confidence="", draw_level="", reasons="")).to_csv(OUT / "answers.csv", index=False)
    print(f"{len(k)} charts: block 1 = {int((k.block == 1).sum())}, block 2 = {int((k.block == 2).sum())} in {OUT}")


def pbinom_ge(probs, k):
    dist = np.zeros(len(probs) + 1); dist[0] = 1.0
    for p in probs:
        dist[1:] = dist[1:] * (1 - p) + dist[:-1] * p
        dist[0] *= (1 - p)
    return dist[k:].sum()


def score():
    one = one_min()
    cc = cash_close(one)
    key = pd.read_csv(OUT / "key.csv", dtype={"id": str})
    blk = opt("--block", "all")
    blocks = [1, 2] if blk == "all" else [int(blk)]
    ans = pd.read_csv(OUT / "answers.csv", dtype=str).fillna("")
    x = key[key.block.isin(blocks)].merge(ans, on="id")
    x = x[x.bias.str.strip() != ""]
    rows = []
    for r in x.itertuples():
        d = pd.Timestamp(r.date)
        k = cc.index.get_loc(d)
        move = cc.close.iloc[k] - cc.close.iloc[k - 1]
        day = one[(one.index >= pd.Timestamp(f"{r.date} 09:30", tz=TZ)) & (one.index < pd.Timestamp(f"{r.date} 16:00", tz=TZ))]
        px = one[one.index < pd.Timestamp(f"{r.date} 09:30", tz=TZ)].close.iloc[-1]
        reach = None
        if r.draw_level.strip():
            lv = float(r.draw_level)
            reach = bool(day.high.max() >= lv) if lv >= px else bool(day.low.min() <= lv)
        b = r.bias.strip().lower()
        rows.append(dict(id=r.id, bias=b, conf=r.confidence.strip(), up=move > 0, move=move,
                         hit=None if b not in ("long", "short") or move == 0 else bool((move > 0) == (b == "long")),
                         reach=reach, reasons=[t.strip().lower() for t in (getattr(r, "tags", "") or r.reasons).split(";") if t.strip()]))
    s = pd.DataFrame(rows)
    up = s.up.mean()
    print(f"days scored {len(s)}; up days {100 * up:.0f} %; calls long {int((s.bias == 'long').sum())}, short "
          f"{int((s.bias == 'short').sum())}, none {int((s.bias == 'none').sum())}")

    def test(sub, label):
        c = sub[sub.hit.notna()]
        if c.empty:
            print(f"  {label}: no calls"); return
        probs = np.where(c.bias == "long", up, 1 - up)
        k = int(c.hit.astype(bool).sum())
        print(f"  {label}: {k} of {len(c)} right ({100 * k / len(c):.0f} %), expected under the base rate "
              f"{probs.sum():.1f}, one-sided p = {pbinom_ge(probs, k):.3f}")
    test(s, "all calls")
    test(s[s.conf == "3"], "confidence 3")
    r_ = s[s.reach.notna()]
    if len(r_):
        print(f"  draw level reached 09:30-15:59: {int(r_.reach.sum())} of {len(r_)} ({100 * r_.reach.mean():.0f} %)")
    tags = s.explode("reasons").dropna(subset=["reasons"])
    for t, g in tags[tags.hit.notna()].groupby("reasons"):
        print(f"    tag {t:<24} {int(g.hit.astype(bool).sum())} of {len(g)} right")
    if "--implied" in sys.argv:                          # 'none' rows whose reasons state a direction
        imp = dict(z.split(":") for z in opt("--implied", "").split(","))
        v = s[s.id.isin(imp)].copy()
        v["bias"] = v.id.map(imp)
        v["hit"] = [None if m == 0 else bool((m > 0) == (b_ == "long")) for m, b_ in zip(v.move, v.bias)]
        print("  directional 'none' rows, scored separately: " + ", ".join(f"{r.id} {r.bias} -> {'right' if r.hit else 'wrong'}" for r in v.itertuples()))
        test(v, "those rows alone")
        test(pd.concat([s[s.hit.notna()], v]), "calls + those rows")
    s.drop(columns=["reasons"]).to_csv(OUT / f"scored_block{blk}.csv", index=False)


def context(one, d):
    """Everything drawn on a chart (as of 09:29): levels and the panel bars."""
    cut = pd.Timestamp(f"{d} 09:30", tz=TZ)
    x = one[one.index < cut]
    x = x[x.index >= cut - pd.Timedelta(days=120)]
    days = sorted(set(x.td))
    pday = x[x.td == days[-2]]
    on = x[x.td == days[-1]]
    lv = dict(PDH=pday.high.max(), PDL=pday.low.min(), settle=pday[pday.tod < 960].close.iloc[-1],
              ONH=on.high.max(), ONL=on.low.min(), last=x.close.iloc[-1])
    xd = x[x.td.isin(days[-61:])]
    dD = bars(xd, key=xd.td)
    x4 = x[x.td.isin(days[-10:])]
    naive = x4.index.tz_localize(None)
    base = x4.td - pd.Timedelta(hours=6)
    k4 = x4.td.astype("int64") // 10 ** 9 * 10 + ((naive - base.to_numpy()) // pd.Timedelta(hours=4)).astype(int)
    return lv, dict(D=dD, **{"4H": bars(x4, key=k4.to_numpy())}, **{"1H": bars(x[x.td.isin(days[-5:])], "1h")},
                    **{"15m": bars(x[x.td.isin(days[-2:])], "15min")})


def resolve_ref(lv, pan, ref):
    """draw_ref -> (price or None, how it was read, alternatives)."""
    import re
    r = ref.strip()
    low = r.lower()
    if low.startswith("none") or not r:
        return None, "no level", ""
    for k, name in (("on high", "ONH"), ("on low", "ONL"), ("pdh", "PDH"), ("pdl", "PDL")):
        if low.startswith(k):
            return lv[name], name, ""
    m = re.search(r"(\d{1,2}:\d{2})", r)
    side = "high" if "high" in low else "low"
    days = {"monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3, "friday": 4, "saturday": 5, "sunday": 6}
    wd = next((v for k, v in days.items() if k in low), None)
    hh, mm = map(int, m.group(1).split(":"))
    pname = "1H" if ("1h" in low or wd is not None) else "15m"
    b = pan[pname]
    hit = b[(b.index.hour == hh) & (b.index.minute == mm) & ((b.index.dayofweek == wd) if wd is not None else True)]
    val = lambda t: b.loc[t, side]
    alts = ", ".join(f"{t:%a %H:%M} {val(t):,.2f}" for t in hit.index[:-1])
    t = hit.index[-1]
    return val(t), f"{pname} bar {t:%a %H:%M} {side}", (f"other {pname} bars at that time: {alts}" if alts else "")


def resolve():
    one = one_min()
    key = pd.read_csv(OUT / "key.csv", dtype={"id": str})
    a = pd.read_csv(OUT / "answers.csv", dtype=str).fillna("")
    for k, r in a.iterrows():
        if not r.get("draw_ref", "").strip():
            continue
        d = key.loc[key.id == r.id, "date"].iloc[0]
        lv, pan = context(one, d)
        px, how, alt = resolve_ref(lv, pan, r.draw_ref)
        a.at[k, "draw_level"] = "" if px is None else f"{px:.2f}"
        print(f"{r.id}  '{r.draw_ref}' -> " + ("none" if px is None else f"{px:,.2f} ({how}; 09:29 close {lv['last']:,.2f})") + (f"  [{alt}]" if alt else ""))
    a.to_csv(OUT / "answers.csv", index=False)


def _atr(b, n=14):
    pc = b.close.shift(1)
    tr = pd.concat([b.high - b.low, (b.high - pc).abs(), (b.low - pc).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False).mean().iloc[-1]


def _slope(b, n=20):
    """Least-squares slope of the last n closes, in that timeframe's ATR per bar."""
    y = b.close.to_numpy()[-n:]
    return np.polyfit(np.arange(len(y)), y, 1)[0] / _atr(b)


def features():
    """Computable versions of the trader's tags, per chart, and three simple rules fixed in this docstring:
        R1 trend      long if at least 2 of the D / 4H / 1H 20-bar slopes are > +0.05 ATR per bar, short if at least
                      2 are < -0.05, else none
        R2 LRL first  long on a 15m run of >= 4 lower highs into price (liquidity resting above), short on a run of
                      >= 4 higher lows (below); if both or neither, R1
        R3 ON side    long if the 09:29 close is in the upper half of the overnight range, short if in the lower half
        R4 daily FVG above (FOUND AFTER READING THE BLOCK-1 CALLS, so in-sample by construction): short if any
                      unfilled daily FVG lies above the 09:29 close, else long; block 2 is its first real test
    Features: slopes; for each timeframe whether the 09:29 close is inside an unfilled FVG (+1 bull, -1 bear, 0) and
    the distance to the nearest unfilled FVG above / below in daily ATR; 15m equal highs / lows (two unswept 15m
    3-bar fractal highs / lows within 0.1 x 15m ATR, above / below price); the longest 15m run of lower highs /
    higher lows in the last 16 bars; the overnight-range position."""
    one = one_min()
    key = pd.read_csv(OUT / "key.csv", dtype={"id": str})
    a = pd.read_csv(OUT / "answers.csv", dtype=str).fillna("")
    blk = int(opt("--block", 1))
    x = key[key.block == blk].merge(a, on="id")
    cc = cash_close(one)
    rows = []
    for r in x.itertuples():
        lv, pan = context(one, r.date)
        px = lv["last"]
        f = dict(id=r.id, call=r.bias.strip().lower(), conf=r.confidence)
        for tf in ("D", "4H", "1H"):
            b = pan[tf] if tf != "D" else pan[tf].iloc[:-1]            # daily: completed bars only
            f[f"slope_{tf}"] = round(_slope(b), 3)
        aD = _atr(pan["D"].iloc[:-1])
        for tf in ("D", "4H", "1H", "15m"):
            gs = fvgs(pan[tf], None)
            inside = [(1 if bull else -1) for _, bot, top, bull in gs if bot <= px <= top]
            f[f"in_{tf}"] = inside[-1] if inside else 0
            above = [bot - px for _, bot, top, _b in gs if bot > px]
            below = [px - top for _, bot, top, _b in gs if top < px]
            f[f"up_{tf}"] = round(min(above) / aD, 2) if above else np.nan
            f[f"dn_{tf}"] = round(min(below) / aD, 2) if below else np.nan
        b15 = pan["15m"]
        a15 = _atr(b15)
        H, L = b15.high.to_numpy(), b15.low.to_numpy()
        fh = [k for k in range(1, len(b15) - 1) if H[k] > H[k - 1] and H[k] >= H[k + 1] and not (H[k + 1:] > H[k]).any()]
        fl = [k for k in range(1, len(b15) - 1) if L[k] < L[k - 1] and L[k] <= L[k + 1] and not (L[k + 1:] < L[k]).any()]
        f["eq_highs"] = int(any(abs(H[i] - H[j]) <= 0.1 * a15 for i in fh for j in fh if i < j))
        f["eq_lows"] = int(any(abs(L[i] - L[j]) <= 0.1 * a15 for i in fl for j in fl if i < j))
        run_lh = run_hl = best_lh = best_hl = 0
        for k in range(len(b15) - 16, len(b15)):
            run_lh = run_lh + 1 if H[k] < H[k - 1] else 0
            run_hl = run_hl + 1 if L[k] > L[k - 1] else 0
            best_lh, best_hl = max(best_lh, run_lh), max(best_hl, run_hl)
        f["run_lower_highs"], f["run_higher_lows"] = best_lh, best_hl
        f["on_pos"] = round((px - lv["ONL"]) / (lv["ONH"] - lv["ONL"]), 2) if lv["ONH"] > lv["ONL"] else np.nan
        votes = sum(np.sign(f[f"slope_{tf}"]) * (abs(f[f"slope_{tf}"]) > 0.05) for tf in ("D", "4H", "1H"))
        f["R1"] = "long" if votes >= 2 else "short" if votes <= -2 else "none"
        lrl_up, lrl_dn = best_lh >= 4, best_hl >= 4
        f["R2"] = "long" if lrl_up and not lrl_dn else "short" if lrl_dn and not lrl_up else f["R1"]
        f["R3"] = "long" if f["on_pos"] >= 0.5 else "short"
        f["R4"] = "short" if not np.isnan(f["up_D"]) else "long"
        k = cc.index.get_loc(pd.Timestamp(r.date))
        f["actual"] = "long" if cc.close.iloc[k] > cc.close.iloc[k - 1] else "short"
        rows.append(f)
    t = pd.DataFrame(rows)
    pd.set_option("display.width", 250); pd.set_option("display.max_columns", 40)
    print(t.to_string(index=False))
    calls = t[t.call.isin(["long", "short"])]
    for rule in ("R1", "R2", "R3", "R4"):
        same = (calls[rule] == calls.call).sum()
        print(f"{rule}: matches {same} of {len(calls)} directional calls; on the 6 'none' rows it says "
              f"{', '.join(t[~t.call.isin(['long', 'short'])][rule])}; right on the day {int((t[rule] == t.actual).sum())} of "
              f"{int((t[rule] != 'none').sum())} of its own calls")
    t.to_csv(OUT / f"features_block{blk}.csv", index=False)


def release2():
    k = pd.read_csv(OUT / "key.csv", dtype={"id": str})
    a = pd.read_csv(OUT / "answers.csv", dtype=str).fillna("")
    kb = k[(k.block == 2) & ~k.id.isin(a.id)].sort_values("id")
    pd.concat([a, pd.DataFrame(dict(id=kb.id, bias="", confidence="", draw_level="", reasons=""))]).to_csv(OUT / "answers.csv", index=False)
    print(f"block 2: {len(kb)} rows appended")


if __name__ == "__main__":
    {"make": make, "score": score, "release2": release2, "resolve": resolve, "features": features}[sys.argv[1]]()
