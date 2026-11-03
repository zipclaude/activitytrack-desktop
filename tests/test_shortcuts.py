# SPDX-License-Identifier: GPL-3.0-or-later
"""
The commands without a window: their targets, the keys of each backend,
the settings, the choice of the backend, the commands themselves, the
portal against a fake one (with a session bus) and X11 (with a display
and python3-xlib).
"""

import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QEventLoop, QSettings, QTimer  # noqa: E402
from PyQt6.QtGui import QKeySequence  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

from activitytrack.pairing import Account  # noqa: E402
from activitytrack.policy import Policy  # noqa: E402
from activitytrack.session import Session  # noqa: E402
from activitytrack.work import (  # noqa: E402
    ACTIVE, CLOSED, PAUSE, STOP, SUSPEND, SUSPENDED, TO_COMPLETE, WORK, StartRequest, Work,
)
from activitytrack_desktop import hotkeys, shortcuts  # noqa: E402
from activitytrack_desktop.targets import pause_target, resume_target, stop_target  # noqa: E402

app = QApplication.instance() or QApplication([])
# the keys saved: in a folder of the tests, not the user's settings
app.setApplicationName("activitytrack-desktop-tests")
QSettings.setDefaultFormat(QSettings.Format.IniFormat)
QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, tempfile.mkdtemp())


def keys(text):
    return QKeySequence.fromString(text, QKeySequence.SequenceFormat.PortableText)


def wait(condition, timeout=5.0):
    end = time.monotonic() + timeout
    while not condition() and time.monotonic() < end:
        loop = QEventLoop()
        QTimer.singleShot(20, loop.quit)
        loop.exec()
    return condition()


class Clock:
    def __init__(self):
        self.ms = 1_800_000_000_000

    def __call__(self):
        return self.ms

    def tick(self, minutes=1):
        self.ms += minutes * 60_000


class TargetsTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.session = Session(self.dir.name, use_keyring=False)
        self.clock = Clock()
        self.work = Work(self.session.store, Policy(), clock=self.clock, zone="Europe/Rome")

    def tearDown(self):
        self.session.store.close()
        self.dir.cleanup()

    def start(self, name):
        self.clock.tick()
        return self.work.start(StartRequest(client="c1", activity=name))

    def command(self, uid, cmd):
        self.clock.tick()
        self.work.command(uid, cmd)

    def test_nothing_running(self):
        self.assertIsNone(pause_target(self.work))
        self.assertIsNone(resume_target(self.work))
        self.assertIsNone(stop_target(self.work))

    def test_one_activity(self):
        a = self.start("A")
        self.assertEqual(pause_target(self.work), a)
        self.assertIsNone(resume_target(self.work))
        self.assertEqual(stop_target(self.work), a)
        self.command(a, PAUSE)
        self.assertIsNone(pause_target(self.work))
        self.assertEqual(resume_target(self.work), a)
        self.assertEqual(stop_target(self.work), a)
        self.command(a, WORK)
        self.command(a, SUSPEND)
        self.assertIsNone(pause_target(self.work))
        self.assertEqual(resume_target(self.work), a)
        # suspended, the only one running: the one to stop
        self.assertEqual(stop_target(self.work), a)

    def test_several(self):
        a = self.start("A")
        self.command(a, PAUSE)
        # concurrent activities (the policy's default): A stays on pause
        b = self.start("B")
        self.assertEqual(self.work.entry(a)["mode"], PAUSE)
        self.assertEqual(pause_target(self.work), b)
        # the one on pause first, even with a newer one suspended
        self.command(b, SUSPEND)
        self.assertEqual(resume_target(self.work), a)
        # two active: a choice, the most recent first; the big card's wins
        c = self.start("C")
        self.assertEqual(stop_target(self.work), [c, a])
        self.assertEqual(stop_target(self.work, focused_uid=a), a)
        self.assertEqual(stop_target(self.work, focused_uid="gone"), [c, a])
        # the most recent at work, among several
        self.command(a, WORK)
        self.assertEqual(pause_target(self.work), a)
        # two on pause: a choice
        self.command(a, PAUSE)
        self.command(c, PAUSE)
        self.assertEqual(resume_target(self.work), [c, a])
        # none on pause: the latest suspended
        self.command(a, STOP)
        self.command(c, STOP)
        self.assertEqual(resume_target(self.work), b)
        self.assertEqual(self.work.entry(b)["status"], SUSPENDED)
        d = self.start("D")
        self.command(d, SUSPEND)
        self.assertEqual(resume_target(self.work), d)
        # nothing active: a choice among the suspended
        self.assertEqual(stop_target(self.work), [d, b])


class KeysTest(unittest.TestCase):
    def test_windows(self):
        self.assertEqual(hotkeys.windows_keys(keys("Ctrl+Alt+A")), (0x2 | 0x1, 0x41))
        self.assertEqual(hotkeys.windows_keys(keys("Ctrl+Shift+F5")), (0x2 | 0x4, 0x74))
        self.assertEqual(hotkeys.windows_keys(keys("Meta+Space")), (0x8, 0x20))
        self.assertEqual(hotkeys.windows_keys(keys("Alt+7")), (0x1, 0x37))
        self.assertEqual(hotkeys.windows_keys(keys("Ctrl+PgDown")), (0x2, 0x22))
        self.assertEqual(hotkeys.windows_keys(keys("F9")), (0, 0x78))

    def test_x11(self):
        self.assertEqual(hotkeys.x11_keys(keys("Ctrl+Alt+A")), (0x61, 4 | 8))
        self.assertEqual(hotkeys.x11_keys(keys("Meta+Shift+Return")), (0xFF0D, 64 | 1))
        self.assertEqual(hotkeys.x11_keys(keys("Ctrl+Alt+P")), (ord("p"), 12))
        self.assertEqual(hotkeys.x11_keys(keys("Alt+F12")), (0xFFC9, 8))

    def test_portal(self):
        self.assertEqual(hotkeys.portal_trigger(keys("Ctrl+Alt+A")), "CTRL+ALT+a")
        self.assertEqual(hotkeys.portal_trigger(keys("Shift+Meta+F12")), "SHIFT+LOGO+F12")
        self.assertEqual(hotkeys.portal_trigger(keys("Ctrl+Alt+Del")), "CTRL+ALT+Delete")

    def test_what_no_backend_takes(self):
        for text in ("", "A", "Shift+A", "Ctrl+A, Ctrl+B", "Ctrl+Alt+?", "Ctrl+Alt+Volume Up"):
            with self.subTest(text):
                self.assertIsNone(hotkeys.parse(keys(text)))
                self.assertIsNone(hotkeys.windows_keys(keys(text)))
                self.assertIsNone(hotkeys.x11_keys(keys(text)))
                self.assertIsNone(hotkeys.portal_trigger(keys(text)))


class SettingsTest(unittest.TestCase):
    def tearDown(self):
        shortcuts.reset()

    def test_defaults_saving_and_reset(self):
        shortcuts.reset()
        got = {a: (on, s.toString()) for a, (on, s) in shortcuts.saved().items()}
        self.assertEqual(got, {"start": (True, "Ctrl+Alt+A"), "pause": (True, "Ctrl+Alt+P"),
                               "stop": (True, "Ctrl+Alt+S")})
        shortcuts.save("pause", False, keys("Ctrl+Shift+F8"))
        shortcuts.save("stop", True, QKeySequence())
        on, seq = shortcuts.saved()["pause"]
        self.assertFalse(on)
        self.assertEqual(seq.toString(QKeySequence.SequenceFormat.PortableText), "Ctrl+Shift+F8")
        self.assertTrue(shortcuts.saved()["stop"][1].isEmpty())
        shortcuts.reset()
        self.assertEqual(shortcuts.saved()["pause"][1].toString(), "Ctrl+Alt+P")

    def test_the_settings_group(self):
        g = shortcuts.GlobalShortcuts(backends={}, platform="linux", qpa="offscreen", wayland_session=False)
        box = shortcuts.ShortcutsBox(g)
        self.assertEqual(box.edits["start"].keySequence().toString(), "Ctrl+Alt+A")
        self.assertIn("Non disponibili", box.state.text())
        box.checks["stop"].setChecked(False)
        self.assertFalse(shortcuts.saved()["stop"][0])
        self.assertFalse(box.edits["stop"].isEnabled())
        box.edits["pause"].setKeySequence(keys("Ctrl+Alt+F2"))
        box.edits["pause"].editingFinished.emit()
        self.assertEqual(shortcuts.saved()["pause"][1].toString(), "Ctrl+Alt+F2")
        box.reset.click()
        self.assertTrue(box.checks["stop"].isChecked())
        self.assertEqual(box.edits["pause"].keySequence().toString(), "Ctrl+Alt+P")


class FakeBackend(hotkeys.Backend):
    why = None

    def __init__(self, parent=None):
        super().__init__(parent)
        self.bound = []

    def title(self):
        return "Fake"

    def open(self):
        return self.why

    def bind(self, bindings):
        self.bound.append({a: s.toString() for a, s in bindings.items()})
        self.errors = {"stop": "già usata da un altro programma"} if "stop" in bindings else {}
        self.changed.emit()


class Refused(FakeBackend):
    why = "manca python3-xlib"


class SelectionTest(unittest.TestCase):
    def tearDown(self):
        shortcuts.reset()

    def test_the_order(self):
        self.assertEqual(hotkeys.order("win32", "windows", False), ["windows"])
        self.assertEqual(hotkeys.order("linux", "xcb", False), ["x11", "portal"])
        # X11 programs on Wayland: a grab would see only them
        self.assertEqual(hotkeys.order("linux", "xcb", True), ["portal"])
        self.assertEqual(hotkeys.order("linux", "wayland", True), ["portal"])
        self.assertEqual(hotkeys.order("linux", "wayland-egl", False), ["portal"])
        self.assertEqual(hotkeys.order("linux", "offscreen", False), [])
        self.assertEqual(hotkeys.order("darwin", "cocoa", False), [])

    def test_the_first_that_opens(self):
        backend, reasons = hotkeys.choose("linux", "xcb", False, {"x11": Refused, "portal": FakeBackend})
        self.assertIsInstance(backend, FakeBackend)
        self.assertEqual(reasons, [("x11", "manca python3-xlib")])
        backend, reasons = hotkeys.choose("linux", "xcb", False, {"x11": Refused, "portal": Refused})
        self.assertIsNone(backend)
        g = shortcuts.GlobalShortcuts(backends={"x11": Refused}, platform="linux", qpa="xcb", wayland_session=False)
        self.assertIn("manca python3-xlib", g.status())
        self.assertIn("Non disponibili", g.status())

    def test_the_keys_to_the_backend(self):
        shortcuts.reset()
        shortcuts.save("start", True, keys("Shift+A"))
        g = shortcuts.GlobalShortcuts(backends={"portal": FakeBackend}, platform="linux", qpa="wayland")
        got = []
        g.triggered.connect(got.append)
        g.apply()
        self.assertEqual(g.backend.bound, [{"pause": "Ctrl+Alt+P", "stop": "Ctrl+Alt+S"}])
        status = g.status()
        self.assertIn("Attive tramite Fake", status)
        self.assertIn("Stop dell'attività: non attiva, già usata da un altro programma", status)
        self.assertIn("Nuova attività: combinazione non valida", status)
        # unchanged: not bound again (the portal would ask the user)
        g.apply()
        self.assertEqual(len(g.backend.bound), 1)
        shortcuts.save("stop", False, keys("Ctrl+Alt+S"))
        g.apply()
        self.assertEqual(g.backend.bound[-1], {"pause": "Ctrl+Alt+P"})
        # pressed: in the GUI thread, once for a key held down
        g.backend.activated.emit("pause")
        g.backend.activated.emit("pause")
        self.assertEqual(got, [])
        self.assertTrue(wait(lambda: got))
        wait(lambda: False, 0.1)
        self.assertEqual(got, ["pause"])


class FakeWindow:
    def __init__(self):
        self.shown = 0

    def show_up(self):
        self.shown += 1


class CommandsTest(unittest.TestCase):
    def setUp(self):
        from activitytrack_desktop.home import Actions
        from activitytrack_desktop.notify import Notifier
        self.dir = tempfile.TemporaryDirectory()
        self.session = Session(self.dir.name, use_keyring=False)
        a = Account("https://at.example.com", None, "d1", "anna", "Anna Rossi", "user", "Infra")
        self.session.store.set_state("account", a.to_json())
        self.session.vault.put("d1", "tok")
        self.actions = Actions(self.session)
        self.window = FakeWindow()
        self.notifier = Notifier(use_dbus=False)
        self.told = []
        self.notifier.show = lambda key, title, body, *a, **k: self.told.append(body)
        self.commands = shortcuts.Commands(self.actions, self.window, self.notifier)
        self.changed = []
        self.actions.changed.connect(lambda: self.changed.append(1))

    def tearDown(self):
        self.session.store.close()
        self.dir.cleanup()

    def entry(self, uid):
        return self.actions.work.entry(uid)

    def test_pause_resume_and_stop(self):
        uid = self.actions.work.start(StartRequest(client="c1", activity="Rete"))
        self.commands.run("pause")
        self.assertEqual((self.entry(uid)["status"], self.entry(uid)["mode"]), (ACTIVE, PAUSE))
        self.assertIn("In pausa:", self.told[-1])
        self.assertTrue(self.changed)
        self.commands.run("pause")
        self.assertEqual(self.entry(uid)["mode"], WORK)
        self.assertIn("Ripresa:", self.told[-1])
        # client and description: closed at once, no sheet
        self.commands.run("stop")
        self.assertEqual(self.entry(uid)["status"], CLOSED)
        self.assertIn("Fermata:", self.told[-1])
        self.commands.run("pause")
        self.assertEqual(self.told[-1], "Nessuna attività da mettere in pausa o da riprendere.")
        self.commands.run("stop")
        self.assertEqual(self.told[-1], "Nessuna attività in corso.")

    def test_the_stop_sheet_in_front(self):
        uid = self.actions.work.start(StartRequest(client="c1"))
        sheets = []

        class Sheet:
            def __init__(self, work, entry_uid, parent=None):
                sheets.append(entry_uid)

            def setWindowFlag(self, *a):
                pass

            show = raise_ = activateWindow = setWindowFlag

            def exec(self):
                return 0
        with mock.patch("activitytrack_desktop.forms.StopDialog", Sheet):
            self.commands.run("stop")
        self.assertEqual(sheets, [uid])
        self.assertEqual(self.entry(uid)["status"], TO_COMPLETE)

    def test_a_choice(self):
        a = self.actions.work.start(StartRequest(client="c1", activity="A"))
        b = self.actions.work.start(StartRequest(client="c1", activity="B"))
        asked = []

        def choose(work, uids, title):
            asked.append(uids)
            return a
        with mock.patch.object(shortcuts, "choose", choose):
            self.commands.run("stop")
        self.assertEqual(sorted(asked[0]), sorted([a, b]))
        self.assertEqual(self.entry(a)["status"], CLOSED)
        self.assertEqual(self.entry(b)["status"], ACTIVE)

    def test_the_chooser(self):
        a = self.actions.work.start(StartRequest(client="c1", activity="A"))
        b = self.actions.work.start(StartRequest(client="c1", activity="B"))
        d = shortcuts.ChooseDialog(self.actions.work, [b, a], "Quale?")
        self.assertEqual(d.list.count(), 2)
        self.assertEqual(d.chosen(), b)
        d.list.setCurrentRow(1)
        self.assertEqual(d.chosen(), a)

    def test_start_and_show(self):
        with mock.patch.object(self.actions, "new_entry") as new_entry:
            self.commands.run("start")
        new_entry.assert_called_once_with()
        self.commands.run("show")
        self.assertEqual(self.window.shown, 1)
        # not paired: the window, which says what to do
        self.session.store.set_state("account", None)
        self.commands.run("pause")
        self.assertEqual(self.window.shown, 2)

    def test_the_sockets_lines(self):
        ran = []
        with mock.patch.object(self.commands, "run", lambda c, t=None: ran.append((c, t))):
            for line in ("pause\n", "start tok-1\n", "show\n", "rm -rf\n", "\n"):
                self.commands.received(line)
            self.assertTrue(wait(lambda: len(ran) == 5))
        self.assertEqual(ran, [("pause", None), ("start", "tok-1"), ("show", None), ("show", "-rf"),
                               ("show", None)])


@unittest.skipUnless(os.environ.get("DBUS_SESSION_BUS_ADDRESS") and sys.platform.startswith("linux"),
                     "no session bus")
class PortalTest(unittest.TestCase):
    def setUp(self):
        shortcuts.reset()
        self.dir = tempfile.TemporaryDirectory()
        self.log = Path(self.dir.name) / "log"
        env = dict(os.environ, PYTHONPATH=os.pathsep.join(sys.path))
        self.server = subprocess.Popen([sys.executable, str(Path(__file__).with_name("fake_portal.py")),
                                        str(self.log)], stdout=subprocess.PIPE, text=True, env=env)
        self.assertEqual(self.server.stdout.readline().strip(), "ready")

    def tearDown(self):
        self.server.terminate()
        self.server.wait(5)
        self.server.stdout.close()
        self.dir.cleanup()
        shortcuts.reset()

    def calls(self):
        return [json.loads(x) for x in self.log.read_text().splitlines()] if self.log.exists() else []

    def test_bound_and_pressed(self):
        g = shortcuts.GlobalShortcuts(backends={"portal": hotkeys.PortalBackend}, platform="linux", qpa="wayland")
        self.assertIsInstance(g.backend, hotkeys.PortalBackend, g.reasons)
        got = []
        g.triggered.connect(got.append)
        g.apply()
        self.assertIn("In attesa della conferma", g.status())
        self.assertTrue(wait(lambda: got))
        self.assertEqual(got, ["pause"])
        calls = self.calls()
        self.assertEqual([c["call"] for c in calls], ["Register", "CreateSession", "BindShortcuts"])
        self.assertEqual(calls[0]["app_id"], "activitytrack-desktop")
        self.assertEqual(calls[2]["shortcuts"], {
            "pause": {"description": "Pausa o ripresa dell'attività", "preferred_trigger": "CTRL+ALT+p"},
            "start": {"description": "Nuova attività", "preferred_trigger": "CTRL+ALT+a"},
            "stop": {"description": "Stop dell'attività", "preferred_trigger": "CTRL+ALT+s"}})
        status = g.status()
        self.assertIn("Attive tramite portale del desktop.", status)
        self.assertIn("Nuova attività: CTRL+ALT+a", status)
        # other keys: the session closed, a new one bound
        shortcuts.save("start", False, keys("Ctrl+Alt+A"))
        with mock.patch.object(shortcuts, "REPEAT_S", 0):
            g.apply()
            self.assertTrue(wait(lambda: len(got) == 2))
        calls = self.calls()
        self.assertEqual([c["call"] for c in calls[3:]], ["Close", "CreateSession", "BindShortcuts"])
        self.assertEqual(calls[3]["session"], calls[2]["session"])
        self.assertEqual(sorted(calls[5]["shortcuts"]), ["pause", "stop"])
        g.close()

    def test_without_the_portal(self):
        self.server.terminate()
        self.server.wait(5)
        backend, reasons = hotkeys.choose("linux", "wayland", True, {"portal": hotkeys.PortalBackend})
        self.assertIsNone(backend)
        self.assertEqual(reasons, [("portal", "il desktop non offre il portale GlobalShortcuts")])


def _xlib():
    try:
        import Xlib.display  # noqa: F401
        return True
    except ImportError:
        return False


@unittest.skipUnless(os.environ.get("DISPLAY") and _xlib(), "no X display or python3-xlib")
class X11Test(unittest.TestCase):
    def press(self, *names):
        from Xlib import X, XK, display
        from Xlib.ext import xtest
        d = display.Display()
        codes = [d.keysym_to_keycode(XK.string_to_keysym(n)) for n in names]
        for c in codes:
            xtest.fake_input(d, X.KeyPress, c)
        for c in reversed(codes):
            xtest.fake_input(d, X.KeyRelease, c)
        d.sync()
        d.close()

    def test_grabbed_and_pressed(self):
        b = hotkeys.X11Backend()
        self.assertIsNone(b.open())
        got = []
        b.activated.connect(got.append)
        b.bind({"start": keys("Ctrl+Alt+A"), "stop": keys("Ctrl+Alt+S")})
        self.assertEqual(b.errors, {})
        self.press("Control_L", "Alt_L", "a")
        self.assertTrue(wait(lambda: got))
        self.assertEqual(got, ["start"])
        # NumLock on: the same shortcut
        self.press("Num_Lock")
        self.press("Control_L", "Alt_L", "s")
        self.assertTrue(wait(lambda: len(got) == 2))
        self.press("Num_Lock")
        self.assertEqual(got[1], "stop")
        # another program has the key
        other = hotkeys.X11Backend()
        self.assertIsNone(other.open())
        other.bind({"start": keys("Ctrl+Alt+A"), "pause": keys("Ctrl+Alt+P")})
        self.assertEqual(other.errors, {"start": "già usata da un altro programma"})
        # released by the first one: free for the other
        b.close()
        other.bind({"start": keys("Ctrl+Alt+A")})
        self.assertEqual(other.errors, {})
        other.close()
