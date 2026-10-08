"""Helper utilities for MOSDAC Video Generator."""

import calendar
from datetime import date, timedelta
from typing import List


def timelist() -> List[str]:
    """Generate list of time slots at 30-minute intervals from 00:00 to 20:30."""
    times: List[str] = []
    for hour in range(0, 21):  # 0 to 20
        for minute in (0, 30):
            times.append(f"{hour:02d}{minute:02d}")
    return times


def last_month() -> str:
    """Return the abbreviation of the previous month (e.g., 'Sep' for October)."""
    today = date.today()
    first_of_month = today.replace(day=1)
    prev_month = first_of_month - timedelta(days=1)
    return prev_month.strftime("%b")