import os
import re
import sqlite3
import threading
import time
import json
from typing import Any, Dict, List, Optional

from jarvis.core.config import DATA_DIR, DB_PATH

os.makedirs(DATA_DIR, exist_ok=True)

SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;

CREATE TABLE IF NOT EXISTS facts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    text TEXT NOT NULL,
    category TEXT DEFAULT 'general',
    source TEXT DEFAULT 'conversation',
    created_at REAL,
    last_used REAL,
    use_count INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS preferences (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key TEXT UNIQUE,
    value TEXT,
    created_at REAL,
    updated_at REAL
);

CREATE TABLE IF NOT EXISTS summaries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT,
    text TEXT,
    created_at REAL
);

CREATE TABLE IF NOT EXISTS activity (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT,
    detail TEXT,
    hour INTEGER,
    day TEXT,
    accepted INTEGER DEFAULT 0,
    created_at REAL
);

CREATE TABLE IF NOT EXISTS profile (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    text TEXT,
    updated_at REAL
);

CREATE VIRTUAL TABLE IF NOT EXISTS facts_fts USING fts5(
    text, content='facts', content_rowid='id'
);

CREATE TRIGGER IF NOT EXISTS facts_ai AFTER INSERT ON facts BEGIN
    INSERT INTO facts_fts(rowid, text) VALUES (new.id, new.text);
END;
CREATE TRIGGER IF NOT EXISTS facts_ad AFTER DELETE ON facts BEGIN
    INSERT INTO facts_fts(facts_fts, rowid, text) VALUES('delete', old.id, old.text);
END;
CREATE TRIGGER IF NOT EXISTS facts_au AFTER UPDATE ON facts BEGIN
    INSERT INTO facts_fts(facts_fts, rowid, text) VALUES('delete', old.id, old.text);
    INSERT INTO facts_fts(rowid, text) VALUES (new.id, new.text);
END;
"""


def _tokenize(text: str) -> List[str]:
    return [t for t in re.findall(r"[a-z0-9']+", (text or "").lower()) if len(t) > 2]


class MemoryStore:
    """SQLite WAL + FTS5 store for durable facts, preferences and activity.

    Writes are batched; reads are synchronous.
    """

    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self._lock = threading.RLock()
        self._pending: List[tuple] = []
        self._last_flush = time.time()
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.executescript(SCHEMA)
            self._conn.commit()
        self._stop = threading.Event()
        self._flusher = threading.Thread(target=self._flush_loop, daemon=True)
        self._flusher.start()

    def _flush_loop(self):
        """Background flusher: keeps the WAL small and writes batched."""
        while not self._stop.wait(5.0):
            try:
                self.flush()
            except Exception:
                pass

    # ---------- batched writes ----------

    def _queue(self, sql: str, params: tuple):
        with self._lock:
            self._pending.append((sql, params))
            if len(self._pending) >= 20 or (time.time() - self._last_flush) > 5.0:
                self.flush()

    def flush(self):
        with self._lock:
            if not self._pending:
                self._last_flush = time.time()
                return
            batch, self._pending = self._pending, []
            # Group by statement so executemany sees one SQL string per group.
            grouped: Dict[str, List[tuple]] = {}
            for sql, params in batch:
                grouped.setdefault(sql, []).append(params)
            try:
                for sql, rows in grouped.items():
                    self._conn.executemany(sql, rows)
                self._conn.commit()
            except Exception as e:
                print(f"Memory flush error: {e}")
            self._last_flush = time.time()

    def _execute(self, sql: str, params: tuple = ()):
        with self._lock:
            cur = self._conn.execute(sql, params)
            self._conn.commit()
            return cur

    # ---------- facts ----------

    def add_fact(self, text: str, category: str = "general", source: str = "conversation") -> int:
        text = (text or "").strip()
        if not text:
            return 0
        now = time.time()
        cur = self._execute(
            "INSERT INTO facts(text, category, source, created_at) VALUES (?,?,?,?)",
            (text, category, source, now),
        )
        return cur.lastrowid

    def add_facts(self, items: List[Dict[str, Any]]):
        """Batched insert of extracted facts."""
        now = time.time()
        rows = [
            (i.get("text", "").strip(), i.get("category", "general"),
             i.get("source", "conversation"), now)
            for i in items if (i.get("text") or "").strip()
        ]
        if not rows:
            return
        with self._lock:
            self._conn.executemany(
                "INSERT INTO facts(text, category, source, created_at) VALUES (?,?,?,?)", rows
            )
            self._conn.commit()

    def delete_fact(self, needle: str) -> int:
        """Delete facts matching a substring or FTS query. Returns count removed."""
        needle = (needle or "").strip()
        if not needle:
            return 0
        with self._lock:
            cur = self._conn.execute(
                "SELECT id, text FROM facts WHERE lower(text) LIKE ?", (f"%{needle.lower()}%",)
            )
            rows = cur.fetchall()
            for r in rows:
                self._conn.execute("DELETE FROM facts WHERE id = ?", (r["id"],))
            self._conn.commit()
        return len(rows)

    def search_facts(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """FTS5 search with a LIKE fallback for partial/short queries."""
        query = (query or "").strip()
        if not query:
            return []
        tokens = _tokenize(query)
        out: List[Dict[str, Any]] = []

        if tokens:
            match = " OR ".join(f'"{t}"' for t in tokens)
            try:
                with self._lock:
                    cur = self._conn.execute(
                        "SELECT f.id, f.text, f.category, f.source, f.created_at, f.use_count "
                        "FROM facts_fts JOIN facts f ON f.id = facts_fts.rowid "
                        "WHERE facts_fts MATCH ? ORDER BY rank LIMIT ?",
                        (match, limit),
                    )
                    out = [dict(r) for r in cur.fetchall()]
            except sqlite3.OperationalError:
                out = []

        if len(out) < limit:
            like = f"%{query.lower()}%"
            with self._lock:
                cur = self._conn.execute(
                    "SELECT id, text, category, source, created_at, use_count "
                    "FROM facts WHERE lower(text) LIKE ? ORDER BY created_at DESC LIMIT ?",
                    (like, limit - len(out)),
                )
                seen = {f["id"] for f in out}
                for r in cur.fetchall():
                    if r["id"] not in seen:
                        out.append(dict(r))

        for f in out:
            f["score"] = self._score(query, f["text"])
        out.sort(key=lambda f: f["score"], reverse=True)
        return out[:limit]

    @staticmethod
    def _score(query: str, text: str) -> float:
        q = set(_tokenize(query))
        t = set(_tokenize(text))
        if not q:
            return 0.0
        return len(q & t) / len(q)

    def all_facts(self, limit: int = 500) -> List[Dict[str, Any]]:
        with self._lock:
            cur = self._conn.execute(
                "SELECT id, text, category, source, created_at, use_count "
                "FROM facts ORDER BY created_at DESC LIMIT ?", (limit,)
            )
            return [dict(r) for r in cur.fetchall()]

    # ---------- preferences ----------

    def set_preference(self, key: str, value: str):
        now = time.time()
        with self._lock:
            self._conn.execute(
                "INSERT INTO preferences(key, value, created_at, updated_at) VALUES (?,?,?,?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
                (key, value, now, now),
            )
            self._conn.commit()

    def get_preferences(self) -> Dict[str, str]:
        with self._lock:
            cur = self._conn.execute("SELECT key, value FROM preferences")
            return {r["key"]: r["value"] for r in cur.fetchall()}

    # ---------- summaries ----------

    def add_summary(self, session_id: str, text: str):
        if not (text or "").strip():
            return
        self._queue("INSERT INTO summaries(session_id, text, created_at) VALUES (?,?,?)",
                    (session_id, text, time.time()))

    def recent_summaries(self, limit: int = 5) -> List[Dict[str, Any]]:
        with self._lock:
            cur = self._conn.execute(
                "SELECT id, session_id, text, created_at FROM summaries "
                "ORDER BY created_at DESC LIMIT ?", (limit,)
            )
            return [dict(r) for r in cur.fetchall()]

    # ---------- activity (pattern learning) ----------

    def log_activity(self, kind: str, detail: str = "", accepted: int = 0):
        now = time.time()
        self._queue(
            "INSERT INTO activity(kind, detail, hour, day, accepted, created_at) VALUES (?,?,?,?,?,?)",
            (kind, detail, time.localtime(now).tm_hour, time.strftime("%Y-%m-%d", time.localtime(now)),
             accepted, now),
        )

    def activity_stats(self) -> Dict[str, Any]:
        with self._lock:
            cur = self._conn.execute(
                "SELECT hour, COUNT(*) AS n FROM activity GROUP BY hour ORDER BY n DESC LIMIT 12"
            )
            by_hour = {r["hour"]: r["n"] for r in cur.fetchall()}
            cur = self._conn.execute(
                "SELECT kind, COUNT(*) AS n FROM activity GROUP BY kind ORDER BY n DESC LIMIT 20"
            )
            by_kind = {r["kind"]: r["n"] for r in cur.fetchall()}
            cur = self._conn.execute(
                "SELECT COUNT(*) AS n FROM activity WHERE accepted = 1"
            )
            accepted = cur.fetchone()["n"]
            cur = self._conn.execute("SELECT COUNT(*) AS n FROM activity")
            total = cur.fetchone()["n"]
        return {"by_hour": by_hour, "by_kind": by_kind,
                "accepted": accepted, "total": total}

    # ---------- profile summary ----------

    def set_profile_summary(self, text: str):
        with self._lock:
            self._conn.execute("DELETE FROM profile")
            self._conn.execute(
                "INSERT INTO profile(text, updated_at) VALUES (?,?)", (text, time.time())
            )
            self._conn.commit()

    def get_profile_summary(self) -> str:
        with self._lock:
            cur = self._conn.execute(
                "SELECT text FROM profile ORDER BY updated_at DESC LIMIT 1"
            )
            row = cur.fetchone()
        return (row["text"] if row else "") or ""

    def profile_updated_at(self) -> float:
        with self._lock:
            cur = self._conn.execute("SELECT MAX(updated_at) AS t FROM profile")
            row = cur.fetchone()
        return (row["t"] if row and row["t"] else 0.0) or 0.0

    # ---------- bulk forget ----------

    def forget_everything(self):
        """Wipe learned memory. Does NOT touch data/profile.yaml (form-fill data)."""
        with self._lock:
            for table in ("facts", "preferences", "summaries", "activity", "profile"):
                self._conn.execute(f"DELETE FROM {table}")
            try:
                self._conn.execute("INSERT INTO facts_fts(facts_fts) VALUES('rebuild')")
            except sqlite3.OperationalError:
                pass
            self._conn.commit()
        self._pending.clear()

    # ---------- context building ----------

    def build_context(self, query: str = "", max_chars: int = 1200) -> str:
        """Profile summary (<=300 tokens) + top-5 FTS5 hits, placed after the system prompt."""
        parts: List[str] = []
        summary = self.get_profile_summary().strip()
        if summary:
            # ~300 tokens ~= 1200 chars.
            parts.append(f"PROFILE: {summary[:1200]}")

        if query:
            hits = self.search_facts(query, limit=5)
            if not hits:
                # No keyword overlap: fall back to the most recent facts.
                hits = self.all_facts(limit=3)
            if hits:
                lines = "\n".join(f"- {h['text']}" for h in hits)
                parts.append(f"RELEVANT MEMORY:\n{lines}")

        ctx = "\n\n".join(parts)
        return ctx[:max_chars] if ctx else ""

    def close(self):
        self._stop.set()
        self.flush()
        with self._lock:
            self._conn.close()


store = MemoryStore()
