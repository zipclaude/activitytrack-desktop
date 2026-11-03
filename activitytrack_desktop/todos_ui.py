# SPDX-License-Identifier: GPL-3.0-or-later
"""
The Da fare section (the app's tab, issue #96): every to-do in the Home's
sections, the done ones and the ignored ones on request, by company, with
the search.
"""

from PyQt6.QtCore import QSettings
from PyQt6.QtGui import QActionGroup
from PyQt6.QtWidgets import QHBoxLayout, QMenu, QVBoxLayout, QWidget

from activitytrack import texts
from activitytrack.i18n import _
from activitytrack.texts import FIELDS
from activitytrack.todos import DONE, IGNORED, TODO, sections

from . import theme, widgets as W
from .home import COLUMN, KEYS, TodoRow, clear, matches, scroll_page, search_field


class TodosPage(QWidget):
    def __init__(self, actions, parent=None):
        super().__init__(parent)
        self.actions = actions
        self.settings = QSettings()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 18, 0, 0)
        self.new = W.button(_("Nuovo Da fare"), lambda: actions.new_todo(), "primary", "add",
                            W.with_key(_("Nuovo Da fare"), KEYS["new_todo"]))
        head = W.page(_("Da fare"), self.new)
        head.setContentsMargins(24, 0, 20, 8)
        lay.addWidget(head)
        column = QWidget()
        column.setMaximumWidth(COLUMN)
        self.column = QVBoxLayout(column)
        self.column.setContentsMargins(0, 0, 0, 0)
        self.column.setSpacing(8)
        bar = QHBoxLayout()
        bar.setSpacing(8)
        self.done = W.chip(_("Anche le fatte"), checkable=True)
        self.done.setChecked(self.settings.value("todos/done", False, type=bool))
        self.ignored = W.chip(texts.SHOWS[IGNORED], checkable=True)
        self.ignored.setChecked(self.settings.value("todos/ignored", False, type=bool))
        self.company = self.settings.value("todos/company") or None
        self.company_menu = QMenu(self)
        self.company_button = W.chip(menu=self.company_menu)
        for b in (self.done, self.ignored):
            b.toggled.connect(self._changed)
        for w in (self.done, self.ignored, self.company_button):
            bar.addWidget(w)
        bar.addStretch()
        self.search = search_field(self.refresh_list)
        bar.addWidget(self.search)
        self.column.addLayout(bar)
        self.list = QVBoxLayout()
        self.list.setSpacing(8)
        self.column.addLayout(self.list)
        self.column.addStretch()
        self.scroll = scroll_page(column)
        lay.addWidget(self.scroll)
        actions.changed.connect(self.refresh)
        actions.redraw.connect(self.refresh)
        theme.notifier().changed.connect(self.refresh)
        self.refresh()

    def _changed(self):
        self.settings.setValue("todos/done", self.done.isChecked())
        self.settings.setValue("todos/ignored", self.ignored.isChecked())
        self.settings.setValue("todos/company", self.company or "")
        self.refresh()

    def _pick(self, uid):
        self.company = uid
        self._changed()

    def refresh(self):
        work = self.actions.work
        p = work.policy
        self.new.setEnabled(self.actions.session.account is not None)
        self.ignored.setVisible(p.feature("ignoreTodos"))
        companies = [(r["uid"], r.get("name") or "") for r in work.masters("company")]
        if self.company not in {c for c, _n in companies}:
            self.company = None
        self.company_menu.clear()
        group = QActionGroup(self.company_menu)
        for value, text in [(None, _("Tutte le aziende"))] + companies:
            a = self.company_menu.addAction(text)
            a.setCheckable(True)
            a.setChecked(value == self.company)
            group.addAction(a)
            a.triggered.connect(lambda _c=False, v=value: self._pick(v))
        self.company_button.setText((work.name("company", self.company) or FIELDS["company"]) + "  ▾")
        W.set_changed(self.company_button, self.company is not None)
        self.company_button.setVisible(p.field("company").visible and len(companies) > 1)
        self.refresh_list()

    def shown(self):
        show = {TODO}
        if self.done.isChecked():
            show.add(DONE)
        if self.ignored.isChecked() and self.actions.work.policy.feature("ignoreTodos"):
            show.add(IGNORED)
        return show

    def refresh_list(self):
        todos = self.actions.todos
        clear(self.list)
        everything = todos.all() if todos.policy.feature("todos") else []
        groups = sections(everything, [], self.shown(), 0, self.company, tz=todos.tz())
        words = self.search.text().casefold().split()
        shown = 0
        for section, items in groups:
            items = [it for it in items if matches(todos.work, it[1], words)]
            if not items:
                continue
            self.list.addWidget(W.section_head(texts.SECTIONS[section], section == "overdue"))
            for _kind, t, st in items:
                self.list.addWidget(TodoRow(self.actions, t, st, kind_word=False))
                shown += 1
        if not shown:
            empty = W.label(_("Niente da mostrare con questi filtri.") if words or everything
                            else _("Nessun Da fare."), "muted")
            empty.setContentsMargins(4, 12, 0, 0)
            self.list.addWidget(empty)

    def focus_search(self):
        self.search.setFocus()
        self.search.selectAll()
