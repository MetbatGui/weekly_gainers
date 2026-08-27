from datetime import date, datetime

from domain.collection_completeness import find_required_periods
from domain.models import CollectionStatus, WeeklyCollectionEvent


def event(
    event_id: str,
    year: int,
    week: int,
    last_trading_day: date,
    *,
    month: int | None = None,
    week_of_month: int | None = None,
    status: CollectionStatus = CollectionStatus.FINAL,
    total_count: int = 100,
) -> WeeklyCollectionEvent:
    result = WeeklyCollectionEvent(
        id=event_id,
        year=year,
        week=week,
        collected_at=datetime(2026, 1, 1),
        day_of_week="Thursday",
        last_trading_day=last_trading_day,
        status=status,
        total_count=total_count,
    )
    if month is not None:
        result.month = month
    if week_of_month is not None:
        result.week_of_month = week_of_month
    return result


def test_finds_an_interior_weekly_gap_even_when_newer_data_exists():
    events = [
        event("2023-W01", 2023, 1, date(2023, 1, 6)),
        event(
            "2023-W03",
            2023,
            3,
            date(2023, 1, 20),
            status=CollectionStatus.COMPLETED,
        ),
    ]

    required = find_required_periods(
        events, period_type="WEEKLY", coverage_start=date(2023, 1, 1), today=date(2023, 1, 20)
    )

    assert [(item.event_id, item.is_final, item.force) for item in required] == [
        ("2023-W02", True, False),
    ]


def test_assigns_december_monday_to_next_year_iso_week_one():
    required = find_required_periods(
        [], period_type="WEEKLY", coverage_start=date(2024, 12, 30), today=date(2025, 1, 3)
    )

    assert len(required) == 1
    period = required[0]
    assert (period.event_id, period.year, period.value, period.start_date, period.end_date) == (
        "2025-W01", 2025, 1, date(2024, 12, 30), date(2025, 1, 3)
    )
    assert period.is_final is False


def test_distinguishes_a_real_iso_week_53_from_a_nonexistent_one():
    real_week_53 = find_required_periods(
        [], period_type="WEEKLY", coverage_start=date(2020, 12, 28), today=date(2021, 1, 1)
    )
    no_phantom_week_53 = find_required_periods(
        [], period_type="WEEKLY", coverage_start=date(2021, 1, 1), today=date(2021, 1, 8)
    )

    assert [period.event_id for period in real_week_53] == ["2020-W53"]
    assert [period.event_id for period in no_phantom_week_53] == ["2021-W01"]


def test_finds_missing_december_month_when_january_data_exists():
    events = [
        event(
            "2024-M01", 2024, 0, date(2024, 1, 15), month=1, week_of_month=0,
            status=CollectionStatus.COMPLETED,
        ),
    ]

    required = find_required_periods(
        events, period_type="MONTHLY", coverage_start=date(2023, 12, 1), today=date(2024, 1, 15)
    )

    assert [(item.event_id, item.is_final, item.force) for item in required] == [
        ("2023-M12", True, False),
    ]


def test_forces_recollection_of_historical_event_with_unknown_market_total():
    events = [event("2023-W01", 2023, 1, date(2023, 1, 6), total_count=0)]

    required = find_required_periods(
        events, period_type="WEEKLY", coverage_start=date(2023, 1, 2), today=date(2023, 1, 13)
    )

    assert [(item.event_id, item.is_final, item.force) for item in required] == [
        ("2023-W01", True, True),
        ("2023-W02", False, False),
    ]


def test_forces_recollection_when_week_has_wrong_thursday_month_assignment():
    events = [
        event(
            "2024-W01", 2024, 1, date(2024, 1, 5), month=12, week_of_month=5,
            status=CollectionStatus.COMPLETED,
        ),
    ]

    required = find_required_periods(
        events, period_type="WEEKLY", coverage_start=date(2024, 1, 1), today=date(2024, 1, 5)
    )

    assert [(item.event_id, item.is_final, item.force) for item in required] == [
        ("2024-W01", False, True),
    ]


def test_forces_refresh_when_current_week_was_prematurely_finalized():
    events = [event("2024-W01", 2024, 1, date(2024, 1, 5), status=CollectionStatus.FINAL)]

    required = find_required_periods(
        events, period_type="WEEKLY", coverage_start=date(2024, 1, 1), today=date(2024, 1, 5)
    )

    assert [(item.event_id, item.is_final, item.force) for item in required] == [
        ("2024-W01", False, True),
    ]


def test_forces_refresh_when_current_month_was_prematurely_finalized():
    events = [
        event(
            "2024-M01", 2024, 0, date(2024, 1, 15), month=1, week_of_month=0,
            status=CollectionStatus.FINAL,
        ),
    ]

    required = find_required_periods(
        events, period_type="MONTHLY", coverage_start=date(2024, 1, 1), today=date(2024, 1, 15)
    )

    assert [(item.event_id, item.is_final, item.force) for item in required] == [
        ("2024-M01", False, True),
    ]
