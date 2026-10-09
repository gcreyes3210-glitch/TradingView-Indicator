#!/usr/bin/env python3
"""Forward bias log: one row per morning in data/forward/bias_log.csv, written before 09:30 New York, scored against
the day's close-to-close direction. Printed with the weekly ORB check (tools/calibrate_orb.py) or on its own:

    python3 tools/bias_log.py [--log data/forward/bias_log.csv] [--bars data/bars/MNQ_1m.parquet]

Columns: date (YYYY-MM-DD, the New York trading day), bias (long / short / none), confidence (1-3), note (free text).
Direction: MNQ cash close (last 1-minute close before 16:00 New York) of the date against the previous trading day's
cash close; up = long right, down = short right, unchanged = neither. 'none' rows are counted, not scored; a day
whose close comes from a different contract than the previous close (Databento's volume roll) is 'roll', not scored.
Written-before-09:30 check: each row's time is the git author time of the commit that last changed that line (git
blame), so a row edited later takes the later time; a row committed after 09:30 New York on its date, or not committed
at all, is 'late' and left out of the score. A row whose day
is not in the bars yet is 'pending'.
Score: hit rate of the long / short calls against 50 % (one-sided binomial p), by confidence, next to the share of
up days over the same dates (the hit rate of saying 'long' every day).
"""
import sys, subprocess, pathlib, math
import pandas as pd

TZ = "America/New_York"
LOG = "data/forward/bias_log.csv"


def blame_times(path):
    """{line number (1 = header): author time (New York) or None when uncommitted}."""
    try:
        out = subprocess.run(["git", "blame", "--line-porcelain", "--", path], capture_output=True, text=True, check=True).stdout
    except Exception:
        return {}
    times, line, t = {}, None, None
    for s in out.splitlines():
        if s[:40].strip() and len(s.split()) >= 3 and len(s.split()[0]) == 40:
            sha, _, final = s.split()[:3]
            line = int(final)
            uncommitted = set(sha) == {"0"}
        elif s.startswith("author-time "):
            t = pd.Timestamp(int(s.split()[1]), unit="s", tz="UTC").tz_convert(TZ)
            times[line] = None if uncommitted else t
    return times


def closes(bars_path):
    """Cash close and the contract it came from, per New York date."""
    one = pd.read_parquet(bars_path, columns=["close", "instrument_id"])
    m = one.index.hour * 60 + one.index.minute
    cash = one[(m >= 9 * 60 + 30) & (m < 16 * 60)]
    c = cash.groupby(cash.index.date)[["close", "instrument_id"]].last()
    c.index = pd.to_datetime(c.index)
    return c


def binom_p(k, n):
    return sum(math.comb(n, i) for i in range(k, n + 1)) / 2 ** n if n else float("nan")


def report(log=LOG, bars="data/bars/MNQ_1m.parquet"):
    p = pathlib.Path(log)
    if not p.exists():
        print(f"\nbias log: {log} not found"); return
    d = pd.read_csv(p, dtype=str).fillna("")
    print(f"\nforward bias log ({log}): {len(d)} rows")
    if d.empty:
        return
    bt = blame_times(log)
    c = closes(bars)
    rows = []
    for k, r in d.iterrows():
        day = pd.Timestamp(r.date)
        t = bt.get(k + 2)
        late = t is None or t > pd.Timestamp(f"{r.date} 09:30", tz=TZ)
        bias = r.bias.strip().lower()
        status, move = "", None
        if late:
            status = "late" if t is not None else "uncommitted"
        elif day not in c.index or c.index.get_loc(day) == 0:
            status = "pending"
        elif c.instrument_id.iloc[c.index.get_loc(day)] != c.instrument_id.iloc[c.index.get_loc(day) - 1]:
            status = "roll"                              # the two closes are different contracts
        else:
            i = c.index.get_loc(day)
            move = c.close.iloc[i] - c.close.iloc[i - 1]
            status = "none" if bias == "none" else "scored"
        hit = None if status != "scored" or move == 0 else (move > 0) == (bias == "long")
        rows.append(dict(date=r.date, bias=bias, conf=r.confidence, committed=t, status=status, move=move, hit=hit))
    x = pd.DataFrame(rows)
    print("  " + "  ".join(f"{k} {v}" for k, v in x.status.value_counts().items()))
    s = x[(x.status == "scored") & x.hit.notna()]
    if len(s):
        k, n = int(s.hit.sum()), len(s)
        up = (x[x.move.notna()].move > 0).mean()
        print(f"  calls scored {n}: right {k} ({100 * k / n:.0f} %), one-sided binomial p vs 50 % = {binom_p(k, n):.3f}; "
              f"up days over the same dates {100 * up:.0f} %")
        for cf, g in s.groupby("conf"):
            print(f"    confidence {cf}: {int(g.hit.sum())} of {len(g)} right")
    late = x[x.status.isin(["late", "uncommitted"])]
    if len(late):
        print("  not scored (committed after 09:30 or not committed): " + ", ".join(late.date))


if __name__ == "__main__":
    opt = lambda k, dflt: sys.argv[sys.argv.index(k) + 1] if k in sys.argv else dflt
    report(opt("--log", LOG), opt("--bars", "data/bars/MNQ_1m.parquet"))
