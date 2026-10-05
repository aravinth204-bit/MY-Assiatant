import time
import threading
import pyautogui
from typing import Callable, Optional

from src.logger import get_logger

logger = get_logger("tab_closer")

try:
    import win32gui
    HAS_WIN32 = True
except ImportError:
    HAS_WIN32 = False

class TabCloser:
    def __init__(
        self,
        config_manager,
        on_warning_callback: Optional[Callable[[str, Optional[int]], None]] = None,
        on_folder_state_callback: Optional[Callable[[Optional[str]], None]] = None,
    ):
        self.config_manager = config_manager
        self.on_warning_callback = on_warning_callback
        self.on_folder_state_callback = on_folder_state_callback
        self.running = False
        self._thread = None
        self._stop_event = threading.Event()

    def get_active_window_info(self):
        if HAS_WIN32:
            try:
                hwnd = win32gui.GetForegroundWindow()
                return win32gui.GetWindowText(hwnd) or "", win32gui.GetClassName(hwnd) or ""
            except Exception as e:
                logger.debug(f"Error getting foreground window info: {e}")
        return "", ""

    def get_active_window_title(self) -> str:
        return self.get_active_window_info()[0]

    @staticmethod
    def _site_matches_title(domain: str, title: str) -> bool:
        domain = domain.lower()
        if "youtube" in domain or "youtu.be" in domain:
            return "youtube" in title or "youtu.be" in title
        if "instagram" in domain:
            return "instagram" in title
        return domain in title

    def start(self):
        try:
            if not self._thread or not self._thread.is_alive():
                self._stop_event.clear()
                self.running = True
                self._thread = threading.Thread(target=self._loop, daemon=True)
                self._thread.start()
                logger.info("TabCloser service started")
        except Exception as e:
            logger.error(f"Error starting TabCloser: {e}", exc_info=True)

    def stop(self):
        self.running = False
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3.0)
            if self._thread.is_alive():
                logger.warning("TabCloser thread did not stop within 3 seconds")
        logger.info("TabCloser service stopped")

    def _loop(self):
        pyautogui.FAILSAFE = False
        last_check_time = time.monotonic()
        while self.running and not self._stop_event.is_set():
            try:
                now = time.monotonic()
                elapsed_seconds = max(0.0, now - last_check_time)
                last_check_time = now
                active_title, window_class = self.get_active_window_info()
                title = active_title.lower()
                folder_name = active_title.strip() if window_class in ("CabinetWClass", "ExploreWClass") else None
                if self.on_folder_state_callback:
                    self.on_folder_state_callback(folder_name)

                if title:
                    tracked_sites = self.config_manager.get("tracked_websites", [])
                    for site in tracked_sites:
                        domain = site.get("domain", "").lower()
                        limit_mins = site.get("limit_minutes", 0)
                        used_secs = site.get("used_seconds", 0)
                        limit_secs = limit_mins * 60

                        if domain and self._site_matches_title(domain, title):
                            site["used_seconds"] = used_secs + elapsed_seconds
                            self.config_manager.save_config()

                            if site["used_seconds"] >= limit_secs and limit_mins > 0:
                                logger.info(f"Time limit reached for {domain} (limit: {limit_mins}m, used: {site['used_seconds']}s)")

                                cancelled = False
                                tab_closed = False
                                for seconds_left in range(10, 0, -1):
                                    if not self.running or self._stop_event.is_set() or not self._site_matches_title(domain, self.get_active_window_title().lower()):
                                        cancelled = True
                                        break
                                    if self.on_warning_callback:
                                        self.on_warning_callback(domain, seconds_left)
                                    if self._stop_event.wait(1.0):
                                        cancelled = True
                                        break

                                if self.on_warning_callback:
                                    self.on_warning_callback(domain, None)

                                if not cancelled and self._site_matches_title(domain, self.get_active_window_title().lower()):
                                    try:
                                        pyautogui.hotkey('ctrl', 'w')
                                        tab_closed = True
                                    except Exception as pe:
                                        logger.error(f"pyautogui error closing tab: {pe}", exc_info=True)
                                elif not cancelled:
                                    logger.info(f"Active site changed before closing {domain}; tab closure cancelled.")

                                if tab_closed:
                                    site["used_seconds"] = 0
                                    self.config_manager.save_config()
                                break
                            break
            except Exception as e:
                logger.error(f"Unexpected error in TabCloser loop: {e}", exc_info=True)

            last_check_time = time.monotonic()
            self._stop_event.wait(2.0)
