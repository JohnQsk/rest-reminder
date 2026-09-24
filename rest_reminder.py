#!/usr/bin/env python3
"""Pomodoro-style rest reminder with a periodic eye-comfort nudge.

Cycles between work and break periods. When a work period ends, a topmost
popup reminds you to rest. During the work period, a Windows notification-area
balloon asks how your eyes feel on a fixed cadence — every 5 minutes by
default, independently of the cycle length. A 1-second timer re-asserts the
popup's topmost flag so it climbs back above all windows until you click OK
(same trick as the legacy PowerShell version: setting topmost is not subject
to Windows' foreground lock).

The eye-comfort nudge needs no click and hides itself. It uses a notification
balloon via System.Windows.Forms.NotifyIcon rather than a WinRT toast, because a
toast only renders when its sender AUMID is registered as an installed app —
from a bare checkout it silently renders nothing. Both paths are driven through
PowerShell's built-in .NET bindings, so no third-party Python package is needed.

Usage:
    python rest_reminder.py                      # defaults: 20min work, 20s break, 30 cycles
    python rest_reminder.py -w 1500 -b 30 -c 10  # 25min work, 30s break, 10 cycles
    python rest_reminder.py -w 3 -b 2 -c 1       # quick test run
    python rest_reminder.py -g -w 3 -b 2 -c 1    # no blocking popup at all
    python rest_reminder.py --eye-interval 600   # eye nudge every 10 minutes
    python rest_reminder.py --no-eye-check       # break popup only

Options:
    -w, --work-time    work time per cycle, in seconds (default: 1200)
    -b, --break-time   break time per cycle, in seconds (default: 20)
    -c, --cycles       total number of cycles (default: 30)
    -g, --gentle       use a Windows notification for the break reminder too,
                       instead of the focus-stealing popup (falls back to the
                       popup if the notification cannot be shown)
        --eye-check    send the eye-comfort notification on the
                       --eye-interval cadence (default: on; use --no-eye-check
                       to disable)
        --eye-interval seconds between eye-comfort notifications during work
                       (default: 300, i.e. the 20-20-20 rule)
        --eye-method   'balloon' (default, needs no app registration) or
                       'toast' (WinRT toast, only renders for a registered app)
        --eye-seconds  how long the balloon stays on screen (default: 8)
    -h, --help         show the built-in help message

Notes:
    - Platform: Windows.
    - Notifications are best-effort. Windows may suppress them (Focus Assist /
      Do Not Disturb) and gives no confirmation that anything was painted, so a
      successful call is reported as "acceptance unconfirmed" rather than as
      proof that a window appeared.
    - Close the popup with the OK button or the Enter key. The popup cannot be
      hidden behind other windows while it is open; use -g to avoid it.
    - Stop the script at any time with Ctrl+C.
    - Requires no third-party packages; uses tkinter from the standard library.
"""

import argparse
import os
import subprocess
import sys
import time
import tkinter as tk

POPUP_WIDTH = 420
POPUP_HEIGHT = 200


# PowerShell snippet that raises a notification-area balloon via
# System.Windows.Forms.NotifyIcon.
#
# A balloon is used instead of a WinRT toast on purpose. Showing a toast requires
# the sender's AUMID to be registered (a Start-menu entry carrying a
# System.AppUserModel.ID): with an unregistered AUMID, Show() succeeds and
# renders nothing at all, which is exactly the bug that made this feature look
# broken. This project is handed out as bare .py files, so it must not depend on
# an installer having registered an application identity. NotifyIcon is the older
# Win32 path and needs no registration whatsoever.
#
# Arguments arrive through environment variables (RR_TITLE / RR_MESSAGE /
# RR_SECONDS) rather than named parameters: `powershell -Command <script>
# -Title x` does NOT bind those to the snippet's param() block, and -File is
# blocked by the default execution policy on many machines.
_BALLOON_PS = r"""
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
$ni = New-Object System.Windows.Forms.NotifyIcon
$ni.Icon = [System.Drawing.SystemIcons]::Information
$ni.BalloonTipTitle = $env:RR_TITLE
$ni.BalloonTipText = $env:RR_MESSAGE
$ni.BalloonTipIcon = [System.Windows.Forms.ToolTipIcon]::Info
$ni.Visible = $true
$ni.ShowBalloonTip([int]$env:RR_SECONDS * 1000)
Start-Sleep -Seconds ([int]$env:RR_SECONDS + 1)
$ni.Visible = $false
$ni.Dispose()
"""


# WinRT toast variant, kept for --eye-method toast. See the note above: this only
# renders when the AUMID passed to CreateToastNotifier is registered, which
# 'Rest Reminder' is not.
_TOAST_PS = r"""
$ErrorActionPreference = 'Stop'
$null = [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime]
$null = [Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime]
$body = '<text>' + [System.Security.SecurityElement]::Escape($env:RR_TITLE) + '</text><text>' + [System.Security.SecurityElement]::Escape($env:RR_MESSAGE) + '</text>'
$xml = New-Object Windows.Data.Xml.Dom.XmlDocument
$xml.LoadXml("<toast><visual><binding template='ToastGeneric'>$body</binding></visual></toast>")
$toast = New-Object Windows.UI.Notifications.ToastNotification $xml
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('Rest Reminder').Show($toast)
"""


def _run_ps(snippet, title, message, seconds=None):
    """Run a notification snippet. Returns (ok, detail).

    ok=True means PowerShell accepted the call. Windows gives no confirmation
    that anything was painted, so the detail says so explicitly.
    """
    if not sys.platform.startswith("win"):
        return False, "Windows notifications require Windows"

    env = dict(os.environ)
    env["RR_TITLE"] = title
    env["RR_MESSAGE"] = message
    if seconds is not None:
        env["RR_SECONDS"] = str(seconds)
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive",
             "-WindowStyle", "Hidden", "-Command", snippet],
            capture_output=True,
            text=True,
            timeout=60,
            env=env,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return False, f"could not run PowerShell: {exc}"

    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip().splitlines()
        return False, f"PowerShell exited {result.returncode}: {detail[0] if detail else 'no output'}"
    return True, "sent (acceptance unconfirmed; Focus Assist may suppress it)"


def show_balloon(message, title="Eye check", seconds=8):
    """Show a notification-area balloon. Returns (ok, detail).

    Needs no AUMID registration, so it works from a bare checkout. The balloon
    requires no click and hides itself after the system timeout.
    """
    return _run_ps(_BALLOON_PS, title, message, seconds=seconds)


def show_toast(message, title="Eye check"):
    """Show a WinRT toast. Returns (ok, detail).

    Only renders when the notifier's AUMID is registered; kept for
    --eye-method toast.
    """
    return _run_ps(_TOAST_PS, title, message)


def show_notification(root, message, title="Health Reminder", timeout=30):
    """Show a topmost popup and block until it is dismissed.

    The popup closes when the user clicks OK / presses Enter, or on its own
    after `timeout` seconds. The auto-close matters because Windows' foreground
    lock can leave the process without foreground rights, in which case the
    popup is visible and topmost but never receives keystrokes: without a
    timeout it would sit there until clicked. Pass timeout=0 to keep it open
    until it is dismissed.
    """
    win = tk.Toplevel(root)
    win.title(title)
    win.resizable(False, False)

    screen_w = win.winfo_screenwidth()
    screen_h = win.winfo_screenheight()
    win.geometry(
        f"{POPUP_WIDTH}x{POPUP_HEIGHT}"
        f"+{(screen_w - POPUP_WIDTH) // 2}+{(screen_h - POPUP_HEIGHT) // 2}"
    )

    label = tk.Label(win, text=message, justify="center", wraplength=POPUP_WIDTH - 20)
    label.pack(expand=True, fill="both", padx=10, pady=10)

    closed = False

    def close():
        nonlocal closed
        if closed:
            return
        closed = True
        win.destroy()

    ok_text = "OK" if not timeout else f"OK  (auto-closes in {timeout}s)"
    ok = tk.Button(win, text=ok_text, width=26, command=close)
    ok.pack(pady=(0, 12))
    ok.focus_set()
    win.bind("<Return>", lambda _event: close())
    win.bind("<Escape>", lambda _event: close())
    win.protocol("WM_DELETE_WINDOW", close)

    def reassert_topmost():
        if closed or not win.winfo_exists():
            return
        # Toggling the flag forces SetWindowPos(HWND_TOPMOST) again,
        # pushing the dialog back to the top of the z-order.
        win.attributes("-topmost", False)
        win.attributes("-topmost", True)
        win.lift()
        win.after(1000, reassert_topmost)

    def countdown_close(remaining):
        if closed or not win.winfo_exists():
            return
        if remaining <= 0:
            close()
            return
        if remaining <= 5:
            ok.config(text=f"OK  (auto-closes in {remaining}s)")
        win.after(1000, lambda: countdown_close(remaining - 1))

    win.attributes("-topmost", True)
    win.lift()
    win.after(1000, reassert_topmost)
    if timeout:
        win.after(1000, lambda: countdown_close(timeout))

    win.wait_window()


def countdown(seconds, activity):
    for sec in range(seconds, 0, -1):
        print(f"\r{activity}: {sec:4d}s remaining", end="", flush=True)
        time.sleep(1)
    print()


def notify(method, message, title="Eye check", seconds=8):
    """Dispatch to the selected notification method. Returns (ok, detail)."""
    if method == "toast":
        return show_toast(message, title)
    return show_balloon(message, title, seconds=seconds)


def run_work_period(seconds, eye_interval, eye_method="balloon", eye_seconds=8,
                    activity="Work countdown"):
    """Count down a work period, raising an eye-comfort notification on a cadence.

    `eye_interval` is independent of the cycle length: with the defaults the
    work period is 20 minutes and the notification fires every 5, 10 and 15
    minutes. That is the point — the 20-20-20 rule is a 20-minute rule for the
    *eyes*, so it should not stretch just because the pomodoro got longer.
    """
    next_eye = eye_interval if eye_interval > 0 else None
    for sec in range(seconds, 0, -1):
        elapsed = seconds - sec
        print(f"\r{activity}: {sec:4d}s remaining", end="", flush=True)

        if next_eye is not None and elapsed >= next_eye:
            ok, detail = notify(
                eye_method,
                "How do your eyes feel? Look 20 feet away for 20 seconds, "
                "and blink deliberately.",
                "Eye check",
                seconds=eye_seconds,
            )
            print(f"\r  [eye check at {elapsed // 60}m{elapsed % 60:02d}s] "
                  f"{'ok' if ok else 'FAILED'} - {detail}")
            # Keep an absolute cadence even if this iteration ran long.
            next_eye += eye_interval

        time.sleep(1)
    print()


def main():
    parser = argparse.ArgumentParser(
        description="Pomodoro-style rest reminder with a topmost break popup "
                    "and a bottom-right eye-comfort notification.",
        epilog="examples:\n"
               "  python rest_reminder.py                     # 20min work, 20s break, 30 cycles\n"
               "  python rest_reminder.py -w 1500 -b 30 -c 10 # 25min work, 30s break, 10 cycles\n"
               "  python rest_reminder.py -w 3 -b 2 -c 1      # quick test run\n"
               "  python rest_reminder.py -g -w 3 -b 2 -c 1   # toasts only, no popup\n"
               "  python rest_reminder.py --eye-interval 600  # eye nudge every 10min\n"
               "  python rest_reminder.py --no-eye-check      # break popup only",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("-w", "--work-time", type=int, default=20 * 60,
                        help="work time per cycle, in seconds (default: 1200)")
    parser.add_argument("-b", "--break-time", type=int, default=20,
                        help="break time per cycle, in seconds (default: 20)")
    parser.add_argument("-c", "--cycles", type=int, default=30,
                        help="total number of cycles (default: 30)")
    parser.add_argument("-g", "--gentle", action="store_true",
                        help="use a Windows toast for the break reminder instead of "
                             "the topmost popup (falls back to the popup if unsupported)")
    parser.add_argument("--eye-check", dest="eye_check", action="store_true",
                        default=True, help="send the eye-comfort toast on the "
                                           "--eye-interval cadence (default: on)")
    parser.add_argument("--no-eye-check", dest="eye_check", action="store_false",
                        help="disable the eye-comfort toast")
    parser.add_argument("--eye-interval", type=int, default=300, metavar="SECONDS",
                        help="seconds between eye-comfort notifications during "
                             "work (default: 300, i.e. the 20-20-20 rule)")
    parser.add_argument("--eye-method", choices=("balloon", "toast"), default="balloon",
                        help="how to show the eye-comfort notification: "
                             "'balloon' uses the notification-area balloon, which "
                             "needs no app registration (default); 'toast' uses the "
                             "WinRT toast, which only renders if the sender is a "
                             "registered app")
    parser.add_argument("--eye-seconds", type=int, default=8, metavar="SECONDS",
                        help="how long the balloon stays on screen (default: 8; "
                             "Windows may use its own timeout)")
    parser.add_argument("--popup-timeout", type=int, default=30, metavar="SECONDS",
                        help="auto-close the break popup after SECONDS; 0 keeps it "
                             "open until dismissed (default: 30)")
    args = parser.parse_args()

    # One hidden root window is created for the whole session; every popup is a
    # Toplevel of it. Re-creating tk.Tk() per popup repeatedly destroys and
    # rebuilds the whole Tcl interpreter (30 times for the default run).
    root = tk.Tk()
    root.withdraw()
    root.title("Rest Reminder")

    try:
        for i in range(1, args.cycles + 1):
            print(f"\n=== Work Cycle {i}/{args.cycles} ===")
            print(f"Working... (next break in {args.work_time / 60:g} minutes)")
            run_work_period(args.work_time,
                            args.eye_interval if args.eye_check else 0,
                            args.eye_method, args.eye_seconds)

            message = (
                f"Work session complete! Please take a {args.break_time} second break.\n"
                "- Stretch your neck and shoulders\n"
                "- Look at something 20 feet away\n"
                "- Drink some water"
            )
            if args.gentle:
                ok, detail = notify(args.eye_method, message, "Health Reminder",
                                    seconds=args.eye_seconds)
                print(f"Break notification: {'ok' if ok else 'FAILED'} - {detail}")
            if not args.gentle or not ok:
                show_notification(root, message, timeout=args.popup_timeout)

            print(f"Taking break... ({args.break_time} seconds)")
            countdown(args.break_time, "Break countdown")

        print(f"\nDaily session complete! Finished {args.cycles} pomodoro cycles.")
        final = "Daily work session completed! Remember to stay active!"
        ok = False
        if args.gentle:
            ok, detail = notify(args.eye_method, final, "Health Reminder",
                                seconds=args.eye_seconds)
            print(f"Break notification: {'ok' if ok else 'FAILED'} - {detail}")
        if not ok:
            show_notification(root, final, timeout=args.popup_timeout)
    except KeyboardInterrupt:
        print("\nInterrupted by user.")
    finally:
        try:
            root.destroy()
        except tk.TclError:
            pass

    return 0


if __name__ == "__main__":
    sys.exit(main())
