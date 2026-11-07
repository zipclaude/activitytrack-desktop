# ActivityTrack Desktop

The tray application of [ActivityTrack](https://gitlab.com/infraconsulting/activitytrack)
for the PC: the running activities and the to-dos a click away, so that
a short activity goes in from the keyboard instead of the phone.

It works with [ActivityTrack Web](https://gitlab.com/infraconsulting/activitytrack-web),
which is a prerequisite: the desktop is paired like a phone and syncs both
ways; without a network it keeps working and syncs when the network is
back. Reports, master data and the management systems stay on the phone
and the web.

Status: under development, phase 4 of [docs/DESIGN.md](docs/DESIGN.md) (reminders). Linux first: KDE Plasma
and XFCE, on Wayland and X11.

## Install

From the [releases](https://gitlab.com/infraconsulting/activitytrack-desktop/-/releases):

- **Debian 13 / 14, Ubuntu 24.04 / 26.04**: `sudo apt install ./python3-activitytrack_<version>-1-<distro>_all.deb ./activitytrack-desktop_<version>-1-<distro>_all.deb`
  (the library from its own release),
  then start *ActivityTrack* from the menu.
- **Other distributions**: install Python 3.11 or newer, PyQt6, cryptography and keyring
  (and, for the global keyboard shortcuts, python-xlib on X11 and jeepney on Wayland; optional) from the distribution, unpack `activitytrack-desktop-<version>.tar.gz` and run
  `python3 -m activitytrack_desktop` in its folder.

Then, on the web, open **Dispositivi** → **Associa un dispositivo**, copy the link and paste it in
the window that opens at the first start.

Global keyboard shortcuts (Settings → Generale → Scorciatoie globali): **Ctrl+Alt+A** new
activity, **Ctrl+Alt+P** pause or resume, **Ctrl+Alt+S** stop. They use RegisterHotKey on Windows,
python-xlib on X11 (the `.deb` depends on `python3-xlib`; from the tarball install it from the
distribution) and the desktop portal's GlobalShortcuts through jeepney on Wayland (KDE Plasma 6, GNOME 48+, which
ask to confirm the keys). Anywhere, a desktop shortcut can run `activitytrack-desktop --start`,
`--pause` or `--stop`, which go to the running instance (started when there is none).

The desktop needs a notification area: native on KDE Plasma; on XFCE the panel's
"Status Tray" (or "Notification Area") plugin.

## Development

The rules, the local copy and the sync are in the library
[python3-activitytrack](https://gitlab.com/infraconsulting/python3-activitytrack), shared with the
command line and the text interface (one application, one data folder, one pairing).

```sh
apt install python3-pyqt6 python3-cryptography python3-keyring flake8
git clone https://gitlab.com/infraconsulting/python3-activitytrack ../python3-activitytrack
export PYTHONPATH=$PWD/../python3-activitytrack
python3 -m activitytrack_desktop --dev     # --dev: http:// servers allowed (a local ActivityTrack Web)
QT_QPA_PLATFORM=offscreen python3 -m unittest discover -s tests -t .
flake8 activitytrack_desktop tests
```

## License

GPL-3.0-or-later, as the app and the web.
