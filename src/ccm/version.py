"""Version management for CCM."""

from __future__ import annotations

from ccm.config import Config
from ccm.constants import SCHEMA_VERSION, VERSION


class VersionManager:
    """Manages version compatibility between CCM and config schema."""

    @staticmethod
    def check_compatibility(config: Config | None = None) -> tuple[bool, str]:
        """Check if CCM version is compatible with config schema version.

        Args:
            config: Config to check, or None to load from file

        Returns:
            Tuple of (is_compatible, message)
        """
        if config is None:
            config = Config.load()

        if config.version == SCHEMA_VERSION:
            return True, f"Version match: {VERSION}"

        # Parse versions for comparison
        try:
            ccm_major, ccm_minor, ccm_patch = map(int, VERSION.split("."))
            schema_major, schema_minor, schema_patch = map(int, config.version.split("."))
        except ValueError:
            return False, f"Invalid version format: CCM={VERSION}, Schema={config.version}"

        # Major version must match exactly
        if ccm_major != schema_major:
            return (
                False,
                f"Major version mismatch: CCM={VERSION}, Schema={config.version}. "
                f"Please upgrade ccm to {config.version}",
            )

        # Minor version: CCM >= schema required
        if ccm_minor < schema_minor:
            return (
                False,
                f"CCM version too old: {VERSION} < {config.version}. "
                f"Please upgrade ccm to {config.version}",
            )

        # Patch version differences are OK
        return True, f"Version compatible: CCM={VERSION}, Schema={config.version}"

    @staticmethod
    def get_upgrade_command(target_version: str) -> str:
        """Get the command to upgrade CCM to target version."""
        return f"pip install --upgrade ccm=={target_version}"

    @staticmethod
    def migrate_config(config: Config) -> Config:
        """Migrate config to current schema version if possible.

        Args:
            config: Config to migrate

        Returns:
            Migrated config

        Raises:
            ValueError: If migration is not possible
        """
        # For now, we require exact version match
        # Future versions could implement automatic migration
        is_compatible, message = VersionManager.check_compatibility(config)

        if not is_compatible:
            raise ValueError(f"Cannot migrate: {message}")

        # Update version to current
        if config.version != SCHEMA_VERSION:
            config.version = SCHEMA_VERSION
            config.save()

        return config
