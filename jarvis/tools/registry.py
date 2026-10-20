import asyncio
import functools
from typing import Callable, Any, Dict, List
from jarvis.core.config import CONFIG

class ToolRegistry:
    def __init__(self):
        self.tools = {}

    def tool(self, name: str, description: str, tier: str = "CONFIRM"):
        def decorator(func: Callable):
            # Simplified schema generation from type hints
            schema = {
                "name": name,
                "description": description,
                "tier": tier,
                "parameters": {
                    "type": "object",
                    "properties": {
                        k: {"type": "string"} for k in func.__code__.co_varnames[1:]
                    }
                }
            }
            self.tools[name] = {"func": func, "schema": schema}
            return func
        return decorator

registry = ToolRegistry()
