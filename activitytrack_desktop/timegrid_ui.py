# SPDX-License-Identifier: GPL-3.0-or-later
"""
The app's grid of 5-minute cells for choosing times (web issue #38, the
library's timegrid): one row per hour, 12 hours at a time, ▲ Prima /
Dopo ▼ move by 3 hours. Start and end are chosen together by dragging
from the first cell to the last, or clicking the first and then the last;
the other activities of the day are hatched. "Orario esatto" takes the
minutes off the grid. A button next to the time fields opens it.
"""

from datetime import date as _date

from PyQt6.QtCore import QDateTime, QRectF, QSize, Qt, QTime, pyqtSignal as Signal
from PyQt6.QtGui import QBrush, QColor, QPainter, QPalette, QPen
from PyQt6.QtWidgets import (
    QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QPushButton, QTimeEdit, QToolButton, QVBoxLayout, QWidget,
)

from activitytrack import formats, timegrid
from activitytrack.i18n import _
from activitytrack.texts import hm

CELL, GAP, ROW = 22, 2, 24


class GridView(QWidget):
    """The cells: a click picks one, a drag or a second click a span."""

    changed = Signal()
    picked = Signal(int)

    def __init__(self, ranged, first, busy=(), parent=None):
        super().__init__(parent)
        self.ranged, self.first, self.busy = ranged, first, list(busy)
        self.a = self.b = None
        self.waiting = self.dragging = False
        self.shown = (None, None)
        self.label_w = 46 if formats.time_format() == formats.H12 else 28
        self.setMouseTracking(False)
        self.setMinimumSize(self.sizeHint())

    def sizeHint(self):
        return QSize(self._x(12), timegrid.WINDOW_HOURS * ROW)

    def selection(self):
        """Minutes (start, end) chosen; end None while the second cell is awaited."""
        if self.a is None:
            return self.shown
        start, end = timegrid.span(self.a, self.b)
        return start, None if self.waiting else end

    def _x(self, col):
        """Left edge of a column: a wider gap every 15 minutes."""
        return self.label_w + col * (CELL + GAP) + (col // 3) * 2

    def _cell_at(self, pos):
        row = int(pos.y() // ROW)
        if pos.y() < 0 or row >= timegrid.WINDOW_HOURS:
            return None
        for col in range(12):
            if self._x(col) <= pos.x() < self._x(col) + CELL + GAP + (2 if col % 3 == 2 else 0):
                return (self.first + row) * 12 + col
        return None

    def mousePressEvent(self, ev):
        i = self._cell_at(ev.position())
        if i is None:
            return
        if self.ranged and self.waiting:
            self.b, self.waiting = i, False
        else:
            self.a = self.b = i
            self.waiting = self.dragging = True
        self.update()
        self.changed.emit()

    def mouseMoveEvent(self, ev):
        if not self.dragging:
            return
        i = self._cell_at(ev.position())
        if i is not None and i != self.b:
            self.b = i
            self.update()
            self.changed.emit()

    def mouseReleaseEvent(self, ev):
        if not self.dragging:
            return
        self.dragging = False
        if not self.ranged:
            self.picked.emit(self.a * timegrid.STEP)
            return
        if self.b != self.a:
            self.waiting = False
        self.update()
        self.changed.emit()

    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pal = self.palette()
        base, mid = pal.color(QPalette.ColorRole.Base), pal.color(QPalette.ColorRole.Mid)
        cell = QColor(base).darker(108) if base.lightness() > 128 else QColor(base).lighter(140)
        on = pal.color(QPalette.ColorRole.Highlight)
        start, end = self.selection()
        for r in range(timegrid.WINDOW_HOURS):
            h = self.first + r
            y = r * ROW
            p.setPen(pal.color(QPalette.ColorRole.PlaceholderText))
            p.drawText(QRectF(0, y, self.label_w - 4, ROW), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                       formats.hour(h))
            for c in range(12):
                m = (h * 12 + c) * timegrid.STEP
                rect = QRectF(self._x(c), y + 1, CELL, ROW - 3)
                if start is None:
                    chosen = False
                else:
                    chosen = start <= m < end if end is not None else m == start - start % timegrid.STEP
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(on if chosen else cell)
                p.drawRoundedRect(rect, 4, 4)
                if not chosen and any(m < b and m + timegrid.STEP > a for a, b in self.busy):
                    p.setBrush(QBrush(mid, Qt.BrushStyle.BDiagPattern))
                    p.setPen(QPen(mid, 1, Qt.PenStyle.DashLine))
                    p.drawRoundedRect(rect, 4, 4)
        p.end()


class TimeGridDialog(QDialog):
    """
    A time, or a start and an end, on the grid. After exec(): start and end
    in minutes of the day (end None for a single time; above 1440 the next
    day), or exact for a time typed off the grid.
    """

    def __init__(self, day, start=None, end=None, ranged=False, busy=(), opened_end=False, parent=None):
        super().__init__(parent)
        self.setWindowTitle(_("Orari") if ranged else _("Orario"))
        self.ranged, self.opened_end = ranged, opened_end
        self.start = self.end = None
        at = start if start is not None else end
        first = timegrid.window_for(at) if at is not None else 7
        lay = QVBoxLayout(self)
        days = (_("lun"), _("mar"), _("mer"), _("gio"), _("ven"), _("sab"), _("dom"))
        self.head = QLabel()
        self.head.setStyleSheet("font-weight: 600")
        lay.addWidget(QLabel(f"{days[day.weekday()]} {formats.day(day)}"))
        lay.addWidget(self.head)
        self.hint = QLabel(_("Clicca l'ultima casella"))
        self.hint.setStyleSheet("color: palette(placeholder-text)")
        lay.addWidget(self.hint)
        self.grid = GridView(ranged, first, busy)
        self.grid.shown = (start, end if ranged else None)
        self.before = QPushButton(_("▲ Prima"), clicked=lambda: self._move(-3))
        self.after = QPushButton(_("Dopo ▼"), clicked=lambda: self._move(3))
        lay.addWidget(self.before)
        lay.addWidget(self.grid)
        lay.addWidget(self.after)
        row = QHBoxLayout()
        row.addWidget(QLabel(_("Orario esatto")))
        self.exact = QTimeEdit(QTime(at // 60 % 24, at % 60) if at is not None else QTime(9, 0))
        self.exact.setDisplayFormat(formats.qt_time())
        row.addWidget(self.exact)
        row.addWidget(QPushButton(_("Usa"), clicked=self._exact))
        row.addStretch()
        lay.addLayout(row)
        box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        box.accepted.connect(self._ok)
        box.rejected.connect(self.reject)
        lay.addWidget(box)
        self.grid.changed.connect(self._show)
        self.grid.picked.connect(self._picked)
        self._show()

    def _move(self, hours):
        self.grid.first = timegrid.shift(self.grid.first, hours)
        self.grid.update()

    def _show(self):
        start, end = self.grid.selection()
        if self.ranged:
            shown = [formats.minutes(x) if x is not None else "…" for x in (start, end)]
            text = " – ".join(shown)
            if start is not None and end is not None and end > start:
                text += " · " + hm((end - start) * 60_000)
        else:
            text = formats.minutes(start) if start is not None else "—"
        self.head.setText(text)
        self.hint.setVisible(self.ranged and self.grid.waiting)

    def _picked(self, minute):
        self.start = minute
        self.accept()

    def _exact(self):
        t = self.exact.time()
        minute = t.hour() * 60 + t.minute()
        if self.ranged and self.opened_end:
            self.end = minute
        else:
            self.start = minute
        self.accept()

    def _ok(self):
        g = self.grid
        if g.a is None:
            self.reject()
            return
        start, end = timegrid.span(g.a, g.b)
        if not self.ranged:
            self.start = start
        elif g.waiting:
            # one cell only: the field opened takes it, the other stays
            if self.opened_end:
                self.end = end
            else:
                self.start = start
        else:
            self.start, self.end = start, end
        self.accept()


def grid_button(parent=None):
    b = QToolButton(parent)
    b.setText("▦")
    b.setToolTip(_("Scegli sulla griglia degli orari"))
    return b


def _set_minute(edit, day, minute):
    """A QDateTimeEdit at a minute of a day (1440 and above: the next day)."""
    extra, minute = divmod(minute, 1440)
    dt = QDateTime(day, QTime(minute // 60, minute % 60)).addDays(extra)
    edit.setDateTime(dt)


def attach_range(work, start_edit, end_edit, skip=None, parent=None):
    """Grid buttons for a start and an end (QDateTimeEdit): (start button, end button)."""
    buttons = []
    for opened_end in (False, True):
        b = grid_button(parent)

        def open_(checked=False, opened_end=opened_end):
            qday = start_edit.date()
            day = _date(qday.year(), qday.month(), qday.day())
            s = start_edit.time()
            e = end_edit.time() if end_edit.isEnabled() else None
            end = None
            if e is not None:
                end = e.hour() * 60 + e.minute() + 1440 * start_edit.date().daysTo(end_edit.date())
            d = TimeGridDialog(day, s.hour() * 60 + s.minute(), end, ranged=end_edit.isEnabled(),
                               busy=work.busy(day, skip), opened_end=opened_end, parent=parent)
            if d.exec():
                if d.start is not None:
                    _set_minute(start_edit, qday, d.start)
                if d.end is not None:
                    _set_minute(end_edit, qday, d.end)
        b.clicked.connect(open_)
        buttons.append(b)
    return buttons


def attach_single(work, day_edit, time_edit, parent=None):
    """A grid button for a time of a day (a QDateEdit and a QTimeEdit)."""
    b = grid_button(parent)

    def open_():
        qday = day_edit.date()
        day = _date(qday.year(), qday.month(), qday.day())
        t = time_edit.time()
        d = TimeGridDialog(day, t.hour() * 60 + t.minute(), busy=work.busy(day), parent=parent)
        if d.exec() and d.start is not None:
            time_edit.setTime(QTime(d.start // 60, d.start % 60))
    b.clicked.connect(open_)
    return b
