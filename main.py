import os

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
from src.mascot_roamer import MascotRoamer
from src.click_hook import MascotClickHook
from src.logger import get_logger

logger = get_logger("main")

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
WEBVIEW_STORAGE_PATH = os.path.join(os.environ["TEMP"], "ARAVI-WebView2")

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
    click_hook = None
    tray_thread = None
    mascot_visible = True

    # 1. Initialize Core Managers
    config_manager = ConfigManager()
    system_monitor = SystemMonitor(
        storage_threshold_pct=config_manager.get("storage_threshold_pct", 90)
    )
    smart_cleaner = SmartCleaner(protected_folders=config_manager.get("protected_folders", []))
    
    def on_site_warning(domain, seconds_remaining):
        if api_bridge:
            api_bridge.update_website_warning(domain, seconds_remaining)

    def on_water_reminder():
        if api_bridge:
            api_bridge.show_water_reminder()

    last_folder_title = None

    def on_folder_state(folder_title):
        nonlocal last_folder_title
        if folder_title:
            api_bridge.pause_roaming(3.0)
            folder_name = folder_title
            for suffix in (' - File Explorer', ' - Windows Explorer'):
                if folder_name.endswith(suffix):
                    folder_name = folder_name[:-len(suffix)].strip()
            if folder_name and folder_name != last_folder_title:
                api_bridge.notify_ui('idle', f"I'm watching what you're doing in {folder_name}.")
            last_folder_title = folder_name
        else:
            last_folder_title = None

    def on_active_window_state(window_title):
        if window_title:
            api_bridge.observe_active_window(window_title.strip())

    def on_active_app_state(app_name):
        if app_name:
            api_bridge.record_app_activity(app_name)

    def is_app_observation_enabled():
        return api_bridge.get_window_observation_status()

    tab_closer = TabCloser(
        config_manager,
        on_warning_callback=on_site_warning,
        on_folder_state_callback=on_folder_state,
        on_active_window_callback=on_active_window_state,
        on_active_app_callback=on_active_app_state,
        is_active_app_observation_enabled=is_app_observation_enabled
    )
    reminder_manager = ReminderManager(
        config_manager,
        on_water_reminder_callback=on_water_reminder
    )

    def open_settings_window():
        global settings_window
        settings_html = os.path.join(os.path.dirname(__file__), "ui", "settings.html")
        if settings_window is None:
            settings_window = webview.create_window(
                "ARAVI-ASSISTANT Control Center",
                url=settings_html,
                js_api=api_bridge,
                width=1240,
                height=850,
                resizable=True,
                min_size=(980, 680)
            )
        else:
            try:
                settings_window.load_url(settings_html)
                settings_window.resize(1240, 850)
                settings_window.show()
                settings_window.focus()
            except Exception:
                settings_window = webview.create_window(
                    "ARAVI-ASSISTANT Control Center",
                    url=settings_html,
                    js_api=api_bridge,
                    width=1240,
                    height=850,
                    resizable=True,
                    min_size=(980, 680)
                )

    api_bridge = ApiBridge(
        system_monitor=system_monitor,
        smart_cleaner=smart_cleaner,
        tab_closer=tab_closer,
        reminder_manager=reminder_manager,
        config_manager=config_manager,
        settings_window_func=open_settings_window
    )

    mascot_roamer = MascotRoamer(api_bridge)
    api_bridge.set_roamer(mascot_roamer)

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

    win_w = 280
    win_h = 200
    pos_x = 40
    pos_y = screen_height - win_h

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
    api_bridge.set_character_window(character_window, pos_x, pos_y, win_w, win_h)
    mascot_roamer.win_w = win_w
    mascot_roamer.win_h = win_h
    mascot_roamer.pause(6.0)

    click_hook = MascotClickHook(api_bridge, on_click_callback=open_settings_window)

    shutdown_started = threading.Event()

    def shutdown_services(wait_for_tray=False):
        if not shutdown_started.is_set():
            shutdown_started.set()
            for service in (tab_closer, reminder_manager, mascot_roamer, click_hook):
                if service:
                    try:
                        service.stop()
                    except Exception as e:
                        logger.error("Error stopping %s: %s", type(service).__name__, e, exc_info=True)

        if tray_icon:
            try:
                tray_icon.stop()
            except Exception as e:
                logger.error("Error stopping system tray icon: %s", e, exc_info=True)
        if wait_for_tray and tray_thread and tray_thread.is_alive() and threading.current_thread() is not tray_thread:
            tray_thread.join(timeout=2.0)
            if tray_thread.is_alive():
                logger.warning("System tray thread did not stop within 2 seconds")

    def on_character_closed():
        shutdown_services()
        if settings_window:
            try:
                settings_window.destroy()
            except Exception as e:
                logger.error("Error closing settings window: %s", e, exc_info=True)

    character_window.events.closed += on_character_closed

    # 4. System Tray Icon Setup
    if HAS_PYSTRAY:
        def on_tray_settings(icon, item):
            open_settings_window()

        def on_tray_toggle_visibility(icon, item):
            nonlocal mascot_visible
            if character_window:
                try:
                    if mascot_visible:
                        character_window.hide()
                        mascot_visible = False
                        mascot_roamer.enabled = False
                        click_hook.enabled = False
                    else:
                        character_window.show()
                        mascot_visible = True
                        mascot_roamer.enabled = True
                        click_hook.enabled = True
                        mascot_roamer.pause(3.0)
                except Exception as e:
                    logger.error("Error toggling mascot visibility: %s", e, exc_info=True)

        def on_tray_quit(icon, item):
            shutdown_services()
            for window in (settings_window, character_window):
                if window:
                    try:
                        window.destroy()
                    except Exception as e:
                        logger.error("Error closing application window: %s", e, exc_info=True)

        tray_menu = pystray.Menu(
            pystray.MenuItem("Control Center & Settings", on_tray_settings),
            pystray.MenuItem("Show / Hide Mascot", on_tray_toggle_visibility),
            pystray.MenuItem("Quit ARAVI", on_tray_quit)
        )
        tray_icon = pystray.Icon("ARAVI-ASSISTANT", create_tray_icon_image(), "ARAVI-ASSISTANT", tray_menu)

    # 5. Launch PyWebView Engine with EdgeChromium (WebView2) for proper desktop transparency
    try:
        tab_closer.start()
        reminder_manager.start()
        mascot_roamer.start()
        click_hook.start()
        if tray_icon:
            tray_thread = threading.Thread(target=tray_icon.run, daemon=True)
            tray_thread.start()
        os.makedirs(WEBVIEW_STORAGE_PATH, exist_ok=True)
        webview.start(
            gui='edgechromium',
            debug=False,
            private_mode=False,
            storage_path=WEBVIEW_STORAGE_PATH
        )
    finally:
        shutdown_services(wait_for_tray=True)

if __name__ == "__main__":
    main()
