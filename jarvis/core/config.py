import os
import yaml
from dotenv import load_dotenv

load_dotenv()

def load_config():
    with open("config.yaml", "r") as f:
        return yaml.safe_load(f)

CONFIG = load_config()
API_KEY = os.getenv("CLAUDE_API_KEY")
