"""
Geo Data Resolver Flask 路由藍圖
處理所有與地理資料解析相關的 HTTP 請求和 PubSub 訊息

直接使用 Service Layer 架構，簡化路由邏輯
"""

from flask import Blueprint, jsonify, request

from services.dataflow_service import DataflowService
from utils.infra_logging import Logging, _logger
from utils.request_context import set_current_log, clear_current_log
from uuid import uuid4
from utils.error_handling import handle_route_exceptions, is_pubsub_request

geo_bp = Blueprint('geo_bp', __name__)


@geo_bp.route('/', methods=['POST'])
@Logging.logtobq(task_code="001")
@handle_route_exceptions
def trigger_geo_flow():
    """
    觸發 Google Maps 地理資料處理流程（帶有批次回調機制）
    Daily Job 觸發點：處理完第一批次後，發布帶有 start_date/end_date 的回調訊息
    """
    # 使用 Service Layer 處理請求
    shared_log = Logging(mission_name="route_trigger", log_uuid=str(uuid4()), flow_code="E06_geo_data_resolver")
    set_current_log(shared_log)
    service = DataflowService()
    try:
        data = request.get_json() or {}
    except Exception:
        data = {}

    try:
        response_data, status_code = service.handle_daily_request(data)
        
        # 確保狀態碼在有效範圍內
        if not isinstance(status_code, int) or status_code < 200 or status_code >= 600:
            status_code = 500
            response_data = {
                "status": "error",
                "error_type": "invalid_status_code",
                "message": "Invalid status code returned from service"
            }
            
    except Exception as e:
        _logger.log_text(f"Unhandled exception in trigger_geo_flow: {str(e)}", severity="Error")
        response_data = {
            "status": "error",
            "error_type": "internal_error",
            "message": "Internal server error occurred"
        }
        status_code = 500
    finally:
        clear_current_log()

    # 若為 Pub/Sub push 訊息，成功處理後回傳 204
    if is_pubsub_request(data) and 200 <= status_code < 300:
        return "", 204

    return jsonify(response_data), status_code


@geo_bp.route('/get_data_range', methods=['POST'])
@Logging.logtobq(task_code="002")
@handle_route_exceptions
def get_data_range():
    """
    處理來自 Pub/Sub 的日期範圍處理請求（帶有批次回調機制）
    接收來自 daily job 的回調訊息，處理指定日期範圍的批次
    """
    # 使用 Service Layer 處理請求
    shared_log = Logging(mission_name="route_get_data_range", log_uuid=str(uuid4()), flow_code="E06_geo_data_resolver")
    set_current_log(shared_log)
    service = DataflowService()
    try:
        data = request.get_json() or {}
    except Exception:
        data = {}

    try:
        response_data, status_code = service.handle_date_range_request(data)
        
        # 確保狀態碼在有效範圍內
        if not isinstance(status_code, int) or status_code < 200 or status_code >= 600:
            status_code = 500
            response_data = {
                "status": "error",
                "error_type": "invalid_status_code", 
                "message": "Invalid status code returned from service"
            }
            
    except Exception as e:
        _logger.log_text(f"Unhandled exception in get_data_range: {str(e)}", severity="Error")
        response_data = {
            "status": "error",
            "error_type": "internal_error",
            "message": "Internal server error occurred"
        }
        status_code = 500
    finally:
        clear_current_log()

    # Pub/Sub push 訊息路由：成功後回傳 204
    if is_pubsub_request(data) and 200 <= status_code < 300:
        return "", 204

    return jsonify(response_data), status_code