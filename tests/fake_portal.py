# SPDX-License-Identifier: GPL-3.0-or-later
"""
The desktop portal's GlobalShortcuts on the session bus (jeepney), for
the shortcuts' test: it answers each request as a desktop whose user
accepts the preferred keys, presses "pause" after each binding, and
writes what it got (one JSON line per call) to the file given.
"""

import json
import sys

from jeepney import DBusAddress, HeaderFields, MessageType, message_bus, new_error, new_method_return, new_signal
from jeepney.io.blocking import open_dbus_connection

PATH = "/org/freedesktop/portal/desktop"
SHORTCUTS = "org.freedesktop.portal.GlobalShortcuts"


def plain(value):
    """A variant's value ((signature, value) in jeepney)."""
    return value[1] if isinstance(value, tuple) else value


def main():
    log = sys.argv[1]
    conn = open_dbus_connection("SESSION")

    def write(**what):
        with open(log, "a", encoding="utf-8") as f:
            f.write(json.dumps(what) + "\n")

    def signal(to, path, interface, member, signature, body):
        msg = new_signal(DBusAddress(path, interface=interface), member, signature, body)
        msg.header.fields[HeaderFields.destination] = to
        conn.send(msg)

    def request(msg, options):
        sender = msg.header.fields[HeaderFields.sender]
        return f"{PATH}/request/{sender.lstrip(':').replace('.', '_')}/{plain(options['handle_token'])}"

    def respond(msg, path, results):
        signal(msg.header.fields[HeaderFields.sender], path, "org.freedesktop.portal.Request", "Response", "ua{sv}",
               (0, results))

    def handle(msg):
        """[(reply's signature, body)] and what to send after it."""
        f = msg.header.fields
        sender = f[HeaderFields.sender]
        call = (f.get(HeaderFields.interface), f.get(HeaderFields.member))
        if call == ("org.freedesktop.DBus.Properties", "Get"):
            if tuple(msg.body) != (SHORTCUTS, "version"):
                raise LookupError("org.freedesktop.DBus.Error.InvalidArgs")
            return "v", (("u", 1),), []
        if call == ("org.freedesktop.host.portal.Registry", "Register"):
            write(call="Register", app_id=msg.body[0])
            return "", (), []
        if call == (SHORTCUTS, "CreateSession"):
            options = msg.body[0]
            session = f"{PATH}/session/{sender.lstrip(':').replace('.', '_')}/{plain(options['session_handle_token'])}"
            write(call="CreateSession")
            path = request(msg, options)
            return "o", (path,), [lambda: respond(msg, path, {"session_handle": ("s", session)})]
        if call == (SHORTCUTS, "BindShortcuts"):
            session, shortcuts, _parent, options = msg.body
            got = {k: {n: plain(v) for n, v in props.items()} for k, props in shortcuts}
            write(call="BindShortcuts", session=session, shortcuts=got)
            path = request(msg, options)
            results = {"shortcuts": ("a(sa{sv})", [(k, {"trigger_description": ("s", v["preferred_trigger"])})
                                                   for k, v in got.items()])}
            return "o", (path,), [lambda: respond(msg, path, results),
                                  lambda: signal(sender, PATH, SHORTCUTS, "Activated", "osta{sv}",
                                                 (session, "pause", 1, {}))]
        if call == ("org.freedesktop.portal.Session", "Close"):
            write(call="Close", session=f[HeaderFields.path])
            return "", (), []
        raise LookupError("org.freedesktop.DBus.Error.UnknownMethod")

    if conn.send_and_get_reply(message_bus.RequestName("org.freedesktop.portal.Desktop", 4)).body[0] != 1:
        sys.exit("service taken")
    print("ready", flush=True)
    while True:
        msg = conn.receive()
        if msg.header.message_type != MessageType.method_call:
            continue
        try:
            signature, body, after = handle(msg)
            conn.send(new_method_return(msg, signature or None, body))
        except LookupError as e:
            conn.send(new_error(msg, str(e)))
            continue
        for f in after:
            f()


if __name__ == "__main__":
    main()
