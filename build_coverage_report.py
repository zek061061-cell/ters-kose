"""Generate a deployable coverage snapshot from the central data files."""

import json
from pathlib import Path

from coverage import build_coverage


output = Path(__file__).with_name("data") / "coverage_report.json"
report = {"ok": True, **build_coverage()}
output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps(report["summary"], ensure_ascii=False))
