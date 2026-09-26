#!/usr/bin/env python3
"""Slice a TradingView 'List of trades' CSV export by the fields in the entry tag.

Works for any strategy in this repo whose entry comment is  SIDE|NAME|key:value|key:value|...
(ORB, VP-80).  Usage:

    python3 tools/analyze_tags.py export.csv                 # overall, per year, per exit, per tag field
    python3 tools/analyze_tags.py export.csv --year 2023-09-22   # yearly split anchored on this date

Numeric tag fields are bucketed into terciles; text fields (side, open, ent, dow ...) are grouped as-is.
"""
import csv, collections, sys, datetime as dt

path = sys.argv[1]
anchor = "2023-09-22"
if "--year" in sys.argv:
    anchor = sys.argv[sys.argv.index("--year") + 1]

rows = list(csv.DictReader(open(path, encoding="utf-8-sig")))
tr = {}
for r in rows:
    n = int(r["Trade number"]); t = tr.setdefault(n, {})
    if r["Type"].startswith("Entry"):
        parts = r["Signal"].split("|")
        d = {}
        for x in parts[2:]:
            if ":" in x:
                k, v = x.split(":", 1); d[k] = v
        qty = max(int(float(r["Size (qty)"])), 1)
        t.update(side=parts[0], tags=d, t=r["Date and time"], pnl=float(r["Net PnL USD"]) / qty,
                 mfe=float(r["Favorable excursion USD"]) / qty, mae=float(r["Adverse excursion USD"]) / qty,
                 dur=int(r["Duration (bars)"]))
    else:
        t["exit"] = r["Signal"]
T = [t for t in tr.values() if t.get("exit") and t["exit"] != "Open" and "pnl" in t]
T.sort(key=lambda t: t["t"])

def summ(nm, T):
    if not T:
        print(f"{nm:30s} none"); return
    pn = [t["pnl"] for t in T]; w = [p for p in pn if p > 0]; l = [p for p in pn if p <= 0]
    cum = peak = dd = st = mx = 0
    for p in pn:
        cum += p; peak = max(peak, cum); dd = min(dd, cum - peak); st = st + 1 if p <= 0 else 0; mx = max(mx, st)
    pf = sum(w) / -sum(l) if l and sum(l) < 0 else 9.99
    print(f"{nm:30s} n={len(pn):4d} win {100*len(w)/len(pn):3.0f}% net {sum(pn):+7.0f} PF {pf:4.2f} DD {dd:6.0f} avgW {sum(w)/max(len(w),1):5.0f} avgL {sum(l)/max(len(l),1):5.0f} streak {mx}")

print("trades", len(T), "first", T[0]["t"] if T else "-", "last", T[-1]["t"] if T else "-")
summ("ALL", T)
a = dt.date.fromisoformat(anchor)
for k in range(3):
    y0 = a.replace(year=a.year + k).isoformat(); y1 = a.replace(year=a.year + k + 1).isoformat()
    summ(f"  yr{k+1} {y0[:4]}/{y1[2:4]}", [t for t in T if y0 <= t["t"][:10] < y1])
print("exits", dict(collections.Counter(t["exit"] for t in T)))

def by(nm, f):
    d = collections.defaultdict(list)
    for t in T: d[f(t)].append(t)
    print("== " + nm)
    for k, v in sorted(d.items(), key=lambda x: str(x[0])): summ("  " + str(k), v)

by("side", lambda t: t["side"])
keys = sorted({k for t in T for k in t["tags"]})
for k in keys:
    vals = [t["tags"][k] for t in T if k in t["tags"]]
    try:
        nums = sorted(float(v) for v in vals if v not in ("na", "NaN"))
    except ValueError:
        nums = []
    if nums and len(set(nums)) > 6:
        q1 = nums[len(nums) // 3]; q2 = nums[2 * len(nums) // 3]
        def bucket(t, k=k, q1=q1, q2=q2):
            v = t["tags"].get(k, "na")
            try: x = float(v)
            except ValueError: return "na"
            return f"1 low  (<{q1:g})" if x < q1 else f"2 mid  ({q1:g}-{q2:g})" if x < q2 else f"3 high (>={q2:g})"
        by(k + " (terciles)", bucket)
    else:
        by(k, lambda t, k=k: t["tags"].get(k, "na"))
