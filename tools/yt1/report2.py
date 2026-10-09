#!/usr/bin/env python3
"""YT2 table (29 TRADING RUSH triggers).   python3 tools/yt1/report2.py is|full
Verdicts use the level registered in YT2_SPEC.md: 0.05 / (53 + 29)."""
import sys, pathlib, importlib
import pandas as pd
sys.path.insert(0, str(pathlib.Path(__file__).parent))
import core, report

IDS = [f"T{i:02d}" for i in range(1, 30)]
N_ALL = 53 + 29

if __name__ == "__main__":
    phase = sys.argv[1]
    rows = []
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
    df = pd.DataFrame(rows)
    df.to_csv(core.OUT / f"yt2_{phase}_table.csv", index=False)
    (core.OUT / f"yt2_{phase}_table.md").write_text(report.md(df, phase) + "\n")
    pd.set_option("display.width", 250)
    cols = ["id", "n", "net", "R", "win", "pf", "p", "R_nb1", "R_nb2"] + (["years_pos", "R_h1", "R_h2", "verdict"] if phase == "full" else ["by_year_net"])
    print(df[cols].to_string(index=False))
