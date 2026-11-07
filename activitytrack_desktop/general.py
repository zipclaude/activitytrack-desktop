# SPDX-License-Identifier: GPL-3.0-or-later
"""Settings → Generale: starting with the session and the updates of the paired server (docs/DESIGN.md §6.3)."""

import sys
import threading
import time

from PyQt6.QtCore import QObject, QSettings, Qt, QTimer, QUrl, pyqtSignal as Signal
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QFormLayout, QGroupBox, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget,
)

from activitytrack import formats, texts, updates
from activitytrack.i18n import _
from activitytrack.sync import Runner

from . import __version__, autostart

CHECK_EVERY_MS = 3600_000


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


class Updates(QObject):
    """
    What the paired server says of a newer version (activitytrack#1): its manifest comes with each sync and
    is checked against the key of the pairing link; asked again once a day. A notification once per version,
    with the button to download when this installation can (the package manager's cannot); the package is
    checked against its sha256 and then handed to the system.
    """

    found = Signal(object)
    # (path of the package or "", error)
    downloaded = Signal(str, str)
    _got = Signal(object)
    _fetched = Signal(str, str)

    def __init__(self, actions, notifier, service=None, parent=None):
        super().__init__(parent)
        self.actions, self.notifier = actions, notifier
        self.core = updates.Updates(actions.session, Runner(actions.session), lambda: actions.work.policy)
        self.status = updates.Status(updates.NONE)
        self._got.connect(self._result)
        self._fetched.connect(self._file)
        notifier.answered.connect(self._answer)
        if service is not None:
            service.changed.connect(lambda *_a: self.evaluate())
        self.timer = QTimer(self, interval=CHECK_EVERY_MS, timeout=self.maybe)
        self.timer.start()
        QTimer.singleShot(60_000, self.maybe)

    def maybe(self):
        if self.core.due(time.time()):
            self.check()
        else:
            self.evaluate()

    def evaluate(self):
        """What the last sync brought, without asking the server again."""
        self._got.emit(self.core.status())

    def check(self):
        """Asks the server now."""
        def work():
            try:
                self._got.emit(self.core.check())
            except Exception as e:
                self._got.emit(updates.Status(updates.ERROR, error=str(e) or type(e).__name__))
        threading.Thread(target=work, daemon=True).start()

    def _result(self, status):
        self.status = status
        self.found.emit(status)
        release = status.release
        s = QSettings()
        if status.state == updates.AVAILABLE and s.value("updates/notified", "") != release.version:
            s.setValue("updates/notified", release.version)
            buttons = [("download", _("Scarica"))] if status.downloadable else []
            self.notifier.show(f"update|{release.version}", _("ActivityTrack %s disponibile") % release.version,
                               texts.update_state(status, __version__), buttons, persistent=False)

    def _answer(self, key, action):
        if key.startswith("update|") and self.status.downloadable:
            self.download()

    def download(self):
        release = self.status.release
        if release is None or not self.status.downloadable:
            return

        def work():
            try:
                self._fetched.emit(str(self.core.download(release)), "")
            except Exception as e:
                self._fetched.emit("", str(e) or type(e).__name__)
        threading.Thread(target=work, daemon=True).start()

    def _file(self, path, error):
        self.downloaded.emit(path, error)
        if path:
            # the system's own way to install it: the software centre, the installer, the archive manager
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))


class GeneralPanel(QWidget):
    def __init__(self, actions, updater, parent=None):
        super().__init__(parent)
        self.actions, self.updater = actions, updater
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        start = QGroupBox(_("Avvio"))
        sl = QVBoxLayout(start)
        self.autostart = QCheckBox(_("Avvia ActivityTrack all'accesso, nell'area di notifica"))
        self.autostart.toggled.connect(self._autostart)
        sl.addWidget(self.autostart)
        lay.addWidget(start)
        # dates and times as on ActivityTrack Web; the command line and the terminal follow
        shown = QGroupBox(_("Date e orari"))
        fl = QFormLayout(shown)
        fl.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.FieldsStayAtSizeHint)
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
        self.check = QCheckBox(_("Controlla ogni giorno se il server ha una versione nuova"))
        self.betas = QCheckBox(_("Anche le versioni beta"))
        self.check.toggled.connect(updater.core.set_check)
        self.betas.toggled.connect(updater.core.set_betas)
        bl.addWidget(self.check)
        bl.addWidget(self.betas)
        row = QHBoxLayout()
        self.now = QPushButton(_("Controlla ora"), clicked=self._check_now)
        self.download = QPushButton(_("Scarica"), clicked=updater.download)
        self.download.hide()
        # plain text: what comes from the server is shown as it is
        self.result = QLabel(wordWrap=True, textFormat=Qt.TextFormat.PlainText)
        row.addWidget(self.now)
        row.addWidget(self.download)
        row.addWidget(self.result, 1)
        bl.addLayout(row)
        lay.addWidget(box)
        lay.addStretch()
        version = QLabel(f"ActivityTrack Desktop {__version__}")
        version.setProperty("role", "small")
        lay.addWidget(version)
        updater.found.connect(self._found)
        updater.downloaded.connect(self._downloaded)
        self.refresh()

    def add_group(self, box):
        """Another group of settings (the keyboard shortcuts), after the others."""
        lay = self.layout()
        # before the stretch and the version
        lay.insertWidget(lay.count() - 2, box)

    def refresh(self):
        p = self.actions.work.policy
        self.autostart.blockSignals(True)
        self.autostart.setChecked(autostart.enabled())
        self.autostart.blockSignals(False)
        self.date_format.setCurrentIndex(max(0, self.date_format.findData(formats.date_format())))
        self.time_format.setCurrentIndex(max(0, self.time_format.findData(formats.time_format())))
        check, betas = self.updater.core.settings()
        for box, value, key in ((self.check, check, "updateCheck"), (self.betas, betas, "updateBetas")):
            box.blockSignals(True)
            box.setChecked(value)
            box.setEnabled(not p.setting_fixed(key))
            box.setToolTip(_("Impostato dalla policy") if p.setting_fixed(key) else "")
            box.blockSignals(False)

    def _formats(self):
        formats.save(self.actions.session.store, self.date_format.currentData(), self.time_format.currentData())
        self.actions.changed_elsewhere()

    def _autostart(self, on):
        try:
            autostart.set_enabled(on)
        except OSError as e:
            self.result.setText(str(e))
        self.refresh()

    def _check_now(self):
        self.result.setText(_("Controllo…"))
        self.updater.check()

    def _found(self, status):
        self.result.setText(texts.update_state(status, __version__))
        self.download.setVisible(status.downloadable)
        self.download.setEnabled(True)

    def _downloaded(self, path, error):
        self.download.setEnabled(True)
        self.result.setText(_("Scaricato e controllato: %s") % path if path
                            else _("Scaricamento non riuscito: %s") % error)
