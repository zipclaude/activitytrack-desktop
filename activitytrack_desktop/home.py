# SPDX-License-Identifier: GPL-3.0-or-later
"""
The activities on the desktop (docs/DESIGN.md §6.1, §6.3): the commands,
shared by the tray menu and the window, and the Home with the activities
running and those left to complete.
"""

from PyQt6.QtCore import QObject, QSettings, Qt, QTimer, pyqtSignal as Signal
from PyQt6.QtWidgets import (
    QComboBox, QFrame, QHBoxLayout, QLabel, QMenu, QMessageBox, QPushButton, QScrollArea, QSizePolicy, QToolButton,
    QVBoxLayout, QWidget,
)

from activitytrack import formats, texts
from activitytrack.i18n import _
from activitytrack.policy import stored
from activitytrack.texts import KINDS, clock, error_text, hm, state_label
from activitytrack.todos import DEFAULT_SHOW, SHOWS, WINDOWS, Todos
from activitytrack.work import (
    ACTIVE, PAUSE, REOPEN, STOP, SUSPENDED, TO_COMPLETE, TRAVEL, WORK, Work, WorkError,
)

from . import forms

# the app's colours of the modes
COLOURS = {WORK: "#2e7d32", PAUSE: "#f9a825", TRAVEL: "#1565c0", SUSPENDED: "#ef6c00", TO_COMPLETE: "#c62828"}


def commands(entry, policy):
    """[(label, command)] the state allows, as the app's card buttons (the library's, for every interface)."""
    return texts.entry_commands(entry, policy)


class Actions(QObject):
    """
    The commands on activities. [changed] after each: the sync pushes and the
    views redraw; [redraw] when the data changed elsewhere (a sync): the views
    only, or every sync would start another.
    """

    changed = Signal()
    redraw = Signal()

    def __init__(self, session, parent=None):
        super().__init__(parent)
        self.session = session
        self.work = Work(session.store, stored(session.store), zone=_zone())
        self.todos = Todos(self.work)

    def refresh_policy(self):
        self.work.policy = stored(self.session.store)

    def _parent(self):
        from PyQt6.QtWidgets import QApplication
        return QApplication.activeWindow()

    def changed_elsewhere(self):
        # the command line or the terminal may have changed the formats too
        formats.load(self.session.store)
        self.redraw.emit()

    def _done(self):
        self.changed.emit()

    def _fail(self, e):
        QMessageBox.warning(self._parent(), "ActivityTrack", error_text(e) if isinstance(e, WorkError) else str(e))
        self.changed.emit()

    def new_entry(self, todo=None):
        if self.session.account is None:
            return
        self.refresh_policy()
        d = forms.QuickEntry(self.work, self._parent(), todo=todo)
        # from the tray: in front of what the user was doing
        d.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        d.show()
        d.raise_()
        d.activateWindow()
        if d.exec():
            self._done()

    def full_entry(self):
        self.refresh_policy()
        if forms.EntryDialog(self.work, self._parent()).exec():
            self._done()

    def command(self, uid, cmd):
        self.refresh_policy()
        try:
            if cmd == STOP:
                forms.stop(self.work, uid, self._parent())
            else:
                self.work.command(uid, cmd)
        except WorkError as e:
            self._fail(e)
            return
        self._done()

    def edit(self, uid):
        self.refresh_policy()
        try:
            forms.edit_entry(self.work, uid, self._parent())
        except WorkError as e:
            self._fail(e)
            return
        self._done()

    def complete(self, uid):
        self.refresh_policy()
        try:
            forms.StopDialog(self.work, uid, self._parent()).exec()
        except WorkError as e:
            self._fail(e)
            return
        self._done()

    def _do(self, f, *args):
        self.refresh_policy()
        try:
            f(*args)
        except WorkError as e:
            self._fail(e)
            return
        self._done()

    def start_todo(self, uid):
        t = self.session.store.get("todo", uid)
        if t is not None:
            self.new_entry(todo=t)

    def todo_done(self, uid, done=True):
        self._do(self.todos.set_done, uid, done)

    def todo_ignore(self, uid, ignored=True):
        self._do(self.todos.set_ignored, uid, ignored)

    def todo_reopen(self, uid):
        self._do(self.todos.reopen, uid)

    def todo_postpone(self, uid):
        """Later by the user's snooze (Promemoria), within the policy."""
        from .reminder_ui import local_intervals
        from activitytrack.reminders import config_of
        self._do(self.todos.postpone, uid, config_of(self.work.policy, local_intervals())["planSnoozeMin"])

    def reopen_entry(self, uid):
        self._do(self.work.command, uid, REOPEN)

    def new_todo(self, plan=None):
        if self.session.account is None:
            return
        self.refresh_policy()
        d = forms.TodoDialog(self.todos, self._parent(), plan=plan)
        d.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        if d.exec():
            self._done()

    def edit_todo(self, uid):
        self.refresh_policy()
        try:
            ok = forms.TodoDialog(self.todos, self._parent(), uid=uid).exec()
        except WorkError as e:
            self._fail(e)
            return
        if ok:
            self._done()


def _zone():
    from PyQt6.QtCore import QTimeZone
    z = bytes(QTimeZone.systemTimeZoneId()).decode()
    return z or None


class Card(QFrame):
    """One activity: who and what, its state since when, the time so far, its commands."""

    def __init__(self, actions, entry, parent=None):
        super().__init__(parent)
        work = actions.work
        self.setFrameShape(QFrame.Shape.StyledPanel)
        lay = QVBoxLayout(self)
        status = entry.get("status")
        colour = COLOURS.get(entry.get("mode") if status == ACTIVE else status, "#6f7680")
        self.setStyleSheet(f"Card {{ border-left: 5px solid {colour}; }}")
        title = QLabel(work.label(entry))
        title.setStyleSheet("font-weight: bold; font-size: 11pt")
        title.setWordWrap(True)
        lay.addWidget(title)
        company = work.name("company", entry.get("companyUid"))
        open_seg = work.open_segment(entry["uid"])
        since = clock(open_seg["startUtcMs"]) if open_seg else clock(work.last_boundary(entry["uid"]) or 0)
        totals = work.totals(entry["uid"])
        parts = [f"<b style='color:{colour}'>{state_label(entry)}</b> " + _("dalle %s") % since]
        parts.append(f"{KINDS[WORK]} {hm(totals[WORK])}")
        if totals[TRAVEL]:
            parts.append(f"{KINDS[TRAVEL]} {hm(totals[TRAVEL])}")
        if company and company not in title.text():
            parts.insert(0, company)
        if entry.get("needsReview"):
            parts.append("<b style='color:#c62828'>" + _("da verificare") + "</b>")
        info = QLabel(" · ".join(parts))
        lay.addWidget(info)
        row = QHBoxLayout()
        for text, cmd in commands(entry, work.policy):
            b = QPushButton(text)
            b.clicked.connect(lambda _c=False, u=entry["uid"], c=cmd: actions.command(u, c))
            row.addWidget(b)
        if status == TO_COMPLETE:
            row.addWidget(QPushButton(_("Completa…"), clicked=lambda: actions.complete(entry["uid"])))
        row.addStretch()
        row.addWidget(QPushButton(_("Modifica…"), clicked=lambda: actions.edit(entry["uid"])))
        lay.addLayout(row)


class TodoRow(QFrame):
    """A to-do of the Home list: title, client and state, when; start, done and the rest in a menu."""

    def __init__(self, actions, t, st, parent=None):
        super().__init__(parent)
        work, policy = actions.work, actions.work.policy
        self.setFrameShape(QFrame.Shape.StyledPanel)
        lay = QHBoxLayout(self)
        text = QVBoxLayout()
        title = QLabel(t.get("title") or "")
        title.setWordWrap(True)
        title.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        font = title.font()
        font.setBold(st not in ("done", "ignored"))
        font.setStrikeOut(st == "ignored")
        title.setFont(font)
        text.addWidget(title)
        who = work.name("client", t.get("clientUid")) or work.name("company", t.get("companyUid"))
        parts = [who, texts.TODO_STATES.get(st, "")]
        if t.get("priority") and st not in ("done", "ignored"):
            parts.append(f"P{t['priority']}")
        sub = QLabel(" · ".join(x for x in parts if x))
        sub.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        sub.setStyleSheet("color: #c62828" if st == "overdue" else "color: palette(placeholder-text)")
        text.addWidget(sub)
        lay.addLayout(text, 1)
        lay.addWidget(QLabel(texts.todo_when(t, actions.todos.tz())))
        uid = t["uid"]
        if st not in ("done", "ignored"):
            if policy.feature("entries"):
                lay.addWidget(QPushButton(_("Avvia"), clicked=lambda: actions.start_todo(uid)))
            lay.addWidget(QPushButton(_("Fatto"), clicked=lambda: actions.todo_done(uid)))
        else:
            lay.addWidget(QPushButton(_("Riapri"), clicked=lambda: actions.todo_reopen(uid)))
        more = QToolButton(text="⋯", popupMode=QToolButton.ToolButtonPopupMode.InstantPopup)
        menu = QMenu(more)
        if st not in ("done", "ignored") and t.get("planDate") and policy.feature("planning"):
            minutes = policy.setting("planSnoozeMin", 15)
            menu.addAction(_("Posticipa di %d min") % minutes, lambda: actions.todo_postpone(uid))
        if st not in ("done", "ignored") and policy.feature("ignoreTodos"):
            menu.addAction(_("Ignora"), lambda: actions.todo_ignore(uid))
        menu.addAction(_("Modifica…"), lambda: actions.edit_todo(uid))
        more.setMenu(menu)
        lay.addWidget(more)


class EntryRow(QFrame):
    """A stopped activity of the Home list: complete it, or open it."""

    def __init__(self, actions, e, end, parent=None):
        super().__init__(parent)
        work = actions.work
        self.setFrameShape(QFrame.Shape.StyledPanel)
        lay = QHBoxLayout(self)
        text = QVBoxLayout()
        title = QLabel(work.label(e))
        title.setWordWrap(True)
        title.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        text.addWidget(title)
        t = work.totals(e["uid"])
        missing = e.get("status") == TO_COMPLETE
        sub = QLabel(f"{state_label(e)} · {KINDS[WORK]} {hm(t[WORK])}")
        sub.setStyleSheet("color: #c62828" if missing else "color: palette(placeholder-text)")
        text.addWidget(sub)
        lay.addLayout(text, 1)
        lay.addWidget(QLabel(_("fino alle %s") % formats.time(end)))
        uid = e["uid"]
        if missing:
            lay.addWidget(QPushButton(_("Completa…"), clicked=lambda: actions.complete(uid)))
        more = QToolButton(text="⋯", popupMode=QToolButton.ToolButtonPopupMode.InstantPopup)
        menu = QMenu(more)
        menu.addAction(_("Modifica…"), lambda: actions.edit(uid))
        menu.addAction(_("Riapri"), lambda: actions.reopen_entry(uid))
        more.setMenu(menu)
        lay.addWidget(more)


class Filters(QWidget):
    """
    Period, state, company and tag of the Home list, as the app's; kept
    between starts. A setting the policy fixes (homeWindow, homeShow) is
    greyed with its value.
    """

    changed = Signal()

    def __init__(self, actions, parent=None):
        super().__init__(parent)
        self.actions = actions
        self.settings = QSettings()
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.window = QComboBox()
        for w in WINDOWS:
            self.window.addItem(texts.WINDOWS[w], w)
        self.show_button = QToolButton(popupMode=QToolButton.ToolButtonPopupMode.InstantPopup)
        self.show_menu = QMenu(self.show_button)
        self.show_actions = {}
        for key in SHOWS:
            a = self.show_menu.addAction(texts.SHOWS[key])
            a.setCheckable(True)
            a.toggled.connect(self._changed)
            self.show_actions[key] = a
        self.show_button.setMenu(self.show_menu)
        self.company = QComboBox()
        self.tag = QComboBox()
        # a long company name must not push the list out of the window
        for c in (self.company, self.tag):
            c.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
            c.setMinimumContentsLength(12)
        for w in (self.window, self.show_button, self.company, self.tag):
            lay.addWidget(w)
        lay.addStretch()
        self.load()
        self.window.currentIndexChanged.connect(self._changed)
        self.company.currentIndexChanged.connect(self._changed)
        self.tag.currentIndexChanged.connect(self._changed)

    def load(self):
        p = self.actions.work.policy
        window = p.setting("homeWindow", -1)
        if not p.setting_fixed("homeWindow"):
            window = int(self.settings.value("home/window", window))
        self.window.setCurrentIndex(max(0, self.window.findData(window)))
        self.window.setEnabled(not p.setting_fixed("homeWindow"))
        shown = p.setting("homeShow", ",".join(DEFAULT_SHOW))
        if not p.setting_fixed("homeShow"):
            shown = self.settings.value("home/show", shown)
        shown = {x.strip() for x in str(shown).split(",")}
        for key, a in self.show_actions.items():
            a.blockSignals(True)
            a.setChecked(key in shown)
            a.blockSignals(False)
        self.show_button.setEnabled(not p.setting_fixed("homeShow"))
        self._label()
        self.fill()

    def fill(self):
        """The companies and tags of the master data (kept when the list is filled again)."""
        work = self.actions.work
        for combo, type_, first, saved in ((self.company, "company", _("Tutte le aziende"), "home/company"),
                                           (self.tag, "tag", _("Tutti i tag"), "home/tag")):
            current = combo.currentData() if combo.count() else self.settings.value(saved)
            combo.blockSignals(True)
            combo.clear()
            combo.addItem(first, None)
            for r in work.masters(type_):
                combo.addItem(r.get("name") or "", r["uid"] if type_ == "company" else r.get("name"))
            combo.setCurrentIndex(max(0, combo.findData(current)) if current else 0)
            combo.blockSignals(False)
        self.company.setVisible(work.policy.field("company").visible and self.company.count() > 2)
        self.tag.setVisible(work.policy.field("tags").visible and self.tag.count() > 1)

    def _label(self):
        shown = [texts.SHOWS[k] for k, a in self.show_actions.items() if a.isChecked()]
        self.show_button.setText(_("Stato: %s") % (", ".join(shown) if shown else _("nessuno")) + " ▾")

    def _changed(self):
        self._label()
        self.settings.setValue("home/window", self.window.currentData())
        self.settings.setValue("home/show", ",".join(self.shown()))
        self.settings.setValue("home/company", self.company.currentData() or "")
        self.settings.setValue("home/tag", self.tag.currentData() or "")
        self.changed.emit()

    def shown(self):
        return [k for k, a in self.show_actions.items() if a.isChecked()]

    def values(self):
        return dict(show=self.shown(), window=self.window.currentData(), company=self.company.currentData(),
                    tag=self.tag.currentData())


class Home(QWidget):
    """The activities running, then one list of to-dos and stopped activities with the filters (app Home)."""

    def __init__(self, actions, parent=None):
        super().__init__(parent)
        self.actions = actions
        lay = QVBoxLayout(self)
        top = QHBoxLayout()
        self.new = QPushButton(_("Nuova attività…"), clicked=lambda: actions.new_entry())
        self.new.setDefault(True)
        self.full = QPushButton(_("Modulo completo…"), clicked=actions.full_entry)
        self.new_todo = QPushButton(_("Nuovo Da fare…"), clicked=lambda: actions.new_todo())
        for b in (self.new, self.full, self.new_todo):
            top.addWidget(b)
        top.addStretch()
        lay.addLayout(top)
        self.scroll = QScrollArea(widgetResizable=True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        lay.addWidget(self.scroll)
        self.filters = None
        actions.changed.connect(self.refresh)
        actions.redraw.connect(self.refresh)
        # the elapsed times move
        self._tick = QTimer(self, interval=30_000, timeout=self.refresh)
        self._tick.start()
        self.refresh()

    def _heading(self, lay, title):
        head = QLabel(title.upper())
        head.setStyleSheet("color: palette(placeholder-text); font-weight: bold; margin-top: 8px")
        lay.addWidget(head)

    def refresh(self):
        work = self.actions.work
        policy = work.policy
        position = self.scroll.verticalScrollBar().value()
        body = QWidget()
        lay = QVBoxLayout(body)
        paired = self.actions.session.account is not None
        self.new.setEnabled(paired and policy.feature("entries"))
        self.full.setEnabled(paired and policy.feature("entries"))
        self.new_todo.setEnabled(paired)
        self.new_todo.setVisible(policy.feature("todos"))
        if not paired:
            lay.addWidget(QLabel(_("Associa questo PC a un server ActivityTrack Web dalla scheda "
                                   "«Sincronizzazione».")))
        running = work.running()
        if running:
            self._heading(lay, _("In corso"))
            for e in running:
                lay.addWidget(Card(self.actions, e))
        # the filters live across redraws: the list below is drawn again
        if self.filters is None:
            self.filters = Filters(self.actions)
            self.filters.changed.connect(self.refresh)
        else:
            self.filters.setParent(None)
            self.filters.fill()
        lay.addWidget(self.filters)
        f = self.filters.values()
        groups = self.actions.todos.home(f["show"], f["window"], f["company"], f["tag"])
        for section, items in groups:
            self._heading(lay, texts.SECTIONS[section])
            for kind, obj, extra in items:
                if kind == "todo":
                    lay.addWidget(TodoRow(self.actions, obj, extra))
                else:
                    lay.addWidget(EntryRow(self.actions, obj, extra))
        if paired and not groups:
            empty = QLabel(_("Niente in questo intervallo."))
            empty.setStyleSheet("color: palette(placeholder-text); margin-top: 8px")
            lay.addWidget(empty)
        lay.addStretch()
        body.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        # the previous body goes with its rows (setWidget deletes it); the filters were taken out first
        self.scroll.setWidget(body)
        self.scroll.verticalScrollBar().setValue(position)
