"""Abstract interfaces for CCM components.

This module defines interfaces to avoid circular dependencies
between builder and project modules.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any


class ProfileBuilderInterface(ABC):
    """Interface for profile building operations."""

    @abstractmethod
    def build(self, profile_name: str) -> Path:
        """Build a profile and return the profile directory."""
        pass

    @abstractmethod
    def build_with_auto_fetch(
        self, profile_name: str, project_dir: Path
    ) -> tuple[Path, dict[str, Any]]:
        """Build profile with auto-fetch detection."""
        pass

    @abstractmethod
    def validate(self, profile_name: str) -> list[str]:
        """Validate a profile configuration."""
        pass

    @abstractmethod
    def list_profiles(self) -> list[str]:
        """List all available profiles."""
        pass

    @abstractmethod
    def show_profile(self, profile_name: str) -> dict[str, Any] | None:
        """Show profile details."""
        pass

    @abstractmethod
    def create_profile(
        self,
        name: str,
        description: str = "",
        extends: str | None = None,
        from_sources: dict | None = None,
    ) -> Any:
        """Create a new profile."""
        pass


class ProjectManagerInterface(ABC):
    """Interface for project management operations."""

    @abstractmethod
    def activate(self, profile_name: str) -> dict[str, Any]:
        """Activate a profile in the current project."""
        pass

    @abstractmethod
    def deactivate(self) -> bool:
        """Deactivate the current project's profile."""
        pass

    @abstractmethod
    def status(self) -> dict[str, Any]:
        """Get current project status."""
        pass

    @abstractmethod
    def refresh(self) -> dict[str, Any]:
        """Refresh project links after profile changes."""
        pass
