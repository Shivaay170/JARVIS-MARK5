from openai import AsyncOpenAI
from jarvis.core.config import API_KEY, CONFIG

PROVIDER_BASE_URLS = {
    "groq": "https://api.groq.com/openai/v1",
}


def provider_base_url(name: str) -> str:
    return PROVIDER_BASE_URLS.get(name, PROVIDER_BASE_URLS["groq"])


def make_client() -> AsyncOpenAI:
    provider = CONFIG.get("settings", {}).get("llm", {}).get("provider", "groq")
    return AsyncOpenAI(api_key=API_KEY, base_url=provider_base_url(provider))


client = make_client()
