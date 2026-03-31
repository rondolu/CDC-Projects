"""
統一的基礎設施日誌模組。

此模組提供完整的日誌管理功能，包括：
- Flow logs (LOG_DATASET.FLOW_LOG)
- API logs (API_DATASET.API_LOG)
- Cloud Logging 結構化日誌

Flow Log Schema:
- DATETIME (STRING): 記錄時間
- FLOW_ID (STRING): 流程識別碼或 UUID_Request
- FLOW_NAME (STRING): 流程名稱或 API Type
- TASK_CODE (STRING): 任務代碼
- TASK_NAME (STRING): 任務名稱
- STATUS (STRING): Success/Error
- MESSAGE (STRING): 錯誤訊息
- SEVERITY (STRING): 嚴重程度

API Log Schema:
- UUID_Request (STRING): 請求唯一識別碼
- API_Type (STRING): API 類型
- API_Name (STRING): API 名稱
- Start_Time (DATETIME): 開始時間
- End_Time (DATETIME): 結束時間
- Status_Code (STRING): 狀態碼
- Status_Detail (STRING): 狀態詳細資訊
- Retry (INTEGER): 重試次數
"""

from __future__ import annotations

from functools import wraps
from datetime import datetime
from typing import Callable, Any, Optional
from uuid import uuid4

from google.cloud import bigquery
from google.cloud import storage
from google.cloud import logging as cloud_logging
from .request_context import get_current_log


_logging_client = cloud_logging.Client()
_log_name = "custom-log"
_logger = _logging_client.logger(_log_name)

class Logging:
    """
    Infra Logging utility

    Example:
        from utils.infra_logging import Logging
        flow_code = "E11_credolab"
        log_uuid = str(uuid4())
        mission_name = "init"
        log = Logging(mission_name, log_uuid, flow_code)
        log.flowlog("main", "99", "message", "Success", "Debug")
    """

    def __init__(self, mission_name: str, log_uuid: str, flow_code: str, date_range: Optional[str] = None):
        # Basic context
        self.mission_name = mission_name
        self.log_uuid = log_uuid or str(uuid4())
        self.date_range = date_range

        # flow_code format: "<flow_id>_<flow_name>" (e.g., "E11_credolab")
        parts = (flow_code or "_").split("_", 1)
        self.flow_id = parts[0]
        self.flow_name = parts[1] if len(parts) > 1 else ""
        self.storage_client = storage.Client()
        self.bigquery_client = bigquery.Client()

        # Config for datasets/tables
        try:
            from modules.config import config  # late import to avoid cycles
            self.flow_log_dataset = config.bq_log_dataset
            self.flow_log_table = config.bq_flow_log_table
            self.api_log_dataset = config.bq_api_dataset
            self.api_log_table = config.bq_api_log_table
        except Exception:
            self.flow_log_dataset = "LOG_DATASET"
            self.flow_log_table = "FLOW_LOG"
            self.api_log_dataset = "API_DATASET"
            self.api_log_table = "API_LOG"

        self.status_s = "Success"
        self.status_f = "Error"
        self.severity_0 = "Info"
        self.severity_1 = "Debug"
        self.severity_2 = "Error"
        self.severity_3 = "Notice"

    # -------------------- Flow log --------------------
    def flowlog(
        self,
        task_name: str,
        task_code: str,
        message: str = "",
        status: Optional[str] = None,
        severity: Optional[str] = None,
        log_table: Optional[str] = None,
    ) -> None:
        """
        將日誌資料寫入 BigQuery FLOW_LOG 表格，並可選擇寫入 Cloud Logging。

        Table Schema (BQ):
          FLOW_ID, DATETIME, FLOW_NAME, TASK_CODE, TASK_NAME, STATUS, MESSAGE, SEVERITY
        """
        flow_id = f"{self.flow_name}_{self.log_uuid}"
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        if status is None:
            status = self.status_s
        if severity is None:
            severity = self.severity_0
        if log_table is None:
            log_table = self.flow_log_table

        row = {
            "FLOW_ID": flow_id,
            "DATETIME": now_str,
            "FLOW_NAME": self.flow_name,
            "TASK_CODE": f"{self.flow_id}{task_code}",
            "TASK_NAME": task_name,
            "STATUS": status,
            "MESSAGE": message,
            "SEVERITY": severity,
        }

        table_id = f"{self.flow_log_dataset}.{log_table}"
        try:
            errors = self.bigquery_client.insert_rows_json(table_id, [row])
            if errors:
                _logger.log_text(f"Flow log insert errors: {errors}", severity="Warning")
        except Exception as e:
            _logger.log_text(f"Failed to write flow log: {e}", severity="Warning")

        # Cloud Logging structured log (always write structured for observability)
        try:
            if str(severity) not in ("Info", "INFO"):
                _logger.log_struct({
                **row,
                "timestamp": datetime.now().isoformat(),
                "log_type": "flow_log",
                "service": "credolab-service",
                "mission_name": self.mission_name,
                "date_range": self.date_range,
                }, severity=severity)
        except Exception as e:
            _logger.log_text(f"Failed to write struct flow log: {e}", severity="Warning")
    # -------------------- API log --------------------
    def apilog(
        self,
        uuid_request: str,
        api_type: str,
        api_name: str,
        start_time: datetime,
        end_time: Optional[datetime] = None,
        status_code: str = "",
        status_detail: str = "",
        retry: int = 0,
    ) -> None:
        """將日誌資料寫入 BigQuery API_LOG 表格和 Cloud Logging。"""
        api_row = {
            "UUID_Request": uuid_request,
            "API_Type": api_type,
            "API_Name": api_name,
            "Start_Time": start_time.isoformat() if start_time else None,
            "End_Time": end_time.isoformat() if end_time else None,
            "Status_Code": str(status_code),
            "Status_Detail": status_detail,
            "Retry": retry,
        }

        structured = {
            **api_row,
            "timestamp": datetime.now().isoformat(),
            "log_type": "api_log",
            "service": "credolab-service",
            "mission_name": self.mission_name,
            "date_range": self.date_range,
            "duration_ms": int((end_time - start_time).total_seconds() * 1000)
            if start_time and end_time else None,
        }

        table_id = f"{self.api_log_dataset}.{self.api_log_table}"
        try:
            errors = self.bigquery_client.insert_rows_json(table_id, [api_row])
            if errors:
                _logger.log_text(f"API log insert errors: {errors}", severity="Warning")
        except Exception as e:
            _logger.log_text(f"Failed to write API log: {e}", severity="Warning")

        # Map HTTP status code to severity
        # Special case for 400 with "reference_number_invalid"
        if str(status_code) == "400" and (
            "reference_number_invalid" in status_detail
            or "Dataset with the specified reference number does not exist" in status_detail
        ):
            severity = "WARNING"
        elif str(status_code).startswith(("4", "5")):
            severity = "ERROR"
        else:
            severity = "Info"
        
        try:
            if str(severity) not in ("Info", "INFO"):
                _logger.log_struct(structured, severity=severity)
        except Exception as e:
            _logger.log_text(f"Failed to write struct api log: {e}", severity="Warning")

    # -------------------- Decorators --------------------
    @staticmethod
    def logtobq(task_code: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """
        裝飾器用於在方法執行前後寫入流程日誌。
        預期實例會有 `log` 屬性且為 Logging 類型。
        如果缺少會退回到臨時的 Logging 實例。
        """
        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            @wraps(func)
            def wrapper(*args, **kwargs):
                # Detect instance (method) vs function
                instance = args[0] if args and hasattr(args[0], "__class__") else None
                # Prefer request-scoped shared logger if available
                shared_log = get_current_log()
                log: Optional[Logging] = (
                    shared_log if isinstance(shared_log, Logging)
                    else (getattr(instance, "log", None) if instance else None)
                )
                if not isinstance(log, Logging):
                    log = Logging(func.__name__, str(uuid4()), "E05_credolab")

                mission_name = getattr(log, "mission_name", None)
                date_range = getattr(log, "date_range", None)
                basicmsg = f"[Mission_name={mission_name}, Function_name={func.__name__}, Date_Range={date_range}]"

                try:
                    if instance:
                        result = func(instance, *args[1:], **kwargs)
                    else:
                        result = func(*args, **kwargs)
                    last_result = result

                    # 嘗試從返回值判斷 HTTP 狀態碼（支援 Flask 的 (body, status) 或 Response.status_code）
                    status_code: Optional[int] = None
                    try:
                        if isinstance(last_result, tuple) and len(last_result) >= 2 and isinstance(last_result[1], int):
                            status_code = last_result[1]
                        elif hasattr(last_result, "status_code"):
                            status_code = int(getattr(last_result, "status_code"))
                    except Exception:
                        status_code = None

                    if isinstance(last_result, str) and last_result.startswith("DEBUG:"):
                        log.flowlog(func.__name__, task_code, basicmsg + last_result, log.status_s, log.severity_1)
                    elif isinstance(last_result, str) and last_result.startswith("NOTICE:"):
                        log.flowlog(func.__name__, task_code, basicmsg + last_result, log.status_s, log.severity_3)
                    elif status_code is not None and status_code >= 400:
                        log.flowlog(
                            func.__name__, task_code, f"{basicmsg} HTTP {status_code}", log.status_f, log.severity_2
                        )
                    else:
                        log.flowlog(func.__name__, task_code, basicmsg, log.status_s, log.severity_0)
                    return result
                except Exception as e:
                    log.flowlog(func.__name__, task_code, basicmsg + "ERROR:" + str(e), log.status_f, log.severity_2)
                    _logger.log_text({e}, severity="Warning")

            return wrapper
        return decorator

    @staticmethod
    def logapicall(api_type: str = "UNKNOWN") -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """
        裝飾器用於寫入 API 日誌。
        預期實例會有 `log` 屬性且為 Logging 類型。
        如果缺少會退回到臨時的 Logging 實例。
        """
        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            @wraps(func)
            def wrapper(*args, **kwargs):
                instance = args[0] if args and hasattr(args[0], "__class__") else None
                shared_log = get_current_log()
                log: Optional[Logging] = (
                    shared_log if isinstance(shared_log, Logging)
                    else (getattr(instance, "log", None) if instance else None)
                )
                if not isinstance(log, Logging):
                    # Standardize to single flow_name for BQ (credolab)
                    log = Logging(func.__name__, str(uuid4()), "E05_credolab")

                start_time = datetime.now()
                try:
                    result = func(instance, *args[1:], **kwargs) if instance else func(*args, **kwargs)
                    end_time = datetime.now()
                    status_code = getattr(result, 'status_code', 200) if hasattr(result, 'status_code') else 200
                    log.apilog(
                        uuid_request=log.log_uuid,
                        api_type=api_type,
                        api_name=func.__name__,
                        start_time=start_time,
                        end_time=end_time,
                        status_code=str(status_code),
                        status_detail="Success",
                    )
                    return result
                except Exception as e:
                    end_time = datetime.now()
                    status_code = getattr(e, 'status_code', 500) if hasattr(e, 'status_code') else 500
                    log.apilog(
                        uuid_request=log.log_uuid,
                        api_type=api_type,
                        api_name=func.__name__,
                        start_time=start_time,
                        end_time=end_time,
                        status_code=str(status_code),
                        status_detail=str(e),
                    )
                    raise
            return wrapper
        return decorator


# Optional aliases for external usage
logtobq = Logging.logtobq
logapicall = Logging.logapicall