# CCM - Claude Code Manager

> Profile and source management for Claude Code

CCM is a tool for managing Claude Code profiles, sources, and project configurations. It allows you to:

- **Manage sources**: Fetch and update third-party plugin repositories from GitHub
- **Build profiles**: Combine resources from multiple sources with inheritance
- **Smart detection**: Automatically detect project type and fetch relevant resources
- **Project binding**: Activate/deactivate profiles per project

---

## Installation

```bash
pip install ccm
```

Or install from source:

```bash
git clone https://github.com/wangli-td/ccm.git
cd ccm
pip install -e .
```

---

## Quick Start

### 1. Add a Source

```bash
ccm source add ecc affaan-m/everything-claude-code
```

### 2. List Available Profiles

```bash
ccm profile list
```

Built-in profiles:
- `base` - Global base rules
- `coding` - General coding configuration
- `coding-python` - Python development (with auto-detection)

### 3. Activate Profile in Project

```bash
cd ~/my-project
ccm activate coding-python
```

CCM will:
- Detect project type (e.g., `requirements.txt` → Python)
- Build profile with relevant resources
- Create `.claude/` directory with symlinks

### 4. Check Status

```bash
ccm status
```

---

## Configuration

### Sources

Sources are third-party repositories containing Claude Code resources:

```bash
# Add a source
ccm source add <name> <github-repo> [--ref main]

# List sources
ccm source list

# Update a source
ccm source update <name>

# Remove a source
ccm source remove <name>
```

### Profiles

Profiles define which resources to use from sources:

```bash
# Create a profile
ccm profile create my-profile --extends coding

# Validate a profile
ccm profile validate my-profile

# Build a profile
ccm profile build my-profile

# Show profile details
ccm profile show my-profile
```

#### Profile Configuration

Profiles are defined in `~/.ccm/profiles/<name>.json`:

```json
{
  "name": "my-profile",
  "description": "My custom profile",
  "extends": "coding",
  "auto_fetch": {
    "detect": [
      {"file": "package.json", "source": "ecc", "skills": ["node-patterns"]}
    ],
    "default": {"source": "ecc", "skills": ["general"]}
  },
  "from": {
    "ecc": {
      "agents": ["tdd-guide"],
      "skills": ["my-skill"],
      "commands": ["/my-cmd"],
      "rules": ["my-rules"]
    }
  }
}
```

**Fields:**
- `extends`: Parent profile to inherit from
- `auto_fetch.detect`: Rules to detect project type based on files
- `auto_fetch.default`: Default resources if no detection matches
- `from`: Resources to include from each source

---

## Project Workflow

```bash
# Enter project directory
cd ~/my-python-project

# Activate profile (auto-detects Python)
ccm activate coding-python

# Work with Claude Code...
# Claude will use the activated profile

# When done, or to switch profiles
ccm deactivate

# Refresh after profile changes
ccm refresh
```

---

## Directory Structure

```
~/.ccm/                      # CCM home directory
├── config.json              # Main configuration
├── sources/                 # Cloned source repositories
│   └── ecc/
├── index/                   # Source indexes
│   └── ecc.json
├── profiles/                # Built profiles
│   └── coding-python/
│       ├── agents/
│       ├── skills/
│       ├── commands/
│       ├── rules/
│       └── profile.json
└── logs/
    └── updates.json

~/my-project/
├── .ccm                     # Active profile name
├── .claude/                 # Symlinks to profile
│   ├── agents -> ~/.ccm/profiles/coding-python/agents
│   ├── skills -> ~/.ccm/profiles/coding-python/skills
│   ├── commands -> ~/.ccm/profiles/coding-python/commands
│   ├── rules -> ~/.ccm/profiles/coding-python/rules
│   ├── CLAUDE.md            # Project configuration for Claude
│   └── ...
└── src/
```

---

## Commands Reference

### Source Commands

| Command | Description |
|---------|-------------|
| `ccm source add <name> <repo>` | Add a source from GitHub |
| `ccm source list` | List configured sources |
| `ccm source show <name>` | Show source details |
| `ccm source update <name>` | Update source to latest |
| `ccm source update --all` | Update all sources |
| `ccm source remove <name>` | Remove a source |

### Profile Commands

| Command | Description |
|---------|-------------|
| `ccm profile create <name>` | Create a new profile |
| `ccm profile list` | List available profiles |
| `ccm profile show <name>` | Show profile details |
| `ccm profile validate <name>` | Validate profile configuration |
| `ccm profile build <name>` | Build profile from sources |

### Project Commands

| Command | Description |
|---------|-------------|
| `ccm activate <profile>` | Activate profile in current project |
| `ccm deactivate` | Deactivate current project profile |
| `ccm status` | Show project status |
| `ccm refresh` | Refresh project links |

### TUI (Terminal User Interface)

```bash
# Launch interactive TUI
ccm tui
```

TUI provides a visual interface for:
- **Source Browser**: Browse sources, filter items, view details
- **Profile Configurator**: View profiles, add/remove items, jump to source

Features:
- Items grouped by type (🤖 Agents, 📚 Skills, ⚡ Commands, 📋 Rules)
- Source shown as `[@source]` hint
- Inherited items shown in gray (non-selectable)
- Keyboard navigation with Tab/Shift+Tab

### Diagnostic Commands

| Command | Description |
|---------|-------------|
| `ccm doctor` | Check configuration and diagnose issues |
| `ccm log` | Show update history |
| `ccm clean` | Clean up unused sources |

---

## Version Compatibility

CCM uses strict version locking. The CCM version must match the schema version in `~/.ccm/config.json`.

```bash
$ ccm doctor
CCM version: 0.2.0
Schema version: 0.2.0
✓ Version match: 0.2.0
```

If versions don't match, upgrade CCM:

```bash
pip install --upgrade ccm
```

---

## Development

```bash
# Clone repository
git clone https://github.com/wangli-td/ccm.git
cd ccm

# Install in development mode
pip install -e ".[dev]"

# Run tests
pytest

# Format code
black src/
ruff check src/

# Type check
mypy src/ccm
```

---

## Architecture

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Source    │────▶│   Indexer   │────▶│   Profile   │
│  (GitHub)   │     │  (Parse)    │     │   Builder   │
└─────────────┘     └─────────────┘     └──────┬──────┘
        ▲                                      │
        │         ┌─────────────┐              ▼
        └─────────│ Auto Fetch  │◀────┌─────────────┐
                  │  (Detect)   │     │   Profile   │
                  └─────────────┘     │  (Output)   │
                                      └──────┬──────┘
                                             │
┌─────────────┐     ┌─────────────┐         ▼
│   Claude    │◀────│   Linker    │◀────────┘
│   Code      │     │  (Symlink)  │
└─────────────┘     └─────────────┘
```

---

## License

MIT
