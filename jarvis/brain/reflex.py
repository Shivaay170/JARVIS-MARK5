import re
from typing import Any, Dict, Optional, Tuple

from jarvis.core.config import CONFIG


class ReflexLayer:
    """Handles simple commands without an LLM call.

    Patterns come from config.yaml (`reflex_table`). Named capture groups in the
    pattern become keyword arguments for the tool, e.g.:

        "volume (\\d{1,3})"  ->  set_volume(level="50")
    """

    def __init__(self):
        self.table: Dict[str, str] = CONFIG.get("reflex_table", {
            r"what('s| is) the time": "get_time",
            r"what('s| is) the date": "get_date",
            r"\bbattery\b": "get_system_info",
            r"\block\b": "lock_system",
        })
        self._compiled = [(re.compile(p, re.I), a) for p, a in self.table.items()]

    def check(self, text: str) -> Optional[str]:
        found = self.match(text)
        return found[0] if found else None

    def match(self, text: str) -> Optional[Tuple[str, Dict[str, Any]]]:
        """Return (action, args) if the text matches a reflex pattern."""
        if not text:
            return None
        for pattern, action in self._compiled:
            m = pattern.search(text)
            if not m:
                continue
            groups = m.groupdict()
            args = {k: v for k, v in groups.items() if v is not None}
            return action, args
        return None


reflex = ReflexLayer()
