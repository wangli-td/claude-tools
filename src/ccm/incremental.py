"""Incremental build support for CCM.

Tracks file hashes to avoid unnecessary copies during profile building.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


class IncrementalBuilder:
    """Manages incremental builds by tracking file hashes."""

    def __init__(self, profile_dir: Path):
        self.profile_dir = profile_dir
        self.state_file = profile_dir / ".build_state.json"
        self.state: dict[str, str] = self._load_state()
        self.updated_files: list[Path] = []
        self.removed_files: list[Path] = []

    def _load_state(self) -> dict[str, str]:
        """Load previous build state."""
        if self.state_file.exists():
            try:
                return json.loads(self.state_file.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, IOError):
                return {}
        return {}

    def save_state(self) -> None:
        """Save current build state."""
        self.state_file.write_text(
            json.dumps(self.state, indent=2, sort_keys=True),
            encoding="utf-8"
        )

    def needs_update(self, source_path: Path, dest_path: Path) -> bool:
        """Check if file needs to be updated.

        Args:
            source_path: Path to source file
            dest_path: Path to destination file

        Returns:
            True if file needs to be copied/updated
        """
        # Destination doesn't exist - needs update
        if not dest_path.exists():
            return True

        # Compare hashes
        current_hash = self._hash_file(source_path)
        stored_hash = self.state.get(str(dest_path.relative_to(self.profile_dir)))

        return current_hash != stored_hash

    def record_file(self, dest_path: Path, source_path: Path | None = None) -> None:
        """Record a file as updated.

        Args:
            dest_path: Path where file was copied to
            source_path: Optional source path to compute hash from
        """
        rel_path = str(dest_path.relative_to(self.profile_dir))

        if source_path and source_path.exists():
            self.state[rel_path] = self._hash_file(source_path)
        else:
            # If no source, mark as present but unknown hash
            self.state[rel_path] = "present"

        self.updated_files.append(dest_path)

    def remove_stale_files(self, current_files: set[Path]) -> None:
        """Remove files that are no longer in the profile.

        Args:
            current_files: Set of files that should exist
        """
        stale = []
        for rel_path in list(self.state.keys()):
            full_path = self.profile_dir / rel_path
            if full_path not in current_files:
                stale.append(rel_path)

        for rel_path in stale:
            full_path = self.profile_dir / rel_path
            if full_path.exists():
                full_path.unlink()
                self.removed_files.append(full_path)
            del self.state[rel_path]

    def _hash_file(self, path: Path) -> str:
        """Compute MD5 hash of file content."""
        hash_md5 = hashlib.md5()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()[:16]

    def get_stats(self) -> dict[str, Any]:
        """Get build statistics."""
        return {
            "updated": len(self.updated_files),
            "removed": len(self.removed_files),
            "total_tracked": len(self.state),
        }
