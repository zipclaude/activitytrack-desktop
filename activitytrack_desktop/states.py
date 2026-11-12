# SPDX-License-Identifier: GPL-3.0-or-later
"""
The icon and the colour of every displayed state of an activity, in one table (docs/ACTIVITY-MODEL.md
§2.2); the words are the library's (texts.display_label). Home cards, rows, the detail dialog and the
tray menu draw a state through it.
"""

from activitytrack import model
from activitytrack.model import ABSENCE, PAUSE, TODO, TRAVEL, WORK

from . import theme

# state: (icon of icons.PATHS, colour)
LOOK = {
    model.DELETED: ("bin", theme.GREY),
    ABSENCE: ("dot", theme.PINK),
    model.LATE: ("exclaim", theme.BROWN),
    model.PLANNED: ("clock", theme.GREY),
    TODO: ("checkbox", theme.WHITE),
    WORK: ("play", theme.GREEN),
    TRAVEL: ("travel", theme.BLUE),
    PAUSE: ("pause", theme.YELLOW),
    model.SUSPENDED: ("suspend", theme.ORANGE),
    model.DONE: ("done", theme.GREENISH),
    model.INCOMPLETE: ("stop", theme.REDDISH),
}


def icon(state):
    return LOOK.get(state, LOOK[TODO])[0]


def colour(state):
    return LOOK.get(state, LOOK[TODO])[1]
