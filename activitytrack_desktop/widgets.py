# SPDX-License-Identifier: GPL-3.0-or-later
"""
The app's components, painted (docs/DESIGN.md §6.4): cards with the
company's colour band, the round command buttons with their name under
them, the state pill, the Home list's marks, the tag dots, the chips of
the filters and the navigation rail.
"""

from PyQt6.QtCore import QPointF, QRectF, QSize, Qt, pyqtSignal as Signal
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import (
    QAbstractButton, QDialog, QDialogButtonBox, QFrame, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QSizePolicy, QToolButton, QVBoxLayout, QWidget,
)

from . import icons, theme


def role(widget, name):
    """A style-sheet role (theme.style_sheet), set again on a shown widget."""
    widget.setProperty("role", name)
    widget.style().unpolish(widget)
    widget.style().polish(widget)
    return widget


def label(text="", kind=None, wrap=False):
    w = QLabel(text)
    if kind:
        w.setProperty("role", kind)
    w.setWordWrap(wrap)
    return w


def with_key(text, key):
    """A tooltip with its keyboard shortcut: "Pausa (Ctrl+P)"."""
    return f"{text} ({key})" if key else text


class Elided(QLabel):
    """One line, cut with "…" when the room ends (the app's maxLines = 1)."""

    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.setMinimumWidth(40)

    def paintEvent(self, ev):
        p = QPainter(self)
        p.setFont(self.font())
        p.setPen(self.palette().color(self.foregroundRole()))
        text = self.fontMetrics().elidedText(self.text(), Qt.TextElideMode.ElideRight, self.contentsRect().width())
        p.drawText(self.contentsRect(), int(self.alignment() | Qt.AlignmentFlag.AlignVCenter), text)
        p.end()


class Surface(QFrame):
    """
    A card (Material filled card on the page's grey): rounded, the colour
    [band] on its start edge (Colors.kt Banded), lighter on hover when it
    opens something.
    """

    clicked = Signal()
    BAND = 6

    def __init__(self, band=None, radius=16, clickable=False, parent=None):
        super().__init__(parent)
        self.band, self.radius, self.clickable = band, radius, clickable
        self.hover = False
        self.outlined = False
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, clickable)
        if clickable:
            self.setCursor(Qt.CursorShape.PointingHandCursor)

    def enterEvent(self, ev):
        self.hover = self.clickable
        self.update()
        super().enterEvent(ev)

    def leaveEvent(self, ev):
        self.hover = False
        self.update()
        super().leaveEvent(ev)

    def mouseReleaseEvent(self, ev):
        inside = self.rect().contains(ev.position().toPoint())
        if self.clickable and ev.button() == Qt.MouseButton.LeftButton and inside:
            self.clicked.emit()
        super().mouseReleaseEvent(ev)

    def paintEvent(self, ev):
        t = theme.tokens()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        path = QPainterPath()
        path.addRoundedRect(r, self.radius, self.radius)
        fill = QColor(t.surface2 if self.hover else t.surface)
        if self.outlined:
            fill = QColor(t.bg)
        p.fillPath(path, fill)
        if self.band:
            p.save()
            p.setClipPath(path)
            p.fillRect(QRectF(0, 0, self.BAND, self.height()), QColor(self.band))
            p.restore()
        p.setPen(QPen(QColor(t.line if self.outlined else t.line_soft), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(path)
        p.end()


class RoundButton(QAbstractButton):
    """A command: a disc in its colour with the icon (CommandIconButton), or tonal when [colour] is None."""

    def __init__(self, icon, colour=None, size=56, tip="", parent=None):
        super().__init__(parent)
        self.icon_name, self.colour, self.diameter = icon, colour, size
        self.setFixedSize(size, size)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover)
        self.setToolTip(tip)
        self.setAccessibleName(tip)

    def sizeHint(self):
        return QSize(self.diameter, self.diameter)

    def paintEvent(self, ev):
        t = theme.tokens()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self.colour:
            fill, ink = QColor(self.colour), QColor(theme.on_colour(self.colour))
        else:
            fill, ink = QColor(t.secondary_c), QColor(t.on_secondary_c)
        if not self.isEnabled():
            fill, ink = QColor(t.surface3), QColor(t.muted)
        elif self.isDown():
            fill = fill.darker(115)
        elif self.underMouse():
            fill = fill.lighter(110) if fill.lightness() < 160 else fill.darker(106)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(fill)
        p.drawEllipse(r)
        if self.hasFocus():
            p.setPen(QPen(QColor(t.text), 2))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(r.adjusted(1, 1, -1, -1))
        side = self.diameter * (0.54 if self.diameter >= 48 else 0.5)
        icons.paint(p, self.icon_name, QRectF((self.width() - side) / 2, (self.height() - side) / 2, side, side), ink)
        p.end()


class Command(QWidget):
    """A round button with its name under it (the app's LabeledCommand, issue #91)."""

    def __init__(self, text, icon, colour, slot, size=56, tip=None, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        self.button = RoundButton(icon, colour, size, tip or text)
        self.button.clicked.connect(lambda _c=False: slot())
        lay.addWidget(self.button, 0, Qt.AlignmentFlag.AlignHCenter)
        self.text = QLabel(text)
        self.text.setFont(theme.font("label", QFont.Weight.Medium))
        self.text.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        lay.addWidget(self.text)
        self.setMinimumWidth(size + 16)


class Pill(QWidget):
    """The state, coloured, with its icon: "In lavoro dalle 03:11" (StatePill)."""

    def __init__(self, text, colour, icon=None, parent=None):
        super().__init__(parent)
        self.text, self.colour, self.icon_name = text, colour, icon
        self.setFont(theme.font("body", QFont.Weight.DemiBold))
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

    def sizeHint(self):
        fm = QFontMetrics(self.font())
        h = fm.height() + 10
        return QSize(fm.horizontalAdvance(self.text) + 24 + (h - 6 if self.icon_name else 0), h)

    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect())
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(self.colour))
        p.drawRoundedRect(r, r.height() / 2, r.height() / 2)
        ink = QColor(theme.on_colour(self.colour))
        x = 12.0
        if self.icon_name:
            side = r.height() - 10
            icons.paint(p, self.icon_name, QRectF(x - 2, 5, side, side), ink)
            x += side + 4
        p.setPen(ink)
        p.setFont(self.font())
        p.drawText(QRectF(x, 0, r.width() - x, r.height()), Qt.AlignmentFlag.AlignVCenter, self.text)
        p.end()


def state_icon(entry):
    """The icon of a state, the command's that leads to it."""
    from activitytrack.work import ACTIVE, PAUSE, SUSPENDED, TRAVEL
    if entry.get("status") == ACTIVE:
        return {PAUSE: "pause", TRAVEL: "travel"}.get(entry.get("mode"), "play")
    return "suspend" if entry.get("status") == SUSPENDED else "stop"


class Tag(QWidget):
    """A small chip: "P1", "in ritardo" (the app's to-do chips)."""

    def __init__(self, text, fill, ink, parent=None):
        super().__init__(parent)
        self.text, self.fill, self.ink = text, fill, ink
        self.setFont(theme.font("small", QFont.Weight.DemiBold))
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

    def sizeHint(self):
        fm = QFontMetrics(self.font())
        return QSize(fm.horizontalAdvance(self.text) + 16, fm.height() + 4)

    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect())
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(self.fill))
        p.drawRoundedRect(r, r.height() / 2, r.height() / 2)
        p.setPen(QColor(self.ink))
        p.setFont(self.font())
        p.drawText(r, Qt.AlignmentFlag.AlignCenter, self.text)
        p.end()


# the Home list's marks (HomeList.kt, the web's .mark): overdue, planned, open, done, ignored; to complete, closed
MARKS = ("overdue", "planned", "open", "done", "ignored", "to_complete", "closed")


class Mark(QWidget):
    """The state of a row of the Home list, at its start."""

    def __init__(self, kind, parent=None):
        super().__init__(parent)
        self.kind = kind
        self.setFixedSize(30, 30)

    def paintEvent(self, ev):
        t = theme.tokens()
        k = self.kind
        fill, ink = {
            "overdue": (t.err_bg, t.danger), "planned": (t.secondary_c, t.on_secondary_c),
            "to_complete": (t.warn_bg, t.text), "done": (t.surface3, t.muted), "ignored": (t.surface3, t.muted),
            "closed": (t.surface3, t.muted),
        }.get(k, (None, t.muted))
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        if fill:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(fill))
        else:
            p.setPen(QPen(QColor(t.line), 1))
            p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(r)
        c = r.center()
        glyph = {"planned": "clock", "done": "done", "to_complete": "edit"}.get(k)
        if glyph:
            icons.paint(p, glyph, QRectF(c.x() - 8, c.y() - 8, 16, 16), ink)
        elif k == "overdue":
            p.setPen(QColor(ink))
            f = theme.font("title", QFont.Weight.Bold)
            p.setFont(f)
            p.drawText(r, Qt.AlignmentFlag.AlignCenter, "!")
        elif k == "ignored":
            p.setPen(QPen(QColor(ink), 2, cap=Qt.PenCapStyle.RoundCap))
            p.drawLine(QPointF(c.x() - 5, c.y()), QPointF(c.x() + 5, c.y()))
        elif k == "closed":
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(ink))
            p.drawRoundedRect(QRectF(c.x() - 5, c.y() - 5, 10, 10), 2, 2)
        else:
            p.setPen(QPen(QColor(ink), 1.6))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(c, 4.5, 4.5)
        p.end()


class TagDots(QWidget):
    """The tags' colours at the top right of a card (issue #133): at most four dots, then "+n"."""

    MAX = 4

    def __init__(self, tags, colours, parent=None):
        super().__init__(parent)
        self.tags = list(tags or [])
        self.colours = colours
        self.setFont(theme.font("small"))
        self.setVisible(bool(self.tags))
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.setToolTip(", ".join(self.tags))

    def sizeHint(self):
        n = min(len(self.tags), self.MAX)
        extra = QFontMetrics(self.font()).horizontalAdvance(f"+{len(self.tags) - self.MAX}") + 3 \
            if len(self.tags) > self.MAX else 0
        return QSize(max(1, n * 13 + extra), 12)

    def paintEvent(self, ev):
        t = theme.tokens()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        x = 1.0
        for name in self.tags[:self.MAX]:
            p.setBrush(QColor(self.colours.get(name) or (t.muted if t.dark else theme.NO_COLOR)))
            p.drawEllipse(QRectF(x, 1.5, 9, 9))
            x += 13
        if len(self.tags) > self.MAX:
            p.setPen(QColor(t.muted))
            p.drawText(QRectF(x, -2, 40, 16), Qt.AlignmentFlag.AlignVCenter, f"+{len(self.tags) - self.MAX}")
        p.end()


def chip(text="", checkable=False, menu=None, tip=""):
    """A filter chip: outlined, tonal when on (or changed), with its drop-down menu."""
    b = QToolButton()
    b.setProperty("chip", True)
    b.setText(text)
    b.setCheckable(checkable)
    b.setToolTip(tip)
    b.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
    if menu is not None:
        b.setMenu(menu)
        b.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
    return b


def set_changed(button, on):
    """A filter chip away from its default: tonal, as the web's .changed."""
    if bool(button.property("changed")) != on:
        button.setProperty("changed", on)
        button.style().unpolish(button)
        button.style().polish(button)


def icon_button(icon, tip, slot=None, menu=None):
    """A plain icon button (more, search): the icon in the text colour, a round hover."""
    b = QToolButton()
    b.setProperty("role", "icon")
    t = theme.tokens()
    b.setIcon(icons.material(icon, t.muted, t.line))
    b.setIconSize(QSize(20, 20))
    b.setProperty("icon_name", icon)
    b.setToolTip(tip)
    b.setAccessibleName(tip)
    if slot is not None:
        b.clicked.connect(lambda _c=False: slot())
    if menu is not None:
        b.setMenu(menu)
        b.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
    return b


def button(text, slot, kind=None, icon=None, tip=""):
    """A Material button: outlined, or "primary" (filled) or "tonal"; with an icon before the text."""
    from PyQt6.QtWidgets import QPushButton
    b = QPushButton(text)
    if kind:
        b.setProperty("role", kind)
    if icon:
        t = theme.tokens()
        ink = {"primary": t.on_primary, "tonal": t.on_secondary_c}.get(kind, t.primary)
        b.setIcon(icons.material(icon, ink, t.muted))
        b.setIconSize(QSize(18, 18))
        b.setProperty("icon_name", icon)
    b.setToolTip(tip)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    b.clicked.connect(lambda _c=False: slot())
    return b


def section_head(text, late=False):
    """A section of a list in capitals, red when it is late (the app's labelMedium in primary or error)."""
    w = QLabel(text.upper())
    w.setProperty("role", "section-late" if late else "section")
    w.setContentsMargins(4, 10, 0, 2)
    f = w.font()
    f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 0.6)
    w.setFont(f)
    return w


class RailItem(QAbstractButton):
    """A destination of the rail: the icon in a pill when chosen, its name under it (Material navigation rail)."""

    def __init__(self, text, icon, tip="", parent=None):
        super().__init__(parent)
        self.setText(text)
        self.icon_name = icon
        self.setCheckable(True)
        self.setAutoExclusive(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover)
        self.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self.setFont(theme.font("label", QFont.Weight.DemiBold))
        self.setToolTip(tip or text)
        self.setAccessibleName(text)
        self.alert = False

    def sizeHint(self):
        return QSize(88, 64)

    def paintEvent(self, ev):
        t = theme.tokens()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pill = QRectF((self.width() - 56) / 2, 6, 56, 32)
        if self.isChecked() or self.underMouse() or self.hasFocus():
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(255, 255, 255, 56 if self.isChecked() else 26))
            p.drawRoundedRect(pill, 16, 16)
        ink = QColor(t.on_bar) if self.isChecked() else QColor(255, 255, 255, 205)
        icons.paint(p, self.icon_name, QRectF(pill.center().x() - 12, pill.center().y() - 12, 24, 24), ink)
        if self.alert:
            p.setPen(QPen(QColor(t.bar), 2))
            p.setBrush(QColor("#ff5449"))
            p.drawEllipse(QPointF(pill.center().x() + 11, pill.top() + 7), 5, 5)
        p.setPen(ink)
        p.setFont(self.font())
        p.drawText(QRectF(0, pill.bottom() + 3, self.width(), 18), Qt.AlignmentFlag.AlignHCenter, self.text())
        p.end()


class Rail(QWidget):
    """The window's navigation on the left, on the theme's green (the web's rail): the logo, the sections."""

    chosen = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(96)
        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(4, 14, 4, 12)
        self.lay.setSpacing(6)
        self.logo = QWidget()
        self.logo.setFixedSize(88, 54)
        self.logo.paintEvent = self._paint_logo
        self.lay.addWidget(self.logo)
        self.items = {}
        self.top = QVBoxLayout()
        self.top.setSpacing(4)
        self.lay.addLayout(self.top)
        self.lay.addStretch()
        self.bottom = QVBoxLayout()
        self.lay.addLayout(self.bottom)

    def _paint_logo(self, ev):
        p = QPainter(self.logo)
        icons.logo(p, QRectF((self.logo.width() - 40) / 2, 2, 40, 40), QColor(255, 255, 255, 46))
        p.end()

    def add(self, key, text, icon, tip=""):
        item = RailItem(text, icon, tip)
        item.clicked.connect(lambda _c=False, k=key: self.chosen.emit(k))
        self.top.addWidget(item)
        self.items[key] = item
        return item

    def add_bottom(self, text, icon, slot, tip=""):
        item = RailItem(text, icon, tip)
        item.setCheckable(False)
        item.setAutoExclusive(False)
        item.clicked.connect(lambda _c=False: slot())
        self.bottom.addWidget(item)
        return item

    def select(self, key):
        if key in self.items:
            self.items[key].setChecked(True)

    def paintEvent(self, ev):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(theme.tokens().bar))
        p.end()


def choose(parent, title, rows):
    """
    The small list of a command with several possible activities: [(uid, text)];
    the first chosen, Enter confirms. The uid chosen, or None.
    """
    d = QDialog(parent)
    d.setWindowTitle(title)
    d.setMinimumWidth(420)
    lay = QVBoxLayout(d)
    head = label(title, "h2")
    lay.addWidget(head)
    listing = QListWidget()
    for uid, text in rows:
        item = QListWidgetItem(text)
        item.setData(Qt.ItemDataRole.UserRole, uid)
        listing.addItem(item)
    listing.setCurrentRow(0)
    listing.itemActivated.connect(lambda _i: d.accept())
    lay.addWidget(listing)
    box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
    box.accepted.connect(d.accept)
    box.rejected.connect(d.reject)
    lay.addWidget(box)
    d.listing = listing
    listing.setFocus()
    if d.exec() and listing.currentItem() is not None:
        return listing.currentItem().data(Qt.ItemDataRole.UserRole)
    return None


def page(title, *actions):
    """A section's head: its name, large, and its buttons on the right."""
    w = QWidget()
    lay = QHBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(8)
    lay.addWidget(label(title, "page"))
    lay.addStretch()
    for a in actions:
        lay.addWidget(a)
    return w


def recolour(root):
    """The icons of the buttons in the new theme's colours (the painted widgets read it themselves)."""
    from PyQt6.QtWidgets import QPushButton
    t = theme.tokens()
    for b in root.findChildren(QToolButton) + root.findChildren(QPushButton):
        name = b.property("icon_name")
        if not name:
            continue
        if isinstance(b, QToolButton):
            b.setIcon(icons.material(name, t.muted, t.line))
        else:
            kind = b.property("role")
            ink = {"primary": t.on_primary, "tonal": t.on_secondary_c}.get(kind, t.primary)
            b.setIcon(icons.material(name, ink, t.muted))
    root.update()
