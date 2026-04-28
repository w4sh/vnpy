"""
API 限流器，基于令牌桶算法实现。

用于控制对外部 API（如 Tushare、数据供应商接口）的请求速率，
防止过度调用导致 IP 被封或配额耗尽。

令牌以固定速率（rate_per_minute/分钟）补充到桶中，
桶有最大容量（burst），允许短期突发请求，
同时将长期平均速率控制在设定值以内。
"""

from __future__ import annotations

import logging
import time
from datetime import datetime

logger = logging.getLogger(__name__)


class RateLimiter:
    """基于令牌桶算法的 API 限流器。

    每次请求消耗一定数量的令牌：当桶中令牌充足时立即返回；
    令牌不足时，调用方会被 sleep 阻塞，直到累计了足够令牌。
    """

    def __init__(self, rate_per_minute: int = 200, burst: int | None = None) -> None:
        """初始化限流器。

        Parameters
        ----------
        rate_per_minute : int
            每分钟最大令牌补充数量，默认 200。
        burst : int or None
            桶的最大容量（突发上限）。
            默认取 rate_per_minute 的 10%，且不低于 1。
        """
        self.rate_per_minute: int = rate_per_minute
        self._refill_rate: float = rate_per_minute / 60.0

        if burst is None:
            self._burst: int = max(1, int(rate_per_minute * 0.1))
        else:
            self._burst = burst

        self._tokens: float = float(self._burst)
        self._last_refill: float = time.time()
        self._used_today: int = 0
        self._today: datetime.date = datetime.now().date()

        logger.info(
            "RateLimiter 初始化: rate=%d/min, burst=%d",
            rate_per_minute,
            self._burst,
        )

    # ---- 内部支撑方法 ----

    def _reset_daily_if_needed(self) -> None:
        """如果日期已变更，重置当日使用计数。"""
        today = datetime.now().date()
        if today != self._today:
            self._used_today = 0
            self._today = today

    def _refill(self) -> None:
        """根据自上次补充以来经过的时间，补充令牌到桶中。"""
        self._reset_daily_if_needed()
        now = time.time()
        elapsed = now - self._last_refill
        self._tokens = min(self._burst, self._tokens + elapsed * self._refill_rate)
        self._last_refill = now

    # ---- 公开方法 ----

    def acquire(self) -> None:
        """获取 1 个令牌，令牌不足时 sleep 等待直到有足够令牌。"""
        self.acquire_batch(1)

    def acquire_batch(self, n: int) -> None:
        """批量获取 n 个令牌，令牌不足时 sleep 等待。

        Parameters
        ----------
        n : int
            需要获取的令牌数量。若为 0 或负数则直接返回。
        """
        if n <= 0:
            return

        if n > self._burst:
            logger.warning(
                "请求 %d 个令牌超过桶容量 %d，需等待更长时间",
                n,
                self._burst,
            )

        self._refill()

        if self._tokens >= n:
            self._tokens -= n
            self._used_today += n
            return

        # 令牌不足，计算需要等待的时间
        deficit: float = n - self._tokens
        sleep_time: float = deficit / self._refill_rate
        logger.info(
            "限流等待 %.2fs 以获取 %d 个令牌（缺口: %.2f）",
            sleep_time,
            n,
            deficit,
        )
        time.sleep(sleep_time)

        # 等待后消耗令牌，使用 max 防止浮点误差导致的微小负值
        self._tokens = max(0.0, self._tokens + sleep_time * self._refill_rate - n)
        self._last_refill = time.time()
        self._used_today += n

    def get_stats(self) -> dict[str, int]:
        """返回当前限流器的统计信息。

        Returns
        -------
        dict[str, int]
            包含以下键的字典：
            - used_today: 当日已消耗的令牌总数
            - remaining: 当前桶中剩余令牌数
            - rate_per_minute: 每分钟补充速率
        """
        self._reset_daily_if_needed()
        self._refill()
        return {
            "used_today": self._used_today,
            "remaining": int(self._tokens),
            "rate_per_minute": self.rate_per_minute,
        }
