"""
GCS 服務：提供單筆與批次上傳功能
"""

from __future__ import annotations

from typing import List, Dict, Any
import json
from google.cloud import storage
from utils.infra_logging import _logger


class GCSService:
    def __init__(self) -> None:
        self.client = storage.Client()

    def upload_text(self, bucket_name: str, blob_name: str, data: str, content_type: str = "application/json") -> str:
        try:
            bucket = self.client.bucket(bucket_name)
            blob = bucket.blob(blob_name)
            blob.upload_from_string(data, content_type=content_type)
            return f"gs://{bucket_name}/{blob_name}"
        except Exception as e:
            _logger.log_text(f"GCS upload_text error: {e}", severity="Error")
            raise

    def upload_rows_as_json(self, rows: List[Dict[str, Any]], bucket_name: str, prefix: str, partition_date: str) -> Dict[str, Any]:
        """
        將每筆 rows 以 JSON 格式上傳至 GCS，檔名格式：
        {prefix}/{partition_date}_{cuid}_{serial_number}.json

        Returns:
            {
                'uploaded': int,
                'total': int,
                'failed': List[Dict[str, str]],
            }
        """
        uploaded = 0
        failed: List[Dict[str, str]] = []

        for row in rows:
            cuid = row.get("cuid") or "null"
            serial_number = row.get("serial_number") or "null"
            blob_name = f"{prefix}/{partition_date}_{cuid}_{serial_number}.json"
            try:
                data = json.dumps(row, ensure_ascii=False)
                self.upload_text(
                    bucket_name,
                    blob_name,
                    data,
                    content_type="application/json",
                )
                uploaded += 1
            except Exception as e:
                _logger.log_text(
                    f"GCS upload failed for cuid={cuid}, serial_number={serial_number}: {e}",
                    severity="Warning",
                )
                failed.append({
                    "cuid": str(cuid),
                    "serial_number": str(serial_number),
                    "error": str(e),
                })

        return {
            "uploaded": uploaded,
            "total": len(rows),
            "failed": failed,
        }
