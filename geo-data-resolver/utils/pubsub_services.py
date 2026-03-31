"""

提供統一的發布介面：
- publish_pubsub_message(topic_name, message, project_id=None, attributes=None)

"""

from __future__ import annotations

import json
from typing import Union, Optional, Dict, List
from datetime import datetime
from google.cloud import pubsub_v1
from modules.config import config
from utils.infra_logging import _logger
from modules.exceptions import PubSubError


class PubSubService:

    def __init__(self) -> None:
        self._publisher_client: Optional[pubsub_v1.PublisherClient] = None

    @property
    def publisher_client(self) -> pubsub_v1.PublisherClient:
        """取得 Pub/Sub Publisher 客戶端。"""
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
        """發布訊息到 Pub/Sub 主題。

        Args:
            topic_name: 主題名稱
            message: 要發布的訊息（字串或 dict）
            project_id: 專案 ID，若為 None 則使用配置中的 pubsub_project_id 或 project_id
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
                message_data = json.dumps(message, ensure_ascii=False).encode("utf-8")
            elif isinstance(message, str):
                message_data = message.encode("utf-8")
            else:
                message_data = str(message).encode("utf-8")

            # 發布訊息
            if attributes:
                future = self.publisher_client.publish(topic_path, message_data, **attributes)
            else:
                future = self.publisher_client.publish(topic_path, message_data)

            message_id = future.result(timeout=30)
            return message_id

        except Exception as e:
            _logger.log_text(f"Pub/Sub publish failed: {str(e)}", severity="Error")
            raise PubSubError(f"Pub/Sub 訊息發布失敗: {str(e)}") from e

    def publish_daily_recall(
        self,
        current_batch: int,
    ) -> Optional[str]:
        """發布 daily_recall 訊息以觸發下一批。

        Args:
            current_batch: 目前批次編號

        Returns:
            Optional[str]: 發布的訊息 ID；若發布失敗則為 None
        """
        try:
            next_batch = current_batch + 1

            message = {
                "message_type": "daily_recall",
                "processing_params": {
                    "batch_number": next_batch,
                    "source": "daily_job",
                },
                "timestamp": datetime.now().isoformat(),
            }
            attributes = {"start_date": "", "end_date": ""}
            msg_id = self.publish_pubsub_message(
                topic_name=config.pubsub_geo_topic,
                message=message,
                project_id=config.pubsub_project_id,
                attributes=attributes,
            )
            _logger.log_text(
                f"Published daily recall: batch {next_batch}",
                severity="Info",
            )
            return msg_id
        except Exception as e:
            _logger.log_text(f"Failed to publish daily recall message: {e}", severity="Error")
            return None

    def publish_range_recall(
        self,
        current_batch: int,
        start_date: str,
        end_date: str,
    ) -> Optional[str]:
        """發布 range_recall 訊息以觸發下一批（含日期區間）。

        Args:
            current_batch: 目前批次編號
            start_date: 開始日期
            end_date: 結束日期

        Returns:
            Optional[str]: 發布的訊息 ID；若發布失敗則為 None
        """
        try:
            next_batch = current_batch + 1

            message = {
                "message_type": "range_recall",
                "processing_params": {
                    "batch_number": next_batch,
                    "start_date": start_date,
                    "end_date": end_date,
                    "source": "get_data_range",
                },
                "timestamp": datetime.now().isoformat(),
            }
            attributes = {"start_date": start_date, "end_date": end_date}
            msg_id = self.publish_pubsub_message(
                topic_name=config.pubsub_geo_topic,
                message=message,
                project_id=config.pubsub_project_id,
                attributes=attributes,
            )
            _logger.log_text(
                f"Published range recall: batch {next_batch}",
                severity="Info",
            )
            return msg_id
        except Exception as e:
            _logger.log_text(f"Failed to publish range recall message: {e}", severity="Error")
            return None
    