# SPDX-License-Identifier: GPL-3.0-or-later
"""
System-wide keyboard shortcuts: one backend per desktop, chosen at run
time. Windows: RegisterHotKey; X11: XGrabKey on the root window
(python3-xlib, optional); Wayland: the GlobalShortcuts portal (jeepney), where the
desktop asks the user to confirm the keys. Each backend takes
{action: QKeySequence} and emits [activated](action).
"""

import os
import secrets
import sys

from PyQt6.QtCore import QAbstractNativeEventFilter, QObject, QSocketNotifier, Qt, pyqtSignal as Signal
from PyQt6.QtGui import QKeySequence

from activitytrack.i18n import _

# ---- the keys: Qt's key -> (X keysym name, keysym, Windows virtual key) ----

_KEYS = {}
for _i in range(26):
    _KEYS[Qt.Key.Key_A.value + _i] = (chr(ord("a") + _i), ord("a") + _i, ord("A") + _i)
for _i in range(10):
    _KEYS[Qt.Key.Key_0.value + _i] = (str(_i), ord("0") + _i, ord("0") + _i)
for _i in range(24):
    _KEYS[Qt.Key.Key_F1.value + _i] = (f"F{_i + 1}", 0xFFBE + _i, 0x70 + _i)
for _key, _value in {
    Qt.Key.Key_Space: ("space", 0x20, 0x20), Qt.Key.Key_Return: ("Return", 0xFF0D, 0x0D),
    Qt.Key.Key_Enter: ("KP_Enter", 0xFF8D, 0x0D), Qt.Key.Key_Escape: ("Escape", 0xFF1B, 0x1B),
    Qt.Key.Key_Tab: ("Tab", 0xFF09, 0x09), Qt.Key.Key_Backspace: ("BackSpace", 0xFF08, 0x08),
    Qt.Key.Key_Insert: ("Insert", 0xFF63, 0x2D), Qt.Key.Key_Delete: ("Delete", 0xFFFF, 0x2E),
    Qt.Key.Key_Home: ("Home", 0xFF50, 0x24), Qt.Key.Key_End: ("End", 0xFF57, 0x23),
    Qt.Key.Key_PageUp: ("Page_Up", 0xFF55, 0x21), Qt.Key.Key_PageDown: ("Page_Down", 0xFF56, 0x22),
    Qt.Key.Key_Left: ("Left", 0xFF51, 0x25), Qt.Key.Key_Up: ("Up", 0xFF52, 0x26),
    Qt.Key.Key_Right: ("Right", 0xFF53, 0x27), Qt.Key.Key_Down: ("Down", 0xFF54, 0x28),
    Qt.Key.Key_Print: ("Print", 0xFF61, 0x2C), Qt.Key.Key_Pause: ("Pause", 0xFF13, 0x13),
}.items():
    _KEYS[_key.value] = _value
# keys that are no text: a shortcut without Ctrl, Alt or Super is allowed on them
_ALONE = {Qt.Key.Key_Print.value, Qt.Key.Key_Pause.value, *range(Qt.Key.Key_F1.value, Qt.Key.Key_F24.value + 1)}
_MODIFIERS = (("ctrl", Qt.KeyboardModifier.ControlModifier), ("alt", Qt.KeyboardModifier.AltModifier),
              ("shift", Qt.KeyboardModifier.ShiftModifier), ("meta", Qt.KeyboardModifier.MetaModifier))


def parse(seq):
    """(Qt key, {modifiers}) of a one-combination shortcut a backend can take, else None."""
    if seq is None or seq.isEmpty() or seq.count() != 1:
        return None
    combo = seq[0]
    key = combo.key().value
    if key not in _KEYS:
        return None
    mods = frozenset(name for name, flag in _MODIFIERS if combo.keyboardModifiers() & flag)
    if not mods & {"ctrl", "alt", "meta"} and key not in _ALONE:
        # a letter alone, or with Shift, would take the key from every program
        return None
    return key, mods


def windows_keys(seq):
    """(MOD_* flags, VK_* code) for RegisterHotKey, else None."""
    p = parse(seq)
    if p is None:
        return None
    key, mods = p
    bits = {"alt": 0x1, "ctrl": 0x2, "shift": 0x4, "meta": 0x8}
    return sum(bits[m] for m in mods), _KEYS[key][2]


# X11's modifier masks (Mod1 is Alt, Mod4 Super on every current keymap)
X_SHIFT, X_LOCK, X_CONTROL, X_MOD1, X_MOD2, X_MOD4 = 1, 2, 4, 8, 16, 64
X_RELEVANT = X_SHIFT | X_CONTROL | X_MOD1 | X_MOD4


def x11_keys(seq):
    """(keysym, modifier mask) for XGrabKey, else None."""
    p = parse(seq)
    if p is None:
        return None
    key, mods = p
    bits = {"shift": X_SHIFT, "ctrl": X_CONTROL, "alt": X_MOD1, "meta": X_MOD4}
    return _KEYS[key][1], sum(bits[m] for m in mods)


def portal_trigger(seq):
    """The portal's preferred trigger ("CTRL+ALT+a", the shortcuts specification), else None."""
    p = parse(seq)
    if p is None:
        return None
    key, mods = p
    names = [n for m, n in (("ctrl", "CTRL"), ("alt", "ALT"), ("shift", "SHIFT"), ("meta", "LOGO")) if m in mods]
    return "+".join(names + [_KEYS[key][0]])


def text(seq):
    """A shortcut as the user reads it (Ctrl+Alt+A, in the interface's language)."""
    return seq.toString(QKeySequence.SequenceFormat.NativeText)


# ---- the backends ----

class Backend(QObject):
    """
    open() → None when it works here, else why not; bind({action: QKeySequence})
    replaces the shortcuts; [errors] {action: text} of those refused.
    """

    activated = Signal(str)
    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.errors = {}

    def title(self):
        return ""

    def open(self):
        return None

    def bind(self, bindings):
        self.errors = {}

    def close(self):
        pass

    def state(self):
        """A line on how the shortcuts stand, beyond the errors ("" when nothing to add)."""
        return ""


WM_HOTKEY = 0x0312
MOD_NOREPEAT = 0x4000


class _WindowsFilter(QAbstractNativeEventFilter):
    def __init__(self, backend):
        super().__init__()
        self.backend = backend

    def nativeEventFilter(self, event_type, message):
        if bytes(event_type) in (b"windows_dispatcher_MSG", b"windows_generic_MSG") and message:
            import ctypes.wintypes
            msg = ctypes.wintypes.MSG.from_address(int(message))
            if msg.message == WM_HOTKEY:
                action = self.backend.ids.get(int(msg.wParam))
                if action is not None:
                    self.backend.activated.emit(action)
                    return True, None
        return False, None


class WindowsBackend(Backend):
    """RegisterHotKey for the GUI thread (no window): WM_HOTKEY reaches Qt's native event filter."""

    def title(self):
        return "Windows"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.ids = {}
        self.filter = None

    def open(self):
        if sys.platform != "win32":
            return _("non è Windows")
        import ctypes
        from PyQt6.QtCore import QCoreApplication
        self.user32 = ctypes.WinDLL("user32", use_last_error=True)
        self.filter = _WindowsFilter(self)
        QCoreApplication.instance().installNativeEventFilter(self.filter)
        return None

    def bind(self, bindings):
        import ctypes
        self.close()
        self.errors = {}
        for n, (action, seq) in enumerate(sorted(bindings.items()), start=1):
            mods, vk = windows_keys(seq)
            if self.user32.RegisterHotKey(None, n, mods | MOD_NOREPEAT, vk):
                self.ids[n] = action
            else:
                code = ctypes.get_last_error()
                # 1409: ERROR_HOTKEY_ALREADY_REGISTERED
                self.errors[action] = _("già usata da un altro programma") if code == 1409 else f"Windows {code}"
        self.changed.emit()

    def close(self):
        for n in list(self.ids):
            self.user32.UnregisterHotKey(None, n)
        self.ids = {}


class X11Backend(Backend):
    """XGrabKey on the root window, with and without CapsLock and NumLock; the events read in the GUI thread."""

    def title(self):
        return "X11"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.display = None
        self.grabs = {}      # (keycode, mask) -> action

    def open(self):
        try:
            from Xlib import display
        except ImportError:
            return _("manca python3-xlib")
        try:
            self.display = display.Display()
        except Exception as e:
            return _("display X11 non raggiungibile (%s)") % (str(e) or type(e).__name__)
        self.root = self.display.screen().root
        self.numlock = self._numlock_mask()
        self.notifier = QSocketNotifier(self.display.fileno(), QSocketNotifier.Type.Read, self)
        self.notifier.activated.connect(self._events)
        return None

    def _numlock_mask(self):
        from Xlib import XK
        code = self.display.keysym_to_keycode(XK.string_to_keysym("Num_Lock"))
        for i, codes in enumerate(self.display.get_modifier_mapping()):
            if code and code in codes:
                return 1 << i
        return X_MOD2

    def _variants(self, mask):
        return sorted({mask, mask | X_LOCK, mask | self.numlock, mask | X_LOCK | self.numlock})

    def bind(self, bindings):
        from Xlib import X, error
        self._ungrab()
        self.errors = {}
        for action, seq in sorted(bindings.items()):
            keysym, mask = x11_keys(seq)
            keycode = self.display.keysym_to_keycode(keysym)
            if not keycode:
                self.errors[action] = _("tasto assente da questa tastiera")
                continue
            catchers = []
            for m in self._variants(mask):
                c = error.CatchError(error.BadAccess)
                self.root.grab_key(keycode, m, False, X.GrabModeAsync, X.GrabModeAsync, onerror=c)
                catchers.append(c)
            self.display.sync()
            if any(c.get_error() for c in catchers):
                for m in self._variants(mask):
                    self.root.ungrab_key(keycode, m)
                self.errors[action] = _("già usata da un altro programma")
            else:
                self.grabs[(keycode, mask)] = action
        self.display.sync()
        self._events()
        self.changed.emit()

    def _ungrab(self):
        for keycode, mask in self.grabs:
            for m in self._variants(mask):
                self.root.ungrab_key(keycode, m)
        self.grabs = {}

    def _events(self, *_args):
        from Xlib import X
        while self.display.pending_events():
            e = self.display.next_event()
            if e.type == X.KeyPress:
                action = self.grabs.get((e.detail, e.state & X_RELEVANT))
                if action is not None:
                    self.activated.emit(action)

    def close(self):
        if self.display is not None:
            self._ungrab()
            self.display.flush()


PORTAL = "org.freedesktop.portal.Desktop"
PORTAL_PATH = "/org/freedesktop/portal/desktop"
SHORTCUTS = "org.freedesktop.portal.GlobalShortcuts"
REQUEST = "org.freedesktop.portal.Request"
SESSION = "org.freedesktop.portal.Session"
REGISTRY = "org.freedesktop.host.portal.Registry"
APP_ID = "activitytrack-desktop"


def _variant(value):
    """The value of a variant as jeepney reads it ((signature, value)), or the value itself."""
    return value[1] if isinstance(value, tuple) and len(value) == 2 and isinstance(value[0], str) else value


class PortalBackend(Backend):
    """
    The XDG desktop portal's GlobalShortcuts (KDE Plasma 6, GNOME 48 and
    later): a session, its shortcuts bound with the keys as a preference,
    which the desktop confirms with the user; [Activated] when pressed.

    Over jeepney (QtDBus cannot send the portal's a(sa{sv}) from Python):
    its blocking connection, read in the GUI thread when a socket notifier
    says data came, receive(timeout=0) until nothing is left. No thread,
    no locking; only the first calls (open) wait for their reply.
    """

    WAITING, BOUND, REFUSED, FAILED = "waiting", "bound", "refused", "failed"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.conn = None
        self.session = None
        self.status = None
        self.triggers = {}
        self.replies = {}       # serial -> callback(message)
        self.requests = {}      # request path -> callback(code, results)
        self._generation = 0

    def title(self):
        return _("portale del desktop")

    def open(self):
        if not sys.platform.startswith("linux"):
            return _("non è Linux")
        try:
            from jeepney import DBusAddress, DBusErrorResponse, MatchRule, Properties, message_bus, new_method_call
            from jeepney.io.blocking import open_dbus_connection
        except ImportError:
            return _("manca python3-jeepney")
        try:
            self.conn = open_dbus_connection("SESSION")
        except Exception as e:
            # no address (KeyError), no socket, refused authentication…
            return _("bus di sessione non raggiungibile (%s)") % (str(e) or type(e).__name__)
        try:
            # a program outside a sandbox tells the portal who it is, before any other call
            self._call_sync(new_method_call(DBusAddress(PORTAL_PATH, PORTAL, REGISTRY), "Register", "sa{sv}",
                                            (APP_ID, {})))
        except (DBusErrorResponse, TimeoutError):
            pass
        try:
            self._call_sync(Properties(DBusAddress(PORTAL_PATH, PORTAL, SHORTCUTS)).get("version"), timeout=5)
            for interface in (REQUEST, SHORTCUTS):
                self._call_sync(message_bus.AddMatch(MatchRule(type="signal", interface=interface)))
        except (DBusErrorResponse, TimeoutError, OSError):
            self.conn.close()
            self.conn = None
            return _("il desktop non offre il portale GlobalShortcuts")
        self.notifier = QSocketNotifier(self.conn.sock.fileno(), QSocketNotifier.Type.Read, self)
        self.notifier.activated.connect(self._read)
        # what came with the replies above waits in jeepney's buffer, not on the socket
        self._read()
        return None

    def _call_sync(self, msg, timeout=3):
        from jeepney.wrappers import unwrap_msg
        return unwrap_msg(self.conn.send_and_get_reply(msg, timeout=timeout))

    def _call(self, path, interface, member, signature=None, body=(), reply=None):
        from jeepney import DBusAddress, new_method_call
        msg = new_method_call(DBusAddress(path, PORTAL, interface), member, signature, body)
        serial = next(self.conn.outgoing_serial)
        if reply is not None:
            self.replies[serial] = reply
        self.conn.send(msg, serial=serial)

    def _read(self, *_args):
        from jeepney import HeaderFields, MessageType
        while self.conn is not None:
            try:
                msg = self.conn.receive(timeout=0)
            except TimeoutError:
                return
            except OSError:
                # the bus went away
                self.notifier.setEnabled(False)
                self.conn = None
                self._done(2)
                return
            fields = msg.header.fields
            kind = msg.header.message_type
            if kind in (MessageType.method_return, MessageType.error):
                callback = self.replies.pop(fields.get(HeaderFields.reply_serial), None)
                if callback is not None:
                    callback(msg)
            elif kind == MessageType.signal:
                interface, member = fields.get(HeaderFields.interface), fields.get(HeaderFields.member)
                if (interface, member) == (REQUEST, "Response"):
                    callback = self.requests.pop(fields.get(HeaderFields.path), None)
                    if callback is not None and len(msg.body) >= 2:
                        callback(int(msg.body[0]), msg.body[1] or {})
                elif (interface, member) == (SHORTCUTS, "Activated"):
                    self._activated(msg.body)

    def _request(self, member, signature, body, callback):
        """A portal call with its Request: [callback](code, results) when the Response comes."""
        from jeepney import MessageType
        token = "atdesk" + secrets.token_hex(6)
        sender = self.conn.unique_name.lstrip(":").replace(".", "_")
        path = f"{PORTAL_PATH}/request/{sender}/{token}"
        self.requests[path] = callback
        body[-1]["handle_token"] = ("s", token)

        def replied(msg):
            if msg.header.message_type == MessageType.error:
                self.requests.pop(path, None)
                callback(2, {})
            elif msg.body and msg.body[0] != path:
                # an old portal: its own path
                self.requests[msg.body[0]] = self.requests.pop(path, callback)
        self._call(PORTAL_PATH, SHORTCUTS, member, signature, tuple(body), reply=replied)

    def bind(self, bindings):
        self._generation += 1
        generation = self._generation
        self.errors, self.triggers = {}, {}
        if self.session:
            self._call(self.session, SESSION, "Close")
            self.session = None
        if not bindings or self.conn is None:
            self.status = None if self.conn is not None else self.FAILED
            self.changed.emit()
            return
        self.status = self.WAITING
        self.changed.emit()
        shortcuts = [(action, {"description": ("s", action_names().get(action, action)),
                               "preferred_trigger": ("s", portal_trigger(seq))})
                     for action, seq in sorted(bindings.items())]

        def created(code, results):
            if generation != self._generation:
                return
            session = _variant(results.get("session_handle"))
            if code != 0 or not session:
                return self._done(code)
            self.session = str(session)
            self._request("BindShortcuts", "oa(sa{sv})sa{sv}", [self.session, shortcuts, "", {}], bound)

        def bound(code, results):
            if generation != self._generation:
                return
            if code == 0:
                for action, props in _variant(results.get("shortcuts")) or []:
                    self.triggers[action] = _variant((props or {}).get("trigger_description", ""))
            self._done(code)

        self._request("CreateSession", "a{sv}", [{"session_handle_token": ("s", "atdesk" + secrets.token_hex(6))}],
                      created)

    def _done(self, code):
        self.status = {0: self.BOUND, 1: self.REFUSED}.get(code, self.FAILED)
        self.changed.emit()

    def _activated(self, body):
        if len(body) >= 2 and self.session and str(body[0]) == self.session:
            options = body[3] if len(body) > 3 and isinstance(body[3], dict) else {}
            token = _variant(options.get("activation_token"))
            if token:
                # Wayland: the window the shortcut opens may take the focus with it
                os.environ["XDG_ACTIVATION_TOKEN"] = str(token)
            self.activated.emit(str(body[1]))

    def state(self):
        if self.status == self.WAITING:
            return _("In attesa della conferma del desktop…")
        if self.status == self.REFUSED:
            return _("Il desktop non ha confermato le scorciatoie.")
        if self.status == self.FAILED:
            return _("Il portale non ha registrato le scorciatoie.")
        if self.status == self.BOUND:
            return _("I tasti si confermano e si cambiano nelle impostazioni del desktop.")
        return ""

    def close(self):
        if self.conn is not None:
            if self.session:
                self._call(self.session, SESSION, "Close")
            self.notifier.setEnabled(False)
            self.conn.close()
            self.conn = None
        self.session = None


def action_names():
    """The actions as the user reads them."""
    return {"start": _("Nuova attività"), "pause": _("Pausa o ripresa dell'attività"),
            "stop": _("Stop dell'attività")}


BACKENDS = {"windows": WindowsBackend, "x11": X11Backend, "portal": PortalBackend}


def order(platform, qpa, wayland_session):
    """The backends to try, in order."""
    if platform == "win32":
        return ["windows"]
    if not platform.startswith("linux"):
        return []
    if qpa.startswith("wayland") or wayland_session:
        # under XWayland a grab sees only the X programs: the portal
        return ["portal"]
    if qpa == "xcb":
        return ["x11", "portal"]
    return []


def choose(platform=None, qpa=None, wayland_session=None, backends=None):
    """(the first backend that opens, or None; [(kind, why not)] of those that did not)."""
    from PyQt6.QtGui import QGuiApplication
    platform = platform or sys.platform
    qpa = qpa if qpa is not None else QGuiApplication.platformName()
    if wayland_session is None:
        wayland_session = os.environ.get("XDG_SESSION_TYPE") == "wayland" or bool(os.environ.get("WAYLAND_DISPLAY"))
    backends = BACKENDS if backends is None else backends
    reasons = []
    for kind in order(platform, qpa, wayland_session):
        if kind not in backends:
            continue
        backend = backends[kind]()
        why = backend.open()
        if why is None:
            return backend, reasons
        reasons.append((kind, why))
    return None, reasons
