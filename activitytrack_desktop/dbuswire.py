# SPDX-License-Identifier: GPL-3.0-or-later
"""
A small D-Bus client on the session bus, for the GlobalShortcuts portal:
PyQt's QtDBus cannot send an array of structures (the portal's
a(sa{sv})), and no other D-Bus library is a dependency. The messages are
read in the GUI thread (a socket notifier); only what the portal needs:
calls with their replies, signals, and for the tests a name and methods.
"""

import os
import select
import socket
import struct
import time

from PyQt6.QtCore import QObject, QSocketNotifier, pyqtSignal as Signal

BUS = "org.freedesktop.DBus"
BUS_PATH = "/org/freedesktop/DBus"
CALL, RETURN, ERROR, SIGNAL = 1, 2, 3, 4
NO_REPLY = 0x1

_FIELDS = {1: "path", 2: "interface", 3: "member", 4: "error", 5: "reply_serial", 6: "destination", 7: "sender",
           8: "signature"}
_FIELD_TYPES = {1: "o", 2: "s", 3: "s", 4: "s", 5: "u", 6: "s", 7: "s", 8: "g"}
_ALIGN = {"y": 1, "b": 4, "n": 2, "q": 2, "i": 4, "u": 4, "x": 8, "t": 8, "d": 8, "h": 4, "s": 4, "o": 4, "g": 1,
          "a": 4, "(": 8, "{": 8, "v": 1}
_FIXED = {"y": "B", "b": "I", "n": "h", "q": "H", "i": "i", "u": "I", "x": "q", "t": "Q", "d": "d", "h": "I"}


class DBusError(Exception):
    def __init__(self, name, text=""):
        super().__init__(f"{name}: {text}" if text else name)
        self.name = name


class Variant:
    """A value with its type, for a "v"; read variants come back as their plain value."""

    def __init__(self, signature, value):
        self.signature, self.value = signature, value

    def __repr__(self):
        return f"Variant({self.signature!r}, {self.value!r})"


def _end(sig, i):
    """The index after the complete type starting at sig[i]."""
    c = sig[i]
    if c == "a":
        return _end(sig, i + 1)
    if c in "({":
        i += 1
        while sig[i] not in ")}":
            i = _end(sig, i)
        return i + 1
    return i + 1


def split(sig):
    """The complete types of a signature: "sa{sv}u" → ["s", "a{sv}", "u"]."""
    out, i = [], 0
    while i < len(sig):
        j = _end(sig, i)
        out.append(sig[i:j])
        i = j
    return out


def _guess(value):
    """The type of a plain value in a variant."""
    if isinstance(value, bool):
        return "b"
    if isinstance(value, int):
        return "i"
    if isinstance(value, float):
        return "d"
    if isinstance(value, dict):
        return "a{sv}"
    if isinstance(value, (list, tuple)):
        return "as"
    return "s"


class _Writer:
    def __init__(self):
        self.buf = bytearray()

    def pad(self, n):
        self.buf += b"\0" * (-len(self.buf) % n)

    def write(self, sig, value):
        c = sig[0]
        if c in _FIXED:
            self.pad(_ALIGN[c])
            self.buf += struct.pack("<" + _FIXED[c], value if c == "d" else int(value))
        elif c in "so":
            data = str(value).encode()
            self.write("u", len(data))
            self.buf += data + b"\0"
        elif c == "g":
            data = str(value).encode()
            self.buf += bytes([len(data)]) + data + b"\0"
        elif c == "v":
            if not isinstance(value, Variant):
                value = Variant(_guess(value), value)
            self.write("g", value.signature)
            self.write(value.signature, value.value)
        elif c == "a":
            self.pad(4)
            at = len(self.buf)
            self.buf += b"\0\0\0\0"
            element = sig[1:]
            self.pad(_ALIGN[element[0]])
            start = len(self.buf)
            if element[0] == "{":
                key, val = split(element[1:-1])
                for k, v in value.items():
                    self.pad(8)
                    self.write(key, k)
                    self.write(val, v)
            else:
                for v in value:
                    self.write(element, v)
            struct.pack_into("<I", self.buf, at, len(self.buf) - start)
        elif c == "(":
            self.pad(8)
            for s, v in zip(split(sig[1:-1]), value):
                self.write(s, v)
        else:
            raise ValueError(f"type {c!r}")

    def write_all(self, sig, values):
        for s, v in zip(split(sig), values):
            self.write(s, v)


class _Reader:
    def __init__(self, data, endian="<", pos=0):
        self.data, self.endian, self.pos = data, endian, pos

    def align(self, n):
        self.pos += -self.pos % n

    def read(self, sig):
        c = sig[0]
        if c in _FIXED:
            self.align(_ALIGN[c])
            fmt = self.endian + _FIXED[c]
            (v,) = struct.unpack_from(fmt, self.data, self.pos)
            self.pos += struct.calcsize(fmt)
            return bool(v) if c == "b" else v
        if c in "so":
            n = self.read("u")
            v = bytes(self.data[self.pos:self.pos + n]).decode()
            self.pos += n + 1
            return v
        if c == "g":
            n = self.data[self.pos]
            v = bytes(self.data[self.pos + 1:self.pos + 1 + n]).decode()
            self.pos += n + 2
            return v
        if c == "v":
            return self.read(self.read("g"))
        if c == "a":
            n = self.read("u")
            element = sig[1:]
            self.align(_ALIGN[element[0]])
            end = self.pos + n
            if element[0] == "{":
                key, val = split(element[1:-1])
                out = {}
                while self.pos < end:
                    self.align(8)
                    k = self.read(key)
                    out[k] = self.read(val)
                return out
            items = []
            while self.pos < end:
                items.append(self.read(element))
            return items
        if c == "(":
            self.align(8)
            return tuple(self.read(s) for s in split(sig[1:-1]))
        raise ValueError(f"type {c!r}")


class Message:
    def __init__(self, type_, serial=0, flags=0, body=(), **fields):
        self.type, self.serial, self.flags, self.body = type_, serial, flags, list(body)
        for name in _FIELDS.values():
            setattr(self, name, fields.get(name))

    def encode(self):
        body = _Writer()
        if self.signature:
            body.write_all(self.signature, self.body)
        fields = [(code, Variant(_FIELD_TYPES[code], getattr(self, name)))
                  for code, name in _FIELDS.items() if getattr(self, name)]
        head = _Writer()
        head.buf += struct.pack("<BBBBII", ord("l"), self.type, self.flags, 1, len(body.buf), self.serial)
        head.write("a(yv)", fields)
        head.pad(8)
        return bytes(head.buf + body.buf)


def decode(buf):
    """(message, bytes used) for the first complete message in [buf], or (None, 0)."""
    if len(buf) < 16:
        return None, 0
    endian = "<" if buf[0:1] == b"l" else ">"
    body_len, serial, fields_len = struct.unpack_from(endian + "III", buf, 4)
    head_len = 16 + fields_len
    total = head_len + (-head_len % 8) + body_len
    if len(buf) < total:
        return None, 0
    r = _Reader(buf, endian, 12)
    fields = r.read("a(yv)")
    r.align(8)
    m = Message(buf[1], serial, buf[2])
    for code, value in fields:
        if code in _FIELDS:
            setattr(m, _FIELDS[code], value)
    if m.signature:
        m.body = [r.read(s) for s in split(m.signature)]
    return m, total


def _address(text):
    """A socket address from a D-Bus address ("unix:path=…" or "unix:abstract=…"; the first usable)."""
    for part in (text or "").split(";"):
        kind, _sep, rest = part.partition(":")
        if kind != "unix":
            continue
        keys = dict(kv.partition("=")[::2] for kv in rest.split(","))
        if keys.get("path"):
            return _unescape(keys["path"])
        if keys.get("abstract"):
            return "\0" + _unescape(keys["abstract"])
    raise OSError("no unix address in the D-Bus address")


def _unescape(value):
    out, i = bytearray(), 0
    while i < len(value):
        if value[i] == "%":
            out.append(int(value[i + 1:i + 3], 16))
            i += 3
        else:
            out += value[i].encode()
            i += 1
    return out.decode()


class Bus(QObject):
    """A connection to the session bus. Raises OSError or DBusError when it cannot be had."""

    closed = Signal()

    def __init__(self, address=None, parent=None):
        super().__init__(parent)
        address = address if address is not None else os.environ.get("DBUS_SESSION_BUS_ADDRESS", "")
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(5)
        try:
            self.sock.connect(_address(address))
            self._auth()
        except OSError:
            self.sock.close()
            raise
        self.sock.setblocking(False)
        self.buf = bytearray()
        self.serial = 0
        self.replies = {}      # serial -> callback(message)
        self.signals = []      # (interface, member, callback(message))
        self.methods = {}      # (interface, member) -> callback(message) -> (signature, body)
        self._waiting = {}
        self.notifier = QSocketNotifier(self.sock.fileno(), QSocketNotifier.Type.Read, self)
        self.notifier.activated.connect(self._readable)
        self.unique_name = self.call_sync(BUS, BUS_PATH, BUS, "Hello")[0]

    def _auth(self):
        self.sock.sendall(b"\0AUTH EXTERNAL " + str(os.getuid()).encode().hex().encode() + b"\r\n")
        line = b""
        while not line.endswith(b"\r\n"):
            got = self.sock.recv(256)
            if not got:
                raise OSError("the bus closed the connection")
            line += got
        if not line.startswith(b"OK "):
            raise OSError("the bus refused the authentication")
        self.sock.sendall(b"BEGIN\r\n")

    def close(self):
        if self.sock is not None:
            self.notifier.setEnabled(False)
            self.sock.close()
            self.sock = None

    def _send(self, m):
        if self.sock is None:
            raise OSError("closed")
        self.serial += 1
        m.serial = self.serial
        data = m.encode()
        self.sock.setblocking(True)
        try:
            self.sock.sendall(data)
        finally:
            self.sock.setblocking(False)
        return m.serial

    def call(self, destination, path, interface, member, signature="", body=(), reply=None):
        """A method call; [reply](message) with its return or error (message.type ERROR)."""
        m = Message(CALL, flags=0 if reply else NO_REPLY, body=body, path=path, interface=interface, member=member,
                    destination=destination, signature=signature)
        serial = self._send(m)
        if reply is not None:
            self.replies[serial] = reply
        return serial

    def call_sync(self, destination, path, interface, member, signature="", body=(), timeout=3.0):
        """The reply's body; DBusError on an error, TimeoutError when none comes."""
        serial = self.call(destination, path, interface, member, signature, body,
                           reply=lambda m: self._waiting.__setitem__(serial, m))
        end = time.monotonic() + timeout
        while serial not in self._waiting:
            left = end - time.monotonic()
            if left <= 0 or self.sock is None:
                self.replies.pop(serial, None)
                raise TimeoutError(member)
            select.select([self.sock], [], [], left)
            self._readable()
        m = self._waiting.pop(serial)
        if m.type == ERROR:
            raise DBusError(m.error or "", m.body[0] if m.body and isinstance(m.body[0], str) else "")
        return m.body

    def emit(self, path, interface, member, signature="", body=(), destination=None):
        self._send(Message(SIGNAL, flags=NO_REPLY, body=body, path=path, interface=interface, member=member,
                           destination=destination, signature=signature))

    def on_signal(self, interface, member, callback):
        """[callback](message) for each signal; the bus is asked to send them."""
        self.signals.append((interface, member, callback))
        self.call(BUS, BUS_PATH, BUS, "AddMatch", "s", [f"type='signal',interface='{interface}',member='{member}'"])

    def on_method(self, interface, member, callback):
        """Serves a method: [callback](message) returns (signature, body), or raises DBusError."""
        self.methods[(interface, member)] = callback

    def request_name(self, name):
        return self.call_sync(BUS, BUS_PATH, BUS, "RequestName", "su", [name, 4])[0] == 1

    def _readable(self, *_args):
        if self.sock is None:
            return
        try:
            while True:
                got = self.sock.recv(65536)
                if not got:
                    self.close()
                    self.closed.emit()
                    return
                self.buf += got
        except (BlockingIOError, InterruptedError):
            pass
        except OSError:
            self.close()
            self.closed.emit()
            return
        while True:
            m, used = decode(self.buf)
            if m is None:
                break
            del self.buf[:used]
            self._dispatch(m)

    def _dispatch(self, m):
        if m.type in (RETURN, ERROR):
            callback = self.replies.pop(m.reply_serial, None)
            if callback is not None:
                callback(m)
        elif m.type == SIGNAL:
            for interface, member, callback in list(self.signals):
                if m.interface == interface and m.member == member:
                    callback(m)
        elif m.type == CALL:
            self._serve(m)

    def _serve(self, m):
        callback = self.methods.get((m.interface, m.member))
        try:
            if callback is None:
                raise DBusError("org.freedesktop.DBus.Error.UnknownMethod", m.member or "")
            signature, body = callback(m)
            out = Message(RETURN, flags=NO_REPLY, body=body, reply_serial=m.serial, destination=m.sender,
                          signature=signature)
        except DBusError as e:
            out = Message(ERROR, flags=NO_REPLY, body=[str(e)], reply_serial=m.serial, destination=m.sender,
                          error=e.name, signature="s")
        if not m.flags & NO_REPLY:
            self._send(out)
