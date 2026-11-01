# SPDX-License-Identifier: GPL-3.0-or-later
"""
The tray icon, drawn so that it needs no image files: a disc in the colour
of the state (the app's: work green, pause yellow, travel blue; grey when
nothing runs) with its sign, and a red dot when the sync needs attention.
"""

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap

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
