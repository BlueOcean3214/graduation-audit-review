# 毕业实验七字段外置派生证据台账 — 独立复审包

本仓库用于 **ChatGPT 第二轮独立复核**，不是压缩包。仓库根目录直接保存 5 个审计交付文件，字节与生成目录一致，未做任何行尾规范化或内容改写。

## 1. 基线与来源

| 项 | 值 |
| --- | --- |
| 数据快照仓库 | `BlueOcean3214/graduation-preflight-audit` |
| 快照 commit | `7b99ad96db78167c490874af9c4b48484b6d6ef0` |
| 源码仓库 | `BlueOcean3214/AI-Study-Assistant` |
| 源码 commit | `df155a5c145297bc5e6a085636fadfd6185586bd`（PR #26 head） |
| 审计报告日期 | 2026-11-24 |
| 审计范围 | 165 条真实生成记录：main 140、suppl-subj 10、suppl-s7empty 5、B0 legacy 10 |

本次仅做交付打包与上传；**没有**重新运行审计脚本、没有修改原始记录、没有访问实验数据库或盲评私有数据、没有修改任何现有仓库或 PR。

## 2. 文件清单

| 文件 | 字节 | SHA-256 | 作用 |
| --- | ---: | --- | --- |
| `DERIVED-FIELD-EVIDENCE-LEDGER.md` | 31,324 | `68bbfd8cabd847bab659aad7abe64b7708a34247bd8081fae2c526a7acdf0642` | 主报告：方法、逐字段结论、覆盖率、不能确定项、剩余风险、契约修订建议 |
| `DERIVED-FIELD-EVIDENCE.jsonl` | 1,068,174 | `706b26d03d945b5392882c85043781d0270f2d39cb74293a4f1e63d3dacab097` | 165 行逐条证据，一行对应一条原始记录 |
| `AUDIT-MANIFEST.sha256` | 367 | `8e03c89ad41d159b49888b3b7eb1cb91e5ea749cfe98113e4790de1cfdb062a4` | 对上述报告、JSONL、`_stats.json`、生成脚本的 SHA-256 清单 |
| `_stats.json` | 1,890 | `c59ac9968b998425f212afb68d30ad481438c9976063693850f57ea7ce26477b` | 全部完整性断言与分段计数 |
| `build_evidence_ledger.py` | 23,444 | `ddfd1af80b4b247e1cea22750e3f357adf057cb99353c6f7be44c785b222210b` | 台账生成脚本（本包未重新执行） |

此外仓库根目录只有本 `README.md` 与 `.gitattributes`，没有其他数据文件。

## 3. 打包后已执行的复核

1. **字节一致**：5 个文件从 `F:\somethingProject\graduation-audit-output\` 复制到本仓库，逐一比对 SHA-256，5/5 一致。
2. **清单校验**：`AUDIT-MANIFEST.sha256` 覆盖的 4 个文件全部匹配；清单本身不被自身覆盖（这是清单格式的固有限制，已如实说明）。
3. **JSONL 严格解析**：1,068,174 字节、无 BOM、165 个物理行；165/165 解析成功；空行 0；无效 JSON 0；`audit_locator` 165 个且唯一；`(repository, result_file, line_number)` 三元组 165 个且唯一；无重复记录。
4. **字段状态计数**：`derived` 825 项（5 字段 × 165）、`unrecoverable` 330 项（2 字段 × 165），合计 1,155 项，与 7 字段 × 165 条一致。
5. **禁止文件扫描**：目录内没有 `.db / .sqlite / .zip / .key / .pem`，没有 `blind_private`、盲评映射或 `feedback` 数据库文件；只有 5 个文本工件。
6. **执行日志**：源目录中不存在完整审计执行日志，因此**未纳入**；没有伪造日志或校验结果。
7. **行尾**：报告、JSONL、脚本为 LF；清单与 `_stats.json` 为 CRLF。全部按原字节保留，未做 LF 规范化。

## 4. 如何校验

清单行使用 CRLF，Linux/macOS 直接 `sha256sum -c` 会把 `\r` 当成文件名的一部分。请先去掉行尾 `\r`：

```bash
sed 's/\r$//' AUDIT-MANIFEST.sha256 | sha256sum -c -
```

Windows PowerShell：

```powershell
Get-Content AUDIT-MANIFEST.sha256 | ForEach-Object {
  $p = $_ -split '  ',2
  $h = (Get-FileHash -Algorithm SHA256 -LiteralPath $p[1]).Hash.ToLower()
  if ($h -ne $p[0]) { throw "MISMATCH $($p[1])" }
}
"OK"
```

Python（跨平台）：

```python
import hashlib, pathlib
for line in pathlib.Path("AUDIT-MANIFEST.sha256").read_text(encoding="utf-8").splitlines():
    expected, name = line.split("  ", 1)
    actual = hashlib.sha256(pathlib.Path(name).read_bytes()).hexdigest()
    assert actual == expected, name
print("OK")
```

## 5. 复审边界（重要）

- 七字段中 **0 个是 direct**；`run_id` 与 `base_sha` 在 165/165 上为 `unrecoverable`。
- 其余五个字段为 `externally_derived`：`knowledge_result_ids`（165/165，值 `[]`）、`memory_injected`（165/165，170 个条目）、`short_term_injected`（165/165，true 80）、`difficult_flag`（165/165，true 10）、`data_kind`（165/165，`simulated_learner_fixture`）。
- `memory_injected.status="active"` 是**推定**：prompt 不携带 status，依据是唯一消费者 `get_learning_memory` 只请求 active，加上 gold `injected=true`；不是从记录直接读出。
- `short_term_injected` 采用“实际内容注入”语义；若改按“存在非空短期条目”，S7-empty 的 5 条会翻转。
- `base_sha` 缺失，运行时源码版本未被机器绑定；`prompt_sha256` 只证明“记录 ↔ prompt 文件”绑定，不证明运行时实际发送给模型的消息逐字节相同。
- 设计 §5.6.6 所需的 `injected.json` 在快照与源码仓库中均不存在，无法按原文做逐项完全一致检查。
- 本台账是**仓库外追溯证据**，不改变 `results.jsonl`，也不能让预检转绿；预检仍会对七字段缺失报 FAIL。
- 本仓库不包含真实 `experiments/graduation/runs/`、`feedback.db`、`blind_private/` 或任何盲评私有映射。

## 6. 建议复审重点

1. 每个字段的派生规则是否确实由源码与数据支撑，是否存在循环论证或把统计规律当单条证据。
2. `memory_injected` 的 170 条 content 唯一映射是否成立；status 推定是否可接受，是否应降为 `unknown`。
3. `short_term_injected` 的语义选择是否合理；S7-empty 5 条翻转对结论的影响。
4. `difficult_flag` 对 B0 的“组固定 false、原始反馈满足条件”处理是否清晰、是否会被误读。
5. `data_kind` 的 provenance 派生是否足以弥补 §3.4 文件字段缺失。
6. 三层状态（`recorded_at_generation` / `externally_derived` / `unrecoverable`）的契约修订建议是否越界，是否会被误读为“§7.1 已满足”。

## 7. 复现限制

`build_evidence_ledger.py` 为只读脚本，但硬编码了两个本地路径（审计快照仓与源码工作树）。仅凭本仓库不能直接重跑；它的价值是让复审者检查派生逻辑。JSONL 中每条记录都保留 `source`、`audit_locator`、`prompt`、`plan` 与七字段 `state/value/evidence`，可脱离脚本逐条核对。

## 8. 决策状态

本审计**不批准**方案 B，也不修改冻结设计或契约报告；是否采用契约修订、是否重跑，均待导师/负责人决策。
