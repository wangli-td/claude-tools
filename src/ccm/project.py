"""Project binding for CCM."""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any

from ccm.constants import CLAUDE_DIR, PROJECT_CONFIG_FILE
from ccm.interfaces import ProfileBuilderInterface, ProjectManagerInterface


class ProjectManager(ProjectManagerInterface):
    """Manages project-level profile activation."""

    def __init__(self, project_dir: Path | None = None) -> None:
        self.project_dir = project_dir or Path.cwd()
        self.claude_dir = self.project_dir / CLAUDE_DIR
        self.project_config_file = self.project_dir / PROJECT_CONFIG_FILE

    def activate(self, profile_name: str) -> dict[str, Any]:
        """Activate a profile in the current project.

        Args:
            profile_name: Name of the profile to activate

        Returns:
            Dict with activation results including auto_fetch info

        Raises:
            ValueError: If profile not found or invalid
        """
        from ccm.builder import ProfileBuilder

        builder = ProfileBuilder()

        # Validate profile first
        errors = builder.validate(profile_name)
        if errors:
            raise ValueError(f"Profile validation failed: {errors[0]}")

        # Build profile with auto-fetch
        profile_dir, auto_fetch_result = builder.build_with_auto_fetch(
            profile_name, self.project_dir
        )

        # Write project config
        self.project_config_file.write_text(profile_name, encoding="utf-8")

        # Create/update .claude/ directory
        self._setup_claude_dir(profile_dir)

        return {
            "profile": profile_name,
            "profile_dir": profile_dir,
            "auto_fetch": auto_fetch_result,
        }

    def deactivate(self) -> bool:
        """Deactivate the current project's profile.

        Returns:
            True if deactivated, False if no profile was active
        """
        if not self.project_config_file.exists():
            return False

        # Remove .claude/ directory
        if self.claude_dir.exists():
            shutil.rmtree(self.claude_dir)

        # Remove project config
        self.project_config_file.unlink()

        return True

    def status(self) -> dict[str, Any]:
        """Get current project status.

        Returns:
            Dict with project status information
        """
        status = {
            "project_dir": str(self.project_dir),
            "active": False,
            "profile": None,
            "claude_dir_exists": self.claude_dir.exists(),
            "links": {},
        }

        if self.project_config_file.exists():
            profile_name = self.project_config_file.read_text(encoding="utf-8").strip()
            status["active"] = True
            status["profile"] = profile_name

            # Check links
            for item in ["agents", "skills", "commands", "rules"]:
                link_path = self.claude_dir / item
                if link_path.exists():
                    if link_path.is_symlink():
                        status["links"][item] = str(link_path.readlink())
                    else:
                        status["links"][item] = "(directory)"

            # Check CLAUDE.md
            claude_md = self.claude_dir / "CLAUDE.md"
            status["claude_md_exists"] = claude_md.exists()

        return status

    def refresh(self) -> dict[str, Any]:
        """Refresh project links after profile changes.

        Returns:
            Dict with refresh results
        """
        if not self.project_config_file.exists():
            raise ValueError("No profile activated in this project")

        profile_name = self.project_config_file.read_text(encoding="utf-8").strip()

        # Rebuild profile (lazy import to avoid circular dependency)
        from ccm.builder import ProfileBuilder
        builder = ProfileBuilder()
        profile_dir, auto_fetch_result = builder.build_with_auto_fetch(
            profile_name, self.project_dir
        )

        # Recreate links
        self._setup_claude_dir(profile_dir)

        return {
            "profile": profile_name,
            "profile_dir": profile_dir,
            "refreshed": True,
        }

    def _setup_claude_dir(self, profile_dir: Path) -> None:
        """Set up .claude/ directory with symlinks."""
        # Remove existing .claude/ if it exists
        if self.claude_dir.exists():
            shutil.rmtree(self.claude_dir)

        self.claude_dir.mkdir(parents=True, exist_ok=True)

        # Create symlinks for each type
        for item in ["agents", "skills", "commands", "rules"]:
            src = profile_dir / item
            dst = self.claude_dir / item

            if src.exists() and any(src.iterdir()):
                dst.symlink_to(src, target_is_directory=True)

        # Copy CLAUDE.md if exists
        src_claude_md = profile_dir / "CLAUDE.md"
        if src_claude_md.exists():
            shutil.copy2(src_claude_md, self.claude_dir / "CLAUDE.md")
        else:
            # Generate basic CLAUDE.md
            self._generate_claude_md()

    def _generate_claude_md(self) -> None:
        """Generate a basic CLAUDE.md for the project."""
        profile_name = self.project_config_file.read_text(encoding="utf-8").strip()
        project_name = self.project_dir.name

        content = f"""# {project_name}

> Profile: {profile_name}

## Project Overview

<!-- Describe what this project does -->

## Tech Stack

<!-- List languages, frameworks, tools -->

## Development Guidelines

<!-- Project-specific rules and conventions -->

---

*Generated by CCM*
"""

        (self.claude_dir / "CLAUDE.md").write_text(content, encoding="utf-8")
