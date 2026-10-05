"""
Win32 low-level mouse hook to detect left-clicks on the mascot window.
Since pywebview transparent+frameless windows pass clicks through transparent
pixels to the desktop, we intercept at the OS level instead.
"""
import threading
import ctypes
import ctypes.wintypes
import time
from src.logger import get_logger

logger = get_logger("click_hook")

WH_MOUSE_LL = 14
WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP   = 0x0202

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

HOOKPROC = ctypes.WINFUNCTYPE(
    ctypes.c_long, ctypes.c_int, ctypes.wintypes.WPARAM, ctypes.wintypes.LPARAM
)

class MSLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("pt",      ctypes.wintypes.POINT),
        ("mouseData", ctypes.wintypes.DWORD),
        ("flags",   ctypes.wintypes.DWORD),
        ("time",    ctypes.wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]

class MascotClickHook:
    """
    Listens for left mouse-button clicks via a low-level Windows hook.
    When a click falls inside the mascot window bounding box and the
    user didn't drag, triggers on_click_callback().
    """

    def __init__(self, api_bridge, on_click_callback):
        self._api_bridge = api_bridge
        self._click_callback = on_click_callback
        self._hook = None
        self._hook_proc = None
        self._thread = None
        self.running = False
        self.enabled = True

        # Track press position to distinguish click vs drag
        self._press_x = None
        self._press_y = None
        self._press_time = 0.0

    def start(self):
        self.running = True
        self._thread = threading.Thread(target=self._run_hook, daemon=True)
        self._thread.start()
        logger.info("MascotClickHook started")

    def stop(self):
        self.running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
            if self._thread.is_alive():
                logger.warning("MascotClickHook thread did not stop within 2 seconds")
        logger.info("MascotClickHook stopped")

    def _get_mascot_rect(self):
        """Return (x, y, w, h) of mascot window from api_bridge position."""
        try:
            x = int(getattr(self._api_bridge, '_win_x', 40))
            y = int(getattr(self._api_bridge, '_win_y', 800))
            w = 260
            h = 240
            return x, y, w, h
        except Exception:
            return 40, 800, 260, 240

    def _point_in_mascot(self, px, py):
        x, y, w, h = self._get_mascot_rect()
        return x <= px <= x + w and y <= py <= y + h

    def _run_hook(self):
        def low_level_mouse_proc(nCode, wParam, lParam):
            try:
                if nCode >= 0:
                    ms = ctypes.cast(lParam, ctypes.POINTER(MSLLHOOKSTRUCT)).contents
                    px, py = ms.pt.x, ms.pt.y

                    if wParam == WM_LBUTTONDOWN:
                        self._press_x = px
                        self._press_y = py
                        self._press_time = time.time()

                    elif wParam == WM_LBUTTONUP:
                        if self._press_x is not None:
                            drag_dist = ((px - self._press_x)**2 + (py - self._press_y)**2) ** 0.5
                            elapsed = time.time() - self._press_time

                            # A click: minimal movement, short duration
                            if drag_dist < 8 and elapsed < 0.5:
                                if self.enabled and self._point_in_mascot(px, py):
                                    logger.debug(f"Click detected on mascot at ({px},{py})")
                                    try:
                                        self._click_callback()
                                    except Exception as e:
                                        logger.error(f"Click callback error: {e}")

                        self._press_x = None
                        self._press_y = None
            except Exception as e:
                logger.debug(f"Hook proc error: {e}")

            return user32.CallNextHookEx(self._hook, nCode, wParam, lParam)

        self._hook_proc = HOOKPROC(low_level_mouse_proc)
        self._hook = user32.SetWindowsHookExW(
            WH_MOUSE_LL,
            self._hook_proc,
            None,
            0
        )

        if not self._hook:
            logger.error("Failed to install mouse hook!")
            return

        # Windows message pump required to keep the hook alive
        msg = ctypes.wintypes.MSG()
        while self.running:
            if user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1):
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))
            else:
                time.sleep(0.01)

        try:
            user32.UnhookWindowsHookEx(self._hook)
        except Exception:
            pass
