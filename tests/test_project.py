"""Tests for project management."""

from __future__ import annotations

import pytest

from ccm.builder import ProfileBuilder
from ccm.config import SourceConfig
from ccm.indexer import Indexer
from ccm.profile_config import ProfileConfig, SourceSelection
from ccm.project import ProjectManager


class TestProjectManager:
    """Test project management."""

    def test_activate_profile(self, mock_ccm_home, mock_source, mock_config, temp_dir):
        """Test activating a profile in a project."""
        # Setup
        indexer = Indexer()
        source = SourceConfig(name="test-source", github="test/source")
        indexer.index_source(source)

        builder = ProfileBuilder()
        profile = ProfileConfig(
            name="test",
            from_sources={"test-source": SourceSelection(agents=["test-agent"])},
        )
        profile.save(mock_ccm_home / "profiles")

        # Activate
        project = ProjectManager(project_dir=temp_dir)
        result = project.activate("test")

        assert result["profile"] == "test"
        assert (temp_dir / ".ccm").exists()
        assert (temp_dir / ".claude").exists()

    def test_deactivate_profile(self, mock_ccm_home, mock_source, mock_config, temp_dir):
        """Test deactivating a profile."""
        # Setup
        indexer = Indexer()
        source = SourceConfig(name="test-source", github="test/source")
        indexer.index_source(source)

        builder = ProfileBuilder()
        profile = ProfileConfig(
            name="test",
            from_sources={"test-source": SourceSelection(agents=["test-agent"])},
        )
        profile.save(mock_ccm_home / "profiles")

        # Activate then deactivate
        project = ProjectManager(project_dir=temp_dir)
        project.activate("test")

        assert project.deactivate() is True
        assert not (temp_dir / ".ccm").exists()
        assert not (temp_dir / ".claude").exists()

    def test_deactivate_without_activation(self, temp_dir):
        """Test deactivating when nothing is active."""
        project = ProjectManager(project_dir=temp_dir)
        assert project.deactivate() is False

    def test_status_active(self, mock_ccm_home, mock_source, mock_config, temp_dir):
        """Test status when profile is active."""
        # Setup
        indexer = Indexer()
        source = SourceConfig(name="test-source", github="test/source")
        indexer.index_source(source)

        builder = ProfileBuilder()
        profile = ProfileConfig(
            name="test",
            from_sources={"test-source": SourceSelection(agents=["test-agent"])},
        )
        profile.save(mock_ccm_home / "profiles")

        # Activate and check status
        project = ProjectManager(project_dir=temp_dir)
        project.activate("test")

        status = project.status()
        assert status["active"] is True
        assert status["profile"] == "test"
        assert status["claude_dir_exists"] is True

    def test_status_inactive(self, temp_dir):
        """Test status when no profile is active."""
        project = ProjectManager(project_dir=temp_dir)

        status = project.status()
        assert status["active"] is False
        assert status["profile"] is None

    def test_refresh(self, mock_ccm_home, mock_source, mock_config, temp_dir):
        """Test refreshing project links."""
        # Setup
        indexer = Indexer()
        source = SourceConfig(name="test-source", github="test/source")
        indexer.index_source(source)

        builder = ProfileBuilder()
        profile = ProfileConfig(
            name="test",
            from_sources={"test-source": SourceSelection(agents=["test-agent"])},
        )
        profile.save(mock_ccm_home / "profiles")

        # Activate and refresh
        project = ProjectManager(project_dir=temp_dir)
        project.activate("test")

        result = project.refresh()
        assert result["profile"] == "test"
        assert result["refreshed"] is True

    def test_refresh_without_activation(self, temp_dir):
        """Test refreshing when nothing is active."""
        project = ProjectManager(project_dir=temp_dir)

        with pytest.raises(ValueError, match="No profile activated"):
            project.refresh()

    def test_auto_fetch_detection(self, mock_ccm_home, mock_source, mock_config, temp_dir):
        """Test auto-fetch detection based on project files."""
        from ccm.indexer import Indexer
        from ccm.config import SourceConfig

        # Index the mock source
        indexer = Indexer()
        source = SourceConfig(name="test-source", github="test/source")
        indexer.index_source(source)

        # Setup profile with auto_fetch
        profile = ProfileConfig(
            name="test",
            auto_fetch={
                "detect": [
                    {"file": "requirements.txt", "source": "test-source", "skills": ["python"]}
                ],
                "default": {"source": "test-source", "skills": ["general"]},
            },
            from_sources={},
        )
        profile.save(mock_ccm_home / "profiles")

        # Create project file
        (temp_dir / "requirements.txt").write_text("requests\n")

        # Activate
        project = ProjectManager(project_dir=temp_dir)
        result = project.activate("test")

        assert result["auto_fetch"]["matched"] is True
        assert "requirements.txt" in result["auto_fetch"]["detected_files"]
