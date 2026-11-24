"""Schema and documentation consistency tests (no third-party packages)."""

import json
import unittest
from pathlib import Path

from v3 import build_evidence_ledger_v3 as v3

ROOT = Path(__file__).resolve().parents[1]


class TestSchema(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schema = json.loads((ROOT / "historical-evidence.schema.json").read_text(encoding="utf-8"))

    def test_schema_id_and_versions_match_builder(self):
        self.assertEqual(self.schema["$schema"], "https://json-schema.org/draft/2020-12/schema")
        self.assertEqual(self.schema["properties"]["schema"]["const"], v3.SCHEMA_ID)
        self.assertEqual(self.schema["properties"]["builder_version"]["const"], v3.BUILDER_VERSION)
        self.assertEqual(self.schema["properties"]["segment"]["enum"], list(v3.SEGMENT_ORDER))

    def test_envelope_definition_has_eight_required_keys(self):
        envelope = self.schema["$defs"]["envelope"]
        self.assertEqual(
            envelope["required"],
            ["value", "evidence_state", "original_field_present", "source_refs",
             "rule_id", "rule_version", "verification", "limitations"],
        )
        self.assertEqual(envelope["properties"]["evidence_state"]["enum"], list(v3.EVIDENCE_STATES))
        self.assertEqual(envelope["properties"]["verification"]["enum"], list(v3.VERIFICATION_STATES))

    def test_memory_and_short_definitions_do_not_forge_values(self):
        entry = self.schema["$defs"]["memoryEntry"]
        self.assertEqual(
            entry["properties"]["subfields"]["required"],
            ["content", "memory_type", "subject_key", "strength",
             "gold_status", "memory_id", "runtime_status"],
        )
        self.assertEqual(
            entry["properties"]["subfields"]["additionalProperties"],
            {"$ref": "#/$defs/envelope"},
        )
        self.assertEqual(self.schema["$defs"]["memoryFlat"]["properties"]["status"]["type"], "null")
        short = self.schema["properties"]["fields"]["properties"]["short_term_injected"]
        self.assertEqual(short["properties"]["value"]["properties"]["short_term_injected"]["type"], "null")
        self.assertEqual(
            short["properties"]["frozen_field_compatibility"]["properties"]["semantics_status"]["const"],
            "pending_advisor_confirmation",
        )


class TestDocuments(unittest.TestCase):
    def read(self, name):
        return (ROOT / name).read_text(encoding="utf-8")

    def test_all_deliverable_documents_exist(self):
        for name in (
            "README.md",
            "HISTORICAL-EVIDENCE-CONTRACT.md",
            "FUTURE-PRODUCER-RECORDING-SPEC.md",
            "ADVISOR-DECISION-BRIEF-V3.md",
        ):
            self.assertGreater(len(self.read(name)), 1000, name)

    def test_contract_lists_every_state_and_forbids_substitution(self):
        text = self.read("HISTORICAL-EVIDENCE-CONTRACT.md")
        for state in v3.EVIDENCE_STATES:
            self.assertIn("`" + state + "`", text)
        for phrase in ("审计定位符不是", "复核提交不是", "§5.6.6", "两层验收分离"):
            self.assertIn(phrase, text)

    def test_advisor_brief_has_eight_decisions_and_no_approval_claim(self):
        text = self.read("ADVISOR-DECISION-BRIEF-V3.md")
        for number in range(1, 9):
            self.assertIn("D%d" % number, text)
        self.assertIn("不代替决定", text)
        self.assertIn("不构成契约修订批准", text)

    def test_producer_spec_matches_validate_required_fields(self):
        text = self.read("FUTURE-PRODUCER-RECORDING-SPEC.md")
        required = (
            "run_id", "base_sha", "runtime_source_commit", "runtime_worktree_clean",
            "runtime_patch_sha256", "knowledge_result_ids", "memory_injected",
            "short_term_slot_enabled", "short_term_block_present",
            "short_term_feedback_history_present", "difficult_flag", "data_kind",
            "config_sha256", "plan_sha256", "prompt_sha256", "injected_json_sha256",
            "injected_json_ref", "result_schema_version", "experiment_design_version",
            "generated_at", "model_alias", "model_snapshot_id",
        )
        for field in required:
            self.assertIn(field, text)


if __name__ == "__main__":
    unittest.main()
