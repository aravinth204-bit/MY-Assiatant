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
            if not self.running:
                self.running = True
                self._thread = threading.Thread(target=self._loop, daemon=True)
                self._thread.start()
                logger.info("TabCloser service started")
        except Exception as e:
            logger.error(f"Error starting TabCloser: {e}", exc_info=True)

    def stop(self):
        try:
            self.running = False
            logger.info("TabCloser service stopped")
        except Exception as e:
            logger.error(f"Error stopping TabCloser: {e}", exc_info=True)

    def _loop(self):
        pyautogui.FAILSAFE = False
        while self.running:
            try:
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
                            # Add 2 seconds to tracked time
                            site["used_seconds"] = used_secs + 2
                            self.config_manager.save_config()

                            if site["used_seconds"] >= limit_secs and limit_mins > 0:
                                logger.info(f"Time limit reached for {domain} (limit: {limit_mins}m, used: {site['used_seconds']}s)")

                                cancelled = False
                                for seconds_left in range(10, 0, -1):
                                    if not self.running or not self._site_matches_title(domain, self.get_active_window_title().lower()):
                                        cancelled = True
                                        break
                                    if self.on_warning_callback:
                                        self.on_warning_callback(domain, seconds_left)
                                    time.sleep(1.0)

                                if self.on_warning_callback:
                                    self.on_warning_callback(domain, None)

                                if not cancelled and self._site_matches_title(domain, self.get_active_window_title().lower()):
                                    try:
                                        pyautogui.hotkey('ctrl', 'w')
                                    except Exception as pe:
                                        logger.error(f"pyautogui error closing tab: {pe}", exc_info=True)
                                elif not cancelled:
                                    logger.info(f"Active site changed before closing {domain}; tab closure cancelled.")

                                # Reset used seconds so it doesn't repeatedly trigger instantly
                                site["used_seconds"] = 0
                                self.config_manager.save_config()
                                break
            except Exception as e:
                logger.error(f"Unexpected error in TabCloser loop: {e}", exc_info=True)

            time.sleep(2.0)

