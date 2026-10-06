import ctypes
import os
from typing import Any, Callable, Dict, List, Optional


MAX_RESULTS = 50
DRIVE_FIXED = 3


def get_local_drive_roots() -> List[str]:
    if os.name != "nt":
        raise OSError("Searching all local drives is supported on Windows only.")

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.GetLogicalDrives.restype = ctypes.c_uint32
    kernel32.GetDriveTypeW.argtypes = [ctypes.c_wchar_p]
    kernel32.GetDriveTypeW.restype = ctypes.c_uint
    drive_mask = kernel32.GetLogicalDrives()
    if not drive_mask:
        raise ctypes.WinError()

    roots = []
    for index in range(26):
        if drive_mask & (1 << index):
            root = f"{chr(ord('A') + index)}:\\"
            if kernel32.GetDriveTypeW(root) == DRIVE_FIXED:
                roots.append(root)

    if not roots:
        raise OSError("No accessible local drives were found.")
    return roots


def search_files(
    query: str,
    roots: Optional[List[str]] = None,
    max_results: int = MAX_RESULTS,
    progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
    cancel_event=None,
) -> Dict[str, Any]:
    if not isinstance(query, str) or not query.strip():
        raise ValueError("Enter a file name to search for.")
    if len(query) > 128:
        raise ValueError("The file name search must be 128 characters or fewer.")
    if not isinstance(max_results, int) or max_results < 1:
        raise ValueError("The result limit must be a positive whole number.")

    normalized_query = query.strip().casefold()
    search_roots = get_local_drive_roots() if roots is None else roots
    if not search_roots:
        raise OSError("No local drives are available to search.")

    matches = []
    scanned_directories = 0
    skipped_directories = 0
    skipped_items = 0
    scanned_entries = 0
    pending = list(search_roots)
    current_directory = ""

    def report_progress():
        if progress_callback:
            progress_callback({
                "scanned_directories": scanned_directories,
                "scanned_entries": scanned_entries,
                "skipped_directories": skipped_directories,
                "skipped_items": skipped_items,
                "match_count": len(matches),
                "current_path": current_directory,
            })

    while pending and len(matches) < max_results:
        if cancel_event and cancel_event.is_set():
            break
        directory = pending.pop()
        current_directory = directory
        report_progress()
        try:
            with os.scandir(directory) as entries:
                scanned_directories += 1
                for entry in entries:
                    if cancel_event and cancel_event.is_set():
                        break
                    scanned_entries += 1
                    try:
                        is_directory = entry.is_dir(follow_symlinks=False)
                        if is_directory:
                            is_junction = getattr(entry, "is_junction", lambda: False)()
                            if not entry.is_symlink() and not is_junction:
                                pending.append(entry.path)
                        elif (
                            entry.is_file(follow_symlinks=False)
                            and normalized_query in entry.name.casefold()
                        ):
                            matches.append({
                                "name": entry.name,
                                "path": entry.path,
                            })
                            if len(matches) >= max_results:
                                break
                    except OSError:
                        skipped_items += 1
                    if scanned_entries % 1000 == 0:
                        report_progress()
        except OSError:
            skipped_directories += 1

    cancelled = bool(cancel_event and cancel_event.is_set())
    current_directory = ""
    report_progress()
    return {
        "query": query.strip(),
        "matches": matches,
        "scanned_directories": scanned_directories,
        "scanned_entries": scanned_entries,
        "skipped_directories": skipped_directories,
        "skipped_items": skipped_items,
        "truncated": (bool(pending) and not cancelled) or len(matches) >= max_results,
        "cancelled": cancelled,
    }
