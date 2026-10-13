"""Generate a browser smoke bundle from original-source-equivalent synthetic receipts."""
from __future__ import annotations
import argparse
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/"tests")]
from test_prospective_replay import ProspectiveTimeMachineTests
from fire_public.receipt_history import import_receipts
from fire_public.prospective_replay import replay,_write_private,open_archive


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("private_parent",type=Path)
    args=parser.parse_args()
    if not args.private_parent.is_dir():
        raise ValueError("temporary private parent directory required")
    fixture=ProspectiveTimeMachineTests("test_as_of_replay_preserves_source_gaps_and_status_reversal")
    fixture.setUp()
    try:
        fixture.add(0,name='EARLY <img src=x onerror=alert(1)>')
        fixture.add(6,agency="failed",listed=True)
        fixture.add(12,listed=False)
        fixture.add(18,name="FUTURE NAME",status="UC")
        import_receipts(fixture.store,fixture.receipts)
        fixture.store.connection.commit()
        db=open_archive(fixture.path)
        try:
            report=replay(db,at="2026-10-12T22:00:00Z")
        finally:
            db.close()
        dest=args.private_parent/"agency-console"
        _write_private(dest,report)
        print(dest/"index.html")
    finally:
        fixture.doCleanups()


if __name__=="__main__":
    main()
