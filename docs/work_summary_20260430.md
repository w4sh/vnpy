# 工作进展 — 2026-04-30

## 一、Scheduler 独立化与部署

### 改动
- 创建 `run_scheduler.py`：独立运行入口，支持 `--daemon`/`--status`/`--stop`/`--install`
- 注册 macOS launchd 服务 `com.vnpy.scheduler`，开机自启 + keepalive
- `web_app/scheduler_tasks.py`：重构定时任务，分离日频与季频逻辑

### 定时任务配置
| 任务 | 触发 | 说明 |
|------|------|------|
| recalc_dirty_strategies | 每 5 分钟 | 重算 dirty 策略 |
| recover_stuck_strategies | 每 10 分钟 | 恢复卡死的 recomputing 状态 |
| run_daily_candidate_screening | 交易日 15:30 | 收盘后选股 |
| run_daily_factor_update | 交易日 15:35 | 日终因子增量更新 |
| run_quarterly_factor_update | 手动/按月 | 季频财务数据全量更新（耗时 80+ 分钟） |

## 二、因子评估 Web API

### 改动
- 新建 `web_app/evaluation_api.py`，注册 `eval_bp` 蓝图到 Flask
- 端点：`GET /api/evaluation/latest`（最新评估摘要）
- 端点：`GET /api/evaluation/list`（评估文件列表）
- 前端 `index.html`：新增风险分析面板（IC 表、因子评分、相关性矩阵）

## 三、2026Q1 季频数据补全

### 数据清理
- 移除了 6 个异常报告期的 26 条脏数据
- 修复 CheckpointManager 目录问题（data_dir 直接使用，不追加 /checkpoint 子目录）

### 增量更新结果
| 指标 | 更新前 | 更新后 | 变化 |
|------|-------|-------|------|
| 总行数 | 707,980 | 717,798 | +9,818 |
| 2026Q1 行数 | 14,265 | 21,161 | +6,896 |
| 2026Q1 股票数 | 2,890 (54%) | 4,328 (81%) | +1,438 |
| 处理失败数 | - | 0 | - |
| 空数据（退市/停牌） | - | 988 | - |

- 49 批次全部完成，零失败
- 剩余 ~700 只股票无数据（新上市或延迟披露）

### 当前数据状态
| 数据集 | 行数 | 股票数 | 覆盖时段 |
|-------|------|--------|---------|
| fundamental_daily | 7,217,141 | 5,725 | 2020-04-13 ~ 2026-04-29（无缺失） |
| fundamental_quarterly | 717,798 | ~5,000 | 39 个报告期（2014~2026Q1） |
| flow_daily | 303 | - | 2025-01-14 ~ 2026-04-29 |

## 四、股票名称显示修复

### 问题
候选股推荐列表的股票名称字段为空字符串

### 根因
- `screening_engine.py` 的 `score_stock()` 中硬编码 `name=""`
- 数据库已有 `name` 字段但未填充

### 修复
- `screening_engine.py`：在 `score_stock()` 中通过 `get_stock_name()` 从 `STOCK_NAMES` 字典查询
- `app.py` 两个 API 端点增加 `c.name or get_stock_name(c.symbol)` fallback
- 已回填 40 条历史记录的空名称

## 五、遗留事项

- [ ] 2026Q1 尚有 ~700 只股票无财务数据，待后续披露后补全
- [ ] `flow_daily` 数据量偏少（303 行），需确认北向资金流接口正常
- [ ] scheduler 独立部署后需观察首个交易日（15:30）能否正常触发
