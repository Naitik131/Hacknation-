import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent

steps = [
    ("Build structured paper/author/grant links", "build_graph.py"),
    ("Build ClinVar variant links", "build_clinvar_graph.py"),
    ("Build patient organization links", "build_patient_organizations.py"),
    ("Merge every source into unified graph", "merge_graphs_enhanced.py"),
]

for label, script in steps:
    path = ROOT / script
    if not path.exists():
        print(f"\nSKIP: {script} not found")
        continue

    print("\n" + "=" * 70)
    print(label)
    print("=" * 70)

    result = subprocess.run([sys.executable, str(path)], cwd=ROOT)
    if result.returncode != 0:
        raise SystemExit(f"\nFAILED: {script}")

print("\nDONE.")
print("Now copy the refreshed unified graph into the frontend:")
print()
print("cp data/graph_nodes_unified.jsonl rare-disease-atlas/public/data/")
print("cp data/edges_unified.jsonl rare-disease-atlas/public/data/")
