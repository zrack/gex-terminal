import asyncio
from contextlib import AsyncExitStack
from importlib.resources import files
import json
import math
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from urllib.parse import urlsplit

from gex_terminal import wind_tunnel as wind
from gex_terminal.wind_tunnel_investigation import investigate
from tests.test_wind_tunnel_assets import BROWSER_DOM_HARNESS


REQUEST = {"session": "zero-gamma-flip", "remove_call_update": False}
REMOVAL = {**REQUEST, "remove_call_update": True}


class WindTunnelInvestigationTests(unittest.IsolatedAsyncioTestCase):
    async def test_fixed_cutoffs_attribute_the_flip_and_remove_only_the_update(self):
        observed = await investigate(REQUEST)
        removed = await investigate(REMOVAL)
        before, after = observed["before"], observed["after"]
        self.assertEqual(before["as_of"], "2026-07-16T16:00:00Z")
        self.assertEqual(after["as_of"], "2026-07-16T16:00:04Z")
        self.assertEqual(before["spot"], after["spot"])
        self.assertEqual(after["spot"], 5948.75)
        self.assertEqual(before["summary"]["gamma_wall"], 5925)
        self.assertEqual(after["summary"]["gamma_wall"], 5950)
        self.assertLess(before["summary"]["total_net_gex"], 0)
        self.assertGreater(after["summary"]["total_net_gex"], 0)
        self.assertEqual(before["source"]["checkpoint"], 5)
        self.assertEqual(after["source"]["checkpoint"], 6)
        self.assertEqual(before["source"]["source_sha256"], after["source"]["source_sha256"])
        self.assertNotEqual(before["source"]["checkpoint_sha256"], after["source"]["checkpoint_sha256"])
        self.assertEqual(observed["event"]["index"], 6)
        self.assertEqual(observed["event"]["as_of"], after["as_of"])
        self.assertEqual(observed["event"]["volume"], 2880)
        driver = observed["contributions"][0]
        self.assertEqual((driver["strike"], driver["option_type"]), (5950, "C"))
        self.assertEqual((driver["before_quantity"], driver["after_quantity"]), (0, 2880))
        self.assertGreater(driver["delta_gex"], 0)
        delta = after["summary"]["total_net_gex"] - before["summary"]["total_net_gex"]
        self.assertEqual(observed["net_gex_delta"], delta)
        self.assertTrue(math.isclose(observed["attributed_gex_delta"], delta, rel_tol=1e-12, abs_tol=1e-6))
        attributed = math.fsum(row["delta_gex"] for row in observed["contributions"])
        self.assertEqual(attributed, observed["attributed_gex_delta"])
        self.assertIsNone(observed["counterfactual"])
        self.assertEqual(removed["before"], before)
        self.assertEqual(removed["after"], after)
        counterfactual = removed["counterfactual"]
        self.assertEqual(counterfactual["as_of"], after["as_of"])
        self.assertEqual(counterfactual["spot"], after["spot"])
        self.assertEqual(counterfactual["summary"]["gamma_wall"], 5925)
        self.assertLess(counterfactual["summary"]["total_net_gex"], 0)
        self.assertEqual(removed["contributions"][0]["counterfactual_quantity"], 0)
        self.assertEqual(removed["contributions"][0]["counterfactual_gex"], 0)
        self.assertEqual(await investigate(REQUEST), observed)

    async def test_investigation_cannot_choose_a_different_source_event_or_model(self):
        for change in ({"session": "nq-research-loop"}, {"checkpoint": 7}, {"event": 7},
                       {"model": "open_interest"}, {"remove_call_update": 1}, {"remove_call_update": "false"}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                await investigate({**REQUEST, **change})

    async def test_http_receipt_saves_exports_and_reproduces_the_removal(self):
        from aiohttp import ClientSession
        from gex_terminal import wind_tunnel_server as server

        async with AsyncExitStack() as resources:
            directory = resources.enter_context(tempfile.TemporaryDirectory())
            runner, launch = await server.start_server(Path(directory) / "research", port=0)
            resources.push_async_callback(runner.cleanup)
            parsed = urlsplit(launch)
            origin = f"{parsed.scheme}://{parsed.netloc}"
            headers = {"X-GEX-Capability": parsed.fragment.removeprefix("cap=")}
            async with ClientSession(headers=headers) as client:
                async with client.post(f"{origin}/api/investigate", json=REMOVAL) as response:
                    self.assertEqual(response.status, 200, await response.text())
                    displayed = await response.json()
                async with client.post(f"{origin}/api/receipts", json={
                    "name": "ES flip without the call update", "kind": "investigate", "request": displayed["request"],
                }) as response:
                    self.assertEqual(response.status, 200, await response.text())
                    receipt = await response.json()
                async with client.get(f"{origin}/api/receipts/{receipt['receipt_sha256']}/export") as response:
                    self.assertEqual(response.status, 200, await response.text())
                    self.assertIn("attachment", response.headers["Content-Disposition"])
                    exported = await response.read()
                async with client.post(f"{origin}/api/reproduce", data=exported, headers={"Content-Type": "application/json"}) as response:
                    self.assertEqual(response.status, 200, await response.text())
                    reproduced = await response.json()
                self.assertEqual(reproduced["status"], "verified")
                self.assertEqual(receipt["result"], displayed)
                self.assertEqual(reproduced["result"], displayed)


class InvestigationBrowserTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("node"), "Node.js is needed for the browser workflow harness")
    def test_browser_opens_flip_renders_driver_and_saves_selected_branch(self):
        async def fixtures():
            removed = await investigate(REMOVAL)
            return {
                "catalog": wind.catalog(),
                "checkpoints": {session: wind.checkpoints(session) for session in (wind.DEFAULTS["session"], REQUEST["session"])},
                "observed": await investigate(REQUEST),
                "receipt": {"kind": "investigate", "name": "ES removal", "request": removed["request"], "result": removed},
            }

        assets = str(files("gex_terminal").joinpath("wind_tunnel_web"))
        result = subprocess.run(
            [shutil.which("node"), "-e", BROWSER_INVESTIGATION_HARNESS, assets],
            input=json.dumps(asyncio.run(fixtures())), text=True, capture_output=True, timeout=15,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


BROWSER_INVESTIGATION_HARNESS = BROWSER_DOM_HARNESS + r"""
const {catalog, checkpoints, observed, receipt} = JSON.parse(fs.readFileSync(0, 'utf8'));
const flipResult = receipt.result, flipSource = observed.request.session;
const calls = [];
let deferCalculation = false, finishCalculation;
global.fetch = async (url, options) => {
  assert.equal(options.headers['X-GEX-Capability'], 'local-test-capability');
  const path = url.replace('/api/', ''), body = options.body ? JSON.parse(options.body) : null;
  calls.push({path, body});
  const state = {status: 'available', spot: 5948.75, summary: {total_net_gex: 1, gamma_wall: 5950}};
  let result;
  if (path === 'catalog') result = catalog;
  else if (path.startsWith('checkpoints?session=')) result = checkpoints[decodeURIComponent(path.split('=')[1])];
  else if (path === 'calculate') {
    if (deferCalculation) await new Promise(resolve => {finishCalculation = resolve;});
    result = {request: body, baseline: state, scenario: state};
  }
  else if (path === 'surface') result = {request: body, axes: {}, points: []};
  else if (path === 'investigate') result = body.remove_call_update ? flipResult : observed;
  else if (path === 'receipts') result = receipt;
  else if (path === 'reproduce') {
    assert.deepEqual(body, receipt);
    result = {status: 'verified', result: flipResult};
  } else throw new Error('Unexpected endpoint ' + path);
  return {ok: true, status: 200, json: async () => result};
};
const app = fs.readFileSync(root + '/app.js', 'utf8');
assert(app.includes('  initialize();'));
vm.runInThisContext(app.replace('  initialize();', '  globalThis.initializeBrowser = initialize;'));
const element = id => elements.get('#' + id);
const contents = node => [node.textContent, ...node.children.map(contents)].join(' ');
const settle = () => new Promise(setImmediate);
function assertWalls(...strikes) {
  const cards = element('investigation-snapshots').children;
  assert.equal(cards.length, strikes.length);
  strikes.forEach((strike, index) => assert(contents(cards[index]).includes(`Dominant wall ${strike.toLocaleString()}`)));
}
(async () => {
  await initializeBrowser();
  assert(element('investigation-entry').hidden);
  deferCalculation = true;
  const loading = element('source').listeners.change({target: {value: flipSource}});
  await settle();
  assert.equal(element('investigation-entry').hidden, false);
  assert.equal(element('investigate-flip').disabled, true);
  deferCalculation = false;
  finishCalculation();
  await loading;
  await settle();
  assert.equal(element('investigate-flip').disabled, false);
  await element('investigate-flip').listeners.click();
  await settle();
  assert.equal(element('flip-investigation').hidden, false);
  assertWalls(5925, 5950);
  const driver = contents(element('investigation-contract-rows').children[0]);
  assert(driver.includes(`${(5950).toLocaleString()} call`) && driver.includes((2880).toLocaleString()));
  assert.deepEqual(calls.filter(x => x.path === 'investigate').at(-1).body, {session: flipSource, remove_call_update: false});

  element('remove-call-update').checked = true;
  await element('remove-call-update').listeners.change({target: element('remove-call-update')});
  await settle();
  assertWalls(5925, 5950, 5925);
  assert.deepEqual(calls.filter(x => x.path === 'investigate').at(-1).body, {session: flipSource, remove_call_update: true});
  assert.equal(element('save-investigation').disabled, false);
  element('save-investigation').listeners.click();
  assert.equal(element('save-dialog').open, true);
  element('scenario-name').value = receipt.name;
  await element('save-form').listeners.submit({preventDefault() {}});
  assert.deepEqual(calls.filter(x => x.path === 'receipts').at(-1).body, {
    name: receipt.name, kind: 'investigate', request: receipt.request,
  });

  await element('source').listeners.change({target: {value: catalog.defaults.session}});
  assert(element('investigation-entry').hidden);
  assert(element('flip-investigation').hidden);
  const raw = JSON.stringify(receipt);
  await element('receipt-file').listeners.change({target: {files: [{size: raw.length, text: async () => raw}], value: 'receipt.json'}});
  assert.match(element('import-status').textContent, /verified and reopened/i);
  assert.equal(element('source').value, flipSource);
  assert.equal(element('remove-call-update').checked, true);
  assertWalls(5925, 5950, 5925);
})().catch(error => {console.error(error); process.exitCode = 1;});
"""
