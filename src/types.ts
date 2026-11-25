export type Segment =
  | 'main'
  | 'supplementary-subject'
  | 'supplementary-s7empty'
  | 'b0-legacy';

export interface EvidenceFieldBase<T = unknown> {
  state: 'derived' | 'unrecoverable' | 'unknown' | 'direct';
  value: T;
  reason?: string;
  caveat?: string;
  evidence: Record<string, unknown>;
  code_refs: string[];
}

export interface MemoryInjectedItem {
  memory_type: string | null;
  subject_key: string | null;
  strength: string | null;
  status: string | null;
}

export interface MemoryEvidenceEntry {
  index: number;
  prompt_subject?: string;
  prompt_type?: string;
  content: string;
  gold_index?: number;
  subject_label?: string;
  status_basis?: string;
  type_matches_prompt?: boolean;
  strength_matches_prompt?: boolean;
  error?: string;
  state?: string;
}

export interface EvidenceRecord {
  index: number;
  source: {
    repository: string;
    commit: string;
    result_file: string;
    line_number: number;
    sample_id: string;
    group: string;
    repeat_index: number;
    experiment_id: string;
    prompt_ref: string;
    prompt_sha256: string;
  };
  segment: Segment;
  audit_locator: string;
  b0: {
    ordinal: number | null;
    mapped_via: string;
    repeat_index_collides_across_run_dirs: boolean;
  } | null;
  prompt: {
    file: string;
    sha256_recomputed: string;
    sha256_matches_record: boolean;
    user_chars_recomputed: number;
    prompt_chars_matches_record: boolean;
  };
  plan: {
    file: string;
    identity_in_plan: boolean;
    plan_seq_matches_record: boolean;
    round_index_matches_record: boolean;
    plan_sha256_matches_record: boolean;
    config_sha256_matches_snapshot_config: boolean;
    plan_sha256: string;
  } | null;
  fields: {
    run_id: EvidenceFieldBase<null>;
    base_sha: EvidenceFieldBase<null>;
    knowledge_result_ids: EvidenceFieldBase<string[]>;
    memory_injected: EvidenceFieldBase<MemoryInjectedItem[]> & {
      evidence: {
        prompt_block_present: boolean;
        prompt_entry_count: number;
        expected_injected_count: number;
        entries: MemoryEvidenceEntry[];
        slot_enabled: boolean;
        subject_filter: string | null;
      };
    };
    short_term_injected: EvidenceFieldBase<boolean> & {
      evidence: {
        marker_present: boolean;
        slot_enabled: boolean;
        section_title: string;
        note: string;
      };
    };
    difficult_flag: EvidenceFieldBase<boolean> & {
      evidence: {
        latest_feedback: {
          index: number;
          task: string;
          status: string;
          reason: string | null;
          created_at: string | null;
        } | null;
        raw_condition_partial_and_reason: boolean;
        feedback_slot_enabled: boolean;
        b0_fixed_false: boolean;
        dynamic_rule_present_in_prompt: boolean;
        agree: boolean;
      };
    };
    data_kind: EvidenceFieldBase<string>;
  };
}

export interface ManifestEntry {
  filename: string;
  expectedSha256: string;
  actualSha256: string | null;
  bytes: number | null;
  status: 'matched' | 'mismatch' | 'migrated_to_node' | 'missing';
}

export interface B0AuditRow {
  index: number;
  audit_locator: string;
  sample_id: string;
  run_dir: string;
  experiment_id: string;
  repeat_index: number;
  ordinal: number | null;
  legacyKey: string;
  legacyKeyOwnerSample: string;
  legacyCollided: boolean;
  quadKey: string;
}

export interface OverviewResponse {
  baseline: {
    auditRepo: string;
    auditCommit: string;
    srcRepo: string;
    srcCommit: string;
    reviewRepo: string;
    reviewBaselineCommit: string;
    auditDate: string;
  };
  statsJson: {
    stats: Record<string, unknown>;
    checks: Record<string, boolean | number | unknown[] | Record<string, number>>;
  };
  liveVerification: {
    totalBytes: number;
    hasBom: boolean;
    physicalLines: number;
    parsedRecords: number;
    emptyLines: number;
    invalidJsonLines: number;
    uniqueLocators: number;
    uniqueTriples: number;
    uniqueFourTuples: number;
    promptHashMatched: number;
    promptCharsMatched: number;
    planMatched: number;
    fieldStateCounts: {
      direct: number;
      derived: number;
      unrecoverable: number;
      unknown: number;
      total: number;
    };
    segments: Record<string, number>;
    groups: Record<string, number>;
    samples: Record<string, number>;
  };
  manifest: ManifestEntry[];
  secondRoundDiagnostics: {
    b0Collision: {
      totalRows: number;
      legacyUniqueKeys: number;
      quadUniqueKeys: number;
      collidingRowsCount: number;
      rows: B0AuditRow[];
    };
    memoryStatusAudit: {
      recordsWithMemory: number;
      totalEntries: number;
      uniqueGoldMatches: number;
      typeMatches: number;
      strengthMatches: number;
      nonActiveCount: number;
      subfieldGrades: Array<{
        subfield: string;
        grade: 'externally_derived' | 'inferred_unknown';
        basis: string;
      }>;
    };
    shortTermSemantics: {
      blockPresentTrue: number;
      blockPresentFalse: number;
      payloadNonemptyTrue: number;
      payloadNonemptyFalse: number;
      flippingRecords: Array<{
        index: number;
        audit_locator: string;
        sample_id: string;
        group: string;
        repeat_index: number;
        segment: Segment;
      }>;
    };
  };
}

export interface RecordSummary {
  index: number;
  audit_locator: string;
  segment: Segment;
  sample_id: string;
  group: string;
  repeat_index: number;
  experiment_id: string;
  prompt_sha256_ok: boolean;
  prompt_chars_ok: boolean;
  plan_bound: boolean;
  memory_count: number;
  short_term_block_present: boolean;
  short_term_payload_nonempty: boolean;
  difficult_flag: boolean;
  data_kind: string;
  b0_ordinal: number | null;
}
