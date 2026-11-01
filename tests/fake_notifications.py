# SPDX-License-Identifier: GPL-3.0-or-later
"""
A notification server on the session bus, for the notifier's test: it
answers each notification by pressing its first button, and writes what
it got to the file given.
"""

import json
import sys

from PyQt6.QtCore import QCoreApplication, QObject, QTimer, pyqtClassInfo, pyqtSignal, pyqtSlot
from PyQt6.QtDBus import QDBusAbstractAdaptor, QDBusConnection


@pyqtClassInfo("D-Bus Interface", "org.freedesktop.Notifications")
class Adaptor(QDBusAbstractAdaptor):
    ActionInvoked = pyqtSignal("uint", str)
    NotificationClosed = pyqtSignal("uint", "uint")

    def __init__(self, parent, log):
        super().__init__(parent)
        self.log = log
        self.next = 0

    @pyqtSlot(result="QStringList")
    def GetCapabilities(self):
        return ["actions", "body"]

    @pyqtSlot(str, "uint", str, str, str, "QStringList", "QVariantMap", int, result="uint")
    def Notify(self, app, replaces, icon, summary, body, actions, hints, timeout):
        self.next += 1
        nid = replaces or self.next
        with open(self.log, "a") as f:
            f.write(json.dumps({"id": nid, "summary": summary, "body": body, "actions": list(actions)}) + "\n")
        QTimer.singleShot(100, lambda: self.ActionInvoked.emit(nid, actions[0]))
        return nid

    @pyqtSlot("uint")
    def CloseNotification(self, nid):
        self.NotificationClosed.emit(nid, 3)


def main():
    app = QCoreApplication(sys.argv)
    bus = QDBusConnection.sessionBus()
    root = QObject()
    Adaptor(root, sys.argv[1])
    bus.registerObject("/org/freedesktop/Notifications", root)
    if not bus.registerService("org.freedesktop.Notifications"):
        sys.exit("service taken")
    print("ready", flush=True)
    app.exec()


if __name__ == "__main__":
    main()
