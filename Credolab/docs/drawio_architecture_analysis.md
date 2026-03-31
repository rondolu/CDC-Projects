# Credolab 批次處理架構分析

## Draw.io 流程圖各區塊重要性分析

### **入口點區塊 (Entry Points)**

#### 1. `POST /` & `POST /get_data_range`
**重要性**: 這是整個系統的兩個主要入口點
- `POST /`: 處理每日批次處理請求
- `POST /get_data_range`: 處理日期範圍批次處理請求

**為什麼重要**:
- 分離不同的業務場景（每日 vs 範圍）
- 允許不同的參數驗證和處理邏輯
- 支援不同的重試和監控策略

#### 2. `handle_daily_request()` & `handle_date_range_request()`
**重要性**: 請求處理器，負責參數驗證和初始設置
- 驗證輸入參數
- 建立適當的 BatchContext
- 觸發處理流程

**為什麼重要**:
- 集中處理 HTTP 請求的業務邏輯
- 隔離外部接口和內部處理邏輯
- 統一錯誤處理和回應格式

### **核心處理區塊 (Core Processing)**

# 批次處理架構

本文件已精簡為與現行程式一致的概覽；移除早期假設與重複內容，詳細請參考下方單一來源文件。

## 分層與職責
- 路由層：`blueprints/credolab_routes.py` 對外 API（daily/range）
- 服務層：`services/dataflow_service.py` 協調資料流與 recall 決策；`services/credolab_api_service.py` 封裝外部 API 呼叫
- 應用層：`application/batch_process_service.py` 完成批次處理、GCS/BQ 寫入、最後一批的 flatten 與 anonymization 發布
- 工具/基礎設施：`utils/infra_logging.py`（FLOW/API 日誌）、`utils/pubsub_services.py`（publish_*）、`infrastructure/credolab_client.py`

## 資料流（現況）
1) BigQuery 查詢 VMB 資料（daily 或日期區間）
2) 依 `batch_size` 切批：第一批直接處理，後續以 Pub/Sub recall 推進
3) 逐筆呼叫 Credolab API；成功彙整寫 BQ、原始寫 GCS；失敗寫入 Failed Retry 表（不在此流程自動重試）
4) 是否最後一批：否→發布下一批 recall；是→執行 flatten（android/ios）並發布 anonymization（必要時）

## 設定
- 全部表名/資料集/Topic/batch_size 取自 `config/config.yaml` 與環境變數；避免任何硬編碼

## 日誌
- 使用 `utils/infra_logging.Logging`：
    - FLOW_LOG：完成/錯誤時寫入；`task_code = flow_id + 細項代碼`
    - API_LOG：每次外部 API 呼叫結果（含 UUID_Request）
- “all job completed” 僅在最後一批完成且發布 anonymization 後（依實際執行路徑）寫一次

## 單一來源文件（建議閱讀順序）
- 架構概覽：`docs/ARCHITECTURE_ANALYSIS.md`
- 數據流程：`docs/DATAFLOW_SUMMARY.md`
- Recall 機制：`docs/RECALL_MECHANISM_GUIDE.md`
- 日誌規範：`docs/LOGGING_GUIDE.md`

以上內容取代舊版的長篇架構分析。
- 後續批次：協調處理

**為什麼重要**:
- 不同的處理策略
- 狀態管理差異

### **批次處理區塊 (Batch Processing)**

#### 9. `_initiate_batch_processing()` & `_orchestrate_batch_processing()`
**重要性**: 分離首次和後續批次處理邏輯

#### 10. `_process_batch_records()`
**重要性**: 單一批次的記錄處理
- API 呼叫階段
- 批次儲存階段
- 下一批次觸發

**為什麼重要**:
- 封裝單一批次的完整處理邏輯
- 統一的錯誤處理和狀態管理

#### 11. `FOR each record` 循環
**重要性**: 逐筆處理批次中的每條記錄
- 迭代處理
- 收集成功/失敗結果

**為什麼重要**:
- 細粒度的錯誤處理
- 部分失敗的恢復能力

#### 12. `_call_credolab_api()` & API 服務鏈
**重要性**: 外部 API 呼叫
- `get_credolab_insights()`: 業務邏輯
- `CredolabAPIClient.get_insights()`: HTTP 客戶端

**為什麼重要**:
- 分層架構：業務邏輯 vs 技術實現
- 可測試性和可替換性

#### 13. `2xx?` 決策點
**重要性**: API 回應狀態檢查
- 成功：進入儲存流程
- 失敗：進入錯誤處理

**為什麼重要**:
- 正確處理不同的 HTTP 狀態碼
- 區分可重試和不可重試的錯誤

### **儲存區塊 (Storage)**

#### 14. `_batch_upload_to_gcs()` & `_batch_insert_to_bigquery()`
**重要性**: 批次儲存操作
- GCS: 檔案儲存
- BigQuery: 結構化資料儲存

**為什麼重要**:
- 雙重儲存確保資料持久性
- 分離不同的儲存後端
- 獨立的錯誤處理

#### 15. `insert_failed_record()`
**重要性**: 失敗記錄處理
- 寫入重試列表
- 保留錯誤資訊

**為什麼重要**:
- 支援失敗重試機制
- 資料完整性保障

### **流程控制區塊 (Flow Control)**

#### 16. 批次摘要 & 狀態檢查
**重要性**: 批次完成檢查
- 統計成功/失敗數量
- 判斷是否還有下一批次

**為什麼重要**:
- 狀態追蹤和監控
- 流程控制決策

#### 17. `Batch Status?` 決策點
**重要性**: 決定後續動作
- 還有批次：發布 recall 訊息
- 最後批次：執行最終處理

**為什麼重要**:
- 正確的流程終止條件
- 最終處理的觸發

#### 18. `publish_*_recall_message()`
**重要性**: 觸發下一批次處理
- 非同步批次間轉換
- 保持處理連續性

**為什麼重要**:
- 支援大規模批次處理
- 避免記憶體和資源限制

### **最終處理區塊 (Final Processing)**

#### 19. `flatten SQLs (android/ios)`
**重要性**: 資料轉換處理
- 執行資料扁平化 SQL
- 準備下游處理

**為什麼重要**:
- 資料管道的關鍵步驟
- 確保資料格式一致性

#### 20. `publish_anonymization`
**重要性**: 通知下游系統
- 觸發資料匿名化處理

**為什麼重要**:
- 系統間解耦
- 事件驅動架構

## 為什麼要拆分 `_initiate_batch_processing()` 和 `_orchestrate_batch_processing()`？

### **架構設計原理**

這兩個函數的拆分是基於**單一責任原則**和**關注點分離**的設計模式：

#### `_initiate_batch_processing()` 的責任：
1. **初始化階段**：設定總批次數，準備第一批資料
2. **首次處理**：處理第一批次的業務邏輯
3. **狀態建立**：建立批次處理的初始狀態
4. **回應準備**：準備第一批次的處理回應

#### `_orchestrate_batch_processing()` 的責任：
1. **協調階段**：計算批次範圍，準備當前批次資料
2. **後續處理**：處理第 N 批次的業務邏輯
3. **流程控制**：判斷是否為最後一批次
4. **最終處理**：觸發 flatten SQL 和 anonymization

### **拆分的技術原因**

1. **狀態差異**：
   - 首次批次：需要初始化總批次數，設定回調函數
   - 後續批次：總批次數已知，只需要處理當前批次

2. **流程差異**：
   - 首次批次：處理後立即返回回應
   - 後續批次：處理後可能觸發最終處理或下一批次

3. **錯誤處理差異**：
   - 首次批次失敗：直接影響整個流程
   - 後續批次失敗：可能允許部分成功

## 合併成單一函數的優缺點分析

### **優點 (Pros)**

#### 1. **簡化代碼結構**
- 減少函數數量，降低複雜度
- 統一的處理邏輯，減少重複代碼
- 更容易理解整體流程

#### 2. **統一的錯誤處理**
- 單一的 try-catch 區塊
- 一致的錯誤處理策略
- 減少錯誤處理的差異

#### 3. **更好的性能**
- 減少函數呼叫的開銷
- 更少的堆疊框架
- 潛在的內聯優化機會

#### 4. **開發便利性**
- 單一函數更容易除錯
- 減少在函數間跳轉的認知負擔
- 統一的測試覆蓋

### **缺點 (Cons)**

#### 1. **違反單一責任原則**
- 一個函數負責太多不同的邏輯
- 初始化和協調的責任混在一起
- 難以維護和修改

#### 2. **降低可測試性**
- 難以單獨測試初始化邏輯
- 難以模擬不同的批次狀態
- 測試案例膨脹

#### 3. **降低可重用性**
- 無法在其他地方重用初始化邏輯
- 緊耦合的設計限制靈活性

#### 4. **增加複雜度**
- 條件分支增加（if first batch else...）
- 更多的巢狀邏輯
- 難以理解和維護

#### 5. **降低可擴展性**
- 新增批次處理模式需要修改單一函數
- 難以支援不同的批次策略
- 違反開閉原則

### **實際案例分析**

目前的拆分設計在以下場景中表現優異：

1. **測試場景**：
   ```python
   # 可以單獨測試初始化
   context = service._initiate_batch_processing(data, context)
   
   # 可以單獨測試協調
   result = service._orchestrate_batch_processing(data, context)
   ```

2. **擴展場景**：
   ```python
   # 可以輕鬆新增不同的批次處理策略
   def _custom_batch_processing(self, data, context):
       # 自定義邏輯
       pass
   ```

3. **錯誤處理場景**：
   ```python
   # 初始化失敗 vs 協調失敗有不同的處理策略
   try:
       result = self._initiate_batch_processing(data, context)
   except Exception as e:
       # 初始化失敗的處理
   
   try:
       result = self._orchestrate_batch_processing(data, context)
   except Exception as e:
       # 協調失敗的處理
   ```

## BatchContext 詳解

### **BatchContext 資料結構**

```python
@dataclass
class BatchContext:
    """批次處理的上下文資訊，包含批次編號、總批次數等處理參數"""
    batch_number: int                    # 當前批次編號 (1-based)
    total_batches: int                   # 總批次數
    start_date: Optional[str] = None     # 開始日期 (range 模式)
    end_date: Optional[str] = None       # 結束日期 (range 模式)
    device_type: Optional[str] = None    # 設備類型過濾
    callback_handler: Optional[Callable] = None  # 下一批次回調函數
    source: str = "unknown"              # 請求來源標識
```

### **各欄位重要性**

#### 1. `batch_number` & `total_batches`
**重要性**: 追蹤處理進度
- `batch_number`: 當前正在處理的批次 (1, 2, 3...)
- `total_batches`: 總共需要處理的批次數

**使用場景**:
- 計算資料範圍: `start_idx = (batch_number - 1) * batch_size`
- 判斷完成狀態: `batch_number >= total_batches`
- 進度報告: `"Processing batch 3 of 10"`

#### 2. `start_date` & `end_date`
**重要性**: 支援日期範圍查詢
- Range 模式的核心參數
- 用於 SQL 查詢和訊息傳遞

**使用場景**:
- SQL 參數: `WHERE date BETWEEN start_date AND end_date`
- Pub/Sub 訊息: 傳遞給下一批次的處理器

#### 3. `device_type`
**重要性**: 設備類型過濾
- 支援 Android/iOS 分離處理
- 業務邏輯的靈活性

#### 4. `callback_handler`
**重要性**: 非同步批次間轉換
- 函數指標，指向下一批次的觸發函數
- 實現事件驅動的批次處理

**使用場景**:
```python
# 在 _initiate_batch_processing 中設定
def publish_next_batch():
    if context.callback_handler:
        return context.callback_handler(context)

# 在 _orchestrate_batch_processing 中呼叫
next_batch_publisher()
```

#### 5. `source`
**重要性**: 追蹤請求來源
- 區分 daily/range 模式
- 支援不同的處理策略和監控

### **BatchContext 的設計模式優勢**

#### 1. **參數封裝**
- 避免長參數列表
- 類型安全 (dataclass)
- 預設值處理

#### 2. **狀態管理**
- 集中管理批次狀態
- 不可變性保障 (可以凍結)
- 序列化支援

#### 3. **依賴注入**
- 透過 callback_handler 實現依賴注入
- 鬆耦合的設計
- 易於測試和模擬

#### 4. **流程控制**
- 支援複雜的批次處理邏輯
- 靈活的回調機制
- 可擴展的處理框架

### **實際應用示例**

```python
# Daily 模式的 BatchContext
daily_context = BatchContext(
    batch_number=1,
    total_batches=5,
    callback_handler=publish_daily_recall,
    source="daily_mode"
)

# Range 模式的 BatchContext
range_context = BatchContext(
    batch_number=2,
    total_batches=10,
    start_date="2025-01-01",
    end_date="2025-01-31",
    device_type="android",
    callback_handler=publish_range_recall,
    source="range_mode"
)
```

這個設計使得批次處理框架具有高度的靈活性、可測試性和可維護性。</content>
<parameter name="filePath">d:\Users\00580097\credolab\Credolab\batch_processing_architecture_analysis.md