# app/services/config_manager.py
from __future__ import annotations

import logging
import yaml
from pathlib import Path
from typing import Any, Dict

logger = logging.getLogger("avatar.config_manager")

CONFIG_PATH = Path(__file__).resolve().parent.parent.parent / "config" / "system.yaml"

_LOADED_CONFIG: Dict[str, Any] = {}

def get_config() -> Dict[str, Any]:
    """Retrieve the parsed system operating configuration."""
    global _LOADED_CONFIG
    if not _LOADED_CONFIG:
        if CONFIG_PATH.exists():
            try:
                content = CONFIG_PATH.read_text(encoding="utf-8")
                _LOADED_CONFIG = yaml.safe_load(content) or {}
                logger.info("Successfully loaded system config from %s", CONFIG_PATH)
            except Exception as e:
                logger.error("Failed to parse config file: %s", e)
                _LOADED_CONFIG = {}
        else:
            logger.warning("Config file not found at %s. Using default dictionary.", CONFIG_PATH)
            _LOADED_CONFIG = {}
    return _LOADED_CONFIG

def get_setting(key_path: str, default: Any = None) -> Any:
    """Get a configuration setting using a dot-separated path (e.g. 'system.project_name')."""
    cfg = get_config()
    parts = key_path.split(".")
    val = cfg
    for part in parts:
        if isinstance(val, dict) and part in val:
            val = val[part]
        else:
            return default
    return val
