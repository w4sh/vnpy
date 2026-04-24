#!/usr/bin/env python3
"""
Tushare Pro 实时报价服务
使用免费积分层级获取股票/期货实时行情
"""

import tushare as ts
from datetime import datetime
import time


class TushareQuoteService:
    """Tushare Pro 行情服务"""

    # 免费积分配置 (120积分/天)
    FREE_TIER_LIMITS = {
        "daily_requests": 8000,  # 每天8000次请求
        "minute_requests": 500,  # 每分钟500次请求
    }

    def __init__(self, token: str):
        """
        初始化行情服务

        Args:
            token: Tushare Pro API Token
        """
        self.token = token
        ts.set_token(token)
        self.pro = ts.pro_api()
        self.request_count = 0
        self.last_request_time = None

    def _convert_symbol(self, symbol: str) -> str:
        """
        转换股票代码格式
        数据库格式(.SZSE/.SSE) -> Tushare格式(.SZ/.SH)

        Args:
            symbol: 原始股票代码

        Returns:
            转换后的Tushare格式代码
        """
        if ".SZSE" in symbol.upper():
            return symbol.replace(".SZSE", ".SZ")
        elif ".SSE" in symbol.upper():
            return symbol.replace(".SSE", ".SH")
        return symbol

    def _check_rate_limit(self):
        """检查速率限制"""
        now = datetime.now()

        # 重置每日计数
        if self.last_request_time is None or self.last_request_date != now.date():
            self.request_count = 0
            self.last_request_date = now.date()

        # 检查每日限制
        if self.request_count >= self.FREE_TIER_LIMITS["daily_requests"]:
            raise Exception(
                f"已达到每日请求限制 ({self.FREE_TIER_LIMITS['daily_requests']} 次)"
            )

        # 检查每分钟限制
        if self.last_request_time:
            time_diff = (now - self.last_request_time).total_seconds()
            if (
                time_diff < 60
                and self.request_count % self.FREE_TIER_LIMITS["minute_requests"] == 0
            ):
                wait_time = 60 - time_diff
                print(f"接近每分钟限制,等待 {wait_time:.1f} 秒...")
                time.sleep(wait_time)

        self.last_request_time = now
        self.request_count += 1

    def get_stock_quote(self, ts_code: str) -> dict | None:
        """
        获取股票实时行情

        Args:
            ts_code: 股票代码 (格式: 000001.SZ 或 000001.SZSE)

        Returns:
            行情数据字典
        """
        try:
            self._check_rate_limit()

            # 转换代码格式
            tushare_code = self._convert_symbol(ts_code)

            # 获取最新日线数据
            df = self.pro.daily(
                ts_code=tushare_code, trade_date=datetime.now().strftime("%Y%m%d")
            )

            if df.empty:
                # 如果今天没有数据,获取最近一天
                df = self.pro.daily(ts_code=tushare_code)
                df = df.sort_values("trade_date", ascending=False)
                df = df.head(1)

            if not df.empty:
                row = df.iloc[0]
                return {
                    "ts_code": row["ts_code"],
                    "trade_date": row["trade_date"],
                    "open": float(row["open"]),
                    "high": float(row["high"]),
                    "low": float(row["low"]),
                    "close": float(row["close"]),
                    "vol": float(row["vol"]),
                    "amount": float(row["amount"]),
                }

            return None

        except Exception as e:
            print(f"获取 {ts_code} 行情失败: {str(e)}")
            return None

    def get_futures_quote(self, ts_code: str) -> dict | None:
        """
        获取期货实时行情

        Args:
            ts_code: 期货代码 (格式: IF2401.CFFEX)

        Returns:
            行情数据字典
        """
        try:
            self._check_rate_limit()

            # 获取最新日线数据
            df = self.pro.fut_daily(
                ts_code=ts_code, trade_date=datetime.now().strftime("%Y%m%d")
            )

            if df.empty:
                # 如果今天没有数据,获取最近一天
                df = self.pro.fut_daily(ts_code=ts_code)
                df = df.sort_values("trade_date", ascending=False)
                df = df.head(1)

            if not df.empty:
                row = df.iloc[0]
                return {
                    "ts_code": row["ts_code"],
                    "trade_date": row["trade_date"],
                    "open": float(row["open"]),
                    "high": float(row["high"]),
                    "low": float(row["low"]),
                    "close": float(row["close"]),
                    "vol": float(row["vol"]),
                    "amount": float(row["amount"]),
                }

            return None

        except Exception as e:
            print(f"获取 {ts_code} 期货行情失败: {str(e)}")
            return None

    def batch_update_quotes(self, symbols: list[str]) -> dict[str, dict | None]:
        """
        批量更新行情

        Args:
            symbols: 代码列表 (股票或期货)

        Returns:
            {代码: 行情数据} 字典
        """
        results = {}

        for symbol in symbols:
            # 判断是股票还是期货
            # 支持多种格式: .SZ/.SH (Tushare格式), .SZSE/.SSE (数据库格式)
            if (
                ".CF" in symbol.upper()
                or ".SH" in symbol.upper()
                or ".SZ" in symbol.upper()
                or ".SSE" in symbol.upper()
                or ".SZSE" in symbol.upper()
            ):
                quote = self.get_stock_quote(symbol)
            else:
                quote = self.get_futures_quote(symbol)

            results[symbol] = quote

            # 避免请求过快
            time.sleep(0.2)

        return results

    def get_usage_info(self) -> dict:
        """获取当前使用情况"""
        return {
            "token": self.token[:20] + "...",  # 部分隐藏
            "request_count": self.request_count,
            "daily_limit": self.FREE_TIER_LIMITS["daily_requests"],
            "remaining": self.FREE_TIER_LIMITS["daily_requests"] - self.request_count,
            "last_request": self.last_request_time.isoformat()
            if self.last_request_time
            else None,
        }


# 单例实例
_quote_service: TushareQuoteService | None = None


def get_quote_service(token: str = None) -> TushareQuoteService:
    """
    获取行情服务单例

    Args:
        token: Tushare Pro API Token (首次调用时必需)

    Returns:
        TushareQuoteService 实例
    """
    global _quote_service

    if _quote_service is None:
        if token is None:
            raise ValueError("首次调用需要提供 token")
        _quote_service = TushareQuoteService(token)

    return _quote_service
