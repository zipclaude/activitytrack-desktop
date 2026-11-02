# SPDX-License-Identifier: GPL-3.0-or-later
"""
Desktop notifications (docs/DESIGN.md §3, §3.1): on Linux the
freedesktop service over D-Bus, with buttons (Plasma, XFCE's notifyd);
elsewhere, or without the service, the tray icon's messages, without
buttons: a click opens the same question in a window.
"""

from PyQt6.QtCore import QMetaType, QObject, pyqtSignal as Signal, pyqtSlot as Slot

from activitytrack.i18n import _

try:
    from PyQt6.QtDBus import QDBusArgument, QDBusConnection, QDBusInterface, QDBusMessage
except ImportError:
    # Windows: the tray's messages only
    QDBusConnection = QDBusMessage = None


def _dbus_slot(method):
    """The D-Bus signals arrive as messages: PyQt picks that overload from the decorated signature."""
    return Slot(QDBusMessage)(method) if QDBusMessage is not None else method


SERVICE = "org.freedesktop.Notifications"
PATH = "/org/freedesktop/Notifications"
DEFAULT = "default"


class Notifier(QObject):
    """
    show(key, …) posts or replaces the notification of [key] (a reminder);
    [answered] (key, action) when a button is pressed or the notification
    clicked (action "default").
    """

    answered = Signal(str, str)

    def __init__(self, tray=None, use_dbus=True, parent=None):
        super().__init__(parent)
        self.tray = tray
        self._ids = {}       # key -> notification id
        self._keys = {}      # notification id -> key
        self._last_tray_key = None
        self.bus = None
        self.buttons = False
        if use_dbus and QDBusConnection is not None:
            self._connect()
        if tray is not None:
            self.attach_tray(tray)

    def _connect(self):
        bus = QDBusConnection.sessionBus()
        if not bus.isConnected():
            return
        iface = QDBusInterface(SERVICE, PATH, SERVICE, bus)
        if not iface.isValid():
            return
        caps = iface.call("GetCapabilities")
        args = caps.arguments() if caps.type() == QDBusMessage.MessageType.ReplyMessage else []
        self.buttons = bool(args) and "actions" in (args[0] or [])
        self.bus = bus
        self.iface = iface
        bus.connect(SERVICE, PATH, SERVICE, "ActionInvoked", self._invoked)
        bus.connect(SERVICE, PATH, SERVICE, "NotificationClosed", self._closed)

    def attach_tray(self, tray):
        """The tray icon whose messages stand in when there is no notification service."""
        self.tray = tray
        tray.messageClicked.connect(self._tray_clicked)

    @property
    def native(self):
        """Notifications with buttons: the answers need no window."""
        return self.bus is not None and self.buttons

    def show(self, key, title, body, actions=(), persistent=True):
        """actions: [(id, label)]; persistent: stays until answered (the server may still expire it)."""
        if self.bus is not None:
            flat = []
            for action_id, label in actions if self.buttons else ():
                flat += [action_id, label]
            flat += [DEFAULT, _("Apri")]
            replaces = QDBusArgument(self._ids.get(key, 0), QMetaType.Type.UInt.value)
            # the specification's types: a Python list would travel as "av", not "as"
            flat = QDBusArgument(flat, QMetaType.Type.QStringList.value)
            reply = self.iface.call("Notify", "ActivityTrack", replaces, "activitytrack-desktop", title, body, flat,
                                    {"desktop-entry": "activitytrack-desktop"}, 0 if persistent else -1)
            if reply.type() == QDBusMessage.MessageType.ReplyMessage and reply.arguments():
                nid = int(reply.arguments()[0])
                self._ids[key] = nid
                self._keys[nid] = key
                return
        if self.tray is not None:
            self._last_tray_key = key
            self.tray.showMessage(title, body, self.tray.icon(), 0 if persistent else 10_000)

    def close(self, key):
        nid = self._ids.pop(key, None)
        if nid is not None:
            self._keys.pop(nid, None)
            if self.bus is not None:
                self.iface.call("CloseNotification", QDBusArgument(nid, QMetaType.Type.UInt.value))

    @_dbus_slot
    def _invoked(self, msg):
        args = msg.arguments()
        if len(args) < 2:
            return
        key = self._keys.get(int(args[0]))
        if key is not None:
            self.answered.emit(key, str(args[1]))
            self.close(key)

    @_dbus_slot
    def _closed(self, msg):
        args = msg.arguments()
        if args:
            key = self._keys.pop(int(args[0]), None)
            if key is not None:
                self._ids.pop(key, None)

    def _tray_clicked(self):
        if self._last_tray_key is not None:
            self.answered.emit(self._last_tray_key, DEFAULT)
            self._last_tray_key = None
