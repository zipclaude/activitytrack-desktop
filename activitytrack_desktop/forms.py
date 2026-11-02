# SPDX-License-Identifier: GPL-3.0-or-later
"""
The activity forms (docs/DESIGN.md §6.2–6.3): the quick entry, keyboard
first; the full form, new or existing; the stop sheet; a segment's times.
Every field takes free text: company, client and role complete from the
master data, a new name becomes a personal record when the policy allows.
"""

from datetime import date

from PyQt6.QtCore import QDate, QDateTime, QTime, Qt
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QCompleter, QDateEdit, QDateTimeEdit, QDialog, QDialogButtonBox, QFormLayout, QGroupBox,
    QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPlainTextEdit, QPushButton, QRadioButton, QSpinBox, QTimeEdit,
    QVBoxLayout, QWidget,
)

from activitytrack import formats
from activitytrack.i18n import _
from activitytrack.texts import KINDS, clock, error_text, field_label, hm, state_label
from activitytrack.work import (
    ACTIVE, PAUSE, STOP, SUSPEND, TO_COMPLETE, TRAVEL, WORK, StartRequest, WorkError,
)

from .timegrid_ui import attach_range, attach_single

KEEP = "KEEP"


def _ms(edit):
    return edit.dateTime().toMSecsSinceEpoch()


def _datetime(ms):
    return QDateTime.fromMSecsSinceEpoch(int(ms))


def _formatted(*edits):
    """Date and time edits in the user's formats (European, American, ISO; 24 or 12 hours)."""
    for e in edits:
        if isinstance(e, QDateTimeEdit) and not isinstance(e, (QDateEdit, QTimeEdit)):
            e.setDisplayFormat(f"{formats.qt_date()} {formats.qt_time()}")
        elif isinstance(e, QDateEdit):
            e.setDisplayFormat("ddd " + formats.qt_date())
        else:
            e.setDisplayFormat(formats.qt_time())


def _follow_client(company, client):
    """A known client chosen brings its company, as in the app."""
    def follow():
        uid = client.value()
        r = client.work.store.get("client", uid) if uid else None
        if r and r.get("companyUid") and company.value() != r["companyUid"]:
            company.set_value(r["companyUid"])
            client.set_value(uid)
    client.activated.connect(lambda _i: follow())


def _row(*widgets):
    w = QWidget()
    lay = QHBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 0)
    for x in widgets:
        lay.addWidget(x)
    lay.addStretch()
    return w


class MasterCombo(QComboBox):
    """A master record picked from the list or typed freely."""

    def __init__(self, work, type_, parent=None):
        super().__init__(parent)
        self.work, self.type_ = work, type_
        self.setEditable(True)
        self.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        c = self.completer()
        c.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        c.setFilterMode(Qt.MatchFlag.MatchContains)
        c.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        self.fill()

    def fill(self, company=None):
        text = self.currentText()
        self.blockSignals(True)
        self.clear()
        self.addItem("", None)
        for r in self.work.masters(self.type_, company):
            name = r.get("name") or r.get("text") or ""
            self.addItem(name, r["uid"])
            if self.type_ == "client" and company is None and r.get("companyUid"):
                self.setItemData(self.count() - 1, self.work.name("company", r["companyUid"]),
                                 Qt.ItemDataRole.ToolTipRole)
        self.setEditText(text)
        self.blockSignals(False)

    def value(self):
        """The chosen record's uid, or the text typed (None when empty)."""
        text = self.currentText().strip()
        if not text:
            return None
        i = self.currentIndex()
        if i > 0 and self.itemText(i) == text:
            return self.itemData(i)
        return text

    def set_value(self, value):
        """A record's uid, or a name typed earlier."""
        i = self.findData(value) if value else -1
        if i >= 0:
            self.setCurrentIndex(i)
        else:
            self.setEditText((self.work.name(self.type_, value) or value) if value else "")


class Description(QPlainTextEdit):
    """Multi-line: from the PC descriptions are longer. Ctrl+Enter confirms the dialog."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTabChangesFocus(True)
        self.setMinimumHeight(70)

    def value(self):
        return self.toPlainText().strip()


def _tags_text(tags):
    return ", ".join(tags or [])


def _tags(text):
    return [t.strip() for t in text.split(",") if t.strip()]


class StartOptions(QWidget):
    """Work or travel, already done (start and end), and what to do with the activities running."""

    def __init__(self, work, parent=None):
        super().__init__(parent)
        self.work = work
        lay = QFormLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        modes = QHBoxLayout()
        self.work_mode = QRadioButton(KINDS[WORK], checked=True)
        self.travel_mode = QRadioButton(KINDS[TRAVEL])
        modes.addWidget(self.work_mode)
        modes.addWidget(self.travel_mode)
        modes.addStretch()
        self.travel_mode.setVisible(work.policy.feature("travel"))
        lay.addRow(_("Tipo"), modes)
        self.done = QCheckBox(_("Già fatta: indica inizio e fine"))
        lay.addRow("", self.done)
        self.start = QDateTimeEdit(QDateTime.currentDateTime().addSecs(-30 * 60), calendarPopup=True)
        self.end = QDateTimeEdit(QDateTime.currentDateTime(), calendarPopup=True)
        _formatted(self.start, self.end)
        for e in (self.start, self.end):
            e.setMaximumDateTime(QDateTime.currentDateTime().addSecs(60))
        grid_start, grid_end = attach_range(work, self.start, self.end, parent=self)
        times = QHBoxLayout()
        times.addWidget(self.start)
        times.addWidget(grid_start)
        times.addWidget(QLabel("→"))
        times.addWidget(self.end)
        times.addWidget(grid_end)
        times.addStretch()
        self.times = QWidget()
        self.times.setLayout(times)
        times.setContentsMargins(0, 0, 0, 0)
        lay.addRow(_("Quando"), self.times)
        self.times.setEnabled(False)
        self.done.toggled.connect(self.times.setEnabled)
        # the activities running: left running, suspended or stopped
        self.others = {}
        concurrent = work.policy.feature("concurrentEntries")
        for e in work.running():
            if e.get("status") != ACTIVE:
                continue
            c = QComboBox()
            if concurrent:
                c.addItem(_("Lasciala in corso"), KEEP)
            if e.get("mode") != PAUSE:
                c.addItem(_("Sospendila"), SUSPEND)
            c.addItem(_("Fermala"), STOP)
            # starting another activity usually means switching: the one at work is suspended
            if e.get("mode") != PAUSE:
                c.setCurrentIndex(c.findData(SUSPEND))
            self.others[e["uid"]] = c
            lay.addRow(work.label(e), c)

    def apply(self, req):
        req.mode = TRAVEL if self.travel_mode.isChecked() else WORK
        if self.done.isChecked():
            req.start_ms, req.end_ms = _ms(self.start), _ms(self.end)
            # an activity already done leaves the running ones as they are
            req.others = {}
        else:
            req.others = {u: c.currentData() for u, c in self.others.items() if c.currentData() != KEEP}
        return req


class _Dialog(QDialog):
    def __init__(self, title, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.lay = QVBoxLayout(self)
        self.message = QLabel(wordWrap=True)
        self.message.setStyleSheet("color: #c62828")
        self.message.hide()

    def fail(self, e):
        self.message.setText(error_text(e) if isinstance(e, WorkError) else str(e))
        self.message.show()

    def buttons(self, ok_text, extra=(), cancel=True):
        box = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel if cancel else
                               QDialogButtonBox.StandardButton.NoButton)
        self.ok = box.addButton(ok_text, QDialogButtonBox.ButtonRole.AcceptRole)
        self.ok.setDefault(True)
        for text, slot in extra:
            box.addButton(text, QDialogButtonBox.ButtonRole.ActionRole).clicked.connect(slot)
        box.accepted.connect(self.confirm)
        box.rejected.connect(self.reject)
        QShortcut(QKeySequence("Ctrl+Return"), self, activated=self.confirm)
        QShortcut(QKeySequence("Ctrl+Enter"), self, activated=self.confirm)
        self.lay.addWidget(self.message)
        self.lay.addWidget(box)


class QuickEntry(_Dialog):
    """A new activity with the main fields; "Altri campi…" opens the full form with what was typed."""

    def __init__(self, work, parent=None, todo=None):
        super().__init__(_("Nuova attività"), parent)
        self.work = work
        self.todo = todo
        self.result_uid = None
        self.setMinimumWidth(520)
        p = work.policy
        form = QFormLayout()
        self.description = Description()
        form.addRow(field_label(p, "description"), self.description)
        self.client = MasterCombo(work, "client")
        form.addRow(field_label(p, "client"), self.client)
        self.tags = QLineEdit(placeholderText=_("separati da virgole"))
        if p.field("tags").visible:
            form.addRow(field_label(p, "tags"), self.tags)
        self.lay.addLayout(form)
        self.options = StartOptions(work)
        self.lay.addWidget(self.options)
        if todo:
            self.description.setPlainText(todo.get("title") or "")
            self.client.set_value(todo.get("clientUid"))
        hint = QLabel(_("Ctrl+Invio per avviare"))
        hint.setStyleSheet("color: palette(placeholder-text)")
        self.lay.addWidget(hint)
        self.buttons(_("Avvia"), [(_("Altri campi…"), self.more)])
        self.description.setFocus()

    def request(self):
        req = StartRequest(activity=self.description.value(), client=self.client.value(),
                           tags=_tags(self.tags.text()), todo=self.todo["uid"] if self.todo else None)
        return self.options.apply(req)

    def confirm(self):
        try:
            self.result_uid = self.work.start(self.request())
        except WorkError as e:
            self.fail(e)
            return
        self.accept()

    def more(self):
        d = EntryDialog(self.work, self.parent(), start=self.request())
        self.hide()
        if d.exec():
            self.result_uid = d.result_uid
            self.accept()
        else:
            self.show()


class EntryDialog(_Dialog):
    """Every field the policy shows; for an existing activity its times too."""

    def __init__(self, work, parent=None, uid=None, start=None):
        super().__init__(_("Attività") if uid else _("Nuova attività"), parent)
        self.work, self.uid = work, uid
        self.result_uid = uid
        self.setMinimumWidth(600)
        p = work.policy
        e = work.entry(uid) if uid else {}
        form = QFormLayout()
        self.fields = {}

        def add(name, widget):
            rule = p.field(name)
            if not rule.visible:
                return
            widget.setEnabled(rule.enabled)
            label = field_label(p, name) + (" *" if rule.required else "")
            form.addRow(label, widget)
            self.fields[name] = widget

        self.company = MasterCombo(work, "company")
        self.client = MasterCombo(work, "client")
        self.role = MasterCombo(work, "role")
        self.preset = QComboBox()
        self.preset.addItem("", None)
        for r in work.masters("preset"):
            self.preset.addItem(r.get("text") or "", r["uid"])
        self.description = Description()
        self.locality = QLineEdit()
        self.notes = QPlainTextEdit()
        self.notes.setTabChangesFocus(True)
        self.notes.setMaximumHeight(90)
        self.tags = QLineEdit(placeholderText=_("separati da virgole"))
        add("company", self.company)
        add("client", self.client)
        add("role", self.role)
        if self.preset.count() > 1:
            add("quickPick", self.preset)
        add("description", self.description)
        add("locality", self.locality)
        add("notes", self.notes)
        add("tags", self.tags)
        self.company.currentTextChanged.connect(self._company_changed)
        _follow_client(self.company, self.client)
        self.preset.activated.connect(self._preset)
        self.lay.addLayout(form)

        if uid:
            self.company.set_value(e.get("companyUid"))
            self.client.set_value(e.get("clientUid"))
            self.role.set_value(e.get("roleUid"))
            self.description.setPlainText(e.get("activity") or "")
            self.locality.setText(e.get("locality") or "")
            self.notes.setPlainText(e.get("notes") or "")
            self.tags.setText(_tags_text(e.get("tags")))
            self._times_box(e)
            extra = []
            if p.feature("deleteEntries"):
                extra.append((_("Elimina"), self.delete))
            self.buttons(_("Salva"), extra)
        else:
            self.options = StartOptions(work)
            self.lay.addWidget(self.options)
            if start is not None:
                self.description.setPlainText(start.activity)
                self.client.set_value(start.client)
                self.tags.setText(_tags_text(start.tags))
            self.todo = start.todo if start is not None else None
            self.buttons(_("Avvia"))

    def _company_changed(self):
        company = self.company.value()
        known = company if company and self.work.store.get("company", company) else None
        self.client.fill(known)

    def _preset(self):
        uid = self.preset.currentData()
        r = self.work.store.get("preset", uid) if uid else None
        if r is None:
            return
        if not self.description.value():
            self.description.setPlainText(r.get("text") or "")
        if r.get("defaultRoleUid") and not self.role.value():
            self.role.set_value(r["defaultRoleUid"])
        if r.get("companyUid") and not self.company.value():
            self.company.set_value(r["companyUid"])

    def _times_box(self, e):
        box = QGroupBox(field_label(self.work.policy, "times"))
        lay = QVBoxLayout(box)
        totals = self.work.totals(e["uid"])
        lay.addWidget(QLabel(f"{state_label(e)} · {KINDS[WORK]} {hm(totals[WORK])} · {KINDS[TRAVEL]} "
                             f"{hm(totals[TRAVEL])} · {KINDS[PAUSE]} {hm(totals[PAUSE])}"))
        editable = self.work.policy.setting("editableTimes", True)
        for s in self.work.segments(e["uid"]):
            row = QHBoxLayout()
            end = clock(s["endUtcMs"]) if s.get("endUtcMs") else _("in corso")
            row.addWidget(QLabel(f"{KINDS.get(s['kind'], s['kind'])}  {clock(s['startUtcMs'])} – {end}"))
            row.addStretch()
            if editable:
                row.addWidget(QPushButton(_("Modifica…"), clicked=lambda _c=False, s=s: self._segment(s)))
                if s.get("endUtcMs"):
                    row.addWidget(QPushButton(_("Elimina"), clicked=lambda _c=False, s=s: self._remove(s)))
            lay.addLayout(row)
        if editable and e.get("status") != ACTIVE:
            row = QHBoxLayout()
            row.addStretch()
            row.addWidget(QPushButton(_("Aggiungi un tratto…"), clicked=lambda: self._segment(None)))
            lay.addLayout(row)
        if e.get("needsReview"):
            warn = QLabel(_("Da verificare: due tratti si sovrappongono."))
            warn.setStyleSheet("color: #c62828")
            lay.addWidget(warn)
        self.lay.addWidget(box)

    def _segment(self, s):
        d = SegmentDialog(self.work, self.uid, s, self)
        if d.exec():
            self._reopen()

    def _remove(self, s):
        try:
            self.work.remove_segment(s["uid"])
        except WorkError as e:
            self.fail(e)
            return
        self._reopen()

    def _reopen(self):
        # the times changed: the form shows them again
        self.done(2)

    def values(self):
        return dict(
            activity=self.description.value(), client=self.client.value() or "", company=self.company.value() or "",
            role=self.role.value() or "", locality=self.locality.text(), notes=self.notes.toPlainText(),
            tags=_tags(self.tags.text()),
        )

    def confirm(self):
        v = self.values()
        try:
            if self.uid:
                self.work.edit(self.uid, **v)
            else:
                req = StartRequest(activity=v["activity"], client=v["client"] or None, company=v["company"] or None,
                                   role=v["role"] or None, locality=v["locality"], notes=v["notes"], tags=v["tags"],
                                   todo=self.todo)
                self.result_uid = self.work.start(self.options.apply(req))
        except WorkError as e:
            self.fail(e)
            return
        self.accept()

    def delete(self):
        text = _("Eliminare questa attività? Si elimina anche sugli altri dispositivi.")
        ok = QMessageBox.question(self, _("Elimina"), text)
        if ok != QMessageBox.StandardButton.Yes:
            return
        try:
            self.work.delete(self.uid)
        except WorkError as e:
            self.fail(e)
            return
        self.accept()


def edit_entry(work, uid, parent=None):
    """The full form of an activity; shown again after its times changed."""
    while True:
        d = EntryDialog(work, parent, uid=uid)
        r = d.exec()
        if r != 2:
            return r


class SegmentDialog(_Dialog):
    """A stretch of time: its kind, start and end (the running one keeps no end)."""

    def __init__(self, work, entry_uid, segment=None, parent=None):
        super().__init__(_("Tratto") if segment else _("Nuovo tratto"), parent)
        self.work, self.entry_uid, self.segment = work, entry_uid, segment
        form = QFormLayout()
        self.kind = QComboBox()
        for k in (WORK, TRAVEL, PAUSE):
            if k != TRAVEL or work.policy.feature("travel"):
                self.kind.addItem(KINDS[k], k)
        running = segment is not None and segment.get("endUtcMs") is None
        now = QDateTime.currentDateTime()
        self.start = QDateTimeEdit(_datetime(segment["startUtcMs"]) if segment else now.addSecs(-1800),
                                   calendarPopup=True)
        self.end = QDateTimeEdit(_datetime(segment["endUtcMs"]) if segment and segment.get("endUtcMs") else now,
                                 calendarPopup=True)
        _formatted(self.start, self.end)
        if segment:
            self.kind.setCurrentIndex(max(0, self.kind.findData(segment["kind"])))
        self.kind.setEnabled(not running)
        self.end.setEnabled(not running)
        grid_start, grid_end = attach_range(work, self.start, self.end, skip=segment["uid"] if segment else None,
                                            parent=self)
        form.addRow(_("Tipo"), self.kind)
        form.addRow(_("Inizio"), _row(self.start, grid_start))
        form.addRow(_("Fine"), _row(self.end, grid_end) if not running else QLabel(_("in corso")))
        self.lay.addLayout(form)
        self.running = running
        self.buttons(_("Salva"))

    def confirm(self):
        try:
            end = None if self.running else _ms(self.end)
            if self.segment:
                self.work.edit_segment(self.segment["uid"], _ms(self.start), end, self.kind.currentData())
            else:
                self.work.add_segment(self.entry_uid, _ms(self.start), end, self.kind.currentData())
        except WorkError as e:
            self.fail(e)
            return
        self.accept()


class StopDialog(_Dialog):
    """
    After Stop, when details are missing or the activity came from a to-do:
    the description, the client and whether the to-do is done.
    """

    def __init__(self, work, uid, parent=None):
        super().__init__(_("Completa l'attività"), parent)
        self.work, self.uid = work, uid
        e = work.entry(uid)
        form = QFormLayout()
        self.description = Description()
        self.description.setPlainText(e.get("activity") or "")
        form.addRow(field_label(work.policy, "description"), self.description)
        self.client = MasterCombo(work, "client")
        self.client.set_value(e.get("clientUid"))
        form.addRow(field_label(work.policy, "client"), self.client)
        self.todo = work.store.get("todo", e["todoUid"]) if e.get("todoUid") else None
        self.todo_done = QCheckBox(_("Il Da fare «%s» è completato") % (self.todo or {}).get("title", ""))
        if self.todo and not self.todo.get("done"):
            form.addRow("", self.todo_done)
        self.lay.addLayout(form)
        # "Più tardi" is the way out: it keeps what was typed
        self.buttons(_("Chiudi l'attività"), [(_("Più tardi"), self.later)], cancel=False)

    def _save(self):
        self.work.edit(self.uid, activity=self.description.value(), client=self.client.value() or "")
        if self.todo is not None and self.todo_done.isChecked():
            now = self.work.clock()
            done = {"done": True, "doneUtcMs": now, "ignoredUtcMs": None, "updatedUtcMs": now}
            self.work.store.write("todo", self.todo["uid"], done, now)

    def confirm(self):
        try:
            self._save()
            if not self.description.value():
                ok = QMessageBox.question(self, self.windowTitle(), _(
                    "Chiudere senza descrizione? Va bene quando il lavoro si capisce dal cliente."))
                if ok != QMessageBox.StandardButton.Yes:
                    return
                self.work.complete(self.uid, allow_empty=True)
            else:
                self.work.complete(self.uid)
        except WorkError as e:
            self.fail(e)
            return
        self.accept()

    def later(self):
        try:
            self._save()
        except WorkError as e:
            self.fail(e)
            return
        self.reject()


def stop(work, uid, parent=None):
    """Stop, then the stop sheet when the activity is left to complete."""
    status = work.command(uid, STOP)
    if status == TO_COMPLETE:
        StopDialog(work, uid, parent).exec()
    return status


class _DayTime(QWidget):
    """An optional day with an optional time (a due date, a plan)."""

    def __init__(self, work, label, with_duration=False, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.on = QCheckBox(label)
        self.day = QDateEdit(QDate.currentDate(), calendarPopup=True)
        self.timed = QCheckBox(_("alle"))
        self.time = QTimeEdit(QTime(9, 0))
        _formatted(self.day, self.time)
        self.grid = attach_single(work, self.day, self.time, parent=self)
        for w in (self.on, self.day, self.timed, self.time, self.grid):
            lay.addWidget(w)
        self.duration = None
        if with_duration:
            self.duration = QSpinBox(minimum=0, maximum=24 * 60, singleStep=15, suffix=_(" min"))
            self.duration.setSpecialValueText(_("senza durata"))
            lay.addWidget(self.duration)
        lay.addStretch()
        self.on.toggled.connect(self._enable)
        self.timed.toggled.connect(self._enable)
        self._enable()

    def _enable(self):
        on = self.on.isChecked()
        self.day.setEnabled(on)
        self.timed.setEnabled(on)
        self.time.setEnabled(on and self.timed.isChecked())
        self.grid.setEnabled(on and self.timed.isChecked())
        if self.duration is not None:
            self.duration.setEnabled(on and self.timed.isChecked())

    def set(self, day, minute=None, duration=None):
        self.on.setChecked(bool(day))
        if day:
            self.day.setDate(QDate(day.year, day.month, day.day))
        self.timed.setChecked(minute is not None)
        if minute is not None:
            self.time.setTime(QTime(minute // 60, minute % 60))
        if self.duration is not None:
            self.duration.setValue(duration or 0)
        self._enable()

    def value(self):
        """(day, minute, duration) or Nones."""
        if not self.on.isChecked():
            return None, None, None
        d = self.day.date()
        day = date(d.year(), d.month(), d.day())
        if not self.timed.isChecked():
            return day, None, None
        t = self.time.time()
        duration = self.duration.value() or None if self.duration is not None else None
        return day, t.hour() * 60 + t.minute(), duration


class TodoDialog(_Dialog):
    """A to-do, new or existing: the fields the policy shows."""

    def __init__(self, todos, parent=None, uid=None, plan=None):
        super().__init__(_("Da fare") if uid else _("Nuovo Da fare"), parent)
        self.todos, self.uid = todos, uid
        self.result_uid = uid
        self.setMinimumWidth(560)
        work = todos.work
        p = work.policy
        t = todos.todo(uid) if uid else {}
        form = QFormLayout()
        self.title = QLineEdit(t.get("title") or "")
        form.addRow(_("Titolo"), self.title)
        self.company = MasterCombo(work, "company")
        self.client = MasterCombo(work, "client")
        if p.field("company").visible:
            form.addRow(field_label(p, "company"), self.company)
        form.addRow(field_label(p, "client"), self.client)
        _follow_client(self.company, self.client)
        self.notes = QPlainTextEdit(t.get("notes") or "")
        self.notes.setTabChangesFocus(True)
        self.notes.setMaximumHeight(110)
        form.addRow(field_label(p, "notes"), self.notes)
        self.refs = QPlainTextEdit(t.get("refs") or "")
        self.refs.setTabChangesFocus(True)
        self.refs.setMaximumHeight(60)
        self.refs.setPlaceholderText(_("ticket, link: uno per riga"))
        if p.field("refs").visible:
            form.addRow(_("Riferimenti"), self.refs)
        self.due = _DayTime(work, _("entro"))
        self.due.set(_iso(t.get("dueDate")), t.get("dueTimeMin"))
        if p.field("todoDue").visible:
            form.addRow(field_label(p, "todoDue"), self.due)
        self.plan = _DayTime(work, _("il"), with_duration=True)
        self.plan.set(_iso(t.get("planDate")), t.get("planStartMin"), t.get("durationMin"))
        if plan is not None:
            self.plan.set(*plan)
        if p.field("todoPlan").visible and p.feature("planning"):
            form.addRow(field_label(p, "todoPlan"), self.plan)
        self.priority = QComboBox()
        self.priority.addItem("—", None)
        for i in range(1, 6):
            self.priority.addItem(f"P{i}", i)
        self.priority.setCurrentIndex(max(0, self.priority.findData(t.get("priority"))))
        if p.field("todoPriority").visible:
            form.addRow(field_label(p, "todoPriority"), self.priority)
        if uid:
            self.company.set_value(t.get("companyUid"))
            self.client.set_value(t.get("clientUid"))
        self.lay.addLayout(form)
        extra = []
        if uid and p.feature("deleteTodos") and not t.get("externalKey"):
            extra.append((_("Elimina"), self.delete))
        self.buttons(_("Salva"), extra)
        self.title.setFocus()

    def confirm(self):
        due_day, due_min, _d = self.due.value()
        plan_day, plan_min, duration = self.plan.value()
        try:
            self.result_uid = self.todos.save(
                self.uid, self.title.text(), company=self.company.value(), client=self.client.value(),
                notes=self.notes.toPlainText(), refs=self.refs.toPlainText(), due_date=due_day, due_min=due_min,
                plan_date=plan_day, plan_min=plan_min, duration_min=duration, priority=self.priority.currentData())
        except WorkError as e:
            self.fail(e)
            return
        self.accept()

    def delete(self):
        if QMessageBox.question(self, _("Elimina"), _("Eliminare questo Da fare?")) != QMessageBox.StandardButton.Yes:
            return
        try:
            self.todos.delete(self.uid)
        except WorkError as e:
            self.fail(e)
            return
        self.accept()


def _iso(text):
    try:
        return date.fromisoformat(text) if text else None
    except ValueError:
        return None
