#!/usr/bin/env python3
"""Hand-built checks for the RDM detection primitives (tools/rdm.py). Run: python3 tests/test_rdm.py (pytest-compatible)."""
import sys, pathlib
import numpy as np
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "tools"))
import rdm


def test_pivot_high_and_low():
    h = np.array([1, 2, 3, 9, 3, 2, 1, 2, 3], float)
    l = np.array([5, 4, 3, 7, 3, 1, 4, 5, 6], float)
    ph, pl = rdm.pivots(h, l, 3)
    assert list(np.flatnonzero(ph)) == [3]          # 9 above the 3 before and >= the 3 after
    assert list(np.flatnonzero(pl)) == [5]          # 1 below the 3 before, <= the 3 after


def test_pivot_needs_full_right_side_and_strict_left():
    h = np.array([1, 2, 3, 9, 3, 2], float)        # only 2 bars after the 9: not a pivot yet
    assert not rdm.pivots(h, h, 3)[0].any()
    h = np.array([9, 1, 2, 9, 3, 2, 1], float)     # equal high 3 bars earlier: not strictly above the left side
    assert not rdm.pivots(h, h, 3)[0][3]


def test_smt_bearish_x_sweeps_y_fails():
    # X: swing high 10 at bar 3 (confirmed at bar 6), sweep at bar 8 (11 > 10). Y: corresponding high 20, stays below.
    hx = np.array([5, 6, 7, 10, 7, 6, 5, 8, 11, 9], float)
    hy = np.array([15, 16, 17, 20, 17, 16, 15, 18, 19, 18], float)
    ev = rdm.smt_events(hx, hx - 1, hy, hy - 1, 3)
    assert (8, -1, 3) in ev


def test_smt_none_when_y_also_sweeps():
    hx = np.array([5, 6, 7, 10, 7, 6, 5, 8, 11, 9], float)
    hy = np.array([15, 16, 17, 20, 17, 16, 15, 18, 21, 18], float)   # Y makes a higher high too
    assert all(e[1] != -1 for e in rdm.smt_events(hx, hx - 1, hy, hy - 1, 3))


def test_smt_no_lookahead_sweep_before_confirmation_is_ignored():
    # the high at bar 3 is only confirmed at bar 6; a break at bar 5 would contradict the pivot, so it never pivots
    hx = np.array([5, 6, 7, 10, 7, 12, 5, 8, 13, 9], float)
    hy = np.array([15, 16, 17, 20, 17, 16, 15, 18, 19, 18], float)
    assert all(not (e[1] == -1 and e[2] == 3) for e in rdm.smt_events(hx, hx - 1, hy, hy - 1, 3))


def test_smt_bullish_mirror():
    lx = np.array([10, 9, 8, 5, 8, 9, 10, 7, 4, 6], float)
    ly = np.array([30, 29, 28, 25, 28, 29, 30, 27, 26, 27], float)
    ev = rdm.smt_events(lx + 1, lx, ly + 1, ly, 3)
    assert (8, 1, 3) in ev


def test_fvg_bullish_and_bearish():
    h = np.array([10, 12, 15, 14, 9], float)
    l = np.array([8, 9, 11, 10, 7], float)
    g = rdm.fvgs(h, l)
    assert (2, 1, 10.0, 11.0) in g                  # l[2] = 11 > h[0] = 10
    assert (4, -1, 9.0, 11.0) in g                  # h[4] = 9 < l[2] = 11


def test_zone_touch_overlap_and_activity():
    bar_lo, bar_hi, bar_t = np.array([100., 104.]), np.array([103., 106.]), np.array([10, 20])
    z_lo, z_hi = np.array([102., 107., 101.]), np.array([102.5, 108., 101.5])
    z_from, z_until = np.array([0, 0, 15]), np.array([100, 100, 100])
    ids = ["a", "b", "c"]
    # a overlaps bar 0; b is above both bars; c overlaps bar 0's range but only becomes active at 15
    assert rdm.zone_touch(bar_lo, bar_hi, bar_t, z_lo, z_hi, z_from, z_until, ids) == {"a"}
    assert rdm.zone_touch(bar_lo[1:], bar_hi[1:], bar_t[1:], z_lo, z_hi, z_from, z_until, ids) == set()


def test_bearish_smt_is_a_high_sweep():
    # regression (stage 2): the bearish SMT (dir -1) sweeps a swing HIGH, so the trade it sets up is a short
    hx = np.array([5, 6, 7, 10, 7, 6, 5, 8, 11, 9], float)
    hy = np.array([15, 16, 17, 20, 17, 16, 15, 18, 19, 18], float)
    t, d, p = [e for e in rdm.smt_events(hx, hx - 1, hy, hy - 1, 3) if e[0] == 8][0]
    assert d == -1 and hx[t] > hx[p]
    import inspect
    assert "side = dd " in inspect.getsource(rdm.setups_day)


if __name__ == "__main__":
    fails = 0
    for name, f in sorted(globals().items()):
        if name.startswith("test_") and callable(f):
            try:
                f(); print(f"ok    {name}")
            except AssertionError as e:
                fails += 1; print(f"FAIL  {name} {e}")
    print(f"{'all passed' if not fails else f'{fails} failed'}")
    sys.exit(1 if fails else 0)
