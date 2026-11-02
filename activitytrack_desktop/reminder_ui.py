# SPDX-License-Identifier: GPL-3.0-or-later
"""
The reminders on the desktop (docs/DESIGN.md §7): one timer for the next
reminder, the notifications with the app's buttons, the answers, each
reminder switchable by the user, the intervals within the policy.
"""

from datetime import datetime, timedelta

from PyQt6.QtCore import QObject, QSettings, QTimer
from PyQt6.QtWidgets import (
    QCheckBox, QDialog, QDialogButtonBox, QFormLayout, QGroupBox, QLabel, QSpinBox, QVBoxLayout, QWidget,
)

from activitytrack import formats, reminders as R
from activitytrack.i18n import _
from activitytrack.texts import clock
from activitytrack.work import PAUSE, STOP, TO_COMPLETE, WORK, WorkError

from .notify import DEFAULT

# switched on by default (docs/DESIGN.md §7)
SWITCHES = {
    R.CONFIRM: _("«Ancora su …?» mentre un'attività è in corso"),
    R.PAUSE_KIND: _("«Ancora in pausa?»"),
    R.PLANNED: _("Da fare pianificato in arrivo"),
    R.DAY_START: _("Nessuna attività all'inizio della giornata"),
    R.PLANNED_END: _("Fine prevista di un'attività"),
}
INTERVALS = {
    "confirmIntervalMin": _("«Ancora su …?» ogni (min)"),
    "maxConfirmations": _("Al massimo, senza risposta (0 = sempre)"),
    "pauseIntervalMin": _("«Ancora in pausa?» ogni (min)"),
    "dayStartDelayMin": _("Inizio giornata: dopo (min)"),
    "planLeadMin": _("Da fare pianificato: prima (min)"),
    "planSnoozeMin": _("Posticipa di (min)"),
}
# the longest wait of the timer: a change elsewhere, a time-zone change or a sleep is seen within it
MAX_WAIT_MS = 10 * 60_000


def switched_on(kind):
    return QSettings().value(f"reminders/on/{kind}", True, type=bool)


def local_intervals():
    s = QSettings()
    return {k: s.value(f"reminders/{k}", type=int) for k in R.DEFAULTS if s.contains(f"reminders/{k}")}


class Reminders(QObject):
    def __init__(self, actions, notifier, show_window, parent=None):
        super().__init__(parent)
        self.actions = actions
        self.notifier = notifier
        self.show_window = show_window
        self.sources = R.Sources(actions.work, actions.todos)
        self.timer = QTimer(self, singleShot=True, timeout=self.fire)
        notifier.answered.connect(self.answer)
        actions.changed.connect(self.arm)
        actions.redraw.connect(self.arm)
        actions.reminders = self

    def config(self):
        return R.config_of(self.actions.work.policy, local_intervals())

    def _inputs(self, now):
        tz = self.actions.todos.tz()
        store = self.sources
        planner = R.Planner(self.config(), store.windows("workSchedule"), store.windows("lunchBreak"), tz,
                            store.days_off())
        entries = store.entries(tz)
        todos = store.planned_todos(tz, now) if self.actions.work.policy.feature("todos") else []
        day = store.day_start_state(tz, now.date()) if switched_on(R.DAY_START) else None
        return planner, entries, todos, day

    def _now(self):
        return datetime.now(self.actions.todos.tz())

    def _enabled(self, r):
        return switched_on(r.kind)

    def arm(self):
        """The timer for the next reminder switched on; at most MAX_WAIT_MS ahead."""
        if self.actions.session.account is None:
            self.timer.stop()
            return
        now = self._now()
        planner, entries, todos, day = self._inputs(now)
        reminders = [r for r in planner.planned(entries, todos, now, day) if self._enabled(r)]
        if any(r.at <= now for r in reminders):
            wait = 1000
        else:
            later = [r.at for r in reminders]
            wait = int((min(later) - now).total_seconds() * 1000) + 500 if later else MAX_WAIT_MS
        self.timer.start(max(1000, min(wait, MAX_WAIT_MS)))

    def fire(self):
        if self.actions.session.account is None:
            return
        now = self._now()
        planner, entries, todos, day = self._inputs(now)
        for r in planner.due(entries, todos, now, day):
            if self._enabled(r):
                self.post(r)
            # recorded even when switched off: switching it on does not bring back the old ones
            self.sources.reminded(r, self.actions.work.clock())
        self.arm()

    # ---- the notifications ----

    def _title(self, uid):
        e = self.actions.session.store.get("entry", uid) or {}
        w = self.actions.work
        return w.name("client", e.get("clientUid")) or w.name("company", e.get("companyUid")) or "ActivityTrack"

    def message(self, r):
        """(title, body, [(action, label)]) of a reminder, as the app's (ReminderNotifications.kt)."""
        w = self.actions.work
        if r.kind == R.CONFIRM:
            last = self.sources.last_confirmed(r.key)
            hhmm = clock(last) if last else ""
            return (_("Ancora su %s?") % self._title(r.key), _("Ultima conferma alle %s") % hhmm,
                    [("yes", _("Sì")), ("pause", _("Pausa")), ("stop_at", _("Stop alle %s") % hhmm)])
        if r.kind == R.PAUSE_KIND:
            return (_("Ancora in pausa?"), self._title(r.key), [("resume", _("Riprendi")), ("stop", _("Stop"))])
        if r.kind == R.DAY_START:
            return (_("Nessuna attività oggi"), _("Registra un'assenza o avvia un'attività."),
                    [("absent", _("Assente tutto il giorno")), ("start", _("Avvia un'attività"))])
        if r.kind == R.PLANNED:
            t = self.actions.session.store.get("todo", r.key) or {}
            start = r.at + timedelta(minutes=self.config()["planLeadMin"])
            who = w.name("client", t.get("clientUid")) or w.name("company", t.get("companyUid"))
            return (_("%s alle %s") % (t.get("title") or "", formats.time(start)), who,
                    [("start", _("Avvia")), ("postpone", _("Posticipa di %d min") % self.config()["planSnoozeMin"]),
                     ("replan", _("Ripianifica"))])
        e = self.actions.session.store.get("entry", r.key) or {}
        end = clock(e.get("plannedEndUtcMs") or 0)
        return (_("%s finita?") % self._title(r.key), _("Fine prevista %s") % end,
                [("stop", _("Sì, stop alle %s") % end), ("go_on", _("No, continua"))])

    def post(self, r):
        title, body, buttons = self.message(r)
        self.notifier.show(f"{r.kind}|{r.key}", title, body, buttons)

    def answer(self, key, action):
        kind, _sep, uid = key.partition("|")
        if kind not in R.KINDS:
            # another notification (an update)
            return
        if action == DEFAULT:
            if self.notifier.native:
                self.show_window()
                return
            # no buttons on the notification (Windows): the question in a window
            r = R.Reminder(kind, uid, self._now())
            title, body, buttons = self.message(r)
            action = ask(title, body, buttons)
            if action is None:
                return
        try:
            self.dispatch(kind, uid, action)
        except WorkError as e:
            self.actions._fail(e)
        self.arm()

    def dispatch(self, kind, uid, action):
        a = self.actions
        w = a.work
        now = w.clock()
        if kind == R.CONFIRM:
            if action == "yes":
                self.sources.confirmed(uid, now)
            elif action == "pause":
                a.command(uid, PAUSE)
            elif action == "stop_at":
                self.stop_at(uid, self.sources.last_confirmed(uid) or now)
        elif kind == R.PAUSE_KIND:
            a.command(uid, WORK if action == "resume" else STOP)
        elif kind == R.DAY_START:
            if action == "absent":
                w.absent_all_day(datetime.fromisoformat(uid).date())
                a.changed.emit()
            else:
                a.new_entry()
        elif kind == R.PLANNED:
            {"start": a.start_todo, "postpone": a.todo_postpone, "replan": a.edit_todo}[action](uid)
        elif kind == R.PLANNED_END:
            if action == "stop":
                e = a.session.store.get("entry", uid) or {}
                self.stop_at(uid, e.get("plannedEndUtcMs") or now)
            else:
                w.go_on(uid)
                a.changed.emit()

    def stop_at(self, uid, at_ms):
        """Stop at a past time ("when I last said yes", the planned end), then the stop sheet if needed."""
        from . import forms
        a = self.actions
        status = a.work.command(uid, STOP, at=at_ms)
        if status == TO_COMPLETE:
            forms.StopDialog(a.work, uid, a._parent()).exec()
        a.changed.emit()


def ask(title, body, buttons):
    """The question of a notification without buttons: the action chosen, or None."""
    d = QDialog()
    d.setWindowTitle("ActivityTrack")
    lay = QVBoxLayout(d)
    head = QLabel(f"<b>{title}</b>")
    head.setWordWrap(True)
    lay.addWidget(head)
    if body:
        lay.addWidget(QLabel(body, wordWrap=True))
    box = QDialogButtonBox()
    chosen = []
    for action, label in buttons:
        b = box.addButton(label, QDialogButtonBox.ButtonRole.ActionRole)
        b.clicked.connect(lambda _c=False, a=action: (chosen.append(a), d.accept()))
    lay.addWidget(box)
    d.exec()
    return chosen[0] if chosen else None


class ReminderSettings(QWidget):
    """Settings → Promemoria: each reminder on or off, the intervals (greyed when the policy fixes them)."""

    def __init__(self, actions, notifier, parent=None):
        super().__init__(parent)
        self.actions = actions
        lay = QVBoxLayout(self)
        title = QLabel(_("Promemoria"))
        title.setStyleSheet("font-size: 18pt")
        lay.addWidget(title)
        box = QGroupBox(_("Mostra"))
        bl = QVBoxLayout(box)
        settings = QSettings()
        self.switches = {}
        for kind, label in SWITCHES.items():
            c = QCheckBox(label, checked=switched_on(kind))
            c.toggled.connect(lambda on, k=kind: (settings.setValue(f"reminders/on/{k}", on), actions.redraw.emit()))
            bl.addWidget(c)
            self.switches[kind] = c
        lay.addWidget(box)
        form = QFormLayout()
        self.spins = {}
        for key, label in INTERVALS.items():
            lo, hi = R.LIMITS[key]
            s = QSpinBox(minimum=lo, maximum=hi)
            s.valueChanged.connect(lambda v, k=key: (settings.setValue(f"reminders/{k}", v), actions.redraw.emit()))
            form.addRow(label, s)
            self.spins[key] = s
        lay.addLayout(form)
        note = QLabel(_("Le notifiche hanno i pulsanti delle risposte.") if notifier.native else _(
            "Le notifiche di questo desktop non hanno pulsanti: un clic apre la domanda in una finestra."))
        note.setWordWrap(True)
        note.setStyleSheet("color: palette(placeholder-text)")
        lay.addWidget(note)
        lay.addWidget(QLabel(_("Il telefono mostra gli stessi promemoria. Una risposta che cambia l'attività o il "
                               "Da fare (pausa, stop, avvio) vale anche sull'altro dispositivo; un «Sì» resta "
                               "su quello dove lo dai."), wordWrap=True))
        lay.addStretch()
        self.refresh()

    def refresh(self):
        policy = self.actions.work.policy
        config = R.config_of(policy, local_intervals())
        for key, s in self.spins.items():
            s.blockSignals(True)
            s.setValue(config[key])
            s.blockSignals(False)
            fixed = policy.setting_fixed(key)
            s.setEnabled(not fixed)
            s.setToolTip(_("Impostato dalla policy") if fixed else "")
