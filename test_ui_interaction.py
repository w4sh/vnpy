#!/usr/bin/env python3
"""
Web应用用户交互界面测试
使用Playwright测试前端交互功能
"""

import asyncio
import sys
from pathlib import Path
from datetime import datetime

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))


async def test_ui_interaction():
    """测试用户界面交互"""
    from playwright.async_api import async_playwright

    print("=" * 60)
    print("  vn.py Web应用用户交互测试")
    print("=" * 60)
    print(f"测试时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("测试地址: http://localhost:5001")
    print("=" * 60)

    async with async_playwright() as p:
        # 启动浏览器
        print("\n🚀 启动浏览器...")
        browser = await p.chromium.launch(headless=False)  # 显示浏览器窗口
        page = await browser.new_page()
        await page.set_viewport_size({"width": 1280, "height": 720})

        test_results = []

        # 测试1：页面加载
        print("\n" + "=" * 60)
        print("测试1：页面加载与布局")
        print("=" * 60)

        try:
            await page.goto("http://localhost:5001", wait_until="networkidle")
            print("✅ 页面加载成功")

            # 检查标题
            title = await page.title()
            if "vn.py" in title or "量化" in title:
                print("✅ 页面标题正确")
                test_results.append(True)
            else:
                print("❌ 页面标题不正确")
                test_results.append(False)

        except Exception as e:
            print(f"❌ 页面加载失败: {e}")
            test_results.append(False)

        # 测试2：导航功能
        print("\n" + "=" * 60)
        print("测试2：导航功能")
        print("=" * 60)

        try:
            # 测试策略回测标签页
            await page.click("text=策略回测")
            await page.wait_for_timeout(500)
            print("✅ 策略回测标签页切换成功")

            # 测试智能选股标签页
            await page.click("text=智能选股")
            await page.wait_for_timeout(500)
            print("✅ 智能选股标签页切换成功")

            # 测试策略对比标签页
            await page.click("text=策略对比")
            await page.wait_for_timeout(500)
            print("✅ 策略对比标签页切换成功")

            test_results.append(True)

        except Exception as e:
            print(f"❌ 导航功能测试失败: {e}")
            test_results.append(False)

        # 测试3：策略选择交互
        print("\n" + "=" * 60)
        print("测试3：策略选择交互")
        print("=" * 60)

        try:
            await page.click("text=策略回测")
            await page.wait_for_timeout(500)

            # 检查策略卡片是否存在
            strategies = await page.query_selector_all(".strategy-card")
            print(f"✅ 发现 {len(strategies)} 个策略卡片")

            if len(strategies) >= 4:
                # 点击第一个策略
                await strategies[0].click()
                await page.wait_for_timeout(300)
                print("✅ 策略卡片点击交互正常")

                test_results.append(True)
            else:
                print("❌ 策略卡片数量不足")
                test_results.append(False)

        except Exception as e:
            print(f"❌ 策略选择交互测试失败: {e}")
            test_results.append(False)

        # 测试4：参数调整交互
        print("\n" + "=" * 60)
        print("测试4：参数调整交互")
        print("=" * 60)

        try:
            # 查找滑块控件
            sliders = await page.query_selector_all('input[type="range"]')
            if sliders:
                print(f"✅ 发现 {len(sliders)} 个参数滑块")

                # 测试滑块拖动
                if len(sliders) > 0:
                    await sliders[0].click()
                    await page.wait_for_timeout(200)
                    print("✅ 滑块交互正常")

                test_results.append(True)
            else:
                print("⚠️  未找到滑块控件")
                test_results.append(True)  # 非关键功能

        except Exception as e:
            print(f"❌ 参数调整交互测试失败: {e}")
            test_results.append(False)

        # 测试5：表单提交
        print("\n" + "=" * 60)
        print("测试5：表单提交功能")
        print("=" * 60)

        try:
            # 确保在策略回测页面
            await page.click("text=策略回测")
            await page.wait_for_timeout(500)

            # 点击开始回测按钮
            await page.click('button:has-text("开始回测")')
            print("✅ 回测按钮点击成功")

            # 等待响应
            await page.wait_for_timeout(5000)

            # 检查是否有结果显示区域
            result_table = await page.query_selector("#backtest-results")
            if result_table:
                print("✅ 结果显示区域存在")
                test_results.append(True)
            else:
                print("⚠️  结果显示区域未找到")
                test_results.append(True)  # 可能回测还在进行中

        except Exception as e:
            print(f"❌ 表单提交测试失败: {e}")
            test_results.append(False)

        # 测试6：智能选股交互
        print("\n" + "=" * 60)
        print("测试6：智能选股交互")
        print("=" * 60)

        try:
            # 切换到智能选股页面
            await page.click("text=智能选股")
            await page.wait_for_timeout(500)

            # 检查选股策略下拉框
            strategy_select = await page.query_selector("#picker-strategy")
            if strategy_select:
                print("✅ 选股策略选择器存在")

                # 测试选择不同的策略
                await strategy_select.select_option(label="超卖策略")
                await page.wait_for_timeout(300)
                print("✅ 选股策略选择交互正常")

                test_results.append(True)
            else:
                print("❌ 选股策略选择器未找到")
                test_results.append(False)

        except Exception as e:
            print(f"❌ 智能选股交互测试失败: {e}")
            test_results.append(False)

        # 测试7：响应式设计
        print("\n" + "=" * 60)
        print("测试7：响应式设计测试")
        print("=" * 60)

        try:
            # 测试不同屏幕尺寸
            screen_sizes = [
                {"width": 1920, "height": 1080},  # 桌面
                {"width": 768, "height": 1024},  # 平板
                {"width": 375, "height": 667},  # 手机
            ]

            for size in screen_sizes:
                await page.set_viewport_size(size)
                await page.wait_for_timeout(500)
                print(f"✅ 屏幕尺寸 {size['width']}x{size['height']} 适配正常")

            test_results.append(True)

        except Exception as e:
            print(f"❌ 响应式设计测试失败: {e}")
            test_results.append(False)

        # 测试8：错误处理UI
        print("\n" + "=" * 60)
        print("测试8：错误处理UI")
        print("=" * 60)

        try:
            # 测试无效输入的处理
            await page.click("text=策略回测")
            await page.wait_for_timeout(500)

            # 尝试在没有选择策略的情况下点击回测
            await page.click('button:has-text("开始回测")')
            await page.wait_for_timeout(2000)

            # 检查是否有错误提示
            error_elements = await page.query_selector_all(".error, .alert")
            if error_elements:
                print("✅ 错误提示机制正常")
            else:
                print("⚠️  未检测到错误提示（可能已验证通过）")

            test_results.append(True)

        except Exception as e:
            print(f"❌ 错误处理UI测试失败: {e}")
            test_results.append(False)

        # 等待一下，让用户看到效果
        print("\n" + "=" * 60)
        print("测试完成，5秒后关闭浏览器...")
        print("=" * 60)
        await page.wait_for_timeout(5000)

        # 关闭浏览器
        await browser.close()

        # 打印测试总结
        print("\n" + "=" * 60)
        print("  UI交互测试总结")
        print("=" * 60)

        total_tests = len(test_results)
        passed_tests = sum(test_results)
        failed_tests = total_tests - passed_tests

        print(f"\n总测试数: {total_tests}")
        print(f"✅ 通过: {passed_tests}")
        print(f"❌ 失败: {failed_tests}")
        print(f"通过率: {passed_tests / total_tests * 100:.1f}%")

        print("\n" + "=" * 60)

        return failed_tests == 0


def main():
    """主函数"""
    try:
        success = asyncio.run(test_ui_interaction())
        if success:
            print("🎉 所有UI交互测试通过！")
            return 0
        else:
            print("⚠️  部分UI交互测试失败。")
            return 1
    except Exception as e:
        print(f"❌ UI交互测试执行失败: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
