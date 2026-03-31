"""
路由錯誤處理與 Pub/Sub 檢測工具

提供統一的 Flask 路由錯誤處理裝飾器，以及 Pub/Sub push 訊息格式檢測。

本模組暴露兩個主要介面：
- is_pubsub_request(data): 判斷輸入是否為 Pub/Sub push 訊息格式
- handle_route_exceptions(func): 裝飾器，為 Flask 路由統一處理例外並回傳一致的 JSON 響應
"""

from functools import wraps
from typing import Any, Callable, Dict, Tuple, Optional
from flask import jsonify, request
from utils.infra_logging import _logger

from modules.exceptions import GeoDataError, DataValidationError, GoogleMapsAPIError

__all__ = ["handle_route_exceptions", "is_pubsub_request"]


def is_pubsub_request(data: Dict[str, Any]) -> bool:
    """
    判斷請求內容是否符合 GCP Pub/Sub push 訊息格式。

    Args:
        data: 以 request.get_json() 取得的請求內容（通常為 dict）。

    Returns:
        bool: 當 data 具有形如 {"message": {"data": "..."}} 的結構時回傳 True，否則 False。
    """
    try:
        return isinstance(data, dict) \
            and isinstance(data.get("message"), dict) \
            and "data" in data["message"]
    except Exception:
        return False


def handle_route_exceptions(func: Callable) -> Callable:
    """
    統一路由錯誤處理裝飾器。

    裝飾被註冊為 Flask 路由的函式，攔截並轉換常見例外為一致的 JSON 響應：
    - DataValidationError -> HTTP 400
    - GoogleMapsAPIError -> HTTP e.status_code 或 502（預設）
    - GeoDataError -> HTTP e.status_code 或 500（預設）
    - 其他未預期錯誤 -> HTTP 500（隱藏內部細節）

    Args:
        func: 被裝飾的路由處理函式。

    Returns:
        Callable: 包裹後的路由處理函式，永遠回傳 (jsonify(body), status_code)。
    """

    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except DataValidationError as e:
            _logger.log_text(f"Data validation error: {e}", severity="Warning")
            body = {"status": "error", "error_type": "validation_error", "message": str(e)}
            return jsonify(body), 400
        except GoogleMapsAPIError as e:
            code_val: Optional[int] = getattr(e, "status_code", None)
            try:
                code = int(code_val) if code_val is not None else 502
            except Exception:
                code = 502
            _logger.log_text(f"Google Maps API error: {e}", severity="Warning")
            body = {"status": "error", "error_type": "googlemaps_api_error", "message": str(e)}
            return jsonify(body), code
        except GeoDataError as e:
            code_val: Optional[int] = getattr(e, "status_code", None)
            try:
                code = int(code_val) if code_val is not None else 500
            except Exception:
                code = 500
            _logger.log_text(f"Geo data error: {e}", severity="Warning")
            body = {"status": "error", "error_type": "geo_data_error", "message": str(e)}
            return jsonify(body), code
        except Exception as e:
            _logger.log_text(f"Unhandled error in route: {e}", severity="Error")
            body = {"status": "error", "error_type": "internal_error", "message": "Internal server error"}
            return jsonify(body), 500

    return wrapper
