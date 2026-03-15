"""TUI for CCM using Textual."""

from __future__ import annotations

from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import (
    Footer,
    Header,
    Label,
    ListItem,
    ListView,
    Markdown,
    Static,
    TabbedContent,
    TabPane,
    Button,
    Input,
    RadioButton,
    RadioSet,
)
from textual.reactive import reactive

from ccm.builder import ProfileBuilder


class SourceBrowser(Static):
    """Source browser widget."""

    def __init__(self) -> None:
        super().__init__()
        self.builder = ProfileBuilder()
        self.current_source: str | None = None
        self.current_type: str = "agents"

    def compose(self) -> ComposeResult:
        with Horizontal():
            # Left sidebar: source list
            with Vertical(classes="sidebar"):
                yield Label("Sources", classes="title")
                source_items = []
                for s in self.builder.config.sources:
                    item = ListItem(Label(s.name))
                    item._ccm_source_name = s.name
                    source_items.append(item)
                yield ListView(*source_items, id="source-list")

            # Middle: type selector and item list
            with Vertical(classes="item-list"):
                yield Label("Type", classes="title")
                with RadioSet(id="type-selector"):
                    yield RadioButton("Agents", value=True)
                    yield RadioButton("Skills")
                    yield RadioButton("Commands")
                    yield RadioButton("Rules")
                yield Label("Items", classes="title")
                yield Input(placeholder="Filter items...", id="item-filter")
                yield ListView(id="item-list")

            # Right: detail view
            with Vertical(classes="detail-view"):
                yield Label("Detail", classes="title")
                yield Markdown("Select a source and item to view details", id="detail-md")

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Handle list selection."""
        list_view = event.list_view

        if list_view.id == "source-list":
            # Source list
            if hasattr(event.item, '_ccm_source_name'):
                self.current_source = event.item._ccm_source_name
                self.update_item_list()
        elif list_view.id == "item-list":
            # Item list
            if hasattr(event.item, '_ccm_item_name'):
                self.show_detail(event.item._ccm_item_name)

    def on_radio_set_changed(self, event: RadioSet.Changed) -> None:
        """Handle type selection via radio buttons."""
        type_map = {
            "Agents": "agents",
            "Skills": "skills",
            "Commands": "commands",
            "Rules": "rules",
        }
        selected_label = str(event.pressed.label)
        if selected_label in type_map:
            self.current_type = type_map[selected_label]
            self.update_item_list()

    def on_input_changed(self, event: Input.Changed) -> None:
        """Handle filter input."""
        if event.input.id == "item-filter":
            self.update_item_list(event.value)

    def update_item_list(self, filter_text: str = "") -> None:
        """Update item list based on selected source and type."""
        if not self.current_source:
            return

        item_list = self.query_one("#item-list", ListView)
        # Remove existing items
        for child in list(item_list.children):
            child.remove()

        items = self.builder.get_available_items(self.current_source, self.current_type)
        filter_lower = filter_text.lower()

        for item in items:
            # Show full path in display
            display_text = f"{self.current_source}:{self.current_type}/{item['name']}"
            if not filter_text or filter_lower in item['name'].lower():
                list_item = ListItem(Label(display_text))
                list_item._ccm_item_name = item['name']
                item_list.append(list_item)

    def show_detail(self, item_name: str) -> None:
        """Show item detail."""
        if not self.current_source:
            return

        detail = self.builder.get_item_detail(self.current_source, self.current_type, item_name)
        if detail:
            md = self.query_one("#detail-md", Markdown)
            # Show full reference path
            full_path = f"{self.current_source}:{self.current_type}/{item_name}"
            content = f"""# {detail['title'] or item_name}

**Full Reference:** `{full_path}`

**Source:** {self.current_source}
**Type:** {self.current_type}

{detail['description']}

## Full Content

{detail['content'][:2000]}{'...' if len(detail['content']) > 2000 else ''}
"""
            md.update(content)

    def navigate_to(self, source: str, type_name: str, item_name: str) -> None:
        """Navigate to a specific source/type/item."""
        self.current_source = source
        self.current_type = type_name

        # Update source list selection
        source_list = self.query_one("#source-list", ListView)
        for i, child in enumerate(source_list.children):
            if hasattr(child, '_ccm_source_name') and child._ccm_source_name == source:
                source_list.index = i
                break

        # Update type selector (RadioSet)
        radio_set = self.query_one("#type-selector", RadioSet)
        type_map = {"agents": 0, "skills": 1, "commands": 2, "rules": 3}
        if type_name in type_map:
            idx = type_map[type_name]
            # Get the radio button at the index and press it
            buttons = list(radio_set.query(RadioButton))
            if 0 <= idx < len(buttons):
                buttons[idx].value = True

        # Update item list
        self.update_item_list()

        # Show detail
        self.show_detail(item_name)


class ProfileConfigurator(Static):
    """Profile configurator with add/remove functionality."""

    selected_profile: reactive[str | None] = reactive(None)
    selected_source: reactive[str | None] = reactive(None)
    selected_item: reactive[str | None] = reactive(None)
    selected_type: reactive[str] = reactive("agents")
    selected_profile_item: reactive[dict | None] = reactive(None)

    def __init__(self) -> None:
        super().__init__()
        self.builder = ProfileBuilder()

    def compose(self) -> ComposeResult:
        with Horizontal():
            # Left: profile list
            with Vertical(classes="sidebar"):
                yield Label("Profiles", classes="title")
                profiles = self.builder.list_profiles()
                profile_items = []
                for p in profiles:
                    item = ListItem(Label(p))
                    item._ccm_profile_name = p
                    profile_items.append(item)
                yield ListView(*profile_items, id="profile-list")

            # Middle: current profile details with clickable items
            with Vertical(classes="profile-detail"):
                yield Label("Profile Details", classes="title")
                yield Markdown("Select a profile to view details", id="profile-md")
                yield Label("Profile Items (click to select):", classes="subtitle")
                yield ListView(id="profile-items-list")
                with Horizontal(classes="button-row"):
                    yield Button("View Details", id="btn-view-in-source", variant="primary")
                    yield Button("Remove", id="btn-remove-from-detail", variant="error")

            # Right: available items to add
            with Vertical(classes="add-panel"):
                yield Label("Add to Profile", classes="title")
                yield Label("1. Select Source:", classes="subtitle")
                source_items = []
                for s in self.builder.config.sources:
                    item = ListItem(Label(s.name))
                    item._ccm_source_name = s.name
                    source_items.append(item)
                yield ListView(*source_items, id="add-source-list")

                yield Label("2. Select Type:", classes="subtitle")
                with RadioSet(id="add-type-list"):
                    yield RadioButton("Agents", value=True)
                    yield RadioButton("Skills")
                    yield RadioButton("Commands")
                    yield RadioButton("Rules")

                yield Label("3. Select Item:", classes="subtitle")
                yield Input(placeholder="Filter items...", id="add-item-filter")
                yield ListView(id="add-item-list")

                with Horizontal(classes="button-row"):
                    yield Button("Add to Profile", id="btn-add", variant="primary")

    def watch_selected_profile(self, profile: str | None) -> None:
        """Update profile details when selection changes."""
        if profile:
            self.update_profile_detail()

    def update_profile_detail(self) -> None:
        """Update profile detail view."""
        if not self.selected_profile:
            return

        info = self.builder.inspect_profile(self.selected_profile)
        if not info:
            return

        # Update markdown summary
        md = self.query_one("#profile-md", Markdown)
        content = f"""# {info['name']}

**Description:** {info.get('description', 'N/A')}

**Extends:** {info.get('extends', 'None')}

**Inheritance Chain:** {' -> '.join(info.get('inheritance_chain', []))}

**Total Resources:** {info.get('total_resources', 0)}

## Direct Sources
"""
        for source, types in info.get('resources', {}).items():
            total = sum(len(v) for v in types.values() if v)
            if total > 0:
                content += f"\n### {source} ({total} items)\n"
                for type_name, items in types.items():
                    if items:
                        content += f"- **{type_name}:** {len(items)} items\n"

        md.update(content)

        # Update clickable items list - grouped by type (agents/skills/commands/rules)
        items_list = self.query_one("#profile-items-list", ListView)
        for child in list(items_list.children):
            child.remove()

        # Get direct sources to check if item is removable
        direct_sources = set(info.get('direct_sources', []))

        # Define type order and icons
        type_order = ['agents', 'skills', 'commands', 'rules']
        type_icons = {
            'agents': '🤖',
            'skills': '📚',
            'commands': '⚡',
            'rules': '📋'
        }

        # Collect all items by type first
        items_by_type: dict[str, list[tuple[str, str, bool]]] = {
            'agents': [],
            'skills': [],
            'commands': [],
            'rules': []
        }

        for source, types in info.get('resources', {}).items():
            is_direct = source in direct_sources
            for type_name, items in types.items():
                if items and type_name in items_by_type:
                    for item in items:
                        if isinstance(item, dict):
                            item_name = item['name']
                        else:
                            item_name = item
                        items_by_type[type_name].append((item_name, source, is_direct))

        # Render grouped by type
        for type_name in type_order:
            items = items_by_type[type_name]
            if items:
                # Type header
                type_icon = type_icons.get(type_name, '📄')
                header_label = Label(f"{type_icon} {type_name.upper()} ({len(items)})")
                header_label.styles.background = "#1e1e2e"
                header_label.styles.color = "#22d3ee"  # cyan accent
                header_label.styles.text_style = "bold"
                header_label.styles.padding = (1, 0)
                header_item = ListItem(header_label)
                header_item._ccm_header = True
                items_list.append(header_item)

                # Items under this type
                for item_name, source, is_direct in sorted(items, key=lambda x: x[0]):
                    if is_direct:
                        list_item = ListItem(Label(f"  └─ {item_name}  [@{source}]"))
                        list_item._ccm_source = source
                        list_item._ccm_type = type_name
                        list_item._ccm_item = item_name
                        items_list.append(list_item)
                    else:
                        # Inherited items
                        list_item = ListItem(Label(f"  └─ {item_name}  [@{source}]"))
                        list_item._ccm_inherited = True
                        list_item.styles.color = "#64748b"
                        list_item.styles.text_style = "dim"
                        items_list.append(list_item)

    def on_radio_set_changed(self, event: RadioSet.Changed) -> None:
        """Handle type selection via radio buttons in profile configurator."""
        type_map = {
            "Agents": "agents",
            "Skills": "skills",
            "Commands": "commands",
            "Rules": "rules",
        }
        selected_label = str(event.pressed.label)
        if selected_label in type_map:
            self.selected_type = type_map[selected_label]
            self.update_add_item_list()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Handle list selections."""
        list_view = event.list_view

        if list_view.id == "profile-list":
            if hasattr(event.item, '_ccm_profile_name'):
                self.selected_profile = event.item._ccm_profile_name
        elif list_view.id == "profile-items-list":
            # Clicked on an item in profile - select it for removal (single click)
            # Skip if is header or inherited item
            if hasattr(event.item, '_ccm_header'):
                self.selected_profile_item = None
                return

            if hasattr(event.item, '_ccm_inherited'):
                # Inherited items cannot be selected
                self.selected_profile_item = None
                return

            if not hasattr(event.item, '_ccm_source'):
                self.selected_profile_item = None
                return

            self.selected_profile_item = {
                'source': event.item._ccm_source,
                'type': event.item._ccm_type,
                'item': event.item._ccm_item,
            }
            # No auto-navigation - user can click Remove or View Details

        elif list_view.id == "add-source-list":
            if hasattr(event.item, '_ccm_source_name'):
                self.selected_source = event.item._ccm_source_name
                self.update_add_item_list()
        elif list_view.id == "add-item-list":
            if hasattr(event.item, '_ccm_item_name'):
                self.selected_item = event.item._ccm_item_name

    def on_input_changed(self, event: Input.Changed) -> None:
        """Handle filter input."""
        if event.input.id == "add-item-filter":
            self.update_add_item_list(event.value)

    def update_add_item_list(self, filter_text: str = "") -> None:
        """Update available items to add."""
        if not self.selected_source:
            return

        item_list = self.query_one("#add-item-list", ListView)
        # Remove existing items
        for child in list(item_list.children):
            child.remove()

        items = self.builder.get_available_items(self.selected_source, self.selected_type)
        filter_lower = filter_text.lower()

        # Get current profile's items to mark already added ones
        added_items = set()
        if self.selected_profile:
            info = self.builder.inspect_profile(self.selected_profile)
            if info and self.selected_source in info.get('resources', {}):
                source_resources = info['resources'][self.selected_source]
                if self.selected_type in source_resources:
                    for item in source_resources[self.selected_type]:
                        item_name = item['name'] if isinstance(item, dict) else item
                        added_items.add(item_name)

        for item in items:
            item_name = item['name']
            # Show full path in display, mark if already added
            if item_name in added_items:
                display_text = f"✓ {self.selected_source}:{self.selected_type}/{item_name}"
            else:
                display_text = f"  {self.selected_source}:{self.selected_type}/{item_name}"
            if not filter_text or filter_lower in item_name.lower():
                list_item = ListItem(Label(display_text))
                list_item._ccm_item_name = item_name
                if item_name in added_items:
                    list_item._ccm_already_added = True
                    list_item.add_class("added")
                item_list.append(list_item)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "btn-add":
            self.add_to_profile()
        elif event.button.id == "btn-remove-from-detail":
            self.remove_from_profile_detail()
        elif event.button.id == "btn-view-in-source":
            self.view_in_source_browser()

    def add_to_profile(self) -> None:
        """Add selected item to profile."""
        if not all([self.selected_profile, self.selected_source, self.selected_item]):
            self.notify("Please select profile, source, and item", severity="error")
            return

        success = self.builder.add_to_profile(
            self.selected_profile,
            self.selected_source,
            self.selected_type,
            self.selected_item,
        )

        if success:
            full_ref = f"{self.selected_source}:{self.selected_type}/{self.selected_item}"
            self.notify(f"Added {full_ref} to {self.selected_profile}", severity="information")
            self.update_profile_detail()
            # Refresh add-item-list to update markers
            self.update_add_item_list()
        else:
            self.notify("Failed to add item", severity="error")

    def view_in_source_browser(self) -> None:
        """View selected item in Source Browser."""
        if not self.selected_profile_item:
            self.notify("Please select an item from the profile list", severity="error")
            return

        source = self.selected_profile_item['source']
        type_name = self.selected_profile_item['type']
        item_name = self.selected_profile_item['item']

        # Switch to Source Browser tab and navigate
        app = self.app
        tabs = app.query_one(TabbedContent)
        tabs.active = "sources"

        # Get SourceBrowser and navigate
        source_browser = app.query_one(SourceBrowser)
        source_browser.navigate_to(source, type_name, item_name)

    def remove_from_profile_detail(self) -> None:
        """Remove selected item from profile (called from detail view)."""
        if not self.selected_profile:
            self.notify("Please select a profile first", severity="error")
            return

        if not self.selected_profile_item:
            self.notify("Please select an item from the profile list", severity="error")
            return

        source = self.selected_profile_item['source']
        type_name = self.selected_profile_item['type']
        item_name = self.selected_profile_item['item']

        success = self.builder.remove_from_profile(
            self.selected_profile,
            source,
            type_name,
            item_name,
        )

        if success:
            full_ref = f"{source}:{type_name}/{item_name}"
            self.notify(f"Removed {full_ref} from {self.selected_profile}", severity="information")
            self.selected_profile_item = None
            self.update_profile_detail()
            # Refresh add-item-list to update markers
            self.update_add_item_list()
        else:
            # Check if this is an inherited item
            info = self.builder.inspect_profile(self.selected_profile)
            is_direct = False
            if info and source in info.get('direct_sources', []):
                is_direct = True
            if not is_direct:
                self.notify(f"Cannot remove '{item_name}' - it's inherited from a parent profile", severity="error")
            else:
                self.notify(f"Failed to remove '{item_name}' - item not found in profile", severity="error")


class CCMTUI(App):
    """CCM TUI Application."""

    CSS = """
    /* Base theme - dark professional */
    $primary: #6366f1;
    $primary-dark: #4f46e5;
    $primary-light: #818cf8;
    $accent: #22d3ee;
    $success: #22c55e;
    $warning: #f59e0b;
    $error: #ef4444;
    $surface: #1e1e2e;
    $surface-light: #2d2d44;
    $surface-dark: #16161e;
    $text: #e2e8f0;
    $text-muted: #94a3b8;

    Screen {
        align: center middle;
        background: $surface-dark;
    }

    /* Header styling */
    Header {
        background: $surface;
        color: $text;
        border-bottom: solid $primary;
        height: 3;
    }

    Header .title {
        text-style: bold;
        color: $primary-light;
    }

    Header .clock {
        color: $text-muted;
    }

    /* Footer styling */
    Footer {
        background: $surface;
        color: $text-muted;
        border-top: solid $surface-light;
        height: 1;
    }

    Footer .key {
        color: $accent;
        text-style: bold;
    }

    /* Tab styling */
    TabbedContent {
        background: $surface-dark;
        border: none;
    }

    TabPane {
        background: $surface-dark;
        padding: 1;
    }

    /* Active tab */
    TabbedContent > TabBar {
        background: $surface;
        height: 3;
    }

    TabbedContent > TabBar > Tab {
        background: $surface-light;
        color: $text-muted;
        padding: 1 2;
        text-style: bold;
    }

    TabbedContent > TabBar > Tab:hover {
        background: $surface;
        color: $text;
    }

    TabbedContent > TabBar > Tab.active {
        background: $primary;
        color: $text;
        text-style: bold underline;
    }

    /* Panel containers */
    .sidebar {
        width: 20%;
        height: 100%;
        background: $surface;
        border: solid $primary-dark;
        padding: 0;
        margin: 0 1;
    }

    .item-list {
        width: 25%;
        height: 100%;
        background: $surface;
        border: solid $primary-dark;
        padding: 0;
        margin: 0 1;
    }

    .detail-view {
        width: 55%;
        height: 100%;
        background: $surface;
        border: solid $primary-dark;
        padding: 0;
        margin: 0 1;
    }

    .profile-detail {
        width: 40%;
        height: 100%;
        background: $surface;
        border: solid $primary-dark;
        padding: 0;
        margin: 0 1;
    }

    .add-panel {
        width: 40%;
        height: 100%;
        background: $surface;
        border: solid $primary-dark;
        padding: 0;
        margin: 0 1;
    }

    /* Section titles */
    .title {
        text-style: bold;
        background: $primary-dark;
        color: $text;
        padding: 1;
        content-align: center middle;
    }

    .subtitle {
        text-style: bold;
        color: $primary-light;
        padding: 1;
        background: $surface-light;
        margin: 1 0 0 0;
    }

    /* ListView styling */
    ListView {
        height: 1fr;
        background: $surface;
        border: solid $surface-light;
        padding: 0;
    }

    ListView:focus {
        border: solid $accent;
    }

    ListView > ListItem {
        background: $surface;
        color: $text;
        padding: 0 2;
        height: auto;
        margin: 0;
    }

    ListView > ListItem:hover {
        background: $surface-light;
    }

    /* Selected item - very visible */
    ListView > ListItem.selected {
        background: $primary;
        color: $text;
        text-style: bold;
        border-left: thick $accent;
    }

    /* Focused item */
    ListView > ListItem:focus {
        background: $primary-dark;
        border-left: thick $accent;
    }

    /* Focused ListView with selected item */
    ListView:focus > ListItem.selected {
        background: $accent;
        color: $surface-dark;
        text-style: bold;
        border-left: thick $primary-light;
    }

    /* Even more visible for item lists */
    #item-list:focus > ListItem.selected,
    #add-item-list:focus > ListItem.selected,
    #profile-items-list:focus > ListItem.selected {
        background: $accent;
        color: $surface-dark;
        text-style: bold;
        border-left: thick $primary;
    }

    /* Profile list - very visible selection */
    #profile-list > ListItem.selected {
        background: $accent;
        color: $surface-dark;
        text-style: bold;
        border-left: thick $primary;
    }

    #profile-list:focus > ListItem.selected {
        background: $accent;
        color: $surface-dark;
        text-style: bold;
        border-left: thick $primary;
    }

    #profile-list > ListItem:hover {
        background: $primary-light;
        color: $text;
    }

    /* Already added items in add-item-list */
    #add-item-list > ListItem.added {
        color: $success;
        text-style: bold;
    }

    #add-item-list > ListItem.added Label {
        color: $success;
    }

    /* Item list specific - stronger highlight */
    #item-list > ListItem.selected,
    #add-item-list > ListItem.selected,
    #profile-items-list > ListItem.selected {
        background: $accent;
        color: $surface-dark;
        text-style: bold;
        border-left: solid $primary-light;
    }

    #item-list > ListItem:hover,
    #add-item-list > ListItem:hover,
    #profile-items-list > ListItem:hover {
        background: $primary-light;
        color: $text;
    }

    #item-list:focus > ListItem.selected,
    #add-item-list:focus > ListItem.selected,
    #profile-items-list:focus > ListItem.selected {
        background: $accent;
        color: $surface-dark;
    }

    /* Profile items list - header style */
    #profile-items-list > ListItem {
        padding: 0 1;
    }

    /* Markdown styling */
    Markdown {
        height: 1fr;
        background: $surface;
        border: none;
        padding: 1 2;
        scrollbar-color: $primary-dark $surface-light;
        scrollbar-color-hover: $primary $surface-light;
        color: $text;
    }

    /* Input styling */
    Input {
        margin: 1;
        background: $surface-light;
        border: solid $primary-dark;
        color: $text;
        padding: 0 1;
    }

    Input:focus {
        border: solid $accent;
    }

    Input .placeholder {
        color: $text-muted;
    }

    /* Button styling */
    .button-row {
        height: auto;
        padding: 1;
        background: $surface-light;
    }

    Button {
        margin: 0 1;
        background: $primary;
        color: $text;
        border: none;
        padding: 1 2;
        text-style: bold;
        min-width: 16;
    }

    Button:hover {
        background: $primary-light;
    }

    Button#btn-add {
        background: $success;
    }

    Button#btn-add:hover {
        background: #4ade80;
    }

    Button#btn-remove {
        background: $error;
    }

    Button#btn-remove:hover {
        background: #f87171;
    }

    /* RadioSet styling */
    RadioSet {
        background: $surface;
        border: none;
        padding: 0 1;
        height: auto;
    }

    RadioSet:focus {
        border: solid $accent;
    }

    RadioButton {
        background: $surface;
        color: $text;
        padding: 0 1;
    }

    RadioButton:hover {
        background: $surface-light;
    }

    RadioButton > .toggle {
        background: $surface-light;
        border: solid $primary-light;
    }

    RadioButton.-on {
        background: $primary-dark;
        color: $text;
        text-style: bold;
    }

    RadioButton.-on > .toggle {
        background: $primary;
        border: solid $accent;
    }

    /* Filter input */
    #item-filter, #add-item-filter {
        margin: 0 1;
        border-left: solid $accent;
    }

    /* Notification styling */
    .notification {
        padding: 1 2;
    }

    .notification.error {
        background: $error;
        color: $text;
    }

    .notification.information {
        background: $success;
        color: $text;
    }
    """

    BINDINGS = [
        ("q", "quit", "Quit"),
        ("tab", "switch_tab", "Switch Tab"),
    ]

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)

        with TabbedContent():
            with TabPane("Source Browser", id="sources"):
                yield SourceBrowser()
            with TabPane("Profile Configurator", id="profiles"):
                yield ProfileConfigurator()

        yield Footer()

    def action_switch_tab(self) -> None:
        """Switch between tabs."""
        tabs = self.query_one(TabbedContent)
        current = tabs.active
        if current == "sources":
            tabs.active = "profiles"
        else:
            tabs.active = "sources"


def run_tui() -> None:
    """Run the TUI application."""
    app = CCMTUI()
    app.run()


if __name__ == "__main__":
    run_tui()
