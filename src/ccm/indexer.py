"""Indexer for source repositories."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from ccm.config import SourceConfig
from ccm.constants import INDEX_DIR, SOURCE_TYPES, SOURCES_DIR


class Indexer:
    """Indexes source repository contents."""

    def __init__(self) -> None:
        INDEX_DIR.mkdir(parents=True, exist_ok=True)

    def index_source(self, source: SourceConfig) -> dict[str, Any]:
        """Generate index for a source.

        Args:
            source: Source configuration

        Returns:
            Index dictionary
        """
        source_dir = SOURCES_DIR / source.name
        if not source_dir.exists():
            raise ValueError(f"Source directory not found: {source_dir}")

        # Get git commit
        try:
            from git import Repo

            repo = Repo(source_dir)
            commit = repo.head.commit.hexsha
        except Exception:
            commit = "unknown"

        # Scan contents
        contents: dict[str, dict[str, dict[str, str]]] = {}

        for type_name in SOURCE_TYPES:
            type_dir = source_dir / type_name
            if not type_dir.exists():
                continue

            contents[type_name] = {}

            for item_path in type_dir.rglob("*.md"):
                # Calculate relative path from type directory
                rel_path = item_path.relative_to(type_dir)
                # Name is path without extension
                name = str(rel_path.with_suffix(""))
                # Hash for change detection
                content_hash = self._hash_file(item_path)

                contents[type_name][name] = {
                    "path": str(type_name / rel_path),
                    "hash": content_hash,
                }

        # Build index
        index = {
            "source": source.name,
            "github": source.github,
            "ref": source.ref,
            "commit": commit,
            "last_updated": self._now(),
            "contents": contents,
        }

        # Save index
        self._save_index(source.name, index)

        return index

    def load_index(self, source_name: str) -> dict[str, Any] | None:
        """Load index for a source.

        Args:
            source_name: Source name

        Returns:
            Index dictionary or None if not found
        """
        index_file = INDEX_DIR / f"{source_name}.json"
        if not index_file.exists():
            return None

        with open(index_file, "r", encoding="utf-8") as f:
            return json.load(f)

    def list_items(self, source_name: str, type_name: str) -> list[str]:
        """List all items of a specific type in a source.

        Args:
            source_name: Source name
            type_name: Type (agents, skills, commands, rules)

        Returns:
            List of item names
        """
        index = self.load_index(source_name)
        if not index:
            return []

        contents = index.get("contents", {})
        type_contents = contents.get(type_name, {})
        return list(type_contents.keys())

    def get_item_path(self, source_name: str, type_name: str, item_name: str) -> Path | None:
        """Get the file path for an item.

        Args:
            source_name: Source name
            type_name: Type (agents, skills, commands, rules)
            item_name: Item name (can include subdirectories like "common/security")

        Returns:
            Path to the item file or None if not found
        """
        source_dir = SOURCES_DIR / source_name
        if not source_dir.exists():
            return None

        # Try direct path first
        item_path = source_dir / type_name / f"{item_name}.md"
        if item_path.exists():
            return item_path

        # Check index
        index = self.load_index(source_name)
        if not index:
            return None

        contents = index.get("contents", {})
        type_contents = contents.get(type_name, {})

        if item_name in type_contents:
            path = type_contents[item_name].get("path")
            if path:
                full_path = source_dir / path
                if full_path.exists():
                    return full_path

        return None

    def item_exists(self, source_name: str, type_name: str, item_name: str) -> bool:
        """Check if an item exists in a source.

        Args:
            source_name: Source name
            type_name: Type (agents, skills, commands, rules)
            item_name: Item name

        Returns:
            True if item exists
        """
        return self.get_item_path(source_name, type_name, item_name) is not None

    def _hash_file(self, path: Path) -> str:
        """Calculate MD5 hash of a file."""
        hash_md5 = hashlib.md5()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()

    def _now(self) -> str:
        """Get current ISO timestamp."""
        from datetime import datetime, timezone

        return datetime.now(timezone.utc).isoformat()

    def _save_index(self, source_name: str, index: dict[str, Any]) -> None:
        """Save index to file."""
        index_file = INDEX_DIR / f"{source_name}.json"
        with open(index_file, "w", encoding="utf-8") as f:
            json.dump(index, f, indent=2)
