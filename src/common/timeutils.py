"""UTC storage / Puerto Rico display time conversions.

Contract (non-negotiable #5 in the product spec): every timestamp is stored
in UTC. Local calendar dates, hours, and display strings are *derived* from
UTC using ``America/Puerto_Rico`` at read/display time. A timestamp that has
been shifted for display must never be relabeled as UTC.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

UTC = ZoneInfo("UTC")
PUERTO_RICO_TZ = ZoneInfo("America/Puerto_Rico")


def now_utc() -> datetime:
    return datetime.now(tz=UTC)


def to_puerto_rico(ts: datetime) -> datetime:
    """Convert an aware (or UTC-assumed naive) UTC timestamp to AST/AST-DST."""
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=UTC)
    return ts.astimezone(PUERTO_RICO_TZ)


def puerto_rico_date(ts: datetime) -> date:
    """The America/Puerto_Rico calendar date for a UTC timestamp."""
    return to_puerto_rico(ts).date()


def puerto_rico_hour(ts: datetime) -> int:
    return to_puerto_rico(ts).hour


def today_in_puerto_rico(now: datetime | None = None) -> date:
    return puerto_rico_date(now or now_utc())


def yesterday_in_puerto_rico(now: datetime | None = None) -> date:
    """Resolve "yesterday" once, in Puerto Rico local time.

    This is the canonical reference-date resolution used by data generation.
    Callers must resolve this exactly once per run and freeze the result into
    the run manifest; do not call this repeatedly across a pipeline, since
    wall-clock drift across job steps would break reproducibility.
    """
    return today_in_puerto_rico(now) - timedelta(days=1)


def format_pr_display(ts: datetime, *, with_seconds: bool = False) -> str:
    """Human-facing "AST" display string, e.g. '2026-03-04 14:05 AST'."""
    local = to_puerto_rico(ts)
    fmt = "%Y-%m-%d %H:%M:%S" if with_seconds else "%Y-%m-%d %H:%M"
    tzname = local.tzname() or "AST"
    return f"{local.strftime(fmt)} {tzname}"


def pr_midnight_utc(day: date) -> datetime:
    """UTC instant corresponding to local midnight on ``day`` in Puerto Rico."""
    local_midnight = datetime(day.year, day.month, day.day, 0, 0, 0, tzinfo=PUERTO_RICO_TZ)
    return local_midnight.astimezone(UTC)
