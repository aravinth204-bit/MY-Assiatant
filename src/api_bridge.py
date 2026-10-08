import json
import os
import threading
import time
from datetime import date, datetime
import webview
from typing import Callable, Dict, Any, List, Optional

from src.logger import get_logger
from src.file_finder import search_files
from src import gemini_chat
from src import local_chat
from src import opencode_chat

logger = get_logger("api_bridge")


def _chat_api_result(chat_function: Callable[..., str], *args: Any) -> Dict[str, str]:
    try:
        return {"reply": chat_function(*args)}
    except (RuntimeError, ValueError) as error:
        return {"error": str(error)}


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
        self._last_activity_app = None
        self._last_activity_at = None
        self._last_activity_saved_at = 0.0
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

    def get_focus_mode(self) -> Dict[str, Any]:
        try:
            return self._config_manager.get("focus_mode", {})
        except Exception as e:
            logger.error(f"Error in ApiBridge.get_focus_mode: {e}", exc_info=True)
            return {}

    def set_focus_mode(self, enabled: bool, work_minutes: int = 25, blocked_websites: List[str] = None) -> Dict[str, Any]:
        if isinstance(enabled, bool) is False:
            raise ValueError("Focus mode enabled must be a boolean")
        
        if isinstance(work_minutes, int) is False or not 1 <= work_minutes <= 120:
            raise ValueError("Work minutes must be an integer between 1 and 120")
        
        original_config = self._config_manager.config
        updated_config = dict(original_config)
        updated_config["focus_mode"] = {
            "enabled": enabled,
            "work_minutes": work_minutes,
            "blocked_websites": blocked_websites or ["youtube.com", "instagram.com"],
            "auto_pause_mascot": True
        }
        if not self.save_config(updated_config):
            self._config_manager.config = original_config
            raise OSError("ARAVI could not save the focus mode settings.")
        return self.get_focus_mode()

    def add_ai_model(self, name: str, api_type: str, config: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(name, str) or not name.strip():
            raise ValueError("AI model name must be a non-empty string")
        
        if api_type not in ("gemini", "local", "opencode"):
            raise ValueError("AI model type must be one of: gemini, local, opencode")
        
        original_config = self._config_manager.config
        updated_config = dict(original_config)
        
        # Initialize ai_models list if not exists
        if "ai_models" not in updated_config:
            updated_config["ai_models"] = []
        
        # Check if model already exists
        models = updated_config.get("ai_models", [])
        for model in models:
            if model.get("name") == name:
                raise ValueError(f"AI model '{name}' already exists.")
        
        new_model = {
            "name": name,
            "api_type": api_type,
            "config": config
        }
        models.append(new_model)
        updated_config["ai_models"] = models
        
        if not self.save_config(updated_config):
            self._config_manager.config = original_config
            raise OSError("ARAVI could not save the AI model configuration.")
        
        return {"name": name, "api_type": api_type, "status": "added"}

    def remove_ai_model(self, name: str) -> Dict[str, Any]:
        if not isinstance(name, str) or not name.strip():
            raise ValueError("AI model name must be a non-empty string")
        
        original_config = self._config_manager.config
        updated_config = dict(original_config)
        
        models = updated_config.get("ai_models", [])
        models = [m for m in models if m.get("name") != name]
        updated_config["ai_models"] = models
        
        if not self.save_config(updated_config):
            self._config_manager.config = original_config
            raise OSError("ARAVI could not remove the AI model configuration.")
        
        return {"name": name, "status": "removed"}

    def list_ai_models(self) -> List[Dict[str, Any]]:
        try:
            return self._config_manager.get("ai_models", [])
        except Exception as e:
            logger.error(f"Error listing AI models: {e}", exc_info=True)
            return []

    def set_config(self, config_dict: Dict[str, Any]) -> bool:
        try:
            self._config_manager.config = config_dict
            return self._config_manager.save_config()
        except Exception as e:
            logger.error(f"Error in ApiBridge.set_config: {e}", exc_info=True)
            return False

    def get_window_observation_status(self) -> bool:
        with self._observation_lock:
            return self._window_observation_active

    def start_window_observation(self) -> bool:
        with self._observation_lock:
            self._window_observation_active = True
            self._last_observed_window = None
            self._last_activity_app = None
            self._last_activity_at = None
            self._last_activity_saved_at = time.monotonic()
        self.notify_ui('idle', 'App activity observation is on. Window titles stay on this device.')
        return True

    def stop_window_observation(self) -> bool:
        with self._observation_lock:
            self._flush_current_app_activity(time.monotonic())
            self._window_observation_active = False
            self._last_observed_window = None
            self._last_activity_app = None
            self._last_activity_at = None
        self.notify_ui('idle', 'App activity observation is off.')
        return False

    def get_app_activity_history(self) -> List[Dict[str, Any]]:
        with self._observation_lock:
            history = self._config_manager.get("app_activity_history", [])
            if not isinstance(history, list):
                return []
            records = [
                dict(entry)
                for entry in history
                if isinstance(entry, dict)
                and isinstance(entry.get("app"), str)
                and isinstance(entry.get("date"), str)
            ]
            return sorted(
                records,
                key=lambda item: (item["date"], self._activity_seconds(item)),
                reverse=True,
            )

    def get_dashboard_activity_history(self) -> List[Dict[str, str]]:
        with self._observation_lock:
            history = self._config_manager.get("dashboard_activity_history", [])
            if not isinstance(history, list):
                return []
            records = [
                {"timestamp": entry["timestamp"], "label": entry["label"]}
                for entry in history
                if isinstance(entry, dict)
                and isinstance(entry.get("timestamp"), str)
                and isinstance(entry.get("label"), str)
            ]
            return sorted(records, key=lambda item: item["timestamp"], reverse=True)

    def record_dashboard_activity(self, activity_type: str) -> bool:
        labels = {
            "chat": "Chat with ARAVI",
            "file_search": "Searched local file names",
            "website_limits": "Updated website limits",
        }
        if not isinstance(activity_type, str) or activity_type not in labels:
            raise ValueError("Unsupported dashboard activity.")

        with self._observation_lock:
            history = self._config_manager.get("dashboard_activity_history", [])
            if not isinstance(history, list):
                history = []
            existing = [
                entry for entry in history
                if isinstance(entry, dict)
                and isinstance(entry.get("timestamp"), str)
                and isinstance(entry.get("label"), str)
            ]
            record = {
                "timestamp": datetime.now().astimezone().isoformat(timespec="minutes"),
                "label": labels[activity_type],
            }
            self._config_manager.config["dashboard_activity_history"] = [record, *existing[:49]]
            if not self._config_manager.save_config():
                logger.error("Could not save dashboard activity history")
                return False
            return True

    def record_app_activity(self, app_name: str):
        if not isinstance(app_name, str):
            return
        app_name = os.path.basename(app_name.strip())
        if app_name.lower().endswith(".exe"):
            app_name = app_name[:-4]
        app_name = app_name.strip()
        if not app_name:
            return
        app_name = app_name[:128]

        with self._observation_lock:
            if not self._window_observation_active:
                return
            now = time.monotonic()
            previous_app = self._last_activity_app
            previous_at = self._last_activity_at
            if previous_app and previous_at is not None:
                self._add_app_activity_seconds(
                    previous_app,
                    min(15.0, max(0.0, now - previous_at)),
                )

            app_changed = previous_app != app_name
            self._last_activity_app = app_name
            self._last_activity_at = now
            if app_changed or now - self._last_activity_saved_at >= 30:
                self._save_app_activity()
                self._last_activity_saved_at = now

    def _flush_current_app_activity(self, now: float):
        if self._last_activity_app and self._last_activity_at is not None:
            self._add_app_activity_seconds(
                self._last_activity_app,
                min(15.0, max(0.0, now - self._last_activity_at)),
            )
            self._save_app_activity()
            self._last_activity_saved_at = now

    def _add_app_activity_seconds(self, app_name: str, seconds: float):
        if seconds <= 0:
            return
        history = self._config_manager.get("app_activity_history", [])
        if not isinstance(history, list):
            history = []
        else:
            history = [entry for entry in history if isinstance(entry, dict)]
        today = date.today().isoformat()
        entry = next(
            (
                item for item in history
                if item.get("app") == app_name and item.get("date") == today
            ),
            None,
        )
        if entry is None:
            entry = {"date": today, "app": app_name, "seconds": 0.0}
            history.append(entry)
        try:
            previous_seconds = max(0.0, float(entry.get("seconds", 0) or 0))
        except (TypeError, ValueError):
            previous_seconds = 0.0
        entry["seconds"] = round(previous_seconds + seconds, 2)
        self._config_manager.config["app_activity_history"] = history

    def _save_app_activity(self):
        if not self._config_manager.save_config():
            logger.error("Could not save local app activity history")

    @staticmethod
    def _activity_seconds(entry: Dict[str, Any]) -> float:
        try:
            return max(0.0, float(entry.get("seconds", 0) or 0))
        except (TypeError, ValueError):
            return 0.0

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

    def get_water_reminder_status(self) -> Dict[str, Any]:
        return {
            "interval_minutes": self._config_manager.get("water_reminder_interval_minutes", 60),
            "pending": bool(self._config_manager.get("water_reminder_pending", False)),
        }

    def set_water_reminder_interval(self, minutes: int) -> Dict[str, Any]:
        if isinstance(minutes, bool) or not isinstance(minutes, int) or not 1 <= minutes <= 300:
            raise ValueError("The water reminder interval must be a whole number between 1 and 300 minutes.")

        original_config = self._config_manager.config
        updated_config = dict(original_config)
        updated_config.update({
            "water_reminder_interval_minutes": minutes,
            "water_reminder_next_at": time.time() + minutes * 60,
            "water_reminder_pending": False,
        })
        if not self.save_config(updated_config):
            self._config_manager.config = original_config
            raise OSError("ARAVI could not save the water reminder interval.")
        return self.get_water_reminder_status()

    def respond_to_water_reminder(self, answer: str) -> Dict[str, Any]:
        if answer not in ("yes", "no"):
            raise ValueError("Choose yes or no to respond to the water reminder.")
        if not self._config_manager.get("water_reminder_pending", False):
            raise ValueError("There is no water reminder waiting for a response.")

        interval = self._config_manager.get("water_reminder_interval_minutes", 60)
        next_interval = interval if answer == "yes" else 10
        original_config = self._config_manager.config
        updated_config = dict(original_config)
        updated_config.update({
            "water_reminder_pending": False,
            "water_reminder_next_at": time.time() + next_interval * 60,
        })
        if not self.save_config(updated_config):
            self._config_manager.config = original_config
            raise OSError("ARAVI could not save your water reminder response.")
        return {"next_reminder_minutes": next_interval}

    def show_water_reminder(self):
        if not self._settings_window_func:
            logger.error("Could not show water reminder because the Control Center is unavailable.")
            return
        try:
            self._settings_window_func()
        except Exception as error:
            logger.error("Could not open the Website Limits page for a water reminder: %s", error, exc_info=True)

    def get_chat_status(self) -> Dict[str, bool]:
        return {"gemini_configured": gemini_chat.is_configured()}

    def chat_with_gemini(
        self,
        message: str,
        history: List[Dict[str, str]] = None,
        use_search: bool = True,
    ) -> Dict[str, str]:
        return _chat_api_result(gemini_chat.chat, message, history, use_search)

    def chat_with_local_model(self, message: str, history: List[Dict[str, str]] = None) -> Dict[str, str]:
        return _chat_api_result(local_chat.chat, message, history)

    def chat_with_local_search(self, message: str, history: List[Dict[str, str]] = None) -> Dict[str, str]:
        return _chat_api_result(local_chat.chat_with_search, message, history)

    def chat_with_opencode(self, message: str, history: List[Dict[str, str]] = None) -> Dict[str, str]:
        return _chat_api_result(opencode_chat.chat, message, history)

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
