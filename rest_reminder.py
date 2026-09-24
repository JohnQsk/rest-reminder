#!/usr/bin/env python3
"""Pomodoro-style rest reminder.

Cycles between work and break periods. When a work period ends, a
topmost popup reminds you to rest. A 1-second timer re-asserts the
topmost flag so the popup climbs back above all windows until you
click OK (same trick as the PowerShell version: setting topmost is
not subject to Windows' foreground lock).

Usage:
    python rest_reminder.py                      # defaults: 20min work, 20s break, 30 cycles
    python rest_reminder.py -w 1500 -b 30 -c 10  # 25min work, 30s break, 10 cycles
    python rest_reminder.py -w 3 -b 2 -c 1       # quick test run
    python rest_reminder.py -g -w 3 -b 2 -c 1    # use a system notification instead

Options:
    -w, --work-time   work time per cycle, in seconds (default: 1200)
    -b, --break-time  break time per cycle, in seconds (default: 20)
    -c, --cycles      total number of cycles (default: 30)
    -g, --gentle      ask for a Windows toast notification instead of the
                      focus-stealing popup (falls back to the popup if the
                      toast cannot be shown)
    -h, --help        show the built-in help message

Notes:
    - Platform: Windows. The topmost re-assertion trick relies on Windows'
      foreground lock and on Win32 window flags.
    - Close the popup with the OK button or the Enter key. The popup cannot
      be hidden behind other windows while it is open.
    - Stop the script at any time with Ctrl+C.
    - Requires no third-party packages; uses tkinter from the standard library.
"""

import argparse
import subprocess
import sys
import time
import tkinter as tk

POPUP_WIDTH = 420
POPUP_HEIGHT = 200


# PowerShell snippet that raises a native Windows toast via the WinRT XML
# API. Doing this through PowerShell keeps the Python side dependency-free
# while still using the bindings that actually work on Windows.
_TOAST_PS = r"""
param([string]$Title, [string]$Message)
$ErrorActionPreference = 'Stop'
$null = [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime]
$null = [Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime]
$esc = { param($s) [System.Security.SecurityElement]::Escape($s) }
$xml = New-Object Windows.Data.Xml.Dom.XmlDocument
$xml.LoadXml("<toast><visual><binding template='ToastGeneric'><text>$(& $esc $Title)</text><text>$(& $esc $Message)</text></binding></visual></toast>")
$toast = New-Object Windows.UI.Notifications.ToastNotification $xml
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('Rest Reminder').Show($toast)
"""


def _show_toast(message, title):
    """Try to raise a native Windows toast. Returns True on success.

    Shells out to PowerShell so no third-party Python package is needed.
    Any failure (non-Windows, no WinRT, PowerShell missing, ...) returns
    False and the caller falls back to the topmost popup.
    """
    if not sys.platform.startswith("win"):
        return False
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive",
             "-WindowStyle", "Hidden", "-Command", _TOAST_PS, "-Title", title,
             "-Message", message],
            capture_output=True,
            timeout=15,
        )
        return result.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def show_notification(root, message, title="Health Reminder"):
    """Show a topmost popup and block until the user dismisses it."""
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

    def close():
        win.destroy()

    ok = tk.Button(win, text="OK", width=10, command=close)
    ok.pack(pady=(0, 12))
    ok.focus_set()
    win.bind("<Return>", lambda _event: close())
    win.protocol("WM_DELETE_WINDOW", close)

    def reassert_topmost():
        if not win.winfo_exists():
            return
        # Toggling the flag forces SetWindowPos(HWND_TOPMOST) again,
        # pushing the dialog back to the top of the z-order.
        win.attributes("-topmost", False)
        win.attributes("-topmost", True)
        win.lift()
        win.after(1000, reassert_topmost)

    win.attributes("-topmost", True)
    win.lift()
    win.after(1000, reassert_topmost)

    win.wait_window()


def countdown(seconds, activity):
    for sec in range(seconds, 0, -1):
        print(f"\r{activity}: {sec:4d}s remaining", end="", flush=True)
        time.sleep(1)
    print()


def main():
    parser = argparse.ArgumentParser(
        description="Pomodoro-style rest reminder with a topmost break popup.",
        epilog="examples:\n"
               "  python rest_reminder.py                     # 20min work, 20s break, 30 cycles\n"
               "  python rest_reminder.py -w 1500 -b 30 -c 10 # 25min work, 30s break, 10 cycles\n"
               "  python rest_reminder.py -w 3 -b 2 -c 1      # quick test run\n"
               "  python rest_reminder.py -g -w 3 -b 2 -c 1   # gentle mode",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("-w", "--work-time", type=int, default=20 * 60,
                        help="work time per cycle, in seconds (default: 1200)")
    parser.add_argument("-b", "--break-time", type=int, default=20,
                        help="break time per cycle, in seconds (default: 20)")
    parser.add_argument("-c", "--cycles", type=int, default=30,
                        help="total number of cycles (default: 30)")
    parser.add_argument("-g", "--gentle", action="store_true",
                        help="request a Windows toast instead of the topmost popup "
                             "(falls back to the popup if unsupported)")
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
            countdown(args.work_time, "Work countdown")

            message = (
                f"Work session complete! Please take a {args.break_time} second break.\n"
                "- Stretch your neck and shoulders\n"
                "- Look at something 20 feet away\n"
                "- Drink some water"
            )
            if args.gentle and _show_toast(message, "Health Reminder"):
                print("Toast notification sent (gentle mode).")
            else:
                if args.gentle:
                    print("Gentle mode unavailable; showing the topmost popup instead.")
                show_notification(root, message)

            print(f"Taking break... ({args.break_time} seconds)")
            countdown(args.break_time, "Break countdown")

        print(f"\nDaily session complete! Finished {args.cycles} pomodoro cycles.")
        final = "Daily work session completed! Remember to stay active!"
        if args.gentle and _show_toast(final, "Health Reminder"):
            print("Toast notification sent (gentle mode).")
        else:
            show_notification(root, final)
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
