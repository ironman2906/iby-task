import sys
import json
from pathlib import Path

# Add project modules to Python path
sys.path.append(str(Path(__file__).parent.parent / "loading"))
sys.path.append(str(Path(__file__).parent))

from loaders import list_sessions, load_session_events
from boundary_detection import run_segmentation
from rule_labeler import label_all


DATA_B = Path(__file__).parent.parent.parent / "data" / "dataset_b"
OUTPUT_PATH = Path(__file__).parent.parent.parent / "outputs" / "segments.jsonl"


def main():
    sessions = list_sessions(DATA_B)

    print(f"Dataset B sessions found: {len(sessions)}")

    all_segments = []
    session_map = []

    for session_dir in sessions:
        session_id = session_dir.name

        events = load_session_events(session_dir)

        if not events:
            print(f"{session_id}: no events, skipped")
            continue

        # Locked Day 2 v2 segmentation
        segments = run_segmentation(events)

        start_idx = len(all_segments)
        all_segments.extend(segments)
        end_idx = len(all_segments)

        session_map.append(
            (session_id, start_idx, end_idx)
        )

        print(
            f"{session_id}: "
            f"{len(events)} events -> {len(segments)} segments"
        )

    print()
    print(f"Total segments before labeling: {len(all_segments)}")

    # Day 4 selected labeling method:
    # Deterministic rule-based labeler
    all_segments, method_counts = label_all(
        all_segments
    )

    print("Applied deterministic rule-based labeling.")

    print("Labeling methods used:")
    for method, count in method_counts.most_common():
        print(f"  {method}: {count}")

    OUTPUT_PATH.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    with open(
        OUTPUT_PATH,
        "w",
        encoding="utf-8"
    ) as f:

        for session_id, start_idx, end_idx in session_map:

            session_segments = all_segments[
                start_idx:end_idx
            ]

            for seg in session_segments:

                line = {
                    "session_id": session_id,
                    "start": seg["start_iso"],
                    "end": seg["end_iso"],
                    "label": seg["label"]
                }

                f.write(
                    json.dumps(
                        line,
                        ensure_ascii=False
                    ) + "\n"
                )

    print()
    print(
        f"Wrote {len(all_segments)} segments to:"
    )
    print(OUTPUT_PATH)


if __name__ == "__main__":
    main()