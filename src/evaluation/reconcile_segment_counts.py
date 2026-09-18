import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent / "loading"))
sys.path.append(str(Path(__file__).parent.parent / "segmentation"))

from loaders import list_sessions, load_session_events
from boundary_detection import run_segmentation


DATA_A = (
    Path(__file__).parent.parent.parent
    / "data"
    / "dataset_a"
)


def main():
    sessions = list_sessions(DATA_A)

    # Use the same first 20 Dataset A sessions used for clustering validation.
    sessions = sessions[:20]

    total_segments = 0
    total_events = 0

    print(f"Dataset A sessions checked: {len(sessions)}")
    print()

    for session_dir in sessions:
        session_id = session_dir.name

        events = load_session_events(session_dir)
        segments = run_segmentation(events)

        total_events += len(events)
        total_segments += len(segments)

        print(
            f"{session_id}: "
            f"{len(events)} events -> "
            f"{len(segments)} segments"
        )

    print()
    print("=" * 60)
    print(f"Total events:   {total_events}")
    print(f"Total segments: {total_segments}")
    print("=" * 60)


if __name__ == "__main__":
    main()