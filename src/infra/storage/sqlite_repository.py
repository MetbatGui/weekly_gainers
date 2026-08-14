import sqlite3
from datetime import datetime, date
from pathlib import Path
from typing import Optional

from domain.models import WeeklyCollectionEvent, WeeklyGainerItem, CollectionStatus
from domain.ports import ReportStoragePort

_ITEM_COLUMNS = [
    "symbol_code", "symbol_name", "start_date", "base_price",
    "end_date", "close_price", "change", "change_rate", "volume", "amount",
]


class SqliteReportStorageAdapter(ReportStoragePort):
    """연도별 SQLite 파일(db/{weekly,monthly}/{year}.db)을 SSOT로 사용하는 저장소 어댑터."""

    def __init__(self, base_dir: str = "db", period_type: str = "WEEKLY"):
        self.period_type = period_type
        subfolder = "weekly" if period_type == "WEEKLY" else "monthly"
        self.base_path = Path(base_dir) / subfolder
        self.base_path.mkdir(parents=True, exist_ok=True)

    def _db_path(self, year: int) -> Path:
        return self.base_path / f"{year}.db"

    def _connect_and_init(self, year: int) -> sqlite3.Connection:
        """스키마(테이블+인덱스)를 보장하며 연결. 쓰기(save) 경로에서만 사용."""
        conn = sqlite3.connect(self._db_path(year))
        conn.execute(
            """CREATE TABLE IF NOT EXISTS events (
                id TEXT PRIMARY KEY, year INTEGER, week INTEGER, month INTEGER,
                week_of_month INTEGER, collected_at TEXT, day_of_week TEXT,
                last_trading_day TEXT, status TEXT, total_count INTEGER, fingerprint TEXT
            )"""
        )
        conn.execute(
            """CREATE TABLE IF NOT EXISTS items (
                event_id TEXT, symbol_code TEXT, symbol_name TEXT,
                start_date TEXT, base_price REAL, end_date TEXT, close_price REAL,
                change REAL, change_rate REAL, volume INTEGER, amount INTEGER
            )"""
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_items_event_id ON items(event_id)"
        )
        return conn

    def _connect_readonly(self, year: int) -> sqlite3.Connection:
        """스키마가 이미 존재한다고 가정하고 DDL 없이 연결. 읽기(get_by_id/exists) 경로 전용."""
        return sqlite3.connect(self._db_path(year))

    @staticmethod
    def _year_of(event_id: str) -> Optional[int]:
        try:
            return int(event_id.split("-")[0])
        except (ValueError, IndexError):
            return None

    def save(self, event: WeeklyCollectionEvent) -> None:
        conn = self._connect_and_init(event.year)
        try:
            conn.execute(
                """INSERT INTO events (id, year, week, month, week_of_month,
                    collected_at, day_of_week, last_trading_day, status, total_count, fingerprint)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(id) DO UPDATE SET
                    year=excluded.year, week=excluded.week, month=excluded.month,
                    week_of_month=excluded.week_of_month, collected_at=excluded.collected_at,
                    day_of_week=excluded.day_of_week, last_trading_day=excluded.last_trading_day,
                    status=excluded.status, total_count=excluded.total_count,
                    fingerprint=excluded.fingerprint""",
                (
                    event.id, event.year, event.week, event.month, event.week_of_month,
                    event.collected_at.isoformat(), event.day_of_week,
                    event.last_trading_day.isoformat(), event.status.value,
                    event.total_count, event.fingerprint,
                ),
            )
            conn.execute("DELETE FROM items WHERE event_id = ?", (event.id,))
            conn.executemany(
                f"""INSERT INTO items (event_id, {", ".join(_ITEM_COLUMNS)})
                    VALUES (?, {", ".join("?" for _ in _ITEM_COLUMNS)})""",
                [
                    (
                        event.id, item.symbol_code, item.symbol_name,
                        item.start_date.isoformat(), item.base_price,
                        item.end_date.isoformat(), item.close_price,
                        item.change, item.change_rate, item.volume, item.amount,
                    )
                    for item in event.items
                ],
            )
            conn.commit()
        finally:
            conn.close()

    def get_by_id(self, event_id: str) -> Optional[WeeklyCollectionEvent]:
        year = self._year_of(event_id)
        if year is None or not self._db_path(year).exists():
            return None

        conn = self._connect_readonly(year)
        try:
            row = conn.execute(
                "SELECT id, year, week, month, week_of_month, collected_at, day_of_week, "
                "last_trading_day, status, total_count, fingerprint FROM events WHERE id = ?",
                (event_id,),
            ).fetchone()
            if row is None:
                return None

            event = WeeklyCollectionEvent(
                id=row[0], year=row[1], week=row[2],
                collected_at=datetime.fromisoformat(row[5]), day_of_week=row[6],
                last_trading_day=date.fromisoformat(row[7]), status=CollectionStatus(row[8]),
                total_count=row[9], fingerprint=row[10],
            )
            event.month = row[3]
            event.week_of_month = row[4]

            item_rows = conn.execute(
                f"SELECT {', '.join(_ITEM_COLUMNS)} FROM items WHERE event_id = ?",
                (event_id,),
            ).fetchall()
            event.items = [
                WeeklyGainerItem(
                    symbol_code=r[0], symbol_name=r[1],
                    start_date=date.fromisoformat(r[2]), base_price=r[3],
                    end_date=date.fromisoformat(r[4]), close_price=r[5],
                    change=r[6], change_rate=r[7], volume=r[8], amount=r[9],
                )
                for r in item_rows
            ]
            return event
        finally:
            conn.close()

    def exists(self, event_id: str) -> bool:
        year = self._year_of(event_id)
        if year is None or not self._db_path(year).exists():
            return False

        conn = self._connect_readonly(year)
        try:
            row = conn.execute(
                "SELECT status FROM events WHERE id = ?", (event_id,)
            ).fetchone()
            return row is not None and row[0] == CollectionStatus.COMPLETED.value
        finally:
            conn.close()
