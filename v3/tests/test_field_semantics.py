# -*- coding: utf-8 -*-
"""Field-by-field semantic checks, including the cases reviewers disputed."""
from __future__ import annotations

import unittest

from v3.tests import helpers


class TestUnrecoverableFields(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = helpers.rows()

    def test_run_id_is_null_and_not_replaced_by_locator(self):
        for row in self.rows:
            field = row["fields"]["run_id"]
            self.assertIsNone(field["value"])
            self.assertEqual(field["evidence_state"], "unrecoverable")
            self.assertEqual(field["verification"], "not_possible")
            self.assertEqual(field["traceability"]["audit_locator"], row["audit_locator"])
            self.assertEqual(field["traceability"]["kind"],
                             "external_audit_identifier_not_run_id")

    def test_base_sha_is_null_and_reviewed_commit_is_not_substituted(self):
        for row in self.rows:
            field = row["fields"]["base_sha"]
            self.assertIsNone(field["value"])
            self.assertIsNone(field["runtime_base_sha"])
            self.assertEqual(field["evidence_state"], "unrecoverable")
            self.assertEqual(field["reviewed_source_commit"], helpers.v3.SOURCE_COMMIT)
            self.assertFalse(field["runtime_source_version_verified"])
            self.assertFalse(field["execution_report_baseline_is_proof"])
            self.assertNotEqual(field["value"], field["reviewed_source_commit"])


class TestKnowledgeResults(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = helpers.rows()

    def test_all_165_are_empty_lists_with_scope_limit(self):
        for row in self.rows:
            field = row["fields"]["knowledge_result_ids"]
            self.assertEqual(field["value"], [])
            self.assertEqual(field["scope"], "empty_configuration_only")
            self.assertTrue(field["prompt_declares_no_knowledge_results"])
            self.assertEqual(field["config_knowledge_results"], [])
            self.assertTrue(any("不能推广" in x for x in field["limitations"]))

    def test_new_records_have_config_plan_record_chain(self):
        for row in self.rows:
            if row["segment"] == "b0-legacy":
                continue
            field = row["fields"]["knowledge_result_ids"]
            self.assertFalse(field["b0_prompt_only"])
            self.assertEqual(field["verification"], "verified")
            self.assertEqual(field["config_sha256"],
                             "b33bd1ac4ca16ffd7a2ad9c8d256b4842454f3c6d5a5268a04df50255d05c256")
            self.assertIsNotNone(row["plan"])
            self.assertTrue(row["plan"]["config_sha256_matches_snapshot_config"])

    def test_b0_is_prompt_only_and_not_upgraded(self):
        b0 = [r for r in self.rows if r["segment"] == "b0-legacy"]
        self.assertEqual(len(b0), 10)
        for row in b0:
            field = row["fields"]["knowledge_result_ids"]
            self.assertTrue(field["b0_prompt_only"])
            self.assertEqual(field["verification"], "partially_verified")
            self.assertEqual(field["b0_plan_binding"]["state"], "not_available_for_b0_legacy")
            self.assertIsNone(row["plan"])


class TestMemoryInjected(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = helpers.rows()
        cls.with_entries = [r for r in cls.rows if r["fields"]["memory_injected"]["entries"]]

    def test_170_entries_over_80_records(self):
        total = sum(len(r["fields"]["memory_injected"]["entries"]) for r in self.rows)
        self.assertEqual(total, 170)
        self.assertEqual(len(self.with_entries), 80)
        for row in self.rows:
            field = row["fields"]["memory_injected"]
            self.assertEqual(field["source_entry_count"], len(field["entries"]))
            self.assertEqual(len(field["value"]), len(field["entries"]))

    def test_every_entry_has_unique_gold_mapping_and_split_subfields(self):
        seen = set()
        for row in self.with_entries:
            row_keys = set()
            for entry in row["fields"]["memory_injected"]["entries"]:
                self.assertIsNotNone(entry["gold_ref"])
                key = (entry["gold_ref"]["file"], entry["gold_ref"]["index"])
                self.assertNotIn(key, row_keys)
                row_keys.add(key)
                seen.add(key)
                subs = entry["subfields"]
                self.assertEqual(set(subs), {"content", "memory_type", "subject_key",
                                             "strength", "gold_status", "memory_id",
                                             "runtime_status"})
                self.assertEqual(subs["content"]["value"], entry["content"])
                self.assertEqual(subs["memory_type"]["verification"], "verified")
                self.assertEqual(subs["strength"]["verification"], "verified")
                self.assertIsNone(subs["memory_id"]["value"])
                self.assertEqual(subs["gold_status"]["value"], "active")
                self.assertEqual(subs["gold_status"]["evidence_state"], "gold_reference")
        self.assertEqual(len(seen), 15)  # 15 distinct Gold memories back 170 injected entries

    def test_runtime_status_is_inferred_and_never_a_bare_value(self):
        for row in self.with_entries:
            field = row["fields"]["memory_injected"]
            for entry in field["entries"]:
                status = entry["subfields"]["runtime_status"]
                self.assertIsNone(status["value"])
                self.assertEqual(status["inferred_value"], "active")
                self.assertEqual(status["evidence_state"], "inferred")
                self.assertEqual(status["verification"], "not_verified")
                self.assertEqual(status["confidence"], "low")
                self.assertFalse(status["section_5_6_6_compared"])
                self.assertEqual(len(status["verification_blockers"]), 4)
            for flat in field["value"]:
                self.assertIsNone(flat["status"])
            self.assertEqual(field["section_5_6_6_status"], "NOT_COMPLETED")
            self.assertFalse(field["injected_json_reference_present"])

    def test_memory_statistics_are_split(self):
        memory = helpers.stats()["memory"]
        self.assertEqual(memory["entries_total"], 170)
        self.assertEqual(memory["gold_status_counts"], {"active": 170})
        self.assertEqual(memory["runtime_status_counts"], {"inferred_active": 170})
        self.assertEqual(memory["runtime_verification_counts"], {"not_verified": 170})
        self.assertEqual(memory["subject_label_exact_matches"], 160)
        self.assertEqual(memory["subject_key_matches"], 0)
        self.assertEqual(memory["subject_key_resolved"], 170)
        self.assertEqual(memory["subject_display_mismatches"], 10)
        self.assertEqual(memory["type_matches"], 170)
        self.assertEqual(memory["strength_matches"], 170)

    def test_s4_display_mismatches_are_preserved(self):
        mismatches = []
        for row in self.with_entries:
            for entry in row["fields"]["memory_injected"]["entries"]:
                if entry["subfields"]["subject_key"]["subject_display_mismatch"]:
                    mismatches.append(row)
                    self.assertEqual(row["source"]["sample_id"], "S4")
                    self.assertEqual(entry["subfields"]["subject_key"]["value"], "medium")
                    self.assertEqual(entry["subfields"]["subject_key"]["prompt_subject"], "中等")
        self.assertEqual(len(mismatches), 10)


class TestShortTerm(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = helpers.rows()
        cls.stats = helpers.stats()

    def test_three_predicates_have_expected_totals(self):
        short = self.stats["short_term"]
        self.assertEqual(short["predicates"]["short_term_slot_enabled_true"], 80)
        self.assertEqual(short["predicates"]["short_term_block_present_true"], 80)
        self.assertEqual(short["predicates"]["short_term_feedback_history_present_true"], 75)
        self.assertEqual(short["legacy_v2_count"], 75)

    def test_s7empty_five_records_show_the_difference(self):
        s7 = [r for r in self.rows if r["segment"] == "supplementary-s7empty"]
        self.assertEqual(len(s7), 5)
        for row in s7:
            value = row["fields"]["short_term_injected"]["value"]
            self.assertTrue(value["short_term_slot_enabled"])
            self.assertTrue(value["short_term_block_present"])
            self.assertFalse(value["short_term_feedback_history_present"])
            pred = row["fields"]["short_term_injected"]["predicates"]["short_term_feedback_history_present"]
            self.assertEqual(pred["feedback_count"], 0)
            self.assertTrue(pred["plan_present"])
            self.assertTrue(pred["payload_parsed"])

    def test_a_c_and_b0_have_no_short_term_slot(self):
        for row in self.rows:
            if row["source"]["group"] in ("A", "C", "C-subj", "B0"):
                value = row["fields"]["short_term_injected"]["value"]
                self.assertFalse(value["short_term_slot_enabled"])
                self.assertFalse(value["short_term_block_present"])
                self.assertFalse(value["short_term_feedback_history_present"])

    def test_frozen_boolean_is_not_redefined(self):
        for row in self.rows:
            field = row["fields"]["short_term_injected"]
            self.assertIsNone(field["value"]["short_term_injected"])
            compatibility = field["frozen_field_compatibility"]
            self.assertFalse(compatibility["v3_redefines_original_field"])
            self.assertEqual(compatibility["semantics_status"], "pending_advisor_confirmation")
            self.assertTrue(compatibility["formal_run_requires_approved_semantics"])


class TestDifficultFlag(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = helpers.rows()

    def test_ten_true_values_follow_latest_feedback_rule(self):
        true_rows = [r for r in self.rows if r["fields"]["difficult_flag"]["value"]]
        self.assertEqual(len(true_rows), 10)
        for row in true_rows:
            self.assertEqual(row["source"]["sample_id"], "S7")
            self.assertIn(row["source"]["group"], ("B", "D"))
            field = row["fields"]["difficult_flag"]
            self.assertTrue(field["raw_condition_partial_and_reason"])
            self.assertTrue(field["feedback_slot_enabled"])
            self.assertTrue(field["dynamic_rule_present_in_prompt"])
            self.assertTrue(field["agree"])

    def test_b0_raw_condition_is_true_but_group_value_stays_false(self):
        b0 = [r for r in self.rows if r["segment"] == "b0-legacy"
              and r["source"]["sample_id"] == "S7"]
        self.assertEqual(len(b0), 5)
        for row in b0:
            field = row["fields"]["difficult_flag"]
            self.assertFalse(field["value"])
            self.assertTrue(field["raw_condition_partial_and_reason"])
            self.assertTrue(field["b0_group_fixed_false"])
            self.assertFalse(field["dynamic_rule_present_in_prompt"])

    def test_no_feedback_records_have_null_latest_feedback(self):
        rows = [r for r in self.rows if r["source"]["sample_id"] == "S7-empty"]
        self.assertEqual(len(rows), 5)
        for row in rows:
            field = row["fields"]["difficult_flag"]
            self.assertIsNone(field["latest_feedback"])
            self.assertFalse(field["value"])
            self.assertTrue(field["agree"])


class TestDataKind(unittest.TestCase):
    def test_all_rows_are_simulated_and_not_native_data_kind(self):
        for row in helpers.rows():
            field = row["fields"]["data_kind"]
            self.assertEqual(field["value"], "simulated_learner_fixture")
            self.assertEqual(field["evidence_state"], "externally_derived")
            self.assertEqual(field["verification"], "partially_verified")
            self.assertTrue(field["sample_simulation_is_simulated"])
            self.assertTrue(field["gold_simulation"])
            self.assertFalse(field["original_sample_has_data_kind"])
            self.assertTrue(field["sample_linked_to_prompt_request"])
            self.assertTrue(field["sample_file"].startswith("samples/"))


if __name__ == "__main__":
    unittest.main()
