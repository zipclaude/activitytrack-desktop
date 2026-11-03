# SPDX-License-Identifier: GPL-3.0-or-later
"""
Which activity a command without a card means (the keyboard shortcuts,
the command line): an entry uid, None when there is nothing to do, or a
list of uids, the most recent first, when the user has to choose.
"""

from activitytrack.work import ACTIVE, PAUSE, SUSPENDED, TRAVEL, WORK


def _most_recent(work, entries):
    return sorted(entries, key=lambda e: -work.last_boundary(e["uid"]))


def _one_or_many(entries):
    if not entries:
        return None
    if len(entries) == 1:
        return entries[0]["uid"]
    return [e["uid"] for e in entries]


def pause_target(work):
    """The most recent activity at work or travelling."""
    moving = [e for e in work.running() if e.get("status") == ACTIVE and e.get("mode") in (WORK, TRAVEL)]
    return _most_recent(work, moving)[0]["uid"] if moving else None


def resume_target(work):
    """The activity on pause (a choice when several are), else the latest suspended."""
    running = work.running()
    paused = [e for e in running if e.get("status") == ACTIVE and e.get("mode") == PAUSE]
    if paused:
        return _one_or_many(_most_recent(work, paused))
    suspended = [e for e in running if e.get("status") == SUSPENDED]
    return _most_recent(work, suspended)[0]["uid"] if suspended else None


def stop_target(work, focused_uid=None):
    """
    The activity shown in the big card ([focused_uid]) when it is running;
    else the only active one, else the only one running; a choice among
    several.
    """
    running = work.running()
    if focused_uid is not None and any(e["uid"] == focused_uid for e in running):
        return focused_uid
    active = [e for e in running if e.get("status") == ACTIVE]
    if len(active) == 1:
        return active[0]["uid"]
    return _one_or_many(_most_recent(work, active) or _most_recent(work, running))
