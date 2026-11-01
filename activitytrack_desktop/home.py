# SPDX-License-Identifier: GPL-3.0-or-later
"""
The activities on the desktop (docs/DESIGN.md §6.1, §6.3): the commands,
shared by the tray menu and the window, and the Home with the activities
running and those left to complete.
"""

from PyQt6.QtCore import QObject, Qt, QTimer, pyqtSignal as Signal
from PyQt6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QMessageBox, QPushButton, QScrollArea, QSizePolicy, QVBoxLayout, QWidget,
)

from . import forms
from .i18n import _
from .policy import stored
from .texts import KINDS, clock, error_text, hm, state_label
from .work import ACTIVE, PAUSE, STOP, SUSPEND, SUSPENDED, TO_COMPLETE, TRAVEL, WORK, Work, WorkError

# the app's colours of the modes
COLOURS = {WORK: "#2e7d32", PAUSE: "#f9a825", TRAVEL: "#1565c0", SUSPENDED: "#ef6c00", TO_COMPLETE: "#c62828"}


def commands(entry, policy):
    """[(label, command)] the state allows, as the app's card buttons."""
    status, mode = entry.get("status"), entry.get("mode")
    travel = policy.feature("travel")
    out = []
    if status == ACTIVE:
        if mode != WORK:
            out.append((_("Riprendi") if mode == PAUSE else _("Lavoro"), WORK))
        if mode != PAUSE:
            out.append((_("Pausa"), PAUSE))
        if mode != TRAVEL and travel:
            out.append((_("Viaggio"), TRAVEL))
        if mode != PAUSE:
            out.append((_("Sospendi"), SUSPEND))
        out.append((_("Stop"), STOP))
    elif status == SUSPENDED:
        out.append((_("Riprendi"), WORK))
        if travel:
            out.append((_("Viaggio"), TRAVEL))
        out.append((_("Stop"), STOP))
    return out


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

    def refresh_policy(self):
        self.work.policy = stored(self.session.store)

    def _parent(self):
        from PyQt6.QtWidgets import QApplication
        return QApplication.activeWindow()

    def changed_elsewhere(self):
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


class Home(QWidget):
    def __init__(self, actions, parent=None):
        super().__init__(parent)
        self.actions = actions
        lay = QVBoxLayout(self)
        top = QHBoxLayout()
        self.new = QPushButton(_("Nuova attività…"), clicked=lambda: actions.new_entry())
        self.new.setDefault(True)
        self.full = QPushButton(_("Modulo completo…"), clicked=actions.full_entry)
        top.addWidget(self.new)
        top.addWidget(self.full)
        top.addStretch()
        lay.addLayout(top)
        self.scroll = QScrollArea(widgetResizable=True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        lay.addWidget(self.scroll)
        actions.changed.connect(self.refresh)
        actions.redraw.connect(self.refresh)
        # the elapsed times move
        self._tick = QTimer(self, interval=30_000, timeout=self.refresh)
        self._tick.start()
        self.refresh()

    def refresh(self):
        work = self.actions.work
        body = QWidget()
        lay = QVBoxLayout(body)
        paired = self.actions.session.account is not None
        self.new.setEnabled(paired)
        self.full.setEnabled(paired)
        if not paired:
            lay.addWidget(QLabel(_("Associa questo PC a un server ActivityTrack Web dalla scheda "
                                   "«Sincronizzazione».")))
        running = work.running()
        missing = sorted((e for e in work.entries() if e.get("status") == TO_COMPLETE),
                         key=lambda e: -work.last_boundary(e["uid"]))
        for title, rows in ((_("In corso"), running), (_("Da completare"), missing)):
            if not rows:
                continue
            head = QLabel(title.upper())
            head.setStyleSheet("color: palette(placeholder-text); font-weight: bold; margin-top: 8px")
            lay.addWidget(head)
            for e in rows:
                lay.addWidget(Card(self.actions, e))
        if paired and not running and not missing:
            lay.addWidget(QLabel(_("Nessuna attività in corso.")))
        lay.addStretch()
        body.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        self.scroll.setWidget(body)
