"""
BigQuery Service 模組
提供 BigQuery 數據操作的高層級介面，整合配置管理和錯誤處理
"""

from typing import List, Dict, Any, Optional, cast
from datetime import datetime, timezone, date
import re
import json
from google.cloud import bigquery
from google.cloud.exceptions import GoogleCloudError

from modules.config import config
from modules.exceptions import CredolabError, DataValidationError
from utils.infra_logging import _logger
from utils.metrics import metrics


class BigQueryService:
    """BigQuery 服務類別，提供資料查詢和操作功能"""
    
    def __init__(self):
        self.config = config  # 使用單例配置
        self.client: Optional[bigquery.Client] = None
        self._initialize_client()
    
    def _initialize_client(self):
        """初始化 BigQuery 客戶端"""
        try:
            creds = self.config.gcp_credentials
            if creds:  # 只有在取得憑證時才傳入，避免型別不符警告
                self.client = bigquery.Client(
                    project=self.config.project_id,
                    credentials=cast(Any, creds)
                )
            else:
                self.client = bigquery.Client(project=self.config.project_id)
        except Exception as e:
            _logger.log_text(f"Failed to initialize BigQuery client: {str(e)}", severity="Error")
            raise CredolabError(f"BigQuery initialization failed: {str(e)}")
    
    def _prepare_query_parameters(self, query_params: Dict[str, Any]) -> List[bigquery.ScalarQueryParameter]:
        """準備查詢參數，根據參數值類型自動設定對應的參數型別

        Args:
            query_params: 參數字典

        Returns:
            List[bigquery.ScalarQueryParameter]: BigQuery 參數列表
        """
        parameters = []
        
        date_like_regex = re.compile(r"^\d{4}-\d{2}-\d{2}$")  # YYYY-MM-DD

        for param_name, param_value in query_params.items():
            # Explicit DATE type support (datetime.date)
            if isinstance(param_value, date) and not isinstance(param_value, datetime):
                parameters.append(bigquery.ScalarQueryParameter(param_name, "DATE", param_value))
            elif isinstance(param_value, str):
                # Heuristic: if looks like YYYY-MM-DD (e.g., partition_date), send as DATE
                if date_like_regex.match(param_value):
                    parameters.append(bigquery.ScalarQueryParameter(param_name, "DATE", param_value))
                else:
                    parameters.append(bigquery.ScalarQueryParameter(param_name, "STRING", param_value))
            elif isinstance(param_value, int):
                parameters.append(bigquery.ScalarQueryParameter(param_name, "INT64", param_value))
            elif isinstance(param_value, float):
                parameters.append(bigquery.ScalarQueryParameter(param_name, "FLOAT64", param_value))
            elif isinstance(param_value, bool):
                parameters.append(bigquery.ScalarQueryParameter(param_name, "BOOL", param_value))
            elif isinstance(param_value, datetime):
                parameters.append(bigquery.ScalarQueryParameter(param_name, "DATETIME", param_value))
            elif param_value is None:
                # NULL 值，使用 STRING 類型
                parameters.append(bigquery.ScalarQueryParameter(param_name, "STRING", None))
            else:
                # 對於其他類型，轉換為字串
                parameters.append(bigquery.ScalarQueryParameter(param_name, "STRING", str(param_value)))
                
        return parameters
    
    def execute_query(
        self, 
        query: str, 
        query_params: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        執行 BigQuery 查詢

        Args:
            query: SQL 查詢字串
            query_params: 查詢參數字典

        Returns:
            List[Dict]: 查詢結果列表
        """
        try:
            if self.client is None:
                raise CredolabError("BigQuery client not initialized")
            job_config = bigquery.QueryJobConfig()

            if query_params:
                try:
                    print("Query Parameters:", json.dumps(query_params, ensure_ascii=False, default=str))
                except Exception as e:
                    _logger.log_text(f"Get Query Parameters Error: {e}", severity="Error")

            if query_params:
                job_config.query_parameters = self._prepare_query_parameters(query_params)
                
            query_job = self.client.query(query, job_config=job_config)
            results = query_job.result()

            # 轉換結果為字典列表
            result_list = []
            for row in results:
                result_list.append(dict(row))

            return result_list
            
        except GoogleCloudError as e:
            _logger.log_text(f"BigQuery query error: {str(e)}", severity="Error")
            raise CredolabError(f"BigQuery query failed: {str(e)}")
        except Exception as e:
            _logger.log_text(f"Unexpected error in execute_query: {str(e)}", severity="Error")
            raise CredolabError(f"Query execution failed: {str(e)}")
    
    def insert_rows(
        self, 
        table_id: str, 
        rows: List[Dict[str, Any]]
    ) -> bool:
        """
        插入資料到 BigQuery 表格
        
        Args:
            table_id: 完整的表格 ID (project.dataset.table)
            rows: 要插入的資料列表

        Returns:
            bool: 插入是否成功
        """
        try:
            if self.client is None:
                raise CredolabError("BigQuery client not initialized")
            table_ref = self.client.get_table(table_id)
            errors = self.client.insert_rows_json(table_ref, rows)
            
            if errors:
                error_msg = f"Failed to insert rows: {errors}"
                _logger.log_text(f"Failed to insert rows: {errors}", severity="Error")
                raise CredolabError(error_msg)
            
            print(f"Successfully inserted {len(rows)} rows into {table_id}")
            # Metrics: count successful BQ writes
            metrics.inc_bq_write(len(rows))
            metrics.maybe_flush()
            return True
            
        except GoogleCloudError as e:
            _logger.log_text(f"BigQuery insert error: {str(e)}", severity="Error")
            raise CredolabError(f"Failed to insert rows: {str(e)}")
        except Exception as e:
            _logger.log_text(f"Unexpected error in insert_rows: {str(e)}", severity="Error")
            raise CredolabError(f"Insert operation failed: {str(e)}")
    
    def run_sql_file(self, sql_path: str, query_params: Optional[Dict[str, Any]] = None) -> None:
        """讀取並執行 SQL 檔案（主要用於 RAW -> TRANS 的搬運）。

        - 如果傳入相對路徑或僅檔名，會到專案 sql/ 目錄尋找該檔案。

        Args:
            sql_path: 檔名或絕對路徑
            query_params: 可選；若缺 partition_date 會補。
        """
        try:
            from pathlib import Path
            path = Path(sql_path)
            if not path.is_absolute():
                path = Path(__file__).parent.parent / 'sql' / path.name
            if not path.exists():
                raise CredolabError(f"SQL file not found: {path}")

            sql_text = path.read_text(encoding='utf-8')
            if query_params is None:
                query_params = {}
            if 'partition_date' not in query_params:
                query_params['partition_date'] = datetime.now(timezone.utc).strftime('%Y-%m-%d')

            self.execute_query(sql_text, query_params)
            _logger.log_text(f"Executed SQL file: {path.name} params={query_params}", severity="Info")
        except Exception as e:
            raise CredolabError(f"Failed to run sql file {sql_path}: {e}")
    

    def insert_failed_record(self, record: Dict[str, Any], status_code: str, error_message: str):
        """
        插入 API 呼叫失敗的紀錄到 CREDOLAB_FAILED_RETRY_LIST
        
        Args:
            record: 包含失敗記錄資訊的字典 (通常是 VMB record)
            status_code: HTTP 狀態碼 (如 "400", "504", "204")
            error_message: API 呼叫失敗的錯誤訊息
        """
        try:
            if self.client is None:
                raise CredolabError("BigQuery client not initialized")

            table_id = self.config.bq_credolab_failed_retry_table
            
            # 根據 schema 準備 row
            failed_row = {
                "uuid": record.get("uuid"),
                "cuid": record.get("cuid") or record.get("user_id"),
                "reference_id": record.get("reference_id") or record.get("referenceNumber"),
                "series_number": record.get("series_number"),
                "device_os": record.get("device_os") or record.get("device_type"),
                "api_payload_message": json.dumps(record, ensure_ascii=False, default=str), # 儲存整個 payload 為 JSON
                "api_status": status_code,  # 儲存 HTTP 狀態碼
                "BQ_UPDATED_TIME": datetime.now().isoformat(),
                "PARTITION_DATE": datetime.now().strftime('%Y-%m-%d')
            }
            
            self.insert_rows(table_id, [failed_row])

        except Exception as e:
            # 如果連寫入失敗紀錄都失敗，只記錄日誌，避免無限循環或中斷主流程
            _logger.log_text(f"CRITICAL: Failed to insert failed API call record to BigQuery: {str(e)}", severity="Warning")
