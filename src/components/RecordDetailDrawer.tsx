import {
  CheckCircle2,
  Code2,
  FileText,
  Layers,
  ShieldAlert,
  X,
} from 'lucide-react';
import type { EvidenceRecord } from '../types.ts';

interface RecordDetailDrawerProps {
  record: EvidenceRecord | null;
  loading: boolean;
  onClose: () => void;
}

function StateBadge({ state }: { state: string }) {
  if (state === 'derived') {
    return (
      <span className="rounded bg-emerald-50 px-2 py-0.5 text-[11px] font-medium text-emerald-700 ring-1 ring-emerald-200">
        derived
      </span>
    );
  }
  if (state === 'unrecoverable') {
    return (
      <span className="rounded bg-rose-50 px-2 py-0.5 text-[11px] font-medium text-rose-700 ring-1 ring-rose-200">
        unrecoverable
      </span>
    );
  }
  return (
    <span className="rounded bg-amber-50 px-2 py-0.5 text-[11px] font-medium text-amber-800 ring-1 ring-amber-200">
      {state}
    </span>
  );
}

export function RecordDetailDrawer({
  record,
  loading,
  onClose,
}: RecordDetailDrawerProps) {
  if (!record && !loading) return null;

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-slate-900/40 backdrop-blur-[1px]">
      <div className="flex h-full w-full max-w-3xl flex-col bg-white shadow-2xl">
        <div className="flex items-center justify-between border-b border-slate-200 px-6 py-4">
          <div>
            <h3 className="text-base font-semibold text-slate-900">
              {loading
                ? '正在加载记录证据...'
                : `记录 #${record!.index + 1} · ${record!.source.sample_id} / ${record!.source.group} (r${record!.source.repeat_index})`}
            </h3>
            {record && (
              <p className="mt-0.5 font-mono text-xs text-slate-500">
                {record.audit_locator}
              </p>
            )}
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg p-1.5 text-slate-500 hover:bg-slate-100 hover:text-slate-900 cursor-pointer"
            aria-label="关闭详情"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-6 space-y-6">
          {loading || !record ? (
            <div className="py-12 text-center text-sm text-slate-500">
              正在读取完整证据 JSON...
            </div>
          ) : (
            <>
              {/* Source & Prompt & Plan Chain */}
              <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                <div className="rounded-lg border border-slate-200 bg-slate-50 p-4 text-xs space-y-1.5">
                  <div className="flex items-center gap-1.5 font-semibold text-slate-800">
                    <FileText className="h-3.5 w-3.5 text-slate-500" />
                    Prompt 校验
                  </div>
                  <div className="font-mono text-[11px] text-slate-600 break-all">
                    {record.prompt.file}
                  </div>
                  <div className="flex items-center justify-between pt-1">
                    <span className="text-slate-600">SHA-256 重算一致</span>
                    <span className="inline-flex items-center gap-1 font-medium text-emerald-700">
                      <CheckCircle2 className="h-3.5 w-3.5" />
                      {String(record.prompt.sha256_matches_record)}
                    </span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-slate-600">User 字符数</span>
                    <span className="font-mono text-slate-900">
                      {record.prompt.user_chars_recomputed} (匹配:{' '}
                      {String(record.prompt.prompt_chars_matches_record)})
                    </span>
                  </div>
                  <div className="font-mono text-[10px] text-slate-400 break-all pt-1">
                    {record.prompt.sha256_recomputed}
                  </div>
                </div>

                <div className="rounded-lg border border-slate-200 bg-slate-50 p-4 text-xs space-y-1.5">
                  <div className="flex items-center gap-1.5 font-semibold text-slate-800">
                    <Layers className="h-3.5 w-3.5 text-slate-500" />
                    计划 / B0 绑定信息
                  </div>
                  {record.plan ? (
                    <>
                      <div className="font-mono text-[11px] text-slate-600 break-all">
                        {record.plan.file}
                      </div>
                      <div className="flex justify-between pt-1">
                        <span className="text-slate-600">身份在 plan 中</span>
                        <span className="font-mono text-emerald-700">
                          {String(record.plan.identity_in_plan)}
                        </span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-slate-600">
                          plan_seq / round_index
                        </span>
                        <span className="font-mono text-emerald-700">
                          {String(record.plan.plan_seq_matches_record)} /{' '}
                          {String(record.plan.round_index_matches_record)}
                        </span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-slate-600">
                          plan_sha256 / config_sha256
                        </span>
                        <span className="font-mono text-emerald-700">
                          {String(record.plan.plan_sha256_matches_record)} /{' '}
                          {String(record.plan.config_sha256_matches_snapshot_config)}
                        </span>
                      </div>
                    </>
                  ) : (
                    <div className="space-y-1 text-slate-600">
                      <p>B0 Legacy 无 plan.json 绑定。</p>
                      {record.b0 && (
                        <>
                          <p>
                            B0 序号 (ordinal):{' '}
                            <span className="font-mono font-semibold text-slate-900">
                              {record.b0.ordinal}
                            </span>{' '}
                            ({record.b0.mapped_via})
                          </p>
                          <p className="text-amber-700">
                            注：原脚本以 (experiment_id, repeat_index)
                            查找存在键冲突，经第二轮四元组复核确认 ordinal 正确。
                          </p>
                        </>
                      )}
                    </div>
                  )}
                </div>
              </div>

              {/* 7 Fields Detailed Breakdown */}
              <div className="space-y-4">
                <h4 className="text-sm font-semibold text-slate-900">
                  §7.1 七字段逐项证据与源码索引
                </h4>

                {(
                  Object.entries(record.fields) as Array<
                    [string, Record<string, unknown>]
                  >
                ).map(([fieldName, fieldData]) => {
                  const state = String(fieldData.state);
                  const value = fieldData.value;
                  const reason = fieldData.reason
                    ? String(fieldData.reason)
                    : null;
                  const caveat = fieldData.caveat
                    ? String(fieldData.caveat)
                    : null;
                  const codeRefs = (fieldData.code_refs as string[]) ?? [];
                  const evidence = fieldData.evidence as Record<string, unknown>;

                  return (
                    <div
                      key={fieldName}
                      className="rounded-xl border border-slate-200 bg-white p-4 shadow-xs"
                    >
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <div className="flex items-center gap-2">
                          <span className="font-mono text-sm font-semibold text-slate-900">
                            {fieldName}
                          </span>
                          <StateBadge state={state} />
                          {fieldName === 'memory_injected' &&
                            Array.isArray(value) &&
                            value.length > 0 && (
                              <span className="inline-flex items-center gap-1 rounded bg-amber-50 px-2 py-0.5 text-[11px] font-medium text-amber-800 ring-1 ring-amber-200">
                                <ShieldAlert className="h-3 w-3" />
                                status 为 inferred/unknown
                              </span>
                            )}
                        </div>
                        <div className="font-mono text-xs text-slate-700">
                          value:{' '}
                          <span className="rounded bg-slate-100 px-1.5 py-0.5 text-slate-900">
                            {fieldName === 'memory_injected' &&
                            Array.isArray(value)
                              ? `[${value.length} items]`
                              : JSON.stringify(value)}
                          </span>
                        </div>
                      </div>

                      {reason && (
                        <p className="mt-2 rounded bg-rose-50/60 px-3 py-2 text-xs text-rose-900">
                          {reason}
                        </p>
                      )}

                      {caveat && (
                        <p className="mt-2 rounded bg-amber-50/70 px-3 py-2 text-xs text-amber-900">
                          {caveat}
                        </p>
                      )}

                      {/* Special readable view for memory_injected entries */}
                      {fieldName === 'memory_injected' &&
                        record.fields.memory_injected.evidence.entries.length >
                          0 && (
                          <div className="mt-3 space-y-2">
                            <div className="text-xs font-medium text-slate-700">
                              注入记忆明细（Gold 唯一映射）
                            </div>
                            <div className="space-y-2">
                              {record.fields.memory_injected.evidence.entries.map(
                                (entry) => (
                                  <div
                                    key={entry.index}
                                    className="rounded-lg border border-slate-200 bg-slate-50 p-3 text-xs"
                                  >
                                    <div className="flex flex-wrap items-center justify-between gap-2">
                                      <span className="font-medium text-slate-900">
                                        #{entry.index} · {entry.prompt_type} ·{' '}
                                        {entry.subject_label ?? entry.prompt_subject}
                                      </span>
                                      <span className="font-mono text-[11px] text-emerald-700">
                                        gold[{entry.gold_index}] · type一致:{' '}
                                        {String(entry.type_matches_prompt)} ·
                                        strength一致:{' '}
                                        {String(entry.strength_matches_prompt)}
                                      </span>
                                    </div>
                                    <p className="mt-1.5 text-slate-700">
                                      {entry.content}
                                    </p>
                                  </div>
                                )
                              )}
                            </div>
                          </div>
                        )}

                      {/* Evidence JSON */}
                      <details className="mt-3">
                        <summary className="cursor-pointer text-xs font-medium text-slate-600 hover:text-slate-900">
                          展开原始 evidence 对象
                        </summary>
                        <pre className="mt-2 max-h-60 overflow-auto rounded-lg bg-slate-900 p-3 text-[11px] text-slate-100">
                          {JSON.stringify(
                            fieldName === 'memory_injected'
                              ? { value, evidence }
                              : evidence,
                            null,
                            2
                          )}
                        </pre>
                      </details>

                      {/* Code Refs */}
                      {codeRefs.length > 0 && (
                        <div className="mt-3 flex flex-wrap items-center gap-1.5">
                          <Code2 className="h-3.5 w-3.5 text-slate-400" />
                          {codeRefs.map((ref) => (
                            <span
                              key={ref}
                              className="rounded bg-slate-100 px-2 py-0.5 font-mono text-[11px] text-slate-700"
                            >
                              {ref}
                            </span>
                          ))}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
