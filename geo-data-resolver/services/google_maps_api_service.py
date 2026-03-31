"""
Google Maps API Service 模組
提供 Google Maps API 呼叫的高層級介面，整合速率限制和錯誤處理
"""

import os
from typing import Dict, Any, Optional, List
from datetime import datetime
from uuid import uuid4

from infrastructure.google_maps_client import GoogleMapsAPIClient
from models.google_maps_models import POIScenarioEnum
from utils.request_context import get_current_log
from modules.config import config
from modules.exceptions import GoogleMapsAPIError
from utils.infra_logging import Logging, _logger
from utils.helpers import validate_and_convert_coordinates
from utils.metrics import metrics


class GoogleMapsAPIService:
    """Google Maps API 服務類別，提供 API 呼叫功能"""
    
    def __init__(self):
        """初始化 Google Maps API 服務"""
        self.config = config  # 使用單例配置
        os.environ["ssl_verify"] = "False"
        self.client = GoogleMapsAPIClient()
        
        shared_log = get_current_log()
        self.log = shared_log if isinstance(shared_log, Logging) else Logging(
            mission_name="google_maps_api_service",
            log_uuid=str(uuid4()),
            flow_code="G01_google_maps"
        )
    
    def get_area_insights(
        self,
        latitude: str,
        longitude: str,
        scenario: POIScenarioEnum,
        radius: str = "700",
    ) -> Dict[str, Any]:
        """
        取得特定區域的洞察資料
        
        Args:
            latitude: 緯度
            longitude: 經度
            scenario: POI 情境類型
            radius: 搜尋半徑（公尺），預設 700
            
        Returns:
            Dict: 包含 count 和回應時間的字典
            
        Raises:
            GoogleMapsAPIError: API 呼叫失敗時拋出
        """
        start_time = datetime.now()
        
        try: 
            # 驗證座標；當無效時直接回傳 null
            if not validate_and_convert_coordinates(latitude, longitude):
                end_time = datetime.now()
                self.log.apilog(
                    uuid_request=self.log.log_uuid,
                    api_type="geo-data-resolver-api",
                    api_name="geo-data-resolver",
                    start_time=start_time,
                    end_time=end_time,
                    status_code="200",
                    status_detail="Skipped API call - coordinates_invalid",
                    retry=0,
                )
                return {"count": "null", "response_time_ms": 0}

            response, retry_count = self.client.get_places_aggregate(
                latitude=latitude,
                longitude=longitude,
                scenario=scenario,
                radius=radius
            )
            
            end_time = datetime.now()
            
            # Metrics: 計數成功的 API 呼叫
            metrics.inc_api_call()
            metrics.maybe_flush()
            
            self.log.apilog(
                uuid_request=self.log.log_uuid,
                api_type="geo-data-resolver-api",
                api_name="geo-data-resolver",
                start_time=start_time,
                end_time=end_time,
                status_code="200",
                status_detail=f"Success - Scenario: {scenario.value}, Count: {response.get('count', 0)}",
                retry=retry_count,
            )
            
            return response
            
        except Exception as e:
            end_time = datetime.now()
            status_code = getattr(e, 'status_code', 500)
            retry_count = getattr(e, 'retry_count', 0)
            
            # 仍然計數retry的 API 呼叫以反映 QPS 需求
            metrics.inc_api_call()
            metrics.maybe_flush()
            
            self.log.apilog(
                uuid_request=self.log.log_uuid,
                api_type="geo-data-resolver-api",
                api_name="geo-data-resolver",
                start_time=start_time,
                end_time=end_time,
                status_code=str(status_code),
                status_detail=str(e),
                retry=retry_count,
            )
            
            _logger.log_text(
                f"Failed to get area insights for location ({latitude}, {longitude}), "
                f"scenario {scenario.value}: {str(e)}",
                severity="Error"
            )
            raise GoogleMapsAPIError(f"Area insights retrieval failed: {str(e)}") from e
    
    def get_places_by_scenarios(
        self,
        latitude: float,
        longitude: float,
        scenarios: List[POIScenarioEnum],
        radius: float = 700,
    ) -> Dict[str, Any]:
        """
        批次取得多個情境的 POI 資料
        
        Args:
            latitude: 緯度
            longitude: 經度
            scenarios: POI 情境類型列表
            radius: 搜尋半徑（公尺），預設 700
            
        Returns:
            Dict: 包含各情境結果的字典，格式為 {scenario: {count, response_time_ms}}
        """
        results = {}
        errors = []
        
        for scenario in scenarios:
            try:
                result = self.get_area_insights(
                    latitude=latitude,
                    longitude=longitude,
                    scenario=scenario,
                    radius=radius
                )
                results[scenario.value] = result
                
            except Exception as e:
                error_msg = f"Scenario {scenario.value} failed: {str(e)}"
                errors.append(error_msg)
                _logger.log_text(error_msg, severity="Warning")
                # 繼續處理其他情境
                results[scenario.value] = {
                    "count": 0,
                    "error": str(e),
                    "response_time_ms": 0
                }
        
        # 如果所有情境都失敗，則拋出錯誤
        if len(errors) == len(scenarios):
            raise GoogleMapsAPIError(
                f"All scenarios failed. Errors: {'; '.join(errors)}"
            )
        
        return {
            "results": results,
            "total_scenarios": len(scenarios),
            "successful_scenarios": len(scenarios) - len(errors),
            "errors": errors if errors else None
        }
    
    def get_api_status(self) -> Dict[str, Any]:
        """
        取得 API 狀態資訊
        
        Returns:
            Dict: 包含 API 配置和狀態的字典
        """
        try:
            return {
                "status": "healthy",
                "base_url": self.client.base_url,
                "qpm_limit": self.client.qpm_limit,
                "max_retries": self.client.max_retries,
                "timeout": self.client.timeout,
                "min_interval": self.client.min_interval,
            }
        except Exception as e:
            _logger.log_text(f"Failed to get API status: {str(e)}", severity="Error")
            return {
                "status": "error",
                "error": str(e)
            }
