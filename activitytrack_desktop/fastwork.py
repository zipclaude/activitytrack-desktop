# SPDX-License-Identifier: GPL-3.0-or-later
"""
The library's Work reads the segments of one activity by reading all of them and keeping the ones it wants
(Work.segments: `store.all("segment")` filtered in Python), and every JSON of every segment is parsed again
at each call. Drawing the Home asks for the segments of every activity, several times each (the displayed
state, the totals, the span, the last boundary): with a few hundred activities one redraw read the table
thousands of times and took more than a second on the interface's thread (desktop#34).

Inside `with work.snapshot():` the segments are read once and grouped by activity; the views draw under it.
Outside it, or in a command, the library's own reading is used: what a command decides is never read
from a snapshot. (The right fix is the library's: segments of one activity with an SQL filter, or a grouped
reading for the lists; this class goes away with it.)
"""

from collections import defaultdict
from contextlib import contextmanager, nullcontext

from activitytrack.work import Work


class SnapshotWork(Work):
    _by_entry = None

    @contextmanager
    def snapshot(self):
        """The segments of the store read once, for the reads of a redraw (re-entrant, GUI thread only)."""
        if self._by_entry is not None:
            yield self
            return
        index = defaultdict(list)
        for s in self.store.all("segment"):
            index[s.get("entryUid")].append(s)
        self._by_entry = index
        try:
            yield self
        finally:
            self._by_entry = None

    def segments(self, entry_uid):
        index = self._by_entry
        if index is None:
            return super().segments(entry_uid)
        return sorted(index.get(entry_uid, ()), key=lambda s: (s.get("startUtcMs") or 0, s.get("endUtcMs") or 2 ** 62))


def snapshot(work):
    """work.snapshot() when it has one (the desktop's), else nothing: for the views, whatever Work they got."""
    return work.snapshot() if hasattr(work, "snapshot") else nullcontext()
