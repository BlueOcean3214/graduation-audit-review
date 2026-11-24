# -*- coding: utf-8 -*-
"""Structural checks over all 165 V3 evidence rows."""
from __future__ import annotations

import copy
import unittest

from v3 import build_evidence_ledger_v3 as v3
from v3.tests import helpers


class TestEvidenceRows(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = helpers.rows()
        cls.stats = helpers.stats()

    def test_165_rows_with_unique_audit_locators(self):
        self.assertEqual(len(self.rows), 165)
        locators = [r["audit_locator"] for r in self.rows]
        self.assertEqual(len(set(locators)), 165)
        identities = [tuple(sorted(r["identity"].items())) for r in self.rows]
        self.assertEqual(len(set(identities)), 165)

    def test_segment_counts_are_exact(self):
        counts = {}
        for row in self.rows:
            counts[row["segment"]] = counts.get(row["segment"], 0) + 1
        self.assertEqual(counts, helpers.EXPECTED_SEGMENTS)

    def test_every_row_has_exactly_seven_envelopes(self):
        for row in self.rows:
            self.assertEqual(set(row["fields"]), set(v3.SEVEN_FIELDS))

    def test_every_envelope_has_required_keys_and_rule_version(self):
        for row in self.rows:
            for name in v3.SEVEN_FIELDS:
                field = row["fields"][name]
                for key in ("value", "evidence_state", "original_field_present",
                            "source_refs", "rule_id", "rule_version",
                            "verification", "limitations"):
                    self.assertIn(key, field, f"{name} missing {key}")
                self.assertEqual(field["rule_version"], v3.RULE_VERSION)
                self.assertIn(field["evidence_state"], v3.EVIDENCE_STATES)
                self.assertIn(field["verification"], v3.VERIFICATION_STATES)

    def test_original_field_presence_is_false_for_all_165(self):
        for row in self.rows:
            self.assertEqual(row["source"]["original_field_presence"],
                             {name: False for name in v3.SEVEN_FIELDS})
            for name in v3.SEVEN_FIELDS:
                self.assertFalse(row["fields"][name]["original_field_present"])

    def test_acceptance_keeps_original_contract_fail_and_layer_pass(self):
        for row in self.rows:
            acc = row["acceptance"]
            self.assertEqual(acc["original_contract_compliance"]["status"], "FAIL")
            self.assertEqual(acc["original_contract_compliance"]["present_fields"], [])
            self.assertEqual(acc["original_contract_compliance"]["missing_fields"],
                             list(v3.SEVEN_FIELDS))
            self.assertEqual(acc["evidence_layer_integrity"]["status"], "PASS")
            self.assertTrue(all(acc["evidence_layer_integrity"]["checks"].values()))

    def test_audit_metadata_is_not_runtime_provenance(self):
        for row in self.rows:
            self.assertEqual(row["audit"]["runtime_source_version_verified"], False)
            self.assertEqual(row["audit"]["reviewed_source_commit"], v3.SOURCE_COMMIT)
            self.assertEqual(row["audit"]["snapshot_commit"], v3.SNAPSHOT_COMMIT)

    def test_validation_rejects_broken_envelopes(self):
        row = copy.deepcopy(self.rows[0])
        broken = copy.deepcopy(row)
        del broken["fields"]["data_kind"]["rule_version"]
        with self.assertRaises(v3.AuditError):
            v3.validate_evidence_row(broken)
        broken = copy.deepcopy(row)
        broken["fields"]["data_kind"]["evidence_state"] = "guessed"
        with self.assertRaises(v3.AuditError):
            v3.validate_evidence_row(broken)
        broken = copy.deepcopy(row)
        broken["fields"]["run_id"]["value"] = "20261113T061051Z-S1-A-r0"
        with self.assertRaises(v3.AuditError):
            v3.validate_evidence_row(broken)


if __name__ == "__main__":
    unittest.main()
