import os
import shutil
import hashlib
import time
from pathlib import Path
from typing import List, Dict, Any, Set
import send2trash

class SmartCleaner:
    def __init__(self, protected_folders: List[str] = None):
        user_profile = os.environ.get("USERPROFILE", "C:\\Users\\Default")
        default_protected = [
            os.path.join(user_profile, "Desktop"),
            os.path.join(user_profile, "Documents"),
            os.path.join(user_profile, "Pictures"),
            os.path.join(user_profile, "Videos")
        ]
        if protected_folders:
            default_protected.extend(protected_folders)
        
        self.protected_folders = [os.path.normpath(p).lower() for p in default_protected]

    def is_protected(self, file_path: str) -> bool:
        norm_path = os.path.normpath(file_path).lower()
        for protected in self.protected_folders:
            if norm_path.startswith(protected):
                return True
        return False

    def scan_temp_files(self) -> List[Dict[str, Any]]:
        candidates = []
        temp_dirs = [
            os.environ.get("TEMP"),
            os.environ.get("TMP"),
            os.path.join(os.environ.get("SystemRoot", "C:\\Windows"), "Temp")
        ]
        for tdir in temp_dirs:
            if tdir and os.path.exists(tdir):
                try:
                    for root, _, files in os.walk(tdir):
                        for f in files:
                            fpath = os.path.join(root, f)
                            try:
                                size = os.path.getsize(fpath)
                                candidates.append({
                                    "category": "Temp Files",
                                    "path": fpath,
                                    "size_bytes": size,
                                    "reason": "Temporary application file"
                                })
                            except Exception:
                                pass
                except Exception:
                    pass
        return candidates

    def scan_downloads_installers(self) -> List[Dict[str, Any]]:
        user_profile = os.environ.get("USERPROFILE", "")
        downloads = os.path.join(user_profile, "Downloads")
        candidates = []
        if os.path.exists(downloads) and not self.is_protected(downloads):
            for root, _, files in os.walk(downloads):
                for f in files:
                    if f.lower().endswith(('.exe', '.msi')):
                        fpath = os.path.join(root, f)
                        try:
                            size = os.path.getsize(fpath)
                            candidates.append({
                                "category": "Installer Files",
                                "path": fpath,
                                "size_bytes": size,
                                "reason": "Installer file in Downloads"
                            })
                        except Exception:
                            pass
        return candidates

    def scan_old_large_files(self, days: int = 180, min_size_mb: int = 200) -> List[Dict[str, Any]]:
        user_profile = os.environ.get("USERPROFILE", "")
        candidates = []
        cutoff_time = time.time() - (days * 86400)
        min_bytes = min_size_mb * 1024 * 1024

        scan_roots = [os.path.join(user_profile, "Downloads")]

        for sroot in scan_roots:
            if os.path.exists(sroot) and not self.is_protected(sroot):
                for root, _, files in os.walk(sroot):
                    for f in files:
                        fpath = os.path.join(root, f)
                        if self.is_protected(fpath):
                            continue
                        try:
                            st = os.stat(fpath)
                            if st.st_size >= min_bytes and st.st_atime < cutoff_time:
                                candidates.append({
                                    "category": "Old Large Files",
                                    "path": fpath,
                                    "size_bytes": st.st_size,
                                    "reason": f"Unused for {days}+ days & > {min_size_mb}MB"
                                })
                        except Exception:
                            pass
        return candidates

    def scan_duplicates_in_downloads(self) -> List[Dict[str, Any]]:
        user_profile = os.environ.get("USERPROFILE", "")
        downloads = os.path.join(user_profile, "Downloads")
        candidates = []
        if not os.path.exists(downloads) or self.is_protected(downloads):
            return candidates

        hashes: Dict[str, str] = {}
        for root, _, files in os.walk(downloads):
            for f in files:
                fpath = os.path.join(root, f)
                try:
                    size = os.path.getsize(fpath)
                    if size > 1024 * 1024:  # check files > 1MB for duplicate scan efficiency
                        h = self._get_file_hash(fpath)
                        if h in hashes:
                            candidates.append({
                                "category": "Duplicate Files",
                                "path": fpath,
                                "size_bytes": size,
                                "reason": f"Duplicate of {os.path.basename(hashes[h])}"
                            })
                        else:
                            hashes[h] = fpath
                except Exception:
                    pass
        return candidates

    def _get_file_hash(self, file_path: str, chunk_size: int = 65536) -> str:
        hasher = hashlib.md5()
        with open(file_path, 'rb') as f:
            buf = f.read(chunk_size)
            while len(buf) > 0:
                hasher.update(buf)
                buf = f.read(chunk_size)
        return hasher.hexdigest()

    def run_full_scan(self) -> List[Dict[str, Any]]:
        all_candidates = []
        all_candidates.extend(self.scan_downloads_installers())
        all_candidates.extend(self.scan_duplicates_in_downloads())
        all_candidates.extend(self.scan_old_large_files())
        return all_candidates

    def clean_selected_files(self, file_paths: List[str]) -> Dict[str, Any]:
        """Move specified files safely to Windows Recycle Bin using send2trash."""
        successful = []
        failed = []
        freed_bytes = 0

        for fpath in file_paths:
            if self.is_protected(fpath):
                failed.append({"path": fpath, "reason": "Protected directory"})
                continue
            if os.path.exists(fpath):
                try:
                    size = os.path.getsize(fpath)
                    send2trash.send2trash(fpath)
                    successful.append(fpath)
                    freed_bytes += size
                except Exception as e:
                    failed.append({"path": fpath, "reason": str(e)})

        return {
            "success_count": len(successful),
            "failed_count": len(failed),
            "freed_mb": round(freed_bytes / (1024 * 1024), 2),
            "failed": failed
        }
