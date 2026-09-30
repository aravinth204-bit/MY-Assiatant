import time
import threading
import winsound
from typing import Callable, Optional, Dict, Any, List

class ReminderManager:
    def __init__(self, config_manager, on_notify_callback: Optional[Callable[[str, str], None]] = None):
        self.config_manager = config_manager
        self.on_notify_callback = on_notify_callback
        self.running = False
        self._thread = None
        self.pomodoro_active = False
        self.pomodoro_end_time = 0
        self.pomodoro_mode = "work" # "work" or "break"

    def start(self):
        if not self.running:
            self.running = True
            self._thread = threading.Thread(target=self._reminder_loop, daemon=True)
            self._thread.start()

    def stop(self):
        self.running = False

    def start_pomodoro(self, minutes: int = 25):
        self.pomodoro_active = True
        self.pomodoro_mode = "work"
        self.pomodoro_end_time = time.time() + (minutes * 60)
        if self.on_notify_callback:
            self.on_notify_callback("pomodoro_start", f"Focus session started! {minutes} minutes on the clock. Stay sharp!")

    def stop_pomodoro(self):
        self.pomodoro_active = False
        if self.on_notify_callback:
            self.on_notify_callback("pomodoro_stop", "Pomodoro timer stopped.")

    def get_pomodoro_status(self) -> Dict[str, Any]:
        if not self.pomodoro_active:
            return {"active": False, "remaining_seconds": 0, "mode": "idle"}
        remaining = max(0, int(self.pomodoro_end_time - time.time()))
        return {
            "active": True,
            "remaining_seconds": remaining,
            "mode": self.pomodoro_mode
        }

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
            now = time.time()
            elapsed_mins = (now - last_check_time) / 60.0

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
            time.sleep(15.0)
