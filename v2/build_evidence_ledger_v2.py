#!/usr/bin/env python3
"""Build the V2 externally-derived evidence ledger for the 165 frozen
graduation experiment records.

V2 is deliberately fail-closed:

* B0 is keyed by (sample_id, experiment_id, repeat_index, run_dir), never by
  the old (experiment_id, repeat_index) pair.
* memory_injected separates recorded content/type/subject/strength from the
  Gold reference status and from the *inferred* historical runtime status.
* short_term_injected is represented by three separate predicates, not one
  ambiguous Boolean.
* run_id and base_sha remain unrecoverable; the reviewed source commit is
  audit metadata, never a runtime base_sha.

The script only reads the snapshot and source repositories.  It writes only
inside its own output directory (default: the directory containing this file).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import subprocess
import sys

SNAPSHOT_REPO = "https://github.com/BlueOcean3214/graduation-preflight-audit"
SNAPSHOT_COMMIT = "7b99ad96db78167c490874af9c4b48484b6d6ef0"
SOURCE_REPO = "https://github.com/BlueOcean3214/AI-Study-Assistant"
SOURCE_COMMIT = "df155a5c145297bc5e6a085636fadfd6185586bd"
SCHEMA_ID = "graduation-derived-field-evidence/v2"
BUILDER_VERSION = "2.0.0"

SEVEN_FIELDS = (
    "run_id",
    "base_sha",
    "knowledge_result_ids",
    "memory_injected",
    "short_term_injected",
    "difficult_flag",
    "data_kind",
)

SEGMENTS = {
    "main-20261113T061051Z": "main",
    "suppl-subj-20261113T062711Z": "supplementary-subject",
    "suppl-s7empty-20261113T062822Z": "supplementary-s7empty",
    "b0-remainder-20261113T013105Z": "b0-legacy",
    "20261112T210000-20261113T011751Z": "b0-legacy",
    "20261112T210000-20261113T012031Z": "b0-legacy",
}
SEGMENT_ORDER = ("main", "supplementary-subject", "supplementary-s7empty", "b0-legacy")

GROUP_SLOTS = {
    "A": {"feedback": False, "short_term": False, "memory": False},
    "B": {"feedback": True, "short_term": True, "memory": False},
    "B0": {"feedback": True, "short_term": False, "memory": False, "summary": False},
    "C": {"feedback": False, "short_term": False, "memory": True},
    "D": {"feedback": True, "short_term": True, "memory": True},
    "C-subj": {"feedback": False, "short_term": False, "memory": True,
                "memory_scope": "subject"},
    "D-subj": {"feedback": True, "short_term": True, "memory": True,
                "memory_scope": "subject"},
}
MEMORY_GROUPS = {"C", "D", "C-subj", "D-subj"}
SUBJECT_FILTER = {"S5": "概率论"}

MEMORY_HEADER = "【真实长期学习记忆检索结果】"
SHORT_HEADER = "【学习者近期情况（程序统计，非模型总结）】"
SHORT_DATA_START = "<<<LEARNER_CONTEXT_DATA>>>"
SHORT_DATA_END = "<<<END>>>"
KNOWLEDGE_NONE = "本次没有知识库检索结果"
DIFFICULT_RULE = "最近一次反馈是 partial 且原因是任务难度太高"
B0_GROUP = "B0"
B0_EXPECTED_TOTAL = 10

EXECUTION_REPORT_BASELINE = "e5f97e9fd9d721af24ed5d7a6c047ff305fd3fcd"

CODE = {
    "agent_tools_sanitize": "agent_tools.py:203-219",
    "agent_tools_get_memory": "agent_tools.py:222-269",
    "agent_tools_status_filter": "agent_tools.py:267",
    "memory_service_retrieve": "memory_service.py:2117-2190",
    "derive_difficult": "agent_tools.py:414-435",
    "difficult_rule": "ai_service.py:159-182",
    "memory_fields": "agent_plan_draft.py:111-120",
    "memory_block": "agent_plan_draft.py:354-382",
    "draft_content": "agent_plan_draft.py:385-441",
    "group_slots": "experiments/graduation/build_prompts.py:44-67",
    "collect_inputs": "experiments/graduation/build_prompts.py:285-368",
    "group_inputs": "experiments/graduation/build_prompts.py:376-408",
    "subject_filter": "experiments/graduation/build_prompts.py:84",
    "seed_simulation": "experiments/graduation/seed_fixture.py:91-96",
    "config_hash": "experiments/graduation/plan_schedule.py:64-83",
    "plan_digest": "experiments/graduation/plan_schedule.py:236-238",
    "prompt_hash": "experiments/graduation/build_prompts.py:485-493",
    "result_fields": "experiments/graduation/run_experiment.py:664-677",
    "result_schema": "experiments/graduation/result_schema.py",
    "design_5_6_6": "docs/GRADUATION-EXPERIMENT-DESIGN.md §5.6.6",
    "design_3_4": "docs/GRADUATION-EXPERIMENT-DESIGN.md §3.4",
    "design_7_1": "docs/GRADUATION-EXPERIMENT-DESIGN.md §7.1",
}


class AuditError(RuntimeError):
    """Base class for a fail-closed audit build error."""


class B0MappingError(AuditError):
    """B0 mapping is not uniquely and consistently defined."""


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_text(text: str) -> str:
    return sha256_bytes(text.encode("utf-8"))


def canonical_json(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                       separators=(",", ":"), allow_nan=False)


def config_sha256(config) -> str:
    return sha256_text(canonical_json(config))


def plan_digest(plan) -> str:
    payload = {k: v for k, v in plan.items() if k != "plan_sha256"}
    return sha256_text(canonical_json(payload))


def split_prompt(text: str):
    pre = "===== SYSTEM =====\n"
    mid = "\n\n===== USER =====\n"
    if not (text.startswith(pre) and text.endswith("\n") and mid in text):
        raise AuditError("unexpected prompt envelope")
    body = text[len(pre):]
    idx = body.index(mid)
    return body[:idx], body[idx + len(mid):-1]


def prompt_hash(system: str, user: str) -> str:
    messages = [{"role": "system", "content": system},
                {"role": "user", "content": user}]
    return sha256_text(json.dumps(messages, ensure_ascii=False, sort_keys=True))


def parse_json_after(user: str, header: str, opener: str):
    idx = user.find(header)
    if idx < 0:
        return -1, None
    start = user.find(opener, idx)
    if start < 0:
        raise AuditError(f"header {header!r} has no JSON opener {opener!r}")
    value, consumed = json.JSONDecoder().raw_decode(user[start:])
    return idx, value


def feedback_latest(sample):
    feedback = sample.get("feedbacks") or []
    if not feedback:
        return None
    last = feedback[-1]
    return {
        "index": len(feedback),
        "task": last.get("task"),
        "status": last.get("status"),
        "reason": last.get("reason"),
        "created_at": last.get("created_at"),
    }


# ---------------------------------------------------------------------------
# B0 mapping: four-field key and fail-closed consistency checks
# ---------------------------------------------------------------------------

def parse_b0_map(text: str):
    """Parse B0-REPEAT-MAP.md.

    The table has 18 columns.  The fourth field key is the tuple
    (sample_id, experiment_id, repeat_index, run_dir); ordinal is *not* part
    of the key because it is the value being checked.
    """
    rows = []
    for lineno, line in enumerate(text.splitlines(), 1):
        if not line.startswith("| S"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) != 18:
            raise B0MappingError(
                f"B0 map line {lineno}: expected 18 cells, got {len(cells)}")
        sample, ordinal, sample_col, group, repeat, experiment_id, run_dir = cells[:7]
        try:
            ordinal_i = int(ordinal)
            repeat_i = int(repeat)
        except ValueError as exc:
            raise B0MappingError(
                f"B0 map line {lineno}: non-integer ordinal/repeat") from exc
        if sample != sample_col:
            raise B0MappingError(
                f"B0 map line {lineno}: sample column mismatch {sample!r} != {sample_col!r}")
        if group != B0_GROUP:
            raise B0MappingError(
                f"B0 map line {lineno}: expected group B0, got {group!r}")
        if ordinal_i < 1:
            raise B0MappingError(f"B0 map line {lineno}: ordinal must be >= 1")
        rows.append({
            "line_number": lineno,
            "sample_id": sample,
            "ordinal": ordinal_i,
            "group": group,
            "repeat_index": repeat_i,
            "experiment_id": experiment_id,
            "run_dir": run_dir,
            "generated_at": cells[16],
        })
    if not rows:
        raise B0MappingError("B0 map has no data rows")

    keys = [(r["sample_id"], r["experiment_id"], r["repeat_index"], r["run_dir"])
            for r in rows]
    if len(set(keys)) != len(keys):
        seen = set()
        duplicates = []
        for key in keys:
            if key in seen:
                duplicates.append(key)
            seen.add(key)
        raise B0MappingError(
            "B0 map contains duplicate four-field keys: "
            + repr(duplicates))
    return rows


def _b0_key(item):
    return (item["sample_id"], item["experiment_id"],
            item["repeat_index"], item["run_dir"])


def validate_b0_records(rows, records, expected_total=B0_EXPECTED_TOTAL):
    """Validate map rows against actual B0 records.

    Returns a statistics dict and raises B0MappingError on any inconsistency.
    A record without an exact map row is never counted as matched.
    """
    row_by_key = {}
    for row in rows:
        key = _b0_key(row)
        row_by_key[key] = row
    record_keys = [_b0_key(r) for r in records]
    if len(set(record_keys)) != len(record_keys):
        raise B0MappingError("B0 records contain duplicate four-field keys")

    errors = []
    stats = {
        "b0_map_expected_total": expected_total,
        "b0_map_rows": len(rows),
        "b0_map_unique_keys": len(row_by_key),
        "b0_map_record_count": len(records),
        "b0_map_matched": 0,
        "b0_map_sample_matches": 0,
        "b0_map_experiment_matches": 0,
        "b0_map_repeat_matches": 0,
        "b0_map_run_dir_matches": 0,
        "b0_map_ordinal_matches": 0,
        "b0_map_legacy_key_collisions": 0,
        "b0_map_errors": [],
        "b0_map_all": False,
    }

    legacy = {}
    for row in rows:
        legacy_key = (row["experiment_id"], row["repeat_index"])
        legacy.setdefault(legacy_key, []).append(row)
    stats["b0_map_legacy_key_collisions"] = sum(
        1 for values in legacy.values() if len(values) > 1)

    if len(rows) != expected_total:
        errors.append({"code": "map_rows", "detail":
                       f"expected {expected_total} map rows, got {len(rows)}"})
    if len(row_by_key) != expected_total:
        errors.append({"code": "map_unique_keys", "detail":
                       f"expected {expected_total} unique map keys, got {len(row_by_key)}"})
    if len(records) != expected_total:
        errors.append({"code": "record_count", "detail":
                       f"expected {expected_total} B0 records, got {len(records)}"})

    by_sample = {}
    for rec in records:
        by_sample.setdefault(rec["sample_id"], []).append(rec)
    ordinal_expected = {}
    for sample_id, sample_records in by_sample.items():
        ordered = sorted(sample_records, key=lambda r: (r.get("generated_at") or "",
                                                        r.get("audit_locator") or ""))
        for rank, rec in enumerate(ordered, 1):
            ordinal_expected[rec["audit_locator"]] = rank
            if not rec.get("generated_at"):
                errors.append({"code": "generated_at", "detail":
                               f"{rec['audit_locator']}: missing generated_at"})

    seen_record_keys = set()
    for rec in records:
        key = _b0_key(rec)
        seen_record_keys.add(key)
        row = row_by_key.get(key)
        if row is None:
            errors.append({"code": "missing_map_row", "detail": rec["audit_locator"]})
            continue
        stats["b0_map_sample_matches"] += int(row["sample_id"] == rec["sample_id"])
        stats["b0_map_experiment_matches"] += int(
            row["experiment_id"] == rec["experiment_id"])
        stats["b0_map_repeat_matches"] += int(
            row["repeat_index"] == rec["repeat_index"])
        stats["b0_map_run_dir_matches"] += int(row["run_dir"] == rec["run_dir"])
        expected_ordinal = ordinal_expected.get(rec["audit_locator"])
        ordinal_ok = expected_ordinal == row["ordinal"]
        stats["b0_map_ordinal_matches"] += int(ordinal_ok)
        if not ordinal_ok:
            errors.append({"code": "ordinal", "detail":
                           f"{rec['audit_locator']}: map ordinal={row['ordinal']} "
                           f"chronological rank={expected_ordinal}"})
        all_fields = (row["sample_id"] == rec["sample_id"]
                      and row["experiment_id"] == rec["experiment_id"]
                      and row["repeat_index"] == rec["repeat_index"]
                      and row["run_dir"] == rec["run_dir"])
        if all_fields and ordinal_ok:
            stats["b0_map_matched"] += 1
        else:
            errors.append({"code": "field_mismatch", "detail": rec["audit_locator"]})

    for row in rows:
        if _b0_key(row) not in seen_record_keys:
            errors.append({"code": "unused_map_row", "detail":
                           f"B0 map line {row['line_number']}: {_b0_key(row)}"})

    stats["b0_map_errors"] = errors
    stats["b0_map_all"] = (
        not errors
        and stats["b0_map_rows"] == expected_total
        and stats["b0_map_unique_keys"] == expected_total
        and stats["b0_map_record_count"] == expected_total
        and stats["b0_map_matched"] == expected_total
        and stats["b0_map_sample_matches"] == expected_total
        and stats["b0_map_experiment_matches"] == expected_total
        and stats["b0_map_repeat_matches"] == expected_total
        and stats["b0_map_run_dir_matches"] == expected_total
        and stats["b0_map_ordinal_matches"] == expected_total
    )
    if not stats["b0_map_all"]:
        raise B0MappingError(json.dumps(stats, ensure_ascii=False, indent=2))
    return stats


def legacy_b0_lookup(rows):
    """Reproduce the V1 lookup for regression tests only.

    This is intentionally *not* used by the V2 builder.  It demonstrates why
    the old key loses rows when S5 and S7 share an experiment_id.
    """
    mapping = {}
    for row in rows:
        mapping[(row["experiment_id"], row["repeat_index"])] = row
    return mapping


# ---------------------------------------------------------------------------
# Prompt readers
# ---------------------------------------------------------------------------

def parse_memory_block(user: str):
    idx, entries = parse_json_after(user, MEMORY_HEADER, "[")
    if idx < 0:
        return -1, []
    if not isinstance(entries, list):
        raise AuditError("memory block is not a list")
    return idx, entries


def evaluate_short_term(user: str, group: str):
    """Compute the three short-term predicates independently.

    payload_nonempty is based on the learner-history evidence count, not just
    on the presence of a JSON object.  S7-empty has a block (and a payload
    object) but zero feedback rows; that is the five-record difference between
    block_present and payload_nonempty.
    """
    if group not in GROUP_SLOTS:
        raise AuditError(f"unknown group {group!r}")
    slot_enabled = bool(GROUP_SLOTS[group].get("short_term"))
    block_present = SHORT_HEADER in user
    parse_error = None
    payload = None
    feedback_count = None
    plan_text = None
    if block_present:
        header_idx = user.find(SHORT_HEADER)
        start = user.find(SHORT_DATA_START, header_idx)
        end = user.find(SHORT_DATA_END, start + len(SHORT_DATA_START)) if start >= 0 else -1
        if start < 0 or end < 0:
            parse_error = "short-term block markers are missing"
        else:
            raw = user[start + len(SHORT_DATA_START):end].strip()
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError as exc:
                parse_error = f"short-term payload is not JSON: {exc}"
            else:
                if not isinstance(payload, dict):
                    parse_error = "short-term payload is not an object"
                else:
                    progress = payload.get("学习进度")
                    if not isinstance(progress, dict):
                        parse_error = "short-term payload lacks 学习进度 object"
                    else:
                        feedback_count = progress.get("已读取反馈数")
                        if not isinstance(feedback_count, int) or feedback_count < 0:
                            parse_error = "short-term 已读取反馈数 is not a non-negative integer"
                    plan_text = payload.get("今日计划")
    if block_present != slot_enabled:
        parse_error = (parse_error + "; " if parse_error else "") + (
            f"slot_enabled={slot_enabled} but block_present={block_present}")
    payload_nonempty = bool(feedback_count and feedback_count > 0) if parse_error is None else False

    def predicate(value, evidence):
        return {"value": bool(value),
                "state": "externally_derived" if parse_error is None else "unknown",
                "evidence": evidence}

    return {
        "state": "externally_derived" if parse_error is None else "unknown",
        "semantics": "three_separate_predicates",
        "predicates": {
            "short_term_slot_enabled": predicate(slot_enabled, {
                "group": group,
                "group_slots": dict(GROUP_SLOTS[group]),
                "basis": "experiment design matrix + build_prompts.GROUP_SLOTS",
            }),
            "short_term_block_present": predicate(block_present, {
                "section_title": SHORT_HEADER,
                "marker_found": SHORT_HEADER in user,
                "basis": "literal marker in prompt user content",
            }),
            "short_term_payload_nonempty": predicate(payload_nonempty, {
                "feedback_count": feedback_count,
                "plan": plan_text,
                "criteria": "已读取反馈数 > 0",
                "payload_parsed": payload is not None,
                "basis": "parsed learner-context JSON, not header presence",
            }),
        },
        "evidence": {
            "parse_error": parse_error,
            "payload": payload,
            "code_refs": [CODE["draft_content"], CODE["group_inputs"]],
        },
        "frozen_field_compatibility": {
            "original_field": "short_term_injected",
            "original_definition": "§7.1 Boolean; the frozen design does not "
                                   "further split slot, block and payload semantics",
            "v2_redefines_original_field": False,
            "candidate_meaning": "short_term_block_present",
            "decision": "pending_advisor_confirmation",
        },
    }


# ---------------------------------------------------------------------------
# Field builders
# ---------------------------------------------------------------------------

def _subfield(state, value, evidence, **extra):
    payload = {"state": state, "value": value, "evidence": evidence}
    payload.update(extra)
    return payload


def build_memory_field(sample, group, user):
    """Build memory_injected with per-subfield provenance.

    The prompt has no memory_id and no status.  A memory entry is mapped to
    Gold by exact unique content; type/subject_key/strength are external
    derivations.  Gold status is stored separately.  Historical runtime status
    is explicitly inferred, never presented as a direct read.
    """
    mem_idx, entries = parse_memory_block(user)
    gold_memories = sample.get("gold_standard", {}).get("memories", [])
    expected = []
    if group in MEMORY_GROUPS:
        expected = [m for m in gold_memories if m.get("injected") is True]
        if group in ("C-subj", "D-subj"):
            expected = [m for m in expected if m.get("subject_key") == "概率论"]

    errors = []
    built = []
    type_matches = 0
    strength_matches = 0
    subject_label_matches = 0
    subject_label_mismatches = []
    matched = 0
    runtime_inferred = 0
    runtime_unknown = 0

    for pos, entry in enumerate(entries):
        content = entry.get("content")
        hits = [i for i, m in enumerate(gold_memories) if m.get("content") == content]
        if len(hits) != 1:
            errors.append({"code": "memory_content", "index": pos,
                           "detail": f"gold content matches={len(hits)}"})
            built.append({
                "index": pos,
                "content": content,
                "subfields": {
                    "content": _subfield("unknown", content, {
                        "source": "prompt.memory_block",
                        "gold_match_count": len(hits),
                    }),
                    "memory_type": _subfield("unknown", None, {"reason": "content_not_unique"}),
                    "subject_key": _subfield("unknown", None, {"reason": "content_not_unique"}),
                    "strength": _subfield("unknown", None, {"reason": "content_not_unique"}),
                    "gold_status": _subfield("unknown", None, {"reason": "content_not_unique"}),
                    "runtime_status": _subfield(
                        "unknown", None,
                        {"reason": "content_not_unique"},
                        verification="not_verified",
                        section_5_6_6_compared=False),
                },
                "gold_ref": None,
            })
            continue

        gold_index = hits[0]
        gold = gold_memories[gold_index]
        matched += 1
        prompt_type = entry.get("type")
        prompt_subject = entry.get("subject")
        prompt_strength = entry.get("strength")
        type_ok = prompt_type == gold.get("memory_type")
        strength_ok = prompt_strength == gold.get("strength")
        subject_ok = prompt_subject in (gold.get("subject_label"), gold.get("subject_key"))
        type_matches += int(type_ok)
        strength_matches += int(strength_ok)
        subject_label_matches += int(subject_ok)
        if not subject_ok:
            subject_label_mismatches.append({
                "index": pos,
                "prompt_subject": prompt_subject,
                "gold_subject_label": gold.get("subject_label"),
                "gold_subject_key": gold.get("subject_key"),
                "content": content,
            })
        if not type_ok:
            errors.append({"code": "memory_type", "index": pos,
                           "detail": f"prompt={prompt_type!r} gold={gold.get('memory_type')!r}"})
        if not strength_ok:
            errors.append({"code": "memory_strength", "index": pos,
                           "detail": f"prompt={prompt_strength!r} gold={gold.get('strength')!r}"})

        gold_status = gold.get("status")
        gold_injected = gold.get("injected") is True
        if gold_status == "active" and gold_injected:
            runtime_basis = [
                "Gold reference says status=active and injected=true",
                "historical consumer path get_learning_memory() passes status='active' to retrieve()",
                "prompt carries no status or memory_id, so runtime status was not directly recorded",
            ]
            runtime_blocked = [
                "runtime_base_sha_unrecoverable",
                "injected_json_absent",
                "prompt_omits_status",
                "reviewed_source_commit_is_not_runtime_proof",
            ]
            runtime = _subfield(
                "inferred", "active",
                {
                    "basis": runtime_basis,
                    "code_refs": [CODE["agent_tools_get_memory"],
                                  CODE["agent_tools_status_filter"],
                                  CODE["agent_tools_sanitize"],
                                  CODE["memory_fields"]],
                    "confidence": "low",
                    "verification": "not_verified",
                    "blocked_by": runtime_blocked,
                    "section_5_6_6_compared": False,
                },
                basis=runtime_basis,
                confidence="low",
                verification="not_verified",
                blocked_by=runtime_blocked,
                section_5_6_6_compared=False,
            )
            runtime_inferred += 1
        else:
            runtime = _subfield(
                "unknown", None,
                {
                    "reason": "Gold status/injected does not support an active inference",
                    "gold_status": gold_status,
                    "gold_injected": gold_injected,
                    "verification": "not_verified",
                    "section_5_6_6_compared": False,
                },
                verification="not_verified",
                section_5_6_6_compared=False,
            )
            runtime_unknown += 1
            errors.append({"code": "memory_nonactive", "index": pos,
                           "detail": f"gold status={gold_status!r} injected={gold_injected}"})

        built.append({
            "index": pos,
            "content": content,
            "subfields": {
                "content": _subfield("externally_derived", content, {
                    "source": "prompt.memory_block",
                    "gold_match_count": 1,
                    "gold_index": gold_index,
                }),
                "memory_type": _subfield("externally_derived" if type_ok else "conflicting",
                                         gold.get("memory_type"), {
                    "prompt_type": prompt_type,
                    "gold_memory_type": gold.get("memory_type"),
                }),
                "subject_key": _subfield("externally_derived", gold.get("subject_key"), {
                    "prompt_subject": prompt_subject,
                    "gold_subject_label": gold.get("subject_label"),
                    "prompt_subject_matches_label_or_key": subject_ok,
                    "basis": "unique exact content match to Gold; key is Gold metadata",
                }),
                "strength": _subfield("externally_derived" if strength_ok else "conflicting",
                                      gold.get("strength"), {
                    "prompt_strength": prompt_strength,
                    "gold_strength": gold.get("strength"),
                }),
                "gold_status": _subfield("gold_reference", gold_status, {
                    "source": f"samples/{sample.get('sample_id')}.json#gold_standard.memories[{gold_index}].status",
                    "meaning": "fixture expectation only; not a runtime read",
                }),
                "runtime_status": runtime,
            },
            "gold_ref": {
                "file": f"samples/{sample.get('sample_id')}.json",
                "index": gold_index,
                "content_match_count": 1,
            },
        })

    if len(entries) != len(expected):
        errors.append({"code": "memory_count", "detail":
                       f"got={len(entries)} expected={len(expected)}"})
    if mem_idx >= 0 and group not in MEMORY_GROUPS:
        errors.append({"code": "unexpected_memory_block", "detail": group})

    state = "unknown" if errors else ("partially_derived" if entries else "externally_derived")
    return {
        "field": "memory_injected",
        "state": state,
        "evidence_model": "per_subfield",
        "value": built,
        "evidence": {
            "prompt_block_present": mem_idx >= 0,
            "prompt_entry_count": len(entries),
            "expected_injected_count": len(expected),
            "group_memory_slot_enabled": group in MEMORY_GROUPS,
            "subject_filter": SUBJECT_FILTER.get(sample.get("sample_id")) if group in ("C-subj", "D-subj") else None,
            "matched_entries": matched,
            "type_matches": type_matches,
            "subject_label_matches": subject_label_matches,
            "subject_label_mismatches": subject_label_mismatches,
            "subject_label_mismatch_count": len(subject_label_mismatches),
            "strength_matches": strength_matches,
            "runtime_status_inferred_active": runtime_inferred,
            "runtime_status_unknown": runtime_unknown,
            "injected_json_reference_present": False,
            "section_5_6_6_status": "NOT_COMPLETED",
            "section_5_6_6_reason": "no injected.json in snapshot; runtime base_sha unrecoverable; prompt omits status",
            "errors": errors,
            "code_refs": [CODE["agent_tools_sanitize"], CODE["agent_tools_get_memory"],
                          CODE["agent_tools_status_filter"], CODE["memory_service_retrieve"],
                          CODE["memory_fields"], CODE["memory_block"],
                          CODE["design_5_6_6"]],
        },
        "caveat": "每条的 runtime_status=active 是 inferred（低置信度），依据是 Gold "
                  "active/injected 与当前源码只传 status='active'；不是运行时直接读取，"
                  "也不能证明历史运行使用了 reviewed_source_commit。",
    }


def build_knowledge_field(config, config_hash, plan_info, user, group):
    config_empty = config.get("knowledge_results") == []
    prompt_none = KNOWLEDGE_NONE in user
    errors = []
    if not config_empty:
        errors.append({"code": "config_not_empty"})
    if not prompt_none:
        errors.append({"code": "prompt_missing_no_knowledge_phrase"})
    binding = None
    if plan_info is not None:
        binding = {
            "plan_file": plan_info["file"],
            "config_sha256_matches_snapshot_config": plan_info["config_sha256_matches_snapshot_config"],
            "plan_sha256": plan_info["plan_sha256"],
        }
        if not plan_info["config_sha256_matches_snapshot_config"]:
            errors.append({"code": "plan_config_mismatch"})
    else:
        binding = {
            "state": "not_available_for_b0_legacy",
            "reason": "B0 legacy results have no plan.json/config_sha256 chain",
        }
    return {
        "field": "knowledge_result_ids",
        "state": "externally_derived" if not errors else "unknown",
        "value": [] if not errors else None,
        "scope": "empty_configuration_only",
        "evidence": {
            "config_knowledge_results": config.get("knowledge_results"),
            "config_knowledge_search_failed": config.get("knowledge_search_failed"),
            "config_sha256_recomputed": config_hash,
            "prompt_declares_no_knowledge_results": prompt_none,
            "prompt_phrase": KNOWLEDGE_NONE,
            "plan_binding": binding,
            "b0_legacy_prompt_only": group == B0_GROUP,
            "code_refs": [CODE["collect_inputs"], CODE["config_hash"], CODE["prompt_hash"]],
            "errors": errors,
        },
        "limitations": [
            "只证明本批 config.knowledge_results=[] 的空配置情形；不能推广到非空检索结果。",
            "B0 legacy 没有 config→plan→record 哈希链，仅由 prompt 文本明示无检索结果支撑。",
        ],
    }


def build_difficult_field(sample, group, user):
    latest = feedback_latest(sample)
    raw = bool(latest and latest["status"] == "partial"
               and latest["reason"] == "任务难度太高")
    feedback_slot = bool(GROUP_SLOTS[group].get("feedback"))
    if group == B0_GROUP:
        value = False
    elif feedback_slot:
        value = raw
    else:
        value = False
    rule_present = DIFFICULT_RULE in user
    agree = (not rule_present) if group == B0_GROUP else (rule_present == value)
    return {
        "field": "difficult_flag",
        "state": "externally_derived" if agree else "unknown",
        "value": value,
        "evidence": {
            "latest_feedback": latest,
            "raw_condition_partial_and_reason": raw,
            "feedback_slot_enabled": feedback_slot,
            "b0_group_fixed_false": group == B0_GROUP,
            "dynamic_rule_present_in_prompt": rule_present,
            "agree": agree,
            "code_refs": [CODE["derive_difficult"], CODE["difficult_rule"],
                          CODE["group_slots"]],
        },
    }


def build_data_kind_field(sample, sample_linked):
    sim = sample.get("simulation", {})
    gold = sample.get("gold_standard", {})
    ok = (sim.get("is_simulated") is True and gold.get("simulation") is True
          and sample_linked)
    original_has = "data_kind" in sample
    return {
        "field": "data_kind",
        "state": "externally_derived" if ok else "unknown",
        "value": "simulated_learner_fixture" if ok else None,
        "evidence": {
            "sample_file": f"samples/{sample.get('sample_id')}.json",
            "sample_simulation_is_simulated": sim.get("is_simulated"),
            "gold_simulation": gold.get("simulation"),
            "sample_linked_to_prompt_request": sample_linked,
            "seed_fixture_requires_is_simulated": True,
            "original_sample_has_data_kind": original_has,
            "design_requirement": "§3.4 requires data_kind in sample files",
            "code_refs": [CODE["seed_simulation"], CODE["design_3_4"]],
        },
        "provenance_note": "由样本 provenance（simulation.is_simulated=true 且 "
                           "gold_standard.simulation=true）派生；样本文件本身没有 §3.4 "
                           "要求的 data_kind 字段，故不是原始记录直接生成的值。",
    }


def build_unrecoverable_fields(rec, audit_locator, experiment_id):
    batch_value = f"batch:{experiment_id}" if experiment_id else None
    run_id = {
        "field": "run_id",
        "recorded_at_generation": False,
        "state": "unrecoverable",
        "value": None,
        "reason": "生产器从未写入 run_id；结果记录字段集不含该字段，事后无法还原生成时刻的 run 标识。",
        "traceability": {
            "audit_locator": audit_locator,
            "audit_locator_kind": "external_audit_identifier_not_run_id",
            "derived_batch_locator": {
                "state": "derived_identifier",
                "value": batch_value,
                "basis": "experiment_id present in original record",
                "is_original_run_id": False,
            },
        },
        "evidence": {
            "record_has_field": "run_id" in rec,
            "code_refs": [CODE["result_fields"], CODE["design_7_1"]],
        },
    }
    base_sha = {
        "field": "base_sha",
        "recorded_at_generation": False,
        "state": "unrecoverable",
        "value": None,
        "runtime_base_sha": {"value": None, "state": "unrecoverable"},
        "reviewed_source_commit": SOURCE_COMMIT,
        "reviewed_source_commit_scope": "audit_metadata_only",
        "runtime_source_version_verified": False,
        "reason": "运行器未在开始时记录 git HEAD/工作树状态；执行报告中的基线只是报告声明，不能证明运行当时工作树干净或确为该提交。",
        "evidence": {
            "record_has_field": "base_sha" in rec,
            "execution_report_baseline": EXECUTION_REPORT_BASELINE,
            "execution_report_baseline_is_proof": False,
            "base_sha_not_substituted_by_reviewed_commit": True,
            "code_refs": [CODE["result_fields"], CODE["result_schema"],
                          CODE["design_7_1"]],
        },
    }
    return run_id, base_sha


# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------

def _read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _verify_git(path: pathlib.Path, expected_commit: str, label: str):
    try:
        head = subprocess.check_output(
            ["git", "-C", str(path), "rev-parse", "HEAD"], text=True).strip()
        status = subprocess.check_output(
            ["git", "-C", str(path), "status", "--porcelain"], text=True).strip()
    except (OSError, subprocess.CalledProcessError) as exc:
        raise AuditError(f"cannot verify {label} git state: {exc}") from exc
    if head != expected_commit:
        raise AuditError(f"{label} HEAD {head} != pinned {expected_commit}")
    if status:
        raise AuditError(f"{label} worktree is dirty:\n{status}")
    return head


def _load_records(audit_root: pathlib.Path):
    records = []
    for run_dir in sorted((audit_root / "runs").iterdir()):
        if not run_dir.is_dir():
            continue
        if run_dir.name not in SEGMENTS:
            raise AuditError(f"unexpected run directory {run_dir.name}")
        segment = SEGMENTS[run_dir.name]
        result_file = run_dir / "results.jsonl"
        for lineno, line in enumerate(result_file.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError as exc:
                raise AuditError(f"{result_file}:{lineno}: {exc}") from exc
            records.append({
                "run_dir": run_dir.name,
                "segment": segment,
                "line_number": lineno,
                "line": line,
                "record": rec,
                "audit_locator": f"runs/{run_dir.name}/results.jsonl:{lineno}",
            })
    return records


def _load_plans(audit_root: pathlib.Path):
    plans = {}
    for path in sorted(audit_root.glob("runs/*/plan.json")):
        plans[path.parent.name] = _read_json(path)
    return plans


def _plan_info(plan, rec, config_hash):
    tasks = {}
    for block in plan.get("blocks", []):
        block_sample_id = block.get("sample_id")
        for task in block.get("tasks", []):
            key = (block_sample_id, task.get("group"), task.get("repeat_index"))
            if key in tasks:
                raise AuditError(f"duplicate plan task {key}")
            tasks[key] = task
    key = (rec.get("sample_id"), rec.get("group"), rec.get("repeat_index"))
    task = tasks.get(key)
    in_plan = task is not None
    plan_seq_ok = bool(task) and task.get("plan_seq") == rec.get("plan_seq")
    round_ok = bool(task) and task.get("round_index") == rec.get("round_index")
    sha_match = rec.get("plan_sha256") == plan.get("plan_sha256")
    cfg_match = plan.get("config_sha256") == config_hash
    digest_ok = plan.get("plan_sha256") == plan_digest(plan)
    return {
        "file": None,
        "identity_in_plan": in_plan,
        "plan_seq_matches_record": plan_seq_ok,
        "round_index_matches_record": round_ok,
        "plan_sha256_matches_record": sha_match,
        "config_sha256_matches_snapshot_config": cfg_match,
        "plan_sha256_matches_plan_digest": digest_ok,
        "plan_sha256": plan.get("plan_sha256"),
        "config_sha256": plan.get("config_sha256"),
    }


def _b0_records(records):
    out = []
    for item in records:
        if item["segment"] != "b0-legacy":
            continue
        rec = item["record"]
        out.append({
            "sample_id": rec.get("sample_id"),
            "experiment_id": rec.get("experiment_id"),
            "repeat_index": rec.get("repeat_index"),
            "run_dir": item["run_dir"],
            "generated_at": rec.get("generated_at"),
            "audit_locator": item["audit_locator"],
        })
    return out


def _segment_stats(rows):
    out = {}
    for segment in SEGMENT_ORDER:
        selected = [r for r in rows if r["segment"] == segment]
        out[segment] = {
            "records": len(selected),
            "memory_entries": sum(len(r["fields"]["memory_injected"]["value"]) for r in selected),
            "memory_records": sum(1 for r in selected if r["fields"]["memory_injected"]["value"]),
            "short_term_slot_enabled_true": sum(
                1 for r in selected if r["fields"]["short_term_injected"]["predicates"]["short_term_slot_enabled"]["value"]),
            "short_term_block_present_true": sum(
                1 for r in selected if r["fields"]["short_term_injected"]["predicates"]["short_term_block_present"]["value"]),
            "short_term_payload_nonempty_true": sum(
                1 for r in selected if r["fields"]["short_term_injected"]["predicates"]["short_term_payload_nonempty"]["value"]),
            "difficult_true": sum(1 for r in selected if r["fields"]["difficult_flag"]["value"] is True),
            "knowledge_empty": sum(1 for r in selected if r["fields"]["knowledge_result_ids"]["value"] == []),
            "field_states": {
                name: {
                    state: sum(1 for r in selected if r["fields"][name]["state"] == state)
                    for state in sorted({r["fields"][name]["state"] for r in selected})
                }
                for name in SEVEN_FIELDS
            },
        }
    return out


def build_ledger(audit_root: pathlib.Path, source_root: pathlib.Path,
                 out_dir: pathlib.Path, verify_baseline=True,
                 expected_records=165, expected_segments=None):
    if verify_baseline:
        _verify_git(audit_root, SNAPSHOT_COMMIT, "snapshot")
        _verify_git(source_root, SOURCE_COMMIT, "source")

    config = _read_json(audit_root / "config" / "config.json")
    config_hash = config_sha256(config)
    samples = {}
    for path in sorted((audit_root / "samples").glob("*.json")):
        data = _read_json(path)
        samples[data["sample_id"]] = data
    plans = _load_plans(audit_root)
    b0_rows = parse_b0_map((audit_root / "B0-REPEAT-MAP.md").read_text(encoding="utf-8"))
    records = _load_records(audit_root)
    b0_stats = validate_b0_records(b0_rows, _b0_records(records))
    b0_info_by_locator = {}
    for item in records:
        if item["segment"] != "b0-legacy":
            continue
        rec = item["record"]
        row = next((r for r in b0_rows
                    if _b0_key(r) == (rec.get("sample_id"), rec.get("experiment_id"),
                                      rec.get("repeat_index"), item["run_dir"])), None)
        if row is None:
            raise AuditError(
                f"{item['audit_locator']}: no exact four-field B0 map row")
        b0_info_by_locator[item["audit_locator"]] = {
            "state": "externally_derived",
            "ordinal": row["ordinal"],
            "map_line_number": row["line_number"],
            "mapped_via": "B0-REPEAT-MAP.md",
            "key": {
                "sample_id": rec.get("sample_id"),
                "experiment_id": rec.get("experiment_id"),
                "repeat_index": rec.get("repeat_index"),
                "run_dir": item["run_dir"],
            },
            "repeat_index_collides_across_run_dirs": True,
        }

    rows = []
    seen_locators = set()
    seen_identities = set()
    errors = []
    for item in records:
        rec = item["record"]
        sid = rec.get("sample_id")
        group = rec.get("group")
        run_dir = audit_root / "runs" / item["run_dir"]
        if sid not in samples:
            raise AuditError(f"unknown sample {sid!r}")
        sample = samples[sid]
        prompt_text = (run_dir / rec["prompt_ref"]).read_text(encoding="utf-8")
        system, user = split_prompt(prompt_text)
        recomputed = prompt_hash(system, user)
        hash_ok = recomputed == rec.get("prompt_sha256")
        chars_ok = len(user) == rec.get("prompt_chars")
        if not hash_ok or not chars_ok:
            errors.append({"code": "prompt", "detail":
                           f"{item['audit_locator']} hash_ok={hash_ok} chars_ok={chars_ok}"})

        locator = item["audit_locator"]
        if locator in seen_locators:
            raise AuditError(f"duplicate audit locator {locator}")
        seen_locators.add(locator)
        identity = (rec.get("experiment_id"), sid, group, rec.get("repeat_index"))
        if identity in seen_identities:
            errors.append({"code": "identity", "detail": str(identity)})
        seen_identities.add(identity)

        plan = plans.get(item["run_dir"])
        plan_info = None
        if plan is not None:
            plan_info = _plan_info(plan, rec, config_hash)
            plan_info["file"] = f"runs/{item['run_dir']}/plan.json"
            if not all(plan_info[k] for k in (
                    "identity_in_plan", "plan_seq_matches_record",
                    "round_index_matches_record", "plan_sha256_matches_record",
                    "config_sha256_matches_snapshot_config",
                    "plan_sha256_matches_plan_digest")):
                errors.append({"code": "plan", "detail": locator})

        sample_linked = str(sample.get("current_user_request", "")) in user
        short = evaluate_short_term(user, group)
        memory = build_memory_field(sample, group, user)
        difficult = build_difficult_field(sample, group, user)
        knowledge = build_knowledge_field(config, config_hash, plan_info, user, group)
        data_kind = build_data_kind_field(sample, sample_linked)
        run_id, base_sha = build_unrecoverable_fields(
            rec, locator, rec.get("experiment_id"))

        for name, field in (("short", short), ("memory", memory),
                            ("difficult", difficult), ("knowledge", knowledge),
                            ("data_kind", data_kind)):
            if field.get("state") == "unknown":
                errors.append({"code": f"field_{name}", "detail": locator})

        row = {
            "schema": SCHEMA_ID,
            "builder_version": BUILDER_VERSION,
            "audit": {
                "snapshot_repository": SNAPSHOT_REPO,
                "snapshot_commit": SNAPSHOT_COMMIT,
                "reviewed_source_repository": SOURCE_REPO,
                "reviewed_source_commit": SOURCE_COMMIT,
                "runtime_source_version_verified": False,
                "evidence_states": {
                    "direct": "recorded in the original result at generation time",
                    "externally_derived": "derived from prompt/config/plan/sample evidence outside the record",
                    "gold_reference": "fixture Gold value, not a runtime read",
                    "inferred": "low-confidence inference from code path + Gold; not verified",
                    "unknown": "cannot be uniquely determined from available evidence",
                    "unrecoverable": "original field was never recorded and cannot be reconstructed",
                },
            },
            "source": {
                "repository": SNAPSHOT_REPO,
                "commit": SNAPSHOT_COMMIT,
                "result_file": f"runs/{item['run_dir']}/results.jsonl",
                "line_number": item["line_number"],
                "record_sha256": sha256_text(item["line"]),
                "record_sha256_basis": "UTF-8 bytes of the JSONL line as present in the normalized snapshot",
                "sample_id": sid,
                "group": group,
                "repeat_index": rec.get("repeat_index"),
                "experiment_id": rec.get("experiment_id"),
                "prompt_ref": rec.get("prompt_ref"),
                "prompt_sha256": rec.get("prompt_sha256"),
                "original_field_presence": {name: name in rec for name in SEVEN_FIELDS},
            },
            "segment": item["segment"],
            "audit_locator": locator,
            "derived_batch_locator": {
                "state": "derived_identifier",
                "value": f"batch:{rec.get('experiment_id')}",
                "basis": "experiment_id present in the original record",
                "is_original_run_id": False,
            },
            "b0": b0_info_by_locator.get(locator),
            "prompt": {
                "file": f"runs/{item['run_dir']}/{rec.get('prompt_ref')}",
                "sha256_recomputed": recomputed,
                "sha256_matches_record": hash_ok,
                "user_chars_recomputed": len(user),
                "prompt_chars_matches_record": chars_ok,
            },
            "plan": plan_info,
            "fields": {
                "run_id": run_id,
                "base_sha": base_sha,
                "knowledge_result_ids": knowledge,
                "memory_injected": memory,
                "short_term_injected": short,
                "difficult_flag": difficult,
                "data_kind": data_kind,
            },
        }
        rows.append(row)

    if len(rows) != expected_records:
        errors.append({"code": "record_count", "detail":
                       f"expected {expected_records}, got {len(rows)}"})
    if expected_segments:
        for segment, expected in expected_segments.items():
            actual = sum(1 for r in rows if r["segment"] == segment)
            if actual != expected:
                errors.append({"code": "segment_count", "detail":
                               f"{segment}: expected {expected}, got {actual}"})

    # Aggregate direct counts.  Do not infer these from expected constants.
    memory_entries = sum(len(r["fields"]["memory_injected"]["value"]) for r in rows)
    memory_records = sum(1 for r in rows if r["fields"]["memory_injected"]["value"])
    memory_matched = sum(r["fields"]["memory_injected"]["evidence"]["matched_entries"] for r in rows)
    memory_type_matches = sum(r["fields"]["memory_injected"]["evidence"]["type_matches"] for r in rows)
    memory_subject_matches = sum(r["fields"]["memory_injected"]["evidence"]["subject_label_matches"] for r in rows)
    memory_subject_mismatches = [
        {"audit_locator": r["audit_locator"], **m}
        for r in rows
        for m in r["fields"]["memory_injected"]["evidence"]["subject_label_mismatches"]
    ]
    memory_subject_key_resolved = sum(
        1 for r in rows for entry in r["fields"]["memory_injected"]["value"]
        if entry["subfields"]["subject_key"]["value"] is not None)
    memory_strength_matches = sum(r["fields"]["memory_injected"]["evidence"]["strength_matches"] for r in rows)
    runtime_inferred = sum(r["fields"]["memory_injected"]["evidence"]["runtime_status_inferred_active"] for r in rows)
    runtime_unknown = sum(r["fields"]["memory_injected"]["evidence"]["runtime_status_unknown"] for r in rows)
    short_slot = sum(r["fields"]["short_term_injected"]["predicates"]["short_term_slot_enabled"]["value"] for r in rows)
    short_block = sum(r["fields"]["short_term_injected"]["predicates"]["short_term_block_present"]["value"] for r in rows)
    short_payload = sum(r["fields"]["short_term_injected"]["predicates"]["short_term_payload_nonempty"]["value"] for r in rows)
    difficult_true = sum(r["fields"]["difficult_flag"]["value"] is True for r in rows)
    knowledge_empty = sum(r["fields"]["knowledge_result_ids"]["value"] == [] for r in rows)
    seven_present = sum(any(r["source"]["original_field_presence"].values()) for r in rows)
    prompt_hash_ok = sum(r["prompt"]["sha256_matches_record"] for r in rows)
    prompt_chars_ok = sum(r["prompt"]["prompt_chars_matches_record"] for r in rows)
    plan_ok = sum(1 for r in rows if r["plan"] and r["plan"]["identity_in_plan"])
    plan_sha_ok = sum(1 for r in rows if r["plan"] and r["plan"]["plan_sha256_matches_record"])
    plan_cfg_ok = sum(1 for r in rows if r["plan"] and r["plan"]["config_sha256_matches_snapshot_config"])

    field_states = {}
    for name in SEVEN_FIELDS:
        distribution = {}
        for row in rows:
            state = row["fields"][name]["state"]
            distribution[state] = distribution.get(state, 0) + 1
        field_states[name] = distribution

    memory_subfield_states = {}
    for sub in ("content", "memory_type", "subject_key", "strength",
                "gold_status", "runtime_status"):
        distribution = {}
        for row in rows:
            for entry in row["fields"]["memory_injected"]["value"]:
                state = entry["subfields"][sub]["state"]
                distribution[state] = distribution.get(state, 0) + 1
        memory_subfield_states[sub] = distribution

    checks = {
        "records_expected": len(rows) == expected_records,
        "strict_json_records": len(rows) == expected_records,
        "audit_locator_unique": len(seen_locators) == len(rows),
        "identity_unique": len(seen_identities) == len(rows),
        "prompt_hash_all": prompt_hash_ok == len(rows),
        "prompt_chars_all": prompt_chars_ok == len(rows),
        "plan_identity_new": plan_ok == 155,
        "plan_sha_new": plan_sha_ok == 155,
        "plan_config_new": plan_cfg_ok == 155,
        "b0_map_all": b0_stats["b0_map_all"],
        "memory_entries_170": memory_entries == 170,
        "memory_match_unique_170": memory_matched == 170,
        "memory_type_all": memory_type_matches == 170,
        "memory_subject_key_resolved_170": memory_subject_key_resolved == 170,
        "memory_strength_all": memory_strength_matches == 170,
        "memory_runtime_inferred_170": runtime_inferred == 170,
        "memory_runtime_unknown_0": runtime_unknown == 0,
        "short_slot_80": short_slot == 80,
        "short_block_80": short_block == 80,
        "short_payload_75": short_payload == 75,
        "difficult_true_10": difficult_true == 10,
        "knowledge_empty_165": knowledge_empty == 165,
        "seven_fields_absent_165": seven_present == 0,
        "no_build_errors": not errors,
    }
    stats = {
        "schema": SCHEMA_ID,
        "builder_version": BUILDER_VERSION,
        "baseline": {
            "snapshot_repository": SNAPSHOT_REPO,
            "snapshot_commit": SNAPSHOT_COMMIT,
            "reviewed_source_repository": SOURCE_REPO,
            "reviewed_source_commit": SOURCE_COMMIT,
            "runtime_source_version_verified": False,
        },
        "records": {
            "total": len(rows),
            "by_segment": {s: sum(1 for r in rows if r["segment"] == s) for s in SEGMENT_ORDER},
            "audit_locator_unique": len(seen_locators),
            "identity_unique": len(seen_identities),
            "strict_json": len(rows),
            "records_with_seven_fields": seven_present,
        },
        "field_state_distribution": field_states,
        "memory": {
            "records_with_entries": memory_records,
            "entries_total": memory_entries,
            "gold_unique_matches": memory_matched,
            "type_matches": memory_type_matches,
            "subject_label_matches": memory_subject_matches,
            "subject_label_mismatches": memory_subject_mismatches,
            "subject_label_mismatch_count": len(memory_subject_mismatches),
            "subject_key_resolved": memory_subject_key_resolved,
            "strength_matches": memory_strength_matches,
            "gold_status_reference_counts": {"active": runtime_inferred},
            "runtime_status": {"inferred_active": runtime_inferred, "unknown": runtime_unknown},
            "subfield_state_distribution": memory_subfield_states,
            "section_5_6_6_status": "NOT_COMPLETED",
            "injected_json_reference_present": False,
            "caveat": "runtime status is inferred, not read; base_sha is unrecoverable",
        },
        "short_term": {
            "predicates": {
                "short_term_slot_enabled_true": short_slot,
                "short_term_block_present_true": short_block,
                "short_term_payload_nonempty_true": short_payload,
            },
            "by_segment": {
                s: {
                    "slot_enabled_true": sum(
                        1 for r in rows if r["segment"] == s and r["fields"]["short_term_injected"]["predicates"]["short_term_slot_enabled"]["value"]),
                    "block_present_true": sum(
                        1 for r in rows if r["segment"] == s and r["fields"]["short_term_injected"]["predicates"]["short_term_block_present"]["value"]),
                    "payload_nonempty_true": sum(
                        1 for r in rows if r["segment"] == s and r["fields"]["short_term_injected"]["predicates"]["short_term_payload_nonempty"]["value"]),
                } for s in SEGMENT_ORDER
            },
            "s7empty_d_records": [
                {
                    "audit_locator": r["audit_locator"],
                    "sample_id": r["source"]["sample_id"],
                    "group": r["source"]["group"],
                    "slot_enabled": r["fields"]["short_term_injected"]["predicates"]["short_term_slot_enabled"]["value"],
                    "block_present": r["fields"]["short_term_injected"]["predicates"]["short_term_block_present"]["value"],
                    "payload_nonempty": r["fields"]["short_term_injected"]["predicates"]["short_term_payload_nonempty"]["value"],
                    "feedback_count": r["fields"]["short_term_injected"]["evidence"]["payload"].get("学习进度", {}).get("已读取反馈数")
                    if r["fields"]["short_term_injected"]["evidence"]["payload"] else None,
                }
                for r in rows
                if r["source"]["sample_id"] == "S7-empty" and r["source"]["group"] == "D"
            ],
            "original_boolean_semantics_decision": "pending_advisor_confirmation",
        },
        "b0_mapping": b0_stats,
        "segments": _segment_stats(rows),
        "integrity": checks,
        "errors": errors,
    }
    if not all(checks.values()):
        raise AuditError("V2 integrity checks failed:\n" + json.dumps(
            {"checks": checks, "errors": errors}, ensure_ascii=False, indent=2))

    out_dir.mkdir(parents=True, exist_ok=True)
    jsonl_path = out_dir / "DERIVED-FIELD-EVIDENCE-V2.jsonl"
    stats_path = out_dir / "DERIVED-FIELD-EVIDENCE-V2-STATS.json"
    jsonl_text = "\n".join(json.dumps(r, ensure_ascii=False, sort_keys=True,
                                      separators=(",", ":")) for r in rows) + "\n"
    jsonl_path.write_text(jsonl_text, encoding="utf-8", newline="\n")
    stats_path.write_text(json.dumps(stats, ensure_ascii=False, indent=2) + "\n",
                          encoding="utf-8", newline="\n")
    return {"jsonl": jsonl_path, "stats": stats_path, "rows": rows, "stats_data": stats}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit-root", type=pathlib.Path,
                        default=pathlib.Path(r"F:\somethingProject\graduation-preflight-audit"))
    parser.add_argument("--source-root", type=pathlib.Path,
                        default=pathlib.Path(r"F:\somethingProject\dsbot-preflight"))
    parser.add_argument("--out-dir", type=pathlib.Path, default=pathlib.Path(__file__).parent)
    parser.add_argument("--no-baseline-check", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = build_ledger(args.audit_root, args.source_root, args.out_dir,
                              verify_baseline=not args.no_baseline_check,
                              expected_segments={
                                  "main": 140,
                                  "supplementary-subject": 10,
                                  "supplementary-s7empty": 5,
                                  "b0-legacy": 10,
                              })
    except AuditError as exc:
        print(f"V2 BUILD FAILED: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result["stats_data"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
