# SPDX-License-Identifier: GPL-3.0-or-later
"""The tray icon, the window and the pairing dialog (docs/DESIGN.md §6)."""

import threading
from datetime import datetime

from PyQt6.QtCore import QObject, Qt, QTimer, pyqtSignal as Signal
from PyQt6.QtGui import QGuiApplication, QIcon
from PyQt6.QtWidgets import (
    QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QMainWindow, QMenu, QMessageBox,
    QPushButton, QSystemTrayIcon, QTabWidget, QVBoxLayout, QWidget,
)

from . import __version__, icons, pairing, wire
from .i18n import _

PAIR_ERRORS = {
    pairing.NOT_A_LINK: _("Non è un collegamento di associazione: copialo dalla pagina «Dispositivi» del web."),
    pairing.VERSION: _("Collegamento di una versione che questa app non conosce: aggiorna ActivityTrack Desktop."),
    pairing.NOT_HTTPS: _("Il server deve usare HTTPS."),
    pairing.BAD_PIN: _("Il collegamento è incompleto: copialo di nuovo."),
    pairing.INVALID_CODE: _("Codice scaduto o già usato: creane un altro dalla pagina web."),
    pairing.USER_DISABLED: _("Il tuo utente non può sincronizzare: chiedi all'amministratore."),
    pairing.NETWORK: _("Server non raggiungibile: controlla la rete e l'indirizzo."),
    pairing.CERTIFICATE: _("Il certificato del server non è valido o non corrisponde al collegamento."),
    pairing.SERVER: _("Il server ha risposto con un errore."),
    pairing.APP_TOO_OLD: _("Il server non accetta questa versione: aggiorna ActivityTrack Desktop."),
    pairing.SERVER_TOO_OLD: _("Questa versione è più recente del server: va aggiornato il server."),
}


def state_text(session, state, detail):
    """What the sync says, for the window, the tooltip and the menu."""
    store = session.store
    if session.account is None:
        return _("Non associato: associa questo PC a un server ActivityTrack Web.")
    if store.get_state("revoked"):
        return _("Il server ha revocato l'associazione di questo PC. I dati restano qui: "
                 "per sincronizzare di nuovo associalo dalla pagina «Dispositivi» del web.")
    code = store.get_state("incompatible")
    if code == wire.SERVER_TOO_OLD:
        return _("Questa versione è più recente del server ActivityTrack Web: va aggiornato il server "
                 "(avvisa l'amministratore). I dati restano qui e si sincronizzano dopo l'aggiornamento.")
    if code:
        return _("Il server ActivityTrack Web non accetta più questa versione: aggiorna ActivityTrack Desktop. "
                 "I dati restano qui e si sincronizzano dopo l'aggiornamento.")
    if state == "offline":
        return _("Server non raggiungibile: le modifiche partono appena torna la rete.")
    if state == "failed":
        return _("Sincronizzazione non riuscita: %s") % detail
    last = store.get_state("last_sync")
    if last:
        return _("Sincronizzato alle %s") % datetime.fromtimestamp(last / 1000).strftime("%H:%M")
    return _("In attesa della prima sincronizzazione…")


def needs_attention(session, state):
    return bool(session.account is None or session.store.get_state("revoked")
                or session.store.get_state("incompatible") or state == "failed")


class _Pairing(QObject):
    done = Signal(object, object)


class PairDialog(QDialog):
    def __init__(self, session, parent=None):
        super().__init__(parent)
        self.session = session
        self.account = None
        self.setWindowTitle(_("Associa a un server"))
        self.setMinimumWidth(520)
        lay = QVBoxLayout(self)
        intro = QLabel(_("Sul web apri «Dispositivi» → «Associa un dispositivo», copia il collegamento e "
                         "incollalo qui. Vale 10 minuti e una sola volta."))
        intro.setWordWrap(True)
        lay.addWidget(intro)
        self.link = QLineEdit(placeholderText="activitytrack://pair?v=1&u=…")
        clip = QGuiApplication.clipboard().text().strip()
        if clip.startswith("activitytrack://pair"):
            self.link.setText(clip)
        lay.addWidget(self.link)
        self.message = QLabel(wordWrap=True)
        self.message.setStyleSheet("color: #c62828")
        self.message.hide()
        lay.addWidget(self.message)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        self.ok = self.buttons.addButton(_("Associa"), QDialogButtonBox.ButtonRole.AcceptRole)
        self.buttons.accepted.connect(self._pair)
        self.buttons.rejected.connect(self.reject)
        lay.addWidget(self.buttons)
        self._signal = _Pairing()
        self._signal.done.connect(self._paired)

    def _pair(self):
        try:
            link = pairing.PairLink.parse(self.link.text(), allow_http=self.session.allow_http)
        except pairing.PairError as e:
            self._error(e.code)
            return
        self.ok.setEnabled(False)
        self.message.setStyleSheet("")
        self.message.setText(_("Associazione con %s…") % link.server)
        self.message.show()

        def work():
            try:
                self._signal.done.emit(self.session.pair(link), None)
            except pairing.PairError as e:
                self._signal.done.emit(None, e.code)
        threading.Thread(target=work, daemon=True).start()

    def _paired(self, account, error):
        self.ok.setEnabled(True)
        if error:
            self._error(error)
            return
        self.account = account
        self.accept()

    def _error(self, code):
        self.message.setStyleSheet("color: #c62828")
        self.message.setText(PAIR_ERRORS.get(code, code))
        self.message.show()


class SyncPanel(QWidget):
    """Settings → Sincronizzazione, as the app's."""

    def __init__(self, session, service, parent=None):
        super().__init__(parent)
        self.session, self.service = session, service
        lay = QVBoxLayout(self)
        title = QLabel(_("Sincronizzazione"))
        title.setStyleSheet("font-size: 18pt")
        lay.addWidget(title)
        self.form = QFormLayout()
        self.values = {}
        for key, label in (("server", _("Server")), ("user", _("Utente")), ("org", _("Organizzazione")),
                           ("pending", _("Modifiche in attesa di invio"))):
            v = QLabel(textInteractionFlags=Qt.TextInteractionFlag.TextSelectableByMouse)
            self.values[key] = v
            self.form.addRow(label, v)
        lay.addLayout(self.form)
        self.status = QLabel(wordWrap=True)
        lay.addWidget(self.status)
        self.errors = QLabel(wordWrap=True)
        self.errors.setStyleSheet("color: #c62828")
        lay.addWidget(self.errors)
        row = QHBoxLayout()
        self.sync_now = QPushButton(_("Sincronizza ora"), clicked=lambda: self.service.sync(full=True))
        self.pair = QPushButton(_("Associa a un server…"), clicked=self._pair)
        self.unpair = QPushButton(_("Dissocia"), clicked=self._unpair)
        for b in (self.sync_now, self.pair, self.unpair):
            row.addWidget(b)
        row.addStretch()
        lay.addLayout(row)
        self.secret = QLabel(wordWrap=True)
        self.secret.setStyleSheet("color: palette(placeholder-text)")
        lay.addWidget(self.secret)
        lay.addStretch()
        version = QLabel(f"ActivityTrack Desktop {__version__}")
        version.setStyleSheet("color: palette(placeholder-text)")
        lay.addWidget(version)
        service.changed.connect(lambda *_a: self.refresh())
        self.refresh()

    def refresh(self):
        a = self.session.account
        store = self.session.store
        for key in self.values:
            self.values[key].setText("")
        if a is not None:
            self.values["server"].setText(a.server + (_(" · chiave fissata") if a.pin else ""))
            self.values["user"].setText(f"{a.name} ({a.username})" if a.name else a.username)
            self.values["org"].setText(a.org)
            self.values["pending"].setText(str(store.db.execute("SELECT count(*) FROM pending").fetchone()[0]))
        self.status.setText(state_text(self.session, self.service.state, self.service.detail))
        errors = store.errors()
        self.errors.setText(_("Non sincronizzati:") + "\n" + "\n".join(
            f"· {e['type']} {e['uid'][:8]}: {e['error']} {e['detail']}" for e in errors) if errors else "")
        self.errors.setVisible(bool(errors))
        self.sync_now.setVisible(a is not None and not store.get_state("revoked"))
        self.unpair.setVisible(a is not None)
        self.pair.setText(_("Associa di nuovo…") if a is not None else _("Associa a un server…"))
        self.secret.setText("" if self.session.vault.secure else _(
            "Nessun portachiavi di sistema: il token di accesso è in un file leggibile solo dal tuo utente."))

    def _pair(self):
        d = PairDialog(self.session, self)
        if d.exec():
            self.service.sync(full=True)
        self.refresh()

    def _unpair(self):
        ok = QMessageBox.question(self, _("Dissocia"), _(
            "Il PC tiene i suoi dati. Per sincronizzare di nuovo va riassociato dalla pagina web."))
        if ok == QMessageBox.StandardButton.Yes:
            self.session.unpair()
            self.refresh()
            self.service.changed.emit("unpaired", "")


class MainWindow(QMainWindow):
    def __init__(self, session, service, actions=None, notifier=None):
        super().__init__()
        self.setWindowTitle("ActivityTrack")
        # the installed icon (the app's), else the drawn one
        self.setWindowIcon(QIcon.fromTheme("activitytrack-desktop", icons.icon()))
        self.panel = SyncPanel(session, service)
        self.tabs = QTabWidget()
        self.home = None
        if actions is not None:
            from .home import Home
            self.home = Home(actions)
            self.tabs.addTab(self.home, _("Attività"))
        self.reminders_tab = None
        if actions is not None and notifier is not None:
            from .reminder_ui import ReminderSettings
            self.reminders_tab = ReminderSettings(actions, notifier)
            self.tabs.addTab(self.reminders_tab, _("Promemoria"))
            actions.redraw.connect(self.reminders_tab.refresh)
        self.tabs.addTab(self.panel, _("Sincronizzazione"))
        self.setCentralWidget(self.tabs)
        self.resize(640, 560)
        # set when the application really quits: Qt 6's quit() asks every window to close first
        self.quitting = False

    def show_up(self):
        self.panel.refresh()
        if self.home is not None:
            self.home.refresh()
            if self.panel.session.account is None:
                self.tabs.setCurrentWidget(self.panel)
        self.show()
        self.raise_()
        self.activateWindow()

    def closeEvent(self, event):
        # closing the window leaves the tray icon: "Esci" quits
        if self.quitting:
            event.accept()
            return
        event.ignore()
        self.hide()


class Tray(QSystemTrayIcon):
    """The icon shows the running activity; the menu has its commands and a new activity."""

    # running activities with their commands in the menu
    MENU_ENTRIES = 5

    def __init__(self, session, service, window, quit_app, actions=None):
        super().__init__(icons.icon())
        self.session, self.service, self.window, self.actions = session, service, window, actions
        self.quit_app = quit_app
        self._menu = QMenu()
        self.setContextMenu(self._menu)
        self.activated.connect(self._activated)
        service.changed.connect(lambda *_a: self.refresh())
        if actions is not None:
            actions.changed.connect(self.refresh)
            actions.redraw.connect(self.refresh)
        # the elapsed time in the tooltip
        self._tick = QTimer(self, interval=60_000, timeout=self.refresh)
        self._tick.start()
        self.refresh()

    def _activated(self, reason):
        if reason in (QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick):
            if self.window.isVisible() and self.window.isActiveWindow():
                self.window.hide()
            else:
                self.window.show_up()
        elif reason == QSystemTrayIcon.ActivationReason.MiddleClick and self.actions is not None:
            self._pause_or_resume()

    def _pause_or_resume(self):
        """Middle click: pause the activity at work, or resume the one paused."""
        from .work import ACTIVE, PAUSE, WORK
        running = [e for e in self.actions.work.running() if e.get("status") == ACTIVE]
        if len(running) == 1:
            e = running[0]
            self.actions.command(e["uid"], WORK if e.get("mode") == PAUSE else PAUSE)

    def _running(self):
        return self.actions.work.running() if self.actions is not None and self.session.account else []

    def refresh(self):
        from .home import commands
        from .texts import hm, state_label
        from .work import ACTIVE

        sync_text = state_text(self.session, self.service.state, self.service.detail)
        alert = needs_attention(self.session, self.service.state)
        running = self._running()
        first = running[0] if running else None
        state = icons.IDLE
        if first is not None and first.get("status") == ACTIVE:
            modes = {"WORK": icons.WORK, "PAUSE": icons.PAUSE, "TRAVEL": icons.TRAVEL}
            state = modes.get(first.get("mode"), icons.IDLE)
        self.setIcon(icons.icon(state, alert))
        lines = ["ActivityTrack"]
        work = self.actions.work if self.actions is not None else None
        for e in running[:3]:
            t = work.totals(e["uid"])
            lines.append(f"{work.label(e)} — {state_label(e)} ({hm(t['WORK'])})")
        if self.session.account is not None and not running:
            lines.append(_("Nessuna attività in corso"))
        if alert or not running:
            lines.append(sync_text)
        self.setToolTip("\n".join(lines))

        m = self._menu
        m.clear()
        for e in running[:self.MENU_ENTRIES]:
            sub = m.addMenu(f"{work.label(e)} — {state_label(e)}")
            for text, cmd in commands(e, work.policy):
                sub.addAction(text, lambda u=e["uid"], c=cmd: self.actions.command(u, c))
            sub.addSeparator()
            sub.addAction(_("Modifica…"), lambda u=e["uid"]: self.actions.edit(u))
        if self.actions is not None and self.session.account is not None:
            new = m.addAction(_("Nuova attività…"), lambda: self.actions.new_entry())
            new.setEnabled(work.policy.feature("entries"))
            if work.policy.feature("todos"):
                startable = self.actions.todos.startable() if work.policy.feature("entries") else []
                if startable:
                    sub = m.addMenu(_("Avvia Da fare"))
                    for t in startable:
                        who = work.name("client", t.get("clientUid"))
                        sub.addAction(" · ".join(x for x in (t.get("title"), who) if x),
                                      lambda u=t["uid"]: self.actions.start_todo(u))
                m.addAction(_("Nuovo Da fare…"), lambda: self.actions.new_todo())
            m.addSeparator()
        status = m.addAction(sync_text if len(sync_text) < 70 else sync_text[:67] + "…")
        status.setEnabled(False)
        m.addAction(_("Apri ActivityTrack"), self.window.show_up)
        if self.session.account is not None:
            m.addAction(_("Sincronizza ora"), lambda: self.service.sync(full=True))
        m.addSeparator()
        m.addAction(_("Esci"), self.quit_app)
