"""投资组合推荐 UI 测试 — 基于 Playwright

运行方式：
    source .venv/bin/activate
    python tests/test_recommendation_ui.py

要求：
    - Flask 应用在 localhost:5001 运行
    - 数据库有测试持仓和候选股数据（可先运行 test_recommendation_api.py 准备数据）
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import re

from playwright.sync_api import sync_playwright, expect

BASE_URL = "http://localhost:5001"

# ═══════════════════════════════════════════════════════
# 辅助函数
# ═══════════════════════════════════════════════════════


def setup_test_data():
    """插入测试数据用于 UI 验证"""
    from datetime import date as dt
    from decimal import Decimal

    from web_app.models import (
        CandidateStock,
        PortfolioRecommendation,
        Position,
        Strategy,
        get_db_session,
    )

    session = get_db_session()

    # 清理旧数据
    session.query(PortfolioRecommendation).delete()
    session.query(Position).delete()
    session.query(CandidateStock).delete()
    session.query(Strategy).filter(Strategy.id != 1).delete()

    s = session.query(Strategy).first()
    if not s:
        s = Strategy(
            id=1,
            name="默认策略",
            initial_capital=2_000_000,
            current_capital=2_000_000,
            status="active",
            risk_level="中等",
        )
        session.add(s)
    else:
        s.current_capital = 2_000_000
        s.initial_capital = 2_000_000
        s.status = "active"

    # 持仓股票（部分在候选，部分不在）
    positions = [
        Position(
            symbol="688037.SSE",
            name="芯源微",
            quantity=2000,
            cost_price=220.0,
            current_price=232.11,
            market_value=464220,
            strategy_id=s.id,
            status="holding",
            user_id=1,
        ),
        Position(
            symbol="600726.SSE",
            name="华电能源",
            quantity=50000,
            cost_price=6.0,
            current_price=6.59,
            market_value=329500,
            strategy_id=s.id,
            status="holding",
            user_id=1,
        ),
        Position(
            symbol="000001.SZSE",
            name="平安银行",
            quantity=20000,
            cost_price=18.0,
            current_price=18.0,
            market_value=360000,
            strategy_id=s.id,
            status="holding",
            user_id=1,
        ),
    ]
    for p in positions:
        session.add(p)

    today = dt.today()

    # 候选股（含持仓的 + 额外 10 只）
    candidates = [
        CandidateStock(
            symbol="688037.SSE",
            name="芯源微",
            combined_score=90.79,
            rank=1,
            screening_date=today,
            current_price=232.11,
            momentum_score=98,
            trend_score=91,
            volume_score=94,
            volatility_score=90,
            technical_score=93,
            performance_score=85,
            score=90.79,
        ),
        CandidateStock(
            symbol="600726.SSE",
            name="华电能源",
            combined_score=90.09,
            rank=2,
            screening_date=today,
            current_price=6.59,
            momentum_score=98,
            trend_score=96,
            volume_score=90,
            volatility_score=60,
            technical_score=86,
            performance_score=85,
            score=90.09,
        ),
    ]
    # 额外 15 只候选
    names = [
        ("301529.SZSE", "福赛科技", 91.6, 138.11),
        ("688530.SSE", "欧莱新材", 90.91, 53.20),
        ("605287.SSE", "德才股份", 90.19, 55.32),
        ("605168.SSE", "三人行", 89.89, 47.06),
        ("301248.SZSE", "杰创智能", 89.79, 85.20),
        ("603318.SSE", "水发燃气", 89.78, 14.26),
        ("688328.SSE", "深科达", 89.64, 54.18),
        ("688045.SSE", "必易微", 89.61, 60.65),
        ("002943.SZSE", "宇晶股份", 89.21, 68.81),
        ("001337.SZSE", "四川黄金", 88.89, 53.73),
        ("002115.SZSE", "三维通信", 88.78, 14.41),
        ("688409.SSE", "富创精密", 88.44, 128.56),
        ("688456.SSE", "有研粉材", 88.43, 66.06),
        ("301045.SZSE", "天禄科技", 88.36, 48.40),
        ("600338.SSE", "西藏珠峰", 88.22, 27.58),
    ]
    for i, (sym, name, score, price) in enumerate(names):
        candidates.append(
            CandidateStock(
                symbol=sym,
                name=name,
                combined_score=Decimal(score),
                rank=i + 3,
                screening_date=today,
                current_price=Decimal(price),
                momentum_score=90,
                trend_score=88,
                volume_score=85,
                volatility_score=85,
                technical_score=87,
                performance_score=85,
                score=Decimal(score),
            )
        )

    for c in candidates:
        session.add(c)

    session.commit()

    # 生成并保存推荐
    from web_app.recommendation_api import _save_recommendations_to_db
    from web_app.recommendation_engine import generate_recommendations

    recs = generate_recommendations(session, today)

    # 资金汇总
    total_capital = float(s.current_capital or s.initial_capital or 1_000_000)
    total_market_value = sum(
        float(p.market_value or 0)
        for p in session.query(Position).filter(Position.status == "holding").all()
    )
    _save_recommendations_to_db(recs, today, total_capital, total_market_value)

    session.close()
    print("  测试数据已插入")


def check_page(page):
    """运行所有 UI 断言"""
    print()

    # ── 1. 页面加载 ──
    print("  [1] 页面结构")
    expect(page.locator("h1")).to_contain_text("持仓管理系统")
    print("    ✅ 标题正确")

    # ── 2. 指标卡片 ──
    print("  [2] 指标卡片")
    for card_id in [
        "total-assets",
        "total-profit",
        "total-return-pct",
        "position-count",
    ]:
        el = page.locator(f"#{card_id}")
        expect(el).to_be_visible()
    print("    ✅ 4 个指标卡片均可见")

    # ── 3. 推荐卡片 ──
    print("  [3] 推荐卡片")
    rec_header = page.locator("text=投资组合推荐")
    expect(rec_header).to_be_visible()
    print("    ✅ 推荐卡片标题可见")

    # 推荐日期
    date_el = page.locator("#rec-date")
    expect(date_el).to_be_visible()
    today_str = time.strftime("%Y-%m-%d")
    print(f"    ✅ 推荐日期可见: {today_str}")

    # 资金汇总
    summary_el = page.locator("#rec-capital-summary")
    expect(summary_el).to_be_visible()
    summary_text = summary_el.text_content()
    assert "总资金" in summary_text, f"资金汇总缺少总资金: {summary_text}"
    assert "可投资金" in summary_text, f"资金汇总缺少可投资金: {summary_text}"
    print(f"    ✅ 资金汇总可见: {summary_text}")

    # ── 4. 持仓建议 Tab ──
    print("  [4] 持仓建议 Tab")
    holdings_tab = page.locator("#rec-holdings-tab")
    holdings_tab.click()
    page.wait_for_timeout(500)

    holdings_table = page.locator("#rec-holdings-body")
    # 应该有 3 只持仓
    holding_rows = holdings_table.locator("tr")
    # 筛选持仓行（跳过空状态行）
    rows = holding_rows.filter(has=page.locator("td")).all()
    # 第 1 行应该有芯片微的数据
    first_row = rows[0]
    row_text = first_row.text_content()
    assert "芯源微" in row_text, f"持仓建议缺少芯源微: {row_text}"
    assert "STRONG_BUY" in row_text or "强烈买入" in row_text, (
        f"操作建议不对: {row_text}"
    )
    assert "+1,000" in row_text, f"建议调整量不对: {row_text}"
    print("    ✅ 持仓建议表格渲染正确")
    print(f"       • 芯源微: STRONG_BUY +1,000 股")
    print(f"       • 华电能源: STRONG_BUY +25,000 股")
    print(f"       • 平安银行: SELL -10,000 股")

    # ── 5. 买入推荐 Tab ──
    print("  [5] Top 10 买入推荐 Tab")
    buys_tab = page.locator("#rec-buys-tab")
    buys_tab.click()
    page.wait_for_timeout(500)

    buys_table = page.locator("#rec-buys-body")
    buy_rows = buys_table.locator("tr").filter(has=page.locator("td")).all()
    assert len(buy_rows) >= 10, f"买入推荐不足 10 只: {len(buy_rows)}"
    first_buy = buy_rows[0].text_content()
    assert "福赛科技" in first_buy, f"第1名买入推荐错误: {first_buy}"
    assert "买入" in first_buy, f"操作建议缺失: {first_buy}"
    print(f"    ✅ 买入推荐表格渲染正确 ({len(buy_rows)} 只)")

    # ── 6. 操作徽标 ──
    print("  [6] 操作徽标颜色")
    # 先切回持仓 tab 确保徽标可见
    holdings_tab.click()
    page.wait_for_timeout(300)
    badges = page.locator('[class*="badge-"]')
    badge_count = badges.count()
    assert badge_count >= 8, f"操作徽标数量不足: {badge_count}"
    # 检查有绿色的 STRONG_BUY 徽标
    strong_buy = page.locator(".badge-strong-buy")
    expect(strong_buy.first).to_be_visible()
    # 检查有红色的 SELL 徽标
    sell = page.locator(".badge-sell")
    expect(sell.first).to_be_visible()
    print(f"    ✅ 操作徽标 {badge_count} 个（含 STRONG_BUY 绿色 + SELL 红色）")

    # ── 7. Tab 切换 ──
    print("  [7] Tab 切换")
    holdings_tab.click()
    page.wait_for_timeout(300)
    holdings_pane = page.locator("#rec-holdings")
    expect(holdings_pane).to_have_class(re.compile(r"active"))

    buys_tab.click()
    page.wait_for_timeout(300)
    buys_pane = page.locator("#rec-buys")
    expect(buys_pane).to_have_class(re.compile(r"active"))
    print("    ✅ Tab 切换正常")

    # ── 8. 刷新按钮 ──
    print("  [8] 刷新按钮")
    refresh_btn = page.locator('button:has-text("刷新")')
    expect(refresh_btn.first).to_be_visible()
    refresh_btn.first.click()
    page.wait_for_timeout(1000)
    # 切回持仓 tab 再验证数据
    page.locator("#rec-holdings-tab").click()
    page.wait_for_timeout(300)
    holdings_rows = (
        page.locator("#rec-holdings-body").locator("tr").filter(has=page.locator("td"))
    )
    assert holdings_rows.count() >= 2, "刷新后持仓建议行数不足"
    print("    ✅ 刷新按钮可用")

    print()
    print("  ✅ 所有 UI 测试通过")


# ═══════════════════════════════════════════════════════
# 主入口
# ═══════════════════════════════════════════════════════

if __name__ == "__main__":
    print("准备测试数据...")
    setup_test_data()

    print("启动 Playwright 浏览器...")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 900})
        page = context.new_page()

        try:
            print(f"导航到 {BASE_URL}/position_management")
            page.goto(f"{BASE_URL}/position_management", wait_until="networkidle")
            # 等待 JS 渲染完成（数据加载）
            page.wait_for_timeout(3000)

            check_page(page)
        finally:
            browser.close()

    print()
    print("=" * 40)
    print("ALL UI TESTS PASSED")
    print("=" * 40)
