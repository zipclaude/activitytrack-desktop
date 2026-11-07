# SPDX-License-Identifier: GPL-3.0-or-later
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from activitytrack import updates
from activitytrack_desktop import autostart

class UpdatesTest(unittest.TestCase):
    def test_compare(self):
        order = ["0.9.3-alfa1", "0.9.3-beta.2", "0.9.3-beta.10", "0.9.3", "0.9.4-alfa1", "0.9.4-beta1", "0.9.4",
                 "1.0"]
        for a, b in zip(order, order[1:]):
            self.assertEqual(updates.compare(a, b), -1, (a, b))
            self.assertEqual(updates.compare(b, a), 1, (a, b))
        self.assertEqual(updates.compare("1.0", "1.0.0"), 0)
        self.assertEqual(updates.compare("v1.2", "1.2.0"), 0)
        self.assertEqual(updates.compare("x", "0.0.1"), -1)


@unittest.skipIf(sys.platform == "win32", "the XDG entry")
class AutostartTest(unittest.TestCase):
    def test_xdg_entry(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": d}):
            self.assertFalse(autostart.enabled())
            autostart.set_enabled(True)
            text = (Path(d) / "autostart" / "activitytrack-desktop.desktop").read_text()
            self.assertIn("--hidden", text)
            self.assertIn("Icon=activitytrack-desktop", text)
            self.assertTrue(autostart.enabled())
            autostart.set_enabled(False)
            self.assertFalse(autostart.enabled())
