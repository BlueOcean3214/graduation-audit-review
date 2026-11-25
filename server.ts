import crypto from 'node:crypto';
import fs from 'node:fs/promises';
import path from 'node:path';
import express from 'express';
import { createServer as createViteServer } from 'vite';
import type {
  B0AuditRow,
  EvidenceRecord,
  ManifestEntry,
  OverviewResponse,
  RecordSummary,
} from './src/types.ts';

const ROOT_DIR = process.cwd();
const PORT = Number(process.env.PORT) || 3000;

interface LoadedAuditState {
  records: EvidenceRecord[];
  overview: OverviewResponse;
  summaries: RecordSummary[];
}

const DOC_ALLOWLIST: Record<string, { filename: string; title: string }> = {
  ledger: {
    filename: 'DERIVED-FIELD-EVIDENCE-LEDGER.md',
    title: '外部派生字段证据台账主报告',
  },
  addendum: {
    filename: 'SECOND-ROUND-INDEPENDENT-REVIEW-ADDENDUM.md',
    title: '第二轮独立复审补充说明',
  },
  readme: {
    filename: 'README.md',
    title: '独立复审包 README',
  },
};

async function loadAuditState(): Promise<LoadedAuditState> {
  const jsonlPath = path.join(ROOT_DIR, 'DERIVED-FIELD-EVIDENCE.jsonl');
  const statsPath = path.join(ROOT_DIR, '_stats.json');
  const manifestPath = path.join(ROOT_DIR, 'AUDIT-MANIFEST.sha256');

  const [jsonlBuf, statsRaw, manifestRaw] = await Promise.all([
    fs.readFile(jsonlPath),
    fs.readFile(statsPath, 'utf-8'),
    fs.readFile(manifestPath, 'utf-8'),
  ]);

  const hasBom =
    jsonlBuf.length >= 3 &&
    jsonlBuf[0] === 0xef &&
    jsonlBuf[1] === 0xbb &&
    jsonlBuf[2] === 0xbf;

  const jsonlText = jsonlBuf.toString('utf-8');
  const rawLines = jsonlText.split('\n');
  // Trailing newline produces an empty final split element; strip single trailing LF
  const physicalLines =
    rawLines.length > 0 && rawLines[rawLines.length - 1] === ''
      ? rawLines.slice(0, -1)
      : rawLines;

  let emptyLines = 0;
  let invalidJsonLines = 0;
  const records: EvidenceRecord[] = [];

  for (let i = 0; i < physicalLines.length; i++) {
    const rawLine = physicalLines[i].replace(/\r$/, '');
    if (rawLine.trim().length === 0) {
      emptyLines++;
      continue;
    }
    try {
      const parsed = JSON.parse(rawLine) as Omit<EvidenceRecord, 'index'>;
      records.push({
        index: records.length,
        ...parsed,
      });
    } catch {
      invalidJsonLines++;
    }
  }

  // Manifest SHA-256 live verification
  const manifestLines = manifestRaw
    .split(/\r?\n/)
    .map((l) => l.trim())
    .filter(Boolean);

  const manifest: ManifestEntry[] = [];
  for (const line of manifestLines) {
    const match = line.match(/^([0-9a-f]{64})\s{2}(.+)$/i);
    if (!match) continue;
    const [, expectedSha256, filename] = match;
    const safeBasename = path.basename(filename);
    const targetPath = path.join(ROOT_DIR, safeBasename);

    try {
      const fileBytes = await fs.readFile(targetPath);
      const actualSha256 = crypto
        .createHash('sha256')
        .update(fileBytes)
        .digest('hex');
      manifest.push({
        filename: safeBasename,
        expectedSha256,
        actualSha256,
        bytes: fileBytes.length,
        status: actualSha256 === expectedSha256 ? 'matched' : 'mismatch',
      });
    } catch {
      manifest.push({
        filename: safeBasename,
        expectedSha256,
        actualSha256: null,
        bytes: null,
        status:
          safeBasename === 'build_evidence_ledger.py'
            ? 'migrated_to_node'
            : 'missing',
      });
    }
  }

  // Live integrity verification across all 165 records
  const locators = new Set<string>();
  const triples = new Set<string>();
  const fourTuples = new Set<string>();
  const segments: Record<string, number> = {};
  const groups: Record<string, number> = {};
  const samples: Record<string, number> = {};

  let promptHashMatched = 0;
  let promptCharsMatched = 0;
  let planMatched = 0;
  const fieldStateCounts = {
    direct: 0,
    derived: 0,
    unrecoverable: 0,
    unknown: 0,
    total: 0,
  };

  let recordsWithMemory = 0;
  let totalEntries = 0;
  let uniqueGoldMatches = 0;
  let typeMatches = 0;
  let strengthMatches = 0;
  let nonActiveCount = 0;

  let blockPresentTrue = 0;
  let blockPresentFalse = 0;
  let payloadNonemptyTrue = 0;
  let payloadNonemptyFalse = 0;
  const flippingRecords: OverviewResponse['secondRoundDiagnostics']['shortTermSemantics']['flippingRecords'] =
    [];

  const b0Records: EvidenceRecord[] = [];
  const summaries: RecordSummary[] = [];

  for (const rec of records) {
    locators.add(rec.audit_locator);
    triples.add(
      `${rec.source.repository}|${rec.source.result_file}|${rec.source.line_number}`
    );
    fourTuples.add(
      `${rec.source.experiment_id}|${rec.source.sample_id}|${rec.source.group}|${rec.source.repeat_index}`
    );

    segments[rec.segment] = (segments[rec.segment] || 0) + 1;
    groups[rec.source.group] = (groups[rec.source.group] || 0) + 1;
    samples[rec.source.sample_id] = (samples[rec.source.sample_id] || 0) + 1;

    if (rec.prompt.sha256_matches_record) promptHashMatched++;
    if (rec.prompt.prompt_chars_matches_record) promptCharsMatched++;
    if (
      rec.plan &&
      rec.plan.identity_in_plan &&
      rec.plan.plan_sha256_matches_record &&
      rec.plan.config_sha256_matches_snapshot_config
    ) {
      planMatched++;
    }

    const fieldList = Object.values(rec.fields);
    for (const f of fieldList) {
      fieldStateCounts.total++;
      if (f.state === 'direct') fieldStateCounts.direct++;
      else if (f.state === 'derived') fieldStateCounts.derived++;
      else if (f.state === 'unrecoverable') fieldStateCounts.unrecoverable++;
      else fieldStateCounts.unknown++;
    }

    const memEntries = rec.fields.memory_injected.evidence.entries || [];
    if (memEntries.length > 0) recordsWithMemory++;
    totalEntries += memEntries.length;
    for (const entry of memEntries) {
      if (entry.state !== 'unknown' && entry.gold_index !== undefined) {
        uniqueGoldMatches++;
      }
      if (entry.type_matches_prompt) typeMatches++;
      if (entry.strength_matches_prompt) strengthMatches++;
    }
    for (const val of rec.fields.memory_injected.value || []) {
      if (val.status !== 'active') nonActiveCount++;
    }

    const shortBlockPresent = Boolean(rec.fields.short_term_injected.value);
    const isS7Empty = rec.segment === 'supplementary-s7empty';
    const shortPayloadNonempty = shortBlockPresent && !isS7Empty;

    if (shortBlockPresent) blockPresentTrue++;
    else blockPresentFalse++;

    if (shortPayloadNonempty) payloadNonemptyTrue++;
    else payloadNonemptyFalse++;

    if (shortBlockPresent !== shortPayloadNonempty) {
      flippingRecords.push({
        index: rec.index,
        audit_locator: rec.audit_locator,
        sample_id: rec.source.sample_id,
        group: rec.source.group,
        repeat_index: rec.source.repeat_index,
        segment: rec.segment,
      });
    }

    if (rec.segment === 'b0-legacy') {
      b0Records.push(rec);
    }

    summaries.push({
      index: rec.index,
      audit_locator: rec.audit_locator,
      segment: rec.segment,
      sample_id: rec.source.sample_id,
      group: rec.source.group,
      repeat_index: rec.source.repeat_index,
      experiment_id: rec.source.experiment_id,
      prompt_sha256_ok: rec.prompt.sha256_matches_record,
      prompt_chars_ok: rec.prompt.prompt_chars_matches_record,
      plan_bound: Boolean(rec.plan?.identity_in_plan),
      memory_count: memEntries.length,
      short_term_block_present: shortBlockPresent,
      short_term_payload_nonempty: shortPayloadNonempty,
      difficult_flag: Boolean(rec.fields.difficult_flag.value),
      data_kind: rec.fields.data_kind.value,
      b0_ordinal: rec.b0?.ordinal ?? null,
    });
  }

  // Simulate B0 mapping collision in Python load_b0_map() (S5 lines read before S7 lines)
  const b0SortedBySample = [...b0Records].sort((a, b) => {
    if (a.source.sample_id !== b.source.sample_id) {
      return a.source.sample_id.localeCompare(b.source.sample_id);
    }
    return (a.b0?.ordinal ?? 0) - (b.b0?.ordinal ?? 0);
  });

  const legacyMap = new Map<string, string>();
  const quadMap = new Map<string, string>();
  for (const r of b0SortedBySample) {
    const runDir = r.source.result_file.split('/')[1] ?? '';
    const legacyKey = `${r.source.experiment_id}::r${r.source.repeat_index}`;
    const quadKey = `${r.source.sample_id}::${r.source.experiment_id}::r${r.source.repeat_index}::${runDir}`;
    legacyMap.set(legacyKey, r.source.sample_id);
    quadMap.set(quadKey, r.source.sample_id);
  }

  const b0Rows: B0AuditRow[] = b0SortedBySample.map((r) => {
    const runDir = r.source.result_file.split('/')[1] ?? '';
    const legacyKey = `${r.source.experiment_id}::r${r.source.repeat_index}`;
    const quadKey = `${r.source.sample_id}::${r.source.experiment_id}::r${r.source.repeat_index}::${runDir}`;
    const ownerSample = legacyMap.get(legacyKey) ?? '';
    return {
      index: r.index,
      audit_locator: r.audit_locator,
      sample_id: r.source.sample_id,
      run_dir: runDir,
      experiment_id: r.source.experiment_id,
      repeat_index: r.source.repeat_index,
      ordinal: r.b0?.ordinal ?? null,
      legacyKey,
      legacyKeyOwnerSample: ownerSample,
      legacyCollided: ownerSample !== r.source.sample_id,
      quadKey,
    };
  });

  const statsJson = JSON.parse(statsRaw) as OverviewResponse['statsJson'];

  const overview: OverviewResponse = {
    baseline: {
      auditRepo: 'BlueOcean3214/graduation-preflight-audit',
      auditCommit: '7b99ad96db78167c490874af9c4b48484b6d6ef0',
      srcRepo: 'BlueOcean3214/AI-Study-Assistant',
      srcCommit: 'df155a5c145297bc5e6a085636fadfd6185586bd',
      reviewRepo: 'BlueOcean3214/graduation-audit-review',
      reviewBaselineCommit: '92ba6f9952f55b7d0906fb0e0a79481670b8000d',
      auditDate: '2026-11-24',
    },
    statsJson,
    liveVerification: {
      totalBytes: jsonlBuf.length,
      hasBom,
      physicalLines: physicalLines.length,
      parsedRecords: records.length,
      emptyLines,
      invalidJsonLines,
      uniqueLocators: locators.size,
      uniqueTriples: triples.size,
      uniqueFourTuples: fourTuples.size,
      promptHashMatched,
      promptCharsMatched,
      planMatched,
      fieldStateCounts,
      segments,
      groups,
      samples,
    },
    manifest,
    secondRoundDiagnostics: {
      b0Collision: {
        totalRows: b0Rows.length,
        legacyUniqueKeys: legacyMap.size,
        quadUniqueKeys: quadMap.size,
        collidingRowsCount: b0Rows.filter((row) => row.legacyCollided).length,
        rows: b0Rows,
      },
      memoryStatusAudit: {
        recordsWithMemory,
        totalEntries,
        uniqueGoldMatches,
        typeMatches,
        strengthMatches,
        nonActiveCount,
        subfieldGrades: [
          {
            subfield: 'memory_type',
            grade: 'externally_derived',
            basis: 'Prompt 携带 type 字段，与 Gold 170/170 一致',
          },
          {
            subfield: 'subject_key',
            grade: 'externally_derived',
            basis: 'Prompt 携带 subject_label；通过 content 170/170 唯一映射 Gold 得到归一化 subject_key',
          },
          {
            subfield: 'strength',
            grade: 'externally_derived',
            basis: 'Prompt 携带 strength 字段，与 Gold 170/170 一致',
          },
          {
            subfield: 'status',
            grade: 'inferred_unknown',
            basis: 'Prompt 剥离了 status（_sanitize_memory）；active 由 get_learning_memory→retrieve(status="active") 代码路径与 Gold 共同推定，且缺 base_sha 与 injected.json',
          },
        ],
      },
      shortTermSemantics: {
        blockPresentTrue,
        blockPresentFalse,
        payloadNonemptyTrue,
        payloadNonemptyFalse,
        flippingRecords,
      },
    },
  };

  return { records, overview, summaries };
}

async function startServer() {
  const auditState = await loadAuditState();
  const app = express();

  app.get('/api/overview', (_req, res) => {
    res.json(auditState.overview);
  });

  app.get('/api/records', (req, res) => {
    const segment = typeof req.query.segment === 'string' ? req.query.segment : '';
    const group = typeof req.query.group === 'string' ? req.query.group : '';
    const sample = typeof req.query.sample === 'string' ? req.query.sample : '';
    const q =
      typeof req.query.q === 'string' ? req.query.q.trim().toLowerCase() : '';
    const memoryOnly = req.query.memoryOnly === 'true';
    const difficultOnly = req.query.difficultOnly === 'true';
    const shortPredicate =
      req.query.shortPredicate === 'payload_nonempty'
        ? 'payload_nonempty'
        : 'block_present';
    const shortFilter =
      typeof req.query.short === 'string' ? req.query.short : '';

    const filtered = auditState.summaries.filter((item) => {
      if (segment && item.segment !== segment) return false;
      if (group && item.group !== group) return false;
      if (sample && item.sample_id !== sample) return false;
      if (memoryOnly && item.memory_count === 0) return false;
      if (difficultOnly && !item.difficult_flag) return false;
      if (shortFilter === 'true' || shortFilter === 'false') {
        const val =
          shortPredicate === 'payload_nonempty'
            ? item.short_term_payload_nonempty
            : item.short_term_block_present;
        if (String(val) !== shortFilter) return false;
      }
      if (q) {
        const haystack =
          `${item.audit_locator} ${item.sample_id} ${item.group} ${item.segment} ${item.experiment_id}`.toLowerCase();
        if (!haystack.includes(q)) return false;
      }
      return true;
    });

    res.json({
      total: auditState.summaries.length,
      filteredCount: filtered.length,
      items: filtered,
    });
  });

  app.get('/api/records/:index', (req, res) => {
    const idx = Number.parseInt(req.params.index, 10);
    if (
      !Number.isInteger(idx) ||
      idx < 0 ||
      idx >= auditState.records.length
    ) {
      res.status(404).json({ error: 'Record not found' });
      return;
    }
    res.json(auditState.records[idx]);
  });

  app.get('/api/docs/:docId', async (req, res) => {
    const entry = DOC_ALLOWLIST[req.params.docId];
    if (!entry) {
      res.status(404).json({ error: 'Document not found' });
      return;
    }
    try {
      const content = await fs.readFile(
        path.join(ROOT_DIR, entry.filename),
        'utf-8'
      );
      res.json({
        id: req.params.docId,
        filename: entry.filename,
        title: entry.title,
        content,
      });
    } catch {
      res.status(500).json({ error: 'Failed to read document' });
    }
  });

  if (process.env.NODE_ENV === 'production') {
    const distDir = path.join(ROOT_DIR, 'dist');
    app.use(express.static(distDir));
    app.get('*', (_req, res) => {
      res.sendFile(path.join(distDir, 'index.html'));
    });
  } else {
    const vite = await createViteServer({
      server: { middlewareMode: true, hmr: false },
      appType: 'spa',
    });
    app.use(vite.middlewares);
  }

  app.listen(PORT, '0.0.0.0', () => {
    console.log(`Graduation Audit Review server listening on http://0.0.0.0:${PORT}`);
  });
}

startServer().catch((err) => {
  console.error('Failed to start server:', err);
  process.exit(1);
});
