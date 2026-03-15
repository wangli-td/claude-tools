"""Tests for configuration management."""

from __future__ import annotations

import pytest

from ccm.config import Config, SourceConfig
from ccm.constants import SCHEMA_VERSION


class TestConfig:
    """Test configuration management."""

    def test_default_config(self, mock_ccm_home):
        """Test default configuration."""
        config = Config.load()

        assert config.version == SCHEMA_VERSION
        assert config.sources == []
        assert config.settings.auto_update is False

    def test_add_source(self, mock_ccm_home):
        """Test adding a source."""
        config = Config.load()

        source = SourceConfig(name="test", github="test/repo", ref="main")
        config.add_source(source)

        assert len(config.sources) == 1
        assert config.get_source("test").github == "test/repo"

    def test_add_duplicate_source(self, mock_ccm_home):
        """Test adding duplicate source raises error."""
        config = Config.load()

        source = SourceConfig(name="test", github="test/repo")
        config.add_source(source)

        with pytest.raises(ValueError, match="already exists"):
            config.add_source(source)

    def test_remove_source(self, mock_ccm_home):
        """Test removing a source."""
        config = Config.load()

        source = SourceConfig(name="test", github="test/repo")
        config.add_source(source)

        assert config.remove_source("test") is True
        assert config.get_source("test") is None

    def test_remove_nonexistent_source(self, mock_ccm_home):
        """Test removing non-existent source returns False."""
        config = Config.load()

        assert config.remove_source("nonexistent") is False

    def test_version_check(self, mock_ccm_home):
        """Test version compatibility check."""
        config = Config.load()

        assert config.check_version() is True

        # Test incompatible version
        config.version = "999.0.0"
        assert config.check_version() is False
