"""Memory provenance tests: fields are split and status is never a direct read."""
from __future__ import annotations

import unittest

from v2 import build_evidence_ledger_v2 as ledger
from v2.tests.helpers import gold_memory, memory_prompt, sample_with_memories


def entry_for(gold, subject=None, strength=None):
    return {
        "type": gold["memory_type"],
        "subject": subject if subject is not None else gold["subject_label"],
        "content": gold["content"],
        "strength": gold["strength"] if strength is None else strength,
        "evidence_count": 5,
        "episode": 1,
        "evidence_feedback_ids": [1, 2],
        "updated_at": "2026-11-08T21:00:00",
    }


class MemoryProvenanceTests(unittest.TestCase):
    def test_runtime_status_is_inferred_not_direct(self):
        gold = gold_memory()
        sample = sample_with_memories([gold])
        result = ledger.build_memory_field(sample, "C", memory_prompt([entry_for(gold)]))
        self.assertEqual(result["state"], "partially_derived")
        self.assertEqual(result["evidence"]["section_5_6_6_status"], "NOT_COMPLETED")
        entry = result["value"][0]
        self.assertNotIn("status", entry)
        self.assertIn("gold_status", entry["subfields"])
        self.assertIn("runtime_status", entry["subfields"])
        self.assertEqual(entry["subfields"]["gold_status"]["state"], "gold_reference")
        self.assertEqual(entry["subfields"]["gold_status"]["value"], "active")
        runtime = entry["subfields"]["runtime_status"]
        self.assertEqual(runtime["state"], "inferred")
        self.assertEqual(runtime["value"], "active")
        self.assertEqual(runtime["verification"], "not_verified")
        self.assertFalse(runtime["section_5_6_6_compared"])
        self.assertTrue(runtime["basis"])
        self.assertTrue(runtime["blocked_by"])

    def test_unique_content_maps_type_subject_strength(self):
        gold = gold_memory(memory_type="task_topic", subject_key="algebra",
                           subject_label="Algebra practice", strength=0.6)
        sample = sample_with_memories([gold])
        result = ledger.build_memory_field(sample, "C", memory_prompt([entry_for(gold)]))
        entry = result["value"][0]
        self.assertEqual(entry["subfields"]["memory_type"]["value"], "task_topic")
        self.assertEqual(entry["subfields"]["subject_key"]["value"], "algebra")
        self.assertEqual(entry["subfields"]["strength"]["value"], 0.6)
        self.assertEqual(entry["gold_ref"]["content_match_count"], 1)
        self.assertEqual(result["evidence"]["matched_entries"], 1)

    def test_ambiguous_content_fails_closed(self):
        gold = gold_memory()
        duplicate = dict(gold, subject_key="beta", subject_label="Beta")
        sample = sample_with_memories([gold, duplicate])
        result = ledger.build_memory_field(sample, "C", memory_prompt([entry_for(gold)]))
        self.assertEqual(result["state"], "unknown")
        self.assertEqual(result["value"][0]["subfields"]["content"]["state"], "unknown")
        self.assertTrue(any(e["code"] == "memory_content" for e in result["evidence"]["errors"]))

    def test_count_mismatch_fails_closed(self):
        gold1 = gold_memory(subject_key="a", subject_label="A", content="content a")
        gold2 = gold_memory(subject_key="b", subject_label="B", content="content b")
        sample = sample_with_memories([gold1, gold2])
        result = ledger.build_memory_field(sample, "C", memory_prompt([entry_for(gold1)]))
        self.assertEqual(result["state"], "unknown")
        self.assertTrue(any(e["code"] == "memory_count" for e in result["evidence"]["errors"]))

    def test_type_mismatch_fails_closed(self):
        gold = gold_memory()
        bad = entry_for(gold)
        bad["type"] = "time_pattern"
        sample = sample_with_memories([gold])
        result = ledger.build_memory_field(sample, "C", memory_prompt([bad]))
        self.assertEqual(result["state"], "unknown")
        self.assertEqual(result["value"][0]["subfields"]["memory_type"]["state"], "conflicting")

    def test_subject_display_mismatch_is_recorded_not_hidden(self):
        gold = gold_memory(memory_type="time_pattern", subject_key="medium",
                           subject_label="medium",
                           content="初步观察：中等 任务近期 5 次实际用时约为预估的 2.2 倍")
        sample = sample_with_memories([gold], sample_id="S4")
        result = ledger.build_memory_field(sample, "C", memory_prompt([entry_for(gold, subject="中等")]))
        self.assertEqual(result["state"], "partially_derived")
        self.assertEqual(result["evidence"]["subject_label_mismatch_count"], 1)
        self.assertEqual(result["value"][0]["subfields"]["subject_key"]["value"], "medium")
        self.assertFalse(result["value"][0]["subfields"]["subject_key"]["evidence"]["prompt_subject_matches_label_or_key"])

    def test_nonactive_gold_does_not_become_runtime_active(self):
        gold = gold_memory(status="weakened", injected=False)
        sample = sample_with_memories([gold])
        result = ledger.build_memory_field(sample, "C", memory_prompt([entry_for(gold)]))
        self.assertEqual(result["state"], "unknown")
        runtime = result["value"][0]["subfields"]["runtime_status"]
        self.assertEqual(runtime["state"], "unknown")
        self.assertIsNone(runtime["value"])

    def test_no_memory_group_has_no_entries(self):
        gold = gold_memory()
        sample = sample_with_memories([gold])
        result = ledger.build_memory_field(sample, "A", "no memory block")
        self.assertEqual(result["state"], "externally_derived")
        self.assertEqual(result["value"], [])
        self.assertEqual(result["evidence"]["prompt_entry_count"], 0)


if __name__ == "__main__":
    unittest.main()
