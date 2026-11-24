# 历史实验数据追溯与证据台账 V2 修复报告

- 文档版本：V2 实施报告（2026-11-24）
- 审计快照：`BlueOcean3214/graduation-preflight-audit` @ `7b99ad96db78167c490874af9c4b48484b6d6ef0`（只读）
- 复核源码：`BlueOcean3214/AI-Study-Assistant` @ `df155a5c145297bc5e6a085636fadfd6185586bd`（只读）
- 第一版审计交付：`BlueOcean3214/graduation-audit-review` @ `10a52394f110d471f9f36d832c56388c836e70ee`
- 本报告对应的 V2 产物位于本仓库 `v2/`，不覆盖第一版任何文件。

> 本报告只描述历史数据的可追溯性，不改变原始记录，不改变 `result_schema.py`，也不让 PR #26 的预检转为 PASS。历史 165 条记录仍缺少 §7.1 原始字段；预检按原始合同仍应报告 FAIL。

## 1. 执行摘要

本轮完成四项整改：

1. **B0 映射校验**：旧逻辑以 `(experiment_id, repeat_index)` 为键，在 `b0-remainder` 中 S5 与 S7 共用 experiment_id 时发生覆盖；新逻辑使用 `(sample_id, experiment_id, repeat_index, run_dir)` 四元组，并对映射表、唯一键、逐条字段、ordinal、未使用行全部 fail-closed。历史 10 条 B0 的 ordinal 经独立复核全部正确，未发现历史数据错误。
2. **memory 字段级证据**：170 条记忆全部按 content 唯一映射到 Gold；`content`、`memory_type`、`subject_key`、`strength` 标为 externally_derived；Gold 中的 status 单独标为 gold_reference；历史运行时 status 标为 inferred（低置信度，verification=not_verified），不再输出裸 `status="active"`。明确声明 §5.6.6 未完成。
3. **短期记忆三谓词**：拆成 `short_term_slot_enabled`、`short_term_block_present`、`short_term_payload_nonempty`，分别统计为 80 / 80 / 75；S7-empty 的 5 条 D 组记录是唯一差异来源。没有重定义冻结设计的 Boolean，兼容性决定留给导师。
4. **不可恢复字段**：`run_id`、`base_sha` 保持 `unrecoverable`，不填任何替代值；用 `audit_locator` 和 `derived_batch_locator` 提供定位与批次追溯；`reviewed_source_commit` 只表示本次审计复核所用源码，并显式标注 `runtime_source_version_verified=false`。

V2 共 165 行，逐条可严格解析，165 个唯一 `audit_locator`；B0 10/10 唯一映射；memory 170/170；短期三谓词 80/80/75；所有完整性检查为 true。新增 42 项单元/全量回归测试，全部通过。

## 2. 基线与只读边界

| 对象 | 固定版本 | 使用方式 |
| --- | --- | --- |
| 数据快照 | `7b99ad96db78167c490874af9c4b48484b6d6ef0` | 只读，逐字节读取 JSONL、Prompt、plan、config、样本 |
| 复核源码 | `df155a5c145297bc5e6a085636fadfd6185586bd` | 只读，用于确认字段生产者与消费路径 |
| 第一版审计 | `10a52394f110d471f9f36d832c56388c836e70ee` | 只读，不覆盖、不改写 |
| PR #26 | `BlueOcean3214/AI-Study-Assistant#26` | 未修改、未合并 |

V2 构建器在启动时检查两个本地工作树的 HEAD 与 clean 状态；不满足固定提交或工作树有改动时直接失败。实际执行时快照仓与源码仓均 clean。

没有访问 `feedback.db`、其他真实数据库、`blind_private/`；没有执行真实 `--repack`；没有重新生成任何历史实验；没有修改 165 条 `results.jsonl`。

## 3. B0 映射漏洞与修复

### 3.1 旧逻辑

第一版 `build_evidence_ledger.py` 的 `load_b0_map()` 使用：

```python
(experiment_id, repeat_index)
```

作为字典键，后续只判断 `hit is not None`，不校验 `sample_id` 与 `run_dir`。

`b0-remainder-20261113T013105Z` 中 S5 与 S7 共用同一个 experiment_id，二者都有 `repeat_index=0,1,2,3`。10 行 B0 映射因此只有 6 个唯一旧键：S7 覆盖 S5 的 4 个条目。旧逻辑下，一条 S5 remainder 记录可以命中 S7 的 map row 而被当成“有效映射”。

需要强调：这不是已经证实的历史结果错误。按四元组独立复核，10 条记录分别命中正确的 S5/S7 第 1–5 次，ordinal 全部正确；问题在于旧校验不能证明这一点，而不是历史 ordinal 被写错。

### 3.2 新逻辑

V2 使用四元组：

```python
(sample_id, experiment_id, repeat_index, run_dir)
```

并执行以下 fail-closed 检查：

1. `parse_b0_map()` 校验表头 18 列、每行 `sample_id` 与列一致、`group=B0`、ordinal/repeat_index 可解析且 ordinal≥1；四元组重复立即抛 `B0MappingError`。
2. `validate_b0_records()` 校验映射行数、唯一键数、B0 记录数、记录四元组唯一性。
3. 每条记录按四元组精确命中；任何字段不一致、缺失映射、未使用映射都会进入 `b0_map_errors`。
4. ordinal 不取自映射表自报值，而是按每个 sample 的实际记录 `generated_at`（同时间再按 audit_locator）排序计算第 n 次，再与 map 的 ordinal 比较。
5. `b0_map_all` 不是“命中数=10”就为真，而是所有计数等于期望值且 `b0_map_errors=[]` 的合取；不满足时直接抛错，不写出产物。

### 3.3 实测统计

| 指标 | 值 |
| --- | ---: |
| `b0_map_rows` | 10 |
| `b0_map_unique_keys` | 10 |
| `b0_map_record_count` | 10 |
| `b0_map_matched` | 10 |
| `b0_map_sample_matches` | 10 |
| `b0_map_experiment_matches` | 10 |
| `b0_map_repeat_matches` | 10 |
| `b0_map_run_dir_matches` | 10 |
| `b0_map_ordinal_matches` | 10 |
| `b0_map_legacy_key_collisions` | 4（仅用于说明旧键退化，不参与 V2 匹配） |
| `b0_map_errors` | `[]` |
| `b0_map_all` | true |

四元组验证结果：S5、S7 各 5 条，分别映射到 B0 第 1–5 次；10 条记录的 `prompt_sha256` 与对应 Prompt 文件重算一致；B0 记录无 `plan.json`，`plan` 字段为 `null`，这是 legacy 事实，不是缺失。

### 3.4 回归测试

`v2/tests/test_b0_mapping.py` 覆盖：

- S5/S7 共用 experiment_id 时四元组不发生覆盖；
- 旧 lookup 只剩 2 个键且 `(exp, 0)`、`(exp, 1)` 都指向 S7，证明旧逻辑会把 S5 记录路由到 S7；
- 新 map 中 S5 remainder 命中 S5，ordinal 正确；
- 完全重复的四元组被拒绝；
- 删除一条映射记录（记录无对应 map row）被拒绝；
- `run_dir` 不一致被拒绝；
- ordinal 不一致被拒绝；
- 真实 `B0-REPEAT-MAP.md` 为 10 行、10 唯一键、旧逻辑 6 键；
- 165 条全量快照回归由 `test_full_snapshot_v2.py` 覆盖。

## 4. memory_injected 的分层证据

### 4.1 为什么不能直接写 status

源码路径（复核版本 `df155a5`）：

- `agent_tools.py:203-219` 的 `_sanitize_memory()` 只保留 type/subject/content/strength/evidence_count/episode/evidence_feedback_ids/updated_at；**剥离 status 和 memory_id**。
- `agent_tools.py:222-269` 的 `get_learning_memory()` 在 `:267` 固定传 `status="active"`。
- `memory_service.py:2117-2190` 的 `retrieve()` 返回 status，但 Prompt 只包含 `agent_plan_draft.py:111-120` 白名单字段，status 不会进入 Prompt。
- `agent_plan_draft.py:354-382` 的 `_memory_block()` 只序列化白名单字段；`:385-441` 的 `_build_draft_user_content()` 只在 memories 非空时插入区块。

因此：

- Prompt 能证明“哪些 content 被注入”；
- Prompt 不能证明运行时读到的是 active 还是 weakened/resolved；
- 冻结设计 §5.6.6 要求的 `injected.json` 在快照仓库和源码仓库中都不存在；
- 历史 `base_sha` 不可恢复，不能证明历史运行使用的就是 `df155a5`。

### 4.2 V2 子字段分级

每条 memory 的 `subfields` 结构如下：

| 子字段 | V2 state | 依据 |
| --- | --- | --- |
| `content` | externally_derived | Prompt 中实际出现的 content；与 Gold 唯一精确匹配 |
| `memory_type` | externally_derived | Prompt type 与 Gold memory_type 双源一致（170/170） |
| `subject_key` | externally_derived | Gold 元数据；Prompt 只显示 subject_label 或 key 的展示值 |
| `strength` | externally_derived | Prompt strength 与 Gold strength 一致（170/170） |
| `gold_status` | gold_reference | 只表示夹具 Gold 的期望值，不是运行时读取 |
| `runtime_status` | inferred 或 unknown | Gold active/injected + 当前源码只传 active；低置信度、未验证 |

`runtime_status` 为 inferred 时，对象同时带有：

```json
{
  "state": "inferred",
  "value": "active",
  "verification": "not_verified",
  "confidence": "low",
  "section_5_6_6_compared": false,
  "basis": ["..."],
  "blocked_by": [
    "runtime_base_sha_unrecoverable",
    "injected_json_absent",
    "prompt_omits_status",
    "reviewed_source_commit_is_not_runtime_proof"
  ]
}
```

不存在顶层裸 `status` 字段；170 条条目均无裸 status。

### 4.3 匹配结果

- 有注入条目的记录：80 条；条目总数：170。
- 按 content 与 Gold 唯一匹配：170/170。
- memory_type 一致：170/170。
- strength 一致：170/170。
- subject_key 解析成功：170/170。
- subject 展示值与 Gold 的 label 或 key 一致：160/170。
- 10 条展示值不一致：全部是 S4 的 `time_pattern` 记忆，Prompt 显示“中等”，Gold 的 `subject_key`/`subject_label` 为“medium”；content 唯一匹配、type/strength 一致，因此 subject_key 仍由 Gold 外置派生，但该展示差异被记录在 `subject_label_mismatches`，不隐藏。
- 注入的 170 条全部对应 Gold `status="active"` 且 `injected=true`；没有发现 weakened/resolved 被注入。
- 分段条目：主实验 150（70 条记录），subject 补充 20（10 条记录），S7-empty 0，B0 legacy 0。

### 4.4 §5.6.6 的状态

V2 明确记录：

- `section_5_6_6_status = NOT_COMPLETED`；
- `injected_json_reference_present = false`；
- 原因：没有 `injected.json`、运行时 base_sha 不可恢复、Prompt 不含 status、复核源码提交不能证明运行时源码版本。

因此，170 条映射能说明“Prompt 中出现的记忆与 Gold 的 content/type/strength 高度一致”，不能说明“运行时状态经过逐项核对”，也不能声称完成 §5.6.6。

## 5. 短期记忆三谓词

冻结设计 §7.1 只给了一个 Boolean `short_term_injected`，没有区分“槽位是否开启”“Prompt 是否出现区块”“区块是否有实际历史”。V2 不重定义原字段，而是并列三个谓词。

### 5.1 定义

1. `short_term_slot_enabled`
   - 含义：实验组的短期记忆槽位是否开启。
   - 依据：固定实验矩阵 + `build_prompts.py:44-67` 的 `GROUP_SLOTS`；不是从 Prompt 区块反推。
2. `short_term_block_present`
   - 含义：Prompt 的 user 内容中是否实际出现标题 `【学习者近期情况（程序统计，非模型总结）】`。
   - 依据：Prompt 原文；出现后再检查 `<<<LEARNER_CONTEXT_DATA>>>` 与 `<<<END>>>` 标记。
3. `short_term_payload_nonempty`
   - 含义：区块中的 learner-context JSON 是否真正包含非空学习历史。
   - 依据：解析 JSON 的 `学习进度.已读取反馈数`，严格大于 0 才为 true；不是看到区块头就为 true。

### 5.2 统计

| 谓词 | true | false |
| --- | ---: | ---: |
| `short_term_slot_enabled` | 80 | 85 |
| `short_term_block_present` | 80 | 85 |
| `short_term_payload_nonempty` | 75 | 90 |

分段：

| 分段 | 记录数 | slot true | block true | payload true |
| --- | ---: | ---: | ---: | ---: |
| 主实验 | 140 | 70 | 70 | 70 |
| subject 补充 | 10 | 5 | 5 | 5 |
| S7-empty 补充 | 5 | 5 | 5 | 0 |
| B0 legacy | 10 | 0 | 0 | 0 |

S7-empty 的 5 条 D 组记录：

- slot=true：D 组按设计开启短期槽位；
- block=true：Prompt 确实出现区块；
- payload=false：`已读取反馈数=0`，没有实际学习历史；
- 这 5 条正是 `block_present` 80 与 `payload_nonempty` 75 的差值来源。

没有硬编码 80/80/75；三个数都是逐条计算后聚合。若重新计算不一致，构建器会在 integrity 检查中失败，而不是修改判定去匹配预期。

### 5.3 与冻结设计的关系

V2 没有修改冻结设计，也没有把三个谓词中的任何一个宣布为 §7.1 Boolean 的新定义。`frozen_field_compatibility` 明确记录：

- `v2_redefines_original_field = false`
- `candidate_meaning = short_term_block_present`
- `decision = pending_advisor_confirmation`

原字段究竟取“槽位开启”“区块出现”还是“内容非空”，需要导师确认；V2 只是把三种语义分开，避免一个 Boolean 混合三件事。

## 6. run_id 与 base_sha 的不可恢复表达

### 6.1 run_id

- 原始字段状态：`unrecoverable`，`value=null`，`recorded_at_generation=false`。
- 原因：生产器从未写入 run_id，结果记录字段集中没有该字段；生成后无法还原当时的 run 标识。
- 追溯方式：
  - `audit_locator`：`runs/<run-dir>/results.jsonl:<line>`，是本轮外置审计定位符，不是 run_id；
  - `derived_batch_locator`：`batch:<experiment_id>`，由原始记录中的 experiment_id 生成，明确 `is_original_run_id=false`。
- 不使用 `generated_at+sample+group+round` 合成 run_id；该合成值即使唯一，也只能叫派生定位符，不能叫原始 run_id。

### 6.2 base_sha

`base_sha` 使用三层结构：

```json
{
  "state": "unrecoverable",
  "value": null,
  "runtime_base_sha": {"state": "unrecoverable", "value": null},
  "reviewed_source_commit": "df155a5c145297bc5e6a085636fadfd6185586bd",
  "reviewed_source_commit_scope": "audit_metadata_only",
  "runtime_source_version_verified": false,
  "evidence": {
    "execution_report_baseline": "e5f97e9fd9d721af24ed5d7a6c047ff305fd3fcd",
    "execution_report_baseline_is_proof": false,
    "base_sha_not_substituted_by_reviewed_commit": true
  }
}
```

- `reviewed_source_commit` 只表示本轮审计复核所用源码；不写入 `base_sha` 的 value。
- `execution_report_baseline` 只是执行报告的声明，不等于运行当时工作树干净的证明；明确 `is_proof=false`。
- 不声称 165 条历史记录由 `df155a5` 运行；`runtime_source_version_verified=false`。

## 7. 其他字段

### 7.1 knowledge_result_ids

- 165/165 为 `[]`，state=externally_derived。
- 证据：快照 `config/config.json` 的 `knowledge_results=[]`、`knowledge_search_failed=false`；155 条新数据的 plan 与 config_sha256 链一致；165 条 Prompt 均含“本次没有知识库检索结果”。
- scope 明确为 `empty_configuration_only`：只证明本批空配置，不能推广到非空检索结果的恢复能力。
- B0 10 条没有 plan→config 哈希链，plan_binding 标为 `not_available_for_b0_legacy`，仅由 Prompt 文本明示支撑。

### 7.2 difficult_flag

- 条件：最新一条反馈 `status="partial"` 且 `reason="任务难度太高"`；再叠加组的 feedback 槽位。
- 165 条中 true 10 条，全部是 S7 的 B/D 组（主实验 10 条）。
- B0 特殊：S7 的 5 条 B0 记录原始最新反馈确实满足 partial/难度太高，但 B0 组设计固定 `difficult=False`，且 Prompt 无动态规则。V2 的 value=false，同时记录 `raw_condition_partial_and_reason=true`、`b0_group_fixed_false=true`，不把原始反馈条件等同于 B0 的实验标记。
- 其余组：A/C/C-subj 无 feedback 槽位，value=false；B/D 按最新反馈计算，并与 Prompt 中动态规则出现与否交叉核验。

### 7.3 data_kind

- 165/165 派生为 `simulated_learner_fixture`。
- 依据：8 个样本文件均 `simulation.is_simulated=true`、`gold_standard.simulation=true`，且 `seed_fixture.py:91-96` 强制校验；每条 Prompt 都能链接到对应样本的 `current_user_request`。
- 但样本文件本身没有 §3.4 要求的 `data_kind` 字段；因此这是 provenance 派生值，不是原始样本/记录直接生成的值，V2 明确记录 `original_sample_has_data_kind=false`。

## 8. V2 产物与复现

### 8.1 文件

```text
v2/
├── DERIVED-FIELD-EVIDENCE-V2.jsonl
├── DERIVED-FIELD-EVIDENCE-V2-STATS.json
├── HISTORICAL-EXPERIMENT-DATA-REMEDIATION.md
├── ADVISOR-DECISION-BRIEF.md
├── build_evidence_ledger_v2.py
├── V2-MANIFEST.sha256
└── tests/
    ├── test_b0_mapping.py
    ├── test_memory_provenance.py
    ├── test_short_term_predicates.py
    ├── test_historical_field_states.py
    └── test_full_snapshot_v2.py
```

### 8.2 JSONL 结构

每行是独立 JSON，包含：

- `schema`、`builder_version`、`audit`（快照/复核源码/证据等级定义）；
- `source`（结果文件、行号、原始行 SHA-256、原始七字段存在性、sample/group/repeat/experiment/prompt 信息）；
- `segment`（main / supplementary-subject / supplementary-s7empty / b0-legacy）；
- `audit_locator`、`derived_batch_locator`；
- `b0`（仅 B0：ordinal、map 行号、四元组）；
- `prompt`（文件、重算哈希、与记录是否一致、user 字符数）；
- `plan`（新数据：身份、plan_seq、round_index、plan_sha256、config_sha256；B0 为 null）；
- `fields`（七个字段，每个都有 state/value/evidence；unrecoverable 字段另有 reason 与 traceability）。

原始记录本身没有被修改；JSONL 是外置证据层。

### 8.3 构建命令

```powershell
$env:PYTHONIOENCODING = "utf-8"
& F:\somethingProject\dsbot\.venv\Scripts\python.exe `
  F:\somethingProject\graduation-audit-review-repo\v2\build_evidence_ledger_v2.py `
  --audit-root F:\somethingProject\graduation-preflight-audit `
  --source-root F:\somethingProject\dsbot-preflight `
  --out-dir F:\somethingProject\graduation-audit-review-repo\v2
```

构建器默认校验两个仓库的 HEAD 与 clean 状态；只有所有 integrity 检查通过才写文件，否则退出码 2。

### 8.4 测试命令

```powershell
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONPATH = "F:\somethingProject\graduation-audit-review-repo"
& F:\somethingProject\dsbot\.venv\Scripts\python.exe `
  -m unittest discover -s v2/tests -v
```

测试使用标准库 `unittest`，共 42 项；不依赖网络、不访问真实数据库、不重跑实验。

## 9. 验收结果

| 检查 | 结果 |
| --- | --- |
| V2 JSONL 行数 | 165 |
| 严格 JSON 解析 | 165/165 |
| 唯一 audit_locator | 165/165 |
| 主实验 / subject / S7-empty / B0 | 140 / 10 / 5 / 10 |
| prompt_sha256 重算匹配 | 165/165 |
| prompt_chars 匹配 | 165/165 |
| 新数据 plan 身份 | 155/155 |
| 新数据 plan_sha256 与记录一致 | 155/155 |
| 新数据 config_sha256 与快照 config 一致 | 155/155 |
| memory 条目 | 170 |
| memory Gold 唯一映射 | 170/170 |
| memory type / strength | 170/170 / 170/170 |
| memory subject_key 解析 | 170/170 |
| 短期 slot/block/payload | 80 / 80 / 75 |
| difficult true | 10 |
| knowledge 空 | 165/165 |
| B0 四元组映射 | 10/10，ordinal 10/10，errors=[] |
| 原始七字段存在记录数 | 0 |
| 构建器 integrity | 全部 true |
| 单元/全量测试 | 42/42 通过 |

## 10. 剩余风险与待导师确认

1. `runtime_base_sha` 不可恢复，因此 memory 的 `runtime_status=active` 只能是低置信度 inferred；无法完成 §5.6.6 的逐项状态核对。
2. 快照中没有 `injected.json`；如果导师要求按 §5.6.6 原文对照，必须补齐该参考文件，或明确接受“无法完成”的结论。
3. S4 的 10 条 `time_pattern` 记忆存在展示值与 Gold subject_key 不同（“中等” vs “medium”）；V2 保留并标记，不修改 Gold，也不把它伪装成完全一致。
4. 短期记忆的 §7.1 原 Boolean 语义未定；V2 提供三个谓词，但需要导师确认原字段应取哪一个，或接受三谓词并列。
5. `knowledge_result_ids=[]` 的派生只适用于空配置；未来非空检索批次不能复用该结论。
6. `data_kind` 是 provenance 派生，样本文件本身缺少 §3.4 字段；若导师要求原始样本自带标记，需要修复样本生产流程，而不是回填历史记录。
7. B0 的 `B0-REPEAT-MAP.md:30` 写“三份 experiment_id 互不相同”，该说法只在 run-dir 之间成立；`b0-remainder` 内 S5/S7 共用 experiment_id。V2 已按四元组修正工具逻辑，但不修改快照文档；建议在下一版文档中明确这一点。
8. 若选择重跑，最多只能修复 155/165（B0 10 条按冻结设计不重跑），且无法恢复历史运行时 base_sha；重跑是新数据，不是修复旧记录。
9. V2 是仓库外证据层，不是原始记录的一部分；不能让 PR #26 的预检由 FAIL 变 PASS，也不应把 V2 的值回填到 `results.jsonl`。

## 11. 授权边界确认

本轮实际执行范围：

- 修改/新增：仅审计交付仓库 `graduation-audit-review` 的 `v2/` 目录（构建器、测试、V2 产物、报告、清单）；
- 未修改：快照仓库任何文件、165 条原始 `results.jsonl`、第一版 JSONL/Stats/Manifest/审计报告/第二轮补充说明、冻结设计 v4.5、`result_schema.py`、`AI-Study-Assistant` 源码、PR #26；
- 未访问：`feedback.db`、其他真实数据库、`blind_private/`；
- 未执行：真实 `--repack`、重新生成历史实验、回填原始记录；
- 未合并 PR。

第一版 8 个文件的 SHA-256 在 V2 构建前后保持不变；V2 清单只覆盖新增文件，不覆盖 `AUDIT-MANIFEST.sha256`。

## 12. 结论

现有 165 条历史记录可以在**不改原始数据**的前提下，通过 V2 外置证据层获得：

- 稳定的单条定位（audit_locator）与批次定位（derived_batch_locator）；
- 可核验的 Prompt/plan/config 绑定；
- 170 条记忆的字段级证据分级；
- 短期记忆的三种独立语义；
- B0 10 条的严格四元组映射；
- 对不可恢复字段的诚实表达。

但这不等于原始记录满足 §7.1：`run_id`、`base_sha` 仍不可恢复，memory 运行时 status 仍为 inferred，§5.6.6 仍未完成。是否接受“外置证据层 + 契约修订”、是否重跑、§7.1 Boolean 取哪种语义，应由导师决定；本报告不代替该决定，也不批准方案 B。
