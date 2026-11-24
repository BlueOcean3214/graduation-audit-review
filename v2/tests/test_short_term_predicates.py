"""Short-term predicate tests: slot, block and actual payload are separate."""
from __future__ import annotations

import unittest

from v2 import build_evidence_ledger_v2 as ledger
from v2.tests.helpers import short_block


class ShortTermPredicateTests(unittest.TestCase):
    def test_no_short_slot_for_a(self):
        result = ledger.evaluate_short_term("ordinary user content", "A")
        pred = result["predicates"]
        self.assertFalse(pred["short_term_slot_enabled"]["value"])
        self.assertFalse(pred["short_term_block_present"]["value"])
        self.assertFalse(pred["short_term_payload_nonempty"]["value"])
        self.assertEqual(result["state"], "externally_derived")

    def test_slot_enabled_but_block_missing_is_unknown(self):
        result = ledger.evaluate_short_term("ordinary user content", "B")
        self.assertTrue(result["predicates"]["short_term_slot_enabled"]["value"])
        self.assertFalse(result["predicates"]["short_term_block_present"]["value"])
        self.assertEqual(result["state"], "unknown")
        self.assertIn("slot_enabled=True", result["evidence"]["parse_error"])

    def test_block_present_with_zero_history_is_not_nonempty(self):
        result = ledger.evaluate_short_term(short_block(feedback_count=0), "D")
        pred = result["predicates"]
        self.assertTrue(pred["short_term_slot_enabled"]["value"])
        self.assertTrue(pred["short_term_block_present"]["value"])
        self.assertFalse(pred["short_term_payload_nonempty"]["value"])
        self.assertEqual(result["state"], "externally_derived")
        self.assertEqual(pred["short_term_payload_nonempty"]["evidence"]["feedback_count"], 0)

    def test_block_present_with_history_is_nonempty(self):
        result = ledger.evaluate_short_term(short_block(feedback_count=4), "D")
        pred = result["predicates"]
        self.assertTrue(pred["short_term_slot_enabled"]["value"])
        self.assertTrue(pred["short_term_block_present"]["value"])
        self.assertTrue(pred["short_term_payload_nonempty"]["value"])

    def test_block_without_data_markers_is_unknown(self):
        text = ledger.SHORT_HEADER + "\nno data here"
        result = ledger.evaluate_short_term(text, "D")
        self.assertEqual(result["state"], "unknown")
        self.assertIn("markers", result["evidence"]["parse_error"])

    def test_block_for_group_without_slot_is_unknown(self):
        result = ledger.evaluate_short_term(short_block(feedback_count=1), "C")
        self.assertEqual(result["state"], "unknown")
        self.assertIn("slot_enabled=False", result["evidence"]["parse_error"])

    def test_frozen_boolean_is_not_silently_redefined(self):
        result = ledger.evaluate_short_term(short_block(feedback_count=1), "D")
        compat = result["frozen_field_compatibility"]
        self.assertFalse(compat["v2_redefines_original_field"])
        self.assertEqual(compat["decision"], "pending_advisor_confirmation")
        self.assertEqual(compat["candidate_meaning"], "short_term_block_present")


if __name__ == "__main__":
    unittest.main()
