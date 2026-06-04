import asyncio
import time
from collections import deque
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


class GexTerminalApp(App):
    """A real-time terminal interface tracking intraday option gamma imbalances."""

    TITLE = "Intraday GEX Imbalance Terminal"
    CSS_PATH = str(Path(__file__).with_name("gex_terminal.tcss"))

    BINDINGS = [
        ("q", "quit", "Quit"),
        ("r", "refresh_terminal_data", "Refresh"),
        ("s", "cycle_sort", "Sort"),
        ("f", "cycle_filter", "Filter"),
    ]

    SORT_MODES = ("strike", "net", "volume")
    FILTER_MODES = ("all", "near", "active")
    SORT_LABELS = {"strike": "strike ↑", "net": "|net| ↓", "volume": "volume ↓"}
    FILTER_LABELS = {"all": "all strikes", "near": "near-money", "active": "active only"}

    def __init__(self, consumer: StatefulGexConsumer, config: GexConfig | None = None):
        super().__init__()
        self.consumer = consumer
        self.config = config or GexConfig.from_env()
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
        self._last_refresh_at: str = "--:--:--"

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
                yield Static("", id="zone-ladder", classes="zone-card")

            with Vertical(id="flow-panel"):
                yield Static("Session GEX Flow", classes="section-title")
                yield Static("rolling 36 intervals", classes="subtle")
                yield Sparkline([], min_color="#fb7185", max_color="#38bdf8", id="gex-flow")

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
            f"{self.config.symbol} · OPTIONS CHAIN · CUMULATIVE SESSION VOLUME"
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

    def _render_controls(self) -> None:
        self.query_one("#matrix-controls", Static).update(
            f"sort: [#cbd5e1]{self.SORT_LABELS[self._sort_mode]}[/]  ·  "
            f"filter: [#cbd5e1]{self.FILTER_LABELS[self._filter_mode]}[/]   "
            f"[#5b6675]([b]s[/] sort  [b]f[/] filter  [b]r[/] refresh)[/]"
        )

    def _render_status_bar(self, status: str) -> None:
        color = self._status_color(status)
        bar = Text(" ", style="#94a3b8")
        segments = (
            f"provider {self.config.data_provider}",
            f"{self.config.symbol} ×{self.config.contract_multiplier}",
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

    async def refresh_terminal_data(self) -> None:
        """Poll the consumer and render the latest GEX matrix."""
        started = time.perf_counter()
        data = await self.consumer.process_latest_snapshot(days_to_expiry=self.config.days_to_expiry)
        self._last_latency_ms = (time.perf_counter() - started) * 1000
        self._latencies.append(self._last_latency_ms)
        self._last_refresh_at = self._timestamp()
        self._render_lifecycle()
        status = self.consumer.runtime_status
        self._render_status_bar(status)

        if "error" in data:
            self._last_data = None
            self._render_empty_state(data["error"], status)
            return

        self._last_data = data
        self._gex_flow.append(float(data["total_net_gex"]))
        self._record_events(data)
        self._render_metrics(data)
        self._render_table(data)
        self._render_structure(data)
        self._render_sidebar(data)
        self._render_flow()
        self._render_events()
        self._render_state_banner(status)

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
        self.query_one("#dealer-regime", Static).update(
            f"[b]Dealer Regime[/]   [#64748b]--[/]\nNo snapshot to model yet."
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

        max_volume = max(
            (int(value["C"]) + int(value["P"]) for value in self.consumer.chain_state.values()),
            default=0,
        )
        max_abs_net = max((abs(float(value)) for value in data["net_gex"]), default=0)
        nearest_zero = float(data.get("nearest_zero_strike", data["zero_gamma_strike"]))

        rows = []
        for strike, gamma, call_gex, put_gex, net_gex in zip(
            data["strikes"], data["gammas"], data["call_gex"], data["put_gex"], data["net_gex"]
        ):
            state = self.consumer.chain_state.get(float(strike), {"C": 0, "P": 0})
            rows.append({
                "strike": float(strike),
                "gamma": float(gamma),
                "call_gex": float(call_gex),
                "put_gex": float(put_gex),
                "net_gex": float(net_gex),
                "call_vol": int(state["C"]),
                "put_vol": int(state["P"]),
                "volume": int(state["C"]) + int(state["P"]),
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
        regime_label = "+GEX" if total_net >= 0 else "-GEX"
        regime_color = "green" if total_net >= 0 else "red"

        self.query_one("#structure-meta", Static).update(
            f"computed {self._last_latency_ms:.0f}ms ago | p95 {self._p95_latency():.0f}ms"
        )
        self.query_one("#dealer-regime", Static).update(
            f"[b]Dealer Regime[/]   [{regime_color}]{regime_label}[/]\n"
            f"Net {self._format_money(total_net)} · wall pinned {wall}\n"
            f"Hedging {'compresses' if total_net >= 0 else 'accelerates'} realized vol."
        )
        self.query_one("#balance-pressure", Static).update(
            f"[b]Balance Pressure[/]   [cyan]{imbalance:.2f}x[/]\n"
            f"{'Call-side' if imbalance >= 1 else 'Put-side'} leads on the volume proxy."
        )
        self.query_one("#vol-boundary", Static).update(
            f"[b]Volatility Boundary[/]   [amber]{zero}[/]\n"
            f"Zero-gamma flip — a break shifts the vol regime."
        )
        net_values = [float(value) for value in data["net_gex"]]
        positive = sum(value for value in net_values if value > 0)
        negative = abs(sum(value for value in net_values if value < 0))
        share = positive / (positive + negative) if (positive + negative) else 0.5
        track = 16
        green_cells = max(0, min(track, round(share * track)))
        red_cells = track - green_cells
        gauge = Text("Net Gamma Profile\n", style="bold #8a97a6")
        gauge.append("█" * green_cells, style="#4ade80")
        gauge.append("│", style="#38bdf8")
        gauge.append("█" * red_cells, style="#fb7185")
        gauge.append("\n")
        gauge.append(f"+GEX {wall} wall", style="#4ade80")
        gauge.append("  ", style="#64748b")
        gauge.append(f"zero {zero}", style="#38bdf8")
        self.query_one("#zone-ladder", Static).update(gauge)

    def _render_sidebar(self, data: dict) -> None:
        contract_count = len(data["strikes"])
        volume = sum(
            int(value["C"]) + int(value["P"]) for value in self.consumer.chain_state.values()
        )
        self.query_one("#feed-chain", Static).update(f"[green]*[/] Option chain\n  {contract_count:,} contracts")
        self.query_one("#feed-proxy", Static).update(f"[amber]*[/] OI proxy\n  {volume:,} volume")
        self.query_one("#feed-lock", Static).update("[green]*[/] State lock\n  clean")

    def _render_lifecycle(self) -> None:
        status = self.consumer.runtime_status
        color = self._status_color(status)
        if status != self._last_runtime_status:
            self._event(f"runtime state {status}")
            self._last_runtime_status = status

        self.sub_title = (
            f"{self.config.symbol} · OPTIONS CHAIN · CUMULATIVE SESSION VOLUME · {status}"
        )

        self.query_one("#feed-websocket", Static).update(
            f"[{color}]*[/] Data mode\n  {status}"
        )
        self.query_one("#matrix-meta", Static).update(
            f"mode: {status} | expiry: {self.config.days_to_expiry:g}d | "
            f"multiplier: {self.config.contract_multiplier} | rate: {self.config.risk_free_rate:.2%}"
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
            self._event(f"gamma wall pinned at {self._format_strike(wall)}")
        elif wall != self._last_wall:
            self._event(
                f"gamma wall shifted {self._format_strike(self._last_wall)} -> {self._format_strike(wall)}"
            )

        if self._last_zero is None:
            self._event(f"zero node interpolated at {self._format_strike(zero, decimals=1)}")
        elif abs(zero - self._last_zero) >= 1:
            delta = zero - self._last_zero
            self._event(
                f"zero node moved {delta:+.1f} handles to {self._format_strike(zero, decimals=1)}"
            )

        if self._last_regime is None:
            self._event(f"dealer regime initialized {regime}")
        elif regime != self._last_regime:
            self._event(f"dealer regime flipped {self._last_regime} -> {regime}")

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
    def _crossed_imbalance_threshold(previous: float, current: float) -> bool:
        thresholds = (0.75, 1.0, 1.25, 1.5, 2.0)
        return any((previous < threshold <= current) or (previous > threshold >= current) for threshold in thresholds)

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

    @staticmethod
    def _arrange_rows(rows, sort_mode, filter_mode, spot, max_volume):
        """Filter then sort the matrix rows. Pure function for easy testing."""
        return GexTerminalApp._sort_rows(
            GexTerminalApp._filter_rows(rows, filter_mode, spot, max_volume),
            sort_mode,
        )

    @staticmethod
    def _filter_rows(rows, filter_mode, spot, max_volume):
        """Filter rows by mode. Never returns empty if input was non-empty (usability safety)."""
        if filter_mode == "near" and spot:
            window = max(spot * 0.01, 1.0)
            subset = [row for row in rows if abs(row["strike"] - spot) <= window]
            return subset or list(rows)
        if filter_mode == "active" and max_volume:
            threshold = max_volume * 0.25
            subset = [row for row in rows if row["volume"] >= threshold]
            return subset or list(rows)
        return list(rows)

    @staticmethod
    def _sort_rows(rows, sort_mode):
        if sort_mode == "net":
            return sorted(rows, key=lambda row: abs(row["net_gex"]), reverse=True)
        if sort_mode == "volume":
            return sorted(rows, key=lambda row: row["volume"], reverse=True)
        return sorted(rows, key=lambda row: row["strike"])


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
    )
    math_engine = IntradayGexEngine(multiplier=demo_config.contract_multiplier)
    state_consumer = StatefulGexConsumer(
        math_engine,
        target_underlying=demo_config.symbol,
        risk_free_rate=demo_config.risk_free_rate,
        data_mode=demo_config.data_mode,
        stale_after_seconds=demo_config.stale_after_seconds,
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
