import time
from unittest.mock import patch

from infra.adapters.krx_adapter import KrxStockDataAdapter


def test_throttle_enforces_minimum_interval_between_requests():
    with patch.object(KrxStockDataAdapter, "_login"):
        adapter = KrxStockDataAdapter()

    adapter.MIN_REQUEST_INTERVAL_SECONDS = 0.05

    with patch("time.sleep") as mock_sleep:
        adapter._last_request_time = time.monotonic()
        adapter._throttle()

    mock_sleep.assert_called_once()
    assert mock_sleep.call_args[0][0] <= 0.05


def test_throttle_skips_sleep_when_interval_already_elapsed():
    with patch.object(KrxStockDataAdapter, "_login"):
        adapter = KrxStockDataAdapter()

    adapter.MIN_REQUEST_INTERVAL_SECONDS = 0.01
    adapter._last_request_time = time.monotonic() - 10  # 이미 충분히 지난 시각

    with patch("time.sleep") as mock_sleep:
        adapter._throttle()

    mock_sleep.assert_not_called()
