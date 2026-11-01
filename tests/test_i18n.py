# SPDX-License-Identifier: GPL-3.0-or-later
import importlib.util
import unittest
from pathlib import Path

from activitytrack import i18n
from activitytrack.policy import Policy


SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "strings.py"


def _strings_module():
    path = SCRIPT
    spec = importlib.util.spec_from_file_location("strings", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class I18nTest(unittest.TestCase):
    def setUp(self):
        # the desktop's texts, with the library's (from the package: the tests also run on the installed one)
        import activitytrack_desktop
        i18n.add_catalogs(Path(activitytrack_desktop.__file__).with_name("locale"))

    def tearDown(self):
        i18n.set_language("it")

    # a check of the sources: the packages' job runs the tests on the installed code, without them
    @unittest.skipUnless(SCRIPT.exists(), "not in a source tree")
    def test_every_text_is_translated(self):
        self.assertEqual(_strings_module().check(), [])

    def test_languages(self):
        self.assertEqual(i18n.set_language("de_AT"), "de")
        self.assertEqual(i18n._("Sincronizza ora"), "Jetzt synchronisieren")
        self.assertEqual(i18n._("Posticipa di %d min") % 15, "Um 15 Min. verschieben")
        # another language: English
        self.assertEqual(i18n.set_language("fr_FR"), "en")
        self.assertEqual(i18n._("Esci"), "Quit")
        # an unknown text stays as it is
        self.assertEqual(i18n._("— nuovo —"), "— nuovo —")
        self.assertEqual(i18n.set_language("it"), "it")
        self.assertEqual(i18n._("Esci"), "Esci")

    def test_the_policy_forces_it(self):
        p = Policy({"format": "activitytrack-policy", "schema": 1, "ui": {"language": "es"}})
        self.assertEqual(p.language, "es")
        self.assertIsNone(Policy({"format": "activitytrack-policy", "schema": 1, "ui": {"language": "fr"}}).language)
