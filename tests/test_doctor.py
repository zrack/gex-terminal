import builtins
import importlib.util
import json
import socket
import tempfile
import tomllib
import unittest
from pathlib import Path
from unittest.mock import patch

from gex_terminal import __version__
from gex_terminal.adapters import registry
from gex_terminal.config import ConfigValidationError, GexConfig
from gex_terminal.doctor import (
    DOCTOR_SCHEMA,
    EXIT_CONFIGURATION_FAILURE,
    EXIT_OK,
    EXIT_RUNTIME_FAILURE,
    OPTIONAL_PROVIDER_SDKS,
    REQUIRED_BUNDLED_RESOURCES,
    REQUIRED_RUNTIME_MODULES,
    build_doctor_report,
    doctor_report_to_json,
    doctor_report_to_text,
    probe_hidden_editable_pth,
    probe_temporary_storage,
)


PROVIDER_CATALOG = {
    "databento": "live-uncertified",
    "ibkr": "scaffold",
    "replay": "offline-certified",
    "tradovate": "scaffold",
    "yfinance": "delayed",
}


def _config(**updates) -> GexConfig:
    values = {
        "symbol": "ES",
        "symbols": ("ES",),
        "data_mode": "demo",
        "data_provider": "tradovate",
        "contract_multiplier": 50,
        "risk_free_rate": 0.045,
        "days_to_expiry": 0.25,
        "refresh_interval_seconds": 1.0,
        "stale_after_seconds": 10.0,
        "replay_path": "private-replay-path",
        "replay_delay_seconds": 0.0,
        "tradovate_environment": "demo",
    }
    values.update(updates)
    return GexConfig(**values)


def _report(config=None, **overrides):
    arguments = {
        "config": config or _config(),
        "find_spec": lambda _name: object(),
        "distribution_version": lambda _name: __version__,
        "resource_exists": lambda _resource: True,
        "storage_probe": lambda: {"ok": True, "artifact_removed": True},
        "hidden_pth_probe": lambda: {"supported": True, "hidden_count": 0},
        "provider_catalog": lambda: PROVIDER_CATALOG,
        "replay_readable": lambda _path: True,
        "logging_validator": lambda: True,
        "python_version": (3, 12, 1),
        "generated_at": "2026-09-04T00:00:00Z",
    }
    arguments.update(overrides)
    return build_doctor_report(**arguments)


def _check(report, check_id):
    return next(check for check in report["checks"] if check["id"] == check_id)


class DoctorReportTests(unittest.TestCase):
    def test_resource_manifest_matches_shipped_data_files(self):
        package_root = Path(__file__).resolve().parent.parent / "gex_terminal"
        shipped = {"gex_terminal.tcss"}
        for directory in (
            package_root / "data" / "replays",
            package_root / "data" / "provider_fixtures",
        ):
            shipped.update(
                path.relative_to(package_root).as_posix()
                for path in directory.iterdir()
                if path.is_file() and path.name != "__init__.py"
            )

        self.assertEqual(set(REQUIRED_BUNDLED_RESOURCES), shipped)

    def test_module_manifests_match_package_dependency_groups(self):
        project = tomllib.loads(
            (Path(__file__).resolve().parent.parent / "pyproject.toml").read_text(
                encoding="utf-8"
            )
        )["project"]
        required_names = {
            requirement.split(">", 1)[0].split("=", 1)[0].lower()
            for requirement in project["dependencies"]
        }

        self.assertEqual(
            {name.lower() for name, _module in REQUIRED_RUNTIME_MODULES},
            required_names,
        )
        for module_name, extra_name in OPTIONAL_PROVIDER_SDKS.values():
            dependency_names = {
                requirement.split(">", 1)[0].split("=", 1)[0].lower()
                for requirement in project["optional-dependencies"][extra_name]
            }
            self.assertIn(module_name.lower(), dependency_names)

    def test_versioned_report_drives_text_json_and_success_exit(self):
        report = _report()

        self.assertEqual(report["schema"], DOCTOR_SCHEMA)
        self.assertEqual(report["summary"]["exit_code"], EXIT_OK)
        self.assertEqual(report["summary"]["status"], "pass")
        self.assertEqual(json.loads(doctor_report_to_json(report)), report)
        text = doctor_report_to_text(report)
        self.assertIn("Result: PASS (exit 0)", text)
        self.assertIn("[PASS] package.bundled_resources", text)
        self.assertIn("[UNVERIFIED] provider.live_access", text)
        self.assertFalse(report["execution"]["network_used"])
        self.assertFalse(report["execution"]["live_adapter_constructed"])
        self.assertFalse(report["execution"]["optional_sdk_imported"])
        self.assertFalse(report["execution"]["persistent_state_created"])

    def test_config_shape_contains_names_and_types_but_no_values_or_paths(self):
        symbol_secret = "PRIVATE-SYMBOL-SENTINEL"
        replay_secret = "/Users/private-person/secret-session.jsonl"
        report = _report(
            _config(symbol=symbol_secret, replay_path=replay_secret),
        )
        rendered = doctor_report_to_json(report)
        shape = _check(report, "configuration.shape")

        self.assertTrue(shape["details"]["fields"])
        self.assertFalse(shape["details"]["values_disclosed"])
        self.assertIn({"name": "replay_path", "type": "str"}, shape["details"]["fields"])
        self.assertNotIn(symbol_secret, rendered)
        self.assertNotIn(replay_secret, rendered)
        self.assertNotIn("/Users/", rendered)

    def test_invalid_config_is_safe_diagnostic_and_never_echoes_untrusted_error(self):
        secret = "private-token-shaped-value"
        raw_path = "/Users/private-person/.env"
        report = _report(
            config=None,
            config_error=ConfigValidationError(f"{secret} at {raw_path}"),
        )
        rendered = doctor_report_to_json(report)
        config_check = _check(report, "configuration.shape")

        self.assertEqual(report["summary"]["exit_code"], EXIT_CONFIGURATION_FAILURE)
        self.assertEqual(config_check["status"], "fail")
        self.assertIn("a configuration field failed validation", config_check["summary"])
        self.assertNotIn(secret, rendered)
        self.assertNotIn(raw_path, rendered)

    def test_known_config_validation_message_keeps_safe_field_and_constraint(self):
        report = _report(
            config=None,
            config_error=ConfigValidationError(
                "GEX_STALE_AFTER_SECONDS must be numeric"
            ),
        )

        self.assertIn(
            "GEX_STALE_AFTER_SECONDS must be numeric",
            _check(report, "configuration.shape")["summary"],
        )

    def test_invalid_logging_configuration_is_safe_config_failure(self):
        report = _report(logging_validator=lambda: False)

        self.assertEqual(report["summary"]["exit_code"], EXIT_CONFIGURATION_FAILURE)
        self.assertEqual(
            _check(report, "configuration.logging")["status"],
            "fail",
        )

    def test_missing_required_module_or_resource_is_runtime_failure(self):
        def missing_numpy(name):
            return None if name == "numpy" else object()

        module_report = _report(find_spec=missing_numpy)
        resource_name = REQUIRED_BUNDLED_RESOURCES[1]
        resource_report = _report(
            resource_exists=lambda resource: resource != resource_name,
        )

        self.assertEqual(module_report["summary"]["exit_code"], EXIT_RUNTIME_FAILURE)
        self.assertEqual(
            _check(module_report, "package.required_modules")["details"]["missing"],
            ["numpy"],
        )
        self.assertEqual(resource_report["summary"]["exit_code"], EXIT_RUNTIME_FAILURE)
        self.assertEqual(
            _check(resource_report, "package.bundled_resources")["details"]["missing"],
            [resource_name],
        )

    def test_unsupported_python_fails_but_absent_distribution_metadata_warns(self):
        old_python = _report(python_version=(3, 10, 14))

        def missing_distribution(_name):
            from importlib.metadata import PackageNotFoundError

            raise PackageNotFoundError

        source_mode = _report(distribution_version=missing_distribution)

        self.assertEqual(old_python["summary"]["exit_code"], EXIT_RUNTIME_FAILURE)
        self.assertEqual(_check(old_python, "runtime.python")["status"], "fail")
        self.assertEqual(source_mode["summary"]["exit_code"], EXIT_OK)
        self.assertEqual(_check(source_mode, "package.metadata")["status"], "warning")

    def test_malformed_distribution_version_cannot_leak_probe_content(self):
        secret_path = "/Users/private-person/metadata-secret"
        report = _report(distribution_version=lambda _name: secret_path)
        rendered = doctor_report_to_json(report)

        self.assertEqual(report["summary"]["exit_code"], EXIT_RUNTIME_FAILURE)
        self.assertEqual(_check(report, "package.metadata")["status"], "fail")
        self.assertNotIn(secret_path, rendered)

    def test_unselected_missing_extras_warn_but_selected_missing_sdk_fails(self):
        optional_modules = {module for module, _extra in OPTIONAL_PROVIDER_SDKS.values()}

        def no_optional(name):
            return None if name in optional_modules else object()

        demo_report = _report(find_spec=no_optional)
        live_report = _report(
            _config(data_mode="live", data_provider="databento"),
            find_spec=no_optional,
        )

        self.assertEqual(demo_report["summary"]["exit_code"], EXIT_OK)
        for provider in OPTIONAL_PROVIDER_SDKS:
            self.assertEqual(
                _check(demo_report, f"provider.sdk.{provider}")["status"],
                "warning",
            )
        self.assertEqual(live_report["summary"]["exit_code"], EXIT_CONFIGURATION_FAILURE)
        self.assertEqual(
            _check(live_report, "provider.sdk.databento")["status"],
            "fail",
        )
        self.assertEqual(
            _check(live_report, "provider.live_access")["details"]["entitlements"],
            "unverified",
        )

    def test_scaffold_incompatible_instrument_and_unreadable_replay_fail(self):
        scaffold = _report(_config(data_mode="live", data_provider="ibkr"))
        incompatible = _report(
            _config(data_mode="live", data_provider="yfinance", symbol="ES"),
        )
        missing_replay = _report(
            _config(data_mode="replay"),
            replay_readable=lambda _path: False,
        )

        for report in (scaffold, incompatible, missing_replay):
            self.assertEqual(
                report["summary"]["exit_code"],
                EXIT_CONFIGURATION_FAILURE,
            )
            self.assertEqual(_check(report, "provider.selection")["status"], "fail")
        self.assertIn("scaffold", _check(scaffold, "provider.selection")["summary"])
        self.assertIn(
            "instrument class",
            _check(incompatible, "provider.selection")["summary"],
        )
        self.assertIn("not readable", _check(missing_replay, "provider.selection")["summary"])

    def test_live_auth_entitlements_and_transport_are_always_unverified(self):
        report = _report(
            _config(data_mode="live", data_provider="databento"),
        )
        access = _check(report, "provider.live_access")

        self.assertEqual(report["summary"]["exit_code"], EXIT_OK)
        self.assertEqual(report["summary"]["status"], "warning")
        self.assertEqual(_check(report, "provider.selection")["status"], "warning")
        self.assertEqual(access["status"], "unverified")
        self.assertEqual(
            set(access["details"].values()),
            {"unverified"},
        )
        self.assertIn("Local preflight only", report["evidence_ceiling"])

    def test_storage_failure_is_fixed_safe_runtime_diagnostic(self):
        secret = "/private/readonly/secret-directory"

        def denied_probe():
            raise PermissionError(secret)

        report = _report(storage_probe=denied_probe)
        rendered = doctor_report_to_json(report)

        self.assertEqual(report["summary"]["exit_code"], EXIT_RUNTIME_FAILURE)
        self.assertEqual(
            _check(report, "storage.temporary_round_trip")["status"],
            "fail",
        )
        self.assertNotIn(secret, rendered)

    def test_real_storage_probe_round_trips_and_removes_its_directory(self):
        with tempfile.TemporaryDirectory() as parent:
            result = probe_temporary_storage(parent=parent)
            remaining = tuple(Path(parent).iterdir())

        self.assertEqual(result, {"ok": True, "artifact_removed": True})
        self.assertEqual(remaining, ())

    def test_read_only_storage_factory_failure_creates_no_reported_path(self):
        secret = "/private/readonly/private-probe"

        def denied_factory(**_options):
            raise PermissionError(secret)

        result = probe_temporary_storage(directory_factory=denied_factory)
        report = _report(storage_probe=lambda: result)

        self.assertEqual(result, {"ok": False, "artifact_removed": True})
        self.assertEqual(report["summary"]["exit_code"], EXIT_RUNTIME_FAILURE)
        self.assertNotIn(secret, doctor_report_to_json(report))

    def test_hidden_editable_pth_is_counted_without_its_path(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            hidden = Path(temporary_directory) / "__editable__.gex_terminal-0.4.0.pth"
            visible = Path(temporary_directory) / "other-project.pth"
            hidden.write_text("private path", encoding="utf-8")
            visible.write_text("private path", encoding="utf-8")
            result = probe_hidden_editable_pth(
                site_directories=(temporary_directory,),
                flag_reader=lambda path: 8 if path == hidden else 0,
                hidden_flag=8,
            )
            report = _report(hidden_pth_probe=lambda: result)
            rendered = doctor_report_to_json(report)

        visibility = _check(report, "runtime.editable_pth_visibility")
        self.assertEqual(result, {"supported": True, "hidden_count": 1})
        self.assertEqual(visibility["status"], "warning")
        self.assertEqual(visibility["details"], {"hidden_count": 1})
        self.assertIn("reviewed wheel", visibility["action"])
        self.assertNotIn(temporary_directory, rendered)

    def test_doctor_does_not_use_network_build_adapters_or_import_optional_sdks(self):
        original_import = builtins.__import__
        optional_modules = {module for module, _extra in OPTIONAL_PROVIDER_SDKS.values()}

        def guarded_import(name, *args, **kwargs):
            if name.split(".", 1)[0] in optional_modules:
                raise AssertionError(f"optional SDK import attempted: {name}")
            return original_import(name, *args, **kwargs)

        def network_forbidden(*_args, **_kwargs):
            raise AssertionError("network operation attempted")

        original_builders = dict(registry.ADAPTERS)
        try:
            registry.ADAPTERS.clear()
            registry.ADAPTERS.update(
                {
                    name: network_forbidden
                    for name in original_builders
                }
            )
            with (
                patch.object(builtins, "__import__", side_effect=guarded_import),
                patch.object(socket, "socket", side_effect=network_forbidden),
                patch.object(socket, "create_connection", side_effect=network_forbidden),
            ):
                report = build_doctor_report(
                    _config(),
                    find_spec=importlib.util.find_spec,
                    distribution_version=lambda _name: __version__,
                    resource_exists=lambda _resource: True,
                    storage_probe=lambda: {"ok": True, "artifact_removed": True},
                    hidden_pth_probe=lambda: {"supported": True, "hidden_count": 0},
                    replay_readable=lambda _path: True,
                    logging_validator=lambda: True,
                    python_version=(3, 12, 1),
                    generated_at="2026-09-04T00:00:00Z",
                )
        finally:
            registry.ADAPTERS.clear()
            registry.ADAPTERS.update(original_builders)

        self.assertEqual(report["summary"]["exit_code"], EXIT_OK)
        self.assertFalse(report["execution"]["network_used"])
        self.assertFalse(report["execution"]["live_adapter_constructed"])
        self.assertFalse(report["execution"]["optional_sdk_imported"])


if __name__ == "__main__":
    unittest.main()
