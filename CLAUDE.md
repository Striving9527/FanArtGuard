# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

MoviePilot V2 插件 — 监听 `TransferComplete` 事件，自动检测媒体目录中缺失的 fanart / background / backdrop / thumb 图片，用已有最高优先级图片复制填充。

## Repository Structure

```
├── package.json            # V1 索引（key=类名FanArtGuard, v2:true 标记V2兼容）
├── package.v2.json         # V2 索引（主入口，不含 v2 字段, 不含 release）
├── plugins/                # V1 代码目录
│   └── fanartguard/
│       └── __init__.py     # 插件主类 (V1 兼容副本)
└── plugins.v2/             # V2 代码目录（主代码，修改只改这里）
    └── fanartguard/
        └── __init__.py     # 插件主类
```

- 目录名 `fanartguard` = 类名 `FanArtGuard` 小写（MoviePilot 强制要求）
- 两个 `__init__.py` 内容必须一致

## Version Update Checklist

修改代码后**必须同步更新 3 处版本号**，否则 MoviePilot 不会提示更新：

1. `plugins.v2/fanartguard/__init__.py` → `plugin_version = "X.Y"`
2. `package.v2.json` → `"version": "X.Y"` + `history` 加一条记录
3. `package.json` → `"version": "X.Y"` + `history` 加一条记录

## Validation

```bash
# 语法检查
python3 -m py_compile plugins.v2/fanartguard/__init__.py

# JSON 格式检查
python3 -c "import json; json.load(open('package.v2.json')); json.load(open('package.json')); print('OK')"

# 确认版本号一致
grep plugin_version plugins.v2/fanartguard/__init__.py
grep version package.v2.json
grep version package.json
```

## MoviePilot V2 Plugin API

继承 `_PluginBase`，关键方法签名：

| Method | Role |
|--------|------|
| `init_plugin(self, config: dict = None)` | 必须开头调 `self.stop_service()` 清旧状态 |
| `get_state(self) -> bool` | 返回 `self._enabled` |
| `get_form(self) -> Tuple[List[dict], Dict[str, Any]]` | Vuetify 配置页 + 默认值 |
| `get_page(self) -> List[dict]` | 详情页，可返回空 list 或 None |
| `get_service(self) -> List[Dict[str, Any]]` | 定时任务，id 唯一，trigger 用 `CronTrigger` |
| `get_api(self) -> List[Dict[str, Any]]` | API 端点，auth 填 `"bear"` |
| `get_command(self)` | `@staticmethod`，无命令返回 `[]` |
| `stop_service(self)` | 移除事件监听、清理资源，用 try/except 包裹 |

关键依赖导入：
```python
from app.core.event import eventmanager, Event  # 事件单例，不要自己 new EventManager()
from app.plugins import _PluginBase
from app.schemas.types import EventType
from app.schemas import NotificationType
from app.log import logger  # 用 logger.info/warn/error，不要用 self.info()
```

## Plugin Behavior

**触发模式**：
- `on_transfer_complete` → 监听 `EventType.TransferComplete`，只处理 `target_path` 对应目录
- `_scan_all` → 遍历 `scan_paths`（留空则自动读系统 `MEDIA_ROOT`），跳过隐藏目录和 `exclude_paths`

**图片处理逻辑**（`_process_directory`）：
- 按 `image_types` 顺序（fanart > background > backdrop > thumb）收集已存在图片
- 用最高优先级已有的图片作为源，复制填充所有缺失类型
- 全部齐全或全部缺失时跳过

**配置项**：enabled, enable_auto, enable_cron, cron, scan_paths, exclude_paths, extensions, image_types, notify, onlyonce

## Pitfalls

- **`"release": true`** 会导致 MP 去 GitHub Releases 找文件（404），不要加
- **`package.v2.json` 不加 `"v2": true`**，`package.json` 才需要这个标记
- 不要自己 `EventManager()` new 实例，用模块级的 `eventmanager` 单例
- 不要用 `self.info()` / `super().info()`，用 `logger.info()`
- 通知用 `self.post_message(mtype=NotificationType.MediaServer, ...)`，标题格式 `【FanArt守护者】`
