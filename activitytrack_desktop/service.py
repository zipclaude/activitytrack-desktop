# SPDX-License-Identifier: GPL-3.0-or-later
"""
When the desktop syncs (docs/DESIGN.md §5.2): a few seconds after a local
change, `sync/head` every 30 s and a sync when the server moved, when the
network comes back and after the PC slept. The network calls run in a
worker thread; the interface hears the outcome through signals.
"""

import time

from PyQt6 import sip
from PyQt6.QtCore import QObject, QThread, QTimer, pyqtSignal as Signal, pyqtSlot as Slot

from activitytrack.sync import Runner

TICK_MS = 30_000
DEBOUNCE_MS = 3_000
# how often the data folder is looked at for the other interfaces' changes
WATCH_MS = 2_000
# a wall-clock jump this much larger than the tick means the PC slept
SLEEP_GAP_S = 90
# how long quitting waits for a sync running: the window must not freeze
STOP_WAIT_MS = 2_000


class _Worker(QObject):
    finished = Signal(str, str)

    def __init__(self, session):
        super().__init__()
        self.session = session
        self.runner = Runner(session)

    @Slot(bool)
    def run(self, full):
        """[full]: sync even when the server did not move."""
        try:
            self.finished.emit(*self.runner.run(full))
        finally:
            # the worker thread's connection: the next run may come after a long sleep
            self.session.store.close()


class SyncService(QObject):
    # state: ok, idle, offline, failed, revoked, incompatible, unpaired; detail
    changed = Signal(str, str)
    # the data changed from another connection: the cli, the tui, this service's worker
    elsewhere = Signal()
    _run = Signal(bool)

    def __init__(self, session, parent=None):
        super().__init__(parent)
        self.session = session
        self.state, self.detail = "idle", ""
        self.busy = False
        self._again = None
        self._thread = QThread()
        self._worker = _Worker(session)
        self._worker.moveToThread(self._thread)
        self._run.connect(self._worker.run)
        self._worker.finished.connect(self._done)
        self._thread.start()
        self._tick = QTimer(self, interval=TICK_MS, timeout=self._on_tick)
        self._debounce = QTimer(self, singleShot=True, interval=DEBOUNCE_MS, timeout=lambda: self.sync(full=True))
        self._wall = time.time()
        self._watch_network()
        self._version = None
        self._watch = QTimer(self, interval=WATCH_MS, timeout=self._watch_data)

    def start(self):
        self._tick.start()
        self._watch.start()
        self.sync(full=True)

    def stop(self, wait_ms=STOP_WAIT_MS):
        """False when a sync still runs after [wait_ms]: it is left to the end of the process."""
        self._tick.stop()
        self._watch.stop()
        self._debounce.stop()
        self._thread.quit()
        if self._thread.wait(wait_ms):
            return True
        # Qt aborts the process when a running QThread is destroyed: the thread and its worker
        # pass to C++, which never deletes them
        sip.transferto(self._thread, None)
        sip.transferto(self._worker, None)
        return False

    def changed_here(self):
        """A local change: pushed in a few seconds, several changes together."""
        self._debounce.start()

    def sync(self, full=False):
        if self.session.account is None or self.session.store.get_state("revoked"):
            return
        if self.busy:
            self._again = bool(self._again) or full
            return
        self.busy = True
        self._run.emit(full)

    @Slot(str, str)
    def _done(self, state, detail):
        self.busy = False
        self.state, self.detail = state, detail
        self.changed.emit(state, detail)
        if self._again is not None:
            full, self._again = self._again, None
            self.sync(full)

    def _watch_data(self):
        """
        Another interface wrote (SQLite's data_version moves on another
        connection's commit): the views redraw, and its changes leave.
        """
        version = self.session.store.db.execute("PRAGMA data_version").fetchone()[0]
        if self._version is not None and version != self._version:
            self.elsewhere.emit()
            if self.session.store.has_pending():
                self.changed_here()
        self._version = version

    def _on_tick(self):
        now = time.time()
        slept = now - self._wall > TICK_MS / 1000 + SLEEP_GAP_S
        self._wall = now
        self.sync(full=slept)

    def _watch_network(self):
        from PyQt6.QtNetwork import QNetworkInformation

        if not QNetworkInformation.loadDefaultBackend():
            return
        info = QNetworkInformation.instance()
        info.reachabilityChanged.connect(
            lambda r: r == QNetworkInformation.Reachability.Online and self.sync(full=True))
