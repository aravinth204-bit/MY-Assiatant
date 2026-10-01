import os
import sys

# Direct temp files to D drive if C drive space is constrained
os.makedirs("D:\\pip_temp", exist_ok=True)
os.environ["TEMP"] = "D:\\pip_temp"
os.environ["TMP"] = "D:\\pip_temp"

import threading
import webview
from PIL import Image, ImageDraw

from src.system_monitor import SystemMonitor
from src.smart_cleaner import SmartCleaner
from src.tab_closer import TabCloser
from src.reminders import ReminderManager
from src.config import ConfigManager
from src.api_bridge import ApiBridge

try:
    import webview.platforms.winforms as _wf
    _old_form_init = _wf.BrowserView.BrowserForm.__init__
    def _patched_form_init(self, window, cache_dir):
        _old_form_init(self, window, cache_dir)
        if getattr(window, 'transparent', False):
            # On Windows WinForms, WebView2 hosted in a Form requires the Form itself
            # to enable transparency and match TransparencyKey to avoid showing the default Form background box.
            try:
                self.AllowTransparency = True
                transparent_key = _wf.Color.FromArgb(255, 1, 2, 3) # Unique color key for transparency
                self.BackColor = transparent_key
                self.TransparencyKey = transparent_key
            except Exception:
                pass
    _wf.BrowserView.BrowserForm.__init__ = _patched_form_init
except Exception:
    pass

try:
    import pystray
    HAS_PYSTRAY = True
except ImportError:
    HAS_PYSTRAY = False

# Global references
character_window = None
settings_window = None
tray_icon = None

def create_tray_icon_image():
    """Generate a high-res teal/coral tray icon image."""
    image = Image.new('RGBA', (64, 64), color=(0, 0, 0, 0))
    dc = ImageDraw.Draw(image)
    # Circle base (teal)
    dc.ellipse((4, 4, 60, 60), fill=(20, 184, 166, 255))
    # Eye accent (coral cutouts)
    dc.polygon([(20, 26), (28, 20), (36, 26), (28, 32)], fill=(244, 63, 94, 255))
    dc.polygon([(36, 26), (44, 20), (52, 26), (44, 32)], fill=(244, 63, 94, 255))
    return image

def main():
    global character_window, settings_window, tray_icon

    # 1. Initialize Core Managers
    config_manager = ConfigManager()
    system_monitor = SystemMonitor()
    smart_cleaner = SmartCleaner(protected_folders=config_manager.get("protected_folders", []))
    
    def on_tab_trigger(domain, message):
        if api_bridge:
            api_bridge.notify_ui('webshoot', message)

    def on_reminder_trigger(rtype, message):
        if api_bridge:
            pose = 'celebrate' if rtype.startswith('pomodoro') else 'idle'
            api_bridge.notify_ui(pose, message)

    tab_closer = TabCloser(config_manager, on_trigger_callback=on_tab_trigger)
    reminder_manager = ReminderManager(config_manager, on_notify_callback=on_reminder_trigger)

    def open_settings_window():
        global settings_window
        settings_html = os.path.join(os.path.dirname(__file__), "ui", "settings.html")
        if settings_window is None:
            settings_window = webview.create_window(
                "ARAVI-ASSISTANT Control Center",
                url=settings_html,
                js_api=api_bridge,
                width=900,
                height=650,
                resizable=True,
                min_size=(800, 550)
            )
        else:
            try:
                settings_window.show()
                settings_window.focus()
            except Exception:
                settings_window = webview.create_window(
                    "ARAVI-ASSISTANT Control Center",
                    url=settings_html,
                    js_api=api_bridge,
                    width=900,
                    height=650,
                    resizable=True
                )

    api_bridge = ApiBridge(
        system_monitor=system_monitor,
        smart_cleaner=smart_cleaner,
        tab_closer=tab_closer,
        reminder_manager=reminder_manager,
        config_manager=config_manager,
        settings_window_func=open_settings_window
    )

    # 2. Start Background Services
    tab_closer.start()
    reminder_manager.start()

    # 3. Create Main Mascot Window
    character_html = os.path.join(os.path.dirname(__file__), "ui", "character.html")
    
    screen_width = 1920
    screen_height = 1080
    try:
        import win32api
        screen_width = win32api.GetSystemMetrics(0)
        screen_height = win32api.GetSystemMetrics(1)
    except Exception:
        pass

    win_w = 260
    win_h = 240
    pos_x = 40
    pos_y = screen_height - win_h - 60

    character_window = webview.create_window(
        "ARAVI Mascot",
        url=character_html,
        js_api=api_bridge,
        width=win_w,
        height=win_h,
        x=pos_x,
        y=pos_y,
        frameless=True,
        on_top=True,
        transparent=True,
        easy_drag=False,
        resizable=False
    )
    api_bridge.set_character_window(character_window, pos_x, pos_y)

    # 4. System Tray Icon Setup
    if HAS_PYSTRAY:
        def on_tray_settings(icon, item):
            open_settings_window()

        def on_tray_toggle_visibility(icon, item):
            if character_window:
                try:
                    character_window.hide() if character_window.on_top else character_window.show()
                except Exception:
                    pass

        def on_tray_quit(icon, item):
            tab_closer.stop()
            reminder_manager.stop()
            icon.stop()
            sys.exit(0)

        tray_menu = pystray.Menu(
            pystray.MenuItem("Control Center & Settings", on_tray_settings),
            pystray.MenuItem("Show / Hide Mascot", on_tray_toggle_visibility),
            pystray.MenuItem("Quit ARAVI", on_tray_quit)
        )
        tray_icon = pystray.Icon("ARAVI-ASSISTANT", create_tray_icon_image(), "ARAVI-ASSISTANT", tray_menu)
        threading.Thread(target=tray_icon.run, daemon=True).start()

    # 5. Launch PyWebView Engine with EdgeChromium (WebView2) for proper desktop transparency
    webview.start(gui='edgechromium', debug=False)

if __name__ == "__main__":
    main()
