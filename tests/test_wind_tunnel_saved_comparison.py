"""Regressions for comparing independently reconstructed saved ES and NQ flips."""

import asyncio
from contextlib import AsyncExitStack
from importlib.resources import files
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from urllib.parse import urlsplit
from unittest.mock import patch

from tests.test_wind_tunnel_assets import BROWSER_DOM_HARNESS
from tests.test_wind_tunnel_saved_investigation import (
    prepare_switch_fixtures,
    saved_flip_events,
    write_saved_flip_fixture,
)


KIND = "compare-saved-flips"
SESSION_KIND = "compare-saved-sessions"


async def comparison_fixture(directory, resources):
    from gex_terminal.wind_tunnel_saved_replay import SavedReplay
    from gex_terminal.wind_tunnel_sources import checkpoint_core

    plans = await prepare_switch_fixtures(directory)
    es, nq = plans["ES"], plans["NQ"]
    core = checkpoint_core(Path(es["checkpoint_path"]), [Path(nq["checkpoint_path"])])
    replays = {}
    for symbol, plan in plans.items():
        replay = SavedReplay(plan["capture_path"], plan["capture_sha256"], symbol=symbol)
        resources.callback(replay.close)
        replays[symbol] = replay
    request = {
        "es": {"capture_sha256": es["capture_sha256"], "sequence": 2},
        "nq": {"capture_sha256": nq["capture_sha256"], "sequence": 6},
    }
    return plans, core, replays, request


async def same_market_fixture(directory, resources, symbol):
    from gex_terminal.saved_workspace import prepare_saved_workspace
    from gex_terminal.wind_tunnel_saved_replay import SavedReplay
    from gex_terminal.wind_tunnel_sources import checkpoint_core

    first_day = saved_flip_events(symbol)
    first_tick, put, call = first_day[:3]
    strike = call["strike"] + 25
    second_day = [
        {**first_tick, "price": float(strike), "event_time": "2026-10-19T15:30:00Z"},
        {**call, "strike": strike, "contract_id": f"call-{strike}", "volume": 10, "sequence": 1,
         "expiry": "2026-10-20", "expiry_timestamp": "2026-10-20T20:00:00Z",
         "event_time": "2026-10-19T15:30:01Z"},
        {**put, "strike": strike, "contract_id": f"put-{strike}", "volume": 40, "sequence": 2,
         "expiry": "2026-10-20", "expiry_timestamp": "2026-10-20T20:00:00Z",
         "event_time": "2026-10-19T15:30:02Z"},
    ]
    plans, replays = [], []
    for index, events in enumerate((first_day, second_day)):
        source = directory / f"source-{index}"
        source.mkdir()
        path, checksum = await write_saved_flip_fixture(source, events, symbol=symbol)
        plan = await asyncio.to_thread(prepare_saved_workspace, path, symbol, directory / f"capture-{index}")
        if plan["capture_sha256"] != checksum:
            raise AssertionError("Preparing a same-market fixture must preserve its checksum")
        replay = SavedReplay(plan["capture_path"], checksum, symbol=symbol)
        resources.callback(replay.close)
        plans.append(plan)
        replays.append(replay)
    core = checkpoint_core(Path(plans[0]["checkpoint_path"]), [Path(plans[1]["checkpoint_path"])])
    return plans, core, replays


def same_market_pair(symbol, plans, replays):
    request = {side: {"symbol": symbol, "capture_sha256": plan["capture_sha256"], "sequence": 2}
               for side, plan in zip(("left", "right"), plans)}
    return request, dict(zip(("left", "right"), replays))


class SavedFlipComparisonTests(unittest.IsolatedAsyncioTestCase):
    def assert_market_side(self, side, *, market, selection, contract, signs):
        self.assertEqual(side["source"]["symbol"], market)
        self.assertEqual(side["source"]["capture_sha256"], selection["capture_sha256"])
        self.assertEqual(side["event"]["sequence"], selection["sequence"])
        self.assertEqual(side["contributions"][0]["contract_id"], contract)
        self.assertEqual(side["counterfactual_status"], "available")
        self.assertEqual(side["counterfactual"]["as_of"], side["after"]["as_of"])
        self.assertEqual(tuple(side[case]["summary"]["net_sign"] for case in ("before", "after", "counterfactual")),
                         signs)
        self.assertTrue(side["request"]["remove_update"])
        self.assertTrue(math.isclose(math.fsum(row["delta_gex"] for row in side["contributions"]),
                                     side["net_gex_delta"], abs_tol=1e-6, rel_tol=1e-10))

    async def test_same_market_pairs_resolve_identical_sequences_by_capture_and_reopen_one_receipt(self):
        from aiohttp import ClientSession
        from gex_terminal import wind_tunnel_server as server

        for symbol, strike in (("ES", 5000), ("NQ", 20000)):
            with self.subTest(symbol=symbol):
                async with AsyncExitStack() as resources:
                    directory = Path(resources.enter_context(tempfile.TemporaryDirectory()))
                    plans, core, replays = await same_market_fixture(directory, resources, symbol)
                    request, _ = same_market_pair(symbol, plans, replays)
                    bindings = {plan["checkpoint_sha256"]: replay for plan, replay in zip(plans, replays)}
                    runner, launch = await server.start_server(directory / "research", port=0, core=core,
                                                               saved_replays=bindings)
                    resources.push_async_callback(runner.cleanup)
                    parsed = urlsplit(launch)
                    origin = f"{parsed.scheme}://{parsed.netloc}"
                    headers = {"X-GEX-Capability": parsed.fragment.removeprefix("cap=")}
                    client = await resources.enter_async_context(ClientSession(headers=headers))

                    async def post(operation, body, expected=200):
                        async with client.post(f"{origin}/api/{operation}", json=body) as response:
                            self.assertEqual(response.status, expected, await response.text())
                            return await response.json()

                    async with client.get(f"{origin}/api/catalog") as response:
                        self.assertEqual(response.status, 200)
                        catalog = await response.json()
                    sources = [catalog["sessions"][0], *catalog["saved_checkpoints"]]
                    self.assertEqual({source["investigation_capture"]["sha256"] for source in sources},
                                     {plan["capture_sha256"] for plan in plans})
                    timelines = await asyncio.gather(*(post("investigation-timeline", {
                        "capture_sha256": request[side]["capture_sha256"],
                    }) for side in ("left", "right")))
                    for timeline, side, sequences in zip(timelines, ("left", "right"), ([2, 5], [2])):
                        self.assertEqual(timeline["capture_sha256"], request[side]["capture_sha256"])
                        self.assertEqual([marker["sequence"] for marker in timeline["markers"]], sequences)
                    self.assertNotEqual(timelines[0]["markers"][0]["as_of"], timelines[1]["markers"][0]["as_of"])

                    result = await post(SESSION_KIND, request)
                    self.assert_market_side(result["left"], market=symbol, selection=request["left"],
                                            contract=f"call-{strike}", signs=(-1, 1, -1))
                    self.assert_market_side(result["right"], market=symbol, selection=request["right"],
                                            contract=f"put-{strike + 25}", signs=(1, -1, 1))
                    self.assertEqual(result["request"]["left"], request["left"])
                    self.assertEqual(result["request"]["right"], request["right"])
                    self.assertNotIn(str(directory), json.dumps(result))
                    reversed_result = await post(SESSION_KIND, {"left": request["right"], "right": request["left"]})
                    self.assertEqual(reversed_result["left"], result["right"])
                    self.assertEqual(reversed_result["right"], result["left"])

                    other_symbol = "ES" if symbol == "NQ" else "NQ"
                    for invalid in (
                        {**request, "right": request["left"]},
                        {**request, "right": {**request["left"], "sequence": 5}},
                        {**request, "right": {**request["right"], "capture_sha256": "0" * 64}},
                        {**request, "right": {**request["right"], "symbol": other_symbol}},
                    ):
                        await post(SESSION_KIND, invalid, expected=400)

                    receipt = await post("receipts", {"name": f"Two {symbol} sessions", "kind": SESSION_KIND,
                                                      "request": result["request"]})
                    self.assertEqual(receipt["result"], result)
                    async with client.get(f"{origin}/api/receipts") as response:
                        self.assertEqual(response.status, 200)
                        self.assertEqual([item["id"] for item in (await response.json())["receipts"]],
                                         [receipt["receipt_sha256"]])
                    async with client.get(f"{origin}/api/receipts/{receipt['receipt_sha256']}/export") as response:
                        self.assertEqual(response.status, 200, await response.text())
                        exported = await response.json()
                    self.assertEqual(exported, receipt)
                    reopened = await post("reproduce", exported)
                    self.assertEqual((reopened["status"], reopened["result"]), ("verified", result))

    async def test_direct_launch_and_fresh_reproduction_accept_repeated_market_flags(self):
        from gex_terminal import wind_tunnel_cli as cli, wind_tunnel_server as server

        class StartupObserved(Exception):
            pass

        for symbol in ("ES", "NQ"):
            with self.subTest(symbol=symbol):
                async with AsyncExitStack() as resources:
                    directory = Path(resources.enter_context(tempfile.TemporaryDirectory()))
                    plans, _, replays = await same_market_fixture(directory, resources, symbol)
                    request, session_replays = same_market_pair(symbol, plans, replays)
                    receipt = await server.make_receipt("Same-market CLI pair", SESSION_KIND, request,
                                                        session_replays=session_replays)
                    receipt_path = directory / "pair.json"
                    receipt_path.write_bytes(server.canonical_bytes(receipt))
                    first, second = (plan["capture_path"] for plan in plans)
                    flag = f"--saved-{symbol.lower()}-capture"
                    flags = [flag, second, flag, first]
                    expected = {plan["capture_sha256"] for plan in plans}

                    async def inspect_startup(workspace, *, core, saved_replays, **kwargs):
                        self.assertEqual({item.capture_sha256 for item in saved_replays.values()}, expected)
                        self.assertEqual({item.symbol for item in saved_replays.values()}, {symbol})
                        self.assertEqual(len(core.catalog()["saved_checkpoints"]), 2)
                        raise StartupObserved

                    launch = cli.parser().parse_args(["serve", *flags, "--port", "0", "--no-browser"])
                    with patch.object(cli, "start_server", inspect_startup), self.assertRaises(StartupObserved):
                        await cli.run(launch)

                    repository = str(Path(__file__).resolve().parents[1])
                    environment = {**os.environ, "PYTHONPATH": os.pathsep.join(filter(None, (
                        repository, os.environ.get("PYTHONPATH"),
                    )))}

                    async def invoke(captures):
                        return await asyncio.to_thread(subprocess.run, [sys.executable, "-m",
                            "gex_terminal.wind_tunnel_cli", "reproduce", str(receipt_path), *captures],
                            cwd=directory, env=environment, capture_output=True, text=True, timeout=30)

                    result = await invoke(flags)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    reproduced = json.loads(result.stdout)
                    self.assertEqual((reproduced["status"], reproduced["result"]), ("verified", receipt["result"]))
                    for invalid in ([flag, first], [flag, first, flag, first]):
                        result = await invoke(invalid)
                        self.assertNotEqual(result.returncode, 0)
                        self.assertEqual(result.stdout, "")
                        self.assertNotIn(str(directory), result.stderr)

    async def test_http_compares_exact_market_bound_updates_and_reproduces_one_receipt(self):
        from aiohttp import ClientSession
        from gex_terminal import wind_tunnel as wind, wind_tunnel_server as server

        async with AsyncExitStack() as resources:
            directory = Path(resources.enter_context(tempfile.TemporaryDirectory()))
            plans, core, replays, request = await comparison_fixture(directory, resources)
            bindings = {plan["checkpoint_sha256"]: replays[symbol] for symbol, plan in plans.items()}
            workspace = directory / "ES-research"
            runner, launch = await server.start_server(workspace, port=0, core=core, saved_replays=bindings,
                                                       comparison_workspace=directory / "NQ-research")
            resources.push_async_callback(runner.cleanup)
            parsed = urlsplit(launch)
            origin = f"{parsed.scheme}://{parsed.netloc}"
            headers = {"X-GEX-Capability": parsed.fragment.removeprefix("cap=")}
            client = await resources.enter_async_context(ClientSession(headers=headers))

            async def post(operation, body, expected=200):
                async with client.post(f"{origin}/api/{operation}", json=body) as response:
                    self.assertEqual(response.status, expected, await response.text())
                    return await response.json()

            comparison = await post(KIND, request)
            self.assert_market_side(comparison["es"], market="ES", selection=request["es"],
                                    contract="call-5000", signs=(-1, 1, -1))
            self.assert_market_side(comparison["nq"], market="NQ", selection=request["nq"],
                                    contract="put-20000", signs=(1, -1, 1))
            self.assertEqual(comparison["request"]["operation"], KIND)
            self.assertEqual(comparison["request"]["es"], request["es"])
            self.assertEqual(comparison["request"]["nq"], request["nq"])
            self.assertNotIn(str(directory), json.dumps(comparison))

            for invalid in (
                {"es": request["es"]},
                {"es": request["nq"], "nq": request["es"]},
                {**request, "nq": {**request["nq"], "capture_sha256": "0" * 64}},
                {**request, "nq": {**request["nq"], "sequence": 4}},
                {**request, "nq": {**request["nq"], "sequence": True}},
            ):
                with self.subTest(invalid=invalid):
                    await post(KIND, invalid, expected=400)

            receipt = await post("receipts", {"name": "Paired saved flips", "kind": KIND,
                                              "request": comparison["request"]})
            self.assertEqual(receipt["result"], comparison)
            self.assertEqual(receipt["kind"], KIND)
            async with client.get(f"{origin}/api/receipts") as response:
                self.assertEqual(response.status, 200, await response.text())
                listed = (await response.json())["receipts"]
            self.assertEqual([(row["kind"], row["id"]) for row in listed], [(KIND, receipt["receipt_sha256"])])
            async with client.get(f"{origin}/api/receipts/{receipt['receipt_sha256']}/export") as response:
                self.assertEqual(response.status, 200, await response.text())
                self.assertIn("attachment", response.headers["Content-Disposition"])
                exported = await response.json()
            self.assertEqual(exported, receipt)
            reopened = await post("reproduce", exported)
            self.assertEqual(reopened["status"], "verified")
            self.assertEqual(reopened["result"], comparison)

            # A valid envelope for a changed driver must still fail replay verification.
            altered_side = {**comparison["es"], "contributions": []}
            altered_side.pop("result_sha256")
            altered_side["result_sha256"] = wind._sha(altered_side)
            altered_result = {**comparison, "es": altered_side}
            altered_result.pop("result_sha256")
            altered_result["result_sha256"] = wind._sha(altered_result)
            altered = {**receipt, "result": altered_result}
            altered.pop("receipt_sha256")
            altered["receipt_sha256"] = server.digest(altered)
            mismatch = await post("reproduce", altered)
            self.assertEqual(mismatch["status"], "mismatch")

    async def test_fresh_cli_reproduces_comparison_only_with_both_matching_captures(self):
        from gex_terminal import wind_tunnel_server as server

        async with AsyncExitStack() as resources:
            directory = Path(resources.enter_context(tempfile.TemporaryDirectory()))
            plans, _, replays, request = await comparison_fixture(directory, resources)
            receipt = await server.make_receipt("CLI pair", KIND, request, comparison_replays=replays)
            artifact = directory / "pair.json"
            artifact.write_bytes(server.canonical_bytes(receipt))
            es_path = plans["ES"]["capture_path"]
            nq_path = plans["NQ"]["capture_path"]
            repository = str(Path(__file__).resolve().parents[1])
            module_paths = [part for part in (repository, os.environ.get("PYTHONPATH")) if part]
            env = {**os.environ, "PYTHONPATH": os.pathsep.join(module_paths)}
            command = [sys.executable, "-m", "gex_terminal.wind_tunnel_cli"]

            async def invoke(action, flags, *, receipt_path=artifact):
                return await asyncio.to_thread(subprocess.run, [*command, action, str(receipt_path), *flags],
                                               cwd=directory, env=env, capture_output=True, text=True, timeout=30)

            both = ["--saved-nq-capture", nq_path, "--saved-es-capture", es_path]
            reproduced = await invoke("reproduce", both)
            self.assertEqual(reproduced.returncode, 0, reproduced.stderr)
            report = json.loads(reproduced.stdout)
            self.assertEqual(report["status"], "verified")
            self.assertEqual(report["result"], receipt["result"])
            for flags in (["--saved-es-capture", es_path],
                          ["--saved-es-capture", nq_path, "--saved-nq-capture", es_path]):
                with self.subTest(flags=flags):
                    invalid = await invoke("verify", flags)
                    self.assertNotEqual(invalid.returncode, 0)
                    self.assertEqual(invalid.stdout, "")
                    self.assertNotIn(str(directory), invalid.stderr)

            single = await server.make_receipt("One saved flip", "investigate-saved", request["es"],
                                               saved_replay=replays["ES"])
            single_path = directory / "single.json"
            single_path.write_bytes(server.canonical_bytes(single))
            rejected = await invoke("verify", both, receipt_path=single_path)
            self.assertNotEqual(rejected.returncode, 0)
            self.assertEqual(rejected.stdout, "")


class SavedFlipComparisonBrowserTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("node"), "Node.js is needed for the browser workflow harness")
    def test_side_by_side_comparison_saves_and_reopens_both_original_flips(self):
        from gex_terminal import wind_tunnel as wind, wind_tunnel_server as server

        async def make_fixture(directory, symbol):
            async with AsyncExitStack() as resources:
                if symbol:
                    plans, core, replays = await same_market_fixture(directory, resources, symbol)
                    request, sources = same_market_pair(symbol, plans, replays)
                    receipt = await server.make_receipt("Saved session comparison", SESSION_KIND, request,
                                                        session_replays=sources)
                    timelines = {plan["capture_sha256"]: await replay.timeline() for plan, replay in zip(plans, replays)}
                else:
                    plans_by_market, core, replays_by_market, request = await comparison_fixture(directory, resources)
                    receipt = await server.make_receipt("Legacy ES and NQ comparison", KIND, request,
                                                        comparison_replays=replays_by_market)
                    plans = list(plans_by_market.values())
                    timelines = {plan["capture_sha256"]: await replays_by_market[market].timeline()
                                 for market, plan in plans_by_market.items()}
                catalog = core.catalog()
                captures = {plan["checkpoint_sha256"]: plan["capture_sha256"] for plan in plans}
                catalog["sessions"][0]["investigation_capture"] = {"sha256": plans[0]["capture_sha256"]}
                for source in catalog["saved_checkpoints"]:
                    source["investigation_capture"] = {"sha256": captures[source["checkpoint_sha256"]]}
                return {"catalog": catalog, "checkpoints": wind.checkpoints(wind.DEFAULTS["session"]),
                        "timelines": timelines, "receipt": receipt, "legacy": symbol is None}

        assets = str(files("gex_terminal").joinpath("wind_tunnel_web"))
        for symbol in ("ES", "NQ", None):
            with self.subTest(symbol=symbol), tempfile.TemporaryDirectory() as directory:
                result = subprocess.run([shutil.which("node"), "-e", COMPARISON_BROWSER_HARNESS, assets],
                                        input=json.dumps(asyncio.run(make_fixture(Path(directory), symbol))),
                                        text=True, capture_output=True, timeout=15)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


COMPARISON_BROWSER_HARNESS = BROWSER_DOM_HARNESS + r"""
const {catalog, checkpoints, timelines, receipt, legacy} = JSON.parse(fs.readFileSync(0, 'utf8'));
const left = legacy ? receipt.request.es : receipt.request.left;
const right = legacy ? receipt.request.nq : receipt.request.right;
const calls = [];
let saved = legacy, mismatchedReport = true;
const createElement = document.createElement;
document.createElement = tag => Object.assign(createElement(tag), {style: {}});
global.fetch = async (url, options) => {
  assert.equal(options.headers['X-GEX-Capability'], 'local-test-capability');
  const path = url.replace('/api/', '');
  const body = options.body ? JSON.parse(options.body) : null;
  calls.push({path, body});
  const state = {status: 'available', spot: 5000, summary: {total_net_gex: 1, gamma_wall: 5000}};
  let result;
  if (path === 'catalog') result = catalog;
  else if (path.startsWith('checkpoints?session=')) result = checkpoints;
  else if (path === 'calculate') result = {request: body, baseline: state, scenario: state};
  else if (path === 'surface') result = {request: body, axes: {}, points: []};
  else if (path === 'investigation-timeline') {
    result = timelines[body.capture_sha256];
    assert(result, 'Each comparison timeline must be requested by its capture checksum');
  } else if (path === receipt.kind) {
    assert.equal(legacy, false, 'Reopening a legacy pair must use its original receipt');
    assert.deepEqual(body.left, left);
    assert.deepEqual(body.right, right);
    const side = receipt.result.right;
    result = mismatchedReport
      ? {...receipt.result, right: {...side, source: {...side.source, capture_sha256: left.capture_sha256}}}
      : receipt.result;
  } else if (path === 'receipts' && body) {
    assert.deepEqual(body, {kind: receipt.kind, request: receipt.request, name: receipt.name});
    saved = true;
    result = receipt;
  } else if (path === 'receipts') result = {receipts: saved ? [{...receipt, id: receipt.receipt_sha256}] : []};
  else if (path === `receipts/${receipt.receipt_sha256}`) result = receipt;
  else if (path === 'reproduce') {
    assert.deepEqual(body, receipt);
    result = {status: 'verified', result: receipt.result};
  } else throw new Error('Unexpected endpoint ' + path);
  return {ok: true, status: 200, json: async () => result, text: async () => JSON.stringify(result)};
};
const app = fs.readFileSync(root + '/app.js', 'utf8');
assert(app.includes('  initialize();'));
vm.runInThisContext(app.replace('  initialize();', '  globalThis.initializeBrowser = initialize;'));
const element = id => elements.get('#' + id);
const contents = node => [node.textContent, ...node.children.map(contents)].join(' ');
const settle = () => new Promise(setImmediate);
async function choose(id, value) {
  const select = element(id);
  value = String(value);
  assert(select.options.some(option => option.value === value));
  select.value = value;
  await select.listeners.change({target: select});
}
function assertComparison() {
  assert.equal(element('flip-comparison').hidden, false);
  const leftResult = legacy ? receipt.result.es : receipt.result.left;
  const rightResult = legacy ? receipt.result.nq : receipt.result.right;
  const leftRendered = contents(element('a-flip-comparison-result'));
  const rightRendered = contents(element('b-flip-comparison-result'));
  assert(leftRendered.includes(leftResult.contributions[0].contract_id));
  assert(rightRendered.includes(rightResult.contributions[0].contract_id));
  assert.match(leftRendered, /Negative.*Positive.*Negative/is);
  assert.match(rightRendered, /Positive.*Negative.*Positive/is);
}
(async () => {
  await initializeBrowser();
  if (!legacy) {
    await element('open-flip-comparison').listeners.click();
    await settle();
    await choose('compare-a-capture', left.capture_sha256);
    await choose('compare-b-capture', right.capture_sha256);
    await settle();
    assert.deepEqual(new Set(calls.filter(call => call.path === 'investigation-timeline').map(call => call.body.capture_sha256)),
                     new Set([left.capture_sha256, right.capture_sha256]));
    await choose('compare-a-flip', left.sequence);
    await choose('compare-b-flip', right.sequence);
    await element('run-flip-comparison').listeners.click();
    await settle();
    assert.match(element('flip-comparison-status').textContent, /did not match/i);
    assert(element('save-flip-comparison').disabled, 'A different capture with the same ordinal must not be saveable');
    mismatchedReport = false;
    await element('run-flip-comparison').listeners.click();
    await settle();
    assertComparison();
    element('save-flip-comparison').listeners.click();
    assert.equal(element('save-dialog').open, true);
    element('scenario-name').value = receipt.name;
    await element('save-form').listeners.submit({preventDefault() {}});
    assert(saved);
    await choose('compare-a-flip', left.sequence + 3);
    assert(element('save-flip-comparison').disabled, 'Changing either marker invalidates the previous save');
  }
  await element('open-receipts').listeners.click();
  const row = element('receipts-list').children.find(item => contents(item).includes(receipt.name));
  assert(row, 'The paired artifact belongs in Saved scenarios');
  const timelineCalls = calls.filter(call => call.path === 'investigation-timeline').length;
  await row.children[1].children[0].listeners.click();
  await settle();
  assertComparison();
  assert.equal(element('compare-a-capture').value, left.capture_sha256);
  assert.equal(element('compare-b-capture').value, right.capture_sha256);
  assert.equal(element('compare-a-flip').value, String(left.sequence));
  assert.equal(element('compare-b-flip').value, String(right.sequence));
  assert.equal(calls.filter(call => call.path === 'investigation-timeline').length, timelineCalls);
})().catch(error => {console.error(error); process.exitCode = 1;});
"""
