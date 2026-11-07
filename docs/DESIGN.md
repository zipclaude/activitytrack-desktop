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
| D9 | Qt through PyQt6 (2026-11-01, §4). |
| D10 | No costs: no paid certificates or stores; the Windows installer is not signed (2026-11-01). |

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
- No distribution packages there: the release bundles Python, PyQt6 and
  the libraries (§8).

## 4. Technology

**Python 3 + Qt 6 through PyQt6, from the distribution's packages**
(`python3-pyqt6`: Debian 13 6.9, Debian 14 6.11, Ubuntu 24.04 6.6,
Ubuntu 26.04 6.10). Standard library SQLite for the local store.
PySide6 was the first choice, but Ubuntu 24.04 does not have it; PyQt6 is
GPL v3, as this project.

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

A navigation rail on the left, as the web's, with the sections of
`ui.SECTIONS` (Home, Da fare, Impostazioni; Ctrl+1… in that order) and
"Sincronizza" at the bottom; each section's page has its name and buttons on
top and a scrolling column, at most 920 px wide.

- **Home** (`home.py`), as the phone's `HomeScreen.kt`: the **big card** of
  the latest activity (the most recent start or end; a small card clicked
  takes its place): company, client, description, the state pill with its
  time, the totals, the running stretch's time, the tag dots, the round
  commands with their names under them. Then the **small cards** of the
  other activities running or suspended (one line, state, times, a round
  resume or pause button). Without an activity the big card has Avvia and
  Viaggio. Then the filters (period, state, company, tag as chips with
  menus; a search) and the list of to-dos and stopped activities in
  sections (`todos.home`, as `web/homelist.py`), each row with its state
  mark (overdue, planned, open, details missing, closed, done, ignored).
- **Da fare** (`todos_ui.py`): every to-do in the same sections, the done
  and the ignored on request, by company, with the search.
- **Activity form**: every field the policy shows; segments when
  `editableTimes`; expenses later.
- **To-do form**: title, notes, company/client, due date, plan (date,
  time, duration), priority.
- **Impostazioni**: Sincronizzazione (server and pairing, "Non
  sincronizzati"), Promemoria (each on/off, intervals within the policy),
  Generale (autostart, date and time formats, updates: GitLab check as the
  app, §12.4), as chips over their pages.

### 6.4 Look

The app's Material 3 (`theme.py`, `widgets.py`), the same design as the
web's `app.css`:

- **Fusion** style everywhere (KDE, XFCE, GNOME, Windows look alike), the
  palette and one application style sheet from the tokens: neutral pages
  (white and greys, or near-black and dark greys), the tonal palette of the
  launcher green #1F5C4A on the rail (#1F5C4A, dark #173F34), the buttons
  (filled, tonal, outlined, as pills) and what is selected.
- **Light or dark as the system**: `QStyleHints.colorScheme` (Qt ≥ 6.5,
  followed while running); on Qt 6.4 (Ubuntu 24.04) the lightness of the
  palette the system gave at the start.
- The activities keep the app's colours (`CommandButtons.kt`): work green
  #2E7D32, pause amber #F9A825 (dark icon), travel blue #1565C0, suspend
  orange #EF6C00, stop red #C62828. The company's colour (else the
  client's) is a band on the start edge of cards and rows; the tags'
  colours are dots at the top right.
- Painted widgets, no image files and no icon font: the cards, the round
  command buttons, the state pill, the list marks, the tag dots, the rail.
  The icons are the app's Material icons (Apache-2.0) as SVG path data
  (`icons.PATHS`), painted in any colour; the drop-down arrows are drawn
  into a temporary folder, as a style sheet takes them as files only.
- The text never smaller than 10 pt (Material's body); the dialogs have
  their name on top and, in the quick entry and the stop sheet, the
  fields' names above the fields, as the phone's screens.

### 6.5 Keys

While the window has the focus (`QAction`s of the window, shown in the
tooltips): Ctrl+N new activity (quick entry), Ctrl+P pause/resume, Ctrl+T
stop (the stop sheet when details are missing), Ctrl+D new to-do, Ctrl+F the
search of the list shown, Ctrl+1/2/3 the sections, F5 sync; Ctrl+Enter
confirms a form.

The activity a key acts on comes from `targets.py`, without Qt, for the
global shortcuts too (§10, phase 6):

- `pause_target(work)`: the activity at work or travelling;
- `resume_target(work)`: the paused one, else the latest suspended;
- `pause_or_resume(work)`: `(PAUSE, target)` when something is at work,
  else `(WORK, target)`, else `(None, None)`;
- `stop_target(work, focused_uid=None)`: the big card's while it runs,
  else the active one, else the suspended one;
- `running(work)`: the Home's order of the cards (the first is big).

Each returns an entry uid, None, or a list of uids, the latest first, when
it is the user's choice (two at work with concurrent activities): the
window shows them in a small list (`widgets.choose`), Enter takes the first.

### 6.6 Agenda and Report (later)

Two more sections of the rail, between Da fare and Impostazioni: an entry
in `ui.SECTIONS` each (key, name, icon `agenda` / `report`, the function
that builds the page), nothing else to change in the window; Ctrl+3 and
Ctrl+4 move to them and Impostazioni becomes Ctrl+5.

- **Agenda** (`agenda_ui.py`), as the web's agenda and the app's: day,
  week and month with ‹ › and "Oggi"; day and week a painted timeline
  (hours on the left, a column per day, blocks of the activities in the
  company's colour, running ones striped, planned to-dos outlined, the
  red line of now, the zoom); month a grid of days with the tag dots and
  the hours worked. A click on a block opens the activity or the to-do;
  a drag on empty space plans a to-do there (`Actions.new_todo(plan=…)`
  already takes it). The lanes of overlapping blocks and the totals come
  from the library (as `web/agenda.py`), so that the cli and the tui can
  use them.
- **Report** (`report_ui.py`): the period (day, week, month, custom), by
  company, client and tag, the totals of work, travel and pause per day
  and per client as the app's report (rounding as the policy says), with
  the export to CSV; the sums in the library (as `web/report.py`).
  Charts painted with QPainter (bars per day), no new dependency.

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
  PyInstaller (one folder: Python, PyQt6, cryptography, keyring) and
  Inno Setup; Start menu entry, autostart option, uninstaller. The
  bundled libraries are pinned in `requirements-windows.txt`, with the
  same versions as Debian 13 where possible.
- **Not signed on Windows** (D10): SmartScreen warns at the first run of
  the installer ("Ulteriori informazioni" → "Esegui comunque"); the user
  manual shows it, and the release page gives the installer's SHA-256 to
  check it.
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
6. **Later**: global shortcut (D7, on `targets.py`), Agenda and Report
   (§6.6), attachments, other packages.

## 11. Open points

None for now.
