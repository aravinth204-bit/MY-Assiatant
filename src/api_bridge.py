import webview
from typing import Dict, Any, List

class ApiBridge:
    def __init__(self, system_monitor, smart_cleaner, tab_closer, reminder_manager, config_manager, settings_window_func=None):
        self._system_monitor = system_monitor
        self._smart_cleaner = smart_cleaner
        self._tab_closer = tab_closer
        self._reminder_manager = reminder_manager
        self._config_manager = config_manager
        self._settings_window_func = settings_window_func
        self._character_window = None

    def set_character_window(self, window, x: int = 40, y: int = 0):
        self._character_window = window
        self._win_x = x
        self._win_y = y

    def get_system_stats(self) -> Dict[str, Any]:
        return self._system_monitor.get_system_stats()

    def get_top_processes(self, limit: int = 5, sort_by: str = 'memory_percent') -> List[Dict[str, Any]]:
        return self._system_monitor.get_top_processes(limit=limit, sort_by=sort_by)

    def terminate_process(self, pid: int) -> bool:
        return self._system_monitor.terminate_process(pid)

    def scan_cleaner(self) -> List[Dict[str, Any]]:
        return self._smart_cleaner.run_full_scan()

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
        result = self._smart_cleaner.clean_selected_files(file_paths)
        if result.get("freed_mb", 0) > 0 and self._is_window_alive():
            try:
                self._character_window.evaluate_js(f"window.setPose('celebrate', 'Cleaned {result['freed_mb']} MB of junk!');")
            except BaseException:
                pass
        return result

    def get_config(self) -> Dict[str, Any]:
        return self._config_manager.config

    def save_config(self, config_dict: Dict[str, Any]) -> bool:
        self._config_manager.config = config_dict
        return self._config_manager.save_config()

    def start_pomodoro(self, minutes: int = 25):
        self._reminder_manager.start_pomodoro(minutes)

    def stop_pomodoro(self):
        self._reminder_manager.stop_pomodoro()

    def get_pomodoro_status(self) -> Dict[str, Any]:
        return self._reminder_manager.get_pomodoro_status()

    def open_settings(self):
        if self._settings_window_func:
            self._settings_window_func()

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
            except BaseException:
                pass

    def move_window_to(self, x: int, y: int):
        if self._is_window_alive():
            try:
                self._character_window.move(int(x), int(y))
            except BaseException:
                pass

    def notify_ui(self, pose: str, speech_text: str):
        if self._is_window_alive():
            try:
                clean_text = speech_text.replace("'", "\\'").replace('"', '\\"')
                self._character_window.evaluate_js(f"window.setPose('{pose}', '{clean_text}');")
            except BaseException:
                pass
