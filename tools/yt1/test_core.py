#!/usr/bin/env python3
"""Unit tests of core.simulate on hand-made bars.   python3 tools/yt1/test_core.py"""
import sys, pathlib
import numpy as np, pandas as pd
sys.path.insert(0, str(pathlib.Path(__file__).parent))
import core
from core import simulate, TICK, PV, COMM


class Fake:
    def __init__(self, rows):
        r = np.array(rows, float)
        self.O, self.H, self.L, self.C = r[:, 0], r[:, 1], r[:, 2], r[:, 3]
        self.n = len(r)
        self.ts = pd.date_range("2024-01-02 09:30", periods=self.n, freq="1min", tz=core.TZ)


def pnl(side, entry_raw, exit_raw):
    return side * ((exit_raw - side * TICK) - (entry_raw + side * TICK)) * PV - 2 * COMM


def near(a, b):
    assert abs(a - b) < 1e-9, (a, b)


def run():
    # 1 close entry, stop on a later bar; nothing happens on the entry bar even though its low is under the stop
    c = Fake([(100, 101, 95, 100), (100, 102, 99.5, 101), (101, 101, 97, 98), (98, 99, 97, 98)])
    t = simulate(c, 0, 1, "close", stop=98, exit_i=3)
    assert t["reason"] == "SL" and t["k"] == 2; near(t["pnl"], pnl(1, 100, 98)); near(t["R"], t["pnl"] / ((100.25 - 98) * PV))
    # 2 stop and target on the same later bar -> stop
    c = Fake([(100, 100, 100, 100), (100, 106, 97, 103), (103, 104, 102, 103)])
    t = simulate(c, 0, 1, "close", stop=98, target=105, exit_i=2)
    assert t["reason"] == "SL"; near(t["pnl"], pnl(1, 100, 98))
    # 3 target, then time exit; a bar opening beyond the target fills at the open
    c = Fake([(100, 100, 100, 100), (100, 104, 99, 104), (107, 108, 106, 107)])
    t = simulate(c, 0, 1, "close", stop=98, target=105, exit_i=2)
    assert t["reason"] == "TP"; near(t["pnl"], pnl(1, 100, 107))
    t = simulate(c, 0, 1, "close", stop=98, target=110, exit_i=2)
    assert t["reason"] == "time"; near(t["pnl"], pnl(1, 100, 107))
    # 4 gap through the stop fills at the open
    c = Fake([(100, 100, 100, 100), (95, 96, 94, 95), (95, 95, 95, 95)])
    t = simulate(c, 0, 1, "close", stop=98, exit_i=2)
    assert t["reason"] == "SL"; near(t["pnl"], pnl(1, 100, 95))
    # 5 short side mirrors
    c = Fake([(100, 100, 100, 100), (100, 101, 96, 97), (97, 103, 97, 102)])
    t = simulate(c, 0, -1, "close", stop=102, target=95.5, exit_i=2)
    assert t["reason"] == "SL" and t["k"] == 2; near(t["pnl"], pnl(-1, 100, 102))
    t = simulate(c, 0, -1, "close", stop=102, target=96, exit_i=2)
    assert t["reason"] == "TP" and t["k"] == 1; near(t["pnl"], pnl(-1, 100, 96))
    # 6 'open' entry: the whole next bar is live, path decides (open nearer the low -> low first -> stop)
    c = Fake([(100, 100, 100, 100), (100, 110, 99, 105), (105, 105, 105, 105)])
    t = simulate(c, 0, 1, "open", stop=99.5, target=108, exit_i=2)
    assert t["reason"] == "SL" and t["k"] == 1
    c = Fake([(100, 101, 90, 95), (95, 95, 95, 95)])                      # open nearer the high: high first
    t = simulate(Fake([(100, 100, 100, 100)] + [(100, 101, 90, 95), (95, 95, 95, 95)]), 0, 1, "open", stop=92, target=100.75, exit_i=2)
    assert t["reason"] == "TP"
    # 7 buy stop: fills at the stop price; later path of the fill bar can stop it out
    c = Fake([(100, 100, 100, 100), (100, 103, 99, 99.5), (99.5, 99.5, 99.5, 99.5)])
    t = simulate(c, 0, 1, "stop", price=102, expire=1, stop=99.25, exit_i=2)   # path O,L(99),H(103),C: fill 102 then close 99.5 -> not stopped
    assert t["j"] == 1 and t["reason"] == "time"; near(t["pnl"], pnl(1, 102, 99.5))
    c = Fake([(100, 100, 100, 100), (100, 103, 99, 99.0), (99, 99, 99, 99)])
    t = simulate(c, 0, 1, "stop", price=102, expire=1, stop=99.25, exit_i=2)   # after the high the path falls to 99.0 -> stopped
    assert t["reason"] == "SL" and t["k"] == 1; near(t["pnl"], pnl(1, 102, 99.25))
    # 8 buy stop gapped over: fills at the open
    c = Fake([(100, 100, 100, 100), (104, 105, 103.5, 104), (104, 104, 104, 104)])
    t = simulate(c, 0, 1, "stop", price=102, expire=1, stop=99, exit_i=2)
    near(t["entry"], 104 + TICK)
    # 9 buy limit: fills at the limit on a touch; stop below on the same down leg
    c = Fake([(100, 100, 100, 100), (100, 100.5, 97, 98), (98, 98, 98, 98)])
    t = simulate(c, 0, 1, "limit", price=99, expire=1, stop=97.5, exit_i=2)
    assert t["reason"] == "SL" and t["k"] == 1; near(t["pnl"], pnl(1, 99, 97.5))
    t = simulate(c, 0, 1, "limit", price=99, expire=1, stop=96, target=100.25, exit_i=2)   # high came before the fill: no target credit
    assert t["reason"] == "time"; near(t["pnl"], pnl(1, 99, 98))
    # 10 limit never touched / expired
    assert simulate(c, 0, 1, "limit", price=96, expire=1, stop=95, exit_i=2) is None
    c = Fake([(100, 100, 100, 100), (100, 101, 99.5, 100), (100, 100, 98, 99), (99, 99, 99, 99)])
    assert simulate(c, 0, 1, "limit", price=99, expire=1, stop=95, exit_i=3) is None
    assert simulate(c, 0, 1, "limit", price=99, expire=2, stop=95, exit_i=3)["j"] == 2
    # 11 cancel level reached before the limit
    assert simulate(c, 0, 1, "limit", price=99, expire=2, stop=95, exit_i=3, cancel_hi=101) is None
    assert simulate(c, 0, 1, "limit", price=99, expire=2, stop=95, exit_i=3, cancel_hi=101.25) is not None
    # 12 scale-out: half at 102, rest at the time exit; stop to break-even after the first part
    c = Fake([(100, 100, 100, 100), (100, 102.5, 99.5, 102), (102, 102, 99, 99.5), (99.5, 99.5, 99.5, 99.5)])
    t = simulate(c, 0, 1, "close", stop=98, parts=[(102, 0.5), (106, 0.5)], exit_i=3)
    near(t["pnl"], ((102 - TICK - 100.25) * 0.5 + (99.5 - TICK - 100.25) * 0.5) * PV - 2 * COMM)
    t = simulate(c, 0, 1, "close", stop=98, parts=[(102, 0.5), (106, 0.5)], exit_i=3, be_after_part=True)
    assert t["reason"] == "SL"; near(t["pnl"], ((102 - TICK - 100.25) * 0.5 + (100 - TICK - 100.25) * 0.5) * PV - 2 * COMM)
    # 13 trailing stop array: value at bar k applies from bar k+1 and only tightens
    c = Fake([(100, 100, 100, 100), (100, 103, 100, 103), (103, 104, 101, 101.5), (101.5, 102, 101, 101)])
    tr = np.array([np.nan, 101.25, 101.25, np.nan])
    t = simulate(c, 0, 1, "close", stop=98, trail=tr, exit_i=3)
    assert t["reason"] == "SL" and t["k"] == 2; near(t["pnl"], pnl(1, 100, 101.25))
    # 14 exit signal at a bar's close
    sig = np.array([False, True, False, False])
    t = simulate(c, 0, 1, "close", stop=98, exit_sig=sig, exit_i=3)
    assert t["reason"] == "sig" and t["k"] == 1; near(t["pnl"], pnl(1, 100, 103))
    # 15 no-stop trade needs r_pts; a stop on the wrong side is rejected; entry on the flat bar is no trade
    assert simulate(c, 0, 1, "close", exit_i=3) is None
    near(simulate(c, 0, 1, "close", exit_i=3, r_pts=2.0)["R"], pnl(1, 100, 101) / (2 * PV))
    assert simulate(c, 0, 1, "close", stop=100.5, exit_i=3) is None
    assert simulate(c, 3, 1, "close", stop=90, exit_i=3) is None
    # 16 break-even trigger: armed when 103 trades, applies from the next bar
    c = Fake([(100, 100, 100, 100), (100, 103, 99.9, 102), (102, 102, 99.5, 99.8), (99.8, 99.8, 99.8, 99.8)])
    t = simulate(c, 0, 1, "close", stop=98, be_trigger=103, exit_i=3)
    assert t["reason"] == "SL" and t["k"] == 2; near(t["pnl"], pnl(1, 100, 100))
    # 17 sell limit and sell stop mirrors
    c = Fake([(100, 100, 100, 100), (100, 102, 99.5, 101.5), (101.5, 101.5, 98, 98)])
    t = simulate(c, 0, -1, "limit", price=101, expire=1, stop=103, target=98.5, exit_i=2)
    assert t["j"] == 1 and t["reason"] == "TP" and t["k"] == 2; near(t["pnl"], pnl(-1, 101, 98.5))
    c = Fake([(100, 100.5, 100, 100), (100, 100.25, 98, 98.5), (98.5, 99, 97, 97)])
    t = simulate(c, 0, -1, "stop", price=99, expire=1, stop=100.5, exit_i=2)
    assert t["j"] == 1; near(t["pnl"], pnl(-1, 99, 97))
    print("all simulate tests pass")


if __name__ == "__main__":
    run()
