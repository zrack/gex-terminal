"""Exercise the shipped intake controller, including asynchronous ownership races."""
import asyncio
from importlib.resources import files
import json
import shutil
import subprocess
import unittest


@unittest.skipUnless(shutil.which("node"), "Node.js is needed for the browser intake harness")
class WindTunnelIntakeAssetTests(unittest.TestCase):
    def test_guided_session_keeps_opaque_checkpoint_and_portable_receipt(self):
        from gex_terminal.consumer import StatefulGexConsumer
        from gex_terminal.engine import IntradayGexEngine
        from gex_terminal.wind_tunnel_checkpoint import build_terminal_checkpoint, validate_checkpoint

        async def fixture():
            consumer = StatefulGexConsumer(IntradayGexEngine(50.0), data_mode="demo", risk_free_rate=.037)
            for message in (
                {"type": "underlying_tick", "symbol": "ES", "price": 6000.0, "timestamp": "2026-10-18T15:34:00Z"},
                {"type": "options_volume_tick", "strike": 6000.0, "option_type": "C", "volume": 20,
                 "iv": .2, "expiry": "2026-10-19", "timestamp": "2026-10-18T15:34:00Z"},
            ):
                await consumer.update_market_state(json.dumps(message))
            return await build_terminal_checkpoint(consumer, fallback_dte=.75,
                                                   source_label="Local capture " + "a" * 64 + " · event 2")

        artifact = asyncio.run(fixture())
        transport = json.dumps(artifact, sort_keys=True, separators=(",", ":"), allow_nan=False)
        result = self.run_harness("flow", transport)
        returned = json.loads(result.stdout.splitlines()[-1])
        self.assertEqual(returned["request"]["terminal_checkpoint"], transport)
        self.assertEqual(validate_checkpoint(returned["request"]["terminal_checkpoint"]), artifact)
        # Verify the browser-emitted JSON request can reproduce through the real core.
        from gex_terminal.wind_tunnel_server import make_receipt, reproduce_receipt
        receipt = asyncio.run(make_receipt("Guided intake transport", "calculate", returned["request"]))
        self.assertEqual(asyncio.run(reproduce_receipt(receipt))["status"], "verified")

    def test_failed_canceled_and_stale_intake_never_replace_current_source(self):
        self.run_harness("races", '{"source":{},"parameters":{}}')

    def test_permission_size_partial_and_malformed_inventory_fail_closed(self):
        self.run_harness("bounds", '{"source":{},"parameters":{}}')

    def run_harness(self, mode, artifact):
        root = files("gex_terminal").joinpath("wind_tunnel_web")
        result = subprocess.run([shutil.which("node"), "-e", BROWSER_INTAKE_HARNESS, str(root), mode],
                                input=json.dumps({"artifact": artifact}), text=True, capture_output=True,
                                timeout=15, check=False)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("intake browser workflow passed", result.stdout)
        return result


BROWSER_INTAKE_HARNESS = r"""
const assert = require('node:assert/strict'), fs = require('node:fs'), vm = require('node:vm');
const root = process.argv[1], mode = process.argv[2], artifact = JSON.parse(fs.readFileSync(0, 'utf8')).artifact;
const realSetTimeout = global.setTimeout; global.setTimeout = (...args) => {const timer = realSetTimeout(...args); timer.unref(); return timer;};
class Element {
  constructor(tag = 'div') {this.tagName = tag.toUpperCase(); this.children = []; this.files = []; this.value = ''; this.textContent = ''; this.hidden = false; this.disabled = false; this.checked = false; this.listeners = {}; this.classes = new Set(); this.classList = {add: v => this.classes.add(v), remove: v => this.classes.delete(v), contains: v => this.classes.has(v), toggle: (v, yes) => yes ? this.classes.add(v) : this.classes.delete(v)};}
  get options() {return this.children.filter(item => item.tagName === 'OPTION');}
  append(...items) {this.children.push(...items);}
  replaceChildren(...items) {this.children = [...items]; this.value = '';}
  addEventListener(name, action) {this.listeners[name] = action;}
  setAttribute(name, value) {this[name] = value;}
  checkValidity() {return this.value !== '' && Number.isFinite(Number(this.value));}
  showModal() {this.open = true;}
  close() {this.open = false; this.listeners.close?.();}
  focus() {} select() {}
}
const page = fs.readFileSync(root + '/index.html', 'utf8'), elements = new Map(), element = id => elements.get('#' + id);
for (const match of page.matchAll(/<([a-z][a-z0-9]*)\b[^>]*\bid="([^"]+)"[^>]*>/g)) {const e = new Element(match[1]); e.value = match[0].match(/\bvalue="([^"]*)"/)?.[1] || ''; elements.set('#' + match[2], e);}
for (const match of page.matchAll(/<select\b[^>]*\bid="([^"]+)"[^>]*>([\s\S]*?)<\/select>/g)) {const select = element(match[1]); for (const om of match[2].matchAll(/<option\b([^>]*)>([^<]*)<\/option>/g)) {const option = new Element('option'); option.value = om[1].match(/value="([^"]*)"/)?.[1] || ''; option.textContent = om[2]; select.append(option); if (!select.value || om[1].includes('selected')) select.value = option.value;}}
elements.set('#comparison-table tbody', new Element('tbody')); elements.set('#search-table tbody', new Element('tbody'));
global.document = {querySelector: selector => {if (selector.includes('option[value=')) return null; assert(elements.has(selector), 'Missing ' + selector); return elements.get(selector);}, querySelectorAll: () => [], createElement: tag => new Element(tag), addEventListener() {}, body: new Element('body')};
global.window = {addEventListener() {}}; global.location = {origin: 'http://127.0.0.1:12345', hash: '#cap=local-test-capability', pathname: '/', search: ''}; global.history = {replaceState() {}}; global.sessionStorage = {setItem() {}, getItem() {return null;}, removeItem() {}};
const bundled = {name: 'wind-tunnel-lab', label: 'Synthetic lab', symbol: 'ES', status: 'available'};
const defaults = {session: 'wind-tunnel-lab', model: 'raw_trade_volume', fallback_dte: .25, risk_free_rate: .045};
const inventory = {intake_id: 'verified-token', content_sha256: 'a'.repeat(64), symbol: 'ES', source_kind: 'captured_session', synthetic: true, source: {provider: 'replay', mode: 'demo'}, event_count: 2, first_event_time: '2026-10-18T15:33:00Z', last_event_time: '2026-10-18T15:34:00Z', model_inputs: {contract_multiplier: 50, risk_free_rate: .037, days_to_expiry: .75}, quality: {available: true, scope: 'recorded_end_of_session', status: 'SIM', health: 'healthy', malformed_count: 0, dropped_count: 0, fallback_iv_tick_count: 1}, warnings: ['Fallback IV may be used; integrity does not certify a provider.'], event_time_fallback_count: 0, checkpoints: [{sequence: 0, event_time: '2026-10-18T15:33:00Z', event_type: 'underlying_tick'}, {sequence: 1, event_time: '2026-10-18T15:34:00Z', event_type: 'options_volume_tick'}], default_sequence: 1};
let requests = [], saved, inspection = async () => structuredClone(inventory), freeze = async () => ({terminal_checkpoint: artifact});
global.fetch = async (url, options) => {
  assert.equal(options.headers['X-GEX-Capability'], 'local-test-capability');
  const path = url.replace('/api/', ''), raw = options.body;
  const body = path === 'intake' ? raw : raw ? JSON.parse(raw) : null;
  requests.push({path, body, options}); let result;
  if (path === 'catalog') result = {sessions: [bundled], defaults};
  else if (path.startsWith('checkpoints?')) result = {checkpoints: [{index: 0, as_of: '2026-10-18T15:34:00Z'}]};
  else if (path === 'intake') {assert.equal(options.headers['Content-Type'], 'application/octet-stream'); result = await inspection(raw);}
  else if (path === 'intake/checkpoint') result = await freeze(body);
  else if (path.startsWith('intake/') && options.method === 'DELETE') result = {status: 'discarded'};
  else if (path === 'calculate') {const value = {spot: 6000, summary: {total_net_gex: 1, gamma_wall_strike: 6000}}; result = {request: body, baseline: value, scenario: value, result_sha256: 'b'.repeat(64)};}
  else if (path === 'surface') result = {request: body, axes: {}, points: [], result_sha256: 'c'.repeat(64)};
  else if (path === 'receipts') {saved = body; result = {id: 'receipt'};}
  else if (path === 'reproduce') result = {status: 'verified', result: {request: body.request}};
  else throw new Error('Unexpected ' + path);
  return {ok: true, status: 200, json: async () => result};
};
let app = fs.readFileSync(root + '/app.js', 'utf8');
app = app.replace('  initialize();', '  globalThis.browser = {initialize, showIntake, changeIntakeFile, toggleIntake, verifySession, openIntakeCheckpoint, discardIntake, requestFromControls, saveReceipt, importReceipt, loadSource, state, intake};');
vm.runInThisContext(app, {filename: 'app.js'});
const file = (name = 'capture.gex-session.jsonl', size = 500) => ({name, size, privatePath: '/must-not-be-sent-as-a-path'});
function choose(selected = file(), permission = true) {element('session-file').files = [selected]; browser.changeIntakeFile(); element('intake-rights').checked = permission; browser.toggleIntake(); return selected;}
function deferred() {let resolve; const promise = new Promise(r => {resolve = r;}); return {promise, resolve};}
const unchanged = () => {assert.equal(browser.state.source, 'wind-tunnel-lab'); assert.equal(browser.state.terminalCheckpoint, null);};
(async () => {
  await browser.initialize(); unchanged(); browser.showIntake();
  if (mode === 'flow') {
    const selected = choose(); await browser.verifySession(); unchanged();
    assert.equal(requests.find(r => r.path === 'intake').body, selected, 'Send the original File bytes; do not read a server path');
    assert.equal(element('intake-review').hidden, false); assert.equal(element('open-intake-checkpoint').disabled, false);
    const details = element('intake-details').children.map(e => e.textContent).join('\n');
    assert.match(details, /integrity is not provider certification/); assert.match(details, /synthetic inputs/); assert.match(details, /3\.7%/); assert.match(details, /0\.75 days/); assert.match(details, /a{64}/); assert.match(details, /end of session, not the selected prefix/); assert.match(details, /fallback IV 1/);
    assert.equal(element('intake-warnings').children[0].textContent, inventory.warnings[0]); assert.match(element('intake-checkpoint-note').textContent, /raw captured prefix.*authoritative accepted cutoff/); assert.match(element('intake-checkpoint').options[1].textContent, /raw through/);
    element('intake-checkpoint').value = '1'; await browser.openIntakeCheckpoint();
    assert.deepEqual(requests.find(r => r.path === 'intake/checkpoint').body, {intake_id: 'verified-token', sequence: 1});
    assert.equal(browser.state.source, 'terminal-checkpoint'); assert.equal(browser.requestFromControls().terminal_checkpoint, artifact); assert.equal(browser.requestFromControls().fallback_dte, .75);
    assert.equal(element('intake-dialog').open, false); assert.equal(element('play-replay').disabled, true);
    assert.match(element('header-source').textContent, /Frozen captured checkpoint/); assert.match(element('evidence-limit').textContent, /^Frozen captured inputs/);
    element('scenario-name').value = 'Intake scenario'; await browser.saveReceipt({preventDefault() {}});
    assert.equal(saved.request.terminal_checkpoint, artifact); assert.equal(saved.request.model, 'terminal_selected');
    await browser.loadSource('wind-tunnel-lab'); const rawReceipt = JSON.stringify({kind: 'calculate', request: saved.request});
    await browser.importReceipt({target: {files: [{size: rawReceipt.length, text: async () => rawReceipt}], value: 'receipt.json'}});
    assert.equal(browser.requestFromControls().terminal_checkpoint, artifact); assert.match(element('header-source').textContent, /Frozen captured checkpoint/);
    console.log('intake browser workflow passed'); console.log(JSON.stringify({request: browser.requestFromControls()}));
  } else if (mode === 'races') {
    choose(); inspection = async () => {throw new Error('Capture integrity failed');}; await browser.verifySession(); unchanged(); assert.equal(browser.intake.verified, null); assert.match(element('intake-status').textContent, /integrity failed/);
    const old = deferred(); inspection = () => old.promise; choose(); const pending = browser.verifySession(); assert.equal(requests.filter(r => r.path === 'intake').at(-1).options.signal, undefined, 'Canceled inspections must finish to release their server token'); browser.discardIntake(); old.resolve({...inventory, intake_id: 'canceled-token'}); await pending; unchanged(); assert.equal(browser.intake.verified, null); assert(requests.some(r => r.path === 'intake/canceled-token' && r.options.method === 'DELETE'));
    const first = deferred(); inspection = () => first.promise; choose(); const firstRequest = browser.verifySession(); choose(file('second.gex-session.jsonl')); inspection = async () => ({...inventory, intake_id: 'second-token'}); await browser.verifySession(); first.resolve({...inventory, intake_id: 'first-token'}); await firstRequest; assert.equal(browser.intake.verified.intake_id, 'second-token'); unchanged();
    const late = deferred(); freeze = () => late.promise; const opening = browser.openIntakeCheckpoint(); browser.discardIntake(); late.resolve({terminal_checkpoint: artifact}); await opening; unchanged();
    choose(); inspection = async () => structuredClone(inventory); await browser.verifySession(); freeze = async () => {throw new Error('No usable timed contracts at this checkpoint');}; await browser.openIntakeCheckpoint(); unchanged(); assert.match(element('intake-status').textContent, /No usable timed contracts/); assert.equal(element('open-intake-checkpoint').disabled, false);
    element('intake-rights').checked = false; element('intake-rights').listeners.change(); assert.equal(browser.intake.verified, null); assert.equal(element('open-intake-checkpoint').disabled, true);
    console.log('intake browser workflow passed');
  } else if (mode === 'bounds') {
    choose(file(), false); await browser.verifySession(); assert.equal(requests.filter(r => r.path === 'intake').length, 0); unchanged();
    for (const selected of [file('large.gex-session.jsonl', 4 * 1024 * 1024 + 1), file('empty.gex-session.jsonl', 0), file('capture.gex-session.jsonl.partial')]) {choose(selected); await browser.verifySession(); assert.equal(requests.filter(r => r.path === 'intake').length, 0); assert.equal(browser.intake.verified, null); unchanged();}
    choose(); inspection = async () => ({...inventory, checkpoints: []}); await browser.verifySession(); assert.equal(browser.intake.verified, null); unchanged(); assert.match(element('intake-status').textContent, /usable checkpoint inventory/);
    choose(); inspection = async () => ({...inventory, checkpoints: [{sequence: -1}]}); await browser.verifySession(); assert.equal(browser.intake.verified, null); unchanged();
    console.log('intake browser workflow passed');
  } else throw new Error('Unknown harness mode');
})().catch(error => {console.error(error); process.exitCode = 1;});
"""
