import os
import subprocess
from typing import Optional

from jarvis.core.config import CONFIG


class Vision:
    """Screen awareness.

    The configured vision model (meta-llama/llama-4-scout-17b-16e-instruct) is
    not served by Groq, so vision degrades to window-title only. The model id
    stays in config.yaml and can be pointed at a provider that serves it.
    """

    def __init__(self):
        self.cfg = CONFIG.get("settings", {}).get("llm", {})
        self.vision_model = self.cfg.get("vision_model")
        self.enabled = bool(self.cfg.get("vision_enabled", True))
        # Groq has no vision model in the free tier -> degrade.
        self.supported = False
        self.degraded_reason = "vision model not served by this provider"

    def active_window_title(self) -> str:
        """Title of the focused window (the cheap screen signal)."""
        script = ("Get-Process | Where-Object {$_.MainWindowTitle} | "
                  "Select-Object -First 1 -ExpandProperty MainWindowTitle")
        try:
            out = subprocess.run(
                ["powershell", "-NoProfile", "-Command", script],
                capture_output=True, text=True, timeout=8
            )
            return (out.stdout or "").strip().splitlines()[0] if out.stdout else ""
        except Exception:
            return ""

    def list_windows(self) -> str:
        script = ("Get-Process | Where-Object {$_.MainWindowTitle} | "
                  "Select-Object -ExpandProperty MainWindowTitle")
        try:
            out = subprocess.run(
                ["powershell", "-NoProfile", "-Command", script],
                capture_output=True, text=True, timeout=8
            )
            return (out.stdout or "").strip()
        except Exception:
            return ""

    def describe_screen(self) -> str:
        """Screen context. Degrades to window titles when no vision model."""
        title = self.active_window_title()
        if self.supported:
            return f"Active window: {title}"
        windows = self.list_windows()
        if windows:
            return f"Active window: {title}\nOpen windows: {windows}"
        return f"Active window: {title}" if title else "No screen context available."

    def capture_context(self) -> str:
        return self.describe_screen()


vision = Vision()
