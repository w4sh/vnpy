"""
因子同步任务的断点恢复管理器。

用于季度/日度因子同步过程中记录已处理标的与批次进度，
支持中断后从断点恢复，避免重复计算。
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)


class CheckpointManager:
    """管理因子同步任务的断点持久化与恢复。"""

    def __init__(
        self, data_dir: str | None = None, task_name: str = "quarterly_sync"
    ) -> None:
        """初始化断点管理器。

        Parameters
        ----------
        data_dir : str or None
            断点文件存储目录，默认使用 ~/.vntrader/factors/checkpoint/
        task_name : str
            任务名称，用于区分不同同步任务（如 quarterly_sync、daily_sync）
        """
        if data_dir is None:
            data_dir = os.path.join(
                os.path.expanduser("~"),
                ".vntrader",
                "factors",
                "checkpoint",
            )
        self.data_dir = Path(data_dir)
        self.task_name = task_name

    def _filepath(self, date_str: str) -> Path:
        """构造指定日期的 checkpoint 文件路径。"""
        return self.data_dir / f"{self.task_name}_{date_str}.json"

    def load(self, date_str: str) -> dict | None:
        """加载指定日期的 checkpoint 文件。

        Parameters
        ----------
        date_str : str
            日期字符串，格式为 YYYYMMDD

        Returns
        -------
        dict or None
            checkpoint 数据字典，文件不存在时返回 None
        """
        filepath = self._filepath(date_str)
        if not filepath.exists():
            logger.debug("Checkpoint 文件不存在: %s", filepath)
            return None

        try:
            with open(filepath, encoding="utf-8") as f:
                data = json.load(f)
            logger.debug(
                "已加载 checkpoint: %s, 批次=%s, 已处理=%d",
                date_str,
                data.get("batch_num"),
                len(data.get("processed", [])),
            )
            return data
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("加载 checkpoint 失败 (%s): %s", filepath, e)
            return None

    def save(
        self,
        date_str: str,
        batch_num: int,
        processed: list[str],
        failed: list[dict],
        status: str,
    ) -> None:
        """保存 checkpoint 数据。

        Parameters
        ----------
        date_str : str
            日期字符串，格式为 YYYYMMDD
        batch_num : int
            当前已完成的批次编号
        processed : list[str]
            已成功处理的 symbol 列表
        failed : list[dict]
            处理失败的 symbol 列表，每项包含 "symbol" 和 "error" 键
        status : str
            任务状态，如 "in_progress"、"completed"、"failed"
        """
        self.data_dir.mkdir(parents=True, exist_ok=True)

        payload: dict = {
            "task": self.task_name,
            "date": date_str,
            "batch_num": batch_num,
            "processed": processed,
            "failed": failed,
            "status": status,
            "updated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        }

        filepath = self._filepath(date_str)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

        logger.info(
            "Checkpoint 已保存: %s, 批次=%d, 已处理=%d, 失败=%d",
            date_str,
            batch_num,
            len(processed),
            len(failed),
        )

    def get_processed(self, date_str: str) -> set[str]:
        """返回指定日期已处理的 symbol 集合。

        Parameters
        ----------
        date_str : str
            日期字符串，格式为 YYYYMMDD

        Returns
        -------
        set[str]
            已处理的 symbol 集合，无 checkpoint 时返回空集
        """
        data = self.load(date_str)
        if data is None:
            return set()
        return set(data.get("processed", []))

    def mark_complete(self, date_str: str) -> None:
        """将指定日期任务的状态标记为 "completed"。

        Parameters
        ----------
        date_str : str
            日期字符串，格式为 YYYYMMDD
        """
        data = self.load(date_str)
        if data is None:
            logger.warning("无法标记完成：checkpoint 不存在 (%s)", date_str)
            return

        data["status"] = "completed"
        data["updated_at"] = (
            datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        )

        filepath = self._filepath(date_str)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        logger.info("任务已完成: %s", date_str)

    def mark_failed(self, date_str: str, error: str) -> None:
        """将指定日期任务的状态标记为 "failed"，并记录错误信息。

        Parameters
        ----------
        date_str : str
            日期字符串，格式为 YYYYMMDD
        error : str
            失败原因描述
        """
        data = self.load(date_str)
        if data is None:
            logger.warning("无法标记失败：checkpoint 不存在 (%s)", date_str)
            return

        data["status"] = "failed"
        data["error"] = error
        data["updated_at"] = (
            datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        )

        filepath = self._filepath(date_str)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        logger.error("任务失败: %s, 原因: %s", date_str, error)
