
class GeoDataError(Exception):
    """
    Google Maps Geo Data Resolver 基本例外類別
    
    所有應用程式特定的例外都應該繼承此類別。
    """
    
    def __init__(self, message: str, status_code: int = 500):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
    
    def __str__(self):
        return self.message


class DataValidationError(GeoDataError):
    """資料驗證錯誤"""
    
    def __init__(self, message: str):
        super().__init__(f"Data validation error: {message}", 400)


class GoogleMapsAPIError(GeoDataError):
    """Google Maps API 相關錯誤"""
    
    def __init__(self, message: str, status_code: int = 502):
        super().__init__(f"Google Maps API error: {message}", status_code)


class GoogleMapsAPITimeoutError(GoogleMapsAPIError):
    """Google Maps API 超時錯誤"""
    
    def __init__(self, message: str = "Google Maps API request timed out"):
        super().__init__(message, 504)


class GoogleMapsAPIRateLimitError(GoogleMapsAPIError):
    """Google Maps API 速率限制錯誤"""
    
    def __init__(self, message: str = "Google Maps API rate limit exceeded"):
        super().__init__(message, 429)


class PubSubError(GeoDataError):
    """Pub/Sub 相關錯誤"""
    
    def __init__(self, message: str):
        super().__init__(f"Pub/Sub error: {message}", 500)

    
