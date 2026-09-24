# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-09-24

First public release.

### Added

- **Periodic eye-comfort check** (`rest_reminder.py`): every cycle a small
  borderless notification appears in the **bottom-right corner** (16 px from the
  right edge, above the taskbar) asking *"how do your eyes feel?"*, with four
  one-click answers — Comfortable, Dry/gritty, Strained/sore, Blurry — plus
  *Ask me later*.
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

[1.0.0]: https://github.com/JohnQsk/rest-reminder/releases/tag/v1.0.0
