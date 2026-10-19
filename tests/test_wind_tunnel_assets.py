import asyncio
import hashlib
from importlib.resources import files
import json
import shutil
import subprocess
import unittest


class WindTunnelAssetTests(unittest.TestCase):
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


BROWSER_HANDOFF_HARNESS = r"""
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
elements.set('#comparison-table tbody', new Element('tbody')); elements.set('#search-table tbody', new Element('tbody'));
global.document = {querySelector: selector => {if (selector.includes('option[value=')) return null; assert(elements.has(selector), 'Missing browser element: ' + selector); return elements.get(selector);}, querySelectorAll: () => [], createElement: tag => new Element(tag), addEventListener() {}, body: new Element('body')};
global.window = {addEventListener() {}};
global.location = {origin: 'http://127.0.0.1:12345', hash: '#cap=local-test-capability', pathname: '/', search: ''};
global.history = {replaceState() {}}; global.sessionStorage = {setItem() {}, getItem() {return null;}, removeItem() {}};
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
  assert.match(elements.get('#source-context').textContent, /2026-10-19.*quality: SIM.*synthetic DEMO/);
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
  const importTarget = () => ({files: [{size: rawReceipt.length, text: async () => rawReceipt}], disabled: false, value: 'receipt.json'});
  verificationStatus = 'mismatch'; await browser.importReceipt({target: importTarget()});
  assert.equal(browser.state.source, 'wind-tunnel-lab', 'Unverified receipt must not replace the active source');
  assert.equal(browser.state.terminalCheckpoint, null);
  verificationStatus = 'verified';
  await browser.importReceipt({target: {files: [{size: rawReceipt.length, text: async () => rawReceipt}], disabled: false, value: 'receipt.json'}});
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


if __name__ == "__main__":
    unittest.main()
