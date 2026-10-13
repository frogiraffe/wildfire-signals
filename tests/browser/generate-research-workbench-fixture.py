"""Generate a complete all-original-source-replayed *synthetic* browser smoke dataset.

Uses existing government response fixtures with fake incident names. No genuine
third-party corroboration or independently verified fire labels are involved.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from test_calfire_incident_matrix import FullDetailCoverageTests
from fire_public.calfire_ambiguity_dossiers import build_from_matrix
from fire_public.calfire_lineage_audit import analyze as lineage
from fire_public.research_workbench import queue, offline_html


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    if not args.output.parent.is_dir() or args.output.exists() or args.output.is_symlink():
        raise ValueError("test HTML output must be a new file in an existing private temp directory")
    fixture = FullDetailCoverageTests("test_replay_full_source_url_partition_and_explicit_non_truth")
    fixture.setUp()
    try:
        original = build_from_matrix(fixture.full())
        report = queue(original, lineage(original))
        args.output.write_text(offline_html(report), encoding="utf-8")
        print(report["original_candidate_population"])
    finally:
        fixture.doCleanups()


if __name__ == "__main__":
    main()
