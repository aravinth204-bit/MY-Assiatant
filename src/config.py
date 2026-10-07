import os
import json
from typing import Dict, Any, List

CONFIG_FILE_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config.json")

DEFAULT_CONFIG: Dict[str, Any] = {
    "character_name": "Aravi",
    "storage_threshold_pct": 90,
    "start_with_windows": False,
    "protected_folders": [],
    "tracked_websites": [
        {"domain": "youtube.com", "limit_minutes": 30, "used_seconds": 0},
        {"domain": "instagram.com", "limit_minutes": 20, "used_seconds": 0}
    ],
    "app_activity_history": [],
    "dashboard_activity_history": [],
    "reminders": [
        {"id": 1, "text": "Drink Water", "interval_minutes": 60, "enabled": True},
        {"id": 2, "text": "Stretch and relax eyes", "interval_minutes": 45, "enabled": True}
    ],
    "pomodoro": {
        "work_minutes": 25,
        "break_minutes": 5
    }
}

class ConfigManager:
    def __init__(self, filepath: str = CONFIG_FILE_PATH):
        self.filepath = filepath
        self.config = self.load_config()

    def load_config(self) -> Dict[str, Any]:
        if os.path.exists(self.filepath):
            try:
                with open(self.filepath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    # Merge with default config keys if missing
                    merged = DEFAULT_CONFIG.copy()
                    merged.update(data)
                    return merged
            except Exception:
                return DEFAULT_CONFIG.copy()
        return DEFAULT_CONFIG.copy()

    def save_config(self) -> bool:
        try:
            with open(self.filepath, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=4)
            return True
        except Exception:
            return False

    def get(self, key: str, default=None):
        return self.config.get(key, default)

    def set(self, key: str, value: Any):
        self.config[key] = value
        self.save_config()

    def update_tracked_site(self, domain: str, limit_minutes: int):
        sites = self.config.get("tracked_websites", [])
        for site in sites:
            if site["domain"].lower() == domain.lower():
                site["limit_minutes"] = limit_minutes
                self.save_config()
                return
        sites.append({"domain": domain, "limit_minutes": limit_minutes, "used_seconds": 0})
        self.config["tracked_websites"] = sites
        self.save_config()

    def add_used_time(self, domain: str, seconds: int):
        sites = self.config.get("tracked_websites", [])
        for site in sites:
            if site["domain"].lower() in domain.lower() or domain.lower() in site["domain"].lower():
                site["used_seconds"] = site.get("used_seconds", 0) + seconds
                self.save_config()
                return
