# SPDX-License-Identifier: GPL-3.0-or-later
"""
The commands without a window: the system-wide shortcuts (hotkeys.py)
and the command line's --start, --pause, --stop sent to the running
instance. Each opens what it needs in front of what the user is doing;
the keys are set in Settings → Generale.
"""

import os
import time

from PyQt6.QtCore import QObject, QSettings, Qt, QTimer, pyqtSignal as Signal
from PyQt6.QtGui import QKeySequence
from PyQt6.QtWidgets import (
    QApplication, QCheckBox, QDialog, QDialogButtonBox, QGridLayout, QGroupBox, QHBoxLayout, QKeySequenceEdit,
    QLabel, QListWidget, QListWidgetItem, QPushButton, QVBoxLayout,
)

from activitytrack.i18n import _
from activitytrack.texts import state_label
from activitytrack.work import PAUSE, STOP, TO_COMPLETE, WORK, WorkError

from . import hotkeys
from .targets import pause_target, resume_target, stop_target

ACTIONS = ("start", "pause", "stop")
# the commands the single instance's socket takes (one per line; "show" is the old client's)
COMMANDS = ACTIONS + ("show",)
DEFAULTS = {"start": "Ctrl+Alt+A", "pause": "Ctrl+Alt+P", "stop": "Ctrl+Alt+S"}
GROUP = "globalShortcuts"
# a key held down, or pressed twice by mistake: one command
REPEAT_S = 0.5


# ---- the settings ----

def saved():
    """{action: (enabled, QKeySequence)}, the defaults where nothing was saved."""
    s = QSettings()
    out = {}
    for a in ACTIONS:
        keys = s.value(f"{GROUP}/{a}/keys", DEFAULTS[a])
        on = s.value(f"{GROUP}/{a}/enabled", True, type=bool)
        out[a] = (on, QKeySequence.fromString(str(keys or ""), QKeySequence.SequenceFormat.PortableText))
    return out


def save(action, enabled, seq):
    s = QSettings()
    s.setValue(f"{GROUP}/{action}/keys", seq.toString(QKeySequence.SequenceFormat.PortableText))
    s.setValue(f"{GROUP}/{action}/enabled", bool(enabled))


def reset():
    QSettings().remove(GROUP)


# ---- the shortcuts ----

class GlobalShortcuts(QObject):
    """
    The backend of this desktop with the saved keys; [triggered](action)
    in the GUI thread, after the backend's own handler has returned.
    """

    triggered = Signal(str)
    changed = Signal()

    def __init__(self, backends=None, parent=None, **where):
        super().__init__(parent)
        self.backend, self.reasons = hotkeys.choose(backends=backends, **where)
        self.applied = None
        self.invalid = []
        self._last = {}
        if self.backend is not None:
            self.backend.setParent(self)
            self.backend.activated.connect(self._activated)
            self.backend.changed.connect(self.changed)

    def wanted(self):
        """{action: QKeySequence} of the shortcuts switched on that a backend can take; the others in [invalid]."""
        out, self.invalid = {}, []
        for a, (on, seq) in saved().items():
            if not on or seq.isEmpty():
                continue
            if hotkeys.parse(seq) is None:
                self.invalid.append(a)
            else:
                out[a] = seq
        return out

    def apply(self):
        """The saved keys to the backend (again only when they changed: the portal asks the user)."""
        wanted = self.wanted()
        key = {a: s.toString(QKeySequence.SequenceFormat.PortableText) for a, s in wanted.items()}
        if self.backend is not None and key != self.applied:
            self.applied = key
            self.backend.bind(wanted)
        self.changed.emit()

    def _activated(self, action):
        now = time.monotonic()
        if now - self._last.get(action, -REPEAT_S) < REPEAT_S:
            return
        self._last[action] = now
        # out of the backend's handler: the command may open a dialog with its own event loop
        QTimer.singleShot(0, lambda: self.triggered.emit(action))

    def status(self):
        """What the settings say: the backend in use and the shortcuts refused, or why there is none."""
        names = hotkeys.action_names()
        lines = []
        if self.backend is None:
            why = "; ".join(r for _k, r in self.reasons) or _("desktop non supportato")
            lines.append(_("Non disponibili su questo desktop: %s.") % why)
        elif not self.applied:
            lines.append(_("Nessuna scorciatoia attiva."))
        else:
            lines.append(_("Attive tramite %s.") % self.backend.title())
            state = self.backend.state()
            if state:
                lines.append(state)
            triggers = getattr(self.backend, "triggers", {})
            for a in ACTIONS:
                if triggers.get(a):
                    lines.append(f"{names[a]}: {triggers[a]}")
            for a, why in sorted(self.backend.errors.items()):
                lines.append(_("%s: non attiva, %s.") % (names.get(a, a), why))
        for a in self.invalid:
            lines.append(_("%s: combinazione non valida (serve Ctrl, Alt o Super).") % names.get(a, a))
        return "\n".join(lines)

    def close(self):
        if self.backend is not None:
            self.backend.close()


# ---- the commands ----

def front(widget):
    """In front of what the user is doing (on Wayland the desktop may only flash it)."""
    widget.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
    widget.show()
    widget.raise_()
    widget.activateWindow()


class ChooseDialog(QDialog):
    """Which activity: the list of the candidates, the most recent first and selected."""

    def __init__(self, work, uids, title, parent=None):
        super().__init__(parent)
        self.setWindowTitle("ActivityTrack")
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(title))
        self.list = QListWidget()
        for uid in uids:
            e = work.entry(uid)
            item = QListWidgetItem(f"{work.label(e)} — {state_label(e)}")
            item.setData(Qt.ItemDataRole.UserRole, uid)
            self.list.addItem(item)
        self.list.setCurrentRow(0)
        self.list.itemActivated.connect(lambda _item: self.accept())
        lay.addWidget(self.list)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

    def chosen(self):
        item = self.list.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item is not None else None


def choose(work, uids, title):
    d = ChooseDialog(work, uids, title)
    front(d)
    return d.chosen() if d.exec() else None


class Commands(QObject):
    """start, pause (pause or resume), stop, show: run in the GUI thread through the Actions."""

    def __init__(self, actions, window, notifier, parent=None):
        super().__init__(parent)
        self.actions, self.window, self.notifier = actions, window, notifier
        self._busy = False
        notifier.answered.connect(lambda key, _action: key == "shortcut" and window.show_up())

    def received(self, line):
        """A line of the single instance's socket: a command, and the launcher's activation token."""
        words = line.split()
        command = words[0] if words and words[0] in COMMANDS else "show"
        token = words[1] if len(words) > 1 else None
        QTimer.singleShot(0, lambda: self.run(command, token))

    def run(self, command, token=None):
        if token:
            # Wayland: the token of the launcher lets the dialog take the focus
            os.environ["XDG_ACTIVATION_TOKEN"] = token
        if self._busy:
            # a dialog of the previous command is open: in front again
            modal = QApplication.activeModalWidget()
            if modal is not None:
                front(modal)
            return
        if command == "show" or self.actions.session.account is None:
            self.window.show_up()
            return
        self._busy = True
        try:
            self.actions.refresh_policy()
            {"start": self.start, "pause": self.pause, "stop": self.stop}[command]()
        finally:
            self._busy = False

    def _tell(self, text):
        self.notifier.show("shortcut", "ActivityTrack", text, persistent=False)

    def _pick(self, target, title):
        if isinstance(target, list):
            return choose(self.actions.work, target, title)
        return target

    def start(self):
        if not self.actions.work.policy.feature("entries"):
            self.window.show_up()
            return
        self.actions.new_entry()

    def pause(self):
        work = self.actions.work
        uid = self._pick(pause_target(work), _("Quale attività mettere in pausa?"))
        if uid is not None:
            return self._command(uid, PAUSE, _("In pausa: %s"))
        target = resume_target(work)
        if target is None:
            return self._tell(_("Nessuna attività da mettere in pausa o da riprendere."))
        uid = self._pick(target, _("Quale attività riprendere?"))
        if uid is not None:
            self._command(uid, WORK, _("Ripresa: %s"))

    def _command(self, uid, cmd, said):
        work = self.actions.work
        try:
            label = work.label(work.entry(uid))
            work.command(uid, cmd)
        except WorkError as e:
            self.actions._fail(e)
            return
        self.actions._done()
        self._tell(said % label)

    def stop(self):
        work = self.actions.work
        target = stop_target(work, getattr(self.window, "focused_uid", None))
        if target is None:
            return self._tell(_("Nessuna attività in corso."))
        uid = self._pick(target, _("Quale attività fermare?"))
        if uid is None:
            return
        # the stop of the Actions, with the sheet in front
        from . import forms
        try:
            label = work.label(work.entry(uid))
            status = work.command(uid, STOP)
        except WorkError as e:
            self.actions._fail(e)
            return
        self.actions._done()
        if status == TO_COMPLETE:
            d = forms.StopDialog(work, uid)
            front(d)
            d.exec()
            self.actions._done()
        else:
            self._tell(_("Fermata: %s") % label)


# ---- Settings → Generale ----

class ShortcutsBox(QGroupBox):
    """Each action with its keys and a switch; the backend's state; the defaults back."""

    def __init__(self, shortcuts, parent=None):
        super().__init__(_("Scorciatoie globali"), parent)
        self.shortcuts = shortcuts
        lay = QVBoxLayout(self)
        grid = QGridLayout()
        names = hotkeys.action_names()
        self.checks, self.edits = {}, {}
        for row, a in enumerate(ACTIONS):
            check = QCheckBox(names[a])
            edit = QKeySequenceEdit()
            if hasattr(edit, "setMaximumSequenceLength"):
                # Qt 6.5: one combination; before, the first is kept
                edit.setMaximumSequenceLength(1)
            if hasattr(edit, "setClearButtonEnabled"):
                edit.setClearButtonEnabled(True)
            check.toggled.connect(lambda _on, a=a: self._save(a))
            edit.editingFinished.connect(lambda a=a: self._save(a))
            grid.addWidget(check, row, 0)
            grid.addWidget(edit, row, 1)
            self.checks[a], self.edits[a] = check, edit
        lay.addLayout(grid)
        self.state = QLabel(wordWrap=True, textFormat=Qt.TextFormat.PlainText)
        lay.addWidget(self.state)
        hint = QLabel(_("Nelle impostazioni della tastiera del desktop si possono anche assegnare dei tasti ai "
                        "comandi «activitytrack-desktop --start», «--pause» e «--stop»."), wordWrap=True)
        hint.setStyleSheet("color: palette(placeholder-text)")
        lay.addWidget(hint)
        row = QHBoxLayout()
        self.reset = QPushButton(_("Ripristina predefinite"), clicked=self._reset)
        row.addWidget(self.reset)
        row.addStretch()
        lay.addLayout(row)
        shortcuts.changed.connect(self._state)
        self.load()

    def load(self):
        for a, (on, seq) in saved().items():
            for w in (self.checks[a], self.edits[a]):
                w.blockSignals(True)
            self.checks[a].setChecked(on)
            self.edits[a].setKeySequence(seq)
            self.edits[a].setEnabled(on)
            for w in (self.checks[a], self.edits[a]):
                w.blockSignals(False)
        self._state()

    def _save(self, action):
        seq = self.edits[action].keySequence()
        if seq.count() > 1:
            seq = QKeySequence(seq[0])
            self.edits[action].setKeySequence(seq)
        on = self.checks[action].isChecked()
        self.edits[action].setEnabled(on)
        save(action, on, seq)
        self.shortcuts.apply()

    def _reset(self):
        reset()
        self.load()
        self.shortcuts.apply()

    def _state(self):
        self.state.setText(self.shortcuts.status())
