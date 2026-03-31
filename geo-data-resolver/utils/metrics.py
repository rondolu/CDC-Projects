"""
Google Maps Geo Data Resolver 指標模組

追蹤項目：
- QPS_COUNT：每分鐘 Google Maps API 呼叫次數
- BQ_OPS_COUNT：每分鐘成功寫入 BigQuery 的操作次數

於分鐘切換時列印單行摘要到 stdout；不會寫入 BigQuery。
"""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Optional

from modules.config import config


class _MinutelyMetrics:
    """每分鐘指標收集器"""
    
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._current_minute: Optional[str] = None
        self._api_calls = 0
        self._bq_writes = 0
        self._last_flush_check = datetime.now(timezone.utc)
    
    # --- Public API ---
    def inc_api_call(self) -> None:
        """增加 Google Maps API 呼叫計數"""
        with self._lock:
            self._rollover_if_needed()
            self._api_calls += 1
    
    def inc_bq_write(self, rows: int = 1) -> None:
        """增加 BigQuery 寫入計數"""
        with self._lock:
            self._rollover_if_needed()
            self._bq_writes += rows
    
    def maybe_flush(self) -> None:
        """檢查是否需要刷新指標（在分鐘切換時）"""
        with self._lock:
            self._rollover_if_needed(force_check=True)
    
    # --- Internals ---
    def _now_minute_key(self) -> str:
        """獲取當前分鐘的鍵值"""
        return datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')
    
    def _rollover_if_needed(self, force_check: bool = False) -> None:
        """檢查是否需要切換到新分鐘並刷新舊數據"""
        now = datetime.now(timezone.utc)
        current_key = self._now_minute_key()
        
        # 避免過於頻繁的檢查
        if not force_check and (now - self._last_flush_check).total_seconds() < 5:
            return
        
        self._last_flush_check = now
        
        # 如果分鐘改變，刷新舊指標
        if self._current_minute is not None and self._current_minute != current_key:
            self._flush_locked()
        
        # 設置新的分鐘
        if self._current_minute != current_key:
            self._current_minute = current_key
            self._api_calls = 0
            self._bq_writes = 0
    
    def _flush_locked(self) -> None:
        """刷新當前指標到輸出（需要在鎖內調用）"""
        if self._current_minute is None:
            return
        
        # 簡單的 stdout 輸出
        try:
            project_id = getattr(config, 'project_id', 'unknown')
        except Exception:
            project_id = 'unknown'
        
        message = (
            f"[METRICS] {self._current_minute} | "
            f"Project: {project_id} | "
            f"GoogleMaps_API_Calls: {self._api_calls} | "
            f"BQ_Writes: {self._bq_writes}"
        )
        
        print(message)


# 全域實例
metrics = _MinutelyMetrics()