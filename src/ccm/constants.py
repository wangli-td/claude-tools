"""Constants for CCM."""

import os
from pathlib import Path

# Version
VERSION = "0.2.0"
SCHEMA_VERSION = "0.2.0"

# Directories
HOME_DIR = Path.home()
CCM_DIR = HOME_DIR / ".ccm"
SOURCES_DIR = CCM_DIR / "sources"
INDEX_DIR = CCM_DIR / "index"
PROFILES_DIR = CCM_DIR / "profiles"
LOGS_DIR = CCM_DIR / "logs"

# Config files
CONFIG_FILE = CCM_DIR / "config.json"

# Project files
PROJECT_CONFIG_FILE = ".ccm"
CLAUDE_DIR = ".claude"

# Source types
SOURCE_TYPES = ["agents", "skills", "commands", "rules"]

# Default settings
DEFAULT_SETTINGS = {
    "auto_update": False,
    "update_interval": "24h",
}