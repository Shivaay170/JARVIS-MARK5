import asyncio
import inspect
from collections import defaultdict
from typing import Any, Callable

class EventBus:
    def __init__(self):
        self.subscribers = defaultdict(list)

    def subscribe(self, event_type: str, callback: Callable):
        self.subscribers[event_type].append(callback)

    async def publish(self, event_type: str, data: Any):
        if event_type in self.subscribers:
            tasks = []
            for cb in self.subscribers[event_type]:
                try:
                    res = cb(data)
                    if inspect.isawaitable(res):
                        tasks.append(res)
                except Exception as e:
                    print(f"EventBus callback error on '{event_type}': {e}")
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)

bus = EventBus()
