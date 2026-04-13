---
name: ta-lib
description: 快速安装和配置 ta-lib 技术分析库(必须从自定义镜像安装)
---

# TA-Lib 安装助手

自动化安装 ta-lib 技术分析库,这是 vn.py 项目的重要依赖。

## 背景

TA-Lib 是一个广泛使用的技术分析库,包含超过 150 种技术指标。由于编译复杂性,vn.py 项目提供了预编译的 wheel 包,必须从自定义镜像安装。

## 系统要求

- Python 3.10+
- uv 包管理器(推荐)或 pip
- 网络连接到 https://pypi.vnpy.com

## 安装步骤

### 使用 uv (推荐)

```bash
# 安装 ta-lib 0.6.4 版本(从 vnpy 自定义镜像)
uv pip install ta-lib==0.6.4 --index=https://pypi.vnpy.com --system
```

### 使用 pip

```bash
# 从自定义镜像安装
pip install ta-lib==0.6.4 -i https://pypi.vnpy.com/simple
```

## 验证安装

```bash
# 验证 ta-lib 是否正确安装
python -c "import talib; print(talib.__version__)"

# 应该输出: 0.6.4
```

## 常见问题

### 问题 1: 安装失败,提示找不到版本

**原因**: 使用了错误的 PyPI 源

**解决**: 必须使用 `--index=https://pypi.vnpy.com` 参数

### 问题 2: 导入错误

**原因**: 可能安装了错误版本或从源码编译失败

**解决**: 卸载后重新安装
```bash
uv pip uninstall ta-lib
uv pip install ta-lib==0.6.4 --index=https://pypi.vnpy.com --system
```

### 问题 3: macOS 平台问题

**原因**: macOS 可能需要额外依赖

**解决**: 确保安装了 Xcode Command Line Tools
```bash
xcode-select --install
```

## 版本锁定

vn.py 项目要求使用 **ta-lib==0.6.4**,不要升级到其他版本,因为:
- 预编译 wheel 只针对此版本
- API 兼容性保证
- 测试覆盖此版本

## 相关链接

- vn.py 官方文档: https://www.vnpy.com/docs
- TA-Lib 官方文档: https://ta-lib.org
