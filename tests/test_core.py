import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from linuxcnc_notify.core import active, default_config, ensure_config, faults


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
        status.joint = [{"fault": 1}, {"max_hard_limit": 1}]
        self.assertEqual(faults(status), ["joint 0 drive fault", "joint 1 maximum hard limit"])

    def test_active(self):
        status = mock.Mock(interp_state=FakeLinuxCNC.INTERP_PAUSED)
        self.assertTrue(active(status, FakeLinuxCNC))


if __name__ == "__main__":
    unittest.main()
