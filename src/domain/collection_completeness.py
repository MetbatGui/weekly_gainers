"""Pure DB-coverage rules for scheduled weekly and monthly collections."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Iterable, Literal

from domain.models import CollectionStatus, WeeklyCollectionEvent

PeriodType = Literal["WEEKLY", "MONTHLY"]


@dataclass(frozen=True)
class RequiredPeriod:
    period_type: PeriodType
    event_id: str
    year: int
    value: int
    start_date: date
    end_date: date
    is_final: bool
    force: bool


def find_required_periods(
    events: Iterable[WeeklyCollectionEvent],
    *,
    period_type: PeriodType,
    coverage_start: date,
    today: date,
) -> list[RequiredPeriod]:
    """Return missing or invalid periods between the coverage start and today.

    Past periods must be FINAL. The in-progress current period may be COMPLETED or
    FINAL, but any structural inconsistency is repaired with a forced recollection.
    """
    period_type = period_type.upper()  # type: ignore[assignment]
    if period_type not in ("WEEKLY", "MONTHLY"):
        raise ValueError(f"Unsupported period type: {period_type}")
    if coverage_start > today:
        return []

    by_id = {event.id: event for event in events}
    periods = (
        _weekly_periods(coverage_start, today)
        if period_type == "WEEKLY"
        else _monthly_periods(coverage_start, today)
    )

    required: list[RequiredPeriod] = []
    for period in periods:
        existing = by_id.get(period.event_id)
        if existing is None:
            required.append(period)
            continue
        if not _is_complete(existing, period):
            required.append(
                RequiredPeriod(
                    **{**period.__dict__, "force": True},
                )
            )
    return required


def _weekly_periods(coverage_start: date, today: date) -> list[RequiredPeriod]:
    monday = coverage_start - timedelta(days=coverage_start.weekday())
    # A partial week belongs to the coverage only when its Thursday is on or
    # after the requested start. This preserves the ISO year boundary rule:
    # 2024-12-30 belongs to 2025-W01, while 2022-W52 is not pulled in merely
    # because the coverage begins on 2023-01-01.
    if monday + timedelta(days=3) < coverage_start:
        monday += timedelta(weeks=1)
    current_monday = today - timedelta(days=today.weekday())
    periods: list[RequiredPeriod] = []
    while monday <= current_monday:
        iso_year, iso_week, _ = monday.isocalendar()
        periods.append(
            RequiredPeriod(
                period_type="WEEKLY",
                event_id=f"{iso_year}-W{iso_week:02d}",
                year=iso_year,
                value=iso_week,
                start_date=monday,
                end_date=monday + timedelta(days=4),
                is_final=monday < current_monday,
                force=False,
            )
        )
        monday += timedelta(weeks=1)
    return periods


def _monthly_periods(coverage_start: date, today: date) -> list[RequiredPeriod]:
    cursor = coverage_start.replace(day=1)
    current_month = today.replace(day=1)
    periods: list[RequiredPeriod] = []
    while cursor <= current_month:
        next_month = cursor.replace(year=cursor.year + 1, month=1) if cursor.month == 12 else cursor.replace(month=cursor.month + 1)
        periods.append(
            RequiredPeriod(
                period_type="MONTHLY",
                event_id=f"{cursor.year}-M{cursor.month:02d}",
                year=cursor.year,
                value=cursor.month,
                start_date=cursor,
                end_date=next_month - timedelta(days=1),
                is_final=cursor < current_month,
                force=False,
            )
        )
        cursor = next_month
    return periods


def _is_complete(event: WeeklyCollectionEvent, period: RequiredPeriod) -> bool:
    if event.total_count <= 0:
        return False
    if period.is_final and event.status != CollectionStatus.FINAL:
        return False
    if not period.is_final and event.status != CollectionStatus.COMPLETED:
        return False
    if not (period.start_date <= event.last_trading_day <= period.end_date):
        return False

    if period.period_type == "MONTHLY":
        return (
            event.id == period.event_id
            and event.week == 0
            and event.month == period.value
            and event.week_of_month == 0
        )

    thursday = event.last_trading_day + timedelta(days=3 - event.last_trading_day.weekday())
    iso_year, iso_week, _ = thursday.isocalendar()
    week_of_month = sum(
        (date(thursday.year, thursday.month, 1) + timedelta(days=offset)).weekday() == 3
        for offset in range(thursday.day)
    )
    return (
        event.id == period.event_id
        and event.month == thursday.month
        and event.week_of_month == week_of_month
        and (iso_year, iso_week) == (period.year, period.value)
    )
