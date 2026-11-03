# SPDX-License-Identifier: GPL-3.0-or-later
"""Which activity the keys act on (targets.py): no Qt."""

import tempfile
import unittest

from activitytrack.store import Store
from activitytrack.work import PAUSE, SUSPEND, WORK, StartRequest, Work

from activitytrack_desktop import targets

MIN = 60_000
NOW = 1_800_000_000_000


class TargetsTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.store = Store(f"{self.dir.name}/t.sqlite3")
        self.work = Work(self.store, clock=lambda: NOW, zone="Europe/Rome")
        self.store.pulled({"type": "client", "uid": "c1", "rev": 1, "fields": {"name": "Biblioteca"}})

    def tearDown(self):
        self.store.close()
        self.dir.cleanup()

    def start(self, minutes_ago):
        """An activity at work since [minutes_ago], the others left as they are (concurrent activities)."""
        return self.work.start(StartRequest(client="c1", activity="x", start_ms=NOW - minutes_ago * MIN))

    def at(self, uid, cmd, minutes_ago):
        self.work.command(uid, cmd, at=NOW - minutes_ago * MIN)

    def test_nothing_running(self):
        w = self.work
        self.assertIsNone(targets.pause_target(w))
        self.assertIsNone(targets.resume_target(w))
        self.assertIsNone(targets.stop_target(w))
        self.assertIsNone(targets.stop_target(w, "gone"))
        self.assertEqual(targets.pause_or_resume(w), (None, None))
        self.assertEqual(targets.running(w), [])

    def test_one_at_work(self):
        a = self.start(30)
        w = self.work
        self.assertEqual(targets.pause_target(w), a)
        self.assertIsNone(targets.resume_target(w))
        self.assertEqual(targets.pause_or_resume(w), (PAUSE, a))
        self.assertEqual(targets.stop_target(w), a)

    def test_travelling_is_paused_too(self):
        a = self.start(30)
        self.at(a, "TRAVEL", 10)
        self.assertEqual(targets.pause_target(self.work), a)

    def test_paused_resumes(self):
        a = self.start(30)
        self.at(a, PAUSE, 10)
        w = self.work
        self.assertIsNone(targets.pause_target(w))
        self.assertEqual(targets.resume_target(w), a)
        self.assertEqual(targets.pause_or_resume(w), (WORK, a))
        self.assertEqual(targets.stop_target(w), a)

    def test_the_paused_one_before_the_suspended(self):
        a = self.start(60)
        b = self.start(40)
        self.at(a, SUSPEND, 30)
        self.at(b, PAUSE, 20)
        self.assertEqual(targets.resume_target(self.work), b)

    def test_else_the_latest_suspended(self):
        a = self.start(60)
        b = self.start(50)
        self.at(b, SUSPEND, 40)
        self.at(a, SUSPEND, 20)
        w = self.work
        self.assertEqual(targets.resume_target(w), a)
        self.assertEqual(targets.pause_or_resume(w), (WORK, a))
        # two suspended to stop: the user chooses, the latest first
        self.assertEqual(targets.stop_target(w), [a, b])

    def test_two_at_work_are_a_choice(self):
        a = self.start(60)
        b = self.start(20)
        w = self.work
        self.assertEqual(targets.pause_target(w), [b, a])
        self.assertEqual(targets.pause_or_resume(w), (PAUSE, [b, a]))
        self.assertEqual(targets.stop_target(w), [b, a])
        self.assertEqual(targets.running(w), [b, a])

    def test_two_paused_are_a_choice(self):
        a = self.start(60)
        b = self.start(50)
        self.at(a, PAUSE, 30)
        self.at(b, PAUSE, 10)
        self.assertEqual(targets.resume_target(self.work), [b, a])

    def test_one_at_work_and_one_paused(self):
        a = self.start(60)
        b = self.start(50)
        self.at(a, PAUSE, 30)
        w = self.work
        self.assertEqual(targets.pause_or_resume(w), (PAUSE, b))
        # stop: both active, a choice without the big card; the pause moved later than b's start
        self.assertEqual(targets.stop_target(w), [a, b])
        self.assertEqual(targets.stop_target(w, a), a)

    def test_stop_the_big_card_else_the_active_one(self):
        a = self.start(60)
        b = self.start(50)
        self.at(a, SUSPEND, 40)
        w = self.work
        self.assertEqual(targets.stop_target(w), b)
        self.assertEqual(targets.stop_target(w, a), a)
        # a card no longer running is not a target
        self.assertEqual(targets.stop_target(w, "gone"), b)
        self.work.command(b, "STOP")
        self.assertEqual(targets.stop_target(w, b), a)
