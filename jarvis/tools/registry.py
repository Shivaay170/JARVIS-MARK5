import asyncio
import functools
from typing import Any, Callable, Dict, List, Optional

from jarvis.core.config import CONFIG


def _docstring_params(func: Callable) -> Dict[str, str]:
    """Parse `Args:` sections from a docstring into {param: description}."""
    import re
    doc = func.__doc__ or ""
    out: Dict[str, str] = {}
    section = re.split(r"^\s*(Args|Arguments|Parameters)\s*:\s*$", doc, flags=re.M)
    if len(section) < 3:
        return out
    body = section[2]
    for block in re.split(r"\n\s*\n", body):
        m = re.match(r"\s*(\w+)\s*(\([^)]*\))?\s*:\s*(.+)", block)
        if m:
            out[m.group(1)] = m.group(3).strip().split("\n")[0][:80]
    return out


def _param_schema(func: Callable) -> Dict[str, Any]:
    """Build a JSON schema from type hints, with short descriptions."""
    import inspect
    try:
        sig = inspect.signature(func)
    except (TypeError, ValueError):
        return {"type": "object", "properties": {}}

    type_map = {
        int: "integer", float: "number", bool: "boolean",
        str: "string", list: "array", dict: "object",
    }
    doc_params = _docstring_params(func)
    props: Dict[str, Any] = {}
    required: List[str] = []
    for name, p in sig.parameters.items():
        if name in ("self", "kwargs", "args"):
            continue
        jtype = type_map.get(p.annotation, "string")
        props[name] = {"type": jtype, "description": doc_params.get(name, name)}
        if p.default is inspect.Parameter.empty:
            required.append(name)
    schema: Dict[str, Any] = {"type": "object", "properties": props}
    if required:
        schema["required"] = required
    return schema


class ToolRegistry:
    def __init__(self):
        self.tools: Dict[str, Dict[str, Any]] = {}

    def tool(self, name: str, description: str, tier: str = "CONFIRM"):
        """Register a tool.

        Short descriptions matter: they are sent with every request and
        count against the prompt cache.
        """
        def decorator(func: Callable):
            schema = {
                "name": name,
                "description": description,
                "tier": tier,
                "parameters": _param_schema(func),
            }
            self.tools[name] = {"func": func, "schema": schema}
            return func
        return decorator

    def openai_schema(self) -> List[Dict[str, Any]]:
        """Tool schemas in OpenAI function-calling format."""
        out = []
        for t in self.tools.values():
            s = t["schema"]
            out.append({
                "type": "function",
                "function": {
                    "name": s["name"],
                    "description": s["description"],
                    "parameters": s["parameters"],
                },
            })
        return out

    def get(self, name: str) -> Optional[Dict[str, Any]]:
        return self.tools.get(name)


registry = ToolRegistry()


def load_builtin_tools():
    """Import the tool modules so the registry is populated on demand."""
    import importlib
    for mod in ("jarvis.tools.windows_tools", "jarvis.memory.memory_tools"):
        try:
            importlib.import_module(mod)
        except Exception as e:
            print(f"Tool module load failed ({mod}): {e}")


load_builtin_tools()
