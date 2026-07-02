from datetime import date
import pytest

from domain.models import WeeklyGainerItem
from domain.gainer_filter import GainerFilter

def test_union_filter():
    """GainerFilter가 시작/종료일 지수구성종목 합집합 및 등락률 20% 이상 기준에 맞춰 정확히 필터링하는지 검증"""
    start_components = {"A", "B", "C"}
    end_components = {"C", "D", "E"}
    # 합집합 풀: {"A", "B", "C", "D", "E"}

    filter_logic = GainerFilter(start_components, end_components, threshold=20.0)

    # 테스트용 종목 데이터 구성
    items = [
        # 통과 조건 만족 (합집합 속함 & 20% 이상)
        WeeklyGainerItem("A", "종목A", date(2026, 6, 22), 10000.0, date(2026, 6, 26), 12500.0, 2500.0, 25.0, 1000, 12500000),
        # 탈락: 등락률 미달 (15% < 20%)
        WeeklyGainerItem("B", "종목B", date(2026, 6, 22), 10000.0, date(2026, 6, 26), 11500.0, 1500.0, 15.0, 1000, 11500000),
        # 통과 조건 만족 (합집합 속함 & 딱 20%)
        WeeklyGainerItem("C", "종목C", date(2026, 6, 22), 10000.0, date(2026, 6, 26), 12000.0, 2000.0, 20.0, 1000, 12000000),
        # 통과 조건 만족 (종료일에만 있었으나 합집합에 포함되므로 통과)
        WeeklyGainerItem("E", "종목E", date(2026, 6, 22), 10000.0, date(2026, 6, 26), 20000.0, 10000.0, 100.0, 1000, 20000000),
        # 탈락: 합집합 풀에 제외된 종목 (등락률은 30%로 만족하나 풀에 없음)
        WeeklyGainerItem("F", "종목F", date(2026, 6, 22), 10000.0, date(2026, 6, 26), 13000.0, 3000.0, 30.0, 1000, 13000000),
    ]

    filtered_items = filter_logic.filter(items)

    # A, C, E 세 종목만 필터링되어야 함
    assert len(filtered_items) == 3
    symbols = {item.symbol_code for item in filtered_items}
    assert symbols == {"A", "C", "E"}

def test_no_index_filter():
    """지수 구성종목 제한이 없을 때, 단순 등락률 기준으로만 필터링하는지 검증"""
    filter_logic = GainerFilter(start_components=None, end_components=None, threshold=20.0)

    items = [
        WeeklyGainerItem("A", "종목A", date(2026, 6, 22), 10000.0, date(2026, 6, 26), 12500.0, 2500.0, 25.0, 1000, 12500000),
        WeeklyGainerItem("B", "종목B", date(2026, 6, 22), 10000.0, date(2026, 6, 26), 11500.0, 1500.0, 15.0, 1000, 11500000),
        WeeklyGainerItem("F", "종목F", date(2026, 6, 22), 10000.0, date(2026, 6, 26), 13000.0, 3000.0, 30.0, 1000, 13000000),
    ]

    filtered_items = filter_logic.filter(items)

    # 지수 제한이 없으므로 등락률 20% 이상인 A, F 모두 통과되어야 함
    assert len(filtered_items) == 2
    symbols = {item.symbol_code for item in filtered_items}
    assert symbols == {"A", "F"}
