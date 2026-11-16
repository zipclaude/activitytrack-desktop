# SPDX-License-Identifier: GPL-3.0-or-later
import ast
import importlib.util
import json
import tempfile
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


PACKAGE = Path(__file__).resolve().parent.parent / "activitytrack_desktop"
PACKAGING = Path(__file__).resolve().parent.parent / "packaging"
# the texts that are the same word in the language as in Italian (the catalogs' keys), and in English
SAME_AS_ITALIAN = {
    "en": {" min", "Home", "ISO (2026-12-31)", "Server", "Stop"},
    "de": {"ISO (2026-12-31)", "Server"},
    "es": {" min", "ISO (2026-12-31)", "Pausa", "Periodo", "Tipo", "dom", "europeo (31/12/2026)", "lun", "mar"},
}
# the literals of the sources that are not interface texts: the name of a key of the keyboard
NOT_TEXTS = {("hotkeys.py", "Home")}
SAME_AS_ENGLISH = {"de": {"ISO (2026-12-31)", "Organizzazione", "Pausa", "Server"},
                   "es": {" min", "Generale", "ISO (2026-12-31)"}}


def _catalogs(folder=PACKAGE / "locale"):
    return {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in sorted(Path(folder).glob("*.json"))}


class CatalogsTest(unittest.TestCase):
    """The desktop's catalogs are complete and say what the app, the web and the library say (desktop#37)."""

    def test_the_languages(self):
        # the app, the web, the cli and the tui have Italian (the language of the sources), English, German, Spanish
        self.assertEqual(i18n.LANGUAGES, ("it", "en", "de", "es"))
        self.assertEqual(sorted(_catalogs()), sorted(set(i18n.LANGUAGES) - {"it"}))
        siblings = [PACKAGE.parent.parent / "activitytrack-cli" / "activitytrack_cli" / "locale",
                    PACKAGE.parent.parent / "activitytrack-tui" / "activitytrack_tui" / "locale"]
        for folder in siblings:
            if folder.is_dir():
                self.assertEqual(sorted(_catalogs(folder)), sorted(_catalogs()), str(folder))

    def test_the_catalogs_have_the_same_texts(self):
        catalogs = _catalogs()
        for lang in ("de", "es"):
            self.assertEqual(sorted(catalogs[lang]), sorted(catalogs["en"]), lang)

    @unittest.skipUnless(SCRIPT.exists(), "not in a source tree")
    def test_the_texts_of_the_sources_are_the_catalogs_keys(self):
        # none missing, none left over from a text that changed
        self.assertEqual(sorted(_catalogs()["en"]), sorted(_strings_module().strings()))

    def test_nothing_is_left_in_italian_or_english(self):
        catalogs = _catalogs()
        for lang, catalog in catalogs.items():
            same = sorted(k for k, v in catalog.items() if v == k.split("|")[-1])
            self.assertEqual(same, sorted(SAME_AS_ITALIAN[lang]), f"{lang}: left in Italian")
            for k, v in catalog.items():
                self.assertTrue(v.strip(), f"{lang}: {k!r} is empty")
        for lang in ("de", "es"):
            same = sorted(k for k, v in catalogs[lang].items() if v == catalogs["en"][k])
            self.assertEqual(same, sorted(SAME_AS_ENGLISH[lang]), f"{lang}: left in English")

    @unittest.skipUnless(SCRIPT.exists(), "not in a source tree")
    def test_the_placeholders_are_those_of_the_text(self):
        strings = _strings_module()
        for lang, catalog in _catalogs().items():
            for k, v in catalog.items():
                self.assertEqual(strings.placeholders(v), strings.placeholders(k.split("|")[-1]), f"{lang}: {k!r}")

    @unittest.skipUnless(SCRIPT.exists(), "not in a source tree")
    def test_the_check_finds_what_is_wrong(self):
        strings = _strings_module()
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "locale").mkdir()
            (root / "m.py").write_text('_("uno %s")\n_("due")\npgettext("c", "tre")\n_("quattro")\n', encoding="utf-8")
            (root / "locale" / "xx.json").write_text(json.dumps({
                "uno %s": "one %d", "due": "", "c|tre": "three", "vecchio": "old"}), encoding="utf-8")
            old, strings.PACKAGE = strings.PACKAGE, root
            try:
                errors = strings.check()
            finally:
                strings.PACKAGE = old
        self.assertEqual(sorted(e.split(": ", 1)[1] for e in errors), sorted([
            "placeholders of 'uno %s'", "empty 'due'", "missing 'quattro'", "stale 'vecchio'"]))

    @unittest.skipUnless(SCRIPT.exists(), "not in a source tree")
    def test_no_text_bypasses_the_catalogs(self):
        # an Italian text of the catalogs written as a plain literal would stay Italian in every language
        keys = {k.split("|")[-1] for k in _catalogs()["en"]}
        for path in sorted(PACKAGE.glob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            wrapped = {id(n) for call in ast.walk(tree) if isinstance(call, ast.Call)
                       and getattr(call.func, "id", None) in ("_", "pgettext") for n in ast.walk(call)}
            for node in ast.walk(tree):
                if (isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value in keys
                        and id(node) not in wrapped and (path.name, node.value) not in NOT_TEXTS):
                    self.fail(f"{path.name}:{node.lineno}: {node.value!r} is not passed to _()")

    def test_the_desktop_says_what_the_library_says(self):
        # the desktop's catalog is loaded after the library's and wins: a text both have is worded alike
        import activitytrack
        lib = _catalogs(Path(activitytrack.__file__).with_name("locale"))
        for lang, catalog in _catalogs().items():
            different = sorted(k for k, v in catalog.items() if k in lib[lang] and lib[lang][k] != v)
            self.assertEqual(different, [], lang)

    def test_the_lists_of_to_dos_and_travel_are_named_as_the_app_does(self):
        catalogs = _catalogs()
        self.assertEqual([catalogs[lang]["Da fare"] for lang in ("en", "de", "es")],
                         ["To-dos", "Aufgaben", "Pendientes"])
        self.assertEqual(catalogs["de"]["Nuovo viaggio"], "Neue Reise")

    def test_a_prompt_reads_the_same_in_the_settings_as_in_the_reminder(self):
        # the settings quote the reminders' questions («Ancora in pausa?»): the same words in every language
        for lang, catalog in _catalogs().items():
            self.assertIn(catalog["Ancora in pausa?"], catalog["«Ancora in pausa?»"], lang)
            self.assertIn(catalog["Ancora in pausa?"], catalog["«Ancora in pausa?» ogni (min)"], lang)
            stem = catalog["Ancora su %s?"].split("%s")[0]
            for key in ("«Ancora su …?» mentre un'attività è in corso", "«Ancora su …?» ogni (min)"):
                self.assertIn(stem, catalog[key], lang)

    def test_the_new_texts_of_1_0_are_there(self):
        # the plan's grid (desktop#35) and the language (desktop#36)
        for lang, catalog in _catalogs().items():
            for text in ("Lingua", "Lingua del sistema", "La lingua cambia al prossimo avvio di ActivityTrack.",
                         "Clicca per il solo orario di inizio, oppure trascina (o clicca due volte) per inizio e fine"):
                self.assertIn(text, catalog, lang)

    def test_the_launcher_and_the_store_page_speak_every_language(self):
        entry = (PACKAGING / "activitytrack-desktop.desktop").read_text(encoding="utf-8")
        for key in ("GenericName", "Comment", "Keywords"):
            for lang in ("it", "de", "es"):
                self.assertRegex(entry, rf"(?m)^{key}\[{lang}\]=.+$", f"{key}[{lang}]")
        meta = (PACKAGING / "it.infraconsulting.activitytrack_desktop.metainfo.xml").read_text(encoding="utf-8")
        for lang in ("it", "de", "es"):
            self.assertIn(f'<summary xml:lang="{lang}">', meta)
