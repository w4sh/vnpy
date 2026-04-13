# 股指期货数据源方案对比

**更新时间**：2026-04-13
**目标**：获取 IF/IH/IC 股指期货 5 年历史数据（日线）

---

## 📊 数据源方案对比

### 1️⃣ **Tushare（当前使用）**

#### 基本信息
- **类型**：专业金融数据服务
- **官网**：https://tushare.pro
- **Token**：已配置（免费账号）
- **Python库**：`pip install tushare`

#### 优势
✅ 数据质量高，权威性强
✅ 文档完善，社区活跃
✅ 支持多种金融产品（股票、期货、基金等）
✅ 数据字段完整（OHLCV + 持仓量）
✅ 历史数据跨度长

#### 劣势
❌ **免费账号频率限制严重**：20次/分钟
❌ 下载 5 年数据需要 **2-3 小时**
❌ 需要注册账号并获取 Token
❌ 免费账号有每日调用次数限制

#### 频率限制详情
```
免费账号：
- fut_daily 接口：20 次/分钟
- fut_basic 接口：10 次/天
- 适合：偶尔下载、个人学习

付费账号：
- 根据等级不同，频率限制提升
- 价格：360元/年起步
- 适合：量化交易、商业用途
```

#### 代码示例
```python
import tushare as ts

# 设置 Token
ts.set_token("YOUR_TOKEN")
pro = ts.pro_api()

# 下载股指期货日线数据
df = pro.fut_daily(
    ts_code="IF2412.CFX",  # 合约代码
    start_date="20200413",
    end_date="20250413"
)
```

#### 适用场景
- ✅ 需要高质量历史数据
- ✅ 数据准确性要求高
- ✅ 愿意等待长时间下载
- ❌ 需要快速获取数据

---

### 2️⃣ **AKShare（推荐）**

#### 基本信息
- **类型**：开源 Python 库（基于新浪财经等数据源）
- **GitHub**：https://github.com/akfamily/akshare
- **文档**：https://akshare.akfamily.xyz
- **Python库**：`pip install akshare`
- **Star数**：15k+（非常活跃）

#### 优势
✅ **完全免费，无频率限制**
✅ 数据源丰富（新浪、东方财富等）
✅ 一行代码获取连续合约数据
✅ 支持实时行情和历史数据
✅ 社区活跃，文档详细
✅ **下载速度快**：5年数据只需 **5-10 分钟**

#### 劣势
❌ 数据质量可能略低于 Tushare
❌ 依赖第三方数据源（新浪财经）
❌ 数据源可能不稳定

#### 核心接口
```python
import akshare as ak

# 获取沪深300连续合约数据（推荐）
df = ak.futures_zh_daily_sina(symbol="IF99", adjust="0")

# 获取上证50连续合约数据
df = ak.futures_zh_daily_sina(symbol="IH99", adjust="0")

# 获取中证500连续合约数据
df = ak.futures_zh_daily_sina(symbol="IC99", adjust="0")

# 数据字段：date, open, high, low, close, volume, hold
```

#### 数据字段说明
| 字段 | 说明 |
|------|------|
| date | 日期 |
| open | 开盘价 |
| high | 最高价 |
| low | 最低价 |
| close | 收盘价 |
| volume | 成交量 |
| hold | 持仓量 |

#### 适用场景
- ✅ **快速获取历史数据**
- ✅ 个人学习和研究
- ✅ 策略回测
- ✅ 数据质量要求中等
- ❌ 商业用途（需确认授权）

#### 实施建议
**创建 `scripts/download_data_akshare.py`**：
```python
import akshare as ak
from vnpy.trader.object import BarData
from vnpy.trader.constant import Exchange, Interval
from vnpy.alpha import AlphaLab
from datetime import datetime

def download_akshare_data():
    """使用 AKShare 下载股指期货数据"""
    lab = AlphaLab("/Users/w4sh8899/project/vnpy/lab_data")

    # 配置合约参数（与 Tushare 相同）
    contracts = {
        "IF.CFFEX": {"size": 300, "pricetick": 0.2},
        "IH.CFFEX": {"size": 300, "pricetick": 0.2},
        "IC.CFFEX": {"size": 200, "pricetick": 0.2},
    }

    # 连续合约映射
    symbol_map = {
        "IF": "IF99",
        "IH": "IH99",
        "IC": "IC99",
    }

    for symbol, continuous_code in symbol_map.items():
        print(f"下载 {symbol} 数据...")

        # 获取数据
        df = ak.futures_zh_daily_sina(symbol=continuous_code, adjust="0")

        # 转换为 BarData
        bars = []
        for _, row in df.iterrows():
            bar = BarData(
                symbol=symbol,
                exchange=Exchange.CFFEX,
                datetime=datetime.strptime(row["date"], "%Y-%m-%d"),
                interval=Interval.DAILY,
                open_price=float(row["open"]),
                high_price=float(row["high"]),
                low_price=float(row["low"]),
                close_price=float(row["close"]),
                volume=float(row["volume"]),
                turnover=0.0,  # AKShare 没有成交额
                open_interest=float(row["hold"]),
                gateway_name="AKSHARE",
            )
            bars.append(bar)

        # 保存到 AlphaLab
        lab.save_bar_data(bars)
        print(f"✓ {symbol} 下载完成：{len(bars)} 条数据")

if __name__ == "__main__":
    download_akshare_data()
```

---

### 3️⃣ **efinance（备选）**

#### 基本信息
- **类型**：开源 Python 库（基于东方财富网）
- **GitHub**：https://github.com/Micro-sheep/efinance
- **文档**：https://efinance.readthedocs.io/
- **Python库**：`pip install efinance`
- **Star数**：3.4k+

#### 优势
✅ 完全免费，无频率限制
✅ 数据质量较好（东方财富网）
✅ 支持实时行情
✅ 支持多种金融产品
✅ API 设计友好

#### 劣势
❌ 文档不如 AKShare 详细
❌ 社区相对较小
❌ 期货数据接口可能不如股票完善

#### 代码示例
```python
import efinance

# 获取实时行情
df = efinance.get FuturesRealtime()

# 获取历史K线
df = efinance.get_futures_hist()
```

#### 适用场景
- ✅ 免费数据需求
- ✅ 需要实时行情
- ✅ 对东方财富网数据源有偏好
- ❌ 需要详细文档支持

---

### 4️⃣ **Yahoo Finance（不推荐）**

#### 基本信息
- **类型**：国际金融数据平台
- **Python库**：`yfinance`
- **官网**：https://finance.yahoo.com

#### 优势
✅ 国际知名平台
✅ 全球股市数据齐全
✅ Python 库易用

#### 劣势
❌ **不支持中国股指期货**（IF/IH/IC）
❌ 只有股票、ETF、指数数据
❌ 中国市场数据不完整

#### 适用场景
- ❌ **不适用于当前需求**

---

### 5️⃣ **新浪财经 API（已弃用）**

#### 基本信息
- **类型**：网页爬虫 / Sina Finance API
- **状态**：2023年后逐渐被限制

#### 优势
✅ 曾经免费可用
✅ 数据实时性好

#### 劣势
❌ **反爬虫措施严格**
❌ 容易被封禁 IP
❌ 接口不稳定
❌ 不符合 2026 年合规要求

#### 适用场景
- ❌ **已不推荐使用**
- ⚠️ 建议使用 AKShare（已封装新浪数据源）

---

## 🎯 **方案推荐**

### **场景 1：快速获取数据** ⭐⭐⭐⭐⭐
**推荐**：**AKShare**
- 理由：免费、无频率限制、速度快
- 预计时间：5-10 分钟
- 适合：策略开发、快速验证

### **场景 2：高质量数据**
**推荐**：**Tushare 付费版**
- 理由：数据最权威、质量最高
- 成本：360元/年起
- 适合：量化交易、商业用途

### **场景 3：免费高质量数据**
**推荐**：**Tushare 免费版 + 耐心**
- 理由：数据质量高，只是速度慢
- 预计时间：2-3 小时
- 适合：不着急、需要高质量数据

### **场景 4：实时行情**
**推荐**：**efinance**
- 理由：实时性好、免费
- 适合：盘后分析、实时监控

---

## 📋 **实施建议**

### **立即行动：并行方案**

#### 方案 A：继续 Tushare V3 下载（后台）
```bash
# V3 脚本已启动，正在后台运行
# 预计完成时间：2-3 小时
# 数据质量：高
```

#### 方案 B：快速使用 AKShare（推荐）
```bash
# 1. 安装 AKShare
pip install akshare

# 2. 运行 AKShare 下载脚本（5-10分钟）
python scripts/download_data_akshare.py

# 3. 立即开始策略回测
python scripts/run_backtest.py
```

#### 方案 C：对比验证
```bash
# 同时使用两个数据源，对比数据质量
# 如果 AKShare 数据足够好，就优先使用它
```

---

## 📝 **总结对比表**

| 数据源 | 速度 | 质量 | 成本 | 频率限制 | 推荐度 |
|--------|------|------|------|----------|--------|
| **AKShare** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | 免费 | 无 | ⭐⭐⭐⭐⭐ |
| **Tushare免费** | ⭐⭐ | ⭐⭐⭐⭐⭐ | 免费 | 20次/分钟 | ⭐⭐⭐ |
| **Tushare付费** | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | 360元/年 | 提升 | ⭐⭐⭐⭐ |
| **efinance** | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | 免费 | 无 | ⭐⭐⭐⭐ |
| Yahoo Finance | ⭐⭐⭐⭐⭐ | N/A | 免费 | 无 | ❌ |
| 新浪财经 | ⭐⭐ | ⭐⭐⭐ | 免费 | 严格限制 | ❌ |

---

## 🔗 **参考资源**

### AKShare
- [GitHub 仓库](https://github.com/akfamily/akshare)
- [官方文档 - 期货数据](https://akshare.akfamily.xyz/data/futures/futures.html)
- [期货数据源代码](https://akshare.akfamily.xyz/_sources/data/futures/futures.md.txt)

### efinance
- [GitHub 仓库](https://github.com/Micro-sheep/efinance)
- [官方文档](https://efinance.readthedocs.io/)
- [知乎介绍文章](https://zhuanlan.zhihu.com/p/594951746)

### Tushare
- [官网](https://tushare.pro)
- [官方文档](https://tushare.pro/document/1)

### 数据源对比
- [2026年数据API选择指南](https://developer.volcengine.com/articles/7600710063493218314)
- [股指期货API入门指南](https://cloud.tencent.com/developer/article/)

---

**Created**: 2026-04-13
**Project**: vn.py 量化交易系统
**Author**: Claude Code
