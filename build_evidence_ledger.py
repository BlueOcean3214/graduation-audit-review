#!/usr/bin/env python3
"""Build an external derived-field evidence ledger for the 165 frozen
graduation experiment records.

Read-only with respect to both repositories. Writes only into this directory.
"""
from __future__ import annotations

import hashlib
import json
import pathlib
import sys

AUDIT_ROOT = pathlib.Path(r"F:\somethingProject\graduation-preflight-audit")
OUT_ROOT = pathlib.Path(r"F:\somethingProject\graduation-audit-output")
SRC_ROOT = pathlib.Path(r"F:\somethingProject\dsbot-preflight")

AUDIT_REPO = "https://github.com/BlueOcean3214/graduation-preflight-audit"
AUDIT_COMMIT = "7b99ad96db78167c490874af9c4b48484b6d6ef0"
SRC_REPO = "https://github.com/BlueOcean3214/AI-Study-Assistant"
SRC_COMMIT = "df155a5c145297bc5e6a085636fadfd6185586bd"

SEGMENTS = {
    "main-20261113T061051Z": "main",
    "suppl-subj-20261113T062711Z": "supplementary-subject",
    "suppl-s7empty-20261113T062822Z": "supplementary-s7empty",
    "b0-remainder-20261113T013105Z": "b0-legacy",
    "20261112T210000-20261113T011751Z": "b0-legacy",
    "20261112T210000-20261113T012031Z": "b0-legacy",
}

CODE = {
    "sanitize": "experiments/graduation/agent_tools.py:203-219",
    "get_learning_memory": "experiments/graduation/agent_tools.py:222-269",
    "status_filter": "experiments/graduation/agent_tools.py:267",
    "retrieve": "experiments/graduation/memory_service.py:2117-2190",
    "normalize_subject": "experiments/graduation/memory_service.py:normalize_subject",
    "derive_difficult": "experiments/graduation/agent_tools.py:414-435",
    "difficult_rule": "experiments/graduation/ai_service.py:159-182",
    "memory_fields": "experiments/graduation/agent_plan_draft.py:111-120",
    "memory_block": "experiments/graduation/agent_plan_draft.py:354-382",
    "draft_content": "experiments/graduation/agent_plan_draft.py:385-441",
    "slots": "experiments/graduation/build_prompts.py:44-67",
    "collect_inputs": "experiments/graduation/build_prompts.py:285-368",
    "group_inputs": "experiments/graduation/build_prompts.py:376-408",
    "seed_sim": "experiments/graduation/seed_fixture.py:92-93",
    "config_hash": "experiments/graduation/plan_schedule.py:64-83",
    "plan_digest": "experiments/graduation/plan_schedule.py:236-238",
    "prompt_hash": "experiments/graduation/build_prompts.py:485-493",
    "result_fields": "experiments/graduation/run_experiment.py:664-677",
    "schema_unrecoverable": "experiments/graduation/result_schema.py:275-277",
    "subject_filter": "experiments/graduation/build_prompts.py:84",
}

MEMORY_HEADER = "【真实长期学习记忆检索结果】"
SHORT_HEADER = "【学习者近期情况（程序统计，非模型总结）】"
KNOWLEDGE_NONE = "本次没有知识库检索结果"
DIFFICULT_RULE = "最近一次反馈是 partial 且原因是任务难度太高"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_json(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False)


def config_sha256(config) -> str:
    return sha256_bytes(canonical_json(config).encode("utf-8"))


def plan_digest(plan) -> str:
    payload = {k: v for k, v in plan.items() if k != "plan_sha256"}
    return sha256_bytes(canonical_json(payload).encode("utf-8"))


def split_prompt(text: str):
    pre = "===== SYSTEM =====\n"
    mid = "\n\n===== USER =====\n"
    if not (text.startswith(pre) and text.endswith("\n") and mid in text):
        raise ValueError("unexpected prompt envelope")
    body = text[len(pre):]
    idx = body.index(mid)
    return body[:idx], body[idx + len(mid):-1]


def prompt_hash(system: str, user: str) -> str:
    messages = [{"role": "system", "content": system},
                {"role": "user", "content": user}]
    return sha256_bytes(json.dumps(messages, ensure_ascii=False,
                                   sort_keys=True).encode("utf-8"))


def parse_memory_block(user: str):
    idx = user.find(MEMORY_HEADER)
    if idx < 0:
        return -1, []
    start = user.find("[", idx)
    entries, _ = json.JSONDecoder().raw_decode(user[start:])
    if not isinstance(entries, list):
        raise ValueError("memory block is not a list")
    return idx, entries


def load_b0_map():
    text = (AUDIT_ROOT / "B0-REPEAT-MAP.md").read_text(encoding="utf-8")
    mapping = {}
    rows = 0
    for line in text.splitlines():
        if not line.startswith("| S"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        sample, nth, _sid, _group, repeat, expid, run_dir = cells[:7]
        mapping[(expid, int(repeat))] = {"sample_id": sample, "ordinal": int(nth),
                                         "run_dir": run_dir}
        rows += 1
    return mapping, rows


def feedback_latest(sample):
    fb = sample.get("feedbacks") or []
    if not fb:
        return None
    last = fb[-1]
    return {"index": len(fb), "task": last.get("task"),
            "status": last.get("status"), "reason": last.get("reason"),
            "created_at": last.get("created_at")}


def main() -> int:
    config = json.loads((AUDIT_ROOT / "config" / "config.json").read_text(encoding="utf-8"))
    config_hash = config_sha256(config)
    samples = {}
    for path in sorted((AUDIT_ROOT / "samples").glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        samples[data["sample_id"]] = data

    plans = {}
    for path in sorted(AUDIT_ROOT.glob("runs/*/plan.json")):
        plan = json.loads(path.read_text(encoding="utf-8"))
        plans[path.parent.name] = plan

    b0_map, b0_rows = load_b0_map()

    records = []
    for run_dir in sorted((AUDIT_ROOT / "runs").iterdir()):
        if not run_dir.is_dir():
            continue
        segment = SEGMENTS[run_dir.name]
        result_file = run_dir / "results.jsonl"
        lines = result_file.read_text(encoding="utf-8").splitlines()
        for lineno, line in enumerate(lines, 1):
            if not line.strip():
                continue
            rec = json.loads(line)
            records.append((run_dir, segment, lineno, rec))

    out_lines = []
    stats = {
        "records": len(records),
        "by_segment": {},
        "prompt_hash_ok": 0,
        "prompt_hash_bad": [],
        "prompt_chars_ok": 0,
        "knowledge_none_prompt": 0,
        "plan_ok": 0,
        "plan_config_ok": 0,
        "plan_task_fields_ok": 0,
        "plan_task_fields_bad": [],
        "plan_sha_record_ok": 0,
        "identity_unique": 0,
        "memory_records": 0,
        "memory_entries": 0,
        "memory_map_unique": 0,
        "memory_nonactive": [],
        "memory_count_mismatch": [],
        "short_true": 0,
        "short_false": 0,
        "difficult_true": 0,
        "rule_present": 0,
        "b0_map_matched": 0,
        "sample_link_ok": 0,
        "data_kind_sim_ok": 0,
        "request_in_prompt": 0,
        "records_with_seven_fields": 0,
        "memory_strength_mismatch": [],
        "memory_type_mismatch": [],
    }
    SEVEN = {"run_id", "base_sha", "knowledge_result_ids", "memory_injected",
             "short_term_injected", "difficult_flag", "data_kind"}
    seen_ids = set()

    for run_dir, segment, lineno, rec in records:
        sid = rec["sample_id"]
        group = rec["group"]
        sample = samples[sid]
        prompt_path = run_dir / rec["prompt_ref"]
        prompt_text = prompt_path.read_text(encoding="utf-8")
        system, user = split_prompt(prompt_text)
        recomputed = prompt_hash(system, user)
        hash_ok = recomputed == rec.get("prompt_sha256")
        stats["prompt_hash_ok"] += int(hash_ok)
        if not hash_ok:
            stats["prompt_hash_bad"].append(f"{run_dir.name}:{lineno}")
        stats["prompt_chars_ok"] += int(len(user) == rec.get("prompt_chars"))
        stats["by_segment"][segment] = stats["by_segment"].get(segment, 0) + 1
        stats["knowledge_none_prompt"] += int(KNOWLEDGE_NONE in user)
        stats["sample_link_ok"] += int(str(sample.get("current_user_request", "")) in user)
        stats["request_in_prompt"] += int(str(sample.get("current_user_request", "")) in user)
        stats["data_kind_sim_ok"] += int(
            sample.get("simulation", {}).get("is_simulated") is True
            and sample.get("gold_standard", {}).get("simulation") is True)
        stats["records_with_seven_fields"] += int(bool(SEVEN & set(rec.keys())))
        identity = (rec.get("experiment_id"), sid, group, rec.get("repeat_index"))
        if identity not in seen_ids:
            seen_ids.add(identity)
            stats["identity_unique"] += 1

        plan = plans.get(run_dir.name)
        plan_info = None
        if plan:
            plan_tasks = {(b["sample_id"], t["group"], t["repeat_index"]): t
                          for b in plan["blocks"] for t in b["tasks"]}
            task = plan_tasks.get((sid, group, rec.get("repeat_index")))
            in_plan = task is not None
            sha_match = rec.get("plan_sha256") == plan.get("plan_sha256")
            cfg_match = plan.get("config_sha256") == config_hash
            plan_seq_ok = bool(task) and task.get("plan_seq") == rec.get("plan_seq")
            round_ok = bool(task) and task.get("round_index") == rec.get("round_index")
            stats["plan_ok"] += int(in_plan)
            stats["plan_sha_record_ok"] += int(sha_match)
            stats["plan_config_ok"] += int(cfg_match)
            stats["plan_task_fields_ok"] += int(plan_seq_ok and round_ok)
            if not (plan_seq_ok and round_ok):
                stats["plan_task_fields_bad"].append(
                    f"{run_dir.name}:{lineno} {sid}/{group}/r{rec.get('repeat_index')}")
            plan_info = {
                "file": f"runs/{run_dir.name}/plan.json",
                "identity_in_plan": in_plan,
                "plan_seq_matches_record": plan_seq_ok,
                "round_index_matches_record": round_ok,
                "plan_sha256_matches_record": sha_match,
                "config_sha256_matches_snapshot_config": cfg_match,
                "plan_sha256": plan.get("plan_sha256"),
            }

        b0_info = None
        if segment == "b0-legacy":
            key = (rec.get("experiment_id"), rec.get("repeat_index"))
            hit = b0_map.get(key)
            b0_info = {"ordinal": hit["ordinal"] if hit else None,
                       "mapped_via": "B0-REPEAT-MAP.md",
                       "repeat_index_collides_across_run_dirs": True}
            stats["b0_map_matched"] += int(hit is not None)

        # ---- memory_injected ----
        mem_idx, entries = parse_memory_block(user)
        expected_memories = []
        if group in ("C", "D", "C-subj", "D-subj"):
            active = [m for m in sample["gold_standard"].get("memories", [])
                      if m.get("injected") is True]
            if group in ("C-subj", "D-subj"):
                active = [m for m in active if m.get("subject_key") == "概率论"]
            expected_memories = active
        mem_values = []
        mem_evidence = []
        for pos, entry in enumerate(entries):
            content = entry.get("content")
            hits = [m for m in sample["gold_standard"].get("memories", [])
                    if m.get("content") == content]
            if len(hits) == 1:
                gold = hits[0]
                stats["memory_map_unique"] += 1
                status = gold.get("status")
                if status != "active" or gold.get("injected") is not True:
                    stats["memory_nonactive"].append(
                        f"{run_dir.name}:{lineno}#{pos} {sid}/{group}")
                mem_values.append({
                    "memory_type": gold.get("memory_type"),
                    "subject_key": gold.get("subject_key"),
                    "strength": gold.get("strength"),
                    "status": status,
                })
                mem_evidence.append({
                    "index": pos,
                    "prompt_subject": entry.get("subject"),
                    "prompt_type": entry.get("type"),
                    "content": content,
                    "gold_index": sample["gold_standard"]["memories"].index(gold),
                    "subject_label": gold.get("subject_label"),
                    "status_basis": "gold.memories.status + injected=true; "
                                    "get_learning_memory only passes status='active'",
                    "type_matches_prompt": entry.get("type") == gold.get("memory_type"),
                    "strength_matches_prompt": entry.get("strength") == gold.get("strength"),
                })
                if entry.get("type") != gold.get("memory_type"):
                    stats["memory_type_mismatch"].append(f"{run_dir.name}:{lineno}#{pos}")
                if entry.get("strength") != gold.get("strength"):
                    stats["memory_strength_mismatch"].append(f"{run_dir.name}:{lineno}#{pos}")
            else:
                stats["memory_map_unique"] += 0
                mem_evidence.append({"index": pos, "content": content,
                                     "error": f"gold content matches={len(hits)}",
                                     "state": "unknown"})
                mem_values.append({"memory_type": None, "subject_key": None,
                                   "strength": None, "status": None})
        if len(entries) != len(expected_memories) and group in ("C", "D", "C-subj", "D-subj"):
            stats["memory_count_mismatch"].append(
                f"{run_dir.name}:{lineno} {sid}/{group} got={len(entries)} expected={len(expected_memories)}")
        stats["memory_records"] += int(bool(entries))
        stats["memory_entries"] += len(entries)

        mem_state = "derived" if all(e.get("state") != "unknown" for e in mem_evidence) else "unknown"
        memory_field = {
            "state": mem_state,
            "value": mem_values,
            "evidence": {
                "prompt_block_present": mem_idx >= 0,
                "prompt_entry_count": len(entries),
                "expected_injected_count": len(expected_memories),
                "entries": mem_evidence,
                "slot_enabled": group in ("C", "D", "C-subj", "D-subj"),
                "subject_filter": "概率论" if group in ("C-subj", "D-subj") else None,
            },
            "code_refs": [CODE["sanitize"], CODE["get_learning_memory"],
                          CODE["status_filter"], CODE["retrieve"],
                          CODE["memory_fields"], CODE["memory_block"]],
            "caveat": "prompt 的 memory 区块不含 status/memory_id；status='active' 是由"
                      "唯一已知消费者（get_learning_memory→retrieve(status='active')）"
                      "与 gold.injected=true 共同推定的，运行时源码版本未由 base_sha 绑定。",
        }

        # ---- short_term_injected ----
        short_present = SHORT_HEADER in user
        short_slot = group in ("B", "D", "D-subj")
        stats["short_true" if short_present else "short_false"] += 1
        short_field = {
            "state": "derived" if short_present == short_slot else "unknown",
            "value": short_present,
            "evidence": {
                "marker_present": short_present,
                "slot_enabled": short_slot,
                "section_title": SHORT_HEADER,
                "note": "按 §7.1 boolean 取『实际内容注入』语义；S7-empty 的 D 组区块存在但计数为 0。",
            },
            "code_refs": [CODE["slots"], CODE["group_inputs"], CODE["draft_content"]],
        }

        # ---- difficult_flag ----
        latest = feedback_latest(sample)
        raw_condition = bool(latest and latest["status"] == "partial"
                             and latest["reason"] == "任务难度太高")
        feedback_slot = group in ("B", "D", "D-subj")
        if group == "B0":
            difficult_value = False
        elif feedback_slot:
            difficult_value = raw_condition
        else:
            difficult_value = False
        rule_present = DIFFICULT_RULE in user
        stats["rule_present"] += int(rule_present)
        stats["difficult_true"] += int(difficult_value)
        agree = (rule_present == difficult_value) if group != "B0" else (rule_present is False)
        difficult_field = {
            "state": "derived" if agree else "unknown",
            "value": difficult_value,
            "evidence": {
                "latest_feedback": latest,
                "raw_condition_partial_and_reason": raw_condition,
                "feedback_slot_enabled": feedback_slot,
                "b0_fixed_false": group == "B0",
                "dynamic_rule_present_in_prompt": rule_present,
                "agree": agree,
            },
            "code_refs": [CODE["derive_difficult"], CODE["difficult_rule"], CODE["slots"]],
        }

        # ---- knowledge_result_ids ----
        knowledge_field = {
            "state": "derived",
            "value": [],
            "evidence": {
                "config_knowledge_results": config.get("knowledge_results"),
                "config_knowledge_search_failed": config.get("knowledge_search_failed"),
                "config_sha256": config_hash,
                "plan_config_sha256_matches": None if plan is None else plan_info["config_sha256_matches_snapshot_config"],
                "prompt_states_no_knowledge": KNOWLEDGE_NONE in user,
                "b0_legacy_no_plan_binding": group == "B0",
                "note": "prompt 明示本次没有知识库检索结果 → id 列表为空；"
                        "新数据另有 config→plan→record 哈希链，B0 只有 prompt 文本证据。",
            },
            "code_refs": [CODE["collect_inputs"], CODE["config_hash"], CODE["prompt_hash"]],
        }

        # ---- data_kind ----
        data_kind_field = {
            "state": "derived",
            "value": "simulated_learner_fixture",
            "evidence": {
                "sample_file": f"samples/{sid}.json",
                "sample_simulation_is_simulated": sample.get("simulation", {}).get("is_simulated"),
                "gold_simulation": sample.get("gold_standard", {}).get("simulation"),
                "seed_fixture_requires_is_simulated": True,
                "sample_id_linked_via_prompt_request": str(sample.get("current_user_request", "")) in user,
                "design_section": "§3.4",
            },
            "code_refs": [CODE["seed_sim"], "docs/GRADUATION-EXPERIMENT-DESIGN.md §3.4"],
        }

        # ---- run_id / base_sha ----
        locator = f"runs/{run_dir.name}/results.jsonl:{lineno}"
        run_id_field = {
            "state": "unrecoverable",
            "value": None,
            "reason": "生产器从未写入 run_id；results.jsonl 字段集不含该字段，事后无法还原"
                      "生成时刻的 run_id（§7.1 示例形态含 generated_at/sample/group/round，"
                      "但原始记录未保存生成时的 run 标识）。",
            "evidence": {
                "record_fields": sorted(rec.keys()),
                "audit_locator": locator,
                "audit_locator_is_not_run_id": True,
            },
            "code_refs": [CODE["result_fields"], "docs/GRADUATION-EXPERIMENT-DESIGN.md §7.1"],
        }
        base_sha_field = {
            "state": "unrecoverable",
            "value": None,
            "reason": "运行器未在开始时记录 git HEAD/工作树状态；执行报告中的基线提交只是"
                      "报告声明，不能证明运行当时工作树干净或确为该提交。",
            "evidence": {
                "record_fields": sorted(rec.keys()),
                "execution_report_baseline_is_not_proof": True,
            },
            "code_refs": [CODE["result_fields"], "docs/GRADUATION-EXPERIMENT-CONTRACT-REPORT.md §3"],
        }

        out = {
            "source": {
                "repository": AUDIT_REPO,
                "commit": AUDIT_COMMIT,
                "result_file": f"runs/{run_dir.name}/results.jsonl",
                "line_number": lineno,
                "sample_id": sid,
                "group": group,
                "repeat_index": rec.get("repeat_index"),
                "experiment_id": rec.get("experiment_id"),
                "prompt_ref": rec.get("prompt_ref"),
                "prompt_sha256": rec.get("prompt_sha256"),
            },
            "segment": segment,
            "audit_locator": locator,
            "b0": b0_info,
            "prompt": {
                "file": f"runs/{run_dir.name}/{rec.get('prompt_ref')}",
                "sha256_recomputed": recomputed,
                "sha256_matches_record": hash_ok,
                "user_chars_recomputed": len(user),
                "prompt_chars_matches_record": len(user) == rec.get("prompt_chars"),
            },
            "plan": plan_info,
            "fields": {
                "run_id": run_id_field,
                "base_sha": base_sha_field,
                "knowledge_result_ids": knowledge_field,
                "memory_injected": memory_field,
                "short_term_injected": short_field,
                "difficult_flag": difficult_field,
                "data_kind": data_kind_field,
            },
        }
        out_lines.append(json.dumps(out, ensure_ascii=False))

    # ---- global integrity ----
    checks = {
        "record_count_165": len(out_lines) == 165,
        "unique_identity_165": stats["identity_unique"] == 165,
        "prompt_hash_all": stats["prompt_hash_ok"] == 165,
        "prompt_chars_all": stats["prompt_chars_ok"] == 165,
        "plan_identity_all_new": stats["plan_ok"] == 155,
        "plan_sha_record_all_new": stats["plan_sha_record_ok"] == 155,
        "plan_config_all": stats["plan_config_ok"] == 155,
        "plan_task_fields_all": stats["plan_task_fields_ok"] == 155,
        "plan_task_fields_bad": stats["plan_task_fields_bad"],
        "knowledge_none_all": stats["knowledge_none_prompt"] == 165,
        "b0_map_all": stats["b0_map_matched"] == 10,
        "b0_map_rows": b0_rows,
        "sample_link_all": stats["sample_link_ok"] == 165,
        "data_kind_sim_all": stats["data_kind_sim_ok"] == 165,
        "memory_entries_total": stats["memory_entries"],
        "memory_map_unique": stats["memory_map_unique"],
        "memory_nonactive": stats["memory_nonactive"],
        "memory_count_mismatch": stats["memory_count_mismatch"],
        "records_with_seven_fields": stats["records_with_seven_fields"],
        "memory_type_mismatch": stats["memory_type_mismatch"],
        "memory_strength_mismatch": stats["memory_strength_mismatch"],
        "segments": stats["by_segment"],
        "short_true": stats["short_true"],
        "short_false": stats["short_false"],
        "difficult_true": stats["difficult_true"],
        "rule_present": stats["rule_present"],
    }

    (OUT_ROOT / "DERIVED-FIELD-EVIDENCE.jsonl").write_text(
        "\n".join(out_lines) + "\n", encoding="utf-8", newline="\n")
    (OUT_ROOT / "_stats.json").write_text(
        json.dumps({"stats": stats, "checks": checks}, ensure_ascii=False, indent=2),
        encoding="utf-8")

    print(json.dumps(checks, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
