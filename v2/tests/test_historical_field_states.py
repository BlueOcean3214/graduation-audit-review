"""Tests for unrecoverable fields and the other V2 field boundaries."""
from __future__ import annotations

import unittest

from v2 import build_evidence_ledger_v2 as ledger
from v2.tests.helpers import sample_with_memories


class HistoricalFieldStateTests(unittest.TestCase):
    def test_run_id_and_base_sha_are_not_fabricated(self):
        run_id, base_sha = ledger.build_unrecoverable_fields({}, "runs/x/results.jsonl:1", "exp-1")
        self.assertEqual(run_id["state"], "unrecoverable")
        self.assertIsNone(run_id["value"])
        self.assertFalse(run_id["recorded_at_generation"])
        locator = run_id["traceability"]["audit_locator"]
        self.assertNotEqual(locator, "exp-1")
        self.assertFalse(run_id["traceability"]["derived_batch_locator"]["is_original_run_id"])
        self.assertEqual(run_id["traceability"]["derived_batch_locator"]["value"], "batch:exp-1")

        self.assertEqual(base_sha["state"], "unrecoverable")
        self.assertIsNone(base_sha["value"])
        self.assertIsNone(base_sha["runtime_base_sha"]["value"])
        self.assertEqual(base_sha["runtime_base_sha"]["state"], "unrecoverable")
        self.assertEqual(base_sha["reviewed_source_commit"], ledger.SOURCE_COMMIT)
        self.assertFalse(base_sha["runtime_source_version_verified"])
        self.assertTrue(base_sha["evidence"]["base_sha_not_substituted_by_reviewed_commit"])
        self.assertFalse(base_sha["evidence"]["execution_report_baseline_is_proof"])

    def test_base_sha_does_not_contain_reviewed_commit_as_value(self):
        _, base_sha = ledger.build_unrecoverable_fields({}, "loc", "exp")
        self.assertNotEqual(base_sha.get("value"), ledger.SOURCE_COMMIT)
        self.assertNotIn("base_sha", base_sha)  # no nested replacement key

    def test_knowledge_empty_scope_is_explicit_and_limited(self):
        config = {"knowledge_results": [], "knowledge_search_failed": False}
        plan_info = {
            "file": "runs/x/plan.json",
            "config_sha256_matches_snapshot_config": True,
            "plan_sha256": "abc",
        }
        result = ledger.build_knowledge_field(config, ledger.config_sha256(config),
                                              plan_info, ledger.KNOWLEDGE_NONE, "D")
        self.assertEqual(result["state"], "externally_derived")
        self.assertEqual(result["value"], [])
        self.assertEqual(result["scope"], "empty_configuration_only")
        self.assertTrue(any("不能推广" in x for x in result["limitations"]))

    def test_nonempty_knowledge_config_is_unknown(self):
        config = {"knowledge_results": [{"id": "k1"}], "knowledge_search_failed": False}
        result = ledger.build_knowledge_field(config, "hash", None,
                                              ledger.KNOWLEDGE_NONE, "D")
        self.assertEqual(result["state"], "unknown")
        self.assertIsNone(result["value"])

    def test_b0_knowledge_has_no_plan_binding(self):
        config = {"knowledge_results": [], "knowledge_search_failed": False}
        result = ledger.build_knowledge_field(config, "hash", None,
                                              ledger.KNOWLEDGE_NONE, "B0")
        self.assertEqual(result["evidence"]["plan_binding"]["state"],
                         "not_available_for_b0_legacy")
        self.assertTrue(result["evidence"]["b0_legacy_prompt_only"])

    def test_data_kind_is_provenance_derived(self):
        sample = sample_with_memories([], sample_id="S1")
        result = ledger.build_data_kind_field(sample, True)
        self.assertEqual(result["state"], "externally_derived")
        self.assertEqual(result["value"], "simulated_learner_fixture")
        self.assertFalse(result["evidence"]["original_sample_has_data_kind"])
        self.assertIn("provenance", result["provenance_note"])

    def test_data_kind_unknown_without_simulation_flag(self):
        sample = sample_with_memories([])
        sample["simulation"] = {"is_simulated": False}
        result = ledger.build_data_kind_field(sample, True)
        self.assertEqual(result["state"], "unknown")
        self.assertIsNone(result["value"])

    def test_b0_difficult_is_fixed_false_even_when_raw_feedback_qualifies(self):
        sample = sample_with_memories([], sample_id="S7",
                                      feedback_status="partial",
                                      feedback_reason="任务难度太高")
        result = ledger.build_difficult_field(sample, "B0", "no dynamic rule")
        self.assertFalse(result["value"])
        self.assertTrue(result["evidence"]["raw_condition_partial_and_reason"])
        self.assertTrue(result["evidence"]["b0_group_fixed_false"])
        self.assertTrue(result["evidence"]["agree"])
        self.assertEqual(result["state"], "externally_derived")

    def test_b_difficult_uses_latest_feedback_and_prompt_rule(self):
        sample = sample_with_memories([], sample_id="S7",
                                      feedback_status="partial",
                                      feedback_reason="任务难度太高")
        result = ledger.build_difficult_field(
            sample, "B", ledger.DIFFICULT_RULE)
        self.assertTrue(result["value"])
        self.assertTrue(result["evidence"]["dynamic_rule_present_in_prompt"])
        self.assertEqual(result["state"], "externally_derived")

    def test_b_difficult_false_when_latest_feedback_is_not_partial(self):
        sample = sample_with_memories([], sample_id="S1",
                                      feedback_status="not_completed",
                                      feedback_reason="任务难度太高")
        result = ledger.build_difficult_field(sample, "B", "no rule")
        self.assertFalse(result["value"])
        self.assertFalse(result["evidence"]["raw_condition_partial_and_reason"])


if __name__ == "__main__":
    unittest.main()
