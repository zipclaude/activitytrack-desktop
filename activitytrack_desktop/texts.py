# SPDX-License-Identifier: GPL-3.0-or-later
"""The words of the interface for the activities: field labels, states, errors, times."""

from datetime import datetime

from .i18n import _
from .work import ACTIVE, CLOSED, PAUSE, SUSPENDED, TO_COMPLETE, TRAVEL, WORK

# the app's names of the fields; the policy may rename them
FIELDS = {
    "company": _("Azienda"), "client": _("Cliente"), "role": _("Ruolo"), "quickPick": _("Scelta rapida"),
    "description": _("Descrizione"), "locality": _("Località"), "notes": _("Note"), "tags": _("Tag"),
    "times": _("Tempi"),
}

MODES = {WORK: _("In lavoro"), PAUSE: _("In pausa"), TRAVEL: _("In viaggio")}
KINDS = {WORK: _("Lavoro"), PAUSE: _("Pausa"), TRAVEL: _("Viaggio")}
STATES = {SUSPENDED: _("Sospesa"), TO_COMPLETE: _("Da completare"), CLOSED: _("Chiusa")}

ERRORS = {
    "client_required": _("Serve il cliente (o un viaggio)."),
    "client_company_mismatch": _("Il cliente è di un'altra azienda."),
    "master_locked": _("La policy non permette di creare anagrafiche: scegli tra quelle esistenti."),
    "future_time": _("L'orario è nel futuro."),
    "invalid_range": _("La fine è prima dell'inizio."),
    "too_short": _("L'attività è troppo breve."),
    "before_segment": _("L'orario è prima dell'ultimo cambio registrato."),
    "details_missing": _("Manca la descrizione."),
    "todos_only": _("La policy permette di avviare attività solo dai Da fare."),
    "tag_not_allowed": _("La policy permette solo i tag delle anagrafiche: «%s» non c'è."),
    "times_locked": _("La policy non permette di modificare i tempi."),
    "illegal": _("Comando non possibile in questo stato."),
    "feature": _("Funzione disattivata dalla policy."),
    "not_found": _("L'attività non c'è più (eliminata su un altro dispositivo?)."),
}


def field_label(policy, name):
    return policy.field(name).label or FIELDS[name]


def error_text(e):
    if e.code == "required":
        return _("Campo obbligatorio: %s.") % FIELDS.get(e.detail, e.detail)
    text = ERRORS.get(e.code, e.code)
    return text % e.detail if "%s" in text else text


def state_label(entry):
    if entry.get("status") == ACTIVE:
        return MODES.get(entry.get("mode"), "")
    return STATES.get(entry.get("status"), "")


def hm(ms):
    """Hours and minutes, as the app shows durations: 1:05."""
    minutes = max(0, ms) // 60_000
    return f"{minutes // 60}:{minutes % 60:02d}"


def clock(ms):
    """The local time of day of an instant, with the date when not today."""
    t = datetime.fromtimestamp(ms / 1000)
    if t.date() == datetime.now().date():
        return t.strftime("%H:%M")
    return t.strftime("%d/%m %H:%M")
