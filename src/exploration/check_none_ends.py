import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent / "loading"))

from loaders import list_sessions, load_gt_manifest, extract_true_segments

DATA_A = Path(__file__).parent.parent.parent / "data" / "dataset_a"

none_end_count = 0
total = 0

for session_dir in list_sessions(DATA_A):
    gt_manifest = load_gt_manifest(session_dir)
    segments = extract_true_segments(gt_manifest)

    for seg in segments:
        total += 1

        if seg["end"] is None:
            none_end_count += 1

            print(
                f"{session_dir.name}: "
                f"[{seg['process_code']}] "
                f"continues_to_next={seg['continues_to_next']} "
                f"seq={seg['seq']} "
                f"phase={seg['phase']}"
            )

print(f"\n{none_end_count}/{total} executions have no end_ts")