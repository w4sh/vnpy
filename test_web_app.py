#!/usr/bin/env python3
"""
Web应用功能测试脚本
验证各个API接口是否正常工作
"""

import sys
from pathlib import Path
from datetime import datetime

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))


def test_api_imports():
    """测试API相关导入"""
    print("🔍 测试API导入...")
    try:
        import polars as pl  # noqa: F401

        print("  ✓ Polars导入成功")
    except ImportError as e:
        print(f"  ✗ Polars导入失败: {e}")
        return False

    try:
        from flask import Flask  # noqa: F401

        print("  ✓ Flask导入成功")
    except ImportError as e:
        print(f"  ✗ Flask导入失败: {e}")
        return False

    try:
        from vnpy.alpha import AlphaLab  # noqa: F401

        print("  ✓ AlphaLab导入成功")
    except ImportError as e:
        print(f"  ✗ AlphaLab导入失败: {e}")
        return False

    try:
        from vnpy.alpha.strategy.backtesting import BacktestingEngine  # noqa: F401

        print("  ✓ BacktestingEngine导入成功")
    except ImportError as e:
        print(f"  ✗ BacktestingEngine导入失败: {e}")
        return False

    return True


def test_strategy_imports():
    """测试策略导入"""
    print("\n🔍 测试策略导入...")
    try:
        from scripts.dual_ma_strategy import DualMaStrategy  # noqa: F401

        print("  ✓ 双均线策略导入成功")
    except ImportError as e:
        print(f"  ✗ 双均线策略导入失败: {e}")
        return False

    try:
        from scripts.bollinger_bands_strategy import BollingerBandsStrategy  # noqa: F401

        print("  ✓ 布林带策略导入成功")
    except ImportError as e:
        print(f"  ✗ 布林带策略导入失败: {e}")
        return False

    try:
        from scripts.momentum_strategy import MomentumStrategy  # noqa: F401

        print("  ✓ 动量策略导入成功")
    except ImportError as e:
        print(f"  ✗ 动量策略导入失败: {e}")
        return False

    try:
        from scripts.dual_thrust_strategy import DualThrustStrategy  # noqa: F401

        print("  ✓ Dual Thrust策略导入成功")
    except ImportError as e:
        print(f"  ✗ Dual Thrust策略导入失败: {e}")
        return False

    return True


def test_data_access():
    """测试数据访问"""
    print("\n🔍 测试数据访问...")
    try:
        from vnpy.alpha import AlphaLab  # noqa: F401

        lab = AlphaLab("/Users/w4sh8899/project/vnpy/lab_data")

        # 测试加载数据
        bars = lab.load_bar_data(
            "000001.SZSE", "d", datetime(2020, 1, 1), datetime(2020, 2, 1)
        )
        print(f"  ✓ 数据访问成功，测试数据有 {len(bars)} 条")

        return True
    except Exception as e:
        print(f"  ✗ 数据访问失败: {e}")
        return False


def test_web_app_structure():
    """测试Web应用结构"""
    print("\n🔍 测试Web应用结构...")
    required_files = [
        "web_app/app.py",
        "web_app/templates/index.html",
        "web_app/requirements.txt",
        "start_web.sh",
    ]

    all_exist = True
    for file_path in required_files:
        if Path(file_path).exists():
            print(f"  ✓ {file_path} 存在")
        else:
            print(f"  ✗ {file_path} 不存在")
            all_exist = False

    return all_exist


def main():
    """主测试函数"""
    print("=" * 60)
    print("  vn.py Web应用功能测试")
    print("=" * 60)
    print("")

    results = []

    # 运行各项测试
    results.append(("API导入", test_api_imports()))
    results.append(("策略导入", test_strategy_imports()))
    results.append(("数据访问", test_data_access()))
    results.append(("应用结构", test_web_app_structure()))

    # 显示测试结果
    print("\n" + "=" * 60)
    print("  测试结果汇总")
    print("=" * 60)

    all_passed = True
    for test_name, passed in results:
        status = "✓ 通过" if passed else "✗ 失败"
        print(f"{test_name:12s}: {status}")
        if not passed:
            all_passed = False

    print("=" * 60)

    if all_passed:
        print("🎉 所有测试通过！Web应用已准备就绪。")
        print("")
        print("🚀 启动命令：")
        print("   ./start_web.sh")
        print("")
        print("📱 访问地址：")
        print("   http://localhost:5000")
        print("")
        print("📖 使用文档：")
        print("   docs/web_app_guide.md")
        print("=" * 60)
        return True
    else:
        print("❌ 部分测试失败，请检查错误信息。")
        print("=" * 60)
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
