"""
Google Maps Places Aggregate API Pydantic 模型

定義 API 請求和回應的資料驗證模型
"""

from enum import Enum


class POIScenarioEnum(str, Enum):
    """POI 情境類型列舉"""
    CORPORATE_FINANCE = "corporate_finance"
    RESIDENTIAL = "residential"
    COMMERCIAL = "commercial"