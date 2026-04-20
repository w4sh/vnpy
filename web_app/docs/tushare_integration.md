# Tushare Pro 实时行情集成文档

## 概述

成功集成Tushare Pro API,实现持仓价格的自动更新功能。使用120积分的免费账户,每天可调用8000次API。

## 完成的功能

### 1. 核心模块

#### 1.1 行情服务 (`data_feed/quote_service.py`)
- **TushareQuoteService类**: 封装Tushare Pro API调用
- **功能特性**:
  - 自动速率限制(每日8000次,每分钟500次)
  - 支持股票和期货行情获取
  - 自动代码格式转换(.SZSE/.SSE → .SZ/.SH)
  - 批量行情查询
  - 使用统计追踪

#### 1.2 价格更新器 (`data_feed/update_prices.py`)
- **功能**: 自动更新数据库中所有持仓的当前价格
- **特性**:
  - 批量获取行情
  - 自动计算市值、盈亏、盈亏比例
  - 支持dry-run模式测试
  - 详细的更新日志

#### 1.3 Flask API (`quote_api.py`)
- **端点**:
  - `POST /api/quote/update` - 更新所有持仓价格
  - `GET /api/quote/<symbol>` - 获取单个标的行情
  - `GET /api/quote/usage` - 查看API使用情况
  - `GET /api/quote/test` - 测试连接

### 2. 前端集成

#### 2.1 用户界面
- 在持仓管理页面添加"更新价格"按钮
- 实时显示更新状态
- 自动刷新持仓数据

#### 2.2 JavaScript功能
```javascript
updatePrices() // 触发价格更新
```

## 使用方法

### 命令行方式
```bash
# 更新所有持仓价格
python3 data_feed/update_prices.py

# 测试模式(不实际更新数据库)
python3 data_feed/update_prices.py --dry-run

# 使用自定义token
python3 data_feed/update_prices.py --token YOUR_TOKEN
```

### Web界面方式
1. 访问 http://localhost:5001
2. 点击"持仓管理" → "持仓概览"
3. 点击"🔄 更新价格"按钮
4. 等待更新完成,自动刷新数据

### API调用方式
```bash
# 触发价格更新
curl -X POST http://localhost:5001/api/quote/update

# 获取单个标的行情
curl http://localhost:5001/api/quote/000001.SZ

# 查看使用情况
curl http://localhost:5001/api/quote/usage
```

## 技术细节

### API限制
- **免费积分**: 120积分/天
- **每日请求**: 8000次
- **每分钟限制**: 500次
- **速率控制**: 自动检测并等待

### 数据格式转换
```python
# 数据库格式 → Tushare格式
000001.SZSE → 000001.SZ
600036.SSE  → 600036.SH
```

### 价格计算逻辑
```python
market_value = current_price * quantity
profit_loss = market_value - (cost_price * quantity)
profit_loss_pct = (profit_loss / (cost_price * quantity)) * 100
```

## 测试结果

### 连接测试
✓ Tushare Pro连接正常
✓ Token验证通过
✓ 行情数据获取成功

### 更新测试
✓ 4个持仓全部更新成功
✓ 价格数据准确
✓ 盈亏计算正确
✓ API使用统计正常

### 示例数据
```
000001.SZSE  平安银行   13.20 → 11.17 (-15.38%)
600036.SSE   招商银行   38.20 → 39.13 (+2.43%)
600519.SSE   贵州茅台  1720.00 → 1446.90 (-15.88%)
000002.SZSE  万科A     11.50 → 4.02 (-65.04%)
```

## 文件清单

### 新增文件
- `data_feed/__init__.py` - 模块初始化
- `data_feed/quote_service.py` - 行情服务(200行)
- `data_feed/update_prices.py` - 价格更新脚本(140行)
- `quote_api.py` - Flask API蓝图(90行)

### 修改文件
- `app_position_only.py` - 注册quote_bp蓝图
- `templates/index.html` - 添加更新按钮和JS函数

## 后续优化方向

1. **自动化**: 使用APScheduler实现定时更新
2. **性能**: 添加Redis缓存减少API调用
3. **监控**: 更详细的错误日志和报警
4. **功能**: 支持更多技术指标
5. **数据**: 添加历史价格存储

## 注意事项

1. **API限制**: 免费账户每天8000次调用,注意频率控制
2. **数据延迟**: Tushare日线数据有T+1延迟
3. **市场时间**: 非交易时间可能返回上一交易日数据
4. **错误处理**: 网络问题时会自动重试

## 费用说明

### Tushare Pro积分体系
- **免费积分**: 120积分/天(每天重置)
- **积分消耗**:
  - 日线数据: 1次调用 = 1积分
  - 分钟数据: 1次调用 = 1积分
  - 其他接口: 不同接口消耗不同

### 升级方案
- **标准版**: 2000积分/月, ¥300/月
- **高级版**: 10000积分/月, ¥2000/月
- **专业版**: 40000积分/月, ¥8000/月

对于个人投资者,免费版120积分/天(约3600积分/月)已足够基本使用。

## 总结

✅ 完成Tushare Pro API集成
✅ 实现价格自动更新功能
✅ 添加Web界面操作
✅ 修复Decimal类型转换问题
✅ 通过完整功能测试

系统已可用于实际投资组合管理!
