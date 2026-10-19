import asyncio
import html
import importlib
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import tomllib
import unicodedata
import unittest
from argparse import Namespace
from contextlib import redirect_stdout
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import unquote, urlsplit

import gex_terminal
from gex_terminal.capture_governance import (
    CAPTURE_POLICY_SCHEMA,
    capture_policy_identity,
    load_capture_policy,
)
from gex_terminal.config import GexConfig
from gex_terminal.cli import inject_provider_command
from gex_terminal.demo_lab import build_demo_lab
from gex_terminal.package_data import provider_fixture_path
from gex_terminal.provider_fixture_lab import (
    build_provider_fixture_lab_report,
    bundled_provider_fixture_cases,
)
from gex_terminal.provider_injector import inject_provider_fixture
from gex_terminal.replay_catalog import (
    bundled_replay_sessions,
    replay_session_path,
)
from gex_terminal.replay_lab import build_replay_lab_report
from gex_terminal.research_journal import (
    add_journal_entry,
    build_journal_report,
)


PROJECT_ROOT = Path(__file__).resolve().parent.parent
PACKAGE_ROOT = Path(gex_terminal.__file__).resolve().parent


def _pyproject() -> dict:
    with (PROJECT_ROOT / "pyproject.toml").open("rb") as pyproject_file:
        return tomllib.load(pyproject_file)


def _config() -> GexConfig:
    return GexConfig(
        symbol="ES",
        symbols=("ES", "NQ", "SPX", "QQQ"),
        data_mode="demo",
        data_provider="tradovate",
        contract_multiplier=50,
        risk_free_rate=0.045,
        days_to_expiry=0.01,
        refresh_interval_seconds=1.0,
        stale_after_seconds=10.0,
        replay_path=str(replay_session_path("demo")),
        replay_delay_seconds=0.0,
        tradovate_environment="demo",
    )


@contextmanager
def _working_directory(path: Path):
    original = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(original)


class ReleaseMetadataContractTests(unittest.TestCase):
    def test_project_and_module_versions_agree(self):
        project_version = _pyproject()["project"]["version"]

        self.assertEqual(gex_terminal.__version__, project_version)
        self.assertRegex(project_version, r"^\d+\.\d+\.\d+(?:[a-zA-Z0-9.-]+)?$")

    def test_console_entrypoint_and_python_requirement_are_release_contracts(self):
        project = _pyproject()["project"]
        entrypoint = project["scripts"]["gex-terminal"]

        self.assertEqual(project["requires-python"], ">=3.11")
        self.assertEqual(entrypoint, "gex_terminal.cli:main_sync")

        module_name, attribute_name = entrypoint.split(":", maxsplit=1)
        entrypoint_callable = getattr(importlib.import_module(module_name), attribute_name)
        self.assertTrue(callable(entrypoint_callable))

    def test_package_data_declares_bundled_runtime_resources(self):
        package_data = _pyproject()["tool"]["setuptools"]["package-data"][
            "gex_terminal"
        ]

        self.assertTrue(
            any(str(pattern).startswith("data/replays/") for pattern in package_data),
            package_data,
        )
        self.assertTrue(
            any(
                str(pattern).startswith("data/provider_fixtures/")
                for pattern in package_data
            ),
            package_data,
        )


class BundledResourceContractTests(unittest.TestCase):
    def test_sanitized_capture_policy_example_is_packaged_and_valid(self):
        policy_path = provider_fixture_path("capture_policy_example.json")
        policy = load_capture_policy(policy_path)

        self.assertTrue(policy_path.is_absolute(), policy_path)
        self.assertTrue(policy_path.is_relative_to(PACKAGE_ROOT), policy_path)
        self.assertEqual(policy["schema"], CAPTURE_POLICY_SCHEMA)
        self.assertEqual(policy["research_use"]["status"], "prohibited")
        self.assertFalse(policy["rights"]["redistributable"])
        self.assertEqual(len(capture_policy_identity(policy)["sha256"]), 64)

        serialized = json.dumps(policy).casefold()
        for sensitive_name in (
            "api_key",
            "account_id",
            "authorization",
            "credential",
            "secret",
            "subscription_id",
        ):
            self.assertNotIn(sensitive_name, serialized)

    def test_fresh_process_loads_dotenv_from_arbitrary_working_directory(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            (temp_path / ".env").write_text(
                "GEX_SYMBOL=NQ\nGEX_DATA_MODE=replay\n",
                encoding="utf-8",
            )
            environment = os.environ.copy()
            environment.pop("GEX_SYMBOL", None)
            environment.pop("GEX_DATA_MODE", None)
            existing_pythonpath = environment.get("PYTHONPATH")
            environment["PYTHONPATH"] = os.pathsep.join(
                part
                for part in (str(PROJECT_ROOT), existing_pythonpath)
                if part
            )
            completed = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    (
                        "import json; "
                        "from gex_terminal.config import GexConfig; "
                        "config = GexConfig.from_env(); "
                        "print(json.dumps({'symbol': config.symbol, "
                        "'data_mode': config.data_mode}))"
                    ),
                ],
                cwd=temp_path,
                env=environment,
                check=True,
                capture_output=True,
                text=True,
            )

        self.assertEqual(
            json.loads(completed.stdout),
            {"symbol": "NQ", "data_mode": "replay"},
        )

    def test_bundled_replays_resolve_from_an_arbitrary_working_directory(self):
        sessions = bundled_replay_sessions()

        with tempfile.TemporaryDirectory() as temp_dir:
            with _working_directory(Path(temp_dir)):
                paths = [replay_session_path(session.name) for session in sessions]

        self.assertTrue(paths)
        for path in paths:
            self.assertTrue(path.is_absolute(), path)
            self.assertTrue(path.is_relative_to(PACKAGE_ROOT), path)
            self.assertTrue(path.is_file(), path)
            self.assertGreater(path.stat().st_size, 0, path)

    def test_bundled_provider_fixtures_run_from_an_arbitrary_working_directory(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with _working_directory(Path(temp_dir)):
                report = asyncio.run(build_provider_fixture_lab_report(_config()))

        self.assertEqual(report["scorecard"]["failed"], 0, report["cases"])
        self.assertEqual(
            report["scorecard"]["total"], len(bundled_provider_fixture_cases())
        )
        for case in report["cases"]:
            summary = case["summary"]
            self.assertTrue(summary["ok"], summary)
            self.assertGreater(summary["normalized_messages"], 0, summary)

    def test_generated_bundled_fixture_command_resolves_from_arbitrary_cwd(self):
        args = Namespace(
            command_path="bundled:yfinance-etf-options",
            provider=None,
            fixture_format="auto",
            metadata=None,
            underlying_fixture=None,
            symbol=None,
            export=None,
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            output = io.StringIO()
            with _working_directory(Path(temp_dir)), redirect_stdout(output):
                asyncio.run(inject_provider_command(_config(), args))

        self.assertIn("yfinance", output.getvalue())
        self.assertIn("SPY", output.getvalue())
        self.assertIn(
            "gex_terminal/data/provider_fixtures/yfinance_option_chain_records.json",
            output.getvalue(),
        )
        self.assertNotIn(str(PACKAGE_ROOT), output.getvalue())

    def test_bundled_replay_reports_serialize_stable_sources(self):
        report = asyncio.run(
            build_replay_lab_report(_config(), session_names=("gap-fade",))
        )
        serialized = json.dumps(report)

        self.assertEqual(report["sessions"][0]["path"], "bundled:gap-fade")
        self.assertEqual(
            report["sessions"][0]["snapshot"]["replay_session"]["path"],
            "bundled:gap-fade",
        )
        self.assertNotIn(str(PROJECT_ROOT), serialized)
        self.assertNotIn(str(PACKAGE_ROOT), serialized)
        self.assertNotIn("site-packages", serialized)

    def test_demo_lab_artifacts_do_not_serialize_host_paths(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir) / "portable-demo"
            manifest = asyncio.run(
                build_demo_lab(
                    _config(),
                    output_dir,
                    replay_session_name="gap-fade",
                    screenshot_width=80,
                    screenshot_height=24,
                )
            )
            serialized_outputs = "\n".join(
                path.read_text(encoding="utf-8")
                for path in output_dir.rglob("*")
                if path.is_file()
            )

        self.assertEqual(manifest["replay_session"]["path"], "bundled:gap-fade")
        self.assertIn("bundled:gap-fade", serialized_outputs)
        self.assertNotIn(str(PROJECT_ROOT), serialized_outputs)
        self.assertNotIn(str(PACKAGE_ROOT), serialized_outputs)
        self.assertNotIn(temp_dir, serialized_outputs)
        self.assertNotIn("site-packages", serialized_outputs)

    def test_bundled_journal_reports_serialize_stable_sources(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            entry = asyncio.run(
                add_journal_entry(
                    _config(),
                    Path(temp_dir) / "journal",
                    replay_session_name="gap-fade",
                )
            )
            report = build_journal_report((entry,))
        serialized = json.dumps(report)

        self.assertEqual(entry["source"]["path"], "bundled:gap-fade")
        self.assertEqual(entry["summary"]["path"], "bundled:gap-fade")
        self.assertEqual(
            entry["snapshot"]["replay_session"]["path"], "bundled:gap-fade"
        )
        self.assertNotIn(str(PROJECT_ROOT), serialized)
        self.assertNotIn(str(PACKAGE_ROOT), serialized)
        self.assertNotIn(temp_dir, serialized)
        self.assertNotIn("site-packages", serialized)

    def test_direct_bundled_provider_injection_serializes_resource_identities(self):
        snapshot = asyncio.run(
            inject_provider_fixture(
                provider="databento",
                fixture_path=provider_fixture_path("databento_trade_records.json"),
                config=_config(),
                metadata_path=provider_fixture_path("databento_definition_records.json"),
                underlying_path=provider_fixture_path(
                    "databento_underlying_mbp1_record.json"
                ),
            )
        )
        injection = snapshot["provider_injection"]
        serialized = json.dumps(snapshot)

        self.assertEqual(injection["source_kind"], "offline_provider_fixture")
        self.assertIs(injection["network_used"], False)
        self.assertEqual(snapshot["feed_quality"]["status"], "REPLAY")
        self.assertEqual(snapshot["feed_quality"]["health"], "degraded")
        self.assertEqual(
            injection["fixture"],
            "gex_terminal/data/provider_fixtures/databento_trade_records.json",
        )
        self.assertEqual(
            injection["metadata"],
            "gex_terminal/data/provider_fixtures/databento_definition_records.json",
        )
        self.assertEqual(
            injection["underlying_fixture"],
            "gex_terminal/data/provider_fixtures/databento_underlying_mbp1_record.json",
        )
        self.assertNotIn(str(PROJECT_ROOT), serialized)
        self.assertNotIn(str(PACKAGE_ROOT), serialized)
        self.assertNotIn("site-packages", serialized)

    def test_bundled_resource_names_are_unique(self):
        replay_names = [session.name for session in bundled_replay_sessions()]
        fixture_names = [case.name for case in bundled_provider_fixture_cases()]

        self.assertEqual(len(replay_names), len(set(replay_names)))
        self.assertEqual(len(fixture_names), len(set(fixture_names)))
        self.assertEqual(
            len(replay_names), len({name.casefold() for name in replay_names})
        )
        self.assertEqual(
            len(fixture_names), len({name.casefold() for name in fixture_names})
        )


class DocumentationLinkContractTests(unittest.TestCase):
    # This intentionally small parser covers the documentation conventions here:
    # inline links/images (including titles and angle-wrapped paths), ATX and
    # single-line Setext headings, inline formatting, and fenced code. It is not
    # a full Markdown renderer: reference links, raw HTML anchors, and headings
    # nested in lists/quotes are outside this contract.
    _MARKDOWN_LINK = re.compile(
        r'''!?\[([^\]\n]*)\]\(\s*'''
        r'''(<[^>\n]*>|(?:\\.|[^()\s]|\([^()\n]*\))+)'''
        r'''(?:\s+(?:"[^"\n]*"|'[^'\n]*'))?\s*\)'''
    )
    _INLINE_CODE = re.compile(r"(?<!`)(`+)(?!`)(.*?)\1(?!`)")

    @staticmethod
    def _without_fenced_code(markdown: str) -> str:
        lines = []
        fence = None
        for line in markdown.splitlines():
            marker = re.match(r"^ {0,3}(`{3,}|~{3,})(.*)$", line)
            if fence is not None:
                if (
                    marker
                    and marker[1][0] == fence[0]
                    and len(marker[1]) >= len(fence)
                    and not marker[2].strip()
                ):
                    fence = None
                lines.append("")
            elif marker and not (marker[1][0] == "`" and "`" in marker[2]):
                fence = marker[1]
                lines.append("")
            else:
                lines.append(line)
        return "\n".join(lines)

    @classmethod
    def _heading_slug(cls, heading: str) -> str:
        def plain_text(text: str) -> str:
            text = cls._MARKDOWN_LINK.sub(lambda match: match[1], text)
            text = re.sub(r"<[^>]*>", "", text)
            text = re.sub(r"(\*{1,3}|~~)(.*?)\1", r"\2", text)
            text = re.sub(r"(?<!\w)(_{1,3})(?!_)(.*?)\1(?!\w)", r"\2", text)
            return re.sub(r"\\([!\"#$%&'()*+,\-./:;<=>?@\[\]\\^_`{|}~])", r"\1", text)

        # Protect code before rendering links/entities/formatting. Placeholders
        # also let a real link whose label contains code retain its whole label.
        code_spans = []

        def protect_code(match: re.Match) -> str:
            code_spans.append(match[2])
            return f"\x00{len(code_spans) - 1}\x00"

        protected = cls._INLINE_CODE.sub(protect_code, heading)
        text = html.unescape(plain_text(protected))
        text = re.sub(
            r"\x00(\d+)\x00", lambda match: code_spans[int(match[1])], text
        ).strip().lower()
        return "".join(
            "-" if character == " " else character
            for character in text
            if character in " -_"
            or unicodedata.category(character)[0] in "LNM"
        )

    @classmethod
    def _heading_ids(cls, markdown: str) -> set[str]:
        headings = set()
        lines = cls._without_fenced_code(markdown).splitlines()
        for index, line in enumerate(lines):
            atx = re.match(r"^ {0,3}#{1,6}(?:[ \t]+(.*?)|[ \t]*)$", line)
            if atx:
                heading = re.sub(r"[ \t]+#+[ \t]*$", "", atx[1] or "")
            elif (
                index > 0
                and re.fullmatch(r" {0,3}(?:=+|-+)[ \t]*", line)
                and lines[index - 1].strip()
                and not re.match(r"^ {0,3}(?:#|[-*+>] )", lines[index - 1])
            ):
                heading = lines[index - 1].strip()
            else:
                continue
            base = cls._heading_slug(heading)
            anchor = base
            suffix = 0
            while anchor in headings:
                suffix += 1
                anchor = f"{base}-{suffix}"
            headings.add(anchor)
        return headings

    @classmethod
    def _broken_links(cls, documents: list[Path], root: Path) -> list[str]:
        missing = []
        headings_by_path = {}
        for document in documents:
            prose = cls._without_fenced_code(document.read_text(encoding="utf-8"))
            prose = cls._INLINE_CODE.sub("", prose)
            for match in cls._MARKDOWN_LINK.finditer(prose):
                target = match[2].removeprefix("<").removesuffix(">")
                parsed = urlsplit(target)
                if parsed.scheme or parsed.netloc:
                    continue
                path = unquote(parsed.path)
                if path.startswith("/"):
                    resolved = (root / path.lstrip("/")).resolve()
                else:
                    resolved = (document.parent / path).resolve() if path else document.resolve()
                reason = None
                if not resolved.exists():
                    reason = "missing file"
                elif parsed.fragment and resolved.suffix.lower() == ".md":
                    if resolved not in headings_by_path:
                        headings_by_path[resolved] = cls._heading_ids(
                            resolved.read_text(encoding="utf-8")
                        )
                    if unquote(parsed.fragment) not in headings_by_path[resolved]:
                        reason = "missing heading"
                if reason:
                    missing.append(f"{document.relative_to(root)} -> {target} ({reason})")
        return missing

    def test_key_relative_markdown_links_resolve(self):
        documents = [
            *sorted(PROJECT_ROOT.glob("*.md")),
            *sorted((PROJECT_ROOT / "docs").rglob("*.md")),
            *sorted((PROJECT_ROOT / "assets").rglob("*.md")),
        ]
        missing = self._broken_links(documents, PROJECT_ROOT)
        self.assertEqual(missing, [], "Broken local Markdown links:\n" + "\n".join(missing))

    def test_heading_ids_normalize_common_markdown_and_resolve_collisions(self):
        markdown = """# Install & **Run**: `command_name`!
## [Café](https://example.com) — _été_ ###
## <em>Details</em> &amp; More
## `__init__` and snake_case
## Read [`payload`](input.json)
## Repeat
## Repeat-1
## Repeat
## Repeat
## Repeat-1
Setext Title
============
## Two  Spaces
"""
        self.assertEqual(
            self._heading_ids(markdown),
            {
                "install--run-command_name", "café--été", "details--more",
                "__init__-and-snake_case", "read-payload", "repeat", "repeat-1", "repeat-2",
                "repeat-3", "repeat-1-1", "setext-title", "two--spaces",
            },
        )

    def test_link_syntax_inside_heading_code_stays_literal(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            guide = root / "guide.md"
            guide.write_text(
                "# Read `[payload](input.json)`\n"
                "[rendered heading](#read-payloadinputjson)\n"
                "[incorrectly stripped label](#read-payload)\n"
                "# Literal `&amp;`\n"
                "[literal entity](#literal-amp)\n"
                "[incorrectly decoded entity](#literal-)\n",
                encoding="utf-8",
            )
            self.assertEqual(
                self._broken_links([guide], root),
                [
                    "guide.md -> #read-payload (missing heading)",
                    "guide.md -> #literal- (missing heading)",
                ],
            )

    def test_fenced_examples_do_not_create_headings_or_links(self):
        markdown = """# Real
````markdown
# Fake
[broken](missing.md)
```
## Still Fake
````
~~~markdown
## Also Fake
~~~
## Real
`[inline example](missing.md)`
"""
        self.assertEqual(self._heading_ids(markdown), {"real", "real-1"})
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            document = root / "guide.md"
            document.write_text(markdown, encoding="utf-8")
            self.assertEqual(self._broken_links([document], root), [])

    def test_links_validate_files_and_decoded_local_heading_fragments(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            guide = root / "guide.md"
            (root / "other guide.md").write_text("# Café\n## Next\n## Next\n", encoding="utf-8")
            (root / "image.svg").write_text("<svg/>", encoding="utf-8")
            guide.write_text(
                "# Here\n"
                "[same page](#here)\n"
                "[encoded](other%20guide.md#caf%C3%A9)\n"
                '[title](<other guide.md#next-1> "A guide")\n'
                "[root](/other%20guide.md#next)\n"
                "![image](image.svg#fragment)\n"
                "[external](https://example.com/missing.md#missing)\n"
                "[protocol-relative](//example.com/missing.md#missing)\n"
                "[email](mailto:example@example.com)\n",
                encoding="utf-8",
            )
            self.assertEqual(self._broken_links([guide], root), [])
            with guide.open("a", encoding="utf-8") as output:
                output.write(
                    "[bad same page](#absent)\n"
                    "[bad heading](other%20guide.md#missing)\n"
                    "[bad suffix](other%20guide.md#next-2)\n"
                    "[bad file](missing.md#here)\n"
                )
            self.assertEqual(
                self._broken_links([guide], root),
                [
                    "guide.md -> #absent (missing heading)",
                    "guide.md -> other%20guide.md#missing (missing heading)",
                    "guide.md -> other%20guide.md#next-2 (missing heading)",
                    "guide.md -> missing.md#here (missing file)",
                ],
            )


if __name__ == "__main__":
    unittest.main()
