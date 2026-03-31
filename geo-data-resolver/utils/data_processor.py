"""
資料處理工具：將 API 回應與來源記錄整理成可寫入 BigQuery 的列

包含：
- prepare_geo_raw_row：產出 RAW_EDEP_DATASET.GEO_DATA 所需欄位（raw 表）
"""

from __future__ import annotations

from typing import Dict, Any
import json
from datetime import datetime, timezone


def prepare_geo_raw_row(
    source_record: Dict[str, Any],
    api_result: Dict[str, Any] | None,
) -> Dict[str, Any]:
    """
    產出 RAW_EDEP_DATASET.GEO_DATA 的列資料

    """

    now_utc = datetime.now(timezone.utc)
    bq_updated_time = now_utc.strftime('%Y-%m-%dT%H:%M:%S.%f')

    row = {
        "uuid": source_record.get("uuid"),
        "cuid": source_record.get("cuid"),
        "serial_number": source_record.get("serial_number"),
        "contact_address": source_record.get("contact_address"),
        "residence_address": source_record.get("residence_address"),
        "company_name": source_record.get("company_name"),
        "contract_longitude": str(source_record.get("contract_longitude")),
        "contract_latitude": str(source_record.get("contract_latitude")),
        "raw_data": json.dumps(api_result, ensure_ascii=False, default=str),
        "BQ_UPDATED_TIME": bq_updated_time,
        "PARTITION_DATE": now_utc.strftime('%Y-%m-%d')
    }
    
    return row
