#!/usr/bin/env python3
"""E20 - Turn of the month, the cash sessions only (Quantified Strategies). YT1_SPEC.md, Family E.

Spec text:
  Long 09:30 open -> flat bar on the last 4 trading days of a month and the first 3 of the next. No stop.
  Neighbours: last 3 + first 2; last 5 + first 4.

How the position in the month is known without the future (fixed before the first run; see notes/E20.md):
  * a TRADING DAY is a weekday that is not a US stock-market holiday on the fixed list below (New Year's Day, Martin
    Luther King Day, Presidents' Day, Good Friday, Memorial Day, Juneteenth from 2022, Independence Day, Labor Day,
    Thanksgiving, Christmas, with the exchange's observed-date shifts). The list is a calendar a trader holds in
    advance; it is computed from the year alone and reads no bar.
  * "last N of the month", decided before the 09:30 open of day D: the number of calendar trading days AFTER D in
    D's month (from the list only, no bar is read) is smaller than N.
  * "first M of the month": the number of trading days BEFORE D in D's month is smaller than M, where an earlier
    date counts only if it is a calendar trading day AND the bars show a cash session on it (a past weekday without
    a session, e.g. an unscheduled closure, is not a trading day). Dates before the first day the bars cover are
    taken from the calendar alone.
  * D itself must be a calendar trading day with a cash session (a row of the day table). A cash session that the
    futures exchange runs on a listed holiday (the Globex-only half sessions the day table also holds) is NOT a
    trading day: it is neither counted nor traded.
  * each such day is one trade: signalled at the close of the last 1-minute bar before 09:30, entered at the 09:30
    bar's open (etype 'open'), no stop, no target, exit at the flat bar. R unit = 0.1 x the day's daily ATR(14).
Tags: "T-4" .. "T-1" = fourth-to-last .. last trading day of the month, "T+1" .. "T+3" = first .. third.
`calendar_check(ctx)` compares the list with the cash days present in the bars.
"""
import datetime as dt
import numpy as np
import pandas as pd
import core

ID = "E20"
NAME = "Turn of the month, cash sessions: long 09:30 open to the flat bar on the last N and first M trading days"
VARIANTS = {
    "base": dict(last=4, first=3),
    "nb1": dict(last=3, first=2),
    "nb2": dict(last=5, first=4),
}

_ONE = dt.timedelta(days=1)
_HOL = {}


def _easter(y):
    """Easter Sunday, Gregorian calendar (anonymous / Meeus algorithm)."""
    a = y % 19
    b, c = divmod(y, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month, day = divmod(h + l - 7 * m + 114, 31)
    return dt.date(y, month, day + 1)


def _nth(y, month, weekday, n):
    """The n-th `weekday` (0 = Monday) of a month; n = -1 for the last."""
    if n > 0:
        d = dt.date(y, month, 1)
        d += dt.timedelta(days=(weekday - d.weekday()) % 7 + 7 * (n - 1))
        return d
    d = dt.date(y + (month == 12), month % 12 + 1, 1) - _ONE
    return d - dt.timedelta(days=(d.weekday() - weekday) % 7)


def _observed(d, saturday_to_friday=True):
    """A fixed-date holiday on a Saturday is kept on the Friday before, on a Sunday on the Monday after."""
    if d.weekday() == 5:
        return d - _ONE if saturday_to_friday else None
    if d.weekday() == 6:
        return d + _ONE
    return d


def holidays(y):
    """US stock-market holidays of year y: {date: name}. Fixed rules, known years ahead."""
    if y in _HOL:
        return _HOL[y]
    h = {}
    # New Year's Day on a Saturday is not moved to the Friday (it would fall in the old year's last session)
    ny = _observed(dt.date(y, 1, 1), saturday_to_friday=False)
    if ny is not None:
        h[ny] = "New Year's Day"
    h[_nth(y, 1, 0, 3)] = "Martin Luther King Day"
    h[_nth(y, 2, 0, 3)] = "Presidents' Day"
    h[_easter(y) - dt.timedelta(days=2)] = "Good Friday"
    h[_nth(y, 5, 0, -1)] = "Memorial Day"
    if y >= 2022:
        h[_observed(dt.date(y, 6, 19))] = "Juneteenth"
    h[_observed(dt.date(y, 7, 4))] = "Independence Day"
    h[_nth(y, 9, 0, 1)] = "Labor Day"
    h[_nth(y, 11, 3, 4)] = "Thanksgiving"
    h[_observed(dt.date(y, 12, 25))] = "Christmas"
    _HOL[y] = h
    return h


def is_trading_day(d):
    """Calendar answer, no bars: a weekday that is not on the holiday list."""
    return d.weekday() < 5 and d not in holidays(d.year)


def _month_end(d):
    return dt.date(d.year + (d.month == 12), d.month % 12 + 1, 1) - _ONE


def position(d, sessions, first_covered):
    """(trading days before d in its month, calendar trading days after d in its month).
    sessions = dates with a cash session in the bars; only dates BEFORE d are looked up in it."""
    before = 0
    x = d.replace(day=1)
    while x < d:
        if is_trading_day(x) and (x in sessions or x < first_covered):
            before += 1
        x += _ONE
    after = 0
    x, end = d + _ONE, _month_end(d)
    while x <= end:
        if is_trading_day(x):
            after += 1
        x += _ONE
    return before, after


def orders(ctx, last=4, first=3):
    D = ctx.days
    sessions = {t.date() for t in D.index}
    if not len(D):
        return []
    first_covered = D.index[0].date()
    out = []
    for d, day in D.iterrows():
        dd = d.date()
        if not is_trading_day(dd):
            continue                          # a session on a listed holiday is not a trading day
        before, after = position(dd, sessions, first_covered)
        if after < last:
            tag = f"T-{after + 1}"
        elif before < first:
            tag = f"T+{before + 1}"
        else:
            continue
        if not day.atr == day.atr:
            continue                          # no daily ATR: not traded (run_orders drops these days as well)
        i = int(day.i_open) - 1               # the last 1-minute bar before 09:30
        if i < 0 or ctx.cdate[i] != np.datetime64(d, "D") or ctx.tod[i] >= 570:
            continue                          # no bar earlier on the trade date to signal from
        out.append(dict(i=i, side=1, etype="open", exit_i=int(day.i_end), r_pts=0.1 * float(day.atr), tag=tag))
    return out


def trades(ctx, **p):
    return core.run_orders(ctx, orders(ctx, **p), max_per_day=1)


def calendar_check(ctx):
    """The holiday list against the cash days in the bars, over the span of the day table."""
    D = ctx.days
    have = {t.date() for t in D.index}
    d0, d1 = D.index[0].date(), D.index[-1].date()
    cal, x = set(), d0
    while x <= d1:
        if is_trading_day(x):
            cal.add(x)
        x += _ONE
    missing = sorted(cal - have)              # calendar trading days without a cash session in the bars
    extra = sorted(have - cal)                # cash sessions on a day the list calls a holiday (or a weekend)
    return dict(span=f"{d0} -> {d1}", calendar_trading_days=len(cal), cash_days_in_bars=len(have),
                calendar_trading_days_without_a_cash_session=[str(x) for x in missing],
                cash_sessions_on_listed_holidays=[f"{x} {holidays(x.year).get(x, 'not a listed holiday')}"
                                                  + (" (short session)" if bool(D.early[pd.Timestamp(x)]) else "")
                                                  for x in extra])
