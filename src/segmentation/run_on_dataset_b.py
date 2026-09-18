import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent / "loading"))
sys.path.append(str(Path(__file__).parent))

from loaders import list_sessions, load_session_events
from boundary_detection import run_segmentation

DATA_B = Path(__file__).parent.parent.parent / "data" / "dataset_b"


def main():
    sessions = list_sessions(DATA_B)
    total_segments = 0

    for session_dir in sessions:
        events = load_session_events(session_dir)
        if not events:
            print(f"WARNING: no events for {session_dir.name}")
            continue
        segments = run_segmentation(events)
        total_segments += len(segments)
        print(f"{session_dir.name}: {len(events)} events -> {len(segments)} segments")

    print(f"\nTotal segments across all Dataset B sessions: {total_segments}")


if __name__ == "__main__":
    main()