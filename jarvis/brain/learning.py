import asyncio
import time
from typing import List, Optional

from jarvis.memory.store import store
from jarvis.brain.llm import llm

# One profile rewrite per day at most.
PROFILE_REWRITE_INTERVAL = 24 * 3600
# Session-level fact extraction: after 2 minutes idle, one call for the session.
IDLE_EXTRACT_SECONDS = 120


class PatternLearner:
    """Pattern learning: app usage by hour, commands used, accepted/rejected suggestions.

    All writes are batched (see MemoryStore). The profile summary is rewritten
    at most once per day, using a single LLM call.
    """

    def __init__(self):
        self._session_transcript: List[str] = []
        self._last_activity = time.time()
        self._extracted = False
        self._profile_lock = asyncio.Lock()

    # ---------- activity ----------

    def note_command(self, text: str):
        self._session_transcript.append(text)
        self._last_activity = time.time()
        store.log_activity("command", (text or "")[:200])

    def note_app_usage(self, app_name: str):
        store.log_activity("app", app_name)

    def note_suggestion(self, accepted: bool, detail: str = ""):
        store.log_activity("suggestion", detail, accepted=1 if accepted else 0)

    # ---------- session fact extraction ----------

    def idle_for(self) -> float:
        return time.time() - self._last_activity

    async def maybe_extract_facts(self, force: bool = False) -> bool:
        """Extract durable facts once per session (after 2 min idle).

        One LLM call for the whole session, not per turn.
        """
        if self._extracted and not force:
            return False
        if not force and self.idle_for() < IDLE_EXTRACT_SECONDS:
            return False
        if not self._session_transcript:
            self._extracted = True
            return False

        transcript = "\n".join(self._session_transcript[-40:])

        prompt = (
            "Extract durable facts about the user from this conversation. "
            "Only include facts that stay true beyond this session "
            "(identity, preferences, ongoing projects, recurring habits). "
            "Skip anything transient.\n"
            'Respond as JSON: {"facts":[{"text":"...","category":"personal|preference|project"}]}\n\n'
            f"Conversation:\n{transcript}"
        )
        try:
            data = await llm.complete_json(prompt, role="fast")
        except Exception as e:
            print(f"Fact extraction error: {e}")
            return False
        if not data:
            return False
        facts = data.get("facts") if isinstance(data, dict) else None
        if not facts:
            return False
        store.add_facts(facts)
        # Only clear the transcript once the facts are safely stored.
        self._session_transcript.clear()
        self._extracted = True
        return True

    # ---------- profile rewrite (once per day) ----------

    async def maybe_rewrite_profile(self, force: bool = False) -> bool:
        """Rewrite the profile summary, at most once per day, one LLM call."""
        if self._profile_lock.locked():
            return False
        last = store.profile_updated_at()
        if not force and (time.time() - last) < PROFILE_REWRITE_INTERVAL:
            return False

        facts = store.all_facts(limit=200)
        prefs = store.get_preferences()
        stats = store.activity_stats()
        if not facts and not prefs:
            return False

        fact_lines = "\n".join(f"- {f['text']}" for f in facts[:80])
        pref_lines = "\n".join(f"- {k}: {v}" for k, v in prefs.items())
        hours = ", ".join(f"{h}h x{n}" for h, n in sorted(stats["by_hour"].items(), key=lambda x: -x[1])[:5])

        prompt = (
            "Rewrite the user profile summary from these notes. "
            "Max 300 tokens. Keep only durable, useful facts. No preamble.\n"
            f"FACTS:\n{fact_lines}\n\n"
            f"PREFERENCES:\n{pref_lines}\n\n"
            f"ACTIVE HOURS: {hours}"
        )
        try:
            summary = await llm.complete(prompt, role="fast", temperature=0.3)
        except Exception as e:
            print(f"Profile rewrite error: {e}")
            return False
        if not summary:
            return False
        store.set_profile_summary(summary)
        return True


learner = PatternLearner()
