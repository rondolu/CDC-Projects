"""
Google Cloud Storage 服務模組

提供 GCS 檔案操作的完整功能
"""

import json
from typing import Union, Optional, Dict
from google.cloud import storage
from modules.config import config
from utils.infra_logging import Logging


class GCSService:
    """Google Cloud Storage 服務類別"""
    
    def __init__(self):
        self._storage_client = None
    
    @property
    def storage_client(self) -> storage.Client:
        """取得 Storage 客戶端"""
        if self._storage_client is None:
            self._storage_client = storage.Client(project=config.project_id)
        return self._storage_client
    
    def download_from_gcs(self, blob_name: str, bucket_name: Optional[str] = None) -> str:
        """從 Google Cloud Storage 下載資料
        
        Args:
            blob_name: Blob 名稱
            bucket_name: 儲存桶名稱，若為 None 則使用預設
            
        Returns:
            str: 檔案內容
            
        Raises:
            Exception: 當下載失敗時
        """
        if bucket_name is None:
            bucket_name = config.gcs_bucket_name
        
        try:
            bucket = self.storage_client.bucket(bucket_name)
            blob = bucket.blob(blob_name)
            return blob.download_as_text()
        except Exception as e:
            raise Exception(f"GCS 下載失敗: {str(e)}")
    
    def read_file_from_gcs(self, bucket_name: str, file_name: str) -> str:
        """從 GCS 讀取檔案內容
        
        Args:
            bucket_name: 儲存桶名稱
            file_name: 檔案名稱
            
        Returns:
            str: 檔案內容
        """
        return self.download_from_gcs(file_name, bucket_name)
    
    def batch_upload_to_gcs(self, file_list: list, bucket_name: Optional[str] = None) -> list:
        """批次上傳多個檔案到 Google Cloud Storage
        
        Args:
            file_list: 檔案列表，每個元素為 dict，包含:
                - blob_name: str, Blob 名稱 (檔案路徑)
                - data: Union[str, bytes, Dict], 要上傳的資料
                - content_type: str, 內容類型 (預設 "application/json")
            bucket_name: 儲存桶名稱，若為 None 則使用預設
            
        Returns:
            list: 上傳檔案的 GCS URI 列表
            
        Raises:
            Exception: 當上傳失敗時
        """
        if bucket_name is None:
            bucket_name = config.gcs_bucket_name
        
        try:
            bucket = self.storage_client.bucket(bucket_name)
            uploaded_uris = []
            
            for file_info in file_list:
                blob_name = file_info.get('blob_name')
                data = file_info.get('data')
                content_type = file_info.get('content_type', 'application/json')
                
                blob = bucket.blob(blob_name)
                
                # 根據資料類型處理上傳
                if isinstance(data, dict):
                    blob.upload_from_string(json.dumps(data, ensure_ascii=False, default=str), content_type=content_type)
                elif isinstance(data, str):
                    blob.upload_from_string(data, content_type=content_type)
                elif isinstance(data, bytes):
                    blob.upload_from_string(data, content_type=content_type)
                else:
                    raise Exception(f"不支援的資料類型: {type(data)}")
                
                uploaded_uris.append(f"gs://{bucket_name}/{blob_name}")
            
            return uploaded_uris
            
        except Exception as e:
            raise Exception(f"GCS 批次上傳失敗: {str(e)}")