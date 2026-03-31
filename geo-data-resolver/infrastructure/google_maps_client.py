"""
Google Maps API 客戶端

提供與 Google Maps Area Insights API 的整合，包括認證、請求管理、
錯誤處理和重試機制。
"""

import os
import time
import requests
from typing import Dict, Any, List, Optional, Tuple

from modules.config import config
from utils.secret_manager_service import SecretManagerService
from modules.exceptions import (
    GoogleMapsAPIError,
    GoogleMapsAPITimeoutError,
)
from models.google_maps_models import (
    POIScenarioEnum,
)
from utils.infra_logging import _logger


class GoogleMapsAPIClient:
    """
    Google Maps API 客戶端

    提供與 Google Maps Area Insights API 的整合，包括認證、請求管理、
    錯誤處理和重試機制。
    """

    def __init__(self):
        """初始化 Google Maps API 客戶端"""
        self.base_url = config.google_maps_base_url
        self.secret_service = SecretManagerService()
        self.api_key = self.secret_service.get_api_key()
        self.timeout = config.google_maps_timeout
        self.max_retries = config.google_maps_max_retries
        self.qpm_limit = config.google_maps_qpm_limit
        self.proxies = config.google_maps_proxies
        self.ssl_verify = os.getenv("ssl_verify", "true").lower() == "true"

        self.last_request_time = 0.0
        self.min_interval = 60.0 / self.qpm_limit if self.qpm_limit and self.qpm_limit > 0 else 0.0

        self.session = self._setup_session()

    def _setup_session(self) -> requests.Session:
        """設定 HTTP 會話。"""
        session = requests.Session()
        session.headers.update({
            "Content-Type": "application/json",
            "X-Goog-Api-Key": self.api_key,
        })
        return session

    def _rate_limit(self) -> None:
        """實施 QPM 速率限制。"""
        if not self.min_interval:
            return
        now = time.time()
        delta = now - self.last_request_time
        if delta < self.min_interval:
            time.sleep(self.min_interval - delta)
        self.last_request_time = time.time()

    def get_places_aggregate(
        self,
        latitude: float,
        longitude: float,
        scenario: POIScenarioEnum,
        radius: float = 700,
    ) -> Tuple[Dict[str, Any], int]:
        """
        呼叫 Google Maps Area Insights computeInsights，使用該情境的 includedTypes 清單一次送出，
        回傳該情境的總數（服務端已會對 includedTypes 清單加總）。
        """

        included_types = self._get_poi_types_for_scenario(scenario) or ["establishment"]
        api_url = f"{self.base_url}/v1:computeInsights"
        payload = {
            "insights": ["INSIGHT_COUNT"],
            "filter": {
                "locationFilter": {
                    "circle": {
                        "latLng": {"latitude": latitude, "longitude": longitude},
                        "radius": radius,
                    }
                },
                "typeFilter": {"includedTypes": included_types},
                "operatingStatus": ["OPERATING_STATUS_OPERATIONAL"],
            },
        }

        retry_count = 0
        last_exception = None

        for attempt in range(self.max_retries + 1):
            # 速率限制
            self._rate_limit()
            
            start_ts = time.time()
            try:
                response = self.session.post(
                    api_url,
                    json=payload,
                    timeout=self.timeout,
                    # proxies=self.proxies,
                    verify=self.ssl_verify,
                )
                elapsed_ms = (time.time() - start_ts) * 1000.0

                if response.status_code == 200:
                    data = response.json() or {}
                    count_val = None
                    if isinstance(data, dict):
                        if "count" in data:
                            count_val = data.get("count")
                        elif "insights" in data:
                            try:
                                for item in data.get("insights", []) or []:
                                    if isinstance(item, dict) and item.get("name") in ("INSIGHT_COUNT", "count"):
                                        count_val = item.get("count") or item.get("value")
                                        break
                            except Exception:
                                pass
                    try:
                        total_int = int(count_val) if count_val is not None else 0
                    except Exception:
                        total_int = 0
                    return {"count": str(total_int), "response_time_ms": elapsed_ms}, retry_count
                
                # 檢查是否為可重試的錯誤
                is_retryable_error = response.status_code in [429, 500, 502, 503, 504]
                
                if is_retryable_error and attempt < self.max_retries:
                    retry_count += 1
                    sleep_time = (2 ** attempt) + (time.time() % 1)
                    time.sleep(sleep_time)
                    continue

                else:
                    raise GoogleMapsAPIError(
                        f"API returned status {response.status_code}: {response.text}",
                        status_code=response.status_code,
                    )
            except requests.exceptions.Timeout:
                retry_count += 1
                last_exception = GoogleMapsAPITimeoutError("Request timed out")
                if attempt < self.max_retries:
                    continue
                else:
                    raise last_exception
            except requests.exceptions.RequestException as e:
                retry_count += 1
                last_exception = GoogleMapsAPIError(f"Network error: {e}")
                if attempt < self.max_retries:
                    continue
                else:
                    raise last_exception

        if last_exception:
            raise last_exception
        else:
            raise GoogleMapsAPIError("Request failed after all retries")


    def _get_poi_types_for_scenario(self, scenario: POIScenarioEnum) -> List[str]:
        """根據情境獲取對應的 POI 類型"""
        poi_scenarios = config.get("google_maps_api.poi_scenarios", {})
        mapping = {
            POIScenarioEnum.CORPORATE_FINANCE: poi_scenarios.get("corporate_finance"),
            POIScenarioEnum.RESIDENTIAL: poi_scenarios.get("residential"),
            POIScenarioEnum.COMMERCIAL: poi_scenarios.get("commercial"),
        }
        return mapping.get(scenario, ["establishment"]) or ["establishment"]

    def _process_places_response(self, response_data: Dict[str, Any]) -> Dict[str, Any]:
        try:
            insights = response_data.get("insights", []) if isinstance(response_data, dict) else []
            for item in insights:
                if isinstance(item, dict) and item.get("name") in ("INSIGHT_COUNT", "count"):
                    count_val = item.get("count") or item.get("value")

                    return {"count": count_val}
        except Exception as e:
            _logger.log_text(f"Response parsing warning: {e}", severity="Warning")
        return {"count": 0}

    