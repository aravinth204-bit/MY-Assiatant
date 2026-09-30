import time
import threading
import pyautogui
from typing import Callable, Optional

try:
    import win32gui
    HAS_WIN32 = True
except ImportError:
    HAS_WIN32 = False

class TabCloser:
    def __init__(self, config_manager, on_trigger_callback: Optional[Callable[[str, str], None]] = None):
        self.config_manager = config_manager
        self.on_trigger_callback = on_trigger_callback
        self.running = False
        self._thread = None

    def get_active_window_title(self) -> str:
        if HAS_WIN32:
            try:
                hwnd = win32gui.GetForegroundWindow()
                return win32gui.GetWindowText(hwnd) or ""
            except Exception:
                return ""
        return ""

    def start(self):
        if not self.running:
            self.running = True
            self._thread = threading.Thread(target=self._loop, daemon=True)
            self._thread.start()

    def stop(self):
        self.running = False

    def _loop(self):
        pyautogui.FAILSAFE = False
        while self.running:
            title = self.get_active_window_title().lower()
            if title:
                tracked_sites = self.config_manager.get("tracked_websites", [])
                for site in tracked_sites:
                    domain = site.get("domain", "").lower()
                    limit_mins = site.get("limit_minutes", 0)
                    used_secs = site.get("used_seconds", 0)
                    limit_secs = limit_mins * 60

                    if domain and domain in title:
                        # Add 2 seconds to tracked time
                        site["used_seconds"] = used_secs + 2
                        self.config_manager.save_config()

                        if site["used_seconds"] >= limit_secs and limit_mins > 0:
                            # Time limit exceeded!
                            if self.on_trigger_callback:
                                self.on_trigger_callback(domain, f"Time limit of {limit_mins} mins reached for {domain}! Closing tab...")
                            
                            time.sleep(1.5)  # give time for web-shoot animation
                            try:
                                pyautogui.hotkey('ctrl', 'w')
                            except Exception:
                                pass
                            
                            # Reset used seconds so it doesn't repeatedly trigger instantly
                            site["used_seconds"] = 0
                            self.config_manager.save_config()
                            break

            time.sleep(2.0)
