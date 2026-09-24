#!/usr/bin/env python3
"""Pomodoro-style rest reminder with a periodic eye-comfort nudge.

Cycles between work and break periods. When a work period ends, a topmost
popup reminds you to rest. During the work period, a native Windows
notification (the bottom-right toast) asks how your eyes feel on a fixed
cadence — every 5 minutes by default, independently of the cycle length.
A 1-second timer re-asserts the popup's topmost flag so it climbs back above
all windows until you click OK (same trick as the legacy PowerShell version:
setting topmost is not subject to Windows' foreground lock).

The eye-comfort nudge uses the real Windows toast API, not a hand-drawn window:
it needs no click, fades into the Action Center on its own, and is raised
through PowerShell's WinRT bindings so no third-party Python package is needed.

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
    -g, --gentle       use a Windows toast for the break reminder too, instead
                       of the focus-stealing popup (falls back to the popup if
                       the toast cannot be shown)
        --eye-check    send the eye-comfort toast on the --eye-interval
                       cadence (default: on; use --no-eye-check to disable)
        --eye-interval seconds between eye-comfort toasts during work
                       (default: 300, i.e. the 20-20-20 rule)
    -h, --help         show the built-in help message

Notes:
    - Platform: Windows. The topmost re-assertion trick relies on Windows'
      foreground lock and on Win32 window flags.
    - Both notifications are best-effort. Windows silently suppresses toasts
      while Focus Assist / Do Not Disturb is on, which this script cannot
      detect, so a hidden toast is reported as "not confirmed" rather than as
      an error.
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


# PowerShell snippet that raises a native Windows toast via the WinRT XML API.
#
# Arguments arrive through environment variables (RR_TITLE / RR_MESSAGE) rather
# than named parameters: `powershell -Command <script> -Title x` does NOT bind
# those to the snippet's param() block, and -File is unavailable because it is
# blocked by the default execution policy on many machines.
#
# Note: [System.Security.SecurityElement]::Escape() is called as a method, not
# through a script block. `$(& $esc $Title)` is a syntax error in PowerShell and
# would make every toast attempt fail silently.
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


def show_toast(message, title="Health Reminder"):
    """Raise a native Windows toast. Returns (ok, detail).

    A toast is exactly the notification the OS puts in the bottom-right corner:
    it requires no click and disappears by itself. Any failure (non-Windows, no
    WinRT, PowerShell unavailable) is reported instead of raised, so callers can
    fall back to the popup.

    A return of ok=True means PowerShell accepted the call. Windows gives no
    confirmation that a toast was actually painted: Focus Assist can swallow it
    silently, so detail reports that the result is unconfirmed.
    """
    if not sys.platform.startswith("win"):
        return False, "native toasts require Windows"

    env = dict(os.environ)
    env["RR_TITLE"] = title
    env["RR_MESSAGE"] = message
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive",
             "-WindowStyle", "Hidden", "-Command", _TOAST_PS],
            capture_output=True,
            text=True,
            timeout=30,
            env=env,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return False, f"could not run PowerShell: {exc}"

    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip().splitlines()
        return False, f"PowerShell exited {result.returncode}: {detail[0] if detail else 'no output'}"
    return True, "sent (acceptance unconfirmed; Focus Assist may suppress it)"


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


def run_work_period(seconds, eye_interval, activity="Work countdown"):
    """Count down a work period, raising an eye-comfort toast on a fixed cadence.

    `eye_interval` is independent of the cycle length: with the defaults the
    work period is 20 minutes and the toast fires every 5, 10 and 15 minutes.
    That is the point — the 20-20-20 rule is a 20-minute rule for the *eyes*,
    so it should not stretch just because the pomodoro got longer.
    """
    next_eye = eye_interval if eye_interval > 0 else None
    for sec in range(seconds, 0, -1):
        elapsed = seconds - sec
        print(f"\r{activity}: {sec:4d}s remaining", end="", flush=True)

        if next_eye is not None and elapsed >= next_eye:
            ok, detail = show_toast(
                "How do your eyes feel? Look 20 feet away for 20 seconds, "
                "and blink deliberately.",
                "Eye check",
            )
            if ok:
                print(f"\r  [eye check at {elapsed // 60}m{elapsed % 60:02d}s] "
                      f"{detail}")
            else:
                print(f"\r  [eye check FAILED] {detail}")
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
                        help="seconds between eye-comfort toasts during work "
                             "(default: 300, i.e. the 20-20-20 rule)")
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
            run_work_period(args.work_time, args.eye_interval if args.eye_check else 0)

            message = (
                f"Work session complete! Please take a {args.break_time} second break.\n"
                "- Stretch your neck and shoulders\n"
                "- Look at something 20 feet away\n"
                "- Drink some water"
            )
            if args.gentle:
                ok, detail = show_toast(message, "Health Reminder")
                print(f"Break notification: {'ok' if ok else 'failed'} - {detail}")
                if not ok:
                    print("Falling back to the topmost popup.")
            if not args.gentle or not ok:
                show_notification(root, message, timeout=args.popup_timeout)

            print(f"Taking break... ({args.break_time} seconds)")
            countdown(args.break_time, "Break countdown")

        print(f"\nDaily session complete! Finished {args.cycles} pomodoro cycles.")
        final = "Daily work session completed! Remember to stay active!"
        ok = False
        if args.gentle:
            ok, detail = show_toast(final, "Health Reminder")
            print(f"Break notification: {'ok' if ok else 'failed'} - {detail}")
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
