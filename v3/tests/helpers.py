# -*- coding: utf-8 -*-
"""Shared fixtures for V3 tests.

The tests read the frozen snapshot and the pinned source tree in read-only mode.
No test writes into v2/, v3/, the snapshot repository, or the source repository.
"""
from __future__ import annotations

import functools
import os
import pathlib
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from v3 import build_evidence_ledger_v3 as v3  # noqa: E402

AUDIT_ROOT = pathlib.Path(os.environ.get(
    "AUDIT_SNAPSHOT_ROOT", r"F:\somethingProject\graduation-preflight-audit"))
SOURCE_ROOT = pathlib.Path(os.environ.get(
    "AUDIT_SOURCE_ROOT", r"F:\somethingProject\dsbot-preflight"))
EXPECTED_SEGMENTS = {
    "main": 140,
    "supplementary-subject": 10,
    "supplementary-s7empty": 5,
    "b0-legacy": 10,
}


@functools.lru_cache(maxsize=1)
def built():
    if not (AUDIT_ROOT / "MANIFEST.sha256").is_file():
        raise RuntimeError("audit snapshot not found: " + str(AUDIT_ROOT))
    if not (SOURCE_ROOT / "experiments" / "graduation" / "run_experiment.py").is_file():
        raise RuntimeError("pinned source tree not found: " + str(SOURCE_ROOT))
    return v3.build_ledger(
        AUDIT_ROOT,
        SOURCE_ROOT,
        pathlib.Path("."),
        verify_baseline=True,
        expected_segments=EXPECTED_SEGMENTS,
        write=False,
    )


def rows():
    return built()["rows"]


def stats():
    return built()["stats"]
