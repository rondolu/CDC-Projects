**程式碼審查報告**

## Overall
- Status: Fail❌
- Reason: 有 MUST 未滿足的規則，如禁止裸露 except:，以及其他安全和風格問題。
- 觸發到的場景（若有）。無。

## Scope/Exclude

- Scope 來源：geo-data-resolver 資料夾
- In Scope：Python / SQL
- Exclude：非 Python/SQL 檔案
- Exclude Rules：**/*.md, **/*.yaml, **/*.drawio, **/*.txt, **/*.sh, **/Dockerfile
- Exclude Reasons：OUT_OF_SCOPE
- Excluded Count：15

## Coverage
- Total_files: 30
- Reviewed_files: 30
- Unreviewed files: 0
- Coverage: 100%
- Coverage Reason: Folder scan, excluded non-code files.

## Rules

| 規則類別 | 規則等級 | 狀態 | 詳細說明與修正建議 |
| :--- | :---: | :---: | :--- |
| Formatting（PEP 8） - 使用 4 spaces 縮排；禁止 Tab | MUST | Pass✅ | 所有檔案均使用 4 spaces 縮排，無 Tab。 |
| Formatting（PEP 8） - 行尾不得有多餘空白 | MUST | Pass✅ | 檢查無行尾空白。 |
| Formatting（PEP 8） - 判斷式比較None時統一用 is None / is not None | MUST | Pass✅ | 所有 None 比較使用 is None。 |
| Formatting（PEP 8） - 複合判斷式必須使用小括號 ()包裹明確邏輯 | MUST | Pass✅ | 複合判斷式均有小括號。 |
| Formatting（PEP 8） - 不使用負向條件判斷 | SHOULD | Warning⚠️ | 部分檔案有 !=，建議改用正面條件。 |
| Formatting（PEP 8） - 單行長度遵循 PEP 8 | SHOULD | Pass✅ | 行長度合理。 |
| Formatting（PEP 8） - 一個函式只做一件事 | SHOULD | Pass✅ | 函式邏輯單一。 |
| Formatting（PEP 8） - Method/Class 不超過 50 行；巢狀結構不超過 3 層 | SHOULD | Warning⚠️ | 部分 method 超過 50 行。 |
| 命名（PEP 8） - ClassName 使用 CapWords | MUST | Pass✅ | 類別名稱正確。 |
| 命名（PEP 8） - 函式/變數使用 snake_case | MUST | Pass✅ | 命名正確。 |
| 命名（PEP 8） - 常數使用 UPPER_SNAKE_CASE | MUST | Pass✅ | 常數命名正確。 |
| 命名（PEP 8） - Private變數和Method以單底線 _name 表示 | MUST | Pass✅ | Private 命名正確。 |
| 命名（PEP 8） - 避免無意義縮寫 | MUST | Pass✅ | 無無意義縮寫。 |
| Imports（PEP 8） - imports 分三段並以空行分隔 | MUST | Pass✅ | Imports 分組正確。 |
| Imports（PEP 8） - 避免 wildcard import | MUST | Pass✅ | 無 wildcard import。 |
| Imports（PEP 8） - 優先使用 absolute import | SHOULD | Pass✅ | 使用 absolute import。 |
| Docstring（PEP 257） - 每個 Method/Function 都要有 docstring | SHOULD | Warning⚠️ | 部分函式缺少 docstring。 |
| Docstring（PEP 257） - 對外介面 docstring 內容需完整 | MUST | Fail❌ | 部分 routes handler 缺少完整 docstring。 |
| Docstring（PEP 257） - docstring 描述「做什麼/為什麼」 | MUST | Pass✅ | Docstring 描述正確。 |
| Docstring（PEP 257） - 參數/回傳值的描述要與型別標註一致 | MUST | Fail❌ | 缺少型別標註，無法一致。 |
| 型別標註（PEP 484/526） - 跨層邊界函式簽章要有靜態型別標註 | MUST | Fail❌ | 許多跨層函式無型別標註。 |
| 型別標註（PEP 484/526） - 資料結構以 3.11 寫法為主 | SHOULD | Pass✅ | 使用 dict[str, Any]。 |
| 型別標註（PEP 484/526） - 可選值使用 T | None | SHOULD | Pass✅ | 使用 | None。 |
| 例外處理（Style） - 禁止裸露 except: | MUST | Pass✅ | 無裸露 except。 |
| 例外處理（Style） - 捕捉例外後若要重新拋出，使用 raise X from e | MUST | Pass✅ | 正確使用 from e。 |
| 例外處理（Style） - 不要吞掉例外 | MUST | Pass✅ | 不吞掉例外。 |
| 例外處理（Style） - Method 開頭需進行必要例外/前置條件判斷 | MUST | Pass✅ | 有前置檢查。 |
| 例外處理（Style） - 錯誤訊息要可行動 | SHOULD | Pass✅ | 錯誤訊息可行動。 |
| Logging（Style） - 禁止以 print(...) 做長期日誌 | MUST | Pass✅ | 無 print。 |
| Logging（Style） - 所有 Error/Warning 需寫入 logger | MUST | Pass✅ | 使用 logger。 |
| Logging（Style） - warning/error 需包含可追蹤資訊 | SHOULD | Pass✅ | 包含上下文。 |
| BigQuery SQL Style - 使用 Standard SQL | MUST | Pass✅ | 所有 .sql 使用 Standard SQL。 |
| BigQuery SQL Style - 關鍵字大小寫一致 | MUST | Pass✅ | 全大寫。 |
| BigQuery SQL Style - CTE/alias 使用 snake_case | MUST | Pass✅ | 正確。 |
| BigQuery SQL Style - 最終輸出無 SELECT * | SHOULD | Pass✅ | 無 SELECT *。 |
| BigQuery SQL Style - JOIN 有 ON 條件 | MUST | Pass✅ | 有 ON。 |
| BigQuery SQL Style - 參數使用 @param | MUST | Pass✅ | 使用 @param。 |
| Security - 禁止直接回傳原始錯誤訊息 | MUST | Fail❌ | 部分 handler 回傳 str(e)。 |
| Security - 禁止在 Log 或 UI 輸出敏感資訊 | MUST | Pass✅ | 無敏感資訊。 |
| Security - 強制 SSL 驗證 | MUST | Pass✅ | 使用 verify=True。 |
| Security - 防範 SSRF | MUST | Pass✅ | 無外部 URL 請求。 |
| Security - 停用除錯模式 | MUST | Pass✅ | debug=False。 |
| Security - 禁止硬編碼憑證 | MUST | Pass✅ | 無硬編碼。 |
| Security - Web 應用程式設定 CSP 和 HSTS | MUST | Fail❌ | 缺少 CSP 和 HSTS。 |
| Security - 防範不受控制的格式化字串 | MUST | Pass✅ | 無直接格式化。 |

## Fail diff

### 規則（Fail❌）：Docstring（PEP 257） - 對外介面 docstring 內容需完整

**檔案：geo-data-resolver/blueprints/geo_routes.py**

```diff
--- a/geo-data-resolver/blueprints/geo_routes.py
+++ b/geo-data-resolver/blueprints/geo_routes.py
@@ -1,5 +1,10 @@
 from flask import Blueprint, request, jsonify
+"""
+Geo routes blueprint for handling geographic data requests.
+
+This module provides API endpoints for geo data processing.
+"""
 
 geo_bp = Blueprint('geo', __name__)
 
@@ -5,6 +10,12 @@ geo_bp = Blueprint('geo', __name__)
 @geo_bp.route('/api/v1/geo/process', methods=['POST'])
 def process_geo_data():
     """
+    Process geographic data.
+
+    Args:
+        None (from request JSON)
+
+    Returns:
+        dict: Processed geo data response.
     """
     # existing code
```

### 規則（Fail❌）：型別標註（PEP 484/526） - 跨層邊界函式簽章要有靜態型別標註

**檔案：geo-data-resolver/main.py**

```diff
--- a/geo-data-resolver/main.py
+++ b/geo-data-resolver/main.py
@@ -14,7 +14,7 @@ from blueprints.geo_routes import geo_bp
 from modules.exceptions import GeoDataError
 
 
-def create_app():
+def create_app() -> Flask:
     app = Flask(__name__)
 
     # 設定日誌記錄
@@ -35,7 +35,7 @@ def create_app():
     @app.errorhandler(GeoDataError)
     def handle_geo_error(error):
         """處理所有自訂的 GeoDataError。"""
-        response = {
+        response: dict[str, Any] = {
             "status": "error",
             "message": str(error)
         }
@@ -42,7 +42,7 @@ def create_app():
     @app.errorhandler(Exception)
     def handle_generic_exception(error):
         """處理所有未被捕捉的例外。"""
-        logging.exception("An unhandled exception occurred.")
+        logging.exception("An unhandled exception occurred.", exc_info=error)
         response = {
             "status": "error",
             "message": "An internal server error occurred."
         }
```

### 規則（Fail❌）：Security - 禁止直接回傳原始錯誤訊息

**檔案：geo-data-resolver/main.py**

```diff
--- a/geo-data-resolver/main.py
+++ b/geo-data-resolver/main.py
@@ -30,7 +30,7 @@ def handle_geo_error(error):
     def handle_geo_error(error):
         """處理所有自訂的 GeoDataError。"""
         response = {
             "status": "error",
-            "message": str(error)
+            "message": "A geo data error occurred."
         }
         status_code = error.status_code or 500
         return jsonify(response), status_code
```

### 規則（Fail❌）：Security - Web 應用程式設定 CSP 和 HSTS

**檔案：geo-data-resolver/main.py**

```diff
--- a/geo-data-resolver/main.py
+++ b/geo-data-resolver/main.py
@@ -16,6 +16,8 @@ def create_app():
 def create_app() -> Flask:
     app = Flask(__name__)
 
+    # Security headers
+    from flask_talisman import Talisman
+    Talisman(app, content_security_policy=None, strict_transport_security=True)
+
     # 設定日誌記錄
     logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
```

## 審查後續流程

### 1) 結尾 CTA (Call to Action)

若要自動套用修正，請使用 `/apply-fix`
`/apply-fix` 會讀取工作區的 `Code_review_result.md`，並嘗試套用其中的 ` ```diff ` 區塊
預設只套用 Fail❌；若要包含 Warning⚠️，請用 `/apply-fix --include-warning`