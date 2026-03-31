"""
輔助函數模組
包含各種共用的輔助功能，包括資料驗證等
"""

from datetime import datetime
from typing import Optional


def validate_date_format(date_string: Optional[str], date_format: str = '%Y-%m-%d') -> bool:
    """
    驗證日期字串格式
    
    Args:
        date_string: 待驗證的日期字串
        date_format: 預期的日期格式
        
    Returns:
        bool: 格式是否正確
    """
    if not date_string:
        return False
        
    try:
        datetime.strptime(date_string, date_format)
        return True
    except (ValueError, TypeError):
        return False

