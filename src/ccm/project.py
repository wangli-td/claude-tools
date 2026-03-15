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

        Removes profile-specific resources but preserves local project resources.

        Returns:
            True if deactivated, False if no profile was active
        """
        if not self.project_config_file.exists():
            return False

        # Remove only profile-specific resources, preserve local resources
        if self.claude_dir.exists():
            self._cleanup_profile_resources()

            # Remove .claude/ directory only if empty (no local resources)
            if self._is_claude_dir_empty():
                shutil.rmtree(self.claude_dir)

        # Clean up any temp backup directories
        backup_dir = self.project_dir / ".ccm_backup_temp"
        if backup_dir.exists():
            shutil.rmtree(backup_dir)

        # Remove project config
        self.project_config_file.unlink()

        return True

    def _cleanup_profile_resources(self) -> None:
        """Remove profile-specific resources while preserving local ones.

        Only removes _profile symlinks. Preserves:
        - CLAUDE.md (user may have edited it)
        - All local skills/agents/commands/rules
        - Any other user-created files
        """
        # Remove _profile symlinks from each resource directory
        for item in ["agents", "skills", "commands", "rules"]:
            item_dir = self.claude_dir / item
            if not item_dir.exists():
                continue

            profile_link = item_dir / "_profile"
            if profile_link.exists() and profile_link.is_symlink():
                profile_link.unlink()

    def _is_claude_dir_empty(self) -> bool:
        """Check if .claude/ directory has no user-created content.

        Returns True only if directory is completely empty or has no
        meaningful content (only empty directories).
        """
        if not self.claude_dir.exists():
            return True

        for item in self.claude_dir.iterdir():
            if item.is_file():
                # Any file is considered user content
                return False
            if item.is_dir():
                # Check if resource directory has local content (not just _profile)
                for subitem in item.iterdir():
                    if subitem.name != "_profile" or not subitem.is_symlink():
                        return False
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

            # Check links and local resources
            for item in ["agents", "skills", "commands", "rules"]:
                item_path = self.claude_dir / item
                if item_path.exists():
                    profile_link = item_path / "_profile"

                    parts = []
                    if profile_link.exists() and profile_link.is_symlink():
                        parts.append(f"profile -> {profile_link.readlink()}")

                    # Count local items (excluding _profile)
                    local_items = [f for f in item_path.iterdir() if f.name != "_profile"]
                    if local_items:
                        parts.append(f"local ({len(local_items)} items)")

                    if parts:
                        status["links"][item] = " + ".join(parts)

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
        """Set up .claude/ directory with merged profile and local resources.

        Structure:
            .claude/
            ├── agents/
            │   ├── _profile/ -> symlink to profile/agents/
            │   └── <local agents...>   # project-specific agents (preserved)
            ├── skills/
            │   ├── _profile/ -> symlink to profile/skills/
            │   └── <local skills...>   # project-specific skills (preserved)
            ├── commands/
            │   ├── _profile/ -> symlink to profile/commands/
            │   └── <local commands...> # project-specific commands (preserved)
            └── rules/
                ├── _profile/ -> symlink to profile/rules/
                └── <local rules...>    # project-specific rules (preserved)

        Note: CLAUDE.md is not managed by CCM. Users should create it in the
        project root directory if needed.
        """
        # Backup existing local resources before removing .claude/
        local_backup = self._backup_local_resources()

        # Remove existing .claude/ if it exists
        if self.claude_dir.exists():
            shutil.rmtree(self.claude_dir)

        self.claude_dir.mkdir(parents=True, exist_ok=True)

        # Create merged structure for each type
        for item in ["agents", "skills", "commands", "rules"]:
            profile_src = profile_dir / item
            item_dir = self.claude_dir / item
            profile_link = item_dir / "_profile"

            # Create parent directory
            item_dir.mkdir(parents=True, exist_ok=True)

            # Create symlink to profile resources
            if profile_src.exists() and any(profile_src.iterdir()):
                profile_link.symlink_to(profile_src, target_is_directory=True)

            # Restore local resources from backup (directly in item_dir, not _local/)
            if item in local_backup:
                for backup_item in local_backup[item].iterdir():
                    dst = item_dir / backup_item.name
                    if backup_item.is_dir():
                        shutil.copytree(backup_item, dst)
                    else:
                        shutil.copy2(backup_item, dst)

        # Clean up backup
        if local_backup:
            shutil.rmtree(self.project_dir / ".ccm_backup_temp")

    def _backup_local_resources(self) -> dict[str, Path]:
        """Backup local resources before refreshing .claude/ directory.

        Returns:
            Dict mapping resource type to backup path
        """
        backup_dir = self.project_dir / ".ccm_backup_temp"
        backup: dict[str, Path] = {}

        if not self.claude_dir.exists():
            return backup

        for item in ["agents", "skills", "commands", "rules"]:
            item_dir = self.claude_dir / item
            if not item_dir.exists() or not item_dir.is_dir():
                continue

            backup_path = backup_dir / item
            backup_path.mkdir(parents=True, exist_ok=True)

            # Backup everything except _profile symlink
            for subitem in item_dir.iterdir():
                if subitem.name == "_profile" and subitem.is_symlink():
                    continue
                dst = backup_path / subitem.name
                if subitem.is_dir():
                    shutil.copytree(subitem, dst)
                else:
                    shutil.copy2(subitem, dst)

            if any(backup_path.iterdir()):
                backup[item] = backup_path

        return backup
