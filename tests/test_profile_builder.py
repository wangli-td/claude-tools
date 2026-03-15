"""Tests for profile building."""

from __future__ import annotations

from ccm.builder import ProfileBuilder
from ccm.config import SourceConfig
from ccm.indexer import Indexer
from ccm.profile_config import ProfileConfig, SourceSelection


class TestProfileBuilder:
    """Test profile building."""

    def test_create_profile(self, mock_ccm_home):
        """Test creating a profile."""
        builder = ProfileBuilder()

        profile = builder.create_profile(
            name="test-profile",
            description="Test profile",
            extends="base",
        )

        assert profile.name == "test-profile"
        assert profile.description == "Test profile"
        assert profile.extends == "base"

    def test_list_profiles(self, mock_ccm_home):
        """Test listing profiles."""
        builder = ProfileBuilder()

        # Create a profile
        builder.create_profile(name="test-profile")

        profiles = builder.list_profiles()
        # Profile should be in the list (may also include builtin profiles)
        assert "test-profile" in profiles

    def test_show_profile(self, mock_ccm_home):
        """Test showing profile details."""
        builder = ProfileBuilder()
        builder.create_profile(
            name="test-profile",
            description="Test",
            extends="base",
        )

        info = builder.show_profile("test-profile")
        assert info is not None
        assert info["name"] == "test-profile"
        assert info["extends"] == "base"

    def test_validate_missing_source(self, mock_ccm_home, mock_config):
        """Test validation with missing source."""
        builder = ProfileBuilder(config=mock_config)

        # Create profile with non-existent source
        profile = ProfileConfig(
            name="test",
            from_sources={"nonexistent": SourceSelection(agents=["test"])},
        )
        profile.save(mock_ccm_home / "profiles")

        errors = builder.validate("test")
        assert any("not configured" in e for e in errors)

    def test_validate_missing_resource(self, mock_ccm_home, mock_source, mock_config):
        """Test validation with missing resource."""
        builder = ProfileBuilder()
        indexer = Indexer()
        source = SourceConfig(name="test-source", github="test/source")
        indexer.index_source(source)

        # Create profile with non-existent resource
        profile = ProfileConfig(
            name="test",
            from_sources={"test-source": SourceSelection(agents=["nonexistent"])},
        )
        profile.save(mock_ccm_home / "profiles")

        errors = builder.validate("test")
        assert any("not found" in e for e in errors)

    def test_circular_inheritance_detection(self, mock_ccm_home):
        """Test circular inheritance is detected."""
        builder = ProfileBuilder()

        # Create circular dependency: a -> b -> a
        a = ProfileConfig(name="a", extends="b")
        a.save(mock_ccm_home / "profiles")

        b = ProfileConfig(name="b", extends="a")
        b.save(mock_ccm_home / "profiles")

        errors = builder.validate("a")
        assert any("Circular" in e for e in errors)

    def test_build_profile(self, mock_ccm_home, mock_source, mock_config):
        """Test building a profile."""
        builder = ProfileBuilder()
        indexer = Indexer()
        source = SourceConfig(name="test-source", github="test/source")
        indexer.index_source(source)

        # Create and build profile
        profile = ProfileConfig(
            name="test",
            from_sources={
                "test-source": SourceSelection(
                    agents=["test-agent"],
                    skills=["test-skill"],
                )
            },
        )
        profile.save(mock_ccm_home / "profiles")

        profile_dir = builder.build("test")

        assert profile_dir.exists()
        assert (profile_dir / "agents" / "test-agent.md").exists()
        assert (profile_dir / "skills" / "test-skill.md").exists()

    def test_inheritance_merge(self, mock_ccm_home, mock_source, mock_config):
        """Test profile inheritance merging."""
        builder = ProfileBuilder()
        indexer = Indexer()
        source = SourceConfig(name="test-source", github="test/source")
        indexer.index_source(source)

        # Create base profile
        base = ProfileConfig(
            name="base",
            from_sources={
                "test-source": SourceSelection(agents=["test-agent"])
            },
        )
        base.save(mock_ccm_home / "profiles")

        # Create child profile
        child = ProfileConfig(
            name="child",
            extends="base",
            from_sources={
                "test-source": SourceSelection(skills=["test-skill"])
            },
        )
        child.save(mock_ccm_home / "profiles")

        profile_dir = builder.build("child")

        # Should have both agent (from base) and skill (from child)
        assert (profile_dir / "agents" / "test-agent.md").exists()
        assert (profile_dir / "skills" / "test-skill.md").exists()
