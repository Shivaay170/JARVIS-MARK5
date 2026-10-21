import re
from typing import Optional, Tuple

from jarvis.memory.store import store
from jarvis.memory.memory_tools import load_profile

# Pattern -> handler. Matched before the LLM so these cost zero LLM calls.
_COMMANDS = [
    (re.compile(r"^\s*(?:what|who)\s+(?:do\s+you\s+know\s+about\s+me|know\s+about\s+me|"
                r"do\s+you\s+know\s+me|know\s+me|am\s+i)\b", re.I), "know_me"),
    (re.compile(r"^\s*forget\s+everything\b", re.I), "forget_all"),
    (re.compile(r"^\s*forget\s+(?:all\s+)?(?:the\s+)?(?:fact|fact\s+about|that|it)\s+"
                r"(?:that\s+)?(?:about\s+)?(.{2,})$", re.I), "forget_one"),
    (re.compile(r"^\s*forget\s+(.{2,})$", re.I), "forget_one"),
]


def match(text: str) -> Optional[Tuple[str, str]]:
    """Return (command, argument) for a memory command, or None."""
    if not text:
        return None
    for pattern, name in _COMMANDS:
        m = pattern.match(text)
        if m:
            arg = (m.group(1) if m.groups() else "").strip()
            return name, arg
    return None


def _know_me() -> str:
    facts = store.all_facts(limit=200)
    summary = store.get_profile_summary().strip()
    prefs = store.get_preferences()

    lines = []
    if summary:
        lines.append(summary)
    if facts:
        lines.append("Things I have noted:")
        lines.extend(f"- {f['text']}" for f in facts[:25])
    if prefs:
        lines.append("Preferences:")
        lines.extend(f"- {k}: {v}" for k, v in prefs.items())
    if not lines:
        return "I don't know anything about you yet, sir."
    return "\n".join(lines)


def _forget_one(arg: str) -> str:
    if not arg:
        return "Tell me what to forget, sir."
    removed = store.delete_fact(arg)
    if removed:
        return f"Forgot {removed} item(s), sir."
    return f"Nothing matched '{arg}', sir."


def _forget_all() -> str:
    # Learned memory only; data/profile.yaml (form-fill data) is kept.
    store.forget_everything()
    return "Forgotten, sir. I've cleared everything I had learned."


def run(name: str, arg: str) -> str:
    if name == "know_me":
        return _know_me()
    if name == "forget_one":
        return _forget_one(arg)
    if name == "forget_all":
        return _forget_all()
    return "I'm not sure I follow, sir."
