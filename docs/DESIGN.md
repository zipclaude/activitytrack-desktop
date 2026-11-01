# ActivityTrack Desktop — design

A tray application for the PC: the running activities and the *To-dos* a
click away, so that a short activity goes in from the keyboard instead of
the phone. It works with ActivityTrack Web (a prerequisite) as one more
synced device, like a phone.

Status: proposal, 2026-10-31. Linux first; Windows before the release.

## 1. Scope

In:
- the running activities and their commands: pause, travel, back to work,
  suspend, stop;
- new activities: quick start with the main fields, and the full form;
  every field may be written freely, not only picked from the master data
  (as on the phone, within the policy);
- editing activities: fields, times (when the policy allows), notes —
  descriptions from the PC tend to be long;
- *To-dos*: list with the Home's filters, start, done, ignore, new,
  postpone/plan;
- reminders as on the phone, each one switchable by the user;
- offline work, synced when the network is back.

Out (phone and web): reports, master-data editing, plugins / management
systems, attachments upload (first versions), absences, calendar export.

## 2. Owner decisions (2026-10-31)

| # | Decision |
|---|---|
| D1 | Pairing as for the phone: one-time link from the web, pasted in the app. |
| D2 | Quick entry from the notification/icon with the main fields; the full form for everything; free text allowed in every field. |
| D3 | To-dos: also create and postpone from the desktop. |
| D4 | All the phone's reminders are available, each one switchable by the user; duplicates with the phone are accepted. |
| D5 | Packages: `.deb` and `.tar.gz`; others later. |
| D6 | Version aligned with app and web. |
| D7 | Global shortcut: later, once the rest is stable. |
| D8 | Windows too, before the release (2026-11-01). |

## 3. Desktop environments

Targets: KDE Plasma and XFCE, on Wayland and X11; Windows 10 and 11 (§3.1).

- **Tray**: StatusNotifierItem over D-Bus (what Qt's `QSystemTrayIcon`
  uses when a `StatusNotifierWatcher` is present), XEmbed fallback on X11.
  Plasma: native. XFCE: the panel's notification area handles both. GNOME
  is not a target (it needs the AppIndicator extension).
- **Windows**: on Wayland the application cannot place its window next to
  the icon; the compositor decides. The window remembers its size, not its
  position.
- **Notifications**: `org.freedesktop.Notifications` with actions
  (buttons): "Pause", "Still working", "Open"…; a click on a reminder
  opens the matching form.
- **Secrets**: the device token in the Secret Service (KWallet, GNOME
  Keyring) via `python3-keyring`; without one, a file readable only by the
  user, said so in the settings.
- **Autostart**: an XDG autostart `.desktop` entry, switchable in the
  settings.
- **Single instance**: a second launch raises the window of the first
  (`QLocalServer`, a local socket on Linux and a named pipe on Windows).
- **Sleep**: a wall-clock jump between two ticks of the 30 s timer means
  the PC slept: sync at once, and the reminders are planned again. The
  same on both systems; no logind or Windows power events needed.

### 3.1 Windows

- **Tray**: the notification area, native in Qt.
- **Notifications**: Qt's tray messages become Windows toasts, without
  buttons: a click opens the window on the question ("Stai ancora
  lavorando…?"). Toasts with buttons (WinRT) may come later.
- **Secrets**: `keyring` uses the Credential Manager.
- **Autostart**: `HKCU\Software\Microsoft\Windows\CurrentVersion\Run`.
- **Data**: `%APPDATA%\ActivityTrack Desktop\` (Qt's `AppDataLocation`).
- **Certificates**: Python's `ssl` reads the Windows trust store; the pin
  works as on Linux.
- No distribution packages there: the release bundles Python, PySide6 and
  the libraries (§8).

## 4. Technology

**Python 3 + Qt 6 (PySide6), from the distribution's packages**
(`python3-pyside6.qtwidgets`, `.qtdbus`, `.qtnetwork`; Debian 13: 6.8,
Debian 14: 6.11). Standard library SQLite for the local store.

Why:
- Qt's tray is the one that works on Plasma and XFCE under Wayland and
  X11; widgets look native on KDE and follow the GTK theme on XFCE.
- The same language as the server: `web/ops.py` (the commands) and
  `web/homelist.py` (the Home list) are already Python ports of the app's
  rules.
- The same code runs on Windows (D8), and on macOS should it come.
- On Linux, Debian packages as for the web server: no bundled runtime.

Alternative considered: **Kotlin/JVM** reusing the app's `core:domain`
(pure Kotlin: policy parser and signature, reminder planner, start
defaults, to-do plan) and its sync engine (behind interfaces). Rejected
for the UI side, which is the product here: Compose Desktop's tray is
AWT's, XEmbed only (no tray on Wayland), and its windows run under
XWayland; a JVM for a resident tray icon is also heavy. What would be
reused is about 2,100 lines, ported to Python with their tests (§9).

To check before phase 1: PySide6 in Ubuntu 24.04 and 26.04 (the `.deb`
targets of the web).

## 5. Architecture

```
ui/        tray icon, menu, windows (Qt widgets)
model/     typed views of the records: Entry, Segment, Todo, Company…
ops/       commands, as web/ops.py and the app's rules
sync/      engine, transport, pairing (SYNC.md)
store/     SQLite: records, pending changes, state
reminders/ planner (port of ReminderPlanner.kt) and scheduler
policy/    parser, signature, gate (port of domain/policy)
```

### 5.1 Local store

The desktop keeps **every record it pulls**, raw:

```
record(type, uid, fields JSON, rev, deleted)      -- as the server last sent it
pending(seq, type, uid, op, fields JSON, times JSON)  -- local changes not yet pushed
state(key, value)                                  -- cursor, device id, server info
```

- The UI reads a record as `record.fields` overlaid with its `pending`
  fields; a command writes only to `pending` (field + time of change).
- Push sends `pending` in order (parents first), applies the answers to
  `record`, deletes the pushed rows; a refused field shows in "Non
  sincronizzati" as on the phone.
- Pull writes `record`; a field still in `pending` is not overwritten.
- Keeping every type raw (expenses, absences… too) costs little and lets a
  later version use them without a full resync. Attachment files are not
  downloaded.
- No shadow table: `record` is the shadow, `pending` the difference.

### 5.2 Sync

The phone's protocol (`SYNC.md` §5, §12), with the headers
`X-ActivityTrack-App` / `-Schema`:
- push a few seconds after a command (the server sees the change at once:
  the web and the phone's next sync);
- `sync/head` every 30 s while online, a pull when `rev` moved;
- on network return (Qt's `QNetworkInformation`) and on resume from
  sleep (§3);
- 401: "associazione revocata"; 426: the update message, data kept.

### 5.3 Rules shared with the phone

- **Commands** as the phone: a new start with an activity already running
  follows `features.concurrentEntries`; stop asks the details the phone
  asks (`complete_enough`), else the entry stays "dati mancanti".
- **Free text**: description, locality and notes are free; company,
  client and role complete from the master data, and a name they do not
  have becomes a new personal record, as the app's "Nuovo cliente" — when
  the policy's `masterData.source` is `user`. With `importOnly` only the
  central records can be picked, as on the phone.
- **Policy**: the desktop applies the keys it knows (features, fields,
  `editableTimes`, `tagsFreeText`, reminder intervals) and ignores the
  phone-only ones (location, calls, widgets…): a policy is not refused for
  a key the desktop does not use. Signature checked as on the phone.
- **Two devices at once**: commands on the PC and on the phone on the same
  entry merge field by field; overlapping segments get "da verificare"
  (`SYNC.md` §11), shown on the desktop too.

## 6. Interface

### 6.1 Tray icon

- Icon by state: idle, working, pause, travel, "da verificare" or not
  synced (a dot).
- Tooltip: the running activity, client and elapsed time; the count of
  overdue to-dos.
- **Left click**: the main window. **Middle click**: pause / back to work
  of the single running activity.
- **Menu**: per running activity, its commands; "Nuova attività…";
  "Avvia da fare ▸" (today's and overdue, at most 10); "Nuovo da fare…";
  "Sincronizza ora"; "Impostazioni"; "Esci".

### 6.2 Quick entry

A small window, keyboard first (Enter confirms, Esc closes):
- description (multi-line), company/client with completion from the
  master data and free text, tags;
- start now, or "already done" with start/end (a short activity recorded
  after the fact);
- "Altri campi…" opens the full form with what was typed.

### 6.3 Main window

- **Home**: the running activities with their commands, then the list of
  to-dos and stopped activities with the filters period, state, company,
  tag (as `web/homelist.py`).
- **Activity form**: every field the policy shows; segments when
  `editableTimes`; expenses later.
- **To-do form**: title, notes, company/client, due date, plan (date,
  time, duration), priority.
- **Settings**: server and pairing, reminders (each on/off, intervals
  within the policy), autostart, language, updates (GitHub check as the
  app, §12.4), "Non sincronizzati".

Languages: it, en, de, es (Qt `.ts` files, the app's strings as source).

## 7. Reminders

The phone's (`ReminderPlanner.kt`), each one with its switch:

| Reminder | Default on the desktop |
|---|---|
| "Stai ancora lavorando a …?" (confirm) | on |
| "Ancora in pausa?" | on |
| Planned to-do about to start | on |
| Day start without an activity | on |
| End-of-day summary | off |
| Activities with missing details | on |
| Sync: revoked, incompatible, not synced | on (not switchable) |
| Updates | on |

Not on the desktop: movement, arrival (location), calls. Duplicates with
the phone are accepted (D4); a reminder answered on one device disappears
from the other at the next sync, where the answer is a synced change
(a command, a to-do started).

## 8. Packaging and releases

- Version aligned with app and web (D6); tags `vX.Y.Z` on the desktop
  repository; the release workflow builds `activitytrack-desktop_X.Y.Z_all.deb`
  (Debian 13/14, Ubuntu) and `activitytrack-desktop-X.Y.Z.tar.gz`, with
  `SHA256SUMS`.
- Dependencies from the distribution only; `python3 -m activitytrack_desktop`
  from the tarball on other distributions.
- Files: `/usr/lib/python3/dist-packages/activitytrack_desktop/`,
  `/usr/bin/activitytrack-desktop`, `.desktop` file, icons (hicolor, SVG),
  AppStream metadata.
- Data: `~/.local/share/activitytrack-desktop/` (SQLite), settings in
  `~/.config/activitytrack-desktop/`.
- **Windows**: a per-user installer `ActivityTrackDesktop-X.Y.Z-setup.exe`
  (no administrator rights), made on the CI's Windows runner with
  PyInstaller (one folder: Python, PySide6, cryptography, keyring) and
  Inno Setup; Start menu entry, autostart option, uninstaller. The
  bundled libraries are pinned in `requirements-windows.txt`, with the
  same PySide6 minor as Debian 13 where possible.
- **Signing on Windows**: without a code-signing certificate SmartScreen
  warns at the first run ("Esegui comunque"). A certificate costs a yearly
  fee: to decide before the release.
- A user manual chapter (it/en) and screenshots; the server's admin manual
  says the desktop exists.

## 9. Server changes (activitytrack-web)

- `Device.kind` (`phone` | `desktop`), sent by `pair` (`kind`, default
  `phone`); "Telefoni" becomes "Dispositivi" in menu, pages and manual.
- A desktop cannot be the plugin holder ("Invia ai gestionali" hidden).
- The policy editor's "too old" warning counts phones only: the desktop
  ignores the keys it does not use (§5.3).
- `docs/SYNC.md`: the desktop as a node; nothing else changes on the wire
  (schema 1).

## 10. Phases

1. **Skeleton**: repository, packaging, CI (flake8, tests on Debian and
   on Windows, `.deb`/tar);
   tray icon, pairing by link, token in the keyring, store, sync engine
   (push/pull/head, 401, 426) with tests against a local server.
   Server: `Device.kind`, "Dispositivi".
2. **Activities**: running list, commands from menu and window, quick
   entry, full form, free-text fields, policy.
3. **To-dos**: Home list with filters, start/done/ignore, new and plan.
4. **Reminders**: planner port with its tests, notifications with actions,
   per-reminder switches.
5. **Finish**: settings, languages, update check, autostart, manual,
   the Windows installer (D8), release 1.0 together with app and web (or
   a 0.9.x beta first).
6. **Later**: global shortcut (D7), attachments, other packages.

## 11. Open points

- PySide6 on Ubuntu 24.04 (§4).
- Code signing on Windows (§8).
