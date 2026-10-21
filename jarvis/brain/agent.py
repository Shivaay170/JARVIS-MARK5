import asyncio
import inspect
import json
import time
from typing import Any, Dict, List, Optional

from jarvis.brain.llm import llm
from jarvis.brain.learning import learner
from jarvis.tools.registry import registry
from jarvis.memory.store import store
from jarvis.core.bus import bus
from jarvis.core.config import ACTIONS_LOG

RATE_LIMIT_MESSAGE = "I'm rate limited, sir, one moment."


class Agent:
    def __init__(self):
        self.max_steps = 8
        self.history: List[Dict[str, Any]] = []

    async def run(self, prompt: str) -> str:
        """Run the tool-calling loop until the model produces a final answer."""
        learner.note_command(prompt)
        context = store.build_context(prompt)

        messages: List[Dict[str, Any]] = [{"role": "user", "content": prompt}]
        tools = registry.openai_schema()

        for step in range(self.max_steps):
            response = await self._get_llm_response(messages, context, tools)

            if response.get("type") == "rate_limited":
                return RATE_LIMIT_MESSAGE
            if response.get("type") == "error":
                return "I'm having a moment of silence, sir."

            tool_call = response.get("tool")
            if not tool_call:
                text = response.get("text", "").strip()
                if not text:
                    text = "At your service, sir."
                messages.append({"role": "assistant", "content": text})
                self.history = messages[-10:]
                return text

            name = tool_call.get("name", "")
            raw_args = tool_call.get("arguments") or "{}"
            try:
                args = json.loads(raw_args) if raw_args.strip() else {}
            except json.JSONDecodeError:
                args = {}
            if not isinstance(args, dict):
                args = {}

            tool_def = registry.get(name)
            if not tool_def:
                messages.append({"role": "assistant", "content": f"Error: unknown tool {name}."})
                continue

            # Drop empty-valued keys the model sometimes emits, and keep only
            # arguments the tool actually accepts.
            args = {k: v for k, v in args.items() if v not in (None, "")}
            valid = set(inspect.signature(tool_def["func"]).parameters.keys())
            args = {k: v for k, v in args.items() if k in valid}

            tier = tool_def["schema"]["tier"]
            if tier == "BLOCKED":
                result = "Action blocked for safety."
            elif tier == "CONFIRM":
                confirmed = await self._confirm_action(name, args)
                result = (await self._execute_tool(tool_def["func"], args)
                          if confirmed else "Action cancelled by user.")
            else:
                result = await self._execute_tool(tool_def["func"], args)

            messages.append({
                "role": "assistant",
                "content": "",
                "tool_calls": [{
                    "id": tool_call.get("id") or f"call_{step}",
                    "type": "function",
                    "function": {"name": name, "arguments": json.dumps(args)},
                }],
            })
            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.get("id") or f"call_{step}",
                "content": str(result),
            })

        return "I'm sorry, I couldn't complete this task within the step limit."

    async def _get_llm_response(self, messages, context, tools) -> Dict[str, Any]:
        """One LLM turn: stream text, capture the first tool call, log usage."""
        text_parts: List[str] = []
        tool_call: Optional[Dict[str, Any]] = None
        kind = "text"

        # Build the message list for the API: history (without the trailing
        # assistant/tool turns) + context + current turn.
        api_messages = self._api_messages(messages)

        async for event in llm.generate(
            "",
            role="fast",
            context=context,
            history=api_messages,
            tools=tools,
            temperature=0.7,
        ):
            etype = event.get("type")
            if etype == "text":
                text_parts.append(event.get("text", ""))
                if tool_call is None:
                    await bus.publish("response_delta", event.get("text", ""))
            elif etype == "tool":
                tool_call = event.get("tool")
                kind = "tool"
            elif etype == "rate_limited":
                return {"type": "rate_limited"}
            elif etype == "error":
                return {"type": "error", "message": event.get("message", "")}

        return {"type": kind, "text": "".join(text_parts), "tool": tool_call}

    def _api_messages(self, messages) -> List[Dict[str, Any]]:
        """Turn the agent's working list into API-shaped messages."""
        out: List[Dict[str, Any]] = []
        for m in messages:
            role = m.get("role")
            if role == "assistant" and m.get("tool_calls"):
                out.append(m)
            elif role == "tool":
                out.append(m)
            elif role == "user":
                out.append({"role": "user", "content": m.get("content", "")})
        return out

    async def _execute_tool(self, func, args):
        start = time.time()
        try:
            res = await asyncio.to_thread(func, **args)
        except TypeError as e:
            res = f"Tool call failed: {e}"
        except Exception as e:
            res = f"Tool error: {e}"
        if time.time() - start > 1.0:
            await bus.publish("speak", "On it, sir.")
        self._log_action(func, args, res)
        return res

    @staticmethod
    def _log_action(func, args, res):
        try:
            with open(ACTIONS_LOG, "a", encoding="utf-8") as f:
                f.write(f"{time.ctime()}: {func.__name__} with {args} -> {res}\n")
        except Exception:
            pass

    async def _confirm_action(self, name, args) -> bool:
        await bus.publish("confirm_request", {"tool": name, "args": args})
        # Waits for a confirm_response event; defaults to cancelled.
        try:
            return await asyncio.wait_for(self._await_confirm(), timeout=15.0)
        except asyncio.TimeoutError:
            return False

    async def _await_confirm(self) -> bool:
        loop = asyncio.get_event_loop()
        fut: asyncio.Future = loop.create_future()

        def _on_confirm(data):
            if not fut.done():
                loop.call_soon_threadsafe(fut.set_result, bool(data))

        bus.subscribe("confirm_response", _on_confirm)
        try:
            return await fut
        finally:
            bus.subscribers.get("confirm_response", []).remove(_on_confirm)


agent = Agent()
