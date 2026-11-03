# SPDX-License-Identifier: GPL-3.0-or-later
"""
The desktop portal's GlobalShortcuts on the session bus, for the
shortcuts' test: it answers each request as a desktop whose user accepts
the preferred keys, presses "pause" after each binding, and writes what
it got (one JSON line per call) to the file given.
"""

import json
import sys

from PyQt6.QtCore import QCoreApplication, QTimer

from activitytrack_desktop import dbuswire as w

PATH = "/org/freedesktop/portal/desktop"
SHORTCUTS = "org.freedesktop.portal.GlobalShortcuts"


def main():
    app = QCoreApplication(sys.argv)
    bus = w.Bus()
    log = sys.argv[1]
    sessions = []

    def write(**what):
        with open(log, "a", encoding="utf-8") as f:
            f.write(json.dumps(what) + "\n")

    def request(m, options):
        """The Request's path, and its Response a little later."""
        path = f"{PATH}/request/{m.sender.lstrip(':').replace('.', '_')}/{options['handle_token']}"
        return path, lambda results: QTimer.singleShot(50, lambda: bus.emit(
            path, "org.freedesktop.portal.Request", "Response", "ua{sv}", [0, results], destination=m.sender))

    def get(m):
        if m.body != [SHORTCUTS, "version"]:
            raise w.DBusError("org.freedesktop.DBus.Error.InvalidArgs", "no such property")
        return "v", [w.Variant("u", 1)]

    def register(m):
        write(call="Register", app_id=m.body[0])
        return "", []

    def create(m):
        options = m.body[0]
        session = f"{PATH}/session/{m.sender.lstrip(':').replace('.', '_')}/{options['session_handle_token']}"
        sessions.append(session)
        write(call="CreateSession")
        path, respond = request(m, options)
        respond({"session_handle": w.Variant("s", session)})
        return "o", [path]

    def bind(m):
        session, shortcuts, _parent, options = m.body
        write(call="BindShortcuts", session=session, shortcuts={k: v for k, v in shortcuts})
        path, respond = request(m, options)
        respond({"shortcuts": w.Variant("a(sa{sv})", [
            (k, {"trigger_description": w.Variant("s", v.get("preferred_trigger", ""))}) for k, v in shortcuts])})
        QTimer.singleShot(200, lambda: bus.emit(PATH, SHORTCUTS, "Activated", "osta{sv}",
                                                [session, "pause", 1, {}],
                                                destination=m.sender))
        return "o", [path]

    def close(m):
        write(call="Close", session=m.path)
        return "", []

    bus.on_method("org.freedesktop.DBus.Properties", "Get", get)
    bus.on_method("org.freedesktop.host.portal.Registry", "Register", register)
    bus.on_method(SHORTCUTS, "CreateSession", create)
    bus.on_method(SHORTCUTS, "BindShortcuts", bind)
    bus.on_method("org.freedesktop.portal.Session", "Close", close)
    if not bus.request_name("org.freedesktop.portal.Desktop"):
        sys.exit("service taken")
    print("ready", flush=True)
    app.exec()


if __name__ == "__main__":
    main()
