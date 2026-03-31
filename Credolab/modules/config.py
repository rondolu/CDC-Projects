"""
配置管理模組

此模組負責從 YAML 檔案、環境變數和 GCP Secret Manager 載入、
驗證和管理應用程式的所有配置。
"""
import os
import yaml
import google.auth
from pathlib import Path
from typing import Any, Optional
from google.cloud import logging as cloud_logging

from modules.exceptions import CredolabError


_logging_client = cloud_logging.Client()
_log_name = "custom-log"
_logger = _logging_client.logger(_log_name)

def get_config() -> 'Configuration':
    """
    提供一個全域、快取過的 Configuration 實例。
    """
    return Configuration()


class Configuration:
    """
    應用程式配置管理類別。
    
    負責從多個來源載入設定值，並提供一個統一的介面來存取這些值。
    優先順序：環境變數 > YAML 檔案 > 預設值。

    """
    
    def __init__(self, config_path: Optional[str] = None):
        """
        初始化配置管理。
        
        Args:
            config_path: YAML 配置檔案的路徑。如果為 None，則使用預設路徑。
        """
        self.config_path = config_path or Path(__file__).parent.parent / "config" / "config.yaml"
        self._root = self._load_yaml_config()
        self._active_env_name = None  # 例如：vn-loancloudmvp-data / ovs-lx-vdo-01-ut-6869fc / ovs-lx-vdo-01-prod-d27767
        self._active: dict = {}
        self._select_active_environment()
        self._secret_client = None
        # _logger.log_text(f"Configuration loaded from {self.config_path} (active env: {self._active_env_name})", severity="Info")

    # --------------------
    # 載入與環境選擇
    # --------------------
    def _load_yaml_config(self) -> dict:
        """
        載入 YAML 配置檔案。
        """
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f) or {}
        except FileNotFoundError:
            # logging.warning(f"Config file not found at {self.config_path}. Using defaults.")
            _logger.log_text(f"Config file not found at {self.config_path}. Using defaults.", severity="Warning")
            return {}
        except yaml.YAMLError as e:
            raise CredolabError(f"Error parsing YAML config file: {e}")

    def _select_active_environment(self) -> None:
        """
        以 project_id 作為環境鍵選擇配置（僅此一途）。
        """
        root = self._root or {}

        try:
            _, env_project = google.auth.default()
        except Exception as e:
            raise CredolabError(
                f"無法透過 ADC 取得 project id：{e}。"
            )

        if env_project not in root:
            available = ', '.join([k for k, v in root.items() if isinstance(v, dict) and k != 'default'])
            raise CredolabError(
                f"找不到對應環境 '{env_project}' 的設定於 config.yaml。可用環境：[{available}]。"
            )

        self._active_env_name = env_project
        self._active = root[env_project]

    # --------------------
    # 存取輔助
    # --------------------
    def _get(self, key_path: str, default: Any = None) -> Any:
        """
        從環境變數或配置檔案中取得設定值（使用當前 active 環境）。
        
        Args:
            key_path: 點分隔的鍵路徑 (e.g., 'gcp.project_id')。
            default: 如果找不到鍵，則返回的預設值。
            
        Returns:
            設定值。
        """
        # 環境變數優先（GLOBAL 覆蓋）
        env_key = key_path.upper().replace('.', '_')
        value = os.environ.get(env_key)
        if value is not None:
            return value

        # 依序走訪 active (prokect環境)配置
        val = self._active
        for key in key_path.split('.'):
            if isinstance(val, dict) and key in val:
                val = val[key]
            else:
                return default
        return val
    
    # --------------------
    # GCP
    # --------------------
    @property
    def gcp_project_id(self) -> str:
        return self._get('gcp.project_id')
        
    @property
    def project_id(self) -> str:
        """舊名稱的別名，向後相容性用法 (alias for gcp_project_id)"""
        return self.gcp_project_id
        
    @property 
    def gcp_credentials(self) -> Optional[Any]:
        """如可用則回傳 GCP 憑證。"""
        # 可以實作為回傳 service account 憑證
        # 目前回傳 None 以使用預設認證
        return None

    # --------------------
    # BigQuery
    # --------------------
    @property
    def bq_log_dataset(self) -> str:
        return self._get('bigquery.log_dataset', 'LOG_DATASET')
    
    @property
    def bq_api_dataset(self) -> str:
        return self._get('bigquery.api_dataset', 'API_DATASET')

    @property
    def bq_flow_log_table(self) -> str:
        return self._get('bigquery.flow_log_table', 'FLOW_LOG')

    @property
    def bq_api_log_table(self) -> str:
        return self._get('bigquery.api_log_table', 'API_LOG')

    @property
    def bq_raw_edep_dataset(self) -> str:
        return self._get('bigquery.raw_edep_dataset')

    @property
    def bq_credolab_table_android(self) -> str:
        """取得完整的 Android Credolab 表格 ID"""
        dataset = self.bq_raw_edep_dataset
        table = self._get('bigquery.credolab_android_table', 'CREDOLAB_DATA_ANDROID')
        return f"{self.gcp_project_id}.{dataset}.{table}"

    @property
    def bq_credolab_table_ios(self) -> str:
        """取得完整的 iOS Credolab 表格 ID"""
        dataset = self.bq_raw_edep_dataset
        table = self._get('bigquery.credolab_ios_table', 'CREDOLAB_DATA_iOS')
        return f"{self.gcp_project_id}.{dataset}.{table}"
        
    @property
    def bq_credolab_failed_retry_table(self) -> str:
        """取得完整的失敗重試表格 ID"""
        dataset = self.bq_raw_edep_dataset
        table = self._get('bigquery.credolab_failed_retry_table', 'CREDOLAB_FAILED_RETRY_LIST')
        return f"{self.gcp_project_id}.{dataset}.{table}"

    # --------------------
    # Credolab API
    # --------------------
    @property
    def credolab_base_url(self) -> str:
        return self._get('credolab_api.base_url', 'https://api.credolab.com')

    @property
    def credolab_proxies(self) -> dict:
        """取得 Credolab API 用的 proxies 設定 (dict)。若未設定則回傳空 dict。

        YAML 範例：
        credolab_api:
            proxies:
                https: "http://10.171.21.2:8080"
        """
        val = self._get('credolab_api.proxies', {})
        return val if isinstance(val, dict) else {}

    @property
    def credolab_secret_version_name(self) -> Optional[str]:
        """
        取得 Credolab API Key 的 Secret Manager 版本名稱
        """
        return self._get('credolab_api.secret_version_name')
    
    @property
    def credolab_default_api_key(self) -> str:
        """
        取得預設的 Credolab API Key（用於開發環境）
        """
        return self._get('credolab_api.default_api_key', '')

    @property
    def credolab_timeout(self) -> int:
        return int(self._get('credolab_api.timeout', 60))

    @property
    def credolab_max_retries(self) -> int:
        return int(self._get('credolab_api.max_retries', 3))

    @property
    def credolab_qpm_limit(self) -> int:
        """
        每分鐘查詢次數 (queries per minute) 的設定值。
        """
        return int(self._get('credolab_api.qpm_limit', 50))
        
    @property
    def credolab_batch_size(self) -> int:
        return int(self._get('credolab_api.batch_size', 50))

    @property
    def credolab_api_codes(self) -> list:
        return self._get('credolab_api.api_codes', [])
        
    @property
    def ssl_verify(self) -> bool:
        return self._get('credolab_api.ssl_verify', True)

    # --------------------
    # GCS
    # --------------------        
    @property
    def gcs_bucket_name(self) -> str:
        """取得 GCS 儲存桶名稱"""
        return self._get('gcs.bucket_name', 'rawdata_api')
    
    @property
    def gcs_blob_path(self) -> str:
        """取得 GCS blob 路徑"""
        return self._get('gcs.blob_path', 'EDEP/CREDOLAB')

    # --------------------
    # Pub/Sub
    # --------------------
    @property
    def pubsub_project_id(self) -> str:
        return self._get('pubsub.project_id', self.project_id)
    
    @property
    def pubsub_credolab_topic(self) -> str:
        return self._get('pubsub.credolab_topic', 'credolab')
    
    @property
    def pubsub_anonymization_topic(self) -> str:
        return self._get('pubsub.anonymization_topic', 'anonymization-trigger')
    
    @property
    def pubsub_batch_topic(self) -> str:
        return self._get('pubsub.batch_topic', 'credolab-batch-processing')


# 提供一個單例模式的 config 物件
config = get_config()
