"""Capture Blind Replay Study documentation images with synthetic ES sessions."""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import shutil
import sys
import tempfile
import uuid

from refresh_previews import ROOT, sha256
from refresh_wind_tunnel_review_previews import browser, create_capture, wind_tunnel


BLIND_IMAGE = "wind-tunnel-study-blind.png"
COMPARISON_IMAGE = "wind-tunnel-study-comparison.png"
BLIND_STEPS = """
async page => {
  await page.setViewportSize({width: 1440, height: 1250});
  await page.getByRole('heading', {name: 'Study cases', exact: true}).waitFor();
  await page.getByRole('radio', {name: 'Sign holds'}).check();
  const reasoning = page.getByLabel('Reasoning (optional)');
  await reasoning.fill('The call update drove this flip. I expect the positive sign to hold.');
  await page.getByText('Recorded · Holds', {exact: true}).waitFor();
  if (!await page.getByRole('button', {name: 'Lock calls and reveal'}).isDisabled()
      || await page.locator('.study-results-heading').isVisible()
      || await page.locator('.study-result-cases tbody tr').count()) {
    throw new Error('An incomplete synthetic study must stay blind.');
  }
  await reasoning.blur();
  await page.evaluate(() => window.scrollTo(0, 0));
  const pane = await page.locator('.study-pane').boundingBox();
  await page.setViewportSize({width: 1440, height: Math.ceil(pane.y + pane.height + 22)});
  await page.screenshot({path: 'wind-tunnel-study-blind.png', animations: 'disabled'});
}
"""
COMPARISON_STEPS = """
async page => {
  const width = 1440;
  await page.setViewportSize({width, height: 1450});
  const a = page.getByRole('article', {name: 'Study A · ES', exact: true});
  const b = page.getByRole('article', {name: 'Study B · ES', exact: true});
  const submit = pane => pane.getByRole('button', {name: 'Lock calls and reveal', exact: true});
  const results = pane => pane.getByRole('heading', {name: 'Study results', exact: true});
  await a.getByRole('heading', {name: 'Study cases', exact: true}).waitFor();
  await b.getByRole('heading', {name: 'Study cases', exact: true}).waitFor();

  async function call(pane, first, second, note) {
    await pane.getByRole('radio', {name: first, exact: true}).check();
    await pane.getByLabel('Reasoning (optional)').fill(note);
    await pane.getByRole('button', {name: 'Next unanswered case', exact: true}).click();
    await pane.getByRole('radio', {name: second, exact: true}).check();
  }
  await call(a, 'Sign holds', 'Sign changes', 'I expect the positive sign to hold because call volume led the flip.');
  await call(b, 'Sign changes', 'Sign holds', 'I expect a reversal if put exposure catches up.');
  await submit(a).click();
  await results(a).waitFor();
  if (await results(b).isVisible() || await b.locator('.study-result-cases tbody tr').count()) {
    throw new Error('Revealing Study A must leave Study B blind.');
  }
  await submit(b).click();
  await results(b).waitFor();
  const save = page.getByRole('button', {name: 'Save comparison', exact: true});
  await save.waitFor();
  if (!await save.isEnabled()) throw new Error('The paired receipt is unavailable.');

  for (const [pane, expected] of [[a, ['50%', '0%']], [b, ['50%', '100%']]]) {
    const scores = await pane.locator('.study-score strong').allTextContents();
    if (JSON.stringify(scores) !== JSON.stringify(expected)) throw new Error('Unexpected synthetic scores.');
    await pane.getByRole('button', {name: 'Inspect miss · Saved ES case 1', exact: true}).click();
    await pane.getByRole('heading', {name: 'Without driving update', exact: true}).waitFor();
    const contracts = pane.locator('.study-drilldown details.blind-contracts');
    if (await contracts.locator('tbody tr').count() < 1) throw new Error('Contract drivers are unavailable.');
    await contracts.locator('summary').click();
    const plot = pane.getByRole('img', {name: /Observed ES futures prices/});
    const plotId = await plot.getAttribute('id');
    await page.waitForFunction(id => document.getElementById(id).data?.[0]?.x.length === 16, plotId);
  }

  await b.getByRole('heading', {name: 'Study B · Saved ES case 1 · Miss', exact: true}).blur();
  await page.mouse.move(24, 24);
  await page.evaluate(() => window.scrollTo(0, 0));
  const boxes = await Promise.all([a.boundingBox(), b.boundingBox()]);
  const bottom = Math.max(...boxes.map(box => box.y + box.height));
  await page.setViewportSize({width, height: Math.ceil(bottom + 22)});
  await page.screenshot({path: 'wind-tunnel-study-comparison.png', animations: 'disabled'});
}
"""


async def take_preview(cli: str, directory: Path, name: str, steps: str, *flags: str) -> None:
    recipe = directory / f"{name}.js"
    recipe.write_text(steps, encoding="utf-8")
    session = f"-s=gex-study-preview-{uuid.uuid4().hex[:10]}"
    async with wind_tunnel(directory, directory / name, "--blind-study", *flags) as launch:
        await browser(cli, session, directory, "open", launch, "--browser=chromium")
        try:
            await browser(cli, session, directory, "run-code", "--filename", str(recipe))
        finally:
            await browser(cli, session, directory, "close")


async def refresh(output: Path, cli: str) -> None:
    sys.path.insert(0, str(ROOT))
    output.mkdir(parents=True, exist_ok=False)
    start = datetime(2026, 10, 18, 15, 30, tzinfo=timezone.utc)
    with tempfile.TemporaryDirectory(prefix="gex-study-previews-") as temporary:
        directory = Path(temporary)
        captures = []
        for index in range(4):
            side = "a" if index < 2 else "b"
            capture = directory / f"study-{side}-{index % 2 + 1}.gex-session.jsonl"
            await create_capture(capture, start + timedelta(days=index), 5000 + 25 * index, reverses=side == "a")
            captures.append(capture)
        await take_preview(cli, directory, "blind", BLIND_STEPS)
        await take_preview(cli, directory, "comparison", COMPARISON_STEPS,
                           "--study-a-capture", str(captures[0]), "--study-a-capture", str(captures[1]),
                           "--study-b-capture", str(captures[2]), "--study-b-capture", str(captures[3]))
        for name in (BLIND_IMAGE, COMPARISON_IMAGE):
            shutil.copyfile(directory / name, output / name)
        metadata = {"synthetic_saved_capture_sha256": {capture.name: sha256(capture) for capture in captures},
                    "images": {name: sha256(output / name) for name in (BLIND_IMAGE, COMPARISON_IMAGE)}}
    (output / "study-preview-capture.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path, help="New directory for screenshots and the local hash manifest.")
    parser.add_argument("--playwright-cli", default="playwright-cli", help="Installed Playwright CLI or wrapper path.")
    args = parser.parse_args()
    cli = shutil.which(args.playwright_cli)
    if cli is None:
        parser.error("Install playwright-cli and its Chromium browser, or specify a wrapper path.")
    asyncio.run(refresh(args.output.absolute(), cli))


if __name__ == "__main__":
    main()
