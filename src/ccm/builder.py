"""Profile builder for CCM."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from ccm import constants
from ccm.config import Config
from ccm.constants import SOURCE_TYPES
from ccm.indexer import Indexer
from ccm.incremental import IncrementalBuilder
from ccm.interfaces import ProfileBuilderInterface
from ccm.profile_config import ProfileConfig, SourceSelection


class ProfileBuilder(ProfileBuilderInterface):
    """Builds profiles by merging sources and handling inheritance."""

    def __init__(self, config: Config | None = None) -> None:
        self.config = config or Config.load()
        self.indexer = Indexer()
        constants.PROFILES_DIR.mkdir(parents=True, exist_ok=True)

    def build(self, profile_name: str) -> Path:
        """Build a profile.

        Args:
            profile_name: Name of the profile to build

        Returns:
            Path to the built profile directory

        Raises:
            ValueError: If profile not found or invalid
        """
        # Load profile config
        profile = self._load_profile_config(profile_name)
        if not profile:
            raise ValueError(f"Profile '{profile_name}' not found")

        # Check for circular inheritance
        self._check_circular_inheritance(profile_name, set())

        # Build profile directory
        profile_dir = constants.PROFILES_DIR / profile_name
        if not profile_dir.exists():
            profile_dir.mkdir(parents=True, exist_ok=True)

        # Initialize incremental builder
        incremental = IncrementalBuilder(profile_dir)

        # Merge inherited profiles
        merged_selection = self._merge_inheritance(profile)

        # Copy resources from sources (with incremental support)
        current_files = self._copy_resources_incremental(profile_dir, merged_selection, incremental)

        # Remove stale files
        incremental.remove_stale_files(current_files)

        # Save build state
        incremental.save_state()

        # Save resolved profile config
        resolved_config = profile.model_dump(by_alias=True)
        resolved_config["resolved_from"] = {
            source: selection.model_dump()
            for source, selection in merged_selection.items()
        }

        with open(profile_dir / "profile.json", "w", encoding="utf-8") as f:
            json.dump(resolved_config, f, indent=2)

        return profile_dir

    def build_with_auto_fetch(
        self, profile_name: str, project_dir: Path
    ) -> tuple[Path, dict[str, Any]]:
        """Build a profile with auto-fetch detection.

        Args:
            profile_name: Name of the profile to build
            project_dir: Project directory to scan for auto-fetch

        Returns:
            Tuple of (profile_dir, auto_fetch_result)
        """
        # Load profile config
        profile = self._load_profile_config(profile_name)
        if not profile:
            raise ValueError(f"Profile '{profile_name}' not found")

        # Detect auto-fetch additions
        auto_fetch_result = self._detect_auto_fetch(profile, project_dir)

        # Temporarily modify profile with auto-fetch results
        if auto_fetch_result["matched"]:
            for source, items in auto_fetch_result["additions"].items():
                if source not in profile.from_sources:
                    profile.from_sources[source] = SourceSelection()

                selection = profile.from_sources[source]
                for skill in items.get("skills", []):
                    if skill not in selection.skills:
                        selection.skills.append(skill)

        # Build the profile
        profile_dir = self.build(profile_name)

        return profile_dir, auto_fetch_result

    def validate(self, profile_name: str) -> list[str]:
        """Validate a profile configuration.

        Args:
            profile_name: Name of the profile to validate

        Returns:
            List of error messages (empty if valid)
        """
        errors = []

        profile = self._load_profile_config(profile_name)
        if not profile:
            return [f"Profile '{profile_name}' not found"]

        # Check inheritance
        if profile.extends:
            # Support both single and multiple inheritance
            parents = profile.extends if isinstance(profile.extends, list) else [profile.extends]
            for parent_name in parents:
                parent = self._load_profile_config(parent_name)
                if not parent:
                    errors.append(f"Parent profile '{parent_name}' not found")

            # Check for circular inheritance
            try:
                self._check_circular_inheritance(profile_name, set())
            except ValueError as e:
                errors.append(str(e))

        # Check sources exist
        for source_name in profile.get_all_sources():
            source = self.config.get_source(source_name)
            if not source:
                errors.append(f"Source '{source_name}' not configured")
                continue

            # Check indexed
            index = self.indexer.load_index(source_name)
            if not index:
                errors.append(f"Source '{source_name}' not indexed")
                continue

        # Check resources exist
        for source_name, selection in profile.from_sources.items():
            for type_name in SOURCE_TYPES:
                items = getattr(selection, type_name, [])
                for item_name in items:
                    if not self.indexer.item_exists(source_name, type_name, item_name):
                        errors.append(
                            f"Resource not found: {source_name}:{type_name}/{item_name}"
                        )

        return errors

    def list_profiles(self) -> list[str]:
        """List all available profiles."""
        profiles = []

        # Check built-in profiles in package
        builtin_dir = Path(__file__).parent / "profiles"
        if builtin_dir.exists():
            for f in builtin_dir.glob("*.json"):
                profiles.append(f.stem)

        # Check user profiles (both config files and built directories)
        if constants.PROFILES_DIR.exists():
            # Check built profile directories
            for d in constants.PROFILES_DIR.iterdir():
                if d.is_dir() and (d / "profile.json").exists():
                    if d.name not in profiles:
                        profiles.append(d.name)
            # Check profile config files
            for f in constants.PROFILES_DIR.glob("*.json"):
                if f.stem not in profiles:
                    profiles.append(f.stem)

        return sorted(profiles)

    def show_profile(self, profile_name: str) -> dict[str, Any] | None:
        """Show profile details."""
        profile = self._load_profile_config(profile_name)
        if not profile:
            return None

        # Get inheritance chain
        inheritance_chain = self._get_inheritance_chain(profile_name)

        # Get all resources
        all_resources: dict[str, dict[str, list[str]]] = {}
        for source_name, selection in profile.from_sources.items():
            all_resources[source_name] = {
                "agents": selection.agents,
                "skills": selection.skills,
                "commands": selection.commands,
                "rules": selection.rules,
            }

        return {
            "name": profile.name,
            "description": profile.description,
            "extends": profile.extends,
            "inheritance_chain": inheritance_chain,
            "auto_fetch": profile.auto_fetch.model_dump() if profile.auto_fetch else None,
            "resources": all_resources,
        }

    def create_profile(
        self,
        name: str,
        description: str = "",
        extends: str | None = None,
        from_sources: dict[str, SourceSelection] | None = None,
    ) -> ProfileConfig:
        """Create a new profile."""
        profile = ProfileConfig(
            name=name,
            description=description,
            extends=extends,
            from_sources=from_sources or {},
        )

        # Save raw config
        profile_file = constants.PROFILES_DIR / f"{name}.json"
        profile_file.parent.mkdir(parents=True, exist_ok=True)

        with open(profile_file, "w", encoding="utf-8") as f:
            json.dump(profile.model_dump(by_alias=True), f, indent=2)

        return profile

    def _load_profile_config(self, name: str) -> ProfileConfig | None:
        """Load profile configuration."""
        # Try user profile config file first (created by create_profile)
        user_file = constants.PROFILES_DIR / f"{name}.json"
        if user_file.exists():
            with open(user_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            return ProfileConfig(**data)

        # Try built profile directory (created by build)
        built_file = constants.PROFILES_DIR / name / "profile.json"
        if built_file.exists():
            with open(built_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            return ProfileConfig(**data)

        # Try built-in profiles
        builtin_file = Path(__file__).parent / "profiles" / f"{name}.json"
        if builtin_file.exists():
            with open(builtin_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            return ProfileConfig(**data)

        return None

    def _check_circular_inheritance(self, profile_name: str, visited: set[str]) -> None:
        """Check for circular inheritance."""
        if profile_name in visited:
            chain = " -> ".join(visited) + f" -> {profile_name}"
            raise ValueError(f"Circular inheritance detected: {chain}")

        visited.add(profile_name)

        profile = self._load_profile_config(profile_name)
        if profile and profile.extends:
            # Support both single and multiple inheritance
            parents = profile.extends if isinstance(profile.extends, list) else [profile.extends]
            for parent in parents:
                self._check_circular_inheritance(parent, visited.copy())

    def _get_inheritance_chain(self, profile_name: str) -> list[str]:
        """Get the inheritance chain for a profile (supports multiple inheritance)."""
        # Use BFS to get topological order
        visited = set()
        chain = []

        def visit(name: str):
            if name in visited:
                return
            visited.add(name)

            profile = self._load_profile_config(name)
            if profile and profile.extends:
                # Support both single and multiple inheritance
                parents = profile.extends if isinstance(profile.extends, list) else [profile.extends]
                # Visit parents first (left to right for multiple inheritance)
                for parent in parents:
                    visit(parent)

            chain.append(name)

        visit(profile_name)
        return chain

    def _merge_inheritance(self, profile: ProfileConfig) -> dict[str, SourceSelection]:
        """Merge profile with its inheritance chain."""
        chain = self._get_inheritance_chain(profile.name)
        # Reverse to start from base
        chain.reverse()

        merged: dict[str, SourceSelection] = {}

        for profile_name in chain:
            p = self._load_profile_config(profile_name)
            if not p:
                continue

            for source_name, selection in p.from_sources.items():
                if source_name not in merged:
                    merged[source_name] = SourceSelection()

                # Merge each type (child overrides)
                merged_selection = merged[source_name]
                if selection.agents:
                    merged_selection.agents = selection.agents.copy()
                if selection.skills:
                    merged_selection.skills = selection.skills.copy()
                if selection.commands:
                    merged_selection.commands = selection.commands.copy()
                if selection.rules:
                    merged_selection.rules = selection.rules.copy()

        return merged

    def _copy_resources(
        self, profile_dir: Path, selections: dict[str, SourceSelection]
    ) -> None:
        """Copy resources from sources to profile directory (legacy, non-incremental)."""
        for source_name, selection in selections.items():
            for type_name in SOURCE_TYPES:
                items = getattr(selection, type_name, [])
                if not items:
                    continue

                type_dir = profile_dir / type_name
                type_dir.mkdir(parents=True, exist_ok=True)

                for item_name in items:
                    src_path = self.indexer.get_item_path(source_name, type_name, item_name)
                    if not src_path:
                        continue

                    # Preserve subdirectory structure
                    rel_path = Path(item_name + ".md")
                    dst_path = type_dir / rel_path
                    dst_path.parent.mkdir(parents=True, exist_ok=True)

                    shutil.copy2(src_path, dst_path)

    def _copy_resources_incremental(
        self,
        profile_dir: Path,
        selections: dict[str, SourceSelection],
        incremental: IncrementalBuilder,
    ) -> set[Path]:
        """Copy resources with incremental build support.

        Args:
            profile_dir: Target profile directory
            selections: Resources to copy
            incremental: Incremental build tracker

        Returns:
            Set of all destination files that should exist
        """
        current_files: set[Path] = set()

        for source_name, selection in selections.items():
            for type_name in SOURCE_TYPES:
                items = getattr(selection, type_name, [])
                if not items:
                    continue

                type_dir = profile_dir / type_name
                type_dir.mkdir(parents=True, exist_ok=True)

                for item_name in items:
                    src_path = self.indexer.get_item_path(source_name, type_name, item_name)
                    if not src_path:
                        continue

                    # Preserve subdirectory structure
                    rel_path = Path(item_name + ".md")
                    dst_path = type_dir / rel_path
                    dst_path.parent.mkdir(parents=True, exist_ok=True)

                    # Track this file
                    current_files.add(dst_path)

                    # Check if update needed
                    if incremental.needs_update(src_path, dst_path):
                        shutil.copy2(src_path, dst_path)
                        incremental.record_file(dst_path, src_path)

        return current_files

    def _detect_auto_fetch(
        self, profile: ProfileConfig, project_dir: Path
    ) -> dict[str, Any]:
        """Detect auto-fetch additions based on project files."""
        result = {
            "matched": False,
            "detected_files": [],
            "additions": {},
        }

        if not profile.auto_fetch:
            return result

        # Check detect rules in order
        for rule in profile.auto_fetch.detect:
            file_path = project_dir / rule.file
            if file_path.exists():
                result["matched"] = True
                result["detected_files"].append(rule.file)

                if rule.source not in result["additions"]:
                    result["additions"][rule.source] = {"skills": []}

                for skill in rule.skills:
                    if skill not in result["additions"][rule.source]["skills"]:
                        result["additions"][rule.source]["skills"].append(skill)

        # If no match, use default
        if not result["matched"] and profile.auto_fetch.default:
            default = profile.auto_fetch.default
            source = default.get("source")
            skills = default.get("skills", [])

            if source:
                result["additions"][source] = {"skills": skills}

        return result

    def inspect_profile(self, profile_name: str) -> dict[str, Any] | None:
        """Inspect a profile and show all its contents including inherited resources.

        Args:
            profile_name: Name of the profile to inspect

        Returns:
            Detailed profile information or None if not found
        """
        profile = self._load_profile_config(profile_name)
        if not profile:
            return None

        # Get inheritance chain
        inheritance_chain = self._get_inheritance_chain(profile_name)

        # Get merged resources (including inherited)
        merged_selection = self._merge_inheritance(profile)

        # Build detailed resource info
        resources: dict[str, dict[str, list[dict[str, str]]]] = {}
        total_resources = 0

        for source_name, selection in merged_selection.items():
            resources[source_name] = {
                "agents": [],
                "skills": [],
                "commands": [],
                "rules": [],
            }

            for type_name in SOURCE_TYPES:
                items = getattr(selection, type_name, [])
                for item_name in items:
                    # Check if item exists in index
                    exists = self.indexer.item_exists(source_name, type_name, item_name)
                    item_info = {
                        "name": item_name,
                        "exists": exists,
                        "path": str(self.indexer.get_item_path(source_name, type_name, item_name)) if exists else None,
                    }
                    resources[source_name][type_name].append(item_info)
                    total_resources += 1

        # Get profile sources (directly defined, not inherited)
        direct_sources = set(profile.from_sources.keys())
        inherited_sources = set(merged_selection.keys()) - direct_sources

        return {
            "name": profile.name,
            "description": profile.description,
            "extends": profile.extends,
            "inheritance_chain": inheritance_chain,
            "direct_sources": list(direct_sources),
            "inherited_sources": list(inherited_sources),
            "auto_fetch": profile.auto_fetch.model_dump() if profile.auto_fetch else None,
            "resources": resources,
            "total_resources": total_resources,
            "config_file": str(constants.PROFILES_DIR / f"{profile_name}.json"),
            "built_dir": str(constants.PROFILES_DIR / profile_name),
        }

    def list_available_skills(self, source_name: str | None = None) -> dict[str, list[str]]:
        """List all available skills from indexed sources.

        Args:
            source_name: Optional source name to filter by

        Returns:
            Dict mapping source names to lists of skill names
        """
        result: dict[str, list[str]] = {}

        if source_name:
            # List skills from specific source
            skills = self.indexer.list_items(source_name, "skills")
            if skills:
                result[source_name] = sorted(skills)
        else:
            # List skills from all sources
            for src in self.config.sources:
                skills = self.indexer.list_items(src.name, "skills")
                if skills:
                    result[src.name] = sorted(skills)

        return result

    def list_available_agents(self, source_name: str | None = None) -> dict[str, list[str]]:
        """List all available agents from indexed sources.

        Args:
            source_name: Optional source name to filter by

        Returns:
            Dict mapping source names to lists of agent names
        """
        result: dict[str, list[str]] = {}

        if source_name:
            agents = self.indexer.list_items(source_name, "agents")
            if agents:
                result[source_name] = sorted(agents)
        else:
            for src in self.config.sources:
                agents = self.indexer.list_items(src.name, "agents")
                if agents:
                    result[src.name] = sorted(agents)

        return result

    def suggest_profile(self, project_dir: Path | None = None) -> dict[str, Any]:
        """Suggest a profile based on project files.

        Args:
            project_dir: Project directory to analyze (defaults to current directory)

        Returns:
            Suggestion with detected files and recommended skills
        """
        if project_dir is None:
            project_dir = Path.cwd()

        result = {
            "project_dir": str(project_dir),
            "detected_files": [],
            "suggested_sources": {},
            "suggested_profile": None,
        }

        # Detect project type based on common files
        detection_rules = [
            ("requirements.txt", "python", "python-dev"),
            ("pyproject.toml", "python", "python-dev"),
            ("setup.py", "python", "python-dev"),
            ("package.json", "notebooklm", "notebooklm-integration"),
            ("Cargo.toml", "rust", "rust-dev"),
            ("go.mod", "golang", "go-dev"),
            ("pom.xml", "java", "java-dev"),
            ("build.gradle", "java", "java-dev"),
            ("Gemfile", "ruby", "ruby-dev"),
            ("composer.json", "php", "php-dev"),
        ]

        detected_types = set()
        for filename, source, skill in detection_rules:
            if (project_dir / filename).exists():
                result["detected_files"].append(filename)
                detected_types.add((source, skill))

        # Build suggestions
        for source, skill in detected_types:
            if source not in result["suggested_sources"]:
                result["suggested_sources"][source] = {"skills": []}
            result["suggested_sources"][source]["skills"].append(skill)

        # Suggest a profile name based on detected types
        if detected_types:
            type_names = sorted(set(t[0] for t in detected_types))
            if len(type_names) == 1:
                result["suggested_profile"] = f"coding-{type_names[0]}"
            else:
                result["suggested_profile"] = "coding-full"

        return result

    def get_available_items(self, source_name: str, type_name: str) -> list[dict[str, Any]]:
        """Get detailed information about all items of a specific type in a source.

        Args:
            source_name: Source name
            type_name: Type (agents, skills, commands, rules)

        Returns:
            List of item details including name, description, and metadata
        """
        items = []
        index = self.indexer.load_index(source_name)
        if not index:
            return items

        contents = index.get("contents", {})
        type_contents = contents.get(type_name, {})

        for item_name in type_contents:
            item_path = self.indexer.get_item_path(source_name, type_name, item_name)
            if item_path and item_path.exists():
                content = item_path.read_text(encoding="utf-8")
                # Extract first paragraph as description
                lines = content.strip().split("\n")
                description = ""
                for line in lines:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        description = line
                        break

                items.append({
                    "name": item_name,
                    "description": description[:100] + "..." if len(description) > 100 else description,
                    "source": source_name,
                    "type": type_name,
                    "path": str(item_path),
                })

        return sorted(items, key=lambda x: x["name"])

    def get_item_detail(self, source_name: str, type_name: str, item_name: str) -> dict[str, Any] | None:
        """Get detailed information about a specific item.

        Args:
            source_name: Source name
            type_name: Type (agents, skills, commands, rules)
            item_name: Item name

        Returns:
            Item details including full content, or None if not found
        """
        item_path = self.indexer.get_item_path(source_name, type_name, item_name)
        if not item_path or not item_path.exists():
            return None

        content = item_path.read_text(encoding="utf-8")

        # Parse markdown structure
        lines = content.split("\n")
        title = ""
        description = ""
        sections = {}
        current_section = None
        current_content = []

        for line in lines:
            if line.startswith("# "):
                title = line[2:].strip()
            elif line.startswith("## "):
                if current_section:
                    sections[current_section] = "\n".join(current_content).strip()
                current_section = line[3:].strip()
                current_content = []
            elif line.strip() and not description:
                description = line.strip()
            elif current_section is not None:
                current_content.append(line)

        if current_section:
            sections[current_section] = "\n".join(current_content).strip()

        return {
            "name": item_name,
            "type": type_name,
            "source": source_name,
            "title": title,
            "description": description,
            "sections": sections,
            "content": content,
            "path": str(item_path),
        }

    def add_to_profile(self, profile_name: str, source_name: str, item_type: str, item_name: str) -> bool:
        """Add an item from a source to a profile.

        Args:
            profile_name: Profile name
            source_name: Source name
            item_type: Type (agents, skills, commands, rules)
            item_name: Item name

        Returns:
            True if successful
        """
        profile = self._load_profile_config(profile_name)
        if not profile:
            return False

        # Check if source exists in profile
        if source_name not in profile.from_sources:
            profile.from_sources[source_name] = SourceSelection()

        selection = profile.from_sources[source_name]
        items = getattr(selection, item_type, [])

        if item_name not in items:
            items.append(item_name)
            setattr(selection, item_type, items)

        # Save updated profile
        profile_file = constants.PROFILES_DIR / f"{profile_name}.json"
        with open(profile_file, "w", encoding="utf-8") as f:
            json.dump(profile.model_dump(by_alias=True), f, indent=2)

        return True

    def remove_from_profile(self, profile_name: str, source_name: str, item_type: str, item_name: str) -> bool:
        """Remove an item from a profile.

        Args:
            profile_name: Profile name
            source_name: Source name
            item_type: Type (agents, skills, commands, rules)
            item_name: Item name

        Returns:
            True if successful
        """
        profile = self._load_profile_config(profile_name)
        if not profile or source_name not in profile.from_sources:
            return False

        selection = profile.from_sources[source_name]
        items = getattr(selection, item_type, [])

        if item_name in items:
            items.remove(item_name)
            setattr(selection, item_type, items)

            # Remove source if empty
            if all(len(getattr(selection, t, [])) == 0 for t in ["agents", "skills", "commands", "rules"]):
                del profile.from_sources[source_name]

            # Save updated profile
            profile_file = constants.PROFILES_DIR / f"{profile_name}.json"
            with open(profile_file, "w", encoding="utf-8") as f:
                json.dump(profile.model_dump(by_alias=True), f, indent=2)

            return True

        return False

    def get_profile_source_usage(self, profile_name: str) -> dict[str, Any]:
        """Get detailed source usage information for a profile.

        Args:
            profile_name: Profile name

        Returns:
            Dict with source usage details
        """
        profile = self._load_profile_config(profile_name)
        if not profile:
            return {}

        result = {
            "profile": profile_name,
            "direct_sources": {},
            "inherited_sources": {},
            "available_sources": [],
        }

        # Get merged selection to see inherited sources
        merged = self._merge_inheritance(profile)

        # Direct sources
        for source_name, selection in profile.from_sources.items():
            result["direct_sources"][source_name] = {
                "agents": selection.agents,
                "skills": selection.skills,
                "commands": selection.commands,
                "rules": selection.rules,
            }

        # Inherited sources (in merged but not in direct)
        for source_name, selection in merged.items():
            if source_name not in profile.from_sources:
                result["inherited_sources"][source_name] = {
                    "agents": selection.agents,
                    "skills": selection.skills,
                    "commands": selection.commands,
                    "rules": selection.rules,
                }

        # Available sources (configured but not used)
        configured = {s.name for s in self.config.sources}
        used = set(merged.keys())
        result["available_sources"] = sorted(configured - used)

        return result
