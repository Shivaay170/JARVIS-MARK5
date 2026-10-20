import asyncio
from collections import defaultdict
from typing import Any, Callable, Coroutine

class EventBus:
    def __init__(self):
        self.subscribers = defaultdict(list)

    def subscribe(self, event_type: str, callback: Callable[[Any], Coroutine]):
        self.subscribers[event_type].append(callback)

    async def publish(self, event_type: str, data: Any):
        if event_type in self.subscribers:
            await asyncio.gather(*(cb(data) for cb in self.subscribers[event_type]))

bus = EventBus()
