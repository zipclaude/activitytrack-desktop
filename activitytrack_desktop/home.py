# SPDX-License-Identifier: GPL-3.0-or-later
"""
The activities on the desktop (docs/DESIGN.md §6.1, §6.3): the commands,
shared by the tray menu, the window and its shortcuts, and the Home as the
phone's: the big card of the latest activity, the small cards of the others
running or suspended, then the list of to-dos and stopped activities with
its filters.
"""

from datetime import datetime

from PyQt6.QtCore import QObject, QSettings, Qt, QTimer, pyqtSignal as Signal
from PyQt6.QtGui import QActionGroup, QFont
from PyQt6.QtWidgets import (
    QHBoxLayout, QLabel, QLineEdit, QMenu, QMessageBox, QScrollArea, QVBoxLayout, QWidget,
)

from activitytrack import formats, texts
from activitytrack.i18n import _
from activitytrack.policy import stored
from activitytrack import homelist, model
from activitytrack.homelist import DEFAULT_SHOW, SHOWS, WINDOWS
from activitytrack.texts import KINDS, FIELDS, clock, display_label, entry_actions, error_text, hm
from activitytrack.work import PAUSE, TRAVEL, WORK, Work, WorkError

from . import forms, icons, states, targets, theme, widgets as W

# the round buttons of the commands: icon and colour (CommandButtons.kt); a command is its kind, or "stop"
COMMAND_LOOK = {WORK: ("play", theme.GREEN), PAUSE: ("pause", theme.YELLOW), TRAVEL: ("travel", theme.BLUE),
                "stop": ("stop", theme.RED)}
# the window's keys (docs/DESIGN.md §6.5), shown in the tooltips and menus
KEYS = {"new_entry": "Ctrl+N", "pause": "Ctrl+P", "stop": "Ctrl+T", "new_todo": "Ctrl+D", "find": "Ctrl+F",
        "sync": "F5"}
# the width of the pages' column: a wide window keeps the cards readable
COLUMN = 920


def commands(work, entry):
    """[Action] the state allows, as the app's card buttons (the library's, for every interface); no delete."""
    return [a for a in entry_actions(work, entry) if a.verb not in ("delete", "restore")]


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
        # the command line or the terminal may have changed the formats too
        formats.load(self.session.store)
        self.redraw.emit()

    def _done(self):
        self.changed.emit()

    def _fail(self, e):
        QMessageBox.warning(self._parent(), "ActivityTrack", error_text(e) if isinstance(e, WorkError) else str(e))
        self.changed.emit()

    def new_entry(self, todo=None, travel=False):
        if self.session.account is None:
            return
        self.refresh_policy()
        d = forms.QuickEntry(self.work, self._parent(), todo=todo)
        if travel and self.work.policy.feature("travel"):
            d.options.travel_mode.setChecked(True)
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

    def _ask(self, title, text):
        ok = QMessageBox.question(self._parent(), title, text)
        return ok == QMessageBox.StandardButton.Yes

    def do(self, uid, verb, kind=None, at=None):
        """One command by name (Work.perform), with the questions of §3: stop, travel from work, reopen, delete."""
        self.refresh_policy()
        try:
            if verb == "stop":
                if not forms.stop(self.work, uid, self._parent(), at):
                    return
            elif verb == "travel_from_work":
                answer = QMessageBox.question(
                    self._parent(), KINDS[TRAVEL], _("Hai completato l'attività lavorativa?"),
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                    | QMessageBox.StandardButton.Cancel)
                if answer == QMessageBox.StandardButton.Cancel:
                    return
                self.work.travel_from_work(uid, answer == QMessageBox.StandardButton.Yes, at)
            elif verb == "reopen" and not self._ask(_("Riapri"), _("Riaprire l'attività?")):
                return
            elif verb == "delete" and not self._ask(
                    _("Elimina"), _("Eliminare? Si elimina anche sugli altri dispositivi; si può ripristinare.")):
                return
            else:
                self.work.perform(uid, verb, kind, at)
        except WorkError as e:
            self._fail(e)
            return
        self._done()

    def act(self, uid, action):
        """A button of texts.entry_actions."""
        self.do(uid, action.verb, action.kind)

    def command(self, uid, kind):
        """The pause and resume keys and menus: PAUSE pauses, WORK resumes a pause or a suspended activity."""
        if kind == PAUSE:
            self.do(uid, "switch", PAUSE)
        else:
            self.resume(uid)

    def resume(self, uid, at=None):
        """Riprendi: the kind open before a pause; from a suspended activity, work."""
        seg = self.work.open_segment(uid)
        if seg is None:
            self.do(uid, "resume", WORK, at)
        else:
            self.do(uid, "switch", self.work.resume_kind(uid), at)

    def _pick(self, target, title):
        """The uid of a target (targets.py); a list is the user's choice in a small list."""
        if not isinstance(target, list):
            return target
        rows = []
        for uid in target:
            e = self.session.store.get("entry", uid) or {}
            rows.append((uid, f"{self.work.label(e)} — {display_label(self.work.display(e)[0])}"))
        return W.choose(self._parent(), title, rows)

    def pause_or_resume(self):
        """Ctrl+P: pause the activity at work, else resume the paused or suspended one."""
        if self.session.account is None:
            return
        cmd, target = targets.pause_or_resume(self.work)
        title = _("Quale attività mettere in pausa?") if cmd == PAUSE else _("Quale attività riprendere?")
        uid = self._pick(target, title)
        if uid is not None:
            self.command(uid, cmd)

    def stop_current(self, focused=None):
        """Ctrl+T: stop the activity of the big card (the stop sheet when details are missing)."""
        if self.session.account is None:
            return
        uid = self._pick(targets.stop_target(self.work, focused), _("Quale attività fermare?"))
        if uid is not None:
            self.do(uid, "stop")

    def edit(self, uid):
        """The detail of an activity: the to-do and absence dialogs, else the full form."""
        self.refresh_policy()
        e = self.work.entry(uid)
        if e.get("kind") == model.ABSENCE:
            return self.edit_absence(uid)
        if e.get("status") == model.TODO and e.get("deletedUtcMs") is None:
            return self.edit_todo(uid)
        try:
            forms.edit_entry(self.work, uid, self._parent(), self)
        except WorkError as ex:
            self._fail(ex)
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
        t = self.session.store.get("entry", uid)
        if t is not None:
            self.new_entry(todo=t)

    def todo_done(self, uid, done=True):
        self._do(self.work.tick if done else self.work.untick, uid)

    def todo_ignore(self, uid):
        """Into the bin (policy ignoreTodos maps to delete)."""
        self._do(self.work.delete, uid)

    def todo_reopen(self, uid):
        """A ticked-off to-do is TODO again, a deleted one is restored."""
        e = self.work.entry(uid)
        self._do(self.work.restore if e.get("deletedUtcMs") is not None else self.work.untick, uid)

    def todo_postpone(self, uid):
        """Later by the user's snooze (Promemoria), within the policy."""
        self._do(self.work.postpone, uid, self.snooze_min())

    def snooze_min(self):
        """The minutes of a postpone: the user's (Promemoria) within the policy, the menus' and the reminders'."""
        from .reminder_ui import local_intervals
        from activitytrack.reminders import config_of
        return config_of(self.work.policy, local_intervals())["planSnoozeMin"]

    def reopen_entry(self, uid):
        self.do(uid, "reopen", WORK)

    def new_todo(self, plan=None):
        if self.session.account is None:
            return
        self.refresh_policy()
        d = forms.TodoDialog(self.work, self._parent(), plan=plan)
        d.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        if d.exec():
            self._done()

    def edit_todo(self, uid):
        self.refresh_policy()
        try:
            ok = forms.TodoDialog(self.work, self._parent(), uid=uid).exec()
        except WorkError as e:
            self._fail(e)
            return
        if ok:
            self._done()

    def new_absence(self, first=None):
        if self.session.account is None:
            return
        self.refresh_policy()
        d = forms.AbsenceDialog(self.work, self._parent(), first=first)
        if d.exec():
            self._done()

    def edit_absence(self, uid):
        self.refresh_policy()
        try:
            ok = forms.AbsenceDialog(self.work, self._parent(), uid=uid).exec()
        except WorkError as e:
            self._fail(e)
            return
        if ok:
            self._done()


def _zone():
    from PyQt6.QtCore import QTimeZone
    z = bytes(QTimeZone.systemTimeZoneId()).decode()
    return z or None


def _time(ms):
    return formats.time(datetime.fromtimestamp(ms / 1000))


def _span(work, uid):
    """"11:00–11:45" from the first start to the last end ("…" while one is open), the day when not today."""
    segs = work.segments(uid)
    if not segs:
        return ""
    start = min(s["startUtcMs"] for s in segs)
    ends = [s.get("endUtcMs") for s in segs]
    end = "…" if None in ends else _time(max(ends))
    return f"{clock(start)}–{end}"


def _who(work, e):
    """The card's title: the client, else the company (the app's card.title)."""
    return work.name("client", e.get("clientUid")) or work.name("company", e.get("companyUid"))


class BigCard(W.Surface):
    """
    The latest activity, as the phone's big card: company, client and
    description, the state since when, the totals, the time of the running
    stretch, the round commands with their names (HomeScreen.kt EntryCardView).
    """

    def __init__(self, actions, entry, tags, parent=None):
        work = actions.work
        super().__init__(theme.band(work, entry.get("companyUid"), entry.get("clientUid")), 16, True, parent)
        self.uid = entry["uid"]
        self.setToolTip(_("Apri l'attività"))
        self.clicked.connect(lambda: actions.edit(self.uid))
        outer = QVBoxLayout(self)
        outer.setContentsMargins(self.BAND + 18, 14, 18, 16)
        outer.setSpacing(6)
        top = QHBoxLayout()
        top.setSpacing(12)
        text = QVBoxLayout()
        text.setSpacing(2)
        client = work.name("client", entry.get("clientUid"))
        company = work.name("company", entry.get("companyUid"))
        if client and company:
            text.addWidget(W.label(company, "muted"))
        title = QLabel(client or company or _("Senza cliente"))
        title.setFont(theme.font("card"))
        title.setWordWrap(True)
        text.addWidget(title)
        if (entry.get("activity") or "").strip():
            what = QLabel(entry["activity"].strip())
            what.setWordWrap(True)
            text.addWidget(what)
        top.addLayout(text, 1)
        side = QVBoxLayout()
        side.setSpacing(4)
        side.addWidget(W.TagDots(entry.get("tags"), tags), 0, Qt.AlignmentFlag.AlignRight)
        open_seg = work.open_segment(self.uid)
        self.timer = QLabel(hm(work.clock() - open_seg["startUtcMs"]) if open_seg else "")
        self.timer.setFont(theme.font("timer", QFont.Weight.Light))
        self.timer.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.timer.setToolTip(_("Il tratto in corso"))
        side.addWidget(self.timer, 0, Qt.AlignmentFlag.AlignRight)
        side.addStretch()
        top.addLayout(side)
        outer.addLayout(top)

        shown, since = work.display(entry)
        text_ = display_label(shown) + (" " + _("dalle %s") % formats.time(since) if since else "")
        self.pill = W.Pill(text_, states.colour(shown), states.icon(shown))
        outer.addWidget(self.pill)
        if entry.get("plannedEndUtcMs"):
            outer.addWidget(W.label(_("Fine prevista alle %s") % clock(entry["plannedEndUtcMs"]), "small"))
        totals = work.totals(self.uid)
        parts = [f"{KINDS[WORK]} {hm(totals[WORK])}"]
        if totals[TRAVEL] or work.policy.feature("travel"):
            parts.append(f"{KINDS[TRAVEL]} {hm(totals[TRAVEL])}")
        line = QHBoxLayout()
        line.addWidget(W.label(" · ".join(parts), "small"))
        if entry.get("needsReview"):
            review = W.label(_("da verificare"), "error")
            review.setToolTip(_("Da verificare: due tratti si sovrappongono."))
            line.addWidget(review)
        line.addStretch()
        outer.addLayout(line)

        row = QHBoxLayout()
        row.setSpacing(10)
        row.setContentsMargins(0, 6, 0, 0)
        self.commands = {}
        for act in commands(work, entry):
            name = act.kind or act.verb
            icon, colour = COMMAND_LOOK.get(name, ("play", theme.ORANGE))
            key = KEYS["stop"] if act.verb == "stop" else KEYS["pause"] if act.kind == PAUSE or act.label == _(
                "Riprendi") else ""
            c = W.Command(act.label, icon, colour, lambda u=self.uid, a=act: actions.act(u, a),
                          tip=W.with_key(act.label, key))
            self.commands[name] = c
            row.addWidget(c)
        row.addStretch()
        edit = W.icon_button("edit", _("Modifica…"), lambda: actions.edit(self.uid))
        row.addWidget(edit, 0, Qt.AlignmentFlag.AlignBottom)
        outer.addLayout(row)


class EmptyCard(W.Surface):
    """The big card when nothing runs: the message and the start and travel buttons (EmptyEntryCard)."""

    def __init__(self, actions, parent=None):
        super().__init__(None, 16, False, parent)
        work = actions.work
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 22, 18, 20)
        lay.setSpacing(14)
        title = QLabel(_("Nessuna attività in corso"))
        title.setFont(theme.font("card"))
        title.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        lay.addWidget(title)
        row = QHBoxLayout()
        row.setSpacing(28)
        row.addStretch()
        paired = actions.session.account is not None
        allowed = work.policy.feature("entries") and paired
        self.todo = W.Command(_("Da fare"), "checkbox", theme.GREY, lambda: actions.new_todo(), 64,
                              W.with_key(_("Nuovo Da fare"), KEYS["new_todo"]))
        self.todo.button.setEnabled(paired and work.policy.feature("todos"))
        self.todo.setVisible(work.policy.feature("todos"))
        row.addWidget(self.todo)
        self.start = W.Command(KINDS[WORK], "play", theme.GREEN, lambda: actions.new_entry(), 64,
                               W.with_key(_("Nuova attività"), KEYS["new_entry"]))
        self.start.button.setEnabled(allowed)
        row.addWidget(self.start)
        if work.policy.feature("travel"):
            self.travel = W.Command(KINDS[TRAVEL], "travel", theme.BLUE, lambda: actions.new_entry(travel=True), 64,
                                    _("Nuovo viaggio"))
            self.travel.button.setEnabled(allowed)
            row.addWidget(self.travel)
        self.absence = W.Command(KINDS[model.ABSENCE], "dot", theme.PINK, lambda: actions.new_absence(), 64,
                                 _("Nuova assenza"))
        self.absence.button.setEnabled(paired)
        row.addWidget(self.absence)
        row.addStretch()
        lay.addLayout(row)


class SmallCard(W.Surface):
    """
    Another activity running or suspended (SmallEntryCard): one line, the
    state and its times; a click brings it to the big card, the button
    resumes or pauses it.
    """

    def __init__(self, actions, entry, tags, select, parent=None):
        work = actions.work
        super().__init__(theme.band(work, entry.get("companyUid"), entry.get("clientUid")), 14, True, parent)
        self.uid = entry["uid"]
        self.setToolTip(_("Mostra nella scheda grande"))
        self.clicked.connect(lambda: select(self.uid))
        lay = QHBoxLayout(self)
        lay.setContentsMargins(self.BAND + 14, 8, 10, 8)
        lay.setSpacing(12)
        text = QVBoxLayout()
        text.setSpacing(4)
        what = (entry.get("activity") or "").strip()
        title = W.Elided(" · ".join(x for x in (_who(work, entry) or _("Senza cliente"), what) if x))
        title.setFont(theme.font("title", QFont.Weight.Medium))
        text.addWidget(title)
        line = QHBoxLayout()
        line.setSpacing(8)
        shown = work.display(entry)[0]
        pill = W.Pill(display_label(shown), states.colour(shown), states.icon(shown))
        pill.setFont(theme.font("label", QFont.Weight.DemiBold))
        line.addWidget(pill)
        t = work.totals(self.uid)
        line.addWidget(W.label(f"{_span(work, self.uid)} ({hm(t[WORK] + t[TRAVEL])})", "small"))
        line.addStretch()
        text.addLayout(line)
        lay.addLayout(text, 1)
        dots = W.TagDots(entry.get("tags"), tags)
        lay.addWidget(dots, 0, Qt.AlignmentFlag.AlignTop)
        resting = shown in (model.SUSPENDED, PAUSE)
        cmd = WORK if resting else PAUSE
        icon, colour = COMMAND_LOOK[cmd]
        name = _("Riprendi") if resting else _("Pausa")
        self.button = W.RoundButton(icon, colour, 44, name)
        self.button.clicked.connect(lambda _c=False: actions.command(self.uid, cmd))
        lay.addWidget(self.button)


def _row_shell(row, mark):
    """The rows' common layout: the mark, the texts, the side, the buttons."""
    lay = QHBoxLayout(row)
    lay.setContentsMargins(row.BAND + 12, 9, 10, 9)
    lay.setSpacing(12)
    lay.addWidget(W.Mark(mark))
    return lay


def _texts(title, sub, dim=False, strike=False, alert=False):
    box = QVBoxLayout()
    box.setSpacing(2)
    t = W.Elided(title)
    f = theme.font("title", QFont.Weight.Normal if dim else QFont.Weight.DemiBold)
    f.setStrikeOut(strike)
    t.setFont(f)
    if dim:
        W.role(t, "muted")
    box.addWidget(t)
    s = W.Elided(sub)
    s.setFont(theme.font("label"))
    W.role(s, "error" if alert else "muted")
    if strike:
        f = s.font()
        f.setStrikeOut(True)
        s.setFont(f)
    box.addWidget(s)
    return box, t, s


def _side(when, extra="", alert=False, dots=None):
    box = QVBoxLayout()
    box.setSpacing(2)
    if dots is not None:
        box.addWidget(dots, 0, Qt.AlignmentFlag.AlignRight)
    w = W.label(when, "error" if alert else None)
    w.setAlignment(Qt.AlignmentFlag.AlignRight)
    w.setFont(theme.font("label"))
    box.addWidget(w)
    if extra:
        e = W.label(extra, "small")
        e.setAlignment(Qt.AlignmentFlag.AlignRight)
        box.addWidget(e)
    return box


class TodoRow(W.Surface):
    """
    A TODO activity of the lists: its mark (the displayed state), the title, "client · Da fare · state";
    when on the right; start and done at hand, the rest in a menu. A click opens it.
    """

    def __init__(self, actions, t, st, parent=None, kind_word=True):
        work, policy = actions.work, actions.work.policy
        super().__init__(theme.band(work, t.get("companyUid"), t.get("clientUid")) or theme.tokens().line, 12, True,
                         parent)
        uid = t["uid"]
        self.uid = uid
        over = st in (model.DONE, model.DELETED)
        self.outlined = st == model.DELETED
        self.clicked.connect(lambda: actions.edit(uid))
        lay = _row_shell(self, st)
        who = work.name("client", t.get("clientUid")) or work.name("company", t.get("companyUid"))
        parts = [who, _("Da fare") if kind_word else "", display_label(st) if st != model.TODO else ""]
        if t.get("priority") and not over:
            parts.append(texts.PRIORITIES.get(t["priority"], ""))
        box, self.title, self.sub = _texts(t.get("activity") or "", " · ".join(x for x in parts if x), over,
                                           st == model.DELETED, st == model.LATE)
        lay.addLayout(box, 1)
        lay.addLayout(_side(texts.todo_when(t, work.tz), alert=st == model.LATE))
        if not over:
            if policy.feature("entries"):
                start = W.RoundButton("play", theme.GREEN, 36, _("Avvia"))
                start.clicked.connect(lambda _c=False: actions.start_todo(uid))
                lay.addWidget(start)
            done = W.RoundButton("done", None, 36, _("Fatto"))
            done.clicked.connect(lambda _c=False: actions.todo_done(uid))
            lay.addWidget(done)
        else:
            again = W.RoundButton("restore", None, 36, _("Ripristina") if st == model.DELETED else _("Riapri"))
            again.clicked.connect(lambda _c=False: actions.todo_reopen(uid))
            lay.addWidget(again)
        menu = QMenu(self)
        if not over and t.get("planDate") and policy.feature("planning"):
            menu.addAction(_("Posticipa di %d min") % actions.snooze_min(), lambda: actions.todo_postpone(uid))
        if not over and (policy.feature("ignoreTodos") or policy.feature("deleteTodos")):
            menu.addAction(_("Elimina"), lambda: actions.do(uid, "delete"))
        menu.addAction(_("Modifica…"), lambda: actions.edit(uid))
        self.more = W.icon_button("more", _("Altro"), menu=menu)
        lay.addWidget(self.more)


class EntryRow(W.Surface):
    """A stopped activity of the Home list: a click opens it; INCOMPLETE ones are marked and in red."""

    def __init__(self, actions, e, end, tags=None, parent=None):
        work = actions.work
        super().__init__(theme.band(work, e.get("companyUid"), e.get("clientUid")) or theme.tokens().line, 12, True,
                         parent)
        uid = e["uid"]
        self.uid = uid
        shown = e.get("_display") or work.display(e)[0]
        missing = shown == model.INCOMPLETE
        self.clicked.connect(lambda: actions.edit(uid))
        lay = _row_shell(self, shown)
        client, company = work.name("client", e.get("clientUid")), work.name("company", e.get("companyUid"))
        parts = [company if client else "", (e.get("activity") or "").strip() or _("senza descrizione"),
                 display_label(shown)]
        box, self.title, self.sub = _texts(client or company or _("Senza cliente"),
                                           " · ".join(x for x in parts if x), not missing, False, missing)
        lay.addLayout(box, 1)
        t = work.totals(uid)
        extra = f"{KINDS[WORK]} {hm(t[WORK])}" + (f" · {KINDS[TRAVEL]} {hm(t[TRAVEL])}" if t[TRAVEL] else "")
        lay.addLayout(_side(_span(work, uid), extra, dots=W.TagDots(e.get("tags"), tags or {})))
        menu = QMenu(self)
        menu.addAction(_("Modifica…"), lambda: actions.edit(uid))
        menu.addAction(_("Riapri"), lambda: actions.reopen_entry(uid))
        self.more = W.icon_button("more", _("Altro"), menu=menu)
        lay.addWidget(self.more)


def search_field(on_change):
    """The search of a list (Ctrl+F): what is typed narrows the rows below."""
    f = QLineEdit()
    f.setPlaceholderText(_("Cerca"))
    f.setClearButtonEnabled(True)
    t = theme.tokens()
    f.addAction(icons.material("search", t.muted), QLineEdit.ActionPosition.LeadingPosition)
    f.setToolTip(W.with_key(_("Cerca"), KEYS["find"]))
    f.setMinimumWidth(160)
    f.setMaximumWidth(280)
    f.textChanged.connect(lambda _t: on_change())
    return f


def matches(work, obj, words):
    """Every word typed in the title, the description, the client, the company, the notes or the tags."""
    if not words:
        return True
    hay = " ".join(str(x) for x in (
        obj.get("activity"), obj.get("notes"), " ".join(obj.get("tags") or []),
        work.name("client", obj.get("clientUid")), work.name("company", obj.get("companyUid")),
    ) if x).casefold()
    return all(w in hay for w in words)


class Filters(QWidget):
    """
    Period, state, company and tag of the Home list, as chips with their
    menus like the app's; kept between starts. A setting the policy fixes
    (homeWindow, homeShow) is greyed with its value. The search narrows
    the rows (Ctrl+F).
    """

    changed = Signal()

    def __init__(self, actions, parent=None):
        super().__init__(parent)
        self.actions = actions
        self.settings = QSettings()
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 8, 0, 0)
        lay.setSpacing(8)
        self.window_menu = QMenu(self)
        group = QActionGroup(self)
        self.window_actions = {}
        for w in WINDOWS:
            a = self.window_menu.addAction(texts.WINDOWS[w])
            a.setCheckable(True)
            group.addAction(a)
            a.triggered.connect(self._changed)
            self.window_actions[w] = a
        self.window_button = W.chip(menu=self.window_menu, tip=_("Periodo"))
        self.show_menu = QMenu(self)
        self.show_actions = {}
        for key in SHOWS:
            a = self.show_menu.addAction(texts.SHOWS[key])
            a.setCheckable(True)
            a.toggled.connect(self._changed)
            self.show_actions[key] = a
        self.show_button = W.chip(menu=self.show_menu, tip=_("Cosa mostra la lista"))
        self.company_menu = QMenu(self)
        self.company_button = W.chip(menu=self.company_menu)
        self.tag_menu = QMenu(self)
        self.tag_button = W.chip(menu=self.tag_menu)
        self.company = self.tag = None
        for w in (self.window_button, self.show_button, self.company_button, self.tag_button):
            lay.addWidget(w)
        lay.addStretch()
        self.search = search_field(self.changed.emit)
        lay.addWidget(self.search)
        self.load()

    def load(self):
        p = self.actions.work.policy
        window = p.setting("homeWindow", -1)
        if not p.setting_fixed("homeWindow"):
            window = int(self.settings.value("home/window", window))
        (self.window_actions.get(window) or self.window_actions[-1]).setChecked(True)
        self.window_button.setEnabled(not p.setting_fixed("homeWindow"))
        shown = p.setting("homeShow", ",".join(DEFAULT_SHOW))
        if not p.setting_fixed("homeShow"):
            shown = self.settings.value("home/show", shown)
        shown = {x.strip() for x in str(shown).split(",")}
        for key, a in self.show_actions.items():
            a.blockSignals(True)
            a.setChecked(key in shown)
            a.blockSignals(False)
        self.show_button.setEnabled(not p.setting_fixed("homeShow"))
        self.company = self.settings.value("home/company") or None
        self.tag = self.settings.value("home/tag") or None
        self.fill()

    def _menu(self, menu, first, items, current, pick):
        menu.clear()
        group = QActionGroup(menu)
        for value, text in [(None, first)] + items:
            a = menu.addAction(text)
            a.setCheckable(True)
            a.setChecked(value == current)
            group.addAction(a)
            a.triggered.connect(lambda _c=False, v=value: pick(v))

    def fill(self):
        """The companies and tags of the master data (the choice kept when they are filled again)."""
        work = self.actions.work
        companies = [(r["uid"], r.get("name") or "") for r in work.masters("company")]
        tags = [(r.get("name"), r.get("name")) for r in work.masters("tag") if r.get("name")]
        if self.company not in {c for c, _n in companies}:
            self.company = None
        if self.tag not in {t for t, _n in tags}:
            self.tag = None
        self._menu(self.company_menu, _("Tutte le aziende"), companies, self.company, self._company)
        self._menu(self.tag_menu, _("Tutti i tag"), tags, self.tag, self._tag)
        self.company_button.setVisible(work.policy.field("company").visible and len(companies) > 1)
        self.tag_button.setVisible(work.policy.field("tags").visible and bool(tags))
        self._label()

    def _company(self, uid):
        self.company = uid
        self._changed()

    def _tag(self, name):
        self.tag = name
        self._changed()

    def _label(self):
        window = self.values()["window"]
        self.window_button.setText(texts.WINDOWS[window] + "  ▾")
        W.set_changed(self.window_button, window != -1)
        self.show_button.setText(_("Stato") + "  ▾")
        self.show_button.setToolTip(", ".join(texts.SHOWS[k] for k in self.shown()) or _("nessuno"))
        W.set_changed(self.show_button, set(self.shown()) != set(DEFAULT_SHOW))
        work = self.actions.work
        self.company_button.setText((work.name("company", self.company) or FIELDS["company"]) + "  ▾")
        W.set_changed(self.company_button, self.company is not None)
        self.tag_button.setText((self.tag or FIELDS["tags"]) + "  ▾")
        W.set_changed(self.tag_button, self.tag is not None)

    def _changed(self):
        self._label()
        self.settings.setValue("home/window", self.values()["window"])
        self.settings.setValue("home/show", ",".join(self.shown()))
        self.settings.setValue("home/company", self.company or "")
        self.settings.setValue("home/tag", self.tag or "")
        self.changed.emit()

    def shown(self):
        return [k for k, a in self.show_actions.items() if a.isChecked()]

    def words(self):
        return self.search.text().casefold().split()

    def values(self):
        window = next((w for w, a in self.window_actions.items() if a.isChecked()), -1)
        return dict(show=self.shown(), window=window, company=self.company, tag=self.tag)


def clear(lay):
    """The widgets of a layout gone at once (findChildren no longer sees them)."""
    while lay.count():
        item = lay.takeAt(0)
        w = item.widget()
        if w is not None:
            w.setParent(None)
            w.deleteLater()
        elif item.layout() is not None:
            clear(item.layout())


def scroll_page(column):
    """A section's scrolling body: [column] centred, no wider than COLUMN."""
    scroll = QScrollArea(widgetResizable=True)
    scroll.setFrameShape(QScrollArea.Shape.NoFrame)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    body = QWidget()
    body.setProperty("page", True)
    lay = QHBoxLayout(body)
    lay.setContentsMargins(24, 4, 24, 24)
    column.setMaximumWidth(COLUMN)
    lay.addWidget(column)
    scroll.setWidget(body)
    return scroll


class Home(QWidget):
    """
    The phone's Home: the big card of the latest activity, the small cards
    of the others, the filters, then the list in sections.
    """

    def __init__(self, actions, parent=None, on_pair=None):
        super().__init__(parent)
        self.actions = actions
        self.on_pair = on_pair
        self.selected = None
        self.big_uid = None
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 18, 0, 0)
        # the four ways to begin (§3): Da fare, Lavoro, Viaggio, Assenza
        self.new_todo = W.button(_("Da fare"), lambda: actions.new_todo(), None, "add",
                                 W.with_key(_("Nuovo Da fare"), KEYS["new_todo"]))
        self.new = W.button(KINDS[WORK], lambda: actions.new_entry(), "primary", "play",
                            W.with_key(_("Nuova attività"), KEYS["new_entry"]))
        self.new_travel = W.button(KINDS[TRAVEL], lambda: actions.new_entry(travel=True), None, "travel",
                                   _("Nuovo viaggio"))
        self.new_absence = W.button(KINDS[model.ABSENCE], lambda: actions.new_absence(), None, "dot",
                                    _("Nuova assenza"))
        more = QMenu(self)
        self.full = more.addAction(_("Modulo completo…"), actions.full_entry)
        self.more = W.icon_button("more", _("Altro"), menu=more)
        head = W.page(_("Home"), self.new_todo, self.new_travel, self.new_absence, self.new, self.more)
        head.setContentsMargins(24, 0, 24, 8)
        column = QWidget()
        column.setMaximumWidth(COLUMN)
        top = QHBoxLayout()
        top.addWidget(head)
        lay.addLayout(top)
        self.column = QVBoxLayout(column)
        self.column.setContentsMargins(0, 0, 0, 0)
        self.column.setSpacing(10)
        self.cards = QVBoxLayout()
        self.cards.setSpacing(10)
        self.column.addLayout(self.cards)
        self.filters = Filters(actions)
        self.filters.changed.connect(self.refresh_list)
        self.column.addWidget(self.filters)
        self.list = QVBoxLayout()
        self.list.setSpacing(8)
        self.column.addLayout(self.list)
        self.column.addStretch()
        self.scroll = scroll_page(column)
        lay.addWidget(self.scroll)
        actions.changed.connect(self.refresh)
        actions.redraw.connect(self.refresh)
        theme.notifier().changed.connect(self.refresh)
        # the elapsed times move
        self._tick = QTimer(self, interval=30_000, timeout=self.refresh)
        self._tick.start()
        self.refresh()

    def select(self, uid):
        """A small card to the big one (the app's vm.select)."""
        self.selected = uid
        self.refresh()

    def refresh(self):
        work = self.actions.work
        policy = work.policy
        paired = self.actions.session.account is not None
        self.new.setEnabled(paired and policy.feature("entries"))
        self.full.setEnabled(paired and policy.feature("entries"))
        self.new_todo.setEnabled(paired)
        self.new_todo.setVisible(policy.feature("todos"))
        self.new_travel.setEnabled(paired and policy.feature("entries"))
        self.new_travel.setVisible(policy.feature("travel"))
        self.new_absence.setEnabled(paired)
        clear(self.cards)
        tags = theme.tag_colours(work)
        if not paired:
            self.cards.addWidget(self._unpaired())
        running = {e["uid"]: e for e in work.running()}
        order = targets.running(work)
        if self.selected in running:
            order.remove(self.selected)
            order.insert(0, self.selected)
        self.big_uid = order[0] if order else None
        if order:
            self.cards.addWidget(BigCard(self.actions, running[order[0]], tags))
            for uid in order[1:]:
                self.cards.addWidget(SmallCard(self.actions, running[uid], tags, self.select))
        elif paired:
            self.cards.addWidget(EmptyCard(self.actions))
        self.filters.fill()
        # unpaired: the card that says how to begin, nothing to filter
        self.filters.setVisible(paired)
        self.refresh_list()

    def refresh_list(self):
        work = self.actions.work
        clear(self.list)
        tags = theme.tag_colours(work)
        f = self.filters.values()
        words = self.filters.words()
        groups = homelist.home(work, f["show"], f["window"], f["company"], f["tag"])
        shown = 0
        for section, items in groups:
            items = [it for it in items if matches(work, it[1], words)]
            if not items:
                continue
            self.list.addWidget(W.section_head(texts.SECTIONS[section], section in ("overdue", "missing")))
            for kind, obj, extra in items:
                if kind == "todo":
                    self.list.addWidget(TodoRow(self.actions, obj, extra))
                else:
                    self.list.addWidget(EntryRow(self.actions, obj, extra, tags))
                shown += 1
        if self.actions.session.account is not None and not shown:
            empty = W.label(_("Niente da mostrare con questi filtri.") if words or groups
                            else _("Niente in questo intervallo."), "muted")
            empty.setContentsMargins(4, 12, 0, 0)
            self.list.addWidget(empty)

    def _unpaired(self):
        card = W.Surface(None, 16)
        lay = QVBoxLayout(card)
        lay.setContentsMargins(20, 18, 20, 18)
        lay.setSpacing(10)
        lay.addWidget(W.label(_("Associa questo PC"), "h2"))
        lay.addWidget(W.label(_("Collega ActivityTrack a un server ActivityTrack Web: le attività e i Da fare "
                                "restano sincronizzati con il telefono e il web."), wrap=True))
        if self.on_pair is not None:
            row = QHBoxLayout()
            row.addWidget(W.button(_("Associa a un server…"), self.on_pair, "tonal", "devices"))
            row.addStretch()
            lay.addLayout(row)
        return card

    def focus_search(self):
        self.filters.search.setFocus(Qt.FocusReason.ShortcutFocusReason)
        self.filters.search.selectAll()
