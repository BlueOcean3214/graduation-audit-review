# V2 审计证据层

本目录是历史实验数据审计的第二版（V2）外置证据层，针对 165 条历史记录，独立于第一版产物。

## 基线

| 对象 | 版本 |
| --- | --- |
| 数据快照 | `BlueOcean3214/graduation-preflight-audit` @ `7b99ad96db78167c490874af9c4b48484b6d6ef0` |
| 复核源码 | `BlueOcean3214/AI-Study-Assistant` @ `df155a5c145297bc5e6a085636fadfd6185586bd` |
| 第一版审计 | `BlueOcean3214/graduation-audit-review` @ `10a52394f110d471f9f36d832c56388c836e70ee` |

V2 不修改原始记录，不修改第一版文件，不让预检转为 PASS。

## 产物

| 文件 | 说明 |
| --- | --- |
| `DERIVED-FIELD-EVIDENCE-V2.jsonl` | 165 行逐条证据台账；每行含来源、定位符、Prompt/plan 绑定和七字段证据 |
| `DERIVED-FIELD-EVIDENCE-V2-STATS.json` | 总体、分段、memory、短期三谓词、B0 映射和完整性统计 |
| `HISTORICAL-EXPERIMENT-DATA-REMEDIATION.md` | 技术整改报告（中文） |
| `ADVISOR-DECISION-BRIEF.md` | 面向导师的决策说明（2–4 页） |
| `build_evidence_ledger_v2.py` | 确定性构建器；失败即不写产物 |
| `tests/` | 42 项单元与全量回归测试 |
| `V2-MANIFEST.sha256` | 本目录新增文件的 SHA-256 清单 |

## 复现

```powershell
$env:PYTHONIOENCODING = "utf-8"
& F:\somethingProject\dsbot\.venv\Scripts\python.exe `
  v2\build_evidence_ledger_v2.py `
  --audit-root F:\somethingProject\graduation-preflight-audit `
  --source-root F:\somethingProject\dsbot-preflight `
  --out-dir v2
```

构建器会校验快照仓与源码仓的 HEAD 和 clean 状态；任一完整性检查失败时退出码为 2，不写文件。

测试：

```powershell
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONPATH = (Get-Location).Path
& F:\somethingProject\dsbot\.venv\Scripts\python.exe -m unittest discover -s v2/tests -v
```

## 校验清单

在仓库根目录执行：

```powershell
Get-Content v2/V2-MANIFEST.sha256 | ForEach-Object {
  $hash, $path = $_ -split "  ", 2
  $actual = (Get-FileHash $path -Algorithm SHA256).Hash.ToLower()
  if ($actual -ne $hash) { throw "MISMATCH: $path" }
}
```

## 关键限制

- `run_id`、`base_sha` 保持 `unrecoverable`，没有伪造替代值。
- memory 的 content/type/subject_key/strength 是 externally_derived；Gold status 是 gold_reference；运行时 status 是 inferred / not_verified。
- 短期记忆拆成 slot_enabled / block_present / payload_nonempty 三个谓词，冻结设计原 Boolean 的语义仍待导师确认。
- §5.6.6 未完成：快照中没有 `injected.json`，运行时 base_sha 不可恢复。
- 预检仍按原始合同报告 FAIL；V2 只是外置证据层。

详见 `HISTORICAL-EXPERIMENT-DATA-REMEDIATION.md` 与 `ADVISOR-DECISION-BRIEF.md`。
