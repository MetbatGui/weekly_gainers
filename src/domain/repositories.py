from abc import ABC, abstractmethod
from typing import Optional, List
from .models import WeeklyCollectionEvent

class IWeeklyGainerRepository(ABC):
    """주간 등락률 데이터 및 수집 이벤트를 관리하는 레포지토리 인터페이스.
    
    이 인터페이스를 상속받아 파케이, DB 등 다양한 저장 방식을 구현할 수 있습니다.
    """

    @abstractmethod
    def save(self, event: WeeklyCollectionEvent) -> None:
        """수집 이벤트 및 관련 종목 데이터를 저장합니다.

        Args:
            event (WeeklyCollectionEvent): 저장할 수집 이벤트 엔티티
        """
        pass

    @abstractmethod
    def get_by_id(self, event_id: str) -> Optional[WeeklyCollectionEvent]:
        """식별자(예: 2026-W18)를 통해 수집 이벤트를 조회합니다.

        Args:
            event_id (str): 주차 식별자

        Returns:
            Optional[WeeklyCollectionEvent]: 조회된 이벤트 엔티티, 없으면 None
        """
        pass

    @abstractmethod
    def exists(self, event_id: str) -> bool:
        """해당 주차의 데이터가 이미 존재하는지 확인합니다.

        Args:
            event_id (str): 주차 식별자

        Returns:
            bool: 존재 여부
        """
        pass

    @abstractmethod
    def list_all_events(self) -> List[WeeklyCollectionEvent]:
        """저장된 모든 수집 이벤트의 메타데이터 리스트를 반환합니다.

        Returns:
            List[WeeklyCollectionEvent]: 수집 이벤트 리스트
        """
        pass
