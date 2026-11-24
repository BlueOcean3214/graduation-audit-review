# 历史证据契约（V3）

- 契约版本：`graduation-derived-field-evidence/v3`
- 构建器版本：`3.0.0`；规则版本：`1.0.0`
- 适用对象：快照仓 `7b99ad96db78167c490874af9c4b48484b6d6ef0` 中冻结的 165 条结果记录
- 复核源码基线：`df155a5c145297bc5e6a085636fadfd6185586bd`（只读复核基线，**不是**运行时版本证明）
- 本契约只定义“历史工件能支持到什么程度的证据”，不修改冻结设计 §7.1，也不把外置证据变成原始记录。

## 1. 五条不可违反的规则

1. **原记录优先**：只有原始 `results.jsonl` 行里真实存在的字段才能标 `recorded`。本批 165 条没有任何 §7.1 字段，因此不存在 `recorded`。
2. **不得冒充**：审计定位符不是 `run_id`；复核提交不是 `base_sha`；Gold 值不是运行时值；代码路径推断不是运行时观测。
3. **确定性与唯一性**：每条派生值必须能由冻结工件 + 明确规则重算；映射不唯一即 `unknown`，不选“最像”的。
4. **逐字段独立判定**：不得因为其他字段可信就提升本字段状态；复合字段必须拆子字段，各自定状态。
5. **两层验收分离**：`original_contract_compliance` 与 `evidence_layer_integrity` 分别计算，后者 PASS 不能改变前者 FAIL。

## 2. 状态词（字段级）

| 状态 | 含义 | 本批是否使用 |
| --- | --- | --- |
| `recorded` | 原始记录中直接存在该字段值 | 否 |
| `externally_derived` | 由冻结工件按确定性规则唯一得到；值是外部追溯值，不是原始值 | 是 |
| `partially_derived` | 复合值中部分子字段为外部派生、部分只能推断/不可得 | 是（有注入条目的 memory） |
| `inferred` | 依赖代码语义、设计约定或 Gold 参照的推定，未被运行时工件直接证实 | 是（memory 子字段 runtime_status） |
| `gold_reference` | 仅作为期望值/参照，不可当作运行时事实 | 是（memory 子字段 gold_status） |
| `unknown` | 证据不足、映射歧义或语义未定，无法给出唯一值 | 保留 |
| `conflicting` | 多个同等强度证据互相矛盾 | 保留 |
| `unrecoverable` | 所需信息在生成时未记录且事后无法恢复（不是“暂时没找到”） | 是（run_id、base_sha、memory_id） |

状态不是质量排序，不能把 `inferred` 写成 `externally_derived` 来“提升可信度”。复合字段出现子状态差异时必须用 `partially_derived`，并在子字段中保留各自状态。

## 3. 逐字段语义

### 3.1 `run_id` — `unrecoverable`

- 要求：生成开始时唯一生成并写入记录。
- 事实：165 条均无该字段；记录中无任何可反推唯一运行标识的字段。
- 结论：值恒为 `null`，`verification=not_possible`。
- 禁止：把 `audit_locator`、`derived_batch_locator`、`experiment_id+时间戳` 写成 `run_id`。`audit_locator` 只是外部定位符（`is_original_run_id=false`）。

### 3.2 `base_sha` — `unrecoverable`

- 要求：运行开始时采集工作树提交，并独立记录工作树是否干净。
- 事实：执行报告给出的 `e5f97e9…` 是报告口径的基线，不是每份运行的运行时证明；事后 HEAD 不能证明当时状态；无逐运行 Git 元数据。
- 结论：`value=null`，`runtime_base_sha=null`，`execution_report_baseline=e5f97e9…` 且 `is_proof=false`，`runtime_source_version_verified=false`。
- 禁止：用 `reviewed_source_commit`（`df155a5…`）替代 `base_sha`。

### 3.3 `knowledge_result_ids` — `externally_derived`

- 规则 `HIST-KNOWLEDGE-EMPTY-CONFIG`。
- 本批 `config.knowledge_results=[]`、`knowledge_search_failed=false`，设计规定五组不做 RAG；155 条新数据另有 `config_sha256 → plan_sha256 → record.plan_sha256` 链；B0 10 条无 plan，仅有 prompt 文本明示“本次没有知识库检索结果”。
- 值：`[]`（165/165）。
- 验证：新数据 155 条 `verified`（哈希链闭合）；B0 10 条 `partially_verified`（prompt-only）。
- 限度：只证明**本批空配置**，不能推广为“任何运行都没有知识检索”。B0 不得与新数据同强度引用。

### 3.4 `memory_injected` — `partially_derived`

采用**条目数组**，每条含七个可分子字段：

| 子字段 | 状态 | 依据 |
| --- | --- | --- |
| `content` | `externally_derived` | prompt 记忆区块中的 content 与 Gold 记忆按 content 唯一匹配 |
| `memory_type` | `externally_derived` | prompt 的 type 与 Gold `memory_type` 一致（170/170） |
| `subject_key` | `externally_derived` | 由 Gold 的 `subject_key` 解析；prompt 展示的是 `subject_label or subject_key` |
| `strength` | `externally_derived` | prompt 强度与 Gold `strength` 一致（170/170） |
| `gold_status` | `gold_reference` | Gold 的 status，仅参照 |
| `memory_id` | `unrecoverable` | 注入渲染层剥离，未写入记录 |
| `runtime_status` | `inferred` | 只能由 `get_learning_memory → retrieve(status="active")` 的代码语义推定，且 prompt 不含 status |

规则 `HIST-MEMORY-PROMPT-TO-GOLD`：

- 条目数必须等于该组槽位应有数量；content 必须在该样本 Gold 中唯一命中；type、strength 必须一致；否则该行 `unknown` 并记录原因，不猜。
- 有注入条目的行 `partially_derived`；无注入条目的组（A/B/B0）为空数组，`externally_derived`。
- `runtime_status` 只允许 `value=null, inferred_value="active", verification=not_verified, confidence=low`，并列出阻断原因：无 `injected.json`、运行时 `base_sha` 不可恢复、prompt 不含 status、复核源码提交不是运行时证明。
- §5.6.6 要求“每份 run 的 `memory_injected` 与 `injected.json` 完全一致”。历史快照无 `injected.json`，故 `section_5_6_6_status=NOT_COMPLETED`，不得声称完成。
- 主题展示差异（S4 的 `中等` vs Gold `medium`）是已知 10 条，记录为展示差异，不以展示值覆盖 `subject_key`。

### 3.5 `short_term_injected` — 三谓词并列，原 Boolean 待定

规则 `HIST-SHORT-TERM-THREE-PREDICATES`。V3 不把任一谓词冒充冻结设计的单一 Boolean。

1. `short_term_slot_enabled`：组别矩阵是否开启 short 槽（`GROUP_SLOTS`）。
2. `short_term_block_present`：prompt 是否实际出现短期区块头（`【学习者近期情况（程序统计，非模型总结）】`）。
3. `short_term_feedback_history_present`：短期区块 JSON 的 `学习进度.已读取反馈数 > 0`。V2 的 `short_term_payload_nonempty` 实际就是这个谓词，V3 已更名，计数不变（75）。

本批：slot 80、block 80、feedback history 75。差异 5 条全部是 S7-empty 的 D 组：区块存在但反馈数为 0。冻结字段 `short_term_injected` 的 Boolean 语义标 `pending_advisor_confirmation`；`value.short_term_injected=null`。

### 3.6 `difficult_flag` — `externally_derived`

规则 `HIST-DIFFICULT-FEEDBACK-RULE`：

1. 取该样本最新一条反馈；`raw_condition = status=="partial" and reason=="任务难度太高"`。
2. 再叠加组别槽位：仅 feedback 槽开启的组（B/D/B0 设计差异）才可能为 true；B0 固定 `difficult=False`。
3. 最终 `value = raw_condition and feedback_slot_enabled`，并记录 `dynamic_rule_present_in_prompt`（`ai_service.py:159-182` 的固定规则是否出现在 prompt）。

本批 true 10 条，全部为 S7 的 B/D。B0 的 5 条 S7 原始条件为 true，但组定义固定 false，必须保留这一差异而不是判为矛盾。验证 `verified`（最新反馈、槽位、prompt 规则三处一致）。

### 3.7 `data_kind` — `externally_derived`

规则 `HIST-DATA-KIND-SAMPLE-SIMULATION`：

- 样本 `simulation.is_simulated=true` 且 `gold_standard.simulation=true`，`seed_fixture.py` 强制校验二者一致；prompt 含对应样例请求，样本与记录绑定成立。
- 值：`simulated_learner_fixture`（165/165）。
- 限度：8 个样本文件均**没有**原生 `data_kind` 字段，因此这不是 §3.4 “样本创建时写入”的合规证据，只是可追溯派生；验证 `partially_verified`。

## 4. 证据封套

每个字段是一个对象，八个必填键：

```json
{
  "value": null,
  "evidence_state": "unrecoverable",
  "original_field_present": false,
  "source_refs": [{"kind": "result_record", "path": "...", "line": 1}],
  "rule_id": "HIST-RUN-ID-UNRECOVERABLE",
  "rule_version": "1.0.0",
  "verification": "not_possible",
  "limitations": ["..."]
}
```

- `original_field_present` 逐字段记录；本批全为 false。
- `source_refs` 必须能定位到原始文件/行、prompt 哈希、plan 或样本；不得只写“见代码”。
- `limitations` 必须写明不能证明什么，尤其是“prompt 哈希只证明 prompt 内容与记录绑定，不证明实际发送给模型的字节或运行时注入集合”。
- `verification` 只描述该字段证据是否闭合，不描述整个契约。

## 5. 行级与构建级规则

- 一行对应一条原始记录；`audit_locator = runs/<run-dir>/results.jsonl:<line>`，165 个唯一。
- `identity=(experiment_id,sample_id,group,repeat_index)`；B0 另有 `b0.ordinal`，用 `(sample_id, experiment_id, repeat_index, run_dir)` 四元组映射，避免批次内 S5/S7 共用 experiment_id 的旧键冲突。
- 记录哈希：`record_sha256` 对原始行 UTF-8 字节（快照为 LF）计算；不得对重新序列化的对象计算。
- prompt 哈希：按 `build_prompts.py:485-493` 对 `[{system},{user}]` 的 canonical JSON 计算，不是对 txt 文件字节计算。
- 构建必须：全量内存构建 → 完整性检查 → 临时文件 → 回读校验 → 原子替换；失败恢复旧文件并写 `failed` 状态。禁止边算边覆盖。
- 统计只能从行重算，不得复制 V2 或手工常量；`V3-BUILD-STATE.json` 不进入 manifest。
- 重复构建必须逐字节一致；`generated_at` 不写入交付产物。

## 6. 双层验收

```json
"acceptance": {
  "original_contract_compliance": {"state": "FAIL", "records_with_all_seven": 0, "reason": "..."},
  "evidence_layer_integrity": {"state": "PASS", "checks": {...}}
}
```

- **original_contract_compliance**：按冻结 §7.1 与 `result_schema.py` 判定原始记录是否合规。本批 0 条含七字段，恒为 FAIL。
- **evidence_layer_integrity**：外置层自身是否 165/165、映射唯一、哈希闭合、统计自洽。PASS 仅说明“证据层可复核”，不说明原契约合规，也不构成预检放行。

## 7. 本契约明确不主张的事

1. 不主张 165 条已满足 §7.1。
2. 不主张 `run_id`/`base_sha` 已恢复。
3. 不主张 memory 运行时 status 已被观测。
4. 不主张 §5.6.6 已完成。
5. 不主张短期的单一 Boolean 语义已确定。
6. 不主张 `data_kind` 已满足 §3.4 的样本原生字段要求。
7. 不主张统计结论因外置层而改变；统计量仍只依赖原始记录字段。
8. 不主张方案 B 或任何契约修订已获批准。

## 8. 变更规则

- 任何规则变更必须提升 `rule_version`，并保持旧行可按旧版本复现；不得静默改判。
- 任何字段状态降级/升级都必须有新增证据工件；不得仅因复审意见改标签。
- 本契约不修改 `v2/`、V1 文件、165 条原始数据、冻结设计或 `result_schema.py`。
