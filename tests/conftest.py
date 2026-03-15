"""Test configuration for CCM."""

from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path

import pytest


@pytest.fixture
def temp_dir():
    """Create a temporary directory."""
    tmp = tempfile.mkdtemp()
    yield Path(tmp)
    shutil.rmtree(tmp)


@pytest.fixture
def mock_ccm_home(temp_dir, monkeypatch):
    """Create a mock CCM home directory."""
    import ccm.constants as constants

    monkeypatch.setattr(constants, "CCM_DIR", temp_dir)
    monkeypatch.setattr(constants, "SOURCES_DIR", temp_dir / "sources")
    monkeypatch.setattr(constants, "INDEX_DIR", temp_dir / "index")
    monkeypatch.setattr(constants, "PROFILES_DIR", temp_dir / "profiles")
    monkeypatch.setattr(constants, "LOGS_DIR", temp_dir / "logs")
    monkeypatch.setattr(constants, "CONFIG_FILE", temp_dir / "config.json")

    # Also patch in other modules that may have imported constants
    import ccm.config
    import ccm.indexer
    import ccm.builder
    import ccm.project
    import ccm.updater

    monkeypatch.setattr(ccm.config, "CCM_DIR", temp_dir)
    monkeypatch.setattr(ccm.config, "CONFIG_FILE", temp_dir / "config.json")
    monkeypatch.setattr(ccm.indexer, "INDEX_DIR", temp_dir / "index")
    monkeypatch.setattr(ccm.indexer, "SOURCES_DIR", temp_dir / "sources")
    monkeypatch.setattr(ccm.builder.constants, "PROFILES_DIR", temp_dir / "profiles")
    monkeypatch.setattr(ccm.project, "CLAUDE_DIR", ".claude")
    monkeypatch.setattr(ccm.updater.constants, "LOGS_DIR", temp_dir / "logs")
    monkeypatch.setattr(ccm.updater.constants, "PROFILES_DIR", temp_dir / "profiles")
    monkeypatch.setattr(ccm.updater.constants, "INDEX_DIR", temp_dir / "index")
    monkeypatch.setattr(ccm.updater.constants, "SOURCES_DIR", temp_dir / "sources")

    return temp_dir


@pytest.fixture
def mock_source(mock_ccm_home):
    """Create a mock source with some resources."""
    source_dir = mock_ccm_home / "sources" / "test-source"
    source_dir.mkdir(parents=True)

    # Create resource directories
    for type_name in ["agents", "skills", "commands", "rules"]:
        (source_dir / type_name).mkdir(exist_ok=True)

    # Create some test resources
    (source_dir / "agents" / "test-agent.md").write_text("# Test Agent")
    (source_dir / "skills" / "test-skill.md").write_text("# Test Skill")
    (source_dir / "commands" / "test-cmd.md").write_text("# Test Command")
    (source_dir / "rules" / "test-rule.md").write_text("# Test Rule")

    # Initialize git repo
    import subprocess

    subprocess.run(["git", "init"], cwd=source_dir, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=source_dir, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=source_dir, capture_output=True)
    subprocess.run(["git", "add", "."], cwd=source_dir, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=source_dir, capture_output=True)

    return source_dir


@pytest.fixture
def mock_config(mock_ccm_home):
    """Create a mock configuration."""
    from ccm.config import Config, SourceConfig

    config = Config()
    config.add_source(SourceConfig(name="test-source", github="test/source", ref="main"))
    return config
