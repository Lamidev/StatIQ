import datetime
from typing import Tuple, Dict, Any

class TimeHorizonService:
    """
    StatIQ Universal Time Horizon Service.
    Standardizes date and kickoff filtering across:
    - TODAY (today only, up to tomorrow 05:00 WAT)
    - TOMORROW (strictly tomorrow 00:00 to 23:59 WAT)
    - TODAY_AND_TOMORROW / 2DAYS (from now until tomorrow 23:59 WAT)
    - TOMORROW_AND_NEXT / NEXT2DAYS (tomorrow 00:00 until day after tomorrow 23:59 WAT)
    - WEEKEND (Friday to Sunday 23:59 WAT)
    - MIDWEEK_UCL (Tuesday to Wednesday/Thursday 23:59 WAT)
    """

    WAT_TZ = datetime.timezone(datetime.timedelta(hours=1))

    @classmethod
    def normalize_horizon(cls, raw: str) -> str:
        """Normalizes user input string or command argument into a canonical horizon key."""
        if not raw:
            return "TODAY"
        s = raw.lower().replace("_", " ").replace("-", " ").strip()

        # Check explicit TODAY / single-day directives first (e.g. "just for that day", "for that day", "today only")
        if any(k in s for k in [
            "just for that day", "for that day", "just that day", "that day only",
            "just today", "today only", "only today", "same day", "single day", "today"
        ]) and not any(k in s for k in ["and next", "and tomorrow", "and the next", "tomorrow", "next 2 days", "2 days", "2days"]):
            return "TODAY"

        # Check tomorrow and next / next 2 days / tomorrow and the next
        if any(k in s for k in [
            "tomorrow and next", "tomorrow & next", "tomorrow next", "tomorrow + next",
            "tomorrow and the next", "tomorrow & the next", "tomorrow and the next day",
            "tomorrow and day after", "next 2 days", "next2days", "next two days",
            "2 days ahead", "future 2 days"
        ]):
            return "TOMORROW_AND_NEXT"

        # Check today and tomorrow / 2 days / 48h
        if any(k in s for k in [
            "today and tomorrow", "today & tomorrow", "today tomorrow", "today + tomorrow",
            "that day and the next", "that day and next", "2days", "2 days", "48h", "two days"
        ]):
            return "TODAY_AND_TOMORROW"

        # Check strictly tomorrow
        if any(k in s for k in ["tomorrow", "tmrw", "next day"]) and not any(k in s for k in ["next day after", "today and", "and next", "and the next"]):
            return "TOMORROW"

        # Check weekend
        if any(k in s for k in ["weekend", "saturday", "sunday", "fri sun"]):
            return "WEEKEND"

        # Check midweek / champions league
        if any(k in s for k in ["ucl", "champions league", "midweek", "tuesday", "wednesday"]):
            return "MIDWEEK_UCL"

        return "TODAY"

    @classmethod
    def get_horizon_bounds(cls, horizon: str) -> Tuple[float, float, bool, str]:
        """
        Calculates (min_kickoff_ms, end_of_day_ms, today_only_flag, human_readable_desc)
        in WAT (UTC+1) timezone.
        """
        canonical = cls.normalize_horizon(horizon)
        now_wat = datetime.datetime.now(cls.WAT_TZ)
        now_ms = now_wat.timestamp() * 1000.0

        if canonical == "TOMORROW":
            tomorrow_start = (now_wat + datetime.timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
            tomorrow_end = tomorrow_start.replace(hour=23, minute=59, second=59, microsecond=999000)
            return (
                tomorrow_start.timestamp() * 1000.0,
                tomorrow_end.timestamp() * 1000.0,
                False,
                f"Tomorrow ({tomorrow_start.strftime('%a, %d %b')})"
            )

        if canonical == "TODAY_AND_TOMORROW":
            tomorrow_end = (now_wat + datetime.timedelta(days=1)).replace(hour=23, minute=59, second=59, microsecond=999000)
            min_ms = now_ms + (10 * 60 * 1000.0)
            return (
                min_ms,
                tomorrow_end.timestamp() * 1000.0,
                False,
                f"Today & Tomorrow ({now_wat.strftime('%a')} – {(now_wat + datetime.timedelta(days=1)).strftime('%a')})"
            )

        if canonical == "TOMORROW_AND_NEXT":
            tomorrow_start = (now_wat + datetime.timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
            day_after_end = (now_wat + datetime.timedelta(days=2)).replace(hour=23, minute=59, second=59, microsecond=999000)
            return (
                tomorrow_start.timestamp() * 1000.0,
                day_after_end.timestamp() * 1000.0,
                False,
                f"Tomorrow & Next Day ({(now_wat + datetime.timedelta(days=1)).strftime('%a')} – {(now_wat + datetime.timedelta(days=2)).strftime('%a')})"
            )

        if canonical == "WEEKEND":
            days_to_sun = (6 - now_wat.weekday()) % 7
            if days_to_sun == 0 and now_wat.weekday() == 6:
                days_to_sun = 0
            end_of_weekend = (now_wat + datetime.timedelta(days=max(2, days_to_sun))).replace(hour=23, minute=59, second=59, microsecond=999000)
            min_ms = now_ms + (10 * 60 * 1000.0)
            return (
                min_ms,
                end_of_weekend.timestamp() * 1000.0,
                False,
                "Weekend European Block (Fri–Sun)"
            )

        if canonical == "MIDWEEK_UCL":
            days_ahead = 2 if now_wat.weekday() in (1, 2) else 3
            end_of_midweek = (now_wat + datetime.timedelta(days=days_ahead)).replace(hour=23, minute=59, second=59, microsecond=999000)
            min_ms = now_ms + (10 * 60 * 1000.0)
            return (
                min_ms,
                end_of_midweek.timestamp() * 1000.0,
                False,
                "Midweek European Slate (Tue–Thu)"
            )

        # Default: TODAY
        min_ms = now_ms + (10 * 60 * 1000.0)
        end_of_day_ms = (now_wat + datetime.timedelta(days=1)).replace(hour=5, minute=0, second=0, microsecond=0).timestamp() * 1000.0
        return (
            min_ms,
            end_of_day_ms,
            True,
            f"Today ({now_wat.strftime('%a, %d %b')})"
        )

time_horizon_service = TimeHorizonService()
