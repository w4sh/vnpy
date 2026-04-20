#!/usr/bin/env python3
"""
持仓价格自动更新服务
定期从Tushare Pro获取最新行情并更新数据库
"""

import sys
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from data_feed.quote_service import get_quote_service
from models import Position, get_db_session
from datetime import datetime
import argparse


def update_position_prices(token: str, dry_run: bool = False):
    """
    更新所有持仓的当前价格

    Args:
        token: Tushare Pro API Token
        dry_run: 是否只模拟运行,不实际更新数据库
    """
    session = get_db_session()

    try:
        # 获取所有持仓中的股票代码
        positions = session.query(Position).filter(Position.status == "holding").all()

        if not positions:
            print("没有需要更新的持仓")
            return

        print(f"找到 {len(positions)} 个持仓")

        # 提取所有代码
        symbols = list(set([p.symbol for p in positions]))
        print(f"需要更新 {len(symbols)} 个标的的行情")

        # 获取行情服务
        quote_service = get_quote_service(token)

        # 批量获取行情
        print("正在获取最新行情...")
        quotes = quote_service.batch_update_quotes(symbols)

        # 更新持仓
        updated_count = 0
        for position in positions:
            quote = quotes.get(position.symbol)

            if quote and quote.get("close"):
                new_price = quote["close"]
                old_price = float(position.current_price or 0)

                # 更新字段(处理Decimal类型转换)
                cost_price = float(position.cost_price)
                position.current_price = new_price
                position.market_value = new_price * position.quantity
                position.profit_loss = position.market_value - (
                    cost_price * position.quantity
                )
                position.profit_loss_pct = (
                    (position.profit_loss / (cost_price * position.quantity)) * 100
                    if cost_price > 0
                    else 0
                )
                position.update_time = datetime.now()

                updated_count += 1

                price_change = (
                    ((new_price - old_price) / old_price * 100) if old_price > 0 else 0
                )
                print(
                    f"✓ {position.symbol}: {old_price:.2f} → {new_price:.2f} "
                    f"({price_change:+.2f}%)"
                )

        if not dry_run:
            session.commit()
            print(f"\n成功更新 {updated_count} 个持仓")
        else:
            session.rollback()
            print(f"\n[模拟运行] 将更新 {updated_count} 个持仓")

        # 显示使用情况
        usage = quote_service.get_usage_info()
        print(f"\nAPI使用情况:")
        print(f"  本次请求: {usage['request_count']} 次")
        print(f"  剩余额度: {usage['remaining']} 次")
        print(f"  每日限额: {usage['daily_limit']} 次")

    except Exception as e:
        session.rollback()
        print(f"更新失败: {str(e)}")
        raise

    finally:
        session.close()


def main():
    """命令行入口"""
    parser = argparse.ArgumentParser(description="更新持仓价格")
    parser.add_argument(
        "--token",
        type=str,
        default="8338d9ae4c26c3ec32cffbd1b337d97228c22ba84cea0996410513bb",
        help="Tushare Pro API Token",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="模拟运行,不实际更新数据库"
    )

    args = parser.parse_args()

    print("=" * 60)
    print("持仓价格更新服务")
    print("=" * 60)

    update_position_prices(args.token, args.dry_run)

    print("\n" + "=" * 60)
    print("更新完成")
    print("=" * 60)


if __name__ == "__main__":
    main()
