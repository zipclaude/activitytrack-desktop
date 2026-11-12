# SPDX-License-Identifier: GPL-3.0-or-later
"""The windows build and say the right thing (offscreen: QT_QPA_PLATFORM=offscreen)."""

import os
import tempfile
import threading
import time
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QSettings, Qt  # noqa: E402
from PyQt6.QtGui import QColor, QPalette  # noqa: E402
from PyQt6.QtWidgets import QApplication, QDialogButtonBox, QToolButton  # noqa: E402

from activitytrack import wire  # noqa: E402
from activitytrack.texts import sync_needs_attention as needs_attention, sync_state as state_text  # noqa: E402
from activitytrack_desktop import icons  # noqa: E402
from activitytrack.pairing import Account  # noqa: E402
from activitytrack.session import Session  # noqa: E402

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
        s = self.session
        self.assertIn("Non associato", state_text(s, "idle", ""))
        self.assertTrue(needs_attention(s, "idle"))
        self.pair()
        self.assertIn("prima sincronizzazione", state_text(s, "idle", ""))
        self.assertFalse(needs_attention(s, "idle"))
        self.assertIn("non raggiungibile", state_text(s, "offline", "x"))
        s.store.set_state("incompatible", wire.APP_TOO_OLD)
        self.assertIn("aggiorna ActivityTrack sul PC", state_text(s, "incompatible", ""))
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
        from activitytrack.work import StartRequest
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
        self.assertEqual(sub[:3], ["Pausa", "Viaggio", "Stop"])
        self.assertNotIn("Sospendi", sub)
        self.assertIn("Biblioteca · Rete — In lavoro", t.toolTip())
        # middle click: pause, then back to work
        t._pause_or_resume()
        self.assertEqual(actions.work.running()[0]["mode"], "PAUSE")

    def test_the_home_and_the_quick_entry(self):
        from activitytrack_desktop import forms
        from activitytrack_desktop.home import Actions, BigCard, Home
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
        cards = home.scroll.widget().findChildren(BigCard)
        self.assertEqual(len(cards), 1)
        self.assertEqual(home.big_uid, d.result_uid)
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
        d = forms.TodoDialog(actions.work)
        d.title.setText("Rinnovo certificati")
        d.client.setEditText("Hotel Belvedere")
        d.plan.set(date.today(), 23 * 60 + 30, 15)
        d.confirm()
        self.assertEqual(d.result(), 1)
        t = self.session.store.get("entry", d.result_uid)
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

    def sample(self, actions):
        """A client with a company colour, a tag; at work, suspended, stopped and to-dos."""
        from datetime import date

        from activitytrack.work import StartRequest
        store = self.session.store
        store.pulled({"type": "company", "uid": "co", "rev": 1, "fields": {"name": "Alfa", "color": 0x3D7BEA}})
        store.pulled({"type": "client", "uid": "c1", "rev": 1, "fields": {"name": "Biblioteca", "companyUid": "co"}})
        store.pulled({"type": "tag", "uid": "tg", "rev": 1, "fields": {"name": "rete", "color": 0x00A3A3}})
        w = actions.work
        now = w.clock()
        old = w.start(StartRequest(client="c1", activity="", start_ms=now - 200 * 60_000, end_ms=now - 150 * 60_000))
        w.edit(old, client="")
        b = w.start(StartRequest(client="c1", activity="Stampanti", start_ms=now - 120 * 60_000))
        w.suspend(b, at=now - 100 * 60_000)
        a = w.start(StartRequest(client="c1", activity="Rete", tags=["rete"], start_ms=now - 60 * 60_000))
        w.save_todo(None, "Backup", plan_date=date.today(), plan_min=23 * 60, duration_min=30)
        w.save_todo(None, "Inventario")
        return a, b, old

    def test_the_home_light_and_dark(self):
        from activitytrack_desktop import theme
        from activitytrack_desktop.home import Actions, BigCard, EntryRow, Home, SmallCard, TodoRow
        self.pair()
        actions = Actions(self.session)
        a, b, old = self.sample(actions)
        try:
            for dark in (False, True):
                theme.install(dark=dark)
                self.assertEqual(theme.tokens().dark, dark)
                self.assertEqual(QApplication.instance().palette().color(QPalette.ColorRole.Window).name(),
                                 theme.tokens().bg)
                home = Home(actions)
                home.resize(800, 900)
                body = home.scroll.widget()
                big = body.findChildren(BigCard)
                self.assertEqual([c.uid for c in big], [a])
                self.assertEqual(big[0].band, "#3d7bea")
                self.assertEqual(set(big[0].commands), {"PAUSE", "TRAVEL", "stop"})
                self.assertEqual([c.uid for c in body.findChildren(SmallCard)], [b])
                self.assertEqual([r.uid for r in body.findChildren(EntryRow)], [old])
                self.assertEqual(len(body.findChildren(TodoRow)), 2)
                self.assertFalse(home.grab().isNull())
                # a small card brought to the big one
                home.select(b)
                self.assertEqual([c.uid for c in home.scroll.widget().findChildren(BigCard)], [b])
                self.assertEqual(home.big_uid, b)
                # the search narrows the list, not the cards
                home.filters.search.setText("inventario")
                self.assertEqual([r.title.text() for r in body.findChildren(TodoRow)], ["Inventario"])
                self.assertEqual(body.findChildren(EntryRow), [])
                home.filters.search.clear()
        finally:
            theme.install(dark=False)

    def test_the_window_keys(self):
        from PyQt6.QtGui import QKeySequence

        from activitytrack_desktop import widgets
        from activitytrack_desktop.home import Actions
        from activitytrack_desktop.ui import MainWindow
        self.pair()
        actions = Actions(self.session)
        a, b, _old = self.sample(actions)
        w = MainWindow(self.session, self.service, actions)
        keys = {name: act.shortcut().toString() for name, act in w.shortcuts.items()}
        self.assertEqual(keys, {"new_entry": "Ctrl+N", "pause": "Ctrl+P", "stop": "Ctrl+T", "new_todo": "Ctrl+D",
                                "find": "Ctrl+F", "sync": "F5", "section1": "Ctrl+1", "section2": "Ctrl+2",
                                "section3": "Ctrl+3"})
        for act in w.shortcuts.values():
            self.assertIn(act, w.actions())
            self.assertEqual(act.shortcutContext(), Qt.ShortcutContext.WindowShortcut)
        # shown in the tooltips
        self.assertIn("Ctrl+N", w.home.new.toolTip())
        self.assertIn("Ctrl+2", w.rail.items["todos"].toolTip())
        self.assertIn(QKeySequence("F5").toString(), w.sync_item.toolTip())
        # the sections
        w.shortcuts["section2"].trigger()
        self.assertEqual(w.current_section(), "todos")
        w.shortcuts["section3"].trigger()
        self.assertEqual(w.current_section(), "settings")
        w.shortcuts["section1"].trigger()
        self.assertEqual(w.current_section(), "home")
        # the dialogs and the sync, each its action
        with mock.patch.object(actions, "new_entry") as new, mock.patch.object(actions, "new_todo") as todo, \
                mock.patch.object(self.service, "sync") as sync, mock.patch.object(w.home, "focus_search") as find:
            w.shortcuts["new_entry"].trigger()
            w.shortcuts["new_todo"].trigger()
            w.shortcuts["sync"].trigger()
            w.shortcuts["find"].trigger()
        new.assert_called_once_with()
        todo.assert_called_once_with()
        sync.assert_called_once_with(full=True)
        find.assert_called_once_with()
        # pause the one at work, then resume it
        store = self.session.store
        w.shortcuts["pause"].trigger()
        self.assertEqual(store.get("entry", a)["mode"], "PAUSE")
        w.shortcuts["pause"].trigger()
        self.assertEqual(store.get("entry", a)["mode"], "WORK")
        # stop: the big card's (description and client: closed at once, no sheet)
        w.home.select(b)
        w.shortcuts["stop"].trigger()
        self.assertEqual(store.get("entry", b)["status"], "CLOSED")
        self.assertEqual(store.get("entry", a)["mode"], "WORK")
        # two at work: the user chooses in the small list
        from activitytrack.work import StartRequest
        c = actions.work.start(StartRequest(client="c1", activity="Terza"))
        with mock.patch.object(widgets, "choose", return_value=a) as choose:
            w.shortcuts["pause"].trigger()
        self.assertEqual([uid for uid, _t in choose.call_args[0][2]], [c, a])
        self.assertEqual(store.get("entry", a)["mode"], "PAUSE")
        self.assertEqual(store.get("entry", c)["mode"], "WORK")
        # no stop sheet any more: a closed activity without a description is simply DONE
        d = actions.work.start(StartRequest(client="c1", activity=""))
        w.home.select(d)
        w.shortcuts["stop"].trigger()
        self.assertEqual(store.get("entry", d)["status"], "CLOSED")
        self.assertEqual(actions.work.display(store.get("entry", d))[0], "DONE")

    def test_every_displayed_state_has_an_icon_and_a_colour(self):
        from activitytrack import model
        from activitytrack_desktop import icons, states
        self.assertEqual(set(states.LOOK), set(model.DISPLAY_STATES))
        for state in model.DISPLAY_STATES:
            self.assertTrue(states.icon(state) in icons.PATHS or states.icon(state) == "suspend", state)
        # the bin and the plan are both grey (§2.2)
        self.assertEqual(len({states.colour(s) for s in model.DISPLAY_STATES}), len(model.DISPLAY_STATES) - 1)

    def test_the_stop_offers_the_return_trip_and_travel_asks_if_work_is_done(self):
        from activitytrack.work import StartRequest, TRAVEL, WORK
        from activitytrack_desktop import forms
        from activitytrack_desktop.home import Actions
        self.pair()
        actions = Actions(self.session)
        w = actions.work
        now = w.clock()
        self.session.store.pulled({"type": "client", "uid": "c1", "rev": 1, "fields": {"name": "B", "archived": False}})
        uid = w.start(StartRequest(client="c1", activity="x", mode=TRAVEL, start_ms=now - 120 * 60_000))
        w.switch(uid, WORK, at=now - 100 * 60_000)
        self.assertTrue(w.return_trip_offered(uid))
        chosen = {}

        class Box:
            def __init__(self, parent=None):
                self.buttons = []

            def setWindowTitle(self, t):
                pass

            setText = setWindowTitle

            def addButton(self, text, role=None):
                self.buttons.append(text)
                return text

            def exec(self):
                pass

            def clickedButton(self):
                return self.buttons[chosen["i"]]
            StandardButton = forms.QMessageBox.StandardButton
            ButtonRole = forms.QMessageBox.ButtonRole
        with mock.patch.object(forms, "QMessageBox", Box):
            # the third choice: stop and add the return trip
            chosen["i"] = 2
            self.assertTrue(forms.stop(w, uid))
        self.assertEqual(w.entry(uid)["status"], "CLOSED")
        self.assertEqual([s["kind"] for s in w.segments(uid)], [TRAVEL, WORK, TRAVEL])

    def test_an_absence_from_the_dialog(self):
        from datetime import date

        from activitytrack_desktop import forms
        from activitytrack_desktop.home import Actions
        self.pair()
        actions = Actions(self.session)
        d = forms.AbsenceDialog(actions.work, first=date(2026, 11, 16))
        d.kind.setCurrentIndex(d.kind.findData("LEAVE"))
        d.timed.setChecked(True)
        d.confirm()
        self.assertEqual(d.result(), 1)
        (a,) = [e for e in actions.work.entries() if e["kind"] == "ABSENCE"]
        self.assertEqual((a["absenceKind"], a["companyUid"]), ("LEAVE", None))
        self.assertEqual(actions.work.display(a)[0], "ABSENCE")

    def test_the_theme_follows_the_system(self):
        from activitytrack_desktop import theme
        app = QApplication.instance()
        st = theme.notifier()
        saved = st.system_palette
        hints = app.styleHints()
        try:
            # Qt 6.4 (Ubuntu 24.04), or a system that does not tell: the palette's lightness
            with mock.patch.object(type(hints), "colorScheme", create=True, new=None):
                st.system_palette = QPalette(QColor("#202020"))
                self.assertTrue(theme.system_dark(app))
                st.system_palette = QPalette(QColor("#f0f0f0"))
                self.assertFalse(theme.system_dark(app))
            if hasattr(Qt, "ColorScheme"):
                # Qt ≥ 6.5: the scheme first
                with mock.patch.object(type(hints), "colorScheme", lambda _self: Qt.ColorScheme.Dark):
                    self.assertTrue(theme.system_dark(app))
        finally:
            st.system_palette = saved

    def test_the_icons_are_drawn(self):
        from PyQt6.QtCore import QRectF
        for name in list(icons.PATHS) + ["suspend", "more"]:
            r = icons.shape(name).boundingRect()
            self.assertTrue(QRectF(-0.5, -0.5, 25, 25).contains(r), name)
            self.assertGreater(r.width() * r.height(), 20, name)

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

    def test_the_postpone_says_the_minutes_it_postpones(self):
        from datetime import date

        from activitytrack_desktop.home import Actions, TodoRow
        self.pair()
        actions = Actions(self.session)
        uid = actions.work.save_todo(None, "Backup", plan_date=date.today(), plan_min=23 * 60, duration_min=30)
        # the user's own snooze (Promemoria), not the policy's default
        QSettings().setValue("reminders/planSnoozeMin", 25)
        try:
            t = self.session.store.get("entry", uid)
            row = TodoRow(actions, t, "PLANNED")
            more = row.findChildren(QToolButton)[0]
            self.assertIn("Posticipa di 25 min", self.menu_texts(more.menu()))
            self.assertEqual(actions.snooze_min(), 25)
        finally:
            QSettings().remove("reminders")

    def test_cancel_waits_for_the_pairing(self):
        from activitytrack_desktop.ui import PairDialog
        d = PairDialog(self.session)
        d.link.setText("activitytrack://pair?v=1&u=https%3A%2F%2Fat.example.com&c=x")
        started = []
        with mock.patch("activitytrack_desktop.ui.threading.Thread") as thread, \
                mock.patch("activitytrack.pairing.PairLink.parse", return_value=mock.Mock(server="at.example.com")):
            thread.return_value.start = lambda: started.append(True)
            d._pair()
        self.assertEqual(started, [True])
        cancel = d.buttons.button(QDialogButtonBox.StandardButton.Cancel)
        self.assertFalse(cancel.isEnabled())
        # the server already has the code: Esc does not close the dialog
        d.show()
        d.reject()
        self.assertTrue(d.isVisible())
        d._paired(None, "expired")
        self.assertTrue(cancel.isEnabled())
        d.reject()
        self.assertFalse(d.isVisible())

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
        from activitytrack.work import StartRequest
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


class StopTest(unittest.TestCase):
    def test_a_blocked_sync_does_not_hold_the_quit(self):
        from activitytrack_desktop import service as S
        release = threading.Event()

        class Blocked:
            def __init__(self, session):
                pass

            def run(self, full):
                release.wait(30)
                return ("ok", "")
        with tempfile.TemporaryDirectory() as d, mock.patch.object(S, "Runner", Blocked):
            session = Session(d, use_keyring=False)
            service = S.SyncService(session)
            service.busy = True
            service._run.emit(True)
            time.sleep(0.2)
            t = time.monotonic()
            self.assertFalse(service.stop(wait_ms=300))
            self.assertLess(time.monotonic() - t, 2)
            # the thread, still running, outlives the service's wrapper without an abort
            thread = service._thread
            del service
            release.set()
            self.assertTrue(thread.wait(5000))
            session.store.close()

    def test_an_idle_service_stops(self):
        from activitytrack_desktop.service import SyncService
        with tempfile.TemporaryDirectory() as d:
            session = Session(d, use_keyring=False)
            self.assertTrue(SyncService(session).stop())
            session.store.close()


def _signed(version="0.9.9", component="desktop-tar"):
    """(manifest text, fingerprint of its signer): what the server relays in sync/head."""
    import datetime
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID
    from activitytrack import manifest
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "server")])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(1).not_valid_before(now).not_valid_after(now + datetime.timedelta(days=1))
            .sign(key, hashes.SHA256()))
    pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                            serialization.NoEncryption())
    chain = cert.public_bytes(serialization.Encoding.PEM)
    body = {"issued": "2026-11-07T10:00:00Z", "releases": [{
        "version": version, "channel": "prod",
        "packages": [{"component": component, "url": "/api/v1/update/files/" + "ab" * 32, "sha256": "ab" * 32}]}]}
    fingerprint = manifest.fingerprint(cert.public_bytes(serialization.Encoding.DER))
    return manifest.sign(body, pem, chain), fingerprint


class GeneralUiTest(unittest.TestCase):
    def setUp(self):
        from activitytrack_desktop.general import GeneralPanel, Updates
        from activitytrack_desktop.home import Actions
        from activitytrack_desktop.notify import Notifier
        import activitytrack
        activitytrack.set_client("ActivityTrackDesktop", "0.9.8")
        self.addCleanup(activitytrack.set_client, "ActivityTrack", activitytrack.__version__)
        self.dir = tempfile.TemporaryDirectory()
        self.session = Session(self.dir.name, use_keyring=False)
        self.notifier = Notifier(use_dbus=False)
        self.updater = Updates(Actions(self.session), self.notifier)
        self.updater.timer.stop()
        self.panel = GeneralPanel(self.updater.actions, self.updater)
        QSettings().remove("updates")
        for patch in (mock.patch("activitytrack.manifest.from_package_manager", return_value=False),
                      mock.patch("sys.platform", "linux")):
            patch.start()
            self.addCleanup(patch.stop)

    def tearDown(self):
        QSettings().remove("updates")
        self.session.store.close()
        self.dir.cleanup()

    def pair(self, key):
        from activitytrack.pairing import Account
        self.session.store.set_state("account", Account("https://at.example.com", None, "d", "anna", "A", "user", "X",
                                                        key).to_json())

    def test_what_comes_from_the_server_is_shown_as_text(self):
        from activitytrack import updates
        from activitytrack.manifest import Release
        self.assertEqual(self.panel.result.textFormat(), Qt.TextFormat.PlainText)
        self.panel._found(updates.Status(updates.AVAILABLE, Release('1.0"><img src=x>', "prod", "", "", ()), True))
        self.assertIn("<img", self.panel.result.text())
        self.assertFalse(self.panel.download.isHidden())

    def test_a_newer_version_of_the_server_is_notified_once(self):
        text, fingerprint = _signed()
        self.pair(fingerprint)
        self.session.store.set_state("update.manifest", text)
        shown = []
        self.notifier.show = lambda *a, **kw: shown.append(a)
        self.updater.evaluate()
        self.updater.evaluate()
        self.assertEqual(len(shown), 1)
        key, title, body, buttons = shown[0][:4]
        self.assertIn("0.9.9", title)
        self.assertEqual([b[0] for b in buttons], ["download"])
        self.assertFalse(self.panel.download.isHidden())

    def test_a_download_under_way_is_not_started_twice(self):
        text, fingerprint = _signed()
        self.pair(fingerprint)
        self.session.store.set_state("update.manifest", text)
        self.updater.evaluate()
        threads = []

        class Thread:
            def __init__(self, target=None, daemon=None):
                threads.append(target)

            def start(self):
                pass
        with mock.patch("activitytrack_desktop.general.threading.Thread", Thread):
            self.panel.download.click()
            self.assertFalse(self.panel.download.isEnabled())
            self.updater.download()
            self.updater.download()
            self.assertEqual(len(threads), 1)
            # the download ends (here: with an error): the button is back and one may start again
            self.updater._file("", "boom")
            self.assertTrue(self.panel.download.isEnabled())
            self.panel.download.click()
            self.assertEqual(len(threads), 2)

    def test_a_package_manager_installation_is_not_offered_the_download(self):
        text, fingerprint = _signed(component="desktop-deb13")
        self.pair(fingerprint)
        self.session.store.set_state("update.manifest", text)
        shown = []
        self.notifier.show = lambda *a, **kw: shown.append(a)
        with mock.patch("activitytrack.manifest.from_package_manager", return_value=True), \
                mock.patch("activitytrack.updates.distro", return_value="deb13"):
            self.updater.evaluate()
            self.assertEqual(len(shown), 1)
            self.assertEqual(list(shown[0][3]), [])
            self.assertTrue(self.panel.download.isHidden())
            self.assertFalse(self.updater.status.downloadable)

    def test_a_manifest_not_of_the_pinned_key_says_nothing_but_the_reason(self):
        text, _fingerprint = _signed()
        self.pair("cd" * 32)
        self.session.store.set_state("update.manifest", text)
        shown = []
        self.notifier.show = lambda *a, **kw: shown.append(a)
        self.updater.evaluate()
        self.assertEqual(shown, [])
        self.assertIn("firmato", self.panel.result.text())

    def test_the_settings_and_the_policy(self):
        from activitytrack.policy import Policy
        core = self.updater.core
        self.assertEqual(core.settings()[0], True)
        self.panel.check.setChecked(False)
        self.assertEqual(core.settings()[0], False)
        self.updater.actions.work.policy = Policy({"format": "activitytrack-policy", "schema": 1,
                                                   "settings": {"updateCheck": {"value": True, "locked": True}}})
        self.assertEqual(core.settings()[0], True)
        self.panel.refresh()
        self.assertFalse(self.panel.check.isEnabled())


class WatchTest(unittest.TestCase):
    def test_another_interfaces_change_is_seen(self):
        from activitytrack.store import Store
        from activitytrack_desktop.service import SyncService
        with tempfile.TemporaryDirectory() as d:
            session = Session(d, use_keyring=False)
            service = SyncService(session)
            seen = []
            service.elsewhere.connect(lambda: seen.append(True))
            service._watch_data()
            service._watch_data()
            self.assertEqual(seen, [])
            # another connection (the cli in another process) commits
            other = Store(session.folder / "activitytrack.sqlite3")
            other.write("todo", "t1", {"title": "Dalla CLI"}, now_ms=1)
            service._watch_data()
            self.assertEqual(seen, [True])
            self.assertTrue(service._debounce.isActive())
            other.close()
            service.stop()
            session.store.close()


class TimeGridTest(unittest.TestCase):
    """The app's 5-minute grid: a drag or two clicks choose start and end (web issue #38)."""

    def tearDown(self):
        from activitytrack import formats
        formats.set_formats(formats.EU, formats.H24)

    def _centre(self, grid, i):
        from PyQt6.QtCore import QPoint
        row, col = i // 12 - grid.first, i % 12
        return QPoint(int(grid._x(col) + 8), int(row * 24 + 10))

    def test_drag_and_two_clicks(self):
        from datetime import date

        from PyQt6.QtCore import Qt
        from PyQt6.QtTest import QTest

        from activitytrack_desktop.timegrid_ui import TimeGridDialog

        d = TimeGridDialog(date(2026, 11, 2), 9 * 60, 10 * 60, ranged=True, busy=[(14 * 60, 15 * 60)])
        g = d.grid
        self.assertEqual(g.first, 7)
        left = Qt.MouseButton.LeftButton
        QTest.mousePress(g, left, pos=self._centre(g, 111))
        QTest.mouseMove(g, self._centre(g, 120))
        QTest.mouseMove(g, self._centre(g, 127))
        QTest.mouseRelease(g, left, pos=self._centre(g, 127))
        self.assertEqual(d.head.text(), "09:15 – 10:40 · 1:25")
        d._ok()
        self.assertEqual((d.start, d.end), (555, 640))
        # two clicks, the second after the window moved
        d = TimeGridDialog(date(2026, 11, 2), None, None, ranged=True)
        g = d.grid
        QTest.mouseClick(g, left, pos=self._centre(g, 8 * 12))
        self.assertTrue(d.hint.isVisibleTo(d))
        d._move(3)
        QTest.mouseClick(g, left, pos=self._centre(g, 18 * 12 + 5))
        d._ok()
        self.assertEqual((d.start, d.end), (8 * 60, 18 * 60 + 30))

    def test_a_single_time_and_twelve_hours(self):
        from datetime import date

        from PyQt6.QtCore import Qt
        from PyQt6.QtTest import QTest

        from activitytrack import formats
        from activitytrack_desktop.timegrid_ui import TimeGridDialog

        formats.set_formats(formats.US, formats.H12)
        d = TimeGridDialog(date(2026, 11, 2), 14 * 60 + 30)
        self.assertEqual(d.head.text(), "2:30 PM")
        QTest.mouseClick(d.grid, Qt.MouseButton.LeftButton, pos=self._centre(d.grid, 16 * 12 + 3))
        self.assertEqual(d.start, 16 * 60 + 15)
