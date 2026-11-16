# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Flavio Visentin <flavio-activitytrack@infraconsulting.it>
"""The entry point PyInstaller bundles for Windows (docs/DESIGN.md §8)."""
import sys

from activitytrack_desktop.main import main

sys.exit(main())
