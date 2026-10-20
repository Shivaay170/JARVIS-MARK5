import re
from rapidfuzz import process
from jarvis.core.config import CONFIG
from jarvis.core.bus import bus

class ReflexLayer:
    def __init__(self):
        # Defined in config.yaml: reflex_table: { "pattern": "action" }
        self.table = CONFIG.get('reflex_table', {
            r"time": "get_time",
            r"date": "get_date",
            r"battery": "get_system_info",
            r"lock": "lock_system"
        })

    def check(self, text: str):
        text = text.lower()
        for pattern, action in self.table.items():
            if re.search(pattern, text):
                return action
        return None

reflex = ReflexLayer()
