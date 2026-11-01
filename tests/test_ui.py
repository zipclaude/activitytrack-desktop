# SPDX-License-Identifier: GPL-3.0-or-later
"""The windows build and say the right thing (offscreen: QT_QPA_PLATFORM=offscreen)."""

import os
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QSettings  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

from activitytrack_desktop import icons, wire  # noqa: E402
from activitytrack_desktop.pairing import Account  # noqa: E402
from activitytrack_desktop.session import Session  # noqa: E402

app = QApplication.instance() or QApplication([])
# the filters remembered by the Home: in a folder of the tests, not the user's settings
_settings_dir = tempfile.mkdtemp()
app.setApplicationName("activitytrack-desktop-tests")
QSettings.setDefaultFormat(QSettings.Format.IniFormat)
QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, _settings_dir)


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

    def menu_texts(self, menu):
        return [a.text() for a in menu.actions()]

    def test_the_tray(self):
        from activitytrack_desktop.home import Actions
        from activitytrack_desktop.ui import MainWindow, Tray
        from activitytrack_desktop.work import StartRequest
        actions = Actions(self.session)
        w = MainWindow(self.session, self.service, actions)
        t = Tray(self.session, self.service, w, quit_app=lambda: None, actions=actions)
        self.assertIn("Non associato", t.toolTip())
        self.assertNotIn("Sincronizza ora", self.menu_texts(t.contextMenu()))
        self.pair()
        self.session.store.pulled({"type": "client", "uid": "c1", "rev": 1,
                                   "fields": {"name": "Biblioteca", "archived": False}})
        actions.work.start(StartRequest(client="c1", activity="Rete"))
        t.refresh()
        texts = self.menu_texts(t.contextMenu())
        self.assertEqual(texts[0], "Biblioteca · Rete — In lavoro")
        self.assertIn("Nuova attività…", texts)
        self.assertIn("Sincronizza ora", texts)
        sub = [a.text() for a in t.contextMenu().actions()[0].menu().actions()]
        self.assertEqual(sub[:4], ["Pausa", "Viaggio", "Sospendi", "Stop"])
        self.assertIn("Biblioteca · Rete — In lavoro", t.toolTip())
        # middle click: pause, then back to work
        t._pause_or_resume()
        self.assertEqual(actions.work.running()[0]["mode"], "PAUSE")

    def test_the_home_and_the_quick_entry(self):
        from activitytrack_desktop import forms
        from activitytrack_desktop.home import Actions, Card, Home
        self.pair()
        actions = Actions(self.session)
        home = Home(actions)
        d = forms.QuickEntry(actions.work)
        d.description.setPlainText("Configurazione rete")
        d.client.setEditText("Comune di Valdora")
        d.tags.setText("urgente, rete")
        d.confirm()
        self.assertEqual(d.result(), 1)
        e = self.session.store.get("entry", d.result_uid)
        self.assertEqual((e["activity"], e["tags"]), ("Configurazione rete", ["urgente", "rete"]))
        self.assertEqual(self.session.store.get("client", e["clientUid"])["name"], "Comune di Valdora")
        home.refresh()
        cards = home.scroll.widget().findChildren(Card)
        self.assertEqual(len(cards), 1)
        # a refused start says why and stays open
        d = forms.QuickEntry(actions.work)
        d.confirm()
        self.assertIn("Serve il cliente", d.message.text())

    def test_todos_on_the_home_and_in_the_tray(self):
        from datetime import date

        from activitytrack_desktop import forms
        from activitytrack_desktop.home import Actions, Home, TodoRow
        from activitytrack_desktop.ui import MainWindow, Tray
        self.pair()
        actions = Actions(self.session)
        d = forms.TodoDialog(actions.todos)
        d.title.setText("Rinnovo certificati")
        d.client.setEditText("Hotel Belvedere")
        d.plan.set(date.today(), 23 * 60 + 30, 15)
        d.confirm()
        self.assertEqual(d.result(), 1)
        t = self.session.store.get("todo", d.result_uid)
        self.assertEqual((t["planStartMin"], t["durationMin"]), (23 * 60 + 30, 15))
        home = Home(actions)
        rows = home.scroll.widget().findChildren(TodoRow)
        self.assertEqual(len(rows), 1)
        w = MainWindow(self.session, self.service, actions)
        tray = Tray(self.session, self.service, w, quit_app=lambda: None, actions=actions)
        start = [a for a in tray.contextMenu().actions() if a.text() == "Avvia Da fare"]
        self.assertEqual([a.text() for a in start[0].menu().actions()], ["Rinnovo certificati · Hotel Belvedere"])
        self.assertIn("Nuovo Da fare…", self.menu_texts(tray.contextMenu()))
        actions.todo_done(d.result_uid)
        self.assertEqual(home.scroll.widget().findChildren(TodoRow), [])
        # shown again with the done ones in the filter
        home.filters.show_actions["DONE"].setChecked(True)
        self.assertEqual(len(home.scroll.widget().findChildren(TodoRow)), 1)

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


class FakeNotifier:
    native = True

    def __init__(self):
        from PyQt6.QtCore import QObject, pyqtSignal

        class _S(QObject):
            answered = pyqtSignal(str, str)
        self._s = _S()
        self.answered = self._s.answered
        self.shown = []

    def show(self, key, title, body, actions=()):
        self.shown.append((key, title, body, [a for a, _l in actions]))


class RemindersUiTest(unittest.TestCase):
    def setUp(self):
        from activitytrack_desktop.home import Actions
        from activitytrack_desktop.service import SyncService
        self.dir = tempfile.TemporaryDirectory()
        self.session = Session(self.dir.name, use_keyring=False)
        self.service = SyncService(self.session)
        a = Account("https://at.example.com", None, "d1", "anna", "Anna", "user", "Infra")
        self.session.store.set_state("account", a.to_json())
        self.session.vault.put("d1", "tok")
        self.session.store.pulled({"type": "client", "uid": "c1", "rev": 1,
                                   "fields": {"name": "Biblioteca", "archived": False}})
        self.actions = Actions(self.session)
        QSettings().remove("reminders")

    def tearDown(self):
        self.service.stop()
        self.session.store.close()
        self.dir.cleanup()

    def test_confirm_posted_and_answered(self):
        from activitytrack_desktop.reminder_ui import Reminders
        from activitytrack_desktop.work import StartRequest
        work = self.actions.work
        now = [work.clock()]
        work.clock = lambda: now[0]
        uid = work.start(StartRequest(client="c1", activity="Rete", start_ms=now[0] - 40 * 60_000))
        n = FakeNotifier()
        r = Reminders(self.actions, n, show_window=lambda: None)
        r.fire()
        self.assertEqual(len(n.shown), 1)
        key, title, _body, buttons = n.shown[0]
        expected = ("confirm", "Ancora su Biblioteca?", ["yes", "pause", "stop_at"])
        self.assertEqual((key.split("|")[0], title, buttons), expected)
        # shown once: the next only after another interval
        r.fire()
        self.assertEqual(len(n.shown), 1)
        n.answered.emit(key, "pause")
        self.assertEqual(self.session.store.get("entry", uid)["mode"], "PAUSE")
        # switched off: not shown, still recorded
        QSettings().setValue("reminders/on/pause", False)
        now[0] += 20 * 60_000
        r.fire()
        self.assertEqual(len(n.shown), 1)
        self.assertTrue(r.timer.isActive())
