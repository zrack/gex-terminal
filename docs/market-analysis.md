# Competitive Landscape and Product Strategy

External market sources and public product materials were reviewed on
September 3, 2026. Repository capability claims were reconciled to the `0.4.0`
tree. Pricing, coverage, data rights, entitlements, and vendor features change
frequently; recheck the linked first-party sources before reusing a specific
claim.

## Executive Answer

| Question | Answer |
| --- | --- |
| What does the current market signal? | The reviewed public offers make baseline GEX charts easy to obtain and increasingly package interpretation, intraday position estimates, replay, public outcome records, chart integrations, APIs, MCP surfaces, and AI-assisted synthesis around them. This is a current-snapshot inference, not a longitudinal adoption study. |
| What are the closest new threats by overlap? | [GammaTape](https://gammatape.com/) overlaps most with the focused ES/NQ trader workflow through SPX/NDX 0DTE levels, replay, and chart delivery. [FlashAlpha](https://flashalpha.com/pricing) overlaps most with the native-futures developer workflow. Both make “GEX for futures traders” insufficient positioning. |
| Why is Nightglass important? | [Nightglass](https://nightglass.trade/) publicly positions itself as options-flow research; the reviewed materials did not establish native futures-options coverage. Its importance is product design: it narrows raw data, explains why an item survived, joins it to a decision workflow, and keeps a public outcome record. |
| Where can `gex-terminal` win? | As the auditable, futures-native market-structure workbench for ES/NQ: every level traces to a source, contract, timestamp, model, quality state, and evidence ceiling; competing position models can be replayed on identical inputs. |
| What is not a moat? | Basic GEX math, call-positive/put-negative signs, walls, flips, a local dashboard, free software, or Black-76 by itself. Each is already available elsewhere. |
| What could become a moat? | A governed corpus of point-in-time futures-options sessions plus reproducible provider/model comparisons, visible disagreement, and an honest record of descriptive and outcome evidence. That moat does not exist yet. |
| What should the first commercial shape be? | Test a packaged bring-your-own-data desktop product first. Keep the MIT research kernel open; charge, if users validate the model, for distribution, certified live workflows, automation, integrations, governed storage, and support. |

The recommended position is:

> **Know what produced the level.** `gex-terminal` is a local-first ES/NQ
> market-structure instrument for researchers and advanced traders who want to
> inspect the data, assumptions, model disagreement, quality state, and later
> outcome behind every GEX proxy.

This is narrower than a broad options-flow terminal and more defensible than
“another gamma dashboard.”

## Method and Evidence Boundary

This review used first-party vendor product, pricing, methodology, integration,
and documentation pages; exchange and clearing-volume publications; public
source repositories; and the current application, tests, and documentation.

The review did not include paid trials, customer interviews, independent
latency or uptime measurement, contract or regulatory advice, subscriber
counts, retention, realized performance, or private enterprise features.
Vendor feature, accuracy, asset-count, “real-time,” and performance statements
remain vendor claims unless an exchange or clearing source is explicitly named.
An unavailable public detail is recorded as unknown, not assumed absent.

Strategic comparisons are qualitative. “Closest” means greatest overlap with
the intended user and workflow across five lenses: native ES/NQ inputs, model
inspectability, live/replay parity, evidence record, and delivery/developer
surface. It does not mean best overall product. Industry-direction statements
are inferences from the current public offer set plus the cited volume history;
this review did not measure vendor adoption or feature changes over time.

[Nightglass's public terms](https://nightglass.trade/terms) restrict competitive
reuse and reverse engineering. This review uses public category facts only. Do
not copy its interface, content, alert outputs, thresholds, or proprietary
scoring logic.

## Current Industry Signals

| Observable change | Current evidence | Product consequence |
| --- | --- | --- |
| Options participation is still expanding | [OCC's July report](https://www.theocc.com/newsroom/views/2026/08-04-july-2026-monthly-volume-report) shows 2026 year-to-date U.S. options average daily volume of 70.82 million contracts, 23.9% above the comparable 2025 period. | More raw data increases the value of filtering, context, and trustworthy state management. |
| Same-day options dominate SPX activity | [Cboe reported](https://www.cboe.com/insights/posts/market-metrics-that-matter-derivatives-july-2026-volume-highlights) that 0DTE contracts reached 66.2% of SPX volume in July 2026. | Overnight OI alone is least informative exactly where many intraday products make their strongest claims. Intraday quantity semantics must stay explicit. |
| Native futures-options activity is material and around the clock | [CME reports](https://www.cmegroup.com/articles/2025/equity-index-options-state-of-play.html) equity-index options-on-futures ADV grew from more than 700,000 in 2020 to 1.4 million in 2025; ES reached 1.3 million and NQ 87,000. | A native ES/NQ path is a real market, not just a translation of SPX/NDX levels. Globex sessions also make an RTH-only product incomplete for some users. |
| The popular causal story is contested | A [Cboe study](https://www.cboe.com/insights/posts/0-dt-es-decoded-positioning-trends-and-market-impact) estimated balanced customer activity left net SPX 0DTE market-maker gamma hedging at no more than about 0.2% of daily SPX liquidity in its study. | GEX should be presented as a model-dependent structural proxy and competing hypothesis, not an observed cause of every move. |
| Public products package data into decisions | Nightglass, SpotGamma, MenthorQ, and TradingFlow organize data around preparation, filtering, interpretation, delivery, and review. | A product needs a coherent daily job, not a collection of metrics and commands. |
| Trust is a visible product surface | Nightglass exposes a public alert record; replay and historical views are common; several vendors publish formulas or methodology pages. | Reproducibility, complete populations, preregistered definitions, and null results can differentiate more than marketing screenshots. |
| Delivery reaches the user's existing workflow | MenthorQ and GEXBot advertise multiple chart integrations; Quant Data, Unusual Whales, FlashAlpha, and Optionomics advertise API or MCP access. | A terminal-only surface is insufficient long term. Stable local interfaces should precede integrations. |
| Offers span wide price and service bands | Free/open and $39–$75 products coexist with roughly $99–$349 trader offers and substantially more expensive API, history, or enterprise access. | Price alone is weak positioning. Data rights, time saved, support, and evidence quality determine total value. |

## Current Product Truth

### Assets already in the repository

- Contract-aware Black-76 for futures options and Black-Scholes for
  equity/index options, with expiry, multiplier, IV, position-source,
  event-time, and pricing-model provenance.
- Open-interest, raw-volume, and aggressor-directionalized volume models kept
  separate, with coverage and disagreement reporting.
- Deterministic replay, captured sessions, journals, experiment manifests,
  model profiles, append-only corpus registration, and batch comparison.
- A normalized provider boundary spanning replay, delayed data,
  provider-shaped fixtures, and implemented or scaffolded live paths.
- Versioned certification policies, lifecycle and fault tests, redaction, safe
  capture policy, and explicit readiness/evidence vocabularies.
- Local exports, TradingView level files, a Textual interface, and an MIT
  contributor surface.

### Commercial gaps

- Databento remains `live-uncertified`; no provider has a supported recurring
  production envelope for credentialed ES/NQ.
- `predictive_validity=unmeasured`; there is no governed real-session corpus or
  out-of-sample evidence of trading value.
- The personas are hypotheses derived from product reasoning, not validated
  customer segments with observed activation, retention, or willingness to pay.
- Installation still assumes a Python environment. There is no signed desktop
  build, updater, migration/rollback contract, or guided provider setup.
- The CLI is broad and flat. There is no supported read-only Python API, local
  service, WebSocket, REST, or MCP contract.
- Alerts and overlays are local artifacts, not a reliable background delivery
  loop or chart bridge.
- There is no commercial data agreement, billing, support policy, incident
  process, privacy posture, or measured unit economics.

The code is a credible research kernel. The missing work is product validation,
live operational proof, packaging, daily workflow, and commercial authority—not
another formula.

## Market Map

The public market now clusters into six overlapping product types:

1. **Interpretation and research desks:** Nightglass, SpotGamma, and
   TradingFlow reduce a large tape or model surface to a daily research path.
2. **Futures-facing GEX products:** GammaTape and MenthorQ deliver index or
   futures gamma context into ES/NQ trader workflows.
3. **Model-rich exposure terminals:** GEXBot, OptionsDepth, Volland, GammaEdge,
   and SqueezeMetrics compete on position inference, Greeks, history, or
   specialized displays.
4. **Broad retail intelligence platforms:** Unusual Whales, Quant Data,
   Tradytics, and Optionomics bundle flow, dark pools, alerts, AI, mobile, and
   exposure analytics.
5. **Developer data and analytics:** FlashAlpha, Quant Data API, Unusual Whales
   API, and raw providers such as Databento make buying an interface easier
   than building one for many users.
6. **Open and budget tools:** GammaGrid, gex-dashboard, futures-options
   dashboards, Barchart, and small scripts commoditize the baseline calculation
   and increasingly offer history or replay.

## Nightglass Deep Dive

Nightglass matters less for feature parity than for showing how a market-data
tool becomes a product.

| Dimension | Publicly documented fact | Lesson for `gex-terminal` |
| --- | --- | --- |
| Customer job | It targets active traders who want useful options-flow research without manually interpreting the entire tape. | Sell a reduction in a recurring job, not access to a calculation. |
| Workflow | [The platform](https://nightglass.trade/product/) connects filtered alerts, ticker analysis, market and catalyst context, and post-close review. | Organize `gex-terminal` around Today, Explain, Compare, Replay, and Review rather than exposing the CLI taxonomy to users. |
| Interpretation | [Its method](https://nightglass.trade/methodology/) considers relative size, volume versus OI, execution urgency, repetition, related structures, and the event window; it permits an unresolved read. | Make abstention and model disagreement first-class. A data point does not have to become a signal. |
| GEX role | SPX dealer gamma is supporting context; price structure and invalidation remain central to the trade plan. | Do not present a wall as a guaranteed destination or cause. Show what would disconfirm the structural read. |
| Proof | Its first public audit covers 443 alerts over 15 sessions and reports favorable excursion statistics. The site separately states that peak moves are not subscriber returns. | A visible record builds trust, but a short vendor-authored best-move study is not execution evidence. Fixed horizons, costs, chronology, full populations, and reproducible artifacts would be stronger. |
| Pricing | One membership is listed at $149 monthly or $1,500 annually. | Buyers may pay for curation and saved attention, but price does not establish customer count, retention, or fit for this app. |
| Unknowns | Public pages reviewed did not establish its provider, measured latency, SLA, API, raw export contract, chart bridge, or native futures-options coverage. | `gex-terminal` should make those operational and provenance facts explicit rather than merely asserting quality. |

Nightglass's best lesson is the complete loop: select what matters, explain why,
connect it to a decision, and preserve the record. Its weakest transferable
lesson would be copying an interpretation product before `gex-terminal` has
live inputs and empirical evidence.

## Competitive Pressure

Prices are closest relevant public list prices on the review date, not
equivalent bundles. Promotions, billing cadence, exchange fees, professional
status, and commercial rights can change total cost.

| Product | Public offer most relevant here | Where it is ahead | Opening for `gex-terminal` |
| --- | --- | --- | --- |
| [GammaTape](https://gammatape.com/) | Free archive; Pro $99/month; Max $249/month | Focused SPX/NDX-to-ES/NQ workflow, near-real-time levels, 30/90-day replay, and MotiveWave delivery | Native options-on-futures rather than cash-index mapping; provider/model provenance; model-dissent and evidence receipts |
| [FlashAlpha](https://flashalpha.com/pricing) | Growth $299/month; Alpha $1,499/month | Native CME options-on-futures, Black-76, ES/NQ and wider coverage, SDKs/MCP, history, higher Greeks, and quality monitoring | Open and replaceable engine, bring-your-own provider, local privacy, identical-input comparison, and independently reproducible claims |
| [GEXBot](https://www.gexbot.com/docs) | Public price was not reliably exposed in this review | Intraday state model, replay, high visual tunability, higher Greeks, alerts, APIs, and many chart integrations | Native futures-options chain, Globex coverage, open method implementation, and explicit evidence ceilings |
| [SpotGamma](https://spotgamma.com/subscribe-to-spotgamma/) | Essential $99/month; Alpha $299/month | Category trust, research/commentary, polished SPX/0DTE workflow, proprietary flow lenses, education, and community | Local ownership, direct futures contracts, replaceable assumptions, provenance, and reproducible model comparison |
| [MenthorQ](https://menthorq.com/pricing/) | Premium $129/month; Pro $349/month after introductory offers | Broad coverage, education, AI, and the deepest advertised chart-platform integration set | Inspectable calculations and data lineage; public materials reviewed leave native futures-gamma cadence and real-time recomputation unclear |
| [OptionsDepth](https://optionsdepth.com/pricing) | Pro $199/month; Pro Max $249/month | Participant-tagged Cboe positioning, intraday SPX/VIX views, higher-Greek maps, and trader workspace | Native CME inputs, open models, local replay, lower dependency on one participant dataset |
| [Nightglass](https://nightglass.trade/) | $149/month or $1,500/year | Interpretation-first daily workflow, complex-trade reconstruction, education, and public record | Futures-native model laboratory, formula/data provenance, governed replay, and stronger experimental discipline |
| [Unusual Whales](https://unusualwhales.com/pricing) | Retail $50/$75/$120 monthly; API from $150/month | Breadth, tape, alerts, mobile, community, dark pools, API/MCP, and enterprise data surfaces | Narrower ES/NQ job, local control, replaceable models, and less opaque evidence boundaries |
| [Quant Data](https://quantdata.us/api) | Dashboard $74.99/month; API $149.99/month | Accessible dashboard/API, broad U.S. options analytics, MCP, history, and published service claims | Native futures-options research, open calculation, provider comparison, and governed experiment artifacts |
| [Optionomics](https://optionomics.ai/pricing) | $39–$99/month | Low-priced history, flow, AI, public track record, backtesting, REST, MCP, alerts, and mobile distribution | Futures-native depth, local privacy, model provenance, and defensible evidence rather than breadth |
| [TradingFlow](https://tradingflow.com/pricing/) | $59/month, billed quarterly | Strong filtered-flow workflow, live tape, saved views, exports, and evidence-aware methodology language | Direct CME focus, open engine, same-session model comparison, and research governance |
| [GammaGrid](https://github.com/gammagrid/gammagrid) and open peers | Free/open source | Self-hosting, transparent code, visual dashboards, stored snapshots, Greeks, and replay | Certified live futures inputs, provider normalization, stronger temporal contracts, and explicit proof ceilings |

### Closest benchmarks by job

| Job | Benchmark | What must be learned rather than copied |
| --- | --- | --- |
| Daily interpretation and trust | Nightglass | A coherent decision loop and visible record |
| Focused ES/NQ trader UX | GammaTape | Put levels where the trader already works; replay is a primary surface |
| Native futures developer surface | FlashAlpha | Correct asset-class treatment, quality monitoring, and low-friction interfaces |
| Chart distribution | MenthorQ and GEXBot | Integrations can be more valuable than another proprietary chart |
| Polished SPX research | SpotGamma | Category education, habit, and trusted explanation |
| Broad retail platform | Unusual Whales | Breadth, mobile, and community are a different strategy with different costs |
| Open/local baseline | GammaGrid | Open, free, local, and replayable are adoption attributes, not a full moat |

## Strategic White Space

This public scan does not prove that no private or undocumented product covers
the following areas. It does show a coherent combination that is not common in
the reviewed positioning.

| White-space capability | Why it matters | Current foundation |
| --- | --- | --- |
| Native ES/NQ contract truth | Avoids silently translating cash-index assumptions, multipliers, expiries, basis, and sessions into futures claims | Black-76, per-contract multipliers, normalized futures contracts, separate ES/NQ policies |
| Visible model dissent | OI, raw volume, and aggressor-directionalized volume answer different questions and should not be blended into one confident line | Three separate models and comparison reports |
| Provenance on every result | Lets a user distinguish measured input, inferred quantity, configured fallback, and derived proxy | Snapshot, adapter, IV, quality, and model metadata |
| Live/replay parity | Lets a user inspect the exact state that produced a live conclusion and reproduce it later | Event-time replay, captures, manifests, and corpus identity |
| Evidence receipts | Creates a complete, chronological record of what the model said and what later happened without converting best excursion into a forecast claim | Journals, price-action evaluation, split contracts, and evidence ceilings |
| Local/private operation | Fits professionals who cannot send credentials, research inputs, or proprietary experiments to a new hosted vendor | Local application and bring-your-own credentials |
| Open adapter and model contracts | Allows users to replace a provider or model without abandoning the research record | Separated adapters, consumer, engine, and report modules |
| A guided operator loop | Converts strong infrastructure into a usable product | Existing TUI, labs, replay browser, exports, and health state need reorganization |

The potential moat is a trustworthy history of model/provider behavior across
real market regimes. Every retained session makes the comparison system more
useful only if rights, point-in-time identity, and evaluation definitions remain
governed.

## Strategic Implication

The evidence supports a narrow professional ES/NQ research instrument rather
than a broad flow-and-news platform. [Product Vision](product-vision.md) owns
the selected user, experience, trust contract, and possible product form.
[ROADMAP.md](../ROADMAP.md) owns the bring-your-own-data hypothesis, the hosted
tactical-cockpit alternative, and the evidence required to choose between them.

## Decisions From This Review

1. Do not compete on a gamma heatmap, low price, or “for ES/NQ” language.
2. Turn provenance, model disagreement, data quality, replay, and evidence
   receipts into visible user workflows rather than backstage machinery.
3. Validate the research-instrument job and hosted-trader alternative before
   expanding the feature surface.
4. Prefer native CME inputs while treating SPX/NDX-derived context as a separate
   model, not an interchangeable substitute.
5. Stabilize local research interfaces before REST, MCP, or numerous chart
   integrations.
6. Use bring-your-own data for the first commercial experiment unless a written
   agreement authorizes another model.
7. Keep higher Greeks, broad equity flow, dark pools, automated trade calls,
   social/community, and execution outside the initial wedge.
8. Publish negative and unresolved results. The trust system is more valuable
   when it can say that the evidence did not support a claim.

[ROADMAP.md](../ROADMAP.md) owns delivery sequence, dependencies, and exit
criteria. [Product Vision](product-vision.md) owns the durable product shape.

## Primary Sources

### Market structure and data

- OCC: [July 2026 volume](https://www.theocc.com/newsroom/views/2026/08-04-july-2026-monthly-volume-report).
- Cboe: [July 2026 derivatives volume](https://www.cboe.com/insights/posts/market-metrics-that-matter-derivatives-july-2026-volume-highlights),
  [0DTE market-impact study](https://www.cboe.com/insights/posts/0-dt-es-decoded-positioning-trends-and-market-impact),
  and [0DTE resources](https://www.cboe.com/tradable-products/0dte/).
- CME Group: [equity-index options state of play](https://www.cmegroup.com/articles/2025/equity-index-options-state-of-play.html),
  [Q1 2026 recap](https://www.cmegroup.com/newsletters/quarterly-equity-index-recap/2026-april-equity-index-recap.html),
  and [options-on-futures resources](https://www.cmegroup.com/markets/options.html).
- Databento: [options-on-futures introduction](https://databento.com/docs/examples/options/options-on-futures-introduction),
  [options data](https://databento.com/options), and
  [pricing](https://databento.com/pricing).

### Products and methods

- Nightglass: [product](https://nightglass.trade/product/),
  [methodology](https://nightglass.trade/methodology/),
  [performance](https://nightglass.trade/performance/),
  [public alert record](https://nightglass.trade/alerts), and
  [terms](https://nightglass.trade/terms).
- GammaTape: [product and pricing](https://gammatape.com/) and
  [method](https://gammatape.com/docs).
- FlashAlpha: [pricing](https://flashalpha.com/pricing),
  [futures method](https://flashalpha.com/methodology/futures), and
  [API](https://flashalpha.com/api).
- GEXBot: [documentation](https://www.gexbot.com/docs),
  [metrics](https://www.gexbot.com/metrics),
  [integrations](https://www.gexbot.com/integrations/), and
  [API](https://www.gexbot.com/apidocs).
- SpotGamma: [plans](https://spotgamma.com/subscribe-to-spotgamma/),
  [GEX method](https://spotgamma.com/gamma-exposure-gex/), and
  [ES workflow](https://support.spotgamma.com/hc/en-us/articles/50270825725203-How-do-I-use-SpotGamma-if-I-trade-ES-E-mini-S-P-500-futures).
- MenthorQ: [pricing](https://menthorq.com/pricing/),
  [coverage](https://menthorq.com/guide/menthorq-asset-coverage/), and
  [integrations](https://menthorq.com/integrations/).
- OptionsDepth: [pricing](https://optionsdepth.com/pricing) and
  [FAQ](https://www.optionsdepth.com/faq).
- Unusual Whales: [retail pricing](https://unusualwhales.com/pricing),
  [API/MCP](https://unusualwhales.com/public-api), and
  [live-feed limitations](https://docs.unusualwhales.com/features/flow-status-indicator-live-options-feed/).
- Quant Data: [dashboard](https://quantdata.us/) and
  [API](https://quantdata.us/api).
- Other workflow benchmarks: [Optionomics](https://optionomics.ai/pricing),
  [TradingFlow](https://tradingflow.com/pricing/),
  [GammaEdge](https://www.gammaedge.com/), and
  [SqueezeMetrics](https://squeezemetrics.com/monitor/plans).

### Open and self-hosted comparators

- [GammaGrid](https://github.com/gammagrid/gammagrid)
- [gex-dashboard](https://github.com/Darthreign/gex-dashboard)
- [Futures Options S/D Dashboard](https://github.com/Hewkaw02/Futures-Options-SD-Dashboard)
- [0DTE Dealer Gamma](https://github.com/puneet-chandna/0DTE-dealer-gamma)
