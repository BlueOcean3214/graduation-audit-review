# -*- coding: utf-8 -*-
"""Statistics, determinism, and atomic-output checks."""
from __future__ import annotations

import json
import pathlib
import tempfile
import unittest
from unittest import mock

from v3 import build_evidence_ledger_v3 as v3
from v3.tests import helpers


class TestStatisticsAndDeterminism(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.built = helpers.built()
        cls.rows = cls.built["rows"]
        cls.stats = cls.built["stats"]

    def test_build_is_deterministic(self):
        again = v3.build_ledger(
            helpers.AUDIT_ROOT, helpers.SOURCE_ROOT, pathlib.Path("."),
            verify_baseline=True, expected_segments=helpers.EXPECTED_SEGMENTS,
            write=False)
        self.assertEqual(again["jsonl_text"], self.built["jsonl_text"])
        self.assertEqual(again["stats_text"], self.built["stats_text"])

    def test_integrity_checks_all_true(self):
        self.assertEqual(len(self.stats["integrity"]), len(set(self.stats["integrity"])))
        self.assertTrue(all(self.stats["integrity"].values()),
                        [k for k, v in self.stats["integrity"].items() if not v])

    def test_dual_acceptance_is_explicit(self):
        dual = self.stats["dual_acceptance"]
        self.assertEqual(dual["original_contract_compliance"]["status"], "FAIL")
        self.assertEqual(dual["evidence_layer_integrity"]["status"], "PASS")
        self.assertEqual(dual["original_contract_compliance"]["records_with_all_seven"], 0)

    def test_field_state_and_verification_distributions(self):
        states = self.stats["field_state_distribution"]
        self.assertEqual(states["run_id"], {"unrecoverable": 165})
        self.assertEqual(states["base_sha"], {"unrecoverable": 165})
        self.assertEqual(states["knowledge_result_ids"], {"externally_derived": 165})
        self.assertEqual(states["memory_injected"],
                         {"externally_derived": 85, "partially_derived": 80})
        self.assertEqual(states["short_term_injected"], {"externally_derived": 165})
        self.assertEqual(states["difficult_flag"], {"externally_derived": 165})
        self.assertEqual(states["data_kind"], {"externally_derived": 165})
        verification = self.stats["field_verification_distribution"]
        self.assertEqual(verification["run_id"], {"not_possible": 165})
        self.assertEqual(verification["difficult_flag"], {"verified": 165})
        self.assertEqual(verification["knowledge_result_ids"],
                         {"partially_verified": 10, "verified": 155})

    def test_stats_are_recomputed_from_rows_not_copied(self):
        memory = self.stats["memory"]
        rows = self.rows
        self.assertEqual(memory["entries_total"],
                         sum(len(r["fields"]["memory_injected"]["entries"]) for r in rows))
        self.assertEqual(self.stats["records"]["total"], len(rows))
        self.assertEqual(self.stats["short_term"]["predicates"]["short_term_slot_enabled_true"],
                         sum(1 for r in rows
                             if r["fields"]["short_term_injected"]["value"]["short_term_slot_enabled"]))
        self.assertEqual(self.stats["difficult"]["true_total"],
                         sum(1 for r in rows if r["fields"]["difficult_flag"]["value"]))
        for segment in helpers.EXPECTED_SEGMENTS:
            self.assertEqual(self.stats["segments"][segment]["records"],
                             helpers.EXPECTED_SEGMENTS[segment])

    def test_b0_mapping_uses_full_four_field_key(self):
        b0 = self.stats["b0_mapping"]
        self.assertEqual(b0["b0_map_rows"], 10)
        self.assertEqual(b0["b0_map_unique_keys"], 10)
        self.assertEqual(b0["b0_map_matched"], 10)
        self.assertEqual(b0["b0_map_ordinal_matches"], 10)
        self.assertEqual(b0["b0_map_legacy_key_collisions"], 4)
        self.assertEqual(b0["b0_map_errors"], [])


class TestAtomicOutputs(unittest.TestCase):
    def test_successful_write_has_three_files_and_success_state(self):
        built = helpers.built()
        with tempfile.TemporaryDirectory() as tmp:
            out = pathlib.Path(tmp)
            v3.write_outputs_atomic(out, built["jsonl_text"], built["stats_text"],
                                    built["rows"], built["stats"])
            for name in ("DERIVED-FIELD-EVIDENCE-V3.jsonl",
                         "DERIVED-FIELD-EVIDENCE-V3-STATS.json",
                         "V3-BUILD-STATE.json"):
                self.assertTrue((out / name).is_file(), name)
            state = json.loads((out / "V3-BUILD-STATE.json").read_text(encoding="utf-8"))
            self.assertEqual(state["status"], "success")
            self.assertEqual(state["outputs"]["DERIVED-FIELD-EVIDENCE-V3.jsonl"],
                             v3.sha256_bytes((out / "DERIVED-FIELD-EVIDENCE-V3.jsonl").read_bytes()))

    def test_failure_restores_previous_outputs_and_records_failed_state(self):
        built = helpers.built()
        with tempfile.TemporaryDirectory() as tmp:
            out = pathlib.Path(tmp)
            v3.write_outputs_atomic(out, built["jsonl_text"], built["stats_text"],
                                    built["rows"], built["stats"])
            jsonl = out / "DERIVED-FIELD-EVIDENCE-V3.jsonl"
            stats = out / "DERIVED-FIELD-EVIDENCE-V3-STATS.json"
            old_jsonl, old_stats = jsonl.read_bytes(), stats.read_bytes()
            with mock.patch.object(v3, "sha256_bytes",
                                   side_effect=["0" * 64, "0" * 64, "a" * 64, "b" * 64]):
                with self.assertRaises(v3.AuditError):
                    v3.write_outputs_atomic(out, built["jsonl_text"], built["stats_text"],
                                            built["rows"], built["stats"])
            self.assertEqual(jsonl.read_bytes(), old_jsonl)
            self.assertEqual(stats.read_bytes(), old_stats)
            state = json.loads((out / "V3-BUILD-STATE.json").read_text(encoding="utf-8"))
            self.assertEqual(state["status"], "failed")
            self.assertIn("hash mismatch", state["error"])

    def test_bad_staged_stats_does_not_touch_existing_outputs(self):
        built = helpers.built()
        with tempfile.TemporaryDirectory() as tmp:
            out = pathlib.Path(tmp)
            v3.write_outputs_atomic(out, built["jsonl_text"], built["stats_text"],
                                    built["rows"], built["stats"])
            jsonl = out / "DERIVED-FIELD-EVIDENCE-V3.jsonl"
            old = jsonl.read_bytes()
            with self.assertRaises(Exception):
                v3.write_outputs_atomic(out, built["jsonl_text"], "not-json",
                                        built["rows"], built["stats"])
            self.assertEqual(jsonl.read_bytes(), old)


if __name__ == "__main__":
    unittest.main()
