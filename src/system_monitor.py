import psutil
import time
from typing import Dict, Any, List

from src.logger import get_logger

logger = get_logger("system_monitor")

class SystemMonitor:
    def __init__(self):
        self.high_cpu_start_time = None

    def get_system_stats(self) -> Dict[str, Any]:
        """Fetch overall system resource metrics."""
        try:
            cpu_percent = psutil.cpu_percent(interval=None)
            ram_info = psutil.virtual_memory()
            disk_info = psutil.disk_usage('/')
            
            battery = psutil.sensors_battery()
            battery_pct = battery.percent if battery else 100
            is_plugged = battery.power_plugged if battery else True

            # CPU High load duration tracker (> 85% for 2+ minutes)
            if cpu_percent > 85.0:
                if self.high_cpu_start_time is None:
                    self.high_cpu_start_time = time.time()
            else:
                self.high_cpu_start_time = None

            cpu_high_duration = (time.time() - self.high_cpu_start_time) if self.high_cpu_start_time else 0
            is_tired = (cpu_high_duration >= 120) or (battery_pct < 15 and not is_plugged)
            is_storage_alert = disk_info.percent > 90.0 or (disk_info.free / disk_info.total) < 0.10

            return {
                "cpu_percent": cpu_percent,
                "ram_percent": ram_info.percent,
                "ram_used_gb": round(ram_info.used / (1024**3), 2),
                "ram_total_gb": round(ram_info.total / (1024**3), 2),
                "disk_percent": disk_info.percent,
                "disk_free_gb": round(disk_info.free / (1024**3), 2),
                "disk_total_gb": round(disk_info.total / (1024**3), 2),
                "battery_percent": battery_pct,
                "is_plugged": is_plugged,
                "is_tired": is_tired,
                "is_storage_alert": is_storage_alert
            }
        except Exception as e:
            logger.error(f"Error in get_system_stats: {e}", exc_info=True)
            return {
                "cpu_percent": 0.0,
                "ram_percent": 0.0,
                "ram_used_gb": 0.0,
                "ram_total_gb": 0.0,
                "disk_percent": 0.0,
                "disk_free_gb": 0.0,
                "disk_total_gb": 0.0,
                "battery_percent": 100,
                "is_plugged": True,
                "is_tired": False,
                "is_storage_alert": False
            }

    def get_top_processes(self, limit: int = 5, sort_by: str = 'memory_percent') -> List[Dict[str, Any]]:
        """Retrieve top N processes by CPU or RAM consumption."""
        processes = []
        try:
            for proc in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent', 'memory_info']):
                try:
                    pinfo = proc.info
                    processes.append({
                        "pid": pinfo['pid'],
                        "name": pinfo['name'] or f"PID {pinfo['pid']}",
                        "cpu_percent": round(pinfo['cpu_percent'] or 0.0, 1),
                        "ram_mb": round((pinfo['memory_info'].rss if pinfo['memory_info'] else 0) / (1024 * 1024), 1),
                        "memory_percent": round(pinfo['memory_percent'] or 0.0, 1)
                    })
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    continue
                except Exception:
                    continue

            processes.sort(key=lambda x: x.get(sort_by, 0), reverse=True)
            return processes[:limit]
        except Exception as e:
            logger.error(f"Error in get_top_processes: {e}", exc_info=True)
            return []

    def terminate_process(self, pid: int) -> bool:
        """Safely attempt to terminate a process by PID."""
        try:
            proc = psutil.Process(pid)
            proc.terminate()
            proc.wait(timeout=3)
            logger.info(f"Process {pid} terminated successfully")
            return True
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.TimeoutExpired):
            try:
                proc = psutil.Process(pid)
                proc.kill()
                logger.info(f"Process {pid} killed forcefully after timeout")
                return True
            except Exception as e:
                logger.error(f"Failed to kill process {pid}: {e}", exc_info=True)
                return False
        except Exception as e:
            logger.error(f"Error terminating process {pid}: {e}", exc_info=True)
            return False
