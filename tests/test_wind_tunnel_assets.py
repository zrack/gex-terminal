import asyncio
import hashlib
from importlib.resources import files
import json
import shutil
import subprocess
import unittest


class WindTunnelAssetTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("node"), "Node.js is needed for health and focused strike browser regressions")
    def test_browser_health_freshness_price_markers_and_display_only_strike_ranges(self):
        root = files("gex_terminal").joinpath("wind_tunnel_web")
        result = subprocess.run(
            [shutil.which("node"), "-e", BROWSER_HEALTH_RANGES_HARNESS, str(root)],
            text=True, capture_output=True, timeout=15, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("health freshness and focused strike browser regressions passed", result.stdout)

    @unittest.skipUnless(shutil.which("node"), "Node.js is needed for model comparison browser regressions")
    def test_browser_model_comparison_controls_grid_receipts_and_stale_responses(self):
        root = files("gex_terminal").joinpath("wind_tunnel_web")
        result = subprocess.run(
            [shutil.which("node"), "-e", BROWSER_MODELS_HARNESS, str(root)],
            text=True, capture_output=True, timeout=15, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("model comparison browser regressions passed", result.stdout)

    @unittest.skipUnless(shutil.which("node"), "Node.js is needed for pricing coverage browser regressions")
    def test_browser_pricing_coverage_and_unpriced_diagnostics(self):
        root = files("gex_terminal").joinpath("wind_tunnel_web")
        result = subprocess.run(
            [shutil.which("node"), "-e", BROWSER_COVERAGE_HARNESS, str(root)],
            text=True, capture_output=True, timeout=15, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("pricing coverage browser regressions passed", result.stdout)

    def test_offline_chart_and_icon_assets_match_pinned_release_inventory(self):
        root = files("gex_terminal").joinpath("wind_tunnel_web")
        inventory = json.loads(root.joinpath("vendor/manifest.json").read_text())
        self.assertEqual(inventory["schema"], "gex-terminal.vendor-assets.v1")
        for package in inventory["packages"]:
            for name, expected in package["files"].items():
                with self.subTest(asset=name):
                    self.assertEqual(hashlib.sha256(root.joinpath(name).read_bytes()).hexdigest(), expected)
        page = root.joinpath("index.html").read_text()
        self.assertIn('/static/vendor/plotly.min.js', page)
        self.assertNotRegex(page, r'(?:src|href)=["\']https?://')
        self.assertTrue(files("gex_terminal").joinpath("data/wind_tunnel/es_multi_expiry.jsonl").is_file())

    @unittest.skipUnless(shutil.which("node"), "Node.js is needed for the browser workflow harness")
    def test_terminal_handoff_browser_requests_and_portable_reopen(self):
        # Execute the shipped browser controller against a tiny DOM and local API double.
        # This checks data ownership across UI operations, without a browser dependency.
        from gex_terminal.consumer import StatefulGexConsumer
        from gex_terminal.engine import IntradayGexEngine
        from gex_terminal.wind_tunnel_checkpoint import build_terminal_checkpoint, validate_checkpoint

        async def captured_artifact():
            consumer = StatefulGexConsumer(IntradayGexEngine(50.0), data_mode="demo", risk_free_rate=.037)
            for message in (
                {"type": "underlying_tick", "symbol": "ES", "price": 6000.0, "timestamp": "2026-10-18T15:34:00Z"},
                {"type": "options_volume_tick", "strike": 6000.0, "option_type": "C", "volume": 20,
                 "iv": .2, "expiry": "2026-10-19", "timestamp": "2026-10-18T15:34:00Z"},
            ):
                self.assertTrue(await consumer.update_market_state(json.dumps(message)))
            consumer.set_expiry_filter("2026-10-19")
            return await build_terminal_checkpoint(consumer, fallback_dte=.75)

        artifact = asyncio.run(captured_artifact())
        transport = json.dumps(artifact, sort_keys=True, separators=(",", ":"), allow_nan=False)
        self.assertIn('"spot":6000.0', transport)  # JS would erase .0 in an ordinary nested object.
        root = files("gex_terminal").joinpath("wind_tunnel_web")
        result = subprocess.run(
            [shutil.which("node"), "-e", BROWSER_HANDOFF_HARNESS, str(root)],
            input=json.dumps({"artifact": transport}), text=True, capture_output=True, timeout=15, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("handoff browser workflow passed", result.stdout)
        returned = json.loads(result.stdout.splitlines()[-1])
        self.assertEqual(returned["artifact"], transport)
        self.assertEqual(validate_checkpoint(returned["artifact"]), artifact)
        # Validate the actual JSON.parse/stringify request body emitted by the shipped controller.
        from gex_terminal import wind_tunnel
        normalized = wind_tunnel.normalize_request(returned["request"])
        self.assertEqual(normalized["terminal_checkpoint"], transport)
        from gex_terminal.wind_tunnel_server import make_receipt, reproduce_receipt
        receipt = asyncio.run(make_receipt("Browser transport regression", "calculate", returned["request"]))
        self.assertEqual(receipt["request"]["terminal_checkpoint"], transport)
        self.assertEqual(asyncio.run(reproduce_receipt(receipt))["status"], "verified")


BROWSER_DOM_HARNESS = r"""
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const root = process.argv[1];
const realSetTimeout = global.setTimeout; global.setTimeout = (...args) => {const timer = realSetTimeout(...args); timer.unref(); return timer;};
class Element {
  constructor(tag = 'div') {this.tagName = tag.toUpperCase(); this.children = []; this.value = ''; this.textContent = ''; this.hidden = false; this.disabled = false; this.checked = false; this.listeners = {}; this.classes = new Set(); this.classList = {add: v => this.classes.add(v), remove: v => this.classes.delete(v), contains: v => this.classes.has(v), toggle: (v, yes) => yes ? this.classes.add(v) : this.classes.delete(v)};}
  get options() {return this.children.filter(item => item.tagName === 'OPTION');}
  append(...items) {this.children.push(...items);}
  replaceChildren(...items) {this.children = [...items];}
  addEventListener(name, action) {this.listeners[name] = action;}
  setAttribute(name, value) {this[name] = value;}
  checkValidity() {return this.value !== '' && Number.isFinite(Number(this.value));}
  showModal() {this.open = true;}
  close() {this.open = false;}
  focus() {}
  select() {}
}
const page = fs.readFileSync(root + '/index.html', 'utf8'), elements = new Map();
for (const match of page.matchAll(/<([a-z][a-z0-9]*)\b[^>]*\bid="([^"]+)"[^>]*>/g)) {
  const element = new Element(match[1]);
  element.value = match[0].match(/\bvalue="([^"]*)"/)?.[1] || '';
  elements.set('#' + match[2], element);
}
for (const match of page.matchAll(/<select\b[^>]*\bid="([^"]+)"[^>]*>([\s\S]*?)<\/select>/g)) {
  const select = elements.get('#' + match[1]);
  for (const optionMatch of match[2].matchAll(/<option\b([^>]*)>([^<]*)<\/option>/g)) {
    const option = new Element('option'); option.value = optionMatch[1].match(/value="([^"]*)"/)?.[1] || ''; option.textContent = optionMatch[2]; select.append(option);
    if (!select.value || optionMatch[1].includes('selected')) select.value = option.value;
  }
}
for (const id of ['comparison-table', 'search-table', 'model-values-table', 'model-strike-table', 'model-grid-table']) elements.set('#' + id + ' tbody', new Element('tbody'));
for (const [selector, id] of [['.metric-strip', null], ['.pricing-coverage', null], ['.search-controls', null]]) elements.set(selector, new Element('section'));
global.document = {querySelector: selector => {if (selector.includes('option[value=')) return null; assert(elements.has(selector), 'Missing browser element: ' + selector); return elements.get(selector);}, querySelectorAll: () => [], createElement: tag => new Element(tag), addEventListener() {}, body: new Element('body')};
global.window = {addEventListener() {}};
global.location = {origin: 'http://127.0.0.1:12345', hash: '#cap=local-test-capability', pathname: '/', search: ''};
global.history = {replaceState() {}}; global.sessionStorage = {setItem() {}, getItem() {return null;}, removeItem() {}};
"""


BROWSER_HANDOFF_HARNESS = BROWSER_DOM_HARNESS + r"""
const artifact = JSON.parse(fs.readFileSync(0, 'utf8')).artifact;
assert.equal(typeof artifact, 'string');
const artifactMetadata = JSON.parse(artifact), originalArtifact = artifact;
const defaults = {session: 'terminal-checkpoint', checkpoint: 0, model: 'terminal_selected', fallback_dte: .75, risk_free_rate: .037};
const bundledDefaults = {session: 'wind-tunnel-lab', checkpoint: null, model: 'raw_trade_volume', fallback_dte: .25, risk_free_rate: .045};
const terminal = {name: 'terminal-checkpoint', label: 'Frozen Terminal checkpoint', source_kind: 'terminal_checkpoint', symbol: 'ES', as_of: artifactMetadata.source.as_of, expiry_filter: artifactMetadata.source.expiry_filter, quality: artifactMetadata.source.quality, data_mode: 'DEMO', status: 'available', defaults, terminal_checkpoint: artifact};
const bundled = {name: 'wind-tunnel-lab', label: 'Synthetic lab', symbol: 'ES', status: 'available', first_as_of: '2026-09-01T14:00:00Z'};
let bundledOnly = false, saved, requests = [], reproduceBytes = null, verificationStatus = 'verified';
global.fetch = async (url, options) => {
  assert.equal(options.headers['X-GEX-Capability'], 'local-test-capability');
  const path = url.replace('/api/', ''), body = options.body ? JSON.parse(options.body) : null;
  requests.push({path, body});
  let result;
  if (path === 'catalog') result = {sessions: bundledOnly ? [bundled] : [terminal, bundled], defaults: bundledOnly ? bundledDefaults : defaults, bundled_defaults: bundledDefaults};
  else if (path.startsWith('checkpoints?')) {assert(!path.includes('terminal-checkpoint'), 'Portable checkpoint must not require a server file or registered source'); result = {checkpoints: [{index: 0, as_of: '2026-09-01T14:00:00Z'}, {index: 3, as_of: '2026-09-01T14:01:00Z'}]};}
  else if (path === 'calculate') {const value = {spot: 6000, summary: {total_net_gex: 1, gamma_wall_strike: 6000}, pricing_assumptions: {summary: 'Black-76: American exercise: approximation error unmeasured.', limitations: ['European-exercise formulas; early exercise is not modeled.'], rate_note: 'Risk-free rate 3.70% is configured, not observed market data.', time_note: 'ACT/365'}}; result = {request: body, baseline: value, scenario: value, result_sha256: 'b'.repeat(64)};}
  else if (path === 'surface') result = {request: body, axes: {}, points: [], result_sha256: 'c'.repeat(64)};
  else if (path === 'search') result = {request: body, outcome: 'no_break_found', cells: [], result_sha256: 'd'.repeat(64)};
  else if (path === 'receipts') {saved = body; result = {id: 'receipt-id'};}
  else if (path === 'reproduce') {reproduceBytes = options.body; result = {status: verificationStatus, result: {request: body.request}};}
  else throw new Error('Unexpected request ' + path);
  return {ok: true, status: 200, json: async () => result};
};
let app = fs.readFileSync(root + '/app.js', 'utf8');
assert(app.includes('  initialize();'));
app = app.replace('  initialize();', '  globalThis.browser = {initialize, loadSource, requestFromControls, calculate, renderPricingAssumptions, playReplay, runSearch, reopenRequest, saveReceipt, importReceipt, state};');
vm.runInThisContext(app, {filename: 'app.js'});
(async () => {
  await browser.initialize();
  assert.equal(browser.state.source, 'terminal-checkpoint', 'Captured source is preferred at launch');
  assert.match(elements.get('#pricing-model-context').textContent, /Black-76.*American.*unmeasured/);
  elements.get('#source-details').listeners.click();
  const renderedText = element => [element.textContent, ...element.children.map(renderedText)].join(' ');
  const details = renderedText(elements.get('#info-content'));
  assert.match(details, /early exercise is not modeled/);
  assert.match(details, /configured, not observed/);
  assert.match(details, /ACT\/365/);
  browser.renderPricingAssumptions({baseline: {pricing_assumptions: {summary: 'Black-76: exercise style unknown: model compatibility unqualified.'}}});
  assert.match(elements.get('#pricing-model-context').textContent, /unknown.*unqualified/);
  assert(!elements.get('#pricing-model-context').textContent.includes('American'), 'New source must not retain the old American qualification');
  browser.renderPricingAssumptions({});
  assert.match(elements.get('#pricing-model-context').textContent, /unavailable.*early exercise is not modeled/);
  browser.renderPricingAssumptions({scenario: {pricing_assumptions: {summary: 'American futures CRR: early exercise is modeled with a finite CRR lattice.', early_exercise_modeled: true,
    pricing_coverage: {priced_quantity: 12, selected_quantity: 13, unpriced_contract_count: 1}}}});
  assert.match(elements.get('#pricing-model-context').textContent, /American futures CRR.*early exercise is modeled/);
  assert(!elements.get('#pricing-model-context').textContent.includes('Early exercise is not modeled'));
  assert.match(elements.get('#pricing-model-context').textContent, /Priced 12 of 13.*1 contract/);
  let request = browser.requestFromControls();
  assert.equal(request.model, 'terminal_selected'); assert.equal(request.fallback_dte, .75); assert.equal(request.risk_free_rate, .037);
  assert.deepEqual(request.terminal_checkpoint, artifact); assert.equal(request.checkpoint, 0, elements.get('#connection-error').textContent);
  assert.equal(elements.get('#checkpoint').disabled, true); assert.equal(elements.get('#play-replay').disabled, true);
  assert.match(elements.get('#header-source').textContent, /Frozen Terminal checkpoint/);
  assert.match(elements.get('#source-context').textContent, /2026-10-19.*Mode: DEMO.*Health: simulated.*synthetic DEMO/);
  const count = requests.length; browser.playReplay(); assert.equal(requests.length, count); assert.equal(browser.state.playback, null);
  elements.get('#spot-number').value = '15'; await browser.calculate();
  assert.equal(browser.state.surface.request.spot_shift, 15); assert.deepEqual(browser.state.surface.request.terminal_checkpoint, artifact);
  elements.get('#reset-scenario').listeners.click();
  assert.equal(browser.requestFromControls().spot_shift, 0); assert.equal(browser.requestFromControls().model, 'terminal_selected');
  assert.equal(browser.requestFromControls().fallback_dte, .75); assert.deepEqual(browser.requestFromControls().terminal_checkpoint, artifact);
  await browser.runSearch();
  assert.deepEqual(browser.state.search.request.terminal_checkpoint, artifact);
  elements.get('#scenario-name').value = 'Frozen test'; await browser.saveReceipt({preventDefault() {}});
  assert.equal(saved.kind, 'search'); assert.deepEqual(saved.request.terminal_checkpoint, artifact);
  assert.equal(artifact, originalArtifact, 'Editing and saving must not mutate the artifact');
  elements.get('#comparison-model').value = 'terminal_selected';
  await browser.loadSource('wind-tunnel-lab');
  assert.equal(elements.get('#comparison-model').value, 'open_interest');
  assert.equal(browser.state.terminalCheckpoint, null); assert(!('terminal_checkpoint' in browser.requestFromControls()));
  assert.equal(browser.requestFromControls().model, 'raw_trade_volume'); assert.equal(browser.requestFromControls().fallback_dte, .25);
  assert.equal(elements.get('#play-replay').disabled, false); assert.match(elements.get('#evidence-limit').textContent, /^Synthetic inputs/);
  assert.equal(elements.get('#position-model').options.find(option => option.value === 'terminal_selected').disabled, true);
  await browser.loadSource('terminal-checkpoint');
  assert.deepEqual(browser.requestFromControls().terminal_checkpoint, artifact, 'Returning to captured source recovers its original artifact');
  bundledOnly = true; await browser.initialize();
  assert.equal(browser.state.source, 'wind-tunnel-lab');
  const importedRequest = {...defaults, terminal_checkpoint: artifact, spot_shift: 7, iv_shift: 1, time_advance: 4};
  const rawReceipt = '{\n  "kind": "calculate", "request": ' + JSON.stringify(importedRequest) + '\n}';
  const beforeOversizeImport = requests.length;
  await browser.importReceipt({target: {files: [{size: 32 * 1024 * 1024 + 1, text: async () => {throw new Error('Oversized receipt must not be read');}}], disabled: false, value: 'too-large.json'}});
  assert.match(elements.get('#import-status').textContent, /32 MiB/);
  assert.equal(requests.length, beforeOversizeImport, 'Oversized receipt must not reach the service');
  const importTarget = () => ({files: [{size: rawReceipt.length, text: async () => rawReceipt}], disabled: false, value: 'receipt.json'});
  verificationStatus = 'mismatch'; await browser.importReceipt({target: importTarget()});
  assert.equal(browser.state.source, 'wind-tunnel-lab', 'Unverified receipt must not replace the active source');
  assert.equal(browser.state.terminalCheckpoint, null);
  verificationStatus = 'verified';
  await browser.importReceipt({target: {files: [{size: 5 * 1024 * 1024, text: async () => rawReceipt}], disabled: false, value: 'receipt.json'}});
  assert.equal(reproduceBytes, rawReceipt, 'Receipt verification must retain exact original bytes');
  assert.equal(browser.state.source, 'terminal-checkpoint');
  assert.equal(browser.requestFromControls().spot_shift, 7); assert.equal(browser.requestFromControls().risk_free_rate, .037);
  assert.deepEqual(browser.requestFromControls().terminal_checkpoint, artifact, 'Imported receipt must remain self-contained after edits');
  elements.get('#scenario-name').value = 'Imported test'; await browser.saveReceipt({preventDefault() {}});
  assert.deepEqual(saved.request.terminal_checkpoint, artifact);
  assert.equal(saved.request.model, 'terminal_selected');
  const replayArtifact = JSON.parse(artifact); replayArtifact.source.synthetic = false; replayArtifact.source.data_mode = 'REPLAY';
  await browser.reopenRequest('calculate', {...importedRequest, terminal_checkpoint: JSON.stringify(replayArtifact)});
  assert.match(elements.get('#source-context').textContent, /REPLAY inputs/);
  assert(!elements.get('#source-context').textContent.includes('synthetic REPLAY'), 'Recorded source provenance must not be replaced by a synthetic claim');
  console.log('handoff browser workflow passed');
  console.log(JSON.stringify({artifact: saved.request.terminal_checkpoint, request: requests.filter(item => item.path === 'calculate').find(item => item.body.terminal_checkpoint === artifact).body}));
})().catch(error => {console.error(error); process.exitCode = 1;});
"""


BROWSER_COVERAGE_HARNESS = BROWSER_DOM_HARNESS + r"""
let app = fs.readFileSync(root + '/app.js', 'utf8');
app = app.replace('  initialize();', '  globalThis.browser = {renderPricingAssumptions, showSource, loadSource, calculate, state};');
vm.runInThisContext(app, {filename: 'app.js'});
const renderedText = element => [element.textContent, ...element.children.map(renderedText)].join(' ');
const coverageText = () => renderedText(elements.get('#pricing-coverage-content'));
const clone = value => JSON.parse(JSON.stringify(value));
const coverage = {status: 'partial', selected_contract_count: 195, priced_contract_count: 194,
  selected_quantity: 1692, priced_quantity: 1691, unpriced_contract_count: 1, unpriced_quantity: 1,
  retained_iv_contract_count: 0};
const excluded = {contract_id: 'sample-put', expiry: '2026-10-16', quantity: 1, reason: 'iv_unavailable',
  iv_provenance: {status: 'outside_no_arbitrage_bounds', option_price: 508, lower_bound: 529.6077024442,
    upper_bound: 30429, underlying_price: 29900.375, underlying_price_age_ms: 493.863121}};
const original = {pricing_coverage: coverage, excluded_contracts: [excluded]};
const report = {request: {fallback_dte: .25, risk_free_rate: .045}, baseline: original, scenario: clone(original)};
browser.state.terminalCheckpoint = JSON.stringify({rows: [{contract_id: 'sample-put', expiry: '2026-10-16', symbol: 'NQ', strike: 30430, option_type: 'P', iv: null}]});
browser.state.calculation = report;
const canonicalBefore = JSON.stringify(report), artifactBefore = browser.state.terminalCheckpoint;
browser.renderPricingAssumptions(report);
assert.match(coverageText(), /Original & scenario · Partial/);
assert.match(coverageText(), /194 \/ 195 contracts priced \(99.49%\)/);
assert.match(coverageText(), /1,691 \/ 1,692 selected quantity priced \(99.94%\)/);
assert.match(coverageText(), /Captured premium 508 points.*below.*529.61 points.*no valid IV/);
assert.match(coverageText(), /excluded from modeled GEX.*Raw quantities are retained/);
assert.match(elements.get('#pricing-model-context').textContent, /Pricing assumptions unavailable/);
browser.showSource();
const details = renderedText(elements.get('#info-content'));
assert.match(details, /NQ 30,430 put · Contract sample-put/);
assert.match(details, /expiry 2026-10-16/);
assert.match(details, /captured IV inversion inputs, not shifted scenario inputs/);
assert.match(details, /do not establish why.*disagree/);
assert.match(details, /Captured underlying age \(ms\).*493.863121/);
assert.equal(JSON.stringify(report), canonicalBefore, 'Rendering must preserve canonical calculation payloads');
assert.equal(browser.state.terminalCheckpoint, artifactBefore, 'Rendering must preserve checkpoint bytes and null IV');

// Ordinary v2 bundled results omit qualified-IV metadata, but include every priced row.
const bundled = {status: 'available', counts: {selected_rows: 10}, contracts: Array.from({length: 10}, (_, i) => ({contract_id: 'bundled-' + i, quantity: i + 1})), excluded_contracts: []};
const bundledReport = {baseline: bundled, scenario: clone(bundled)}, bundledBefore = JSON.stringify(bundledReport);
browser.renderPricingAssumptions(bundledReport);
assert.match(coverageText(), /Original & scenario · Complete/);
assert.match(coverageText(), /10 \/ 10 contracts priced \(100%\)/);
assert.match(coverageText(), /55 \/ 55 selected quantity priced \(100%\)/);
assert.equal(JSON.stringify(bundledReport), bundledBefore, 'Derived presentation coverage must not mutate bundled results');
for (const incomplete of [
  {...bundled, counts: {selected_rows: 11}},
  {...bundled, counts: {}},
  {...bundled, contracts: []},
  {...bundled, contracts: undefined},
  {...bundled, status: 'invalid_scenario'},
  {...bundled, status: 'no_data'},
  {...bundled, contracts: [...bundled.contracts.slice(1), {quantity: -1}]},
  {...bundled, contracts: [...bundled.contracts.slice(1), {quantity: NaN}]},
  {...bundled, contracts: [...bundled.contracts.slice(1), {quantity: Infinity}]},
  {...bundled, contracts: [...bundled.contracts.slice(1), {}]},
  {...bundled, excluded_contracts: [excluded]},
  {...bundled, contracts: bundled.contracts.map(row => ({...row, provider: 'legacy', iv_source: 'legacy_unspecified'}))},
]) {
  browser.renderPricingAssumptions({scenario: incomplete});
  assert.match(coverageText(), /Coverage unavailable/, 'Missing rows, invalid quantities or unavailable states cannot imply complete coverage');
  assert(!coverageText().includes('Complete'));
}

// Expiry removal changes only the scenario denominator. Keep both coverages visible.
const reduced = {pricing_coverage: {...coverage, status: 'complete', selected_contract_count: 194,
  selected_quantity: 1691, unpriced_contract_count: 0, unpriced_quantity: 0}, excluded_contracts: [{...excluded, reason: 'nearest_expiry_excluded'}]};
const branched = {...report, scenario: reduced};
browser.state.calculation = branched; browser.renderPricingAssumptions(branched);
assert.match(coverageText(), /Original · Partial/);
assert.match(coverageText(), /Scenario · Complete.*194 \/ 194 contracts priced \(100%\)/);
assert.match(coverageText(), /1,691 \/ 1,691 selected quantity priced \(100%\)/);
browser.showSource();
assert.equal((renderedText(elements.get('#info-content')).match(/Contract sample-put/g) || []).length, 1,
  'Expiry exclusion must not re-label the scenario contract as unavailable IV');

browser.renderPricingAssumptions({baseline: reduced, scenario: clone(reduced)});
assert.match(coverageText(), /Original & scenario · Complete/);
assert(!coverageText().includes('508'), 'Complete source must clear old unpriced explanation');
browser.renderPricingAssumptions({scenario: {pricing_coverage: {...coverage, priced_contract_count: 0, priced_quantity: 0,
  unpriced_contract_count: 195, unpriced_quantity: 1692}, excluded_contracts: [excluded]}});
assert.match(coverageText(), /Unavailable — no selected contracts are priced/);
assert.match(coverageText(), /0 \/ 195 contracts priced \(0%\)/);
browser.renderPricingAssumptions({scenario: {pricing_coverage: {...coverage, selected_contract_count: 0,
  priced_contract_count: 0, selected_quantity: 0, priced_quantity: 0, unpriced_contract_count: 0, unpriced_quantity: 0}}});
assert.match(coverageText(), /No selected contracts/);
assert.match(coverageText(), /0 \/ 0 contracts priced \(not applicable\)/);
assert(!coverageText().includes('100%'), 'Empty selection is not complete coverage');
browser.renderPricingAssumptions({scenario: {pricing_coverage: {...coverage, selected_contract_count: 100000,
  priced_contract_count: 99999, selected_quantity: 100000, priced_quantity: 99999}}});
assert.match(coverageText(), /Partial/);
assert.match(coverageText(), /priced \(<100%\)/, 'Rounding must not hide a very small omission');
assert(!coverageText().includes('(100%)'));

// Labels and diagnostics are text, including untrusted metadata, never parsed HTML.
const hostile = {...excluded, contract_id: '<img src=x onerror=alert(1)>', expiry: '<script>bad</script>'};
browser.state.terminalCheckpoint = null;
browser.state.calculation = {...report, baseline: {pricing_coverage: coverage, excluded_contracts: [hostile]}, scenario: undefined};
browser.renderPricingAssumptions(browser.state.calculation); browser.showSource();
assert.match(renderedText(elements.get('#info-content')), /<img src=x onerror=alert\(1\)>/);
const descendants = element => [element, ...element.children.flatMap(descendants)];
assert(!descendants(elements.get('#info-content')).some(element => ['IMG', 'SCRIPT'].includes(element.tagName)));
browser.renderPricingAssumptions({baseline: {}});
assert.match(coverageText(), /Coverage unavailable/);
assert(!coverageText().includes('508'));
browser.renderPricingAssumptions(null);
assert.match(coverageText(), /Pricing coverage pending/);
assert.match(elements.get('#pricing-model-context').textContent, /Pricing assumptions pending.*Recalculating/);
assert(!elements.get('#pricing-model-context').textContent.includes('early exercise is not modeled'), 'A pending calculation cannot imply European-only pricing');

// Exercise the actual source-change path while its local checkpoint request is pending.
global.fetch = () => new Promise(() => {});
browser.state.sources = [{name: 'next-source', symbol: 'ES'}];
browser.state.bundledDefaults = {model: 'raw_trade_volume', fallback_dte: .25, risk_free_rate: .045};
browser.state.calculation = report; browser.renderPricingAssumptions(report);
browser.loadSource('next-source');
assert.equal(browser.state.calculation, null);
assert.equal(browser.state.terminalCheckpoint, null);
assert.match(coverageText(), /Pricing coverage pending/);
assert(!coverageText().includes('508'), 'Loading a new source must clear prior coverage and diagnostic details');
browser.showSource();
assert(!renderedText(elements.get('#info-content')).includes('sample-put'));
browser.state.calculation = report; browser.renderPricingAssumptions(report);
browser.calculate();
assert.equal(browser.state.calculation, null, 'Direct replay and breaking-case recalculations must clear stale results');
assert.match(coverageText(), /Pricing coverage pending/);
assert(!coverageText().includes('508'));
console.log('pricing coverage browser regressions passed');
"""


BROWSER_MODELS_HARNESS = BROWSER_DOM_HARNESS + r"""
const renderedText = element => [element.textContent, ...element.children.map(renderedText)].join(' ');
const textAt = selector => renderedText(elements.get(selector));
const terminalArtifact = JSON.stringify({source: {symbol: 'ES', as_of: '2026-10-16T20:59:59Z', data_mode: 'REPLAY', synthetic: false}, parameters: {fallback_dte: .25, risk_free_rate: .045}, rows: [{contract_id: 'missing-es', expiry: '2026-10-19', strike: 7770, option_type: 'P', symbol: 'ES'}]});
const nqArtifact = JSON.stringify({source: {symbol: 'NQ', as_of: '2026-10-16T20:59:59Z', data_mode: 'REPLAY', synthetic: false}, parameters: {fallback_dte: .25, risk_free_rate: .045}, rows: []});
const defaults = {session: 'terminal-checkpoint', checkpoint: 0, model: 'terminal_selected', fallback_dte: .25, risk_free_rate: .045};
const terminal = {name: 'terminal-checkpoint', label: 'ES primary', source_kind: 'terminal_checkpoint', symbol: 'ES', as_of: '2026-10-16T20:59:59Z', status: 'available', defaults, terminal_checkpoint: terminalArtifact};
const bundled = {name: 'wind-tunnel-lab', symbol: 'ES', status: 'available'};
const coverage = {status: 'partial', selected_contract_count: 3, priced_contract_count: 2, selected_quantity: 15, priced_quantity: 14, unpriced_contract_count: 1, unpriced_quantity: 1};
const makeState = (value, model, available = true) => ({model, status: available ? 'available' : 'insufficient_directional_coverage', reason: available ? null : 'No observed aggressor side', spot: 7770, summary: available ? {total_net_gex: value, gamma_wall: 7770, net_sign: Math.sign(value)} : null, matrix: available ? {strikes: [7700, 7770], net_gex: [value / 2, value / 2], call_wall_strike: model === 'terminal_selected' ? 7770 : null, put_wall_strike: model === 'terminal_selected' ? 7700 : null} : null, counts: {source_rows: 1001}, directional_coverage: model === 'directionalized_trade_volume' ? .9 : undefined, pricing_coverage: coverage, excluded_contracts: [{contract_id: 'missing-es', expiry: '2026-10-19', quantity: 1, reason: 'iv_unavailable', iv_provenance: {status: 'outside_no_arbitrage_bounds', option_price: 1, lower_bound: 2}}], pricing_assumptions: {summary: 'Frozen pricing inputs', early_exercise_modeled: true}});
const makeReport = (request, unavailable = false) => ({request: {...request, model: request.terminal_checkpoint ? 'terminal_selected' : 'raw_trade_volume'}, result_sha256: 'b'.repeat(64), models: [{model: request.terminal_checkpoint ? 'terminal_selected' : 'raw_trade_volume', label: 'Call-positive put-negative proxy', baseline: makeState(-10, 'terminal_selected'), scenario: makeState(-20, 'terminal_selected')}, {model: 'directionalized_trade_volume', label: 'Signed aggressor proxy', baseline: makeState(5, 'directionalized_trade_volume'), scenario: makeState(0, 'directionalized_trade_volume', !unavailable)}], agreement: {scenario: {status: unavailable ? 'not_evaluable' : 'available', net_sign_matches: false, gamma_wall_matches: true}}, grid: request.grid ? {axes: {spot_shifts: [-25, 0, 25], iv_shifts: [-1, 0, 1], time_advances: [0, 30, 60]}, case_count: 54, summaries: [{model: 'terminal_selected', label: 'default', case_count: 27, evaluable_count: 27, not_evaluable_count: 0, net_sign_counts: {positive: 0, negative: 27, zero: 0}, net_gex_range: {min: -20, max: -10}, gamma_wall_strikes: [7770], net_sign_stable: true, gamma_wall_stable: true}, {model: 'directionalized_trade_volume', case_count: 27, evaluable_count: 26, not_evaluable_count: 1, net_sign_counts: {positive: 26, negative: 0, zero: 0}, net_gex_range: {min: 0, max: 5}, gamma_wall_strikes: [7770], net_sign_stable: null, gamma_wall_stable: null}], cases: [{model: 'terminal_selected', spot_shift: 0, iv_shift: 0, time_advance: 0, status: 'available', total_net_gex: 0, gamma_wall_strike: 7770, pricing_coverage: coverage}, {model: 'directionalized_trade_volume', spot_shift: -25, iv_shift: -1, time_advance: 0, status: 'insufficient_directional_coverage', total_net_gex: null, gamma_wall_strike: null, reason: 'Missing aggressor quantity'}]} : null});
const tabs = ['landscape', 'compare', 'fragility', 'models'].map(view => {const element = elements.get('#tab-' + view); element.dataset = {view}; return element;});
const presets = ['baseline', 'price-down', 'price-up', 'iv-down', 'iv-up', 'time-30', 'time-60'].map(modelPreset => {const element = new Element('button'); element.dataset = {modelPreset}; return element;});
document.querySelectorAll = selector => selector === '.tabs button' ? tabs : selector === '[data-model-preset]' ? presets : [];
const wireReport = (request, unavailable = false) => {const result = makeReport(request, unavailable); for (const model of result.models) {model.baseline.spot = request.terminal_checkpoint === nqArtifact ? 29392.5 : 7702.875; model.scenario.spot = model.baseline.spot + (request.spot_shift || 0);} if (request.detail_level === 'compact') {delete result.request.terminal_checkpoint; result.request.terminal_checkpoint_sha256 = 'e'.repeat(64);} return result;};
let requests = [], saved, deferModels = false, pending = [], unavailable = false, plots = [], deferCalculate = false, pendingCalculations = [];
global.Plotly = {react: async (target, traces, layout) => {target.data = traces; plots.push({target, traces, layout});}, purge: target => {target.data = null;}, Plots: {resize() {}}}; window.Plotly = global.Plotly;
global.fetch = async (url, options) => {assert(url.startsWith('/api/'), 'Offline controller must use only same-origin API'); const path = url.replace('/api/', ''), body = options.body ? JSON.parse(options.body) : null; requests.push({path, body, signal: options.signal}); let result;
  if (path === 'catalog') result = {sessions: [terminal, bundled], defaults, bundled_defaults: {...defaults, session: 'wind-tunnel-lab', model: 'raw_trade_volume'}, saved_checkpoints: [{artifact: terminalArtifact, label: 'Saved ES', symbol: 'ES', checkpoint_sha256: 'es'}, {artifact: nqArtifact, label: 'Saved NQ', symbol: 'NQ', checkpoint_sha256: 'nq'}]};
  else if (path.startsWith('checkpoints?')) result = {checkpoints: [{index: 0, as_of: '2026-10-16T20:58:00Z'}, {index: 1, as_of: '2026-10-16T20:59:59Z'}]};
  else if (path === 'calculate') {const calculation = {request: body, baseline: makeState(-10, body.model), scenario: makeState(-20, body.model), result_sha256: 'a'.repeat(64)}; if (deferCalculate) return new Promise(resolve => pendingCalculations.push(() => resolve({ok: true, status: 200, json: async () => calculation}))); result = calculation;}
  else if (path === 'models') {if (deferModels) return new Promise(resolve => pending.push({body, signal: options.signal, resolve: () => resolve({ok: true, status: 200, json: async () => wireReport(body)})})); result = wireReport(body, unavailable);}
  else if (path === 'receipts') {saved = body; result = {id: 'saved'};}
  else if (path === 'surface') result = {request: body, axes: {}, points: []};
  else throw new Error('Unexpected request ' + path);
  return {ok: true, status: 200, json: async () => result};
};
let app = fs.readFileSync(root + '/app.js', 'utf8'); app = app.replace('  initialize();', '  globalThis.browser = {initialize, loadSource, setView, requestFromControls, calculateModels, scheduleCalculation, applyModelPreset, renderModels, reopenRequest, saveReceipt, showSource, state};'); vm.runInThisContext(app, {filename: 'app.js'});
const flush = async () => {for (let i = 0; i < 15; i++) await Promise.resolve();};
(async () => {
  await browser.initialize(); assert.equal(browser.state.view, 'compare', 'Large source must keep its existing initial Compare view'); assert.equal(browser.state.sources.length, 3, 'Primary saved checkpoint is deduplicated');
  elements.get('#spot-number').value = '25'; elements.get('#iv-number').value = '1'; elements.get('#time-number').value = '30'; browser.setView('models'); await flush();
  assert.equal(browser.state.view, 'models'); assert(elements.get('.metric-strip').hidden); assert(elements.get('.pricing-coverage').hidden); assert(elements.get('.search-controls').hidden); assert(elements.get('#position-model').disabled);
  let request = requests.filter(item => item.path === 'models').at(-1).body; assert.deepEqual([request.spot_shift, request.iv_shift, request.time_advance, request.grid], [25, 1, 30, false]); assert.equal(request.terminal_checkpoint, terminalArtifact); assert.equal(elements.get('#spot-effective').textContent, 'Original price 7,702.875'); assert.equal(request.detail_level, 'compact'); assert.equal(browser.state.models.request.terminal_checkpoint, undefined); assert.equal(browser.state.modelsRequest.terminal_checkpoint, terminalArtifact); assert.equal(browser.state.modelsRequest.detail_level, 'full');
  assert.match(textAt('#model-cards'), /Default.*Directionalized/); assert.match(textAt('#model-cards'), /2 \/ 3 contracts priced/); assert.match(textAt('#model-cards'), /90% of priced volume/); assert.match(textAt('#model-cards'), /ES 7,770 put.*missing-es/); assert.match(textAt('#model-cards'), /no valid IV/);
  const rows = elements.get('#model-values-table tbody').children; assert.equal(rows.length, 4); assert.equal(rows[3].children[3].textContent, '0', 'A real zero must remain zero'); assert.equal(rows[3].children[5].textContent, 'Unavailable', 'Directional call wall is not a default wall or zero'); assert.equal(rows[1].children[5].textContent, '7,770', 'Default wall comes from its matrix');
  const modelPlots = plots.filter(item => [elements.get('#model-default-plot'), elements.get('#model-directional-plot')].includes(item.target)); assert.equal(modelPlots.length, 2); assert.deepEqual(modelPlots[0].layout.xaxis.range, modelPlots[1].layout.xaxis.range); assert.deepEqual(modelPlots[0].layout.yaxis.range, modelPlots[1].layout.yaxis.range);
  await browser.calculateModels(true); assert.equal(browser.state.models.request.grid, true); assert.equal(requests.filter(item => item.path === 'models').at(-1).body.time_advance, 30); assert.match(textAt('#model-grid-summary'), /54 calculated model cases/); assert.match(textAt('#model-grid-summary'), /stability is not established/); assert.match(textAt('#model-grid-table tbody'), /available.*0.*insufficient_directional_coverage.*Unavailable/);
  elements.get('#scenario-name').value = 'Both models'; await browser.saveReceipt({preventDefault() {}}); assert.equal(saved.kind, 'models'); assert.equal(saved.request.grid, true); assert.equal(saved.request.terminal_checkpoint, terminalArtifact);
  const reproduction = makeReport(saved.request); const beforeReopen = requests.length; await browser.reopenRequest('models', saved.request, reproduction); assert.equal(browser.state.view, 'models'); assert.equal(browser.state.models, reproduction); assert.equal(browser.state.models.request.grid, true, 'Reopening must preserve the saved exact grid request'); assert.equal(requests.length, beforeReopen, 'Verified model receipt reuses its full reproduced result without duplicate calculate or models requests'); assert.equal(elements.get('#calculation-status').textContent, 'Saved model comparison verified · local inputs only', 'Verified receipt reopening must leave a ready status instead of a loading message');
  const nullWall = makeReport(browser.state.models.request); nullWall.agreement.scenario = {status: 'available', net_sign_matches: true, gamma_wall_matches: null}; for (const model of nullWall.models) {model.scenario.summary.total_net_gex = 0; model.scenario.summary.gamma_wall = null;} browser.state.models = nullWall; browser.renderModels(); assert.match(textAt('#model-agreement'), /net sign agrees.*dominant gamma wall is not evaluable/); assert(!textAt('#model-agreement').includes('wall differs'), 'Null walls cannot establish model disagreement');
  unavailable = true; await browser.calculateModels(); assert.match(textAt('#model-agreement'), /not_evaluable/); assert.equal(elements.get('#model-values-table tbody').children[3].children[3].textContent, 'Unavailable'); assert.match(textAt('#model-directional-plot'), /No observed aggressor side/); unavailable = false;
  // A late response must never resurrect a grid after shared controls change.
  deferModels = true; const pendingGrid = browser.calculateModels(true); await flush(); const firstPending = pending.at(-1); browser.applyModelPreset('iv-down'); assert(firstPending.signal.aborted); assert.equal(browser.state.models, null); assert(!textAt('#model-grid-summary').includes('54 calculated')); assert.deepEqual([elements.get('#spot-number').value, elements.get('#iv-number').value, elements.get('#time-number').value], [0, -1, 0]); firstPending.resolve(); await pendingGrid; assert.equal(browser.state.models, null);
  // A source change must clear pending model results and use the selected portable artifact.
  const pendingOld = browser.calculateModels(); await flush(); const oldSource = pending.at(-1); deferModels = false; const beforeSwitch = requests.length; const switchingNq = browser.loadSource('saved-checkpoint-nq'); assert.equal(elements.get('#spot-effective').textContent, 'Original price pending', 'Switching markets must immediately clear the prior price label'); assert.match(elements.get('#source-fingerprint').textContent, /pending.*local inputs only/); assert(!elements.get('#source-fingerprint').textContent.includes('b'.repeat(12)), 'A pending model comparison cannot display the previous result hash'); await switchingNq; assert.equal(elements.get('#spot-effective').textContent, 'Original price 29,392.5', 'Models source switching must update the shared price control without a redundant Calculate request'); assert.equal(requests.slice(beforeSwitch).filter(item => item.path === 'calculate').length, 0, 'Source switching in Models must not calculate a duplicate single model'); assert.equal(requests.slice(beforeSwitch).filter(item => item.path === 'models').length, 1); assert(oldSource.signal.aborted); oldSource.resolve(); await pendingOld; assert.equal(browser.state.source, 'saved-checkpoint-nq'); assert.equal(browser.requestFromControls().session, 'terminal-checkpoint'); assert.equal(browser.requestFromControls().terminal_checkpoint, nqArtifact); assert.equal(browser.state.modelsRequest.terminal_checkpoint, nqArtifact); assert.match(elements.get('#model-price-down').textContent, /100/); assert.match(elements.get('#model-grid-bounds').textContent, /−100 \/ 0 \/ \+100/); assert.equal(browser.state.models.grid, null);
  browser.applyModelPreset('price-up'); assert.equal(elements.get('#spot-number').value, 100); assert.equal(elements.get('#iv-number').value, 0); assert.equal(elements.get('#time-number').value, 0);
  browser.setView('compare'); await flush(); assert(!elements.get('#position-model').disabled); assert(!elements.get('.metric-strip').hidden); assert(browser.state.calculation, 'Returning to Compare recalculates the shared controls');
  // Returning to Fragility after a model-only edit must not reveal stale single-model metrics.
  browser.setView('models'); await flush(); browser.applyModelPreset('time-60'); assert.equal(browser.state.calculation, null); browser.setView('fragility'); assert(elements.get('.metric-strip').hidden, 'Stale metric strip stays hidden while refreshing'); await flush(); assert(browser.state.calculation); assert.equal(browser.state.calculation.request.time_advance, 60); assert(!elements.get('.metric-strip').hidden);
  // A stale ES receipt reproduction must not replace a newer NQ source and its results.
  browser.setView('models'); await flush(); const esRequest = {...defaults, terminal_checkpoint: terminalArtifact, spot_shift: 0, iv_shift: 0, time_advance: 0, grid: true}; const esReproduction = makeReport(esRequest); const reopening = browser.reopenRequest('models', esRequest, esReproduction).then(() => null, error => error); const newerSource = browser.loadSource('saved-checkpoint-nq'); await newerSource; const currentModels = browser.state.models; const staleError = await reopening; assert.match(staleError.message, /Source or assumptions changed/); assert.equal(browser.state.source, 'saved-checkpoint-nq'); assert.equal(browser.state.models, currentModels); assert.equal(browser.state.modelsRequest.terminal_checkpoint, nqArtifact); assert.notEqual(browser.state.models, esReproduction);
  // A playable bundled checkpoint change must transfer busy ownership to Models.
  await browser.loadSource('wind-tunnel-lab'); assert.equal(browser.state.view, 'models'); assert.equal(elements.get('#checkpoint').disabled, false);
  const beforeCheckpoint = requests.length; elements.get('#checkpoint').listeners.input({target: {value: '0'}});
  assert.equal(browser.state.busy, true, 'Checkpoint debounce must disable actions until the requested calculation starts');
  await new Promise(resolve => realSetTimeout(resolve, 220)); await flush();
  assert.equal(browser.state.busy, false, 'Models completion must release inherited single-calculation busy ownership'); assert.equal(browser.state.modelsBusy, false);
  assert.equal(elements.get('#save-scenario').disabled, false); assert.equal(elements.get('#run-model-grid').disabled, false);
  assert.equal(requests.slice(beforeCheckpoint).filter(item => item.path === 'models').length, 1); assert.equal(requests.slice(beforeCheckpoint).filter(item => item.path === 'calculate').length, 0);
  await browser.calculateModels(true); assert.equal(browser.state.models.grid.case_count, 54, 'Grid can run after a replay checkpoint change');
  browser.setView('compare'); await flush(); assert(browser.state.calculation); assert.equal(browser.state.calculation.request.checkpoint, 0); assert.equal(browser.state.busy, false);
  console.log('model comparison browser regressions passed');
})().catch(error => {console.error(error); process.exitCode = 1;});
"""


BROWSER_HEALTH_RANGES_HARNESS = BROWSER_DOM_HARNESS + r"""
const renderedText = element => [element.textContent, ...element.children.map(renderedText)].join(' ');
const textAt = selector => renderedText(elements.get(selector));
const clone = value => JSON.parse(JSON.stringify(value));
const plots = [];
global.Plotly = {react: async (target, traces, layout) => {target.data = traces; plots.push({target, traces: clone(traces), layout: clone(layout)});}, purge: target => {target.data = null;}, Plots: {resize() {}}}; window.Plotly = global.Plotly;
global.fetch = () => {throw new Error('Presentation-only changes must make no API or external requests');};
let app = fs.readFileSync(root + '/app.js', 'utf8'); app = app.replace('  initialize();', '  globalThis.browser = {bindEvents, updateSourceContext, renderPricingAssumptions, renderCompare, renderModels, showSource, state};'); vm.runInThisContext(app, {filename: 'app.js'});
browser.bindEvents();
const source = {name: 'terminal-checkpoint', source_kind: 'terminal_checkpoint', symbol: 'ES', as_of: '2026-10-16T20:59:59Z', data_mode: 'REPLAY', synthetic: false, quality: {status: 'REPLAY', health: 'degraded', fallback_iv_tick_count: 7}};
browser.state.sources = [source]; browser.state.source = source.name;
browser.updateSourceContext(source);
assert.equal(textAt('#header-mode'), 'Mode: REPLAY');
assert.equal(textAt('#header-health'), 'Health: degraded', 'Replay mode must never mask degraded feed health');
assert.match(textAt('#source-context'), /Mode: REPLAY.*Health: degraded.*source ledger.*pricing-coverage denominator/);
browser.updateSourceContext({...source, quality: {status: 'REPLAY'}});
assert.equal(textAt('#header-health'), 'Health: unknown', 'Missing health must be explicitly unknown, never REPLAY');
browser.updateSourceContext({...source, quality: {status: 'healthy'}});
assert.equal(textAt('#header-health'), 'Health: healthy', 'Recognized legacy health status remains supported');
browser.updateSourceContext({...source, quality: {status: 'healthy', health: 'down'}});
assert.equal(textAt('#header-health'), 'Health: down', 'Explicit health takes priority over status');
browser.updateSourceContext(source);
const coverage = {selected_contract_count: 4, priced_contract_count: 4, selected_quantity: 100, priced_quantity: 100};
const freshness = {capture_precision_ambiguity_contract_count: 1, capture_precision_ambiguity_quantity: 30, as_of: source.as_of, capture_as_of: source.as_of, time_basis: 'captured_cutoff', recent_contract_count: 1, older_contract_count: 1, unknown_contract_count: 1, not_applicable_contract_count: 1, retained_iv_contract_count: 1, older_quantity: 20, unknown_quantity: 30, not_applicable_quantity: 40, max_age_seconds: 7200, max_retained_age_seconds: 7200};
const baseline = {status: 'available', spot: 7770, summary: {total_net_gex: 103e9, gamma_wall: 7770}, matrix: {strikes: [1000, 7700, 7770, 7850, 20000], net_gex: [100e9, 1e9, 3e9, -2e9, 1e9]}, pricing_coverage: coverage, iv_freshness: freshness, pricing_assumptions: {summary: 'Frozen pricing inputs', early_exercise_modeled: true}};
const scenario = clone(baseline); scenario.spot = 7795; scenario.summary.total_net_gex = 101e9; scenario.matrix.net_gex = [100e9, 1e9, 1e9, -2e9, 1e9]; scenario.iv_freshness = {...freshness, as_of: '2026-10-16T21:59:59Z', time_basis: 'scenario_model_time', recent_contract_count: 0, older_contract_count: 2, max_age_seconds: 10800, max_retained_age_seconds: 10800};
const report = {request: {spot_shift: 25, iv_shift: 0, time_advance: 60}, baseline, scenario};
browser.state.calculation = report; browser.renderPricingAssumptions(report);
const coverageText = textAt('#pricing-coverage-content');
const coverageBox = elements.get('#pricing-coverage-content'), collapsed = coverageBox.children.find(element => element.tagName === 'DETAILS');
assert(collapsed && !collapsed.open, 'Detailed evidence must use a collapsed native disclosure by default');
assert.match(renderedText(collapsed), /Pricing, IV age & unpriced details.*unknown IV age because the captured cutoff was truncated to microseconds.*Scenario model time/);
const visibleHeadline = coverageBox.children.filter(element => element.tagName !== 'DETAILS').map(renderedText).join(' ');
assert.match(visibleHeadline, /Complete.*4 \/ 4 contracts priced.*Accepted-IV age/);
assert(!visibleHeadline.includes('cutoff was truncated'), 'Precision explanation belongs inside discoverable details');
assert(!visibleHeadline.includes('not an IV pricing expiry'), 'Detailed interpretation must not push the charts below the viewport');

assert.match(coverageText, /Original · Complete.*Scenario · Complete/, 'Different IV reference times must keep both freshness states even when pricing coverage matches');
assert.match(coverageText, /1 within 5m.*1 older than 5m.*1 unknown.*1 not applicable.*Oldest 2h.*retained prior-valid 1/);
assert.match(coverageText, /0 within 5m.*2 older than 5m.*Oldest 3h/);
assert.match(coverageText, /5m is an age reference, not an IV pricing expiry/);
assert.match(coverageText, /1 contract\(s\), 30 selected quantity have unknown IV age because the captured cutoff was truncated to microseconds.*cannot resolve.*does not establish a future observation or zero age/);
assert.match(coverageText, /Scenario model time 2026-10-16 21:59:59 UTC/);
assert.match(textAt('#pricing-model-context'), /Captured .*UTC.*scenario model time .*UTC.*IV age details below/);
browser.renderPricingAssumptions({baseline: {...baseline, iv_freshness: undefined}});
assert.match(textAt('#pricing-coverage-content'), /Accepted-IV age: unknown.*Freshness metadata unavailable/);
assert(!textAt('#pricing-coverage-content').includes('Oldest 0'), 'Unknown ages cannot become zero or fresh');
browser.renderPricingAssumptions(report);
browser.state.view = 'compare'; const before = JSON.stringify(report); browser.renderCompare();
let paired = plots.slice(-2);
assert.deepEqual(paired[0].layout.xaxis.range, paired[1].layout.xaxis.range);
assert.deepEqual(paired[0].layout.yaxis.range, paired[1].layout.yaxis.range);
assert(paired[0].layout.yaxis.range[1] < 10, 'Focused exposure axis ignores clipped outlier values while retaining all data');
assert.deepEqual(paired[0].layout.shapes.map(value => value.x0), [7770, 7795], 'Markers must use actual original and scenario futures prices');
assert.deepEqual(paired[0].layout.shapes, paired[1].layout.shapes, 'Both plots share the same markers');
assert.deepEqual(paired[0].layout.shapes.map(value => value.line.dash), ['dot', 'dash']);
assert(paired[0].layout.annotations.some(value => value.text === 'Original price 7,770'));
assert(paired[0].layout.annotations.some(value => value.text === 'Scenario price 7,795'));
assert.deepEqual(paired[0].traces[0].x, baseline.matrix.strikes, 'Price shifts must never move strikes');
assert.match(textAt('#compare-range-note'), /2 of 5 strikes outside view.*all contracts, totals and exact strike values are retained/);
assert.equal(elements.get('#comparison-table tbody').children.length, 5, 'Exact table retains clipped strikes');
elements.get('#compare-strike-range').listeners.change({target: {value: 'full'}});
paired = plots.slice(-2);
assert(paired[0].layout.xaxis.range[0] < 1000 && paired[0].layout.xaxis.range[1] > 20000);
assert(paired[0].layout.yaxis.range[1] > 100);
assert.match(textAt('#compare-range-note'), /Full strike range.*0 of 5 strikes outside/);
assert.equal(elements.get('#models-strike-range').value, 'full');
assert.equal(JSON.stringify(report), before, 'Display-range controls must not change any results or source data');
// Tick precision must survive both marker geometry and visible price labels.
browser.state.calculation = {...report, baseline: {...baseline, spot: 7702.875}, scenario: {...scenario, spot: 7727.875}}; browser.renderCompare();
assert.deepEqual(plots.at(-1).layout.shapes.map(value => value.x0), [7702.875, 7727.875]);
assert(plots.at(-1).layout.annotations.some(value => value.text === 'Original price 7,702.875'));
assert(plots.at(-1).layout.annotations.some(value => value.text === 'Scenario price 7,727.875'));
assert.match(textAt('#compare-price-legend'), /Original price 7,702\.875.*Scenario price 7,727\.875/);
// Coincident prices use one explicitly combined marker. Missing prices fall back to full range.
browser.state.calculation = {...report, scenario: {...scenario, spot: 7770}}; browser.renderCompare();
assert.equal(plots.at(-1).layout.shapes.length, 1); assert.match(plots.at(-1).layout.annotations[0].text, /Original \+ scenario price 7,770/);
browser.state.calculation = {...report, scenario: {...scenario, spot: null}};
elements.get('#compare-strike-range').listeners.change({target: {value: 'focused'}});
assert.match(textAt('#compare-range-note'), /Full range \(price unavailable\)/);
assert(!plots.at(-1).layout.annotations.some(value => value.text.includes('Scenario price')));
// Models share focus axes, retain every exact strike and expose freshness separately from coverage.
browser.state.calculation = report; browser.state.view = 'models';
browser.state.models = {request: report.request, models: [{model: 'terminal_selected', baseline, scenario}, {model: 'directionalized_trade_volume', baseline: {...baseline, summary: {total_net_gex: 1e9, gamma_wall: 7770}}, scenario: {...scenario, summary: {total_net_gex: -1e9, gamma_wall: 7850}}}], agreement: {scenario: {status: 'available', net_sign_matches: false, gamma_wall_matches: false}}};
browser.renderModels(); const modelBefore = JSON.stringify(browser.state.models);
assert.match(textAt('#model-cards'), /Original · Accepted-IV age: 1 within 5m.*Scenario · Accepted-IV age: 0 within 5m/);
assert.equal(elements.get('#model-strike-table tbody').children.length, 5);
paired = plots.slice(-2); assert.deepEqual(paired[0].layout.xaxis.range, paired[1].layout.xaxis.range); assert.deepEqual(paired[0].layout.yaxis.range, paired[1].layout.yaxis.range); assert.deepEqual(paired[0].layout.shapes.map(value => value.x0), [7770, 7795]);
elements.get('#models-strike-range').listeners.change({target: {value: 'full'}});
assert.equal(JSON.stringify(browser.state.models), modelBefore); assert.equal(elements.get('#model-strike-table tbody').children.length, 5); assert.match(textAt('#models-range-note'), /0 of 5 strikes outside/);
browser.showSource(); assert.match(textAt('#info-content'), /Captured source health degraded.*Accepted-IV age.*5m is an age reference, not an IV pricing expiry/);
console.log('health freshness and focused strike browser regressions passed');
"""

if __name__ == "__main__":
    unittest.main()
