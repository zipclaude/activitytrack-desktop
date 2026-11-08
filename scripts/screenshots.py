# SPDX-License-Identifier: GPL-3.0-or-later
"""
The manual's screenshots (../activitytrack-doc/manual/desktop/img), from sample data in a
temporary folder: no server, no personal data. --dark takes the dark
theme's (home-dark.png…); SCREENSHOTS_OUT another folder.

    QT_QPA_PLATFORM=offscreen python3 scripts/screenshots.py [--dark]
"""

import os
import sys
import tempfile
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QLibraryInfo, QLocale, QSettings, Qt, QTimer, QTranslator  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

# the manuals live in the documentation repository, cloned next to this one
OUT = Path(os.environ.get("SCREENSHOTS_OUT") or ROOT.parent / "activitytrack-doc" / "manual" / "desktop" / "img")
MIN = 60_000


def sample(store, now):
    rev = iter(range(1, 1000))

    def put(type_, uid, fields, central=True):
        store.pulled({"type": type_, "uid": uid, "rev": next(rev), "central": central, "fields": fields})
    for uid, name, company in (("lib", "Biblioteca civica", "muni"), ("tax", "Ufficio Tributi", "muni"),
                               ("hotel", "Hotel Belvedere", "acme"), ("wine", "Cantina Monte Verde", "acme")):
        put("client", uid, {"name": name, "companyUid": company, "archived": False})
    put("role", "sys", {"name": "Sistemista", "archived": False})
    put("company", "acme", {"name": "Alfa Sistemi", "archived": False, "color": 0x3D7BEA})
    put("company", "muni", {"name": "Comune di Valdora", "archived": False, "color": 0x2E9D4E})
    put("tag", "urg", {"name": "urgente", "archived": False, "color": 0xD64545})
    put("tag", "net", {"name": "rete", "archived": False, "color": 0x00A3A3})
    put("preset", "p1", {"text": "Assistenza remota", "position": 1})
    for dow in range(1, 6):
        put("workSchedule", f"w{dow}", {"dayOfWeek": dow, "startMin": 540, "endMin": 1080})
    today = date.fromtimestamp(now / 1000)
    put("todo", "t1", {"title": "Rinnovo certificati", "clientUid": "hotel", "companyUid": "acme", "done": False,
                       "planDate": (today - timedelta(days=2)).isoformat(), "planStartMin": 840, "durationMin": 60,
                       "priority": 1, "refs": "INC0012345"})
    # an hour from now, so that it is "today" whenever the script runs
    soon = min((datetime.fromtimestamp(now / 1000).hour + 1) * 60, 22 * 60)
    put("todo", "t2", {"title": "Backup del server", "clientUid": "tax", "companyUid": "muni", "done": False,
                       "planDate": today.isoformat(), "planStartMin": soon, "durationMin": 90, "refs": ""})
    put("todo", "t3", {"title": "Inventario hardware", "clientUid": "wine", "companyUid": "acme", "done": False,
                       "dueDate": (today + timedelta(days=3)).isoformat(), "refs": ""})
    put("todo", "t4", {"title": "Preventivo stampanti", "done": False, "refs": ""})


def main():
    dark = "--dark" in sys.argv
    # the manual lives in the documentation repository, cloned next to this one: without it the
    # screenshots would land in a stray folder (unless SCREENSHOTS_OUT names another one)
    if not os.environ.get("SCREENSHOTS_OUT") and not OUT.parent.is_dir():
        raise SystemExit(f"clone activitytrack-doc next to this repository ({OUT.parent} is missing)")
    app = QApplication([])
    app.setApplicationName("activitytrack-desktop-screenshots")
    # Qt's own buttons in Italian, as the users see them
    QLocale.setDefault(QLocale(QLocale.Language.Italian, QLocale.Country.Italy))
    qt_texts = QTranslator(app)
    if qt_texts.load(QLocale(), "qtbase", "_", QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)):
        app.installTranslator(qt_texts)
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, tempfile.mkdtemp())

    from activitytrack_desktop import forms, theme
    from activitytrack_desktop.home import Actions
    from activitytrack_desktop.notify import Notifier
    from activitytrack.pairing import Account
    from activitytrack_desktop.service import SyncService
    from activitytrack.session import Session
    from activitytrack_desktop.ui import MainWindow, PairDialog
    from activitytrack.work import PAUSE, TRAVEL, StartRequest

    theme.install(app, dark=dark)
    # the dark set: the Home, the Da fare and the quick entry, with "-dark" in the name
    suffix = "-dark" if dark else ""

    def save(widget, name, always=False):
        if always or not dark or name in ("home", "todos", "quick"):
            # the layouts settled first: a scroll bar shown for a moment would be in the picture
            app.processEvents()
            widget.grab().save(str(OUT / f"{name}{suffix}.png"))

    OUT.mkdir(parents=True, exist_ok=True)
    folder = tempfile.mkdtemp()
    session = Session(folder, use_keyring=False)
    pair = PairDialog(session)
    pair.link.setText("activitytrack://pair?v=1&u=https%3A%2F%2Fat.example.com&c=Xk3…")
    pair.resize(560, 190)
    pair.show()
    save(pair, "pair")

    account = Account("https://at.example.com", None, "d1", "anna", "Anna Rossi", "user", "Esempio Srl")
    session.store.set_state("account", account.to_json())
    session.vault.put("d1", "x")
    session.store.set_state("last_sync", int(datetime.now().timestamp() * 1000))
    now = int(datetime.now().timestamp() * 1000)
    sample(session.store, now)
    service = SyncService(session)
    # no server: the network coming up must not start a sync
    service.sync = lambda full=False: None
    actions = Actions(session)
    w = actions.work
    b = w.start(StartRequest(client="hotel", activity="Aggiornamento firewall", start_ms=now - 300 * MIN,
                             end_ms=now - 240 * MIN))
    c = w.start(StartRequest(client="tax", activity="", start_ms=now - 200 * MIN, end_ms=now - 140 * MIN))
    d = w.start(StartRequest(client="wine", activity="Installazione stampanti", start_ms=now - 130 * MIN))
    w.command(d, "SUSPEND", at=now - 100 * MIN)
    a = w.start(StartRequest(client="lib", activity="Configurazione rete Wi-Fi della sala lettura",
                             tags=["urgente", "rete"], start_ms=now - 95 * MIN))
    w.command(a, TRAVEL, at=now - 70 * MIN)
    w.command(a, "WORK", at=now - 52 * MIN)
    del b, c
    notifier = Notifier(use_dbus=False)
    win = MainWindow(session, service, actions, notifier)
    win.resize(980, 860)
    win.show_up()
    win.show_section("home")
    save(win, "home")
    win.show_section("todos")
    save(win, "todos")
    win.show_section("settings", win.panel)
    win.panel.refresh()
    win.resize(980, 640)
    save(win, "sync")
    if win.reminders_tab is not None:
        win.show_section("settings", win.reminders_tab)
        save(win, "reminders")
    if getattr(win, "general", None) is not None:
        win.show_section("settings", win.general)
        save(win, "general")

    q = forms.QuickEntry(w)
    q.description.setPlainText("Telefonata con l'ufficio per la VPN")
    q.client.setEditText("Ufficio Tributi")
    q.resize(600, 520)
    q.show()
    save(q, "quick")
    e = forms.EntryDialog(w, uid=a)
    e.resize(660, 760)
    e.show()
    save(e, "entry")
    stopped = [x for x in w.entries() if x.get("status") == "TO_COMPLETE"][0]
    s = forms.StopDialog(w, stopped["uid"])
    s.resize(540, 280)
    s.show()
    save(s, "stop")
    t = forms.TodoDialog(actions.todos, uid="t2")
    t.resize(640, 560)
    t.show()
    save(t, "todo")

    from PyQt6.QtCore import QPoint
    from PyQt6.QtTest import QTest
    from activitytrack_desktop.timegrid_ui import TimeGridDialog

    today = datetime.now().date()
    g = TimeGridDialog(today, None, None, ranged=True, busy=w.busy(today))
    cell = lambda i: QPoint(int(g.grid._x(i % 12) + 8), int((i // 12 - g.grid.first) * 24 + 10))  # noqa: E731
    QTest.mousePress(g.grid, Qt.MouseButton.LeftButton, pos=cell(99))
    QTest.mouseMove(g.grid, cell(116))
    QTest.mouseRelease(g.grid, Qt.MouseButton.LeftButton, pos=cell(116))
    g.show()
    save(g, "grid")

    from activitytrack_desktop import reminder_ui

    def grab_question():
        for x in app.topLevelWidgets():
            if x.isVisible() and x.windowTitle() == "ActivityTrack" and x is not win:
                save(x, "question")
                x.reject()
    QTimer.singleShot(300, grab_question)
    reminder_ui.ask("Ancora su Biblioteca civica?", "Ultima conferma alle 15:30",
                    [("yes", "Sì"), ("pause", "Pausa"), ("stop_at", "Stop alle 15:30")])
    del PAUSE
    win.quitting = True
    service.stop()
    print("\n".join(sorted(p.name for p in OUT.glob("*.png"))))


if __name__ == "__main__":
    main()
