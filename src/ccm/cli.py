"""CLI for CCM."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import click

from ccm.builder import ProfileBuilder
from ccm.config import Config
from ccm.constants import SCHEMA_VERSION, VERSION
from ccm.indexer import Indexer
from ccm.profile_config import SourceSelection
from ccm.project import ProjectManager
from ccm.source import SourceManager
from ccm.updater import CleanupManager, UpdateManager
from ccm.version import VersionManager


@click.group()
@click.version_option(version=VERSION, prog_name="ccm")
def cli() -> None:
    """Claude Code Manager - Profile and source management for Claude Code."""
    pass


# Source commands
@cli.group()
def source() -> None:
    """Manage source repositories."""
    pass


@source.command("add")
@click.argument("name")
@click.argument("github")
@click.option("--ref", default="main", help="Git ref (branch, tag, or commit)")
def source_add(name: str, github: str, ref: str) -> None:
    """Add a new source repository."""
    manager = SourceManager()

    try:
        source = manager.add(name, github, ref)
        click.echo(f"✓ Added source '{source.name}' from {source.github}")
    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Error cloning repository: {e}", err=True)
        sys.exit(1)


@source.command("list")
def source_list() -> None:
    """List all configured sources."""
    manager = SourceManager()
    sources = manager.list()

    if not sources:
        click.echo("No sources configured.")
        return

    click.echo("Sources:")
    for src in sources:
        click.echo(f"  {src.name}: {src.github} (ref: {src.ref})")


@source.command("show")
@click.argument("name")
def source_show(name: str) -> None:
    """Show details of a source."""
    manager = SourceManager()
    info = manager.show(name)

    if not info:
        click.echo(f"Source '{name}' not found.", err=True)
        sys.exit(1)

    click.echo(f"Source: {info['name']}")
    click.echo(f"  GitHub: {info['github']}")
    click.echo(f"  Ref: {info['ref']}")
    click.echo(f"  Commit: {info['commit'][:8] if info['commit'] != 'unknown' else 'unknown'}")
    click.echo(f"  Last updated: {info['last_updated']}")

    contents = info.get("contents", {})
    if contents:
        click.echo("\nContents:")
        for type_name, items in contents.items():
            click.echo(f"  {type_name}: {len(items)} items")


@source.command("update")
@click.argument("name", required=False)
@click.option("--all", "update_all", is_flag=True, help="Update all sources")
@click.option("--async", "use_async", is_flag=True, help="Update concurrently (faster for multiple sources)")
def source_update(name: str | None, update_all: bool, use_async: bool) -> None:
    """Update source(s) to latest version."""
    if update_all and use_async:
        # Use async concurrent update
        import asyncio
        from ccm.async_source import AsyncSourceManager

        async def do_async_update():
            with AsyncSourceManager() as manager:
                sources = manager.list()
                if not sources:
                    click.echo("No sources to update.")
                    return

                click.echo(f"Updating {len(sources)} sources concurrently...\n")

                def progress_callback(source_name: str, result: dict):
                    if "error" in result:
                        click.echo(f"  ✗ {source_name}: {result['error']}", err=True)
                    else:
                        _print_update_result(source_name, result)

                results = await manager.update_all_async(progress_callback)

                # Summary
                updated = sum(1 for r in results if r.get("updated"))
                errors = sum(1 for r in results if "error" in r)
                click.echo(f"\nSummary: {updated} updated, {errors} errors")

        asyncio.run(do_async_update())
    elif update_all:
        # Sequential update
        manager = SourceManager()
        sources = manager.list()
        if not sources:
            click.echo("No sources to update.")
            return

        for src in sources:
            click.echo(f"\nUpdating {src.name}...")
            try:
                result = manager.update(src.name)
                _print_update_result(src.name, result)
            except Exception as e:
                click.echo(f"  Error: {e}", err=True)
    else:
        # Single source update
        if not name:
            click.echo("Error: Specify a source name or use --all", err=True)
            sys.exit(1)

        manager = SourceManager()
        try:
            result = manager.update(name)
            _print_update_result(name, result)
        except ValueError as e:
            click.echo(f"Error: {e}", err=True)
            sys.exit(1)
        except Exception as e:
            click.echo(f"Error updating source: {e}", err=True)
            sys.exit(1)


@source.command("remove")
@click.argument("name")
@click.confirmation_option(prompt="Are you sure you want to remove this source?")
def source_remove(name: str) -> None:
    """Remove a source."""
    manager = SourceManager()

    if manager.remove(name):
        click.echo(f"✓ Removed source '{name}'")
    else:
        click.echo(f"Source '{name}' not found.", err=True)
        sys.exit(1)


@source.command("skills")
@click.argument("name", required=False)
def source_skills(name: str | None) -> None:
    """List all available skills from sources.

    If NAME is provided, list skills from that specific source.
    Otherwise, list skills from all sources.
    """
    from ccm.builder import ProfileBuilder

    builder = ProfileBuilder()
    skills = builder.list_available_skills(name)

    if not skills:
        if name:
            click.echo(f"No skills found in source '{name}'.")
        else:
            click.echo("No skills found in any source.")
        return

    if name:
        click.echo(f"Skills in source '{name}':")
        for skill in skills.get(name, []):
            click.echo(f"  - {skill}")
    else:
        click.echo("Available skills by source:")
        for source_name, skill_list in skills.items():
            click.echo(f"\n  {source_name} ({len(skill_list)}):")
            for skill in skill_list[:10]:
                click.echo(f"    - {skill}")
            if len(skill_list) > 10:
                click.echo(f"    ... and {len(skill_list) - 10} more")


@source.command("agents")
@click.argument("name", required=False)
@click.option("--detail", "-d", is_flag=True, help="Show detailed description")
def source_agents(name: str | None, detail: bool) -> None:
    """List all available agents from sources.

    If NAME is provided, list agents from that specific source.
    Otherwise, list agents from all sources.
    """
    from ccm.builder import ProfileBuilder

    builder = ProfileBuilder()

    if detail and name:
        # Show detailed info for each agent
        items = builder.get_available_items(name, "agents")
        if not items:
            click.echo(f"No agents found in source '{name}'.")
            return
        click.echo(f"Agents in source '{name}':\n")
        for item in items:
            click.echo(f"  {item['name']}")
            if item['description']:
                click.echo(f"    {item['description']}")
            click.echo()
    else:
        agents = builder.list_available_agents(name)
        if not agents:
            if name:
                click.echo(f"No agents found in source '{name}'.")
            else:
                click.echo("No agents found in any source.")
            return

        if name:
            click.echo(f"Agents in source '{name}':")
            for agent in agents.get(name, []):
                click.echo(f"  - {agent}")
        else:
            click.echo("Available agents by source:")
            for source_name, agent_list in agents.items():
                click.echo(f"\n  {source_name} ({len(agent_list)}):")
                for agent in agent_list[:10]:
                    click.echo(f"    - {agent}")
                if len(agent_list) > 10:
                    click.echo(f"    ... and {len(agent_list) - 10} more")


@source.command("show")
@click.argument("source_name")
@click.argument("item_type", type=click.Choice(["agents", "skills", "commands", "rules"]))
@click.argument("item_name")
def source_show_item(source_name: str, item_type: str, item_name: str) -> None:
    """Show detailed information about a specific item in a source."""
    from ccm.builder import ProfileBuilder

    builder = ProfileBuilder()
    detail = builder.get_item_detail(source_name, item_type, item_name)

    if not detail:
        click.echo(f"{item_type[:-1]} '{item_name}' not found in source '{source_name}'.", err=True)
        sys.exit(1)

    click.echo(f"{detail['title'] or item_name}")
    click.echo(f"Source: {source_name}")
    click.echo(f"Type: {item_type}")
    if detail['description']:
        click.echo(f"\n{detail['description']}")

    if detail['sections']:
        click.echo("\nSections:")
        for section_name, content in detail['sections'].items():
            preview = content.replace('\n', ' ')[:80]
            click.echo(f"  - {section_name}: {preview}...")


@source.command("browse")
@click.argument("source_name")
def source_browse(source_name: str) -> None:
    """Browse all content in a source with descriptions."""
    from ccm.builder import ProfileBuilder

    builder = ProfileBuilder()
    source = builder.config.get_source(source_name)
    if not source:
        click.echo(f"Source '{source_name}' not found.", err=True)
        sys.exit(1)

    click.echo(f"Source: {source_name}")
    click.echo(f"Repository: {source.github}")
    click.echo(f"Ref: {source.ref}")
    click.echo("")

    for type_name in ["agents", "skills", "commands", "rules"]:
        items = builder.get_available_items(source_name, type_name)
        if items:
            click.echo(f"\n{type_name.upper()} ({len(items)}):")
            for item in items:
                click.echo(f"\n  {item['name']}")
                if item['description']:
                    desc = item['description'][:60] + "..." if len(item['description']) > 60 else item['description']
                    click.echo(f"    {desc}")

            click.echo(f"\n  Use 'ccm source show {source_name} {type_name} <name>' for details")
            click.echo()


def _print_update_result(name: str, result: dict[str, Any]) -> None:
    """Print update result."""
    if not result.get("updated"):
        click.echo(f"  {name} is already up to date.")
        return

    click.echo(f"  Updated {name}")
    click.echo(f"    {result.get('old_commit', 'unknown')[:8]} -> {result.get('new_commit', 'unknown')[:8]}")

    changes = result.get("changes", {})
    if changes.get("added"):
        click.echo(f"    + {len(changes['added'])} added")
    if changes.get("modified"):
        click.echo(f"    ~ {len(changes['modified'])} modified")
    if changes.get("removed"):
        click.echo(f"    - {len(changes['removed'])} removed")


# Profile commands (placeholders for Phase 2)
@cli.group()
def profile() -> None:
    """Manage profiles."""
    pass


@profile.command("create")
@click.argument("name")
@click.option("--extends", "parent", help="Parent profile to extend")
@click.option("--description", "-d", help="Profile description")
def profile_create(name: str, parent: str | None, description: str | None) -> None:
    """Create a new profile."""
    builder = ProfileBuilder()

    try:
        profile = builder.create_profile(
            name=name,
            description=description or "",
            extends=parent,
        )
        click.echo(f"✓ Created profile '{profile.name}'")
        if profile.extends:
            click.echo(f"  Extends: {profile.extends}")
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@profile.command("list")
def profile_list() -> None:
    """List all available profiles."""
    builder = ProfileBuilder()
    profiles = builder.list_profiles()

    if not profiles:
        click.echo("No profiles available.")
        return

    click.echo("Profiles:")
    for name in profiles:
        info = builder.show_profile(name)
        if info:
            desc = info.get("description", "")
            extends = info.get("extends")
            line = f"  {name}"
            if extends:
                line += f" (extends: {extends})"
            if desc:
                line += f" - {desc}"
            click.echo(line)
        else:
            click.echo(f"  {name}")


@profile.command("validate")
@click.argument("name")
def profile_validate(name: str) -> None:
    """Validate a profile configuration."""
    builder = ProfileBuilder()
    errors = builder.validate(name)

    if errors:
        click.echo(f"Profile '{name}' has errors:")
        for error in errors:
            click.echo(f"  ✗ {error}")
        sys.exit(1)
    else:
        click.echo(f"✓ Profile '{name}' is valid")


@profile.command("build")
@click.argument("name")
def profile_build(name: str) -> None:
    """Build a profile."""
    builder = ProfileBuilder()

    try:
        profile_dir = builder.build(name)
        click.echo(f"✓ Built profile '{name}'")
        click.echo(f"  Location: {profile_dir}")
    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Error building profile: {e}", err=True)
        sys.exit(1)


@profile.command("show")
@click.argument("name")
def profile_show(name: str) -> None:
    """Show profile details."""
    builder = ProfileBuilder()
    info = builder.show_profile(name)

    if not info:
        click.echo(f"Profile '{name}' not found.", err=True)
        sys.exit(1)

    click.echo(f"Profile: {info['name']}")
    if info.get("description"):
        click.echo(f"  Description: {info['description']}")
    if info.get("extends"):
        click.echo(f"  Extends: {info['extends']}")
    if info.get("inheritance_chain"):
        click.echo(f"  Inheritance: {' -> '.join(info['inheritance_chain'])}")

    resources = info.get("resources", {})
    if resources:
        click.echo("\n  Resources:")
        for source, types in resources.items():
            total = sum(len(v) for v in types.values())
            if total > 0:
                click.echo(f"    From {source}:")
                for type_name, items in types.items():
                    if items:
                        click.echo(f"      {type_name}: {', '.join(items[:3])}{'...' if len(items) > 3 else ''}")


@profile.command("inspect")
@click.argument("name")
@click.option("--show-paths", is_flag=True, help="Show file paths for each resource")
def profile_inspect(name: str, show_paths: bool) -> None:
    """Inspect profile with detailed resource information."""
    builder = ProfileBuilder()
    info = builder.inspect_profile(name)

    if not info:
        click.echo(f"Profile '{name}' not found.", err=True)
        sys.exit(1)

    click.echo(f"Profile: {info['name']}")
    click.echo(f"  Description: {info.get('description') or '(none)'}")

    if info.get("extends"):
        extends = info["extends"]
        if isinstance(extends, list):
            click.echo(f"  Extends: {', '.join(extends)}")
        else:
            click.echo(f"  Extends: {extends}")

    if info.get("inheritance_chain"):
        click.echo(f"  Inheritance chain: {' -> '.join(info['inheritance_chain'])}")

    click.echo(f"\nSources:")
    if info.get("direct_sources"):
        click.echo(f"  Direct: {', '.join(info['direct_sources'])}")
    if info.get("inherited_sources"):
        click.echo(f"  Inherited: {', '.join(info['inherited_sources'])}")

    click.echo(f"\nTotal resources: {info.get('total_resources', 0)}")

    resources = info.get("resources", {})
    for source_name, types in resources.items():
        type_counts = {k: len(v) for k, v in types.items() if v}
        if type_counts:
            click.echo(f"\n  From {source_name}:")
            for type_name, items in types.items():
                if not items:
                    continue
                click.echo(f"    {type_name} ({len(items)}):")
                for item in items:
                    status = "✓" if item.get("exists") else "✗"
                    line = f"      {status} {item['name']}"
                    if show_paths and item.get("path"):
                        line += f" ({item['path']})"
                    click.echo(line)


@profile.command("suggest")
@click.option("--path", type=click.Path(), help="Project directory (default: current)")
def profile_suggest(path: str | None) -> None:
    """Suggest a profile based on project files."""
    builder = ProfileBuilder()
    project_dir = Path(path) if path else Path.cwd()

    suggestion = builder.suggest_profile(project_dir)

    click.echo(f"Project: {suggestion['project_dir']}")

    if suggestion.get("detected_files"):
        click.echo(f"\nDetected files: {', '.join(suggestion['detected_files'])}")
    else:
        click.echo("\nNo specific project files detected.")
        click.echo("This appears to be a generic project.")
        return

    if suggestion.get("suggested_sources"):
        click.echo("\nSuggested sources:")
        for source, items in suggestion["suggested_sources"].items():
            skills = items.get("skills", [])
            click.echo(f"  {source}: {', '.join(skills)}")

    if suggestion.get("suggested_profile"):
        click.echo(f"\nSuggested profile name: {suggestion['suggested_profile']}")
        click.echo("\nTo create this profile, run:")
        click.echo(f"  ccm profile create {suggestion['suggested_profile']} --description 'Auto-generated profile'")
        click.echo("\nThen add the suggested sources and skills to the profile JSON.")


@profile.command("add")
@click.argument("profile_name")
@click.argument("source_name")
@click.argument("item_type", type=click.Choice(["agents", "skills", "commands", "rules"]))
@click.argument("item_name")
def profile_add(profile_name: str, source_name: str, item_type: str, item_name: str) -> None:
    """Add an item from a source to a profile."""
    builder = ProfileBuilder()

    # Verify item exists
    detail = builder.get_item_detail(source_name, item_type, item_name)
    if not detail:
        click.echo(f"{item_type[:-1]} '{item_name}' not found in source '{source_name}'.", err=True)
        sys.exit(1)

    if builder.add_to_profile(profile_name, source_name, item_type, item_name):
        click.echo(f"✓ Added {item_type[:-1]} '{item_name}' from '{source_name}' to profile '{profile_name}'")
        click.echo(f"\n  {detail['description'][:80] if detail['description'] else 'No description'}")
        click.echo(f"\nRun 'ccm profile build {profile_name}' to apply changes.")
    else:
        click.echo(f"Failed to add to profile '{profile_name}'.", err=True)
        sys.exit(1)


@profile.command("remove")
@click.argument("profile_name")
@click.argument("source_name")
@click.argument("item_type", type=click.Choice(["agents", "skills", "commands", "rules"]))
@click.argument("item_name")
@click.confirmation_option(prompt="Are you sure you want to remove this item?")
def profile_remove(profile_name: str, source_name: str, item_type: str, item_name: str) -> None:
    """Remove an item from a profile."""
    builder = ProfileBuilder()

    if builder.remove_from_profile(profile_name, source_name, item_type, item_name):
        click.echo(f"✓ Removed {item_type[:-1]} '{item_name}' from profile '{profile_name}'")
        click.echo(f"\nRun 'ccm profile build {profile_name}' to apply changes.")
    else:
        click.echo(f"Failed to remove from profile '{profile_name}'.", err=True)
        sys.exit(1)


@profile.command("sources")
@click.argument("name")
@click.option("--available", is_flag=True, help="Show available sources not yet used")
def profile_sources(name: str, available: bool) -> None:
    """Show source usage for a profile."""
    builder = ProfileBuilder()
    usage = builder.get_profile_source_usage(name)

    if not usage:
        click.echo(f"Profile '{name}' not found.", err=True)
        sys.exit(1)

    click.echo(f"Profile: {name}\n")

    if usage.get("direct_sources"):
        click.echo("Direct sources:")
        for source, items in usage["direct_sources"].items():
            total = sum(len(v) for v in items.values() if v)
            if total > 0:
                click.echo(f"  {source} ({total} items):")
                for item_type, item_list in items.items():
                    if item_list:
                        click.echo(f"    {item_type}: {', '.join(item_list)}")

    if usage.get("inherited_sources"):
        click.echo("\nInherited sources:")
        for source, items in usage["inherited_sources"].items():
            total = sum(len(v) for v in items.values() if v)
            if total > 0:
                click.echo(f"  {source} ({total} items) - inherited")

    if available and usage.get("available_sources"):
        click.echo("\nAvailable sources (not used):")
        for source in usage["available_sources"]:
            click.echo(f"  - {source}")


@profile.command("wizard")
@click.argument("name")
def profile_wizard(name: str) -> None:
    """Interactive wizard to configure a profile."""
    builder = ProfileBuilder()
    profile = builder._load_profile_config(name)
    if not profile:
        click.echo(f"Profile '{name}' not found.", err=True)
        sys.exit(1)

    click.echo(f"Profile Configuration Wizard: {name}\n")

    # Get current usage
    usage = builder.get_profile_source_usage(name)

    # Show available sources
    if usage.get("available_sources"):
        click.echo("Available sources to add:")
        for i, source in enumerate(usage["available_sources"][:10], 1):
            click.echo(f"  {i}. {source}")

        click.echo("\nTo add items from a source, run:")
        click.echo(f"  ccm source browse <source-name>")
        click.echo(f"  ccm profile add {name} <source> <type> <item>")
    else:
        click.echo("All configured sources are already used in this profile.")

    click.echo("\nTo remove items, run:")
    click.echo(f"  ccm profile remove {name} <source> <type> <item>")


# Project commands
@cli.command()
@click.argument("profile")
def activate(profile: str) -> None:
    """Activate a profile in the current project."""
    project = ProjectManager()

    try:
        result = project.activate(profile)
        click.echo(f"✓ Activated profile '{profile}'")

        auto_fetch = result.get("auto_fetch", {})
        if auto_fetch.get("matched"):
            click.echo(f"  Auto-detected: {', '.join(auto_fetch['detected_files'])}")
    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Error activating profile: {e}", err=True)
        sys.exit(1)


@cli.command()
def deactivate() -> None:
    """Deactivate the current project's profile."""
    project = ProjectManager()

    if project.deactivate():
        click.echo("✓ Deactivated profile")
    else:
        click.echo("No active profile in this project")


@cli.command()
def status() -> None:
    """Show current project status."""
    project = ProjectManager()
    info = project.status()

    click.echo(f"Project: {info['project_dir']}")

    if info["active"]:
        click.echo(f"Profile: {info['profile']}")
        click.echo(f".claude/: {'✓' if info['claude_dir_exists'] else '✗'}")

        if info.get("links"):
            click.echo("\nLinks:")
            for name, target in info["links"].items():
                click.echo(f"  {name}: {target}")

        if info.get("claude_md_exists"):
            click.echo("\nCLAUDE.md: ✓")
    else:
        click.echo("Profile: (none)")
        click.echo("\nRun 'ccm activate <profile>' to activate a profile")


@cli.command()
def refresh() -> None:
    """Refresh project links after profile changes."""
    project = ProjectManager()

    try:
        result = project.refresh()
        click.echo(f"✓ Refreshed profile '{result['profile']}'")
    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Error refreshing: {e}", err=True)
        sys.exit(1)


# Diagnostic commands
@cli.command()
def doctor() -> None:
    """Check configuration and diagnose issues."""
    click.echo("CCM Doctor")
    click.echo(f"  CCM version: {VERSION}")

    config = Config.load()
    click.echo(f"  Schema version: {config.version}")

    # Version compatibility check
    is_compatible, message = VersionManager.check_compatibility(config)
    if is_compatible:
        click.echo(f"  ✓ {message}")
    else:
        click.echo(f"  ✗ {message}")
        sys.exit(1)

    # Sources check
    sources = config.sources
    if sources:
        click.echo(f"  ✓ {len(sources)} source(s) configured")
        for source in sources:
            indexer = Indexer()
            index = indexer.load_index(source.name)
            if index:
                click.echo(f"    ✓ {source.name}: indexed ({index.get('commit', 'unknown')[:8]})")
            else:
                click.echo(f"    ! {source.name}: not indexed")
    else:
        click.echo("  ! No sources configured")

    # Profiles check
    builder = ProfileBuilder()
    profiles = builder.list_profiles()
    if profiles:
        click.echo(f"  ✓ {len(profiles)} profile(s) available")
    else:
        click.echo("  ! No profiles available")

    # Project check
    project = ProjectManager()
    status = project.status()
    if status["active"]:
        click.echo(f"  ✓ Project active: {status['profile']}")
    else:
        click.echo("  ! No active profile in current project")


@cli.command()
@click.option("--limit", "-n", default=20, help="Number of entries to show")
def log(limit: int) -> None:
    """Show update history."""
    manager = UpdateManager()
    logs = manager.get_logs(limit=limit)

    if not logs:
        click.echo("No update history.")
        return

    click.echo(f"Update history (last {len(logs)} entries):")
    for entry in logs:
        ts = entry.get("timestamp", "unknown")[:19]
        entry_type = entry.get("type", "unknown")

        if entry_type == "source_update":
            source = entry.get("source", "unknown")
            old_c = entry.get("old_commit", "unknown")[:8]
            new_c = entry.get("new_commit", "unknown")[:8]
            click.echo(f"  {ts}  {source}: {old_c} -> {new_c}")
        elif entry_type == "profile_build":
            profile = entry.get("profile", "unknown")
            triggered = entry.get("triggered_by", "manual")
            click.echo(f"  {ts}  Built {profile} ({triggered})")


@cli.command()
def ui() -> None:
    """Launch TUI interface for interactive management."""
    try:
        from ccm.tui import run_tui
        run_tui()
    except ImportError as e:
        click.echo(f"Error: TUI dependencies not installed. Run 'pip install textual'", err=True)
        sys.exit(1)


@cli.group()
def clean() -> None:
    """Clean up caches and unused resources."""
    pass


@clean.command("sources")
@click.option("--dry-run", is_flag=True, help="Show what would be removed without removing")
def clean_sources(dry_run: bool) -> None:
    """Clean up unused sources."""
    manager = CleanupManager()
    unused = manager.get_unused_sources()

    if not unused:
        click.echo("No unused sources to clean up.")
        return

    click.echo(f"Found {len(unused)} unused source(s):")
    for source in unused:
        click.echo(f"  - {source}")

    if dry_run:
        click.echo("\n(Dry run - nothing removed)")
        return

    if click.confirm("\nRemove these sources?"):
        removed = manager.cleanup_all_unused()
        click.echo(f"✓ Removed {len(removed)} source(s)")


@clean.command("profiles")
@click.option("--dry-run", is_flag=True, help="Show what would be removed without removing")
@click.option("--keep-configs", is_flag=True, default=True, help="Keep profile config files")
def clean_profiles(dry_run: bool, keep_configs: bool) -> None:
    """Clean up built profiles."""
    manager = CleanupManager()
    built = manager.get_built_profiles()

    if not built:
        click.echo("No built profiles to clean up.")
        return

    click.echo(f"Found {len(built)} built profile(s):")
    for profile in built:
        click.echo(f"  - {profile}")

    if dry_run:
        click.echo("\n(Dry run - nothing removed)")
        return

    if click.confirm("\nRemove these built profiles?"):
        result = manager.cleanup_profiles(keep_configs=keep_configs)
        removed = result.get("removed", [])
        click.echo(f"✓ Removed {len(removed)} item(s)")


@clean.command("index")
@click.option("--dry-run", is_flag=True, help="Show what would be removed without removing")
def clean_index(dry_run: bool) -> None:
    """Clean up index cache."""
    manager = CleanupManager()
    summary = manager.get_cleanup_summary()
    indexes = summary["index"]["files"]

    if not indexes:
        click.echo("No index files to clean up.")
        return

    click.echo(f"Found {len(indexes)} index file(s):")
    for idx in indexes:
        click.echo(f"  - {idx}")

    if dry_run:
        click.echo("\n(Dry run - nothing removed)")
        return

    if click.confirm("\nRemove all index files?"):
        removed = manager.cleanup_index()
        click.echo(f"✓ Removed {len(removed)} index file(s)")


@clean.command("logs")
@click.option("--keep", default=100, help="Number of recent log entries to keep")
@click.option("--dry-run", is_flag=True, help="Show what would be removed without removing")
def clean_logs(keep: int, dry_run: bool) -> None:
    """Clean up old log entries."""
    manager = CleanupManager()
    summary = manager.get_cleanup_summary()
    total = summary["logs"]["entries"]

    if total <= keep:
        click.echo(f"Log has {total} entries (threshold: {keep}). Nothing to clean.")
        return

    to_remove = total - keep
    click.echo(f"Found {total} log entries, will keep {keep}, remove {to_remove}")

    if dry_run:
        click.echo("\n(Dry run - nothing removed)")
        return

    result = manager.cleanup_logs(keep_recent=keep)
    click.echo(f"✓ Removed {result['removed_count']} log entries, kept {result['kept_count']}")


@clean.command("project")
@click.option("--path", type=click.Path(), help="Project directory (default: current)")
@click.option("--dry-run", is_flag=True, help="Show what would be removed without removing")
def clean_project(path: str | None, dry_run: bool) -> None:
    """Clean up project-level .claude/ directory."""
    manager = CleanupManager()
    project_dir = Path(path) if path else Path.cwd()
    claude_dir = project_dir / ".claude"

    if not claude_dir.exists():
        click.echo(f"No .claude/ directory found in {project_dir}")
        return

    # Show what will be removed
    links = [item.name for item in claude_dir.iterdir() if item.is_symlink()]
    files = [item.name for item in claude_dir.iterdir() if item.is_file() and not item.is_symlink()]
    dirs = [item.name for item in claude_dir.iterdir() if item.is_dir()]

    click.echo(f"Found .claude/ directory in {project_dir}:")
    if links:
        click.echo(f"  Symlinks ({len(links)}): {', '.join(links)}")
    if files:
        click.echo(f"  Files ({len(files)}): {', '.join(files)}")
    if dirs:
        click.echo(f"  Directories ({len(dirs)}): {', '.join(dirs)}")

    if dry_run:
        click.echo("\n(Dry run - nothing removed)")
        return

    if click.confirm("\nRemove project .claude/ directory?"):
        result = manager.cleanup_project(project_dir)
        removed = len(result["removed_links"]) + len(result["removed_files"]) + len(result["removed_dirs"])
        click.echo(f"✓ Removed {removed} item(s) from .claude/")
        if result.get("claude_dir_removed"):
            click.echo("  .claude/ directory removed")


@clean.command("all")
@click.option("--dry-run", is_flag=True, help="Show what would be removed without removing")
def clean_all(dry_run: bool) -> None:
    """Full cleanup - removes unused sources, built profiles, and index cache."""
    manager = CleanupManager()
    summary = manager.get_cleanup_summary()

    click.echo("Cleanup summary:")
    click.echo(f"  Unused sources: {len(summary['sources']['unused'])}")
    click.echo(f"  Built profiles: {len(summary['profiles']['built'])}")
    click.echo(f"  Index files: {len(summary['index']['files'])}")
    click.echo(f"  Log entries: {summary['logs']['entries']}")

    if dry_run:
        click.echo("\n(Dry run - nothing removed)")
        return

    if not click.confirm("\nPerform full cleanup?"):
        return

    # Clean unused sources
    removed_sources = manager.cleanup_all_unused()
    click.echo(f"✓ Removed {len(removed_sources)} unused source(s)")

    # Clean built profiles
    result = manager.cleanup_profiles(keep_configs=True)
    click.echo(f"✓ Removed {len(result['removed'])} built profile(s)")

    # Clean index
    removed_index = manager.cleanup_index()
    click.echo(f"✓ Removed {len(removed_index)} index file(s)")

    click.echo("\nFull cleanup complete!")


@clean.command("status")
def clean_status() -> None:
    """Show cleanup status and what can be cleaned."""
    manager = CleanupManager()
    summary = manager.get_cleanup_summary()

    click.echo("CCM Cleanup Status")
    click.echo("")

    # Sources
    click.echo("Sources:")
    click.echo(f"  Total configured: {summary['sources']['total']}")
    if summary['sources']['unused']:
        click.echo(f"  Unused (can be cleaned): {', '.join(summary['sources']['unused'])}")
    else:
        click.echo("  All sources are in use")

    # Profiles
    click.echo("\nProfiles:")
    click.echo(f"  Config files: {len(summary['profiles']['configs'])}")
    if summary['profiles']['built']:
        click.echo(f"  Built profiles (can be cleaned): {', '.join(summary['profiles']['built'])}")
    else:
        click.echo("  No built profiles")

    # Index
    click.echo("\nIndex:")
    if summary['index']['files']:
        click.echo(f"  Indexed sources: {', '.join(summary['index']['files'])}")
    else:
        click.echo("  No index files")

    # Logs
    click.echo("\nLogs:")
    click.echo(f"  Update log entries: {summary['logs']['entries']}")

    # Disk usage
    click.echo("\nDisk Usage:")
    for category, size in summary['disk_usage'].items():
        size_mb = size / (1024 * 1024)
        click.echo(f"  {category}: {size_mb:.2f} MB")


def main() -> None:
    """Entry point."""
    cli()


if __name__ == "__main__":
    main()
