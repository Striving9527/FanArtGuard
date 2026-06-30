import os
import shutil
from pathlib import Path
from typing import Any, List, Dict, Tuple, Optional

from app.core.event import eventmanager, Event
from app.plugins import _PluginBase
from app.schemas.types import EventType
from app.schemas import NotificationType
from app.log import logger


class FanArtGuard(_PluginBase):
    # ─── 插件元数据 ───────────────────────────────────────────
    plugin_name = "FanArt守护者"
    plugin_desc = "自动补充媒体文件夹中缺失的fanart、background、backdrop、thumb图片"
    plugin_icon = "fanart.png"
    plugin_version = "2.0"
    plugin_author = "Striving9527"
    author_url = "https://github.com/Striving9527/FanArtGuard"
    plugin_config_prefix = "fanartguard_"
    plugin_order = 28
    auth_level = 1

    # ─── 私有属性 ────────────────────────────────────────────
    _enabled = False
    _enable_auto = True
    _enable_cron = False
    _cron = ""
    _extensions = "jpg,jpeg,png,webp"
    _image_types = "fanart,background,backdrop,thumb"
    _notify = False
    _onlyonce = False

    def init_plugin(self, config: dict = None):
        if config:
            self._enabled = config.get("enabled", False)
            self._enable_auto = config.get("enable_auto", True)
            self._enable_cron = config.get("enable_cron", False)
            self._cron = config.get("cron") or ""
            self._extensions = config.get("extensions") or "jpg,jpeg,png,webp"
            self._image_types = config.get("image_types") or "fanart,background,backdrop,thumb"
            self._notify = config.get("notify", False)
            self._onlyonce = config.get("onlyonce", False)

        if not self._enabled:
            return

        # 注册事件监听
        if self._enable_auto:
            eventmanager.add_event_listener(
                EventType.TransferComplete, self.on_transfer_complete
            )
            logger.info("[FanArt] 已注册 TransferComplete 事件监听")

        # 立即运行一次
        if self._onlyonce:
            logger.info("[FanArt] 立即运行一次全量扫描")
            self._scan_all()
            self._onlyonce = False
            self.__update_config()

        logger.info(f"[FanArt] v{self.plugin_version} 已启动")

    # ─── 事件处理 ─────────────────────────────────────────────

    def on_transfer_complete(self, event: Event = None):
        if not self._enabled or not self._enable_auto:
            return
        target_path = ""
        if event and event.event_data:
            target_path = event.event_data.get("target_path", "")
        if not target_path or not os.path.isdir(target_path):
            return
        logger.debug(f"[FanArt] TransferComplete → {target_path}")
        self._process_directory(target_path)

    # ─── 核心逻辑 ─────────────────────────────────────────────

    def _process_directory(self, dir_path: str):
        ext_list = self.__parse_list(self._extensions, ["jpg", "jpeg", "png", "webp"])
        type_list = self.__parse_list(self._image_types, ["fanart", "background", "backdrop", "thumb"])

        existing = self._get_existing(dir_path, ext_list, type_list)
        if not existing or len(existing) == len(type_list):
            return

        src_type, src_path = existing[0]
        src_ext = src_path.rsplit(".", 1)[-1].lower()
        copied_list = []

        for img_type in type_list:
            if self._find_image(dir_path, img_type, ext_list):
                continue
            dst = os.path.join(dir_path, f"{img_type}.{src_ext}")
            try:
                shutil.copy(src_path, dst)
                copied_list.append(img_type)
                logger.info(f"[FanArt] ✔ {os.path.basename(dir_path)}: {src_type}.{src_ext} → {img_type}.{src_ext}")
            except OSError as err:
                logger.error(f"[FanArt] ✘ 补充 {img_type} 失败: {err}")

        if copied_list and self._notify:
            self.post_message(
                mtype=NotificationType.MediaServer,
                title="【FanArt守护者】",
                text=f"目录：{os.path.basename(dir_path)}\n"
                     f"已从 {src_type}.{src_ext} 补充：{', '.join(copied_list)}",
            )

    def _scan_all(self):
        media_root = getattr(self, "_media_root", "") or self._get_media_root()
        if not media_root or not os.path.isdir(media_root):
            logger.warn("[FanArt] 未配置媒体库根目录或目录不存在，跳过全量扫描")
            return
        count = 0
        for root, dirs, _ in os.walk(media_root):
            dirs[:] = [d for d in dirs if not d.startswith(".")]
            if self._is_media_dir(root):
                self._process_directory(root)
                count += 1
        logger.info(f"[FanArt] 全量扫描完成，处理 {count} 个目录")
        if self._notify:
            self.post_message(
                mtype=NotificationType.MediaServer,
                title="【FanArt守护者】全量扫描完成",
                text=f"共扫描 {count} 个媒体目录，缺失图片已补充",
            )

    # ─── 辅助方法 ─────────────────────────────────────────────

    @staticmethod
    def __parse_list(raw: str, fallback: List[str]) -> List[str]:
        result = [s.strip().lstrip(".") for s in raw.split(",") if s.strip()]
        return result or fallback

    @staticmethod
    def _find_image(dir_path: str, img_type: str, ext_list: List[str]) -> Optional[str]:
        for ext in ext_list:
            p = os.path.join(dir_path, f"{img_type}.{ext}")
            if os.path.isfile(p):
                return p
        return None

    @staticmethod
    def _get_existing(dir_path: str, ext_list: List[str], type_list: List[str]) -> List[Tuple[str, str]]:
        result = []
        for t in type_list:
            p = FanArtGuard._find_image(dir_path, t, ext_list)
            if p:
                result.append((t, p))
        return result

    @staticmethod
    def _is_media_dir(dir_path: str) -> bool:
        suffixes = {".mp4", ".mkv", ".avi", ".ts", ".mov", ".wmv",
                    ".flv", ".m2ts", ".iso", ".nfo", ".srt", ".ass", ".ssa"}
        try:
            for f in os.listdir(dir_path):
                if os.path.splitext(f)[1].lower() in suffixes:
                    return True
        except OSError:
            pass
        return False

    def _get_media_root(self) -> str:
        try:
            from app.core.config import settings
            return getattr(settings, "MEDIA_ROOT", "") or getattr(settings, "LIBRARY_PATH", "")
        except ImportError:
            return ""

    # ─── 配置页面 ─────────────────────────────────────────────

    def get_form(self) -> Tuple[List[dict], Dict[str, Any]]:
        return [
            {
                'component': 'VForm',
                'content': [
                    {
                        'component': 'VRow',
                        'content': [
                            {
                                'component': 'VCol',
                                'props': {'cols': 12, 'md': 4},
                                'content': [
                                    {
                                        'component': 'VSwitch',
                                        'props': {'model': 'enabled', 'label': '启用插件'}
                                    }
                                ]
                            },
                            {
                                'component': 'VCol',
                                'props': {'cols': 12, 'md': 4},
                                'content': [
                                    {
                                        'component': 'VSwitch',
                                        'props': {'model': 'enable_auto', 'label': '自动触发（监听文件入库）'}
                                    }
                                ]
                            },
                            {
                                'component': 'VCol',
                                'props': {'cols': 12, 'md': 4},
                                'content': [
                                    {
                                        'component': 'VSwitch',
                                        'props': {'model': 'notify', 'label': '操作通知'}
                                    }
                                ]
                            },
                        ]
                    },
                    {
                        'component': 'VRow',
                        'content': [
                            {
                                'component': 'VCol',
                                'props': {'cols': 12, 'md': 4},
                                'content': [
                                    {
                                        'component': 'VSwitch',
                                        'props': {'model': 'enable_cron', 'label': '定时全量扫描'}
                                    }
                                ]
                            },
                            {
                                'component': 'VCol',
                                'props': {'cols': 12, 'md': 4},
                                'content': [
                                    {
                                        'component': 'VTextField',
                                        'props': {
                                            'model': 'cron',
                                            'label': 'Cron 表达式',
                                            'placeholder': '0 3 * * *'
                                        }
                                    }
                                ]
                            },
                            {
                                'component': 'VCol',
                                'props': {'cols': 12, 'md': 4},
                                'content': [
                                    {
                                        'component': 'VSwitch',
                                        'props': {'model': 'onlyonce', 'label': '立即运行一次全量扫描'}
                                    }
                                ]
                            },
                        ]
                    },
                    {
                        'component': 'VRow',
                        'content': [
                            {
                                'component': 'VCol',
                                'props': {'cols': 12, 'md': 6},
                                'content': [
                                    {
                                        'component': 'VTextField',
                                        'props': {
                                            'model': 'extensions',
                                            'label': '图片扩展名',
                                            'placeholder': 'jpg,jpeg,png,webp'
                                        }
                                    }
                                ]
                            },
                            {
                                'component': 'VCol',
                                'props': {'cols': 12, 'md': 6},
                                'content': [
                                    {
                                        'component': 'VTextField',
                                        'props': {
                                            'model': 'image_types',
                                            'label': '图片类型（优先级从高到低）',
                                            'placeholder': 'fanart,background,backdrop,thumb'
                                        }
                                    }
                                ]
                            },
                        ]
                    },
                    {
                        'component': 'VRow',
                        'content': [
                            {
                                'component': 'VCol',
                                'props': {'cols': 12},
                                'content': [
                                    {
                                        'component': 'VAlert',
                                        'props': {
                                            'type': 'info',
                                            'variant': 'tonal',
                                            'text': '自动触发：监听 MoviePilot TransferComplete 事件，即时处理新入库媒体。\n'
                                                    '定时扫描：按 Cron 定期全量扫描，兜底补充遗漏。\n'
                                                    '优先级：fanart > background > backdrop > thumb。'
                                        }
                                    }
                                ]
                            }
                        ]
                    },
                ]
            }
        ], {
            "enabled": False,
            "enable_auto": True,
            "enable_cron": False,
            "cron": "0 3 * * *",
            "extensions": "jpg,jpeg,png,webp",
            "image_types": "fanart,background,backdrop,thumb",
            "notify": False,
            "onlyonce": False,
        }

    def get_page(self) -> List[dict]:
        return [
            {
                'component': 'VAlert',
                'props': {
                    'type': 'info',
                    'variant': 'tonal',
                    'text': 'FanArt守护者 v1.0 已就绪。\n'
                            '自动监听 TransferComplete 事件，即时补充缺失图片。\n'
                            '支持：fanart > background > backdrop > thumb。'
                }
            }
        ]

    # ─── 定时服务 ─────────────────────────────────────────────

    def get_service(self) -> List[Dict[str, Any]]:
        if self._enabled and self._enable_cron and self._cron:
            from apscheduler.triggers.cron import CronTrigger
            return [{
                "id": "FanArtGuard.FullScan",
                "name": "FanArt全量扫描定时服务",
                "trigger": CronTrigger.from_crontab(self._cron),
                "func": self._scan_all,
                "kwargs": {}
            }]
        return []

    # ─── API 端点 ─────────────────────────────────────────────

    def get_api(self) -> List[Dict[str, Any]]:
        return [
            {
                "path": "/scan",
                "endpoint": self._api_scan,
                "methods": ["GET"],
                "auth": "bear",
                "summary": "手动触发扫描",
                "description": "指定目录扫描或全量扫描媒体库",
            },
            {
                "path": "/status",
                "endpoint": self._api_status,
                "methods": ["GET"],
                "auth": "bear",
                "summary": "插件状态",
                "description": "返回插件运行状态信息",
            },
        ]

    def _api_scan(self, path: str = ""):
        import json
        from fastapi.responses import Response
        if path and os.path.isdir(path):
            self._process_directory(path)
            return Response(content=json.dumps({"code": 0, "msg": f"已处理: {path}"}), media_type="application/json")
        elif not path:
            self._scan_all()
            return Response(content=json.dumps({"code": 0, "msg": "全量扫描已启动"}), media_type="application/json")
        else:
            return Response(content=json.dumps({"code": 1, "msg": f"路径无效: {path}"}), media_type="application/json")

    def _api_status(self):
        import json
        from fastapi.responses import Response
        return Response(content=json.dumps({
            "enabled": self._enabled,
            "enable_auto": self._enable_auto,
            "enable_cron": self._enable_cron,
            "cron": self._cron,
            "version": self.plugin_version,
        }), media_type="application/json")

    # ─── 生命周期 ─────────────────────────────────────────────

    def get_state(self) -> bool:
        return self._enabled

    @staticmethod
    def get_command() -> List[Dict[str, Any]]:
        return []

    def stop_service(self):
        try:
            eventmanager.remove_event_listener(
                EventType.TransferComplete, self.on_transfer_complete
            )
        except Exception:
            pass
        logger.info("[FanArt] 已停止")

    # ─── 内部方法 ─────────────────────────────────────────────

    def __update_config(self):
        self.update_config({
            "enabled": self._enabled,
            "enable_auto": self._enable_auto,
            "enable_cron": self._enable_cron,
            "cron": self._cron,
            "extensions": self._extensions,
            "image_types": self._image_types,
            "notify": self._notify,
            "onlyonce": self._onlyonce,
        })
