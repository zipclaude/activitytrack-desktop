# SPDX-License-Identifier: GPL-3.0-or-later
"""Settings → Generale: starting with the session and the update check (docs/DESIGN.md §6.3)."""

import html
import sys
import threading
import time

from PyQt6.QtCore import QObject, QSettings, Qt, QTimer, QUrl, pyqtSignal as Signal
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QFormLayout, QGroupBox, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget,
)

from activitytrack import formats, updates
from activitytrack.i18n import _

from . import __version__, autostart

CHECK_EVERY_MS = 3600_000
# the releases' pages: any other address in GitHub's answer is not opened
RELEASES_SITE = "https://github.com/"


def release_page(release):
    """The page of [release], or the project's releases when GitHub's answer points elsewhere."""
    if release.url.startswith(RELEASES_SITE):
        return release.url
    return f"{RELEASES_SITE}{updates.REPOSITORY}/releases"


def first_start():
    """A tray application starts with the session: switched on at the first start (Linux; on Windows the installer)."""
    s = QSettings()
    if s.value("autostart/done", False, type=bool):
        return
    s.setValue("autostart/done", True)
    if sys.platform != "win32" and not autostart.enabled():
        try:
            autostart.set_enabled(True)
        except OSError:
            pass


def update_settings(policy):
    """(check, betas): the user's choice, the policy's when it fixes them; a pre-release follows the betas."""
    s = QSettings()
    check = policy.setting("updateCheck", True)
    betas = policy.setting("updateBetas", "-" in __version__)
    if not policy.setting_fixed("updateCheck"):
        check = s.value("updates/check", check, type=bool)
    if not policy.setting_fixed("updateBetas"):
        betas = s.value("updates/betas", betas, type=bool)
    return check, betas


class Updates(QObject):
    """Once a day, a newer release on GitHub: a notification that opens its page."""

    found = Signal(object)
    _got = Signal(object, str)

    def __init__(self, actions, notifier, parent=None):
        super().__init__(parent)
        self.actions, self.notifier = actions, notifier
        self.latest = None
        self.error = ""
        self._got.connect(self._result)
        notifier.answered.connect(self._answer)
        self.timer = QTimer(self, interval=CHECK_EVERY_MS, timeout=self.maybe)
        self.timer.start()
        QTimer.singleShot(60_000, self.maybe)

    def maybe(self):
        check, _betas = update_settings(self.actions.work.policy)
        last = QSettings().value("updates/last", 0, type=float)
        if check and time.time() - last >= updates.DAY_S:
            self.check()

    def check(self):
        _check, betas = update_settings(self.actions.work.policy)

        def work():
            try:
                self._got.emit(updates.newer(updates.fetch(), __version__, betas), "")
            except Exception as e:
                self._got.emit(None, str(e) or type(e).__name__)
        threading.Thread(target=work, daemon=True).start()

    def _result(self, release, error):
        self.error = error
        if not error:
            QSettings().setValue("updates/last", time.time())
        self.latest = release
        self.found.emit(release)
        s = QSettings()
        if release is not None and s.value("updates/notified", "") != release.version:
            s.setValue("updates/notified", release.version)
            body = _("Nuova versione beta su GitHub.") if release.beta else _("Nuova versione su GitHub.")
            self.notifier.show(f"update|{release.version}", _("ActivityTrack %s disponibile") % release.version,
                               body, [("open", _("Scarica"))], persistent=False)

    def _answer(self, key, action):
        if key.startswith("update|") and self.latest is not None:
            QDesktopServices.openUrl(QUrl(release_page(self.latest)))


class GeneralPanel(QWidget):
    def __init__(self, actions, updater, parent=None):
        super().__init__(parent)
        self.actions, self.updater = actions, updater
        lay = QVBoxLayout(self)
        title = QLabel(_("Generale"))
        title.setStyleSheet("font-size: 18pt")
        lay.addWidget(title)
        self.autostart = QCheckBox(_("Avvia ActivityTrack all'accesso, nell'area di notifica"))
        self.autostart.toggled.connect(self._autostart)
        lay.addWidget(self.autostart)
        # dates and times as on ActivityTrack Web; the command line and the terminal follow
        shown = QGroupBox(_("Date e orari"))
        fl = QFormLayout(shown)
        self.date_format = QComboBox()
        for value, text in ((formats.EU, _("europeo (31/12/2026)")), (formats.US, _("americano (12/31/2026)")),
                            (formats.ISO, _("ISO (2026-12-31)"))):
            self.date_format.addItem(text, value)
        self.time_format = QComboBox()
        for value, text in ((formats.H24, _("24 ore (18:30)")), (formats.H12, _("12 ore (6:30 PM)"))):
            self.time_format.addItem(text, value)
        fl.addRow(_("Formato delle date"), self.date_format)
        fl.addRow(_("Formato degli orari"), self.time_format)
        self.date_format.activated.connect(self._formats)
        self.time_format.activated.connect(self._formats)
        lay.addWidget(shown)
        box = QGroupBox(_("Aggiornamenti"))
        bl = QVBoxLayout(box)
        self.check = QCheckBox(_("Controlla ogni giorno se c'è una versione nuova su GitHub"))
        self.betas = QCheckBox(_("Anche le versioni beta"))
        self.check.toggled.connect(lambda on: self._save("updates/check", on))
        self.betas.toggled.connect(lambda on: self._save("updates/betas", on))
        bl.addWidget(self.check)
        bl.addWidget(self.betas)
        row = QHBoxLayout()
        self.now = QPushButton(_("Controlla ora"), clicked=self._check_now)
        # rich text, always: what comes from outside is escaped
        self.result = QLabel(openExternalLinks=True, textFormat=Qt.TextFormat.RichText)
        row.addWidget(self.now)
        row.addWidget(self.result, 1)
        bl.addLayout(row)
        lay.addWidget(box)
        lay.addStretch()
        lay.addWidget(QLabel(f"ActivityTrack Desktop {__version__}"))
        updater.found.connect(self._found)
        self.refresh()

    def refresh(self):
        p = self.actions.work.policy
        self.autostart.blockSignals(True)
        self.autostart.setChecked(autostart.enabled())
        self.autostart.blockSignals(False)
        self.date_format.setCurrentIndex(max(0, self.date_format.findData(formats.date_format())))
        self.time_format.setCurrentIndex(max(0, self.time_format.findData(formats.time_format())))
        check, betas = update_settings(p)
        for box, value, key in ((self.check, check, "updateCheck"), (self.betas, betas, "updateBetas")):
            box.blockSignals(True)
            box.setChecked(value)
            box.setEnabled(not p.setting_fixed(key))
            box.setToolTip(_("Impostato dalla policy") if p.setting_fixed(key) else "")
            box.blockSignals(False)

    def _formats(self):
        formats.save(self.actions.session.store, self.date_format.currentData(), self.time_format.currentData())
        self.actions.changed_elsewhere()

    def _save(self, key, on):
        QSettings().setValue(key, on)

    def _autostart(self, on):
        try:
            autostart.set_enabled(on)
        except OSError as e:
            self.result.setText(html.escape(str(e)))
        self.refresh()

    def _check_now(self):
        self.result.setText(_("Controllo…"))
        self.updater.check()

    def _found(self, release):
        if self.updater.error:
            self.result.setText(html.escape(_("GitHub non raggiungibile: %s") % self.updater.error))
        elif release is None:
            self.result.setText(_("Hai l'ultima versione."))
        else:
            self.result.setText(f'<a href="{html.escape(release_page(release))}">'
                                + html.escape(_("Scarica la %s") % release.version) + "</a>")
