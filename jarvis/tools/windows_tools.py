import os
import subprocess
import shutil
import psutil
import numpy as np
from jarvis.tools.registry import registry


@registry.tool("open_app", "Opens a Windows application", "SAFE")
def open_app(app_name: str):
    """Open an application by name.

    Args:
        app_name: Application name, e.g. notepad, chrome.
    """
    subprocess.Popen(f"start {app_name}", shell=True)
    return f"Opening {app_name}."


@registry.tool("get_system_info", "Gets battery, CPU and RAM usage", "SAFE")
def get_system_info():
    cpu = psutil.cpu_percent()
    ram = psutil.virtual_memory().percent
    battery = psutil.sensors_battery().percent if psutil.sensors_battery() else "N/A"
    return f"CPU: {cpu}%, RAM: {ram}%, Battery: {battery}%."


@registry.tool("set_volume", "Sets system volume", "SAFE")
def set_volume(level: int):
    """Set the system volume.

    Args:
        level: Volume level from 0 to 100.
    """
    level = max(0, min(100, int(level)))
    subprocess.run(f"nircmd setvolume {level * 65}", shell=True)
    return f"Volume set to {level}%."


@registry.tool("shutdown_system", "Shuts down the computer", "CONFIRM")
def shutdown_system():
    """Shut down the computer."""
    return "TRIGGER_SHUTDOWN"


@registry.tool("read_file", "Reads a file's content", "SAFE")
def read_file(path: str):
    """Read a text file.

    Args:
        path: Absolute path to the file.
    """
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f"<untrusted>{f.read()}</untrusted>"
    except Exception as e:
        return f"Error reading file: {e}"


@registry.tool("clipboard_set", "Sets the system clipboard", "SAFE")
def clipboard_set(text: str):
    """Copy text to the clipboard.

    Args:
        text: Text to copy.
    """
    subprocess.run("clip", input=text, text=True, capture_output=True)
    return "Clipboard updated."


@registry.tool("clipboard_get", "Gets the system clipboard", "SAFE")
def clipboard_get():
    result = subprocess.run("powershell Get-Clipboard", capture_output=True, text=True, shell=True)
    return f"<untrusted>{result.stdout}</untrusted>"


@registry.tool("get_time", "Gets the current time", "SAFE")
def get_time():
    import datetime
    return f"The current time is {datetime.datetime.now().strftime('%I:%M %p')}."


@registry.tool("get_date", "Gets the current date", "SAFE")
def get_date():
    import datetime
    return f"Today is {datetime.datetime.now().strftime('%A, %B %d, %Y')}."


@registry.tool("lock_system", "Locks the Windows workstation", "SAFE")
def lock_system():
    import ctypes
    ctypes.windll.user32.LockWorkStation()
    return "Workstation locked, sir."


@registry.tool("list_windows", "Lists open window titles", "SAFE")
def list_windows():
    """List the titles of open windows (screen awareness without a vision model)."""
    try:
        import win32gui
    except ImportError:
        return subprocess.run(
            "powershell -Command \"Get-Process | Where-Object {$_.MainWindowTitle} | "
            "Select-Object -ExpandProperty MainWindowTitle\"",
            capture_output=True, text=True, shell=True
        ).stdout.strip() or "No windows found."
    titles = []
    def _enum(hwnd, _):
        if win32gui.IsWindowVisible(hwnd):
            t = win32gui.GetWindowText(hwnd)
            if t:
                titles.append(t)
    win32gui.EnumWindows(_enum, None)
    return ", ".join(titles) if titles else "No windows found."
