#!/usr/bin/env python3
"""YT4 table (TTrades rules G1-G7).   python3 tools/yt1/report4.py is|full
Verdicts use the level registered in YT4_SPEC.md Part 2: 0.05 / 90."""
import sys, pathlib, importlib, json
import pandas as pd
sys.path.insert(0, str(pathlib.Path(__file__).parent))
import core, report

IDS = [f"G{i}" for i in range(1, 8)]
N_ALL = 90

if __name__ == "__main__":
    phase = sys.argv[1]
    rows, extra = [], []
    for ident in IDS:
        mod = importlib.import_module(f"s_{ident}")
        b, n1, n2 = (report.load(phase, ident, v) for v in ("base", "nb1", "nb2"))
        r = dict(id=ident, name=mod.NAME, n=b["n"], net=b["net"], R=b["R"], win=b["win"], pf=b["pf"], dd=b["dd"], dd_R=b["dd_R"], p=b["p"],
                 years_pos=b["years_pos"], years=b["years_traded"], R_h1=b["R_h1"], R_h2=b["R_h2"], n_h1=b["n_h1"], n_h2=b["n_h2"],
                 R_long=b["R_long"], R_short=b["R_short"], R_nb1=n1["R"], n_nb1=n1["n"], R_nb2=n2["R"], n_nb2=n2["n"],
                 by_year_net=" / ".join(f"{v['net']:+.0f}" if v["n"] else "." for v in b["by_year"].values()))
        if phase == "full":
            v = core.verdict(b, [n1, n2], n_tests=N_ALL)
            r["verdict"], r["failed_on"] = v["verdict"], ", ".join(k for k, ok in v["checks"].items() if not ok)
        rows.append(r)
        for var in list(mod.VARIANTS)[1:]:
            s = report.load(phase, ident, var)
            extra.append(dict(id=ident, variant=var, n=s["n"], net=s["net"], R=s["R"], win=s["win"], p=s["p"], years_pos=s["years_pos"],
                              R_h1=s["R_h1"], R_h2=s["R_h2"], by_year_net=" / ".join(f"{v['net']:+.0f}" if v["n"] else "." for v in s["by_year"].values())))
    df = pd.DataFrame(rows); ex = pd.DataFrame(extra)
    df.to_csv(core.OUT / f"yt4_{phase}_table.csv", index=False)
    ex.to_csv(core.OUT / f"yt4_{phase}_variants.csv", index=False)
    (core.OUT / f"yt4_{phase}_table.md").write_text(report.md(df, phase) + "\n")
    pd.set_option("display.width", 250); pd.set_option("display.max_colwidth", 90)
    cols = ["id", "n", "net", "R", "win", "pf", "dd", "p", "R_nb1", "R_nb2"] + (["years_pos", "R_h1", "R_h2", "verdict", "failed_on"] if phase == "full" else [])
    print(df[cols].to_string(index=False)); print(df[["id", "name", "by_year_net"]].to_string(index=False)); print(ex.to_string(index=False))
