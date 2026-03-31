
import uuid
import json
from datetime import datetime, timezone

def prepare_raw_data_for_bq(original_record, api_response):
    """
    將原始 VMB 資料與 Credolab API 回應組合，準備插入 BigQuery 原始表格。
    
    上行電文欄位對應：
    - cuid: 客戶唯一識別碼
    - reference_id: 參考編號 (用於API查詢)
    - device_os: 裝置作業系統 (android/ios)
    - serial_number: HES申貸編號
    
    API 回應會包含 reference_number 欄位，其值等於上行電文的 reference_id

    Args:
        original_record (dict): 從 VMB 表格取得的上行電文記錄
        api_response (dict): Credolab API 回應 (下行電文)

    Returns:
        dict: 符合 BigQuery 原始表格 schema 的資料字典
    """

    return {
        "uuid": str(uuid.uuid4()),
        "cuid": original_record.get('cuid'),
        "reference_id": original_record.get('reference_id'),
        "series_number": original_record.get('serial_number'),
        "device_os": original_record.get('device_os'),
        "raw_data": json.dumps(api_response, ensure_ascii=False, default=str),  # API回應的完整JSON
        "BQ_UPDATED_TIME": datetime.now().isoformat(),
        "PARTITION_DATE": datetime.now().strftime('%Y-%m-%d')
    }