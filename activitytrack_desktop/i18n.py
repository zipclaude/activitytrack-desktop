# SPDX-License-Identifier: GPL-3.0-or-later
"""
The interface is written in Italian, as the app's and the web's; `_`
gives the text in the language chosen at start (locale/<language>.json:
Italian text → translation). The language is the policy's ui.language,
else the system's; another language than it, en, de, es gets English.
Modules keep texts in constants, so the language is set before the
interface's modules are imported (main.py).
"""

import json
from pathlib import Path

LANGUAGES = ("it", "en", "de", "es")
_catalog = {}
_language = "it"


def set_language(code):
    """[code]: "it", "en", "de", "es", or a locale ("de_AT"); returns the language used."""
    global _catalog, _language
    code = (code or "it")[:2].lower()
    if code not in LANGUAGES:
        code = "en"
    _language = code
    _catalog = {}
    if code != "it":
        path = Path(__file__).with_name("locale") / f"{code}.json"
        try:
            _catalog = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            _catalog = {}
    return code


def language():
    return _language


def _(text):
    return _catalog.get(text) or text
