import asyncio
import os
import time
import json
from typing import Any, Dict, List, AsyncGenerator, Optional

from jarvis.core.config import CONFIG, DATA_DIR, USAGE_LOG
from jarvis.core.api import client

os.makedirs(DATA_DIR, exist_ok=True)


class _UsageLog:
    """Batched usage logging: flush to disk every N entries or every T seconds."""

    def __init__(self, file_path: str, batch_size: int = 20, flush_interval: float = 15.0):
        self.path = file_path
        self.batch_size = batch_size
        self.flush_interval = flush_interval
        self.buffer: List[str] = []
        self._last_flush = time.time()

    def add(self, line: str):
        stamp = time.strftime("%Y-%m-%d %H:%M:%S")
        self.buffer.append(f"{stamp} - {line}")
        if len(self.buffer) >= self.batch_size or (time.time() - self._last_flush) > self.flush_interval:
            self.flush()

    def flush(self):
        if not self.buffer:
            return
        payload = "\n".join(self.buffer) + "\n"
        self.buffer.clear()
        self._last_flush = time.time()
        try:
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(payload)
        except Exception as e:
            print(f"Usage log write error: {e}")


usage_log = _UsageLog(USAGE_LOG)


class LLMClient:
    """Groq-first LLM client.

    Roles map to models in config.yaml; no model names are hard-coded here.
    """

    def __init__(self):
        self.client = client
        self.persona = (
            "Calm British butler. Calls user 'sir'. 1-2 short sentences. "
            "Dry wit. No 'as an AI'. No markdown. "
            "Use the provided tools whenever they apply; do not guess their output."
        )

    # ---------- model / role resolution ----------

    def _llm_cfg(self) -> Dict[str, Any]:
        return CONFIG.get("settings", {}).get("llm", {})

    def model_for_role(self, role: str) -> str:
        cfg = self._llm_cfg()
        return cfg.get(f"{role}_model") or cfg.get("fast_model") or cfg.get("agent_model")

    def fallback_model_for_role(self, role: str) -> Optional[str]:
        """The other model, used when the primary is rate limited."""
        cfg = self._llm_cfg()
        primary = self.model_for_role(role)
        others = [m for m in (cfg.get("agent_model"), cfg.get("fast_model")) if m and m != primary]
        return others[0] if others else None

    def reasoning_effort_for_role(self, role: str) -> Optional[str]:
        cfg = self._llm_cfg()
        return cfg.get(f"{role}_reasoning_effort") or cfg.get("reasoning_effort", "low")

    # ---------- request construction ----------

    def _build_messages(self, system_prompt: str, context: Optional[str],
                        history: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Static system prompt first (prompt caching), changing context after."""
        messages: List[Dict[str, Any]] = [{"role": "system", "content": system_prompt}]
        if context:
            messages.append({"role": "system", "content": context})
        messages.extend(history)
        return messages

    def _request_kwargs(self, role: str, messages, tools, temperature: float, model: str):
        kwargs: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": True,
            "stream_options": {"include_usage": True},
            "temperature": temperature,
            # Suppress reasoning output: gpt-oss exposes it on a separate channel.
            "extra_body": {"include_reasoning": False},
        }
        effort = self.reasoning_effort_for_role(role)
        if effort:
            kwargs["reasoning_effort"] = effort
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"
        return kwargs

    # ---------- streaming ----------

    @staticmethod
    def _strip_reasoning(text: str) -> str:
        """Remove residual reasoning blocks if the provider leaks them."""
        if not text:
            return text
        for tag in ("<think>", "</think>", "<reasoning>", "</reasoning>",
                    "<analysis>", "</analysis>", "<|channel|>", "<|end|>"):
            text = text.replace(tag, "")
        return text

    @staticmethod
    def _delta_text(delta) -> str:
        """Content only. Reasoning never reaches the chunker, TTS or overlay."""
        content = getattr(delta, "content", None)
        if not content:
            return ""
        return LLMClient._strip_reasoning(content)

    @staticmethod
    def _delta_reasoning(delta) -> str:
        """Reasoning text lives on `delta.reasoning` (model_extra), channel=analysis."""
        extra = getattr(delta, "model_extra", None) or {}
        return extra.get("reasoning") or ""

    async def _stream_once(self, role: str, messages, tools, temperature: float, model: str):
        """One streaming attempt. Yields ('text', str) / ('tool', dict)."""
        kwargs = self._request_kwargs(role, messages, tools, temperature, model)
        stream = await self.client.chat.completions.create(**kwargs)

        tool_acc: Dict[int, Dict[str, Any]] = {}

        async for chunk in stream:
            usage = getattr(chunk, "usage", None)
            if usage and not chunk.choices:
                # The dedicated usage chunk (stream_options.include_usage).
                usage_log.add(self._usage_line(model, usage))
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta

            # Reasoning is read only so it can be discarded explicitly.
            self._delta_reasoning(delta)

            content = self._delta_text(delta)
            if content:
                yield ("text", content)

            for tc in (getattr(delta, "tool_calls", None) or []):
                idx = tc.index if getattr(tc, "index", None) is not None else 0
                slot = tool_acc.setdefault(idx, {"id": None, "name": "", "arguments": ""})
                if getattr(tc, "id", None):
                    slot["id"] = tc.id
                fn = getattr(tc, "function", None)
                if fn is not None:
                    if getattr(fn, "name", None):
                        slot["name"] = fn.name
                    if getattr(fn, "arguments", None):
                        slot["arguments"] += fn.arguments

        for idx in sorted(tool_acc):
            slot = tool_acc[idx]
            if slot["name"]:
                yield ("tool", slot)

    # ---------- error handling ----------

    @staticmethod
    def _is_rate_limit(err: Exception) -> bool:
        if getattr(err, "status_code", None) == 429:
            return True
        text = str(err).lower()
        return "429" in text or "rate_limit" in text or "rate limit" in text

    @staticmethod
    def _retry_after(err: Exception) -> float:
        resp = getattr(err, "response", None)
        headers = getattr(resp, "headers", None) or {}
        for key in ("retry-after", "x-ratelimit-reset-requests"):
            val = headers.get(key)
            if val is None:
                continue
            try:
                num = float(val)
            except (TypeError, ValueError):
                continue
            if num > 1e9:  # epoch timestamp
                return max(0.0, num - time.time())
            return max(0.0, min(num, 30.0))
        return 2.0

    @staticmethod
    def _is_malformed(err: Exception) -> bool:
        text = str(err).lower()
        return any(k in text for k in ("malformed", "invalid json", "json_decode",
                                       "tool arguments", "invalid_tool", "unterminated"))

    @staticmethod
    def _describe(err: Exception) -> str:
        """Human-readable error with the provider's response body when present."""
        parts = [f"{type(err).__name__}: {err}"]
        resp = getattr(err, "response", None)
        if resp is not None:
            try:
                body = resp.text
                if body:
                    parts.append(f"body={body[:400]}")
            except Exception:
                pass
        return " | ".join(parts)

    # ---------- public API ----------

    async def generate(
        self,
        prompt: str,
        role: str = "fast",
        context: Optional[str] = None,
        history: Optional[List[Dict[str, Any]]] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        temperature: float = 0.7,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Stream a completion.

        Yields dicts: {"type": "text"|"tool"|"error"|"rate_limited"}.
        On 429: honour retry-after, retry once, then fall back to the other model.
        On malformed tool call: retry once at temperature 0.
        """
        hist = list(history or [])
        if prompt:
            hist.append({"role": "user", "content": prompt})
        model = self.model_for_role(role)
        messages = self._build_messages(self.persona, context, hist)

        retried = False
        for _ in range(2):
            try:
                text_parts: List[str] = []
                async for kind, payload in self._stream_once(role, messages, tools, temperature, model):
                    if kind == "text":
                        text_parts.append(payload)
                        yield {"type": "text", "text": payload}
                    elif kind == "tool":
                        yield {"type": "tool", "tool": payload}
                return
            except Exception as e:
                if self._is_rate_limit(e):
                    if not retried:
                        retried = True
                        await asyncio.sleep(self._retry_after(e))
                        continue
                    break  # fall through to the fallback model
                if self._is_malformed(e) and not retried:
                    retried = True
                    temperature = 0.0  # retry once at temperature 0
                    continue
                print(f"LLM Error: {self._describe(e)}")
                yield {"type": "error", "message": self._describe(e)}
                return

        # Rate limited twice: fall back to the other model once.
        fallback = self.fallback_model_for_role(role)
        if fallback and fallback != model:
            try:
                async for kind, payload in self._stream_once(role, messages, tools, temperature, fallback):
                    if kind == "text":
                        yield {"type": "text", "text": payload}
                    elif kind == "tool":
                        yield {"type": "tool", "tool": payload}
                return
            except Exception as e:
                print(f"LLM fallback error: {e}")

        yield {"type": "rate_limited"}

    # ---------- helpers ----------

    async def complete(self, prompt: str, role: str = "fast", context: Optional[str] = None,
                       temperature: float = 0.7) -> str:
        """Non-streaming convenience wrapper returning plain text."""
        out = []
        async for event in self.generate(prompt, role=role, context=context, temperature=temperature):
            if event.get("type") == "text":
                out.append(event.get("text", ""))
        return self._strip_reasoning("".join(out)).strip()

    async def complete_json(self, prompt: str, role: str = "fast", context: Optional[str] = None,
                            temperature: float = 0.0) -> Optional[Any]:
        """Ask for a JSON object and parse it defensively."""
        model = self.model_for_role(role)
        system = ("You extract structured data. Respond with a single valid JSON "
                  "object and nothing else. No prose, no markdown fences.")
        messages = self._build_messages(system, context, [{"role": "user", "content": prompt}])
        kwargs = self._request_kwargs(
            role, messages, None, temperature, model
        )
        kwargs.pop("stream", None)
        kwargs.pop("stream_options", None)
        kwargs["response_format"] = {"type": "json_object"}
        try:
            resp = await self.client.chat.completions.create(**kwargs)
            usage_log.add(self._usage_line(model, resp.usage))
            raw = self._strip_reasoning(resp.choices[0].message.content or "").strip()
            return self._parse_json(raw)
        except Exception as e:
            print(f"LLM JSON error: {e}")
            return None

    @staticmethod
    def _parse_json(raw: str) -> Optional[Any]:
        """Parse JSON, tolerating markdown fences or surrounding prose."""
        if not raw:
            return None
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1] if "```" in raw[3:] else raw[3:]
            raw = raw.removeprefix("json").strip()
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            pass
        start = raw.find("{")
        end = raw.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(raw[start:end + 1])
            except json.JSONDecodeError:
                pass
        start = raw.find("[")
        end = raw.rfind("]")
        if start >= 0 and end > start:
            try:
                return json.loads(raw[start:end + 1])
            except json.JSONDecodeError:
                pass
        return None

    @staticmethod
    def _usage_line(model: str, usage) -> str:
        prompt_tokens = getattr(usage, "prompt_tokens", 0) or 0
        completion_tokens = getattr(usage, "completion_tokens", 0) or 0
        reasoning = getattr(getattr(usage, "completion_tokens_details", None), "reasoning_tokens", 0) or 0
        return (f"model={model} prompt={prompt_tokens} completion={completion_tokens} "
                f"reasoning={reasoning} total={(prompt_tokens or 0) + (completion_tokens or 0)}")


llm = LLMClient()
