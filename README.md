# FanArt守护者

MoviePilot V2 插件 —— 自动补充媒体文件夹中缺失的 `fanart` / `background` / `backdrop` / `thumb` 图片。

## 功能

- **自动触发**：监听 MoviePilot `TransferComplete` 事件，新入库媒体即时检查补充
- **定时扫描**：按 Cron 表达式定期全量扫描，兜底补充遗漏
- **手动扫描**：提供 API 接口和「立即运行」按钮，随时触发
- **排除路径**：可配置跳过指定目录，避免误处理
- **操作通知**：补充完成后发送系统通知

### 工作原理

检查媒体目录中是否存在 `fanart` / `background` / `backdrop` / `thumb` 图片，用**已有最高优先级图片**作为源，复制填充缺失类型。

```
优先级：fanart > background > backdrop > thumb

示例：某目录只有 thumb.jpg，没有 fanart/background/backdrop
      → 将 thumb.jpg 复制为 fanart.jpg、background.jpg、backdrop.jpg
```

## 安装

在 MoviePilot 后台 → 插件管理 → 添加插件，填入仓库地址：

```
https://github.com/Striving9527/FanArtGuard.git
```

## 配置

| 配置项 | 说明 |
|--------|------|
| 启用插件 | 总开关 |
| 自动触发 | 监听文件入库事件，即时处理 |
| 定时全量扫描 | 开启 Cron 定时扫描 |
| Cron 表达式 | 留空默认每 7 天一次 |
| 立即运行一次 | 保存配置后立即全量扫描 |
| 扫描路径 | 每行一个目录，留空自动使用系统媒体库 |
| 排除路径 | 每行一个目录，扫描时跳过 |
| 图片扩展名 | 支持的格式，逗号分隔 |
| 图片类型 | 优先级从高到低排列 |
| 操作通知 | 补充图片后发送系统通知 |

## API

| 端点 | 说明 |
|------|------|
| `GET /api/v1/plugin/FanArtGuard/scan?path=` | 指定目录扫描，留空全量扫描 |
| `GET /api/v1/plugin/FanArtGuard/status` | 查看插件运行状态 |

## 手动安装

如果网络不通，可手动拷贝到 MoviePilot 插件目录：

```bash
git clone https://github.com/Striving9527/FanArtGuard.git /tmp/FanArtGuard
docker cp /tmp/FanArtGuard/plugins.v2/fanartguard moviepilot:/app/plugins.v2/
docker restart moviepilot
```

## 更新日志

参见 `package.v2.json` 中的 `history` 字段。
