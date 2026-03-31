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

from modules.exceptions import GeoDataError


_logging_client = cloud_logging.Client()
_log_name = "geo-data-resolver"
_logger = _logging_client.logger(_log_name)

def get_config() -> 'Configuration':
    """
    提供一個全域、快取過的 Configuration 實例。
    """
    if not hasattr(get_config, "_instance"):
        get_config._instance = Configuration()
    return get_config._instance


class Configuration:
    """
    從 YAML 檔案和環境變數載入配置的類別。
    支援多環境配置，通過 GCP Project ID 自動選擇環境。
    """
    
    def __init__(self):
        """初始化配置管理器"""
        # 獲取當前 GCP 專案 ID
        self.project_id = self._get_project_id()
        
        # 載入 YAML 配置
        self.config_data = self._load_config_file()
        
        # 獲取環境特定配置
        self.env_config = self._get_environment_config()
        
        # 驗證必要配置
        self._validate_config()
    
    def _get_project_id(self) -> str:
        """獲取 GCP 專案 ID"""
        try:
            _, project_id = google.auth.default()
            if project_id:
                return project_id
            
        except Exception as e:
            _logger.log_text(f"Failed to get project ID: {e}", severity="WARNING")
            return "vn-loancloudmvp-data"
    
    def _load_config_file(self) -> dict:
        """載入 YAML 配置檔案"""
        config_path = Path(__file__).parent.parent / "config" / "config.yaml"
        
        try:
            with open(config_path, 'r', encoding='utf-8') as file:
                return yaml.safe_load(file)
        except FileNotFoundError:
            raise GeoDataError(f"Configuration file not found: {config_path}")
        except yaml.YAMLError as e:
            raise GeoDataError(f"Error parsing YAML configuration: {e}")
    
    def _get_environment_config(self) -> dict:
        """獲取環境特定配置"""
        if self.project_id in self.config_data:
            return self.config_data[self.project_id]
        else:
            _logger.log_text(f"No configuration found for project {self.project_id}, using default", severity="WARNING")
            return self.config_data.get("default", {})
    
    def _validate_config(self):
        """驗證必要的配置項目"""
        required_sections = ["gcp", "bigquery", "gcs", "pubsub"]
        
        for section in required_sections:
            if section not in self.env_config:
                _logger.log_text(f"Missing configuration section: {section}, using defaults", severity="WARNING")
    
    def get(self, key: str, default: Any = None) -> Any:
        """獲取配置值，支援點記法路徑"""
        keys = key.split('.')
        value = self.env_config
        
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
        
        return value
    
    # Google Maps API 配置屬性
    @property
    def google_maps_base_url(self) -> str:
        return self.get("google_maps_api.base_url", "https://places.googleapis.com")
    
    @property
    def google_maps_timeout(self) -> int:
        return self.get("google_maps_api.timeout", 30)
    
    @property
    def google_maps_max_retries(self) -> int:
        return self.get("google_maps_api.max_retries", 5)
    
    @property
    def google_maps_qpm_limit(self) -> int:
        return self.get("google_maps_api.qpm_limit", 1200)
    
    @property
    def google_maps_batch_size(self) -> int:
        return self.get("google_maps_api.batch_size", 100)
    
    @property
    def google_maps_proxies(self) -> Optional[dict]:
        val = self.get('google_maps_api.proxies', {})
        return val if isinstance(val, dict) else {}  
    
    @property
    def google_map_secret_version_name(self) -> Optional[str]:
        """
        取得 google map API Key 的 Secret Manager 版本名稱
        """
        return self.get('google_maps_api.secret_version_name')
      
    # BigQuery 配置屬性
    @property
    def raw_hes_dataset(self) -> str:
        return self.get("bigquery.raw_hes_dataset", "RAW_HES_DATASET")
    
    @property
    def raw_vmb_dataset(self) -> str:
        return self.get("bigquery.raw_vmb_dataset", "RAW_VMB_DATASET")
    
    @property
    def raw_edep_dataset(self) -> str:
        return self.get("bigquery.raw_edep_dataset", "RAW_EDEP_DATASET")
    
    @property
    def hes_customer_table(self) -> str:
        return self.get("bigquery.hes_customer_table", "CUSTOMER")
    
    @property
    def hes_application_table(self) -> str:
        return self.get("bigquery.hes_application_table", "APPLICATION")
    
    @property
    def vmb_apply_info_table(self) -> str:
        return self.get("bigquery.vmb_apply_info_table", "APPLY_INFO")
    
    @property
    def geo_table(self) -> str:
        return self.get("bigquery.geo_table", "GEO_DATA")
    
    @property
    def geo_failed_retry_table(self) -> str:
        return self.get("bigquery.geo_failed_retry_table", "GEO_DATA_FAILED_RETRY_LIST")
    
    # GCS 配置屬性
    @property
    def gcs_bucket_name(self) -> str:
        return self.get("gcs.bucket_name")
    
    @property
    def gcs_blob_path(self) -> str:
        return self.get("gcs.blob_path", "GOOGLEMAPS")
    
    # Pub/Sub 配置屬性
    @property
    def pubsub_project_id(self) -> str:
        return self.get("pubsub.project_id", self.project_id)
    
    @property
    def pubsub_batch_topic(self) -> str:
        return self.get("pubsub.batch_topic", "geo-data-resolver")
    
    @property
    def pubsub_geo_topic(self) -> str:
        return self.get("pubsub.geo_topic", "geo-data-resolver")

    @property
    def anonymization_pubsub_topic(self) -> str:
        return self.get("pubsub.anonymization_topic", "anonymization")


# 提供一個單例模式的 config 物件
config = get_config()
