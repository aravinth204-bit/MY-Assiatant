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
        
        # Screen metrics
        self.screen_width = 1920
        self.screen_height = 1080
        self.update_screen_metrics()
        
        # Mascot window dimensions
        self.win_w = 120
        self.win_h = 120

    def update_screen_metrics(self):
        if HAS_WIN32:
            try:
                self.screen_width = win32api.GetSystemMetrics(0)
                self.screen_height = win32api.GetSystemMetrics(1)
            except Exception as e:
                logger.debug(f"Error getting system metrics: {e}")

    def start(self):
        if not self.running:
            self.running = True
            self._thread = threading.Thread(target=self._roam_loop, daemon=True)
            self._thread.start()
            logger.info("MascotRoamer thread started")

    def stop(self):
        self.running = False

    def pause(self, seconds: float = 15.0):
        """Temporarily pause roaming (e.g. when user is dragging or clicking mascot)."""
        self.paused_until = time.time() + seconds
        logger.debug(f"Mascot roaming paused for {seconds} seconds")

    def is_paused(self) -> bool:
        return time.time() < self.paused_until or not self.enabled

    def _roam_loop(self):
        # Initial delay before autonomous roaming begins
        time.sleep(3.0)
        
        min_x = 30
        
        while self.running:
            try:
                if self.is_paused():
                    time.sleep(1.0)
                    continue

                self.update_screen_metrics()
                max_x = max(min_x + 100, self.screen_width - self.win_w - 30)
                bottom_y = max(100, self.screen_height - self.win_h - 50)
                top_y = 30

                curr_x = self.api_bridge._win_x
                curr_y = self.api_bridge._win_y
                if curr_x <= 0: curr_x = min_x
                if curr_y <= 0: curr_y = bottom_y

                # --- STEP 1: WALK GROUND RIGHT (Left to Right) ---
                if self.is_paused(): continue
                self.api_bridge.set_orientation("normal", "right")
                self.api_bridge.notify_ui("walk", None)
                target_x = max_x

                while curr_x < target_x and not self.is_paused() and self.running:
                    curr_x += 4
                    if curr_x > target_x: curr_x = target_x
                    self.api_bridge.move_window_to(curr_x, bottom_y)
                    time.sleep(0.03)

                # --- STEP 2: WEB SHOOT & CLIMB UP (RIGHT WALL) ---
                if not self.is_paused() and self.running:
                    self.api_bridge.set_orientation("normal", "right")
                    self.api_bridge.notify_ui("webshoot", None)
                    self.api_bridge.trigger_web_line("up")
                    time.sleep(0.5)

                    # Zip Up to top ceiling
                    curr_y = bottom_y
                    while curr_y > top_y and not self.is_paused() and self.running:
                        curr_y -= 12
                        if curr_y < top_y: curr_y = top_y
                        self.api_bridge.move_window_to(curr_x, curr_y)
                        time.sleep(0.02)

                    self.api_bridge.clear_web_line()

                # --- STEP 3: WALK CEILING LEFT (Right to Left at Top) ---
                if not self.is_paused() and self.running:
                    self.api_bridge.set_orientation("upside_down", "left")
                    self.api_bridge.notify_ui("walk", None)
                    target_x = min_x

                    while curr_x > target_x and not self.is_paused() and self.running:
                        curr_x -= 4
                        if curr_x < target_x: curr_x = target_x
                        self.api_bridge.move_window_to(curr_x, top_y)
                        time.sleep(0.03)

                # --- STEP 4: WEB SHOOT & ZIP DOWN (LEFT WALL) ---
                if not self.is_paused() and self.running:
                    self.api_bridge.set_orientation("normal", "left")
                    self.api_bridge.notify_ui("webshoot", None)
                    self.api_bridge.trigger_web_line("down")
                    time.sleep(0.5)

                    # Zip Down to ground
                    while curr_y < bottom_y and not self.is_paused() and self.running:
                        curr_y += 12
                        if curr_y > bottom_y: curr_y = bottom_y
                        self.api_bridge.move_window_to(curr_x, curr_y)
                        time.sleep(0.02)

                    self.api_bridge.clear_web_line()

            except Exception as e:
                logger.error(f"Error in MascotRoamer loop: {e}", exc_info=True)
                time.sleep(2.0)
