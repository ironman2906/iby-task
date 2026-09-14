import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent / "loading"))
from loaders import list_sessions, load_session_events

sys.path.append(str(Path(__file__).parent))
from boundary_detection import run_segmentation

DATA_A = Path(__file__).parent.parent.parent / "data" / "dataset_a"

def main():
    sessions = list_sessions(DATA_A)
    session_dir = sessions[0]
    events = load_session_events(session_dir)
    segments = run_segmentation(events)

    print(f"Session: {session_dir.name}")
    print(f"Total events: {len(events)}")
    print(f"Predicted segments: {len(segments)}")
    for i, seg in enumerate(segments[:10]):
        dur = (seg["end_ms"] - seg["start_ms"]) / 1000
        print(f"  [{i}] {seg['start_iso']} -> {seg['end_iso']} ({dur:.1f}s, {len(seg['events'])} events)")

if __name__ == "__main__":
    main()