"""Calendar helpers shared by the universe, factors and strategies."""

from calendar import monthrange
from datetime import date, timedelta


def month_end_dates(from_date: date, to_date: date) -> list[date]:
    """Last weekday (Mon-Fri) of each month with from_date <= d <= to_date.

    Snapshot and rebalancing dates. The trading calendar of the data is the
    union of all markets, including instruments that trade on weekends, so
    dates are not taken from the data. Markets closed on the date (holidays)
    are handled by each instrument using its last price on or before it.
    """
    dates = []
    year, month = from_date.year, from_date.month
    while date(year, month, 1) <= to_date:
        d = date(year, month, monthrange(year, month)[1])
        while d.weekday() >= 5:
            d -= timedelta(days=1)
        if from_date <= d <= to_date:
            dates.append(d)
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return dates
