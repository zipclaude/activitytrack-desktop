# SPDX-License-Identifier: GPL-3.0-or-later
"""ActivityTrack Desktop: the tray application of ActivityTrack (docs/DESIGN.md)."""

# aligned with the app and the web (D6)
__version__ = "1.0.0-beta-1"
# the same version as PEP 440 spells it, for the Python package metadata ("1.0.0-alfa-1" -> "1.0.0a1")
__pep440__ = __version__.replace("-alfa-", "a").replace("-beta-", "b")
