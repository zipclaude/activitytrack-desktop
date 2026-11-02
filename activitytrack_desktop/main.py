# SPDX-License-Identifier: GPL-3.0-or-later
"""Starts ActivityTrack Desktop: one instance per user, living in the tray."""

import argparse
import hashlib
import sys
import traceback
from pathlib import Path

from PyQt6.QtCore import QLibraryInfo, QLocale, QTranslator
from PyQt6.QtNetwork import QLocalServer, QLocalSocket
from PyQt6.QtWidgets import QApplication, QMessageBox, QSystemTrayIcon

import activitytrack
from activitytrack.i18n import _, add_catalogs, set_language
from activitytrack.paths import data_dir

from . import __version__

APP_ID = "activitytrack-desktop"


def _already_running(name):
    """Asks a running instance to show its window; True when there is one."""
    s = QLocalSocket()
    s.connectToServer(name)
    if s.waitForConnected(500):
        s.write(b"show\n")
        s.flush()
        s.waitForBytesWritten(500)
        s.disconnectFromServer()
        return True
    return False


def _log_errors(folder):
    """
    PyQt aborts the process on an exception escaping a slot: a tray
    application must outlive a bug, so it is written to errors.log instead.
    """
    log = folder / "errors.log"

    def hook(kind, value, tb):
        text = "".join(traceback.format_exception(kind, value, tb))
        sys.stderr.write(text)
        try:
            folder.mkdir(parents=True, exist_ok=True)
            with open(log, "a", encoding="utf-8") as f:
                f.write(text + "\n")
        except OSError:
            pass
    sys.excepthook = hook


def _language(app, forced=None):
    """
    The interface's language (the policy's, else the system's), set before
    the interface's modules are imported; Qt's own texts (Annulla, Sì…) and
    the dates follow it.
    """
    # the desktop's own texts, with the library's
    add_catalogs(Path(__file__).with_name("locale"))
    lang = set_language(forced or QLocale.system().name())
    locale = QLocale(lang) if lang != QLocale.system().name()[:2] else QLocale.system()
    QLocale.setDefault(locale)
    qt_texts = QTranslator(app)
    if qt_texts.load(locale, "qtbase", "_", QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)):
        app.installTranslator(qt_texts)
    return lang


def _selftest(app, out):
    import tempfile

    # the catalogs too: the system's language, as at a normal start
    _language(app)

    from .home import Actions
    from .notify import Notifier
    from .reminder_ui import Reminders
    from .service import SyncService
    from activitytrack.session import Session
    from .ui import MainWindow, Tray

    try:
        with tempfile.TemporaryDirectory() as d:
            session = Session(d, use_keyring=False)
            service = SyncService(session)
            actions = Actions(session)
            notifier = Notifier(use_dbus=False)
            window = MainWindow(session, service, actions, notifier)
            Tray(session, service, window, lambda: None, actions)
            Reminders(actions, notifier, window.show_up).arm()
            window.quitting = True
            service.stop()
            session.store.close()
        text = f"ok {__version__} zone={actions.work.zone}\n"
        code = 0
    except Exception:
        text = traceback.format_exc()
        code = 1
    with open(out, "w", encoding="utf-8") as f:
        f.write(text)
    return code


def main(argv=None):
    parser = argparse.ArgumentParser(prog=APP_ID)
    parser.add_argument("--version", action="version", version=f"ActivityTrack Desktop {__version__}")
    parser.add_argument("--hidden", action="store_true", help="start in the tray only (autostart)")
    parser.add_argument("--data", help="data folder (default: the user's application data)")
    parser.add_argument("--dev", action="store_true", help="development: allow http:// servers")
    # the packages' check: everything built on an empty folder, the outcome in a file (no console on Windows)
    parser.add_argument("--selftest", metavar="FILE", help=argparse.SUPPRESS)
    args, qt_args = parser.parse_known_args(argv if argv is not None else sys.argv[1:])

    app = QApplication([sys.argv[0], *qt_args])
    app.setApplicationName(APP_ID)
    app.setApplicationDisplayName("ActivityTrack")
    app.setApplicationVersion(__version__)
    activitytrack.set_client("ActivityTrackDesktop", __version__)
    app.setDesktopFileName(APP_ID)
    app.setQuitOnLastWindowClosed(False)

    if args.selftest:
        return _selftest(app, args.selftest)

    # the folder of every interface (desktop, cli, tui): one application, one device
    folder = Path(args.data) if args.data else data_dir()
    _log_errors(folder)
    # one instance per data folder: a local socket on Linux, a named pipe on Windows
    # (hash() changes at every start: a stable digest instead)
    name = f"{APP_ID}-{hashlib.sha1(str(folder.resolve()).encode()).hexdigest()[:12]}"
    if _already_running(name):
        return 0
    QLocalServer.removeServer(name)
    server = QLocalServer()
    server.listen(name)

    from activitytrack.policy import stored
    from activitytrack.session import Session

    session = Session(folder, allow_http=args.dev)
    _language(app, stored(session.store).language)
    from activitytrack import formats
    formats.load(session.store)

    from .service import SyncService
    from .home import Actions
    from .ui import MainWindow, Tray

    service = SyncService(session)
    actions = Actions(session)
    # a command here goes out in a few seconds; what the sync brought shows at once
    actions.changed.connect(service.changed_here)
    service.changed.connect(lambda *_a: (actions.refresh_policy(), actions.changed_elsewhere()))
    service.elsewhere.connect(actions.changed_elsewhere)
    from .notify import Notifier
    from .reminder_ui import Reminders

    notifier = Notifier()
    window = MainWindow(session, service, actions, notifier)

    def quit_app():
        window.quitting = True
        service.stop()
        app.quit()

    # logging out of the desktop session closes the windows: the window must not refuse
    app.commitDataRequest.connect(lambda _manager: setattr(window, "quitting", True))

    def on_connection():
        c = server.nextPendingConnection()
        c.readyRead.connect(window.show_up)

    server.newConnection.connect(on_connection)

    if QSystemTrayIcon.isSystemTrayAvailable():
        tray = Tray(session, service, window, quit_app, actions)
        tray.show()
        # without the notification service the tray's messages bring the reminders
        notifier.attach_tray(tray)
    else:
        tray = None
        QMessageBox.information(None, "ActivityTrack", _(
            "Il desktop non ha un'area di notifica: ActivityTrack resta aperto in una finestra."))
        window.closeEvent = lambda e: (e.accept(), quit_app() if not window.quitting else None)
    if not args.hidden or tray is None or session.account is None:
        window.show_up()
    from .general import first_start
    first_start()
    reminders = Reminders(actions, notifier, window.show_up)
    reminders.arm()
    service.start()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
