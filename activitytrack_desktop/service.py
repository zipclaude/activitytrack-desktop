# SPDX-License-Identifier: GPL-3.0-or-later
"""
When the desktop syncs (docs/DESIGN.md §5.2): a few seconds after a local
change, `sync/head` every 30 s and a sync when the server moved, when the
network comes back and after the PC slept. The network calls run in a
worker thread; the interface hears the outcome through signals.
"""

import time

from PySide6.QtCore import QObject, QThread, QTimer, Signal, Slot

from .net import NetworkError
from .sync import SyncEngine, SyncFailed, SyncIncompatible, SyncRevoked

TICK_MS = 30_000
DEBOUNCE_MS = 3_000
# a wall-clock jump this much larger than the tick means the PC slept
SLEEP_GAP_S = 90


class _Worker(QObject):
    finished = Signal(str, str)

    def __init__(self, session):
        super().__init__()
        self.session = session

    @Slot(bool)
    def run(self, full):
        """[full]: sync even when the server did not move."""
        http = self.session.http()
        if http is None:
            self.finished.emit("unpaired", "")
            return
        store = self.session.store
        engine = SyncEngine(store, http)
        try:
            if not full and not store.has_pending():
                head = engine.head()
                if head.get("rev") == store.cursor:
                    store.set_state("incompatible", None)
                    self.finished.emit("idle", "")
                    return
            result = engine.sync()
            store.set_state("incompatible", None)
            self.finished.emit("ok", result.errors[0] if result.errors else "")
        except SyncRevoked:
            store.set_state("revoked", True)
            self.finished.emit("revoked", "")
        except SyncIncompatible as e:
            store.set_state("incompatible", e.code)
            self.finished.emit("incompatible", e.code)
        except (NetworkError, SyncFailed) as e:
            self.finished.emit("offline" if isinstance(e, NetworkError) else "failed", str(e))
        except Exception as e:
            self.finished.emit("failed", f"{type(e).__name__}: {e}")
        finally:
            # the worker thread's connection: the next run may come after a long sleep
            store.close()


class SyncService(QObject):
    # state: ok, idle, offline, failed, revoked, incompatible, unpaired; detail
    changed = Signal(str, str)
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

    def start(self):
        self._tick.start()
        self.sync(full=True)

    def stop(self):
        self._tick.stop()
        self._thread.quit()
        self._thread.wait(10_000)

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

    def _on_tick(self):
        now = time.time()
        slept = now - self._wall > TICK_MS / 1000 + SLEEP_GAP_S
        self._wall = now
        self.sync(full=slept)

    def _watch_network(self):
        from PySide6.QtNetwork import QNetworkInformation

        if not QNetworkInformation.loadDefaultBackend():
            return
        info = QNetworkInformation.instance()
        info.reachabilityChanged.connect(
            lambda r: r == QNetworkInformation.Reachability.Online and self.sync(full=True))
