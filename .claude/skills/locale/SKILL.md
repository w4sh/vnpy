---
name: locale
description: 重新生成 vn.py 项目的翻译文件(中英文国际化支持)
---

# 翻译文件生成助手

自动化生成 vn.py 项目的翻译文件(.mo 文件),用于中英文界面切换。

## 背景

vn.py 使用 Babel 进行国际化(i18n)管理,支持中文和英文界面。翻译文件源码是 `.po` 文件,需要编译成二进制 `.mo` 文件才能被程序使用。

## 文件位置

```
vnpy/trader/locale/
├── build_hook.py      # 构建钩子
├── zh_CN/LC_MESSAGES/
│   └── vnpy.po        # 中文翻译源文件
└── en/LC_MESSAGES/
    └── vnpy.po        # 英文翻译源文件
```

## 生成翻译文件

### Windows

```bash
# 运行批处理脚本
vnpy/trader/locale/generate_mo.bat
```

### Linux/macOS

```bash
# 编译中文翻译
msgfmt vnpy/trader/locale/zh_CN/LC_MESSAGES/vnpy.po -o vnpy/trader/locale/zh_CN/LC_MESSAGES/vnpy.mo

# 编译英文翻译
msgfmt vnpy/trader/locale/en/LC_MESSAGES/vnpy.po -o vnpy/trader/locale/en/LC_MESSAGES/vnpy.mo
```

## 修改翻译内容

如果需要添加或修改翻译:

### 1. 编辑 .po 文件

找到需要修改的语言对应的 `.po` 文件,例如:
- 中文: `vnpy/trader/locale/zh_CN/LC_MESSAGES/vnpy.po`
- 英文: `vnpy/trader/locale/en/LC_MESSAGES/vnpy.po`

### 2. 添加新翻译条目

```po
msgid "Original English Text"
msgstr "翻译后的文本"
```

### 3. 重新编译

运行上述生成命令重新编译 `.mo` 文件。

## 在代码中使用翻译

```python
from vnpy.trader.locale import _

# 使用翻译函数
text = _("Hello, World!")
```

## 验证翻译

```python
# 测试翻译是否生效
import locale
# 设置为中文
locale.setlocale(locale.LC_ALL, 'zh_CN.UTF-8')

# 或设置为英文
locale.setlocale(locale.LC_ALL, 'en_US.UTF-8')
```

## 自动构建

项目配置了自动构建钩子(`build_hook.py`),在使用 `uv build` 或 `pip install` 时会自动编译翻译文件。

## 常见问题

### 问题 1: 界面显示英文而非中文

**原因**:
1. 翻译文件未生成
2. 系统语言设置不正确

**解决**:
1. 运行生成命令
2. 检查系统语言环境变量

### 问题 2: 修改翻译后无效果

**原因**: .mo 文件未更新

**解决**: 重新编译 .mo 文件

### 问题 3: msgfmt 命令不存在

**原因**: 系统未安装 gettext 工具

**解决**:
- macOS: `brew install gettext`
- Ubuntu: `sudo apt-get install gettext`
- Windows: 使用批处理脚本(自带 msgfmt)

## 翻译规范

1. **保持简洁**: 界面文本应该简短明了
2. **专业术语**: 金融术语使用标准翻译
3. **一致性**: 相同概念使用相同翻译
4. **格式化**: 保留占位符(如 `{}`, `%s`)

## 相关链接

- Babel 文档: https://babel.pocoo.org/
- GNU gettext: https://www.gnu.org/software/gettext/
