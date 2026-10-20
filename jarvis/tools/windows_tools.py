import os
import subprocess
import shutil
import psutil
import numpy as np
from jarvis.tools.registry import registry

@registry.tool("open_app", "Opens a Windows application by name", "SAFE")
def open_app(app_name: str):
    subprocess.Popen(f"start {app_name}", shell=True)
    return f"Opening {app_name}."

@registry.tool("get_system_info", "Gets battery, CPU, and RAM usage", "SAFE")
def get_system_info():
    cpu = psutil.cpu_percent()
    ram = psutil.virtual_memory().percent
    battery = psutil.sensors_battery().percent if psutil.sensors_battery() else "N/A"
    return f"CPU: {cpu}%, RAM: {ram}%, Battery: {battery}%."

@registry.tool("set_volume", "Sets system volume (0-100)", "SAFE")
def set_volume(level: str):
    # Uses nircmd or similar (assumed in path)
    subprocess.run(f"nircmd setvolume {int(level) * 65}", shell=True)
    return f"Volume set to {level}%."

@registry.tool("shutdown_system", "Shuts down the computer", "CONFIRM")
def shutdown_system():
    # This will be handled by the agent for the countdown
    return "TRIGGER_SHUTDOWN"

@registry.tool("read_file", "Reads a file's content", "SAFE")
def read_file(path: str):
    try:
        with open(path, 'r') as f:
            return f"<untrusted>{f.read()}</untrusted>"
    except Exception as e:
        return f"Error reading file: {e}"

@registry.tool("clipboard_set", "Sets the system clipboard", "SAFE")
def clipboard_set(text: str):
    subprocess.run(f'echo {text} | clip', shell=True)
    return "Clipboard updated."

@registry.tool("clipboard_get", "Gets the system clipboard", "SAFE")
def clipboard_get():
    result = subprocess.run("powershell Get-Clipboard", capture_output=True, text=True, shell=True)
    return f"<untrusted>{result.stdout}</untrusted>"
