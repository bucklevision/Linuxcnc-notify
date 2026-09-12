import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from linuxcnc_notify.core import (active, default_config, ensure_config,
                                  event_enabled, faults,
                                  load_notification_config,
                                  reported_line,
                                  subscription_deep_link)
from linuxcnc_notify.dashboard import collect_variables


class FakeLinuxCNC:
    INTERP_READING = 1
    INTERP_WAITING = 2
    INTERP_PAUSED = 3


class CoreTests(unittest.TestCase):
    def test_topic_is_random_and_long(self):
        first, second = default_config(), default_config()
        self.assertNotEqual(first["topic"], second["topic"])
        self.assertGreaterEqual(len(first["topic"]), 40)

    def test_config_created_mode_600_and_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            first = ensure_config(path)
            second = ensure_config(path)
            self.assertEqual(first, second)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_faults(self):
        status = mock.Mock()
        status.joints = 2
        status.joint = [{"fault": 1}, {"max_hard_limit": 1}]
        self.assertEqual(faults(status), ["joint 0 drive fault", "joint 1 maximum hard limit"])

    def test_unused_compiled_joint_slots_are_ignored(self):
        status = mock.Mock()
        status.joints = 1
        status.joint = [{"fault": 0}, {"fault": 1}]
        self.assertEqual(faults(status), [])

    def test_active(self):
        status = mock.Mock(interp_state=FakeLinuxCNC.INTERP_PAUSED)
        self.assertTrue(active(status, FakeLinuxCNC))

    def test_ntfy_app_deep_link(self):
        config = default_config()
        config.update({"server": "https://ntfy.sh", "topic": "linuxcnc-secret", "machine_name": "Workshop CNC"})
        self.assertEqual(
            subscription_deep_link(config),
            "ntfy://ntfy.sh/linuxcnc-secret?display=Workshop+CNC+LinuxCNC",
        )

    def test_insecure_self_hosted_deep_link(self):
        config = default_config()
        config.update({"server": "http://cnc.local:8080", "topic": "secret", "machine_name": "CNC"})
        self.assertIn("secure=false", subscription_deep_link(config))

    def test_notification_config_and_running_mode(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "notify.conf"
            path.write_text("[notifications]\nprogram_started=yes\nmachine_off=no\nhard_limit=running\n")
            settings = load_notification_config(path)
        self.assertTrue(event_enabled(settings, "program_started"))
        self.assertFalse(event_enabled(settings, "machine_off"))
        self.assertFalse(event_enabled(settings, "hard_limit", False))
        self.assertTrue(event_enabled(settings, "hard_limit", True))

    def test_dashboard_collects_and_groups_variables(self):
        class Status:
            task_state = 4
            file = "/tmp/example.ngc"
            position = (1.0, 2.0, 3.0)
            custom_value = "present"

            def poll(self):
                pass

        grouped = collect_variables(Status())
        self.assertEqual(grouped["Overview"]["task_state"], 4)
        self.assertEqual(grouped["Program and interpreter"]["file"], "/tmp/example.ngc")
        self.assertEqual(grouped["Other"]["custom_value"], "present")

    def test_running_line_uses_motion_not_interpreter_read_ahead(self):
        status = mock.Mock(current_line=198, motion_line=20)
        self.assertEqual(reported_line(status, True), 20)
        self.assertEqual(reported_line(status, False), 198)

    def test_running_line_falls_back_before_motion_starts(self):
        status = mock.Mock(current_line=7, motion_line=0)
        self.assertEqual(reported_line(status, True), 7)


if __name__ == "__main__":
    unittest.main()
