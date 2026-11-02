# SPDX-License-Identifier: GPL-3.0-or-later
"""The notifier on a real session bus, against a fake notification server (skipped without a bus)."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QEventLoop, QTimer  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication([])


@unittest.skipUnless(os.environ.get("DBUS_SESSION_BUS_ADDRESS"), "no session bus")
class NotifyTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.log = Path(self.dir.name) / "log"
        self.server = subprocess.Popen([sys.executable, str(Path(__file__).with_name("fake_notifications.py")),
                                        str(self.log)], stdout=subprocess.PIPE, text=True)
        self.assertEqual(self.server.stdout.readline().strip(), "ready")

    def tearDown(self):
        self.server.terminate()
        self.server.wait(5)
        self.server.stdout.close()
        self.dir.cleanup()

    def test_a_notification_with_buttons_and_its_answer(self):
        from activitytrack_desktop.notify import Notifier
        n = Notifier()
        self.assertTrue(n.native)
        got = []
        n.answered.connect(lambda key, action: got.append((key, action)))
        n.show("confirm:e1", "Ancora su Acme?", "Ultima conferma alle 9:30", [("yes", "Sì"), ("pause", "Pausa")])
        loop = QEventLoop()
        QTimer.singleShot(3000, loop.quit)
        n.answered.connect(lambda *a: loop.quit())
        loop.exec()
        self.assertEqual(got, [("confirm:e1", "yes")])
        sent = json.loads(self.log.read_text().splitlines()[0])
        self.assertEqual(sent["actions"], ["yes", "Sì", "pause", "Pausa", "default", "Apri"])
        self.assertEqual(sent["summary"], "Ancora su Acme?")

    def test_the_default_action_in_the_interfaces_language(self):
        import activitytrack_desktop
        from activitytrack import i18n
        from activitytrack_desktop.notify import Notifier
        i18n.add_catalogs(Path(activitytrack_desktop.__file__).with_name("locale"))
        i18n.set_language("en")
        try:
            Notifier().show("update|1.0", "ActivityTrack 1.0", "", [("open", "Download")], persistent=False)
        finally:
            i18n.set_language("it")
        # written by the server before its reply
        sent = json.loads(self.log.read_text().splitlines()[0])
        self.assertEqual(sent["actions"], ["open", "Download", "default", "Open"])
