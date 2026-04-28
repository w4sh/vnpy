#!/usr/bin/env python3
"""
Web应用完整功能测试脚本
测试所有API接口和用户交互场景
"""

import sys
import requests
from datetime import datetime
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))


class WebAppTester:
    """Web应用测试类"""

    def __init__(self, base_url="http://localhost:5001"):
        self.base_url = base_url
        self.test_results = []

    def log_test(self, test_name, passed, details=""):
        """记录测试结果"""
        status = "✅ 通过" if passed else "❌ 失败"
        result = {"name": test_name, "passed": passed, "details": details}
        self.test_results.append(result)
        print(f"{status} - {test_name}")
        if details:
            print(f"    详情: {details}")

    def test_1_homepage_access(self):
        """测试1：主页访问"""
        print("\n" + "=" * 60)
        print("测试1：主页访问")
        print("=" * 60)

        try:
            response = requests.get(f"{self.base_url}/", timeout=10)
            if response.status_code == 200:
                self.log_test("主页访问", True, f"状态码: {response.status_code}")
                # 检查是否包含关键内容
                if "vn.py" in response.text or "量化" in response.text:
                    self.log_test("主页内容验证", True, "页面包含预期内容")
                else:
                    self.log_test("主页内容验证", False, "页面内容不符合预期")
            else:
                self.log_test("主页访问", False, f"状态码: {response.status_code}")
        except Exception as e:
            self.log_test("主页访问", False, str(e))

    def test_2_api_strategies(self):
        """测试2：获取策略列表API"""
        print("\n" + "=" * 60)
        print("测试2：策略列表API")
        print("=" * 60)

        try:
            response = requests.get(f"{self.base_url}/api/strategies", timeout=10)
            if response.status_code == 200:
                data = response.json()
                self.log_test(
                    "策略列表API调用", True, f"状态码: {response.status_code}"
                )

                # 验证返回的数据结构
                if "strategies" in data:
                    strategies = data["strategies"]
                    self.log_test(
                        "策略列表结构", True, f"发现 {len(strategies)} 个策略"
                    )

                    # 验证每个策略的字段
                    for strategy in strategies:
                        if all(
                            key in strategy
                            for key in ["key", "name", "description", "params"]
                        ):
                            self.log_test(
                                f"策略 {strategy['key']} 字段完整性",
                                True,
                                f"{strategy['name']}",
                            )
                        else:
                            self.log_test(
                                f"策略 {strategy.get('key', 'unknown')} 字段完整性",
                                False,
                                "缺少必要字段",
                            )
                else:
                    self.log_test("策略列表结构", False, "缺少strategies字段")
            else:
                self.log_test(
                    "策略列表API调用", False, f"状态码: {response.status_code}"
                )
        except Exception as e:
            self.log_test("策略列表API调用", False, str(e))

    def test_3_backtest_single_strategy(self):
        """测试3：单个策略回测"""
        print("\n" + "=" * 60)
        print("测试3：单个策略回测")
        print("=" * 60)

        try:
            payload = {
                "strategies": [
                    {
                        "key": "dual_ma",
                        "params": {"fast_window": 5, "slow_window": 20},
                    }
                ],
                "symbols": ["000001.SZSE"],
                "start_date": "2024-01-01",
                "end_date": "2024-12-31",
                "capital": 1000000,
            }

            print("发送回测请求: 双均线策略 (000001.SZSE)")
            response = requests.post(
                f"{self.base_url}/api/backtest",
                json=payload,
                timeout=120,  # 回测可能需要较长时间
            )

            if response.status_code == 200:
                data = response.json()
                self.log_test(
                    "单个策略回测API调用", True, f"状态码: {response.status_code}"
                )

                if data.get("success"):
                    results = data.get("results", [])
                    if results:
                        result = results[0]
                        self.log_test(
                            "回测结果返回",
                            True,
                            f"策略: {result.get('strategy', 'Unknown')}",
                        )

                        # 验证结果字段
                        required_fields = [
                            "total_return",
                            "annual_return",
                            "max_ddpercent",
                            "sharpe_ratio",
                            "total_trades",
                        ]
                        missing_fields = [f for f in required_fields if f not in result]
                        if not missing_fields:
                            self.log_test(
                                "回测结果字段完整性",
                                True,
                                f"收益率: {result.get('total_return', 0):.2f}%, 夏普比率: {result.get('sharpe_ratio', 0):.2f}",
                            )
                        else:
                            self.log_test(
                                "回测结果字段完整性",
                                False,
                                f"缺少字段: {missing_fields}",
                            )
                    else:
                        self.log_test("回测结果返回", False, "结果为空")
                else:
                    error = data.get("error", "Unknown error")
                    self.log_test("回测执行", False, f"错误: {error}")
            else:
                self.log_test(
                    "单个策略回测API调用", False, f"状态码: {response.status_code}"
                )

        except Exception as e:
            self.log_test("单个策略回测", False, str(e))

    def test_4_backtest_multiple_strategies(self):
        """测试4：多策略组合回测"""
        print("\n" + "=" * 60)
        print("测试4：多策略组合回测")
        print("=" * 60)

        try:
            payload = {
                "strategies": [
                    {"key": "dual_ma", "params": {"fast_window": 5, "slow_window": 20}},
                    {
                        "key": "bollinger",
                        "params": {
                            "ma_window": 20,
                            "std_window": 20,
                            "dev_mult": 2.0,
                        },
                    },
                ],
                "symbols": ["000001.SZSE"],
                "start_date": "2024-01-01",
                "end_date": "2024-12-31",
                "capital": 1000000,
            }

            print("发送组合回测请求: 双均线 + 布林带")
            response = requests.post(
                f"{self.base_url}/api/backtest", json=payload, timeout=180
            )

            if response.status_code == 200:
                data = response.json()
                self.log_test(
                    "多策略回测API调用", True, f"状态码: {response.status_code}"
                )

                if data.get("success"):
                    results = data.get("results", [])
                    if len(results) == 2:
                        self.log_test(
                            "多策略结果数量", True, f"返回了 {len(results)} 个策略结果"
                        )
                    else:
                        self.log_test(
                            "多策略结果数量",
                            False,
                            f"预期2个结果，实际返回 {len(results)} 个",
                        )
                else:
                    error = data.get("error", "Unknown error")
                    self.log_test("多策略回测执行", False, f"错误: {error}")
            else:
                self.log_test(
                    "多策略回测API调用", False, f"状态码: {response.status_code}"
                )

        except Exception as e:
            self.log_test("多策略组合回测", False, str(e))

    def test_5_stock_picking(self):
        """测试5：智能选股功能"""
        print("\n" + "=" * 60)
        print("测试5：智能选股功能")
        print("=" * 60)

        try:
            payload = {
                "strategy": "oversold",
                "top_n": 10,
                "min_price": 5.0,
                "max_price": 100.0,
                "min_volume": 5000000,
                "ma_window": 20,
                "std_window": 20,
                "dev_mult": 2.0,
            }

            print("发送选股请求: 超卖策略")
            response = requests.post(
                f"{self.base_url}/api/pick_stocks", json=payload, timeout=60
            )

            if response.status_code == 200:
                data = response.json()
                self.log_test("选股API调用", True, f"状态码: {response.status_code}")

                if data.get("success"):
                    results = data.get("results", [])
                    self.log_test("选股结果返回", True, f"发现 {len(results)} 只股票")

                    if results:
                        # 验证结果字段
                        required_fields = [
                            "symbol",
                            "price",
                            "volume",
                            "bb_position",
                            "score",
                        ]
                        sample = results[0]
                        missing_fields = [f for f in required_fields if f not in sample]
                        if not missing_fields:
                            self.log_test(
                                "选股结果字段完整性",
                                True,
                                f"示例: {sample['symbol']} 价格:{sample['price']:.2f} 得分:{sample['score']:.2f}",
                            )
                        else:
                            self.log_test(
                                "选股结果字段完整性",
                                False,
                                f"缺少字段: {missing_fields}",
                            )
                else:
                    error = data.get("error", "Unknown error")
                    self.log_test("选股执行", False, f"错误: {error}")
            else:
                self.log_test("选股API调用", False, f"状态码: {response.status_code}")

        except Exception as e:
            self.log_test("智能选股功能", False, str(e))

    def test_6_strategy_comparison(self):
        """测试6：策略对比功能"""
        print("\n" + "=" * 60)
        print("测试6：策略对比功能")
        print("=" * 60)

        try:
            payload = {
                "strategies": ["dual_ma", "bollinger", "momentum"],
                "symbols": ["000001.SZSE"],
                "start_date": "2024-01-01",
                "end_date": "2024-12-31",
            }

            print("发送策略对比请求: 3个策略")
            response = requests.post(
                f"{self.base_url}/api/compare_strategies", json=payload, timeout=180
            )

            if response.status_code == 200:
                data = response.json()
                self.log_test(
                    "策略对比API调用", True, f"状态码: {response.status_code}"
                )

                if data.get("success"):
                    results = data.get("results", [])
                    if len(results) == 3:
                        self.log_test(
                            "对比结果数量", True, f"返回了 {len(results)} 个策略对比"
                        )

                        # 分析最佳策略
                        best_return = max(
                            results, key=lambda x: x.get("annual_return", 0)
                        )
                        self.log_test(
                            "最佳收益策略识别",
                            True,
                            f"{best_return.get('strategy')}: {best_return.get('annual_return', 0):.2f}%",
                        )
                    else:
                        self.log_test(
                            "对比结果数量",
                            False,
                            f"预期3个结果，实际返回 {len(results)} 个",
                        )
                else:
                    error = data.get("error", "Unknown error")
                    self.log_test("策略对比执行", False, f"错误: {error}")
            else:
                self.log_test(
                    "策略对比API调用", False, f"状态码: {response.status_code}"
                )

        except Exception as e:
            self.log_test("策略对比功能", False, str(e))

    def test_7_error_handling(self):
        """测试7：错误处理"""
        print("\n" + "=" * 60)
        print("测试7：错误处理和边界条件")
        print("=" * 60)

        # 测试无效的策略键
        try:
            payload = {
                "strategies": [{"key": "invalid_strategy"}],
                "symbols": ["000001.SZSE"],
                "start_date": "2024-01-01",
                "end_date": "2024-12-31",
            }

            response = requests.post(
                f"{self.base_url}/api/backtest", json=payload, timeout=30
            )
            self.log_test(
                "无效策略处理",
                response.status_code == 200,
                f"状态码: {response.status_code}",
            )
        except Exception as e:
            self.log_test("无效策略处理", False, str(e))

        # 测试无效的日期格式
        try:
            payload = {
                "strategies": [{"key": "dual_ma"}],
                "symbols": ["000001.SZSE"],
                "start_date": "invalid-date",
                "end_date": "2024-12-31",
            }

            response = requests.post(
                f"{self.base_url}/api/backtest", json=payload, timeout=30
            )
            self.log_test(
                "无效日期处理",
                response.status_code in [200, 400],
                f"状态码: {response.status_code}",
            )
        except Exception as e:
            self.log_test("无效日期处理", False, str(e))

    def test_8_parameter_validation(self):
        """测试8：参数验证"""
        print("\n" + "=" * 60)
        print("测试8：参数验证和边界测试")
        print("=" * 60)

        # 测试极端参数值
        try:
            payload = {
                "strategies": [
                    {
                        "key": "dual_ma",
                        "params": {"fast_window": 100, "slow_window": 200},
                    }
                ],
                "symbols": ["000001.SZSE"],
                "start_date": "2024-01-01",
                "end_date": "2024-01-31",  # 短时间范围
                "capital": 1000000,
            }

            response = requests.post(
                f"{self.base_url}/api/backtest", json=payload, timeout=60
            )
            self.log_test(
                "极端参数处理",
                response.status_code == 200,
                f"状态码: {response.status_code}",
            )
        except Exception as e:
            self.log_test("极端参数处理", False, str(e))

    def print_summary(self):
        """打印测试总结"""
        print("\n" + "=" * 60)
        print("  测试总结报告")
        print("=" * 60)

        total_tests = len(self.test_results)
        passed_tests = sum(1 for r in self.test_results if r["passed"])
        failed_tests = total_tests - passed_tests

        print(f"\n总测试数: {total_tests}")
        print(f"✅ 通过: {passed_tests}")
        print(f"❌ 失败: {failed_tests}")
        print(f"通过率: {passed_tests / total_tests * 100:.1f}%")

        if failed_tests > 0:
            print("\n失败的测试:")
            for result in self.test_results:
                if not result["passed"]:
                    print(f"  ❌ {result['name']}")
                    if result["details"]:
                        print(f"      {result['details']}")

        print("\n" + "=" * 60)

        return failed_tests == 0


def main():
    """主测试函数"""
    print("=" * 60)
    print("  vn.py Web应用完整功能测试")
    print("=" * 60)
    print(f"测试时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("测试地址: http://localhost:5001")

    # 创建测试实例
    tester = WebAppTester()

    # 执行所有测试
    tester.test_1_homepage_access()
    tester.test_2_api_strategies()
    tester.test_3_backtest_single_strategy()
    tester.test_4_backtest_multiple_strategies()
    tester.test_5_stock_picking()
    tester.test_6_strategy_comparison()
    tester.test_7_error_handling()
    tester.test_8_parameter_validation()

    # 打印总结
    all_passed = tester.print_summary()

    if all_passed:
        print("🎉 所有测试通过！Web应用功能完整。")
        return 0
    else:
        print("⚠️  部分测试失败，请检查详细信息。")
        return 1


if __name__ == "__main__":
    success = main()
    sys.exit(success)
