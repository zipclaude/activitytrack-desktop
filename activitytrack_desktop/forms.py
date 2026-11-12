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
    QButtonGroup, QCheckBox, QComboBox, QCompleter, QDateEdit, QDateTimeEdit, QDialog, QDialogButtonBox, QFormLayout,
    QGroupBox, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPlainTextEdit, QPushButton, QSpinBox, QTimeEdit,
    QVBoxLayout, QWidget,
)

from activitytrack import formats, model
from activitytrack.i18n import _
from activitytrack.texts import (
    ABSENCE_KINDS, KINDS, PRIORITIES, clock, display_label, entry_actions, error_text, field_label, hm,
)
from activitytrack.work import PAUSE, STOP, SUSPEND, TRAVEL, WORK, StartRequest, WorkError

from . import icons, states, theme, widgets as W
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
    lay.setSpacing(0 if widgets and widgets[0].property("seg") else 6)
    for x in widgets:
        lay.addWidget(x)
    lay.addStretch()
    return w


def _wrapped():
    """A form with the names above the fields, as the phone's."""
    form = QFormLayout()
    form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapAllRows)
    form.setVerticalSpacing(8)
    return form


def segmented(*choices):
    """The app's segmented buttons, one checked: [(text, icon)] → the buttons (the first one checked)."""
    group = QButtonGroup()
    out = []
    t = theme.tokens()
    for i, (text, icon) in enumerate(choices):
        b = QPushButton(text)
        b.setCheckable(True)
        b.setAutoDefault(False)
        b.setProperty("seg", "first" if i == 0 else "last" if i == len(choices) - 1 else "mid")
        b.setMinimumWidth(120)
        if icon:
            b.setIcon(icons.material(icon, t.text))
        group.addButton(b)
        out.append(b)
    out[0].setChecked(True)
    # the group lives with the first button
    group.setParent(out[0])
    return out


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
        lay.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapAllRows)
        lay.setVerticalSpacing(8)
        lay.setContentsMargins(0, 0, 0, 0)
        # the app's segmented buttons: work or travel, now or already done
        travel = work.policy.feature("travel")
        self.work_mode, self.travel_mode = segmented((KINDS[WORK], "play"), (KINDS[TRAVEL], "travel"))
        if travel:
            lay.addRow(_("Tipo"), _row(self.work_mode, self.travel_mode))
        self.now_mode, self.begun, self.done = segmented((_("Adesso"), None), (_("Già iniziata"), None),
                                                         (_("Passata"), None))
        self.begun.setToolTip(_("Già iniziata: indica l'inizio"))
        self.done.setToolTip(_("Passata: indica inizio e fine"))
        lay.addRow(_("Quando"), _row(self.now_mode, self.begun, self.done))
        self.start = QDateTimeEdit(QDateTime.currentDateTime().addSecs(-30 * 60), calendarPopup=True)
        self.end = QDateTimeEdit(QDateTime.currentDateTime(), calendarPopup=True)
        _formatted(self.start, self.end)
        for e in (self.start, self.end):
            e.setMaximumDateTime(QDateTime.currentDateTime().addSecs(60))
        grid_start, grid_end = attach_range(work, self.start, self.end, parent=self)
        times = QHBoxLayout()
        times.addWidget(self.start)
        times.addWidget(grid_start)
        arrow = QLabel("→")
        times.addWidget(arrow)
        times.addWidget(self.end)
        times.addWidget(grid_end)
        times.addStretch()
        self.times = QWidget()
        self.times.setLayout(times)
        times.setContentsMargins(0, 0, 0, 0)
        lay.addRow("", self.times)
        self.times.setVisible(False)
        self.end_widgets = (self.end, grid_end)

        def shown():
            self.times.setVisible(self.begun.isChecked() or self.done.isChecked())
            # already begun: only the start; past: start and end
            for w in (*self.end_widgets, arrow):
                w.setVisible(self.done.isChecked())
        self.begun.toggled.connect(shown)
        self.done.toggled.connect(shown)
        shown()
        # the activities running: left running, suspended or stopped
        self.others = {}
        concurrent = work.policy.feature("concurrentEntries")
        for e in work.running():
            if work.open_segment(e["uid"]) is None:
                continue
            c = QComboBox()
            if concurrent:
                c.addItem(_("Lasciala in corso"), KEEP)
            c.addItem(_("Sospendila"), SUSPEND)
            c.addItem(_("Fermala"), STOP)
            # starting another activity usually means switching: the one at work is suspended
            c.setCurrentIndex(c.findData(SUSPEND))
            self.others[e["uid"]] = c
            name = QLabel(work.label(e))
            name.setWordWrap(True)
            lay.addRow(name, _row(c))

    def apply(self, req):
        req.mode = TRAVEL if self.travel_mode.isChecked() else WORK
        if self.begun.isChecked():
            req.start_ms = _ms(self.start)
            req.others = {u: c.currentData() for u, c in self.others.items() if c.currentData() != KEEP}
        elif self.done.isChecked():
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
        self.lay.setContentsMargins(22, 16, 22, 16)
        self.lay.setSpacing(12)
        # the name on top, as the phone's screens
        self.heading = QLabel(title)
        self.heading.setFont(theme.font("card"))
        self.lay.addWidget(self.heading)
        self.message = QLabel(wordWrap=True)
        self.message.setProperty("role", "error")
        self.message.hide()

    def fail(self, e):
        self.message.setText(error_text(e) if isinstance(e, WorkError) else str(e))
        self.message.show()

    def buttons(self, ok_text, extra=(), cancel=True):
        box = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel if cancel else
                               QDialogButtonBox.StandardButton.NoButton)
        self.ok = box.addButton(ok_text, QDialogButtonBox.ButtonRole.AcceptRole)
        self.ok.setDefault(True)
        self.ok.setProperty("role", "primary")
        for text, slot in extra:
            b = box.addButton(text, QDialogButtonBox.ButtonRole.ActionRole)
            b.clicked.connect(slot)
            if getattr(slot, "__name__", "") == "delete":
                b.setProperty("role", "danger")
        box.accepted.connect(self.confirm)
        box.rejected.connect(self.reject)
        QShortcut(QKeySequence("Ctrl+Return"), self, activated=self.confirm)
        QShortcut(QKeySequence("Ctrl+Enter"), self, activated=self.confirm)
        self.lay.addWidget(self.message)
        self.lay.addWidget(box)
        # the fields' names quieter than what is typed, as the app's labels
        for form in self.findChildren(QFormLayout):
            for i in range(form.rowCount()):
                item = form.itemAt(i, QFormLayout.ItemRole.LabelRole)
                if item is not None and isinstance(item.widget(), QLabel):
                    item.widget().setProperty("role", "field")


class QuickEntry(_Dialog):
    """A new activity with the main fields; "Altri campi…" opens the full form with what was typed."""

    def __init__(self, work, parent=None, todo=None):
        super().__init__(_("Nuova attività"), parent)
        self.work = work
        self.todo = todo
        self.result_uid = None
        self.setMinimumWidth(520)
        p = work.policy
        form = _wrapped()
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
            self.description.setPlainText(todo.get("activity") or "")
            self.client.set_value(todo.get("clientUid"))
        hint = QLabel(_("Ctrl+Invio per avviare"))
        hint.setProperty("role", "small")
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

    def __init__(self, work, parent=None, uid=None, start=None, actions=None):
        super().__init__(_("Attività") if uid else _("Nuova attività"), parent)
        self.work, self.uid, self.actions = work, uid, actions
        self.result_uid = uid
        self.setMinimumWidth(600)
        p = work.policy
        e = work.entry(uid) if uid else {}
        if uid:
            self._state_box(e)
        form = QFormLayout()
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
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

    def _state_box(self, e):
        """On top (§8): the state as the Home shows it with the total work time, then what the state allows."""
        work = self.work
        shown, since = work.display(e)
        top = QHBoxLayout()
        text = display_label(shown) + (" " + _("dalle %s") % clock(model.to_ms(since)) if since else "")
        top.addWidget(W.Pill(text, states.colour(shown), states.icon(shown)))
        top.addStretch()
        top.addWidget(QLabel(f"{KINDS[WORK]} {hm(work.totals(e['uid'])[WORK])}"))
        self.lay.addLayout(top)
        if self.actions is None:
            return
        row = QHBoxLayout()
        row.setSpacing(8)
        for act in entry_actions(work, e):
            if act.verb in ("delete", "tick"):
                continue
            b = QPushButton(act.label)
            b.setAutoDefault(False)
            b.clicked.connect(lambda _c=False, a=act: self._act(a))
            row.addWidget(b)
        row.addStretch()
        self.lay.addLayout(row)

    def _act(self, action):
        self.actions.act(self.uid, action)
        # the state changed: the form shows it again
        self.done(2)

    def _times_box(self, e):
        box = QGroupBox(field_label(self.work.policy, "times"))
        lay = QVBoxLayout(box)
        totals = self.work.totals(e["uid"])
        lay.addWidget(QLabel(f"{KINDS[WORK]} {hm(totals[WORK])} · {KINDS[TRAVEL]} "
                             f"{hm(totals[TRAVEL])} · {KINDS[PAUSE]} {hm(totals[PAUSE])}"))
        editable = self.work.policy.setting("editableTimes", True)
        for s in self.work.segments(e["uid"]):
            row = QHBoxLayout()
            end = clock(s["endUtcMs"]) if s.get("endUtcMs") else _("in corso")
            row.addWidget(QLabel(f"{KINDS.get(s['kind'], s['kind'])}  {clock(s['startUtcMs'])} – {end}"))
            row.addStretch()
            if editable:
                row.addWidget(W.icon_button("edit", _("Modifica…"), lambda s=s: self._segment(s)))
                if s.get("endUtcMs"):
                    row.addWidget(W.icon_button("clear", _("Elimina"), lambda s=s: self._remove(s)))
            lay.addLayout(row)
        if editable and work_closed(self.work, e):
            row = QHBoxLayout()
            row.addStretch()
            row.addWidget(W.button(_("Aggiungi un tratto…"), lambda: self._segment(None), "tonal", "add"))
            lay.addLayout(row)
        if e.get("needsReview"):
            warn = QLabel(_("Da verificare: due tratti si sovrappongono."))
            warn.setProperty("role", "error")
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


def work_closed(work, e):
    """No open segment: a segment may be added by hand."""
    return work.open_segment(e["uid"]) is None


def edit_entry(work, uid, parent=None, actions=None):
    """The full form of an activity; shown again after its times or its state changed."""
    while True:
        d = EntryDialog(work, parent, uid=uid, actions=actions)
        r = d.exec()
        if r != 2:
            return r


class SegmentDialog(_Dialog):
    """A stretch of time: its kind, start and end (the running one keeps no end)."""

    def __init__(self, work, entry_uid, segment=None, parent=None):
        super().__init__(_("Tratto") if segment else _("Nuovo tratto"), parent)
        self.work, self.entry_uid, self.segment = work, entry_uid, segment
        form = QFormLayout()
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
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


def stop(work, uid, parent=None, at=None):
    """
    Stop. When the activity went out and came back to work without a return trip, the three choices of
    §3.2; False when the user gave up.
    """
    if work.return_trip_offered(uid):
        box = QMessageBox(parent)
        box.setWindowTitle(_("Stop"))
        box.setText(_("L'attività ha un viaggio di andata: cosa fai?"))
        travel = box.addButton(_("Avvia viaggio di ritorno"), QMessageBox.ButtonRole.ActionRole)
        end = box.addButton(_("Termina l'attività"), QMessageBox.ButtonRole.ActionRole)
        both = None
        if work.return_trip_addable(uid):
            both = box.addButton(_("Termina l'attività ed aggiungi il viaggio di ritorno"),
                                 QMessageBox.ButtonRole.ActionRole)
        box.addButton(QMessageBox.StandardButton.Cancel)
        box.exec()
        chosen = box.clickedButton()
        if chosen is travel:
            work.travel_back(uid, at)
        elif chosen is end:
            work.stop(uid, at)
        elif chosen is both and both is not None:
            work.stop(uid, at, return_trip=True)
        else:
            return False
        return True
    work.stop(uid, at)
    return True


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
    """A TODO activity, new or existing: the fields the policy shows."""

    def __init__(self, work, parent=None, uid=None, plan=None):
        super().__init__(_("Da fare") if uid else _("Nuovo Da fare"), parent)
        self.work, self.uid = work, uid
        self.result_uid = uid
        self.setMinimumWidth(560)
        p = work.policy
        t = work.entry(uid) if uid else {}
        if uid:
            shown, since = work.display(t)
            self.lay.addWidget(W.Pill(display_label(shown), states.colour(shown), states.icon(shown)),
                               0, Qt.AlignmentFlag.AlignLeft)
        form = QFormLayout()
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        self.title = QLineEdit(t.get("activity") or "")
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
        refs = "\n".join(r.get("value") or "" for r in work.store.all("externalRef") if r.get("entryUid") == uid)
        self.refs = QPlainTextEdit(refs)
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
        for i in model.PRIORITIES:
            self.priority.addItem(PRIORITIES[i], i)
        self.priority.setCurrentIndex(max(0, self.priority.findData(t.get("priority") or 0)))
        if p.field("todoPriority").visible:
            form.addRow(field_label(p, "todoPriority"), self.priority)
        if uid:
            self.company.set_value(t.get("companyUid"))
            self.client.set_value(t.get("clientUid"))
        self.lay.addLayout(form)
        extra = []
        if uid and (p.feature("deleteTodos") or p.feature("ignoreTodos")):
            extra.append((_("Elimina"), self.delete))
        self.buttons(_("Salva"), extra)
        self.title.setFocus()

    def confirm(self):
        due_day, due_min, _d = self.due.value()
        plan_day, plan_min, duration = self.plan.value()
        try:
            self.result_uid = self.work.save_todo(
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
            self.work.delete(self.uid)
        except WorkError as e:
            self.fail(e)
            return
        self.accept()


class AbsenceDialog(_Dialog):
    """
    An absence (§3.1): the company (none: every one), what kind, notes, from and to day, optionally the
    times of a permesso; without times one segment per working window of every working day.
    """

    def __init__(self, work, parent=None, uid=None, first=None):
        super().__init__(_("Assenza") if uid else _("Nuova assenza"), parent)
        self.work, self.uid = work, uid
        self.setMinimumWidth(520)
        p = work.policy
        e = work.entry(uid) if uid else {}
        form = _wrapped()
        self.company = MasterCombo(work, "company")
        if p.field("company").visible:
            form.addRow(field_label(p, "company") + " " + _("(vuota: tutte)"), self.company)
        self.kind = QComboBox()
        for k, text in ABSENCE_KINDS.items():
            self.kind.addItem(text, k)
        self.notes = QPlainTextEdit()
        self.notes.setTabChangesFocus(True)
        self.notes.setMaximumHeight(80)
        form.addRow(_("Tipo"), self.kind)
        today = QDate.currentDate()
        self.first = QDateEdit(QDate(first.year, first.month, first.day) if first else today, calendarPopup=True)
        self.last = QDateEdit(self.first.date(), calendarPopup=True)
        self.timed = QCheckBox(_("con orario"))
        self.start = QTimeEdit(QTime(9, 0))
        self.end = QTimeEdit(QTime(13, 0))
        _formatted(self.first, self.last, self.start, self.end)
        form.addRow(_("Dal giorno"), _row(self.first))
        form.addRow(_("Al giorno"), _row(self.last))
        form.addRow("", _row(self.timed, self.start, QLabel("→"), self.end))
        form.addRow(field_label(p, "notes"), self.notes)
        self.first.dateChanged.connect(lambda d: self.last.setDate(max(d, self.last.date())))
        self.timed.toggled.connect(lambda on: (self.start.setEnabled(on), self.end.setEnabled(on)))
        self.start.setEnabled(False)
        self.end.setEnabled(False)
        self.lay.addLayout(form)
        if uid:
            self._load(e)
        extra = []
        if uid and p.feature("deleteEntries"):
            extra.append((_("Elimina"), self.delete))
        self.buttons(_("Salva"), extra)

    def _load(self, e):
        work = self.work
        self.company.set_value(e.get("companyUid"))
        self.kind.setCurrentIndex(max(0, self.kind.findData(e.get("absenceKind") or model.ABSENCE)))
        self.notes.setPlainText(e.get("notes") or "")
        segs = work.real_segments(e["uid"])
        if not segs:
            return
        tz = work.tz
        first = model.from_ms(min(s["startUtcMs"] for s in segs), tz)
        last = model.from_ms(max(s["endUtcMs"] or s["startUtcMs"] for s in segs), tz)
        self.first.setDate(QDate(first.year, first.month, first.day))
        self.last.setDate(QDate(last.year, last.month, last.day))
        spans = {(model.from_ms(s["startUtcMs"], tz).strftime("%H:%M"),
                  model.from_ms(s["endUtcMs"], tz).strftime("%H:%M")) for s in segs if s.get("endUtcMs")}
        if len(spans) == 1:
            a, b = next(iter(spans))
            self.timed.setChecked(True)
            self.start.setTime(QTime.fromString(a, "HH:mm"))
            self.end.setTime(QTime.fromString(b, "HH:mm"))

    @staticmethod
    def _date(edit):
        d = edit.date()
        return date(d.year(), d.month(), d.day())

    def confirm(self):
        start = end = None
        if self.timed.isChecked():
            start = self.start.time().hour() * 60 + self.start.time().minute()
            end = self.end.time().hour() * 60 + self.end.time().minute()
        try:
            self.work.save_absence(self.uid, self._date(self.first), self._date(self.last),
                                   company=self.company.value(), absence_kind=self.kind.currentData(),
                                   notes=self.notes.toPlainText(), start_min=start, end_min=end)
        except WorkError as e:
            self.fail(e)
            return
        self.accept()

    def delete(self):
        if QMessageBox.question(self, _("Elimina"), _("Eliminare questa assenza?")) != QMessageBox.StandardButton.Yes:
            return
        try:
            self.work.delete(self.uid)
        except WorkError as e:
            self.fail(e)
            return
        self.accept()


def _iso(text):
    try:
        return date.fromisoformat(text) if text else None
    except ValueError:
        return None
