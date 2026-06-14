import os
import shutil
from pathlib import Path
from typing import Any, List, Dict, Tuple, Optional

from app.core.event import EventManager, Event
from app.plugins import _PluginBase
from app.schemas.types import EventType
from app.schemas import NotificationType
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger


class FanArtGuard(_PluginBase):
    """FanArt守护者 —— 自动补充媒体文件夹中缺失的fanart/background/backdrop/thumb图片"""

    plugin_name = "FanArt守护者"
    plugin_desc = "自动补充媒体文件夹中缺失的fanart、background、backdrop、thumb图片"
    plugin_version = "1.0"
    plugin_author = "yourname"
    plugin_config_fields = [
        {
            "key": "enable_auto",
            "type": "switch",
            "defaultValue": True,
            "label": "启用自动触发",
            "help": "监听文件转移事件，自动检查并补充缺失图片",
        },
        {
            "key": "enable_cron",
            "type": "switch",
            "defaultValue": False,
            "label": "启用定时全量扫描",
            "help": "按Cron表达式定时扫描整个媒体库，补充所有缺失图片",
        },
        {
            "key": "cron_expression",
            "type": "text",
            "defaultValue": "0 3 * * *",
            "label": "Cron表达式",
            "help": "定时全量扫描的Cron表达式，默认每天凌晨3点执行",
        },
        {
            "key": "media_root",
            "type": "text",
            "defaultValue": "",
            "label": "媒体库根目录",
            "help": "全量扫描时的媒体库根目录（留空则自动使用系统设置）",
        },
        {
            "key": "extensions",
            "type": "text",
            "defaultValue": "jpg,jpeg,png,webp",
            "label": "图片扩展名",
            "help": "支持的图片文件扩展名，逗号分隔",
        },
        {
            "key": "image_types",
            "type": "text",
            "defaultValue": "fanart,background,backdrop,thumb",
            "label": "图片类型",
            "help": "需要检查的图片类型，优先级从高到低排列（fanart > background > backdrop > thumb）",
        },
        {
            "key": "notify_on_copy",
            "type": "switch",
            "defaultValue": False,
            "label": "操作通知",
            "help": "补充图片后发送系统通知",
        },
    ]

    # 后台定时器实例
    _scheduler: Optional[BackgroundScheduler] = None
    # 缓存的配置
    _config: dict = {}
    # event_manager 引用（由 _PluginBase 或本插件维护）
    event_manager: Optional[EventManager] = None

    # ─── 生命周期 ──────────────────────────────────────────────

    def init_plugin(self, config: dict = None):
        """插件初始化：读取配置 → 注册事件监听 → 启动定时任务"""
        self._config = config or {}
        self._refresh_config()

        # 获取 / 创建 EventManager
        if self.event_manager is None:
            self.event_manager = EventManager()

        # 注册事件监听
        if self._config.get("enable_auto", True):
            self.event_manager.add_event_listener(
                EventType.TransferComplete, self.on_transfer_complete
            )
            self.info("已注册 TransferComplete 事件监听")

        # 启动定时任务
        self._start_scheduler()
        self.info(f"FanArt守护者 v{self.plugin_version} 已启动")

    def stop(self):
        """插件卸载时清理资源"""
        self._stop_scheduler()
        if self.event_manager:
            self.event_manager.remove_event_listener(
                EventType.TransferComplete, self.on_transfer_complete
            )
        self.info("FanArt守护者已停止")

    def get_state(self) -> bool:
        return True

    # ─── 事件处理 ──────────────────────────────────────────────

    def on_transfer_complete(self, event: Event):
        """
        文件转移完成事件 —— 这是主要智能触发入口。
        MoviePilot整理完媒体文件后会触发此事件，我们只处理命中的那个目录。
        """
        if not self._config.get("enable_auto", True):
            return

        event_data = event.event_data or {}
        target_path = event_data.get("target_path")
        if not target_path or not os.path.isdir(target_path):
            return

        self.debug(f"收到 TransferComplete 事件: {target_path}")
        self._process_directory(target_path)

    # ─── API 端点（可在 MoviePilot 中手动调用） ────────────────

    def get_api(self):
        """注册API端点，供前端或外部调用"""
        from fastapi import APIRouter

        router = APIRouter(prefix="/FanArtGuard", tags=["FanArt守护者"])

        @router.get("/scan")
        def api_scan(path: str = ""):
            """手动触发扫描：可指定路径，留空则全量扫描"""
            if path and os.path.isdir(path):
                self._process_directory(path)
                return {"code": 0, "msg": f"已处理目录: {path}"}
            elif not path:
                count = self._scan_all()
                return {"code": 0, "msg": f"全量扫描完成，处理了 {count} 个目录"}
            else:
                return {"code": 1, "msg": f"路径无效: {path}"}

        @router.get("/status")
        def api_status():
            """返回插件运行状态"""
            return {
                "code": 0,
                "data": {
                    "enable_auto": self._config.get("enable_auto", True),
                    "enable_cron": self._config.get("enable_cron", False),
                    "cron": self._config.get("cron_expression", ""),
                    "version": self.plugin_version,
                },
            }

        return router

    # ─── 核心逻辑 ──────────────────────────────────────────────

    def _process_directory(self, dir_path: str):
        """处理单个目录：检查缺失图片并补充"""
        existing = self._get_existing_images(dir_path)
        if not existing:
            return  # 没有任何图片，跳过

        src_type, src_path = existing[0]
        if len(existing) == len(self._image_types):
            return  # 所有类型已齐全

        src_ext = src_path.rsplit(".", 1)[-1].lower()
        copied_count = 0

        for img_type in self._image_types:
            if self._find_image(dir_path, img_type):
                continue
            dst_path = os.path.join(dir_path, f"{img_type}.{src_ext}")
            try:
                shutil.copy(src_path, dst_path)
                copied_count += 1
                self.info(f"✔ {os.path.basename(dir_path)}: {src_type}.{src_ext} → {img_type}.{src_ext}")
            except OSError as err:
                self.error(f"✘ 补充 {img_type} 失败: {err}")

        if copied_count and self._config.get("notify_on_copy"):
            self._send_notification(
                f"FanArt守护者 为 {os.path.basename(dir_path)} 补充了 {copied_count} 张图片"
            )

    def _scan_all(self) -> int:
        """全量扫描媒体库根目录"""
        media_root = self._config.get("media_root") or self._get_default_media_root()
        if not media_root or not os.path.isdir(media_root):
            self.warn("未配置媒体库根目录或目录不存在")
            return 0

        count = 0
        for root, dirs, _ in os.walk(media_root):
            # 跳过隐藏目录和系统目录
            dirs[:] = [d for d in dirs if not d.startswith(".")]
            # 只处理包含视频文件的目录（更精准的判断）
            if self._is_media_directory(root):
                self._process_directory(root)
                count += 1

        self.info(f"全量扫描完成，共处理 {count} 个媒体目录")
        return count

    def _find_image(self, dir_path: str, image_type: str) -> Optional[str]:
        """在目录中查找指定类型的图片"""
        for ext in self._extensions:
            img_path = os.path.join(dir_path, f"{image_type}.{ext}")
            if os.path.isfile(img_path):
                return img_path
        return None

    def _get_existing_images(self, dir_path: str) -> List[Tuple[str, str]]:
        """收集目录中已存在的图片，返回 [(类型, 路径), ...]"""
        existing = []
        for img_type in self._image_types:
            img_path = self._find_image(dir_path, img_type)
            if img_path:
                existing.append((img_type, img_path))
        return existing

    @staticmethod
    def _is_media_directory(dir_path: str) -> bool:
        """判断是否为媒体目录（检查是否包含视频/字幕/媒体信息文件）"""
        media_exts = {".mp4", ".mkv", ".avi", ".ts", ".mov", ".wmv",
                      ".flv", ".m2ts", ".iso", ".nfo", ".srt", ".ass", ".ssa"}
        try:
            for f in os.listdir(dir_path):
                if os.path.splitext(f)[1].lower() in media_exts:
                    return True
        except OSError:
            pass
        return False

    # ─── 定时任务 ──────────────────────────────────────────────

    def _start_scheduler(self):
        if not self._config.get("enable_cron") or not self._config.get("cron_expression"):
            return
        try:
            self._scheduler = BackgroundScheduler(timezone="Asia/Shanghai")
            self._scheduler.add_job(
                self._scan_all,
                CronTrigger.from_crontab(self._config["cron_expression"]),
                id="fanart_guard_cron",
                name="FanArt全量扫描",
                replace_existing=True,
            )
            self._scheduler.start()
            self.info(f"定时任务已启动: {self._config['cron_expression']}")
        except Exception as e:
            self.error(f"启动定时任务失败: {e}")

    def _stop_scheduler(self):
        if self._scheduler and self._scheduler.running:
            self._scheduler.shutdown(wait=False)
            self._scheduler = None

    # ─── 配置 & 辅助 ───────────────────────────────────────────

    def _refresh_config(self):
        """将配置项解析为实例属性"""
        self._extensions = [
            e.strip().lstrip(".")
            for e in self._config.get("extensions", "jpg,jpeg,png,webp").split(",")
            if e.strip()
        ] or ["jpg", "jpeg", "png", "webp"]
        self._image_types = [
            t.strip().lower()
            for t in self._config.get("image_types", "fanart,background,backdrop").split(",")
            if t.strip()
        ] or ["fanart", "background", "backdrop", "thumb"]

    def _get_default_media_root(self) -> str:
        """尝试从系统设置或其他途径获取媒体库根目录"""
        # MoviePilot 中可以通过系统设置获取
        try:
            from app.core.config import settings
            return getattr(settings, "MEDIA_ROOT", "") or getattr(settings, "LIBRARY_PATH", "")
        except ImportError:
            return ""

    def _send_notification(self, text: str):
        """发送系统通知"""
        try:
            from app.chain.notification import NotificationChain
            NotificationChain().post(
                title="FanArt守护者",
                text=text,
                mtype=NotificationType.Media整理,
            )
        except Exception:
            self.info(f"[通知] {text}")

    # ─── 日志快捷方法 ──────────────────────────────────────────

    def info(self, msg: str):
        super().info(f"[FanArt] {msg}")

    def warn(self, msg: str):
        super().warn(f"[FanArt] {msg}")

    def error(self, msg: str):
        super().error(f"[FanArt] {msg}")

    def debug(self, msg: str):
        super().debug(f"[FanArt] {msg}")
