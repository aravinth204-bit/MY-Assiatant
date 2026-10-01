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
            except Exception as e:
                logger.debug(f"Error getting foreground window text: {e}")
                return ""
        return ""

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
                                logger.info(f"Time limit reached for {domain} (limit: {limit_mins}m, used: {site['used_seconds']}s)")
                                
                                # Safety Countdown: 10-second visible warning before closing
                                countdown_cancelled = False
                                for remaining in range(10, 0, -1):
                                    if not self.running:
                                        countdown_cancelled = True
                                        break

                                    # Check if user already switched away from distracting domain
                                    current_active = self.get_active_window_title().lower()
                                    if domain not in current_active:
                                        logger.info(f"User switched away from {domain} to '{current_active}'. Cancelling tab closure.")
                                        countdown_cancelled = True
                                        break

                                    if self.on_trigger_callback:
                                        self.on_trigger_callback(
                                            domain,
                                            f"⚠️ {domain} limit reached! Closing in {remaining}s... (Switch away to keep)"
                                        )
                                    time.sleep(1.0)

                                if countdown_cancelled:
                                    # Still reset used_seconds to give a grace period
                                    site["used_seconds"] = 0
                                    self.config_manager.save_config()
                                    break

                                # Re-check active window right before sending Ctrl+W
                                final_title = self.get_active_window_title().lower()
                                if domain in final_title:
                                    logger.info(f"Countdown completed and {domain} is still active. Sending Ctrl+W")
                                    if self.on_trigger_callback:
                                        self.on_trigger_callback(domain, f"Closing {domain} now!")
                                    time.sleep(0.5)
                                    try:
                                        pyautogui.hotkey('ctrl', 'w')
                                    except Exception as pe:
                                        logger.error(f"pyautogui error closing tab: {pe}", exc_info=True)
                                else:
                                    logger.info(f"Tab switch detected at final second ('{final_title}'). Closure skipped.")

                                # Reset used seconds so it doesn't repeatedly trigger instantly
                                site["used_seconds"] = 0
                                self.config_manager.save_config()
                                break
            except Exception as e:
                logger.error(f"Unexpected error in TabCloser loop: {e}", exc_info=True)

            time.sleep(2.0)

