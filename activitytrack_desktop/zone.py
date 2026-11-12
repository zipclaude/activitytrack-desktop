# SPDX-License-Identifier: GPL-3.0-or-later
"""The system's time zone: apart from the other modules, which translate their texts when imported."""

from PyQt6.QtCore import QTimeZone


def system_zone():
    """Qt's zone: the system's IANA one on Windows too (None when Qt does not know it)."""
    z = bytes(QTimeZone.systemTimeZoneId()).decode()
    return z or None
