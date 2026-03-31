"""
Credolab API 客戶端服務

此模組提供 Credolab API 的整合功能，包括：
1. API 呼叫管理（基於 requests）
2. 自動重試機制（使用 urllib3.util.retry）
3. QPM（每分鐘查詢率）限制
4. 標準化的錯誤處理與例外
"""
import time
import os
import requests
import logging
from typing import Dict, List, Any, Optional, Tuple, Callable
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from urllib3.exceptions import MaxRetryError

from modules.config import config
from utils.secret_services import SecretManagerService
from modules.exceptions import CredolabAPIError


class RetryWithRateLimit(Retry):
    """
    自訂的 Retry 類，在每次重試的休眠前強制執行速率限制。
    """
    def __init__(self, *args, rate_limit_func: Optional[Callable] = None, **kwargs):
        """
        Args:
            rate_limit_func: 在每次重試前要呼叫的速率限制函數
        """
        self.rate_limit_func = rate_limit_func
        super().__init__(*args, **kwargs)

    def sleep(self, response=None):
        """
        在執行原始休眠邏輯前，先呼叫速率限制函數。
        這是針對 urllib3 2.x 的調整。
        """
        if callable(self.rate_limit_func):
            try:
                self.rate_limit_func()
            except Exception:
                # 避免速率限制函數本身阻斷重試機制
                logging.exception("rate_limit_func failed during RetryWithRateLimit.sleep")
        
        # 呼叫父類別的 sleep 方法，它會處理所有休眠邏輯，包括 backoff
        super().sleep(response)


class CredolabAPIClient:
    """
    Credolab API 客戶端
    
    提供與 Credolab API 的完整整合，包括認證、請求管理、
    錯誤處理和重試機制。
    """
    
    def __init__(self):
        """初始化 Credolab API 客戶端"""
        self.base_url = config.credolab_base_url
        self._secret_service = SecretManagerService()
        self.api_key = self._secret_service.get_credolab_api_key()
        self.timeout = config.credolab_timeout
        self.max_retries = config.credolab_max_retries
        self.qpm_limit = config.credolab_qpm_limit
        self.ssl_verify = os.getenv("ssl_verify", "false").lower() == "true"
        self.proxies = config.credolab_proxies 

        self.last_request_time = 0
        self.min_interval = 60.0 / self.qpm_limit if self.qpm_limit > 0 else 0

        self.session = self._setup_session()

    def _setup_session(self) -> requests.Session:
        """設定 HTTP 會話、重試策略和 SSL Context。
        
        使用自訂的 RetryWithRateLimit 策略，確保所有自動重試都會經過 _rate_limit() QPM 控制。
        """
        session = requests.Session()
        
        # 使用自訂的重試策略，將 _rate_limit 方法傳入
        retry_strategy = RetryWithRateLimit(
            rate_limit_func=self._rate_limit,
            total=self.max_retries,
            status_forcelist=[500, 502, 503, 504],
            backoff_factor=1
        )
        
        adapter = HTTPAdapter(max_retries=retry_strategy)

        session.mount("https://", adapter)
        session.mount("http://", adapter)
        
        session.headers.update({
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        })
        
        return session

    def _rate_limit(self):
        """實施 QPM (每分鐘查詢率) 速率限制"""
        if self.min_interval == 0:
            return
        elapsed = time.time() - self.last_request_time
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)
        self.last_request_time = time.time()

    def get_insights(self, reference_id: str, api_codes: Optional[List[str]] = None) -> Tuple[Dict[str, Any], int]:
        """
        取得 Credolab 洞察資料。
        Args:
            reference_id: 參考 ID。
            api_codes: 要查詢的 API 代碼列表。
        Returns:
            Tuple[Dict[str, Any], int]: (API 回應的 JSON 資料, 重試次數)

        Raises:
            CredolabAPIError: 當請求最終失敗時（例如，達到最大重試次數，或發生非重試的錯誤）。
        """
        url = f"{self.base_url}/api/insights/v1/{reference_id}"
        params = [('codes', code) for code in api_codes] if api_codes else []
        
        retry_count = 0
        
        try:
            self._rate_limit()
            
            resp = self.session.get(
                url,
                params=params,
                timeout=self.timeout,
                proxies=self.proxies,
                verify=self.ssl_verify
            )
            
            if resp.raw and hasattr(resp.raw, 'retries') and resp.raw.retries:
                retry_count = self.max_retries - resp.raw.retries.total

            # 檢查非 2xx 狀態碼並拋出異常
            resp.raise_for_status()

            try:
                data = resp.json()
            except ValueError:
                raise CredolabAPIError(f"Credolab response is not valid JSON. Full response: {resp.text}", status_code=502)

            if not isinstance(data, dict) or not data:
                raise CredolabAPIError("Credolab response is empty or not an object", status_code=502)

            return data, retry_count

        except MaxRetryError as e:
            status_code = e.reason.status if hasattr(e.reason, 'status') else 504
            raise CredolabAPIError(
                f"API call failed after {self.max_retries} retries: {e.reason}",
                status_code=status_code
            ) from e

        except requests.HTTPError as e:
            # 處理非重試的 HTTP 錯誤（例如 400, 401, 404）
            status_code = e.response.status_code
            resp_text_snippet = e.response.text[:500]
            raise CredolabAPIError(
                f"HTTP {status_code}: {resp_text_snippet}",
                status_code=status_code
            ) from e
            
        except (requests.Timeout, requests.ConnectionError) as e:
            raise CredolabAPIError(
                f"Unhandled network error: {str(e)}",
                status_code=504
            ) from e

    def get_api_status(self) -> Dict[str, Any]:
        """取得 API 客戶端的狀態資訊。"""
        return {
            "base_url": self.base_url,
            "qpm_limit": self.qpm_limit,
            "timeout": self.timeout,
            "max_retries": self.max_retries,
            "available_api_codes": config.credolab_api_codes,
            "proxies": self.proxies
        }