import math
import unittest
from dataclasses import replace

from gex_terminal.databento_certification_policy import (
    CERTIFICATION_POLICY_SCHEMA,
    DatabentoCertificationPolicy,
    DatabentoCertificationThresholds,
    ES_PRELIVE_V1,
    NQ_PRELIVE_V1,
    resolve_databento_certification_policy,
    validate_contract_multiplier,
)


class DatabentoCertificationPolicyTests(unittest.TestCase):
    def test_default_profiles_are_versioned_and_symbol_scoped(self):
        es = resolve_databento_certification_policy(symbol="es")
        nq = resolve_databento_certification_policy(symbol="NQ")

        self.assertIs(es, ES_PRELIVE_V1)
        self.assertIs(nq, NQ_PRELIVE_V1)
        self.assertEqual(es.schema, CERTIFICATION_POLICY_SCHEMA)
        self.assertNotEqual(es.policy_id, nq.policy_id)
        self.assertIsNot(es.thresholds, nq.thresholds)
        self.assertEqual(es.canonical_contract_multiplier, 50.0)
        self.assertEqual(nq.canonical_contract_multiplier, 20.0)
        self.assertGreater(es.thresholds.minimum_definitions, 1)
        self.assertGreater(es.thresholds.minimum_distinct_strikes, 1)

    def test_policy_round_trip_mapping_is_strict(self):
        serialized = ES_PRELIVE_V1.to_dict()
        resolved = resolve_databento_certification_policy(
            symbol="ES",
            policy=serialized,
        )
        self.assertEqual(resolved, ES_PRELIVE_V1)

        serialized["unexpected"] = True
        with self.assertRaisesRegex(ValueError, "unknown.*field"):
            resolve_databento_certification_policy(symbol="ES", policy=serialized)

        invalid_version = ES_PRELIVE_V1.to_dict()
        invalid_version["version"] = 1.0
        with self.assertRaisesRegex(ValueError, "unsupported.*version"):
            resolve_databento_certification_policy(
                symbol="ES",
                policy=invalid_version,
            )

        weakened = ES_PRELIVE_V1.to_dict()
        weakened["thresholds"]["minimum_provider_frames"] = 1
        with self.assertRaisesRegex(
            ValueError,
            "registered certification policy content mismatch",
        ):
            resolve_databento_certification_policy(
                symbol="ES",
                policy=weakened,
            )

    def test_invalid_thresholds_are_rejected(self):
        values = ES_PRELIVE_V1.thresholds.to_dict()
        for field_name, invalid in (
            ("minimum_definitions", 0),
            ("minimum_sequence_coverage", 0.0),
            ("minimum_usable_iv_coverage", 1.01),
            ("maximum_fallback_iv_coverage", -0.01),
            ("maximum_underlying_age_ms", math.inf),
            ("maximum_underlying_age_ms", "2000"),
        ):
            with self.subTest(field_name=field_name):
                invalid_values = {**values, field_name: invalid}
                with self.assertRaises(ValueError):
                    DatabentoCertificationThresholds(**invalid_values)

    def test_custom_policy_still_cannot_cross_symbols(self):
        custom = replace(ES_PRELIVE_V1, policy_id="custom-es-v1")
        with self.assertRaisesRegex(ValueError, "targets ES, not NQ"):
            resolve_databento_certification_policy(symbol="NQ", policy=custom)

    def test_custom_policy_cannot_redefine_symbol_multiplier(self):
        with self.assertRaisesRegex(
            ValueError,
            "ES canonical_contract_multiplier must be 50",
        ):
            DatabentoCertificationPolicy(
                policy_id="bad-es-multiplier",
                version=1,
                symbol="ES",
                canonical_contract_multiplier=1.0,
                thresholds=ES_PRELIVE_V1.thresholds,
            )

    def test_multiplier_validation_is_exact_and_finite(self):
        self.assertEqual(validate_contract_multiplier(ES_PRELIVE_V1, 50), 50.0)
        for invalid in (20, math.nan, math.inf, True):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    validate_contract_multiplier(ES_PRELIVE_V1, invalid)


if __name__ == "__main__":
    unittest.main()
