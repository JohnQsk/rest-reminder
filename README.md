# Rest Reminder

> Pomodoro-style break reminder for **Windows**. Zero dependencies, no network access.

Cycles between work and break periods; when a work period ends, a **topmost popup**
reminds you to rest. This is a **20-20-20 eye-strain** schedule by design: 20 minutes
of work, a short 20-second break (with 30 cycles ≈ 10 hours of coverage).

> ⚠️ **Behavior warning**: the popup deliberately re-asserts itself to the top of the
> z-order every second (`SetWindowPos(HWND_TOPMOST)`), so it **cannot** be hidden
> behind other windows until you click **OK**, press **Enter**, or let it
> **auto-close after 30 seconds** (`--popup-timeout`). This is intended — it is how
> the first popup of the day gets noticed — but it is aggressive by design. If you
> would rather not have your focus taken at all, use **gentle mode**
> (`-Gentle` / `-g`), which sends a Windows toast instead.

## Requirements

- **Windows** (Windows 10 or 11 recommended).
- PowerShell version: Windows PowerShell 5.1 or PowerShell 7+. No modules required;
  `-Gentle` additionally needs [BurntToast](https://github.com/Windos/BurntToast).
- Python version: Python 3 with `tkinter` (standard library only, no pip packages).
  `tkinter` ships with the python.org Windows installer; if it is missing, re-run the
  installer and enable *tcl/tk and IDLE*.

## Implementations

- `rest_reminder.py` — Python 3 with `tkinter` (standard library only).
  **Maintained**: this is the implementation that receives new features.
- [`legacy/rest_reminder.ps1`](legacy/rest_reminder.ps1) — PowerShell, no
  dependencies. **Legacy and frozen**: it keeps working exactly as documented
  below, but it will not gain new functionality and it has **no eye-comfort
  check**. Kept for anyone who wants a PowerShell-only, install-nothing option.

Both follow the same schedule and the same popup behaviour. Gentle mode differs
slightly: Python shells out to the built-in WinRT toast API, PowerShell uses the
BurntToast module, so neither needs a third-party package.

## Eye-comfort check (Python)

Every cycle, before the break popup appears, a **native Windows toast
notification** — the familiar bottom-right message that slides in from the
Action Center — asks *"how do your eyes feel?"*:

- **It needs no click.** The toast fades on its own after a few seconds, exactly
  like any other Windows notification.
- It uses the real WinRT toast API, not a hand-drawn window, and no third-party
  package is needed (Python raises it through PowerShell's built-in WinRT
  bindings).
- Send it every cycle (default) or disable it with `--no-eye-check`.

> **Focus Assist / Do Not Disturb silently suppresses toasts.** Windows gives no
> confirmation that a toast was painted, so the script reports the result as
> *"sent (acceptance unconfirmed)"*. If you never see these notifications, turn
> Focus Assist off, or check the notification settings for *Rest Reminder*.
> Keep the eye reminder audible/visible by trusting the break popup instead if
> toasts are being swallowed.

> This is a self-report prompt, not a diagnosis. If your eyes stay sore or your
> vision stays blurry, see an eye-care professional.

## The popup problem and how it is solved

Windows does not allow a background process to steal focus: a dialog raised
by a script that has been sleeping for 20 minutes appears **behind** all
other windows (the process has lost its foreground rights). This is why the
first popup of the day used to go unnoticed, while later ones worked —
clicking the first popup re-granted the process foreground rights.

Both implementations work around this the same way:

1. The popup window is created with the *topmost* flag set.
2. A 1-second timer keeps re-asserting the flag (`SetWindowPos(HWND_TOPMOST)`),
   which is **not** subject to the foreground lock, so the popup climbs back
   above all windows until you click **OK** (or press **Enter**).

This is a Windows-specific mechanism. The scripts will start on Linux/macOS only if
`tkinter` is present, but the re-assertion trick has no effect there, so the popup
behaves like an ordinary window and gentle mode is unavailable.

## Usage

PowerShell (legacy script, run from the repository root):

```powershell
.\legacy\rest_reminder.ps1                                        # defaults
.\legacy\rest_reminder.ps1 -WorkTime_s 1500 -BreakTime_s 30 -TotalCycles 10
.\legacy\rest_reminder.ps1 -Gentle                                # system notification instead of the popup
.\legacy\rest_reminder.ps1 -WorkTime_s 3 -BreakTime_s 2 -TotalCycles 1   # quick test
```

Python:

```powershell
python rest_reminder.py                              # defaults
python rest_reminder.py -w 1500 -b 30 -c 10
python rest_reminder.py -g                           # toasts only, no blocking popup
python rest_reminder.py --no-eye-check               # break popup only
python rest_reminder.py --popup-timeout 0            # keep the popup until dismissed
python rest_reminder.py -w 3 -b 2 -c 1               # quick test
python rest_reminder.py -h                           # full help
```

## Parameters

| PowerShell     | Python             | Default | Description                          |
| -------------- | ------------------ | ------- | ------------------------------------ |
| `-WorkTime_s`  | `-w/--work-time`   | 1200    | work time per cycle (seconds)        |
| `-BreakTime_s` | `-b/--break-time`  | 20      | break time per cycle (seconds)       |
| `-TotalCycles` | `-c/--cycles`      | 30      | total number of cycles               |
| `-Gentle`      | `-g/--gentle`      | off     | toast instead of popup               |
| —              | `--eye-check`      | on      | bottom-right eye-comfort toast       |
| —              | `--no-eye-check`   | —       | disable the eye-comfort toast        |
| —              | `--popup-timeout`  | 30      | auto-close the popup after N seconds |

## Notes

- 20 seconds of break for 20 minutes of work is deliberate, not a bug: it is the
  [20-20-20 rule](https://www.aao.org/eye-health/tips-prevention/computer-usage) for
  reducing eye strain. Adjust `-BreakTime_s` / `-b` if you want a longer break.
- Stop the script at any time with `Ctrl+C`.
- Gentle mode is best-effort: if the Windows toast API is unavailable (Python) or
  BurntToast is missing (PowerShell), the script prints a notice and falls back to the
  topmost popup rather than failing.
- Windows' foreground lock can leave a freshly started process without foreground
  rights. The popup is then visible and topmost but never receives keystrokes, so
  **Enter may not dismiss it** — click OK, or rely on the 30-second auto-close (use
  `--popup-timeout 0` to disable the auto-close, at which point a click is the only
  way out).
- The eye-comfort toast only exists in the Python implementation. The legacy
  PowerShell script is frozen and will not get it.
- A running countdown is shown in the console (`Write-Progress` in PowerShell, an
  in-place `\r` line in Python).
- The legacy PowerShell script may be dot-sourced to reuse `Start-RestReminder`
  without starting a session: `. .\legacy\rest_reminder.ps1`.

## License

MIT — see [LICENSE](LICENSE).

## Changelog

See [CHANGELOG.md](CHANGELOG.md).
