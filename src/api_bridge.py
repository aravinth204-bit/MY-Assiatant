import json
import threading
import time
import webview
from typing import Dict, Any, List, Optional

from src.logger import get_logger
from src.file_finder import search_files
from src import gemini_chat

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
        self._observation_lock = threading.Lock()
        self._window_observation_active = False
        self._last_observed_window = None
        self._file_search_lock = threading.Lock()
        self._file_search_state = None

    def set_roamer(self, roamer):
        self._roamer = roamer

    def set_character_window(self, window, x: int = 40, y: int = 0, width: int = 120, height: int = 120):
        self._character_window = window
        self._win_x = int(x)
        self._win_y = int(y)
        self._character_width = int(width)
        self._character_height = int(height)

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

    def get_window_observation_status(self) -> bool:
        with self._observation_lock:
            return self._window_observation_active

    def start_window_observation(self) -> bool:
        with self._observation_lock:
            self._window_observation_active = True
            self._last_observed_window = None
        self.notify_ui('idle', 'App activity observation is on. Window titles stay on this device.')
        return True

    def stop_window_observation(self) -> bool:
        with self._observation_lock:
            self._window_observation_active = False
            self._last_observed_window = None
        self.notify_ui('idle', 'App activity observation is off.')
        return False

    def observe_active_window(self, window_title: str):
        with self._observation_lock:
            if not self._window_observation_active or window_title == self._last_observed_window:
                return
            self._last_observed_window = window_title
        self.notify_ui('idle', f'Active window: {window_title}')

    def save_config(self, config_dict: Dict[str, Any]) -> bool:
        try:
            self._config_manager.config = config_dict
            return self._config_manager.save_config()
        except Exception as e:
            logger.error(f"Error in ApiBridge.save_config: {e}", exc_info=True)
            return False

    def set_website_limit(self, domain: str, minutes: int) -> Dict[str, Any]:
        if domain not in ("youtube.com", "instagram.com"):
            raise ValueError("ARAVI can change limits for YouTube or Instagram only.")
        if isinstance(minutes, bool) or not isinstance(minutes, int) or not 1 <= minutes <= 300:
            raise ValueError("The limit must be a whole number between 1 and 300 minutes.")

        original_config = self._config_manager.config
        updated_config = dict(original_config)
        sites = [
            dict(site)
            for site in updated_config.get("tracked_websites", [])
            if isinstance(site, dict)
        ]
        site = next(
            (
                item for item in sites
                if isinstance(item.get("domain"), str)
                and item["domain"].lower().removeprefix("www.") == domain
            ),
            None,
        )
        if site is None:
            site = {"domain": domain, "limit_minutes": minutes, "used_seconds": 0}
            sites.append(site)
        else:
            site["limit_minutes"] = minutes
        updated_config["tracked_websites"] = sites
        if not self.save_config(updated_config):
            self._config_manager.config = original_config
            raise OSError("ARAVI could not save the website limit.")
        return {"domain": domain, "limit_minutes": minutes}

    def get_chat_status(self) -> Dict[str, bool]:
        return {"gemini_configured": gemini_chat.is_configured()}

    def chat_with_gemini(self, message: str, history: List[Dict[str, str]] = None) -> str:
        return gemini_chat.chat(message, history)

    def start_file_search(self, query: str) -> str:
        if not isinstance(query, str) or not query.strip():
            raise ValueError("Enter a file name to search for.")
        if len(query) > 128:
            raise ValueError("The file name search must be 128 characters or fewer.")
        cancel_event = threading.Event()
        search_id = f"file-search-{time.time_ns()}"
        state = {
            "id": search_id,
            "query": query.strip(),
            "status": "running",
            "scanned_directories": 0,
            "scanned_entries": 0,
            "skipped_directories": 0,
            "skipped_items": 0,
            "match_count": 0,
            "current_path": "Preparing local drive search...",
            "matches": [],
            "truncated": False,
            "cancelled": False,
            "error": None,
            "cancel_event": cancel_event,
        }
        with self._file_search_lock:
            if self._file_search_state and self._file_search_state["status"] == "running":
                raise RuntimeError("A file search is already running.")
            self._file_search_state = state

        threading.Thread(
            target=self._run_file_search,
            args=(state,),
            name="ARAVI-FileSearch",
            daemon=True,
        ).start()
        return search_id

    def _run_file_search(self, state: Dict[str, Any]):
        def update_progress(progress):
            with self._file_search_lock:
                if self._file_search_state is state:
                    state.update(progress)

        try:
            result = search_files(
                state["query"],
                progress_callback=update_progress,
                cancel_event=state["cancel_event"],
            )
            with self._file_search_lock:
                if self._file_search_state is state:
                    state.update(result)
                    state["match_count"] = len(result["matches"])
                    state["status"] = "cancelled" if result["cancelled"] else "completed"
        except Exception as error:
            logger.error("Local file search failed: %s", error, exc_info=True)
            with self._file_search_lock:
                if self._file_search_state is state:
                    state["status"] = "failed"
                    state["error"] = str(error)

    def get_file_search_status(self, search_id: str) -> Dict[str, Any]:
        with self._file_search_lock:
            state = self._file_search_state
            if not state or state["id"] != search_id:
                raise ValueError("This file search is no longer available.")
            return {
                key: value
                for key, value in state.items()
                if key not in ("cancel_event",)
            }

    def cancel_file_search(self, search_id: str) -> bool:
        with self._file_search_lock:
            state = self._file_search_state
            if not state or state["id"] != search_id:
                raise ValueError("This file search is no longer available.")
            if state["status"] != "running":
                return False
            state["cancel_event"].set()
            state["current_path"] = "Stopping search..."
            return True

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
                self._character_window.resize(self._character_width, self._character_height)
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
                    speech_json = json.dumps(speech_text)
                    self._character_window.evaluate_js(f"window.setPose('{pose}', {speech_json});")
                else:
                    self._character_window.evaluate_js(f"window.setPose('{pose}');")
                return True
            except BaseException as e:
                logger.debug(f"Failed to evaluate JS notify_ui: {e}")
                return False
        return False
