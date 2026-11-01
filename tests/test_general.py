# SPDX-License-Identifier: GPL-3.0-or-later
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from activitytrack_desktop import autostart, updates

RELEASES = json.dumps([
    {"tag_name": "v0.9.4-beta1", "prerelease": True, "html_url": "https://x/b1"},
    {"tag_name": "v0.9.3", "prerelease": False, "html_url": "https://x/093"},
    {"tag_name": "v0.9.5", "draft": True},
    {"tag_name": "v0.9.3-alfa1", "prerelease": True},
])


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

    def test_newer(self):
        self.assertEqual(updates.newer(RELEASES, "0.9.3-alfa1", betas=True).version, "0.9.4-beta1")
        # without the betas: the stable 0.9.3 is newer than the alfa
        self.assertEqual(updates.newer(RELEASES, "0.9.3-alfa1", betas=False).url, "https://x/093")
        self.assertIsNone(updates.newer(RELEASES, "0.9.4-beta1", betas=True))
        self.assertIsNone(updates.newer("{", "0.9.3", betas=True))


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
