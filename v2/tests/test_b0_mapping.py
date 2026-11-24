"""Regression tests for the B0 four-field mapping and its V1 failure."""
from __future__ import annotations

import pathlib
import unittest

from v2 import build_evidence_ledger_v2 as ledger
from v2.tests.helpers import b0_record, b0_row

SNAPSHOT = pathlib.Path(r"F:\somethingProject\graduation-preflight-audit")


class B0MappingTests(unittest.TestCase):
    def test_shared_experiment_id_does_not_overwrite_four_field_keys(self):
        exp = "exp-shared"
        rows = [
            b0_row("S5", 1, 0, exp, "runA", "2026-11-13T09:17:59+08:00"),
            b0_row("S7", 1, 0, exp, "runA", "2026-11-13T09:20:37+08:00"),
            b0_row("S5", 2, 1, exp, "runB", "2026-11-13T09:31:10+08:00"),
            b0_row("S7", 2, 1, exp, "runB", "2026-11-13T09:31:32+08:00"),
        ]
        records = [
            b0_record("S5", 0, exp, "runA", "2026-11-13T09:17:59+08:00", "a:1"),
            b0_record("S7", 0, exp, "runA", "2026-11-13T09:20:37+08:00", "a:2"),
            b0_record("S5", 1, exp, "runB", "2026-11-13T09:31:10+08:00", "b:1"),
            b0_record("S7", 1, exp, "runB", "2026-11-13T09:31:32+08:00", "b:2"),
        ]
        stats = ledger.validate_b0_records(rows, records, expected_total=4)
        self.assertTrue(stats["b0_map_all"])
        self.assertEqual(stats["b0_map_unique_keys"], 4)
        self.assertEqual(stats["b0_map_legacy_key_collisions"], 2)
        old = ledger.legacy_b0_lookup(rows)
        self.assertEqual(len(old), 2)
        self.assertEqual(old[(exp, 0)]["sample_id"], "S7")
        self.assertEqual(old[(exp, 1)]["sample_id"], "S7")

    def test_s5_remainder_hits_s5_not_s7(self):
        exp = "exp-shared"
        rows = [
            b0_row("S5", 1, 0, exp, "runA", "2026-11-13T09:17:59+08:00"),
            b0_row("S7", 1, 0, exp, "runA", "2026-11-13T09:20:37+08:00"),
            b0_row("S5", 2, 0, exp, "runB", "2026-11-13T09:31:10+08:00"),
            b0_row("S7", 2, 0, exp, "runB", "2026-11-13T09:31:32+08:00"),
        ]
        records = [
            b0_record("S5", 0, exp, "runA", "2026-11-13T09:17:59+08:00", "a:1"),
            b0_record("S7", 0, exp, "runA", "2026-11-13T09:20:37+08:00", "a:2"),
            b0_record("S5", 0, exp, "runB", "2026-11-13T09:31:10+08:00", "b:1"),
            b0_record("S7", 0, exp, "runB", "2026-11-13T09:31:32+08:00", "b:2"),
        ]
        ledger.validate_b0_records(rows, records, expected_total=4)
        by_key = {ledger._b0_key(r): r for r in rows}
        hit = by_key[("S5", exp, 0, "runB")]
        self.assertEqual(hit["sample_id"], "S5")
        self.assertEqual(hit["ordinal"], 2)

    def test_duplicate_four_field_key_is_rejected(self):
        row = b0_row("S5", 1, 0, "exp", "runA", "2026-11-13T09:17:59+08:00")
        with self.assertRaises(ledger.B0MappingError):
            ledger.validate_b0_records([row, dict(row)], [b0_record(
                "S5", 0, "exp", "runA", "2026-11-13T09:17:59+08:00", "a:1")],
                expected_total=1)

    def test_missing_map_row_is_rejected(self):
        rows = [
            b0_row("S5", 1, 0, "exp", "runA", "2026-11-13T09:17:59+08:00"),
            b0_row("S7", 1, 0, "exp", "runA", "2026-11-13T09:20:37+08:00"),
        ]
        records = [
            b0_record("S5", 0, "exp", "runA", "2026-11-13T09:17:59+08:00", "a:1"),
            b0_record("S7", 0, "exp", "runA", "2026-11-13T09:20:37+08:00", "a:2"),
            b0_record("S7", 1, "exp", "runA", "2026-11-13T09:21:37+08:00", "a:3"),
        ]
        with self.assertRaises(ledger.B0MappingError):
            ledger.validate_b0_records(rows, records, expected_total=2)

    def test_run_dir_mismatch_is_rejected(self):
        row = b0_row("S5", 1, 0, "exp", "runA", "2026-11-13T09:17:59+08:00")
        rec = b0_record("S5", 0, "exp", "runB", "2026-11-13T09:17:59+08:00", "b:1")
        with self.assertRaises(ledger.B0MappingError) as ctx:
            ledger.validate_b0_records([row], [rec], expected_total=1)
        self.assertIn("missing_map_row", str(ctx.exception))

    def test_ordinal_mismatch_is_rejected(self):
        rows = [
            b0_row("S5", 2, 0, "exp", "runA", "2026-11-13T09:17:59+08:00"),
            b0_row("S5", 1, 1, "exp", "runA", "2026-11-13T09:20:37+08:00"),
        ]
        records = [
            b0_record("S5", 0, "exp", "runA", "2026-11-13T09:17:59+08:00", "a:1"),
            b0_record("S5", 1, "exp", "runA", "2026-11-13T09:20:37+08:00", "a:2"),
        ]
        with self.assertRaises(ledger.B0MappingError) as ctx:
            ledger.validate_b0_records(rows, records, expected_total=2)
        self.assertIn("ordinal", str(ctx.exception))

    @unittest.skipUnless((SNAPSHOT / "B0-REPEAT-MAP.md").exists(),
                         "snapshot checkout is not present")
    def test_real_b0_map_has_ten_unique_keys_and_six_legacy_pairs(self):
        rows = ledger.parse_b0_map((SNAPSHOT / "B0-REPEAT-MAP.md").read_text(encoding="utf-8"))
        self.assertEqual(len(rows), 10)
        self.assertEqual(len({ledger._b0_key(r) for r in rows}), 10)
        self.assertEqual(len(ledger.legacy_b0_lookup(rows)), 6)
        self.assertEqual(len({r["sample_id"] for r in rows}), 2)


if __name__ == "__main__":
    unittest.main()
