# 1) Business Requirements（業務需求與成功標準）

本文件根據現有程式碼與 SQL 逆向整理業務需求，並定義成功標準、KPI 與邊界條件。

## 1.1 目標與範圍
- 批量解析使用者或企業的地理資料，取得周邊 POI（企業金融、住宅、商業）之計數，並寫入資料湖/倉。
- 支援每日（Daily）與日期區間（Range）兩種處理模式，透過 Pub/Sub 進行批次鏈結。
- 異常時記錄失敗清單，後續再進行重試；成功後再執行扁平化（flatten）與匿名化通知流程。

關聯系統/表：
- 來源（查詢）：`RAW_HES_DATASET.CUSTOMER`、`RAW_HES_DATASET.APPLICATION`、`RAW_VMB_DATASET.APPLY_INFO`
- RAW 成果（寫入）：`RAW_EDEP_DATASET.GEO_DATA`
- 失敗清單：`RAW_EDEP_DATASET.GEO_DATA_FAILED_RETRY_LIST`
- 扁平化（TRANS）：`TRANS_EDEP_DATASET.TMP_GEO_DATA`

## 1.2 Business Requirements（BR）
- BR-01：每日與日期區間模式
  - Daily：未帶日期；系統自動處理當輪批次，並以 Pub/Sub 連鎖後續批次。
  - Range：帶入 `start_date`、`end_date`；同樣以 Pub/Sub 進行多批次串接。
- BR-02：來源資料篩選（避免重複/已處理）
  - 僅選取 `CUID` 不為空之資料。
  - 以 `CUID + SERIAL_NUMBER` 去重，取最新分區（`QUALIFY ROW_NUMBER()`）。
  - 排除已存在於 `RAW_EDEP_DATASET.GEO_DATA` 的 `serial_number`（避免重複寫 RAW）。
  - 排除已在 `GEO_DATA_FAILED_RETRY_LIST` 的 `series_number`（避免重複查失敗清單）。
- BR-03：API 呼叫與處理規則
  - 對每筆資料對應多個 POI 情境（`corporate_finance`、`residential`、`commercial`）。
  - 座標若無效則略過 API 呼叫，該情境的 `count` 視為 `"null"`，不中斷整筆處理。
  - 任一情境拋出例外（API 錯誤或逾時）時，記錄該筆至 `GEO_DATA_FAILED_RETRY_LIST`，並將該情境 `count` 設為 `"null"`。
  - 僅當某筆資料所有情境皆成功（無例外）時，才將整筆彙整後寫入 `RAW_EDEP_DATASET.GEO_DATA`。
- BR-04：批次大小與速率限制
  - 透過設定檔控制 `batch_size`（預設 100）。
  - Google Maps API 以 QPM（每分鐘查詢數）限制，使用指數退避重試策略。
- BR-05：失敗重試（Failed Retry）
  - 於每輪批次完成後，先依「D-14 ~ D-1」視窗查詢 `GEO_DATA_FAILED_RETRY_LIST` 的最新非成功狀態，依 `series_number` 去重（保留最新），再進行補查。
  - 定義「成功」為 `api_status` 前綴為 `2xx` 或值為 `success`；其餘視為需重試候選。
  - 每輪批次開始前，先將「昨日（D-1）」寫入 RAW 成功的 `series_number` 對應的失敗清單狀態更新為 `200`（視為成功）。
- BR-06：扁平化與匿名化
  - 最後一批完成後執行 `flatten_geo_data.sql`，以 `@partition_date`（Range 用 `end_date`，Daily 用今日日期）將 RAW 轉入 `TRANS_EDEP_DATASET.TMP_GEO_DATA`。
  - 扁平化成功才發送匿名化通知（Pub/Sub），目前 payload 為 `{"file_list": ["TRANS_EDEP_DATASET.GEO_DATA"]}`。
- BR-07：可觀測性（Logging/Metrics）
  - 重要步驟需記錄 Flow Log、API Log；量測 QPM、API 成功率、寫入筆數等指標。

## 1.3 成功標準（Acceptance Criteria Summary）
- AC-01：來源查詢遵守去重與排除規則（BR-02）。
- AC-02：無效座標不呼叫 API；該情境 `count = "null"`；不視為失敗。
- AC-03：同一筆資料若任一情境 API 例外，該筆不得寫入 RAW，且寫入失敗清單（BR-03）。
- AC-04：批次前更新 D-1 的失敗清單狀態；批次後於 D-14~D-1 視窗進行重試（BR-05）。
- AC-05：最後一批成功後執行扁平化，成功才發送匿名化通知（BR-06）。

## 1.4 KPI（示例）
- API 成功率 > 95%
- 每日批次完全處理率 100%（含重試觸發）
- 平均每批次處理時間符合 SLA（例如 < 5 分鐘/批）

## 1.5 邊界與風險
- BigQuery 與 Google Maps API 為外部相依；需處理暫時性失敗（429/5xx/Timeout）。
- 來源表結構或品質改變需同步更新查詢規則與驗收規格。
- 匿名化流程只在扁平化成功後觸發，避免下游處理無效資料。
