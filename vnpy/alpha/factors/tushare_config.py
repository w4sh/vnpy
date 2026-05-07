"""
Tushare Token 集中管理

职责:
  - _load_token(): 从环境变量/.env 文件读取 Tushare token
  - get_pro_api(): 线程安全的懒加载单例 pro_api 实例
  - check_api_access(): 诊断当前 token 可用的 API 列表

不引入外部依赖（python-dotenv），手动解析 .env 文件即可。
"""

from __future__ import annotations

import logging
import os
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_ENV_KEY = "TUSHARE_TOKEN"


def _load_token() -> str:
    """从环境变量或 .env 文件加载 Tushare token

    优先级: 环境变量 TUSHARE_TOKEN > $(pwd)/.env > ~/.env

    抛出:
        RuntimeError: 未找到 token
    """
    token = os.environ.get(_ENV_KEY, "").strip()
    if token:
        return token

    # 尝试从项目根 .env 文件加载
    env_candidates = [
        Path.cwd() / ".env",
        Path.home() / ".env",
    ]
    for env_file in env_candidates:
        if not env_file.exists():
            continue
        try:
            for line in env_file.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line.startswith("#") or "=" not in line:
                    continue
                key, *rest = line.split("=", 1)
                if key.strip() == _ENV_KEY:
                    token = rest[0].strip().strip("'").strip('"')
                    if token:
                        # 缓存到环境变量，避免重复读取文件
                        os.environ[_ENV_KEY] = token
                        return token
        except OSError:
            continue

    raise RuntimeError(
        f"未找到 Tushare token。请设置 {_ENV_KEY} 环境变量，"
        "或在当前目录/用户目录创建 .env 文件，"
        f"内容: {_ENV_KEY}=your_token_here"
    )


_pro_api_lock = threading.Lock()
_pro_api_instance: Any = None


def get_pro_api():
    """获取 Tushare Pro API 实例（线程安全懒加载单例）

    首次调用时加载 token 并创建 pro_api 实例，后续调用返回同一个实例。
    避免重复 set_token 可能导致的 token 竞态问题。

    返回:
        tushare.pro.client.DataApi 实例
    """
    global _pro_api_instance

    if _pro_api_instance is not None:
        return _pro_api_instance

    with _pro_api_lock:
        if _pro_api_instance is not None:
            return _pro_api_instance

        import tushare as ts

        token = _load_token()
        logger.info(
            "初始化 Tushare pro_api (token 前缀: %s...%s)",
            token[:4],
            token[-4:],
        )
        ts.set_token(token)
        _pro_api_instance = ts.pro_api()
        return _pro_api_instance


def _reset_pro_api():
    """重置 pro_api 实例（仅用于测试）"""
    global _pro_api_instance
    with _pro_api_lock:
        _pro_api_instance = None


@dataclass
class AccessCheckResult:
    """API 权限检测结果"""

    token_prefix: str
    accessible_apis: list[str]
    blocked_apis: list[tuple[str, str]]  # (api_name, error_message)
    suggestions: list[str]


def check_api_access(api_names: list[str] | None = None) -> AccessCheckResult:
    """检测当前 token 对指定 API 的访问权限

    参数:
        api_names: 要测试的 API 名列表，None 表示默认列表

    返回:
        AccessCheckResult 包含权限检测结果
    """
    if api_names is None:
        api_names = [
            "daily",
            "daily_basic",
            "fina_indicator",
            "income",
            "balancesheet",
            "hk_hold",
        ]

    pro = get_pro_api()
    token = _load_token()

    accessible: list[str] = []
    blocked: list[tuple[str, str]] = []

    for api_name in api_names:
        try:
            method = getattr(pro, api_name, None)
            if method is None:
                blocked.append((api_name, f"API 方法不存在: pro.{api_name}"))
                continue

            # 使用最小化参数调用，检测权限
            if api_name == "daily":
                result = pro.daily(trade_date="20250101", limit=1)
            elif api_name == "daily_basic":
                result = pro.daily_basic(trade_date="20250101", limit=1)
            elif api_name == "fina_indicator":
                result = pro.fina_indicator(ts_code="000001.SZ", limit=1)
            elif api_name == "income":
                result = pro.income(ts_code="000001.SZ", limit=1)
            elif api_name == "balancesheet":
                result = pro.balancesheet(ts_code="000001.SZ", limit=1)
            elif api_name == "hk_hold":
                result = pro.hk_hold(trade_date="20250101", limit=1)
            else:
                result = method(limit=1)

            if result is not None and len(result) > 0:
                accessible.append(api_name)
                logger.info("  ✓ %s: 正常返回 %d 条数据", api_name, len(result))
            else:
                accessible.append(api_name)
                logger.info("  ✓ %s: 正常返回 (空结果)", api_name)

        except Exception as e:
            error_msg = str(e)
            blocked.append((api_name, error_msg))
            logger.warning("  ✗ %s: %s", api_name, error_msg)

    suggestions: list[str] = []
    if blocked:
        suggestions.append(
            "部分 API 无权限，请检查 Tushare 积分是否达到各 API 最低要求。"
        )
        suggestions.append("积分与权限对照: https://tushare.pro/document/1?doc_id=108")
        # 检测是否是严格的 2000 积分场景（daily_basic 需要 2000 起）
        blocked_names = {name for name, _ in blocked}
        if "daily_basic" in blocked_names and "fina_indicator" in accessible:
            suggestions.append(
                "发现 fina_indicator 可用但 daily_basic 不可用，"
                "请确认 Tushare 积分是否确实 >= 2000（而非正好 2000 边界）。"
                "可尝试在 Tushare 官网重新激活 API 权限。"
            )

    return AccessCheckResult(
        token_prefix=token[:4] + "..." + token[-4:],
        accessible_apis=accessible,
        blocked_apis=blocked,
        suggestions=suggestions,
    )
