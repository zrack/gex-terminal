import asyncio
from gex_engine import IntradayGexEngine
from gex_consumer import StatefulGexConsumer
from tradovate_adapter import TradovateAdapter
from gex_terminal import GexTerminalApp

async def main():
    # 1. Initialize the Math Engine (50 multiplier for E-mini futures)
    math_engine = IntradayGexEngine(multiplier=50)
    
    # 2. Initialize the Memory Consumer for ES
    state_consumer = StatefulGexConsumer(math_engine, target_underlying="ES")
    
    # 3. Initialize the Tradovate Adapter
    data_adapter = TradovateAdapter(state_consumer, target_underlying="ES")
    
    # 4. Spin up the background tasks
    # Run the live data stream
    stream_task = asyncio.create_task(data_adapter.stream_market_data())
    # Run the math calculation loop every 2 seconds
    calc_task = asyncio.create_task(state_consumer.continuous_calculation_loop(interval_seconds=2.0))
    
    # 5. Launch the Terminal UI (This blocks the main thread until the user quits)
    app = GexTerminalApp(consumer=state_consumer)
    await app.run_async()
    
    # Clean up tasks on exit
    stream_task.cancel()
    calc_task.cancel()

if __name__ == "__main__":
    asyncio.run(main())
