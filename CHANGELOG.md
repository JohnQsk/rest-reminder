# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.3.0] - 2026-09-24

### Fixed

- **The eye-comfort notification never actually appeared.** It used the WinRT
  toast API with the AUMID `'Rest Reminder'`, which is not a registered
  application identity. With an unregistered AUMID, `ToastNotification.Show()`
  returns success and renders **nothing at all**, so the call looked healthy
  while the user saw no window. Toasts require a Start-menu entry carrying a
  `System.AppUserModel.ID`; this project ships as plain `.py` files and must not
  depend on an installer having registered one. This also explains why every
  third-party Python option (`win11toast`, `Windows-Toasts`, `plyer`,
  `desktop-notifier`) has the same limitation — they all wrap the same API.

### Changed

- The eye-comfort notification now uses the **notification-area balloon**
  (`System.Windows.Forms.NotifyIcon.ShowBalloonTip`) through PowerShell's
  built-in .NET bindings: same bottom-right corner, still needs no click and no
  third-party package, but **no AUMID registration required**, so it works from
  a bare checkout. Verified to display on Windows 10 22H2 (19045).
- Added `--eye-method balloon|toast` (default `balloon`). `toast` is retained
  for anyone whose application identity *is* registered.
- Added `--eye-seconds` (default `8`) to control how long the balloon stays on
  screen; Windows may apply its own timeout.
- Gentle mode (`-g`) now uses the same mechanism as the eye notification instead
  of the toast, so it no longer silently produces nothing when the identity is
  unregistered. As a consequence `-g` no longer needs a popup fallback: the
  balloon is itself reliable.

## [1.2.0] - 2026-09-24

### Changed

- The eye-comfort toast now fires on a **cadence of its own, every 5 minutes by
  default** (`--eye-interval SECONDS`), instead of once per pomodoro cycle. It
  is raised *during* the work period rather than at the end of it, because the
  20-20-20 rule is a 20-minute rule for the eyes: with the defaults the nudge
  now arrives at 5, 10 and 15 minutes instead of once at 20.
- The cadence stays absolute rather than relative: the next toast is scheduled
  from the previous one, so a slow iteration cannot make it drift.

## [1.1.0] - 2026-09-24

### Changed

- The eye-comfort reminder is now a **native Windows toast notification** (the
  OS message that slides in from the bottom-right) instead of a hand-drawn
  tkinter window. It requires no click and dismisses itself, as requested.
  `--eye-log` and the one-click answer buttons are gone with the custom window;
  the nudge is now purely a nudge.
- The break popup **auto-closes after 30 seconds** (`--popup-timeout SECONDS`,
  `0` to keep it open). It shows *"auto-closes in Ns"* in the final 5 seconds.
  This was necessary because Windows' foreground lock can leave the popup
  topmost but unable to receive keystrokes.
- `rest_reminder.py` reports whether each notification was actually sent and
  falls back to the popup with a visible reason instead of failing silently.

### Fixed

- **Native toasts never worked in `rest_reminder.py`.** The PowerShell snippet
  used `$(& $esc $Title)`, which is a syntax error in PowerShell (the call
  operator `&` is not valid inside a subexpression), so every toast attempt
  exited non-zero and the script fell back to the popup without saying so.
  Escaping now uses a direct `[System.Security.SecurityElement]::Escape()` call.
- Toast arguments are now passed as environment variables. `powershell -Command
  <snippet> -Title x` does **not** bind arguments to the snippet's `param()`
  block (`-File` is required for that, but `-File` is blocked by the default
  execution policy on many machines), so named parameters silently failed.

### Known limitations

- Windows provides no confirmation that a notification was displayed. Focus
  Assist / Do Not Disturb suppresses them silently, so the success message is
  reported as *"acceptance unconfirmed"*. (Since 1.3.0 the notification itself
  is the balloon, which needs no app registration.)
- Windows' foreground lock can prevent the popup from ever receiving keyboard
  focus, so **Enter may not dismiss it**; clicking OK and the auto-close both
  work. `focus_force()` was tested and does not fix this.

## [1.0.0] - 2026-09-24

First public release.

### Added

- **Periodic eye-comfort check** (`rest_reminder.py`): every cycle a small
  borderless notification appears in the **bottom-right corner** (16 px from the
  right edge, above the taskbar) asking *"how do your eyes feel?"*, with four
  one-click answers — Comfortable, Dry/gritty, Strained/sore, Blurry — plus
  *Ask me later*.
  - *Superseded in [1.1.0]: the hand-drawn corner window was replaced by a
    native Windows toast, and the answer buttons were dropped.*
  - The window is deliberately **non-activating**: it never steals focus, so a
    running countdown or your typing is not interrupted.
  - It answers with a single click and auto-dismisses after 45 seconds, so an
    ignored window cannot pile up. An unanswered window is collapsed before the
    next cycle's check.
  - `--eye-log PATH` appends every answer to a CSV file
    (`timestamp, cycle, feeling, feeling_label, answer`) for spotting trends.
  - Enabled by default; disable it with `--no-eye-check`.
- MIT `LICENSE`.
- `.gitignore` and `.gitattributes` (repository text normalised to LF;
  `.ps1` files checked out as CRLF).

### Added (PowerShell, later frozen)

- `-Gentle` switch: use a BurntToast system notification instead of the
  focus-stealing popup, with a warning and automatic fallback when the
  BurntToast module is absent.

### Changed

- **The PowerShell implementation is now legacy.** `rest_reminder.ps1` moved to
  [`legacy/rest_reminder.ps1`](legacy/rest_reminder.ps1) and is **frozen**: it
  keeps working as documented, but receives no new features. `rest_reminder.py`
  is the maintained implementation. The PowerShell script has no eye-comfort
  check.
- `rest_reminder.py` no longer creates and destroys a `tk.Tk()` root for every
  popup. A single hidden root lives for the whole session and every window is a
  `Toplevel` of it, instead of rebuilding the Tcl interpreter up to 30 times per
  run.
- Gentle-mode notifications in `rest_reminder.py` are raised through
  PowerShell's WinRT bindings rather than a hand-rolled `ctypes` vtable walk, so
  the feature is dependency-free *and* actually reliable. It still falls back to
  the popup on failure.
- The break popup and the eye-comfort window wrap on the same width, and the
  README now states the intended schedule (20-20-20) explicitly so the short
  break is not mistaken for a bug.
- `Ctrl+C` now exits cleanly (`KeyboardInterrupt` is caught and the Tk root is
  destroyed) instead of dumping a traceback.

### Fixed

- `rest_reminder.ps1` called `New-BurntToastNotification` without importing the
  BurntToast module, so the notification path failed even when the module was
  installed. Added the `Import-Module` call.
- Removed dead code in `rest_reminder.ps1` (an empty `if` block wrapping a
  commented-out notification call).
- `rest_reminder.ps1` executed its main loop on dot-source, which made
  `Start-RestReminder` impossible to reuse. It now runs only when invoked
  directly.
- Removed a duplicated UTF-8 BOM at the start of `rest_reminder.py`, which broke
  the `#!/usr/bin/env python3` shebang outside Windows.
- The PowerShell banner reported integer-divided work minutes (`0 minutes` for a
  3-second test); both implementations now round consistently.

### Security

- Verified no secrets, credentials, email addresses or local filesystem paths
  are committed. The only personal data in the repository is the copyright
  holder named in `LICENSE`.

[1.3.0]: https://github.com/JohnQsk/rest-reminder/releases/tag/v1.3.0
[1.2.0]: https://github.com/JohnQsk/rest-reminder/releases/tag/v1.2.0
[1.1.0]: https://github.com/JohnQsk/rest-reminder/releases/tag/v1.1.0
[1.0.0]: https://github.com/JohnQsk/rest-reminder/releases/tag/v1.0.0
