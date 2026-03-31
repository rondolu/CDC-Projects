"""
每分鐘指標彙整（僅列印，不寫入後端）。

追蹤項目：
- QPS_COUNT：每分鐘 Credolab API 呼叫次數
- BQ_OPS_COUNT：每分鐘成功寫入 BigQuery 的操作次數

於分鐘切換時列印單行摘要到 stdout；不會寫入 BigQuery。
"""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Optional

from modules.config import config


class _MinutelyMetrics:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._minute_key: Optional[str] = None  # 格式：YYYYMMDDHHMM
        self._qps_count = 0
        self._bq_ops_count = 0
    # 依需求不追蹤列數（rows）
    # --- Public API ---
    def inc_api_call(self) -> None:
        self._rollover_if_needed()
        with self._lock:
            self._qps_count += 1

    def inc_bq_write(self, rows: int) -> None:
        self._rollover_if_needed()
        with self._lock:
            self._bq_ops_count += 1
            # 忽略傳入的列數參數

    def maybe_flush(self) -> None:
    # 在接近分鐘邊界時定期呼叫；若不需切換則成本很低
        self._rollover_if_needed(force_check=True)

    # --- Internals ---
    def _now_minute_key(self) -> str:
        now = datetime.now(timezone.utc)
        return now.strftime("%Y%m%d%H%M")

    def _rollover_if_needed(self, force_check: bool = False) -> None:
        current_key = self._now_minute_key()
        # fast path without lock
        if not force_check and self._minute_key == current_key:
            return
        with self._lock:
            if self._minute_key is None:
                # Initialize on first use
                self._minute_key = current_key
                return
            if self._minute_key != current_key:
                # Flush previous minute
                self._flush_locked()
                # Switch to new minute window
                self._minute_key = current_key
                self._qps_count = 0
                self._bq_ops_count = 0
                # nothing to reset for rows

    def _flush_locked(self) -> None:
        # Nothing to flush
        if self._qps_count == 0 and self._bq_ops_count == 0:
            return
        # Compose and print one-line summary for the previous minute
        if not self._minute_key:
            return
        minute_dt = datetime.strptime(self._minute_key, "%Y%m%d%H%M").replace(tzinfo=timezone.utc)
        try:
            print(
                "[MINUTE_METRICS] "
                f"ts={minute_dt.isoformat()} minute={self._minute_key} "
                f"qps={int(self._qps_count)} bq_ops={int(self._bq_ops_count)} "
                f"project={config.project_id}"
            )
        except Exception:
            # Never fail main flow due to metrics printing
            pass


metrics = _MinutelyMetrics()
