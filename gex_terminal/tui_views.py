"""Focused research dialogs; market state remains owned by the application consumer."""

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Footer, OptionList, Static
from textual.widgets.option_list import Option

from gex_terminal.replay_catalog import ReplaySession


class ReplayPicker(ModalScreen):
    """A keyboard and pointer accessible catalog with a visible selected row."""

    def __init__(self, sessions: tuple[ReplaySession, ...], selected: int,
                 active: ReplaySession | None):
        super().__init__()
        self.sessions = sessions
        self.selected_index = selected
        self.active = active

    def compose(self) -> ComposeResult:
        with Vertical(id="replay-dialog", classes="research-dialog"):
            yield Static("OPEN A REPLAY", classes="dialog-eyebrow")
            yield Static("Synthetic sessions · no account or connection needed", classes="dialog-subtitle")
            options = []
            for session in self.sessions:
                label = Text(f"{session.symbol:<4} {session.label}", style="#e9eef3")
                if self.active and session.name == self.active.name:
                    label.append("  · ACTIVE", style="bold #e9b96e")
                options.append(Option(label, id=session.name))
            yield OptionList(*options, id="replay-options")
            yield Static("", id="replay-description")
            yield Static("↑ ↓ choose   Enter load   Esc / p cancel", classes="dialog-hint")
            yield Static("", id="replay-error")

    def on_mount(self) -> None:
        self.select(self.selected_index)
        self.query_one(OptionList).focus()

    def select(self, index: int) -> None:
        self.selected_index = index
        options = self.query_one(OptionList)
        options.highlighted = index
        options.scroll_to_highlight()
        self._describe(index)

    def _describe(self, index: int) -> None:
        session = self.sessions[index]
        content = Text(session.label + "\n", style="bold #e9b96e")
        content.append(session.description + "\n", style="#c3ced8")
        content.append(f"{session.name} · {session.symbol} ×{session.contract_multiplier} · synthetic", style="#9aaaba")
        self.query_one("#replay-description", Static).update(content)
        self.query_one("#replay-error", Static).update("")

    def on_option_list_option_highlighted(self, event: OptionList.OptionHighlighted) -> None:
        # Ignore queued highlights superseded during mount or rapid key repeats.
        if event.option_index != event.option_list.highlighted:
            return
        self.app._replay_browser_index = event.option_index
        self.selected_index = event.option_index
        self._describe(event.option_index)

    async def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        self.app._replay_browser_index = event.option_index
        await self.app.action_select_replay_session()

    def show_error(self, message: str) -> None:
        self.query_one("#replay-error", Static).update(Text(message, style="#fb7185"))


class ResearchInfo(ModalScreen):
    BINDINGS = [Binding("escape", "dismiss", "Close"), Binding("?", "dismiss", "Close", show=False)]

    def __init__(self, title: str, content: Text):
        super().__init__()
        self.info_title = title
        self.content = content

    def compose(self) -> ComposeResult:
        with Vertical(classes="research-dialog", id="info-dialog"):
            yield Static(self.info_title, classes="dialog-eyebrow")
            with VerticalScroll(id="info-scroll"):
                yield Static(self.content, id="info-content")
            yield Static("↑ ↓ scroll   Esc close", classes="dialog-hint")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#info-scroll").focus()
