# SPDX-License-Identifier: GPL-3.0-or-later
"""
The icons, drawn so that they need no image files. The tray icon: a disc
in the colour of the state (the app's: work green, pause yellow, travel
blue; grey when nothing runs) with its sign, and a red dot when the sync
needs attention. The window's: the app's Material icons (Apache-2.0, the
web's _icons.html) as SVG path data, painted in any colour.
"""

import re

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QGuiApplication, QIcon, QPainter, QPainterPath, QPen, QPixmap, QTransform

IDLE, WORK, PAUSE, TRAVEL = "idle", "work", "pause", "travel"
COLOURS = {IDLE: "#6f7680", WORK: "#2e7d32", PAUSE: "#f9a825", TRAVEL: "#1565c0"}
SIZES = (16, 22, 24, 32, 48, 64, 128)


def _draw(size, state, alert):
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    s = size / 64
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(COLOURS[state]))
    p.drawEllipse(QRectF(2 * s, 2 * s, 60 * s, 60 * s))
    p.setBrush(QColor("white"))
    if state == WORK:
        tri = QPainterPath(QPointF(25 * s, 18 * s))
        tri.lineTo(47 * s, 32 * s)
        tri.lineTo(25 * s, 46 * s)
        tri.closeSubpath()
        p.drawPath(tri)
    elif state == PAUSE:
        p.drawRect(QRectF(21 * s, 18 * s, 8 * s, 28 * s))
        p.drawRect(QRectF(35 * s, 18 * s, 8 * s, 28 * s))
    elif state == TRAVEL:
        # a car, as the app's travel button
        p.drawRoundedRect(QRectF(15 * s, 28 * s, 34 * s, 12 * s), 3 * s, 3 * s)
        roof = QPainterPath(QPointF(20 * s, 28 * s))
        roof.lineTo(24 * s, 19 * s)
        roof.lineTo(40 * s, 19 * s)
        roof.lineTo(44 * s, 28 * s)
        roof.closeSubpath()
        p.drawPath(roof)
        p.drawEllipse(QRectF(18 * s, 38 * s, 8 * s, 8 * s))
        p.drawEllipse(QRectF(38 * s, 38 * s, 8 * s, 8 * s))
    else:
        # a clock: what ActivityTrack keeps
        pen = QPen(QColor("white"), 5 * s)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QRectF(16 * s, 16 * s, 32 * s, 32 * s))
        p.drawLine(QPointF(32 * s, 32 * s), QPointF(32 * s, 22 * s))
        p.drawLine(QPointF(32 * s, 32 * s), QPointF(39 * s, 36 * s))
        p.setPen(Qt.PenStyle.NoPen)
    if alert:
        p.setBrush(QColor("white"))
        p.drawEllipse(QRectF(40 * s, 0, 24 * s, 24 * s))
        p.setBrush(QColor("#c62828"))
        p.drawEllipse(QRectF(43 * s, 3 * s, 18 * s, 18 * s))
    p.end()
    return pm


def icon(state=IDLE, alert=False):
    i = QIcon()
    for size in SIZES:
        i.addPixmap(_draw(size, state, alert))
    return i


# ---- the window's icons ----

# the app's drawables (24×24), as in the web's _icons.html
PATHS = {
    "home": "M12,3L2.5,11.5H5V20.5H10V14.5H14V20.5H19V11.5H21.5Z",
    "todo": "M22,7h-9v2h9V7zM22,15h-9v2h9V15zM5.54,11L2,7.46l1.41,-1.41l2.12,2.12l4.24,-4.24l1.41,1.41L5.54,11z"
            "M5.54,19L2,15.46l1.41,-1.41l2.12,2.12l4.24,-4.24l1.41,1.41L5.54,19z",
    "agenda": "M4,5.5H20V20.5H4ZM6,10V18.5H18V10ZM7,2.5H9V7H7ZM15,2.5H17V7H15ZM8,12H11V15H8Z",
    "report": "M4,20.5V18.5H20V20.5ZM5,17V11H8.5V17ZM10.25,17V5H13.75V17ZM15.5,17V8.5H19V17Z",
    "settings": "M19.14,12.94c0.04,-0.3 0.06,-0.61 0.06,-0.94c0,-0.32 -0.02,-0.64 -0.07,-0.94l2.03,-1.58c0.18,-0.14 "
                "0.23,-0.41 0.12,-0.61l-1.92,-3.32c-0.12,-0.22 -0.37,-0.29 -0.59,-0.22l-2.39,0.96c-0.5,-0.38 "
                "-1.03,-0.7 -1.62,-0.94L14.4,2.81c-0.04,-0.24 -0.24,-0.41 -0.48,-0.41h-3.84c-0.24,0 -0.43,0.17 "
                "-0.47,0.41L9.25,5.35C8.66,5.59 8.12,5.92 7.63,6.29L5.24,5.33c-0.22,-0.08 -0.47,0 -0.59,0.22L2.74,8.87"
                "C2.62,9.08 2.66,9.34 2.86,9.48l2.03,1.58C4.84,11.36 4.8,11.69 4.8,12s0.02,0.64 0.07,0.94l-2.03,1.58"
                "c-0.18,0.14 -0.23,0.41 -0.12,0.61l1.92,3.32c0.12,0.22 0.37,0.29 0.59,0.22l2.39,-0.96c0.5,0.38 "
                "1.03,0.7 1.62,0.94l0.36,2.54c0.05,0.24 0.24,0.41 0.48,0.41h3.84c0.24,0 0.44,-0.17 0.47,-0.41l0.36,"
                "-2.54c0.59,-0.24 1.13,-0.56 1.62,-0.94l2.39,0.96c0.22,0.08 0.47,0 0.59,-0.22l1.92,-3.32c0.12,-0.22 "
                "0.07,-0.47 -0.12,-0.61L19.14,12.94zM12,15.6c-1.98,0 -3.6,-1.62 -3.6,-3.6s1.62,-3.6 3.6,-3.6"
                "s3.6,1.62 3.6,3.6S13.98,15.6 12,15.6z",
    "play": "M8,5V19L19,12Z",
    "pause": "M6,5H10V19H6ZM14,5H18V19H14Z",
    "stop": "M6,6H18V18H6Z",
    "travel": "M4,12L6,5.5H18L20,12V19.5H17V17.5H7V19.5H4ZM7,11H17L15.8,7.5H8.2ZM6,13V15.5H9.5V13Z"
              "M14.5,13V15.5H18V13Z",
    "exclaim": "M10.5,4H13.5V14H10.5ZM10.5,17H13.5V20H10.5Z",
    "dot": "M12,7.5C14.5,7.5 16.5,9.5 16.5,12C16.5,14.5 14.5,16.5 12,16.5C9.5,16.5 7.5,14.5 7.5,12"
           "C7.5,9.5 9.5,7.5 12,7.5Z",
    "bin": "M6,19C6,20.1 6.9,21 8,21H16C17.1,21 18,20.1 18,19V7H6ZM19,4H15.5L14.5,3H9.5L8.5,4H5V6H19Z",
    "checkbox": "M4,4H20V20H4ZM6,6V18H18V6Z",
    "add": "M11,5H13V11H19V13H13V19H11V13H5V11H11Z",
    "done": "M9,16.2L4.8,12L3.4,13.4L9,19L21,7L19.6,5.6Z",
    "clear": "M6.4,5L12,10.6L17.6,5L19,6.4L13.4,12L19,17.6L17.6,19L12,13.4L6.4,19L5,17.6L10.6,12L5,6.4Z",
    "sync": "M12,4V1L8,5l4,4V6c3.31,0 6,2.69 6,6 0,1.01 -0.25,1.97 -0.7,2.8l1.46,1.46C19.54,15.03 20,13.57 20,12"
            "c0,-4.42 -3.58,-8 -8,-8zM12,18c-3.31,0 -6,-2.69 -6,-6 0,-1.01 0.25,-1.97 0.7,-2.8L5.24,7.74"
            "C4.46,8.97 4,10.43 4,12c0,4.42 3.58,8 8,8v3l4,-4 -4,-4v3z",
    "edit": "M3,17.25V21h3.75L17.81,9.94l-3.75,-3.75L3,17.25zM20.71,7.04c0.39,-0.39 0.39,-1.02 0,-1.41l-2.34,-2.34"
            "c-0.39,-0.39 -1.02,-0.39 -1.41,0l-1.83,1.83 3.75,3.75 1.83,-1.83z",
    "search": "M15.5,14h-0.79l-0.28,-0.27C15.41,12.59 16,11.11 16,9.5 16,5.91 13.09,3 9.5,3S3,5.91 3,9.5 5.91,16 "
              "9.5,16c1.61,0 3.09,-0.59 4.23,-1.57l0.27,0.28v0.79l5,4.99L20.49,19l-4.99,-5zM9.5,14C7.01,14 5,11.99 "
              "5,9.5S7.01,5 9.5,5 14,7.01 14,9.5 11.99,14 9.5,14z",
    "clock": "M11.99,2C6.47,2 2,6.48 2,12s4.47,10 9.99,10C17.52,22 22,17.52 22,12S17.52,2 11.99,2zM12,20"
             "c-4.42,0 -8,-3.58 -8,-8s3.58,-8 8,-8 8,3.58 8,8 -3.58,8 -8,8zM12.5,7H11v6l5.25,3.15 0.75,-1.23 "
             "-4.5,-2.67z",
    "restore": "M13,3c-4.97,0 -9,4.03 -9,9H1l3.89,3.89 0.07,0.14L9,12H6c0,-3.87 3.13,-7 7,-7s7,3.13 7,7 -3.13,7 "
               "-7,7c-1.93,0 -3.68,-0.79 -4.94,-2.06l-1.42,1.42C8.27,19.99 10.51,21 13,21c4.97,0 9,-4.03 9,-9"
               "s-4.03,-9 -9,-9z",
    "devices": "M4,6h18V4H4c-1.1,0 -2,0.9 -2,2v11H0v3h14v-3H4V6zM23,8h-6c-0.55,0 -1,0.45 -1,1v10c0,0.55 0.45,1 1,1"
               "h6c0.55,0 1,-0.45 1,-1V9c0,-0.55 -0.45,-1 -1,-1zM22,17h-4v-7h4v7z",
}
_TOKEN = re.compile(r"[MmLlHhVvCcSsZz]|[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?")
_ARGS = {"M": 2, "L": 2, "H": 1, "V": 1, "C": 6, "S": 4, "Z": 0}
_cache = {}


def svg_path(d):
    """A QPainterPath of SVG path data: the commands the icons use (M L H V C S Z, absolute or relative)."""
    tokens = _TOKEN.findall(d)
    path = QPainterPath()
    path.setFillRule(Qt.FillRule.WindingFill)
    x = y = sx = sy = 0.0
    ctrl = None
    cmd, i = None, 0
    while i < len(tokens):
        if tokens[i].isalpha():
            cmd = tokens[i]
            i += 1
        up, rel = cmd.upper(), cmd.islower()
        n = _ARGS[up]
        a = [float(v) for v in tokens[i:i + n]]
        i += n
        ox, oy = (x, y) if rel else (0.0, 0.0)
        if up == "M":
            x, y = a[0] + ox, a[1] + oy
            sx, sy = x, y
            path.moveTo(x, y)
            # more pairs after a move are lines
            cmd = "l" if rel else "L"
            ctrl = None
        elif up == "L":
            x, y = a[0] + ox, a[1] + oy
            path.lineTo(x, y)
            ctrl = None
        elif up == "H":
            x = a[0] + ox
            path.lineTo(x, y)
            ctrl = None
        elif up == "V":
            y = a[0] + (y if rel else 0.0)
            path.lineTo(x, y)
            ctrl = None
        elif up == "C":
            c1, c2 = QPointF(a[0] + ox, a[1] + oy), QPointF(a[2] + ox, a[3] + oy)
            x, y = a[4] + ox, a[5] + oy
            path.cubicTo(c1, c2, QPointF(x, y))
            ctrl = c2
        elif up == "S":
            c1 = QPointF(2 * x - ctrl.x(), 2 * y - ctrl.y()) if ctrl is not None else QPointF(x, y)
            c2 = QPointF(a[0] + ox, a[1] + oy)
            x, y = a[2] + ox, a[3] + oy
            path.cubicTo(c1, c2, QPointF(x, y))
            ctrl = c2
        else:
            path.closeSubpath()
            x, y = sx, sy
            ctrl = None
    return path


def shape(name):
    """The icon's path in a 24×24 box; the moon and the dots are drawn, their SVG has arcs."""
    if name not in _cache:
        if name == "suspend":
            outer, inner = QPainterPath(), QPainterPath()
            outer.addEllipse(QRectF(3, 4, 17, 17))
            inner.addEllipse(QRectF(9.5, 0.5, 15, 15))
            _cache[name] = outer.subtracted(inner)
        elif name == "more":
            p = QPainterPath()
            for cx in (5, 12, 19):
                p.addEllipse(QPointF(cx, 12), 2, 2)
            _cache[name] = p
        else:
            _cache[name] = svg_path(PATHS[name])
    return _cache[name]


def paint(p, name, rect, colour):
    """The icon [name] filled with [colour], scaled into [rect]."""
    s = min(rect.width(), rect.height()) / 24
    t = QTransform()
    t.translate(rect.x() + (rect.width() - 24 * s) / 2, rect.y() + (rect.height() - 24 * s) / 2)
    t.scale(s, s)
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(colour))
    p.drawPath(t.map(shape(name)))
    p.restore()


def pixmap(name, colour, size=24):
    ratio = QGuiApplication.instance().devicePixelRatio() if QGuiApplication.instance() else 1.0
    pm = QPixmap(int(size * ratio), int(size * ratio))
    pm.setDevicePixelRatio(ratio)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    paint(p, name, QRectF(0, 0, size, size), colour)
    p.end()
    return pm


def material(name, colour, disabled=None):
    """A QIcon of the icon in [colour] (and [disabled] when greyed), at the usual sizes."""
    i = QIcon()
    for size in (16, 20, 24, 32):
        i.addPixmap(pixmap(name, colour, size))
        if disabled:
            i.addPixmap(pixmap(name, disabled, size), QIcon.Mode.Disabled)
    return i


def logo(p, rect, background):
    """The app's mark (the web's i-logo): a stopwatch on a rounded square."""
    s = rect.width() / 108
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.translate(rect.topLeft())
    p.scale(s, s)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(background))
    p.drawRoundedRect(QRectF(0, 0, 108, 108), 26, 26)
    pen = QPen(QColor("white"), 5)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawEllipse(QPointF(54, 58), 20, 20)
    p.drawLine(QPointF(54, 58), QPointF(54, 46))
    p.drawLine(QPointF(54, 58), QPointF(62, 62))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor("white"))
    p.drawRect(QRectF(48, 30, 12, 6))
    p.restore()
