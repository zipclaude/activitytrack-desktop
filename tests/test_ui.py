# SPDX-License-Identifier: GPL-3.0-or-later
"""The windows build and say the right thing (offscreen: QT_QPA_PLATFORM=offscreen)."""

import os
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication  # noqa: E402

from activitytrack_desktop import icons, wire  # noqa: E402
from activitytrack_desktop.pairing import Account  # noqa: E402
from activitytrack_desktop.session import Session  # noqa: E402

app = QApplication.instance() or QApplication([])


class UiTest(unittest.TestCase):
    def setUp(self):
        from activitytrack_desktop.service import SyncService
        self.dir = tempfile.TemporaryDirectory()
        self.session = Session(self.dir.name, use_keyring=False)
        self.service = SyncService(self.session)

    def tearDown(self):
        self.service.stop()
        self.session.store.close()
        self.dir.cleanup()

    def pair(self):
        a = Account("https://at.example.com", None, "d1", "anna", "Anna Rossi", "user", "Infra")
        self.session.store.set_state("account", a.to_json())
        self.session.vault.put("d1", "tok")

    def test_the_states_of_the_sync(self):
        from activitytrack_desktop.ui import needs_attention, state_text
        s = self.session
        self.assertIn("Non associato", state_text(s, "idle", ""))
        self.assertTrue(needs_attention(s, "idle"))
        self.pair()
        self.assertIn("prima sincronizzazione", state_text(s, "idle", ""))
        self.assertFalse(needs_attention(s, "idle"))
        self.assertIn("non raggiungibile", state_text(s, "offline", "x"))
        s.store.set_state("incompatible", wire.APP_TOO_OLD)
        self.assertIn("aggiorna ActivityTrack Desktop", state_text(s, "incompatible", ""))
        s.store.set_state("incompatible", wire.SERVER_TOO_OLD)
        self.assertIn("va aggiornato il server", state_text(s, "incompatible", ""))
        self.assertTrue(needs_attention(s, "incompatible"))
        s.store.set_state("revoked", True)
        self.assertIn("revocato", state_text(s, "revoked", ""))

    def test_the_sync_panel(self):
        from activitytrack_desktop.ui import SyncPanel
        p = SyncPanel(self.session, self.service)
        self.assertFalse(p.unpair.isVisibleTo(p))
        self.pair()
        self.session.store.write("todo", "t1", {"title": "x"}, now_ms=1)
        p.refresh()
        self.assertEqual(p.values["user"].text(), "Anna Rossi (anna)")
        self.assertEqual(p.values["pending"].text(), "1")
        self.assertTrue(p.unpair.isVisibleTo(p))
        self.assertIn("file leggibile solo dal tuo utente", p.secret.text())

    def test_the_tray(self):
        from activitytrack_desktop.ui import MainWindow, Tray
        w = MainWindow(self.session, self.service)
        t = Tray(self.session, self.service, w, quit_app=lambda: None)
        self.assertIn("Non associato", t.toolTip())
        self.assertFalse(t.sync_now.isVisible())
        self.pair()
        t.refresh()
        self.assertTrue(t.sync_now.isVisible())

    def test_closing_hides_quitting_closes(self):
        from activitytrack_desktop.ui import MainWindow
        w = MainWindow(self.session, self.service)
        w.show()
        # refused, the window only hides: the tray icon stays
        self.assertFalse(w.close())
        self.assertFalse(w.isVisible())
        w.show()
        w.quitting = True
        self.assertTrue(w.close())

    def test_icons(self):
        for state in (icons.IDLE, icons.WORK, icons.PAUSE, icons.TRAVEL):
            self.assertFalse(icons.icon(state, alert=True).isNull())
