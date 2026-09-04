import asyncio
import json
import time
from collections import deque
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Iterable

from rich.text import Text
from textual.app import App, ComposeResult
from textual.containers import Container, Grid, Vertical
from textual.widgets import DataTable, Footer, Header, Sparkline, Static

from gex_terminal.config import GexConfig
from gex_terminal.consumer import StatefulGexConsumer
from gex_terminal.engine import IntradayGexEngine
from gex_terminal.replay_catalog import (
    ReplaySession,
    bundled_replay_sessions,
    config_for_replay_session,
)
from gex_terminal.regime import build_regime_map
from gex_terminal.provider_readiness import runtime_provider_readiness
from gex_terminal.snapshot import build_snapshot, write_snapshot
from gex_terminal.table_rows import arrange_rows, filter_rows, sort_rows


class GexTerminalApp(App):
    """A real-time terminal interface tracking intraday option gamma imbalances."""

    TITLE = "Intraday GEX Imbalance Terminal"
    CSS_PATH = str(Path(__file__).with_name("gex_terminal.tcss"))
    FIRST_RUN_REPLAY = "zero-gamma-flip"

    BINDINGS = [
        ("q", "quit", "Quit"),
        ("r", "refresh_terminal_data", "Refresh"),
        ("s", "cycle_sort", "Sort"),
        ("f", "cycle_filter", "Filter"),
        ("p", "cycle_replay_session", "Replay"),
        ("up", "replay_browser_up", "Up"),
        ("down", "replay_browser_down", "Down"),
        ("enter", "select_replay_session", "Load"),
        ("escape", "close_replay_browser", "Close"),
        ("d", "cycle_expiry_assumption", "DTE"),
        ("x", "cycle_expiry_filter", "Expiry"),
        ("m", "cycle_multiplier_assumption", "Mult"),
        ("i", "cycle_rate_assumption", "Rate"),
        ("e", "export_snapshot", "Export"),
    ]

    SORT_MODES = ("strike", "net", "volume")
    FILTER_MODES = ("all", "near", "active")
    SORT_LABELS = {"strike": "strike ↑", "net": "|net| ↓", "volume": "volume ↓"}
    FILTER_LABELS = {"all": "all strikes", "near": "near-money", "active": "active only"}
    EXPIRY_PRESETS = (0.01, 0.05, 0.25, 1.0, 7.0)
    RATE_PRESETS = (0.0, 0.02, 0.045, 0.05, 0.06)
    MULTIPLIER_PRESETS = (50, 20, 5, 2, 100)

    def __init__(
        self,
        consumer: StatefulGexConsumer,
        config: GexConfig | None = None,
        *,
        allow_replay_switching: bool = True,
        source_task: asyncio.Task | None = None,
    ):
        super().__init__()
        self.consumer = consumer
        self.config = config or GexConfig.from_env()
        self.allow_replay_switching = bool(allow_replay_switching)
        self._source_task = source_task
        self._replay_transition_lock = asyncio.Lock()
        self._gex_flow: deque[float] = deque(maxlen=36)
        self._latencies: deque[float] = deque(maxlen=36)
        self._events: deque[str] = deque(maxlen=7)
        self._symbols = self.config.symbols
        self._last_wall: float | None = None
        self._last_zero: float | None = None
        self._last_imbalance: float | None = None
        self._last_regime: str | None = None
        self._last_runtime_status: str | None = None
        self._last_latency_ms = 0.0
        self._sort_mode = "strike"
        self._filter_mode = "all"
        self._last_data: dict | None = None
        self._last_breakdown: dict = {}
        self._last_refresh_at: str = "--:--:--"
        self._replay_sessions = bundled_replay_sessions()
        self._active_replay_session = self._session_for_path(self.config.replay_path)
        self._replay_index = self._initial_replay_index()
        self._replay_browser_open = False
        self._replay_browser_index = self._initial_browser_index()

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)

        with Grid(id="dashboard"):
            with Vertical(id="sidebar"):
                yield Static("SYMBOLS", classes="rail-label")
                for symbol in self._symbols:
                    classes = "symbol symbol-active" if symbol == self.consumer.target_underlying else "symbol"
                    yield Static(f"{symbol:<8}0DTE", classes=classes)

                yield Static("FEED HEALTH", classes="rail-label")
                yield Static("* WebSocket\n  awaiting ticks", id="feed-websocket", classes="feed-line")
                yield Static("* Option chain\n  no contracts", id="feed-chain", classes="feed-line")
                yield Static("* OI proxy\n  volume weighted", id="feed-proxy", classes="feed-line")
                yield Static("* State lock\n  clean", id="feed-lock", classes="feed-line")

            with Grid(id="top-metrics"):
                yield self._metric("Underlying", "--", "--", self.config.symbol, "stat-spot")
                yield self._metric("Net GEX", "--", "$ / 1%", "positive gamma regime", "stat-netgex")
                yield self._metric("Gamma Wall", "--", "strike", "largest absolute exposure", "stat-wall")
                yield self._metric("Zero Gamma", "--", "node", "volatility inflection", "stat-zero")
                yield self._metric("Imbalance", "--", "C/P", "call/put balance", "stat-imbalance")
                yield self._metric("Latency", "--", "p95", "async queue stable", "stat-latency")

            with Vertical(id="matrix-panel"):
                yield Static("Strike Gamma Exposure Matrix", classes="section-title")
                yield Static("waiting for runtime configuration", id="matrix-meta", classes="subtle")
                yield Static("", id="matrix-controls", classes="subtle")
                yield Static("", id="matrix-state", classes="state-banner")
                yield DataTable(id="gex-table")

            with Vertical(id="structure-panel"):
                yield Static("Market Structure", classes="section-title")
                yield Static("computed after next snapshot", id="structure-meta", classes="subtle")
                yield Static("", id="dealer-regime", classes="zone-card")
                yield Static("", id="balance-pressure", classes="zone-card")
                yield Static("", id="vol-boundary", classes="zone-card")
                yield Static("", id="regime-map", classes="regime-card")

            with Vertical(id="flow-panel"):
                yield Static("Session GEX Flow", classes="section-title")
                yield Static("rolling 36 intervals", classes="subtle")
                yield Sparkline([], min_color="#fb7185", max_color="#38bdf8", id="gex-flow")

            with Vertical(id="quality-panel"):
                yield Static("Provider Health", classes="section-title")
                yield Static("feed quality checks", classes="subtle")
                yield Static("", id="quality-summary", classes="quality-card")

            with Vertical(id="event-panel"):
                yield Static("Event Log", classes="section-title")
                yield Static("async consumer", classes="subtle")
                yield Static("", id="event-log")

        yield Static("", id="status-bar")
        yield Footer()

    def _metric(self, label: str, value: str, corner: str, foot: str, value_id: str) -> Container:
        header = Text(label.upper(), style="bold #8a97a6")
        header.append(f"  {corner}", style="#5b6675")
        return Container(
            Static(header, classes="metric-label"),
            Static(value, id=value_id, classes="metric-value"),
            Static(foot, id=f"{value_id}-foot", classes="metric-foot"),
            classes="metric-card",
        )

    def on_mount(self) -> None:
        self.title = "Intraday GEX Imbalance Terminal"
        self.sub_title = (
            f"{self.config.symbol} · {self._workflow_label()} · CUMULATIVE SESSION VOLUME"
        )
        table = self.query_one("#gex-table", DataTable)
        table.cursor_type = "row"
        table.zebra_stripes = True
        table.add_column("Strike", width=12)
        table.add_column("Call Vol", width=10)
        table.add_column("Put Vol", width=10)
        table.add_column("Gamma", width=10)
        table.add_column("Call GEX", width=12)
        table.add_column("Put GEX", width=12)
        table.add_column("Net GEX", width=18)
        self.query_one("#matrix-state", Static).display = False
        self._render_controls()
        self._render_first_run_guide(self.consumer.runtime_status)
        self._render_status_bar(self.consumer.runtime_status)
        self.set_interval(self.config.refresh_interval_seconds, self.refresh_terminal_data)
        self.call_later(self.refresh_terminal_data)

    async def action_refresh_terminal_data(self) -> None:
        await self.refresh_terminal_data()

    def action_cycle_sort(self) -> None:
        index = self.SORT_MODES.index(self._sort_mode)
        self._sort_mode = self.SORT_MODES[(index + 1) % len(self.SORT_MODES)]
        self._event(f"sort -> {self.SORT_LABELS[self._sort_mode]}")
        self._render_controls()
        if self._last_data is not None:
            self._render_table(self._last_data)

    def action_cycle_filter(self) -> None:
        index = self.FILTER_MODES.index(self._filter_mode)
        self._filter_mode = self.FILTER_MODES[(index + 1) % len(self.FILTER_MODES)]
        self._event(f"filter -> {self.FILTER_LABELS[self._filter_mode]}")
        self._render_controls()
        if self._last_data is not None:
            self._render_table(self._last_data)

    async def action_cycle_replay_session(self) -> None:
        if not self.allow_replay_switching:
            self._event("replay switching is disabled while session capture is active")
            self._render_events()
            return
        if self.config.data_mode.lower() not in {"demo", "replay"}:
            self._event("replay selector is available in demo or replay mode")
            self._render_events()
            return
        self._replay_browser_open = not self._replay_browser_open
        if self._replay_browser_open:
            self._replay_browser_index = self._initial_browser_index()
            self._event("replay browser opened")
            self._render_replay_browser()
        else:
            self._event("replay browser closed")
            self._render_structure_or_first_run()
        self._render_controls()
        self._render_events()

    def action_replay_browser_down(self) -> None:
        if not self._replay_browser_open or not self._replay_sessions:
            return
        self._replay_browser_index = (self._replay_browser_index + 1) % len(self._replay_sessions)
        self._event(f"replay selected -> {self._selected_replay_session().name}")
        self._render_replay_browser()
        self._render_controls()
        self._render_events()

    def action_replay_browser_up(self) -> None:
        if not self._replay_browser_open or not self._replay_sessions:
            return
        self._replay_browser_index = (self._replay_browser_index - 1) % len(self._replay_sessions)
        self._event(f"replay selected -> {self._selected_replay_session().name}")
        self._render_replay_browser()
        self._render_controls()
        self._render_events()

    async def action_select_replay_session(self) -> None:
        if not self.allow_replay_switching:
            self._event("replay switching is disabled while session capture is active")
            self._render_events()
            return
        if self.config.data_mode.lower() not in {"demo", "replay"}:
            self._event("replay selector is available in demo or replay mode")
            self._render_events()
            return
        session = self._selected_replay_session() if self._replay_browser_open else self._next_replay_session()
        await self._load_replay_session(session)

    async def action_cycle_expiry_assumption(self) -> None:
        next_value = self._next_float_preset(self.config.days_to_expiry, self.EXPIRY_PRESETS)
        await self._apply_terminal_assumptions(days_to_expiry=next_value)

    async def action_cycle_expiry_filter(self) -> None:
        choices = self._expiry_filter_choices()
        if len(choices) <= 1:
            self._event("expiry filter -> no tagged expiries available")
            self._render_events()
            return
        current = self.config.expiry_filter.lower()
        try:
            index = [choice.lower() for choice in choices].index(current)
        except ValueError:
            index = -1
        selected = choices[(index + 1) % len(choices)]
        self.config = replace(self.config, expiry_filter=selected)
        self.consumer.set_expiry_filter(selected)
        self._event(f"expiry filter -> {selected}")
        self._render_controls()
        await self.refresh_terminal_data()

    async def action_cycle_rate_assumption(self) -> None:
        next_value = self._next_float_preset(self.config.risk_free_rate, self.RATE_PRESETS)
        await self._apply_terminal_assumptions(risk_free_rate=next_value)

    async def action_cycle_multiplier_assumption(self) -> None:
        next_value = self._next_int_preset(self.config.contract_multiplier, self.MULTIPLIER_PRESETS)
        await self._apply_terminal_assumptions(contract_multiplier=next_value)

    def action_close_replay_browser(self) -> None:
        if not self._replay_browser_open:
            return
        self._replay_browser_open = False
        self._event("replay browser closed")
        self._render_structure_or_first_run()
        self._render_controls()
        self._render_events()

    async def _load_replay_session(self, session: ReplaySession) -> None:
        async with self._replay_transition_lock:
            await self._replace_replay_session(session)

    async def _replace_replay_session(self, session: ReplaySession) -> None:
        if not self.allow_replay_switching:
            self._event("replay load blocked -> active session capture")
            self._render_events()
            return
        if self.config.data_mode.lower() not in {"demo", "replay"}:
            self._event("replay load blocked -> live source owns this session")
            self._render_events()
            return
        try:
            messages = list(self._load_replay_messages(session))
        except (FileNotFoundError, ValueError) as error:
            self._event(f"replay load failed -> {error}")
            self._render_events()
            return

        replay_config = config_for_replay_session(self.config, session)
        if self._source_task is not None:
            self._source_task.cancel()
            try:
                await self._source_task
            except asyncio.CancelledError:
                # Only a settled writer may be replaced. Caller cancellation
                # must still propagate, rather than resetting state on exit.
                if asyncio.current_task().cancelling():
                    raise
            except Exception:
                self._event("replay load blocked -> previous source failed; restart the session")
                self._render_events()
                return
            self._source_task = None
        self.config = replace(
            replay_config,
            replay_delay_seconds=0.0,
            expiry_filter="all",
        )
        self._symbols = self.config.symbols
        self.consumer.engine.multiplier = self.config.contract_multiplier
        await self.consumer.reset_state(
            data_mode="replay",
            target_underlying=self.config.symbol,
            risk_free_rate=self.config.risk_free_rate,
            stale_after_seconds=self.config.stale_after_seconds,
        )
        self.consumer.set_expiry_filter(self.config.expiry_filter)
        self.consumer.mark_connected()
        self.consumer.mark_subscribed(1)
        self._reset_terminal_session_state()
        self._active_replay_session = session
        self._replay_index = self._session_index(session)
        self._replay_browser_index = self._replay_index
        self._replay_browser_open = False

        for message in messages:
            await self.consumer.update_market_state(json.dumps(message))
        self.consumer.mark_disconnected()
        self._event(f"replay loaded -> {session.name}")
        self._render_controls()
        await self.refresh_terminal_data()

    def _reset_terminal_session_state(self) -> None:
        self._gex_flow.clear()
        self._latencies.clear()
        self._events.clear()
        self._last_wall = None
        self._last_zero = None
        self._last_imbalance = None
        self._last_regime = None
        self._last_runtime_status = None
        self._last_latency_ms = 0.0
        self._last_data = None
        self._last_breakdown = {}
        self._last_refresh_at = "--:--:--"

    def _load_replay_messages(self, session: ReplaySession) -> Iterable[dict]:
        path = Path(session.path)
        if not path.exists():
            raise FileNotFoundError(f"Replay file not found: {path}")
        with path.open(encoding="utf-8") as replay_file:
            for line_number, line in enumerate(replay_file, start=1):
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ValueError(
                        f"Invalid JSON in replay file {path} at line {line_number}"
                    ) from exc

    def _next_replay_session(self) -> ReplaySession:
        if not self._replay_sessions:
            raise RuntimeError("No bundled replay sessions are available.")
        next_index = (self._replay_index + 1) % len(self._replay_sessions)
        return self._replay_sessions[next_index]

    def _selected_replay_session(self) -> ReplaySession:
        if not self._replay_sessions:
            raise RuntimeError("No bundled replay sessions are available.")
        return self._replay_sessions[self._replay_browser_index % len(self._replay_sessions)]

    def _initial_browser_index(self) -> int:
        if not self._replay_sessions:
            return 0
        if self.config.data_mode.lower() == "demo":
            return (self._replay_index + 1) % len(self._replay_sessions)
        if self._active_replay_session is not None:
            return self._session_index(self._active_replay_session)
        return (self._replay_index + 1) % len(self._replay_sessions)

    def _replay_label(self) -> str:
        if self.config.data_mode.lower() not in {"demo", "replay"}:
            return "offline only"
        if self._replay_browser_open:
            return f"select {self._selected_replay_session().label}"
        return f"next {self._next_replay_session().label}"

    def _initial_replay_index(self) -> int:
        if not self._replay_sessions:
            return 0
        if self.config.data_mode.lower() == "demo":
            first_run = self._session_for_name(self.FIRST_RUN_REPLAY) or self._replay_sessions[0]
            return self._session_index(first_run) - 1
        if self._active_replay_session is not None:
            return self._session_index(self._active_replay_session)
        first_run = self._session_for_name(self.FIRST_RUN_REPLAY) or self._replay_sessions[0]
        return self._session_index(first_run) - 1

    def _session_for_name(self, name: str) -> ReplaySession | None:
        for session in self._replay_sessions:
            if session.name == name:
                return session
        return None

    def _session_for_path(self, path: str) -> ReplaySession | None:
        normalized = str(Path(path))
        for session in self._replay_sessions:
            if str(Path(session.path)) == normalized:
                return session
        return None

    def _session_index(self, session: ReplaySession | None) -> int:
        if session is None:
            return -1
        for index, candidate in enumerate(self._replay_sessions):
            if candidate.name == session.name:
                return index
        return -1

    def _render_controls(self) -> None:
        self.query_one("#matrix-controls", Static).update(
            f"sort: [#cbd5e1]{self.SORT_LABELS[self._sort_mode]}[/]  ·  "
            f"filter: [#cbd5e1]{self.FILTER_LABELS[self._filter_mode]}[/]   "
            f"replay: [#cbd5e1]{self._replay_label()}[/]   "
            f"expiry: [#cbd5e1]{self.config.expiry_filter}[/]   "
            f"model: [#cbd5e1]{self.config.days_to_expiry:g}DTE · "
            f"{self.config.risk_free_rate:.2%} · ×{self.config.contract_multiplier}[/]   "
            f"[#5b6675]([b]s[/] sort  [b]f[/] filter  [b]p[/] replay  "
            f"[b]x[/] expiry  [b]d[/] dte  [b]m[/] mult  [b]i[/] rate  [b]e[/] export)[/]"
        )

    async def _apply_terminal_assumptions(
        self,
        *,
        days_to_expiry: float | None = None,
        risk_free_rate: float | None = None,
        contract_multiplier: int | None = None,
    ) -> None:
        updates: dict[str, float | int] = {}
        if days_to_expiry is not None:
            updates["days_to_expiry"] = float(days_to_expiry)
        if risk_free_rate is not None:
            updates["risk_free_rate"] = float(risk_free_rate)
            self.consumer.risk_free_rate = float(risk_free_rate)
        if contract_multiplier is not None:
            updates["contract_multiplier"] = int(contract_multiplier)
            self.consumer.engine.multiplier = int(contract_multiplier)

        if not updates:
            return

        self.config = replace(self.config, **updates)
        self._event(
            "assumptions -> "
            f"{self.config.days_to_expiry:g}DTE, "
            f"{self.config.risk_free_rate:.2%}, "
            f"×{self.config.contract_multiplier}"
        )
        self._render_controls()
        if self.consumer.chain_state and self.consumer.current_spot:
            await self.refresh_terminal_data()
        else:
            status = self.consumer.runtime_status
            self._render_lifecycle()
            self._render_status_bar(status)
            self._render_structure_or_first_run()
            self._render_events()

    def _render_structure_or_first_run(self) -> None:
        if self._last_data is not None:
            self._render_structure(self._last_data)
            self._render_expiry(self._last_breakdown)
            return
        self._render_first_run_guide(self.consumer.runtime_status)

    def _render_replay_browser(self) -> None:
        if not self._replay_sessions:
            self.query_one("#dealer-regime", Static).update("[b]Replay Browser[/]\nNo bundled sessions found.")
            return

        selected = self._selected_replay_session()
        active_label = self._active_replay_session.label if self._active_replay_session else "Demo seed"
        self.query_one("#dealer-regime", Static).update(
            "[b]Replay Browser[/]   [cyan]offline sessions[/]\n"
            f"Selected [#cbd5e1]{selected.label}[/]\n"
            f"[#94a3b8]Active:[/] {active_label}"
        )
        self.query_one("#balance-pressure", Static).update(
            "[b]Session Notes[/]\n"
            f"{selected.description}\n"
            f"[#94a3b8]Path:[/] {selected.path}"
        )
        self.query_one("#vol-boundary", Static).update(
            "[b]Controls[/]\n"
            "Up/Down browse · Enter load · Escape close\n"
            "Use exports and journal reports after loading."
        )
        self.query_one("#regime-map", Static).update(self._replay_browser_rows(selected))

    def _replay_browser_rows(self, selected: ReplaySession) -> Text:
        text = Text("Bundled Replay Sessions\n", style="bold #8a97a6")
        for index, session in enumerate(self._replay_sessions, start=1):
            is_selected = session.name == selected.name
            is_active = (
                self._active_replay_session is not None
                and session.name == self._active_replay_session.name
            )
            marker = ">" if is_selected else " "
            active = "*" if is_active else " "
            style = "bold #38bdf8" if is_selected else "#94a3b8"
            text.append(f"{marker} {index:02d} {active} {session.label:<24} {session.name}\n", style=style)
        text.append("\n* active session", style="#64748b")
        return text

    def _render_status_bar(self, status: str) -> None:
        color = self._status_color(status)
        bar = Text(" ", style="#94a3b8")
        segments = (
            f"provider {self.config.data_provider}",
            f"readiness {runtime_provider_readiness(self.config)}",
            self._workflow_label().lower(),
            f"{self.config.symbol} ×{self.config.contract_multiplier}",
            f"expiry {self.config.expiry_filter}",
            f"refresh {self.config.refresh_interval_seconds:g}s",
            f"last {self._last_refresh_at}",
        )
        bar.append("  ·  ".join(segments), style="#94a3b8")
        bar.append("  ·  ", style="#3a4654")
        bar.append(status, style=f"bold {self._hex_status(status)}")
        self.query_one("#status-bar", Static).update(bar)

    def _render_state_banner(self, status: str) -> None:
        banner = self.query_one("#matrix-state", Static)
        if status == "STALE":
            banner.display = True
            banner.update("[amber]■ STALE FEED[/]  no fresh ticks — showing last known snapshot")
        elif status == "DISCONNECTED":
            banner.display = True
            banner.update("[red]■ DISCONNECTED[/]  provider feed is down — snapshot may be outdated")
        else:
            banner.display = False

    def _render_expiry(self, breakdown: dict) -> None:
        meta = self.query_one("#structure-meta", Static)
        if not breakdown:
            meta.update("by expiry · --")
            return
        parts = " · ".join(
            f"{label} {self._format_money(total)}" for label, total in breakdown.items()
        )
        meta.update(f"by expiry · {parts}")

    def action_export_snapshot(self) -> None:
        if self._last_data is None:
            self._event("export skipped — no snapshot yet")
            self._render_events()
            return
        snapshot = build_snapshot(
            symbol=self.consumer.target_underlying,
            spot=self.consumer.current_spot,
            session_open=self.consumer.session_open,
            days_to_expiry=self.config.days_to_expiry,
            contract_multiplier=self.config.contract_multiplier,
            risk_free_rate=self.config.risk_free_rate,
            data=self._last_data,
            chain_state=self.consumer.chain_state,
            expiry_breakdown=self._last_breakdown,
        )
        filename = f"gex_snapshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        try:
            target = write_snapshot(snapshot, filename)
            self._event(f"snapshot exported -> {target.name}")
        except OSError as error:
            self._event(f"export failed — {error}")
        self._render_events()

    async def refresh_terminal_data(self) -> None:
        """Poll the consumer and render the latest GEX matrix."""
        started = time.perf_counter()
        data = await self.consumer.process_latest_snapshot(
            days_to_expiry=self.config.days_to_expiry,
            expiry_filter=self.config.expiry_filter,
        )
        self._last_latency_ms = (time.perf_counter() - started) * 1000
        self._latencies.append(self._last_latency_ms)
        self._last_refresh_at = self._timestamp()
        self._render_lifecycle()
        status = self.consumer.runtime_status
        self._render_status_bar(status)
        self._render_quality()

        if "error" in data:
            self._last_data = None
            self._render_empty_state(data["error"], status)
            return

        self._last_data = data
        self._last_breakdown = await self.consumer.process_expiry_breakdown(
            days_to_expiry=self.config.days_to_expiry
        )
        self._gex_flow.append(float(data["total_net_gex"]))
        self._record_events(data)
        self._render_metrics(data)
        self._render_table(data)
        self._render_structure(data)
        self._render_expiry(self._last_breakdown)
        self._render_sidebar(data)
        self._render_flow()
        self._render_events()
        self._render_state_banner(status)
        if self._replay_browser_open:
            self._render_replay_browser()

    def _render_empty_state(self, reason: str, status: str) -> None:
        self.query_one("#gex-table", DataTable).clear()
        self.query_one("#stat-latency", Static).update(f"{self._last_latency_ms:.0f}ms")

        banner = self.query_one("#matrix-state", Static)
        banner.display = True
        if status == "DISCONNECTED":
            banner.update("[red]■ DISCONNECTED[/]  trying to reach the market-data provider — no snapshot yet")
            self.query_one("#feed-chain", Static).update("[red]*[/] Option chain\n  disconnected")
        elif status == "CONNECTED":
            banner.update("[cyan]■ CONNECTING[/]  awaiting the first option-chain snapshot")
            self.query_one("#feed-chain", Static).update("[cyan]*[/] Option chain\n  connecting")
        else:
            banner.update(f"[amber]■ WAITING[/]  {reason}")
            self.query_one("#feed-chain", Static).update("[amber]*[/] Option chain\n  no contracts")
        self._render_first_run_guide(status, reason)
        if self._replay_browser_open:
            self._render_replay_browser()

    def _render_first_run_guide(self, status: str, reason: str = "waiting for market state") -> None:
        replay = self._next_replay_session()
        self.query_one("#dealer-regime", Static).update(
            "[b]First Run[/]   [cyan]offline research ready[/]\n"
            f"{reason}\n"
            f"[#94a3b8]Next replay:[/] [#cbd5e1]{replay.label}[/]"
        )
        self.query_one("#balance-pressure", Static).update(
            "[b]Start Without Data[/]   [cyan]press p[/]\n"
            "Open the bundled replay browser, then press Enter to load.\n"
            "[#94a3b8]Try:[/] zero-gamma-flip, trend-day, gap-fade."
        )
        self.query_one("#vol-boundary", Static).update(
            "[b]Review Output[/]   [green]press e[/]\n"
            "Export the current snapshot once a replay is loaded.\n"
            "[#94a3b8]Docs:[/] docs/replay-research.md"
        )
        self.query_one("#regime-map", Static).update(
            "[b]Workflow[/]\n"
            f"Mode {status} · symbol {self.config.symbol} · multiplier {self.config.contract_multiplier}\n"
            "Use replay, exports, and journal reports before live feeds."
        )

    def _render_metrics(self, data: dict) -> None:
        total_net = float(data["total_net_gex"])
        call_total = sum(float(value) for value in data["call_gex"])
        put_total_abs = abs(sum(float(value) for value in data["put_gex"]))
        imbalance = self._imbalance(call_total, put_total_abs)
        regime = "positive gamma regime" if total_net >= 0 else "negative gamma regime"

        self.query_one("#stat-spot", Static).update(f"{self.consumer.current_spot:,.2f}")
        self.query_one("#stat-spot-foot", Static).update(self._spot_change_text())

        self.query_one("#stat-netgex", Static).update(self._colored_money(total_net))
        self.query_one("#stat-netgex-foot", Static).update(regime)

        self.query_one("#stat-wall", Static).update(f"[amber]{self._format_strike(data['gamma_wall_strike'])}[/]")
        self.query_one("#stat-zero", Static).update(f"[cyan]{self._format_strike(data['zero_gamma_strike'])}[/]")

        self.query_one("#stat-imbalance", Static).update(f"{imbalance:.2f}x")
        self.query_one("#stat-imbalance-foot", Static).update(
            "call-side dominant" if imbalance >= 1 else "put-side dominant"
        )

        self.query_one("#stat-latency", Static).update(f"{self._p95_latency():.0f}ms")
        self.query_one("#stat-latency-foot", Static).update(
            f"{self.consumer.runtime_status.lower()} | refresh {self.config.refresh_interval_seconds:g}s"
        )

    def _render_table(self, data: dict) -> None:
        table = self.query_one("#gex-table", DataTable)
        table.clear()

        call_volumes = data.get("call_volume", ())
        put_volumes = data.get("put_volume", ())
        max_volume = max(
            (
                int(call_volume) + int(put_volume)
                for call_volume, put_volume in zip(call_volumes, put_volumes)
            ),
            default=0,
        )
        max_abs_net = max((abs(float(value)) for value in data["net_gex"]), default=0)
        nearest_zero = float(data.get("nearest_zero_strike", data["zero_gamma_strike"]))

        rows = []
        for index, (strike, gamma, call_gex, put_gex, net_gex) in enumerate(zip(
            data["strikes"], data["gammas"], data["call_gex"], data["put_gex"], data["net_gex"]
        )):
            state = self.consumer.chain_state.get(float(strike), {"C": 0, "P": 0})
            call_volume = int(call_volumes[index]) if index < len(call_volumes) else int(state["C"])
            put_volume = int(put_volumes[index]) if index < len(put_volumes) else int(state["P"])
            rows.append({
                "strike": float(strike),
                "gamma": float(gamma),
                "call_gex": float(call_gex),
                "put_gex": float(put_gex),
                "net_gex": float(net_gex),
                "call_vol": call_volume,
                "put_vol": put_volume,
                "volume": call_volume + put_volume,
            })

        rows = self._arrange_rows(
            rows, self._sort_mode, self._filter_mode, self.consumer.current_spot, max_volume
        )

        for row in rows:
            row_style = self._row_style(
                strike=row["strike"],
                wall=float(data["gamma_wall_strike"]),
                nearest_zero=nearest_zero,
                total_volume=row["volume"],
                max_volume=max_volume,
            )
            strike_label = self._strike_label(
                row["strike"], data["gamma_wall_strike"], nearest_zero
            )
            table.add_row(
                strike_label,
                self._text(f"{row['call_vol']:,}", row_style),
                self._text(f"{row['put_vol']:,}", row_style),
                self._text(f"{row['gamma']:.5f}", row_style),
                self._money_cell(row["call_gex"], row_style),
                self._money_cell(row["put_gex"], row_style),
                self._net_cell(row["net_gex"], max_abs_net, row_style),
            )

    def _render_structure(self, data: dict) -> None:
        total_net = float(data["total_net_gex"])
        call_total = sum(float(value) for value in data["call_gex"])
        put_total_abs = abs(sum(float(value) for value in data["put_gex"]))
        imbalance = self._imbalance(call_total, put_total_abs)
        zero = self._format_strike(data["zero_gamma_strike"], decimals=1)
        wall = self._format_strike(data["gamma_wall_strike"])
        call_wall = self._format_strike(data.get("call_wall_strike", data["gamma_wall_strike"]))
        put_wall = self._format_strike(data.get("put_wall_strike", data["gamma_wall_strike"]))
        concentration = float(data.get("concentration_ratio", 0.0))
        band_low = self._format_strike(data.get("concentration_band_low", data["gamma_wall_strike"]))
        band_high = self._format_strike(data.get("concentration_band_high", data["gamma_wall_strike"]))
        regime_label = "+GEX" if total_net >= 0 else "-GEX"
        regime_color = "green" if total_net >= 0 else "red"

        self.query_one("#dealer-regime", Static).update(
            f"[b]GEX Proxy Regime[/]   [{regime_color}]{regime_label}[/]\n"
            f"Net {self._format_money(total_net)} · gamma wall {wall}\n"
            f"[green]call wall {call_wall}[/] · [red]put wall {put_wall}[/]"
        )
        self.query_one("#balance-pressure", Static).update(
            f"[b]Proxy Balance[/]   [cyan]{imbalance:.2f}x[/]\n"
            f"{'Call-side' if imbalance >= 1 else 'Put-side'} leads in selected quantities.\n"
            f"Top strike holds [#cbd5e1]{concentration:.0%}[/] of modeled net GEX."
        )
        self.query_one("#vol-boundary", Static).update(
            f"[b]Compatibility Level[/]   [amber]{zero}[/]\n"
            f"Historical strike-profile field; predictive effect unmeasured.\n"
            f"70% band {band_low}–{band_high}."
        )
        self._render_regime_map(data)

    def _render_regime_map(self, data: dict) -> None:
        regime = build_regime_map(data, self.consumer.current_spot)
        trigger = regime["next_trigger"]
        primary = "+GEX" if regime["primary_regime"] == "positive_gex_proxy" else "-GEX"

        text = Text("GEX Proxy Regime Map\n", style="bold #8a97a6")
        text.append(regime["label"], style=f"bold {regime['color']}")
        text.append(f"  base {primary}\n", style="#64748b")
        text.append("Spot ", style="#64748b")
        text.append(self._format_strike(regime["spot"], decimals=1), style="#cbd5e1")
        text.append(" · compat ", style="#64748b")
        text.append(self._format_strike(regime["zero_gamma"], decimals=1), style="#38bdf8")
        text.append(" · wall ", style="#64748b")
        text.append(self._format_strike(regime["gamma_wall"]), style="#fbbf24")
        text.append("\n")
        text.append("Next trigger ", style="#64748b")
        text.append(trigger["label"], style="#cbd5e1")
        text.append(
            f" {trigger['side']} {abs(trigger['distance']):.1f} @ "
            f"{self._format_strike(trigger['price'], decimals=1)}\n",
            style="#94a3b8",
        )
        text.append("+PROXY", style="#22c55e")
        text.append(" / ", style="#64748b")
        text.append("-PROXY", style="#ef4444")
        text.append(" / ", style="#64748b")
        text.append("COMPAT", style="#38bdf8")
        text.append(" / ", style="#64748b")
        text.append("WALL", style="#f59e0b")
        text.append(f"  threshold {regime['proximity_threshold']:.1f}", style="#64748b")
        self.query_one("#regime-map", Static).update(text)

    def _render_sidebar(self, data: dict) -> None:
        contract_count = int(data.get("selected_contract_count", len(data["strikes"])))
        volume = int(sum(data.get("call_volume", ())) + sum(data.get("put_volume", ())))
        self.query_one("#feed-chain", Static).update(f"[green]*[/] Option chain\n  {contract_count:,} contracts")
        self.query_one("#feed-proxy", Static).update(f"[amber]*[/] OI proxy\n  {volume:,} volume")
        self.query_one("#feed-lock", Static).update("[green]*[/] State lock\n  clean")

    def _render_quality(self) -> None:
        quality = self.consumer.feed_quality_snapshot(
            latency_ms=self._last_latency_ms,
            p95_latency_ms=self._p95_latency(),
        )
        status_color = self._hex_status(quality["status"])
        health_color = self._health_color(quality["health"])
        text = Text()
        text.append("Connection  ", style="bold #8a97a6")
        text.append(quality["status"], style=f"bold {self._hex_status(quality['status'])}")
        text.append(f" / {quality['connection_state']}\n", style="#94a3b8")

        text.append("Health      ", style="bold #8a97a6")
        text.append(quality["health"].upper(), style=f"bold {health_color}")
        text.append(f"  mode {quality['data_mode'].lower()}\n", style="#94a3b8")

        text.append("Last msg    ", style="bold #8a97a6")
        text.append(self._format_age(quality["last_message_age_seconds"]), style="#cbd5e1")
        text.append("  snap ", style="#64748b")
        text.append(self._format_age(quality["last_snapshot_age_seconds"]), style="#cbd5e1")
        text.append(f"  stale>{quality['stale_after_seconds']:g}s\n", style="#64748b")

        text.append("Latency     ", style="bold #8a97a6")
        text.append(f"{quality['latency_ms']:.0f}ms", style="#cbd5e1")
        text.append(f" now / {quality['p95_latency_ms']:.0f}ms p95\n", style="#64748b")

        text.append("Payloads    ", style="bold #8a97a6")
        text.append(f"{quality['message_count']:,} ok", style="#cbd5e1")
        text.append(
            f" · {quality['malformed_count']} bad · {quality['dropped_count']} dropped · "
            f"{quality['entitlement_error_count']} entitlement\n",
            style="#64748b",
        )
        text.append("Provider    ", style="bold #8a97a6")
        text.append(f"{quality['frame_count']:,} frames", style="#cbd5e1")
        text.append(
            f" · {quality['parse_error_count']} parse · {quality['reconnect_count']} reconnect · "
            f"{quality['subscribed_symbol_count']} subs {quality['subscription_status']}\n",
            style="#64748b",
        )
        text.append("Note        ", style="bold #8a97a6")
        text.append("; ".join(quality["notes"][:2]), style=status_color)
        self.query_one("#quality-summary", Static).update(text)

    def _render_lifecycle(self) -> None:
        status = self.consumer.runtime_status
        color = self._status_color(status)
        if status != self._last_runtime_status:
            self._event(f"runtime state {status}")
            self._last_runtime_status = status

        self.sub_title = (
            f"{self.config.symbol} · {self._workflow_label()} · CUMULATIVE SESSION VOLUME · {status}"
        )

        self.query_one("#feed-websocket", Static).update(
            f"[{color}]*[/] Data mode\n  {status}"
        )
        self.query_one("#matrix-meta", Static).update(
            f"mode: {status} | expiry: {self.config.days_to_expiry:g}d | "
            f"selection: {self.config.expiry_filter} | multiplier: {self.config.contract_multiplier} | "
            f"rate: {self.config.risk_free_rate:.2%}"
        )
        self.query_one("#stat-latency-foot", Static).update(
            f"{status.lower()} | refresh {self.config.refresh_interval_seconds:g}s"
        )

    def _render_flow(self) -> None:
        sparkline = self.query_one("#gex-flow", Sparkline)
        values = list(self._gex_flow)
        sparkline.data = values if values else [0.0]

    def _render_events(self) -> None:
        if not self._events:
            self._events.appendleft(f"{self._timestamp()} snapshot published to UI")
        self.query_one("#event-log", Static).update("\n".join(self._events))

    def _record_events(self, data: dict) -> None:
        wall = float(data["gamma_wall_strike"])
        zero = float(data["zero_gamma_strike"])
        total_net = float(data["total_net_gex"])
        call_total = sum(float(value) for value in data["call_gex"])
        put_total_abs = abs(sum(float(value) for value in data["put_gex"]))
        imbalance = self._imbalance(call_total, put_total_abs)
        regime = "+GEX" if total_net >= 0 else "-GEX"

        if self._last_wall is None:
            self._event(f"gamma wall initialized at {self._format_strike(wall)}")
        elif wall != self._last_wall:
            self._event(
                f"gamma wall shifted {self._format_strike(self._last_wall)} -> {self._format_strike(wall)}"
            )

        if self._last_zero is None:
            self._event(f"compatibility level initialized at {self._format_strike(zero, decimals=1)}")
        elif abs(zero - self._last_zero) >= 1:
            delta = zero - self._last_zero
            self._event(
                f"compatibility level moved {delta:+.1f} to {self._format_strike(zero, decimals=1)}"
            )

        if self._last_regime is None:
            self._event(f"GEX proxy regime initialized {regime}")
        elif regime != self._last_regime:
            self._event(f"GEX proxy sign changed {self._last_regime} -> {regime}")

        if self._last_imbalance is None:
            self._event(f"call/put imbalance {imbalance:.2f}x")
        elif self._crossed_imbalance_threshold(self._last_imbalance, imbalance):
            self._event(f"imbalance threshold crossed {imbalance:.2f}x")

        self._last_wall = wall
        self._last_zero = zero
        self._last_imbalance = imbalance
        self._last_regime = regime

    def _strike_label(self, strike: float, wall: float, zero: float) -> str:
        label = self._format_strike(strike)
        if float(strike) == float(wall):
            return Text(f"{label} WALL", style="bold #fbbf24")
        if float(strike) == float(zero):
            return Text(f"{label} ZERO", style="bold #38bdf8")
        return Text(label, style="#e9eef3")

    def _row_style(self, strike: float, wall: float, nearest_zero: float, total_volume: int, max_volume: int) -> str:
        if strike == wall:
            return "bold #fbbf24"
        if strike == nearest_zero:
            return "bold #38bdf8"
        if max_volume and total_volume < max_volume * 0.25:
            return "#64748b"
        return "#dce5ee"

    def _spot_change_text(self) -> Text:
        symbol = self.consumer.target_underlying
        spot = self.consumer.current_spot
        open_price = self.consumer.session_open
        if not open_price:
            return Text(symbol, style="#64748b")
        change = spot - open_price
        pct = (change / open_price * 100) if open_price else 0.0
        color = "#4ade80" if change >= 0 else "#fb7185"
        text = Text(f"{symbol}  ", style="#64748b")
        text.append(f"{change:+.2f} / {pct:+.2f}%", style=color)
        return text

    def _colored_money(self, value: float) -> str:
        color = "green" if value >= 0 else "red"
        return f"[{color}]{self._format_money(value)}[/]"

    def _money_cell(self, value: float, fallback_style: str = "#dce5ee") -> Text:
        style = "#4ade80" if value >= 0 else "#fb7185"
        if fallback_style == "#64748b":
            style = "#64748b"
        return Text(self._format_money(value), style=style)

    def _net_cell(self, value: float, max_abs_net: float, fallback_style: str = "#dce5ee") -> Text:
        base = "#4ade80" if value >= 0 else "#fb7185"
        if fallback_style == "#64748b":
            base = "#475569"
        ratio = 0.0 if max_abs_net == 0 else abs(value) / max_abs_net
        cell = Text(f"{self._format_money(value):<8}", style=("bold " + base) if ratio >= 0.6 else base)
        bar = self._bar(ratio, width=9)
        if bar:
            cell.append(bar, style=base)
        return cell

    @staticmethod
    def _bar(ratio: float, width: int = 9) -> str:
        """Render a proportional bar using eighth-block characters for a smooth tip."""
        ratio = max(0.0, min(1.0, ratio))
        units = ratio * width
        full = int(units)
        eighths = " ▏▎▍▌▋▊▉█"
        bar = "█" * full
        if full < width:
            tip = int((units - full) * 8)
            if tip:
                bar += eighths[tip]
        return bar

    @staticmethod
    def _text(value: str, style: str = "#dce5ee") -> Text:
        return Text(value, style=style)

    @staticmethod
    def _format_money(value: float) -> str:
        abs_value = abs(value)
        sign = "+" if value >= 0 else "-"
        if abs_value >= 1_000_000_000:
            return f"{sign}{abs_value / 1_000_000_000:.2f}B"
        if abs_value >= 1_000_000:
            return f"{sign}{abs_value / 1_000_000:.2f}M"
        if abs_value >= 1_000:
            return f"{sign}{abs_value / 1_000:.1f}K"
        return f"{sign}{abs_value:.0f}"

    @staticmethod
    def _format_strike(strike: float, decimals: int = 0) -> str:
        return f"{float(strike):,.{decimals}f}"

    @staticmethod
    def _imbalance(call_total: float, put_total_abs: float) -> float:
        return call_total / put_total_abs if put_total_abs else 0.0

    @staticmethod
    def _timestamp() -> str:
        return datetime.now().strftime("%H:%M:%S")

    def _event(self, message: str) -> None:
        line = f"{self._timestamp()} {message}"
        if self._events and self._events[0].endswith(message):
            return
        self._events.appendleft(line)

    def _p95_latency(self) -> float:
        if not self._latencies:
            return self._last_latency_ms
        values = sorted(self._latencies)
        index = max(0, round((len(values) - 1) * 0.95))
        return values[index]

    @staticmethod
    def _format_age(value: float | None) -> str:
        if value is None:
            return "--"
        if value < 1:
            return f"{value * 1000:.0f}ms ago"
        if value < 60:
            return f"{value:.1f}s ago"
        return f"{value / 60:.1f}m ago"

    @staticmethod
    def _health_color(health: str) -> str:
        return {
            "healthy": "#4ade80",
            "simulated": "#38bdf8",
            "degraded": "#fbbf24",
            "stale": "#fbbf24",
            "entitlement": "#fb7185",
            "down": "#fb7185",
        }.get(health, "#94a3b8")

    @staticmethod
    def _crossed_imbalance_threshold(previous: float, current: float) -> bool:
        thresholds = (0.75, 1.0, 1.25, 1.5, 2.0)
        return any((previous < threshold <= current) or (previous > threshold >= current) for threshold in thresholds)

    @staticmethod
    def _next_float_preset(current: float, presets: tuple[float, ...]) -> float:
        for index, value in enumerate(presets):
            if abs(float(current) - value) < 1e-9:
                return presets[(index + 1) % len(presets)]
        return presets[0]

    @staticmethod
    def _next_int_preset(current: int, presets: tuple[int, ...]) -> int:
        for index, value in enumerate(presets):
            if int(current) == value:
                return presets[(index + 1) % len(presets)]
        return presets[0]

    @staticmethod
    def _status_color(status: str) -> str:
        if status == "LIVE":
            return "green"
        if status == "SIM":
            return "cyan"
        if status == "REPLAY":
            return "cyan"
        if status == "STALE":
            return "amber"
        if status == "CONNECTED":
            return "cyan"
        return "red"

    @staticmethod
    def _hex_status(status: str) -> str:
        return {
            "LIVE": "#4ade80",
            "SIM": "#38bdf8",
            "REPLAY": "#38bdf8",
            "CONNECTED": "#38bdf8",
            "STALE": "#fbbf24",
        }.get(status, "#fb7185")

    def _workflow_label(self) -> str:
        if self.config.data_mode.upper() == "REPLAY":
            return "REPLAY RESEARCH LAB"
        if self.config.data_mode.upper() == "DEMO":
            return "DEMO RESEARCH"
        return "OPTIONS CHAIN"

    def _expiry_filter_choices(self) -> tuple[str, ...]:
        labels = self.consumer.available_expiries()
        choices = ["all"]
        if labels:
            choices.append("0dte")
        choices.extend(
            label for label in labels if label.lower() not in {"all", "0dte"}
        )
        return tuple(dict.fromkeys(choices))

    @staticmethod
    def _arrange_rows(rows, sort_mode, filter_mode, spot, max_volume):
        """Filter then sort the matrix rows. Pure function for easy testing."""
        return arrange_rows(rows, sort_mode, filter_mode, spot, max_volume)

    @staticmethod
    def _filter_rows(rows, filter_mode, spot, max_volume):
        """Filter rows by mode. Never returns empty if input was non-empty (usability safety)."""
        return filter_rows(rows, filter_mode, spot, max_volume)

    @staticmethod
    def _sort_rows(rows, sort_mode):
        return sort_rows(rows, sort_mode)

async def run_mock_session():
    """Boot the math engine, consumer state machine, and terminal together."""
    config = GexConfig.from_env()
    demo_config = GexConfig(
        symbol=config.symbol,
        symbols=config.symbols,
        data_mode="demo",
        data_provider=config.data_provider,
        contract_multiplier=config.contract_multiplier,
        risk_free_rate=config.risk_free_rate,
        days_to_expiry=config.days_to_expiry,
        refresh_interval_seconds=config.refresh_interval_seconds,
        stale_after_seconds=config.stale_after_seconds,
        replay_path=config.replay_path,
        replay_delay_seconds=config.replay_delay_seconds,
        tradovate_environment=config.tradovate_environment,
        expiry_filter=config.expiry_filter,
    )
    math_engine = IntradayGexEngine(multiplier=demo_config.contract_multiplier)
    state_consumer = StatefulGexConsumer(
        math_engine,
        target_underlying=demo_config.symbol,
        risk_free_rate=demo_config.risk_free_rate,
        data_mode=demo_config.data_mode,
        stale_after_seconds=demo_config.stale_after_seconds,
        expiry_filter=demo_config.expiry_filter,
    )
    state_consumer.current_spot = 5943.25
    state_consumer.session_open = 5904.50

    seed_rows: Iterable[tuple[int, int, int, float]] = (
        (5875, 2104, 8992, 0.18),
        (5900, 4781, 7406, 0.16),
        (5915, 5229, 5312, 0.15),
        (5925, 7925, 4812, 0.14),
        (5950, 13480, 3044, 0.13),
        (5975, 9441, 2105, 0.13),
        (6000, 10872, 1624, 0.14),
        (6025, 5128, 938, 0.15),
        (6050, 2775, 611, 0.16),
    )

    for strike, call_volume, put_volume, iv in seed_rows:
        await state_consumer.update_market_state(
            f'{{"type": "options_volume_tick", "strike": {strike}, '
            f'"option_type": "C", "volume": {call_volume}, "iv": {iv}}}'
        )
        await state_consumer.update_market_state(
            f'{{"type": "options_volume_tick", "strike": {strike}, '
            f'"option_type": "P", "volume": {put_volume}, "iv": {iv}}}'
        )

    app = GexTerminalApp(consumer=state_consumer, config=demo_config)
    await app.run_async()


if __name__ == "__main__":
    asyncio.run(run_mock_session())
