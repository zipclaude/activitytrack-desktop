# SPDX-License-Identifier: GPL-3.0-or-later
"""
The interface's language, one of the user's preferences (Settings → Generale): "system" (None) or one
of the languages with a catalog. It is kept in the local copy's state, as the date and time formats, and
read by main() before any module that translates its texts is imported: the library's texts and the
Home build their dictionaries when imported, so the language cannot change under a running window
(the change is for the next start). The policy's ui.language, when there is one, wins over the choice.
Imports nothing but the i18n module: it must stay light for that reason.
"""

from activitytrack.i18n import LANGUAGES

KEY = "language"
# each language in its own name, as the web's: never translated
NAMES = {"it": "Italiano", "en": "English", "de": "Deutsch", "es": "Español"}


def chosen(store):
    """The language the user chose, None for the system's."""
    value = store.get_state(KEY)
    return value if value in LANGUAGES else None


def save(store, code):
    """[code]: a language, or None for the system's."""
    store.set_state(KEY, code if code in LANGUAGES else None)
