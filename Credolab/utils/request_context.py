"""
簡單的請求範圍上下文，使用 contextvars 在整個呼叫鏈中傳遞共用的 Logging 實例
（例如，在 Flask 請求或背景任務中）。

避免在此處匯入 Logging 類別，以防止循環匯入。
"""
from __future__ import annotations

from contextvars import ContextVar
from typing import Any, Optional

_current_log: ContextVar[Optional[Any]] = ContextVar("current_log", default=None)


def set_current_log(log: Any) -> None:
    """設定目前的日誌實例"""


def get_current_log() -> Optional[Any]:
    """取得目前的日誌實例"""


def clear_current_log() -> None:
    """清除目前的日誌實例"""
