"""Tests for source indexing."""

from __future__ import annotations

from ccm.config import SourceConfig
from ccm.indexer import Indexer


class TestIndexer:
    """Test source indexing."""

    def test_index_source(self, mock_ccm_home, mock_source):
        """Test indexing a source."""
        indexer = Indexer()
        source = SourceConfig(name="test-source", github="test/source", ref="main")

        index = indexer.index_source(source)

        assert index["source"] == "test-source"
        assert index["github"] == "test/source"
        assert "commit" in index
        assert "contents" in index

        # Check contents
        contents = index["contents"]
        assert "agents" in contents
        assert "test-agent" in contents["agents"]
        assert "skills" in contents
        assert "test-skill" in contents["skills"]

    def test_load_index(self, mock_ccm_home, mock_source):
        """Test loading an index."""
        indexer = Indexer()
        source = SourceConfig(name="test-source", github="test/source")

        # Index first
        indexer.index_source(source)

        # Then load
        loaded = indexer.load_index("test-source")
        assert loaded is not None
        assert loaded["source"] == "test-source"

    def test_load_nonexistent_index(self, mock_ccm_home):
        """Test loading non-existent index returns None."""
        indexer = Indexer()

        assert indexer.load_index("nonexistent") is None

    def test_item_exists(self, mock_ccm_home, mock_source):
        """Test checking if item exists."""
        indexer = Indexer()
        source = SourceConfig(name="test-source", github="test/source")
        indexer.index_source(source)

        assert indexer.item_exists("test-source", "agents", "test-agent") is True
        assert indexer.item_exists("test-source", "agents", "nonexistent") is False
        assert indexer.item_exists("test-source", "invalid-type", "test") is False

    def test_get_item_path(self, mock_ccm_home, mock_source):
        """Test getting item path."""
        indexer = Indexer()
        source = SourceConfig(name="test-source", github="test/source")
        indexer.index_source(source)

        path = indexer.get_item_path("test-source", "agents", "test-agent")
        assert path is not None
        assert path.name == "test-agent.md"

    def test_list_items(self, mock_ccm_home, mock_source):
        """Test listing items."""
        indexer = Indexer()
        source = SourceConfig(name="test-source", github="test/source")
        indexer.index_source(source)

        agents = indexer.list_items("test-source", "agents")
        assert "test-agent" in agents

        skills = indexer.list_items("test-source", "skills")
        assert "test-skill" in skills
