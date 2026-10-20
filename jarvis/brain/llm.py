import asyncio
import time
from typing import List, Dict
from jarvis.core.config import CONFIG, API_KEY
import anthropic # Example for Claude

class LLMClient:
    def __init__(self):
        self.client = anthropic.Anthropic(api_key=API_KEY)
        self.history = []
        self.persona = "Calm British butler. Calls user 'sir'. 1-2 short sentences. Dry wit. No 'as an AI'. No markdown."

    async def generate(self, prompt: str):
        self.history.append({"role": "user", "content": prompt})

        # Simplified streaming call
        response = self.client.messages.create(
            model=CONFIG['settings']['llm']['model'],
            max_tokens=150,
            system=self.persona,
            messages=self.history,
            stream=True
        )

        full_text = ""
        async for chunk in response:
            text = chunk.content[0].text
            full_text += text
            yield text

        self.history.append({"role": "assistant", "content": full_text})
        if len(self.history) > 10: self.history = self.history[-10:]

llm = LLMClient()
