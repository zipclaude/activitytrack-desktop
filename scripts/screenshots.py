# SPDX-License-Identifier: GPL-3.0-or-later
"""
The manual's screenshots (docs/manual/img), from sample data in a
temporary folder: no server, no personal data.

    QT_QPA_PLATFORM=offscreen python3 scripts/screenshots.py
"""

import os
import sys
import tempfile
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QLibraryInfo, QLocale, QSettings, QTimer, QTranslator  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

OUT = ROOT / "docs" / "manual" / "img"
MIN = 60_000


def sample(store, now):
    rev = iter(range(1, 1000))

    def put(type_, uid, fields, central=True):
        store.pulled({"type": type_, "uid": uid, "rev": next(rev), "central": central, "fields": fields})
    put("company", "acme", {"name": "Alfa Sistemi", "archived": False})
    put("company", "muni", {"name": "Comune di Valdora", "archived": False})
    for uid, name, company in (("lib", "Biblioteca civica", "muni"), ("tax", "Ufficio Tributi", "muni"),
                               ("hotel", "Hotel Belvedere", "acme"), ("wine", "Cantina Monte Verde", "acme")):
        put("client", uid, {"name": name, "companyUid": company, "archived": False})
    put("role", "sys", {"name": "Sistemista", "archived": False})
    put("tag", "urg", {"name": "urgente", "archived": False})
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
    app = QApplication([])
    app.setApplicationName("activitytrack-desktop-screenshots")
    app.setStyle("Fusion")
    # Qt's own buttons in Italian, as the users see them
    QLocale.setDefault(QLocale(QLocale.Language.Italian, QLocale.Country.Italy))
    qt_texts = QTranslator(app)
    if qt_texts.load(QLocale(), "qtbase", "_", QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)):
        app.installTranslator(qt_texts)
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, tempfile.mkdtemp())

    from activitytrack_desktop import forms
    from activitytrack_desktop.home import Actions
    from activitytrack_desktop.notify import Notifier
    from activitytrack.pairing import Account
    from activitytrack_desktop.service import SyncService
    from activitytrack.session import Session
    from activitytrack_desktop.ui import MainWindow, PairDialog
    from activitytrack.work import PAUSE, StartRequest

    OUT.mkdir(parents=True, exist_ok=True)
    folder = tempfile.mkdtemp()
    session = Session(folder, use_keyring=False)
    pair = PairDialog(session)
    pair.link.setText("activitytrack://pair?v=1&u=https%3A%2F%2Fat.example.com&c=Xk3…")
    pair.resize(560, 170)
    pair.show()
    pair.grab().save(str(OUT / "pair.png"))

    account = Account("https://at.example.com", None, "d1", "anna", "Anna Rossi", "user", "Esempio Srl")
    session.store.set_state("account", account.to_json())
    session.vault.put("d1", "x")
    session.store.set_state("last_sync", int(datetime.now().timestamp() * 1000))
    now = int(datetime.now().timestamp() * 1000)
    sample(session.store, now)
    service = SyncService(session)
    actions = Actions(session)
    w = actions.work
    a = w.start(StartRequest(client="lib", activity="Configurazione rete Wi-Fi della sala lettura",
                             tags=["urgente"], start_ms=now - 95 * MIN))
    w.command(a, PAUSE, at=now - 10 * MIN)
    b = w.start(StartRequest(client="tax", activity="", start_ms=now - 200 * MIN, end_ms=now - 140 * MIN))
    del b
    c = w.start(StartRequest(client="hotel", activity="Aggiornamento firewall", start_ms=now - 300 * MIN,
                             end_ms=now - 240 * MIN))
    del c
    notifier = Notifier(use_dbus=False)
    win = MainWindow(session, service, actions, notifier)
    win.resize(760, 760)
    win.show_up()
    win.tabs.setCurrentIndex(0)
    win.grab().save(str(OUT / "home.png"))
    win.tabs.setCurrentWidget(win.panel)
    win.panel.refresh()
    win.grab().save(str(OUT / "sync.png"))
    if win.reminders_tab is not None:
        win.tabs.setCurrentWidget(win.reminders_tab)
        win.grab().save(str(OUT / "reminders.png"))
    if getattr(win, "general", None) is not None:
        win.tabs.setCurrentWidget(win.general)
        win.grab().save(str(OUT / "general.png"))

    q = forms.QuickEntry(w)
    q.description.setPlainText("Telefonata con l'ufficio per la VPN")
    q.client.setEditText("Ufficio Tributi")
    q.resize(560, 430)
    q.show()
    q.grab().save(str(OUT / "quick.png"))
    e = forms.EntryDialog(w, uid=a)
    e.resize(620, 660)
    e.show()
    e.grab().save(str(OUT / "entry.png"))
    stopped = [x for x in w.entries() if x.get("status") == "TO_COMPLETE"][0]
    s = forms.StopDialog(w, stopped["uid"])
    s.resize(520, 250)
    s.show()
    s.grab().save(str(OUT / "stop.png"))
    t = forms.TodoDialog(actions.todos, uid="t2")
    t.resize(600, 480)
    t.show()
    t.grab().save(str(OUT / "todo.png"))

    from activitytrack_desktop import reminder_ui

    def grab_question():
        for x in app.topLevelWidgets():
            if x.isVisible() and x.windowTitle() == "ActivityTrack" and x is not win:
                x.grab().save(str(OUT / "question.png"))
                x.reject()
    QTimer.singleShot(300, grab_question)
    reminder_ui.ask("Ancora su Biblioteca civica?", "Ultima conferma alle 15:30",
                    [("yes", "Sì"), ("pause", "Pausa"), ("stop_at", "Stop alle 15:30")])
    win.quitting = True
    service.stop()
    print("\n".join(sorted(p.name for p in OUT.glob("*.png"))))


if __name__ == "__main__":
    main()
