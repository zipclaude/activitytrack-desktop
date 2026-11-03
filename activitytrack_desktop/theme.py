# SPDX-License-Identifier: GPL-3.0-or-later
"""
The app's Material 3 look (docs/DESIGN.md §6.4): the tonal palette of the
launcher green #1F5C4A, light or dark as the system, on Qt's Fusion style
so that it looks the same on KDE, XFCE, GNOME and Windows. The tokens are
the web's (activitytrack-web app.css): neutral pages, the green on the
rail, the buttons and what is selected; the activities keep the app's
colours. Painted widgets read the current tokens at every paint; the
others take them from the palette and the application's style sheet.
"""

import os
import tempfile
from dataclasses import dataclass

from PyQt6.QtCore import QObject, Qt, pyqtSignal as Signal
from PyQt6.QtGui import QColor, QFont, QPalette
from PyQt6.QtWidgets import QApplication

from activitytrack.work import ACTIVE, CLOSED, PAUSE, SUSPENDED, TO_COMPLETE, TRAVEL, WORK

# the app's colours of the commands and states (CommandButtons.kt)
GREEN, YELLOW, BLUE, ORANGE, RED = "#2e7d32", "#f9a825", "#1565c0", "#ef6c00", "#c62828"
# dark icon and text on yellow: white would fail the contrast
ON_YELLOW = "#212121"
COMMANDS = {WORK: GREEN, PAUSE: YELLOW, TRAVEL: BLUE, "SUSPEND": ORANGE, "STOP": RED, "REOPEN": ORANGE}
# a tag without a colour, a company without one in the agenda (Colors.kt NO_COLOR)
NO_COLOR = "#6b7280"


@dataclass(frozen=True)
class Tokens:
    dark: bool
    bg: str
    surface: str
    surface2: str
    surface3: str
    text: str
    muted: str
    line: str
    line_soft: str
    primary: str
    on_primary: str
    secondary_c: str
    on_secondary_c: str
    danger: str
    err_bg: str
    on_err_bg: str
    warn_bg: str
    chip: str
    bar: str
    on_bar: str = "#ffffff"
    bar_muted: str = "rgba(255, 255, 255, 200)"
    bar_sel: str = "rgba(255, 255, 255, 52)"
    bar_hover: str = "rgba(255, 255, 255, 26)"


# the tones of the launcher green (web app.css --a10…--a90)
A10, A20, A30, A40, A80, A90 = "#002116", "#003827", "#00513b", "#1f6b52", "#8bd6b6", "#a6f2d1"

LIGHT = Tokens(
    dark=False, bg="#f4f4f5", surface="#ffffff", surface2="#ececee", surface3="#e1e1e4", text="#1a1a1b",
    muted="#4e4e53", line="#c6c6cb", line_soft="#e2e2e5", primary=A40, on_primary="#ffffff", secondary_c=A90,
    on_secondary_c=A10, danger="#ba1a1a", err_bg="#ffdad6", on_err_bg="#410002", warn_bg="#ffe0b2", chip="#e3e3e6",
    bar="#1f5c4a",
)
DARK = Tokens(
    dark=True, bg="#121212", surface="#222225", surface2="#2b2b2f", surface3="#35353a", text="#e4e4e6",
    muted="#aaaaaf", line="#4a4a4e", line_soft="#303033", primary=A80, on_primary=A20, secondary_c=A30,
    on_secondary_c=A90, danger="#ffb4ab", err_bg="#5c1a14", on_err_bg="#ffdad6", warn_bg="#4a3000", chip="#303033",
    bar="#173f34",
)

# the type scale, relative to the system's font (Material: body 14, title large 22, headline 28…)
SCALE = {"small": 0.86, "label": 0.93, "body": 1.0, "title": 1.15, "card": 1.5, "page": 1.75, "timer": 2.5}


class _Theme(QObject):
    """The tokens in use; [changed] when the system went from light to dark or back."""

    changed = Signal()

    def __init__(self):
        super().__init__()
        self.tokens = LIGHT
        self.forced = None
        self.system_palette = None
        self.base_pt = 10.0
        self.folder = None


_theme = None


def _state():
    global _theme
    if _theme is None:
        _theme = _Theme()
    return _theme


def tokens():
    return _state().tokens


def notifier():
    return _state()


def system_dark(app):
    """
    The system's choice: QStyleHints.colorScheme (Qt ≥ 6.5), else the
    lightness of the palette the system gave (Qt 6.4, Ubuntu 24.04).
    """
    scheme = getattr(app.styleHints(), "colorScheme", None)
    kinds = getattr(Qt, "ColorScheme", None)
    if scheme is not None and kinds is not None:
        s = scheme()
        if s == kinds.Dark:
            return True
        if s == kinds.Light:
            return False
    palette = _state().system_palette or app.palette()
    return palette.color(QPalette.ColorRole.Window).lightness() < 128


def install(app=None, dark=None):
    """
    The look on the application: Fusion, the palette, the style sheet.
    [dark] forces one (the screenshots); None follows the system, also when
    it changes while the application runs.
    """
    app = app or QApplication.instance()
    st = _state()
    first = st.system_palette is None
    if first:
        # before ours replaces it: Qt 6.4 tells the system's choice by it only
        st.system_palette = QPalette(app.palette())
        # the text never smaller than Material's body (14 px, about 10 pt): Windows' 9 pt is raised
        st.base_pt = max(app.font().pointSizeF(), 10.0)
        if app.font().pointSizeF() < st.base_pt:
            f = app.font()
            f.setPointSizeF(st.base_pt)
            app.setFont(f)
        app.setStyle("Fusion")
        signal = getattr(app.styleHints(), "colorSchemeChanged", None)
        if signal is not None:
            signal.connect(lambda *_a: _follow(app))
    if dark is not None:
        st.forced = dark
    _apply(app, st.forced if st.forced is not None else system_dark(app))


def _follow(app):
    st = _state()
    if st.forced is None:
        _apply(app, system_dark(app))


def _arrows(t):
    """
    The arrows of the drop-downs and spin boxes, drawn into files: a style
    sheet that shapes those boxes takes their arrows as images only.
    """
    from PyQt6.QtCore import QPointF
    from PyQt6.QtGui import QPainter, QPainterPath, QPixmap
    st = _state()
    if st.folder is None:
        st.folder = tempfile.TemporaryDirectory(prefix="activitytrack-desktop-")
    out = {}
    for name, colour in (("down", t.muted), ("up", t.muted), ("down-off", t.line), ("up-off", t.line)):
        pm = QPixmap(20, 12)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        tri = QPainterPath()
        if name.startswith("down"):
            tri.moveTo(QPointF(3, 2))
            tri.lineTo(QPointF(17, 2))
            tri.lineTo(QPointF(10, 10))
        else:
            tri.moveTo(QPointF(3, 10))
            tri.lineTo(QPointF(17, 10))
            tri.lineTo(QPointF(10, 2))
        tri.closeSubpath()
        p.fillPath(tri, QColor(colour))
        p.end()
        out[name] = _save(pm, name, t)
    # the tick of a checked menu item, on the primary colour
    from . import icons
    out["check"] = _save(icons.pixmap("done", t.on_primary, 14), "check", t)
    return out


def _save(pm, name, t):
    path = os.path.join(_state().folder.name, f"{name}-{'dark' if t.dark else 'light'}.png")
    pm.save(path)
    # forward slashes: a style sheet's url() on Windows too
    return path.replace(os.sep, "/")


def _apply(app, dark):
    st = _state()
    changed = st.tokens.dark != dark
    st.tokens = t = DARK if dark else LIGHT
    app.setPalette(palette(t))
    app.setStyleSheet(style_sheet(t, st.base_pt, _arrows(t)))
    if changed:
        st.changed.emit()


def palette(t):
    p = QPalette()
    R, G = QPalette.ColorRole, QPalette.ColorGroup
    roles = {
        R.Window: t.bg, R.WindowText: t.text, R.Base: t.surface, R.AlternateBase: t.surface2, R.Text: t.text,
        R.Button: t.surface2, R.ButtonText: t.text, R.BrightText: "#ffffff", R.Highlight: t.primary,
        R.HighlightedText: t.on_primary, R.ToolTipBase: t.surface3, R.ToolTipText: t.text, R.Link: t.primary,
        R.LinkVisited: t.primary, R.PlaceholderText: t.muted, R.Light: t.surface, R.Midlight: t.line_soft,
        R.Mid: t.line, R.Dark: t.line, R.Shadow: "#000000",
    }
    for role, colour in roles.items():
        p.setColor(role, QColor(colour))
    faded = QColor(t.muted)
    faded.setAlpha(150)
    for role in (R.WindowText, R.Text, R.ButtonText, R.PlaceholderText):
        p.setColor(G.Disabled, role, faded)
    p.setColor(G.Disabled, R.Base, QColor(t.surface2))
    p.setColor(G.Disabled, R.Button, QColor(t.surface2))
    p.setColor(G.Disabled, R.Highlight, QColor(t.line))
    return p


def pt(kind):
    """A size of the type scale, in points."""
    return round(_state().base_pt * SCALE[kind], 1)


def font(kind="body", weight=None, base=None):
    f = QFont(base or QApplication.font())
    f.setPointSizeF(pt(kind))
    if weight is not None:
        f.setWeight(weight)
    return f


def alpha(colour, a):
    """A colour with opacity [a] (0–1), as a style sheet's rgba()."""
    c = QColor(colour)
    return f"rgba({c.red()}, {c.green()}, {c.blue()}, {int(a * 255)})"


def style_sheet(t, base_pt, arrows=None):
    """The application's style sheet: the web's buttons, fields, chips, menus and cards."""
    size = {k: round(base_pt * v, 1) for k, v in SCALE.items()}
    arrows = arrows or {}
    down, up = arrows.get("down", ""), arrows.get("up", "")
    down_off, up_off = arrows.get("down-off", ""), arrows.get("up-off", "")
    check = arrows.get("check", "")
    hover, pressed = alpha(t.primary, 0.08), alpha(t.primary, 0.16)
    primary_hover = QColor(t.primary).lighter(112 if t.dark else 118).name()
    tonal_hover = (QColor(t.secondary_c).lighter(120) if t.dark else QColor(t.secondary_c).darker(106)).name()
    fields = "QLineEdit, QPlainTextEdit, QTextEdit, QComboBox, QAbstractSpinBox"
    return f"""
QMainWindow, QDialog {{ background: {t.bg}; }}
QToolTip {{ background: {t.surface3}; color: {t.text}; border: 1px solid {t.line_soft}; border-radius: 6px;
    padding: 4px 8px; }}
QLabel[role="muted"] {{ color: {t.muted}; }}
QLabel[role="small"] {{ color: {t.muted}; font-size: {size['small']}pt; }}
QLabel[role="error"] {{ color: {t.danger}; }}
QLabel[role="field"] {{ color: {t.muted}; font-weight: 600; padding-top: 7px; }}
QLabel[role="page"] {{ font-size: {size['page']}pt; }}
QLabel[role="h2"] {{ font-size: {size['title']}pt; font-weight: 600; }}
QLabel[role="section"] {{ color: {t.primary}; font-size: {size['small']}pt; font-weight: 700; }}
QLabel[role="section-late"] {{ color: {t.danger}; font-size: {size['small']}pt; font-weight: 700; }}

QPushButton {{ border: 1px solid {t.line}; border-radius: 16px; padding: 0 18px; min-height: 32px;
    color: {t.primary}; background: transparent; font-weight: 600; }}
QPushButton:hover {{ background: {hover}; }}
QPushButton:pressed {{ background: {pressed}; }}
QPushButton:focus {{ border: 2px solid {t.primary}; padding: 0 17px; }}
QPushButton[role="primary"] {{ background: {t.primary}; color: {t.on_primary};
    border: 0; padding: 0 20px; }}
QPushButton[role="primary"]:hover {{ background: {primary_hover}; }}
QPushButton[role="primary"]:focus {{ border: 2px solid {t.text}; padding: 0 18px; }}
QPushButton[role="tonal"] {{ background: {t.secondary_c}; color: {t.on_secondary_c}; border: 0; padding: 0 18px; }}
QPushButton[role="tonal"]:hover {{ background: {tonal_hover}; }}
QPushButton[role="text"] {{ border: 0; padding: 0 10px; }}
QPushButton[role="danger"] {{ color: {t.danger}; }}
QPushButton:disabled {{ color: {alpha(t.muted, 0.6)}; border-color: {t.line_soft}; background: transparent; }}
QPushButton[role="primary"]:disabled {{ background: {t.surface3}; }}
QPushButton[seg="first"], QPushButton[seg="mid"], QPushButton[seg="last"] {{ border-radius: 0; color: {t.text};
    font-weight: 500; padding: 0 22px; }}
QPushButton[seg="first"]:checked, QPushButton[seg="mid"]:checked, QPushButton[seg="last"]:checked {{
    background: {t.secondary_c}; color: {t.on_secondary_c}; }}
QPushButton[seg="first"] {{ border-top-left-radius: 16px; border-bottom-left-radius: 16px; }}
QPushButton[seg="mid"], QPushButton[seg="last"] {{ border-left: 0; }}
QPushButton[seg="last"] {{ border-top-right-radius: 16px; border-bottom-right-radius: 16px; }}
QPushButton[seg="first"]:focus, QPushButton[seg="mid"]:focus, QPushButton[seg="last"]:focus {{
    border: 1px solid {t.primary}; padding: 0 22px; }}
QPushButton[seg="mid"]:focus, QPushButton[seg="last"]:focus {{ border-left: 0; }}

{fields} {{ background: {t.surface}; color: {t.text}; border: 1px solid {t.line}; border-radius: 10px;
    padding: 6px 10px; selection-background-color: {t.primary}; selection-color: {t.on_primary}; }}
QLineEdit, QComboBox, QAbstractSpinBox {{ min-height: 22px; }}
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus, QComboBox:focus, QAbstractSpinBox:focus {{
    border: 2px solid {t.primary}; padding: 5px 9px; }}
QLineEdit:disabled, QPlainTextEdit:disabled, QComboBox:disabled, QAbstractSpinBox:disabled {{
    background: {t.surface2}; color: {alpha(t.muted, 0.7)}; border-color: {t.line_soft}; }}
QComboBox, QDateTimeEdit[calendarPopup="true"] {{ padding-right: 26px; }}
QComboBox:focus, QDateTimeEdit[calendarPopup="true"]:focus {{ padding-right: 25px; }}
QAbstractSpinBox {{ padding-right: 24px; }}
QAbstractSpinBox:focus {{ padding-right: 23px; }}
QComboBox::drop-down, QDateTimeEdit::drop-down {{ border: 0; width: 26px; subcontrol-origin: padding;
    subcontrol-position: center right; }}
QComboBox::down-arrow, QDateTimeEdit::down-arrow, QAbstractSpinBox::down-arrow {{ image: url({down});
    width: 10px; height: 6px; }}
QAbstractSpinBox::up-arrow {{ image: url({up}); width: 10px; height: 6px; }}
QComboBox::down-arrow:disabled, QDateTimeEdit::down-arrow:disabled, QAbstractSpinBox::down-arrow:disabled {{
    image: url({down_off}); }}
QAbstractSpinBox::up-arrow:disabled {{ image: url({up_off}); }}
QComboBox QAbstractItemView {{ background: {t.surface}; color: {t.text}; border: 1px solid {t.line_soft};
    selection-background-color: {t.secondary_c}; selection-color: {t.on_secondary_c}; outline: 0; }}
QAbstractSpinBox::up-button, QAbstractSpinBox::down-button {{ border: 0; width: 18px; background: transparent; }}
QAbstractSpinBox::up-button {{ subcontrol-position: top right; margin: 3px 4px 0 0; }}
QAbstractSpinBox::down-button {{ subcontrol-position: bottom right; margin: 0 4px 3px 0; }}

QCheckBox, QRadioButton {{ spacing: 10px; }}
QGroupBox {{ background: {t.surface}; border: 1px solid {t.line_soft}; border-radius: 14px; margin-top: 22px;
    padding: 14px 14px 10px 14px; }}
QGroupBox::title {{ subcontrol-origin: margin; subcontrol-position: top left; left: 6px; top: 2px;
    padding: 0 4px; color: {t.muted}; font-weight: 600; }}

QMenu {{ background: {t.surface}; color: {t.text}; border: 1px solid {t.line_soft}; border-radius: 8px;
    padding: 6px; }}
QMenu::item {{ padding: 7px 28px 7px 28px; border-radius: 8px; }}
QMenu::item:selected {{ background: {t.surface3}; }}
QMenu::item:disabled {{ color: {t.muted}; }}
QMenu::separator {{ height: 1px; background: {t.line_soft}; margin: 5px 8px; }}
QMenu::indicator {{ width: 14px; height: 14px; left: 8px; border-radius: 4px; border: 2px solid {t.muted}; }}
QMenu::indicator:non-exclusive:checked {{ background: {t.primary}; border-color: {t.primary};
    image: url({check}); }}
QMenu::indicator:exclusive {{ border-radius: 9px; }}
QMenu::indicator:exclusive:checked {{ border-color: {t.primary}; background: qradialgradient(cx: 0.5, cy: 0.5,
    radius: 0.5, fx: 0.5, fy: 0.5, stop: 0 {t.primary}, stop: 0.55 {t.primary}, stop: 0.65 transparent,
    stop: 1 transparent); }}

QToolButton[chip="true"] {{ border: 1px solid {t.line}; border-radius: 8px; padding: 6px 12px; color: {t.text};
    background: transparent; font-weight: 500; }}
QToolButton[chip="true"]:hover {{ background: {t.surface2}; }}
QToolButton[chip="true"]:checked, QToolButton[changed="true"] {{ background: {t.secondary_c};
    color: {t.on_secondary_c}; border-color: {t.secondary_c}; }}
QToolButton[chip="true"]:disabled {{ color: {alpha(t.muted, 0.6)}; border-color: {t.line_soft}; }}
QToolButton[chip="true"]::menu-indicator {{ image: none; width: 0; }}
QToolButton[role="icon"] {{ border: 0; border-radius: 18px; padding: 6px; background: transparent; }}
QToolButton[role="icon"]:hover {{ background: {t.surface3}; }}
QToolButton[role="icon"]::menu-indicator {{ image: none; width: 0; }}
QToolButton {{ color: {t.text}; }}

QScrollArea {{ background: transparent; border: 0; }}
QScrollArea > QWidget > QWidget[page="true"] {{ background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 12px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {t.line}; border-radius: 4px; min-height: 36px; margin: 0 2px; }}
QScrollBar::handle:vertical:hover {{ background: {t.muted}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
QScrollBar:horizontal {{ background: transparent; height: 12px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: {t.line}; border-radius: 4px; min-width: 36px; margin: 2px 0; }}

QListWidget {{ background: {t.surface}; border: 1px solid {t.line_soft}; border-radius: 12px; padding: 4px;
    outline: 0; }}
QListWidget::item {{ padding: 10px 12px; border-radius: 8px; color: {t.text}; }}
QListWidget::item:selected {{ background: {t.secondary_c}; color: {t.on_secondary_c}; }}
QListWidget::item:hover:!selected {{ background: {t.surface2}; }}
QCalendarWidget QWidget {{ alternate-background-color: {t.surface2}; }}
QCalendarWidget QToolButton {{ color: {t.text}; padding: 4px 8px; border-radius: 8px; }}
QCalendarWidget QToolButton:hover {{ background: {t.surface3}; }}
"""


def state_colour(entry):
    """The colour of an activity's state (stateStyle): the command that leads to it; None when closed."""
    status = entry.get("status")
    if status == ACTIVE:
        return COMMANDS.get(entry.get("mode"), GREEN)
    if status == SUSPENDED:
        return ORANGE
    if status == TO_COMPLETE:
        return RED
    return None if status == CLOSED else NO_COLOR


def on_colour(colour):
    """The icon and text colour on a command's colour."""
    return ON_YELLOW if QColor(colour) == QColor(YELLOW) else "#ffffff"


def rgb(value):
    """A synced colour (0xRRGGBB) as #rrggbb; None when unset or not a number."""
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return f"#{value & 0xFFFFFF:06x}"


def band(work, company_uid, client_uid=None):
    """The colour band of a card (Colors.kt Banded): the company's chosen colour, else the client's; None."""
    for type_, uid in (("company", company_uid), ("client", client_uid)):
        r = work.store.get(type_, uid) if uid else None
        if r is not None and rgb(r.get("color")):
            return rgb(r.get("color"))
    return None


def tag_colours(work):
    """{name: #rrggbb} of the tags with a colour."""
    out = {}
    for r in work.store.all("tag"):
        if r.get("name") and rgb(r.get("color")):
            out[r["name"]] = rgb(r["color"])
    return out
