"""Run the whole demo end to end (about 10 seconds)."""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STEPS = [
    "data/make_data.py",           # synthetic company, chats as webhook events, answer key
    "capture/ingest.py",           # webhook events -> one message table (voice notes transcribed)
    "pipeline/build_records.py",   # deals, commitments, proposed CRM updates with approval tiers
    "eval/eval_capture.py",        # score extraction against the answer key + messy set
    "pipeline/qualify.py",         # who gets a meeting, back-tested on unseen months
    "pipeline/handover.py",        # a rep resigned: hand over every open deal with context
    "pipeline/brief.py",           # 7:30am WhatsApp brief per rep + manager summary
    "report/build_report.py",      # before/after table and the demo report
]

for s in STEPS:
    print(f"\n== {s}")
    r = subprocess.run([sys.executable, "-W", "ignore", str(ROOT / s)], cwd=ROOT)
    if r.returncode:
        sys.exit(r.returncode)
print("\nDone. Open outputs/report.html")
