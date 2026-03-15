"""Tests for version management."""

from __future__ import annotations

import pytest

from ccm.config import Config
from ccm.constants import SCHEMA_VERSION, VERSION
from ccm.version import VersionManager


class TestVersionManager:
    """Test version management."""

    def test_version_match(self, mock_ccm_home):
        """Test version compatibility when versions match."""
        config = Config()
        config.version = SCHEMA_VERSION

        is_compatible, message = VersionManager.check_compatibility(config)

        assert is_compatible is True
        assert "match" in message.lower()

    def test_major_version_mismatch(self, mock_ccm_home):
        """Test major version mismatch is detected."""
        config = Config()
        config.version = "999.0.0"

        is_compatible, message = VersionManager.check_compatibility(config)

        assert is_compatible is False
        assert "mismatch" in message.lower()

    def test_minor_version_too_old(self, mock_ccm_home):
        """Test CCM version too old is detected."""
        config = Config()
        # Schema requires newer minor version
        parts = SCHEMA_VERSION.split(".")
        config.version = f"{parts[0]}.{int(parts[1]) + 1}.0"

        is_compatible, message = VersionManager.check_compatibility(config)

        assert is_compatible is False
        assert "too old" in message.lower()

    def test_get_upgrade_command(self):
        """Test getting upgrade command."""
        cmd = VersionManager.get_upgrade_command("1.2.3")
        assert "pip install" in cmd
        assert "1.2.3" in cmd

    def test_migrate_config_same_version(self, mock_ccm_home):
        """Test migration when versions match."""
        config = Config()
        config.version = SCHEMA_VERSION

        migrated = VersionManager.migrate_config(config)

        assert migrated.version == SCHEMA_VERSION

    def test_migrate_config_incompatible(self, mock_ccm_home):
        """Test migration fails for incompatible versions."""
        config = Config()
        config.version = "999.0.0"

        with pytest.raises(ValueError, match="Cannot migrate"):
            VersionManager.migrate_config(config)
