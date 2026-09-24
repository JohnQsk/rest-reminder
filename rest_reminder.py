#!/usr/bin/env python3
"""Pomodoro-style rest reminder with a periodic eye-comfort check.

Cycles between work and break periods. When a work period ends, a topmost
popup reminds you to rest, and a small non-blocking notification slides into
the bottom-right corner asking how your eyes feel right now. A 1-second timer
re-asserts the topmost flag so the popup climbs back above all windows until
you click OK (same trick as the legacy PowerShell version: setting topmost is
not subject to Windows' foreground lock).

Usage:
    python rest_reminder.py                      # defaults: 20min work, 20s break, 30 cycles
    python rest_reminder.py -w 1500 -b 30 -c 10  # 25min work, 30s break, 10 cycles
    python rest_reminder.py -w 3 -b 2 -c 1       # quick test run
    python rest_reminder.py -g -w 3 -b 2 -c 1    # use a system notification instead
    python rest_reminder.py --eye-log eyes.csv   # also append answers to a CSV

Options:
    -w, --work-time   work time per cycle, in seconds (default: 1200)
    -b, --break-time  break time per cycle, in seconds (default: 20)
    -c, --cycles      total number of cycles (default: 30)
    -g, --gentle      ask for a Windows toast notification instead of the
                      focus-stealing popup (falls back to the popup if the
                      toast cannot be shown)
        --eye-check   show the bottom-right eye-comfort check every cycle
                      (default: on; use --no-eye-check to disable)
        --eye-log     append each answer to this CSV file
    -h, --help        show the built-in help message

Notes:
    - Platform: Windows. The topmost re-assertion trick relies on Windows'
      foreground lock and on Win32 window flags. The bottom-right corner
      placement also assumes a Windows-style taskbar.
    - Close the popup with the OK button or the Enter key. The popup cannot
      be hidden behind other windows while it is open.
    - The eye-comfort window is deliberately non-activating: it never steals
      focus, and it answers with one click or fades on its own.
    - Stop the script at any time with Ctrl+C.
    - Requires no third-party packages; uses tkinter from the standard library.
"""

import argparse
import csv
import datetime
import subprocess
import sys
import time
import tkinter as tk

POPUP_WIDTH = 420
POPUP_HEIGHT = 200

EYE_CHECK_WIDTH = 340
EYE_CHECK_HEIGHT = 190
EYE_CHECK_MARGIN = 16
EYE_CHECK_TIMEOUT_MS = 45_000

EYE_FEELINGS = (
    ("comfortable", "Comfortable"),
    ("dry", "Dry / gritty"),
    ("strained", "Strained / sore"),
    ("blurry", "Blurry"),
)


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


class EyeLog:
    """Append-only CSV recorder for eye-comfort answers."""

    def __init__(self, path):
        self.path = path
        self.ready = False
        if not path:
            return
        try:
            with open(path, "a", newline="", encoding="utf-8") as handle:
                csv.writer(handle).writerow(
                    ["timestamp", "cycle", "feeling", "feeling_label", "answer"]
                )
            self.ready = True
        except OSError as exc:
            print(f"Could not open eye log {path!r}: {exc}")

    def write(self, cycle, feeling, label, answer):
        if not self.ready:
            return
        try:
            with open(self.path, "a", newline="", encoding="utf-8") as handle:
                csv.writer(handle).writerow([
                    datetime.datetime.now().isoformat(timespec="seconds"),
                    cycle,
                    feeling,
                    label,
                    answer,
                ])
        except OSError as exc:
            print(f"Could not write to eye log {self.path!r}: {exc}")


def show_eye_check(root, cycle, eye_log):
    """Slide a non-blocking eye-comfort question into the bottom-right corner.

    The window never takes focus, answers with a single click, and disappears
    on its own after EYE_CHECK_TIMEOUT_MS so a forgotten window cannot pile up.
    """
    win = tk.Toplevel(root)
    win.title("Eye check")
    win.resizable(False, False)
    win.overrideredirect(True)
    win.attributes("-topmost", True)

    screen_w = win.winfo_screenwidth()
    screen_h = win.winfo_screenheight()
    x = screen_w - EYE_CHECK_WIDTH - EYE_CHECK_MARGIN
    y = screen_h - EYE_CHECK_HEIGHT - EYE_CHECK_MARGIN * 4  # clear the taskbar
    win.geometry(f"{EYE_CHECK_WIDTH}x{EYE_CHECK_HEIGHT}+{x}+{y}")

    frame = tk.Frame(win, borderwidth=1, relief="solid")
    frame.pack(fill="both", expand=True)

    header = tk.Label(frame, text=f"Cycle {cycle}: how do your eyes feel?",
                      font=("Segoe UI", 10, "bold"))
    header.pack(anchor="w", padx=10, pady=(8, 2))

    hint = tk.Label(frame, text="Blink, then look 20 feet away for 20 seconds.",
                    font=("Segoe UI", 8), fg="#444444")
    hint.pack(anchor="w", padx=10)

    def answer(feeling, label, text):
        eye_log.write(cycle, feeling, label, text)
        print(f"Eye check (cycle {cycle}): {text}")
        win.destroy()

    buttons = tk.Frame(frame)
    buttons.pack(fill="x", padx=8, pady=6)
    for feeling, label in EYE_FEELINGS:
        tk.Button(buttons, text=label, width=15,
                  command=lambda f=feeling, l=label: answer(f, l, l)
                  ).pack(side="top", fill="x", pady=1)

    tk.Button(frame, text="Ask me later", font=("Segoe UI", 8),
              command=lambda: answer("later", "Ask me later", "dismissed")
              ).pack(anchor="e", padx=10, pady=(0, 8))

    def close():
        if win.winfo_exists():
            win.destroy()

    win.protocol("WM_DELETE_WINDOW", close)
    win.after(EYE_CHECK_TIMEOUT_MS, close)
    win.lift()


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
        description="Pomodoro-style rest reminder with a topmost break popup "
                    "and a bottom-right eye-comfort check.",
        epilog="examples:\n"
               "  python rest_reminder.py                     # 20min work, 20s break, 30 cycles\n"
               "  python rest_reminder.py -w 1500 -b 30 -c 10 # 25min work, 30s break, 10 cycles\n"
               "  python rest_reminder.py -w 3 -b 2 -c 1      # quick test run\n"
               "  python rest_reminder.py -g -w 3 -b 2 -c 1   # gentle mode\n"
               "  python rest_reminder.py --eye-log eyes.csv  # record eye comfort",
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
    parser.add_argument("--eye-check", dest="eye_check", action="store_true",
                        default=True, help="show the bottom-right eye-comfort check "
                                           "every cycle (default: on)")
    parser.add_argument("--no-eye-check", dest="eye_check", action="store_false",
                        help="disable the eye-comfort check")
    parser.add_argument("--eye-log", metavar="PATH", default=None,
                        help="append eye-comfort answers to this CSV file")
    args = parser.parse_args()

    eye_log = EyeLog(args.eye_log)

    # One hidden root window is created for the whole session; every window is a
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

            if args.eye_check:
                # Collapse any unanswered corner window before the new one.
                for child in root.winfo_children():
                    if child.winfo_exists() and child.title() == "Eye check":
                        child.destroy()
                show_eye_check(root, i, eye_log)

            message = (
                f"Work session complete! Please take a {args.break_time} second break.\n"
                "- Stretch your neck and shoulders\n"
                "- Look at something 20 feet away\n"
                "- Drink some water"
            )
            root.update()  # let the corner window paint before the modal popup
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
