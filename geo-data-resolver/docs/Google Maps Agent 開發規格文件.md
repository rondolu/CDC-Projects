# Google Maps Agent 開發規格文件

---

## 範疇與目標

- **目標：** 建立一個具備韌性的 Agent 流程，利用 Google Maps API 擴充申貸資料，並將結果寫入 GCS 與 BigQuery，供後續風險分析使用。  
- **涵蓋範圍：**
  - Geocoding、Place Details、Text Search、Routes (ComputeRoutes)、Places Aggregate
  - 三種 Aggregate 情境：公司+金融、商業+設施、住宅
  - 資料完整性檢查、重試機制、隔日補發
  - 壓測：1200 QPM
- **主鍵：** `CUID` + `Serial_number`
- **敏感資料：** 經緯度、地址 → 需依規 AES-256 遮罩

---

## Agent 角色與職責

### Data Fetcher Agent
- **輸入：** HES.Application 與關聯表
- **動作：** 每日 (D-1) 執行 SQL，輸出標準化申貸紀錄
- **輸出：** 合約經緯度、通訊地址、戶籍地址、公司名稱、公司 tax_code

### Enrichment Agents
- **Geocoding Agent：** 地址 ↔ 經緯度轉換
- **Text Search Agent：** 公司查詢 (region=vn、需 tax_code、僅單筆結果)
- **Place Details Agent：** 取得 Place Types
- **Places Aggregate Agent：** 半徑 700m 內三類 POI 統計
- **Routes Agent：** 通勤時間與距離 (通訊↔合約、通訊↔公司)

### Persistence Agent
- **動作：** 將結果寫入 GCS，並 Upsert 至 BigQuery (VDO-BQ、VAP-BQ)
- **特性：** 以 `(CUID, Serial_number)` 為鍵，確保冪等性

---

## 流程編排

1. **載入資料** (HES.Application)
2. **Geocoding & Text Search**
   - 合約經緯度 → Geocoding
   - 通訊地址 → Geocoding
   - 戶籍地址 → Geocoding
   - 公司名稱 → Text Search
3. **Place Details** (合約/通訊/戶籍 Place ID)
4. **Places Aggregate** (合約/通訊/公司)
5. **Compute Routes** (通訊↔合約、通訊↔公司)
6. **Persist** (GCS → BigQuery)

---

## 重試與補發策略

- **空值檢查：** 輸入為空則跳過
- **當日重試：** 失敗最多 5 次
- **隔日補發：** 對昨日失敗 API 重發
- **存在檢查：** 若目標欄位已存在則跳過

---

## 流量控制與批次策略

- **壓測：** 驗證 1,000 QPM 與 1,500 QPM
- **批次策略：**
  - 每 API 類型設置 Token Bucket
  - 429/5xx → 指數退避 + 隨機抖動
- **冪等性：** 以 Key + 欄位群組去重

---

## API 合約摘要

### Places Aggregate
- **三大情境：** 公司+金融、住宅、商業類型+設施
- **共通條件：** `OperatingStatus=OPERATIONAL`、`Radius=700`

### Geocoding
- **Reverse：** lat/lng → 地址元件 + Place ID + plus_code
- **Forward：** 地址 → lat/lng + Place ID + plus_code

### Place Details
- **輸入：** Place ID
- **輸出：** place types

### Text Search
- **限制：** region=vn、需 tax_code、僅單筆結果

### Compute Routes
- **輸入：** 通訊↔合約、通訊↔公司
- **輸出：** 時間、距離


---

## 執行圖

```text
HES SQL -> Fetch Records
   -> Geocoding (合約/通訊/戶籍)
   -> Text Search (公司)
   -> Place Details
   -> Places Aggregate
   -> Compute Routes
   -> Persist (GCS -> BigQuery)
