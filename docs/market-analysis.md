# Competitive Landscape and Product Positioning

External market sources were reviewed August 14, 2026; repository capability
claims were reconciled to the `0.3.0` tree on August 31, 2026. This replaces the
June 12 market snapshot. Pricing, coverage, entitlements, and vendor features
change frequently; recheck the linked first-party sources before reusing price
or package claims.

## Executive Answer

| Question | Answer |
| --- | --- |
| Where does `gex-terminal` fit? | An open, local-first GEX model laboratory and market-structure research workbench for quants, developers, data engineers, and evidence-sensitive futures-options traders who want to own and interrogate the calculation. |
| Is the product unique? | Not because it calculates GEX, shows walls or a flip, runs locally, or is free. Each of those exists elsewhere. The differentiated claim is the combination of provider-normalized inputs, futures-aware Black-76 calculations, explicit provenance, side-by-side position-model comparison, deterministic replay, and fail-closed evidence boundaries. That combination is distinctive in this public scan, but it is not proof that no public or private product has an equivalent. |
| Is price the differentiation? | No. The MIT software price is an adoption wedge, but Barchart offers meaningful delayed GEX from $0 to $29.95/month and open-source alternatives are free. A useful live futures feed can also cost more than a retail app. Total cost includes data, setup, maintenance, and user time. |
| Is tunability the differentiation? | Partly. Inspectable and replaceable assumptions are valuable, but Barchart and open-source projects already expose many controls. Tunability becomes defensible when it is joined to identical-session replay, data lineage, model diffs, and saved experiment manifests. |
| What does building this provide? | Control of the calculation and data path; reproducible research; the ability to compare OI, raw-volume, and directionalized-volume proxies on the same capture; provider independence; a contributor workbench; and an honest boundary between numerical correctness and measured trading value. |
| What does it not yet provide? | A production-certified live ES/NQ workflow, observed dealer inventory, independently validated predictive edge, broad flow/dark-pool coverage, a polished hosted/mobile experience, or necessarily the lowest total cost. |

The recommended position is:

> **Own and interrogate the model.** `gex-terminal` is a local-first,
> provider-normalized research laboratory for equity, index, and native futures
> options. Every output carries its assumptions, provenance, quality state, and
> evidence ceiling, and the same captured session can be replayed across
> competing methodologies.

This is intentionally narrower than “a cheaper SpotGamma” or “another options
flow dashboard.”

## Method and Evidence Boundary

This review used:

- first-party pricing, product, documentation, and methodology pages;
- public repository documentation for open-source alternatives; and
- the current `gex-terminal` code, tests, assumptions, architecture, and
  [roadmap](../ROADMAP.md).

The scan compares publicly documented capabilities as of August 14, 2026. It
does not include paid hands-on trials, independent latency measurement, model
accuracy tests, realized performance, contract review, or private enterprise
features. Asset counts, “real-time” labels, and historical depth are vendor
claims unless explicitly stated otherwise. Prices are closest relevant public
list prices, not equivalent bundles; taxes, professional status, market-data
fees, and billing cadence may change the comparison.

## Current Product Truth

### Shipped strengths

- Contract-aware Black-76 for futures options and Black-Scholes for
  equity/index options, with explicit expiry, multiplier, IV, position-source,
  event-time, and pricing-model provenance.
- OI, raw-volume, and aggressor-directionalized volume models kept separate,
  with coverage and disagreement reporting rather than silently blended.
- Local replay browser, captured-session store, historical journal, Replay Lab,
  Demo Lab, provider-fixture workbench, sensitivity reports, and exportable
  snapshots.
- Normalized adapter boundary spanning replay, yfinance, provider-shaped
  fixtures, and implemented or scaffolded Tradovate, Databento, and IBKR paths.
- A numerical evidence gate and explicit
  `predictive_validity=unmeasured` ceiling.
- Versioned model profiles, reproducible experiment manifests, append-only
  corpus registration, and batch day/expiry/DTE-layer model comparisons.
- MIT source, deterministic fixtures, contributor tests, and local credential
  handling.

### Material constraints

- Replay and fixture paths are software-certified; no provider is yet
  production-certified end to end for credentialed, entitlement-backed live
  ES/NQ chain discovery.
- Open interest and trade volume remain positioning proxies. Aggressor side
  does not establish dealer/customer identity or opening/closing state.
- Synthetic fixtures and integrity-checked captures do not establish market
  edge, forecast validity, fill quality, or P&L.
- Alerts and TradingView outputs are local files, not hosted push, webhook, or
  native chart integrations.
- There is no stable public Python/REST/MCP contract, multi-symbol live scanner,
  DEX/vanna/charm production surface, or options-flow tape.
- The terminal is a poor fit for new, mobile-first, or commentary-seeking
  traders.

## Market Map

The category now has five overlapping product types:

1. **Premium trader terminals:** SpotGamma, MenthorQ, GammaEdge, Volland, and
   TradingFlow package levels, visual workflows, education, integrations, and
   commentary.
2. **Broad retail options platforms:** Unusual Whales, Quant Data, Tradytics,
   and similar products combine flow, dark pools, scanners, alerts, and Greek
   exposure.
3. **Developer data/API products:** Quant Data API, Unusual Whales API,
   FlashAlpha, SqueezeMetrics research data, and raw providers such as
   Databento reduce the need to build ingestion or calculations from scratch.
4. **Budget and generalist tools:** Barchart, OptionCharts, TradingView, and
   thinkorswim cover much of the visible workflow at low or bundled prices.
5. **Open and self-hosted projects:** GammaGrid, gex-dashboard, Futures Options
   S/D Dashboard, 0DTE Dealer Gamma, and simpler GEX scripts commoditize the
   basic calculation and increasingly cover local history, replay, APIs, and
   futures options.

### Direct and high-pressure competitors

| Product | Closest relevant public price | Strongest overlap | Where it is ahead | Where `gex-terminal` can differ |
| --- | ---: | --- | --- | --- |
| [SpotGamma](https://spotgamma.com/subscribe-to-spotgamma/) | Essential $99/mo; Alpha $299/mo; annual discounts | GEX levels, walls, gamma/volatility regimes, 0DTE tools | Category authority, polished SPX workflow, proprietary participant lenses, education, commentary, TRACE/HIRO history | Open calculations, interchangeable inputs, local ownership, model-level controls, provider provenance, reproducible same-session comparisons |
| [MenthorQ](https://menthorq.com/pricing/) | Premium $129/mo after promotion; Pro $349/mo after promotion | ES/NQ gamma levels and futures workflow | 1,400+ claimed assets, five-minute gamma updates, TradingView/NinjaTrader/Sierra/Bookmap and other integrations | Local engine, inspectable assumptions, normalized provider path, replay/evidence artifacts, user-replaceable models |
| [Barchart GEX](https://www.barchart.com/stocks/quotes/AAPL/gamma-exposure) | Free; Premier $29.95/mo or $239.95/yr | GEX/DEX, flip, walls, expiry and OI/volume controls | Best budget direct substitute; consolidated OPRA input, chart UI, expected move, intraday/EOD modes, published formulas, Premier CSV | Native futures-option path, local calculation, provider normalization, full provenance, captured-session replay, method comparison |
| [Unusual Whales](https://unusualwhales.com/pricing) | Retail $50/$75/$120 per month; API from $150/mo | GEX heatmaps, SPX exposure, flow, dark pools, alerts, API | Broad tape and market coverage, one-minute top-tier SPX exposure, established retail UX, WebSocket/MCP/API surfaces | Local user-owned engine and data, explicit model replacement, deterministic offline replay, stricter evidence ceilings |
| [Quant Data](https://quantdata.us/api) | Dashboard $74.99/mo; API $149.99/mo | GEX/DEX/vanna/charm, flow, history, REST/MCP | Strong documented developer surface, 6,000+ claimed tickers, intraday maps, history, broad options analytics | Vendor-calculation independence, raw model control, futures-native focus, provider/method comparison, local research ownership |
| [FlashAlpha](https://flashalpha.com/pricing) | Growth $299/mo for CME futures; Alpha $1,499/mo for deep history | API-first GEX and higher Greeks, ES/NQ, Black-76, history/replay | Closest public API threat to the quant/developer/futures niche; vendor claims CME futures, SDKs/MCP, full-chain levels, flow, and minute history at higher tiers | Open engine, BYO provider, local replay, explicit evidence ceilings, independent comparison instead of consuming one vendor estimate |
| [TradingFlow](https://tradingflow.com/) | $69/mo or $49/mo annual equivalent | GEX/DEX, flow tape, replay, filters and CSV | Strong value bundle and trader-facing “Time Machine” workflow | Formula-level tunability, futures-native research, local provider path, repeatable experiment artifacts |
| [GammaEdge](https://www.gammaedge.com/) | $150/mo or $125/mo annual equivalent | GEX/DEX/charm/vanna and market-structure levels | Education, community, Discord delivery, proprietary trend workflow | Open math, provider/data provenance, research replay, developer extensibility |
| [Volland](https://vol.land/pricing) | From $99/mo; advanced tiers $150-$1,000/mo | Dealer-positioning and multi-Greek analysis | Strong public description of transaction/quote-based dealer-side inference; advanced trader workspaces | Open implementation, lower entry cost, provider independence, deterministic local comparison; licensed participant evidence remains a roadmap gap |

### Open-source and self-hosted pressure

| Project | Publicly documented capability | Implication |
| --- | --- | --- |
| [GammaGrid](https://github.com/gammagrid/gammagrid) | AGPL self-hosted app with local SQLite, GEX, heatmaps, walls/flip, IV surface, full Greeks, history, and replay using delayed yfinance snapshots | “Open, local, and replayable” is no longer unique. Native futures providers, provider normalization, and evidence discipline are the stronger line. |
| [Darthreign/gex-dashboard](https://github.com/Darthreign/gex-dashboard) | MIT local package with GEX/DEX, 0DTE, vanna/charm, OI changes, history, Parquet/export, MCP, optional ES/NQ and provider backfill | The closest open-source feature threat found. Its free data-path durability and redistribution rights require separate review; `gex-terminal` still needs a clearer API and better visuals. |
| [Futures Options S/D Dashboard](https://github.com/Hewkaw02/Futures-Options-SD-Dashboard) | MIT credentialed CME futures dashboard using Black-76, GEX profiles, vanna, walls/flip, time travel, exports, and data-quality scoring | Futures-native Black-76 is not unique. Evidence-bounded model comparison and provider-normalized research must do more work. |
| [0DTE Dealer Gamma](https://github.com/puneet-chandna/0DTE-dealer-gamma) | Source-available SPX dashboard with FastAPI/Next.js, provider registry, Postgres history, WebSocket updates, and vectorized Black-Scholes | A polished open dashboard is attainable. The project is noncommercially licensed and equity-index focused, but it raises the UX bar. |
| [gex-tracker](https://github.com/Matteo-Ferrara/gex-tracker) and similar scripts | Basic call-positive/put-negative GEX calculation and charting | Strong evidence that the core math and standard walls/flip outputs are commodity features. |

### Adjacent products to integrate with, not clone

- [TradingView](https://www.tradingview.com/pricing/) is the charting and alert
  layer to feed. Pine cannot reliably replace a licensed live options-chain
  input, so portable audited levels and automation are the opportunity.
- [Schwab thinkorswim](https://www.schwab.com/trading/thinkorswim) is a strong
  broker-connected options, Greeks, scan, simulation, and execution workflow.
  It does not publicly document a comparable aggregate, replayable GEX model
  laboratory.
- [Cboe delayed quotes](https://www.cboe.com/delayed_quotes/spx/quote_table)
  provide manual reference inputs, Greeks, IV, and OI—not a governed automated
  GEX research feed. Public-page extraction restrictions make licensed adapter
  paths important.
- [OptionStrat](https://optionstrat.com/membership) is a better trade-construction
  and P/L experience. Its strengths are a reason to defer a generic strategy
  builder until the core research niche is proven.

## Best in the Industry by Job

These are evidence-bounded judgments from public documentation, not hands-on
rankings of latency, accuracy, support, or realized results.

| Job | Current benchmark | Why it matters to the roadmap |
| --- | --- | --- |
| Polished SPX/dealer workflow | SpotGamma | Sets the UX, explanation, 0DTE, and category-trust bar. |
| Turnkey futures trader workflow | MenthorQ | Sets the cross-platform integration and low-friction ES/NQ bar. |
| Broad retail options intelligence | Unusual Whales | Shows the value of tape, flow, alerts, breadth, and one product surface. |
| Developer/API access | Quant Data; FlashAlpha is the closest futures-method threat | Makes a paid API faster than building for users who do not require local ownership or replaceable math. |
| Public dealer-side inference explanation | Volland and SqueezeMetrics | Demonstrates how far position attribution can move beyond the standard sign convention. |
| Budget direct GEX | Barchart | Removes low price and basic tunability as defensible claims. |
| Open/local direct comparator | GammaGrid; gex-dashboard for feature breadth | Removes generic “open and replayable” positioning. |
| Visualization and alerts | TradingView | The sensible strategy is export/integration, not chart-platform replacement. |

## Differentiation Assessment

| Dimension | Current strength | Competitive conclusion | Product implication |
| --- | --- | --- | --- |
| Sticker price | Medium | Free software helps, but free pages, low-cost Barchart, and open-source peers exist. Live data may erase the savings. | Use price as adoption, education, and contributor access—not the positioning headline. |
| Model tunability | Medium-high | Valuable, but UI controls and open code exist elsewhere. | Make the shipped model profiles, experiment manifests, and identical-session diffs a visible primary workflow. |
| Auditability and provenance | High | Many vendors explain concepts; fewer expose a replaceable engine with per-output input and model provenance. | Keep every calculation traceable to provider, timestamp, IV source, multiplier, position source, pricing model, and quality state. |
| Reproducibility | High offline | Local history/replay exists elsewhere, but the same normalized replay across competing methodologies is less common. | Make model/provider comparison the hero workflow, not a secondary CLI. |
| Futures-native correctness | Medium-high | MenthorQ, FlashAlpha, and open-source futures dashboards now support this space. | Certify real ES/NQ first, extend to GC only after the contract/data path is stable, and benchmark Black-76 outputs. |
| Evidence discipline | High | Explicitly separating math, software-path tests, live certification, identity inference, and predictive value remains unusual. | Turn the evidence ledger and governed capture corpus into a visible product surface. |
| API/developer ergonomics | Low-medium | Quant Data, Unusual Whales, FlashAlpha, and some open-source peers are easier to build against. | Publish a stable read-only Python/library contract, then local REST/MCP if demand is proven. |
| Live trader experience | Low | Premium vendors win on integrations, automatic updates, alerts, support, and commentary. | Do not claim production substitution until one live path and delivery loop are certified. |

The most durable prospective moat is not the TUI, wall calculation, or free
license. It is a growing corpus of governed point-in-time captures plus a
trusted history of model/provider comparisons, explicit lineage, and honest
validation results. That moat has not yet been built.

## Persona Fit

The persona lens reuses patterns already developed in adjacent projects:
advanced ES/NQ futures traders using NinjaTrader and replay, advanced SPY/index
options users, phone-first novice/prop-evaluation traders, and Python engineers
who extend one deterministic workflow without private production data. Those
patterns were adapted to this product rather than treated as validated
`gex-terminal` customer interviews.

| Persona | Job to be done | Current fit | Primary blocker | Product priority |
| --- | --- | ---: | --- | ---: |
| Quant/model researcher | Inspect assumptions, compare position models, replay controlled sessions, preserve point-in-time provenance | High offline; low empirical | No governed real historical corpus or out-of-sample evidence; the shipped batch surface has only synthetic/offline inputs | Primary |
| Python/data engineer or contributor | Add licensed feeds, schemas, models, fixtures, exports, and tests without leaking credentials | High | Live validation needs credentials; no stable library/API contract; adapter readiness is uneven | Primary |
| Advanced ES/NQ futures trader with existing data | Generate fast structural levels, regime context, overlays, and alerts while understanding assumptions | Medium-low | No production-certified live provider, automated integration loop, or measured trading value | Secondary after live certification |
| Advanced options/volatility trader | Compare GEX with DEX/vanna/charm, flow, term structure, and volatility context | Low-medium | Missing production multi-Greek and flow surfaces; current focus is narrow | Secondary/later |
| Educator/student | Learn GEX, contract treatment, model differences, and evidence limits without a paid feed | Medium-high | No explicit curriculum; synthetic examples can be mistaken for market evidence | Tertiary |
| New, mobile-first, or prop-evaluation trader | Receive simple levels, coaching, and account-survival guidance on a phone | Low | Terminal density, setup, no hosted delivery, no validated signal | Deliberate non-target |

The primary market should therefore be **quants and developers who value
control**, with advanced futures traders as the first adjacent user once live
certification is real. Chasing the novice/mobile audience would pull the product
toward a crowded hosted-signals business and away from its best assets.

## Product Implications From The Competitive Scan

The scan supports four durable decisions:

1. Certify one ES/NQ provider path before widening provider, symbol, or delivery
   breadth.
2. Build licensed, governed point-in-time evidence after certification; model
   profiles, manifests, corpus contracts, and batch comparisons are now shipped
   foundations, not remaining feature gaps.
3. Stabilize a public read-only research interface, then build scanners,
   integrations, and alerts only on a certified path with visible quality.
4. Keep broad flow, dark pools, mobile/social, execution, and proprietary
   commentary outside the core thesis unless persona evidence changes it.

[ROADMAP.md](../ROADMAP.md) is the sole owner of current sequence, status,
dependencies, and exit criteria. This section records the market evidence's
implications without maintaining a second delivery checklist.

## Decision Gates and Success Evidence

| Decision | Evidence required before promotion |
| --- | --- |
| Call a live path certified | A saved redacted report covers entitlements, active contracts, chain coverage, OI/IV provenance, timing, reconnects, and failure handling for the exact provider, symbol, environment, and window; any broader claim follows a packet-defined recurrence rule. |
| Claim model-comparison leadership | A user can replay one governed session through multiple named models and reproduce a versioned diff artifact from the same inputs. |
| Claim research value | A governed corpus and preregistered evaluation protocol exist; results include null/negative findings and keep predictive validity separate from numerical correctness. |
| Target active futures traders | The live path, overlay/alert delivery, data-quality visibility, and failure recovery work as one tested workflow. |
| Add more providers or symbols | The first certified path has stable contracts and comparison metrics; new coverage does not weaken provenance or quality gates. |
| Claim a price advantage | Total cost of ownership includes app, data entitlement, setup, maintenance, and user time—not the $0 software license alone. |

## Primary Sources

Prices and capabilities were checked August 14, 2026.

- SpotGamma: [plans](https://spotgamma.com/subscribe-to-spotgamma/),
  [price explanation](https://support.spotgamma.com/hc/en-us/articles/1500002666102-What-is-the-cost-of-a-SpotGamma-Subscription),
  [GEX methodology](https://spotgamma.com/gamma-exposure-gex/), and
  [API/export limits](https://support.spotgamma.com/hc/en-us/articles/50266085426195-Does-SpotGamma-have-an-API-Can-I-export-data).
- MenthorQ: [pricing](https://menthorq.com/pricing/),
  [coverage](https://menthorq.com/guide/menthorq-asset-coverage/),
  [gamma levels](https://menthorq.com/guide/key-gamma-levels/), and
  [integrations](https://menthorq.com/guide/menthorq-trading-integrations/).
- Barchart: [GEX](https://www.barchart.com/stocks/quotes/AAPL/gamma-exposure)
  and [membership pricing](https://www.barchart.com/membership-comparison).
- Unusual Whales: [retail pricing](https://unusualwhales.com/pricing),
  [API pricing](https://unusualwhales.com/pricing?product=api), and
  [API documentation](https://api.unusualwhales.com/docs).
- Quant Data: [API and pricing](https://quantdata.us/api) and
  [GEX API guide](https://help.quantdata.us/en/articles/15807345-gamma-exposure-gex-api-python-quickstart-dealer-positioning-guide).
- FlashAlpha: [pricing](https://flashalpha.com/pricing),
  [API](https://flashalpha.com/api), and
  [futures/Black-76 documentation](https://flashalpha.com/docs/lab-api-overview).
- Other premium benchmarks: [TradingFlow](https://tradingflow.com/),
  [Volland](https://vol.land/pricing),
  [GammaEdge](https://www.gammaedge.com/), and
  [SqueezeMetrics](https://squeezemetrics.com/monitor/dix).
- Budget/adjacent benchmarks: [OptionCharts](https://optioncharts.io/pricing),
  [TradingView](https://www.tradingview.com/pricing/),
  [thinkorswim](https://www.schwab.com/trading/thinkorswim), and
  [Cboe delayed quotes](https://www.cboe.com/delayed_quotes/spx/quote_table).
- Open-source comparators: [GammaGrid](https://github.com/gammagrid/gammagrid),
  [gex-dashboard](https://github.com/Darthreign/gex-dashboard),
  [Futures Options S/D Dashboard](https://github.com/Hewkaw02/Futures-Options-SD-Dashboard),
  [0DTE Dealer Gamma](https://github.com/puneet-chandna/0DTE-dealer-gamma), and
  [gex-tracker](https://github.com/Matteo-Ferrara/gex-tracker).
