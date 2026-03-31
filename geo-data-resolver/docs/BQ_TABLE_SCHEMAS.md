# BigQuery Table Schemas - Geo Data Resolver

## 表結構說明

### 1. RAW_EDEP_DATASET.GEO_DATA
**用途**: 存儲原始的地理位置數據，作為批次處理的資料源

| 字段名稱 | 模式 | 類型 | 描述 |
|---------|------|------|------|
| uuid | NULLABLE | STRING | 唯一識別碼 |
| cuid | NULLABLE | STRING | 用戶ID |
| serial_number | NULLABLE | STRING | 序列號 |
| contact_address | NULLABLE | STRING | 聯絡地址 |
| residence_address | NULLABLE | STRING | 居住地址 |
| company_name | NULLABLE | STRING | 公司名稱 |
| contract_longitude | NULLABLE | STRING | 合約經度 |
| contract_latitude | NULLABLE | STRING | 合約緯度 |
| raw_data | NULLABLE | STRING | 原始數據 (JSON 格式) |
| BQ_UPDATED_TIME | NULLABLE | DATETIME | BigQuery 更新時間 |
| PARTITION_DATE | NULLABLE | DATE | 分區日期 |

### 2. RAW_EDEP_DATASET.GEO_DATA_FAILED_RETRY_LIST
**用途**: 存儲 API 調用失敗的記錄，用於重試機制和失敗追蹤

| 字段名稱 | 模式 | 類型 | 描述 |
|---------|------|------|------|
| uuid | NULLABLE | STRING | 唯一識別碼 |
| cuid | NULLABLE | STRING | 用戶ID |
| series_number | NULLABLE | STRING | 系列號 |
| contact_address | NULLABLE | STRING | 聯絡地址 |
| residence_address | NULLABLE | STRING | 居住地址 |
| tax_code | NULLABLE | STRING | 公司稅號 |
| company_name | NULLABLE | STRING | 公司名稱 |
| contract_longitude | NULLABLE | STRING | 合約經度 |
| contract_latitude | NULLABLE | STRING | 合約緯度 |
| api_payload_message | NULLABLE | STRING | API 請求載荷消息 |
| api_status | NULLABLE | STRING | API 狀態 (error_code, 錯誤訊息) |
| retry_count | NULLABLE | INTEGER | 重試次數 |
| last_retry_time | NULLABLE | DATETIME | 最後重試時間 |
| BQ_UPDATED_TIME | NULLABLE | DATETIME | BigQuery 更新時間 |
| PARTITION_DATE | NULLABLE | DATE | 分區日期 |

### 3. TRANS_EDEP_DATASET.TMP_GEO_DATA
**用途**: 存儲處理後的地理數據，包含地址解析結果和 POI 信息

| 字段名稱 | 模式 | 類型 | 描述 |
|---------|------|------|------|
| cuid | NULLABLE | STRING | 用戶ID |
| serial_number | NULLABLE | STRING | 序列號 |
| contract_longitude | NULLABLE | STRING | 合約經度 |
| contract_latitude | NULLABLE | STRING | 合約緯度 |
| contact_address | NULLABLE | STRING | 聯絡地址 |
| residence_address | NULLABLE | STRING | 居住地址 |
| company_name | NULLABLE | STRING | 公司名稱 |
| contract_country | NULLABLE | STRING | 合約國家 |
| contract_city | NULLABLE | STRING | 合約城市 |
| contract_district | NULLABLE | STRING | 合約區 |
| contract_ward | NULLABLE | STRING | 合約鄉鎮 |
| contract_street | NULLABLE | STRING | 合約街道 |
| contract_place_id | NULLABLE | STRING | 合約地點ID |
| contract_global_code | NULLABLE | STRING | 合約全球代碼 |
| contact_longitude | NULLABLE | STRING | 聯絡經度 |
| contact_latitude | NULLABLE | STRING | 聯絡緯度 |
| contact_country | NULLABLE | STRING | 聯絡國家 |
| contact_city | NULLABLE | STRING | 聯絡城市 |
| contact_district | NULLABLE | STRING | 聯絡區 |
| contact_ward | NULLABLE | STRING | 聯絡鄉鎮 |
| contact_street | NULLABLE | STRING | 聯絡街道 |
| contact_place_id | NULLABLE | STRING | 聯絡地點ID |
| contact_global_code | NULLABLE | STRING | 聯絡全球代碼 |
| residence_longitude | NULLABLE | STRING | 居住經度 |
| residence_latitude | NULLABLE | STRING | 居住緯度 |
| residence_country | NULLABLE | STRING | 居住國家 |
| residence_city | NULLABLE | STRING | 居住城市 |
| residence_district | NULLABLE | STRING | 居住區 |
| residence_ward | NULLABLE | STRING | 居住鄉鎮 |
| residence_street | NULLABLE | STRING | 居住街道 |
| residence_place_id | NULLABLE | STRING | 居住地點ID |
| residence_global_code | NULLABLE | STRING | 居住全球代碼 |
| company_longitude | NULLABLE | STRING | 公司經度 |
| company_latitude | NULLABLE | STRING | 公司緯度 |
| company_country | NULLABLE | STRING | 公司國家 |
| company_city | NULLABLE | STRING | 公司城市 |
| company_district | NULLABLE | STRING | 公司區 |
| company_ward | NULLABLE | STRING | 公司鄉鎮 |
| company_street | NULLABLE | STRING | 公司街道 |
| company_place_id | NULLABLE | STRING | 公司地點ID |
| company_global_code | NULLABLE | STRING | 公司全球代碼 |
| contract_place_types | NULLABLE | STRING | 合約地點類型 |
| contact_place_types | NULLABLE | STRING | 聯絡地點類型 |
| residence_place_types | NULLABLE | STRING | 居住地點類型 |
| commute_time_contract_contact | NULLABLE | STRING | 合約到聯絡通勤時間 |
| commute_distance_contract_contact | NULLABLE | STRING | 合約到聯絡通勤距離 |
| commute_time_company_contact | NULLABLE | STRING | 公司到聯絡通勤時間 |
| commute_distance_company_contact | NULLABLE | STRING | 公司到聯絡通勤距離 |
| contract_poi_corporate_finance | NULLABLE | STRING | 合約周邊企業金融 POI |
| contract_poi_commercial_facility | NULLABLE | STRING | 合約周邊商業設施 POI |
| contract_poi_residential | NULLABLE | STRING | 合約周邊住宅 POI |
| BQ_UPDATED_TIME | NULLABLE | DATETIME | BigQuery 更新時間 |
| PARTITION_DATE | NULLABLE | DATE | 分區日期 |


