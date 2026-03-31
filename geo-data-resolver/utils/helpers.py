"""
通用的小工具函式。

"""

from typing import Optional, Tuple


def validate_and_convert_coordinates(
	latitude: object,
	longitude: object,
) -> bool:
	"""
	驗證經緯度。

	"""

	# None 檢查
	if latitude is None or longitude is None:
		return False

	if latitude.lower() == "null" or longitude.lower() == "null":
		return False

	return True
