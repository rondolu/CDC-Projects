import base64
import json
from typing import Optional, Dict, Any, Tuple
from datetime import datetime, timedelta

from application.batch_process_service import BatchProcessService, BatchContext
from modules.exceptions import CredolabError, DataValidationError
from utils.infra_logging import Logging, _logger
from utils.request_context import get_current_log
from utils.pubsub_services import PubSubService
from utils.helpers import validate_date_format

class DataFlowService:
    """
    說明：
    - 透過 daily recall 回呼機制，將批次處理委派給核心的 BatchProcessService。
    - 本服務僅負責流程編排與回呼設定，不處理核心業務邏輯。
    """

    def __init__(self):
        self.core = BatchProcessService()
        self.pubsub_service = PubSubService()

    @Logging.logtobq(task_code="05")
    def process(self, start_date: Optional[str] = None, end_date: Optional[str] = None, device_type: Optional[str] = None) -> Dict[str, Any]:
        """統一流程處理，自動判斷 daily 或 range 模式

        參數：
        - start_date: 開始日期（YYYY-MM-DD），不提供就使用昨天
        - end_date: 結束日期（YYYY-MM-DD），不提供就使用 start_date
        - device_type: 裝置類型（android 或 ios），不提供就處理全部

        回傳：
        - Dict，包含第一批處理結果與後續批次觸發狀態
        """
        # 確定處理模式：有日期參數為 range，無日期參數為 daily
        is_range_mode = start_date is not None or end_date is not None
        
        # 根據模式選擇回調函數和參數
        if is_range_mode:
            # Range 模式：設定預設值並傳遞日期參數
            if not start_date:
                from datetime import datetime, timedelta
                yesterday = datetime.now() - timedelta(days=1)
                start_date = yesterday.strftime('%Y-%m-%d')
            if not end_date:
                end_date = start_date

            def callback_handler(context: BatchContext):
                # 檢查是否還有下一批次需要處理
                next_batch_number = context.batch_number + 1
                    
                attributes = {"start_date": start_date, "end_date": end_date}
                return self.pubsub_service.publish_range_recall_message(
                    current_batch=context.batch_number,  
                    start_date=start_date,
                    end_date=end_date,
                    attributes=attributes
                )

            context = BatchContext(
                batch_number=1,
                start_date=start_date,
                end_date=end_date,
                device_type=device_type,
                callback_handler=callback_handler,
                source="range_mode"
            )
            
            return self.core._process_batch_generic(
                batch_loader_func=self.core._load_vmb_data,
                batch_processor_func=self.core._initiate_batch_processing,
                context=context,
                start_date=start_date,
                end_date=end_date,
                device_type=device_type
            )
        else:
            # Daily 模式：不傳遞日期參數，讓 SQL 使用 partition_date
            def callback_handler(context: BatchContext):
                # 檢查是否還有下一批次需要處理
                next_batch_number = context.batch_number + 1
                    
                attributes = {"start_date": "", "end_date": ""}
                return self.pubsub_service.publish_daily_recall_message(
                    current_batch=context.batch_number,  
                    attributes=attributes
                )

            context = BatchContext(
                batch_number=1,
                start_date=None,
                end_date=None,
                device_type=device_type,
                callback_handler=callback_handler,
                source="daily_mode"
            )
            
            return self.core._process_batch_generic(
                batch_loader_func=self.core._load_vmb_data,
                batch_processor_func=self.core._initiate_batch_processing,
                context=context,
                device_type=device_type
            )

    @Logging.logtobq(task_code="06")
    def process_recall_batch(
        self,
        message_type: str,
        batch_number: int,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        device_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        """統一回呼批次處理

        參數：
        - message_type: 訊息類型（"daily_recall" 或 "range_recall"）
        - batch_number: 目前要處理的批次編號（從 1 開始）
        - start_date: 開始日期（YYYY-MM-DD），range_recall 時需要
        - end_date: 結束日期（YYYY-MM-DD），range_recall 時需要
        - device_type: 裝置類型（android 或 ios），可選

        回傳：
        - Dict，包含該批次的處理摘要與後續批次發布狀態
        """

        # 根據訊息類型選擇回調函數
        if message_type == "range_recall":
            def callback_handler(context: BatchContext):
                # 檢查是否還有下一批次需要處理
                next_batch_number = context.batch_number + 1
                    
                attributes = {"start_date": start_date or "", "end_date": end_date or ""}
                return self.pubsub_service.publish_range_recall_message(
                    current_batch=context.batch_number, 
                    start_date=start_date or "",
                    end_date=end_date or "",
                    attributes=attributes,
                )
        else:  # daily_recall
            def callback_handler(context: BatchContext):
                # 檢查是否還有下一批次需要處理
                next_batch_number = context.batch_number + 1
                    
                attributes = {"start_date": "", "end_date": ""}
                return self.pubsub_service.publish_daily_recall_message(
                    current_batch=context.batch_number,  
                    attributes=attributes,
                )

        context = BatchContext(
            batch_number=batch_number,
            start_date=start_date if message_type == "range_recall" else None,
            end_date=end_date if message_type == "range_recall" else None,
            device_type=device_type,
            callback_handler=callback_handler,
            source=message_type,
        )

        if message_type == "range_recall":
            return self.core._process_batch_generic(
                batch_loader_func=self.core._load_vmb_data,
                batch_processor_func=self.core._orchestrate_batch_processing,
                context=context,
                start_date=start_date,
                end_date=end_date,
                device_type=device_type,
            )
        else:  # daily_recall
            return self.core._process_batch_generic(
                batch_loader_func=self.core._load_vmb_data,
                batch_processor_func=self.core._orchestrate_batch_processing,
                context=context,
                device_type=device_type,
            )

    @Logging.logtobq(task_code="03")
    def handle_daily_request(self, request_data: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
        """
        處理 Daily 流程請求

        Args:
            request_data: 請求資料

        Returns:
            Tuple[Dict, int]: (回應資料, HTTP狀態碼)
        """
        try:
            # 檢查是否為 Pub/Sub 回調訊息
            if self._is_pubsub_message(request_data):
                return self._handle_pubsub_callback(request_data)
            
            # 處理一般 API 請求
            return self._handle_daily_job_request(request_data)
            
        except DataValidationError as e:
            return self._create_error_response("validation_error", str(e), 400)
        except CredolabError as e:
            # 使用CredolabError的status_code屬性，如果沒有則預設為500
            status_code = getattr(e, 'status_code', 500)
            return self._create_error_response("credolab_error", str(e), status_code)
        except Exception as e:
            _logger.log_text(f"Unexpected error in handle_daily_request: {str(e)}", severity="Error")
            return self._create_error_response("internal_error", "Internal server error occurred", 500)

    @Logging.logtobq(task_code="04")
    def handle_date_range_request(self, request_data: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
        """
        處理日期範圍處理請求

        Args:
            request_data: 請求資料

        Returns:
            Tuple[Dict, int]: (回應資料, HTTP狀態碼)
        """
        try:
            # 解析 Pub/Sub 訊息
            payload = self._parse_pubsub_message(request_data)
            
            if payload.get('message_type') == 'daily_recall':
                return self._handle_daily_recall_batch(payload)
            else:
                return self._handle_range_recall_batch(payload)
                
        except DataValidationError as e:
            return self._create_error_response("validation_error", str(e), 400)
        except CredolabError as e:
            status_code = getattr(e, 'status_code', 500)
            return self._create_error_response("credolab_error", str(e), status_code)
        except Exception as e:
            _logger.log_text(f"Error in handle_date_range_request: {str(e)}", severity="Error")
            return self._create_error_response("internal_error", "Internal server error occurred", 500)

    def _is_pubsub_message(self, data: Dict[str, Any]) -> bool:
        """檢查是否為 Pub/Sub 訊息格式"""
        return 'message' in data and 'data' in data['message']

    def _parse_pubsub_message(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """解析 Pub/Sub 訊息"""
        try:
            message = base64.b64decode(data['message']['data']).decode('utf-8')
            return json.loads(message)
        except (json.JSONDecodeError, KeyError) as e:
            raise DataValidationError(f"Invalid message data format: {str(e)}")

    def _handle_pubsub_callback(self, request_data: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
        """處理 Pub/Sub 回調訊息"""
        try:
            payload = self._parse_pubsub_message(request_data)
            message_type = payload.get('message_type')
            
            print(f"Received pubsub callback with message_type: {message_type}")
            
            if message_type == 'range_recall':
                return self._handle_range_recall_callback(payload)
            elif message_type == 'daily_recall':
                return self._handle_daily_recall_callback(payload)
            else:
                # 未知的訊息類型，記錄並回傳錯誤
                print(f"Unknown message_type: {message_type}, ignoring callback")
                return {
                    "status": "error", 
                    "message": f"Unknown message_type: {message_type}"
                }, 400
                
        except (json.JSONDecodeError, KeyError) as e:
            _logger.log_text(f"Failed to parse pubsub message: {str(e)}", severity="Error")
            return {
                "status": "error", 
                "message": f"Invalid pubsub message format: {str(e)}"
            }, 400

    def _handle_daily_recall_callback(self, payload: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
        """處理 daily recall 回調"""
        processing_params = payload.get('processing_params', {})
        batch_number = processing_params.get('batch_number')
        
        print(f"Processing daily recall: batch {batch_number}")

        # 處理指定批次（daily模式，不需要日期參數）
        result = self.process_recall_batch(
            message_type="daily_recall",
            batch_number=batch_number,
        )

        response_data = {
            "status": "success",
            "message": f"Daily recall batch {batch_number} completed",
            "batch_result": result,
        }

        return response_data, 200

    def _handle_range_recall_callback(self, payload: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
        """處理 range recall 回調"""
        processing_params = payload.get('processing_params', {})
        batch_number = processing_params.get('batch_number')

        # 處理特定批次（無日期限制）
        result = self.process_recall_batch(
            message_type="range_recall",
            batch_number=batch_number,
        )

        response_data = {
            "status": "success",
            "message": f"Range recall batch {batch_number} completed",
            "batch_result": result,
        }

        return response_data, 200

    def _handle_daily_job_request(self, data: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
        """處理日常任務請求"""
        # 只解析 device_type，不使用 start_date/end_date（讓系統自動使用昨天的 partition_date）
        device_type = data.get('device_type')
        
        # 執行處理（Daily 模式：不傳遞日期參數，讓服務自動使用昨天）
        result = self.process(device_type=device_type)
        
        response_data = {
            "status": "success",
            "message": "Daily Credolab flow initiated with recall mechanism",
            "processing_period": {
                "mode": "daily",
                "device_type": device_type or "all"
            },
            "first_batch_result": result
        }
        
        return response_data, 200

    def _handle_daily_recall_batch(self, payload: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
        """處理 daily recall 批次"""
        processing_params = payload.get('processing_params', {})
        start_date = processing_params.get('start_date')
        end_date = processing_params.get('end_date')
        batch_number = processing_params.get('batch_number')

        # 驗證日期格式
        if start_date and not validate_date_format(start_date):
            raise DataValidationError("Invalid start_date format. Expected YYYY-MM-DD")
        if end_date and not validate_date_format(end_date):
            raise DataValidationError("Invalid end_date format. Expected YYYY-MM-DD")

        # 處理指定批次
        result = self.process_recall_batch(
            message_type="daily_recall",
            batch_number=batch_number,
            start_date=start_date,
            end_date=end_date,
        )

        response_data = {
            "status": "success",
            "message": f"Daily recall batch {batch_number} completed",
            "processing_period": {
                "start_date": start_date,
                "end_date": end_date,
            },
            "batch_result": result,
        }

        _logger.log_text(response_data, severity="Info")

        return response_data, 200

    def _handle_range_recall_batch(self, payload: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
        """處理 range recall 批次"""
        start_date = payload.get('start_date')
        end_date = payload.get('end_date')
        device_type = payload.get('device_type')
        
        # 驗證日期格式
        if not validate_date_format(start_date) or not validate_date_format(end_date):
            raise DataValidationError("Invalid date format. Expected YYYY-MM-DD")

        # 處理日期範圍（帶recall機制）
        result = self.process(
            start_date=start_date,
            end_date=end_date,
            device_type=device_type
        )

        response_data = {
            "status": "success",
            "message": "Range processing initiated with recall mechanism",
            "processing_period": {
                "start_date": start_date,
                "end_date": end_date,
                "device_type": device_type or "all"
            },
            "first_batch_result": result
        }
        
        return response_data, 200

    def _create_error_response(self, error_type: str, message: str, status_code: int) -> Tuple[Dict[str, Any], int]:
        """建立錯誤回應"""
        error_response = {
            "status": "error",
            "error_type": error_type,
            "message": message
        }
        
        return error_response, status_code
