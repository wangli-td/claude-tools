"""Configuration management for CCM."""

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from ccm.constants import CCM_DIR, CONFIG_FILE, SCHEMA_VERSION


class SourceConfig(BaseModel):
    """Configuration for a single source."""

    name: str
    github: str
    ref: str = "main"


class Settings(BaseModel):
    """Global settings."""

    auto_update: bool = False
    update_interval: str = "24h"


class Config(BaseModel):
    """Main configuration model."""

    version: str = SCHEMA_VERSION
    sources: list[SourceConfig] = Field(default_factory=list)
    settings: Settings = Field(default_factory=Settings)

    @classmethod
    def load(cls) -> "Config":
        """Load configuration from file."""
        if not CONFIG_FILE.exists():
            return cls()

        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        return cls(**data)

    def save(self) -> None:
        """Save configuration to file."""
        CCM_DIR.mkdir(parents=True, exist_ok=True)

        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(self.model_dump(), f, indent=2)

    def get_source(self, name: str) -> SourceConfig | None:
        """Get a source by name."""
        for source in self.sources:
            if source.name == name:
                return source
        return None

    def add_source(self, source: SourceConfig) -> None:
        """Add a new source."""
        if self.get_source(source.name):
            raise ValueError(f"Source '{source.name}' already exists")
        self.sources.append(source)
        self.save()

    def remove_source(self, name: str) -> bool:
        """Remove a source by name."""
        for i, source in enumerate(self.sources):
            if source.name == name:
                self.sources.pop(i)
                self.save()
                return True
        return False

    def check_version(self) -> bool:
        """Check if config version matches schema version."""
        return self.version == SCHEMA_VERSION
