"""
應用程式自訂例外模組

此模組定義了所有專案中使用的自訂例外類別，以提供更精確的錯誤處理。
"""

class CredolabError(Exception):
    """所有 Credolab 相關錯誤的基礎例外類別。"""
    def __init__(self, message, status_code=None):
        super().__init__(message)
        self.status_code = status_code

class DataValidationError(CredolabError):
    """資料驗證失敗時引發的例外。"""
    def __init__(self, message="Data validation failed"):
        super().__init__(message, status_code=400)

class CredolabAPIError(CredolabError):
    """Credolab API 呼叫失敗時引發的例外。"""
    pass

