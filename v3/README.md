# V3 历史证据层（frozen 165 records）

本目录是 **仓库外证据层**，不是原始实验记录，也不是预检放行证据。它只回答一个问题：对 2026-11-13 已冻结的 165 条生成记录，七个 §7.1 字段中哪些能凭现有工件外置追溯、哪些不能，以及证据强度到哪里为止。

## 产物

| 文件 | 作用 |
| --- | --- |
| `HISTORICAL-EVIDENCE-CONTRACT.md` | 规范：状态词、封套、逐字段规则、判定优先级、验收分离 |
| `historical-evidence.schema.json` | 逐行 JSON Schema 2020-12 校验 |
| `DERIVED-FIELD-EVIDENCE-V3.jsonl` | 165 行，一条原始记录一行 |
| `DERIVED-FIELD-EVIDENCE-V3-STATS.json` | 由行重算的统计与完整性检查 |
| `V3-BUILD-STATE.json` | 最近一次原子构建的 success/failed 状态 |
| `V3-MANIFEST.sha256` | 本目录交付文件的 SHA-256 |
| `FUTURE-PRODUCER-RECORDING-SPEC.md` | 未来生产器运行时采集规范（不是历史回填方案） |
| `ADVISOR-DECISION-BRIEF-V3.md` | 需导师拍板的语义与整改选项 |
| `build_evidence_ledger_v3.py` | 构建器；只读快照仓与源码仓，不写原始数据 |
| `tests/` | 35 个标准库 unittest，覆盖封套、逐字段语义、B0 四元组、统计与原子写 |

## 构建

要求 Python 3.10+，只读输入：快照仓、源码只读复核基线。输出目录必须与输入分离。

```powershell
$env:PYTHONIOENCODING='utf-8'
& F:\somethingProject\dsbot\.venv\Scripts\python.exe v3\build_evidence_ledger_v3.py `
  --audit-root F:\somethingProject\graduation-preflight-audit `
  --source-root F:\somethingProject\dsbot-preflight `
  --v2-dir F:\somethingProject\graduation-audit-review-repo\v2 `
  --out-dir F:\somethingProject\graduation-audit-review-repo\v3
```

构建顺序：全部行在内存中生成 → 完整性检查 → 写临时目录 → 回读校验 → 原子替换；任何一步失败都不留下混合产物，并把 `V3-BUILD-STATE.json` 写成 `failed`。重复构建应逐字节一致（`generated_at` 不写入产物）。

## 测试

```powershell
$env:PYTHONIOENCODING='utf-8'
$env:PYTHONPATH='F:\somethingProject\graduation-audit-review-repo'
& F:\somethingProject\dsbot\.venv\Scripts\python.exe -m unittest discover -s v3/tests -v
```

预期：`Ran 35 tests ... OK`，exit 0。

## 校验清单

```powershell
# JSONL 严格解析 + 行数
Get-Content v3\DERIVED-FIELD-EVIDENCE-V3.jsonl -Encoding utf8 |
  ForEach-Object { $_ | ConvertFrom-Json | Out-Null }
(Get-Content v3\DERIVED-FIELD-EVIDENCE-V3.jsonl).Count   # 165

# manifest（LF 文本；如被 Windows 检出为 CRLF，先规范化副本再校验）
Get-Content v3\V3-MANIFEST.sha256
```

## 边界（必须与结论一起引用）

- 165 条原始记录**仍不含**七字段；`original_contract_compliance` 为 `FAIL`，预检仍 FAIL。外置层完整不等于原契约合规。
- `run_id`、`base_sha` 在本批**不可恢复**；`audit_locator`、`reviewed_source_commit` 都不是它们的替代值。
- `memory_injected` 的内容/类型/主题/强度可外置映射；运行时 `status` 只能 `inferred`（`not_verified`）。`injected.json` 不存在，§5.6.6 **未完成**。
- 短期字段拆成三谓词；冻结设计中的单一 Boolean 语义仍待导师确认，V3 不擅自重定义。
- 不重跑、不回填、不改快照、不改冻结设计；本目录不构成契约修订批准。
