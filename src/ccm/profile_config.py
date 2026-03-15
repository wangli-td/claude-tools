"""Profile configuration models for CCM."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class AutoFetchDetect(BaseModel):
    """Auto-fetch detection rule."""

    file: str
    source: str
    skills: list[str] = Field(default_factory=list)


class AutoFetchConfig(BaseModel):
    """Auto-fetch configuration."""

    detect: list[AutoFetchDetect] = Field(default_factory=list)
    default: dict[str, Any] = Field(default_factory=dict)


class SourceSelection(BaseModel):
    """Resource selection from a source."""

    agents: list[str] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    commands: list[str] = Field(default_factory=list)
    rules: list[str] = Field(default_factory=list)


class ProfileConfig(BaseModel):
    """Profile configuration model."""

    model_config = {"populate_by_name": True}

    name: str
    description: str = ""
    extends: str | list[str] | None = None
    auto_fetch: AutoFetchConfig | None = None
    from_sources: dict[str, SourceSelection] = Field(default_factory=dict, alias="from")

    @classmethod
    def load(cls, name: str, profiles_dir: Path) -> ProfileConfig | None:
        """Load profile from file."""
        profile_file = profiles_dir / name / "profile.json"
        if not profile_file.exists():
            # Try loading from raw config
            raw_file = profiles_dir / f"{name}.json"
            if raw_file.exists():
                with open(raw_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                return cls(**data)
            return None

        with open(profile_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        return cls(**data)

    def save(self, profiles_dir: Path) -> None:
        """Save profile configuration."""
        profile_dir = profiles_dir / self.name
        profile_dir.mkdir(parents=True, exist_ok=True)

        profile_file = profile_dir / "profile.json"
        with open(profile_file, "w", encoding="utf-8") as f:
            # Use alias for 'from' field
            json.dump(self.model_dump(by_alias=True), f, indent=2)

    def get_all_sources(self) -> list[str]:
        """Get all source names referenced in this profile."""
        sources = set(self.from_sources.keys())

        if self.auto_fetch:
            for detect in self.auto_fetch.detect:
                sources.add(detect.source)
            if self.auto_fetch.default:
                default_source = self.auto_fetch.default.get("source")
                if default_source:
                    sources.add(default_source)

        return list(sources)


from pathlib import Path
import json
