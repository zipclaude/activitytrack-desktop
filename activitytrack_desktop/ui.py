# SPDX-License-Identifier: GPL-3.0-or-later
"""The tray icon, the window and the pairing dialog (docs/DESIGN.md §6)."""

import threading

from PyQt6.QtCore import QObject, Qt, QTimer, pyqtSignal as Signal
from PyQt6.QtGui import QAction, QGuiApplication, QIcon, QKeySequence
from PyQt6.QtWidgets import (
    QApplication, QButtonGroup, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QMainWindow,
    QMenu, QMessageBox, QStackedWidget, QSystemTrayIcon, QVBoxLayout, QWidget,
)

from activitytrack import homelist, pairing, texts
from activitytrack.i18n import _

from . import __version__, icons, theme, widgets as W


class _Pairing(QObject):
    done = Signal(object, object)


class PairDialog(QDialog):
    def __init__(self, session, parent=None):
        super().__init__(parent)
        self.session = session
        self.account = None
        self.busy = False
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
        self.message = W.label(kind="error", wrap=True)
        self.message.hide()
        lay.addWidget(self.message)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        self.ok = self.buttons.addButton(_("Associa"), QDialogButtonBox.ButtonRole.AcceptRole)
        self.ok.setProperty("role", "primary")
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
        # the server spends the code at the request: a cancel could no longer undo the pairing
        self.busy = True
        self.ok.setEnabled(False)
        self.buttons.button(QDialogButtonBox.StandardButton.Cancel).setEnabled(False)
        W.role(self.message, "")
        self.message.setText(_("Associazione con %s…") % link.server)
        self.message.show()

        def work():
            try:
                self._signal.done.emit(self.session.pair(link), None)
            except pairing.PairError as e:
                self._signal.done.emit(None, e.code)
            except Exception as e:
                # the keyring, the disk: the dialog, waiting, must hear the end anyway
                self._signal.done.emit(None, str(e) or type(e).__name__)
        threading.Thread(target=work, daemon=True).start()

    def reject(self):
        # Esc and the window's close too wait for the server's answer
        if not self.busy:
            super().reject()

    def _paired(self, account, error):
        self.busy = False
        self.ok.setEnabled(True)
        self.buttons.button(QDialogButtonBox.StandardButton.Cancel).setEnabled(True)
        if error:
            self._error(error)
            return
        self.account = account
        self.accept()

    def _error(self, code):
        W.role(self.message, "error")
        self.message.setText(texts.pair_error(code))
        self.message.show()


class SyncPanel(QWidget):
    """Settings → Sincronizzazione, as the app's."""

    def __init__(self, session, service, parent=None):
        super().__init__(parent)
        self.session, self.service = session, service
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(12)
        card = W.Surface(None, 16)
        inner = QVBoxLayout(card)
        inner.setContentsMargins(20, 16, 20, 16)
        self.form = QFormLayout()
        self.form.setHorizontalSpacing(20)
        self.form.setVerticalSpacing(8)
        self.values = {}
        for key, label in (("server", _("Server")), ("user", _("Utente")), ("org", _("Organizzazione")),
                           ("pending", _("Modifiche in attesa di invio"))):
            v = QLabel(textInteractionFlags=Qt.TextInteractionFlag.TextSelectableByMouse)
            self.values[key] = v
            self.form.addRow(W.label(label, "muted"), v)
        inner.addLayout(self.form)
        self.status = QLabel(wordWrap=True)
        self.status.setContentsMargins(0, 8, 0, 0)
        inner.addWidget(self.status)
        self.errors = W.label(kind="error", wrap=True)
        inner.addWidget(self.errors)
        row = QHBoxLayout()
        row.setContentsMargins(0, 8, 0, 0)
        from .home import KEYS
        self.sync_now = W.button(_("Sincronizza ora"), lambda: self.service.sync(full=True), "primary", "sync",
                                 W.with_key(_("Sincronizza ora"), KEYS["sync"]))
        self.pair = W.button(_("Associa a un server…"), self._pair, "tonal", "devices")
        self.unpair = W.button(_("Dissocia"), self._unpair, "danger")
        for b in (self.sync_now, self.pair, self.unpair):
            row.addWidget(b)
        row.addStretch()
        inner.addLayout(row)
        lay.addWidget(card)
        self.secret = W.label(kind="muted", wrap=True)
        lay.addWidget(self.secret)
        lay.addStretch()
        lay.addWidget(W.label(f"ActivityTrack Desktop {__version__}", "small"))
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
        self.status.setText(texts.sync_state(self.session, self.service.state, self.service.detail))
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


class Section:
    """
    A destination of the rail (docs/DESIGN.md §6.3): its key, name and icon,
    and how the window builds its page (None when it has nothing to show,
    e.g. without the activities). Agenda and Report will be two more.
    """

    def __init__(self, key, text, icon, build, shown=lambda window: True):
        self.key, self.text, self.icon, self.build, self.shown = key, text, icon, build, shown


def _home(window):
    if window.work_actions is None:
        return None
    from .home import Home
    window.home = Home(window.work_actions, on_pair=lambda: window.show_section("settings", window.panel))
    return window.home


def _todos(window):
    if window.work_actions is None:
        return None
    from .todos_ui import TodosPage
    window.todos = TodosPage(window.work_actions)
    return window.todos


def _settings(window):
    window.settings = SettingsPage(window)
    return window.settings


# in the rail's order; Ctrl+1, Ctrl+2… follow it
SECTIONS = [
    Section("home", _("Home"), "home", _home),
    Section("todos", _("Da fare"), "todo", _todos, lambda w: w.work_actions.work.policy.feature("todos")),
    Section("settings", _("Impostazioni"), "settings", _settings),
]


class SettingsPage(QWidget):
    """Impostazioni: Sincronizzazione, Promemoria, Generale, as chips over their pages."""

    def __init__(self, window, parent=None):
        super().__init__(parent)
        from .home import scroll_page
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 18, 0, 0)
        head = W.page(_("Impostazioni"))
        head.setContentsMargins(24, 0, 24, 8)
        lay.addWidget(head)
        bar = QHBoxLayout()
        bar.setContentsMargins(24, 0, 24, 6)
        bar.setSpacing(8)
        lay.addLayout(bar)
        self.stack = QStackedWidget()
        lay.addWidget(self.stack)
        self.chips, self.scrolls = {}, {}
        group = QButtonGroup(self)
        panels = [(window.panel, _("Sincronizzazione"))]
        if window.reminders_tab is not None:
            panels.append((window.reminders_tab, _("Promemoria")))
        if window.general is not None:
            panels.append((window.general, _("Generale")))
        for panel, text in panels:
            c = W.chip(text, checkable=True)
            group.addButton(c)
            c.clicked.connect(lambda _c=False, p=panel: self.show_panel(p))
            bar.addWidget(c)
            self.chips[panel] = c
            column = QWidget()
            column.setMaximumWidth(720)
            cl = QVBoxLayout(column)
            cl.setContentsMargins(0, 0, 0, 0)
            cl.addWidget(panel)
            self.scrolls[panel] = scroll_page(column)
            self.stack.addWidget(self.scrolls[panel])
        bar.addStretch()
        self.show_panel(window.panel)

    def show_panel(self, panel):
        self.chips[panel].setChecked(True)
        self.stack.setCurrentWidget(self.scrolls[panel])

    def current(self):
        return next(p for p, c in self.chips.items() if c.isChecked())


class MainWindow(QMainWindow):
    """The window: the rail on the left (SECTIONS), the section's page; the keys of docs/DESIGN.md §6.5."""

    def __init__(self, session, service, actions=None, notifier=None):
        super().__init__()
        theme.install()
        # not self.actions: QWidget.actions() is the window's QActions
        self.session, self.service, self.work_actions = session, service, actions
        self.setWindowTitle("ActivityTrack")
        # the installed icon (the app's), else the drawn one
        self.setWindowIcon(QIcon.fromTheme("activitytrack-desktop", icons.icon()))
        self.panel = SyncPanel(session, service)
        self.home = self.todos = None
        self.reminders_tab = None
        if actions is not None and notifier is not None:
            from .reminder_ui import ReminderSettings
            self.reminders_tab = ReminderSettings(actions, notifier)
            actions.redraw.connect(self.reminders_tab.refresh)
        self.general = None
        if actions is not None and notifier is not None:
            from .general import GeneralPanel, Updates
            self.updater = Updates(actions, notifier, service, self)
            self.general = GeneralPanel(actions, self.updater)
            actions.redraw.connect(self.general.refresh)
        central = QWidget()
        lay = QHBoxLayout(central)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self.rail = W.Rail()
        self.rail.chosen.connect(self.show_section)
        lay.addWidget(self.rail)
        self.stack = QStackedWidget()
        lay.addWidget(self.stack, 1)
        self.pages = {}
        self.sections = []
        for section in SECTIONS:
            page = section.build(self)
            if page is None:
                continue
            page.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
            self.pages[section.key] = page
            self.sections.append(section)
            self.stack.addWidget(page)
            self.rail.add(section.key, section.text, section.icon,
                          W.with_key(section.text, f"Ctrl+{len(self.sections)}"))
        self.sync_item = self.rail.add_bottom(_("Sincronizza"), "sync", self.sync)
        self.setCentralWidget(central)
        self.shortcuts = {}
        self._keys()
        self.resize(940, 720)
        self.setMinimumSize(680, 480)
        service.changed.connect(lambda *_a: self._sync_state())
        if actions is not None:
            actions.changed.connect(self._sections)
            actions.redraw.connect(self._sections)
        theme.notifier().changed.connect(lambda: W.recolour(self))
        self._sections()
        self._sync_state()
        self.show_section(self.sections[0].key)
        # set when the application really quits: Qt 6's quit() asks every window to close first
        self.quitting = False

    def _keys(self):
        """The window's shortcuts, while it has the focus (docs/DESIGN.md §6.5)."""
        from .home import KEYS
        a = self.work_actions
        keys = []
        if a is not None:
            keys += [
                ("new_entry", KEYS["new_entry"], lambda: a.new_entry()),
                ("pause", KEYS["pause"], a.pause_or_resume),
                ("stop", KEYS["stop"], lambda: a.stop_current(self.home.big_uid if self.home else None)),
                ("new_todo", KEYS["new_todo"], lambda: a.new_todo()),
                ("find", KEYS["find"], self.find),
            ]
        keys.append(("sync", KEYS["sync"], self.sync))
        for i, section in enumerate(self.sections, 1):
            keys.append((f"section{i}", f"Ctrl+{i}", lambda k=section.key: self.show_section(k)))
        for name, key, slot in keys:
            action = QAction(self)
            action.setShortcut(QKeySequence(key))
            action.setShortcutContext(Qt.ShortcutContext.WindowShortcut)
            action.triggered.connect(lambda _c=False, s=slot: s())
            self.addAction(action)
            self.shortcuts[name] = action

    def _sections(self):
        """A section the policy switches off leaves the rail."""
        for section in self.sections:
            on = section.shown(self)
            self.rail.items[section.key].setVisible(on)
            if not on and self.current_section() == section.key:
                self.show_section(self.sections[0].key)

    def _sync_state(self):
        text = texts.sync_state(self.session, self.service.state, self.service.detail)
        from .home import KEYS
        self.sync_item.setToolTip(W.with_key(text, KEYS["sync"]))
        self.sync_item.alert = texts.sync_needs_attention(self.session, self.service.state)
        self.sync_item.update()

    def sync(self):
        """F5, and the rail's button: now, or to the pairing when there is no server yet."""
        if self.session.account is None:
            self.show_section("settings", self.panel)
        elif not self.session.store.get_state("revoked"):
            self.service.sync(full=True)

    def find(self):
        """Ctrl+F: the search of the list shown, the Home's from elsewhere."""
        page = self.pages.get(self.current_section())
        if not hasattr(page, "focus_search"):
            self.show_section("home")
            page = self.pages.get("home")
        if hasattr(page, "focus_search"):
            page.focus_search()

    @property
    def focused_uid(self):
        """The activity of the Home's big card: what the stop shortcuts act on."""
        return self.home.big_uid if self.home else None

    def show_section(self, key, panel=None):
        section = next((s for s in self.sections if s.key == key), None)
        if section is None or not section.shown(self):
            return
        self.stack.setCurrentWidget(self.pages[key])
        self.rail.select(key)
        # the keys to the page, not a focus ring on its first button
        self.pages[key].setFocus(Qt.FocusReason.OtherFocusReason)
        if panel is not None and key == "settings":
            self.settings.show_panel(panel)

    def current_section(self):
        page = self.stack.currentWidget()
        return next((k for k, p in self.pages.items() if p is page), None)

    def show_up(self):
        self.panel.refresh()
        if self.home is not None:
            self.home.refresh()
            if self.session.account is None:
                self.show_section("settings", self.panel)
        self.show()
        self.raise_()
        self.activateWindow()
        page = self.stack.currentWidget()
        if page is not None and QApplication.focusWidget() is None:
            page.setFocus(Qt.FocusReason.OtherFocusReason)

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
        from activitytrack.work import PAUSE, WORK
        work = self.actions.work
        running = [e for e in work.running() if work.open_segment(e["uid"]) is not None]
        if len(running) == 1:
            e = running[0]
            self.actions.command(e["uid"], WORK if work.open_segment(e["uid"])["kind"] == PAUSE else PAUSE)

    def _running(self):
        return self.actions.work.running() if self.actions is not None and self.session.account else []

    def refresh(self):
        from .home import commands
        from activitytrack.texts import display_label, hm

        sync_text = texts.sync_state(self.session, self.service.state, self.service.detail)
        alert = texts.sync_needs_attention(self.session, self.service.state)
        running = self._running()
        first = running[0] if running else None
        state = icons.IDLE
        seg = self.actions.work.open_segment(first["uid"]) if first is not None else None
        if seg is not None:
            modes = {"WORK": icons.WORK, "PAUSE": icons.PAUSE, "TRAVEL": icons.TRAVEL}
            state = modes.get(seg["kind"], icons.IDLE)
        self.setIcon(icons.icon(state, alert))
        lines = ["ActivityTrack"]
        work = self.actions.work if self.actions is not None else None
        for e in running[:3]:
            t = work.totals(e["uid"])
            lines.append(f"{work.label(e)} — {display_label(work.display(e)[0])} ({hm(t['WORK'])})")
        if self.session.account is not None and not running:
            lines.append(_("Nessuna attività in corso"))
        if alert or not running:
            lines.append(sync_text)
        self.setToolTip("\n".join(lines))

        m = self._menu
        m.clear()
        for e in running[:self.MENU_ENTRIES]:
            sub = m.addMenu(f"{work.label(e)} — {display_label(work.display(e)[0])}")
            for act in commands(work, e):
                sub.addAction(act.label, lambda u=e["uid"], a=act: self.actions.act(u, a))
            sub.addSeparator()
            sub.addAction(_("Modifica…"), lambda u=e["uid"]: self.actions.edit(u))
        if self.actions is not None and self.session.account is not None:
            new = m.addAction(_("Nuova attività…"), lambda: self.actions.new_entry())
            new.setEnabled(work.policy.feature("entries"))
            m.addAction(_("Nuova assenza…"), lambda: self.actions.new_absence())
            if work.policy.feature("todos"):
                startable = homelist.startable(work) if work.policy.feature("entries") else []
                if startable:
                    sub = m.addMenu(_("Avvia Da fare"))
                    for t in startable:
                        who = work.name("client", t.get("clientUid"))
                        sub.addAction(" · ".join(x for x in (t.get("activity"), who) if x),
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
