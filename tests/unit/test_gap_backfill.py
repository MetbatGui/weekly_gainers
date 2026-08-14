from datetime import date

from application.services.collection_orchestrator_service import (
    compute_gap_weeks,
    compute_gap_months,
)


def test_compute_gap_weeks_returns_empty_when_no_last_sync():
    assert compute_gap_weeks(None, date(2026, 6, 26), (2026, 25), (2026, 26)) == []


def test_compute_gap_weeks_returns_empty_when_gap_within_threshold():
    """last_sync 다음날 ~ 오늘 사이 공백이 min_days_back 이하면 (표준 지난주 처리로 충분) 백필 불필요."""
    last_sync = date(2026, 6, 19)  # 6/26(금) 기준 7일 전
    today = date(2026, 6, 26)
    assert compute_gap_weeks(last_sync, today, (2026, 25), (2026, 26), min_days_back=7) == []


def test_compute_gap_weeks_returns_missing_weeks_beyond_threshold():
    """크론이 3주 멈췄다가 재개된 경우, 표준 지난주 범위보다 앞선 주차들을 백필 대상으로 계산."""
    last_sync = date(2026, 6, 1)   # 2026-W23 월요일
    today = date(2026, 6, 26)      # 2026-W26 금요일 (표준 흐름이 W25/W26을 처리)

    gap_weeks = compute_gap_weeks(last_sync, today, (2026, 25), (2026, 26), min_days_back=7)

    # W23(경계 직후)~W24까지가 갭 대상, W25/W26은 표준 흐름이 처리하므로 제외
    assert gap_weeks == [(2026, 23), (2026, 24)]


def test_compute_gap_months_returns_empty_when_no_last_sync():
    assert compute_gap_months(None, date(2026, 6, 26), (2026, 5), (2026, 6)) == []


def test_compute_gap_months_returns_empty_when_gap_within_threshold():
    last_sync = date(2026, 6, 19)
    today = date(2026, 6, 26)
    assert compute_gap_months(last_sync, today, (2026, 5), (2026, 6), min_days_back=7) == []


def test_compute_gap_months_returns_missing_months_beyond_threshold():
    last_sync = date(2026, 3, 15)
    today = date(2026, 6, 26)

    gap_months = compute_gap_months(last_sync, today, (2026, 5), (2026, 6), min_days_back=7)

    # 표준 흐름은 5월(지난달)/6월(이번달)을 처리하므로, 그 이전 달만 갭 대상
    assert gap_months == [(2026, 3), (2026, 4)]


def test_compute_gap_months_excludes_current_month_even_if_last_sync_was_this_month():
    """last_sync가 이번 달 안이면(월 중순에 크론이 오래 멈췄다 재개), 진행 중인 이번 달을
    갭으로 오인해 조기에 FINAL 확정하면 안 된다 (리뷰 지적사항: 되돌리면 collect_period가
    이후 실시간 업데이트/월말 확정을 전부 스킵하게 됨)."""
    last_sync = date(2026, 6, 1)  # 이번 달(6월) 초
    today = date(2026, 6, 26)     # gap_days = 24 > 7 이지만 last_sync가 이미 이번 달

    gap_months = compute_gap_months(last_sync, today, (2026, 5), (2026, 6), min_days_back=7)

    assert gap_months == []
