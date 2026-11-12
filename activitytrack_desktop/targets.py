# SPDX-License-Identifier: GPL-3.0-or-later
"""
Which activity a keyboard command acts on (docs/DESIGN.md §6.5), without
Qt: the window's shortcuts and the global ones share it. Every function
returns an entry uid, None when there is nothing to act on, or a list of
uids (the most recent first) when the choice is the user's: the caller
shows them in a small list.

- pause: the activity at work or travelling;
- resume: the one in pause, else the latest suspended;
- stop: the one in the Home's big card (focused_uid), else the active
  one, else the suspended one.
"""

from activitytrack.work import PAUSE, WORK


def _active(work):
    """Running with an open segment (work, travel or pause), as opposed to suspended."""
    return [e for e in work.running() if work.open_segment(e["uid"]) is not None]


def _mode(work, e):
    return work.open_segment(e["uid"])["kind"]


def _recent(work, entries):
    """The uids, the latest moved first (the Home's order of the cards)."""
    return [e["uid"] for e in sorted(entries, key=lambda e: -work.last_boundary(e["uid"]))]


def _one(uids):
    if not uids:
        return None
    return uids[0] if len(uids) == 1 else uids


def running(work):
    """The activities running or suspended, the latest moved first: the Home's cards, the first one big."""
    return _recent(work, work.running())


def pause_target(work):
    """The activity to pause: the one at work or travelling; several (concurrent activities) are a choice."""
    return _one(_recent(work, [e for e in _active(work) if _mode(work, e) != PAUSE]))


def resume_target(work):
    """The activity to resume: the one in pause (several are a choice), else the latest suspended."""
    paused = _recent(work, [e for e in _active(work) if _mode(work, e) == PAUSE])
    if paused:
        return _one(paused)
    suspended = _recent(work, [e for e in work.running() if work.open_segment(e["uid"]) is None])
    return suspended[0] if suspended else None


def pause_or_resume(work):
    """
    (command, target) of the pause/resume key: PAUSE of pause_target() when
    something is at work, else WORK of resume_target(); (None, None) when
    nothing runs.
    """
    target = pause_target(work)
    if target is not None:
        return PAUSE, target
    target = resume_target(work)
    return (WORK, target) if target is not None else (None, None)


def stop_target(work, focused_uid=None):
    """
    The activity to stop: [focused_uid] (the Home's big card) while it
    runs; else the active one, else the suspended one; several are a choice.
    """
    live = work.running()
    if focused_uid is not None and any(e["uid"] == focused_uid for e in live):
        return focused_uid
    active = [e for e in live if work.open_segment(e["uid"]) is not None]
    return _one(_recent(work, active or live))
