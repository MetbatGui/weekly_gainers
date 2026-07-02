from typing import List, Set, Optional
from domain.models import WeeklyGainerItem

class GainerFilter:
    """지수 구성종목 합집합 및 등락률 기준에 따라 상승 종목을 필터링하는 도메인 서비스."""

    def __init__(
        self,
        start_components: Optional[Set[str]] = None,
        end_components: Optional[Set[str]] = None,
        threshold: float = 20.0
    ):
        """
        Args:
            start_components: 시작일 기준 지수 구성종목 코드 세트 (None이면 필터링 생략)
            end_components: 종료일 기준 지수 구성종목 코드 세트 (None이면 필터링 생략)
            threshold: 등락률 하한값 (%)
        """
        self.threshold = threshold
        
        # 둘 다 None이 아닌 경우에만 합집합 풀 구성
        if start_components is not None or end_components is not None:
            s = start_components if start_components is not None else set()
            e = end_components if end_components is not None else set()
            self.union_pool = s.union(e)
        else:
            self.union_pool = None

    def filter(self, items: List[WeeklyGainerItem]) -> List[WeeklyGainerItem]:
        """등락률 조건 및 지수 합집합 풀 포함 여부를 기준으로 필터링을 수행합니다."""
        filtered = []
        for item in items:
            # 1. 등락률 20% 이상 (threshold 기준)
            if item.change_rate < self.threshold:
                continue
                
            # 2. 지수 합집합 풀이 구성된 경우, 포함 여부 검증
            if self.union_pool is not None and item.symbol_code not in self.union_pool:
                continue
                
            filtered.append(item)
            
        return filtered
