import asyncio
from typing import Any, Dict, List
from jarvis.brain.llm import llm
from jarvis.tools.registry import registry
from jarvis.core.bus import bus
import time

class Agent:
    def __init__(self):
        self.max_steps = 8

    async def run(self, prompt: str):
        context = [{"role": "user", "content": prompt}]

        for step in range(self.max_steps):
            # Get response from LLM with tool schemas
            # (Actual LLM call would pass registry.tools as tools param)
            response = await self._get_llm_response(context)

            if not response.get("tool_call"):
                return response["text"]

            tool_name = response["tool_call"]["name"]
            args = response["tool_call"]["args"]

            tool_def = registry.tools.get(tool_name)
            if not tool_def:
                context.append({"role": "assistant", "content": f"Error: Tool {tool_name} not found."})
                continue

            tier = tool_def["schema"]["tier"]

            if tier == "BLOCKED":
                res = "Action blocked for safety."
            elif tier == "CONFIRM":
                # Emit event to UI for confirmation
                confirmed = await self._confirm_action(tool_name, args)
                if not confirmed:
                    res = "Action cancelled by user."
                else:
                    res = await self._execute_tool(tool_def["func"], args)
            else:
                res = await self._execute_tool(tool_def["func"], args)

            context.append({"role": "tool", "content": res})

        return "I'm sorry, I couldn't complete this task within the step limit."

    async def _execute_tool(self, func, args):
        start = time.time()
        # Run in thread to avoid blocking event loop
        res = await asyncio.to_thread(func, **args)
        if time.time() - start > 1.0:
            await bus.publish("speak", "On it, sir.")

        # Log action
        with open("data/actions.log", "a") as f:
            f.write(f"{time.ctime()}: {func.__name__} with {args} -> {res}\n")
        return res

    async def _confirm_action(self, name, args):
        await bus.publish("confirm_request", {"tool": name, "args": args})
        # Wait for confirmation event (simplified)
        return True

    async def _get_llm_response(self, context):
        # Mocking tool-use logic as the actual LLM SDK varies
        # In reality, this calls llm.generate() and parses the tool_use block
        return {"text": "Processing...", "tool_call": None}

agent = Agent()
