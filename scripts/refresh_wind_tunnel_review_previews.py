"""Capture the saved-flip and blind-review documentation images with synthetic ES data."""

from __future__ import annotations

import argparse
import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from itertools import count
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import uuid

from refresh_previews import ROOT, clean_environment, sha256, source_command


REVIEW_IMAGES = (
    "wind-tunnel-saved-flip.png",
    "wind-tunnel-blind-session-gate.png",
    "wind-tunnel-blind-session-comparison.png",
)
SAVED_FLIP_STEPS = """
async page => {
  const width = 1440;
  await page.setViewportSize({width, height: 1070});
  await page.getByRole('button', {name: 'Find net-GEX flips'}).click();
  await page.locator('#saved-flip-markers button').first().click();
  await page.getByRole('heading', {name: 'Contract contributions'}).waitFor();
  await page.getByRole('checkbox', {name: 'Remove driving update'}).check();
  await page.getByRole('heading', {name: 'After · update removed'}).waitFor();
  if (await page.locator('#investigation-contract-rows tr').count() < 1) {
    throw new Error('Contract drivers are unavailable.');
  }
  const table = page.locator('#flip-investigation .table-scroll');
  if (await table.evaluate(el => el.scrollWidth > el.clientWidth)) {
    throw new Error('The contract contribution table does not fit at the capture width.');
  }
  await page.evaluate(() => window.scrollTo(0, 0));
  const panel = await page.locator('#flip-investigation').boundingBox();
  await page.setViewportSize({width, height: Math.ceil(panel.y + panel.height + 19)});
  await page.screenshot({path: 'wind-tunnel-saved-flip.png', animations: 'disabled'});
}
"""
BLIND_STEPS = """
async page => {
  const width = 1280;
  await page.setViewportSize({width, height: 1220});
  await page.getByRole('button', {name: 'Compare saved sessions'}).click();
  const left = page.getByRole('article', {name: 'Session A (ES) review'});
  const right = page.getByRole('article', {name: 'Session B (ES) review'});
  async function capture(path) {
    await page.evaluate(() => window.scrollTo(0, 0));
    const bottom = Math.max(...(await Promise.all([left.boundingBox(), right.boundingBox()])).map(
      box => box.y + box.height));
    await page.setViewportSize({width, height: Math.ceil(bottom + 19)});
    await page.screenshot({path, animations: 'disabled'});
  }
  await left.getByRole('heading', {name: 'Starting flip'}).waitFor();
  await right.getByRole('heading', {name: 'Starting flip'}).waitFor();
  const textarea = pane => pane.getByRole('textbox', {name: 'Your read', exact: true});
  const reveal = pane => pane.getByRole('button', {name: 'Commit read and reveal'});
  const outcome = pane => pane.getByRole('heading', {name: '30-minute outcome'});
  await textarea(left).fill('The call update explains the flip. I expect the positive sign to hold for 30 minutes.');
  await textarea(right).fill('The call update explains the flip. I expect it to reverse if put exposure rebuilds.');
  if (await outcome(left).isVisible() || await outcome(right).isVisible()) {
    throw new Error('An outcome was visible before commitment.');
  }
  await reveal(left).click();
  await outcome(left).waitFor();
  await page.waitForFunction(() => document.getElementById('blind-price-plot-left').data?.[0]?.x.length === 16);
  if (await outcome(right).isVisible()) throw new Error('Both sides revealed from one commit.');
  await capture('wind-tunnel-blind-session-gate.png');

  await reveal(right).click();
  await outcome(right).waitFor();
  await page.waitForFunction(() => document.getElementById('blind-price-plot-right').data?.[0]?.x.length === 16);
  if (await left.locator('#blind-later-sign-left').textContent() !== 'Positive'
      || await right.locator('#blind-later-sign-right').textContent() !== 'Negative') {
    throw new Error('The deterministic synthetic outcomes changed.');
  }
  await page.getByRole('button', {name: 'Save comparison'}).waitFor();
  await capture('wind-tunnel-blind-session-comparison.png');
}
"""


async def create_capture(path: Path, start: datetime, strike: int, *, reverses: bool) -> None:
    from gex_terminal.session_capture import CapturedSessionWriter

    offsets = (
        (-.25, -.5, .25, 1, .75, 0, -.75, -.5, -1.5, -1.25, -2, -2.5, -2.25, -2.75, -3.25)
        if reverses else
        (.25, .5, 1, .75, .25, 1.25, 1.75, 2, 2.75, 2.25, 2.5, 3.25, 3, 3.5, 4)
    )
    received = count()
    ticks = count()
    expiry = start.replace(hour=20) + timedelta(days=1)
    writer = CapturedSessionWriter(
        path,
        source={"provider": "replay", "mode": "replay", "symbol": "ES", "synthetic": True},
        model_inputs={"days_to_expiry": .01, "risk_free_rate": .045, "contract_multiplier": 50, "expiry_filter": "all"},
        label=f"Synthetic ES session {start:%Y-%m-%d}",
        clock=lambda: start + timedelta(seconds=next(received)),
        monotonic_ns=lambda: next(ticks) * 1_000_000_000,
    )
    base = {"schema_version": 2, "provider": "synthetic", "symbol": "ES"}
    underlying = {**base, "type": "underlying_tick"}
    option = {**base, "type": "options_volume_tick", "strike": strike, "iv": .2, "iv_source": "provider",
              "expiry": expiry.date().isoformat(), "expiry_timestamp": expiry.isoformat(),
              "instrument_class": "futures_option", "volume_semantics": "cumulative",
              "position_source": "open_interest", "contract_multiplier": 50}
    put = {**option, "option_type": "P", "contract_id": f"put-{strike}", "volume": 10, "sequence": 1}
    call = {**option, "option_type": "C", "contract_id": f"call-{strike}", "volume": 40, "sequence": 2}
    cutoff = start + timedelta(seconds=2)
    horizon = cutoff + timedelta(minutes=30)
    await writer.start()
    await writer.append({**underlying, "price": float(strike), "event_time": start.isoformat()})
    await writer.append({**put, "event_time": (start + timedelta(seconds=1)).isoformat()})
    await writer.append({**call, "event_time": cutoff.isoformat()})
    for index, offset in enumerate(offsets, start=1):
        if index == len(offsets):
            await writer.append({**put, "volume": 50 if reverses else 20, "sequence": 3,
                                 "event_time": horizon.isoformat()})
        at = cutoff + timedelta(minutes=2 * index)
        await writer.append({**underlying, "price": strike + offset, "event_time": at.isoformat()})
    await writer.append({**underlying, "price": strike + 8, "event_time": (horizon + timedelta(minutes=10)).isoformat()})
    await writer.finalize()


async def browser(cli: str, session: str, directory: Path, *args: str) -> None:
    # The browser still needs its installed local cache. Credentials and ambient app
    # settings stay out of both child environments.
    environment = clean_environment(os.environ)
    environment.update({key: os.environ[key] for key in ("HOME", "PLAYWRIGHT_BROWSERS_PATH", "XDG_CACHE_HOME")
                        if key in os.environ})
    process = await asyncio.create_subprocess_exec(
        cli, session, *args, cwd=directory, env=environment,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
    )
    try:
        logs, _ = await asyncio.wait_for(process.communicate(), 60)
    except TimeoutError:
        process.kill()
        await process.wait()
        raise
    if process.returncode:
        # Playwright diagnostics can repeat the full capability-bearing URL.
        message = re.sub(r"https?://\S+", "[local URL]", logs.decode(errors="replace"))
        raise RuntimeError(f"Playwright {args[0]} failed: {message}")


@asynccontextmanager
async def wind_tunnel(directory: Path, workspace: Path, *arguments: str) -> AsyncIterator[str]:
    process = await asyncio.create_subprocess_exec(
        *source_command(ROOT, ["wind-tunnel", "serve", "--no-browser", "--port", "0",
                               "--workspace", str(workspace), *arguments]),
        cwd=directory, env=clean_environment(os.environ), stdout=asyncio.subprocess.PIPE,
    )
    try:
        async with asyncio.timeout(50):
            async for line in process.stdout:
                launch = line.decode().strip()
                if launch.startswith("http://127.0.0.1:"):
                    break
            else:
                raise RuntimeError("Wind Tunnel stopped before opening its local review.")
        yield launch
    finally:
        if process.returncode is None:
            process.send_signal(signal.SIGINT)
            await asyncio.wait_for(process.wait(), 10)


async def refresh(output: Path, cli: str) -> None:
    sys.path.insert(0, str(ROOT))
    output.mkdir(parents=True, exist_ok=False)
    start = datetime(2026, 10, 18, 15, 30, tzinfo=timezone.utc)
    sources = (
        ("session-a.gex-session.jsonl", start, 5000, False),
        ("session-b.gex-session.jsonl", start + timedelta(days=1), 5025, True),
    )
    with tempfile.TemporaryDirectory(prefix="gex-review-previews-") as temporary:
        directory = Path(temporary)
        captures = []
        for name, timestamp, strike, reverses in sources:
            capture = directory / name
            await create_capture(capture, timestamp, strike, reverses=reverses)
            captures.append(capture)
        source_hashes = {capture.name: sha256(capture) for capture in captures}
        first, second = (str(capture) for capture in captures)
        for name, steps, flags in (
            ("saved-flip", SAVED_FLIP_STEPS, ("--saved-es-capture", first)),
            ("blind-comparison", BLIND_STEPS,
             ("--blind-review", "--saved-es-capture", first, "--saved-es-capture", second)),
        ):
            recipe = directory / f"{name}.js"
            recipe.write_text(steps, encoding="utf-8")
            session = f"-s=gex-preview-{uuid.uuid4().hex[:10]}"
            async with wind_tunnel(directory, directory / name, *flags) as launch:
                try:
                    await browser(cli, session, directory, "open", launch, "--browser=chromium")
                    await browser(cli, session, directory, "run-code", "--filename", str(recipe))
                finally:
                    await browser(cli, session, directory, "close")
        for name in REVIEW_IMAGES:
            shutil.copyfile(directory / name, output / name)

    metadata = {
        "synthetic_capture_sha256": source_hashes,
        "images": {name: sha256(output / name) for name in REVIEW_IMAGES},
    }
    (output / "review-preview-capture.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")


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
