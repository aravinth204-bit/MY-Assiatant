import time
import webview
from typing import Dict, Any, List

from src.logger import get_logger

logger = get_logger("api_bridge")

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

    def set_character_window(self, window, x: int = 40, y: int = 0):
        self._character_window = window
        self._win_x = x
        self._win_y = y

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
                curr_x = getattr(self._character_window, 'x', None)
                curr_y = getattr(self._character_window, 'y', None)
                if curr_x is None or curr_x == 0:
                    curr_x = getattr(self, '_win_x', 40)
                if curr_y is None or curr_y == 0:
                    curr_y = getattr(self, '_win_y', 0)
                
                new_x = int(curr_x + dx)
                new_y = int(curr_y + dy)
                self._win_x = new_x
                self._win_y = new_y
                self._character_window.move(new_x, new_y)
            except BaseException as e:
                logger.debug(f"Error moving character window by ({dx},{dy}): {e}")

    def move_window_to(self, x: int, y: int):
        if self._is_window_alive():
            try:
                self._character_window.move(int(x), int(y))
            except BaseException as e:
                logger.debug(f"Error moving character window to ({x},{y}): {e}")

    def notify_ui(self, pose: str, speech_text: str, cooldown_key: str = None, cooldown_seconds: float = 300.0) -> bool:
        """Send notification speech bubble to mascot UI with optional cooldown."""
        now = time.time()
        if cooldown_key:
            last_shown = self._notification_cooldowns.get(cooldown_key, 0.0)
            if (now - last_shown) < cooldown_seconds:
                return False
            self._notification_cooldowns[cooldown_key] = now

        if self._is_window_alive():
            try:
                clean_text = speech_text.replace("'", "\\'").replace('"', '\\"')
                self._character_window.evaluate_js(f"window.setPose('{pose}', '{clean_text}');")
                return True
            except BaseException as e:
                logger.debug(f"Failed to evaluate JS notify_ui: {e}")
                return False
        return False

