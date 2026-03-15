"""Update management for CCM."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ccm import constants
from ccm.builder import ProfileBuilder
from ccm.config import Config
from ccm.indexer import Indexer
from ccm.source import SourceManager


class UpdateManager:
    """Manages updates and tracks history."""

    def __init__(self) -> None:
        self.log_file = constants.LOGS_DIR / "updates.json"
        constants.LOGS_DIR.mkdir(parents=True, exist_ok=True)

    def log_update(
        self,
        source_name: str,
        old_commit: str | None,
        new_commit: str,
        changes: dict[str, list[str]],
        affected_profiles: list[str],
    ) -> None:
        """Log an update event."""
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "type": "source_update",
            "source": source_name,
            "old_commit": old_commit,
            "new_commit": new_commit,
            "changes": changes,
            "affected_profiles": affected_profiles,
        }

        logs = self._load_logs()
        logs.append(entry)
        self._save_logs(logs)

    def log_profile_build(self, profile_name: str, triggered_by: str) -> None:
        """Log a profile build event."""
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "type": "profile_build",
            "profile": profile_name,
            "triggered_by": triggered_by,
        }

        logs = self._load_logs()
        logs.append(entry)
        self._save_logs(logs)

    def get_logs(self, limit: int = 50) -> list[dict[str, Any]]:
        """Get update logs."""
        logs = self._load_logs()
        return logs[-limit:]

    def get_affected_profiles(self, source_name: str) -> list[str]:
        """Get profiles affected by a source update."""
        builder = ProfileBuilder()
        affected = []

        for profile_name in builder.list_profiles():
            profile = builder._load_profile_config(profile_name)
            if profile and source_name in profile.get_all_sources():
                affected.append(profile_name)

        return affected

    def rebuild_affected_profiles(self, source_name: str) -> list[str]:
        """Rebuild all profiles affected by a source update."""
        affected = self.get_affected_profiles(source_name)
        rebuilt = []

        builder = ProfileBuilder()
        for profile_name in affected:
            try:
                builder.build(profile_name)
                rebuilt.append(profile_name)
                self.log_profile_build(profile_name, f"source_update:{source_name}")
            except Exception:
                # Log error but continue with other profiles
                pass

        return rebuilt

    def _load_logs(self) -> list[dict[str, Any]]:
        """Load logs from file."""
        if not self.log_file.exists():
            return []

        try:
            with open(self.log_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return []

    def _save_logs(self, logs: list[dict[str, Any]]) -> None:
        """Save logs to file."""
        with open(self.log_file, "w", encoding="utf-8") as f:
            json.dump(logs, f, indent=2)


class CleanupManager:
    """Manages cleanup of unused resources."""

    def __init__(self) -> None:
        self.config = Config.load()

    def get_unused_sources(self) -> list[str]:
        """Get sources that are not referenced by any profile."""
        builder = ProfileBuilder()
        used_sources: set[str] = set()

        for profile_name in builder.list_profiles():
            profile = builder._load_profile_config(profile_name)
            if profile:
                used_sources.update(profile.get_all_sources())

        configured_sources = {s.name for s in self.config.sources}
        return list(configured_sources - used_sources)

    def cleanup_source(self, source_name: str) -> bool:
        """Remove a source and its cache."""
        from ccm.source import SourceManager

        manager = SourceManager(self.config)
        return manager.remove(source_name)

    def cleanup_all_unused(self) -> list[str]:
        """Clean up all unused sources."""
        removed = []
        for source_name in self.get_unused_sources():
            if self.cleanup_source(source_name):
                removed.append(source_name)
        return removed

    def get_built_profiles(self) -> list[str]:
        """Get list of built profiles (in ~/.ccm/profiles/)."""
        profiles = []
        if constants.PROFILES_DIR.exists():
            for d in constants.PROFILES_DIR.iterdir():
                if d.is_dir() and (d / "profile.json").exists():
                    profiles.append(d.name)
        return profiles

    def cleanup_profiles(self, keep_configs: bool = True) -> dict[str, list[str]]:
        """Clean up built profiles.

        Args:
            keep_configs: If True, keep the .json config files, only remove built directories

        Returns:
            Dict with 'removed' and 'kept' lists
        """
        removed = []
        kept = []

        if not constants.PROFILES_DIR.exists():
            return {"removed": removed, "kept": kept}

        for item in constants.PROFILES_DIR.iterdir():
            if item.is_dir():
                # Remove built profile directories
                import shutil
                shutil.rmtree(item)
                removed.append(item.name)
            elif item.suffix == ".json" and not keep_configs:
                # Remove config files if keep_configs is False
                item.unlink()
                removed.append(item.name)
            else:
                kept.append(item.name)

        return {"removed": removed, "kept": kept}

    def cleanup_index(self) -> list[str]:
        """Clean up all index caches.

        Returns:
            List of removed index files
        """
        removed = []
        if constants.INDEX_DIR.exists():
            for f in constants.INDEX_DIR.glob("*.json"):
                f.unlink()
                removed.append(f.stem)
        return removed

    def cleanup_logs(self, keep_recent: int = 100) -> dict[str, Any]:
        """Clean up old log entries.

        Args:
            keep_recent: Number of recent log entries to keep

        Returns:
            Dict with 'removed_count' and 'kept_count'
        """
        log_file = constants.LOGS_DIR / "updates.json"
        if not log_file.exists():
            return {"removed_count": 0, "kept_count": 0}

        try:
            with open(log_file, "r", encoding="utf-8") as f:
                logs = json.load(f)
        except (json.JSONDecodeError, IOError):
            return {"removed_count": 0, "kept_count": 0}

        total = len(logs)
        if total <= keep_recent:
            return {"removed_count": 0, "kept_count": total}

        # Keep only the most recent entries
        kept_logs = logs[-keep_recent:]
        with open(log_file, "w", encoding="utf-8") as f:
            json.dump(kept_logs, f, indent=2)

        return {"removed_count": total - keep_recent, "kept_count": keep_recent}

    def cleanup_project(self, project_dir: Path | None = None) -> dict[str, Any]:
        """Clean up project-level .claude/ directory.

        Args:
            project_dir: Project directory (defaults to current directory)

        Returns:
            Dict with cleanup results
        """
        if project_dir is None:
            project_dir = Path.cwd()

        claude_dir = project_dir / ".claude"
        result = {
            "project_dir": str(project_dir),
            "claude_dir_exists": claude_dir.exists(),
            "removed_links": [],
            "removed_files": [],
            "removed_dirs": [],
            "errors": [],
        }

        if not claude_dir.exists():
            return result

        # Remove symlinks first
        for item in claude_dir.iterdir():
            try:
                if item.is_symlink():
                    item.unlink()
                    result["removed_links"].append(item.name)
                elif item.is_file():
                    item.unlink()
                    result["removed_files"].append(item.name)
                elif item.is_dir():
                    import shutil
                    shutil.rmtree(item)
                    result["removed_dirs"].append(item.name)
            except Exception as e:
                result["errors"].append(f"{item.name}: {e}")

        # Remove .claude directory if empty
        try:
            claude_dir.rmdir()
            result["claude_dir_removed"] = True
        except OSError:
            result["claude_dir_removed"] = False

        return result

    def get_cleanup_summary(self) -> dict[str, Any]:
        """Get a summary of what can be cleaned up.

        Returns:
            Dict with cleanup statistics
        """
        summary = {
            "sources": {
                "total": len(self.config.sources),
                "unused": self.get_unused_sources(),
            },
            "profiles": {
                "built": self.get_built_profiles(),
                "configs": [],
            },
            "index": {
                "files": [],
            },
            "logs": {
                "entries": 0,
            },
            "disk_usage": {
                "sources": 0,
                "profiles": 0,
                "index": 0,
                "logs": 0,
            },
        }

        # Count profile configs
        if constants.PROFILES_DIR.exists():
            for f in constants.PROFILES_DIR.glob("*.json"):
                summary["profiles"]["configs"].append(f.stem)

        # Count index files
        if constants.INDEX_DIR.exists():
            for f in constants.INDEX_DIR.glob("*.json"):
                summary["index"]["files"].append(f.stem)

        # Count log entries
        log_file = constants.LOGS_DIR / "updates.json"
        if log_file.exists():
            try:
                with open(log_file, "r", encoding="utf-8") as f:
                    logs = json.load(f)
                    summary["logs"]["entries"] = len(logs)
            except (json.JSONDecodeError, IOError):
                pass

        # Calculate disk usage
        def dir_size(path: Path) -> int:
            if not path.exists():
                return 0
            total = 0
            for item in path.rglob("*"):
                if item.is_file():
                    total += item.stat().st_size
            return total

        summary["disk_usage"]["sources"] = dir_size(constants.SOURCES_DIR)
        summary["disk_usage"]["profiles"] = dir_size(constants.PROFILES_DIR)
        summary["disk_usage"]["index"] = dir_size(constants.INDEX_DIR)
        summary["disk_usage"]["logs"] = dir_size(constants.LOGS_DIR)

        return summary
