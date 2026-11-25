import {
  AlertTriangle,
  CheckCircle2,
  Database,
  FileCheck2,
  GitCommitHorizontal,
  ShieldAlert,
  ShieldCheck,
} from 'lucide-react';
import type { OverviewResponse } from '../types.ts';

interface OverviewTabProps {
  data: OverviewResponse;
  onNavigateRecords: (filter?: { segment?: string }) => void;
  onNavigateDiagnostics: () => void;
}

const SEGMENT_LABELS: Record<string, { label: string; desc: string }> = {
  main: {
    label: '主实验 (main)',
    desc: 'A/B/C/D × S1–S7 × 5 次（含 plan.json 绑定）',
  },
  'supplementary-subject': {
    label: '补充实验 · 学科过滤',
    desc: 'S5 的 C-subj / D-subj × 5 次（概率论过滤）',
  },
  'supplementary-s7empty': {
    label: '补充实验 · S7-empty',
    desc: 'S7-empty 仅 D 组 × 5 次（短期区块存在但计数为 0）',
  },
  'b0-legacy': {
    label: 'B0 Legacy 复跑',
    desc: 'S5、S7 各 5 次（无 plan.json，依赖 B0-REPEAT-MAP）',
  },
};

export function OverviewTab({
  data,
  onNavigateRecords,
  onNavigateDiagnostics,
}: OverviewTabProps) {
  const { baseline, liveVerification, manifest, statsJson, secondRoundDiagnostics } =
    data;

  const sevenFieldSummary = [
    {
      name: 'knowledge_result_ids',
      state: 'externally_derived',
      coverage: '165 / 165',
      summary: '[]（空知识库配置，Prompt 明示无检索结果）',
      caveat: '仅适用于空配置情形',
    },
    {
      name: 'memory_injected (type / subject / strength)',
      state: 'externally_derived',
      coverage: '170 / 170 条目 (80 条记录)',
      summary: 'content 与 Gold 唯一映射 170/170，type/strength 100% 匹配',
      caveat: '子字段 status 降级为 inferred / unknown',
    },
    {
      name: 'memory_injected.status',
      state: 'inferred_unknown',
      coverage: '170 / 170 条目',
      summary: 'Gold 为 active，由 get_learning_memory→retrieve(status="active") 推定',
      caveat: 'Prompt 已剥离 status，缺 base_sha 与 injected.json',
    },
    {
      name: 'short_term_injected',
      state: 'externally_derived',
      coverage: '165 / 165',
      summary: `区块出现口径 ${secondRoundDiagnostics.shortTermSemantics.blockPresentTrue}/${secondRoundDiagnostics.shortTermSemantics.blockPresentFalse}；非空 payload 口径 ${secondRoundDiagnostics.shortTermSemantics.payloadNonemptyTrue}/${secondRoundDiagnostics.shortTermSemantics.payloadNonemptyFalse}`,
      caveat: 'S7-empty 5 条随语义选择翻转，待导师确认',
    },
    {
      name: 'difficult_flag',
      state: 'externally_derived',
      coverage: '165 / 165 (true: 10)',
      summary: '按最新反馈 partial + 任务难度太高与动态规则匹配，B0 组固定 false',
      caveat: 'S7 在 B0 下原始反馈满足条件但 B0 槽位关闭',
    },
    {
      name: 'data_kind',
      state: 'externally_derived',
      coverage: '165 / 165',
      summary: 'simulated_learner_fixture（8/8 样本与 Gold 均为 simulation=true）',
      caveat: '由样本 provenance 派生，非 §3.4 原文件字段',
    },
    {
      name: 'run_id',
      state: 'unrecoverable',
      coverage: '0 / 165 恢复',
      summary: '生成时未写入 results.jsonl；audit_locator 仅作审计定位，非 run_id',
      caveat: '保持 null，禁止伪造',
    },
    {
      name: 'base_sha',
      state: 'unrecoverable',
      coverage: '0 / 165 恢复',
      summary: '运行器未记录运行时 git HEAD / 工作树状态',
      caveat: '保持 null，执行报告声明不构成机器证明',
    },
  ];

  const assertionEntries = Object.entries(statsJson.checks).filter(
    ([k]) => k !== 'segments'
  );

  return (
    <div className="space-y-6">
      {/* Top KPI Cards */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-xs">
          <div className="flex items-center justify-between text-xs font-medium text-slate-500">
            <span>真实生成记录总数</span>
            <Database className="h-4 w-4 text-slate-400" />
          </div>
          <div className="mt-2 flex items-baseline gap-2">
            <span className="text-3xl font-semibold tracking-tight text-slate-900">
              {liveVerification.parsedRecords}
            </span>
            <span className="text-xs text-slate-500">
              / {liveVerification.physicalLines} 物理行（0 错）
            </span>
          </div>
          <p className="mt-2 text-xs text-slate-600">
            {(liveVerification.totalBytes / 1024 / 1024).toFixed(2)} MB · 无 BOM ·{' '}
            {liveVerification.uniqueLocators} 唯一 locator
          </p>
        </div>

        <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-xs">
          <div className="flex items-center justify-between text-xs font-medium text-slate-500">
            <span>七字段粗粒度统计</span>
            <FileCheck2 className="h-4 w-4 text-emerald-600" />
          </div>
          <div className="mt-2 flex items-baseline gap-2">
            <span className="text-3xl font-semibold tracking-tight text-slate-900">
              {liveVerification.fieldStateCounts.derived}
            </span>
            <span className="text-xs font-medium text-emerald-700">
              derived
            </span>
            <span className="text-slate-300">/</span>
            <span className="text-xl font-semibold text-amber-700">
              {liveVerification.fieldStateCounts.unrecoverable}
            </span>
            <span className="text-xs font-medium text-amber-700">
              unrecoverable
            </span>
          </div>
          <p className="mt-2 text-xs text-slate-600">
            direct: {liveVerification.fieldStateCounts.direct} · 共{' '}
            {liveVerification.fieldStateCounts.total} 项（7 × 165）
          </p>
        </div>

        <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-xs">
          <div className="flex items-center justify-between text-xs font-medium text-slate-500">
            <span>哈希链与 Prompt 绑定</span>
            <ShieldCheck className="h-4 w-4 text-indigo-600" />
          </div>
          <div className="mt-2 flex items-baseline gap-2">
            <span className="text-3xl font-semibold tracking-tight text-slate-900">
              {liveVerification.promptHashMatched}
            </span>
            <span className="text-xs text-slate-500">/ 165 Prompt 匹配</span>
          </div>
          <p className="mt-2 text-xs text-slate-600">
            新数据计划绑定: {liveVerification.planMatched} / 155 · B0 无计划链: 10
          </p>
        </div>

        <div className="rounded-xl border border-amber-200 bg-amber-50/60 p-5 shadow-xs">
          <div className="flex items-center justify-between text-xs font-medium text-amber-800">
            <span>第二轮独立复审限定</span>
            <ShieldAlert className="h-4 w-4 text-amber-600" />
          </div>
          <div className="mt-2 flex items-baseline gap-2">
            <span className="text-2xl font-semibold tracking-tight text-amber-950">
              2 项核心限定
            </span>
          </div>
          <p className="mt-2 text-xs text-amber-900">
            B0 旧键冲突（6 vs 10 键）· memory status 降为 inferred/unknown
          </p>
          <button
            type="button"
            onClick={onNavigateDiagnostics}
            className="mt-2 text-xs font-medium text-amber-800 underline underline-offset-2 hover:text-amber-950 cursor-pointer"
          >
            查看复审诊断细节 →
          </button>
        </div>
      </div>

      {/* Baseline Commits & Boundary */}
      <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-xs">
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 pb-3">
          <div className="flex items-center gap-2">
            <GitCommitHorizontal className="h-4 w-4 text-slate-500" />
            <h2 className="text-sm font-semibold text-slate-900">
              审计基线与边界声明
            </h2>
          </div>
          <span className="rounded-md bg-slate-100 px-2.5 py-1 text-xs font-medium text-slate-700">
            审计日期 {baseline.auditDate} · 只读外置证据（不修改 results.jsonl / 不让预检转 PASS）
          </span>
        </div>
        <div className="mt-4 grid grid-cols-1 gap-4 md:grid-cols-3">
          <div className="rounded-lg bg-slate-50 p-3">
            <div className="text-xs font-medium text-slate-500">数据快照仓库</div>
            <div className="mt-1 font-mono text-xs text-slate-900 break-all">
              {baseline.auditRepo}
            </div>
            <div className="mt-1 font-mono text-[11px] text-slate-500 break-all">
              {baseline.auditCommit}
            </div>
          </div>
          <div className="rounded-lg bg-slate-50 p-3">
            <div className="text-xs font-medium text-slate-500">源码基线仓库</div>
            <div className="mt-1 font-mono text-xs text-slate-900 break-all">
              {baseline.srcRepo}
            </div>
            <div className="mt-1 font-mono text-[11px] text-slate-500 break-all">
              {baseline.srcCommit}
            </div>
          </div>
          <div className="rounded-lg bg-slate-50 p-3">
            <div className="text-xs font-medium text-slate-500">复审交付基线</div>
            <div className="mt-1 font-mono text-xs text-slate-900 break-all">
              {baseline.reviewRepo}
            </div>
            <div className="mt-1 font-mono text-[11px] text-slate-500 break-all">
              {baseline.reviewBaselineCommit}
            </div>
          </div>
        </div>
      </div>

      {/* Segment Distribution */}
      <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-xs">
        <h2 className="text-sm font-semibold text-slate-900">
          样本分段分布（点击分段可跳转至逐条台账）
        </h2>
        <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {Object.entries(liveVerification.segments).map(([seg, count]) => {
            const meta = SEGMENT_LABELS[seg] ?? { label: seg, desc: '' };
            return (
              <button
                key={seg}
                type="button"
                onClick={() => onNavigateRecords({ segment: seg })}
                className="flex flex-col justify-between rounded-lg border border-slate-200 bg-slate-50/70 p-4 text-left transition hover:border-indigo-300 hover:bg-indigo-50/40 cursor-pointer"
              >
                <div>
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-semibold text-slate-900">
                      {meta.label}
                    </span>
                    <span className="rounded bg-white px-2 py-0.5 font-mono text-xs font-semibold text-indigo-700 ring-1 ring-slate-200">
                      {count}
                    </span>
                  </div>
                  <p className="mt-1.5 text-xs text-slate-600">{meta.desc}</p>
                </div>
                <span className="mt-3 text-[11px] font-medium text-indigo-600">
                  筛选查看记录 →
                </span>
              </button>
            );
          })}
        </div>
      </div>

      {/* Seven Field Matrix (with Second Round Refinement) */}
      <div className="rounded-xl border border-slate-200 bg-white shadow-xs overflow-hidden">
        <div className="border-b border-slate-200 px-5 py-4">
          <h2 className="text-sm font-semibold text-slate-900">
            §7.1 七字段证据分级矩阵（已纳入第二轮独立复审细化）
          </h2>
          <p className="mt-1 text-xs text-slate-500">
            区分「externally_derived」、「inferred / unknown」与「unrecoverable」，避免将代码路径推定写成直接记录事实。
          </p>
        </div>
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-slate-200 text-left text-xs">
            <thead className="bg-slate-50 text-slate-600">
              <tr>
                <th className="px-5 py-3 font-semibold">字段 / 子字段</th>
                <th className="px-4 py-3 font-semibold">证据状态</th>
                <th className="px-4 py-3 font-semibold">覆盖范围</th>
                <th className="px-4 py-3 font-semibold">可支持的最强结论</th>
                <th className="px-5 py-3 font-semibold">限定条件 / 缺口</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 bg-white">
              {sevenFieldSummary.map((row) => (
                <tr key={row.name} className="hover:bg-slate-50/70">
                  <td className="px-5 py-3 font-mono font-medium text-slate-900">
                    {row.name}
                  </td>
                  <td className="px-4 py-3 whitespace-nowrap">
                    {row.state === 'externally_derived' && (
                      <span className="inline-flex items-center gap-1 rounded-md bg-emerald-50 px-2 py-0.5 font-medium text-emerald-700 ring-1 ring-emerald-200">
                        externally_derived
                      </span>
                    )}
                    {row.state === 'inferred_unknown' && (
                      <span className="inline-flex items-center gap-1 rounded-md bg-amber-50 px-2 py-0.5 font-medium text-amber-800 ring-1 ring-amber-200">
                        inferred / unknown
                      </span>
                    )}
                    {row.state === 'unrecoverable' && (
                      <span className="inline-flex items-center gap-1 rounded-md bg-rose-50 px-2 py-0.5 font-medium text-rose-700 ring-1 ring-rose-200">
                        unrecoverable
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-3 font-mono text-slate-700 whitespace-nowrap">
                    {row.coverage}
                  </td>
                  <td className="px-4 py-3 text-slate-700">{row.summary}</td>
                  <td className="px-5 py-3 text-slate-500">{row.caveat}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Manifest SHA-256 Live Verification & Stats Assertions */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <div className="rounded-xl border border-slate-200 bg-white shadow-xs overflow-hidden">
          <div className="border-b border-slate-200 px-5 py-4">
            <h2 className="text-sm font-semibold text-slate-900">
              AUDIT-MANIFEST.sha256 实时校验
            </h2>
            <p className="mt-1 text-xs text-slate-500">
              Node.js crypto 对当前磁盘上的交付文件实时计算 SHA-256 并比对清单。
            </p>
          </div>
          <div className="divide-y divide-slate-100">
            {manifest.map((item) => (
              <div key={item.filename} className="px-5 py-3.5 text-xs">
                <div className="flex items-center justify-between gap-2">
                  <span className="font-mono font-semibold text-slate-900">
                    {item.filename}
                  </span>
                  {item.status === 'matched' && (
                    <span className="inline-flex items-center gap-1 rounded bg-emerald-50 px-2 py-0.5 font-medium text-emerald-700 ring-1 ring-emerald-200">
                      <CheckCircle2 className="h-3.5 w-3.5" />
                      SHA-256 匹配
                    </span>
                  )}
                  {item.status === 'migrated_to_node' && (
                    <span className="inline-flex items-center gap-1 rounded bg-slate-100 px-2 py-0.5 font-medium text-slate-700 ring-1 ring-slate-200">
                      已迁移至 Node.js/TS
                    </span>
                  )}
                  {(item.status === 'mismatch' || item.status === 'missing') && (
                    <span className="inline-flex items-center gap-1 rounded bg-rose-50 px-2 py-0.5 font-medium text-rose-700 ring-1 ring-rose-200">
                      <AlertTriangle className="h-3.5 w-3.5" />
                      {item.status}
                    </span>
                  )}
                </div>
                <div className="mt-1.5 font-mono text-[11px] text-slate-500 break-all">
                  期望: {item.expectedSha256}
                </div>
                {item.actualSha256 && (
                  <div className="mt-0.5 font-mono text-[11px] text-slate-500 break-all">
                    实测: {item.actualSha256} ({item.bytes?.toLocaleString()} bytes)
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>

        <div className="rounded-xl border border-slate-200 bg-white shadow-xs overflow-hidden">
          <div className="border-b border-slate-200 px-5 py-4">
            <h2 className="text-sm font-semibold text-slate-900">
              _stats.json 完整性断言清单
            </h2>
            <p className="mt-1 text-xs text-slate-500">
              原始台账生成的全量断言；注：b0_map_all 需配合第二轮四元组复核限定阅读。
            </p>
          </div>
          <div className="max-h-96 overflow-y-auto divide-y divide-slate-100">
            {assertionEntries.map(([key, val]) => {
              const isBool = typeof val === 'boolean';
              const isArray = Array.isArray(val);
              return (
                <div
                  key={key}
                  className="flex items-center justify-between px-5 py-2.5 text-xs"
                >
                  <span className="font-mono text-slate-700">{key}</span>
                  {isBool ? (
                    <span
                      className={`rounded px-2 py-0.5 font-mono font-medium ${
                        val
                          ? 'bg-emerald-50 text-emerald-700'
                          : 'bg-rose-50 text-rose-700'
                      }`}
                    >
                      {String(val)}
                    </span>
                  ) : isArray ? (
                    <span className="rounded bg-slate-100 px-2 py-0.5 font-mono text-slate-700">
                      [{val.length} items]
                    </span>
                  ) : (
                    <span className="rounded bg-slate-100 px-2 py-0.5 font-mono font-semibold text-slate-900">
                      {String(val)}
                    </span>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}
