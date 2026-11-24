# 未来生产器运行时采集规范（Run Provenance）

- 适用：`experiments/graduation/run_experiment.py` 及其调用的 prompt/记忆/计划链路
- 记录模式：`graduation-run-provenance/v1`
- 设计版本：`v4.5`
- 实现状态：独立分支已实现并通过模拟输入测试；**未合并、未用于正式实验**
- 目标：让未来的每条正式记录在**生成时**拥有 §7.1 所需事实，而不是事后从 prompt 反推

## 1. 原则

1. **从运行时对象采集，不从文本反推**：记忆的 id/type/subject/strength/status 必须取自实际注入的对象；知识 id 必须取自实际检索结果对象。
2. **先采集后请求**：Git 状态、run_id、注入清单必须在任何模型请求发出前确定；请求中途变更工作树不能污染已采集的基线。
3. **fail-closed**：关键字段缺失、类型错误、注入集合与 prompt 不一致时，抛错并拒绝写正式记录；不得写“看起来完整”的行。
4. **失败运行也要留元数据**：失败 run 仍应保留 run_id、base_sha、工作树状态、prompt 哈希、错误阶段，便于审计“尝试过什么”。
5. **历史不回填**：本规范只约束未来运行；不得把采集值写回 165 条历史记录。

## 2. 记录字段（正式记录必须全部存在）

| 字段 | 类型 | 采集时点 | 来源/校验 |
| --- | --- | --- | --- |
| `run_id` | string | run 开始 | `YYYYMMDDTHHMMSSZ-<sample>-<group>-r<repeat>-<8hex>`，进程内唯一 |
| `base_sha` | 40 hex | 模型请求前 | `git rev-parse HEAD` |
| `runtime_source_commit` | 40 hex | 同上 | 与 `base_sha` 同次采集；分开保存以便未来允许“基线≠当前”时审计 |
| `runtime_worktree_clean` | bool | 同上 | `git status --porcelain` 为空 |
| `runtime_patch_sha256` | 64 hex/null | 同上 | 脏工作树的二进制 diff + 未跟踪文件内容哈希；干净时必须为 null |
| `knowledge_result_ids` | string[] | prompt 构建后、请求前 | 实际检索结果对象的稳定 id；空结果必须为 `[]`，不得为 null |
| `memory_injected` | object[] | 请求前 | 实际注入对象；每条含 `memory_id/memory_type/subject_key/strength/status`，另可含 `content_sha256` |
| `short_term_slot_enabled` | bool | 请求前 | 组矩阵槽位 |
| `short_term_block_present` | bool | 请求前 | prompt 是否实际出现短期区块 |
| `short_term_feedback_history_present` | bool | 请求前 | 短期区块中反馈条数 > 0 |
| `short_term_feedback_count` | int/null | 请求前 | 实际条数；无区块为 null |
| `difficult_flag` | bool | 请求前 | 组槽位最终结果（不是原始反馈条件） |
| `data_kind` | enum | 样本创建阶段 | `simulated_learner_fixture` / `real_user_data`；样本必须显式带字段 |
| `config_sha256` | 64 hex | 计划生成时 | canonical config 哈希 |
| `plan_sha256` | 64 hex | run 开始 | 本次计划摘要；B0 legacy 兼容路径可为 null |
| `prompt_sha256` | 64 hex | 请求前 | 对实际发送的 `[{system},{user}]` canonical JSON 计算 |
| `injected_json_sha256` | 64 hex | 请求前 | 注入清单文件哈希；即使空清单也要有文件 |
| `injected_json_ref` | string | 请求前 | 相对 run_dir 的路径 |
| `result_schema_version` | string | 写记录时 | 固定 `graduation-run-provenance/v1` |
| `experiment_design_version` | string | 写记录时 | 冻结设计版本 `v4.5` |
| `generated_at` | ISO 时间 | 记录生成 | 与记录原字段一致 |
| `model_alias` | string/null | 请求前 | 请求使用的别名 |
| `model_snapshot_id` | string/null | 请求前 | 供应商快照 id；不可得写 null，不得编造 |

`run_id` 与 `audit_locator` 是两类东西：前者是运行时身份，后者是仓库外审计定位符。任何情况下不得互换。

## 3. 采集顺序（必须固定）

```text
加载 config / plan
  → capture_context()                 # base_sha、工作树、patch 哈希
  → 为本次 run 生成 run_id
  → collect_inputs()                  # 同时保留 memory 原始对象与 short-term 原始事实
  → 构建 prompt                        # 记录实际 system/user 与 prompt_sha256
  → select_injected_memories()        # 与本次 prompt 的记忆区块逐条对齐
  → write_injected_json()             # 原子写入；空清单也写
  → validate_provenance()（预检）
  → 发起模型请求
  → 写 results.jsonl（含 provenance）
  → validate_provenance()（写前最终校验）
```

任一箭头失败即停止；不得先请求后补采集。

## 4. 记忆注入清单

`injected.json` 结构（`graduation-injected-memory/v1`）：

```json
{
  "schema": "graduation-injected-memory/v1",
  "sample_id": "S1",
  "group": "D",
  "memories": [
    {"memory_id": "...", "memory_type": "task_topic", "subject_key": "一元二次方程",
     "strength": 0.9, "status": "active", "content_sha256": "..."}
  ]
}
```

- 由 `get_learning_memory` 返回的**原始对象**生成；不得从渲染后的 prompt 解析。
- 条数、`(memory_type, strength, content_sha256)` 集合必须与本次 prompt 记忆区块完全一致；不一致即拒绝运行。
- 只注入 `status="active"` 的规则仍由检索层保证；清单记录实际 status，供 §5.6.6 对照。
- 文件使用 canonical JSON + 换行，原子写入；哈希写入记录。
- 空清单（A/B/B0）也必须写文件，使“没有注入”成为可验证事实，而不是缺失。

## 5. 短期事实

生产器记录三个独立布尔 + 一个计数，**不**输出单一 `short_term_injected`：

| 事实 | 判定 |
| --- | --- |
| `short_term_slot_enabled` | 组矩阵是否开启 short 槽 |
| `short_term_block_present` | prompt 是否出现短期区块头 |
| `short_term_feedback_history_present` | 短期区块 JSON 的反馈条数 > 0 |
| `short_term_feedback_count` | 实际条数；无区块为 null |

冻结设计中的单一 Boolean 语义尚未获导师确认。生产器不得擅自把任一事实写成 `short_term_injected`；在导师确认前，正式实验应继续记录三事实，并在分析时并列报告。若导师批准某一语义，须以配置项显式声明语义版本，再由生产器派生旧字段；配置项与派生规则必须写入设计修订记录。

## 6. 知识检索 id

- 来源必须是实际检索结果对象（当前配置为空，故为 `[]`）。
- 每个结果必须有稳定 id；缺 id 时抛 `ProvenanceError`，不得用序号、标题哈希或路径代替。
- `knowledge_search_failed=true` 与空结果必须区分：前者不得写成 `[]` 后当作“无知识”。

## 7. 数据标记

- `data_kind` 在**样本创建阶段**写入样本文件；生产器只读取并校验，不在运行时猜。
- 模拟样本必须同时满足 `simulation.is_simulated=true` 与 `gold_standard.simulation=true`；真实样本必须为 false。
- 缺字段即拒绝：不得用“看起来像模拟数据”推断。
- 历史 8 个样本均无原生字段，说明 §3.4 在样本层也未落实；未来样本生成器必须补。

## 8. 失败运行

- 失败记录至少保留：`run_id/base_sha/runtime_worktree_clean/runtime_patch_sha256/prompt_sha256/config_sha256/plan_sha256/generated_at/error_stage/error_message`。
- 失败不得写 `memory_injected=[]` 冒充“无记忆”；应写 `null` 或明确 `not_collected`。
- 失败记录与成功记录必须可区分（`status` 字段），统计默认排除失败运行。

## 9. 校验与 Schema

- 写前 `validate_provenance(strict=True)`：必填、格式、布尔、枚举、哈希、时间、model 类型。
- 正式运行禁止 `strict=False`；该参数只用于单元测试/调试，且必须显式传 `provenance_context`。
- 建议把本规范字段固化为 JSON Schema，并在 CI 中对模拟 run 的产物做校验；Schema 变更须提升 `result_schema_version`。
- `runtime_worktree_clean=false` 时 `runtime_patch_sha256` 必须非空；两者矛盾即拒绝。

## 10. 与现有代码的接入点

| 位置 | 动作 |
| --- | --- |
| `run_experiment.main` | 读取 config 后 `capture_context()`；失败打印拒绝原因并退出（当前退出码 5） |
| `build_prompts.collect_inputs` | 传入 `memory_service`，在 fixed clock 下保留 default/subject 原始记忆对象；失败抛错 |
| `run_experiment.run_one` | 生成 `run_id`；调用 `select_injected_memories` 与 `write_injected_json`；模型请求前完成采集 |
| `run_one` 记录组装 | 合并 provenance 字段；写盘前 `validate_provenance` |
| `run_experiment.main` 调用处 | 传入 `config_sha256/sample/provenance_context`；`ProvenanceError` 不写 results 行 |
| 测试 | 只用模拟 Git 仓库、模拟样本、模拟记忆对象；不得访问真实 `feedback.db` 或 `blind_private/` |

## 11. 迁移与发布门槛

1. 本规范与实现必须先通过独立复审，且不改变冻结设计的统计方法/分组/样本/重复/盲评。
2. 正式启用前，导师需确认：短期的单一 Boolean 语义、memory runtime status 的呈现方式、`data_kind` 的样本原生字段、§5.6.6 的对照物。
3. 启用后，旧记录与新记录必须用版本字段区分；不得把新字段回填旧记录。
4. 预检应新增“provenance 完整”检查，但不得因外置证据或新生产器而把历史批次的 FAIL 改为 PASS。

## 12. 非目标

- 不重跑 155 条历史数据。
- 不为 B0 补造 plan/config。
- 不把 `model_alias` 当作模型快照证明。
- 不承诺 `injected.json` 能替代 §5.6.6 的人工复核；它只是可对照的运行时工件。
