# 外部派生字段证据台账（DERIVED-FIELD-EVIDENCE-LEDGER）

- 审计类型：只读数据审计（不改生产器、不改历史数据、不让预检变绿）
- 审计日期：2026-11-24
- 审计快照：`BlueOcean3214/graduation-preflight-audit` @ `7b99ad96db78167c490874af9c4b48484b6d6ef0`
- 源码基线：`BlueOcean3214/AI-Study-Assistant` @ `df155a5c145297bc5e6a085636fadfd6185586bd`（本地 worktree `F:\somethingProject\dsbot-preflight`，clean）
- 逐条台账：`DERIVED-FIELD-EVIDENCE.jsonl`（165 行）
- 复现脚本：`build_evidence_ledger.py`

> 本台账是**仓库外的审计证据**，不是原始实验记录，也不回填进任何 `results.jsonl`。
> 台账中 `state=derived` 的值一律不得被下游当作 `direct`（原始记录字段）使用。

---

## 0. 结论摘要

1. **165/165 条记录逐条核验完成**，无抽样、无跳过；每条都保留原始文件与行号。
2. 七个字段中：**0 个 direct**、**5 个可外置派生**（knowledge_result_ids、memory_injected、short_term_injected、difficult_flag、data_kind，均 165/165）、**2 个不可恢复**（run_id、base_sha，均 165/165 保持缺失）。
3. 五字段的派生不是"看模型回答猜"，而是由**样本夹具、prompt 实际文本、prompt 哈希、计划/配置哈希链、源码判定路径**共同支撑；其中 memory 的 170 个注入条目全部与 gold 唯一映射，0 歧义。
4. **现行契约（result_schema.py）仍把七个字段全部标为 UNRECOVERABLE**，并明确反对用常量/文本反推冒充记录字段。本台账的派生结论与现行契约**不冲突于事实，冲突于分类**：它证明的是"可在仓库外重建可审计的追溯证据"，不是"原始记录已经满足 §7.1"。
5. 因此，现有 165 条**可以**在不改历史数据的前提下，支撑一份**§7.1 契约修订建议**；但该修订必须引入"生成时记录 / 外部派生 / 不可恢复"三层状态，并明确 run_id、base_sha 在本批数据上仍不可恢复。**不能**据此声称现行 §7.1 已被满足，也**不能**让预检对这些文件转绿。
6. B0 的 10 条只有"记录 + prompt"两级证据，缺 config→plan→record 哈希链；其可派生性弱于 155 条新数据，报告中必须单列。

---

## 1. 目标、授权与边界

### 1.1 目标

对审计快照中的 165 条生成记录，逐条回答：§7.1 要求的七个字段，哪些能从现有证据可靠重建、哪些不能；重建结果的证据是什么、强度如何、还缺什么。产出可复核的外置台账，供导师审阅契约修订建议。

### 1.2 授权与禁止（本次实际遵守）

| 项 | 状态 |
| --- | --- |
| 修改两个仓库的源码/快照/PR/冻结设计/契约报告/执行报告/results.jsonl | 未做 |
| 回填七字段到历史记录 | 未做 |
| 重跑实验 / 真实 `--repack` | 未做 |
| 访问真实 `experiments/graduation/runs/`、`feedback.db`、`blind_private/` | 未做（只读审计快照中的副本） |
| 修改 `dsbot-preflight` 工作区 | 未做（审计前后 `git status` 均为空） |
| 新增审计代码位置 | 仅 `F:\somethingProject\graduation-audit-output\` |

### 1.3 术语

- **direct**：原始记录里已经存在、可直接读取的字段。
- **derived**：原始记录没有，但可由同一批工件（配置、计划、prompt、样本夹具、哈希）按确定规则重建，且规则可复现、证据可定位。
- **unrecoverable**：原始记录没有，且现有工件不足以唯一重建；不得用"看起来合理"的值填充。
- **unknown**：有候选值但存在无法消除的歧义；本台账中将歧义项降级为 unknown，而不是二选一。

---

## 2. 基线与审计对象

### 2.1 对象规模

| 分段 | run-dir | 记录数 | 计划文件 | 说明 |
| --- | --- | ---: | --- | --- |
| 主实验 | `main-20261113T061051Z` | 140 | `plan.json`（140 任务） | A/B/C/D × S1–S7 × 5 次 |
| 补充（主题） | `suppl-subj-20261113T062711Z` | 10 | `plan.json`（10 任务） | S5 的 C-subj / D-subj × 5 次 |
| 补充（S7-empty） | `suppl-s7empty-20261113T062822Z` | 5 | `plan.json`（5 任务） | 仅 D × 5 次 |
| B0 legacy | 3 个目录（见下） | 10 | 无 | S5、S7 各 5 次，legacy 复跑 |
| **合计** | 6 个目录 | **165** | 3 份 | |

B0 的 3 个目录：`20261112T210000-20261113T011751Z`（S5 第 1 次）、`20261112T210000-20261113T012031Z`（S7 第 1 次）、`b0-remainder-20261113T013105Z`（S5/S7 第 2–5 次）。B0 的"第 n 次"以 `B0-REPEAT-MAP.md` 为准；原始 `repeat_index` 跨目录会碰撞，不能直接当身份。

### 2.2 工件清单

- 记录文件：6 份 `results.jsonl`，共 165 行。
- prompt 文件：35 个，唯一 `prompt_sha256` 33 个。B0 在 3 个目录中共保存 4 份文件，但只对应 2 个唯一 prompt（S5、S7 各被重复保存一次）。
- 计划文件：3 份 `plan.json`（140 / 10 / 5 任务），均带 `plan_sha256`。
- 配置：`config/config.json`，canonical JSON 的 SHA-256 = `b33bd1ac4ca16ffd7a2ad9c8d256b4842454f3c6d5a5268a04df50255d05c256`。
- 样本：`samples/S1.json` … `S7.json`、`S7-empty.json`，共 8 份。
- 映射：`B0-REPEAT-MAP.md`。
- 文档：`docs/GRADUATION-EXPERIMENT-DESIGN.md`（v4.5）、`docs/GRADUATION-EXPERIMENT-CONTRACT-REPORT.md`（第十一轮）、`docs/GRADUATION-EXPERIMENT-EXECUTION-REPORT.md`。

### 2.3 快照规范化说明

快照为便于审阅，已把文本文件行尾统一为 LF（见快照 README 与 `.gitattributes`）。因此：

- **不能**对 `.txt` 文件字节直接求哈希当作 `prompt_sha256`；必须按记录中的 system/user 内容重算（见 §3.2）。
- `MANIFEST.sha256` 只证明快照文件在规范化后未被改动，不证明原始运行环境。

---

## 3. 方法与证据分级

### 3.1 严格解析

165 行全部按 JSON 严格解析，不修复、不跳过；每行保留 `result_file` 与 `line_number`。所有哈希重算均使用 UTF-8 文本与标准 JSON 序列化，不依赖本地默认编码。

### 3.2 prompt 哈希重算（关键）

按生产器口径（`build_prompts.py:485-493`）：

```python
sha256(json.dumps(
    [{"role": "system", "content": system},
     {"role": "user",   "content": user}],
    ensure_ascii=False, sort_keys=True
))
```

快照 `.txt` 信封为：

```text
===== SYSTEM =====
<system>

===== USER =====
<user>
```

按信封切分后重算：**165/165 与记录一致**；重算的 user 字符数与记录 `prompt_chars` **165/165 一致**。这说明记录与实际 prompt 内容绑定成立。

注意：直接对 `.txt` 字节求 SHA-256 会得到 0/165 匹配，原因是行尾已规范化；这不是数据异常。

### 3.3 配置 / 计划哈希

- `config_sha256`（`plan_schedule.py:64-83`）：`sha256(canonical_json(config))`，canonical 规则为 `json.dumps(ensure_ascii=False, sort_keys=True, separators=(",", ":"))`。
- `plan_sha256`（`plan_schedule.py:236-238`）：`sha256(canonical_json(plan 去掉 plan_sha256 字段))`。
- 三份 `plan.json` 的 `config_sha256` 都等于快照配置的 canonical 哈希；三份 `plan_sha256` 都自洽；155 条新记录的 `plan_sha256` 与同目录计划一致，身份四元组都出现在计划任务中，且 **155/155 的 `plan_seq` 与 `round_index` 逐条等于计划任务的值**。

### 3.4 证据分级（本台账内部）

| 级别 | 含义 | 本次适用 |
| --- | --- | --- |
| A | 记录 + 哈希链（config→plan→record）+ prompt 三重一致 | 155 条新数据的 knowledge/short/difficult、部分 memory |
| B | 记录 + prompt + 样本夹具（gold）一致，但无完整哈希链 | B0 的 knowledge；memory 的 status 语义 |
| C | 仅 prompt 文本 + 组定义推断 | B0 的 short/difficult |
| D | 无可靠证据 | run_id、base_sha |

### 3.5 禁止的推断方式

- 不由模型回答（`final_output`）反推注入了什么；模型可能复述、改写或遗漏。
- 不用统计规律（例如"大多数 D 组都有记忆"）替代单条证据。
- 不把"代码大概只会跑模拟数据"当作 `data_kind` 的直接证据；必须有样本级 `simulation` 标记与关联。
- 不修改字段定义来迁就现有数据。

---

## 4. 总体完整性核验结果

复现脚本对全部 165 条执行以下断言，结果全部为 true：

| 断言 | 结果 | 说明 |
| --- | --- | --- |
| `record_count_165` | ✅ | 6 份 JSONL 共 165 条 |
| `unique_identity_165` | ✅ | 身份四元组无重复 |
| `prompt_hash_all` | ✅ | 165/165 重算匹配 |
| `prompt_chars_all` | ✅ | 165/165 字符数匹配 |
| `plan_identity_all_new` | ✅ | 155/155 新记录身份在计划中 |
| `plan_sha_record_all_new` | ✅ | 155/155 记录 plan_sha256 与计划一致 |
| `plan_config_all` | ✅ | 155/155 计划 config_sha256 与快照配置一致 |
| `plan_task_fields_all` | ✅ | 155/155 记录的 plan_seq 与 round_index 等于计划任务值 |
| `knowledge_none_all` | ✅ | 165/165 prompt 明示无知识检索结果 |
| `b0_map_all` | ✅ | 10/10 按 B0-REPEAT-MAP 映射成功 |
| `sample_link_all` | ✅ | 165/165 prompt 含对应样本的 `current_user_request` |
| `data_kind_sim_all` | ✅ | 8/8 样本 `simulation.is_simulated=true` 且 gold `simulation=true` |
| `memory_entries_total` | 170 | 80 条记录含 memory 区块 |
| `memory_map_unique` | ✅ | 170/170 唯一定位到 gold 条目 |
| `memory_nonactive` | [] | 无 weakened/resolved/archived 注入 |
| `memory_count_mismatch` | [] | 每条记录条目数与样本 gold 的 `injected=true` 数一致 |
| `memory_type_mismatch` | [] | prompt 的 type 与 gold `memory_type` 全一致 |
| `memory_strength_mismatch` | [] | prompt 的 strength 与 gold `strength` 全一致 |
| `records_with_seven_fields` | 0 | 原始记录不含七字段中任何一个 |

补充事实：

- 165 条记录里 **没有任何一条**包含 `run_id`、`base_sha`、`knowledge_result_ids`、`memory_injected`、`short_term_injected`、`difficult_flag`、`data_kind`。
- 新数据（155 条）记录里也**没有** `config_sha256` 字段；config 绑定只能走 `record.plan_sha256 → plan.config_sha256 → config`。
- B0（10 条）没有 `plan.json`、`plan_sha256`、`seed`、`scheme`、`algorithm_version`，所以不参与上述计划类断言。
- 计划类断言覆盖 155 条新数据；B0 的缺失是 legacy 设计差异，不是数据错误。

---

## 5. 逐字段结论

### 5.1 `run_id` — unrecoverable（165/165）

- 生产器从未写入该字段；记录字段集见 `run_experiment.py:664-677`，无 `run_id`。
- §7.1 的示例形态（`20261120T140012Z-S1-D-r3`）含生成时刻与轮次，但原始记录没有保存"生成时刻的 run 标识"这一语义；用 `generated_at + sample + group + round` 现编一个字符串，只能叫**审计定位符**，不是原始 `run_id`。
- 本台账提供 `audit_locator = runs/<dir>/results.jsonl:<line>`，并在字段结构中明确 `audit_locator_is_not_run_id=true`。
- 结论：**不得**声称 `run_id` 已恢复；如需稳定引用，使用 `audit_locator` 或身份四元组。

### 5.2 `base_sha` — unrecoverable（165/165）

- 运行器未在开始时记录 git HEAD，也未记录工作树是否干净。
- 执行报告中的基线提交（`e5f97e9…`）是**报告声明**，不是运行时的机器证据；事后取 HEAD 得到的是"现在的"提交。
- 可补充的旁证（不等价于 `base_sha`）：以 `e5f97e9..df155a5` 做 diff，生成链中除 `plan_schedule.py` 外均无差异；`plan_schedule.py` 的改动集中在类型校验与身份展开辅助函数（`plan_identity_entries` / `plan_type_problems` 等），未改调度输出算法。该旁证降低"生成逻辑漂移"的风险，但**不能**证明运行当时的工作树就是 `e5f97e9` 且干净。
- 结论：保持缺失；契约修订中应明确本批数据 `base_sha` 不可恢复。

### 5.3 `knowledge_result_ids` — derived（165/165，值 `[]`）

证据链：

1. 配置 `knowledge_results=[]`、`knowledge_search_failed=false`（快照 `config/config.json`）。
2. 三份计划 `config_sha256` 均等于快照配置的 canonical 哈希（`plan_schedule.py:64-83`）。
3. 155 条新记录的 `plan_sha256` 与计划一致（`plan_schedule.py:236-238`）。
4. 165/165 的 prompt 都包含"本次没有知识库检索结果"的明示文本。
5. 配置由 `build_prompts.py:285-368` 读取；知识区块的渲染口径见 `agent_plan_draft.py:385-441`（`knowledge_results=[]` 时写入“本次没有知识库检索结果”）。

限制：

- 该派生只对"配置为空"成立；如果当时配置非空，条目 id 并未被记录，无法恢复。
- B0 没有 config→plan 绑定，只有 prompt 文本证据（级别 B/C），弱于新数据。

### 5.4 `memory_injected` — derived（165/165，170 个条目）

派生步骤：

1. 80 条记录的 prompt 含 memory 区块头"【真实长期学习记忆检索结果】"；区块体是 `json.dumps(payload)`，payload 字段由 `MEMORY_RESULT_FIELDS` 限定（`agent_plan_draft.py:111-120`、`:354-382`）。
2. 逐条解析区块 JSON，得到 `type/subject/content/strength`（prompt 中的 `subject` 渲染的是 `subject_label`）。
3. 用 `content` 在对应样本的 `gold_standard.memories` 中做**精确唯一匹配**；170/170 命中，且命中项 `injected=true`、`status="active"`。
4. 用 gold 的 `memory_type`、`strength` 与 prompt 值交叉核验：0 不一致。
5. 按 §7.1 输出 `[{memory_type, subject_key, strength, status}]`；`subject_key` 取 gold 的归一化键（prompt 只显示 label）。

每条记录条目数与该样本 `injected=true` 的 gold 条数完全一致：

| 样本 | C | D | C-subj | D-subj |
| --- | ---: | ---: | ---: | ---: |
| S1 | 3 | 3 | — | — |
| S2 | 2 | 2 | — | — |
| S3 | 1 | 1 | — | — |
| S4 | 2 | 2 | — | — |
| S5 | 5 | 5 | 2 | 2 |
| S6 | 1 | 1 | — | — |
| S7 | 1 | 1 | — | — |
| S7-empty | — | 0 | — | — |

条目类型分布：`task_topic` 80、`task_performance` 50、`difficulty` 30、`time_pattern` 10，合计 170。

关键限制（必须写入任何引用）：

- **prompt 里没有 `status`、没有 `memory_id`。** `status="active"` 是由"唯一已知消费者 `get_learning_memory` 只传 `status='active'`"（`agent_tools.py:222-269`，第 267 行）与 gold `injected=true` 共同**推定**的，不是从记录读出的。
- 因此本台账能发现"注入了 weakened/resolved"这类**内容级**异常（因为 gold 映射会失败或计数不符），但**不能**像 §5.6.6 要求的那样，用 `injected.json` 逐项对照 `status`；快照中没有 `injected.json`。
- 运行时源码版本未被 `base_sha` 绑定；"只注入 active"这一语义依赖代码路径假设。

### 5.5 `short_term_injected` — derived（165/165）

- 采用**实际内容注入**语义：prompt 中出现短期区块头"【学习者近期情况（程序统计，非模型总结）】"即为 `true`；同时保留 `slot_enabled`（组槽位是否开启）供对照。
- 结果：`true` 80 条（主实验 B 35 + D 35 = 70；补充 S7-empty 5；补充 D-subj 5），`false` 85 条（A 35 + B0 10 + C 35 + C-subj 5）。
- S7-empty 的 D 组：区块存在，但"已读取反馈数"为 0；按内容注入语义为 `true`。若把语义改为"存在非空短期条目"，这 5 条会变为 `false`（全批变为 75 true / 90 false）。本台账选择前者并在每行 `note` 中注明。
- 依据：`build_prompts.py:44-67`（槽位）、`:376-408`（组输入）、`agent_plan_draft.py:385-441`（仅非空才插入）。

限制：§7.1 只给了 boolean 示例，未定义"开关"还是"内容"；本台账明确选定语义，避免混用。

### 5.6 `difficult_flag` — derived（165/165，10 条 true）

判定规则（源码口径）：

1. `agent_tools.py:414-435`：取该样本最新一条反馈；`difficult = status=="partial" and reason=="任务难度太高"`。
2. 再叠加组槽位：只有 feedback 槽开启的组才可能为 true（`build_prompts.py:44-67`、`:376-408`）。
3. B0 组固定 `difficult=False`（设计矩阵），即使原始反馈满足条件也不置 true。
4. 用 prompt 中是否出现动态规则原文"最近一次反馈是 partial 且原因是任务难度太高"做交叉核验（`ai_service.py:159-182`）。

结果：

- `true` 10 条：S7 的 B 组 5 条 + D 组 5 条（该样本最新反馈为 partial / 任务难度太高）。
- `false` 155 条：包括 S1（最新反馈 not_completed，不满足 partial）、S2（partial 但原因是任务时间太长）、S3–S6（completed）、S7-empty（无反馈）、A/C/C-subj（槽位关闭）、B0（组固定 false）。
- B0 的 S7 有 5 条**原始反馈**满足条件，但台账值为 false，证据中同时记录 `raw_condition_partial_and_reason=true` 与 `b0_fixed_false=true`，避免被误读为"漏判"。
- `dynamic_rule_present_in_prompt` 与 `difficult_flag` 在 165 条上完全一致（10/10 出现，155/155 不出现）。

限制：现行契约认为"文本渲染无法区分真的难与恰好写到类似句子"；本台账的强度来自"样本夹具的最新反馈 + 组槽位"这一数据侧证据，而不是只靠 prompt 文本。但运行时是否确实读取了该夹具，仍依赖代码路径与样本绑定。

### 5.7 `data_kind` — derived（165/165，值 `simulated_learner_fixture`）

证据链：

1. 8 份样本文件均带 `simulation.is_simulated=true`，`gold_standard.simulation=true`。
2. `seed_fixture.py:92-93` 对样本做强制校验（模拟标记不成立则拒绝生成夹具）。
3. 每条 prompt 都含对应样本的 `current_user_request` 原文，165/165 建立 sample_id ↔ 记录关联。
4. 设计 §3.4 明确本实验全部为模拟学习者夹具。

限制与冲突：

- 8 份样本文件**都没有** §3.4 要求的 `data_kind` 字段（grep 无命中）；§3.4 要求"所有样本文件、夹具库、结果文件必须带"该标记，本批数据未落实。
- 现行 `result_schema.py:275-280` 把 `data_kind` 标为 UNRECOVERABLE，并明确写道：写入常量 `simulated_learner_fixture` 等于用"代码大概只会跑模拟数据"代替数据证据，属于编造。
- 因此本台账把它标为 **derived（provenance）**，并逐条记录样本级 simulation 证据；它**不是**记录字段，也**不能**在未修订契约的情况下被当作 §7.1 的 direct 值。

---

## 6. 覆盖率与分段统计

### 6.1 字段状态 × 分段

| 字段 | 主实验 140 | 补充-subj 10 | 补充-s7empty 5 | B0 10 | 合计 derived |
| --- | --- | --- | --- | --- | ---: |
| run_id | unrecoverable | unrecoverable | unrecoverable | unrecoverable | 0 |
| base_sha | unrecoverable | unrecoverable | unrecoverable | unrecoverable | 0 |
| knowledge_result_ids | derived | derived | derived | derived（弱） | 165 |
| memory_injected | derived | derived | derived（0 条） | derived（0 条） | 165 |
| short_term_injected | derived | derived | derived | derived | 165 |
| difficult_flag | derived | derived | derived | derived | 165 |
| data_kind | derived | derived | derived | derived | 165 |

### 6.2 记忆条目 × 分段

| 分段 | 含 memory 区块的记录 | 条目数 |
| --- | ---: | ---: |
| 主实验 | 70（C 35 + D 35） | 150 |
| 补充-subj | 10（C-subj 5 + D-subj 5） | 20 |
| 补充-s7empty | 0 | 0 |
| B0 | 0 | 0 |
| **合计** | **80** | **170** |

### 6.3 证据强度 × 分段

| 分段 | knowledge | memory | short | difficult | data_kind |
| --- | --- | --- | --- | --- | --- |
| 新数据 155 | A（config→plan→record + prompt） | A/B（哈希链 + prompt + gold；status 为 B） | A | A | B（样本级） |
| B0 10 | C（仅 prompt） | —（无注入） | C（组定义） | C（组定义 + 反馈） | B（样本级） |

---

## 7. 不能确定项及原因

| 项 | 状态 | 原因 | 影响 | 台账能否弥补 |
| --- | --- | --- | --- | --- |
| `run_id` | unrecoverable | 生成时未写；事后合成即伪造 | 无法用原始 run_id 追溯单次生成 | 否；只能用 audit_locator |
| `base_sha` | unrecoverable | 未记录运行时 HEAD/工作树状态 | 无法证明运行时源码版本 | 否；旁证只能降低风险 |
| memory `status` | unknown→推定 active | prompt 不携带 status；只注入 active 是代码路径语义 | 无法从记录直接检出"注入层退化" | 部分：内容级可查，状态级不能 |
| memory `memory_id` | 缺失（非 §7.1 必填） | `_sanitize_memory` 主动剥离 | 无法按 id 精确引用 | 不影响 §7.1 四元组 |
| §5.6.6 的 `injected.json` | 缺失 | 快照/仓库中均无此文件 | 无法做"逐项完全一致"的合同检查 | 否；只能以 gold + 计数替代 |
| `short_term_injected` 语义 | 二义 | §7.1 未定义"开关"还是"内容" | S7-empty 5 条可能翻转 | 通过显式语义 + slot_enabled 缓解 |
| B0 config→plan 绑定 | 缺失 | legacy 无 plan.json | B0 的 knowledge 证据弱 | 否；只能标注弱证据 |
| `data_kind` 文件标记 | 缺失 | 8 份样本均无该字段 | 与 §3.4 不符 | 可由样本 simulation 派生，但需契约承认 |
| 运行时源码版本 | 未绑定 | 同 base_sha | 派生规则依赖的代码路径未被机器绑定 | 否；lineage diff 仅旁证 |

---

## 8. 剩余风险

1. **循环论证风险**：memory 映射以 gold 为基准，而 gold 与 prompt 由同一团队构造。缓解：content 精确匹配、type/strength 独立交叉核验、计数与样本矩阵一致；但 gold 本身仍是人工产物。
2. **运行时漂移风险**：派生规则依赖 `get_learning_memory`、`_sanitize_memory`、`_memory_block` 等代码路径；由于 `base_sha` 不可恢复，无法机器证明运行时就是该版本。缓解：生成链 diff 旁证 + prompt 结构一致性。
3. **prompt 绑定边界**：`prompt_sha256` 与字符数只证明“记录 ↔ 快照 prompt 文件”绑定，不证明运行时实际发送给模型的消息与文件逐字节相同（没有请求级日志）。这是本台账所有文本类派生的共同上界。
4. **语义重定义风险**：把 derived 值写成 §7.1 字段，容易被下游误读为 direct。缓解：JSONL 每字段强制带 `state`、`evidence`、`caveat`；本文档与字段定义同时声明。
5. **B0 弱证据风险**：B0 无计划绑定，knowledge 只能靠 prompt 文本；如果未来把 B0 与新数据混算，会高估证据强度。缓解：分段统计、单独标注。
6. **§5.6.6 无法执行风险**：缺少 `injected.json`，无法按现行合同做"完全一致"检查；只能做替代性核验。该替代必须写进修订建议，不能默默替换。
7. **误用为"预检通过"风险**：本台账不改变 `results.jsonl`，预检仍会把这七字段报 FAIL；任何人不得据此宣称数据已合规。
8. **S7-empty 语义风险**：若导师认为"短期注入"应指有非空短期数据，则 5 条取值需翻转；台账已记录两种口径的差异。

---

## 9. 对 §7.1 的影响

| §7.1 要求 | 原始记录 | 外置派生 | 结论 |
| --- | --- | --- | --- |
| `run_id` | 无 | 不可恢复 | 缺 |
| `base_sha` | 无 | 不可恢复 | 缺 |
| `knowledge_result_ids` | 无 | `[]`（165/165） | 可补，但仅空配置情形 |
| `memory_injected` | 无 | 四元组 170 条（165/165） | 可补；status 为推定 |
| `short_term_injected` | 无 | boolean（165/165） | 可补；语义需定义 |
| `difficult_flag` | 无 | boolean（165/165） | 可补；依赖夹具与组定义 |
| `data_kind` | 无 | `simulated_learner_fixture`（165/165） | 可补；需契约承认 provenance 派生 |

对分析的影响：

- 统计量（`experiment_id`、`sample_id`、`group`、`condition`、`repeat_index`、`round_index`、`prompt_sha256`、`request_count`、`elapsed_seconds`、`token_usage`）不依赖七字段；本台账不改变任何统计结论。
- H4 的"实际注入集合"解释、§5.6 的公平性核对、§5.6.6 的注入退化检查会受影响：前两者可用台账增强，后者无法按原文执行。

---

## 10. 能否支持契约修订建议

### 10.1 技术结论

**可以支持一份"追溯性契约修订建议"，但不能支持"现行 §7.1 已满足"的结论。**

理由：

- 5 个字段在 165/165 上有可复现、可定位的外部证据；其中 155 条新数据具备 config→plan→record 哈希链，证据强度足以进入论文附录。
- 2 个字段（run_id、base_sha）在本批数据上确实不可恢复；任何"补齐"都会变成伪造。
- 现行 `result_schema.py` 把七字段全部定为 UNRECOVERABLE，且明确反对文本反推与常量填充；修订必须**显式改变分类**，而不是悄悄把派生值塞进 direct。

### 10.2 建议的修订形态（仅技术建议，批准权在负责人）

1. **三层状态**：`recorded_at_generation`（direct）/ `externally_derived`（附规则、证据、commit）/ `unrecoverable`。禁止第四种"看起来像 direct 的补值"。
2. **逐字段定级**：run_id、base_sha 保持 unrecoverable；knowledge_result_ids、memory_injected、short_term_injected、difficult_flag 定为 externally_derived；data_kind 定为 externally_derived（provenance），并要求未来样本文件补 §3.4 标记。
3. **证据绑定**：派生规则必须绑定源码 commit（本批为 `df155a5` 的只读审计，生成逻辑旁证 `e5f97e9`）、审计快照 commit、`MANIFEST.sha256`；台账每行保留 audit_locator。
4. **前向补齐**：下一批实验在生成时写入 run_id、base_sha（开始时的 HEAD + 工作树 clean 检查）、结构化 memory_injected（含 status）、short_term_injected、difficult_flag、data_kind；并生成 `injected.json` 供 §5.6.6 使用。
5. **不可恢复项的处理**：本批 165 条在论文与答辩中如实说明"两项不可恢复、五项外部派生"，不得写成"§7.1 全字段已记录"。
6. **预检口径**：预检继续对缺失七字段报 FAIL；若要接受外置台账，应是**新的、显式的**审计模式，而不是把现有 FAIL 改成 PASS。

### 10.3 与"重跑 155 条"的比较

- 重跑能修复"未来记录"，但**不能**修复 B0 的 10 条（设计冻结、不重跑），也**不能**为已发生的运行补出当时的 `base_sha`。
- 因此即使重跑，最多 155/165 满足新契约；本批 165 条的追溯仍需要外置台账或如实声明缺失。
- 重跑成本参考：约 166 次请求、364k tokens（设计估约 2 小时机器时间），且会引入新的模型随机性；是否重跑属于负责人决策，不在本审计授权内。

---

## 11. 复现方式与工件

### 11.1 命令

```powershell
$env:PYTHONIOENCODING="utf-8"
& "F:\somethingProject\dsbot\.venv\Scripts\python.exe" `
  "F:\somethingProject\graduation-audit-output\build_evidence_ledger.py"
```

脚本只读：

- `F:\somethingProject\graduation-preflight-audit`（快照）
- `F:\somethingProject\dsbot-preflight`（源码，用于读取样本与常量）

### 11.2 产物

| 文件 | 说明 |
| --- | --- |
| `DERIVED-FIELD-EVIDENCE.jsonl` | 165 行，一行对应一条原始记录；含 source/segment/audit_locator/b0/prompt/plan/fields |
| `DERIVED-FIELD-EVIDENCE-LEDGER.md` | 本文件 |
| `_stats.json` | 全部完整性断言与分段计数（脚本生成） |
| `AUDIT-MANIFEST.sha256` | 对上述台账文件生成的 SHA-256 清单 |

### 11.3 JSONL 行结构（摘要）

```json
{
  "source": {"repository": "...", "commit": "7b99ad9...", "result_file": "runs/.../results.jsonl",
             "line_number": 1, "sample_id": "S1", "group": "C", "repeat_index": 0,
             "experiment_id": "...", "prompt_ref": "prompts/S1/C.txt", "prompt_sha256": "..."},
  "segment": "main",
  "audit_locator": "runs/main-.../results.jsonl:1",
  "b0": null,
  "prompt": {"file": "...", "sha256_recomputed": "...", "sha256_matches_record": true,
             "user_chars_recomputed": 1234, "prompt_chars_matches_record": true},
  "plan": {"file": "...", "identity_in_plan": true,
           "plan_seq_matches_record": true, "round_index_matches_record": true,
           "plan_sha256_matches_record": true,
           "config_sha256_matches_snapshot_config": true, "plan_sha256": "..."},
  "fields": {
    "run_id": {"state": "unrecoverable", "value": null, "reason": "...", "evidence": {...}, "code_refs": [...]},
    "base_sha": {"state": "unrecoverable", "value": null, "reason": "...", "evidence": {...}, "code_refs": [...]},
    "knowledge_result_ids": {"state": "derived", "value": [], "evidence": {...}, "code_refs": [...]},
    "memory_injected": {"state": "derived", "value": [{"memory_type": "...", "subject_key": "...",
                          "strength": 0.9, "status": "active"}], "evidence": {...}, "caveat": "..."},
    "short_term_injected": {"state": "derived", "value": true, "evidence": {...}},
    "difficult_flag": {"state": "derived", "value": false, "evidence": {...}},
    "data_kind": {"state": "derived", "value": "simulated_learner_fixture", "evidence": {...}}
  }
}
```

---

## 附录 A：源码锚点

| 主题 | 位置 |
| --- | --- |
| 生产器记录字段 | `experiments/graduation/run_experiment.py:664-677` |
| 七字段契约（全部 UNRECOVERABLE） | `experiments/graduation/result_schema.py:128,193,211,216,222,226,275` |
| 记忆清洗（剥离 status/memory_id） | `experiments/graduation/agent_tools.py:203-219` |
| `get_learning_memory`（status="active"） | `experiments/graduation/agent_tools.py:222-269`（第 267 行） |
| `retrieve` 状态校验与 subject 归一化 | `experiments/graduation/memory_service.py:2117-2190` |
| difficult 判定 | `experiments/graduation/agent_tools.py:414-435` |
| difficult 动态规则 | `experiments/graduation/ai_service.py:159-182` |
| memory payload 字段 | `experiments/graduation/agent_plan_draft.py:111-120` |
| memory 区块渲染 | `experiments/graduation/agent_plan_draft.py:354-382` |
| user content 组装 | `experiments/graduation/agent_plan_draft.py:385-441` |
| 组槽位矩阵 | `experiments/graduation/build_prompts.py:44-67` |
| 主体过滤 `{"S5":"概率论"}` | `experiments/graduation/build_prompts.py:84` |
| 输入收集 / 组输入 | `experiments/graduation/build_prompts.py:285-368`、`:376-408` |
| prompt 哈希口径 | `experiments/graduation/build_prompts.py:485-493` |
| config 哈希 | `experiments/graduation/plan_schedule.py:64-83` |
| plan 哈希 | `experiments/graduation/plan_schedule.py:236-238` |
| 夹具模拟标记强制校验 | `experiments/graduation/seed_fixture.py:92-93` |
| 设计 §7.1 模板 | `docs/GRADUATION-EXPERIMENT-DESIGN.md:1262-1300` |
| 设计 §5.6.6 | `docs/GRADUATION-EXPERIMENT-DESIGN.md:1207-1209` |
| 设计 §3.4 数据标记 | `docs/GRADUATION-EXPERIMENT-DESIGN.md:683-692` |

## 附录 B：关键计数

- 记录 165：main 140 / suppl-subj 10 / suppl-s7empty 5 / B0 10。
- prompt 文件 35，唯一哈希 33。
- 含 memory 区块记录 80，条目 170（task_topic 80 / task_performance 50 / difficulty 30 / time_pattern 10）。
- short_term true 80 / false 85。
- difficult true 10 / false 155。
- knowledge `[]` 165。
- data_kind 派生 165。
- 原始记录含七字段者：0。
- 含完整 config→plan→record 链的新记录：155。
- 无计划绑定的 B0：10。
