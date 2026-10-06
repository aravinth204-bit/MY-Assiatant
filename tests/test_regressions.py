import importlib
import json
import logging
import sys
import types
import unittest
from unittest.mock import patch


def load_app_modules():
    logger = logging.getLogger("test.null")
    logger.addHandler(logging.NullHandler())
    logger.propagate = False

    psutil_stub = types.ModuleType("psutil")
    psutil_stub.cpu_percent = lambda interval=None: 0
    psutil_stub.virtual_memory = lambda: None
    psutil_stub.disk_usage = lambda path: None
    psutil_stub.sensors_battery = lambda: None
    psutil_stub.process_iter = lambda attrs: []

    pyautogui_stub = types.ModuleType("pyautogui")
    pyautogui_stub.FAILSAFE = True
    pyautogui_stub.hotkey = lambda *args: None

    winsound_stub = types.ModuleType("winsound")
    winsound_stub.SND_ALIAS = 0
    winsound_stub.SND_ASYNC = 0
    winsound_stub.PlaySound = lambda *args: None
    winsound_stub.Beep = lambda *args: None

    logger_stub = types.ModuleType("src.logger")
    logger_stub.get_logger = lambda name: logger
    webview_stub = types.ModuleType("webview")

    replacements = {
        "psutil": psutil_stub,
        "pyautogui": pyautogui_stub,
        "winsound": winsound_stub,
        "src.logger": logger_stub,
        "webview": webview_stub,
    }
    original_modules = {name: sys.modules.get(name) for name in replacements}
    sys.modules.update(replacements)
    try:
        return (
            importlib.import_module("src.system_monitor"),
            importlib.import_module("src.tab_closer"),
            importlib.import_module("src.reminders"),
            importlib.import_module("src.mascot_roamer"),
            importlib.import_module("src.api_bridge"),
            pyautogui_stub,
        )
    finally:
        for name, module in original_modules.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module


system_monitor_module, tab_closer_module, reminders_module, roamer_module, api_bridge_module, pyautogui_stub = load_app_modules()


class SystemMonitorTests(unittest.TestCase):
    def test_storage_alert_uses_configured_threshold_including_boundary(self):
        monitor = system_monitor_module.SystemMonitor(storage_threshold_pct=75)
        ram = types.SimpleNamespace(percent=40, used=4, total=10)

        for disk_percent, expected in ((74, False), (75, True), (90, True)):
            disk = types.SimpleNamespace(percent=disk_percent, free=100, total=1000)
            with self.subTest(disk_percent=disk_percent), \
                    patch.object(system_monitor_module.psutil, "cpu_percent", return_value=10), \
                    patch.object(system_monitor_module.psutil, "virtual_memory", return_value=ram), \
                    patch.object(system_monitor_module.psutil, "disk_usage", return_value=disk), \
                    patch.object(system_monitor_module.psutil, "sensors_battery", return_value=None):
                self.assertEqual(monitor.get_system_stats()["is_storage_alert"], expected)

    def test_rejects_invalid_storage_thresholds(self):
        for threshold in (-1, 101, "90", True):
            with self.subTest(threshold=threshold), self.assertRaises(ValueError):
                system_monitor_module.SystemMonitor(storage_threshold_pct=threshold)


class FakeClock:
    def __init__(self, now=0):
        self.now = now
        self.readings = []

    def monotonic(self):
        if self.readings:
            return self.readings.pop(0)
        return self.now


class FakeStopEvent:
    def __init__(self, clock, stop_after_waits, on_wait=None):
        self.clock = clock
        self.stop_after_waits = stop_after_waits
        self.on_wait = on_wait
        self.wait_count = 0
        self.stopped = False

    def is_set(self):
        return self.stopped

    def wait(self, seconds):
        self.wait_count += 1
        self.clock.now += seconds
        if self.on_wait:
            self.on_wait(self.wait_count)
        if self.wait_count >= self.stop_after_waits:
            self.stopped = True
        return self.stopped


class FakeConfig:
    def __init__(self, used_seconds, limit_minutes=1):
        self.site = {
            "domain": "youtube.com",
            "limit_minutes": limit_minutes,
            "used_seconds": used_seconds,
        }
        self.save_count = 0

    def get(self, key, default=None):
        return [self.site] if key == "tracked_websites" else default

    def save_config(self):
        self.save_count += 1
        return True


class TabCloserTests(unittest.TestCase):
    def test_active_window_callback_receives_foreground_title(self):
        config = FakeConfig(0, limit_minutes=0)
        clock = FakeClock()
        clock.readings = [10, 14, 14]
        event = FakeStopEvent(clock, stop_after_waits=1)
        observed_titles = []
        service = tab_closer_module.TabCloser(
            config,
            on_active_window_callback=observed_titles.append,
        )
        service.running = True
        service._stop_event = event
        service.get_active_window_info = lambda: ("Editor - notes.txt", "")

        with patch.object(tab_closer_module.time, "monotonic", side_effect=clock.monotonic):
            service._loop()

        self.assertEqual(observed_titles, ["Editor - notes.txt"])

    def run_monitor(self, used_seconds, stop_after_waits, title_change=None):
        clock = FakeClock()
        clock.readings = [10, 14]
        config = FakeConfig(used_seconds)
        state = types.SimpleNamespace(title="YouTube - Browser")
        event = FakeStopEvent(
            clock,
            stop_after_waits,
            on_wait=lambda count: setattr(state, "title", title_change)
            if title_change and count == 1 else None,
        )
        service = tab_closer_module.TabCloser(config)
        service.running = True
        service._stop_event = event
        service.get_active_window_info = lambda: (state.title, "")
        service.get_active_window_title = lambda: state.title

        with patch.object(tab_closer_module.time, "monotonic", side_effect=clock.monotonic), \
                patch.object(tab_closer_module.time, "sleep", side_effect=AssertionError("blocking sleep used")), \
                patch.object(pyautogui_stub, "hotkey") as hotkey:
            service._loop()

        return config, hotkey

    def test_counts_elapsed_foreground_time(self):
        config = FakeConfig(0, limit_minutes=0)
        clock = FakeClock()
        clock.readings = [10, 14, 14]
        event = FakeStopEvent(clock, stop_after_waits=1)
        service = tab_closer_module.TabCloser(config)
        service.running = True
        service._stop_event = event
        service.get_active_window_info = lambda: ("YouTube - Browser", "")

        with patch.object(tab_closer_module.time, "monotonic", side_effect=clock.monotonic):
            service._loop()

        self.assertEqual(config.site["used_seconds"], 4)

    def test_resets_usage_only_after_auto_close(self):
        config, hotkey = self.run_monitor(60, stop_after_waits=11)

        hotkey.assert_called_once_with("ctrl", "w")
        self.assertEqual(config.site["used_seconds"], 0)

    def test_cancelled_warning_preserves_usage(self):
        config, hotkey = self.run_monitor(
            60, stop_after_waits=2, title_change="Another app",
        )

        hotkey.assert_not_called()
        self.assertEqual(config.site["used_seconds"], 64)

    def test_service_threads_stop_and_restart_cleanly(self):
        class EmptyConfig:
            def get(self, key, default=None):
                return [] if key == "tracked_websites" else default

            def save_config(self):
                return True

        class Api:
            _win_x = 40
            _win_y = 800

            def set_orientation(self, *args):
                pass

            def notify_ui(self, *args):
                pass

            def move_window_to(self, *args):
                pass

            def trigger_web_line(self, *args):
                pass

            def clear_web_line(self):
                pass

        services = [
            reminders_module.ReminderManager(EmptyConfig()),
            roamer_module.MascotRoamer(Api()),
            tab_closer_module.TabCloser(EmptyConfig()),
        ]

        for service in services:
            with self.subTest(service=type(service).__name__):
                for _ in range(2):
                    service.start()
                    service.stop()
                    self.assertFalse(service._thread.is_alive())


class ScreenObservationTests(unittest.TestCase):
    def test_window_titles_are_only_notified_while_observation_is_active(self):
        class CharacterWindow:
            def __init__(self):
                self.scripts = []

            def evaluate_js(self, script):
                self.scripts.append(script)

        bridge = api_bridge_module.ApiBridge(None, None, None, None, None)
        character = CharacterWindow()
        bridge.set_character_window(character)

        bridge.observe_active_window("Editor - private notes")
        self.assertEqual(character.scripts, [])
        self.assertFalse(bridge.get_window_observation_status())

        bridge.start_window_observation()
        title = 'Browser - "private" notes'
        bridge.observe_active_window(title)
        bridge.observe_active_window(title)

        self.assertTrue(bridge.get_window_observation_status())
        self.assertEqual(len(character.scripts), 2)
        expected_message = f"Active window: {title}"
        self.assertEqual(
            character.scripts[-1],
            f"window.setPose('idle', {json.dumps(expected_message)});",
        )

        bridge.stop_window_observation()
        bridge.observe_active_window("Another window")
        self.assertFalse(bridge.get_window_observation_status())
        self.assertEqual(len(character.scripts), 3)

    def test_hiding_warning_restores_expanded_mascot_window_size(self):
        class CharacterWindow:
            def __init__(self):
                self.sizes = []

            def evaluate_js(self, script):
                pass

            def resize(self, width, height):
                self.sizes.append((width, height))

            def move(self, x, y):
                pass

        bridge = api_bridge_module.ApiBridge(None, None, None, None, None)
        character = CharacterWindow()
        bridge.set_character_window(character, 40, 800, 280, 200)

        bridge.update_website_warning("youtube.com", 10)
        bridge.update_website_warning("youtube.com", None)

        self.assertEqual(character.sizes, [(520, 180), (280, 200)])


class MascotRoamerTests(unittest.TestCase):
    def test_climbing_keeps_mascot_at_same_horizontal_position(self):
        class Api:
            def __init__(self):
                self.positions = []

            def move_window_to(self, x, y):
                self.positions.append((x, y))

        api = Api()
        roamer = roamer_module.MascotRoamer(api)
        roamer.running = True

        final_y = roamer._move_vertically(240, 100, 76)

        self.assertEqual(final_y, 76)
        self.assertEqual(api.positions, [(240, 88), (240, 76)])

    def test_roaming_uses_requested_directional_pose_sequence_at_screen_edges(self):
        class Api:
            _win_x = 0
            _win_y = 160

            def __init__(self):
                self.positions = []
                self.orientations = []
                self.poses = []
                self.web_lines = []

            def move_window_to(self, x, y):
                self._win_x = x
                self._win_y = y
                self.positions.append((x, y))

            def set_orientation(self, mode, direction):
                self.orientations.append((mode, direction))

            def notify_ui(self, pose, _message):
                self.poses.append(pose)

            def trigger_web_line(self, direction):
                self.web_lines.append(("show", direction))

            def clear_web_line(self):
                self.web_lines.append(("clear", None))

        api = Api()
        roamer = roamer_module.MascotRoamer(api)
        roamer.screen_width = 300
        roamer.screen_height = 240
        roamer.win_w = 100
        roamer.win_h = 80
        roamer.running = True
        roamer._stop_event.wait = lambda _seconds: False

        roamer._roam_cycle()

        self.assertEqual(api.positions[0], (4, 160))
        self.assertIn((200, 160), api.positions)
        self.assertIn((200, 0), api.positions)
        self.assertIn((0, 0), api.positions)
        self.assertEqual(api.positions[-1], (0, 160))
        self.assertEqual(
            api.orientations,
            [
                ("normal", "right"),
                ("normal", "right"),
                ("upside_down", "left"),
                ("normal", "left"),
            ],
        )
        self.assertEqual(
            api.poses,
            ["walk_right", "climb_up", "ceiling_walk", "climb_down", "landing"],
        )
        self.assertEqual(api.web_lines, [("show", "down"), ("clear", None)])


if __name__ == "__main__":
    unittest.main()
