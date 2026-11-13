# Changelog

What changes in behaviour, compatibility and features, release by release. Bug fixes are not
listed one by one (read `git log` or the issues); security fixes are, under "Security", with
their issue.

## 1.0.0 (pre-release: alfa-1, alfa-2)

The 1.0.0 release is in pre-release. This list is cumulative: it grows with each pre-release
and is final at the release.

### Compatibility

- Needs the library `python3-activitytrack` 1.0.0~alfa-2 or later, and so a server on 1.0
  (sync wire schema 3).
- The data migrate by themselves to the activity model when the store is first opened; the
  to-do is now an activity in the state "Da fare".
- There is no "Sospendi" in the tray or the window, and the stop sheet is gone: an activity
  is suspended when another one starts.

### Features

- Home: four buttons (Da fare, Lavoro, Viaggio, Assenza); Viaggio starts a travel at once;
  work can be started now, already started or past; absence dialog (kind, company, days,
  optional times).
- Each activity shows the icon and colour of its displayed state; the detail has the state
  pill, the total and the actions the state allows. Priorities are named; the bin replaces
  "ignored".
- Travel from work asks whether the work is complete; stop offers the three choices of the
  return trip.

### Behaviour

- What a command moved or removed (an end moved back to a new activity's start, a planned
  segment removed) is shown as a notification.
- The notices of the sync appear in Settings, Sincronizzazione (and keep the alert on the
  sync button of the rail), with a button "Nascondi gli avvisi" to dismiss them.

Various bug fixes.

Earlier versions: see the release notes of each tag.
