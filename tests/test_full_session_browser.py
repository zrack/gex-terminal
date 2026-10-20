"""Large frozen sources open useful comparisons before optional landscapes."""
import asyncio
from importlib.resources import files
import json
import shutil
import subprocess
import unittest
from unittest.mock import patch

from gex_terminal import wind_tunnel as wind
from gex_terminal.wind_tunnel_checkpoint import build_terminal_checkpoint, checkpoint_transport
from tests.test_pricing_coverage import consumer_with
from tests.test_wind_tunnel_assets import BROWSER_DOM_HARNESS
from tests.test_wind_tunnel_checkpoint import option


class FullSessionBrowserTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("node"), "Node.js is needed for browser workflow regression")
    def test_large_source_lazy_coarse_landscape_and_failure_keep_compare_usable(self):
        async def artifact():
            return await build_terminal_checkpoint(await consumer_with(option("priced")), fallback_dte=.25)
        opaque = checkpoint_transport(asyncio.run(artifact()))
        result = subprocess.run([shutil.which("node"), "-e", LARGE_BROWSER_HARNESS,
                                 str(files("gex_terminal").joinpath("wind_tunnel_web"))],
                                input=json.dumps({"artifact": opaque}), capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("large browser workflow passed", result.stdout)


class SurfaceResponsivenessTests(unittest.IsolatedAsyncioTestCase):
    async def test_surface_yields_after_each_cell_without_changing_grid_order(self):
        artifact = await build_terminal_checkpoint(await consumer_with(option("priced")), fallback_dte=.25)
        evaluations, yield_counts = [], []
        original = wind._state

        def evaluate(*args, **kwargs):
            evaluations.append((args[1]["spot_shift"], args[1]["time_advance"]))
            return original(*args, **kwargs)

        async def cooperate(delay):
            self.assertEqual(delay, 0)
            yield_counts.append(len(evaluations))

        with patch.object(wind, "_state", side_effect=evaluate), patch.object(wind.asyncio, "sleep", side_effect=cooperate):
            report = await wind.surface({"terminal_checkpoint": artifact, "spot_shifts": [-100, 0, 100],
                                         "time_advances": [0, 30, 60]})
        self.assertEqual(yield_counts, list(range(2, 19, 2)))
        self.assertEqual([(point["time_index"], point["spot_index"]) for point in report["points"]],
                         [(time, spot) for time in range(3) for spot in range(3)])

    async def test_surface_cancellation_stops_after_first_cell(self):
        artifact = await build_terminal_checkpoint(await consumer_with(option("priced")), fallback_dte=.25)
        with patch.object(wind, "_state", wraps=wind._state) as evaluated, \
                patch.object(wind.asyncio, "sleep", side_effect=asyncio.CancelledError):
            with self.assertRaises(asyncio.CancelledError):
                await wind.surface({"terminal_checkpoint": artifact, "spot_shifts": [-100, 0, 100],
                                    "time_advances": [0, 30, 60]})
        self.assertEqual(evaluated.call_count, 2)


LARGE_BROWSER_HARNESS = BROWSER_DOM_HARNESS + r"""
const artifact = JSON.parse(fs.readFileSync(0, 'utf8')).artifact, originalArtifact = artifact;
let rowCount = 2164, surfaceFailure = false, requests = [];
const defaults = {session: 'terminal-checkpoint', checkpoint: 0, model: 'terminal_selected', fallback_dte: .25, risk_free_rate: .045};
const source = {name: 'terminal-checkpoint', label: 'Saved NQ full session', symbol: 'NQ', source_kind: 'terminal_checkpoint', status: 'available', terminal_checkpoint: artifact, defaults};
const tabs = ['landscape', 'compare', 'fragility'].map(view => {const tab = new Element('button'); tab.dataset = {view}; return tab;});
document.querySelectorAll = selector => selector === '.tabs button' ? tabs : [];
const coverage = {status: 'partial', selected_contract_count: 2164, priced_contract_count: 2161, selected_quantity: 47679, priced_quantity: 47673, unpriced_contract_count: 3, unpriced_quantity: 6};
const excluded = {contract_id: 'unpriced', expiry: '2026-10-16', quantity: 6, reason: 'iv_unavailable', iv_provenance: {status: 'outside_no_arbitrage_bounds', option_price: 508, lower_bound: 529.61}};
function calculated(request) {const value = {status: 'available', spot: 6000, counts: {source_rows: rowCount, selected_rows: rowCount}, summary: {total_net_gex: 1000, gamma_wall: 6000}, matrix: {strikes: [6000], net_gex: [1000]}, pricing_coverage: coverage, excluded_contracts: [excluded]}; return {request, baseline: value, scenario: value, result_sha256: 'a'.repeat(64)};}
global.fetch = async (url, options) => {
  const path = url.replace('/api/', ''), body = options.body ? JSON.parse(options.body) : null;
  requests.push({path, body});
  let result;
  if (path === 'catalog') result = {sessions: [source], defaults};
  else if (path === 'calculate') result = calculated(body);
  else if (path === 'surface') {
    if (surfaceFailure) return {ok: false, status: 408, json: async () => ({error: {message: 'Landscape exceeded its time limit'}})};
    result = {request: body, axes: {spot_shifts: body.spot_shifts, baseline_underlying_prices: body.spot_shifts.map(x => 6000 + x), scenario_underlying_prices: body.spot_shifts.map(x => 6000 + x), time_advances: body.time_advances, scenario_time_advances: body.time_advances}, points: body.time_advances.flatMap((_, ti) => body.spot_shifts.map((__, si) => ({time_index: ti, spot_index: si, baseline_total_net_gex: 1000, scenario_total_net_gex: 1000}))), result_sha256: 'b'.repeat(64)};
  } else throw new Error('Unexpected API path ' + path);
  return {ok: true, status: 200, json: async () => result};
};
let app = fs.readFileSync(root + '/app.js', 'utf8');
app = app.replace('  initialize();', '  globalThis.browser = {initialize, setView, loadSource, calculateLandscape, clearLandscape, state};');
vm.runInThisContext(app, {filename: 'app.js'});
const surfaces = () => requests.filter(request => request.path === 'surface');
const renderedText = element => [element.textContent, ...element.children.map(renderedText)].join(' ');
async function settle() {for (let count = 0; browser.state.surfaceBusy && count < 100; count++) await new Promise(setImmediate); assert.equal(browser.state.surfaceBusy, false);}
(async () => {
  await browser.initialize();
  assert.equal(browser.state.view, 'compare');
  assert.equal(tabs.find(tab => tab.dataset.view === 'compare')['aria-selected'], true);
  assert.equal(surfaces().length, 0, 'Large initialization must not calculate an eager landscape');
  assert(browser.state.calculation);
  const calculation = browser.state.calculation, coverageBefore = renderedText(elements.get('#pricing-coverage-content'));
  assert.match(coverageBefore, /2,161 \/ 2,164/); assert.match(coverageBefore, /47,673 \/ 47,679/);
  browser.setView('landscape'); await settle();
  assert.equal(surfaces().length, 1);
  assert.deepEqual(surfaces()[0].body.spot_shifts, [-100, 0, 100]);
  assert.deepEqual(surfaces()[0].body.time_advances, [0, 30, 60]);
  assert.equal(surfaces()[0].body.terminal_checkpoint, originalArtifact);
  assert.match(elements.get('#landscape-caption').textContent, /Coarse 3 × 3 grid · 9 calculated samples/);
  browser.setView('compare'); browser.setView('landscape'); await settle();
  assert.equal(surfaces().length, 1, 'Returning to a calculated landscape reuses its valid result');
  browser.clearLandscape(); browser.setView('compare'); surfaceFailure = true;
  browser.setView('landscape'); await settle();
  assert.equal(browser.state.calculation, calculation, 'Landscape error must preserve the comparison object');
  assert.equal(renderedText(elements.get('#pricing-coverage-content')), coverageBefore);
  assert.equal(browser.state.terminalCheckpoint, originalArtifact);
  assert.equal(browser.state.surface, null);
  assert.equal(elements.get('#save-scenario').disabled, false, 'Comparison remains saveable after a landscape failure');
  assert(!elements.get('#scenario-state').textContent.includes('Calculation unavailable'));
  assert.match(elements.get('#calculation-status').textContent, /Compare remains available/);
  browser.setView('compare');
  assert.match(elements.get('#calculation-status').textContent, /Compare ready/);
  rowCount = 500; surfaceFailure = false;
  await browser.loadSource('terminal-checkpoint');
  const small = surfaces().at(-1).body;
  assert.equal(small.spot_shifts.length, 17); assert.equal(small.time_advances.length, 9);
  assert.equal(browser.state.largeCheckpoint, false);
  assert(requests.filter(request => request.path !== 'catalog').every(request => request.body.terminal_checkpoint === originalArtifact), 'Every request must preserve the opaque checkpoint bytes');
  console.log('large browser workflow passed');
})().catch(error => {console.error(error); process.exitCode = 1;});
"""


if __name__ == "__main__":
    unittest.main()
