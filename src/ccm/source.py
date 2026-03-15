"""Source management for CCM."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from git import Repo
from git.exc import GitCommandError

from ccm.config import Config, SourceConfig
from ccm.constants import INDEX_DIR, SOURCES_DIR
from ccm.indexer import Indexer


class SourceManager:
    """Manages source repositories."""

    def __init__(self, config: Config | None = None) -> None:
        self.config = config or Config.load()
        self.indexer = Indexer()

    def add(self, name: str, github: str, ref: str = "main") -> SourceConfig:
        """Add a new source.

        Args:
            name: Unique name for the source
            github: GitHub repo in format "owner/repo"
            ref: Git ref (branch, tag, or commit)

        Returns:
            The created SourceConfig

        Raises:
            ValueError: If source already exists
            GitCommandError: If clone fails
        """
        if self.config.get_source(name):
            raise ValueError(f"Source '{name}' already exists")

        source = SourceConfig(name=name, github=github, ref=ref)

        # Clone the repository
        self._clone(source)

        # Add to config
        self.config.add_source(source)

        # Generate index
        self.indexer.index_source(source)

        return source

    def remove(self, name: str) -> bool:
        """Remove a source.

        Args:
            name: Source name

        Returns:
            True if removed, False if not found
        """
        source = self.config.get_source(name)
        if not source:
            return False

        # Remove from config
        self.config.remove_source(name)

        # Remove cached files
        source_dir = SOURCES_DIR / name
        if source_dir.exists():
            import shutil

            shutil.rmtree(source_dir)

        # Remove index
        index_file = INDEX_DIR / f"{name}.json"
        if index_file.exists():
            index_file.unlink()

        return True

    def list(self) -> list[SourceConfig]:
        """List all configured sources."""
        return self.config.sources

    def show(self, name: str) -> dict[str, Any] | None:
        """Show source details including index contents."""
        source = self.config.get_source(name)
        if not source:
            return None

        index = self.indexer.load_index(name)
        if not index:
            return None

        return {
            "name": source.name,
            "github": source.github,
            "ref": source.ref,
            "commit": index.get("commit", "unknown"),
            "last_updated": index.get("last_updated", "unknown"),
            "contents": index.get("contents", {}),
        }

    def update(self, name: str) -> dict[str, Any]:
        """Update a source to latest version.

        Args:
            name: Source name

        Returns:
            Dict with update information including changes

        Raises:
            ValueError: If source not found
            GitCommandError: If update fails
        """
        source = self.config.get_source(name)
        if not source:
            raise ValueError(f"Source '{name}' not found")

        source_dir = SOURCES_DIR / name
        if not source_dir.exists():
            # Re-clone if missing
            self._clone(source)
            return {"updated": True, "changes": {"added": [], "modified": [], "removed": []}}

        # Get current commit
        old_index = self.indexer.load_index(name)
        old_commit = old_index.get("commit") if old_index else None

        # Pull latest
        repo = Repo(source_dir)
        origin = repo.remotes.origin

        try:
            origin.pull(source.ref)
        except GitCommandError as e:
            raise GitCommandError(f"Failed to pull {name}: {e}")

        # Get new commit
        new_commit = repo.head.commit.hexsha

        # Regenerate index
        self.indexer.index_source(source)
        new_index = self.indexer.load_index(name)

        # Calculate changes
        changes = self._calculate_changes(old_index, new_index)

        return {
            "updated": new_commit != old_commit,
            "old_commit": old_commit,
            "new_commit": new_commit,
            "changes": changes,
        }

    def _clone(self, source: SourceConfig) -> None:
        """Clone a source repository."""
        source_dir = SOURCES_DIR / source.name
        source_dir.mkdir(parents=True, exist_ok=True)

        url = f"https://github.com/{source.github}.git"

        try:
            # Try git clone first
            Repo.clone_from(url, source_dir, branch=source.ref, depth=1)
        except GitCommandError:
            # Fallback: try gh CLI
            import subprocess
            import shutil

            if shutil.which("gh"):
                try:
                    # Clean up first
                    if source_dir.exists():
                        shutil.rmtree(source_dir)
                    source_dir.mkdir(parents=True, exist_ok=True)

                    # Use gh repo clone
                    result = subprocess.run(
                        ["gh", "repo", "clone", source.github, str(source_dir), "--", "--depth=1"],
                        capture_output=True,
                        text=True,
                        check=True,
                    )
                except subprocess.CalledProcessError as e:
                    if source_dir.exists():
                        shutil.rmtree(source_dir)
                    raise GitCommandError(f"Failed to clone {source.github}: {e.stderr}")
            else:
                # Clean up on failure
                if source_dir.exists():
                    shutil.rmtree(source_dir)
                raise GitCommandError(f"Failed to clone {source.github} and gh CLI not available")

    def _calculate_changes(
        self, old_index: dict | None, new_index: dict | None
    ) -> dict[str, list[str]]:
        """Calculate changes between two index versions."""
        changes = {"added": [], "modified": [], "removed": []}

        if not old_index:
            # Everything is new
            for type_name, items in (new_index or {}).get("contents", {}).items():
                for name in items:
                    changes["added"].append(f"{type_name}/{name}")
            return changes

        if not new_index:
            # Everything removed
            for type_name, items in old_index.get("contents", {}).items():
                for name in items:
                    changes["removed"].append(f"{type_name}/{name}")
            return changes

        old_contents = old_index.get("contents", {})
        new_contents = new_index.get("contents", {})

        all_types = set(old_contents.keys()) | set(new_contents.keys())

        for type_name in all_types:
            old_items = old_contents.get(type_name, {})
            new_items = new_contents.get(type_name, {})

            # Added items
            for name in new_items:
                if name not in old_items:
                    changes["added"].append(f"{type_name}/{name}")
                elif new_items[name].get("hash") != old_items[name].get("hash"):
                    changes["modified"].append(f"{type_name}/{name}")

            # Removed items
            for name in old_items:
                if name not in new_items:
                    changes["removed"].append(f"{type_name}/{name}")

        return changes
