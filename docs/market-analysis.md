# Competitive Landscape and Product Strategy

Reviewed October 18, 2026 against the current `0.6.0` source and first-party
vendor materials. This replaces the September 3 / `0.4.0` capability snapshot;
earlier assessments remain in Git. [Application Review](application-review.md)
owns current capabilities and historical verification limits;
[Roadmap](../ROADMAP.md) owns sequencing, authorization and exit gates.
Pricing, coverage, rights and product features change: recheck linked sources
before a purchase or commercial decision.

## Assessment

The project has a substantial offline research foundation. Its best product
hypothesis is a bring-your-own-data futures workbench that lets a researcher
inspect what produced a structural read, test the assumptions that change it,
and reproduce the explanation later. That combination still needs observed
repeat use and willingness-to-pay evidence.

Native futures coverage, Black-76, GEX charts, scenarios, higher Greeks, replay,
APIs, MCP and reproducible packs individually already have substitutes. The
commercial test is whether contract semantics, visible data limitations,
controlled model disagreement, local inputs and preserved calculation identity
make a recurring investigation materially easier. This is a product hypothesis,
not a uniqueness, adoption or trading-performance claim.

## Method and Evidence Boundary

The October review combined current source and canonical project documents,
recent merged repair packets, and official vendor product, pricing, method and
source pages. It did not include paid trials, independently measured vendor
latency or uptime, customer interviews, retention, subscriber verification,
contract advice or trading-performance measurement. Vendor claims remain
vendor claims. An undocumented public detail is unknown, not assumed absent.

The supporting full assessment is a derived local report; it does not replace
source authorities or promote readiness. Historical engineering results are
retained in [Application Review](application-review.md). Current strategy must
not interpret those results as user acceptance, live-provider certification or
predictive validity.

## Current Product Truth

| Foundation available | Material boundary |
| --- | --- |
| Contract-aware Black-76/Black-Scholes, effective multipliers and explicit pricing/IV/time provenance | Exercise style, exact expiry/session calendars and declared approximations need a supported-domain policy |
| Separate OI, raw-trade-volume and aggressor-directionalized models, with contribution and disagreement reports | They are distinct proxies; dealer/customer and opening/closing states remain unobserved |
| Captures, deterministic replay, journals, experiments, corpus registration, model profiles and portable receipts | Authorized input, point-in-time eligibility and the retained executable environment are separate obligations |
| Browser Wind Tunnel, scenarios, expiry removal, comparison, sampled fragility and saved receipts; explicit immutable Terminal checkpoint handoff | Default launch uses bundled replays; explicit checkpoint launch accepts frozen demo/replay state, not a general importer, live capture or continuous synchronization |
| Reviewed wheel setup, reusable offline starter, managed combined launch, diagnostics and backup/recovery | Python remains required; signed native distribution and generalized licensed-capture migration are not established |
| Exports, static TradingView overlay and a capability-protected Wind loopback HTTP service | The internal service is not a supported public SDK/REST/MCP contract; continuous chart synchronization is not shipped |
| Databento provider normalization and offline multiplier/product/OI repairs; Tradovate ACK-frame repair | Databento remains `live-uncertified`; Tradovate/IBKR remain `scaffold`; fixtures cannot certify actual access or payload coverage |

The checkpoint implementation connects existing capabilities: `w` freezes
demo/replay Terminal state, while `--wind-tunnel-checkpoint PATH` and
`wind-tunnel --checkpoint PATH` provide explicit local CLI transfer. The
`terminal_selected` model preserves Terminal's per-contract trade-first/OI
fallback selection. Self-contained receipts preserve the detached input and
assumption identity for reproduction without the original file/server.
[Wind Tunnel](wind-tunnel.md) owns the user/receipt contract and
[GEX-WIND-HANDOFF-001](work-packets/GEX-WIND-HANDOFF-001.md) owns integration
evidence. This connection does not establish observed user value or authorize
live capture; general historical intake and recurring investigation remain
separate product questions.

A substantive remaining gap is option-chain quality. The current Databento path
uses option trades to derive IV without subscribing to option bid/ask quotes.
Continuing underlying updates can keep stream health fresh while particular
option IVs remain older or use fallbacks. A usable chain-health surface must
separate per-option model-input quality from connection/stream freshness.
Provider quote initialization and its IV policy need separately routed work.

No recorded participant activation, tested price, commercial data agreement or
supported recurring live operating envelope is established by this review.
`predictive_validity` remains `unmeasured`.

## Current Market Benchmarks

These are different bundles and jobs. Prices below are the regular public
monthly offers observed on the review date, not comparable total costs;
professional status, exchange fees, rights and usage limits can change them.

| Product or substitute | Officially documented overlap | Consequence for this project |
| --- | --- | --- |
| [MenthorQ](https://menthorq.com/pricing/) | Premium $129/month after introductory pricing; Pro $349. Its [gamma guide](https://menthorq.com/academy/gamma-levels/lessons/understanding-gamma-levels/) describes native options-on-futures analytics. Integrations and education are prominent. | Native ES/NQ availability alone is insufficient differentiation. Test inspectability and the research workflow rather than assuming a coverage gap. |
| [FlashAlpha](https://flashalpha.com/pricing) | Growth $299/month, Alpha $1,499; [native ES/NQ/API coverage](https://flashalpha.com/for-ai-agents). Its [official futures integration notes](https://github.com/FlashAlpha-lab/flashalpha-mcp#futures-cme) describe futures historical replay as forthcoming. | Direct developer competition; an API, MCP surface or Black-76 calculation alone is a weak commercial boundary. |
| [GammaTape](https://gammatape.com/methodology) | Starter $24, Pro $49, Max $99/month; 30/90-day replay. Inputs are SPX/SPY and NDX/QQQ same-day chains, translated to futures context using basis or ratios. | Strong low-price competition for delivered levels. Preserve the distinction between mapped cash/ETF context and native CME option contracts. |
| [GEXBot](https://docs.gexbot.com/) | Positioning/flow models, higher Greeks, history, APIs, research tools and chart integrations. Its [URL guide](https://docs.gexbot.com/tools/urls/) includes synthetic index-to-future combinations. | OI/flow separation, history and higher Greeks already have commercial substitutes. Native CME chain support was not established by the reviewed documentation. |
| [SpotGamma](https://spotgamma.com/subscribe-to-spotgamma/) | Research, proprietary positioning/flow views, IV and calculator workflows. The reviewed public pricing page contains inconsistent tier/price text, so no single clean price is asserted here. | Polished interpretation and daily habit are substantial competition. A technically richer model needs a coherent recurring user job. |
| [OptionsDepth](https://www.optionsdepth.com/faq) | Intraday positioning/history and API access; the FAQ describes minute snapshots and a 30-day intraday lookback, with separate API fees/limits. | A scenario surface or history alone is insufficient; input semantics, reproducibility and the workflow matter. |
| [CME QuikStrike](https://www.cmegroup.com/tools-information/quikstrike.html) | Options pricing, Greeks, volatility, OI/volume and strategy tools, with free introductory analytics. | Standard calculations and basic scenario work already have an established exchange-backed substitute. |
| [IBKR Risk Navigator](https://www.interactivebrokers.com/en/trading/risk-navigator.php) | Actual/hypothetical portfolio risk and price/volatility/time scenarios. IBKR separately offers [CME equity-index options](https://www.interactivebrokers.com/en/trading/cme-equity-index-options-on-futures.php). | Broad portfolio risk is a different competitive choice. Specific ES/NQ workflow behavior was not independently tested. |
| [Databento](https://databento.com/pricing/) | CME Standard $199/month for personal use; raw market data and historical usage-based access. Its [official Greeks tutorial](https://databento.com/blog/option-greeks) already demonstrates historical/live Black-76 analytics and a dashboard. | A shared historical/live calculation pipeline alone is not distinctive. Personal data access does not authorize redistribution. |
| [QuantLib](https://github.com/lballabio/QuantLib/blob/master/ql/pricingengines/blackcalculator.hpp), [OpenBB](https://docs.openbb.co/odp/python/reference/cboe/options/chains), [Strata](https://strata.opengamma.io/product_coverage/) | Independent Black-model math, options-data tooling and scenario infrastructure respectively. Reviewed OpenBB/Strata pages do not establish a turnkey native ES/NQ chain workflow. | Reuse independent checks and interoperable inputs where useful; an open math kernel alone is a weak moat. |
| [ThetaData](https://www.thetadata.net/faq) | The FAQ says CME futures are not currently supplied; the [roadmap](https://www.thetadata.net/roadmap) places futures/options on the horizon. | Announced coverage is not an available ES/NQ dependency. |

### Replay and receipt distinctions

GammaTape states that archived sessions were recomputed after a September 27
rule change. Its replay is documented as prior-only within a minute, but the
method can be restated across history. That creates a useful product question:
does a user need the calculation as originally produced, an intentional
restatement under the current model, or both? Keep those identities separate;
do not equate restatement with future-data leakage.

FlashAlpha's [October 17 changelog](https://flashalpha.com/docs/changelog)
announces versioned, hash-verified research packs, initially a SPY/QQQ income
pilot. It also documents expiry-impact/strike-dependency analytics. A blanket
claim that only this project supplies reproducible packs or expiry
concentration is therefore unsupported. Futures scope, exact model identity,
authorized input portability and a usable local workflow are more precise
comparison questions.

## Strategic Opening

The strongest opening remains a completed futures research loop:

1. Bring one authorized source into a declared cutoff and contract scope.
2. See missing, stale, fallback and excluded inputs before interpreting a level.
3. Compare separate quantity models on identical inputs and inspect dissent.
4. Carry the exact checkpoint into a controlled scenario.
5. Explain the model-output change and preserve input/build identity.
6. Reproduce and revisit the result, retaining null and failed-data cases.

Scenario effects explain a model output under assumptions. They do not identify
what caused a market move or establish a profitable trade. A governed real
session corpus may strengthen this workflow over time, but that prospective
asset is not an existing moat or a substitute for customer evidence.

Historical research and a live tactical cockpit have different prerequisites.
A rights-authorized historical workbench can test repeat use and payment before
recurring live certification. A live offer additionally needs entitlement,
chain-quality, timing, recurrence, recovery and support evidence. Neither path
is selected solely by this competitive review.

## Recommendations Routed To The Roadmap

The checkpoint handoff is implemented in its bounded demo/replay scope, with
integration status recorded in its packet. The remaining recommendations are
hypotheses with explicit dependencies, not a feature bundle or delivery
commitment:

- Follow the handoff with one supported user-owned capture/historical input
  only when its recurring investigation and rights path are clear.
- Prioritize chain-health/IV initialization, matched-result explanation,
  preserved-build reproduction and explicit contract/session conventions.
- Assemble the existing research tools into a daily review workflow before
  creating a new backtester or storage system.
- Consider skew/term-structure stresses only after IV inputs and surface policy
  support them. Current uniform shifts are useful sensitivity tests.
- Choose quality-aware alerts and one chart integration from observed demand;
  the static TradingView export already exists.
- Stabilize a small SDK/read-only domain interface for a named developer job;
  MCP can be a later client of that contract.
- Gate native-versus-proxy comparisons, selected higher Greeks and portfolio
  P&L on licensed inputs, conventions and an observed task.
- Defer broad provider/symbol coverage, generalized platform APIs, hosted/mobile
  breadth, automated trade calls and free-form AI advice. Artifact-grounded
  explanations need citations, abstention and testable evidence ceilings first.

Keep the MIT kernel useful. Any paid offer must earn its value through the
completed job, supported workflow and viable costs. Databento's personal data
cost and cheap mapped-level competitors make raw-price competition unattractive;
software pricing still requires actual offer tests, rights answers and observed
support effort.

## Historical Context

The September assessment also reviewed Nightglass, Unusual Whales, Quant Data,
Optionomics, TradingFlow and open dashboards. Those remain possible workflow
benchmarks, but their earlier prices and feature inventories were not refreshed
as part of this focused October comparison and are not current claims here.
Nightglass's [terms](https://nightglass.trade/terms) restrict competitive reuse;
public category lessons do not authorize copying interfaces, outputs or
proprietary scoring. Earlier market-volume observations likewise retain their
original observation periods in Git rather than being presented as October
measurements.

[Roadmap](../ROADMAP.md) owns work order and gates;
[Product Vision](product-vision.md) owns durable direction. This review does not
authorize provider connections, purchases, data redistribution, commercial
launch, readiness promotion or predictive claims.
