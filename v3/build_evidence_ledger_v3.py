#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build the V3 historical evidence layer for the 165 frozen graduation records.

V3 is deliberately stricter than V2:

* every one of the seven §7.1 fields is an evidence envelope with
  value / evidence_state / original_field_present / source_refs / rule_id /
  rule_version / verification / limitations;
* the V2 aggregate statistics are not trusted or copied.  Every count in the
  V3 stats file is recomputed from the 165 V3 rows;
* short_term_injected has three independent predicates and the third one is
  named short_term_feedback_history_present.  The frozen §7.1 Boolean remains
  pending_advisor_confirmation and is not silently redefined;
* Gold status and runtime status are separate statistics; runtime status is
  inferred / not_verified and is never a direct read;
* subject_label_exact_matches, subject_key_matches and
  subject_display_mismatches are separate statistics;
* outputs are written through a staging directory and an explicit build-state
  file.  A failed build restores the previous outputs and records status
  failed, so an old output cannot silently pass as the new one.

V3 reuses the read-only V2 parsing layer for the raw snapshot traversal.  It
does not reuse the V2 aggregate contract, and it never writes into v2/.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import os
import pathlib
import shutil
import sys
import tempfile
import uuid

from v2 import build_evidence_ledger_v2 as v2

SCHEMA_ID = "graduation-derived-field-evidence/v3"
BUILDER_VERSION = "3.0.0"
RULE_VERSION = "1.0.0"
SNAPSHOT_REPO = v2.SNAPSHOT_REPO
SNAPSHOT_COMMIT = v2.SNAPSHOT_COMMIT
SOURCE_REPO = v2.SOURCE_REPO
SOURCE_COMMIT = v2.SOURCE_COMMIT
EXECUTION_REPORT_BASELINE = v2.EXECUTION_REPORT_BASELINE

SEVEN_FIELDS = (
    "run_id",
    "base_sha",
    "knowledge_result_ids",
    "memory_injected",
    "short_term_injected",
    "difficult_flag",
    "data_kind",
)
EVIDENCE_STATES = (
    "recorded",
    "externally_derived",
    "partially_derived",
    "inferred",
    "gold_reference",
    "unknown",
    "conflicting",
    "unrecoverable",
)
VERIFICATION_STATES = (
    "verified",
    "partially_verified",
    "not_verified",
    "not_possible",
    "reference_only",
)
SEGMENT_ORDER = v2.SEGMENT_ORDER
B0_EXPECTED_TOTAL = v2.B0_EXPECTED_TOTAL

RULES = {
    "run_id": ("HIST-RUN-ID-UNRECOVERABLE", "run_id 在生成时未写入；审计定位符不是 run_id"),
    "base_sha": ("HIST-BASE-SHA-UNRECOVERABLE", "运行开始时的工作树提交未写入；事后 HEAD 不是当时提交"),
    "knowledge_result_ids": ("HIST-KNOWLEDGE-EMPTY-CONFIG", "本批 config.knowledge_results=[]；新数据另有 config→plan→record 哈希链"),
    "memory_injected": ("HIST-MEMORY-PROMPT-TO-GOLD", "prompt 记忆区块按 content 唯一映射到 Gold；status 只可推断"),
    "short_term_injected": ("HIST-SHORT-TERM-THREE-PREDICATES", "槽位开关、区块存在、反馈历史存在性三谓词并列"),
    "difficult_flag": ("HIST-DIFFICULT-FEEDBACK-RULE", "最新反馈 partial 且 reason=任务难度太高，再叠加组别槽位"),
    "data_kind": ("HIST-DATA-KIND-SAMPLE-SIMULATION", "由样本 simulation 与 Gold simulation 派生；样本文件缺原生 data_kind"),
}

CODE_REFS = {
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
    "design_5_6_6": "docs/GRADUATION-EXPERIMENT-DESIGN.md §5.6.6",
    "design_3_4": "docs/GRADUATION-EXPERIMENT-DESIGN.md §3.4",
    "design_7_1": "docs/GRADUATION-EXPERIMENT-DESIGN.md §7.1",
}


class AuditError(RuntimeError):
    """A fail-closed V3 build error."""


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_text(text: str) -> str:
    return sha256_bytes(text.encode("utf-8"))


def canonical(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False)


def ref(kind, **kwargs):
    payload = {"kind": kind}
    payload.update({k: v for k, v in kwargs.items() if v is not None})
    return payload


def code_ref(name):
    return ref("code", path=CODE_REFS[name], commit=SOURCE_COMMIT)


def record_ref(row):
    source = row["source"]
    return ref("result_record", repository=source["repository"],
               commit=source["commit"], path=source["result_file"],
               line=source["line_number"])


def prompt_ref(row):
    return ref("prompt", path=row["prompt"]["file"],
               sha256=row["prompt"]["sha256_recomputed"])


def sample_ref(row):
    return ref("sample", path=f"samples/{row['source']['sample_id']}.json")


def config_ref(row):
    plan = row.get("plan") or {}
    return ref("config", path="config/config.json",
               sha256=plan.get("config_sha256"))


def plan_ref(row):
    plan = row.get("plan") or {}
    if not plan.get("file"):
        return None
    return ref("plan", path=plan["file"], sha256=plan.get("plan_sha256"))


def envelope(field, value, state, original_present, source_refs, rule_id,
             verification, limitations, **extra):
    if state not in EVIDENCE_STATES:
        raise AuditError(f"{field}: invalid evidence_state {state!r}")
    if verification not in VERIFICATION_STATES:
        raise AuditError(f"{field}: invalid verification {verification!r}")
    if not isinstance(source_refs, list):
        raise AuditError(f"{field}: source_refs must be a list")
    if not isinstance(limitations, list):
        raise AuditError(f"{field}: limitations must be a list")
    payload = {
        "value": value,
        "evidence_state": state,
        "original_field_present": bool(original_present),
        "source_refs": source_refs,
        "rule_id": rule_id,
        "rule_version": RULE_VERSION,
        "verification": verification,
        "limitations": limitations,
    }
    payload.update(extra)
    return payload


def field_from_v2(row, name):
    return (row.get("fields") or {}).get(name) or {}


# ---------------------------------------------------------------------------
# Field envelopes
# ---------------------------------------------------------------------------

def build_run_id(row):
    f = field_from_v2(row, "run_id")
    trace = f.get("traceability") or {}
    return envelope(
        "run_id", None, "unrecoverable",
        bool(row["source"]["original_field_presence"].get("run_id")),
        [record_ref(row), code_ref("result_fields"), code_ref("design_7_1")],
        RULES["run_id"][0], "not_possible",
        [
            "原始记录没有 run_id，任何合成值都只能是外部审计定位符。",
            "audit_locator 只在审计台账内唯一，不能当作 §7.1 的 run_id。",
        ],
        traceability={
            "audit_locator": row["audit_locator"],
            "kind": "external_audit_identifier_not_run_id",
            "derived_batch_locator": row.get("derived_batch_locator"),
        },
    )


def build_base_sha(row):
    return envelope(
        "base_sha", None, "unrecoverable",
        bool(row["source"]["original_field_presence"].get("base_sha")),
        [record_ref(row), code_ref("result_fields"), code_ref("design_7_1")],
        RULES["base_sha"][0], "not_possible",
        [
            "运行开始时的工作树提交没有记录；事后 HEAD 不能证明当时的代码版本。",
            "reviewed_source_commit 只是本次复核的源码基线，不是运行时 base_sha。",
            "执行报告中的 e5f97e9 是历史执行基线，不是逐条运行的证明。",
        ],
        runtime_base_sha=None,
        reviewed_source_commit=SOURCE_COMMIT,
        reviewed_source_commit_scope="code review baseline only; not a runtime proof",
        runtime_source_version_verified=False,
        execution_report_baseline=EXECUTION_REPORT_BASELINE,
        execution_report_baseline_is_proof=False,
    )


def build_knowledge(row):
    f = field_from_v2(row, "knowledge_result_ids")
    value = f.get("value")
    if value is None:
        value = []
    b0 = row["segment"] == "b0-legacy"
    evidence = f.get("evidence") or {}
    limitations = list(f.get("limitations") or [])
    if b0:
        limitations.append("B0 legacy 无 config→plan→record 哈希链，只有 prompt 文本证据。")
    else:
        limitations.append("本批为空配置；结论不能推广到未来非空检索实验。")
    refs = [record_ref(row), prompt_ref(row), code_ref("collect_inputs"),
            code_ref("config_hash"), code_ref("plan_digest")]
    if not b0:
        refs.extend([config_ref(row), plan_ref(row)])
    return envelope(
        "knowledge_result_ids", list(value), "externally_derived",
        bool(row["source"]["original_field_presence"].get("knowledge_result_ids")),
        [r for r in refs if r is not None],
        RULES["knowledge_result_ids"][0],
        "partially_verified" if b0 else "verified",
        limitations,
        scope=f.get("scope") or "empty_configuration_only",
        b0_prompt_only=b0,
        b0_plan_binding=evidence.get("plan_binding"),
        config_knowledge_results=evidence.get("config_knowledge_results"),
        config_knowledge_search_failed=evidence.get("config_knowledge_search_failed"),
        prompt_declares_no_knowledge_results=evidence.get("prompt_declares_no_knowledge_results"),
        config_sha256=evidence.get("config_sha256_recomputed"),
    )


def _memory_subfield(label, value, state, refs, rule_id, verification,
                     limitations, **extra):
    return envelope(label, value, state, False, refs, rule_id, verification,
                    limitations, **extra)


def build_memory(row):
    f = field_from_v2(row, "memory_injected")
    source_entries = f.get("value") or []
    entries = []
    label_matches = 0
    key_matches = 0
    display_mismatches = 0
    type_matches = 0
    strength_matches = 0
    inferred_active = 0
    unknown_runtime = 0

    for entry in source_entries:
        sub = entry.get("subfields") or {}
        content = sub.get("content") or {}
        mtype = sub.get("memory_type") or {}
        msubject = sub.get("subject_key") or {}
        mstrength = sub.get("strength") or {}
        gstatus = sub.get("gold_status") or {}
        rstatus = sub.get("runtime_status") or {}
        gold_ref = entry.get("gold_ref")
        mapped = gold_ref is not None
        gold_evidence = msubject.get("evidence") or {}
        prompt_subject = gold_evidence.get("prompt_subject")
        gold_label = gold_evidence.get("gold_subject_label")
        gold_key = msubject.get("value")
        label_match = bool(mapped and prompt_subject == gold_label)
        key_match = bool(mapped and prompt_subject == gold_key)
        display_mismatch = bool(mapped and not label_match and not key_match)
        label_matches += int(label_match)
        key_matches += int(key_match)
        display_mismatches += int(display_mismatch)
        type_matches += int(mtype.get("state") == "externally_derived")
        strength_matches += int(mstrength.get("state") == "externally_derived")

        base_refs = [prompt_ref(row), sample_ref(row)]
        subfields = {
            "content": _memory_subfield(
                "content", content.get("value"), content.get("state") or "unknown",
                base_refs, RULES["memory_injected"][0],
                "verified" if mapped else "not_possible",
                [] if mapped else ["content 在 Gold 中不是唯一匹配。"],
                gold_match_count=(content.get("evidence") or {}).get("gold_match_count"),
                gold_index=(content.get("evidence") or {}).get("gold_index"),
                mapping_basis="prompt memory block content -> Gold exact unique match",
            ),
            "memory_type": _memory_subfield(
                "memory_type", mtype.get("value"), mtype.get("state") or "unknown",
                base_refs, RULES["memory_injected"][0],
                "verified" if mtype.get("state") == "externally_derived" else "not_verified",
                [] if mtype.get("state") == "externally_derived" else ["prompt type 与 Gold memory_type 不一致。"],
                prompt_type=(mtype.get("evidence") or {}).get("prompt_type"),
                gold_memory_type=(mtype.get("evidence") or {}).get("gold_memory_type"),
            ),
            "subject_key": _memory_subfield(
                "subject_key", gold_key,
                msubject.get("state") or "unknown", base_refs,
                RULES["memory_injected"][0],
                "partially_verified" if display_mismatch else ("verified" if mapped else "not_possible"),
                ["prompt 的 subject 是展示名，Gold 的 subject_key 是归一化键；S4 的 medium/中等 差异保留。"]
                if display_mismatch else
                (["content 未唯一映射，subject_key 不可确定。"] if not mapped else []),
                prompt_subject=prompt_subject,
                gold_subject_label=gold_label,
                gold_subject_key=gold_key,
                subject_label_exact_match=label_match,
                subject_key_match=key_match,
                subject_display_mismatch=display_mismatch,
                mapping_basis="unique exact content match to Gold; key is Gold metadata",
            ),
            "strength": _memory_subfield(
                "strength", mstrength.get("value"),
                mstrength.get("state") or "unknown", base_refs,
                RULES["memory_injected"][0],
                "verified" if mstrength.get("state") == "externally_derived" else "not_verified",
                [] if mstrength.get("state") == "externally_derived" else ["prompt strength 与 Gold strength 不一致。"],
                prompt_strength=(mstrength.get("evidence") or {}).get("prompt_strength"),
                gold_strength=(mstrength.get("evidence") or {}).get("gold_strength"),
            ),
            "gold_status": _memory_subfield(
                "gold_status", gstatus.get("value"), "gold_reference",
                [sample_ref(row)], RULES["memory_injected"][0], "reference_only",
                ["Gold 是夹具期望，不是运行时读取。"] if mapped else ["无唯一 Gold 映射。"],
                meaning="fixture expectation only; not a runtime read",
            ),
            "memory_id": _memory_subfield(
                "memory_id", None, "unrecoverable",
                [prompt_ref(row), code_ref("agent_tools_sanitize")],
                RULES["memory_injected"][0], "not_possible",
                ["prompt 不含 memory_id；_sanitize_memory 也刻意剥离 memory_id。"],
                reason="prompt_omits_memory_id",
            ),
            "runtime_status": _memory_subfield(
                "runtime_status", None,
                "inferred" if rstatus.get("state") == "inferred" else "unknown",
                [prompt_ref(row), code_ref("agent_tools_get_memory"),
                 code_ref("agent_tools_status_filter"), code_ref("memory_service_retrieve")],
                RULES["memory_injected"][0],
                "not_verified",
                [
                    "prompt 不含 status；runtime status 不是运行时读取。",
                    "无 injected.json，无法完成 §5.6.6 的逐项对照。",
                    "runtime base_sha 不可恢复，reviewed_source_commit 不是运行时证明。",
                ],
                inferred_value=("active" if rstatus.get("state") == "inferred" else None),
                confidence="low",
                verification_blockers=["runtime_base_sha_unrecoverable",
                                       "injected_json_absent",
                                       "prompt_omits_status",
                                       "reviewed_source_commit_is_not_runtime_proof"],
                section_5_6_6_compared=False,
            ),
        }
        if rstatus.get("state") == "inferred":
            inferred_active += 1
        else:
            unknown_runtime += 1
        entries.append({
            "index": entry.get("index"),
            "content": entry.get("content"),
            "gold_ref": gold_ref,
            "subfields": subfields,
        })

    flat_value = [{
        "memory_type": e["subfields"]["memory_type"]["value"],
        "subject_key": e["subfields"]["subject_key"]["value"],
        "strength": e["subfields"]["strength"]["value"],
        "status": None,
    } for e in entries]

    limitations = [
        "历史 prompt 不含 memory_id 与 runtime status；两者都不能直接读取。",
        "runtime status 只能按唯一消费者路径与 Gold 推定为 active，verification=not_verified。",
        "没有 injected.json，§5.6.6 未完成，不能声称逐项一致。",
        "170 条映射均来自 prompt 内容与 Gold 的唯一匹配；S4 的十条展示差异保留。",
    ]
    field = envelope(
        "memory_injected", flat_value,
        "partially_derived" if entries else "externally_derived",
        bool(row["source"]["original_field_presence"].get("memory_injected")),
        [record_ref(row), prompt_ref(row), sample_ref(row),
         code_ref("agent_tools_sanitize"), code_ref("agent_tools_get_memory"),
         code_ref("agent_tools_status_filter"), code_ref("memory_service_retrieve"),
         code_ref("memory_fields"), code_ref("memory_block"),
         code_ref("design_5_6_6")],
        RULES["memory_injected"][0], "partially_verified", limitations,
        entries=entries,
        section_5_6_6_status="NOT_COMPLETED",
        injected_json_reference_present=False,
        source_entry_count=len(entries),
        statistics={
            "subject_label_exact_matches": label_matches,
            "subject_key_matches": key_matches,
            "subject_display_mismatches": display_mismatches,
            "type_matches": type_matches,
            "strength_matches": strength_matches,
            "runtime_status_inferred_active": inferred_active,
            "runtime_status_unknown": unknown_runtime,
        },
    )
    return field


def build_short_term(row):
    f = field_from_v2(row, "short_term_injected")
    preds = f.get("predicates") or {}
    slot = bool((preds.get("short_term_slot_enabled") or {}).get("value"))
    block = bool((preds.get("short_term_block_present") or {}).get("value"))
    feedback_history = bool((preds.get("short_term_payload_nonempty") or {}).get("value"))
    evidence = f.get("evidence") or {}
    payload = evidence.get("payload")
    plan_present = isinstance(payload, dict) and payload.get("今日计划") is not None
    parse_error = evidence.get("parse_error")

    def pred(value, state, verification, detail):
        return envelope(
            "short_term_injected", bool(value), state, False,
            [prompt_ref(row), code_ref("draft_content"), code_ref("group_inputs")],
            RULES["short_term_injected"][0], verification, [],
            **detail,
        )

    predicates = {
        "short_term_slot_enabled": pred(
            slot, "externally_derived", "verified",
            {"group": row["source"]["group"],
             "group_slots": (preds.get("short_term_slot_enabled") or {}).get("evidence", {}).get("group_slots"),
             "basis": "experiment design matrix + build_prompts.GROUP_SLOTS"},
        ),
        "short_term_block_present": pred(
            block, "externally_derived", "verified",
            {"section_title": v2.SHORT_HEADER,
             "marker_found": block,
             "basis": "literal marker in prompt user content"},
        ),
        "short_term_feedback_history_present": pred(
            feedback_history, "externally_derived",
            "verified" if parse_error is None else "not_verified",
            {"feedback_count": (preds.get("short_term_payload_nonempty") or {}).get("evidence", {}).get("feedback_count"),
             "plan_present": plan_present,
             "payload_parsed": payload is not None,
             "criteria": "已读取反馈数 > 0",
             "basis": "parsed learner-context JSON; this predicate is feedback-history presence, not whole-payload non-emptiness",
             "legacy_name": "short_term_payload_nonempty"},
        ),
    }
    value = {
        "short_term_slot_enabled": slot,
        "short_term_block_present": block,
        "short_term_feedback_history_present": feedback_history,
        "short_term_injected": None,
    }
    return envelope(
        "short_term_injected", value, "externally_derived",
        bool(row["source"]["original_field_presence"].get("short_term_injected")),
        [record_ref(row), prompt_ref(row), code_ref("draft_content"),
         code_ref("group_inputs"), code_ref("design_7_1")],
        RULES["short_term_injected"][0], "partially_verified",
        [
            "§7.1 只给 Boolean 示例，未定义它对应槽位、区块还是反馈历史；V3 不擅自重定义。",
            "第三个谓词只表示已读取反馈数 > 0，不表示今日计划或整个 payload 非空。",
            "S7-empty 的 D 组有区块但反馈历史为 0，5 条差异保留。",
            "正式运行必须提供导师批准的 semantics_version。",
        ],
        predicates=predicates,
        frozen_field_compatibility={
            "original_field": "short_term_injected",
            "original_definition": "§7.1 Boolean; frozen design does not split slot/block/payload semantics",
            "v3_redefines_original_field": False,
            "semantics_status": "pending_advisor_confirmation",
            "candidate_meanings": ["short_term_slot_enabled",
                                     "short_term_block_present",
                                     "short_term_feedback_history_present"],
            "legacy_v2_name": "short_term_payload_nonempty",
            "formal_run_requires_approved_semantics": True,
        },
        parse_error=parse_error,
        payload_parsed=payload is not None,
    )


def build_difficult(row):
    f = field_from_v2(row, "difficult_flag")
    evidence = f.get("evidence") or {}
    agree = evidence.get("agree") is True
    value = f.get("value")
    return envelope(
        "difficult_flag", value,
        "externally_derived" if agree else "conflicting",
        bool(row["source"]["original_field_presence"].get("difficult_flag")),
        [record_ref(row), prompt_ref(row), sample_ref(row),
         code_ref("derive_difficult"), code_ref("difficult_rule"),
         code_ref("group_slots")],
        RULES["difficult_flag"][0],
        "verified" if agree else "not_verified",
        [] if agree else ["最终 difficult 值与原始条件/组别槽位不一致。"],
        latest_feedback=evidence.get("latest_feedback"),
        raw_condition_partial_and_reason=evidence.get("raw_condition_partial_and_reason"),
        feedback_slot_enabled=evidence.get("feedback_slot_enabled"),
        b0_group_fixed_false=evidence.get("b0_group_fixed_false"),
        dynamic_rule_present_in_prompt=evidence.get("dynamic_rule_present_in_prompt"),
        agree=agree,
    )


def build_data_kind(row):
    f = field_from_v2(row, "data_kind")
    evidence = f.get("evidence") or {}
    return envelope(
        "data_kind", f.get("value"), "externally_derived",
        bool(row["source"]["original_field_presence"].get("data_kind")),
        [record_ref(row), prompt_ref(row), sample_ref(row),
         code_ref("seed_simulation"), code_ref("design_3_4")],
        RULES["data_kind"][0], "partially_verified",
        [
            "样本文件没有 §3.4 要求的原生 data_kind 字段；该值由 simulation 标记派生。",
            "这不是原始记录直接写入，也不宣称已经满足 §3.4 的字段要求。",
        ],
        sample_simulation_is_simulated=evidence.get("sample_simulation_is_simulated"),
        gold_simulation=evidence.get("gold_simulation"),
        seed_fixture_requires_is_simulated=evidence.get("seed_fixture_requires_is_simulated"),
        sample_file=evidence.get("sample_file"),
        original_sample_has_data_kind=evidence.get("original_sample_has_data_kind"),
        sample_linked_to_prompt_request=evidence.get("sample_linked_to_prompt_request"),
    )


BUILDERS = {
    "run_id": build_run_id,
    "base_sha": build_base_sha,
    "knowledge_result_ids": build_knowledge,
    "memory_injected": build_memory,
    "short_term_injected": build_short_term,
    "difficult_flag": build_difficult,
    "data_kind": build_data_kind,
}


def build_v3_row(row):
    fields = {}
    for name in SEVEN_FIELDS:
        fields[name] = BUILDERS[name](row)
    presence = {name: bool(row["source"]["original_field_presence"].get(name))
                for name in SEVEN_FIELDS}
    missing = [name for name in SEVEN_FIELDS if not presence[name]]
    v3row = {
        "schema": SCHEMA_ID,
        "builder_version": BUILDER_VERSION,
        "audit": {
            "snapshot_repository": SNAPSHOT_REPO,
            "snapshot_commit": SNAPSHOT_COMMIT,
            "reviewed_source_repository": SOURCE_REPO,
            "reviewed_source_commit": SOURCE_COMMIT,
            "runtime_source_version_verified": False,
            "audit_scope": "165 historical records; no backfill",
        },
        "source": dict(row["source"]),
        "segment": row["segment"],
        "audit_locator": row["audit_locator"],
        "derived_batch_locator": row.get("derived_batch_locator"),
        "identity": {
            "experiment_id": row["source"]["experiment_id"],
            "sample_id": row["source"]["sample_id"],
            "group": row["source"]["group"],
            "repeat_index": row["source"]["repeat_index"],
        },
        "b0": row.get("b0"),
        "prompt": dict(row["prompt"]),
        "plan": row.get("plan"),
        "fields": fields,
        "acceptance": {
            "original_contract_compliance": {
                "status": "FAIL" if missing else "PASS",
                "design_version": "v4.5",
                "design_section": "§7.1",
                "missing_fields": missing,
                "present_fields": [name for name in SEVEN_FIELDS if presence[name]],
                "reason": ("原始记录不包含 §7.1 的七字段；外置证据层不能把原记录改成合规，"
                           if missing else "原始记录含全部七字段。"),
            },
            "evidence_layer_integrity": {
                "status": "PASS",
                "checks": {
                    "seven_envelopes_present": len(fields) == 7,
                    "all_envelopes_have_required_keys": True,
                    "original_field_presence_is_boolean": all(
                        isinstance(presence[n], bool) for n in SEVEN_FIELDS),
                },
            },
        },
    }
    return v3row


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def _require(condition, message):
    if not condition:
        raise AuditError(message)


def validate_field_envelope(field, name):
    _require(isinstance(field, dict), f"{name}: envelope is not an object")
    required = ("value", "evidence_state", "original_field_present", "source_refs",
                "rule_id", "rule_version", "verification", "limitations")
    for key in required:
        _require(key in field, f"{name}: missing {key}")
    _require(field["evidence_state"] in EVIDENCE_STATES,
             f"{name}: bad evidence_state")
    _require(field["verification"] in VERIFICATION_STATES,
             f"{name}: bad verification")
    _require(isinstance(field["original_field_present"], bool),
             f"{name}: original_field_present is not bool")
    _require(isinstance(field["source_refs"], list), f"{name}: source_refs not list")
    _require(isinstance(field["limitations"], list), f"{name}: limitations not list")
    _require(isinstance(field["rule_id"], str) and field["rule_id"],
             f"{name}: rule_id missing")
    _require(isinstance(field["rule_version"], str) and field["rule_version"],
             f"{name}: rule_version missing")


def validate_evidence_row(row):
    _require(row.get("schema") == SCHEMA_ID, "bad schema")
    _require(row.get("builder_version") == BUILDER_VERSION, "bad builder_version")
    _require(set(row.get("fields") or {}) == set(SEVEN_FIELDS),
             "fields must be exactly the seven")
    for name in SEVEN_FIELDS:
        validate_field_envelope(row["fields"][name], name)

    run_id = row["fields"]["run_id"]
    _require(run_id["value"] is None and run_id["evidence_state"] == "unrecoverable",
             "run_id must be null/unrecoverable")
    base_sha = row["fields"]["base_sha"]
    _require(base_sha["value"] is None and base_sha["evidence_state"] == "unrecoverable",
             "base_sha must be null/unrecoverable")
    _require(base_sha.get("reviewed_source_commit") == SOURCE_COMMIT,
             "base_sha must carry the reviewed source commit as metadata only")
    _require(base_sha.get("runtime_source_version_verified") is False,
             "base_sha must not claim runtime verification")

    knowledge = row["fields"]["knowledge_result_ids"]
    _require(isinstance(knowledge["value"], list), "knowledge value must be list")
    _require(all(isinstance(x, str) for x in knowledge["value"]),
             "knowledge ids must be strings")

    memory = row["fields"]["memory_injected"]
    _require(isinstance(memory["value"], list), "memory value must be list")
    _require(isinstance(memory.get("entries"), list), "memory entries must be list")
    _require(len(memory["value"]) == len(memory["entries"]),
             "memory value/entries length mismatch")
    for i, entry in enumerate(memory["entries"]):
        for sub in ("content", "memory_type", "subject_key", "strength",
                    "gold_status", "memory_id", "runtime_status"):
            _require(sub in entry.get("subfields", {}),
                     f"memory entry {i}: missing {sub}")
            validate_field_envelope(entry["subfields"][sub], f"memory.{sub}[{i}]")
        _require(entry["subfields"]["runtime_status"]["value"] is None,
                 "runtime_status must not expose a bare value")
        _require(entry["subfields"]["runtime_status"]["evidence_state"] in ("inferred", "unknown"),
                 "runtime_status must be inferred/unknown")

    short = row["fields"]["short_term_injected"]
    _require(set(short["predicates"]) == {
        "short_term_slot_enabled", "short_term_block_present",
        "short_term_feedback_history_present"}, "short predicates mismatch")
    _require(short["value"]["short_term_injected"] is None,
             "frozen short_term_injected Boolean must stay null/pending")
    _require(short["frozen_field_compatibility"]["semantics_status"]
             == "pending_advisor_confirmation",
             "frozen Boolean semantics must remain pending")

    difficult = row["fields"]["difficult_flag"]
    _require(isinstance(difficult["value"], bool), "difficult value must be bool")

    data_kind = row["fields"]["data_kind"]
    _require(isinstance(data_kind["value"], str) and data_kind["value"],
             "data_kind value must be a non-empty string")

    _require(row["acceptance"]["original_contract_compliance"]["status"] in ("FAIL", "PASS"),
             "bad original contract status")
    _require(row["acceptance"]["evidence_layer_integrity"]["status"] in ("FAIL", "PASS"),
             "bad evidence integrity status")
    return True


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------

def _count(values):
    out = {}
    for value in values:
        out[value] = out.get(value, 0) + 1
    return out


def build_stats(rows, v2_rows=None, v2_stats=None):
    by_segment = {s: sum(1 for r in rows if r["segment"] == s) for s in SEGMENT_ORDER}
    field_states = {
        name: _count(r["fields"][name]["evidence_state"] for r in rows)
        for name in SEVEN_FIELDS
    }
    field_verification = {
        name: _count(r["fields"][name]["verification"] for r in rows)
        for name in SEVEN_FIELDS
    }

    memory_entries = [e for r in rows for e in r["fields"]["memory_injected"]["entries"]]
    memory_records = sum(1 for r in rows if r["fields"]["memory_injected"]["entries"])
    memory_subfields = {}
    for sub in ("content", "memory_type", "subject_key", "strength",
                "gold_status", "memory_id", "runtime_status"):
        memory_subfields[sub] = _count(
            e["subfields"][sub]["evidence_state"] for e in memory_entries)
    gold_status_counts = _count(
        e["subfields"]["gold_status"]["value"] for e in memory_entries)
    runtime_status_counts = _count(
        ("inferred_active" if e["subfields"]["runtime_status"]["evidence_state"] == "inferred"
         else "unknown") for e in memory_entries)
    runtime_verification_counts = _count(
        e["subfields"]["runtime_status"]["verification"] for e in memory_entries)
    label_matches = sum(1 for e in memory_entries
                        if e["subfields"]["subject_key"].get("subject_label_exact_match") is True)
    key_matches = sum(1 for e in memory_entries
                      if e["subfields"]["subject_key"].get("subject_key_match") is True)
    key_resolved = sum(1 for e in memory_entries
                       if e["subfields"]["subject_key"].get("value") is not None)
    display_mismatches = []
    for r in rows:
        for e in r["fields"]["memory_injected"]["entries"]:
            sk = e["subfields"]["subject_key"]
            if sk.get("subject_display_mismatch") is True:
                display_mismatches.append({
                    "audit_locator": r["audit_locator"],
                    "index": e.get("index"),
                    "prompt_subject": sk.get("prompt_subject"),
                    "gold_subject_label": sk.get("gold_subject_label"),
                    "gold_subject_key": sk.get("gold_subject_key"),
                    "content": e.get("content"),
                })
    type_matches = sum(1 for e in memory_entries
                       if e["subfields"]["memory_type"]["evidence_state"] == "externally_derived")
    strength_matches = sum(1 for e in memory_entries
                           if e["subfields"]["strength"]["evidence_state"] == "externally_derived")

    short_counts = {
        "short_term_slot_enabled": sum(
            1 for r in rows if r["fields"]["short_term_injected"]["predicates"]["short_term_slot_enabled"]["value"]),
        "short_term_block_present": sum(
            1 for r in rows if r["fields"]["short_term_injected"]["predicates"]["short_term_block_present"]["value"]),
        "short_term_feedback_history_present": sum(
            1 for r in rows if r["fields"]["short_term_injected"]["predicates"]["short_term_feedback_history_present"]["value"]),
    }
    short_segments = {}
    for segment in SEGMENT_ORDER:
        selected = [r for r in rows if r["segment"] == segment]
        short_segments[segment] = {
            "slot_enabled_true": sum(
                1 for r in selected if r["fields"]["short_term_injected"]["predicates"]["short_term_slot_enabled"]["value"]),
            "block_present_true": sum(
                1 for r in selected if r["fields"]["short_term_injected"]["predicates"]["short_term_block_present"]["value"]),
            "feedback_history_present_true": sum(
                1 for r in selected if r["fields"]["short_term_injected"]["predicates"]["short_term_feedback_history_present"]["value"]),
        }

    difficult_true = sum(1 for r in rows if r["fields"]["difficult_flag"]["value"] is True)
    difficult_by_segment = {
        s: sum(1 for r in rows
               if r["segment"] == s and r["fields"]["difficult_flag"]["value"] is True)
        for s in SEGMENT_ORDER
    }
    b0_raw_true_value_false = sum(
        1 for r in rows
        if r["segment"] == "b0-legacy"
        and r["fields"]["difficult_flag"].get("raw_condition_partial_and_reason") is True
        and r["fields"]["difficult_flag"]["value"] is False
    )
    knowledge_empty = sum(
        1 for r in rows if r["fields"]["knowledge_result_ids"]["value"] == [])
    b0_knowledge_prompt_only = sum(
        1 for r in rows if r["segment"] == "b0-legacy"
        and r["fields"]["knowledge_result_ids"].get("b0_prompt_only") is True)
    data_kind_counts = _count(r["fields"]["data_kind"]["value"] for r in rows)
    s7empty = [{
        "audit_locator": r["audit_locator"],
        "sample_id": r["source"]["sample_id"],
        "group": r["source"]["group"],
        "slot_enabled": r["fields"]["short_term_injected"]["predicates"]["short_term_slot_enabled"]["value"],
        "block_present": r["fields"]["short_term_injected"]["predicates"]["short_term_block_present"]["value"],
        "feedback_history_present": r["fields"]["short_term_injected"]["predicates"]["short_term_feedback_history_present"]["value"],
        "feedback_count": r["fields"]["short_term_injected"]["predicates"]["short_term_feedback_history_present"].get("feedback_count"),
        "plan_present": r["fields"]["short_term_injected"]["predicates"]["short_term_feedback_history_present"].get("plan_present"),
    } for r in rows if r["source"]["sample_id"] == "S7-empty" and r["source"]["group"] == "D"]

    segment_stats = {}
    for segment in SEGMENT_ORDER:
        selected = [r for r in rows if r["segment"] == segment]
        segment_stats[segment] = {
            "records": len(selected),
            "field_states": {
                name: _count(r["fields"][name]["evidence_state"] for r in selected)
                for name in SEVEN_FIELDS
            },
            "memory_entries": sum(len(r["fields"]["memory_injected"]["entries"]) for r in selected),
            "memory_records": sum(1 for r in selected if r["fields"]["memory_injected"]["entries"]),
            "short": short_segments[segment],
            "difficult_true": difficult_by_segment[segment],
        }

    stats = {
        "schema": SCHEMA_ID,
        "builder_version": BUILDER_VERSION,
        "rule_version": RULE_VERSION,
        "baseline": {
            "snapshot_repository": SNAPSHOT_REPO,
            "snapshot_commit": SNAPSHOT_COMMIT,
            "reviewed_source_repository": SOURCE_REPO,
            "reviewed_source_commit": SOURCE_COMMIT,
            "runtime_source_version_verified": False,
            "execution_report_baseline": EXECUTION_REPORT_BASELINE,
            "execution_report_baseline_is_proof": False,
        },
        "records": {
            "total": len(rows),
            "by_segment": by_segment,
            "audit_locator_unique": len({r["audit_locator"] for r in rows}),
            "identity_unique": len({
                (r["identity"]["experiment_id"], r["identity"]["sample_id"],
                 r["identity"]["group"], r["identity"]["repeat_index"]) for r in rows}),
            "records_with_seven_fields": sum(
                1 for r in rows if all(r["fields"][n]["original_field_present"] for n in SEVEN_FIELDS)),
        },
        "field_state_distribution": field_states,
        "field_verification_distribution": field_verification,
        "memory": {
            "records_with_entries": memory_records,
            "entries_total": len(memory_entries),
            "gold_status_counts": gold_status_counts,
            "runtime_status_counts": runtime_status_counts,
            "runtime_verification_counts": runtime_verification_counts,
            "subject_label_exact_matches": label_matches,
            "subject_key_matches": key_matches,
            "subject_key_resolved": key_resolved,
            "subject_display_mismatches": len(display_mismatches),
            "subject_display_mismatch_details": display_mismatches,
            "type_matches": type_matches,
            "strength_matches": strength_matches,
            "subfield_state_distribution": memory_subfields,
            "section_5_6_6_status": "NOT_COMPLETED",
            "section_5_6_6_reason": "no injected.json; runtime base_sha unrecoverable; prompt omits status",
            "injected_json_reference_present": False,
        },
        "short_term": {
            "predicates": {
                "short_term_slot_enabled_true": short_counts["short_term_slot_enabled"],
                "short_term_block_present_true": short_counts["short_term_block_present"],
                "short_term_feedback_history_present_true": short_counts["short_term_feedback_history_present"],
            },
            "legacy_v2_name": "short_term_payload_nonempty",
            "legacy_v2_count": short_counts["short_term_feedback_history_present"],
            "by_segment": short_segments,
            "s7empty_d_records": s7empty,
            "original_boolean_semantics_decision": "pending_advisor_confirmation",
        },
        "difficult": {
            "true_total": difficult_true,
            "by_segment": difficult_by_segment,
            "b0_raw_condition_true_but_value_false": b0_raw_true_value_false,
        },
        "knowledge": {
            "empty_list_total": knowledge_empty,
            "b0_prompt_only_total": b0_knowledge_prompt_only,
            "scope": "empty_configuration_only",
        },
        "data_kind": {"counts": data_kind_counts},
        "b0_mapping": (v2_stats or {}).get("b0_mapping"),
        "segments": segment_stats,
        "dual_acceptance": {
            "original_contract_compliance": {
                "status": "FAIL",
                "records_with_all_seven": sum(
                    1 for r in rows if all(r["fields"][n]["original_field_present"] for n in SEVEN_FIELDS)),
                "reason": "原始记录没有七字段；外置证据层不能改变原始契约结论。",
            },
            "evidence_layer_integrity": {
                "status": "PASS",
                "records_validated": len(rows),
                "checks": {},
            },
        },
        "integrity": {},
        "errors": [],
        "v2_comparison": compare_v2(rows, v2_rows, v2_stats),
    }
    stats["integrity"] = integrity_checks(rows, stats, v2_rows, v2_stats)
    stats["dual_acceptance"]["evidence_layer_integrity"]["checks"] = stats["integrity"]
    return stats


def integrity_checks(rows, stats, v2_rows, v2_stats):
    checks = {
        "record_count_165": len(rows) == 165,
        "segment_counts": stats["records"]["by_segment"] == {
            "main": 140, "supplementary-subject": 10,
            "supplementary-s7empty": 5, "b0-legacy": 10},
        "audit_locator_unique_165": stats["records"]["audit_locator_unique"] == 165,
        "identity_unique_165": stats["records"]["identity_unique"] == 165,
        "strict_json_all": all(validate_evidence_row(r) for r in rows),
        "run_id_unrecoverable_165": stats["field_state_distribution"]["run_id"] == {"unrecoverable": 165},
        "base_sha_unrecoverable_165": stats["field_state_distribution"]["base_sha"] == {"unrecoverable": 165},
        "memory_entries_170": stats["memory"]["entries_total"] == 170,
        "memory_records_80": stats["memory"]["records_with_entries"] == 80,
        "gold_status_active_170": stats["memory"]["gold_status_counts"].get("active") == 170,
        "runtime_inferred_active_170": stats["memory"]["runtime_status_counts"].get("inferred_active") == 170,
        "runtime_unknown_0": stats["memory"]["runtime_status_counts"].get("unknown", 0) == 0,
        "runtime_not_verified_170": stats["memory"]["runtime_verification_counts"].get("not_verified") == 170,
        "subject_label_exact_160": stats["memory"]["subject_label_exact_matches"] == 160,
        "subject_key_matches_0": stats["memory"]["subject_key_matches"] == 0,
        "subject_key_resolved_170": stats["memory"]["subject_key_resolved"] == 170,
        "subject_display_mismatches_10": stats["memory"]["subject_display_mismatches"] == 10,
        "short_slot_80": stats["short_term"]["predicates"]["short_term_slot_enabled_true"] == 80,
        "short_block_80": stats["short_term"]["predicates"]["short_term_block_present_true"] == 80,
        "short_feedback_history_75": stats["short_term"]["predicates"]["short_term_feedback_history_present_true"] == 75,
        "short_s7empty_5": len(stats["short_term"]["s7empty_d_records"]) == 5,
        "difficult_true_10": stats["difficult"]["true_total"] == 10,
        "knowledge_empty_165": stats["knowledge"]["empty_list_total"] == 165,
        "b0_prompt_only_10": stats["knowledge"]["b0_prompt_only_total"] == 10,
        "data_kind_165": sum(stats["data_kind"]["counts"].values()) == 165,
        "original_seven_absent_165": stats["records"]["records_with_seven_fields"] == 0,
        "v2_record_count_match": bool(v2_rows) and len(v2_rows) == len(rows),
        "v2_locator_set_match": bool(v2_rows) and {
            r["audit_locator"] for r in v2_rows} == {r["audit_locator"] for r in rows},
        "v2_identity_set_match": bool(v2_rows) and {
            (r["source"]["experiment_id"], r["source"]["sample_id"],
             r["source"]["group"], r["source"]["repeat_index"]) for r in v2_rows} == {
            (r["identity"]["experiment_id"], r["identity"]["sample_id"],
             r["identity"]["group"], r["identity"]["repeat_index"]) for r in rows},
    }
    return checks


def compare_v2(v3_rows, v2_rows, v2_stats):
    if not v2_rows:
        return {"available": False, "reason": "V2 rows not loaded"}
    v2_states = {}
    for name in SEVEN_FIELDS:
        v2_states[name] = _count(r["fields"][name].get("state") for r in v2_rows)
    v3_states = {
        name: _count(r["fields"][name]["evidence_state"] for r in v3_rows)
        for name in SEVEN_FIELDS
    }
    v2_short = (v2_stats or {}).get("short_term", {}).get("predicates", {})
    v3_short = {
        "short_term_slot_enabled_true": sum(
            1 for r in v3_rows if r["fields"]["short_term_injected"]["predicates"]["short_term_slot_enabled"]["value"]),
        "short_term_block_present_true": sum(
            1 for r in v3_rows if r["fields"]["short_term_injected"]["predicates"]["short_term_block_present"]["value"]),
        "short_term_feedback_history_present_true": sum(
            1 for r in v3_rows if r["fields"]["short_term_injected"]["predicates"]["short_term_feedback_history_present"]["value"]),
    }
    v2_memory = (v2_stats or {}).get("memory", {})
    v3_memory = {
        "gold_status_counts": _count(
            e["subfields"]["gold_status"]["value"]
            for r in v3_rows for e in r["fields"]["memory_injected"]["entries"]),
        "runtime_status_counts": _count(
            ("inferred_active" if e["subfields"]["runtime_status"]["evidence_state"] == "inferred"
             else "unknown")
            for r in v3_rows for e in r["fields"]["memory_injected"]["entries"]),
        "subject_label_exact_matches": sum(
            1 for r in v3_rows for e in r["fields"]["memory_injected"]["entries"]
            if e["subfields"]["subject_key"].get("subject_label_exact_match") is True),
        "subject_key_matches": sum(
            1 for r in v3_rows for e in r["fields"]["memory_injected"]["entries"]
            if e["subfields"]["subject_key"].get("subject_key_match") is True),
        "subject_display_mismatches": sum(
            1 for r in v3_rows for e in r["fields"]["memory_injected"]["entries"]
            if e["subfields"]["subject_key"].get("subject_display_mismatch") is True),
    }
    return {
        "available": True,
        "v2_schema": (v2_stats or {}).get("schema"),
        "v2_builder_version": (v2_stats or {}).get("builder_version"),
        "record_count_match": len(v2_rows) == len(v3_rows),
        "locator_set_match": {r["audit_locator"] for r in v2_rows} == {
            r["audit_locator"] for r in v3_rows},
        "identity_set_match": {
            (r["source"]["experiment_id"], r["source"]["sample_id"],
             r["source"]["group"], r["source"]["repeat_index"]) for r in v2_rows} == {
            (r["identity"]["experiment_id"], r["identity"]["sample_id"],
             r["identity"]["group"], r["identity"]["repeat_index"]) for r in v3_rows},
        "v2_field_states": v2_states,
        "v3_field_states": v3_states,
        "short_predicate_counts": {"v2": v2_short, "v3": v3_short},
        "memory_statistics": {
            "v2_gold_status_reference_counts": v2_memory.get("gold_status_reference_counts"),
            "v2_runtime_status": v2_memory.get("runtime_status"),
            "v2_subject_label_matches": v2_memory.get("subject_label_matches"),
            "v3": v3_memory,
        },
        "intentional_differences": [
            "V3 renames short_term_payload_nonempty to short_term_feedback_history_present; value count stays 75.",
            "V3 recomputes Gold status from gold_reference subfields; V2's gold_status_reference_counts was populated from runtime inferred count.",
            "V3 splits subject label exact matches (160), subject key matches (0, because the prompt shows subject_label) and display mismatches (10); V2's subject_label_matches was a combined label-or-key count (170). subject_key_resolved is 170.",
            "V3 wraps every field in an evidence envelope with source_refs/rule_id/verification/limitations; V2 did not.",
            "V3 writes atomically with a build-state file; V2 wrote sequentially.",
        ],
    }


# ---------------------------------------------------------------------------
# Atomic output
# ---------------------------------------------------------------------------

def _state_write(path, payload):
    tmp = path.with_name(path.name + ".tmp-" + uuid.uuid4().hex)
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8", newline="\n")
    os.replace(tmp, path)


def _atomic_write_bytes(path, data):
    tmp = path.with_name(path.name + ".tmp-" + uuid.uuid4().hex)
    with open(tmp, "wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)


def write_outputs_atomic(out_dir, jsonl_text, stats_text, rows, stats):
    out_dir = pathlib.Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    jsonl_path = out_dir / "DERIVED-FIELD-EVIDENCE-V3.jsonl"
    stats_path = out_dir / "DERIVED-FIELD-EVIDENCE-V3-STATS.json"
    state_path = out_dir / "V3-BUILD-STATE.json"
    jsonl_bytes = jsonl_text.encode("utf-8")
    stats_bytes = stats_text.encode("utf-8")
    # Parse back before touching the target files.
    parsed = [json.loads(line) for line in jsonl_text.splitlines() if line]
    if len(parsed) != len(rows):
        raise AuditError("staged JSONL does not round-trip to the row count")
    if json.loads(stats_text)["schema"] != SCHEMA_ID:
        raise AuditError("staged stats schema mismatch")

    old = {}
    for path in (jsonl_path, stats_path):
        old[path] = path.read_bytes() if path.is_file() else None
    stage = out_dir / (".v3-staging-" + uuid.uuid4().hex)
    stage.mkdir()
    try:
        staged_jsonl = stage / jsonl_path.name
        staged_stats = stage / stats_path.name
        staged_jsonl.write_bytes(jsonl_bytes)
        staged_stats.write_bytes(stats_bytes)
        state = {
            "status": "building",
            "builder_version": BUILDER_VERSION,
            "started_at": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
            "outputs": {
                jsonl_path.name: sha256_bytes(jsonl_bytes),
                stats_path.name: sha256_bytes(stats_bytes),
            },
        }
        _state_write(state_path, state)
        os.replace(staged_jsonl, jsonl_path)
        os.replace(staged_stats, stats_path)
        if sha256_bytes(jsonl_path.read_bytes()) != state["outputs"][jsonl_path.name]:
            raise AuditError("final JSONL hash mismatch")
        if sha256_bytes(stats_path.read_bytes()) != state["outputs"][stats_path.name]:
            raise AuditError("final stats hash mismatch")
        state["status"] = "success"
        state["finished_at"] = _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")
        _state_write(state_path, state)
    except Exception as exc:  # noqa: BLE001 - restore and report
        for path, data in old.items():
            try:
                if data is None:
                    if path.exists():
                        path.unlink()
                else:
                    _atomic_write_bytes(path, data)
            except Exception:
                pass
        try:
            _state_write(state_path, {
                "status": "failed",
                "builder_version": BUILDER_VERSION,
                "failed_at": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
                "error": f"{type(exc).__name__}: {exc}",
            })
        except Exception:
            pass
        raise
    finally:
        shutil.rmtree(stage, ignore_errors=True)
    return jsonl_path, stats_path, state_path


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def build_ledger(audit_root, source_root, out_dir, v2_dir=None, verify_baseline=True,
                 expected_segments=None, write=True):
    audit_root = pathlib.Path(audit_root)
    source_root = pathlib.Path(source_root)
    out_dir = pathlib.Path(out_dir)
    v2_dir = pathlib.Path(v2_dir) if v2_dir else pathlib.Path(__file__).resolve().parent.parent / "v2"

    with tempfile.TemporaryDirectory(prefix="v3-v2-parse-") as tmp:
        base = v2.build_ledger(
            audit_root, source_root, pathlib.Path(tmp),
            verify_baseline=verify_baseline,
            expected_segments=expected_segments,
        )
    v2_rows = base["rows"]
    v2_stats = base["stats_data"]
    rows = [build_v3_row(r) for r in v2_rows]
    for row in rows:
        validate_evidence_row(row)
    stats = build_stats(rows, v2_rows=v2_rows, v2_stats=v2_stats)
    if not all(stats["integrity"].values()):
        failed = [k for k, v in stats["integrity"].items() if not v]
        raise AuditError("V3 integrity checks failed: " + repr(failed))
    jsonl_text = "\n".join(canonical(r) for r in rows) + "\n"
    stats_text = json.dumps(stats, ensure_ascii=False, indent=2) + "\n"
    outputs = None
    if write:
        outputs = write_outputs_atomic(out_dir, jsonl_text, stats_text, rows, stats)
    return {"rows": rows, "stats": stats, "v2_rows": v2_rows,
            "v2_stats": v2_stats, "outputs": outputs,
            "jsonl_text": jsonl_text, "stats_text": stats_text}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit-root", type=pathlib.Path,
                        default=pathlib.Path(r"F:\somethingProject\graduation-preflight-audit"))
    parser.add_argument("--source-root", type=pathlib.Path,
                        default=pathlib.Path(r"F:\somethingProject\dsbot-preflight"))
    parser.add_argument("--out-dir", type=pathlib.Path,
                        default=pathlib.Path(__file__).resolve().parent)
    parser.add_argument("--v2-dir", type=pathlib.Path, default=None)
    parser.add_argument("--no-baseline-check", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = build_ledger(
            args.audit_root, args.source_root, args.out_dir, v2_dir=args.v2_dir,
            verify_baseline=not args.no_baseline_check,
            expected_segments={"main": 140, "supplementary-subject": 10,
                               "supplementary-s7empty": 5, "b0-legacy": 10},
        )
    except AuditError as exc:
        print(f"V3 BUILD FAILED: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result["stats"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
