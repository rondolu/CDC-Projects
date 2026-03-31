"""
Google Cloud Pub/Sub 服務模組

提供 Pub/Sub 訊息發布的完整功能
"""
from __future__ import annotations

import json
from typing import Union, Optional, Dict, List

from google.cloud import pubsub_v1
from google.api_core import exceptions as api_exceptions
from modules.config import config
from utils.infra_logging import _logger


class PubSubError(Exception):
	"""Raised when a Pub/Sub operation fails."""
	pass


class PubSubService:
	"""Google Cloud Pub/Sub 服務類別"""

	def __init__(self):
		self._publisher_client: Optional[pubsub_v1.PublisherClient] = None

	@property
	def publisher_client(self) -> pubsub_v1.PublisherClient:
		"""取得 Pub/Sub Publisher 客戶端"""
		if self._publisher_client is None:
			self._publisher_client = pubsub_v1.PublisherClient()
		return self._publisher_client

	def publish_pubsub_message(
		self,
		topic_name: str,
		message: Union[str, Dict],
		project_id: Optional[str] = None,
		attributes: Optional[Dict[str, str]] = None,
	) -> str:
		"""發布訊息到 Pub/Sub 主題

		Args:
			topic_name: 主題名稱
			message: 要發布的訊息（字串或 dict）
			project_id: 專案 ID，若為 None 則使用預設
			attributes: 訊息屬性，用於訂閱篩選器

		Returns:
			str: 訊息 ID

		Raises:
			PubSubError: 當發布失敗時
		"""
		if project_id is None:
			project_id = config.pubsub_project_id or config.project_id

		try:
			topic_path = self.publisher_client.topic_path(project_id, topic_name)

			# 轉換訊息為 bytes
			if isinstance(message, dict):
				message_data = json.dumps(message, ensure_ascii=False, default=str).encode("utf-8")
			elif isinstance(message, str):
				message_data = message.encode("utf-8")
			else:
				message_data = str(message).encode("utf-8")

			# 發布訊息
			if attributes:
				future = self.publisher_client.publish(topic_path, message_data, **attributes)
			else:
				future = self.publisher_client.publish(topic_path, message_data)

			message_id = future.result()
			return message_id

		except Exception as e:
			raise PubSubError(f"Pub/Sub 訊息發布失敗: {str(e)}")

	def publish_anonymization(self, file_list: List[str]) -> str:
		"""發布匿名化觸發訊息

		Args:
			file_list: 要處理的檔案列表

		Returns:
			str: 訊息 ID
		"""
		topic_name = "anonymization"
		message = {"file_list": file_list}
		try:
			message_id = self.publish_pubsub_message(topic_name, message)
			print(f"Published anonymization trigger to topic {topic_name}")
			return message_id
		except api_exceptions.PermissionDenied as e:  # 權限問題
			raise PubSubError("PERMISSION DENIED while publishing anonymization trigger") from e
		except api_exceptions.ServiceUnavailable as e:  # 服務不可用
			raise PubSubError("SERVICE UNAVAILABLE while publishing anonymization trigger") from e
		except api_exceptions.DeadlineExceeded as e:
			raise PubSubError("DEADLINE EXCEEDED while publishing anonymization trigger") from e
		except api_exceptions.GoogleAPICallError as e:
			raise PubSubError(f"Google API error while publishing anonymization trigger: {e}") from e
		except Exception as e:
			raise PubSubError(f"Unexpected error while publishing anonymization trigger: {e}") from e

	def publish_credolab_processing_message(self, start_date: str, end_date: str) -> str:
		"""發布 Credolab 處理訊息

		Args:
			start_date: 開始日期 (YYYYMMDD)
			end_date: 結束日期 (YYYYMMDD)

		Returns:
			str: 訊息 ID
		"""
		message = {
			"start_date": start_date,
			"end_date": end_date,
		}
		return self.publish_pubsub_message(config.pubsub_credolab_topic, message)

	def publish_daily_recall_message(
		self,
		current_batch: int,
		attributes: Optional[Dict[str, str]] = None,
	) -> Optional[str]:
		"""
		發布 Daily Job 的回調訊息（start_date, end_date 有 key 但值為空）
		此訊息會被 credolab-sub02 (→ /) 接收

		Args:
			current_batch: 當前已處理的批次數 (從1開始)
			attributes: 訊息屬性字典，如果未提供則使用預設值

		Returns:
			Optional[str]: 訊息 ID 或 None（如果沒有更多批次）
		"""
		try:
			# 檢查參數有效性
			if current_batch <= 0:
				print("Current batch is 0 or negative. Invalid batch number.")
				return None
				
			next_batch = current_batch + 1

			message_data = {
				"message_type": "daily_recall",
				"processing_params": {
					"batch_number": next_batch,
					"source": "daily_job",
				},
			}

			# 有 key 但值為空，會被 credolab-sub02 (→ /) 接收
			# 篩選器: (NOT attributes.start_date OR NOT attributes.end_date)
			if attributes is None:
				attributes = {
					"start_date": "",  # 空值
					"end_date": "",  # 空值
				}

			message_id = self.publish_pubsub_message(
				config.pubsub_credolab_topic, message_data, attributes=attributes
			)

			print(
				f"Published daily recall message: batch {next_batch} "
				f"with empty date values."
			)

			return message_id

		except Exception as e:
			_logger.log_text(f"Failed to publish daily recall message: {str(e)}", severity="Error")
			raise PubSubError(f"Failed to publish daily recall message: {str(e)}")

	def publish_range_recall_message(
		self,
		current_batch: int,
		start_date: str,
		end_date: str,
		attributes: Optional[Dict[str, str]] = None,
	) -> Optional[str]:
		"""
		發布 get_data_range 的回調訊息（start_date, end_date 有 key 且有值）
		此訊息會被 credolab-sub01 (→ /get_data_range) 接收

		Args:
			current_batch: 目前批次號 (從1開始)
			start_date: 開始日期 (YYYY-MM-DD)
			end_date: 結束日期 (YYYY-MM-DD)
			attributes: 訊息屬性字典，如果未提供則使用預設值

		Returns:
			Optional[str]: 訊息 ID 或 None（如果沒有更多批次）
		"""
		try:
			# 檢查參數有效性
			if current_batch <= 0:
				print("Current batch is 0 or negative. Invalid batch number.")
				return None
				
			next_batch = current_batch + 1

			message_data = {
				"message_type": "range_recall",
				"processing_params": {
					"start_date": start_date,
					"end_date": end_date,
					"batch_number": next_batch,
					"source": "get_data_range",
				},
			}

			if attributes is None:
				attributes = {
					"start_date": start_date,
					"end_date": end_date,
				}

			message_id = self.publish_pubsub_message(
				config.pubsub_credolab_topic, message_data, attributes=attributes
			)

			print(
				f"Published range recall message: batch {next_batch} "
				f"from {start_date} to {end_date}."
			)

			return message_id

		except Exception as e:
			_logger.log_text(f"Failed to publish range recall message: {str(e)}", severity="Error")
			raise PubSubError(f"Failed to publish range recall message: {str(e)}")

