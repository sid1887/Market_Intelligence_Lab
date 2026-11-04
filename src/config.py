"""
Market Intelligence Lab — Central Configuration Loader.

Enforces offline-first safeguards and fail-closed network policies.
"""
import json
import os
from typing import Any, Dict

_DEFAULT_SETTINGS_PATH = os.path.abspath(
    os.path.join(os.path.dirname(os.path.dirname(__file__)), "config", "settings.json")
)

def get_settings(path: str = _DEFAULT_SETTINGS_PATH) -> Dict[str, Any]:
    """Loads settings.json; fails closed to offline mode if file is missing or corrupted."""
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "offline_mode": True,
        "network_access_enabled": False,
        "database_path": "data/market_lab.db"
    }

def is_network_allowed(path: str = _DEFAULT_SETTINGS_PATH) -> bool:
    """
    Enforces strict fail-closed network access check.
    Both offline_mode must be False AND network_access_enabled must be True.
    """
    cfg = get_settings(path)
    if cfg.get("offline_mode", True) is True:
        return False
    if cfg.get("network_access_enabled", False) is not True:
        return False
    return True
