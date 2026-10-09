#!/usr/bin/env python3
"""Collect the YT1 result files into one table.

    python3 tools/yt1/report.py is      in-sample table  -> data/studies/yt1/is_table.csv / .md
    python3 tools/yt1/report.py full    full-span table with verdicts -> data/studies/yt1/full_table.csv / .md
"""
import json, sys, pathlib, importlib
import pandas as pd
sys.path.insert(0, str(pathlib.Path(__file__).parent))
import core

ORDER = ["A01", "A02", "A03", "A05", "A09", "A10", "A14", "B01", "B03", "B04", "B05", "B06", "B07", "B08", "B09", "B14",
         "C01", "C02", "C03", "C04", "C05", "C06", "C07", "C08", "C09", "C10", "C12", "C13", "C15", "C17", "C19a", "C19b",
         "C19c", "C19d", "C19e", "D03", "D05", "D06", "E01", "E02", "E04", "E05", "E06", "E08", "E09", "E10a", "E10b",
         "E11", "E12", "E13", "E15", "E19", "E20"]
assert len(ORDER) == core.N_TESTS


def load(phase, ident, variant):
    f = core.OUT / phase / f"{ident}_{variant}.json"
    return json.loads(f.read_text()) if f.exists() else None


def table(phase):
    rows = []
    for ident in ORDER:
        mod = importlib.import_module(f"s_{ident}")
        b, n1, n2 = (load(phase, ident, v) for v in ("base", "nb1", "nb2"))
        if b is None:
            rows.append(dict(id=ident, name=mod.NAME, n=None)); continue
        r = dict(id=ident, name=mod.NAME, n=b.get("n", 0))
        if b.get("n"):
            r.update(net=b["net"], R=b["R"], win=b["win"], pf=b["pf"], dd=b["dd"], dd_R=b["dd_R"], p=b["p"],
                     years_pos=b["years_pos"], years=b["years_traded"], R_h1=b["R_h1"], R_h2=b["R_h2"],
                     n_h1=b["n_h1"], n_h2=b["n_h2"], R_long=b["R_long"], R_short=b["R_short"],
                     R_nb1=(n1 or {}).get("R"), n_nb1=(n1 or {}).get("n"), R_nb2=(n2 or {}).get("R"), n_nb2=(n2 or {}).get("n"),
                     by_year_net=" / ".join(f"{v['net']:+.0f}" if v["n"] else "." for v in b["by_year"].values()),
                     by_year_R=" / ".join(f"{v['R']:+.2f}" if v["n"] else "." for v in b["by_year"].values()))
        if phase == "full":
            v = core.verdict(b, [n1 or {}, n2 or {}])
            r["verdict"] = v["verdict"]
            r["failed_on"] = ", ".join(k for k, ok in v["checks"].items() if not ok)
        rows.append(r)
    return pd.DataFrame(rows)


def md(df, phase):
    out = []
    if phase == "is":
        out.append("| ID | Rule | n | Net $ | R / trade | Win % | PF | p | R nb1 / nb2 | Net by year 2019 / 20 / 21 / 22 |")
        out.append("|---|---|---|---|---|---|---|---|---|---|")
        for r in df.itertuples():
            if not r.n:
                out.append(f"| {r.id} | {r.name} | 0 | | | | | | | |"); continue
            yrs = " / ".join(r.by_year_net.split(" / ")[:4])
            out.append(f"| {r.id} | {r.name} | {r.n} | {r.net:+,.0f} | {r.R:+.3f} | {r.win:.1f} | {r.pf or 0:.2f} | {r.p:.4f} | "
                       f"{r.R_nb1 if r.R_nb1 is not None else float('nan'):+.3f} / {r.R_nb2 if r.R_nb2 is not None else float('nan'):+.3f} | {yrs} |")
    else:
        out.append("| ID | Rule | n | Net $ | R / trade | Win % | PF | Max DD $ | p | Years + | R 2019-22 / 2023-26 | R nb1 / nb2 | Verdict | Fails on |")
        out.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
        for r in df.itertuples():
            if not r.n:
                out.append(f"| {r.id} | {r.name} | 0 | | | | | | | | | | not enough data | |"); continue
            f = lambda x: "n/a" if x is None or x != x else f"{x:+.3f}"
            out.append(f"| {r.id} | {r.name} | {r.n} | {r.net:+,.0f} | {r.R:+.3f} | {r.win:.1f} | {r.pf or 0:.2f} | {r.dd:,.0f} | {r.p:.4f} | "
                       f"{r.years_pos}/{r.years} | {f(r.R_h1)} / {f(r.R_h2)} | {f(r.R_nb1)} / {f(r.R_nb2)} | {r.verdict} | {r.failed_on} |")
    return "\n".join(out)


if __name__ == "__main__":
    phase = sys.argv[1]
    if len(sys.argv) > 2:
        core.OUT = pathlib.Path(sys.argv[2])
    df = table(phase)
    df.to_csv(core.OUT / f"{phase}_table.csv", index=False)
    (core.OUT / f"{phase}_table.md").write_text(md(df, phase) + "\n")
    pd.set_option("display.width", 250)
    cols = ["id", "n", "net", "R", "win", "pf", "p", "R_nb1", "R_nb2"] + (["years_pos", "R_h1", "R_h2", "verdict"] if phase == "full" else ["by_year_net"])
    print(df[[c for c in cols if c in df.columns]].to_string(index=False))
