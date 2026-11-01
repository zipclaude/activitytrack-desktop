# SPDX-License-Identifier: GPL-3.0-or-later
"""Starts ActivityTrack Desktop: one instance per user, living in the tray."""

import argparse
import hashlib
import sys
from pathlib import Path

from PySide6.QtCore import QLibraryInfo, QLocale, QStandardPaths, QTranslator
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication, QMessageBox, QSystemTrayIcon

from . import __version__
from .i18n import _

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


def main(argv=None):
    parser = argparse.ArgumentParser(prog=APP_ID)
    parser.add_argument("--version", action="version", version=f"ActivityTrack Desktop {__version__}")
    parser.add_argument("--hidden", action="store_true", help="start in the tray only (autostart)")
    parser.add_argument("--data", help="data folder (default: the user's application data)")
    parser.add_argument("--dev", action="store_true", help="development: allow http:// servers")
    args, qt_args = parser.parse_known_args(argv if argv is not None else sys.argv[1:])

    app = QApplication([sys.argv[0], *qt_args])
    app.setApplicationName(APP_ID)
    app.setApplicationDisplayName("ActivityTrack")
    app.setApplicationVersion(__version__)
    app.setDesktopFileName(APP_ID)
    app.setQuitOnLastWindowClosed(False)
    # Qt's own texts (Annulla, Sì…) in the system's language
    qt_texts = QTranslator(app)
    if qt_texts.load(QLocale(), "qtbase", "_", QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)):
        app.installTranslator(qt_texts)

    folder = Path(args.data) if args.data else Path(
        QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation))
    # one instance per data folder: a local socket on Linux, a named pipe on Windows
    # (hash() changes at every start: a stable digest instead)
    name = f"{APP_ID}-{hashlib.sha1(str(folder.resolve()).encode()).hexdigest()[:12]}"
    if _already_running(name):
        return 0
    QLocalServer.removeServer(name)
    server = QLocalServer()
    server.listen(name)

    from .service import SyncService
    from .session import Session
    from .ui import MainWindow, Tray

    session = Session(folder, allow_http=args.dev)
    service = SyncService(session)
    window = MainWindow(session, service)

    def quit_app():
        service.stop()
        app.quit()

    def on_connection():
        c = server.nextPendingConnection()
        c.readyRead.connect(window.show_up)

    server.newConnection.connect(on_connection)

    if QSystemTrayIcon.isSystemTrayAvailable():
        tray = Tray(session, service, window, quit_app)
        tray.show()
    else:
        tray = None
        QMessageBox.information(None, "ActivityTrack", _(
            "Il desktop non ha un'area di notifica: ActivityTrack resta aperto in una finestra."))
        window.closeEvent = lambda e: (e.accept(), quit_app())
    if not args.hidden or tray is None or session.account is None:
        window.show_up()
    service.start()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
