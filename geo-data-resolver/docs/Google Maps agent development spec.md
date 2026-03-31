# Google Maps 代理程式開發規範

---

## 範圍與目標

### 目標

建置一個彈性的代理管道，使用 Google Maps API 為貸款申請增添地理空間特徵，然後將輸出儲存到 GCS 和 BigQuery 中，以供下游風險分析使用。

### 涵蓋範圍

- **API：** Geocoding, Place Details, Text Search, Routes (ComputeRoutes), Places Aggregate
- **功能：** 資料完整性檢查、重試、次日重播
- **測試：** 在 1200 QPM 基準下進行批次壓力測試
- **主要金鑰：** CUID + Serial_number
- **敏感資料：** 經度/緯度、地址；按照指示對指定欄位進行 AES-256 遮罩處理

---

## Agent Roles and Responsibilities

### 資料擷取代理

**輸入：** HES.Application 和聯結資料表

**動作：** 每日執行提供的 SQL（D-1），為代理流程發出標準化記錄

**輸出：** 包含合約 lat/lng、聯絡地址、居住地址、公司名稱、公司稅碼的申請記錄

```sql
-- HES.Application申貸資訊(for googlemaps)
SELECT DISTINCT
  c.CUID,
  ap.SERIAL_NUMBER,
  ap.CREATED_AT,
  c.CURRENT_DETAILED_ADDRESS,
  c.PERMANENT_DETAILED_ADDRESS,
  ay.tax_code,
  ay.company_name,
  ay.LONGITUDE,
  ay.LATITUDE,
  ap.partition_date
FROM `RAW_HES_DATASET.CUSTOMER` c
LEFT JOIN `RAW_HES_DATASET.APPLICATION` ap ON (c.id = ap.customer_id)
LEFT JOIN `RAW_VMB_DATASET.APPLY_INFO` ay ON (c.cuid = ay.cuid)
WHERE c.cuid IS NOT NULL
  AND ap.partition_date = DATE_SUB(CURRENT_DATE(), INTERVAL 1 DAY)
QUALIFY ROW_NUMBER()
  OVER (PARTITION BY c.CUID, ap.SERIAL_NUMBER ORDER BY ap.partition_date DESC) = 1
```

### 豐富化代理（API 執行器）

#### 地理編碼代理

**輸入：** 合約 lat/lng、聯絡地址、居住地址

**輸出（每個輸入）：** 標準化地址（國家/城市/區/里/街道）、lat/lng、地點 ID、全域代碼

#### 文字搜尋代理（公司）

**輸入：** company_name；對於模糊查詢，僅限具有 tax_code 且 region=vn 的名稱；僅保留單一位置匹配

**輸出：** 公司 lat/lng、標準化地址、地點 ID、全域代碼

#### 地點詳細資料代理

**輸入：** 合約/聯絡/居住地點 ID

**輸出：** 每個地點的地點類型（placetypes）

#### 地點彙總代理

**輸入：** 合約/聯絡/公司的 lat/lng 或地點 ID

**輸出：** 700 公尺半徑內的三個 POI 計數（情境）和運營狀態篩選器

#### 路線代理

**輸入：** lat/lng 或地點 ID 配對：聯絡↔合約和聯絡↔公司

**輸出：** 通勤時間、通勤距離

### 持續性代理

**動作：** 將 JSON 輸出寫入 GCS；更新插入 BigQuery 資料集 VDO-BQ 和 VAP-BQ（GoogleMaps 資料集）

**冪等性：** 以（CUID, Serial_number）為金鑰的更新插入，每個欄位群組

---

## 協調流程與決策邏輯

### 整體順序

1. **步驟 1：** 從 HES.Application 載入輸入（資料擷取器）

2. **步驟 2：** 地理編碼與文字搜尋
   - 合約 lat/lng → 地理編碼（反向）
   - 聯絡地址 → 地理編碼（正向）
   - 居住地址 → 地理編碼（正向）
   - 公司名稱 → 文字搜尋（region=vn, tax_code-only, single-result）

3. **步驟 3：** 合約/聯絡/居住地點 ID 的地點詳細資料

4. **步驟 4：** 合約/聯絡/公司 lat/lng 或地點 ID 的地點彙總（三個情境）

5. **步驟 5：** 計算聯絡↔合約和聯絡↔公司的路線

6. **步驟 6–7：** 持續儲存到 VDO-BQ 和 VAP-BQ，中間使用 GCS 儲存

### 呼叫閘控、重試、重播

- **呼叫前空值檢查：** 如果輸入欄位為空值，跳過 API
- **同日重試：** 失敗時最多 5 次嘗試；記錄日誌
- **次日重播：** 重新嘗試昨天的失敗
- **呼叫前存在檢查：** 如果（CUID, Serial_number）的目標輸出欄位已存在，跳過

### 速率限制與批次處理

**壓力測試：** 在 1200 QPM 基準下驗證行為

**批次策略：**
- 每個 API 的交錯佇列以避免同步突發
- 每個 API 類型的權杖桶與 QPM 上限

**適應性退避：** HTTP 429/5xx 上的指數退避與抖動；如果存在則遵守 Retry-After

**冪等寫入：** 以金鑰 + 欄位群組去重以容忍重試

---

## API 合約與提示架構

### 地點彙總提示（三個情境）

**通用篩選器：** OperatingStatus = OPERATING_STATUS_OPERATIONAL, Radius = 700

**情境桶：**
- **公司類型+金融：** corporate_office, bank, atm
- **住宅** apartment_building, apartment_complex, condominium_complex, housing_complex
- **商業類型+設施** restaurant, store, clothing_store, shopping_mall, furniture_store, supermarket, car_repair, car_dealer, electronics_store, convenience_store, jewelry_store, travel_agency, lodging, tourist_attraction, hair_care, amusement_park, movie_theater, gym, cafe, hospital, pharmacy, fire_station, gas_station, library, school, university, post_office, local_government_office


**範例請求：**

```json
{
  "insight": "INSIGHT_COUNT",
  "place": { "location": { "lat": 10.7890648, "lng": 106.7026967 } },
  "includedTypes": ["corporate_office", "bank", "atm"],
  "operatingStatus": ["OPERATING_STATUS_OPERATIONAL"],
  "radiusMeters": 700
}

{
  "insight": "INSIGHT_COUNT",
  "place": { "location": { "lat": 10.7890648, "lng": 106.7026967 } },
  "includedTypes": ["apartment_building", "apartment_complex", "condominium_complex", "housing_complex"],
  "operatingStatus": ["OPERATING_STATUS_OPERATIONAL"],
  "radiusMeters": 700
}

以此類推"商業類型+設施"的請求

```

**Place Aggregate API Response 範例：**

```

{'count': '4'}

```

### 地理編碼

**反向：** latlng → 地址元件 + 地點 ID + plus_code (global_code)

**正向：** 地址 → lat/lng + 地址元件 + 地點 ID + plus_code

**範例：**

```json
{
  "input": { "latlng": "10.7952182,106.7215815" },
  "output": {
    "country": "VN",
    "administrative_area_level_1": "Ho Chi Minh City",
    "administrative_area_level_2": "District X",
    "sublocality_level_1": "Ward Y",
    "route": "Street Z",
    "place_id": "ChIJxxxxxxxx",
    "global_code": "8Pxxxxxx"
  }
}
```

### 地點詳細資料

**範例：**

```json
{
  "input": { "place_id": "ChIJxxxxxxxx" },
  "output": { "place_types": ["apartment_building", "point_of_interest"] }
}
```

### 文字搜尋（公司）

**限制：** region=vn；需要 tax_code；僅接受單一結果；如果有多個，不保留

**範例：**

```json
{
  "input": { "query": "000000 越南銀行", "region": "vn", "requireTaxCode": true },
  "output": {
    "name": "越南銀行",
    "place_id": "ChIJcompany",
    "location": { "lat": 10.818371, "lng": 106.731908 },
    "address_components": { "..." },
    "global_code": "8Pxxxxxx"
  }
}
```

### 計算路線

**配對：** contact↔contract, contact↔company

**輸出：** duration, distance，可選的 polyline 用於路線稽核

**範例：**

```json
{
  "input": {
    "origin": { "lat": 10.7865429, "lng": 106.6333399 },
    "destination": { "lat": 10.7890648, "lng": 106.7026967 },
    "travelMode": "DRIVE"
  },
  "output": { "durationSeconds": 1800, "distanceMeters": 9500 }
}
```

## 執行圖與代理狀態機

### 高階 DAG

```
HES SQL -> 擷取記錄
   -> 地理編碼(合約反向) -> 地點 ID + 地址
   -> 地理編碼(聯絡正向)  -> lat/lng + 地點 ID + 地址
   -> 地理編碼(居住正向)-> lat/lng + 地點 ID + 地址
   -> 文字搜尋(公司)        -> lat/lng + 地點 ID + 地址
   -> 地點詳細資料(合約/聯絡/居住)
   -> 地點彙總(合約/聯絡/公司)
   -> 計算路線(聯絡<->合約, 聯絡<->公司)
   -> 持續儲存 (GCS -> BigQuery: VDO-BQ)
```

### 每次呼叫守衛與重試政策

**先決條件：**
- **合約反向地理編碼：** 需要合約 lat/lng
- **聯絡/居住正向地理編碼：** 需要地址字串
- **地點詳細資料：** 需要地點 ID
- **彙總：** 需要 lat/lng 或地點 ID
- **路線：** 需要起點和終點的 lat/lng 或地點 ID

**重試：** 同日最多 5 次嘗試；指數退避與抖動；記錄每次嘗試

**重播：** 次日工作掃描失敗日誌並重新發出遺漏的呼叫

---

## 測試計劃

### 階段 1：地點彙總首次執行

**資料擷取：** 驗證記錄包含 CUID, Serial_number, 合約 lat/lng, 聯絡/居住地址, 公司名稱

**存在檢查：** 如果三個彙總欄位不存在 → 觸發呼叫

**單次執行測試：**
- **有效輸入：** 合約 lat/lng → 三個彙總計數
- **空值輸入：** 跳過
- **重試與重播：** 模擬 500/503/504；斷言日誌和重試成功

**壓力測試：**
- **1,000 QPM 基準：** 發出 1,500 個請求；驗證成功、完整性、無遺失/拒絕
- **1,500 QPM 基準：** 發出 1,500 個請求；驗證相同
- **1,000 QPM 基準：** 發出 3,000 個請求；驗證超出時的行為

**持續性：** 確認 GCS 寫入和 BQ 更新插入

**內容驗證：** 在六個座標點檢查 POI 計數：
- 10.7384575, 106.7423740
- 10.8173435, 106.7312811
- 10.7890648, 106.7026967
- 10.7865429, 106.6333399
- 10.7952182, 106.7215815
- 10.818371, 106.731908

### 階段 2：地理編碼

**每個群組的存在檢查：** 合約標準化地址；聯絡 lat/lng + 標準化地址；居住 lat/lng + 標準化地址

**測試：** 有效輸入執行；空值跳過；重試和次日重播；持續儲存到 GCS/BQ

### 階段 3：地點詳細資料

**輸入：** 合約/聯絡/居住地點 ID

**輸出：** 三個地點的地點類型；相同的閘控/重試/持續性

### 階段 4：文字搜尋（公司）

**輸入：** 公司名稱；應用 region=vn，需要 tax_code；僅保留單一結果

**輸出：** 公司 lat/lng，標準化地址，地點 ID，全域代碼；閘控/重試/持續性

### 階段 5：計算路線

**配對：** contact↔contract, contact↔company

**測試：** 空值輸入案例：跳過；重試/重播；GCS/BQ 持續性

**輸出：** 通勤時間和距離

---
