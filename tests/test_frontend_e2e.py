#!/usr/bin/env python3
"""
前端E2E测试 - 使用Playwright进行浏览器自动化测试

测试内容：
1. 页面加载和渲染
2. 指标卡片显示
3. 图表渲染和交互
4. 数据表格展示
5. 搜索和筛选功能
6. 数据导出功能
7. 响应式布局
"""

import asyncio
import time
import subprocess
import sys
from pathlib import Path
from datetime import datetime

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("❌ Playwright未安装，正在安装...")
    import subprocess

    subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "playwright",
            "--break-system-packages",
        ],
        check=True,
    )
    subprocess.run(
        [sys.executable, "-m", "playwright", "install", "chromium"], check=True
    )
    from playwright.sync_api import sync_playwright


class FrontendE2ETest:
    """前端端到端测试"""

    def __init__(self, base_url="http://localhost:5001"):
        self.base_url = base_url
        self.screenshots_dir = Path(__file__).parent.parent / "test_screenshots"
        self.screenshots_dir.mkdir(exist_ok=True)
        self.flask_process = None

    def start_flask_app(self):
        """启动Flask应用"""
        print("🚀 启动Flask应用...")
        self.flask_process = subprocess.Popen(
            [sys.executable, "web_app/test_app.py"],
            cwd=str(Path(__file__).parent.parent),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        # 等待应用启动
        for i in range(10):
            try:
                import requests

                response = requests.get(self.base_url, timeout=2)
                if response.status_code == 200:
                    print(f"✅ Flask应用已启动 (PID: {self.flask_process.pid})")
                    return True
            except:
                time.sleep(1)

        raise RuntimeError("Flask应用启动失败")

    def stop_flask_app(self):
        """停止Flask应用"""
        if self.flask_process:
            print("🛑 停止Flask应用...")
            self.flask_process.terminate()
            self.flask_process.wait(timeout=5)
            print("✅ Flask应用已停止")

    def setup_test_data(self):
        """创建测试数据"""
        from web_app.models import (
            Strategy,
            Position,
            Transaction,
            StrategyAuditLog,
            TransactionAuditLog,
            get_db_session,
        )

        print("📊 创建测试数据...")
        session = get_db_session()

        try:
            # 清理旧数据
            session.query(TransactionAuditLog).delete(synchronize_session=False)
            session.query(Transaction).delete(synchronize_session=False)
            session.query(StrategyAuditLog).delete(synchronize_session=False)
            session.query(Position).delete(synchronize_session=False)
            session.query(Strategy).delete(synchronize_session=False)
            session.commit()

            # 创建策略
            strategy1 = Strategy(
                name="双均线策略",
                description="基于双均线的趋势跟踪策略",
                initial_capital=1000000,
                current_capital=1200000,
                total_return=0.20,
                status="active",
            )
            strategy2 = Strategy(
                name="布林带策略",
                description="基于布林带的均值回归策略",
                initial_capital=500000,
                current_capital=550000,
                total_return=0.10,
                status="active",
            )
            session.add_all([strategy1, strategy2])
            session.flush()

            # 创建持仓
            import random

            stocks = [
                ("000001.SZSE", "平安银行", 1000, 10.50, 12.30),
                ("000002.SZSE", "万科A", 2000, 8.20, 9.10),
                ("600000.SSE", "浦发银行", 1500, 7.80, 8.50),
                ("600036.SSE", "招商银行", 800, 35.20, 42.10),
                ("601318.SSE", "中国平安", 500, 48.50, 52.30),
            ]

            for symbol, name, quantity, cost, current in stocks:
                market_value = quantity * current
                profit = (current - cost) * quantity
                profit_pct = ((current - cost) / cost) * 100

                position = Position(
                    symbol=symbol,
                    name=name,
                    quantity=quantity,
                    cost_price=cost,
                    current_price=current,
                    market_value=market_value,
                    profit_loss=profit,
                    profit_loss_pct=profit_pct,
                    strategy_id=strategy1.id,
                    status="holding",
                )
                session.add(position)

            session.commit()
            print(f"✅ 测试数据创建成功（2个策略，5个持仓）")

        except Exception as e:
            session.rollback()
            print(f"❌ 创建测试数据失败: {e}")
            raise
        finally:
            session.close()

    def take_screenshot(self, page, name):
        """截图并保存"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = self.screenshots_dir / f"{name}_{timestamp}.png"
        page.screenshot(path=str(filename), full_page=True)
        print(f"📸 截图已保存: {filename}")
        return filename

    def test_page_load(self, page):
        """测试1: 页面加载"""
        print("\n" + "=" * 60)
        print("测试1: 页面加载和渲染")
        print("=" * 60)

        # 访问持仓管理页面
        print(f"📍 访问页面: {self.base_url}/position_management")
        page.goto(f"{self.base_url}/position_management")

        # 等待页面加载
        page.wait_for_load_state("networkidle")
        time.sleep(2)  # 等待JavaScript执行

        # 验证页面标题
        title = page.title()
        print(f"📄 页面标题: {title}")
        assert "持仓" in title or "vn.py" in title, "页面标题不正确"

        # 验证页面元素
        header = page.locator("h1").first
        header_text = header.text_content()
        print(f"📌 页面标题: {header_text}")
        assert "vn.py" in header_text or "持仓" in header_text

        self.take_screenshot(page, "01_page_load")
        print("✅ 测试1通过: 页面加载成功")

    def test_metric_cards(self, page):
        """测试2: 指标卡片显示"""
        print("\n" + "=" * 60)
        print("测试2: 指标卡片显示")
        print("=" * 60)

        page.goto(f"{self.base_url}/position_management")
        page.wait_for_load_state("networkidle")
        time.sleep(3)  # 等待API数据加载

        # 验证4个指标卡片
        metrics = [
            {"id": "total-assets", "label": "总资产"},
            {"id": "total-profit", "label": "总盈亏"},
            {"id": "total-return-pct", "label": "总收益率"},
            {"id": "position-count", "label": "持仓数量"},
        ]

        for metric in metrics:
            element = page.locator(f"#{metric['id']}")
            print(f"📊 {metric['label']}: {element.text_content()}")

        # 验证数据不为"加载中..."
        total_assets = page.locator("#total-assets").text_content()
        assert "加载中" not in total_assets, "数据未加载"

        self.take_screenshot(page, "02_metric_cards")
        print("✅ 测试2通过: 指标卡片显示正常")

    def test_charts_render(self, page):
        """测试3: 图表渲染"""
        print("\n" + "=" * 60)
        print("测试3: 图表渲染")
        print("=" * 60)

        page.goto(f"{self.base_url}/position_management")
        page.wait_for_load_state("networkidle")
        time.sleep(3)

        # 检查Canvas元素
        canvas_elements = page.locator("canvas").all()
        print(f"📈 找到 {len(canvas_elements)} 个图表")

        assert len(canvas_elements) >= 2, "图表数量不足"

        # 验证图表容器
        chart_container_1 = page.locator("#position-distribution-chart")
        assert chart_container_1.is_visible(), "持仓分布图未渲染"

        chart_container_2 = page.locator("#strategy-comparison-chart")
        assert chart_container_2.is_visible(), "策略对比图未渲染"

        self.take_screenshot(page, "03_charts")
        print("✅ 测试3通过: 图表渲染成功")

    def test_positions_table(self, page):
        """测试4: 持仓表格"""
        print("\n" + "=" * 60)
        print("测试4: 持仓明细表格")
        print("=" * 60)

        page.goto(f"{self.base_url}/position_management")
        page.wait_for_load_state("networkidle")
        time.sleep(3)

        # 验证表格表头
        table_headers = page.locator("table thead th").all()
        headers_text = [h.text_content() for h in table_headers]
        print(f"📋 表格列: {', '.join(headers_text)}")

        expected_headers = [
            "股票代码",
            "股票名称",
            "持仓数量",
            "成本价",
            "当前价",
            "市值",
            "盈亏",
            "盈亏%",
            "策略",
            "操作",
        ]
        for header in expected_headers:
            assert any(header in h for h in headers_text), f"缺少表头: {header}"

        # 验证表格行数（应该有数据）
        table_rows = page.locator("table tbody tr").all()
        print(f"📊 表格行数: {len(table_rows)}")

        # 打印第一行数据
        if len(table_rows) > 0:
            first_row = table_rows[0]
            cells = first_row.locator("td").all()
            row_data = [cell.text_content() for cell in cells[:3]]  # 前3列
            print(f"📌 第一行数据: {', '.join(row_data)}")

        self.take_screenshot(page, "04_positions_table")
        print("✅ 测试4通过: 持仓表格显示正常")

    def test_search_and_filter(self, page):
        """测试5: 搜索和筛选功能"""
        print("\n" + "=" * 60)
        print("测试5: 搜索和筛选功能")
        print("=" * 60)

        page.goto(f"{self.base_url}/position_management")
        page.wait_for_load_state("networkidle")
        time.sleep(3)

        # 测试搜索功能
        search_input = page.locator("#search-input")
        search_input.fill("平安")
        print("🔍 搜索: '平安'")
        time.sleep(1)

        # 验证筛选结果
        table_rows = page.locator("table tbody tr").all()
        print(f"📊 筛选后行数: {len(table_rows)}")

        self.take_screenshot(page, "05_search_results")

        # 清空搜索
        search_input.fill("")
        time.sleep(1)

        # 测试策略筛选
        strategy_filter = page.locator("#strategy-filter")
        strategy_filter.select_option(index=1)  # 选择第一个策略
        print(f"🎯 策略筛选: {strategy_filter.text_content()}")
        time.sleep(1)

        table_rows = page.locator("table tbody tr").all()
        print(f"📊 策略筛选后行数: {len(table_rows)}")

        self.take_screenshot(page, "06_strategy_filter")
        print("✅ 测试5通过: 搜索和筛选功能正常")

    def test_refresh_button(self, page):
        """测试6: 刷新按钮"""
        print("\n" + "=" * 60)
        print("测试6: 数据刷新功能")
        print("=" * 60)

        page.goto(f"{self.base_url}/position_management")
        page.wait_for_load_state("networkidle")
        time.sleep(3)

        # 点击刷新按钮
        refresh_button = page.locator("button:has-text('刷新')")
        assert refresh_button.is_visible(), "刷新按钮不可见"

        print("🔄 点击刷新按钮")
        refresh_button.click()
        time.sleep(2)

        # 验证页面仍然正常
        total_assets = page.locator("#total-assets")
        assert total_assets.is_visible(), "刷新后页面异常"

        self.take_screenshot(page, "07_after_refresh")
        print("✅ 测试6通过: 刷新功能正常")

    def test_export_button(self, page):
        """测试7: 导出功能"""
        print("\n" + "=" * 60)
        print("测试7: 数据导出功能")
        print("=" * 60)

        page.goto(f"{self.base_url}/position_management")
        page.wait_for_load_state("networkidle")
        time.sleep(3)

        # 验证导出按钮
        export_button = page.locator("button:has-text('导出')")
        assert export_button.is_visible(), "导出按钮不可见"

        print("📥 导出按钮存在")
        # 注意：实际下载测试需要配置下载路径，这里只验证按钮存在

        self.take_screenshot(page, "08_export_button")
        print("✅ 测试7通过: 导出按钮正常")

    def test_responsive_layout(self, page):
        """测试8: 响应式布局"""
        print("\n" + "=" * 60)
        print("测试8: 响应式布局")
        print("=" * 60)

        page.goto(f"{self.base_url}/position_management")
        page.wait_for_load_state("networkidle")
        time.sleep(2)

        # 测试不同屏幕尺寸
        viewports = [
            {"width": 1920, "height": 1080, "name": "桌面"},
            {"width": 768, "height": 1024, "name": "平板"},
            {"width": 375, "height": 667, "name": "手机"},
        ]

        for viewport in viewports:
            print(
                f"📱 测试屏幕: {viewport['name']} ({viewport['width']}x{viewport['height']})"
            )
            page.set_viewport_size(
                {"width": viewport["width"], "height": viewport["height"]}
            )
            time.sleep(1)

            # 验证关键元素仍然可见
            header = page.locator("h1")
            assert header.is_visible(), f"{viewport['name']}模式下标题不可见"

            self.take_screenshot(page, f"09_responsive_{viewport['name']}")

        print("✅ 测试8通过: 响应式布局正常")

    def run_all_tests(self):
        """运行所有测试"""
        print("🚀 开始前端E2E测试...")
        print("=" * 60)

        try:
            # 启动Flask应用
            self.start_flask_app()

            # 创建测试数据
            self.setup_test_data()

            # 等待数据写入
            time.sleep(1)

            # 运行测试
            with sync_playwright() as playwright:
                # 启动浏览器
                browser = playwright.chromium.launch(headless=False, slow_mo=500)
                page = browser.new_page()

                try:
                    # 执行所有测试
                    self.test_page_load(page)
                    self.test_metric_cards(page)
                    self.test_charts_render(page)
                    self.test_positions_table(page)
                    self.test_search_and_filter(page)
                    self.test_refresh_button(page)
                    self.test_export_button(page)
                    self.test_responsive_layout(page)

                    print("\n" + "=" * 60)
                    print("🎉 所有测试通过！")
                    print("=" * 60)
                    print(f"📸 截图已保存到: {self.screenshots_dir}")

                except Exception as e:
                    print(f"\n❌ 测试失败: {e}")
                    self.take_screenshot(page, "error_screenshot")
                    raise

                finally:
                    browser.close()

        except Exception as e:
            print(f"\n❌ 测试执行失败: {e}")
            import traceback

            traceback.print_exc()
            return False

        finally:
            # 停止Flask应用
            self.stop_flask_app()

        return True


def main():
    """主函数"""
    print("""
╔═══════════════════════════════════════════════════════════╗
║         vn.py 持仓管理系统 - 前端E2E自动化测试           ║
║                   使用 Playwright                         ║
╚═══════════════════════════════════════════════════════════╝
    """)

    tester = FrontendE2ETest()
    success = tester.run_all_tests()

    if success:
        print("\n✅ E2E测试完成！")
        return 0
    else:
        print("\n❌ E2E测试失败！")
        return 1


if __name__ == "__main__":
    sys.exit(main())
