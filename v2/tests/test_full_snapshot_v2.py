"""Full 165-record regression for the V2 ledger."""
from __future__ import annotations

import json
import pathlib
import tempfile
import unittest

from v2 import build_evidence_ledger_v2 as ledger

SNAPSHOT = pathlib.Path(r"F:\somethingProject\graduation-preflight-audit")
SOURCE = pathlib.Path(r"F:\somethingProject\dsbot-preflight")


@unittest.skipUnless(SNAPSHOT.exists() and SOURCE.exists(),
                     "snapshot or source checkout is not present")
class FullSnapshotV2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix="v2-audit-test-")
        cls.result = ledger.build_ledger(
            SNAPSHOT, SOURCE, pathlib.Path(cls.tmp.name),
            verify_baseline=True,
            expected_segments={
                "main": 140,
                "supplementary-subject": 10,
                "supplementary-s7empty": 5,
                "b0-legacy": 10,
            })
        cls.stats = cls.result["stats_data"]
        cls.rows = cls.result["rows"]
        cls.lines = (pathlib.Path(cls.tmp.name) / "DERIVED-FIELD-EVIDENCE-V2.jsonl").read_text(
            encoding="utf-8").splitlines()

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_165_strict_json_and_unique_locators(self):
        self.assertEqual(len(self.lines), 165)
        parsed = [json.loads(line) for line in self.lines]
        self.assertEqual(len({r["audit_locator"] for r in parsed}), 165)
        self.assertTrue(all(r["schema"] == ledger.SCHEMA_ID for r in parsed))
        self.assertEqual(self.stats["records"]["total"], 165)
        self.assertEqual(self.stats["records"]["records_with_seven_fields"], 0)

    def test_segment_counts(self):
        self.assertEqual(self.stats["records"]["by_segment"], {
            "main": 140,
            "supplementary-subject": 10,
            "supplementary-s7empty": 5,
            "b0-legacy": 10,
        })
        self.assertEqual(self.stats["segments"]["main"]["memory_entries"], 150)
        self.assertEqual(self.stats["segments"]["supplementary-subject"]["memory_entries"], 20)
        self.assertEqual(self.stats["segments"]["supplementary-s7empty"]["memory_entries"], 0)

    def test_field_state_distribution(self):
        dist = self.stats["field_state_distribution"]
        self.assertEqual(dist["run_id"], {"unrecoverable": 165})
        self.assertEqual(dist["base_sha"], {"unrecoverable": 165})
        self.assertEqual(dist["knowledge_result_ids"], {"externally_derived": 165})
        self.assertEqual(dist["memory_injected"],
                         {"externally_derived": 85, "partially_derived": 80})
        self.assertEqual(dist["short_term_injected"], {"externally_derived": 165})
        self.assertEqual(dist["difficult_flag"], {"externally_derived": 165})
        self.assertEqual(dist["data_kind"], {"externally_derived": 165})
        self.assertTrue(all(self.stats["integrity"].values()))

    def test_memory_170_and_subfield_states(self):
        mem = self.stats["memory"]
        self.assertEqual(mem["entries_total"], 170)
        self.assertEqual(mem["records_with_entries"], 80)
        self.assertEqual(mem["gold_unique_matches"], 170)
        self.assertEqual(mem["type_matches"], 170)
        self.assertEqual(mem["strength_matches"], 170)
        self.assertEqual(mem["subject_key_resolved"], 170)
        self.assertEqual(mem["subject_label_matches"], 160)
        self.assertEqual(mem["subject_label_mismatch_count"], 10)
        self.assertEqual(mem["runtime_status"], {"inferred_active": 170, "unknown": 0})
        self.assertEqual(mem["subfield_state_distribution"]["gold_status"],
                         {"gold_reference": 170})
        self.assertEqual(mem["subfield_state_distribution"]["runtime_status"],
                         {"inferred": 170})
        self.assertEqual(mem["section_5_6_6_status"], "NOT_COMPLETED")
        self.assertFalse(mem["injected_json_reference_present"])
        entries = [e for r in self.rows for e in r["fields"]["memory_injected"]["value"]]
        self.assertTrue(all("gold_status" in e["subfields"] for e in entries))
        self.assertTrue(all("runtime_status" in e["subfields"] for e in entries))
        self.assertTrue(all("status" not in e["subfields"] for e in entries))
        self.assertTrue(all(e["subfields"]["runtime_status"]["verification"] == "not_verified"
                            for e in entries))

    def test_short_term_three_predicates(self):
        short = self.stats["short_term"]
        self.assertEqual(short["predicates"], {
            "short_term_slot_enabled_true": 80,
            "short_term_block_present_true": 80,
            "short_term_payload_nonempty_true": 75,
        })
        self.assertEqual(short["by_segment"]["main"]["payload_nonempty_true"], 70)
        self.assertEqual(short["by_segment"]["supplementary-s7empty"],
                         {"slot_enabled_true": 5, "block_present_true": 5,
                          "payload_nonempty_true": 0})
        self.assertEqual(len(short["s7empty_d_records"]), 5)
        for item in short["s7empty_d_records"]:
            self.assertTrue(item["slot_enabled"])
            self.assertTrue(item["block_present"])
            self.assertFalse(item["payload_nonempty"])
            self.assertEqual(item["feedback_count"], 0)

    def test_b0_ten_exact_matches(self):
        b0 = self.stats["b0_mapping"]
        self.assertEqual(b0["b0_map_rows"], 10)
        self.assertEqual(b0["b0_map_unique_keys"], 10)
        self.assertEqual(b0["b0_map_matched"], 10)
        self.assertEqual(b0["b0_map_sample_matches"], 10)
        self.assertEqual(b0["b0_map_experiment_matches"], 10)
        self.assertEqual(b0["b0_map_repeat_matches"], 10)
        self.assertEqual(b0["b0_map_run_dir_matches"], 10)
        self.assertEqual(b0["b0_map_ordinal_matches"], 10)
        self.assertEqual(b0["b0_map_legacy_key_collisions"], 4)
        self.assertEqual(b0["b0_map_errors"], [])
        self.assertTrue(b0["b0_map_all"])
        b0_rows = [r for r in self.rows if r["segment"] == "b0-legacy"]
        self.assertEqual(len(b0_rows), 10)
        self.assertTrue(all(r["plan"] is None for r in b0_rows))
        self.assertTrue(all(r["b0"]["state"] == "externally_derived" for r in b0_rows))

    def test_b0_difficult_is_not_raw_feedback_condition(self):
        b0_s7 = [r for r in self.rows
                 if r["segment"] == "b0-legacy" and r["source"]["sample_id"] == "S7"]
        self.assertEqual(len(b0_s7), 5)
        for row in b0_s7:
            field = row["fields"]["difficult_flag"]
            self.assertFalse(field["value"])
            self.assertTrue(field["evidence"]["raw_condition_partial_and_reason"])
            self.assertTrue(field["evidence"]["b0_group_fixed_false"])

    def test_unrecoverable_fields_and_audit_locator(self):
        for row in self.rows:
            self.assertEqual(row["fields"]["run_id"]["state"], "unrecoverable")
            self.assertIsNone(row["fields"]["run_id"]["value"])
            self.assertEqual(row["fields"]["base_sha"]["state"], "unrecoverable")
            self.assertIsNone(row["fields"]["base_sha"]["value"])
            self.assertFalse(row["fields"]["base_sha"]["runtime_source_version_verified"])
            self.assertEqual(row["fields"]["base_sha"]["reviewed_source_commit"],
                             ledger.SOURCE_COMMIT)
            self.assertEqual(row["audit_locator"],
                             row["fields"]["run_id"]["traceability"]["audit_locator"])
            self.assertEqual(
                row["fields"]["run_id"]["traceability"]["audit_locator_kind"],
                "external_audit_identifier_not_run_id")

    def test_plans_and_prompts_are_bound_for_new_data(self):
        plan_rows = [r for r in self.rows if r["plan"]]
        self.assertEqual(len(plan_rows), 155)
        self.assertTrue(all(r["prompt"]["sha256_matches_record"] for r in self.rows))
        self.assertTrue(all(r["prompt"]["prompt_chars_matches_record"] for r in self.rows))
        self.assertTrue(all(r["plan"]["config_sha256_matches_snapshot_config"]
                            for r in plan_rows))

    def test_knowledge_and_data_kind_are_scoped(self):
        for row in self.rows:
            knowledge = row["fields"]["knowledge_result_ids"]
            self.assertEqual(knowledge["state"], "externally_derived")
            self.assertEqual(knowledge["value"], [])
            self.assertEqual(knowledge["scope"], "empty_configuration_only")
            data_kind = row["fields"]["data_kind"]
            self.assertEqual(data_kind["state"], "externally_derived")
            self.assertFalse(data_kind["evidence"]["original_sample_has_data_kind"])


if __name__ == "__main__":
    unittest.main()
