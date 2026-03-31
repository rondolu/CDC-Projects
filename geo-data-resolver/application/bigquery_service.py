"""
BigQuery Service 模組
- 檢查/建立資料集與資料表
- 查詢與插入
- 紀錄失敗清單
"""

from __future__ import annotations

from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
import json

from google.cloud import bigquery

from modules.config import config
from utils.infra_logging import _logger


class BigQueryService:
    def __init__(self) -> None:
        self.config = config
        self.client = bigquery.Client(project=self.config.project_id)
        # Use plain dataset/table names and build fully-qualified IDs via helper
        self.dataset_id = self.config.raw_edep_dataset
        self.raw_table = self.config.geo_table
        self.failed_retry_table = self.config.geo_failed_retry_table

    def _full_table_id(self, table_name: str) -> str:
        """生成完整的表格 ID (project.dataset.table)"""
        return f"{self.config.project_id}.{self.dataset_id}.{table_name}"

    def insert_rows(self, rows: List[Dict[str, Any]], table_name: Optional[str] = None) -> bool:
        if not rows:
            return True
        try:
            table_id = self._full_table_id(table_name or self.raw_table)
            table = self.client.get_table(table_id)
            errors = self.client.insert_rows_json(table, rows)
            if errors:
                _logger.log_text(f"BigQuery insert errors: {errors}", severity="Error")
                return False
            return True
        except Exception as e:
            _logger.log_text(f"insert_rows error: {e}", severity="Error")
            return False

    def query(self, sql: str) -> List[Dict[str, Any]]:
        try:
            job_config = bigquery.QueryJobConfig()
            job_config.use_legacy_sql = False
            job = self.client.query(sql, job_config=job_config)
            rows_iter = job.result()

            result_list = []
            for row in rows_iter:
                result_list.append(dict(row))

            return result_list
        
        except Exception as e:
            _logger.log_text(f"query error: {e}", severity="Error")
            return []

    def insert_failed_record(self, record: Dict[str, Any], status_code: str) -> bool:
        try:
            now_utc = datetime.now(timezone.utc)
            bq_updated_time = now_utc.strftime('%Y-%m-%dT%H:%M:%S.%f')

            row = {
                "uuid": record.get("uuid"),
                "cuid": record.get("cuid"),
                "series_number": record.get("serial_number"),
                "contact_address": record.get("contact_address"),
                "residence_address": record.get("residence_address"),
                "tax_code": record.get("tax_code"),
                "company_name": record.get("company_name"),
                "contract_longitude": str(record.get("longitude")) if record.get("longitude") is not None else None,
                "contract_latitude": str(record.get("latitude")) if record.get("latitude") is not None else None,
                "api_payload_message": json.dumps(record, ensure_ascii=False, default=str),
                "api_status": str(status_code),
                "BQ_UPDATED_TIME": bq_updated_time,
                "PARTITION_DATE": now_utc.strftime('%Y-%m-%d'),
            }
            table_id = self._full_table_id(self.failed_retry_table)
            table = self.client.get_table(table_id)
            errors = self.client.insert_rows_json(table, [row])
            if errors:
                _logger.log_text(f"Failed to insert failed record: {errors}", severity="Error")
                return False
            return True
        except Exception as e:
            _logger.log_text(f"insert_failed_record error: {e}", severity="Error")
            return False

    def update_failed_retry_status(self, partition_date: str):
        """
        批量更新在指定分區日期已成功處理的重試記錄。
        如果一筆記錄的 series_number 已存在於 GEO_DATA 表中，
        則將其在 GEO_DATA_FAILED_RETRY_LIST 中的狀態更新為 '200'。

        """
        try:
            failed_table = self._full_table_id(self.failed_retry_table)
            raw_table = self._full_table_id(self.raw_table)

            update_query = f"""
            UPDATE `{failed_table}` AS f
            SET
                f.api_status = '200',
                f.BQ_UPDATED_TIME = CURRENT_DATETIME(),
                f.PARTITION_DATE = @partition_date
            WHERE
                f.series_number IN (
                    SELECT DISTINCT r.serial_number
                    FROM `{raw_table}` AS r
                    WHERE r.PARTITION_DATE = @partition_date
                )
                AND NOT (f.api_status LIKE '2%' OR f.api_status = 'success')
            """
            params = [
                bigquery.ScalarQueryParameter("partition_date", "DATE", partition_date),
            ]
            job_config = bigquery.QueryJobConfig(query_parameters=params)
            job_config.use_legacy_sql = False
            self.client.query(update_query, job_config=job_config).result()

            _logger.log_text(
                f"successfully update failed retry table for partition date {partition_date}.",
                severity="Info",
            )
        except Exception as e:
            _logger.log_text(f"Failed to update failed retry table: {e}", severity="Error")

