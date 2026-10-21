import os
import yaml

from jarvis.tools.registry import registry
from jarvis.core.config import PROFILE_PATH
from jarvis.memory.store import store

# Fields used to fill forms. The user writes these in data/profile.yaml.
PROFILE_FIELDS = [
    "full_name", "first_name", "last_name", "email", "phone", "address",
    "city", "state", "zip", "country", "dob", "company", "job_title",
    "linkedin", "github", "website",
]


def load_profile() -> dict:
    """Read data/profile.yaml (user-maintained). Returns {} when absent."""
    if not os.path.exists(PROFILE_PATH):
        return {}
    try:
        with open(PROFILE_PATH, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return data if isinstance(data, dict) else {}
    except Exception as e:
        print(f"Profile load error: {e}")
        return {}


def save_profile(data: dict):
    os.makedirs(os.path.dirname(PROFILE_PATH), exist_ok=True)
    with open(PROFILE_PATH, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, sort_keys=False, allow_unicode=True)


@registry.tool("get_profile_field", "Reads a personal detail from the user's profile", "SAFE")
def get_profile_field(field: str) -> str:
    """Get a stored personal detail.

    Args:
        field: Field name, e.g. full_name, email, phone, address, city, zip.
    """
    key = (field or "").strip().lower().replace(" ", "_")
    profile = load_profile()
    if key in profile and profile[key] not in (None, ""):
        return f"{key}: {profile[key]}"
    # Try the raw text of the file for anything the user wrote free-form.
    for k, v in profile.items():
        if key in str(k).lower():
            return f"{k}: {v}"
    if os.path.exists(PROFILE_PATH):
        with open(PROFILE_PATH, "r", encoding="utf-8") as f:
            body = f.read()
        for line in body.splitlines():
            if key in line.lower().replace(" ", "_"):
                return line.strip()
    return f"No profile field named '{field}'."


@registry.tool("remember", "Stores a durable fact about the user", "SAFE")
def remember(text: str) -> str:
    """Store a durable fact worth remembering.

    Args:
        text: The fact to remember.
    """
    if not (text or "").strip():
        return "Nothing to remember."
    store.add_fact(text.strip(), category="manual")
    return "Noted, sir."


@registry.tool("forget", "Deletes a remembered fact matching the given text", "SAFE")
def forget(text: str) -> str:
    """Delete a remembered fact.

    Args:
        text: Text identifying the fact to delete.
    """
    removed = store.delete_fact(text)
    if removed:
        return f"Forgot {removed} item(s), sir."
    return "Nothing matched that, sir."
