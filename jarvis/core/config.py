import os
import yaml
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def path(*parts) -> str:
    return os.path.join(BASE_DIR, *parts)


def load_config():
    with open(path("config.yaml"), "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


CONFIG = load_config()
API_KEY = os.getenv("GROQ_API_KEY")

DATA_DIR = path("data")
DB_PATH = os.path.join(DATA_DIR, "jarvis.db")
VOICEPRINT_PATH = os.path.join(DATA_DIR, "voiceprint.npy")
VOICEPRINT_LOG = os.path.join(DATA_DIR, "voiceprint.log")
PROFILE_PATH = os.path.join(DATA_DIR, "profile.yaml")
USAGE_LOG = os.path.join(DATA_DIR, "usage.log")
ACTIONS_LOG = os.path.join(DATA_DIR, "actions.log")
MODELS_DIR = path("models")


def get_setting(section: str, key: str, default=None):
    return CONFIG.get("settings", {}).get(section, {}).get(key, default)
