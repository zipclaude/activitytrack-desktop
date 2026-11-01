# ActivityTrack Desktop

The tray application of [ActivityTrack](https://github.com/zipclaude/activitytrack)
for the PC: the running activities and the to-dos a click away, so that
a short activity goes in from the keyboard instead of the phone.

It works with [ActivityTrack Web](https://github.com/zipclaude/activitytrack-web),
which is a prerequisite: the desktop is paired like a phone and syncs both
ways; without a network it keeps working and syncs when the network is
back. Reports, master data and the management systems stay on the phone
and the web.

Status: under development, phase 4 of [docs/DESIGN.md](docs/DESIGN.md) (reminders). Linux first: KDE Plasma
and XFCE, on Wayland and X11.

## Install

From the [releases](https://github.com/zipclaude/activitytrack-desktop/releases):

- **Debian 13 / 14, Ubuntu 24.04 / 26.04**: `sudo apt install ./activitytrack-desktop_<version>-<distro>_all.deb`,
  then start *ActivityTrack* from the menu.
- **Other distributions**: install Python 3.11 or newer, PyQt6, cryptography and keyring
  from the distribution, unpack `activitytrack-desktop-<version>.tar.gz` and run
  `python3 -m activitytrack_desktop` in its folder.

Then, on the web, open **Dispositivi** → **Associa un dispositivo**, copy the link and paste it in
the window that opens at the first start.

The desktop needs a notification area: native on KDE Plasma; on XFCE the panel's
"Status Tray" (or "Notification Area") plugin.

## Development

```sh
apt install python3-pyqt6 python3-cryptography python3-keyring flake8
python3 -m activitytrack_desktop --dev     # --dev: http:// servers allowed (a local ActivityTrack Web)
QT_QPA_PLATFORM=offscreen python3 -m unittest discover -s tests -t .
flake8 activitytrack_desktop tests
```

## License

GPL-3.0-or-later, as the app and the web.
