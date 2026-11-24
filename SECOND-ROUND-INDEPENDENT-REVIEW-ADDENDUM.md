# 第二轮独立复审补充说明

**文件性质**：对已发布审计台账的补充说明，不是新一轮全量审计，也不重新生成台账。

**基线**：审计交付仓库 `BlueOcean3214/graduation-audit-review`，固定 commit `92ba6f9952f55b7d0906fb0e0a79481670b8000d`。

**本轮边界**：只新增本文件；不修改原有 7 个文件，不修改 `results.jsonl`、数据快照、源码仓库、PR #26、冻结设计 v4.5 或 `result_schema.py`；不执行真实 `--repack`；不访问 `feedback.db`、其他真实数据库或 `blind_private`。

---

## 1. 补充说明的目的与审计基线

### 1.1 目的

第二轮独立复审在已发布台账中发现两个需要单独说明的问题：

1. `build_evidence_ledger.py` 的 B0 映射字典存在键冲突，导致 `b0_map_matched=10/10` 不能证明 10 条 B0 都命中了正确的样本与 run-dir。
2. `memory_injected.status` 的证据等级高于实际可支持的程度：170 条内容映射可靠，但 `status="active"` 是从 Gold 与当前源码路径推定的，不是从原始 Prompt 或结果记录中读出的。

同时保留 `short_term_injected` 的语义二义性，供导师决策。本文档只记录发现、限定与建议，不实施修正。

### 1.2 审计基线（严格固定）

| 项 | 固定值 |
| --- | --- |
| 审计交付仓库 | `BlueOcean3214/graduation-audit-review` |
| 交付基线 commit | `92ba6f9952f55b7d0906fb0e0a79481670b8000d` |
| 数据快照仓库 | `BlueOcean3214/graduation-preflight-audit` |
| 快照 commit | `7b99ad96db78167c490874af9c4b48484b6d6ef0` |
| 源码仓库 | `BlueOcean3214/AI-Study-Assistant` |
| 源码 commit | `df155a5c145297bc5e6a085636fadfd6185586bd` |

未使用任何“最新 HEAD”替代上述版本。本文档新增的 commit 只包含本文件，不改变 `92ba6f9` 中已发布的 7 个文件。

### 1.3 证据标签

本文档统一使用以下标签，避免把推定写成事实：

| 标签 | 含义 |
| --- | --- |
| **已验证事实** | 可由固定 commit 的代码、数据或哈希直接复核 |
| **代码校验缺陷** | 代码逻辑本身不能证明其声称的结论 |
| **推定** | 由代码路径、Gold 或设计矩阵推出，但没有运行时直接记录 |
| **修正建议** | 尚未实施的代码或流程改动 |
| **待导师确认** | 涉及冻结设计、契约口径或是否重跑，不能由审计自行决定 |

---

## 2. 第一轮独立复审已经通过的事项

以下结果已由 ChatGPT 直接读取公开仓库复核；本轮对照固定 commit 的文档与代码重新确认了相关位置，但**没有重新执行全量审计**，也没有重新生成台账。

| 检查项 | 结果 | 复核依据 |
| --- | ---: | --- |
| 文件 SHA-256 清单 | 4/4 匹配 | `AUDIT-MANIFEST.sha256` 覆盖的 4 个文件 |
| JSONL 严格解析 | 165/165 | 1,068,174 字节，无 BOM，无空行 |
| 唯一 `audit_locator` | 165/165 | 165 个 locator 全部唯一 |
| 七字段状态 | 5 derived + 2 unrecoverable | 字段级粗粒度统计 |
| 记忆注入条目 | 170 | 80 条记录含 memory 区块 |
| Gold 唯一映射 | 170/170 | 按 `content` 精确匹配 |
| 类型与强度匹配 | 170/170 | prompt 与 Gold 交叉核验 |
| Prompt 哈希 | 165/165 | 按 `build_prompts.py:485-493` 重算 |
| 计划绑定 | 新数据 155/155 | `plan_sha256`、身份、`plan_seq`、`round_index` |

**限定**：表中“5 derived”是字段级粗粒度说法。第 5 节会把 `memory_injected` 拆到子字段；拆开后，`memory_type`、`subject_key`、`strength` 仍可标为 externally derived，但 `status` 只能标为 inferred/unknown。第 9 节据此修正对 §7.1 的表述。

---

## 3. B0 映射键冲突问题

### 3.1 当前代码逻辑

`build_evidence_ledger.py:107-119` 的 `load_b0_map()` 从 `B0-REPEAT-MAP.md` 读表，并用如下键写入字典：

```python
mapping[(expid, int(repeat))] = {
    "sample_id": sample,
    "ordinal": int(nth),
    "run_dir": run_dir,
}
```

后续在 `build_evidence_ledger.py:249-256` 按记录查找：

```python
key = (rec.get("experiment_id"), rec.get("repeat_index"))
hit = b0_map.get(key)
...
stats["b0_map_matched"] += int(hit is not None)
```

键里没有 `sample_id`，也没有 `run_dir`；命中后只检查 `hit is not None`，没有检查 `hit["sample_id"]` 或 `hit["run_dir"]` 是否与当前记录一致。

### 3.2 冲突是如何发生的

`b0-remainder-20261113T013105Z` 同时包含 S5 与 S7 的 B0 记录。映射表中这 8 行的 `experiment_id` 完全相同：

`graduation-memory-ablation@20261112T210000@b0-remainder-20261113T013105Z`

且 S5、S7 都使用 `repeat_index = 0,1,2,3`，只是 `sample_id` 不同。于是同一组键：

| `experiment_id` | `repeat_index` | 先写入 | 后被覆盖为 |
| --- | ---: | --- | --- |
| remainder 的 experiment_id | 0 | S5 第 2 次 | S7 第 2 次 |
| remainder 的 experiment_id | 1 | S5 第 3 次 | S7 第 3 次 |
| remainder 的 experiment_id | 2 | S5 第 4 次 | S7 第 4 次 |
| remainder 的 experiment_id | 3 | S5 第 5 次 | S7 第 5 次 |

`load_b0_map()` 读表顺序是 S5 五行、S7 五行，因此后读的 S7 覆盖先读的 S5。10 行表最终只剩 **6 个唯一键**，而不是 10 个；`rows` 仍返回 10，`b0_map_rows` 也记录 10。

### 3.3 为什么仍会报告 10/10

10 条 B0 记录查找时：

- S5 冒烟记录（独立 experiment_id，r0）命中，`hit is not None`；
- S7 冒烟记录（独立 experiment_id，r0）命中；
- S5 remainder 的 r0–r3 命中，但命中的是**被 S7 覆盖后的条目**；
- S7 remainder 的 r0–r3 命中。

10 条全部满足 `hit is not None`，所以 `b0_map_matched=10`、`b0_map_all=true`。但其中 4 条 S5 remainder 记录的命中对象 `sample_id` 实际是 S7，与当前记录不一致，代码没有发现。

**这是代码校验缺陷，不是已经证实的历史 B0 数据错误。** 当前台账中的 B0 ordinal 是否仍然正确，见第 4 节。

### 3.4 文档表述的附带问题

`B0-REPEAT-MAP.md:30` 写“三份 `experiment_id` 互不相同”。这句话按 run-dir 批次理解成立：两个冒烟批次各有一个 experiment_id，remainder 批次有一个 experiment_id，三者互不相同。但在 remainder 批次内部，S5 与 S7 共享同一个 `experiment_id`；如果把这句读成“逐行 experiment_id 唯一”，就会掩盖本次键冲突。建议后续把口径写成“按批次唯一；批次内可被多个 sample 共用”，而不是只写“三份互不相同”。

---

## 4. B0 已有数据的独立复核结果

使用 `sample_id + experiment_id + repeat_index + run_dir` 四元组，逐条对照 `B0-REPEAT-MAP.md` 的 10 行与 JSONL 中 10 条 `segment="b0-legacy"` 记录：

| 分段 | 记录数 | 期望 ordinal | 台账 ordinal | 四元组命中 |
| --- | ---: | --- | --- | --- |
| S5 冒烟（`20261112T210000-20261113T011751Z`） | 1 | 1 | 1 | 唯一 |
| S5 remainder（r0–r3） | 4 | 2,3,4,5 | 2,3,4,5 | 唯一 |
| S7 冒烟（`20261112T210000-20261113T012031Z`） | 1 | 1 | 1 | 唯一 |
| S7 remainder（r0–r3） | 4 | 2,3,4,5 | 2,3,4,5 | 唯一 |

结果：

- **10/10** 条都能按四元组唯一命中映射表；
- **10/10** 条的 ordinal 与映射表一致；
- **暂未发现**历史台账中的 B0 序号被写错。

原因是 S5 与 S7 的 remainder ordinal 序列恰好平行（r0→2、r1→3、r2→4、r3→5）。键覆盖后，S5 记录拿到的 ordinal 仍然等于它本该得到的值，所以序号没有暴露错误；但 `sample_id` 与 `run_dir` 的一致性没有被检查。

**因此**：

- 现有 10 条 B0 的序号可以按独立复核接受；
- `_stats.json` 的 `b0_map_all=true` 不能单独作为“键唯一、样本一致、run-dir 一致”的证明；
- 在修正校验逻辑之前，不应把 `b0_map_matched=10/10` 当作自动化映射正确性的充分证据。

---

## 5. `memory_injected.status` 证据限制

### 5.1 已经可靠的部分

对 170 个 Prompt 记忆条目：

- 170/170 按 `content` 在对应样本 `gold_standard.memories` 中唯一匹配；
- 170/170 的 `memory_type` 与 Gold 一致；
- 170/170 的 `strength` 与 Gold 一致；
- 每条记录的记忆条数与实验组对应的 Gold 注入集合一致；
- 没有发现 `resolved` 或 `weakened` 记忆被写入 Prompt。

因此，**内容、类型、主题和强度**存在可靠的外部派生证据。

### 5.2 status 为什么不是“读出来的”

`agent_tools.py:203-219` 的 `_sanitize_memory()` 只返回：

`type / subject / content / strength / evidence_count / episode / evidence_feedback_ids / updated_at`

其中：

- 没有 `status`；
- 没有 `memory_id`；
- `subject` 优先取 `subject_label`（`agent_tools.py:212`），不是归一化后的 `subject_key`。

`get_learning_memory()` 在 `agent_tools.py:222-269` 调用：

```python
memory_service.retrieve(..., status="active", ...)
```

固定写死在 `agent_tools.py:267`。`memory_service.py:2117-2190` 的 `retrieve()` 会按 `status` 过滤，并在返回行里带 `status`（`:2184`）；但 `_sanitize_memory()` 在把结果交给 Prompt 之前已经把 `status` 剥离。

`agent_plan_draft.py:111-120` 的 `MEMORY_RESULT_FIELDS` 白名单也不含 `status`；`:354-382` 的 `_memory_block()` 只序列化白名单字段；`:385-441` 的 `_build_draft_user_content()` 仅在记忆非空时插入区块。因此 **Prompt 的 memory JSON 里没有 status 字段**。

台账中的 status 来自：

```python
status = gold.get("status")
if status != "active" or gold.get("injected") is not True:
    ...
mem_values.append({"memory_type": ..., "subject_key": ...,
                   "strength": ..., "status": status})
```

也就是说：`status` 是 **Gold 的值**，再叠加“生成链中唯一已知的 Prompt 记忆消费路径只请求 active”这一代码路径推定；它不是从原始 Prompt 或原始结果记录中读出的。台账的 `caveat` 已写明这一点，但字段级 `state` 仍写作 `derived`，容易被读成与 type/strength 同级。

### 5.3 缺失的两项证据

1. **运行时源码版本未绑定**：`base_sha` 在 165/165 上不可恢复，无法机器证明运行时使用的是哪一版源码，也不能证明就是当前审计所用 `df155a5` 的“只注入 active”代码路径。
2. **`injected.json` 不存在**：设计 §5.6.6 要求“每份 run 的 `memory_injected` 必须与该样本 `injected.json` 完全一致”；在快照仓库与源码工作树中均未找到该文件，无法按原文逐项对照。

即使 170 条内容全部匹配、且没有任何 weakened/resolved 被写入，也**不能**声称已经完成 §5.6.6 要求的注入状态核对。

### 5.4 建议的子字段证据分级

| 子字段 | 建议证据状态 | 说明 |
| --- | --- | --- |
| `memory_type` | externally_derived | Prompt 有 type，且与 Gold 170/170 一致 |
| `subject_key` | externally_derived | Prompt 只有 label；subject_key 由 content 唯一映射到 Gold 得到 |
| `strength` | externally_derived | Prompt 有 strength，且与 Gold 170/170 一致 |
| `status` | **inferred / unknown** | Prompt 无 status；active 是代码路径 + Gold 推定 |

如果契约只允许三态（`recorded_at_generation` / `externally_derived` / `unrecoverable`），则 `status` 应归入 `unknown`，或者新增 `inferred` 子类；**不能**继续把它写成 `externally_derived`。本轮不修改 JSONL，只提出这个更精确的分级建议。

---

## 6. `short_term_injected` 的语义边界

### 6.1 当前口径

当前台账（`build_evidence_ledger.py:335-349`）用：

```python
short_present = SHORT_HEADER in user
```

即：Prompt 中出现短期区块头 `【学习者近期情况（程序统计，非模型总结）】` 就记为 `true`。

结果：

- `true` 80 条：主实验 B 35 + D 35，补充 S7-empty 5，补充 D-subj 5；
- `false` 85 条：A 35 + B0 10 + C 35 + C-subj 5。

### 6.2 二义性

S7-empty 的 D 组：

- 短期区块存在；
- 但“已读取反馈数”为 0，区块内没有实际学习历史条目。

如果按“存在非空学习历史”定义 `short_term_injected`，这 5 条应翻为 `false`，全批变为 `true 75 / false 90`。如果按“区块是否出现”定义，则维持 `true 80 / false 85`。

### 6.3 必须区分的三个谓词

| 谓词 | 含义 | 当前状态 |
| --- | --- | --- |
| `short_term_slot_enabled` | 实验组矩阵是否开启短期槽位（B/D/D-subj） | 可由 `build_prompts.py:44-67`、`:376-408` 确定 |
| `short_term_block_present` | Prompt 是否出现短期区块头 | 当前台账使用的语义 |
| `short_term_payload_nonempty` | 区块内是否存在非空学习历史/计数 | S7-empty 的 D 组为 false |

设计 §7.1 只给了 boolean 示例，没有定义是“开关”“区块”还是“内容”。本轮**不修改**冻结设计中的 Boolean 定义；建议导师明确选择一种语义，或在未来 schema 中同时记录三个谓词。

---

## 7. 对现有派生字段台账的影响

### 7.1 不改变 165 行与总体计数

- `DERIVED-FIELD-EVIDENCE.jsonl` 仍为 165 行、1,068,174 字节；
- `audit_locator` 仍为 165 个唯一值；
- 七字段状态仍为 825 个 `derived` + 330 个 `unrecoverable`；
- 170 个记忆条目、170/170 唯一映射、10 条 B0、80/85 短期计数均不变。

本轮**没有**改写原台账，也没有重新生成 `_stats.json` 或 `AUDIT-MANIFEST.sha256`。

### 7.2 需要加限定语的地方

1. **B0 映射**：现有 10 条记录的 ordinal 经独立四元组复核正确；但 `b0_map_all=true` 只证明“10 条都能命中某个键”，不证明“键唯一、样本一致、run-dir 一致”。在修正校验逻辑前，该布尔值应带此限定。
2. **memory status**：`memory_injected` 的字段级 `state="derived"` 对内容/类型/强度成立；对 `status` 应拆为 `inferred/unknown`。这会影响“五个字段全部 externally_derived”的粗粒度表述，正确说法见第 9 节。
3. **short 语义**：当前 80/85 是“区块出现”口径；若改为“非空 payload”，则为 75/90。两种口径都未被冻结设计明确选择，不能把其中一个写成唯一事实。

### 7.3 对结论的影响

- 170/170 的 Gold 内容映射仍然成立；
- 没有发现 resolved/weakened 被注入；
- 但 `status` 的 active 仍是推定，不能升级为“已核对运行时状态”；
- B0 历史序号没有发现错误，但自动化校验的证明力被削弱；
- 原有审计结论“五项可外部派生、两项不可恢复”需要按第 9 节细化，不能继续用“五项全部 fully derived”一笔带过。

---

## 8. 修正建议和后续验证要求

> 本节全部是建议，本轮不修改、不运行原脚本，也不提交代码修正。

### 8.1 B0 映射键与强制校验

建议把 `load_b0_map()` 的键改为四元组：

```python
key = (sample_id, experiment_id, repeat_index, run_dir)
```

并增加以下强制检查：

1. 每条 B0 结果必须**唯一命中**；
2. `sample_id` 必须与映射行一致；
3. `experiment_id` 必须一致；
4. `repeat_index` 必须一致；
5. `run_dir` 必须一致；
6. `ordinal` 必须与原始映射表一致；
7. 发现重复键、缺失键或多重匹配时立即报错，不得继续报告完整通过。

建议把完成条件从“`hit is not None` 计数到 10”改为：

- `b0_map_rows == 10`；
- `b0_map_unique_keys == 10`；
- `b0_map_matched == 10`；
- 每条记录的五项一致性检查全部通过；
- 任一项失败则 `b0_map_all=false`，并输出具体记录与原因。

### 8.2 回归测试建议

用合成映射表或只读快照做单元级测试，至少覆盖：

| 测试 | 输入 | 期望 |
| --- | --- | --- |
| T1 同 experiment_id、不同 sample | S5/S7 共用 remainder expid，r0–r3 | 四元组键 8 个唯一，不覆盖 |
| T2 完全重复键 | 同一 sample/expid/repeat/run_dir 两行 | 立即报错 |
| T3 S5 记录解析 | S5 remainder r0 | 命中 S5，不得命中 S7 |
| T4 缺失键 | 删除一行 | 报错，不得静默通过 |
| T5 run-dir 不一致 | 记录 run_dir 与映射行不同 | 报错 |
| T6 ordinal 不一致 | 映射 nth 与记录不符 | 报错 |
| T7 完整 10 行 | 现有 B0-REPEAT-MAP | 10/10，且 unique=10 |
| T8 全量快照回归 | 165 条只读快照 | 10/10，0 映射错误 |

测试必须先复现当前漏洞（T1 在旧键下 unique=6、但 matched=10），再验证新键下 unique=10、sample/run_dir 全部一致。

### 8.3 memory status 的后续处理

- 本轮不修改 Prompt，也不把 status 写进 Prompt；
- 未来生成时应在结果记录中写入结构化 `memory_injected`（含 status），并生成 `injected.json`，供 §5.6.6 使用；
- 对现有 165 条，继续保留 170 条内容映射，但把 `status` 标为 `inferred/unknown`；
- 若未来仍用外置台账，应在字段级增加 `status_state="inferred"` 或 `"unknown"`，不能只写字段级 `derived`；
- 在 `base_sha` 不可恢复、`injected.json` 不存在的前提下，任何“已完成 §5.6.6”表述都不成立。

### 8.4 short 语义的后续处理

- 不修改冻结设计；
- 建议未来记录同时保留 `short_term_slot_enabled`、`short_term_block_present`、`short_term_payload_nonempty`；
- 由导师确认 §7.1 的 boolean 取哪一个谓词；在确认前，台账继续使用“区块出现”并注明另一口径的 75/90。

---

## 9. 对冻结设计 §7.1 的影响

### 9.1 逐字段的准确表述

| §7.1 字段 | 现有数据能支持的最强表述 | 不能声称的内容 |
| --- | --- | --- |
| `run_id` | unrecoverable | “已恢复原始 run_id” |
| `base_sha` | unrecoverable | “已证明运行时源码版本” |
| `knowledge_result_ids` | externally_derived（仅空配置情形） | “非空检索也能恢复” |
| `memory_injected` — type/subject/strength | externally_derived | “status 也是记录的” |
| `memory_injected` — status | inferred / unknown | “已完成 §5.6.6 逐项核对” |
| `short_term_injected` | externally_derived（依赖 boolean 语义选择） | “唯一语义已由设计冻结” |
| `difficult_flag` | externally_derived | “B0 也按原始反馈置 true” |
| `data_kind` | externally_derived（provenance） | “样本文件已有 §3.4 字段” |

### 9.2 对“五项 derived”的修正

更准确的说法是：

- **四个字段**（`knowledge_result_ids`、`short_term_injected`、`difficult_flag`、`data_kind`）在各自限定下可标为 externally_derived；其中 `short_term_injected` 需先由导师选定语义，`knowledge_result_ids` 仅适用于空配置情形，`data_kind` 是 provenance 派生；
- **`memory_injected`** 是部分派生：type/subject/strength 可标 externally_derived，status 只能标 inferred/unknown；
- **两个字段**（`run_id`、`base_sha`）保持 unrecoverable。

因此不能再用“五个字段全部 externally_derived”概括本批数据；这正是第二轮复审要求补充说明的核心之一。

### 9.3 对契约修订建议的影响

- 三层状态仍可作为修订方向，但必须为 `status` 增加 `inferred`（或归入 `unknown`）；
- B0 映射修正属于审计工具的校验修复，不改变历史记录本身；但修正前不能把 `b0_map_all=true` 当作强证据；
- short 语义需要导师先定义，再决定 80/85 还是 75/90；
- 本轮不批准方案 B，不修改冻结设计 v4.5，不修改 `result_schema.py`，也不让预检转 PASS。

---

## 10. 当前决策状态

### 10.1 本轮已经完成

- 新增本补充说明；
- 对照固定 commit 复核了 B0 映射代码、`B0-REPEAT-MAP.md`、10 条 B0 记录、memory status 代码路径与 short 语义；
- 没有重新执行全量审计，没有重新生成台账。

### 10.2 尚未实施

- B0 四元组键修正与回归测试；
- memory status 的字段级 `inferred/unknown` 标记；
- short 三谓词的 schema 化；
- §7.1 契约修订或任何重跑。

### 10.3 需要导师确认

1. `memory_injected.status` 在 §7.1 中是否允许标为 `inferred`，还是必须归入 `unknown`；
2. 是否接受“四个字段 + memory 三个子字段 externally_derived、status inferred”的精细表述；
3. `short_term_injected` 的 boolean 取“区块出现”还是“非空 payload”；
4. 是否要求未来重跑，以及是否接受 B0 10 条继续不可重跑；
5. 是否批准 B0 校验修正与回归测试作为独立变更。

### 10.4 结论

**本轮只补充独立复审发现，不改变此前的审计结论，不批准方案 B，不修改冻结设计。**

现有 165 条记录仍可在不改历史数据的前提下支持“追溯性契约修订建议”；但 `memory_injected.status` 的证据等级必须降为 inferred/unknown，B0 的 10/10 自动化命中必须加上“键未唯一、样本未校验”的限定。是否接受这一修订、是否重跑、是否修改设计，均由导师/负责人决定。

---

## 附录 A：本文件引用的固定位置

| 内容 | 位置 |
| --- | --- |
| B0 映射读取 | `build_evidence_ledger.py:107-119` |
| B0 查找与计数 | `build_evidence_ledger.py:249-256` |
| B0 总检查 | `build_evidence_ledger.py:487-488` |
| memory status 取值 | `build_evidence_ledger.py:276-284` |
| short 判定 | `build_evidence_ledger.py:335-349` |
| B0 原始映射表 | `B0-REPEAT-MAP.md`（快照 `7b99ad9`） |
| 记忆投影 | `experiments/graduation/agent_tools.py:203-219` |
| 记忆 Tool 入口 | `experiments/graduation/agent_tools.py:222-269`（`:267` 为 status="active"） |
| 记忆检索 | `experiments/graduation/memory_service.py:2117-2190`（`:2184` 返回 status） |
| 记忆白名单 | `experiments/graduation/agent_plan_draft.py:111-120` |
| 记忆区块 | `experiments/graduation/agent_plan_draft.py:354-382` |
| 用户消息拼装 | `experiments/graduation/agent_plan_draft.py:385-441` |
| 组槽位 | `experiments/graduation/build_prompts.py:44-67` |
| 组输入 | `experiments/graduation/build_prompts.py:376-408` |

## 附录 B：本轮未改变的基线文件

- `DERIVED-FIELD-EVIDENCE-LEDGER.md`
- `DERIVED-FIELD-EVIDENCE.jsonl`
- `AUDIT-MANIFEST.sha256`
- `_stats.json`
- `build_evidence_ledger.py`
- `README.md`
- `.gitattributes`

上述 7 个文件在 `92ba6f9` 中的字节不变；本文件是新增的第 8 个文件，不进入原 `AUDIT-MANIFEST.sha256`，也不改变原有校验结果。
