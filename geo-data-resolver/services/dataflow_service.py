"""
資料流程服務

本模組負責編排批次處理流程，支援：
- 每日模式（不帶日期；內部以分區/日期邏輯處理）
- 日期區間模式（start_date, end_date）

批次處理由 BatchProcessService 執行，透過 Pub/Sub 回呼機制觸發後續批次。
每個批次共用同一個 UUID 以便追蹤流程（flow_id: "geo-data-resolver_{uuid}").
"""

from __future__ import annotations

import base64
import json
from datetime import datetime, timedelta
from typing import Any, Dict, Optional, Tuple, List

from application.batch_process_service import BatchProcessService, BatchContext
from modules.config import config
from modules.exceptions import GeoDataError, DataValidationError
from utils.infra_logging import _logger
from utils.pubsub_services import PubSubService


from utils.request_context import get_current_log

class DataflowService:
    """負責協調地理資料批次流程的服務層。"""

    def __init__(self) -> None:
        self.core = BatchProcessService()
        self.pubsub_service = PubSubService()
        self.log = get_current_log()

    # ---------------------------- public API ----------------------------
    def process(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        統一處理入口：自動判斷每日或日期區間模式。
        回傳第一批的處理結果；後續批次由 Pub/Sub 回呼訊息觸發。
        """

        is_range_mode = start_date is not None or end_date is not None

        if is_range_mode:
            # 補檔 mode
            if not start_date:
                yesterday = datetime.now() - timedelta(days=1)
                start_date = yesterday.strftime("%Y-%m-%d")
            if not end_date:
                end_date = start_date

            def callback_handler(context: BatchContext) -> Optional[str]:
                if context.is_last_batch:
                    _logger.log_text(
                        f"All range batches completed for uuid: {context.batch_uuid}",
                        severity="Info",
                    )
                    return None
                return self.pubsub_service.publish_range_recall(
                    current_batch=context.batch_number,
                    start_date=start_date or "",
                    end_date=end_date or "",
                )

            context = BatchContext(
                batch_number=1,
                start_date=start_date,
                end_date=end_date,
                callback_handler=callback_handler,
                source="range_mode",
                batch_uuid=self.log.log_uuid,
            )
            # 批次前先更新前一輪（或既有）成功紀錄的失敗重試狀態；本輪新寫入將留到下一輪更新
            try:
                yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
                self.core.bq.update_failed_retry_status(yesterday)
            except Exception as e:
                _logger.log_text(f"Pre-batch update_failed_retry_status skipped: {e}", severity="Warning")

            return self.core._process_batch_generic(
                batch_loader_func=self.core._load_geo_data,
                batch_processor_func=self.core._process_single_batch,
                context=context,
                start_date=start_date,
                end_date=end_date,
            )
        
        else:
            # Daily mode
            def callback_handler(context: BatchContext) -> Optional[str]:
                if context.is_last_batch:
                    _logger.log_text(
                        f"All daily batches completed for uuid: {context.batch_uuid}",
                        severity="Info",
                    )
                    return None
                return self.pubsub_service.publish_daily_recall(
                    current_batch=context.batch_number,
                )

            context = BatchContext(
                batch_number=1,
                start_date=None,
                end_date=None,
                callback_handler=callback_handler,
                source="daily_mode",
                batch_uuid=self.log.log_uuid,
            )

            # 批次前先更新前一輪（或既有）成功紀錄的失敗重試狀態；本輪新寫入將留待下一輪更新
            try:
                yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
                self.core.bq.update_failed_retry_status(yesterday)
            except Exception as e:
                _logger.log_text(f"Pre-batch update_failed_retry_status skipped: {e}", severity="Warning")

            return self.core._process_batch_generic(
                batch_loader_func=self.core._load_geo_data,
                batch_processor_func=self.core._process_single_batch,
                context=context,
            )

    def process_recall_batch(
        self,
        message_type: str,
        batch_number: int,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> Dict[str, Any]:
        """處理由 Pub/Sub 回呼觸發的特定批次。"""

        _logger.log_text(
            f"Processing recall: type={message_type}, batch={batch_number}",
            severity="Info",
        )

        if message_type == "range_recall":
            def callback_handler(context: BatchContext) -> Optional[str]:
                if context.is_last_batch:
                    _logger.log_text(
                        f"All range batches completed for uuid: {context.batch_uuid}",
                        severity="Info",
                    )
                    return None
                return self.pubsub_service.publish_range_recall(
                    current_batch=context.batch_number,
                    start_date=start_date or "",
                    end_date=end_date or "",
                )
        else:  # daily_recall
            def callback_handler(context: BatchContext) -> Optional[str]:
                if context.is_last_batch:
                    _logger.log_text(
                        f"All daily batches completed for uuid: {context.batch_uuid}",
                        severity="Info",
                    )
                    return None
                return self.pubsub_service.publish_daily_recall(
                    current_batch=context.batch_number,
                )

        context = BatchContext(
            batch_number=batch_number,
            start_date=start_date if message_type == "range_recall" else None,
            end_date=end_date if message_type == "range_recall" else None,
            callback_handler=callback_handler,
            source=message_type,
            batch_uuid=self.log.log_uuid,
        )

        processor = self.core._process_single_batch
        if message_type == "range_recall":
            return self.core._process_batch_generic(
                batch_loader_func=self.core._load_geo_data,
                batch_processor_func=processor,
                context=context,
                start_date=start_date,
                end_date=end_date,
            )
        else:
            return self.core._process_batch_generic(
                batch_loader_func=self.core._load_geo_data,
                batch_processor_func=processor,
                context=context,
            )

    # ---------------------------- HTTP handlers ----------------------------
    def handle_daily_request(self, request_data: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
        """處理每日模式的 HTTP 請求。"""
        try:
            if self._is_pubsub_message(request_data):
                return self._handle_pubsub_callback(request_data)

            _logger.log_text("Handling daily request", severity="Info")
            result = self.process()
            return result, 200
        except DataValidationError as e:
            return self._create_error_response("validation_error", str(e), 400)
        except GeoDataError as e:
            return self._create_error_response("geo_error", str(e), e.status_code)
        except Exception as e:
            _logger.log_text(f"Error in handle_daily_request: {str(e)}", severity="Error")
            return self._create_error_response("internal_error", "Internal server error", 500)

    def handle_date_range_request(self, request_data: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
        """處理日期區間模式的 HTTP 請求。"""
        try:
            if self._is_pubsub_message(request_data):
                return self._handle_pubsub_callback(request_data)

            start_date = request_data.get("start_date")
            end_date = request_data.get("end_date")
            if not start_date or not end_date:
                return self._create_error_response(
                    "validation_error",
                    "start_date and end_date are required",
                    400,
                )

            _logger.log_text(
                f"Handling date range request: {start_date} to {end_date}",
                severity="Info",
            )
            result = self.process(start_date=start_date, end_date=end_date)
            return result, 200
        except DataValidationError as e:
            return self._create_error_response("validation_error", str(e), 400)
        except GeoDataError as e:
            return self._create_error_response("geo_error", str(e), e.status_code)
        except Exception as e:
            _logger.log_text(f"Error in handle_date_range_request: {str(e)}", severity="Error")
            return self._create_error_response("internal_error", "Internal server error", 500)

    # ---------------------------- pub/sub helpers ----------------------------
    def _is_pubsub_message(self, data: Dict[str, Any]) -> bool:
        """檢查輸入是否為 Pub/Sub push 訊息格式。"""
        return bool(data) and isinstance(data, dict) and "message" in data and "data" in data["message"]

    def _parse_pubsub_message(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """解析 Pub/Sub push 訊息內容為字典。"""
        try:
            message_data = base64.b64decode(data["message"]["data"]).decode("utf-8")
            return json.loads(message_data)
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            raise DataValidationError(f"Invalid Pub/Sub message format: {str(e)}")

    def _handle_pubsub_callback(self, request_data: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
        """處理 Pub/Sub 回呼請求，並路由至對應的處理器。"""
        try:
            payload = self._parse_pubsub_message(request_data)
            message_type = payload.get("message_type")
            _logger.log_text(f"Handling Pub/Sub callback, message_type: {message_type}", severity="Info")

            if message_type == "range_recall":
                return self._handle_range_recall_callback(payload)
            elif message_type == "daily_recall":
                return self._handle_daily_recall_callback(payload)
            else:
                return self._create_error_response(
                    "unknown_message_type",
                    f"Unknown message_type: {message_type}",
                    400,
                )
        except Exception as e:
            _logger.log_text(f"Failed to handle pubsub callback: {str(e)}", severity="Error")
            return self._create_error_response("callback_error", str(e), 400)

    def _handle_daily_recall_callback(self, payload: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
        """處理 daily_recall 訊息類型的回呼。"""
        try:
            params = payload.get("processing_params", {})
            batch_number = params.get("batch_number")
            if not batch_number:
                return self._create_error_response(
                    "validation_error",
                    "Missing required parameters in daily recall",
                    400,
                )

            result = self.process_recall_batch(
                message_type="daily_recall",
                batch_number=int(batch_number),
            )
            return result, 200
        except Exception as e:
            _logger.log_text(f"Error in daily recall callback: {str(e)}", severity="Error")
            return self._create_error_response("callback_error", str(e), 500)

    def _handle_range_recall_callback(self, payload: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
        """處理 range_recall 訊息類型的回呼。"""
        try:
            params = payload.get("processing_params", {})
            batch_number = params.get("batch_number")
            start_date = params.get("start_date")
            end_date = params.get("end_date")

            if not all([batch_number, start_date, end_date]):
                return self._create_error_response(
                    "validation_error",
                    "Missing required parameters in range recall",
                    400,
                )

            result = self.process_recall_batch(
                message_type="range_recall",
                batch_number=str(batch_number),
                start_date=str(start_date),
                end_date=str(end_date),
            )
            return result, 200
        except Exception as e:
            _logger.log_text(f"Error in range recall callback: {str(e)}", severity="Error")
            return self._create_error_response("callback_error", str(e), 500)


    # ---------------------------- error helper ----------------------------
    def _create_error_response(
        self,
        error_type: str,
        message: str,
        status_code: int,
    ) -> Tuple[Dict[str, Any], int]:
        """建立標準化的錯誤回應資料結構。"""
        return {
            "status": "error",
            "error_type": error_type,
            "message": message,
            "timestamp": datetime.now().isoformat(),
        }, status_code

