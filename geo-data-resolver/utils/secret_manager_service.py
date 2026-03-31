"""
Google Cloud Secret Manager 服務模組

提供 Secret Manager 密鑰管理功能
"""

from google.cloud import secretmanager
from modules.config import config
from google.cloud import logging as cloud_logging

_logging_client = cloud_logging.Client()
_log_name = "custom-log"
_logger = _logging_client.logger(_log_name)

class SecretManagerService:
    """Google Cloud Secret Manager 服務類別"""
    
    def __init__(self):
        self._secret_client = None
    
    @property
    def secret_client(self) -> secretmanager.SecretManagerServiceClient:
        """取得 Secret Manager 客戶端"""
        if self._secret_client is None:
            self._secret_client = secretmanager.SecretManagerServiceClient()
        return self._secret_client

    def access_secret_version(self, version_name: str) -> str:
        """以 Secret 版本資源名稱讀取密鑰內容。

        Args:
            version_name: Secret 版本完整資源名稱，例如
            "projects/<PROJECT_NUMBER_OR_ID>/secrets/<SECRET_ID>/versions/<VERSION|latest>"

        Returns:
            str: Secret payload 字串內容

        Raises:
            Exception: 當讀取失敗或 version_name 無效時
        """
        if not version_name:
            raise ValueError("Secret version name is required")
        try:
            response = self.secret_client.access_secret_version(request={"name": version_name})
            secret_value = response.payload.data.decode("utf-8")
            return secret_value
        except Exception as e:
            raise Exception(f"Failed to access secret version '{version_name}': {e}")

    def get_api_key(self) -> str:
        """取得 Google Map API Key

        Returns:
            str: API Key

        Raises:
            Exception: 若無法取得有效的 API Key
        """
        version_name = config.google_map_secret_version_name
        if version_name:
            try:
                api_key = self.access_secret_version(version_name)
                if api_key:
                    return api_key
            except Exception as e:
                _logger.log_text(f"Unable to access secret key: {e}", severity="Warning")

        raise Exception("Google Map API key not configured. Provide secret_version_name or default_api_key in config.")