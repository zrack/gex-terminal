# Market Analysis

Snapshot reviewed June 12, 2026. Pricing, data entitlements, and platform
features change frequently; verify provider pages before publishing hard claims.

`gex-terminal` sits in a small but active market: options-market-structure tools
that turn option-chain data into gamma exposure levels, dealer-positioning
context, and intraday support/resistance zones.

## Current Positioning

`gex-terminal` is currently best positioned as an open-source, local-first
research terminal for traders and developers who want to understand and extend
GEX calculations rather than subscribe to a closed web dashboard.

Current strengths:

- Open-source and inspectable math.
- Fast terminal UI instead of a browser dashboard.
- Local demo/replay mode for no-credential testing.
- Provider adapter architecture for Tradovate, Databento, IBKR, yfinance, and
  replay data.
- Strike-level GEX matrix, gamma wall, zero-gamma node, call/put imbalance, and
  market-structure metrics.

Current constraints:

- Live provider integrations are still early.
- Uses cumulative intraday volume as a practical open-interest proxy until
  stronger live/open-interest data is wired in.
- Does not yet model dealer/customer trade direction.
- Does not include options flow, dark-pool prints, mobile apps, alerts,
  TradingView overlays, execution, or broad equity scanning.

## Similar Products

| Product | Typical Cost | Closest Functionality | Notes |
| --- | ---: | --- | --- |
| [SpotGamma](https://spotgamma.com/) | Essential $99/mo, Alpha $299/mo; annual discounts available | GEX levels, call/put walls, zero gamma, volatility trigger, real-time TRACE, 0DTE tools | One of the category leaders. Strongest benchmark for proprietary dealer-positioning models and market commentary. |
| [MenthorQ](https://menthorq.com/) | Premium $129/mo after first-month promo; Pro $349/mo after first-month promo | Futures gamma levels, net GEX, intraday gamma models, dashboards, platform integrations | Strong overlap with ES/NQ workflow and futures traders. |
| [GammaEdge](https://www.gammaedge.com/) | $150/mo monthly or $125/mo billed annually | Options market-structure levels, Discord bots, trend model | More community/Discord-oriented than terminal-oriented. |
| [Quant Data](https://quantdata.us/) | Starts around $62.50/mo for dashboard; API annual plan shown at $124.99/mo | Options flow, dealer exposure, GEX/DEX/VEX/CHEX, dark-pool prints, alerts, apps | More of a full options-flow and market-data platform than a focused GEX terminal. |
| [Unusual Whales](https://unusualwhales.com/pricing) | Around $48-$50/mo monthly; annual around $528-$530 | Live options flow, dark pools, market maker / Greek exposure pages, API | Cheaper broad flow platform; less specialized around futures GEX than SpotGamma/MenthorQ. |
| [Barchart](https://www.barchart.com/stocks/quotes/%24SPX/gamma-exposure) | Free tier; Plus $9.99/mo; Premier $29.95/mo | Gamma exposure charts based on OPRA data, options pages, screeners | Good free/low-cost comparison point. More website/data-table oriented. |
| [OptionCharts](https://optioncharts.io/) | Free basic features; paid Premium/Ultimate plans | GEX, DEX, historical options metrics, contract history | Free basic GEX is useful for research, but advanced indicators and real-time data are paid. |
| [TradingView](https://www.tradingview.com/) | Free; paid plans from $12.95/mo to $199.95/mo when billed annually, plus exchange data fees | Charting, options chains, Greeks, IV, Pine scripts, alerts, broker integrations | Excellent charting layer. Not a dedicated native dealer-GEX engine, though community scripts and integrations can approximate levels. |
| [Schwab thinkorswim](https://www.schwab.com/trading/thinkorswim) | No platform fee for Schwab clients; trading costs still apply | Options chains, Greeks, risk profile, probability analysis, paperMoney, scans, execution | Very strong broker platform, but not a purpose-built aggregate GEX/dealer-positioning terminal. |

## Free Alternatives

Free or mostly free alternatives exist, but they generally come with tradeoffs:

- [SpotGamma free tools](https://spotgamma.com/free-tools/) provide free
  market snapshots such as an SPX gamma exposure chart.
- [Barchart GEX pages](https://www.barchart.com/stocks/quotes/%24SPX/gamma-exposure)
  expose gamma exposure charts, with paid tiers for deeper site features.
- [OptionCharts](https://optioncharts.io/docs/) has free basic access, with
  advanced charts, downloads, and real-time data behind paid plans.
- TradingView has a free tier and community scripts, but reliable GEX scripts
  often depend on manually maintained levels, paid indicators, or external data.
- Broker platforms such as thinkorswim can be free to clients, but they usually
  provide contract-level options analytics rather than aggregate dealer-flow
  models.

The open-source gap is real: there are free pages and free scripts, but fewer
transparent, local-first tools that expose the calculation path and let
contributors add data adapters.

## Do Schwab And TradingView Have This?

Schwab's thinkorswim has a strong options workflow: option chains, Greeks,
simulated trades, risk profile, probability analysis, scanning, paper trading,
and execution. It does not appear to offer a native aggregate dealer GEX terminal
with gamma wall, zero-gamma, intraday dealer-flow modeling, and provider-adapter
extensibility.

TradingView has excellent charting, alerts, Pine Script, broker integrations,
options chains, live option prices, Greeks, and implied volatility. It also has
community or marketplace scripts for GEX-style levels. TradingView is useful as
a visualization and alert layer, but it is not primarily a transparent GEX
calculation engine.

## Typical Cost Ranges

Practical monthly ranges for this category:

- Free to $30/mo: delayed/basic GEX pages, Barchart, free TradingView, basic
  charting, limited tools.
- $50 to $80/mo: broad retail options-flow platforms such as Unusual Whales or
  entry Quant Data dashboard access.
- $99 to $150/mo: specialized GEX/market-structure products such as SpotGamma
  Essential, MenthorQ Premium, GammaEdge, or focused option calculators.
- $200 to $350/mo: advanced/intraday/pro tiers such as SpotGamma Alpha,
  MenthorQ Pro, or richer data/API workflows.
- $199+/mo for direct futures data feeds: Databento CME Globex plans are data
  infrastructure, not a trader-facing GEX app. They make sense when the project
  needs direct normalized market data and can absorb data engineering work.

Data fees are separate from app fees. For example, Tradovate advertises no
license fees on its platform tiers, but exchange data and trading fees still
apply; its support pages list a CME Group bundle at $12/month for
non-professional users. TradingView lists OPRA real-time options data at $2/month
for non-professional users, in addition to any TradingView subscription.

## Feature Gaps To Prioritize

Features competitors commonly have that `gex-terminal` does not yet have:

- Production-grade live option-chain discovery for ES/NQ and robust reconnects.
- Official open-interest ingestion instead of relying on intraday volume proxy.
- Multi-expiry views with explicit 0DTE filtering and expiration selection.
- Dealer/customer direction inference to avoid naive call-positive/put-negative
  assumptions.
- Vanna, charm, delta exposure, vega exposure, and theta exposure.
- Options-flow feed: sweeps, blocks, splits, premium, side, size, and filters.
- Historical session storage, backtesting, and day-over-day level comparison.
- Chart overlays and integrations for TradingView, NinjaTrader, Sierra Chart, or
  Discord.
- Alerts, webhooks, and level-crossing notifications.
- Multi-symbol scanner for ES, NQ, SPX, SPY, QQQ, IWM, and single names.
- Options P/L calculator with Greeks and volatility/time scenario controls.
- Mobile/web dashboard for users who do not live in a terminal.
- Data-quality panel showing provider latency, dropped messages, stale fields,
  and entitlement failures.

## Product Opportunity

The attractive niche is not "cheaper SpotGamma." Competing head-on with
proprietary positioning models and licensed real-time data would be expensive.

The better opening is:

- Open-source GEX research terminal.
- Local-first and credential-safe.
- Explainable model with transparent assumptions.
- Provider-agnostic adapter system.
- Replayable datasets for learning and reproducible research.
- Fast ES/NQ intraday workflow for traders who already have data access.

That makes `gex-terminal` interesting for contributors because they can improve
the model, add providers, submit normalized payload fixtures, and build export or
visualization tools without needing to join a closed commercial platform.

## Recommended Roadmap Additions

- Add a `GEX_MODEL_NOTES.md` or docs section explaining the current assumptions,
  especially volume-as-open-interest proxy, call/put sign convention, and
  limitations versus proprietary dealer-positioning models.
- Make one provider truly production-ready before widening the provider list.
- Add a historical session store so users can replay, compare, and validate
  levels against price action.
- Add 0DTE and expiry selection as a first-class UI workflow.
- Add vanna/charm/DEX metrics after the live option-chain model stabilizes.
- Add alerting for gamma wall shifts, zero-gamma crosses, stale data, and major
  exposure changes.
- Add export formats designed for TradingView overlays or Discord posts.
- Publish sample replay datasets so new users can evaluate the app without paid
  data.
