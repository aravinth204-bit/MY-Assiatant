import time
import threading
from typing import Optional
from src.logger import get_logger

logger = get_logger("mascot_roamer")

try:
    import win32api
    HAS_WIN32 = True
except ImportError:
    HAS_WIN32 = False

class MascotRoamer:
    def __init__(self, api_bridge):
        self.api_bridge = api_bridge
        self.running = False
        self.paused_until = 0.0
        self.enabled = True
        self._thread = None
        self._stop_event = threading.Event()
        
        # Screen metrics
        self.screen_width = 1920
        self.screen_height = 1080
        self.update_screen_metrics()
        
        # Mascot window dimensions
        self.win_w = 280
        self.win_h = 200

    def update_screen_metrics(self):
        if HAS_WIN32:
            try:
                self.screen_width = win32api.GetSystemMetrics(0)
                self.screen_height = win32api.GetSystemMetrics(1)
            except Exception as e:
                logger.debug(f"Error getting system metrics: {e}")

    def start(self):
        if not self._thread or not self._thread.is_alive():
            self._stop_event.clear()
            self.running = True
            self._thread = threading.Thread(target=self._roam_loop, daemon=True)
            self._thread.start()
            logger.info("MascotRoamer thread started")

    def stop(self):
        self.running = False
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
            if self._thread.is_alive():
                logger.warning("MascotRoamer thread did not stop within 2 seconds")

    def pause(self, seconds: float = 15.0):
        """Temporarily pause roaming (e.g. when user is dragging or clicking mascot)."""
        self.paused_until = time.time() + seconds
        logger.debug(f"Mascot roaming paused for {seconds} seconds")

    def is_paused(self) -> bool:
        return time.time() < self.paused_until or not self.enabled

    def _move_vertically(self, x: int, current_y: int, target_y: int) -> int:
        direction = -1 if target_y < current_y else 1
        while current_y != target_y and not self.is_paused() and self.running:
            current_y += direction * min(12, abs(target_y - current_y))
            self.api_bridge.move_window_to(x, current_y)
            if self._stop_event.wait(0.02):
                break
        return current_y

    def _move_horizontally(self, y: int, current_x: int, target_x: int) -> int:
        direction = -1 if target_x < current_x else 1
        while current_x != target_x and not self.is_paused() and self.running:
            current_x += direction * min(4, abs(target_x - current_x))
            self.api_bridge.move_window_to(current_x, y)
            if self._stop_event.wait(0.03):
                break
        return current_x

    def _roam_cycle(self):
        min_x = 0
        max_x = max(min_x, self.screen_width - self.win_w)
        bottom_y = max(0, self.screen_height - self.win_h)
        top_y = 0

        curr_x = min(max(min_x, self.api_bridge._win_x), max_x)
        curr_y = min(max(top_y, self.api_bridge._win_y), bottom_y)

        curr_y = self._move_vertically(curr_x, curr_y, bottom_y)
        if curr_y != bottom_y or self.is_paused() or not self.running:
            return

        self.api_bridge.set_orientation("normal", "right")
        self.api_bridge.notify_ui("walk_right", None)
        curr_x = self._move_horizontally(bottom_y, curr_x, max_x)
        if curr_x != max_x or self.is_paused() or not self.running:
            return

        self.api_bridge.set_orientation("normal", "right")
        self.api_bridge.notify_ui("climb_up", None)
        curr_y = self._move_vertically(curr_x, bottom_y, top_y)
        if curr_y != top_y or self.is_paused() or not self.running:
            return

        self.api_bridge.set_orientation("upside_down", "left")
        self.api_bridge.notify_ui("ceiling_walk", None)
        curr_x = self._move_horizontally(top_y, max_x, min_x)
        if curr_x != min_x or self.is_paused() or not self.running:
            return

        self.api_bridge.set_orientation("normal", "left")
        self.api_bridge.notify_ui("climb_down", None)
        self.api_bridge.trigger_web_line("down")
        if self._stop_event.wait(0.5):
            self.api_bridge.clear_web_line()
            return
        curr_y = self._move_vertically(curr_x, top_y, bottom_y)
        self.api_bridge.clear_web_line()
        if curr_y == bottom_y and self.running and not self.is_paused():
            self.api_bridge.notify_ui("landing", None)
            self._stop_event.wait(0.85)

    def _roam_loop(self):
        # Initial delay before autonomous roaming begins
        if self._stop_event.wait(3.0):
            return

        while self.running:
            try:
                if self.is_paused():
                    self._stop_event.wait(1.0)
                    continue

                self.update_screen_metrics()
                self._roam_cycle()

            except Exception as e:
                logger.error(f"Error in MascotRoamer loop: {e}", exc_info=True)
                self._stop_event.wait(2.0)
