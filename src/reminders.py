import time
import threading
import winsound
from typing import Callable, Optional, Dict, Any, List

from src.logger import get_logger

logger = get_logger("reminders")

class ReminderManager:
    def __init__(self, config_manager, on_notify_callback: Optional[Callable[[str, str], None]] = None):
        self.config_manager = config_manager
        self.on_notify_callback = on_notify_callback
        self.running = False
        self._thread = None
        self.pomodoro_active = False
        self.pomodoro_end_time = 0
        self.pomodoro_mode = "work" # "work" or "break"
        self._notification_cooldowns: Dict[str, float] = {}

    def should_notify(self, key: str, cooldown_seconds: float = 300.0) -> bool:
        """Enforce cooldown so the same notification type cannot repeat within cooldown_seconds."""
        now = time.time()
        last_time = self._notification_cooldowns.get(key, 0.0)
        if (now - last_time) >= cooldown_seconds:
            self._notification_cooldowns[key] = now
            return True
        return False

    def notify_with_cooldown(self, key: str, rtype: str, message: str, cooldown_seconds: float = 300.0) -> bool:
        if self.should_notify(key, cooldown_seconds):
            if self.on_notify_callback:
                try:
                    self.on_notify_callback(rtype, message)
                    return True
                except Exception as e:
                    logger.error(f"Error in on_notify_callback: {e}", exc_info=True)
        return False

    def start(self):
        try:
            if not self.running:
                self.running = True
                self._thread = threading.Thread(target=self._reminder_loop, daemon=True)
                self._thread.start()
                logger.info("ReminderManager started")
        except Exception as e:
            logger.error(f"Error starting ReminderManager: {e}", exc_info=True)

    def stop(self):
        try:
            self.running = False
            logger.info("ReminderManager stopped")
        except Exception as e:
            logger.error(f"Error stopping ReminderManager: {e}", exc_info=True)

    def start_pomodoro(self, minutes: int = 25):
        try:
            self.pomodoro_active = True
            self.pomodoro_mode = "work"
            self.pomodoro_end_time = time.time() + (minutes * 60)
            logger.info(f"Pomodoro started: {minutes} minutes")
            if self.on_notify_callback:
                self.on_notify_callback("pomodoro_start", f"Focus session started! {minutes} minutes on the clock. Stay sharp!")
        except Exception as e:
            logger.error(f"Error in start_pomodoro: {e}", exc_info=True)

    def stop_pomodoro(self):
        try:
            self.pomodoro_active = False
            logger.info("Pomodoro stopped")
            if self.on_notify_callback:
                self.on_notify_callback("pomodoro_stop", "Pomodoro timer stopped.")
        except Exception as e:
            logger.error(f"Error in stop_pomodoro: {e}", exc_info=True)

    def get_pomodoro_status(self) -> Dict[str, Any]:
        try:
            if not self.pomodoro_active:
                return {"active": False, "remaining_seconds": 0, "mode": "idle"}
            remaining = max(0, int(self.pomodoro_end_time - time.time()))
            return {
                "active": True,
                "remaining_seconds": remaining,
                "mode": self.pomodoro_mode
            }
        except Exception as e:
            logger.error(f"Error in get_pomodoro_status: {e}", exc_info=True)
            return {"active": False, "remaining_seconds": 0, "mode": "idle"}

    def _play_sound(self):
        try:
            winsound.PlaySound("SystemExclamation", winsound.SND_ALIAS | winsound.SND_ASYNC)
        except Exception:
            try:
                winsound.Beep(1000, 400)
            except Exception:
                pass

    def _reminder_loop(self):
        last_check_time = time.time()
        
        while self.running:
            try:
                now = time.time()

                # 1. Check Pomodoro
                if self.pomodoro_active:
                    if now >= self.pomodoro_end_time:
                        self._play_sound()
                        if self.pomodoro_mode == "work":
                            self.pomodoro_mode = "break"
                            break_mins = self.config_manager.get("pomodoro", {}).get("break_minutes", 5)
                            self.pomodoro_end_time = now + (break_mins * 60)
                            if self.on_notify_callback:
                                self.on_notify_callback("pomodoro_end", f"Great job! Focus time completed. Take a {break_mins} min break! 🎉")
                        else:
                            self.pomodoro_active = False
                            if self.on_notify_callback:
                                self.on_notify_callback("pomodoro_break_end", "Break is over! Ready for the next sprint?")

                # 2. Check scheduled / interval reminders
                reminders: List[Dict[str, Any]] = self.config_manager.get("reminders", [])
                for r in reminders:
                    if r.get("enabled", True):
                        interval = r.get("interval_minutes", 60)
                        last_triggered = r.get("last_triggered", 0)
                        if (now - last_triggered) >= (interval * 60):
                            r["last_triggered"] = now
                            self.config_manager.save_config()
                            self._play_sound()
                            if self.on_notify_callback:
                                self.on_notify_callback("reminder", f"⏰ Reminder: {r.get('text', 'Take a break!')}")

                last_check_time = now
            except Exception as e:
                logger.error(f"Unexpected error in ReminderManager loop: {e}", exc_info=True)

            time.sleep(15.0)
