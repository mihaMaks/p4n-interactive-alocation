"""Access code management for location-based authentication.

Each location has unique codes that grant access to its meshes.
Maintainer codes grant full access across all locations.
No username/password needed — the code itself is the credential.
"""
import json
import os
import secrets
import random
from typing import Optional

VALID_ROLES = {"maintainer", "user"}
ANIMAL_NAMES = [
    "Clever Fox", "Brave Lion", "Wise Owl", "Happy Panda", "Swift Falcon", "Gentle Deer", "Bold Tiger", "Quiet Turtle", "Playful Otter", "Curious Cat", "Lively Rabbit", "Calm Bear", "Shy Hedgehog", "Nimble Squirrel", "Sunny Duck"
]

def get_random_animal():
    return random.choice(ANIMAL_NAMES)


class AccessCodeStore:
    """Reads and writes access codes from a JSON file."""

    def __init__(self, filepath: str):
        self._filepath = filepath
        self._bootstrap()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def verify(self, code: str) -> Optional[dict]:
        """Return role info dict if *code* is valid, else ``None``."""
        return self._read()["codes"].get(code)

    def create_code(
        self, role: str, location_id: str, description: str = ""
    ) -> str:
        """Create a new access code and return it."""
        if role not in VALID_ROLES:
            raise ValueError(f"Invalid role '{role}'. Must be one of {VALID_ROLES}")
        code = secrets.token_urlsafe(16)
        data = self._read()
        data["codes"][code] = {
            "role": role,
            "location_id": location_id,
            "description": description,
        }
        self._write(data)
        return code

    def revoke_code(self, code: str) -> bool:
        """Revoke an access code. Returns ``True`` if it existed."""
        data = self._read()
        if code not in data["codes"]:
            return False
        del data["codes"][code]
        self._write(data)
        return True

    def list_codes(self) -> dict:
        """Return all codes (maintainer-only operation)."""
        return self._read()["codes"]

    def assign_animal_name(self, code: str, device_id: str = None) -> str:
        """Assign a unique animal name per device."""
        data = self._read()
        entry = data["codes"].get(code)
        if not entry:
            return "Unknown Animal"

        # Maintainers keep a single name on the code itself
        if entry.get("role") == "maintainer":
            if not entry.get("animal_name"):
                entry["animal_name"] = get_random_animal()
                self._write(data)
            return entry["animal_name"]

        # Users get a name per device_id
        if device_id:
            devices = entry.setdefault("devices", {})
            if device_id not in devices:
                # Pick a name not already used by other devices on this code
                used = {d["animal_name"] for d in devices.values() if "animal_name" in d}
                available = [n for n in ANIMAL_NAMES if n not in used]
                name = random.choice(available) if available else get_random_animal()
                devices[device_id] = {"animal_name": name}
                self._write(data)
            return devices[device_id]["animal_name"]

        # Fallback: old behaviour if no device_id sent
        if not entry.get("animal_name"):
            entry["animal_name"] = get_random_animal()
            self._write(data)
        return entry.get("animal_name", "Unknown Animal")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _bootstrap(self):
        """Create the data file with an initial maintainer code on first run."""
        os.makedirs(os.path.dirname(self._filepath), exist_ok=True)
        if os.path.exists(self._filepath):
            return
        initial_code = secrets.token_urlsafe(16)
        data = {
            "codes": {
                initial_code: {
                    "role": "maintainer",
                    "location_id": "*",
                    "description": "Initial maintainer code (auto-generated)",
                }
            }
        }
        self._write(data)
        print(f"\n{'=' * 60}")
        print(f"  INITIAL MAINTAINER ACCESS CODE: {initial_code}")
        print(f"  Save this code! It will not be shown again.")
        print(f"{'=' * 60}\n")

    def _read(self) -> dict:
        with open(self._filepath, "r") as fh:
            return json.load(fh)

    def _write(self, data: dict):
        with open(self._filepath, "w") as fh:
            json.dump(data, fh, indent=2)
