import json
import time
import webview
from typing import Dict, Any, List, Optional

from src.logger import get_logger

logger = get_logger("api_bridge")

try:
    import win32api
except ImportError:
    win32api = None

class ApiBridge:
    def __init__(self, system_monitor, smart_cleaner, tab_closer, reminder_manager, config_manager, settings_window_func=None):
        self._system_monitor = system_monitor
        self._smart_cleaner = smart_cleaner
        self._tab_closer = tab_closer
        self._reminder_manager = reminder_manager
        self._config_manager = config_manager
        self._settings_window_func = settings_window_func
        self._character_window = None
        self._notification_cooldowns: Dict[str, float] = {}
        self._roamer = None
        self._warning_active = False
        self._warning_origin = None

    def set_roamer(self, roamer):
        self._roamer = roamer

    def set_character_window(self, window, x: int = 40, y: int = 0):
        self._character_window = window
        self._win_x = int(x)
        self._win_y = int(y)

    def get_system_stats(self) -> Dict[str, Any]:
        try:
            return self._system_monitor.get_system_stats()
        except Exception as e:
            logger.error(f"Error in ApiBridge.get_system_stats: {e}", exc_info=True)
            return {}

    def get_top_processes(self, limit: int = 5, sort_by: str = 'memory_percent') -> List[Dict[str, Any]]:
        try:
            return self._system_monitor.get_top_processes(limit=limit, sort_by=sort_by)
        except Exception as e:
            logger.error(f"Error in ApiBridge.get_top_processes: {e}", exc_info=True)
            return []

    def terminate_process(self, pid: int) -> bool:
        try:
            return self._system_monitor.terminate_process(pid)
        except Exception as e:
            logger.error(f"Error in ApiBridge.terminate_process: {e}", exc_info=True)
            return False

    def scan_cleaner(self) -> List[Dict[str, Any]]:
        try:
            return self._smart_cleaner.run_full_scan()
        except Exception as e:
            logger.error(f"Error in ApiBridge.scan_cleaner: {e}", exc_info=True)
            return []

    def _is_window_alive(self) -> bool:
        if not self._character_window:
            return False
        try:
            native = getattr(self._character_window, 'native', None)
            if native:
                if getattr(native, 'IsDisposed', False) or getattr(native, 'Disposing', False):
                    return False
            return True
        except BaseException:
            return False

    def perform_cleanup(self, file_paths: List[str]) -> Dict[str, Any]:
        try:
            result = self._smart_cleaner.clean_selected_files(file_paths)
            if result.get("freed_mb", 0) > 0 and self._is_window_alive():
                try:
                    self._character_window.evaluate_js(f"window.setPose('celebrate', 'Cleaned {result['freed_mb']} MB of junk!');")
                except BaseException:
                    pass
            return result
        except Exception as e:
            logger.error(f"Error in ApiBridge.perform_cleanup: {e}", exc_info=True)
            return {"success_count": 0, "failed_count": len(file_paths), "freed_mb": 0.0, "failed": []}

    def get_config(self) -> Dict[str, Any]:
        try:
            return self._config_manager.config
        except Exception as e:
            logger.error(f"Error in ApiBridge.get_config: {e}", exc_info=True)
            return {}

    def save_config(self, config_dict: Dict[str, Any]) -> bool:
        try:
            self._config_manager.config = config_dict
            return self._config_manager.save_config()
        except Exception as e:
            logger.error(f"Error in ApiBridge.save_config: {e}", exc_info=True)
            return False

    def start_pomodoro(self, minutes: int = 25):
        try:
            self._reminder_manager.start_pomodoro(minutes)
        except Exception as e:
            logger.error(f"Error in ApiBridge.start_pomodoro: {e}", exc_info=True)

    def stop_pomodoro(self):
        try:
            self._reminder_manager.stop_pomodoro()
        except Exception as e:
            logger.error(f"Error in ApiBridge.stop_pomodoro: {e}", exc_info=True)

    def get_pomodoro_status(self) -> Dict[str, Any]:
        try:
            return self._reminder_manager.get_pomodoro_status()
        except Exception as e:
            logger.error(f"Error in ApiBridge.get_pomodoro_status: {e}", exc_info=True)
            return {"active": False, "remaining_seconds": 0, "mode": "idle"}

    def open_settings(self):
        try:
            if self._settings_window_func:
                self._settings_window_func()
        except Exception as e:
            logger.error(f"Error in ApiBridge.open_settings: {e}", exc_info=True)

    def move_window_by(self, dx: int, dy: int):
        if self._is_window_alive():
            try:
                self._win_x = int(self._win_x + dx)
                self._win_y = int(self._win_y + dy)
                self._character_window.move(self._win_x, self._win_y)
                return True
            except BaseException as e:
                logger.debug(f"Error moving character window by ({dx},{dy}): {e}")
                return False
        return False

    def move_window_to(self, x: int, y: int):
        if self._is_window_alive():
            try:
                self._win_x = int(x)
                self._win_y = int(y)
                self._character_window.move(self._win_x, self._win_y)
                return True
            except BaseException as e:
                logger.debug(f"Error moving character window to ({x},{y}): {e}")
                return False
        return False

    def pause_roaming(self, seconds: float = 15.0):
        if self._roamer:
            self._roamer.pause(seconds)

    def update_website_warning(self, domain: str, seconds_remaining: Optional[int]):
        if not self._is_window_alive():
            return

        if seconds_remaining is None:
            if not self._warning_active:
                return
            try:
                self._character_window.evaluate_js("if(window.hideTimeLimitWarning) window.hideTimeLimitWarning();")
                self._character_window.resize(120, 120)
                if self._warning_origin:
                    self._character_window.move(*self._warning_origin)
            except BaseException as e:
                logger.debug(f"Error restoring mascot after website warning: {e}")
            finally:
                self._warning_active = False
                self._warning_origin = None
            return

        self.pause_roaming(seconds_remaining + 2)
        if not self._warning_active:
            self._warning_origin = (self._win_x, self._win_y)
            screen_width = win32api.GetSystemMetrics(0) if win32api else 1920
            warning_width = 520
            try:
                self._character_window.resize(warning_width, 180)
                self._character_window.move(max(0, (screen_width - warning_width) // 2), 36)
                self._warning_active = True
            except BaseException as e:
                logger.error(f"Error showing website time-limit warning: {e}", exc_info=True)
                return

        try:
            domain_json = json.dumps(domain)
            self._character_window.evaluate_js(
                f"if(window.showTimeLimitWarning) window.showTimeLimitWarning({domain_json}, {seconds_remaining});"
            )
        except BaseException as e:
            logger.debug(f"Error updating website time-limit countdown: {e}")

    def set_orientation(self, mode: str, direction: str):
        if self._is_window_alive():
            try:
                self._character_window.evaluate_js(f"if(window.setOrientation) window.setOrientation('{mode}', '{direction}');")
            except BaseException:
                pass

    def trigger_web_line(self, direction: str):
        if self._is_window_alive():
            try:
                self._character_window.evaluate_js(f"if(window.triggerWebLine) window.triggerWebLine('{direction}');")
            except BaseException:
                pass

    def clear_web_line(self):
        if self._is_window_alive():
            try:
                self._character_window.evaluate_js("if(window.clearWebLine) window.clearWebLine();")
            except BaseException:
                pass

    def notify_ui(self, pose: str, speech_text: str = None, cooldown_key: str = None, cooldown_seconds: float = 300.0) -> bool:
        """Send notification speech bubble to mascot UI with optional cooldown."""
        now = time.time()
        if cooldown_key:
            last_shown = self._notification_cooldowns.get(cooldown_key, 0.0)
            if (now - last_shown) < cooldown_seconds:
                return False
            self._notification_cooldowns[cooldown_key] = now

        if self._is_window_alive():
            try:
                if speech_text:
                    clean_text = speech_text.replace("'", "\\'").replace('"', '\\"')
                    self._character_window.evaluate_js(f"window.setPose('{pose}', '{clean_text}');")
                else:
                    self._character_window.evaluate_js(f"window.setPose('{pose}');")
                return True
            except BaseException as e:
                logger.debug(f"Failed to evaluate JS notify_ui: {e}")
                return False
        return False

