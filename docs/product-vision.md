# Product Vision

`gex-terminal` is not trying to be a cheaper clone of a closed commercial
dashboard. The stronger opportunity is an open-source, local-first GEX research
terminal that makes assumptions visible and gives contributors room to improve
the model, data adapters, replay fixtures, and visualization workflows.

## Signature Capabilities

These capabilities are intended to make the project distinctive and useful for
contributors.

### Live Gamma Regime Map

Build a real-time regime panel showing whether price is in positive gamma,
negative gamma, near zero-gamma, pinned near a gamma wall, or entering a
volatility expansion zone.

![Live Gamma Regime Map mockup](../assets/live-gamma-regime-map-mockup.svg)

### Replayable Market Days

Save full intraday sessions and replay them later with synchronized GEX, price,
wall shifts, zero-gamma moves, and event markers.

### TradingView Overlay Export

Export gamma wall, zero-gamma, call wall, put wall, and major exposure bands into
a TradingView-compatible format so users can overlay levels on their charts.

### GEX Alert Engine

Trigger local alerts for zero-gamma crosses, gamma wall shifts, stale data,
regime flips, and major call/put imbalance changes, with optional Discord or
webhook output.

### Multi-Symbol Market Structure Scanner

Scan ES, NQ, SPX, SPY, QQQ, and IWM to rank symbols by gamma concentration,
negative-gamma risk, 0DTE pressure, and the biggest intraday structural shifts.

## Contributor Hooks

The project is intentionally shaped so contributors can help without needing to
own every part of the stack:

- Improve the math model and document assumptions.
- Add provider adapters and normalized payload fixtures.
- Build replay datasets for reproducible research.
- Improve terminal panels, exports, alerts, and data-quality views.
- Compare generated levels against saved price action.
