import asyncio
from textual.app import App, ComposeResult
from textual.containers import Container, Vertical, Horizontal
from textual.widgets import Header, Footer, DataTable, Static
from gex_engine import IntradayGexEngine
from gex_consumer import StatefulGexConsumer

class GexTerminalApp(App):
    """A real-time terminal interface tracking intraday option gamma imbalances."""
    
    CSS = """
    Screen {
        layout: vertical;
    }
    #metrics-panel {
        height: 5;
        margin: 1;
        border: solid gray;
    }
    .metric-box {
        width: 25%;
        content-align: center middle;
        text-style: bold;
    }
    #table-container {
        height: 1fr;
        margin: 1;
    }
    """
    
    BINDINGS = [("q", "quit", "Quit Terminal")]

    def __init__(self, consumer: StatefulGexConsumer):
        super().__init__()
        self.consumer = consumer

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        
        # Top Metrics Bar
        with Horizontal(id="metrics-panel"):
            yield Static("SPOT: --", id="stat-spot", classes="metric-box")
            yield Static("NET GEX: --", id="stat-netgex", classes="metric-box")
            yield Static("GAMMA WALL: --", id="stat-wall", classes="metric-box")
            yield Static("ZERO NODE: --", id="stat-zero", classes="metric-box")
            
        # Main Strike Ledger
        with Container(id="table-container"):
            yield DataTable(id="gex-table")
            
        yield Footer()

    def on_mount(self) -> None:
        """Initialize the data table configuration when the app starts."""
        table = self.query_one("#gex-table", DataTable)
        table.cursor_type = "row"
        table.add_columns("Strike", "Call Volume", "Net GEX ($/1%)", "Put Volume")
        
        # Kick off the background live calculation loop
        self.set_interval(1.0, self.refresh_terminal_data)

    async def refresh_terminal_data(self) -> None:
        """Polls the state consumer and renders updates to the screen elements."""
        # Query our consumer for the latest numpy-computed metrics matrix
        data = await self.consumer.process_latest_snapshot(days_to_expiry=0.01)
        
        if "error" in data:
            return

        # 1. Update Top Panel KPI Cards
        self.query_one("#stat-spot", Static).update(f"SPOT: {self.consumer.current_spot:.2f}")
        self.query_one("#stat-netgex", Static).update(f"TOTAL GEX: ${data['total_net_gex']/1e6:.2f}M")
        self.query_one("#stat-wall", Static).update(f"GAMMA WALL: {data['gamma_wall_strike']}")
        self.query_one("#stat-zero", Static).update(f"ZERO NODE: {data['zero_gamma_strike']}")

        # 2. Update the Strike Matrix rows
        table = self.query_one("#gex-table", DataTable)
        table.clear()

        for i, strike in enumerate(data["strikes"]):
            # Format numbers cleanly for compact presentation
            net_gex_val = data["net_gex"][i]
            gex_str = f"${net_gex_val/1e3:.1f}K" if abs(net_gex_val) < 1e6 else f"${net_gex_val/1e6:.2f}M"
            
            # Identify special rows visually via indicator tokens
            strike_label = f"{strike:.0f}"
            if strike == data["gamma_wall_strike"]:
                strike_label += " [WALL]"
            elif strike == data["zero_gamma_strike"]:
                strike_label += " [FLIP]"

            table.add_row(
                strike_label,
                f"{self.consumer.chain_state[strike]['C']:,}",
                gex_str,
                f"{self.consumer.chain_state[strike]['P']:,}"
            )

# --- Local Simulation Launcher ---
async def run_mock_session():
    """Boots the math engine, consumer state machine, and terminal together."""
    math_engine = IntradayGexEngine(multiplier=50) # ES configuration
    state_consumer = StatefulGexConsumer(math_engine, target_underlying="ES")
    
    # Pre-seed background state data so the screen initializes instantly
    state_consumer.current_spot = 5000.0
    for strike in range(4960, 5050, 10):
        await state_consumer.update_market_state(
            f'{{"type": "options_volume_tick", "strike": {strike}, "option_type": "C", "volume": 500, "iv": 0.12}}'
        )
        await state_consumer.update_market_state(
            f'{{"type": "options_volume_tick", "strike": {strike}, "option_type": "P", "volume": 450, "iv": 0.12}}'
        )

    # Initialize and execute the Textual runtime application
    app = GexTerminalApp(consumer=state_consumer)
    await app.run_async()

if __name__ == "__main__":
    asyncio.run(run_mock_session())