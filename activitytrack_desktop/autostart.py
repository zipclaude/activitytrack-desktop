# SPDX-License-Identifier: GPL-3.0-or-later
"""
Starting with the desktop session (docs/DESIGN.md §3, §3.1): an XDG
autostart entry on Linux, the Run key of the current user on Windows (the
same value the installer's task writes). The application starts hidden,
in the tray.
"""

import os
import shlex
import shutil
import sys
from pathlib import Path

NAME = "ActivityTrack"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def _command():
    """How this copy is started again: the installed program, else Python on the package."""
    if getattr(sys, "frozen", False):
        return [sys.executable]
    installed = shutil.which("activitytrack-desktop")
    if installed and Path(sys.argv[0]).name == "activitytrack-desktop":
        return [installed]
    return [sys.executable, "-m", "activitytrack_desktop"]


def _desktop_file():
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "autostart" / "activitytrack-desktop.desktop"


def enabled():
    if sys.platform == "win32":
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
                winreg.QueryValueEx(k, NAME)
            return True
        except OSError:
            return False
    return _desktop_file().exists()


def set_enabled(on):
    cmd = _command() + ["--hidden"]
    if sys.platform == "win32":
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
            if on:
                winreg.SetValueEx(k, NAME, 0, winreg.REG_SZ, " ".join(f'"{c}"' if " " in c else c for c in cmd))
            else:
                try:
                    winreg.DeleteValue(k, NAME)
                except OSError:
                    pass
        return
    f = _desktop_file()
    if not on:
        f.unlink(missing_ok=True)
        return
    f.parent.mkdir(parents=True, exist_ok=True)
    package_dir = Path(__file__).resolve().parent.parent
    lines = [
        "[Desktop Entry]", "Type=Application", f"Name={NAME}", f"Exec={shlex.join(cmd)}",
        "Icon=activitytrack-desktop", "Terminal=false", "X-GNOME-Autostart-enabled=true",
        "Comment=Running activities and to-dos of ActivityTrack, from the tray",
    ]
    if cmd[1:2] == ["-m"]:
        # from the tarball: Python finds the package in its folder
        lines.append(f"Path={package_dir}")
    f.write_text("\n".join(lines) + "\n")
