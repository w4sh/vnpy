# 布林带选股系统使用说明

## 功能概述

布林带选股系统基于布林带技术指标，从全市场A股中筛选出符合特定条件的股票。该系统支持多种选股策略，可以帮助你快速发现潜在的买入和卖出机会。

## 选股策略说明

### 1. 超卖策略 (oversold)
**信号含义**：价格触及或接近布林带下轨
**交易建议**：可能存在买入机会
**筛选条件**：布林带位置 ≤ 15%
**适用场景**：
- 寻找被超卖的优质股票
- 短期反弹机会
- 价值投资入场点

### 2. 超买策略 (overbought)
**信号含义**：价格触及或接近布林带上轨
**交易建议**：可能存在卖出机会或需要警惕
**筛选条件**：布林带位置 ≥ 85%
**适用场景**：
- 获利了结
- 短期回调风险
- 趋势股票的高位警告

### 3. 向上突破 (breakout_up)
**信号含义**：价格向上突破布林带上轨，且布林带开口
**交易建议**：强势买入信号
**筛选条件**：布林带位置 ≥ 75% 且布林带宽度 > 5%
**适用场景**：
- 趋势跟踪
- 突破买入
- 强势股筛选

### 4. 向下突破 (breakout_down)
**信号含义**：价格向下突破布林带下轨，且布林带开口
**交易建议**：强势卖出信号
**筛选条件**：布林带位置 ≤ 25% 且布林带宽度 > 5%
**适用场景**：
- 止损信号
- 避险操作
- 弱势股规避

### 5. 布林带收缩 (squeeze)
**信号含义**：布林带宽度非常窄，波动率极低
**交易建议**：可能即将出现大行情
**筛选条件**：布林带宽度 < 2%
**适用场景**：
- 行情爆发前的准备
- 潜力股筛选
- 波动率交易

## 快速开始

### 1. 基础选股命令

```bash
# 查找超卖股票（买入机会）
python scripts/pick_stocks.py --strategy oversold --top 10

# 查找超买股票（卖出机会）
python scripts/pick_stocks.py --strategy overbought --top 10

# 查找向上突破股票
python scripts/pick_stocks.py --strategy breakout_up --top 10

# 查找布林带收缩股票
python scripts/pick_stocks.py --strategy squeeze --top 10
```

### 2. 高级参数配置

```bash
# 自定义价格范围和成交量
python scripts/pick_stocks.py --strategy oversold \
    --min-price 10.0 \
    --max-price 100.0 \
    --min-volume 10000000 \
    --top 20

# 调整布林带参数
python scripts/pick_stocks.py --strategy breakout_up \
    --ma-window 10 \
    --std-window 10 \
    --dev-mult 1.5 \
    --top 15
```

### 3. 批量选股（全策略扫描）

```bash
# 运行完整选股系统
python scripts/bollinger_stock_picker.py
```

## 参数说明

| 参数 | 说明 | 默认值 | 推荐范围 |
|------|------|--------|----------|
| --strategy | 选股策略 | oversold | oversold/overbought/breakout_up/breakout_down/squeeze |
| --top | 返回股票数量 | 20 | 10-50 |
| --min-price | 最低价格 | 5.0 | 3.0-50.0 |
| --max-price | 最高价格 | 200.0 | 50.0-500.0 |
| --min-volume | 最小成交量 | 5000000 | 1000000-10000000 |
| --ma-window | 均线周期 | 20 | 5-30 |
| --std-window | 标准差周期 | 20 | 5-30 |
| --dev-mult | 标准差倍数 | 2.0 | 1.5-3.0 |

## 输出结果

选股结果保存在 `/Users/w4sh8899/project/vnpy/output/` 目录下，文件格式为：

- `stock_picker_{strategy}_{timestamp}.txt` - 详细结果
- `stock_picker_summary_{timestamp}.txt` - 汇总报告
- `stock_picker_{strategy}_latest.txt` - 最新结果

### 结果文件内容

每只股票包含以下信息：
- 股票代码
- 当前价格
- 成交量
- 布林带位置（0-100%）
- 布林带上轨、中轨、下轨价格
- 布林带宽度
- 信号得分（用于排序）

## 使用建议

### 1. 策略选择

**市场环境识别**：
- **震荡市场**：优先使用 oversold/overbought 策略
- **趋势市场**：优先使用 breakout_up/breakout_down 策略
- **横盘整理**：关注 squeeze 策略，等待突破

### 2. 参数调整

**保守型投资者**：
- 提高价格门槛：`--min-price 20.0`
- 增加成交量要求：`--min-volume 10000000`
- 选择超卖策略：`--strategy oversold`

**激进型投资者**：
- 关注突破信号：`--strategy breakout_up`
- 降低价格门槛：`--min-price 3.0`
- 缩短周期：`--ma-window 10`

### 3. 风险控制

**止损设置**：
- 超卖策略买入：止损设在布林带下轨下方
- 突破策略买入：止损设在布林带中轨

**仓位管理**：
- 单只股票不超过总资金的10%
- 同一策略的股票分散配置
- 预留30%现金应对风险

### 4. 组合使用

**多策略共振**：
```bash
# 同时运行多个策略
python scripts/pick_stocks.py --strategy oversold --top 5
python scripts/pick_stocks.py --strategy breakout_up --top 5
python scripts/pick_stocks.py --strategy squeeze --top 5
```

选择同时出现在多个策略中的股票，信号更可靠。

## 实战案例

### 案例1：超卖反弹机会

**选股条件**：
```bash
python scripts/pick_stocks.py --strategy oversold \
    --min-price 10.0 \
    --max-price 50.0 \
    --min-volume 5000000 \
    --top 10
```

**交易策略**：
- 分批建仓
- 止损：-5%
- 止盈：回到布林带中轨或+10%

### 案例2：突破追涨

**选股条件**：
```bash
python scripts/pick_stocks.py --strategy breakout_up \
    --min-price 20.0 \
    --min-volume 10000000 \
    --top 5
```

**交易策略**：
- 确认突破有效性（成交量配合）
- 止损：回到布林带内
- 止盈：+15% 或出现明显的顶部信号

### 案例3：潜力股挖掘

**选股条件**：
```bash
python scripts/pick_stocks.py --strategy squeeze \
    --min-price 10.0 \
    --max-price 100.0 \
    --top 20
```

**交易策略**：
- 加入自选股观察
- 等待突破信号
- 突破后根据方向决策

## 技术原理

### 布林带指标

**计算公式**：
- 中轨 = N日移动平均线
- 上轨 = 中轨 + K × N日标准差
- 下轨 = 中轨 - K × N日标准差

**布林带位置**：
```
BB_Position = (当前价格 - 下轨) / (上轨 - 下轨) × 100%
```

**布林带宽度**：
```
BB_Width = (上轨 - 下轨) / 中轨 × 100%
```

### 信号解读

**布林带位置含义**：
- 0-20%：严重超卖
- 20-40%：超卖区域
- 40-60%：正常区域
- 60-80%：超买区域
- 80-100%：严重超买

**布林带宽度含义**：
- <2%：波动率极低，可能即将突破
- 2-5%：波动率正常
- >5%：波动率较高，趋势明显

## 常见问题

### Q1: 为什么有时候选不到股票？

**A**: 这说明当前市场环境不符合该策略的条件。
- **解决方法**：调整参数（降低阈值、扩大价格范围）
- **解决方法**：换用其他策略
- **解决方法**：等待市场环境变化

### Q2: 选出的股票应该立即买入吗？

**A**: 不应该。选股只是第一步，还需要：
- 进一步分析个股基本面
- 查看K线形态和成交量
- 结合大盘环境判断
- 制定明确的交易计划

### Q3: 如何提高选股成功率？

**A**: 多重过滤：
- 技术面：布林带信号 + 成交量确认
- 基本面：选择行业龙头、业绩良好
- 市场面：避开系统性风险
- 时机：选择大盘企稳时介入

### Q4: 选股结果多久更新一次？

**A**: 建议：
- 日内交易：每天盘后更新
- 波段交易：每周更新1-2次
- 长线投资：每月更新1次

## 系统要求

- **Python版本**：3.10+
- **数据源**：已下载的A股历史数据（lab_data/daily/）
- **依赖包**：vnpy、polars、numpy、pandas

## 更新日志

### v1.0 (2026-04-14)
- ✅ 实现基础选股功能
- ✅ 支持5种选股策略
- ✅ 命令行工具
- ✅ 结果保存和导出
- ✅ 评分排序系统

## 下一步计划

- [ ] 添加更多技术指标筛选（RSI、MACD等）
- [ ] 支持自定义策略组合
- [ ] 添加历史回测功能
- [ ] 实现自动监控和提醒
- [ ] Web界面展示

## 参考资料

- 布林带指标发明者：John Bollinger
- vn.py官网：https://www.vnpy.com
- 策略讨论：https://www.vnpy.com/forum
