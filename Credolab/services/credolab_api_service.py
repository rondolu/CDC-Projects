
"""
Credolab API Service 模組
提供 Credolab API 呼叫的高層級介面，整合速率限制和錯誤處理
"""

import logging
import os
from typing import Dict, Any, Optional
from datetime import datetime

from infrastructure.credolab_client import CredolabAPIClient
from uuid import uuid4
from utils.request_context import get_current_log
from modules.config import config
from modules.exceptions import CredolabError
from utils.infra_logging import Logging, _logger
from utils.metrics import metrics


class CredolabAPIService:
    """Credolab API 服務類別，提供 API 呼叫功能"""
    
    def __init__(self):
        self.config = config  # 使用單例配置
        os.environ["ssl_verify"] = "False"
        self.client = CredolabAPIClient()
        # Use shared logger if available; else create standardized one
        shared_log = get_current_log()
        self.log = shared_log if isinstance(shared_log, Logging) else Logging(
            mission_name="credolab_api_service", log_uuid=str(uuid4()), flow_code="E05_credolab"
        )
    
    def get_credolab_insights(self, reference_number: str, api_codes: Optional[list] = None) -> Dict[str, Any]:
        """
        根據參考號碼取得 Credolab 洞察資料

        Args:
            reference_number: 參考號碼
            api_codes: 可選的 API 代碼列表，如未提供則使用配置中的默認值
            
        Returns:
            Dict: 洞察資料
        """
        # 使用配置中的默認 API codes 如果未提供
        if api_codes is None:
            api_codes = self.config.credolab_api_codes
            
        start_time = datetime.now()
        
        try:
            # 呼叫 API
            response, retry_count = self.client.get_insights(reference_number, api_codes)
            end_time = datetime.now()
            # Metrics: count successful API call
            metrics.inc_api_call()
            metrics.maybe_flush()
            
            # 記錄到 API Log via unified logger
            self.log.apilog(
                uuid_request=self.log.log_uuid,
                api_type="credolab_api",
                api_name="CREDOLAB",
                start_time=start_time,
                end_time=end_time,
                status_code="200",
                status_detail="Success",
                retry=retry_count,
            )
            
            return response
            
        except Exception as e:
            end_time = datetime.now()
            status_code = getattr(e, 'status_code', 500)
            retry_count = getattr(e, 'retry_count', 0)
            # Metrics: still count attempted API call to reflect QPS demand
            metrics.inc_api_call()
            metrics.maybe_flush()
            
            # 記錄到 API Log via unified logger
            self.log.apilog(
                uuid_request=self.log.log_uuid,
                api_type="credolab_api",
                api_name="CREDOLAB",
                start_time=start_time,
                end_time=end_time,
                status_code=str(status_code),
                status_detail=str(e),
                retry=retry_count,
            )
            
            raise CredolabError(f"Insights retrieval failed: {str(e)}") from e

    def get_api_status(self) -> Dict[str, Any]:
        """
        取得 API 狀態資訊，會代理到底層的 client.get_api_status
        """
        try:
            return self.client.get_api_status()
        except Exception as e:
            _logger.log_text(f"Failed to get API status: {str(e)}", severity="Info")
            return {"status": "error", "error": str(e)}
