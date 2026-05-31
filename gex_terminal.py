import asyncio
import time
from collections import deque
from datetime import datetime
from typing import Iterable

from rich.text import Text
from textual.app import App, ComposeResult
from textual.containers import Container, Grid, Vertical
from textual.widgets import DataTable, Footer, Header, Sparkline, Static

from gex_consumer import StatefulGexConsumer
from gex_config import GexConfig
from gex_engine import IntradayGexEngine


class GexTerminalApp(App):
    """A real-time terminal interface tracking intraday option gamma imbalances."""

    TITLE = "Intraday GEX Imbalance Terminal"
    CSS_PATH = "gex_terminal.tcss"

    BINDINGS = [("q", "quit", "Quit Terminal"), ("r", "refresh_terminal_data", "Refresh")]

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

        yield Footer()

    def _metric(self, label: str, value: str, corner: str, foot: str, value_id: str) -> Container:
        return Container(
            Static(f"{label.upper()}                 {corner}", classes="metric-label"),
            Static(value, id=value_id, classes="metric-value"),
            Static(foot, id=f"{value_id}-foot", classes="metric-foot"),
            classes="metric-card",
        )

    def on_mount(self) -> None:
        self.title = "Intraday GEX Imbalance Terminal"
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
        self.set_interval(self.config.refresh_interval_seconds, self.refresh_terminal_data)
        self.call_later(self.refresh_terminal_data)

    async def action_refresh_terminal_data(self) -> None:
        await self.refresh_terminal_data()

    async def refresh_terminal_data(self) -> None:
        """Poll the consumer and render the latest GEX matrix."""
        started = time.perf_counter()
        data = await self.consumer.process_latest_snapshot(days_to_expiry=self.config.days_to_expiry)
        self._last_latency_ms = (time.perf_counter() - started) * 1000
        self._latencies.append(self._last_latency_ms)
        self._render_lifecycle()

        if "error" in data:
            self._render_empty_state(data["error"])
            return

        self._gex_flow.append(float(data["total_net_gex"]))
        self._record_events(data)
        self._render_metrics(data)
        self._render_table(data)
        self._render_structure(data)
        self._render_sidebar(data)
        self._render_flow()
        self._render_events()

    def _render_empty_state(self, reason: str) -> None:
        self.query_one("#stat-latency", Static).update(f"{self._last_latency_ms:.0f}ms")
        self.query_one("#feed-chain", Static).update("[red]*[/] Option chain\n  empty")
        self.query_one("#dealer-regime", Static).update(f"[amber]Waiting for data[/]\n{reason}")

    def _render_metrics(self, data: dict) -> None:
        total_net = float(data["total_net_gex"])
        call_total = sum(float(value) for value in data["call_gex"])
        put_total_abs = abs(sum(float(value) for value in data["put_gex"]))
        imbalance = self._imbalance(call_total, put_total_abs)
        regime = "positive gamma regime" if total_net >= 0 else "negative gamma regime"

        self.query_one("#stat-spot", Static).update(f"{self.consumer.current_spot:,.2f}")
        self.query_one("#stat-spot-foot", Static).update(self.consumer.target_underlying)

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

        rows = list(zip(
            data["strikes"],
            data["gammas"],
            data["call_gex"],
            data["put_gex"],
            data["net_gex"],
        ))
        for strike, gamma, call_gex, put_gex, net_gex in rows:
            state = self.consumer.chain_state.get(float(strike), {"C": 0, "P": 0})
            total_volume = int(state["C"]) + int(state["P"])
            row_style = self._row_style(
                strike=float(strike),
                wall=float(data["gamma_wall_strike"]),
                nearest_zero=nearest_zero,
                total_volume=total_volume,
                max_volume=max_volume,
            )
            strike_label = self._strike_label(
                strike,
                data["gamma_wall_strike"],
                nearest_zero,
            )
            table.add_row(
                strike_label,
                self._text(f"{int(state['C']):,}", row_style),
                self._text(f"{int(state['P']):,}", row_style),
                self._text(f"{float(gamma):.5f}", row_style),
                self._money_cell(float(call_gex), row_style),
                self._money_cell(float(put_gex), row_style),
                self._net_cell(float(net_gex), max_abs_net, row_style),
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
            f"Dealer Regime                 [{regime_color}]{regime_label}[/]\n"
            f"Net exposure is {self._format_money(total_net)}. Wall is pinned at {wall}. "
            f"Hedging flows are modeled as {'compressing' if total_net >= 0 else 'accelerating'} realized volatility."
        )
        self.query_one("#balance-pressure", Static).update(
            f"Balance Pressure              [cyan]{imbalance:.2f}x[/]\n"
            f"{'Call-side' if imbalance >= 1 else 'Put-side'} exposure is leading on the intraday volume proxy."
        )
        self.query_one("#vol-boundary", Static).update(
            f"Volatility Boundary           [amber]{zero}[/]\n"
            f"Interpolated zero-gamma boundary. A break through it may shift the realized volatility regime."
        )
        self.query_one("#zone-ladder", Static).update(
            f"[green]+GEX zone[/]\n"
            f"[cyan]zero {zero}[/]\n"
            f"[red]-GEX zone[/]"
        )

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

    def _colored_money(self, value: float) -> str:
        color = "green" if value >= 0 else "red"
        return f"[{color}]{self._format_money(value)}[/]"

    def _money_cell(self, value: float, fallback_style: str = "#dce5ee") -> Text:
        style = "#4ade80" if value >= 0 else "#fb7185"
        if fallback_style == "#64748b":
            style = "#64748b"
        return Text(self._format_money(value), style=style)

    def _net_cell(self, value: float, max_abs_net: float, fallback_style: str = "#dce5ee") -> Text:
        style = "#4ade80" if value >= 0 else "#fb7185"
        if fallback_style == "#64748b":
            style = "#64748b"
        intensity = 0 if max_abs_net == 0 else max(1, round(abs(value) / max_abs_net * 8))
        cell = Text(self._format_money(value), style=style)
        if intensity:
            cell.append(" " + ("#" * intensity), style=style)
        return cell

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
        if status == "STALE":
            return "amber"
        if status == "CONNECTED":
            return "cyan"
        return "red"


async def run_mock_session():
    """Boot the math engine, consumer state machine, and terminal together."""
    config = GexConfig.from_env()
    demo_config = GexConfig(
        symbol=config.symbol,
        symbols=config.symbols,
        data_mode="demo",
        contract_multiplier=config.contract_multiplier,
        risk_free_rate=config.risk_free_rate,
        days_to_expiry=config.days_to_expiry,
        refresh_interval_seconds=config.refresh_interval_seconds,
        stale_after_seconds=config.stale_after_seconds,
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
