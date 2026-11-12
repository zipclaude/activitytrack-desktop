# SPDX-License-Identifier: GPL-3.0-or-later
"""The start: the single instance's socket and quitting without a tray (offscreen: QT_QPA_PLATFORM=offscreen)."""

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from activitytrack_desktop import main


@unittest.skipIf(sys.platform == "win32", "the Unix socket")
class SocketNameTest(unittest.TestCase):
    def test_in_the_users_runtime_folder(self):
        with tempfile.TemporaryDirectory() as runtime, mock.patch.dict(os.environ, {"XDG_RUNTIME_DIR": runtime}):
            name = main._socket_name(Path("/data/a"))
            self.assertEqual(os.path.dirname(name), runtime)
            self.assertTrue(os.path.basename(name).startswith("activitytrack-desktop-"))
            # one per data folder, the same at every start
            self.assertNotEqual(name, main._socket_name(Path("/data/b")))
            self.assertEqual(name, main._socket_name(Path("/data/a")))

    def test_without_a_runtime_folder_the_uid_in_the_name(self):
        for runtime in (None, "", "relative", "/nonexistent-runtime-dir"):
            env = {k: v for k, v in os.environ.items() if k != "XDG_RUNTIME_DIR"}
            if runtime is not None:
                env["XDG_RUNTIME_DIR"] = runtime
            with mock.patch.dict(os.environ, env, clear=True):
                name = main._socket_name(Path("/data/a"))
            self.assertNotIn("/", name)
            self.assertTrue(name.endswith(f"-{os.getuid()}"), name)

    def test_windows_named_pipes_are_per_session(self):
        with mock.patch.object(main.sys, "platform", "win32"):
            name = main._socket_name(Path("/data/a"))
        self.assertRegex(name, r"^activitytrack-desktop-[0-9a-f]{12}$")


# main() in its own process: it makes the QApplication and runs its loop
WITHOUT_TRAY = """
import sys
from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication
import activitytrack_desktop.general as G
import activitytrack_desktop.main as M
import activitytrack_desktop.service as S
M.QSystemTrayIcon.isSystemTrayAvailable = staticmethod(lambda: False)
M.QMessageBox.information = staticmethod(lambda *a, **k: None)
G.first_start = lambda: None
S.SyncService.sync = lambda self, full=False: None
stops = []
stop = S.SyncService.stop
S.SyncService.stop = lambda self: stops.append(1) or stop(self)
start = S.SyncService.start


def close():
    for w in QApplication.topLevelWidgets():
        if w.isVisible():
            w.close()


def started(self):
    start(self)
    QTimer.singleShot(200, close)
    # a quit that does not come
    QTimer.singleShot(10_000, lambda: QApplication.exit(9))
S.SyncService.start = started
code = M.main(["--data", sys.argv[1]])
print("stops", len(stops), flush=True)
sys.exit(code)
"""


class WithoutTrayTest(unittest.TestCase):
    def test_closing_the_window_quits_once(self):
        with tempfile.TemporaryDirectory() as d:
            env = dict(os.environ, QT_QPA_PLATFORM="offscreen", XDG_CONFIG_HOME=d, PYTHONPATH=os.pathsep.join(
                [str(Path(main.__file__).parent.parent), *sys.path]))
            r = subprocess.run([sys.executable, "-c", WITHOUT_TRAY, str(Path(d) / "data")], env=env,
                               capture_output=True, text=True, timeout=60)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("stops 1", r.stdout)
            self.assertNotIn("Traceback", r.stderr)
            self.assertFalse((Path(d) / "data" / "errors.log").exists())


# an instance whose commands are only written: they reach it through the single instance's socket
INSTANCE = """
import sys
from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication
import activitytrack_desktop.general as G
import activitytrack_desktop.main as M
import activitytrack_desktop.service as S
import activitytrack_desktop.shortcuts as SC
M.QSystemTrayIcon.isSystemTrayAvailable = staticmethod(lambda: False)
M.QMessageBox.information = staticmethod(lambda *a, **k: None)
G.first_start = lambda: None
S.SyncService.sync = lambda self, full=False: None
expected = int(sys.argv[2])
ran = []


def run(self, command, token=None):
    ran.append(command)
    print("ran", command, token, flush=True)
    if len(ran) == expected:
        QApplication.exit(0)
SC.Commands.run = run
start = S.SyncService.start


def started(self):
    start(self)
    print("ready", flush=True)
    QTimer.singleShot(30_000, lambda: QApplication.exit(9))
S.SyncService.start = started
sys.exit(M.main(["--data", sys.argv[1], *sys.argv[3:]]))
"""

SECOND = "import sys, activitytrack_desktop.main as M; sys.exit(M.main(['--data', sys.argv[1], sys.argv[2]]))"


class CommandLineTest(unittest.TestCase):
    def env(self, d, **more):
        return dict(os.environ, QT_QPA_PLATFORM="offscreen", XDG_CONFIG_HOME=d, PYTHONPATH=os.pathsep.join(
            [str(Path(main.__file__).parent.parent), *sys.path]), **more)

    def test_the_commands_reach_the_running_instance(self):
        with tempfile.TemporaryDirectory() as d:
            data = str(Path(d) / "data")
            env = {k: v for k, v in self.env(d).items() if k != "XDG_ACTIVATION_TOKEN"}
            first = subprocess.Popen([sys.executable, "-c", INSTANCE, data, "3"], env=env, stdout=subprocess.PIPE,
                                     stderr=subprocess.PIPE, text=True)
            try:
                self.assertEqual(first.stdout.readline().strip(), "ready")
                for option, more in (("--pause", {"XDG_ACTIVATION_TOKEN": "tok-1"}), ("--stop", {}),
                                     ("--start", {})):
                    r = subprocess.run([sys.executable, "-c", SECOND, data, option], env=dict(env, **more),
                                       capture_output=True, text=True, timeout=60)
                    self.assertEqual(r.returncode, 0, r.stderr)
                out, err = first.communicate(timeout=60)
            finally:
                if first.poll() is None:
                    first.kill()
                    first.communicate()
            self.assertEqual(first.returncode, 0, err)
            self.assertEqual(out.split("\n")[:3], ["ran pause tok-1", "ran stop None", "ran start None"])
            self.assertNotIn("Traceback", err)

    def test_without_an_instance_it_starts_and_runs_the_command(self):
        with tempfile.TemporaryDirectory() as d:
            r = subprocess.run([sys.executable, "-c", INSTANCE, str(Path(d) / "data"), "1", "--stop"],
                               env=self.env(d), capture_output=True, text=True, timeout=60)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(r.stdout.split("\n")[:2], ["ready", "ran stop None"])
            self.assertNotIn("Traceback", r.stderr)


# the language is set before any module that translates its texts when imported (the library's texts, the Home…)
LANGUAGE_FIRST = """
import sys
from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication
import activitytrack_desktop.main as M
import activitytrack_desktop.service as S
M.QSystemTrayIcon.isSystemTrayAvailable = staticmethod(lambda: False)
M.QMessageBox.information = staticmethod(lambda *a, **k: None)
S.SyncService.sync = lambda self, full=False: None
language = M._language


def before(app, forced=None):
    print("early", sorted(m for m in sys.modules if m in ("activitytrack.texts", "activitytrack_desktop.home")),
          flush=True)
    return language(app, forced)
M._language = before
start = S.SyncService.start


def started(self):
    start(self)
    from activitytrack import texts
    print("kind", texts.KINDS["WORK"], flush=True)
    QTimer.singleShot(0, QApplication.quit)
S.SyncService.start = started
sys.exit(M.main(["--data", sys.argv[1]]))
"""


class LanguageTest(unittest.TestCase):
    def test_the_texts_are_translated_in_the_language_of_the_system(self):
        with tempfile.TemporaryDirectory() as d:
            env = dict(os.environ, HOME=d, QT_QPA_PLATFORM="offscreen", XDG_CONFIG_HOME=d, LC_ALL="en_US.UTF-8",
                       LANG="en_US.UTF-8", LANGUAGE="en", PYTHONPATH=os.pathsep.join(
                           [str(Path(main.__file__).parent.parent), *sys.path]))
            r = subprocess.run([sys.executable, "-c", LANGUAGE_FIRST, str(Path(d) / "data")], env=env,
                               capture_output=True, text=True, timeout=60)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("early []", r.stdout)
            kind = [line for line in r.stdout.splitlines() if line.startswith("kind ")]
            self.assertEqual(kind, ["kind Work"], r.stdout)
